# =============================================================
#  EASYFOOD - Rotas de Pagamento (Stripe)
# =============================================================
import os
from datetime import datetime
from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required
from backend.models import db, Order, Payment, Customer
from backend.stripe_payment import (
    criar_payment_intent_pix,
    criar_payment_intent_cartao,
    STRIPE_PUBLIC_KEY,
    verificar_webhook,
)

payment_bp = Blueprint("payment", __name__, url_prefix="/api/v1/payment")


def _get_customer_from_session():
    session_token = request.headers.get("X-Session-Token") or \
                    (request.get_json(silent=True) or {}).get("session_token")
    if not session_token:
        return None
    return Customer.query.filter_by(session_token=session_token).first()


# ── Processar pagamento ───────────────────────────────────────
@payment_bp.post("/orders/<int:order_id>/pay")
def pay_order(order_id: int):
    customer = _get_customer_from_session()
    if not customer:
        return jsonify({"error": "Sessão inválida"}), 401

    order = Order.query.filter_by(
        id=order_id, customer_id=customer.id
    ).first_or_404()

    if order.payment_status == "paid":
        return jsonify({"error": "Pedido já pago"}), 400
    if order.status == "cancelled":
        return jsonify({"error": "Pedido cancelado"}), 400

    data              = request.get_json() or {}
    method            = data.get("method", "pix")
    payment_method_id = data.get("payment_method_id")
    restaurant        = order.restaurant

    try:
        if method == "pix":
            intent    = criar_payment_intent_pix(order, restaurant)
            pi_id     = intent["id"]
            pi_status = intent["status"]
            pix_data  = intent.get("next_action", {}).get(
                            "pix_display_qr_code", {})
            pix_qr    = pix_data.get("data", "")

            payment = Payment(
                order_id         = order.id,
                customer_id      = customer.id,
                method           = "pix",
                amount           = order.total,
                status           = "approved" if pi_status == "succeeded" else "pending",
                pix_qr_code      = pix_qr,
                pagarme_order_id = pi_id,
                paid_at          = datetime.utcnow() if pi_status == "succeeded" else None,
            )
            db.session.add(payment)
            order.payment_status = "paid" if pi_status == "succeeded" else "pending"
            order.payment_method = "pix"
            db.session.commit()

            resp = {
                "payment":        payment.to_dict(),
                "stripe_status":  pi_status,
                "client_secret":  intent["client_secret"],
                "public_key":     STRIPE_PUBLIC_KEY,
                "message":        "PIX gerado! Escaneie o QR Code para pagar.",
            }
            if pix_qr:
                resp["pix_qr_code"]  = pix_qr
                resp["pix_qr_image"] = (
                    f"https://api.qrserver.com/v1/create-qr-code/"
                    f"?size=300x300&data={pix_qr}&bgcolor=ffffff&color=000000"
                )
                resp["expires_in"] = 3600
            return jsonify(resp), 200

        elif method in ("credit_card", "debit_card"):
            if not payment_method_id:
                return jsonify({
                    "error":      "payment_method_id obrigatório para cartão",
                    "public_key": STRIPE_PUBLIC_KEY,
                }), 400

            intent    = criar_payment_intent_cartao(order, restaurant, payment_method_id)
            pi_id     = intent["id"]
            pi_status = intent["status"]

            payment = Payment(
                order_id         = order.id,
                customer_id      = customer.id,
                method           = method,
                amount           = order.total,
                status           = "approved" if pi_status == "succeeded" else "pending",
                pagarme_order_id = pi_id,
                paid_at          = datetime.utcnow() if pi_status == "succeeded" else None,
            )
            db.session.add(payment)
            order.payment_status = "paid" if pi_status == "succeeded" else "pending"
            order.payment_method = method
            db.session.commit()

            return jsonify({
                "payment":        payment.to_dict(),
                "stripe_status":  pi_status,
                "client_secret":  intent["client_secret"],
                "message": "Pagamento aprovado!" if pi_status == "succeeded"
                           else "Aguardando confirmação.",
            }), 200

        else:
            return jsonify({"error": f"Método '{method}' não suportado"}), 400

    except Exception as e:
        current_app.logger.error(f"[PAGAMENTO] Erro Stripe: {e}")
        payment = Payment(
            order_id    = order.id,
            customer_id = customer.id,
            method      = method,
            amount      = order.total,
            status      = "error",
        )
        db.session.add(payment)
        db.session.commit()
        return jsonify({"error": "Erro ao processar pagamento", "detail": str(e)}), 500


# ── Webhook Stripe ────────────────────────────────────────────
@payment_bp.post("/webhook/stripe")
def stripe_webhook():
    payload   = request.get_data()
    signature = request.headers.get("Stripe-Signature", "")
    try:
        event = verificar_webhook(payload, signature)
        if event is None:
            event = request.get_json() or {}
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    if event.get("type") == "payment_intent.succeeded":
        pi       = event.get("data", {}).get("object", {})
        pi_id    = pi.get("id")
        order_id = pi.get("metadata", {}).get("order_id")
        if order_id:
            order = Order.query.get(int(order_id))
            if order:
                order.payment_status = "paid"
                payment = Payment.query.filter_by(
                    pagarme_order_id=pi_id
                ).order_by(Payment.id.desc()).first()
                if payment:
                    payment.status  = "approved"
                    payment.paid_at = datetime.utcnow()
                db.session.commit()

    return jsonify({"ok": True}), 200


# ── Consultar status ──────────────────────────────────────────
@payment_bp.get("/orders/<int:order_id>/status")
def payment_status(order_id: int):
    customer = _get_customer_from_session()
    if not customer:
        return jsonify({"error": "Sessão inválida"}), 401

    order = Order.query.filter_by(
        id=order_id, customer_id=customer.id
    ).first_or_404()

    payment = Payment.query.filter_by(
        order_id=order.id
    ).order_by(Payment.id.desc()).first()

    return jsonify({
        "order_id":       order.id,
        "payment_status": order.payment_status,
        "payment":        payment.to_dict() if payment else None,
    }), 200
