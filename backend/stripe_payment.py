# =============================================================
#  EASYFOOD - Integração Stripe
# =============================================================
import os, stripe

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLIC_KEY = os.getenv("STRIPE_PUBLIC_KEY", "")


def criar_payment_intent_pix(order, restaurant) -> dict:
    total_centavos = int(round(float(order.total) * 100))
    intent = stripe.PaymentIntent.create(
        amount               = total_centavos,
        currency             = "brl",
        payment_method_types = ["pix"],
        metadata             = {
            "order_id":        str(order.id),
            "restaurant_id":   str(restaurant.id),
            "restaurant_name": restaurant.name,
        },
        description = f"Pedido #{order.id} - EasyFood - {restaurant.name}",
    )
    return intent


def criar_payment_intent_cartao(order, restaurant,
                                 payment_method_id: str) -> dict:
    total_centavos = int(round(float(order.total) * 100))
    intent = stripe.PaymentIntent.create(
        amount               = total_centavos,
        currency             = "brl",
        payment_method       = payment_method_id,
        payment_method_types = ["card"],
        confirm              = True,
        metadata             = {
            "order_id":        str(order.id),
            "restaurant_id":   str(restaurant.id),
            "restaurant_name": restaurant.name,
        },
        description = f"Pedido #{order.id} - EasyFood - {restaurant.name}",
    )
    return intent


def consultar_payment_intent(pi_id: str) -> dict:
    return stripe.PaymentIntent.retrieve(pi_id)


def verificar_webhook(payload: bytes, signature: str):
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        return None
    return stripe.Webhook.construct_event(payload, signature, secret)
