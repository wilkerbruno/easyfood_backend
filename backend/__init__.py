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

    # NullPool - sem pool, cada request usa conexão nova e descarta ao fim
    import flask_sqlalchemy as _fsa
    def _nullpool_engine(self, bind_key, options, app):
        from sqlalchemy import create_engine as _ce
        from sqlalchemy.pool import NullPool as _NP
        url = options.pop("url", None) or app.config["SQLALCHEMY_DATABASE_URI"]
        return _ce(url, poolclass=_NP)
    _fsa.SQLAlchemy._make_engine = _nullpool_engine

    # Extensoes
    db.init_app(app)
    JWTManager(app)
    CORS(app,
         resources={r"/*": {"origins": "*"}},
         supports_credentials=True,
         allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
         methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    )

    # Garante headers CORS em todas as respostas
    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"]  = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        return response

    # Responde OPTIONS (preflight) em todas as rotas
    @app.before_request
    def handle_options():
        from flask import request, Response
        if request.method == "OPTIONS":
            r = Response()
            r.headers["Access-Control-Allow-Origin"]  = "*"
            r.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            r.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            return r, 200

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

    @app.get("/static/uploads/logos/<path:filename>")
    def serve_logo(filename):
        uploads_dir = os.path.join(STATIC_DIR, "uploads", "logos")
        return send_from_directory(uploads_dir, filename)

    # Inicia o scheduler de liberacao automatica de mesa (apenas 1x por processo)
    if env == "production" and not app.config.get("_SCHEDULER_STARTED"):
        try:
            from backend.scheduler import start_scheduler
            start_scheduler(app)
            app.config["_SCHEDULER_STARTED"] = True
        except Exception as e:
            print(f"[SCHEDULER] Erro ao iniciar: {e}")

    return app
