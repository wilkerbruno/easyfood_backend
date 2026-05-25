# =============================================================
#  EASYFOOD - App Factory (Flask + PWA)
#  Compativel com Python 3.14+
# =============================================================

import os
from flask import Flask, send_from_directory
from flask_jwt_extended import JWTManager
from flask_cors import CORS

from backend.config import config
from backend.models import db

# Raiz absoluta do projeto (pasta pai de /backend)
ROOT_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(ROOT_DIR, "templates")
STATIC_DIR    = os.path.join(ROOT_DIR, "static")


def create_app(env: str = "development") -> Flask:
    app = Flask(
        __name__,
        static_folder=STATIC_DIR,
        template_folder=TEMPLATES_DIR,
    )
    app.config.from_object(config[env])

    # Extensoes
    db.init_app(app)
    JWTManager(app)
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # API Blueprints
    from backend.routes.customer   import customer_bp
    from backend.routes.auth       import auth_bp
    from backend.routes.admin      import admin_bp
    from backend.routes.payment    import payment_bp
    from backend.routes.bank       import bank_bp
    from backend.routes.restaurant import restaurant_bp
    app.register_blueprint(customer_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(payment_bp)
    app.register_blueprint(bank_bp)
    app.register_blueprint(restaurant_bp)

    # Servir o PWA com caminhos absolutos
    @app.get("/")
    def index():
        return send_from_directory(TEMPLATES_DIR, "index.html")

    @app.get("/restaurant")
    def restaurant_panel():
        return send_from_directory(TEMPLATES_DIR, "restaurant.html")

    @app.get("/admin")
    def admin_panel():
        return send_from_directory(TEMPLATES_DIR, "admin.html")

    @app.get("/manifest.json")
    def manifest():
        return send_from_directory(STATIC_DIR, "manifest.json")

    @app.get("/sw.js")
    def service_worker():
        return send_from_directory(STATIC_DIR, "sw.js")

    @app.get("/health")
    def health():
        return {"status": "ok", "app": "EasyFood", "python": "3.14+"}

    return app
