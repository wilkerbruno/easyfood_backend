# =============================================================
#  EASYFOOD - Configuracoes do Backend
#  Banco: MySQL (EasyPanel)
# =============================================================

import os
from datetime import timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Config:
    # MySQL EasyPanel
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://mysql:dm3exjaacxf4ekf9lddw@2.25.131.174:4006/easyfood_bd?charset=utf8mb4"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_POOL_RECYCLE        = 60
    SQLALCHEMY_POOL_PRE_PING       = True
    SQLALCHEMY_POOL_SIZE           = 5
    SQLALCHEMY_MAX_OVERFLOW        = 10

    # JWT
    JWT_SECRET_KEY           = os.getenv("JWT_SECRET_KEY", "easyfood-jwt-secret-2024")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=8)

    # App
    SECRET_KEY             = os.getenv("SECRET_KEY", "easyfood-secret-2024")
    DEBUG                  = False
    CUSTOMER_SESSION_HOURS = 8760  # 1 ano - praticamente nunca expira

    # ── APPMAX Split de Pagamento ──────────────────────────────
    APPMAX_BASE_URL      = os.getenv("APPMAX_BASE_URL", "https://admin.appmax.com.br/api/v4")
    APPMAX_APP_ID        = os.getenv("APPMAX_APP_ID", "")
    APPMAX_CLIENT_ID     = os.getenv("APPMAX_CLIENT_ID", "")
    APPMAX_CLIENT_SECRET = os.getenv("APPMAX_CLIENT_SECRET", "")
    EASYFOOD_FEE_PERCENT = float(os.getenv("EASYFOOD_FEE_PERCENT", "10"))


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


# Fallback SQLite caso o MySQL nao esteja acessivel (desenvolvimento offline)
class LocalConfig(Config):
    SQLALCHEMY_DATABASE_URI        = f"sqlite:///{os.path.join(BASE_DIR, 'easyfood.db')}"
    SQLALCHEMY_POOL_RECYCLE        = None
    SQLALCHEMY_POOL_PRE_PING       = True
    DEBUG                          = True


config = {
    "development": DevelopmentConfig,
    "production":  ProductionConfig,
    "local":       LocalConfig,
    "default":     DevelopmentConfig,
}
