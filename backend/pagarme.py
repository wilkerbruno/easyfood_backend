# =============================================================
#  EASYFOOD - Integração Pagar.me v5
# =============================================================
import os, json, requests
from decimal import Decimal

PAGARME_SECRET_KEY = os.getenv("PAGARME_SECRET_KEY", "")
PAGARME_BASE_URL   = "https://api.pagar.me/core/v5"

def _headers():
    import base64
    token = base64.b64encode(f"{PAGARME_SECRET_KEY}:".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Content-Type":  "application/json",
    }

def _reais_to_centavos(valor: Decimal) -> int:
    return int(round(float(valor) * 100))


# ── Criar recebedor (recipient) para o restaurante ──────────
def criar_recipient(bank_account: dict) -> dict:
    """
    bank_account = {
        holder_name, holder_document, holder_type (individual/company),
        bank, branch_number, branch_check_digit,
        account_number, account_check_digit, type (checking/savings)
    }
    """
    payload = {
        "name":         bank_account.get("holder_name"),
        "email":        bank_account.get("email", ""),
        "description":  bank_account.get("description", "Restaurante EasyFood"),
        "type":         "individual" if len(bank_account.get("holder_document","").replace(".","").replace("-","")) == 11 else "company",
        "document":     bank_account.get("holder_document","").replace(".","").replace("-","").replace("/",""),
        "default_bank_account": {
            "holder_name":          bank_account.get("holder_name"),
            "holder_type":          "individual" if len(bank_account.get("holder_document","").replace(".","").replace("-","")) == 11 else "company",
            "holder_document":      bank_account.get("holder_document","").replace(".","").replace("-","").replace("/",""),
            "bank":                 bank_account.get("bank_code","341"),
            "branch_number":        bank_account.get("branch_number","0001"),
            "branch_check_digit":   bank_account.get("branch_check_digit","0"),
            "account_number":       bank_account.get("account_number"),
            "account_check_digit":  bank_account.get("account_check_digit","0"),
            "type":                 bank_account.get("account_type","checking"),
        },
        "transfer_settings": {
            "transfer_enabled":  True,
            "transfer_interval": "daily",
            "transfer_day":      0,
        }
    }
    r = requests.post(f"{PAGARME_BASE_URL}/recipients",
                      headers=_headers(), json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


# ── Criar pedido PIX com split ───────────────────────────────
def criar_pedido_pix(order, restaurant, platform_recipient_id: str) -> dict:
    total_centavos     = _reais_to_centavos(order.total)
    fee_pct            = float(restaurant.platform_fee_percent or 10)
    platform_centavos  = int(round(total_centavos * fee_pct / 100))
    restaurant_centavos = total_centavos - platform_centavos

    recipient_id = None
    if hasattr(restaurant, 'bank_accounts') and restaurant.bank_accounts:
        recipient_id = restaurant.bank_accounts[0].pagarme_recipient_id

    splits = [
        {
            "recipient_id": platform_recipient_id,
            "amount":       platform_centavos,
            "type":         "flat",
            "options":      {"charge_processing_fee": True, "charge_remainder_fee": True, "liable": True}
        }
    ]
    if recipient_id:
        splits.append({
            "recipient_id": recipient_id,
            "amount":       restaurant_centavos,
            "type":         "flat",
            "options":      {"charge_processing_fee": False, "charge_remainder_fee": False, "liable": False}
        })

    payload = {
        "code":     f"ORDER-{order.id}",
        "currency": "BRL",
        "items": [{
            "amount":      total_centavos,
            "description": f"Pedido #{order.id} - EasyFood",
            "quantity":    1,
            "code":        f"order-{order.id}",
        }],
        "payments": [{
            "payment_method": "pix",
            "pix": {
                "expires_in": 3600,  # 1 hora
                "additional_information": [
                    {"name": "Pedido", "value": str(order.id)},
                    {"name": "Restaurante", "value": restaurant.name},
                ]
            },
        }],
    }
    if order.customer:
        payload["customer"] = {
            "name":  order.customer.name or "Cliente EasyFood",
            "email": order.customer.email or f"cliente{order.customer.id}@easyfood.com",
            "type":  "individual",
        }

    r = requests.post(f"{PAGARME_BASE_URL}/orders",
                      headers=_headers(), json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


# ── Criar pedido CARTÃO com split ────────────────────────────
def criar_pedido_cartao(order, restaurant, platform_recipient_id: str,
                        card_token: str, installments: int = 1) -> dict:
    total_centavos      = _reais_to_centavos(order.total)
    fee_pct             = float(restaurant.platform_fee_percent or 10)
    platform_centavos   = int(round(total_centavos * fee_pct / 100))
    restaurant_centavos = total_centavos - platform_centavos

    recipient_id = None
    if hasattr(restaurant, 'bank_accounts') and restaurant.bank_accounts:
        recipient_id = restaurant.bank_accounts[0].pagarme_recipient_id

    splits = [
        {
            "recipient_id": platform_recipient_id,
            "amount":       platform_centavos,
            "type":         "flat",
            "options":      {"charge_processing_fee": True, "charge_remainder_fee": True, "liable": True}
        }
    ]
    if recipient_id:
        splits.append({
            "recipient_id": recipient_id,
            "amount":       restaurant_centavos,
            "type":         "flat",
            "options":      {"charge_processing_fee": False, "charge_remainder_fee": False, "liable": False}
        })

    payload = {
        "code":     f"ORDER-{order.id}",
        "currency": "BRL",
        "items": [{
            "amount":      total_centavos,
            "description": f"Pedido #{order.id} - EasyFood",
            "quantity":    1,
            "code":        f"order-{order.id}",
        }],
        "payments": [{
            "payment_method": "credit_card",
            "credit_card": {
                "recurrence": False,
                "installments": installments,
                "statement_descriptor": "EASYFOOD",
                "card_token": card_token,
            },
        }],
    }
    if order.customer:
        payload["customer"] = {
            "name":  order.customer.name or "Cliente EasyFood",
            "email": order.customer.email or f"cliente{order.customer.id}@easyfood.com",
            "type":  "individual",
        }

    r = requests.post(f"{PAGARME_BASE_URL}/orders",
                      headers=_headers(), json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


# ── Consultar status de um pedido ────────────────────────────
def consultar_pedido(pagarme_order_id: str) -> dict:
    r = requests.get(f"{PAGARME_BASE_URL}/orders/{pagarme_order_id}",
                     headers=_headers(), timeout=30)
    r.raise_for_status()
    return r.json()


# ── Webhook: verificar assinatura ────────────────────────────
def verificar_webhook(payload: bytes, signature: str) -> bool:
    import hmac, hashlib
    secret = os.getenv("PAGARME_WEBHOOK_SECRET", "")
    if not secret:
        return True  # sem secret configurado, aceita tudo
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
