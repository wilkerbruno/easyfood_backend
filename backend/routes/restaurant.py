# =============================================================
#  EASYFOOD - Rotas do Restaurante
# =============================================================

import bcrypt
from datetime import datetime, date, timedelta
from functools import wraps

from flask import Blueprint, jsonify, request
from flask_jwt_extended import (
    create_access_token, jwt_required,
    get_jwt_identity, get_jwt,
)
from sqlalchemy import func

from backend.models import (
    TableQRCode,
    db, Employee, Restaurant, Order, OrderItem,
    OrderStatusHistory, MenuItem, MenuCategory,
    InventoryItem, InventoryMovement, Review, Payment,
)

restaurant_bp = Blueprint("restaurant", __name__, url_prefix="/api/v1/restaurant")


# ── Helpers ───────────────────────────────────────────────────

def current_employee():
    emp_id = get_jwt_identity()          # vem como string
    return Employee.query.get(int(emp_id))


def require_role(*roles):
    def decorator(f):
        @wraps(f)
        @jwt_required()
        def wrapper(*args, **kwargs):
            claims = get_jwt()
            if claims.get("role") not in roles:
                return jsonify({"error": "Acesso negado"}), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ── Auth ──────────────────────────────────────────────────────

@restaurant_bp.post("/auth/login")
def login():
    data     = request.get_json() or {}
    email    = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "E-mail e senha sao obrigatorios"}), 400

    # Busca o funcionário mais recente com este email
    employee = Employee.query.filter_by(email=email)        .order_by(Employee.id.desc()).first()

    if not employee:
        return jsonify({"error": "Credenciais invalidas"}), 401

    if not employee.is_active:
        return jsonify({"error": "Funcionario desativado"}), 401

    try:
        pwd_ok = bcrypt.checkpw(
            password.encode("utf-8"),
            employee.password_hash.encode("utf-8")
        )
    except Exception as e:
        return jsonify({"error": f"Erro ao verificar senha: {str(e)}"}), 500

    if not pwd_ok:
        return jsonify({"error": "Credenciais invalidas"}), 401

    token = create_access_token(
        identity=str(employee.id),
        additional_claims={
            "role":          employee.role,
            "restaurant_id": employee.restaurant_id,
        },
    )
    return jsonify({"access_token": token, "employee": employee.to_dict()})


# ── Dashboard ─────────────────────────────────────────────────

@restaurant_bp.get("/dashboard")
@jwt_required()
def dashboard():
    emp   = current_employee()
    rid   = emp.restaurant_id
    today = datetime.utcnow().date()
    start = datetime.combine(today, datetime.min.time())

    total_sales = (
        db.session.query(func.sum(Order.total))
        .filter(Order.restaurant_id == rid,
                Order.payment_status == "paid",
                Order.created_at >= start)
        .scalar() or 0
    )
    orders_today = Order.query.filter(
        Order.restaurant_id == rid, Order.created_at >= start).count()
    pending   = Order.query.filter_by(restaurant_id=rid, status="pending").count()
    preparing = Order.query.filter_by(restaurant_id=rid, status="preparing").count()
    low_stock = InventoryItem.query.filter(
        InventoryItem.restaurant_id == rid,
        InventoryItem.is_active == True,
        InventoryItem.quantity   <= InventoryItem.min_quantity,
    ).count()
    expiry_warning = InventoryItem.query.filter(
        InventoryItem.restaurant_id == rid,
        InventoryItem.is_active     == True,
        InventoryItem.expiry_date   != None,
        InventoryItem.expiry_date   <= date.today() + timedelta(days=7),
        InventoryItem.expiry_date   >= date.today(),
    ).count()

    return jsonify({
        "total_sales_today": float(total_sales),
        "orders_today":      orders_today,
        "pending_orders":    pending,
        "preparing_orders":  preparing,
        "low_stock_alerts":  low_stock,
        "expiry_alerts":     expiry_warning,
    })


# ── Pedidos ───────────────────────────────────────────────────

@restaurant_bp.get("/orders")
@jwt_required()
def list_orders():
    emp    = current_employee()
    status = request.args.get("status", "").strip()

    query = Order.query.filter_by(restaurant_id=emp.restaurant_id)
    if status:
        query = query.filter_by(status=status)

    orders = query.order_by(Order.created_at.desc()).limit(200).all()
    return jsonify([o.to_dict(include_items=True) for o in orders])


@restaurant_bp.patch("/orders/<int:order_id>/status")
@jwt_required()
def update_order_status(order_id):
    emp   = current_employee()
    order = Order.query.filter_by(
        id=order_id, restaurant_id=emp.restaurant_id
    ).first_or_404()

    data       = request.get_json() or {}
    new_status = data.get("status", "")
    notes      = data.get("notes", "")

    valid = ["confirmed", "preparing", "ready", "delivered", "cancelled"]
    if new_status not in valid:
        return jsonify({"error": f"Status invalido. Use: {valid}"}), 400

    order.status = new_status
    history = OrderStatusHistory(
        order_id=order.id, status=new_status,
        changed_by=emp.id, notes=notes,
    )
    db.session.add(history)
    db.session.commit()
    return jsonify(order.to_dict(include_items=True))


# ── Cardapio ─────────────────────────────────────────────────

@restaurant_bp.get("/menu")
@jwt_required()
def get_menu():
    emp = current_employee()
    restaurant = Restaurant.query.get(emp.restaurant_id)
    return jsonify(restaurant.to_dict(include_menu=True))


@restaurant_bp.post("/menu/items")
@require_role("admin")
def create_menu_item():
    emp  = current_employee()
    data = request.get_json() or {}
    item = MenuItem(
        restaurant_id    = emp.restaurant_id,
        category_id      = data.get("category_id"),
        name             = data["name"],
        description      = data.get("description"),
        price            = data["price"],
        image_url        = data.get("image_url"),
        preparation_time = data.get("preparation_time"),
    )
    db.session.add(item)
    db.session.commit()
    return jsonify(item.to_dict()), 201


@restaurant_bp.put("/menu/items/<int:item_id>")
@require_role("admin")
def update_menu_item(item_id):
    emp  = current_employee()
    item = MenuItem.query.filter_by(
        id=item_id, restaurant_id=emp.restaurant_id
    ).first_or_404()
    data = request.get_json() or {}
    for field in ["name","description","price","image_url","preparation_time","is_available","category_id"]:
        if field in data:
            setattr(item, field, data[field])
    db.session.commit()
    return jsonify(item.to_dict())


@restaurant_bp.delete("/menu/items/<int:item_id>")
@require_role("admin")
def delete_menu_item(item_id):
    emp  = current_employee()
    item = MenuItem.query.filter_by(
        id=item_id, restaurant_id=emp.restaurant_id
    ).first_or_404()
    item.is_active = False
    db.session.commit()
    return jsonify({"message": "Item removido"})


# ── Estoque ───────────────────────────────────────────────────

@restaurant_bp.get("/inventory")
@jwt_required()
def list_inventory():
    emp   = current_employee()
    items = InventoryItem.query.filter_by(
        restaurant_id=emp.restaurant_id, is_active=True
    ).order_by(InventoryItem.name).all()
    return jsonify([i.to_dict() for i in items])


@restaurant_bp.post("/inventory")
@require_role("admin")
def create_inventory_item():
    emp  = current_employee()
    data = request.get_json() or {}

    expiry = None
    if data.get("expiry_date"):
        try:
            expiry = datetime.strptime(data["expiry_date"], "%Y-%m-%d").date()
        except ValueError:
            pass

    item = InventoryItem(
        restaurant_id = emp.restaurant_id,
        name          = data["name"],
        category      = data.get("category"),
        unit_type     = data.get("unit_type", "unit"),
        quantity      = float(data.get("quantity", 0)),
        min_quantity  = float(data.get("min_quantity", 0)),
        cost_price    = data.get("cost_price"),
        supplier      = data.get("supplier"),
        expiry_date   = expiry,
        batch_number  = data.get("batch_number"),
        location      = data.get("location"),
        notes         = data.get("notes"),
    )
    db.session.add(item)
    db.session.flush()

    if float(data.get("quantity", 0)) > 0:
        mov = InventoryMovement(
            inventory_item_id = item.id,
            restaurant_id     = emp.restaurant_id,
            employee_id       = emp.id,
            movement_type     = "in",
            quantity          = item.quantity,
            quantity_before   = 0,
            quantity_after    = item.quantity,
            reason            = "Cadastro inicial",
        )
        db.session.add(mov)

    db.session.commit()
    return jsonify(item.to_dict()), 201


@restaurant_bp.put("/inventory/<int:item_id>")
@require_role("admin")
def update_inventory_item(item_id):
    emp  = current_employee()
    item = InventoryItem.query.filter_by(
        id=item_id, restaurant_id=emp.restaurant_id, is_active=True
    ).first_or_404()
    data = request.get_json() or {}
    for field in ["name","category","unit_type","min_quantity","cost_price","supplier","batch_number","location","notes"]:
        if field in data:
            setattr(item, field, data[field])
    if data.get("expiry_date"):
        try:
            item.expiry_date = datetime.strptime(data["expiry_date"], "%Y-%m-%d").date()
        except ValueError:
            pass
    db.session.commit()
    return jsonify(item.to_dict())


@restaurant_bp.post("/inventory/<int:item_id>/movement")
@jwt_required()
def add_movement(item_id):
    emp  = current_employee()
    item = InventoryItem.query.filter_by(
        id=item_id, restaurant_id=emp.restaurant_id, is_active=True
    ).first_or_404()

    data     = request.get_json() or {}
    mov_type = data.get("movement_type")
    qty      = float(data.get("quantity", 0))
    reason   = data.get("reason", "")

    if mov_type not in ("in", "out", "adjustment", "waste"):
        return jsonify({"error": "movement_type invalido"}), 400
    if qty <= 0:
        return jsonify({"error": "Quantidade deve ser maior que zero"}), 400

    qty_before = float(item.quantity)
    if mov_type == "in":
        qty_after = qty_before + qty
    elif mov_type in ("out", "waste"):
        qty_after = max(0, qty_before - qty)
    else:
        qty_after = qty   # adjustment = valor absoluto

    mov = InventoryMovement(
        inventory_item_id = item.id,
        restaurant_id     = emp.restaurant_id,
        employee_id       = emp.id,
        movement_type     = mov_type,
        quantity          = qty,
        quantity_before   = qty_before,
        quantity_after    = qty_after,
        reason            = reason,
    )
    item.quantity = qty_after
    db.session.add(mov)
    db.session.commit()
    return jsonify({"message": "Movimentacao registrada", "item": item.to_dict()})


@restaurant_bp.get("/inventory/<int:item_id>/history")
@jwt_required()
def inventory_history(item_id):
    emp  = current_employee()
    item = InventoryItem.query.filter_by(
        id=item_id, restaurant_id=emp.restaurant_id
    ).first_or_404()
    movements = item.movements.order_by(InventoryMovement.created_at.desc()).limit(50).all()
    return jsonify([{
        "id": m.id, "movement_type": m.movement_type,
        "quantity": float(m.quantity),
        "quantity_before": float(m.quantity_before),
        "quantity_after":  float(m.quantity_after),
        "reason":     m.reason,
        "created_at": m.created_at.isoformat(),
    } for m in movements])


# ── Relatorios ────────────────────────────────────────────────

@restaurant_bp.get("/reports/sales")
@require_role("admin")
def sales_report():
    emp       = current_employee()
    date_from = request.args.get("date_from")
    date_to   = request.args.get("date_to")

    query = Order.query.filter_by(
        restaurant_id=emp.restaurant_id, payment_status="paid"
    )
    if date_from:
        try:
            query = query.filter(Order.created_at >= datetime.strptime(date_from, "%Y-%m-%d"))
        except ValueError:
            pass
    if date_to:
        try:
            query = query.filter(Order.created_at <= datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1))
        except ValueError:
            pass

    orders = query.all()
    total  = sum(float(o.total) for o in orders)

    item_sales = (
        db.session.query(
            MenuItem.name,
            func.sum(OrderItem.quantity).label("qty_sold"),
            func.sum(OrderItem.subtotal).label("revenue"),
        )
        .join(OrderItem, OrderItem.menu_item_id == MenuItem.id)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            Order.restaurant_id  == emp.restaurant_id,
            Order.payment_status == "paid",
        )
        .group_by(MenuItem.id, MenuItem.name)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(10)
        .all()
    )

    return jsonify({
        "period":        {"from": date_from, "to": date_to},
        "total_orders":  len(orders),
        "total_revenue": total,
        "top_items": [
            {"name": r.name, "qty_sold": int(r.qty_sold), "revenue": float(r.revenue)}
            for r in item_sales
        ],
    })


# ── QR Codes de Mesa ──────────────────────────────────────────

@restaurant_bp.get("/qrcodes")
@jwt_required()
def list_qrcodes():
    emp  = current_employee()
    qrs  = TableQRCode.query.filter_by(
        restaurant_id=emp.restaurant_id, is_active=True
    ).order_by(TableQRCode.table_number).all()
    return jsonify([q.to_dict() for q in qrs])


@restaurant_bp.post("/qrcodes")
@require_role("admin")
def create_qrcode():
    import secrets
    emp  = current_employee()
    rest = Restaurant.query.get(emp.restaurant_id)
    data = request.get_json() or {}

    table  = data.get("table_number", "").strip()
    label  = data.get("label", f"Mesa {table}").strip()
    qty    = min(int(data.get("quantity", 1)), 50)

    if not table:
        return jsonify({"error": "Numero da mesa e obrigatorio"}), 400

    created = []
    for i in range(qty):
        suffix = f"-{i+1}" if qty > 1 else ""
        qr = TableQRCode(
            food_court_id = rest.food_court_id,
            restaurant_id = emp.restaurant_id,
            table_number  = f"{table}{suffix}",
            qr_token      = secrets.token_hex(16),
            label         = f"{label}{suffix}",
        )
        db.session.add(qr)
        created.append(qr)

    db.session.commit()
    return jsonify([q.to_dict() for q in created]), 201


@restaurant_bp.delete("/qrcodes/<int:qr_id>")
@require_role("admin")
def delete_qrcode(qr_id):
    emp = current_employee()
    qr  = TableQRCode.query.filter_by(
        id=qr_id, restaurant_id=emp.restaurant_id
    ).first_or_404()
    qr.is_active = False
    db.session.commit()
    return jsonify({"message": "QR Code removido"})
