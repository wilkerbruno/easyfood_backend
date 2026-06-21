# =============================================================
#  EASYFOOD - Rotas de Pagamento com Split APPMAX
# =============================================================
from datetime import datetime
from flask import Blueprint, jsonify, request, current_app
from backend.models import db, Order, Payment, Customer, Restaurant
from backend.appmax_payment import (
    criar_pix, criar_cartao,
    pagamento_aprovado, processar_webhook,
)

payment_bp = Blueprint("payment", __name__, url_prefix="/api/v1/payment")


def _get_customer():
    token = (
        request.headers.get("X-Session-Token") or
        (request.get_json(silent=True) or {}).get("session_token")
    )
    if not token:
        return None
    return Customer.query.filter_by(session_token=token).first()


# ── Iniciar pagamento ────────────────────────────────────────

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

    data       = request.get_json() or {}
    method     = data.get("method", "pix")  # pix | credit_card | cash
    restaurant = db.session.get(Restaurant, order.restaurant_id)

    if not restaurant:
        return jsonify({"error": "Restaurante não encontrado"}), 404

    # ── Dinheiro ──────────────────────────────────────────────
    if method == "cash":
        payment = Payment(
            order_id    = order.id,
            customer_id = customer.id,
            method      = "cash",
            amount      = order.total,
            status      = "pending",
            gateway_ref = f"cash_{order.id}",
        )
        db.session.add(payment)
        order.payment_status = "pending"
        order.payment_method = "cash"
        db.session.commit()
        return jsonify({
            "payment": payment.to_dict(),
            "method":  "cash",
            "message": "Pagamento em dinheiro registrado. Aguarde o caixa.",
        }), 200

    try:
        # ── PIX ───────────────────────────────────────────────
        if method == "pix":
            result = criar_pix(order, restaurant, customer)

            payment = Payment(
                order_id    = order.id,
                customer_id = customer.id,
                method      = "pix",
                amount      = order.total,
                status      = "pending",
                gateway_ref = result.get("appmax_order_id", ""),
            )
            db.session.add(payment)
            order.payment_status = "pending"
            order.payment_method = "pix"
            db.session.commit()

            return jsonify({
                "payment":      payment.to_dict(),
                "method":       "pix",
                "pix_qr_code":  result.get("pix_qr_code"),
                "pix_qr_url":   result.get("pix_qr_url"),
                "appmax_id":    result.get("appmax_order_id"),
                "expires_at":   result.get("expires_at"),
                "split_ativo":  bool(restaurant.appmax_recipient_id),
                "message":      "PIX gerado! Escaneie o QR Code para pagar.",
            }), 200

        # ── Cartão ────────────────────────────────────────────
        elif method == "credit_card":
            card_token   = data.get("card_token")
            installments = int(data.get("installments", 1))
            result = criar_cartao(order, restaurant, customer, card_token, installments)

            payment = Payment(
                order_id    = order.id,
                customer_id = customer.id,
                method      = "credit_card",
                amount      = order.total,
                status      = "pending",
                gateway_ref = result.get("appmax_order_id", ""),
            )
            db.session.add(payment)
            order.payment_status = "pending"
            order.payment_method = "credit_card"
            db.session.commit()

            return jsonify({
                "payment":       payment.to_dict(),
                "method":        "credit_card",
                "appmax_id":     result.get("appmax_order_id"),
                "checkout_url":  result.get("checkout_url"),
                "payment_token": result.get("payment_token"),
                "split_ativo":   bool(restaurant.appmax_recipient_id),
                "message":       "Pagamento iniciado!",
            }), 200

        else:
            return jsonify({"error": f"Método '{method}' inválido. Use: pix, credit_card, cash"}), 400

    except Exception as e:
        current_app.logger.error(f"[PAGAMENTO] Erro: {e}")
        return jsonify({"error": "Erro ao processar pagamento", "detail": str(e)}), 500


# ── Webhook APPMAX ───────────────────────────────────────────

@payment_bp.post("/webhook/appmax")
def appmax_webhook():
    """Recebe notificações de pagamento da APPMAX."""
    payload = request.get_json(silent=True) or {}
    try:
        result    = processar_webhook(payload)
        order_id  = result.get("order_id")
        status    = result.get("status")
        appmax_id = result.get("appmax_id")

        if order_id and status == "paid":
            order = db.session.get(Order, int(order_id))
            if order and order.payment_status != "paid":
                order.payment_status = "paid"
                payment = Payment.query.filter_by(
                    gateway_ref=appmax_id
                ).order_by(Payment.id.desc()).first()
                if payment:
                    payment.status  = "approved"
                    payment.paid_at = datetime.utcnow()
                db.session.commit()
                current_app.logger.info(f"[APPMAX WEBHOOK] Pedido {order_id} confirmado como pago")

        elif order_id and status in ("failed", "cancelled"):
            order = db.session.get(Order, int(order_id))
            if order:
                order.payment_status = status
                db.session.commit()

    except Exception as e:
        current_app.logger.error(f"[APPMAX WEBHOOK] Erro: {e}")

    return jsonify({"ok": True}), 200


# ── Confirmar pagamento manualmente ──────────────────────────

@payment_bp.post("/confirm")
def confirm_payment():
    """Verifica pagamento consultando APPMAX antes de marcar como pago."""
    data      = request.get_json() or {}
    order_id  = data.get("order_id")
    appmax_id = data.get("appmax_id")

    if not order_id or not appmax_id:
        return jsonify({"error": "order_id e appmax_id são obrigatórios"}), 400

    try:
        aprovado = pagamento_aprovado(str(appmax_id))
        if aprovado:
            order = db.session.get(Order, int(order_id))
            if order:
                order.payment_status = "paid"
                payment = Payment.query.filter_by(
                    gateway_ref=str(appmax_id)
                ).order_by(Payment.id.desc()).first()
                if payment:
                    payment.status  = "approved"
                    payment.paid_at = datetime.utcnow()
                db.session.commit()
            return jsonify({"ok": True, "paid": True}), 200
        return jsonify({"ok": True, "paid": False, "message": "Pagamento ainda não confirmado"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Status do pedido ─────────────────────────────────────────

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
