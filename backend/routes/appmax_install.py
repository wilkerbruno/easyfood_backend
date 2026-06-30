# =============================================================
#  EASYFOOD - Health Check de Instalacao do App Store APPMAX
#  Endpoint chamado pela Appmax apos o merchant autorizar a
#  instalacao do app na loja dele (POST server-to-server).
# =============================================================
import os
import uuid
from datetime import datetime
from flask import Blueprint, jsonify, request
from backend.models import db, Restaurant

appmax_install_bp = Blueprint("appmax_install", __name__, url_prefix="/appmax")


@appmax_install_bp.post("/health")
def appmax_health_check():
    """
    Recebe o callback de instalacao da Appmax App Store.

    Body esperado:
    {
      "app_id": "889" ou UUID,      # numerico ou UUID, conforme config
      "external_key": "CNPJ",       # identificador do nosso lojista (CNPJ)
      "client_key": "CNPJ",         # deve ser igual a external_key
      "client_id": "ac_xxx",        # credencial do merchant
      "client_secret": "sec_xxx"    # credencial do merchant
    }

    Resposta esperada pela Appmax (200):
    { "external_id": "uuid" }
    """
    data = request.get_json(silent=True) or {}

    app_id        = str(data.get("app_id") or "").strip()
    external_key  = str(data.get("external_key") or "").strip()
    client_key    = str(data.get("client_key") or "").strip()
    client_id     = str(data.get("client_id") or "").strip()
    client_secret = str(data.get("client_secret") or "").strip()

    # 1) Todos os campos obrigatorios
    if not all([app_id, external_key, client_key, client_id, client_secret]):
        return jsonify({
            "message": "app_id, external_key, client_key, client_id and client_secret are required"
        }), 400

    # 2) app_id deve bater com o numerico OU o UUID configurado
    expected_numeric = os.getenv("APPMAX_APP_ID_NUMERIC", "")
    expected_uuid     = os.getenv("APPMAX_APP_ID", "")
    valid_ids = {v for v in (expected_numeric, expected_uuid) if v}
    if not valid_ids or app_id not in valid_ids:
        return jsonify({"message": "invalid app_id"}), 400

    # 3) client_key deve ser igual a external_key (checagem de seguranca)
    if client_key != external_key:
        return jsonify({"message": "invalid client_key"}), 400

    # 4) Upsert da instalacao: external_key = CNPJ do restaurante
    restaurant = Restaurant.query.filter_by(cnpj=external_key).first()
    if not restaurant:
        return jsonify({"message": "merchant not found for external_key"}), 404

    try:
        if not restaurant.appmax_external_id:
            restaurant.appmax_external_id = str(uuid.uuid4())

        restaurant.appmax_merchant_client_id     = client_id
        restaurant.appmax_merchant_client_secret = client_secret
        restaurant.appmax_installed_at           = datetime.utcnow()
        restaurant.appmax_recipient_status        = "instalado"

        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"message": "internal server error"}), 500

    return jsonify({"external_id": restaurant.appmax_external_id}), 200
