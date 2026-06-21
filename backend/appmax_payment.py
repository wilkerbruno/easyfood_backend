# =============================================================
#  EASYFOOD - Integração APPMAX API V4
#  Split de pagamento: EasyFood (marketplace) + Restaurante (recipient)
#  Docs: https://appmax.readme.io
# =============================================================
import os
import requests
from datetime import datetime

APPMAX_BASE_URL     = os.getenv("APPMAX_BASE_URL", "https://admin.appmax.com.br/api/v4")
APPMAX_APP_ID       = os.getenv("APPMAX_APP_ID", "")        # ID do aplicativo
APPMAX_CLIENT_ID    = os.getenv("APPMAX_CLIENT_ID", "")     # Client ID OAuth2
APPMAX_CLIENT_SECRET= os.getenv("APPMAX_CLIENT_SECRET", "") # Client Secret OAuth2

# Percentual que a EasyFood retém de cada venda (taxa do marketplace)
EASYFOOD_FEE_PERCENT = float(os.getenv("EASYFOOD_FEE_PERCENT", "10"))  # 10% default

# Cache do access_token em memória (evita re-autenticar a cada chamada)
_token_cache = {"access_token": None, "expires_at": None}


def _get_access_token() -> str:
    """
    Obtém o access_token via OAuth2 (client_credentials).
    Reutiliza o token em cache enquanto não expirar.
    """
    import time

    if not APPMAX_CLIENT_ID or not APPMAX_CLIENT_SECRET:
        raise RuntimeError(
            "Configure as variáveis APPMAX_APP_ID, APPMAX_CLIENT_ID e "
            "APPMAX_CLIENT_SECRET no EasyPanel"
        )

    # Retorna token em cache se ainda válido (com 60s de margem)
    now = time.time()
    if _token_cache["access_token"] and _token_cache["expires_at"]:
        if now < _token_cache["expires_at"] - 60:
            return _token_cache["access_token"]

    # Solicita novo token
    resp = requests.post(
        f"{APPMAX_BASE_URL}/token",
        json={
            "grant_type":    "client_credentials",
            "client_id":     APPMAX_CLIENT_ID,
            "client_secret": APPMAX_CLIENT_SECRET,
            "app_id":        APPMAX_APP_ID,
        },
        timeout=15,
    )

    if not resp.ok:
        raise RuntimeError(f"APPMAX auth erro {resp.status_code}: {resp.text}")

    data = resp.json()
    token = data.get("access_token") or data.get("token")
    expires_in = int(data.get("expires_in", 3600))

    _token_cache["access_token"] = token
    _token_cache["expires_at"]   = now + expires_in

    return token


def _headers():
    token = _get_access_token()
    return {
        "Content-Type": "application/json",
        "Accept":       "application/json",
        "Authorization": f"Bearer {token}",
    }


def _check_token():
    if not APPMAX_CLIENT_ID or not APPMAX_CLIENT_SECRET:
        raise RuntimeError(
            "Configure APPMAX_APP_ID, APPMAX_CLIENT_ID e APPMAX_CLIENT_SECRET no EasyPanel"
        )


# ═══════════════════════════════════════════════════════════════
#  1. ONBOARDING — Criar recebedor (recipient) via Fast Onboarding
# ═══════════════════════════════════════════════════════════════

def criar_recipient(restaurant) -> dict:
    """
    Cria um recebedor (recipient) na APPMAX para um restaurante.
    O restaurante recebe os pagamentos deduzida a taxa da EasyFood.

    Retorna: { "recipient_id": "...", "status": "pending_kyc", ... }
    """
    _check_token()

    payload = {
        "name":          restaurant.owner_name or restaurant.name,
        "email":         restaurant.owner_email or f"rest{restaurant.id}@easyfood.com",
        "phone":         (restaurant.phone or "00000000000").replace(" ", "").replace("-", ""),
        "document":      (restaurant.cnpj or restaurant.owner_cpf or "00000000000").replace(".", "").replace("-", "").replace("/", ""),
        "document_type": "cnpj" if restaurant.cnpj else "cpf",
        "company_name":  restaurant.razao_social or restaurant.name,
        "metadata": {
            "easyfood_restaurant_id": str(restaurant.id),
            "easyfood_restaurant_name": restaurant.name,
        },
    }

    resp = requests.post(
        f"{APPMAX_BASE_URL}/recipient",
        json=payload,
        headers=_headers(),
        timeout=30,
    )

    if not resp.ok:
        raise RuntimeError(f"APPMAX criar_recipient erro {resp.status_code}: {resp.text}")

    return resp.json().get("data", resp.json())


def gerar_link_kyc(recipient_id: str) -> str:
    """
    Gera o link de FaceMatch (KYC) para o recebedor validar identidade.
    Retorna a URL que deve ser enviada ao dono do restaurante.
    """
    _check_token()

    resp = requests.post(
        f"{APPMAX_BASE_URL}/recipient/{recipient_id}/facematch",
        headers=_headers(),
        timeout=15,
    )

    if not resp.ok:
        raise RuntimeError(f"APPMAX gerar_link_kyc erro {resp.status_code}: {resp.text}")

    data = resp.json().get("data", {})
    return data.get("url") or data.get("facematch_url", "")


def consultar_recipient(recipient_id: str) -> dict:
    """Consulta status do recebedor (KYC aprovado, pendente, etc)."""
    _check_token()

    resp = requests.get(
        f"{APPMAX_BASE_URL}/recipient/{recipient_id}",
        headers=_headers(),
        timeout=15,
    )

    if not resp.ok:
        raise RuntimeError(f"APPMAX consultar_recipient erro {resp.status_code}: {resp.text}")

    return resp.json().get("data", resp.json())


# ═══════════════════════════════════════════════════════════════
#  2. PEDIDO COM SPLIT
# ═══════════════════════════════════════════════════════════════

def _montar_customer(customer, order):
    """Monta objeto customer para o payload APPMAX."""
    return {
        "name":     customer.name or "Cliente EasyFood",
        "email":    customer.email or f"cliente{customer.id}@easyfood.com",
        "phone":    (customer.phone or "11999999999").replace(" ", "").replace("-", ""),
        "tax_id":   "00000000000",  # CPF — idealmente coletar do cliente no futuro
        "ip":       "127.0.0.1",
    }


def _montar_products(order):
    """Monta lista de produtos para o payload APPMAX."""
    products = []
    for item in order.items:
        products.append({
            "sku":         str(item.menu_item_id or item.id),
            "name":        item.name,
            "description": item.name,
            "quantity":    item.quantity,
            "price":       int(round(float(item.unit_price) * 100)),  # centavos
            "tangible":    False,
        })
    return products


def _montar_split(restaurant, order_total_cents: int) -> list:
    """
    Monta regras de split:
    - EasyFood retém EASYFOOD_FEE_PERCENT% (calculado sobre valor líquido)
    - Restaurante recebe o restante
    """
    if not restaurant.appmax_recipient_id:
        return []  # sem recipient cadastrado, sem split

    rest_percent = round(100 - EASYFOOD_FEE_PERCENT, 2)

    return [
        {
            "recipient_id": restaurant.appmax_recipient_id,
            "type":         "percentage",
            "amount":       rest_percent,  # ex: 90 (restaurante fica com 90%)
        }
        # EasyFood (marketplace) fica automaticamente com o restante (10%)
    ]


def criar_pedido_com_split(order, restaurant, customer, method="pix") -> dict:
    """
    Cria pedido na APPMAX com split automático para o restaurante.
    method: "pix" | "credit_card" | "boleto"
    """
    _check_token()

    total_cents = int(round(float(order.total) * 100))
    split       = _montar_split(restaurant, total_cents)

    payload = {
        "customer": _montar_customer(customer, order),
        "products": _montar_products(order),
        "payment": {
            "method":   method,
            "total":    total_cents,
            "currency": "BRL",
            "installments": 1,
        },
        "order": {
            "external_id": str(order.id),
            "amount":      total_cents,
        },
    }

    if split:
        payload["split"] = split

    resp = requests.post(
        f"{APPMAX_BASE_URL}/order",
        json=payload,
        headers=_headers(),
        timeout=30,
    )

    if not resp.ok:
        raise RuntimeError(f"APPMAX criar_pedido erro {resp.status_code}: {resp.text}")

    return resp.json().get("data", resp.json())


def criar_split_pedido_existente(appmax_order_id: str, restaurant) -> dict:
    """
    Cria/atualiza split em pedido já existente na APPMAX
    (apenas para pedidos ainda não aprovados).
    """
    _check_token()

    if not restaurant.appmax_recipient_id:
        raise RuntimeError("Restaurante não possui recipient_id APPMAX cadastrado")

    rest_percent = round(100 - EASYFOOD_FEE_PERCENT, 2)

    payload = {
        "recipients": [
            {
                "recipient_id": restaurant.appmax_recipient_id,
                "type":         "percentage",
                "amount":       rest_percent,
            }
        ]
    }

    resp = requests.post(
        f"{APPMAX_BASE_URL}/order/{appmax_order_id}/split",
        json=payload,
        headers=_headers(),
        timeout=15,
    )

    if not resp.ok:
        raise RuntimeError(f"APPMAX criar_split erro {resp.status_code}: {resp.text}")

    return resp.json().get("data", resp.json())


# ═══════════════════════════════════════════════════════════════
#  3. PIX E CARTÃO
# ═══════════════════════════════════════════════════════════════

def criar_pix(order, restaurant, customer) -> dict:
    """Gera cobrança PIX com split para o restaurante."""
    data = criar_pedido_com_split(order, restaurant, customer, method="pix")
    payment = data.get("payment", {})
    return {
        "appmax_order_id": str(data.get("id", "")),
        "method":          "pix",
        "pix_qr_code":     payment.get("pix_qr_code") or payment.get("qr_code_text") or payment.get("copy_paste"),
        "pix_qr_url":      payment.get("pix_qr_url")  or payment.get("qr_code_url"),
        "expires_at":      payment.get("expires_at"),
        "status":          data.get("status", "pending"),
    }


def criar_cartao(order, restaurant, customer, card_token: str = None, installments: int = 1) -> dict:
    """
    Gera cobrança por cartão com split.
    card_token: token do cartão gerado pelo SDK JS da APPMAX no frontend.
    """
    _check_token()

    total_cents = int(round(float(order.total) * 100))
    split       = _montar_split(restaurant, total_cents)

    payload = {
        "customer": _montar_customer(customer, order),
        "products": _montar_products(order),
        "payment": {
            "method":       "credit_card",
            "total":        total_cents,
            "currency":     "BRL",
            "installments": installments,
            **({"card_token": card_token} if card_token else {}),
        },
        "order": {
            "external_id": str(order.id),
            "amount":      total_cents,
        },
    }

    if split:
        payload["split"] = split

    resp = requests.post(
        f"{APPMAX_BASE_URL}/order",
        json=payload,
        headers=_headers(),
        timeout=30,
    )

    if not resp.ok:
        raise RuntimeError(f"APPMAX cartão erro {resp.status_code}: {resp.text}")

    data    = resp.json().get("data", resp.json())
    payment = data.get("payment", {})
    return {
        "appmax_order_id": str(data.get("id", "")),
        "method":          "credit_card",
        "status":          data.get("status", "pending"),
        "checkout_url":    payment.get("checkout_url"),
        "payment_token":   payment.get("payment_token"),
    }


# ═══════════════════════════════════════════════════════════════
#  4. CONSULTAS E SAQUE
# ═══════════════════════════════════════════════════════════════

def consultar_pedido(appmax_order_id: str) -> dict:
    _check_token()
    resp = requests.get(f"{APPMAX_BASE_URL}/order/{appmax_order_id}", headers=_headers(), timeout=15)
    if not resp.ok:
        raise RuntimeError(f"APPMAX consultar_pedido erro {resp.status_code}: {resp.text}")
    return resp.json().get("data", resp.json())


def pagamento_aprovado(appmax_order_id: str) -> bool:
    try:
        data   = consultar_pedido(appmax_order_id)
        status = str(data.get("status", "")).lower()
        return status in ("paid", "approved", "captured", "completed")
    except Exception as e:
        print(f"[APPMAX] Erro ao verificar pagamento: {e}")
        return False


def consultar_saldo_recipient(recipient_id: str) -> dict:
    _check_token()
    resp = requests.get(f"{APPMAX_BASE_URL}/recipient/{recipient_id}/balance", headers=_headers(), timeout=15)
    if not resp.ok:
        raise RuntimeError(f"APPMAX saldo erro {resp.status_code}: {resp.text}")
    return resp.json().get("data", resp.json())


def solicitar_saque(recipient_id: str, amount_cents: int = None) -> dict:
    _check_token()
    payload = {}
    if amount_cents:
        payload["amount"] = amount_cents
    resp = requests.post(
        f"{APPMAX_BASE_URL}/recipient/{recipient_id}/withdraw",
        json=payload, headers=_headers(), timeout=15,
    )
    if not resp.ok:
        raise RuntimeError(f"APPMAX saque erro {resp.status_code}: {resp.text}")
    return resp.json().get("data", resp.json())


# ═══════════════════════════════════════════════════════════════
#  5. WEBHOOK
# ═══════════════════════════════════════════════════════════════

STATUS_MAP = {
    "paid":       "paid",
    "approved":   "paid",
    "captured":   "paid",
    "completed":  "paid",
    "refused":    "failed",
    "cancelled":  "cancelled",
    "refunded":   "refunded",
    "pending":    "pending",
    "waiting":    "pending",
    "processing": "pending",
}


def processar_webhook(payload: dict) -> dict:
    event      = payload.get("event", "")
    data       = payload.get("data", payload)
    order_id   = str(data.get("external_id") or data.get("order_id") or "")
    appmax_id  = str(data.get("id", ""))
    status_raw = str(data.get("status", "")).lower()
    status     = STATUS_MAP.get(status_raw, "pending")

    return {
        "event":      event,
        "order_id":   order_id,
        "appmax_id":  appmax_id,
        "status":     status,
        "raw_status": status_raw,
        "data":       data,
    }
