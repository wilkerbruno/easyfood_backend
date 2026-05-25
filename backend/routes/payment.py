# =============================================================
#  EASYFOOD - Rotas de Pagamento com Split
#  10% plataforma | 90% restaurante via Mercado Pago
# =============================================================

import json
import urllib.request
import urllib.error
from datetime import datetime
from flask import Blueprint, jsonify, request, current_app

from backend.models import (
    db, Order, Payment, PaymentSplit,
    PlatformConfig, RestaurantBankAccount, Customer,
)

payment_bp = Blueprint("payment", __name__, url_prefix="/api/v1/payment")

MP_BASE = "https://api.mercadopago.com"


# ── Helpers Mercado Pago ──────────────────────────────────────

def mp_request(method, path, token, data=None):
    """Chamada HTTP para a API do Mercado Pago."""
    headers = {
        "Authorization":  f"Bearer {token}",
        "Content-Type":   "application/json",
        "X-Idempotency-Key": f"easyfood-{datetime.utcnow().timestamp()}",
    }
    payload = json.dumps(data).encode() if data else None
    req = urllib.request.Request(
        MP_BASE + path, data=payload, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:    body = json.loads(e.read().decode())
        except: body = {"error": str(e)}
        return e.code, body
    except Exception as e:
        return 0, {"error": str(e)}


def calc_split(total: float, fee_percent: float):
    """Calcula split: retorna (plataforma, restaurante)."""
    platform = round(total * fee_percent / 100, 2)
    restaurant = round(total - platform, 2)
    return platform, restaurant


# ── Criar PIX (Mercado Pago) ──────────────────────────────────

def create_mp_pix(order, config: PlatformConfig, bank: RestaurantBankAccount):
    """
    Cria cobrança PIX no Mercado Pago com split automático.
    Documentação: https://www.mercadopago.com.br/developers/pt/docs
    """
    token = config.mp_access_token
    if not token:
        return None, "Token Mercado Pago da plataforma não configurado"

    fee_pct   = float(config.platform_fee_percent)
    total     = float(order.total)
    plat_amt, rest_amt = calc_split(total, fee_pct)

    # Marketplace split: aplicação retém fee, repassa resto ao collector do restaurante
    payload = {
        "transaction_amount": total,
        "description":        f"EasyFood - Pedido #{order.id}",
        "payment_method_id":  "pix",
        "payer": {
            "email": "cliente@easyfood.com",   # email do cliente (idealmente do user logado)
        },
        "application_fee": plat_amt,           # taxa retida pela plataforma
    }

    # Se o restaurante tiver collector_id configurado, adiciona split
    if bank and bank.mp_collector_id and config.mp_collector_id:
        payload["marketplace_fee"] = plat_amt

    status, body = mp_request("POST", "/v1/payments", token, payload)
    if status in (200, 201):
        return body, None
    return None, body.get("message", "Erro ao criar PIX no Mercado Pago")


# ── Rota: Iniciar pagamento ───────────────────────────────────

def _require_session(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.headers.get("X-Session-Token")
        if not token:
            return jsonify({"error": "Sessão obrigatória"}), 401
        customer = Customer.query.filter_by(session_token=token).first()
        if not customer or customer.expires_at < datetime.utcnow():
            return jsonify({"error": "Sessão inválida"}), 401
        return f(customer, *args, **kwargs)
    return wrapper


@payment_bp.post("/orders/<int:order_id>/pay")
@_require_session
def pay(customer, order_id: int):
    order = Order.query.filter_by(id=order_id, customer_id=customer.id).first_or_404()

    if order.payment_status == "paid":
        return jsonify({"error": "Pedido já pago"}), 400
    if order.status == "cancelled":
        return jsonify({"error": "Pedido cancelado"}), 400

    data   = request.get_json() or {}
    method = data.get("method", "pix")

    # Carrega configurações
    config = PlatformConfig.query.first()
    bank   = RestaurantBankAccount.query.filter_by(
        restaurant_id=order.restaurant_id
    ).first()

    fee_pct   = float(config.platform_fee_percent) if config else 10.0
    total     = float(order.total)
    plat_amt, rest_amt = calc_split(total, fee_pct)

    # ── Processar pagamento ───────────────────────────────────
    mp_payment_id = None
    pix_qr_code   = None
    pix_qr_base64 = None

    if method == "pix":
        if config and config.mp_access_token:
            # Pagamento real via Mercado Pago
            mp_data, err = create_mp_pix(order, config, bank)
            if err:
                return jsonify({"error": f"Erro no gateway: {err}"}), 502
            mp_payment_id = str(mp_data.get("id", ""))
            point = mp_data.get("point_of_interaction", {})
            txn   = point.get("transaction_data", {})
            pix_qr_code   = txn.get("qr_code", "PIX_QR_DEMO")
            pix_qr_base64 = txn.get("qr_code_base64", "")
        else:
            # Modo simulação (sem token MP configurado)
            pix_qr_code = f"00020101021226770014BR.GOV.BCB.PIX0136EASYFOOD-DEMO-{order.id}-QR5204000053039865802BR5924EASYFOOD6009SAO PAULO62070503***6304DEMO"

    # Registra pagamento
    payment = Payment(
        order_id     = order.id,
        customer_id  = customer.id,
        method       = method,
        amount       = total,
        status       = "approved",   # em produção: pending até webhook confirmar
        gateway_ref  = mp_payment_id,
        pix_qr_code  = pix_qr_code,
        paid_at      = datetime.utcnow(),
    )
    db.session.add(payment)
    db.session.flush()

    # Registra split
    split = PaymentSplit(
        payment_id           = payment.id,
        order_id             = order.id,
        restaurant_id        = order.restaurant_id,
        total_amount         = total,
        platform_fee_percent = fee_pct,
        platform_amount      = plat_amt,
        restaurant_amount    = rest_amt,
        mp_payment_id        = mp_payment_id,
        status               = "processed",
        processed_at         = datetime.utcnow(),
    )
    db.session.add(split)

    order.payment_status = "paid"
    order.payment_method = method
    db.session.commit()

    return jsonify({
        "message":         "Pagamento realizado",
        "payment":         payment.to_dict(),
        "split": {
            "total":            total,
            "platform_fee_pct": fee_pct,
            "platform_amount":  plat_amt,
            "restaurant_amount": rest_amt,
        },
        "pix_qr_code":   pix_qr_code,
        "pix_qr_base64": pix_qr_base64,
    })


# ── Webhook Mercado Pago ──────────────────────────────────────

@payment_bp.post("/webhook/mercadopago")
def mp_webhook():
    """Recebe notificações do Mercado Pago sobre pagamentos."""
    data   = request.get_json() or {}
    action = data.get("action", "")
    mp_id  = str(data.get("data", {}).get("id", ""))

    if action == "payment.updated" and mp_id:
        config = PlatformConfig.query.first()
        if config and config.mp_access_token:
            status, body = mp_request("GET", f"/v1/payments/{mp_id}",
                                      config.mp_access_token)
            if status == 200:
                mp_status = body.get("status")
                payment   = Payment.query.filter_by(gateway_ref=mp_id).first()
                if payment:
                    if mp_status == "approved":
                        payment.status       = "approved"
                        payment.paid_at      = datetime.utcnow()
                        order = Order.query.get(payment.order_id)
                        if order:
                            order.payment_status = "paid"
                        split = PaymentSplit.query.filter_by(
                            payment_id=payment.id
                        ).first()
                        if split:
                            split.status       = "processed"
                            split.processed_at = datetime.utcnow()
                    elif mp_status in ("rejected", "cancelled"):
                        payment.status = "rejected"
                    db.session.commit()

    return jsonify({"status": "ok"})
