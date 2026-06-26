# =============================================================
#  EASYFOOD - Job agendado para liberacao automatica de mesa
# =============================================================
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler


def check_table_release(app):
    """Roda a cada minuto com sessão MySQL isolada."""
    try:
        with app.app_context():
            from backend.models import db, Order, Customer
            from backend.firebase_notify import notify_table_release_check
            db.session.remove()  # conexão limpa
            now = datetime.utcnow()
            cutoff_40 = now - timedelta(minutes=40)

            try:
                pending = Order.query.filter(
                    Order.status == "delivered",
                    Order.delivered_at != None,
                    Order.delivered_at <= cutoff_40,
                ).all()
                for order in pending:
                    try:
                        customer = Customer.query.get(order.customer_id)
                        if customer and customer.is_active and not customer.table_release_asked_at:
                            notify_table_release_check(customer, order)
                            customer.table_release_asked_at = now
                            customer.table_release_deadline = now + timedelta(minutes=10)
                            db.session.commit()
                    except Exception as e:
                        db.session.rollback()
                        print(f"[SCHEDULER] Erro pedido {order.id}: {e}")
            except Exception as e:
                db.session.rollback()
                print(f"[SCHEDULER] Erro query pedidos: {e}")

            try:
                expired = Customer.query.filter(
                    Customer.table_release_deadline != None,
                    Customer.table_release_deadline <= now,
                    Customer.is_active == True,
                ).all()
                for customer in expired:
                    try:
                        customer.is_active = False
                        db.session.commit()
                    except Exception as e:
                        db.session.rollback()
            except Exception as e:
                db.session.rollback()
                print(f"[SCHEDULER] Erro query clientes: {e}")
    except Exception as e:
        print(f"[SCHEDULER] Erro geral: {e}")


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
