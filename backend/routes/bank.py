# =============================================================
#  EASYFOOD - Rotas: Conta Bancária e Funcionários do Restaurante
# =============================================================

import bcrypt
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from backend.models import (
    db, Employee, Restaurant,
    RestaurantBankAccount, PlatformConfig,
)

bank_bp = Blueprint("bank", __name__, url_prefix="/api/v1/restaurant")

ROLES = ("admin", "manager", "attendant")
ROLE_LABELS = {"admin": "Administrador", "manager": "Gerente", "attendant": "Funcionário"}


# ── Auth helpers ──────────────────────────────────────────────

def current_employee():
    return Employee.query.get(int(get_jwt_identity()))


def require_roles(*roles):
    from functools import wraps
    def decorator(f):
        @wraps(f)
        @jwt_required()
        def wrapper(*args, **kwargs):
            claims = get_jwt()
            if claims.get("role") not in roles:
                return jsonify({"error": "Acesso negado para este cargo"}), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ══════════════════════════════════════════════════════════════
# CONTA BANCÁRIA DO RESTAURANTE
# (acesso: admin e manager)
# ══════════════════════════════════════════════════════════════

@bank_bp.get("/bank-account")
@require_roles("admin", "manager")
def get_bank_account():
    emp  = current_employee()
    bank = RestaurantBankAccount.query.filter_by(
        restaurant_id=emp.restaurant_id
    ).first()

    config = PlatformConfig.query.first()
    fee    = float(config.platform_fee_percent) if config else 10.0

    return jsonify({
        "bank_account":       bank.to_dict() if bank else None,
        "platform_fee_percent": fee,
        "has_mp_configured":  bool(bank and bank.mp_access_token),
    })


@bank_bp.post("/bank-account")
@require_roles("admin", "manager")
def save_bank_account():
    emp  = current_employee()
    data = request.get_json() or {}

    bank = RestaurantBankAccount.query.filter_by(
        restaurant_id=emp.restaurant_id
    ).first()

    if not bank:
        bank = RestaurantBankAccount(restaurant_id=emp.restaurant_id)
        db.session.add(bank)

    fields = [
        "mp_access_token", "mp_public_key", "mp_collector_id",
        "pix_key", "pix_key_type",
        "bank_name", "bank_code", "bank_agency", "bank_account",
        "bank_account_type", "bank_holder_name", "bank_holder_document",
    ]
    for f in fields:
        if f in data:
            setattr(bank, f, data[f] or None)

    db.session.commit()
    return jsonify({
        "message":      "Conta bancária salva com sucesso!",
        "bank_account": bank.to_dict(),
    })


# ══════════════════════════════════════════════════════════════
# GESTÃO DE FUNCIONÁRIOS
# (listagem: admin e manager | criar/editar/remover: admin e manager*)
# *manager só pode criar/editar attendants — não pode criar outros managers
# ══════════════════════════════════════════════════════════════

@bank_bp.get("/employees")
@require_roles("admin", "manager")
def list_employees():
    emp   = current_employee()
    emps  = Employee.query.filter_by(
        restaurant_id=emp.restaurant_id, is_active=True
    ).order_by(Employee.name).all()
    return jsonify([e.to_dict() for e in emps])


@bank_bp.post("/employees")
@require_roles("admin", "manager")
def create_employee():
    emp  = current_employee()
    data = request.get_json() or {}
    role = data.get("role", "attendant")

    # Manager não pode criar admin ou outro manager
    if emp.role == "manager" and role in ("admin", "manager"):
        return jsonify({"error": "Gerentes só podem cadastrar funcionários (attendant)"}), 403

    if not data.get("email") or not data.get("password"):
        return jsonify({"error": "E-mail e senha são obrigatórios"}), 400
    if Employee.query.filter_by(email=data["email"].strip().lower()).first():
        return jsonify({"error": "E-mail já cadastrado"}), 409
    if len(data["password"]) < 6:
        return jsonify({"error": "Senha deve ter ao menos 6 caracteres"}), 400

    pwd_hash = bcrypt.hashpw(data["password"].encode(), bcrypt.gensalt()).decode()
    new_emp = Employee(
        restaurant_id = emp.restaurant_id,
        name          = data.get("name", "").strip(),
        email         = data["email"].strip().lower(),
        password_hash = pwd_hash,
        role          = role,
    )
    db.session.add(new_emp)
    db.session.commit()
    return jsonify(new_emp.to_dict()), 201


@bank_bp.put("/employees/<int:emp_id>")
@require_roles("admin", "manager")
def update_employee(emp_id: int):
    current = current_employee()
    target  = Employee.query.filter_by(
        id=emp_id, restaurant_id=current.restaurant_id
    ).first_or_404()
    data    = request.get_json() or {}

    # Manager não pode editar admin ou outros managers
    if current.role == "manager" and target.role in ("admin", "manager"):
        return jsonify({"error": "Gerentes não podem editar outros gerentes ou admins"}), 403

    # Manager não pode promover para admin/manager
    new_role = data.get("role", target.role)
    if current.role == "manager" and new_role in ("admin", "manager"):
        return jsonify({"error": "Gerentes não podem promover para gerente ou admin"}), 403

    for field in ["name", "role", "is_active"]:
        if field in data:
            setattr(target, field, data[field])

    if data.get("password"):
        if len(data["password"]) < 6:
            return jsonify({"error": "Senha deve ter ao menos 6 caracteres"}), 400
        target.password_hash = bcrypt.hashpw(
            data["password"].encode(), bcrypt.gensalt()
        ).decode()

    db.session.commit()
    return jsonify(target.to_dict())


@bank_bp.delete("/employees/<int:emp_id>")
@require_roles("admin", "manager")
def delete_employee(emp_id: int):
    current = current_employee()
    target  = Employee.query.filter_by(
        id=emp_id, restaurant_id=current.restaurant_id
    ).first_or_404()

    # Manager não pode remover admin ou outros managers
    if current.role == "manager" and target.role in ("admin", "manager"):
        return jsonify({"error": "Gerentes não podem remover outros gerentes ou admins"}), 403

    # Não pode remover a si mesmo
    if target.id == current.id:
        return jsonify({"error": "Você não pode remover sua própria conta"}), 400

    target.is_active = False
    db.session.commit()
    return jsonify({"message": "Funcionário desativado"})


# ── Info de cargos disponíveis ────────────────────────────────

@bank_bp.get("/roles")
@jwt_required()
def list_roles():
    emp = current_employee()
    # Manager só vê attendant; admin vê todos exceto admin (evitar criar outro admin)
    if emp.role == "manager":
        roles = [{"value": "attendant", "label": "Funcionário"}]
    else:
        roles = [
            {"value": "manager",   "label": "Gerente"},
            {"value": "attendant", "label": "Funcionário"},
        ]
    return jsonify(roles)
