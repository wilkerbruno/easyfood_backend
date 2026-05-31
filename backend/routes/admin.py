# =============================================================
#  EASYFOOD - Rotas do Administrador
# =============================================================

import secrets
import bcrypt
from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, jsonify, request
from flask_jwt_extended import (
    create_access_token, jwt_required,
    get_jwt_identity, get_jwt,
)
from sqlalchemy import func

from backend.models import (
    db, AdminUser, FoodCourt, Restaurant, Employee,
    Order, Customer, Review, TableQRCode,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/api/v1/admin")


# ── Auth guard ────────────────────────────────────────────────

def admin_required(f):
    @wraps(f)
    @jwt_required()
    def wrapper(*args, **kwargs):
        claims = get_jwt()
        if claims.get("type") != "admin":
            return jsonify({"error": "Acesso restrito ao administrador"}), 403
        return f(*args, **kwargs)
    return wrapper


def current_admin():
    return AdminUser.query.get(int(get_jwt_identity()))


# ── Login ─────────────────────────────────────────────────────

@admin_bp.post("/auth/login")
def login():
    data  = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    pwd   = data.get("password", "")

    if not email or not pwd:
        return jsonify({"error": "E-mail e senha sao obrigatorios"}), 400

    admin = AdminUser.query.filter_by(email=email).order_by(AdminUser.id.desc()).first()

    if not admin:
        return jsonify({"error": "Credenciais invalidas"}), 401

    if not admin.is_active:
        return jsonify({"error": "Conta desativada"}), 401

    try:
        pwd_ok = bcrypt.checkpw(
            pwd.encode("utf-8"),
            admin.password_hash.encode("utf-8")
        )
    except Exception as e:
        return jsonify({"error": f"Erro ao verificar senha: {str(e)}"}), 500

    if not pwd_ok:
        return jsonify({"error": "Credenciais invalidas"}), 401

    token = create_access_token(
        identity=str(admin.id),
        additional_claims={"type": "admin", "name": admin.name},
        expires_delta=timedelta(hours=12),
    )
    return jsonify({"access_token": token, "admin": admin.to_dict()})


# ── Dashboard geral ───────────────────────────────────────────

@admin_bp.get("/dashboard")
@admin_required
def dashboard():
    total_courts      = FoodCourt.query.filter_by(is_active=True).count()
    total_restaurants = Restaurant.query.filter_by(is_active=True).count()
    total_orders      = Order.query.count()
    total_customers   = Customer.query.count()

    today = datetime.utcnow().date()
    start = datetime.combine(today, datetime.min.time())

    orders_today = Order.query.filter(Order.created_at >= start).count()
    revenue_today = (
        db.session.query(func.sum(Order.total))
        .filter(Order.payment_status == "paid", Order.created_at >= start)
        .scalar() or 0
    )
    revenue_total = (
        db.session.query(func.sum(Order.total))
        .filter(Order.payment_status == "paid")
        .scalar() or 0
    )

    # Top restaurantes por receita
    top_restaurants = (
        db.session.query(
            Restaurant.name,
            func.sum(Order.total).label("revenue"),
            func.count(Order.id).label("orders"),
        )
        .join(Order, Order.restaurant_id == Restaurant.id)
        .filter(Order.payment_status == "paid")
        .group_by(Restaurant.id, Restaurant.name)
        .order_by(func.sum(Order.total).desc())
        .limit(5).all()
    )

    return jsonify({
        "total_courts":      total_courts,
        "total_restaurants": total_restaurants,
        "total_orders":      total_orders,
        "total_customers":   total_customers,
        "orders_today":      orders_today,
        "revenue_today":     float(revenue_today),
        "revenue_total":     float(revenue_total),
        "top_restaurants": [
            {"name": r.name, "revenue": float(r.revenue), "orders": r.orders}
            for r in top_restaurants
        ],
    })


# ── Praças de Alimentação ─────────────────────────────────────

@admin_bp.get("/courts")
@admin_required
def list_courts():
    courts = FoodCourt.query.order_by(FoodCourt.name).all()
    return jsonify([c.to_dict() for c in courts])


@admin_bp.get("/courts/<int:court_id>")
@admin_required
def get_court(court_id):
    court = FoodCourt.query.get_or_404(court_id)
    data  = court.to_dict()
    data["restaurants"] = [r.to_dict() for r in
                           court.restaurants.filter_by(is_active=True).all()]
    return jsonify(data)


@admin_bp.post("/courts")
@admin_required
def create_court():
    data = request.get_json() or {}
    if not data.get("name") or not data.get("address"):
        return jsonify({"error": "Nome e endereço são obrigatórios"}), 400

    court = FoodCourt(
        name          = data["name"].strip(),
        address       = data["address"].strip(),
        city          = data.get("city", "").strip(),
        state         = data.get("state", "").strip().upper(),
        zip_code      = data.get("zip_code", "").strip(),
        phone         = data.get("phone", "").strip(),
        email         = data.get("email", "").strip().lower(),
        qr_code_token = secrets.token_hex(16),
    )
    db.session.add(court)
    db.session.commit()
    return jsonify(court.to_dict()), 201


@admin_bp.put("/courts/<int:court_id>")
@admin_required
def update_court(court_id):
    court = FoodCourt.query.get_or_404(court_id)
    data  = request.get_json() or {}
    for field in ["name", "address", "city", "state", "zip_code", "phone", "email", "is_active"]:
        if field in data:
            setattr(court, field, data[field])
    db.session.commit()
    return jsonify(court.to_dict())


@admin_bp.delete("/courts/<int:court_id>")
@admin_required
def delete_court(court_id):
    court = FoodCourt.query.get_or_404(court_id)
    court.is_active = False
    db.session.commit()
    return jsonify({"message": "Praça desativada"})


# ── Restaurantes ──────────────────────────────────────────────

@admin_bp.get("/restaurants")
@admin_required
def list_restaurants():
    court_id = request.args.get("court_id")
    query    = Restaurant.query
    if court_id:
        query = query.filter_by(food_court_id=int(court_id))
    rests = query.order_by(Restaurant.name).all()
    return jsonify([r.to_dict() for r in rests])


@admin_bp.get("/restaurants/<int:rest_id>")
@admin_required
def get_restaurant(rest_id):
    rest = Restaurant.query.get_or_404(rest_id)
    data = rest.to_dict()
    data["employees"] = [e.to_dict() for e in rest.employees.filter_by(is_active=True).all()]
    return jsonify(data)


@admin_bp.post("/restaurants")
@admin_required
def create_restaurant():
    data = request.get_json() or {}
    if not data.get("name") or not data.get("food_court_id"):
        return jsonify({"error": "Nome e praça são obrigatórios"}), 400

    # Valida CNPJ (apenas formato, sem dígito verificador aqui)
    cnpj = data.get("cnpj", "").strip()
    cnpj_digits = "".join(c for c in cnpj if c.isdigit())
    if cnpj and len(cnpj_digits) != 14:
        return jsonify({"error": "CNPJ inválido. Informe os 14 dígitos"}), 400

    # Formata CNPJ: 00.000.000/0000-00
    if cnpj_digits:
        cnpj = f"{cnpj_digits[:2]}.{cnpj_digits[2:5]}.{cnpj_digits[5:8]}/{cnpj_digits[8:12]}-{cnpj_digits[12:14]}"

    rest = Restaurant(
        food_court_id = int(data["food_court_id"]),
        name          = data["name"].strip(),
        cnpj          = cnpj or None,
        razao_social  = data.get("razao_social", "").strip() or None,
        owner_name    = data.get("owner_name", "").strip() or None,
        owner_phone   = data.get("owner_phone", "").strip() or None,
        owner_email   = data.get("owner_email", "").strip().lower() or None,
        description   = data.get("description", "").strip() or None,
        category      = data.get("category", "").strip() or None,
        phone         = data.get("phone", "").strip() or None,
        opening_hours = data.get("opening_hours", "").strip() or None,
        is_open       = True,
        is_active     = True,
    )
    db.session.add(rest)
    db.session.flush()

    # Cria admin do restaurante automaticamente se informado
    if data.get("admin_email") and data.get("admin_password"):
        pwd_hash = bcrypt.hashpw(
            data["admin_password"].encode(), bcrypt.gensalt()
        ).decode()
        emp = Employee(
            restaurant_id = rest.id,
            name          = data.get("admin_name", rest.owner_name or "Admin"),
            email         = data["admin_email"].strip().lower(),
            password_hash = pwd_hash,
            role          = "admin",
        )
        db.session.add(emp)

    db.session.commit()

    # Salva dados bancários se informados
    bank_fields = ["pix_key","pix_key_type","bank_name","bank_agency",
                   "bank_account","bank_account_type","bank_holder_name","bank_holder_document"]
    bank_data = {f: data.get(f) for f in bank_fields if data.get(f)}
    if bank_data:
        from backend.models import RestaurantBankAccount
        bank = RestaurantBankAccount(restaurant_id=rest.id, **bank_data)
        db.session.add(bank)
        db.session.commit()

    return jsonify(rest.to_dict()), 201


@admin_bp.put("/restaurants/<int:rest_id>")
@admin_required
def update_restaurant(rest_id):
    rest = Restaurant.query.get_or_404(rest_id)
    data = request.get_json() or {}

    if "cnpj" in data:
        cnpj_digits = "".join(c for c in data["cnpj"] if c.isdigit())
        if cnpj_digits and len(cnpj_digits) != 14:
            return jsonify({"error": "CNPJ inválido"}), 400
        if cnpj_digits:
            data["cnpj"] = f"{cnpj_digits[:2]}.{cnpj_digits[2:5]}.{cnpj_digits[5:8]}/{cnpj_digits[8:12]}-{cnpj_digits[12:14]}"

    for field in ["name","cnpj","razao_social","owner_name","owner_phone",
                  "owner_email","description","category","phone",
                  "opening_hours","is_open","is_active","food_court_id"]:
        if field in data:
            setattr(rest, field, data[field])

    db.session.commit()
    return jsonify(rest.to_dict())


@admin_bp.delete("/restaurants/<int:rest_id>")
@admin_required
def delete_restaurant(rest_id):
    rest = Restaurant.query.get_or_404(rest_id)
    rest.is_active = False
    db.session.commit()
    return jsonify({"message": "Restaurante desativado"})


# ── Funcionários ──────────────────────────────────────────────

@admin_bp.get("/restaurants/<int:rest_id>/employees")
@admin_required
def list_employees(rest_id):
    emps = Employee.query.filter_by(restaurant_id=rest_id).all()
    return jsonify([e.to_dict() for e in emps])


@admin_bp.post("/restaurants/<int:rest_id>/employees")
@admin_required
def create_employee(rest_id):
    data = request.get_json() or {}
    if not data.get("email") or not data.get("password"):
        return jsonify({"error": "E-mail e senha são obrigatórios"}), 400
    if Employee.query.filter_by(email=data["email"].strip().lower()).first():
        return jsonify({"error": "E-mail já cadastrado"}), 409

    pwd_hash = bcrypt.hashpw(data["password"].encode(), bcrypt.gensalt()).decode()
    emp = Employee(
        restaurant_id = rest_id,
        name          = data.get("name", "").strip(),
        email         = data["email"].strip().lower(),
        password_hash = pwd_hash,
        role          = data.get("role", "attendant"),
    )
    db.session.add(emp)
    db.session.commit()
    return jsonify(emp.to_dict()), 201


@admin_bp.put("/employees/<int:emp_id>")
@admin_required
def update_employee(emp_id):
    emp  = Employee.query.get_or_404(emp_id)
    data = request.get_json() or {}
    for field in ["name", "role", "is_active"]:
        if field in data:
            setattr(emp, field, data[field])
    if data.get("password"):
        emp.password_hash = bcrypt.hashpw(
            data["password"].encode(), bcrypt.gensalt()
        ).decode()
    db.session.commit()
    return jsonify(emp.to_dict())


@admin_bp.delete("/employees/<int:emp_id>")
@admin_required
def delete_employee(emp_id):
    emp = Employee.query.get_or_404(emp_id)
    emp.is_active = False
    db.session.commit()
    return jsonify({"message": "Funcionário desativado"})


# ── Relatório global ──────────────────────────────────────────

@admin_bp.get("/reports/global")
@admin_required
def global_report():
    date_from = request.args.get("date_from")
    date_to   = request.args.get("date_to")

    query = Order.query.filter(Order.payment_status == "paid")
    if date_from:
        try: query = query.filter(Order.created_at >= datetime.strptime(date_from, "%Y-%m-%d"))
        except ValueError: pass
    if date_to:
        try: query = query.filter(Order.created_at <= datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1))
        except ValueError: pass

    orders = query.all()

    # Por praça
    by_court = (
        db.session.query(
            FoodCourt.name,
            func.count(Order.id).label("orders"),
            func.sum(Order.total).label("revenue"),
        )
        .join(Restaurant, Restaurant.food_court_id == FoodCourt.id)
        .join(Order, Order.restaurant_id == Restaurant.id)
        .filter(Order.payment_status == "paid")
        .group_by(FoodCourt.id, FoodCourt.name)
        .order_by(func.sum(Order.total).desc())
        .all()
    )

    # Por restaurante
    by_restaurant = (
        db.session.query(
            Restaurant.name,
            FoodCourt.name.label("court"),
            func.count(Order.id).label("orders"),
            func.sum(Order.total).label("revenue"),
        )
        .join(Order, Order.restaurant_id == Restaurant.id)
        .join(FoodCourt, FoodCourt.id == Restaurant.food_court_id)
        .filter(Order.payment_status == "paid")
        .group_by(Restaurant.id, Restaurant.name, FoodCourt.name)
        .order_by(func.sum(Order.total).desc())
        .limit(20).all()
    )

    return jsonify({
        "period":        {"from": date_from, "to": date_to},
        "total_orders":  len(orders),
        "total_revenue": float(sum(float(o.total) for o in orders)),
        "by_court": [
            {"name": r.name, "orders": r.orders, "revenue": float(r.revenue)}
            for r in by_court
        ],
        "by_restaurant": [
            {"name": r.name, "court": r.court, "orders": r.orders, "revenue": float(r.revenue)}
            for r in by_restaurant
        ],
    })


# ── Configuração da Plataforma ────────────────────────────────

@admin_bp.get("/platform-config")
@admin_required
def get_platform_config():
    config = PlatformConfig.query.first()
    return jsonify(config.to_dict() if config else {
        "platform_fee_percent": 10.0,
        "mp_collector_id": None,
        "pix_key": None,
    })


@admin_bp.post("/platform-config")
@admin_required
def save_platform_config():
    data   = request.get_json() or {}
    config = PlatformConfig.query.first()
    if not config:
        config = PlatformConfig()
        db.session.add(config)

    fields = [
        "platform_fee_percent",
        "mp_access_token", "mp_public_key", "mp_collector_id",
        "pix_key", "pix_key_type",
        "bank_name", "bank_agency", "bank_account",
        "bank_account_type", "bank_holder_name", "bank_holder_document",
    ]
    for f in fields:
        if f in data:
            setattr(config, f, data[f] or None)

    db.session.commit()
    return jsonify({"message": "Configurações salvas!", "config": config.to_dict()})


# ── Relatório de splits ───────────────────────────────────────

@admin_bp.get("/reports/splits")
@admin_required
def splits_report():
    from backend.models import PaymentSplit, Restaurant
    date_from = request.args.get("date_from")
    date_to   = request.args.get("date_to")

    query = PaymentSplit.query
    if date_from:
        try: query = query.filter(PaymentSplit.created_at >= datetime.strptime(date_from, "%Y-%m-%d"))
        except ValueError: pass
    if date_to:
        try: query = query.filter(PaymentSplit.created_at <= datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1))
        except ValueError: pass

    splits = query.order_by(PaymentSplit.created_at.desc()).all()

    total_platform   = sum(float(s.platform_amount)   for s in splits)
    total_restaurant = sum(float(s.restaurant_amount) for s in splits)
    total_geral      = sum(float(s.total_amount)      for s in splits)

    return jsonify({
        "total_transactions":    len(splits),
        "total_geral":           total_geral,
        "total_platform":        total_platform,
        "total_restaurant":      total_restaurant,
        "splits": [s.to_dict() for s in splits[:100]],
    })


@admin_bp.post("/restaurants/<int:rest_id>/pagarme/recipient")
@admin_required
def create_pagarme_recipient(rest_id: int):
    """Cria ou atualiza o recipient do restaurante no Pagar.me."""
    from backend.pagarme import criar_recipient
    from backend.models import RestaurantBankAccount

    rest = Restaurant.query.get_or_404(rest_id)
    data = request.get_json() or {}

    try:
        result = criar_recipient(data)
        recipient_id = result.get("id")

        # Salva o recipient_id no banco
        bank = RestaurantBankAccount.query.filter_by(restaurant_id=rest_id).first()
        if bank:
            bank.pagarme_recipient_id = recipient_id
        else:
            bank = RestaurantBankAccount(
                restaurant_id        = rest_id,
                pagarme_recipient_id = recipient_id,
                **{k: data.get(k) for k in ["pix_key","pix_key_type","bank_name",
                   "bank_agency","bank_account","bank_account_type",
                   "bank_holder_name","bank_holder_document"] if data.get(k)}
            )
            db.session.add(bank)

        db.session.commit()
        return jsonify({"recipient_id": recipient_id, "status": "created"}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.get("/restaurants/<int:rest_id>/pagarme/recipient")
@admin_required
def get_pagarme_recipient(rest_id: int):
    """Retorna o recipient_id do restaurante."""
    from backend.models import RestaurantBankAccount
    bank = RestaurantBankAccount.query.filter_by(restaurant_id=rest_id).first()
    if not bank or not bank.pagarme_recipient_id:
        return jsonify({"recipient_id": None, "configured": False}), 200
    return jsonify({"recipient_id": bank.pagarme_recipient_id, "configured": True}), 200
