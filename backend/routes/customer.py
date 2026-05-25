# =============================================================
#  EASYFOOD - Rotas Públicas (Cliente)
# =============================================================

import secrets
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request, current_app
from sqlalchemy import func

from backend.models import (
    db, FoodCourt, Restaurant, Customer,
    Order, OrderItem, OrderStatusHistory,
    Payment, MenuItem, Review,
)

customer_bp = Blueprint("customer", __name__, url_prefix="/api/v1/customer")


# ── Helpers ───────────────────────────────────────────────────

def get_customer_from_token(token: str) -> Customer | None:
    return Customer.query.filter_by(session_token=token).first()


def require_customer(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.headers.get("X-Session-Token")
        if not token:
            return jsonify({"error": "Token de sessão obrigatório"}), 401
        customer = get_customer_from_token(token)
        if not customer or customer.expires_at < datetime.utcnow():
            return jsonify({"error": "Sessão inválida ou expirada"}), 401
        return f(customer, *args, **kwargs)
    return wrapper


# ── Escanear QR Code e iniciar sessão ─────────────────────────

@customer_bp.post("/session/start")
def start_session():
    """Escanear QR Code → inicia sessão do cliente na praça."""
    data = request.get_json()
    qr_token    = data.get("qr_code_token", "").strip()
    table_number = data.get("table_number", "")
    name        = data.get("name", "")
    phone       = data.get("phone", "")

    court = FoodCourt.query.filter_by(qr_code_token=qr_token, is_active=True).first()
    if not court:
        return jsonify({"error": "QR Code inválido"}), 404

    hours = current_app.config.get("CUSTOMER_SESSION_HOURS", 4)
    customer = Customer(
        name          = name,
        phone         = phone,
        session_token = secrets.token_hex(32),
        table_number  = table_number,
        food_court_id = court.id,
        expires_at    = datetime.utcnow() + timedelta(hours=hours),
    )
    db.session.add(customer)
    db.session.commit()

    return jsonify({
        "session_token": customer.session_token,
        "food_court":    court.to_dict(),
        "expires_at":    customer.expires_at.isoformat(),
    }), 201


# ── Listar restaurantes da praça ───────────────────────────────

@customer_bp.get("/restaurants")
@require_customer
def list_restaurants(customer: Customer):
    restaurants = (
        Restaurant.query
        .filter_by(food_court_id=customer.food_court_id, is_active=True)
        .all()
    )
    return jsonify([r.to_dict() for r in restaurants])


# ── Cardápio completo de um restaurante ───────────────────────

@customer_bp.get("/restaurants/<int:restaurant_id>/menu")
@require_customer
def get_menu(customer: Customer, restaurant_id: int):
    restaurant = Restaurant.query.filter_by(
        id=restaurant_id, food_court_id=customer.food_court_id, is_active=True
    ).first_or_404()
    return jsonify(restaurant.to_dict(include_menu=True))


# ── Criar pedido ──────────────────────────────────────────────

@customer_bp.post("/orders")
@require_customer
def create_order(customer: Customer):
    data          = request.get_json()
    restaurant_id = data.get("restaurant_id")
    items_data    = data.get("items", [])
    notes         = data.get("notes", "")

    restaurant = Restaurant.query.filter_by(
        id=restaurant_id, food_court_id=customer.food_court_id, is_active=True, is_open=True
    ).first()
    if not restaurant:
        return jsonify({"error": "Restaurante não encontrado ou fechado"}), 400

    if not items_data:
        return jsonify({"error": "Pedido deve conter pelo menos 1 item"}), 400

    order = Order(
        customer_id   = customer.id,
        restaurant_id = restaurant.id,
        food_court_id = customer.food_court_id,
        table_number  = customer.table_number,
        notes         = notes,
    )
    db.session.add(order)
    db.session.flush()

    subtotal = 0.0
    for item_data in items_data:
        menu_item = MenuItem.query.filter_by(
            id=item_data.get("menu_item_id"), restaurant_id=restaurant.id,
            is_active=True, is_available=True
        ).first()
        if not menu_item:
            db.session.rollback()
            return jsonify({"error": f"Item {item_data.get('menu_item_id')} indisponível"}), 400

        qty       = max(1, int(item_data.get("quantity", 1)))
        sub       = float(menu_item.price) * qty
        subtotal += sub

        order_item = OrderItem(
            order_id     = order.id,
            menu_item_id = menu_item.id,
            quantity     = qty,
            unit_price   = menu_item.price,
            subtotal     = sub,
            notes        = item_data.get("notes", ""),
        )
        db.session.add(order_item)

    order.subtotal = subtotal
    order.total    = subtotal

    history = OrderStatusHistory(order_id=order.id, status="pending", notes="Pedido criado")
    db.session.add(history)
    db.session.commit()

    return jsonify(order.to_dict(include_items=True)), 201


# ── Listar pedidos do cliente ─────────────────────────────────

@customer_bp.get("/orders")
@require_customer
def list_orders(customer: Customer):
    orders = customer.orders.order_by(Order.created_at.desc()).all()
    return jsonify([o.to_dict(include_items=True) for o in orders])


# ── Status de um pedido ───────────────────────────────────────

@customer_bp.get("/orders/<int:order_id>")
@require_customer
def get_order(customer: Customer, order_id: int):
    order = Order.query.filter_by(id=order_id, customer_id=customer.id).first_or_404()
    return jsonify(order.to_dict(include_items=True))


# ── Processar pagamento ───────────────────────────────────────

@customer_bp.post("/orders/<int:order_id>/pay")
@require_customer
def pay_order(customer: Customer, order_id: int):
    order = Order.query.filter_by(id=order_id, customer_id=customer.id).first_or_404()

    if order.payment_status == "paid":
        return jsonify({"error": "Pedido já pago"}), 400
    if order.status == "cancelled":
        return jsonify({"error": "Pedido cancelado"}), 400

    data   = request.get_json()
    method = data.get("method", "pix")

    payment = Payment(
        order_id    = order.id,
        customer_id = customer.id,
        method      = method,
        amount      = order.total,
        status      = "approved",          # mock: em prod integrar gateway real
        pix_qr_code = "00020101..." if method == "pix" else None,
        paid_at     = datetime.utcnow(),
    )
    db.session.add(payment)

    order.payment_status = "paid"
    order.payment_method = method

    db.session.commit()
    return jsonify({"message": "Pagamento realizado", "payment": payment.to_dict()})


# ── Avaliar pedido ────────────────────────────────────────────

@customer_bp.post("/orders/<int:order_id>/review")
@require_customer
def review_order(customer: Customer, order_id: int):
    order = Order.query.filter_by(
        id=order_id, customer_id=customer.id, status="delivered"
    ).first_or_404()

    if Review.query.filter_by(order_id=order.id).first():
        return jsonify({"error": "Pedido já avaliado"}), 400

    data   = request.get_json()
    rating = data.get("rating")
    if not rating or rating not in range(1, 6):
        return jsonify({"error": "Avaliação deve ser entre 1 e 5"}), 400

    review = Review(
        order_id=order.id, customer_id=customer.id,
        restaurant_id=order.restaurant_id,
        rating=rating, comment=data.get("comment", ""),
    )
    db.session.add(review)
    db.session.commit()
    return jsonify({"message": "Avaliação registrada"}), 201
