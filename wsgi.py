# =============================================================
#  EASYFOOD - WSGI Entry Point (Gunicorn / EasyPanel)
# =============================================================

import os
import sys

# Garante que o diretório raiz está no path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend import create_app
from backend.models import db

app = create_app(os.getenv("FLASK_ENV", "production"))


def init_db():
    """Cria tabelas e dados iniciais se não existirem."""
    with app.app_context():
        try:
            db.create_all()

            # Admin padrão
            from backend.models import AdminUser, PlatformConfig
            import bcrypt

            if not AdminUser.query.first():
                pwd = bcrypt.hashpw(b"admin@easyfood", bcrypt.gensalt()).decode()
                admin = AdminUser(
                    name="Administrador EasyFood",
                    email="admin@easyfood.com",
                    password_hash=pwd,
                )
                db.session.add(admin)
                db.session.commit()
                print("[INIT] Admin padrão criado: admin@easyfood.com")

            if not PlatformConfig.query.first():
                config = PlatformConfig(platform_fee_percent=10.00)
                db.session.add(config)
                db.session.commit()
                print("[INIT] Configuração da plataforma criada (taxa: 10%)")

        except Exception as e:
            print(f"[INIT] Aviso: {e}")


# Inicializa o banco na primeira execução
init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
