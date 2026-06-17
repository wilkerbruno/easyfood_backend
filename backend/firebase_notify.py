# =============================================================
#  EASYFOOD - Notificacoes Push via Firebase Cloud Messaging
# =============================================================
import os
import json
import firebase_admin
from firebase_admin import credentials, messaging

_initialized = False


def init_firebase():
    """Inicializa o Firebase Admin SDK uma unica vez."""
    global _initialized
    if _initialized:
        return True

    cred_json = os.getenv("FIREBASE_CREDENTIALS_JSON", "")
    if not cred_json:
        return False

    try:
        cred_dict = json.loads(cred_json)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        _initialized = True
        return True
    except Exception as e:
        print(f"[FIREBASE] Erro ao inicializar: {e}")
        return False


def send_push(fcm_token: str, title: str, body: str, data: dict = None) -> bool:
    """Envia uma notificacao push para um token especifico."""
    if not fcm_token:
        return False
    if not init_firebase():
        print("[FIREBASE] Nao inicializado, pulando envio")
        return False

    try:
        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()},
            token=fcm_token,
        )
        response = messaging.send(message)
        print(f"[FIREBASE] Push enviado: {response}")
        return True
    except Exception as e:
        print(f"[FIREBASE] Erro ao enviar push: {e}")
        return False


# ── Mensagens prontas para cada situacao ────────────────────────

ORDER_STATUS_MESSAGES = {
    "confirmed":  ("Pedido confirmado! 🎉",  "Seu pedido #{order_id} foi confirmado pelo restaurante."),
    "preparing":  ("Pedido em preparo 👨‍🍳",  "Seu pedido #{order_id} esta sendo preparado."),
    "ready":      ("Pedido pronto! ✅",        "Seu pedido #{order_id} esta pronto e sera entregue em breve."),
    "delivered":  ("Pedido entregue! 🍽️",     "Seu pedido #{order_id} foi entregue. Bom apetite!"),
    "cancelled":  ("Pedido cancelado",        "Seu pedido #{order_id} foi cancelado."),
}


def notify_order_status(customer, order):
    """Notifica o cliente sobre mudanca de status do pedido."""
    if not customer or not customer.fcm_token:
        return False
    msg = ORDER_STATUS_MESSAGES.get(order.status)
    if not msg:
        return False
    title, body_template = msg
    body = body_template.format(order_id=order.id)
    return send_push(
        customer.fcm_token, title, body,
        data={"type": "order_status", "order_id": order.id, "status": order.status}
    )


def notify_table_release_check(customer):
    """Pergunta ao cliente se a mesa ja foi liberada."""
    if not customer or not customer.fcm_token:
        return False
    return send_push(
        customer.fcm_token,
        "A mesa ja foi liberada? 🪑",
        "Faz um tempo que seu pedido foi entregue. Você ainda está na mesa?",
        data={"type": "table_release_check", "table_number": customer.table_number or ""}
    )
