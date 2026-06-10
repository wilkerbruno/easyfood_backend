import os
from datetime import datetime
from flask import Blueprint, jsonify, request, current_app, render_template
from backend.models import db, Order, Payment, Customer, Restaurant
from backend.stripe_payment import criar_payment_intent, STRIPE_PUBLIC_KEY, verificar_webhook

payment_bp = Blueprint("payment", __name__, url_prefix="/api/v1/payment")


def _get_customer():
    token = request.headers.get("X-Session-Token") or \
            (request.get_json(silent=True) or {}).get("session_token")
    if not token:
        return None
    return Customer.query.filter_by(session_token=token).first()


@payment_bp.post("/orders/<int:order_id>/pay")
def pay_order(order_id):
    customer = _get_customer()
    if not customer:
        return jsonify({"error": "Sessão inválida"}), 401
    order = Order.query.filter_by(id=order_id, customer_id=customer.id).first_or_404()
    if order.payment_status == "paid":
        return jsonify({"error": "Pedido já pago"}), 400
    if order.status == "cancelled":
        return jsonify({"error": "Pedido cancelado"}), 400
    data   = request.get_json() or {}
    method = data.get("method", "credit_card")
    restaurant = db.session.get(Restaurant, order.restaurant_id)
    if not restaurant:
        return jsonify({"error": "Restaurante não encontrado"}), 404
    try:
        intent    = criar_payment_intent(order, restaurant, method)
        pi_id     = intent["id"]
        pi_status = intent["status"]
        payment = Payment(
            order_id    = order.id,
            customer_id = customer.id,
            method      = method,
            amount      = order.total,
            status      = "approved" if pi_status == "succeeded" else "pending",
            gateway_ref = pi_id,
            paid_at     = datetime.utcnow() if pi_status == "succeeded" else None,
        )
        db.session.add(payment)
        order.payment_status = "paid" if pi_status == "succeeded" else "pending"
        order.payment_method = method
        db.session.commit()
        return jsonify({
            "payment":       payment.to_dict(),
            "stripe_status": pi_status,
            "client_secret": intent["client_secret"],
            "public_key":    STRIPE_PUBLIC_KEY,
            "message":       "Pagamento iniciado!",
        }), 200
    except Exception as e:
        current_app.logger.error(f"[PAGAMENTO] Erro: {e}")
        return jsonify({"error": "Erro ao processar pagamento", "detail": str(e)}), 500


@payment_bp.post("/webhook/stripe")
def stripe_webhook():
    payload   = request.get_data()
    signature = request.headers.get("Stripe-Signature", "")
    try:
        event = verificar_webhook(payload, signature) or (request.get_json() or {})
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    if event.get("type") == "payment_intent.succeeded":
        pi       = event.get("data", {}).get("object", {})
        order_id = pi.get("metadata", {}).get("order_id")
        if order_id:
            order = db.session.get(Order, int(order_id))
            if order:
                order.payment_status = "paid"
                p = Payment.query.filter_by(
                    gateway_ref=pi.get("id")
                ).order_by(Payment.id.desc()).first()
                if p:
                    p.status  = "approved"
                    p.paid_at = datetime.utcnow()
                db.session.commit()
    return jsonify({"ok": True}), 200


@payment_bp.get("/orders/<int:order_id>/status")
def payment_status(order_id):
    customer = _get_customer()
    if not customer:
        return jsonify({"error": "Sessão inválida"}), 401
    order   = Order.query.filter_by(id=order_id, customer_id=customer.id).first_or_404()
    payment = Payment.query.filter_by(order_id=order.id).order_by(Payment.id.desc()).first()
    return jsonify({
        "order_id":       order.id,
        "payment_status": order.payment_status,
        "payment":        payment.to_dict() if payment else None,
    }), 200


@payment_bp.get("/checkout")
def checkout_page():
    return render_template("checkout.html")


@payment_bp.post("/confirm")
def confirm_payment():
    import stripe as _stripe
    data  = request.get_json() or {}
    oid   = data.get("order_id")
    pi_id = data.get("payment_intent_id")
    if not oid or not pi_id:
        return jsonify({"error": "Dados invalidos"}), 400
    try:
        _stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
        intent = _stripe.PaymentIntent.retrieve(pi_id)
        if intent.status == "succeeded":
            order = db.session.get(Order, int(oid))
            if order:
                order.payment_status = "paid"
                p = Payment.query.filter_by(
                    gateway_ref=pi_id
                ).order_by(Payment.id.desc()).first()
                if p:
                    p.status  = "approved"
                    p.paid_at = datetime.utcnow()
                db.session.commit()
            return jsonify({"ok": True}), 200
        return jsonify({"ok": False, "status": intent.status}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
