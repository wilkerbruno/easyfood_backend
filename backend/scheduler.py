# =============================================================
#  EASYFOOD - Job agendado para liberacao automatica de mesa
# =============================================================
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler


def check_table_release(app):
    """
    Roda a cada minuto:
    1. Pedidos entregues ha 40+ min sem pergunta feita -> envia notificacao
    2. Clientes que nao responderam em 10 min -> desconecta (libera a mesa)
    """
    with app.app_context():
        from backend.models import db, Order, Customer
        from backend.firebase_notify import notify_table_release_check

        now = datetime.utcnow()

        # 1) Pedidos entregues ha mais de 40 minutos
        cutoff_40min = now - timedelta(minutes=40)
        orders = Order.query.filter(
            Order.status == "delivered",
            Order.delivered_at.isnot(None),
            Order.delivered_at <= cutoff_40min,
        ).all()

        for order in orders:
            customer = db.session.get(Customer, order.customer_id)
            if not customer or not customer.is_active:
                continue
            # Ja perguntamos para esse cliente? Evita duplicar pergunta
            if customer.table_release_asked_at:
                continue

            notify_table_release_check(customer)
            customer.table_release_asked_at = now
            customer.table_release_deadline = now + timedelta(minutes=10)
            db.session.commit()
            print(f"[SCHEDULER] Pergunta de liberacao enviada - cliente {customer.id}, mesa {customer.table_number}")

        # 2) Clientes que nao responderam dentro do prazo -> desconecta
        expired_customers = Customer.query.filter(
            Customer.is_active == True,
            Customer.table_release_deadline.isnot(None),
            Customer.table_release_deadline <= now,
        ).all()

        for customer in expired_customers:
            customer.is_active = False
            db.session.commit()
            print(f"[SCHEDULER] Cliente {customer.id} desconectado automaticamente - mesa {customer.table_number} liberada")


def start_scheduler(app):
    """Inicia o scheduler em background, executado uma vez por processo."""
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        func=lambda: check_table_release(app),
        trigger="interval",
        minutes=1,
        id="check_table_release",
        replace_existing=True,
    )
    scheduler.start()
    print("[SCHEDULER] Iniciado - verificando liberacao de mesa a cada 1 minuto")
    return scheduler
