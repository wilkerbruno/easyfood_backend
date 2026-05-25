# =============================================================
#  EASYFOOD - Rotas de Auth do Cliente (cadastro/login)
# =============================================================

import secrets
import bcrypt
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import (
    create_access_token, jwt_required, get_jwt_identity
)
from backend.models import db, UserAccount, Customer, FoodCourt, TableQRCode

auth_bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


# ── Cadastro ──────────────────────────────────────────────────
@auth_bp.post("/register")
def register():
    data  = request.get_json() or {}
    name  = data.get("name", "").strip()
    email = data.get("email", "").strip().lower()
    phone = data.get("phone", "").strip()
    pwd   = data.get("password", "")

    if not name or not email or not pwd:
        return jsonify({"error": "Nome, e-mail e senha sao obrigatorios"}), 400
    if len(pwd) < 6:
        return jsonify({"error": "Senha deve ter ao menos 6 caracteres"}), 400
    # Desativa contas duplicadas antigas, mantém a mais recente
    existing = UserAccount.query.filter_by(email=email).all()
    if existing:
        return jsonify({"error": "E-mail ja cadastrado"}), 409

    pwd_hash = bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode()
    user = UserAccount(name=name, email=email, phone=phone, password_hash=pwd_hash)
    db.session.add(user)
    db.session.commit()

    token = create_access_token(
        identity=str(user.id),
        additional_claims={"type": "customer", "name": user.name},
        expires_delta=timedelta(days=30),
    )
    return jsonify({"access_token": token, "user": user.to_dict()}), 201


# ── Login ─────────────────────────────────────────────────────
@auth_bp.post("/login")
def login():
    data  = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    pwd   = data.get("password", "")

    if not email or not pwd:
        return jsonify({"error": "E-mail e senha sao obrigatorios"}), 400

    # Busca o usuario mais recente com este email (resolve duplicatas)
    user = UserAccount.query.filter_by(email=email)        .order_by(UserAccount.id.desc()).first()

    if not user:
        return jsonify({"error": "E-mail ou senha invalidos"}), 401

    if not user.is_active:
        return jsonify({"error": "Conta desativada"}), 401

    try:
        pwd_ok = bcrypt.checkpw(pwd.encode("utf-8"), user.password_hash.encode("utf-8"))
    except Exception:
        return jsonify({"error": "Erro ao verificar senha"}), 500

    if not pwd_ok:
        return jsonify({"error": "E-mail ou senha invalidos"}), 401

    token = create_access_token(
        identity=str(user.id),
        additional_claims={"type": "customer", "name": user.name},
        expires_delta=timedelta(days=30),
    )
    return jsonify({"access_token": token, "user": user.to_dict()})


# ── Perfil ────────────────────────────────────────────────────
@auth_bp.get("/me")
@jwt_required()
def me():
    user_id = get_jwt_identity()
    user = UserAccount.query.get(int(user_id))
    if not user:
        return jsonify({"error": "Usuario nao encontrado"}), 404
    return jsonify(user.to_dict())


# ── Escanear QR Code com conta logada ─────────────────────────
@auth_bp.post("/scan")
@jwt_required(optional=True)
def scan_qr():
    """
    Escaneia QR Code (token da praça OU token de mesa).
    Funciona com ou sem conta logada.
    """
    data         = request.get_json() or {}
    qr_token     = data.get("qr_token", "").strip()
    table_number = data.get("table_number", "").strip()
    name         = data.get("name", "").strip()

    if not qr_token:
        return jsonify({"error": "Token QR invalido"}), 400

    # Tenta resolver como QR de mesa específica
    table_qr = TableQRCode.query.filter_by(qr_token=qr_token, is_active=True).first()
    if table_qr:
        court        = FoodCourt.query.get(table_qr.food_court_id)
        table_number = table_qr.table_number
    else:
        # Tenta resolver como token da praça
        court = FoodCourt.query.filter_by(qr_code_token=qr_token, is_active=True).first()
        table_qr = None

    if not court:
        return jsonify({"error": "QR Code invalido ou expirado"}), 404

    # Dados do usuário logado (se houver)
    user_id = get_jwt_identity()
    user    = UserAccount.query.get(int(user_id)) if user_id else None

    hours      = current_app.config.get("CUSTOMER_SESSION_HOURS", 4)
    session_tk = secrets.token_hex(32)

    customer = Customer(
        name          = (user.name if user else name) or "Cliente",
        phone         = user.phone if user else "",
        email         = user.email if user else "",
        session_token = session_tk,
        table_number  = table_number,
        food_court_id = court.id,
        expires_at    = datetime.utcnow() + timedelta(hours=hours),
    )
    db.session.add(customer)
    db.session.commit()

    return jsonify({
        "session_token":  session_tk,
        "food_court":     court.to_dict(),
        "table_number":   table_number,
        "restaurant_id":  table_qr.restaurant_id if table_qr else None,
        "expires_at":     customer.expires_at.isoformat(),
        "user":           user.to_dict() if user else None,
    }), 201
