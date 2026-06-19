# =============================================================
#  EASYFOOD - Rotas de Pagamento (APPMAX)
# =============================================================
import os
from datetime import datetime
from flask import Blueprint, jsonify, request, current_app, render_template
from backend.models import db, Order, Payment, Customer, Restaurant
from backend.appmax_payment import (
    criar_cartao_appmax, criar_pix_appmax,
    verificar_pagamento_appmax, pagamento_confirmado_appmax,
    processar_webhook_appmax,
)

payment_bp = Blueprint("payment", __name__, url_prefix="/api/v1/payment")


def _get_customer():
    token = request.headers.get("X-Session-Token") or \
            (request.get_json(silent=True) or {}).get("session_token")
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
    method     = data.get("method", "credit-card")  # credit-card | pix | cash
    restaurant = db.session.get(Restaurant, order.restaurant_id)
    if not restaurant:
        return jsonify({"error": "Restaurante não encontrado"}), 404

    # Pagamento em dinheiro — confirma direto sem gateway
    if method == "cash":
        payment = Payment(
            order_id    = order.id,
            customer_id = customer.id,
            method      = "cash",
            amount      = order.total,
            status      = "pending",
            gateway_ref = f"cash_{order.id}",
            paid_at     = None,
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
        if method == "pix":
            result = criar_pix_appmax(order, restaurant)
            payment = Payment(
                order_id    = order.id,
                customer_id = customer.id,
                method      = "pix",
                amount      = order.total,
                status      = "pending",
                gateway_ref = result.get("appmax_id", ""),
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
                "appmax_id":    result.get("appmax_id"),
                "expires_at":   result.get("expires_at"),
                "message":      "PIX gerado! Escaneie o QR Code para pagar.",
            }), 200

        else:  # credit-card
            result = criar_cartao_appmax(order, restaurant)
            payment = Payment(
                order_id    = order.id,
                customer_id = customer.id,
                method      = "credit-card",
                amount      = order.total,
                status      = "pending",
                gateway_ref = result.get("appmax_id", ""),
            )
            db.session.add(payment)
            order.payment_status = "pending"
            order.payment_method = "credit-card"
            db.session.commit()
            return jsonify({
                "payment":       payment.to_dict(),
                "method":        "credit-card",
                "checkout_url":  result.get("checkout_url"),
                "payment_token": result.get("payment_token"),
                "appmax_id":     result.get("appmax_id"),
                "message":       "Checkout APPMAX gerado!",
            }), 200

    except Exception as e:
        current_app.logger.error(f"[PAGAMENTO APPMAX] Erro: {e}")
        return jsonify({"error": "Erro ao processar pagamento", "detail": str(e)}), 500


# ── Webhook APPMAX ───────────────────────────────────────────

@payment_bp.post("/webhook/appmax")
def appmax_webhook():
    """Recebe notificações de pagamento da APPMAX."""
    payload = request.get_json(silent=True) or {}
    try:
        result   = processar_webhook_appmax(payload)
        order_id = result.get("order_id")
        status   = result.get("status")

        if order_id and status == "paid":
            order = db.session.get(Order, int(order_id))
            if order:
                order.payment_status = "paid"
                payment = Payment.query.filter_by(
                    gateway_ref=result.get("appmax_id")
                ).order_by(Payment.id.desc()).first()
                if payment:
                    payment.status  = "approved"
                    payment.paid_at = datetime.utcnow()
                db.session.commit()
                current_app.logger.info(f"[APPMAX] Pedido {order_id} pago via webhook")

    except Exception as e:
        current_app.logger.error(f"[APPMAX WEBHOOK] Erro: {e}")

    return jsonify({"ok": True}), 200


# ── Confirmar pagamento manualmente ─────────────────────────

@payment_bp.post("/confirm")
def confirm_payment():
    """
    Confirma pagamento consultando a APPMAX diretamente.
    Evita marcar como pago sem verificação real.
    """
    data      = request.get_json() or {}
    order_id  = data.get("order_id")
    appmax_id = data.get("appmax_id")

    if not order_id or not appmax_id:
        return jsonify({"error": "Dados inválidos"}), 400

    try:
        confirmado = pagamento_confirmado_appmax(str(appmax_id))
        if confirmado:
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
            return jsonify({"ok": True}), 200
        return jsonify({"ok": False, "message": "Pagamento ainda não confirmado"}), 200
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
