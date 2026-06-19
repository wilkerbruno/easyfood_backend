# =============================================================
#  EASYFOOD - Integração APPMAX (Split de Pagamento)
#  Docs: https://docs.appmax.com.br
# =============================================================
import os
import requests

APPMAX_API_URL = "https://admin.appmax.com.br/api/v3"
APPMAX_API_KEY = os.getenv("APPMAX_API_KEY", "")


def _headers():
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {APPMAX_API_KEY}",
    }


# ── Criar pedido de pagamento ────────────────────────────────

def criar_pedido_appmax(order, restaurant, method="credit-card"):
    """
    Cria um pedido na APPMAX e retorna os dados para o cliente pagar.

    method: "credit-card" | "pix" | "boleto"
    """
    if not APPMAX_API_KEY:
        raise RuntimeError("APPMAX_API_KEY não configurada")

    items = []
    for item in order.items:
        items.append({
            "sku":         str(item.menu_item_id),
            "description": item.name,
            "quantity":    item.quantity,
            "price":       int(item.unit_price * 100),  # em centavos
        })

    # Dados do pedido
    payload = {
        "order": {
            "order_id":  str(order.id),
            "ip":        "127.0.0.1",
            "total":     int(order.total_amount * 100),  # em centavos
            "freight":   0,
            "discount":  0,
            "products":  items,
        },
        "customer": {
            "name":  order.customer.name or "Cliente EasyFood",
            "email": order.customer.email or f"cliente{order.customer.id}@easyfood.com",
            "phone": (order.customer.phone or "00000000000").replace(" ", "").replace("-", ""),
            "tax_id": "00000000000",  # CPF placeholder — idealmente coletar do cliente
        },
        "payment": {
            "type": method,
        },
    }

    resp = requests.post(
        f"{APPMAX_API_URL}/order",
        json=payload,
        headers=_headers(),
        timeout=30,
    )

    if not resp.ok:
        raise RuntimeError(f"APPMAX erro {resp.status_code}: {resp.text}")

    data = resp.json()
    return data


def criar_pix_appmax(order, restaurant):
    """Cria pagamento PIX via APPMAX e retorna qr_code e qr_code_url."""
    data = criar_pedido_appmax(order, restaurant, method="pix")
    payment = data.get("data", {}).get("payment", {})
    return {
        "gateway":     "appmax",
        "method":      "pix",
        "pix_qr_code": payment.get("qr_code_text") or payment.get("qr_code"),
        "pix_qr_url":  payment.get("qr_code_url"),
        "appmax_id":   data.get("data", {}).get("id"),
        "expires_at":  payment.get("expires_at"),
    }


def criar_cartao_appmax(order, restaurant):
    """
    Cria pagamento por cartão via APPMAX.
    Retorna dados para exibir o checkout (hosted payment page ou client_secret equivalente).
    """
    data = criar_pedido_appmax(order, restaurant, method="credit-card")
    payment_data = data.get("data", {})
    return {
        "gateway":        "appmax",
        "method":         "credit-card",
        "appmax_id":      payment_data.get("id"),
        "checkout_url":   payment_data.get("checkout_url"),
        "payment_token":  payment_data.get("payment_token"),
    }


# ── Verificar status de pagamento ────────────────────────────

def verificar_pagamento_appmax(appmax_order_id: str) -> dict:
    """Consulta o status de um pedido na APPMAX."""
    resp = requests.get(
        f"{APPMAX_API_URL}/order/{appmax_order_id}",
        headers=_headers(),
        timeout=15,
    )
    if not resp.ok:
        raise RuntimeError(f"APPMAX erro {resp.status_code}: {resp.text}")
    return resp.json()


def pagamento_confirmado_appmax(appmax_order_id: str) -> bool:
    """Retorna True se o pagamento foi confirmado/aprovado."""
    try:
        data = verificar_pagamento_appmax(appmax_order_id)
        status = (
            data.get("data", {}).get("status", "")
            or data.get("status", "")
        )
        return status.lower() in ("paid", "approved", "completed", "captured")
    except Exception as e:
        print(f"[APPMAX] Erro ao verificar pagamento: {e}")
        return False


# ── Webhook ──────────────────────────────────────────────────

def processar_webhook_appmax(payload: dict) -> dict:
    """
    Processa evento de webhook recebido da APPMAX.
    Retorna dict com: order_id, status, appmax_id
    """
    event  = payload.get("event", "")
    data   = payload.get("data", {})

    order_id   = str(data.get("order_id", ""))
    appmax_id  = str(data.get("id", ""))
    status_raw = data.get("status", "").lower()

    STATUS_MAP = {
        "paid":      "paid",
        "approved":  "paid",
        "captured":  "paid",
        "refused":   "failed",
        "cancelled": "cancelled",
        "pending":   "pending",
        "waiting":   "pending",
    }
    status = STATUS_MAP.get(status_raw, "pending")

    return {
        "event":      event,
        "order_id":   order_id,
        "appmax_id":  appmax_id,
        "status":     status,
        "raw_status": status_raw,
    }
