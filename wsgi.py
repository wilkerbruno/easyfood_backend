import os, sys, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backend import create_app

app = create_app(os.getenv("FLASK_ENV", "production"))

def init_db():
    try:
        with app.app_context():
            from backend.models import db
            db.create_all()
            from backend.models import AdminUser, PlatformConfig
            import bcrypt
            if not AdminUser.query.first():
                pwd = bcrypt.hashpw(b"admin@easyfood", bcrypt.gensalt()).decode()
                db.session.add(AdminUser(name="Admin EasyFood", email="admin@easyfood.com", password_hash=pwd))
                db.session.commit()
            if not PlatformConfig.query.first():
                db.session.add(PlatformConfig(platform_fee_percent=10.00))
                db.session.commit()
    except Exception as e:
        print(f"[DB] {e}")

threading.Thread(target=init_db, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)