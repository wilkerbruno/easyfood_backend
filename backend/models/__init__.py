# =============================================================
#  EASYFOOD - Modelos SQLAlchemy
# =============================================================

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


# ──────────────────────────────────────────────────────────────
class FoodCourt(db.Model):
    __tablename__ = "food_courts"

    id             = db.Column(db.Integer, primary_key=True)
    name           = db.Column(db.String(150), nullable=False)
    address        = db.Column(db.String(300), nullable=False)
    city           = db.Column(db.String(100))
    state          = db.Column(db.String(2))
    zip_code       = db.Column(db.String(10))
    phone          = db.Column(db.String(20))
    email          = db.Column(db.String(200))
    qr_code_token  = db.Column(db.String(64), unique=True, nullable=False)
    is_active      = db.Column(db.Boolean, default=True)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at     = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    restaurants = db.relationship("Restaurant", backref="food_court", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id, "name": self.name,
            "address": self.address, "city": self.city,
            "state": self.state, "zip_code": self.zip_code,
            "phone": self.phone, "email": self.email,
            "is_active": self.is_active,
            "qr_code_token": self.qr_code_token,
            "restaurant_count": self.restaurants.filter_by(is_active=True).count(),
        }


# ──────────────────────────────────────────────────────────────
class Restaurant(db.Model):
    __tablename__ = "restaurants"

    id               = db.Column(db.Integer, primary_key=True)
    food_court_id    = db.Column(db.Integer, db.ForeignKey("food_courts.id"), nullable=False)
    name             = db.Column(db.String(150), nullable=False)
    cnpj             = db.Column(db.String(18))
    razao_social     = db.Column(db.String(200))
    owner_name       = db.Column(db.String(150))
    owner_phone      = db.Column(db.String(20))
    owner_email      = db.Column(db.String(200))
    description      = db.Column(db.Text)
    logo_url              = db.Column(db.String(500))
    appmax_recipient_id   = db.Column(db.String(100))  # ID do recebedor na APPMAX
    appmax_recipient_status = db.Column(db.String(50))  # pending_kyc | active | blocked
    appmax_external_id      = db.Column(db.String(64))   # UUID gerado no health check da App Store
    appmax_merchant_client_id     = db.Column(db.String(255))
    appmax_merchant_client_secret = db.Column(db.String(255))
    appmax_installed_at           = db.Column(db.DateTime)
    category         = db.Column(db.String(100))
    phone            = db.Column(db.String(20))
    opening_hours    = db.Column(db.String(200))
    is_open          = db.Column(db.Boolean, default=True)
    is_active        = db.Column(db.Boolean, default=True)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at       = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    menu_categories = db.relationship("MenuCategory", backref="restaurant", lazy="dynamic")
    menu_items      = db.relationship("MenuItem",     backref="restaurant", lazy="dynamic")
    employees       = db.relationship("Employee",     backref="restaurant", lazy="dynamic")
    inventory_items = db.relationship("InventoryItem", backref="restaurant", lazy="dynamic")

    def to_dict(self, include_menu=False):
        data = {
            "id": self.id, "name": self.name,
            "cnpj": self.cnpj, "razao_social": self.razao_social,
            "owner_name": self.owner_name, "owner_phone": self.owner_phone,
            "owner_email": self.owner_email,
            "description": self.description, "logo_url": self.logo_url,
            "category": self.category, "is_open": self.is_open,
            "phone": self.phone, "opening_hours": self.opening_hours,
            "food_court_id": self.food_court_id,
            "is_active": self.is_active,
        }
        if include_menu:
            data["menu"] = [c.to_dict(include_items=True) for c in
                            self.menu_categories.filter_by(is_active=True).order_by("display_order")]
        return data


# ──────────────────────────────────────────────────────────────
class Employee(db.Model):
    __tablename__ = "employees"

    id            = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurants.id"), nullable=False)
    name          = db.Column(db.String(150), nullable=False)
    email         = db.Column(db.String(200), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role          = db.Column(db.Enum("admin", "manager", "attendant"), default="attendant")
    is_active     = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at    = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "name": self.name,
            "email": self.email, "role": self.role,
            "restaurant_id": self.restaurant_id,
            "is_active": self.is_active,
        }


# ──────────────────────────────────────────────────────────────
class MenuCategory(db.Model):
    __tablename__ = "menu_categories"

    id            = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurants.id"), nullable=False)
    name          = db.Column(db.String(100), nullable=False)
    display_order = db.Column(db.Integer, default=0)
    is_active     = db.Column(db.Boolean, default=True)

    items = db.relationship("MenuItem", backref="category", lazy="dynamic")

    def to_dict(self, include_items=False):
        data = {"id": self.id, "name": self.name, "display_order": self.display_order}
        if include_items:
            data["items"] = [i.to_dict() for i in
                             self.items.filter_by(is_active=True, is_available=True)]
        return data


# ──────────────────────────────────────────────────────────────
class MenuItem(db.Model):
    __tablename__ = "menu_items"

    id               = db.Column(db.Integer, primary_key=True)
    restaurant_id    = db.Column(db.Integer, db.ForeignKey("restaurants.id"), nullable=False)
    category_id      = db.Column(db.Integer, db.ForeignKey("menu_categories.id"))
    name             = db.Column(db.String(200), nullable=False)
    description      = db.Column(db.Text)
    price            = db.Column(db.Numeric(10, 2), nullable=False)
    image_url        = db.Column(db.String(500))
    is_available     = db.Column(db.Boolean, default=True)
    is_active        = db.Column(db.Boolean, default=True)
    preparation_time = db.Column(db.Integer)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at       = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "name": self.name,
            "description": self.description, "price": float(self.price),
            "image_url": self.image_url, "is_available": self.is_available,
            "preparation_time": self.preparation_time, "category_id": self.category_id,
        }


# ──────────────────────────────────────────────────────────────
class Customer(db.Model):
    __tablename__ = "customers"

    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(150))
    phone         = db.Column(db.String(20))
    email         = db.Column(db.String(200))
    session_token = db.Column(db.String(64), unique=True, nullable=False)
    table_number  = db.Column(db.String(20))
    food_court_id = db.Column(db.Integer, db.ForeignKey("food_courts.id"), nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at    = db.Column(db.DateTime, nullable=False)

    fcm_token            = db.Column(db.String(255))
    table_release_asked_at  = db.Column(db.DateTime)  # quando perguntamos se liberou a mesa
    table_release_deadline  = db.Column(db.DateTime)  # prazo para responder (10 min depois)
    is_active             = db.Column(db.Boolean, default=True)  # False = desconectado/mesa liberada

    orders = db.relationship("Order", backref="customer", lazy="dynamic")


# ──────────────────────────────────────────────────────────────
class Order(db.Model):
    __tablename__ = "orders"

    id             = db.Column(db.Integer, primary_key=True)
    customer_id    = db.Column(db.Integer, db.ForeignKey("customers.id"),    nullable=False)
    restaurant_id  = db.Column(db.Integer, db.ForeignKey("restaurants.id"),  nullable=False)
    food_court_id  = db.Column(db.Integer, db.ForeignKey("food_courts.id"),  nullable=False)
    table_number   = db.Column(db.String(20))
    status         = db.Column(db.Enum("pending","confirmed","preparing","ready","delivered","cancelled"),
                               default="pending")
    payment_status = db.Column(db.Enum("pending","paid","refunded"), default="pending")
    payment_method = db.Column(db.Enum("pix","credit_card","debit_card","cash"))
    subtotal       = db.Column(db.Numeric(10, 2), default=0)
    discount       = db.Column(db.Numeric(10, 2), default=0)
    total          = db.Column(db.Numeric(10, 2), default=0)
    notes          = db.Column(db.Text)
    delivered_at   = db.Column(db.DateTime)  # quando o status virou "delivered"
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at     = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items          = db.relationship("OrderItem",          backref="order",  lazy="dynamic", cascade="all, delete-orphan")
    status_history = db.relationship("OrderStatusHistory", backref="order",  lazy="dynamic", cascade="all, delete-orphan")
    payment        = db.relationship("Payment",            backref="order",  uselist=False)

    def to_dict(self, include_items=False):
        data = {
            "id": self.id, "status": self.status,
            "payment_status": self.payment_status,
            "payment_method": self.payment_method,
            "subtotal": float(self.subtotal), "discount": float(self.discount),
            "total": float(self.total), "table_number": self.table_number,
            "notes": self.notes, "created_at": self.created_at.isoformat(),
            "restaurant_id": self.restaurant_id,
        }
        if include_items:
            data["items"] = [i.to_dict() for i in self.items]
        return data


# ──────────────────────────────────────────────────────────────
class OrderItem(db.Model):
    __tablename__ = "order_items"

    id           = db.Column(db.Integer, primary_key=True)
    order_id     = db.Column(db.Integer, db.ForeignKey("orders.id"),      nullable=False)
    menu_item_id = db.Column(db.Integer, db.ForeignKey("menu_items.id"),  nullable=False)
    quantity     = db.Column(db.Integer, default=1)
    unit_price   = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal     = db.Column(db.Numeric(10, 2), nullable=False)
    notes        = db.Column(db.String(500))

    menu_item = db.relationship("MenuItem")

    def to_dict(self):
        return {
            "id": self.id, "menu_item_id": self.menu_item_id,
            "name": self.menu_item.name if self.menu_item else "",
            "quantity": self.quantity, "unit_price": float(self.unit_price),
            "subtotal": float(self.subtotal), "notes": self.notes,
        }


# ──────────────────────────────────────────────────────────────
class OrderStatusHistory(db.Model):
    __tablename__ = "order_status_history"

    id         = db.Column(db.Integer, primary_key=True)
    order_id   = db.Column(db.Integer, db.ForeignKey("orders.id"),      nullable=False)
    status     = db.Column(db.String(50), nullable=False)
    changed_by = db.Column(db.Integer, db.ForeignKey("employees.id"))
    notes      = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ──────────────────────────────────────────────────────────────
class Payment(db.Model):
    __tablename__ = "payments"

    id          = db.Column(db.Integer, primary_key=True)
    order_id    = db.Column(db.Integer, db.ForeignKey("orders.id"),     nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"),  nullable=False)
    method      = db.Column(db.Enum("pix","credit_card","debit_card","cash"), nullable=False)
    amount      = db.Column(db.Numeric(10, 2), nullable=False)
    status      = db.Column(db.Enum("pending","approved","rejected","refunded"), default="pending")
    gateway_ref = db.Column(db.String(200))
    pix_qr_code = db.Column(db.Text)
    paid_at     = db.Column(db.DateTime)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "method": self.method,
            "amount": float(self.amount), "status": self.status,
            "pix_qr_code": self.pix_qr_code,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
        }


# ──────────────────────────────────────────────────────────────
class InventoryItem(db.Model):
    __tablename__ = "inventory_items"

    id            = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurants.id"), nullable=False)
    name          = db.Column(db.String(200), nullable=False)
    category      = db.Column(db.String(100))
    unit_type     = db.Column(db.Enum("unit","kg","g","l","ml"), default="unit")
    quantity      = db.Column(db.Numeric(10, 3), default=0)
    min_quantity  = db.Column(db.Numeric(10, 3), default=0)
    cost_price    = db.Column(db.Numeric(10, 2))
    supplier      = db.Column(db.String(200))
    expiry_date   = db.Column(db.Date)
    batch_number  = db.Column(db.String(100))
    location      = db.Column(db.String(100))
    notes         = db.Column(db.Text)
    is_active     = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at    = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    movements = db.relationship("InventoryMovement", backref="item", lazy="dynamic")

    @property
    def is_low_stock(self):
        return float(self.quantity) <= float(self.min_quantity)

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "category": self.category,
            "unit_type": self.unit_type, "quantity": float(self.quantity),
            "min_quantity": float(self.min_quantity), "cost_price": float(self.cost_price or 0),
            "supplier": self.supplier,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "batch_number": self.batch_number, "location": self.location,
            "notes": self.notes, "is_low_stock": self.is_low_stock,
        }


# ──────────────────────────────────────────────────────────────
class InventoryMovement(db.Model):
    __tablename__ = "inventory_movements"

    id                = db.Column(db.Integer, primary_key=True)
    inventory_item_id = db.Column(db.Integer, db.ForeignKey("inventory_items.id"), nullable=False)
    restaurant_id     = db.Column(db.Integer, db.ForeignKey("restaurants.id"),     nullable=False)
    employee_id       = db.Column(db.Integer, db.ForeignKey("employees.id"))
    movement_type     = db.Column(db.Enum("in","out","adjustment","waste"), nullable=False)
    quantity          = db.Column(db.Numeric(10, 3), nullable=False)
    quantity_before   = db.Column(db.Numeric(10, 3), nullable=False)
    quantity_after    = db.Column(db.Numeric(10, 3), nullable=False)
    reason            = db.Column(db.String(300))
    related_order_id  = db.Column(db.Integer, db.ForeignKey("orders.id"))
    created_at        = db.Column(db.DateTime, default=datetime.utcnow)


# ──────────────────────────────────────────────────────────────
class Review(db.Model):
    __tablename__ = "reviews"

    id            = db.Column(db.Integer, primary_key=True)
    order_id      = db.Column(db.Integer, db.ForeignKey("orders.id"),      nullable=False, unique=True)
    customer_id   = db.Column(db.Integer, db.ForeignKey("customers.id"),   nullable=False)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurants.id"), nullable=False)
    rating        = db.Column(db.SmallInteger, nullable=False)
    comment       = db.Column(db.Text)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)


# ──────────────────────────────────────────────────────────────
# ADMINISTRADOR DO SISTEMA
# ──────────────────────────────────────────────────────────────
class AdminUser(db.Model):
    __tablename__ = "admin_users"

    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(150), nullable=False)
    email         = db.Column(db.String(200), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active     = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at    = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "name": self.name,
            "email": self.email, "is_active": self.is_active,
        }




# ──────────────────────────────────────────────────────────────
# CONFIGURACAO DA PLATAFORMA (taxa, conta Mercado Pago, etc.)
# ──────────────────────────────────────────────────────────────
class PlatformConfig(db.Model):
    __tablename__ = "platform_config"

    id                      = db.Column(db.Integer, primary_key=True)
    platform_fee_percent    = db.Column(db.Numeric(5, 2), default=10.00,
                                        comment="Percentual retido pela plataforma (ex: 10.00)")
    mp_access_token         = db.Column(db.String(500), comment="Mercado Pago Access Token da plataforma")
    mp_public_key           = db.Column(db.String(500), comment="Mercado Pago Public Key")
    mp_collector_id         = db.Column(db.String(100), comment="ID do recebedor da plataforma no MP")
    pix_key                 = db.Column(db.String(200), comment="Chave PIX da plataforma (fallback)")
    pix_key_type            = db.Column(db.Enum("cpf","cnpj","email","phone","random"),
                                        comment="Tipo da chave PIX")
    bank_name               = db.Column(db.String(100))
    bank_agency             = db.Column(db.String(20))
    bank_account            = db.Column(db.String(30))
    bank_account_type       = db.Column(db.Enum("checking","savings"), default="checking")
    bank_holder_name        = db.Column(db.String(150))
    bank_holder_document    = db.Column(db.String(18), comment="CPF ou CNPJ")
    updated_at              = db.Column(db.DateTime, default=datetime.utcnow,
                                        onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "platform_fee_percent": float(self.platform_fee_percent),
            "mp_collector_id":      self.mp_collector_id,
            "pix_key":              self.pix_key,
            "pix_key_type":         self.pix_key_type,
            "bank_name":            self.bank_name,
            "bank_agency":          self.bank_agency,
            "bank_account":         self.bank_account,
            "bank_account_type":    self.bank_account_type,
            "bank_holder_name":     self.bank_holder_name,
            "bank_holder_document": self.bank_holder_document,
        }

    def to_dict_safe(self):
        """Versão sem dados sensíveis para o frontend do restaurante."""
        return {
            "platform_fee_percent": float(self.platform_fee_percent),
        }


# ──────────────────────────────────────────────────────────────
# CONTA BANCARIA DO RESTAURANTE
# ──────────────────────────────────────────────────────────────
class RestaurantBankAccount(db.Model):
    __tablename__ = "restaurant_bank_accounts"

    id                   = db.Column(db.Integer, primary_key=True)
    restaurant_id        = db.Column(db.Integer, db.ForeignKey("restaurants.id"),
                                     nullable=False, unique=True)
    # Mercado Pago
    mp_access_token      = db.Column(db.String(500))
    mp_public_key        = db.Column(db.String(500))
    mp_collector_id      = db.Column(db.String(100),
                                     comment="ID do recebedor no Pagar.me para split")
    pagarme_recipient_id = db.Column(db.String(100),
                                     comment="ID do recipient no Pagar.me")
    # PIX
    pix_key              = db.Column(db.String(200))
    pix_key_type         = db.Column(db.Enum("cpf","cnpj","email","phone","random"))
    # Dados bancários
    bank_name            = db.Column(db.String(100))
    bank_code            = db.Column(db.String(10), comment="Código do banco ex: 001, 341, 077")
    bank_agency          = db.Column(db.String(20))
    bank_account         = db.Column(db.String(30))
    bank_account_type    = db.Column(db.Enum("checking","savings"), default="checking")
    bank_holder_name     = db.Column(db.String(150))
    bank_holder_document = db.Column(db.String(18), comment="CPF ou CNPJ do titular")
    is_verified          = db.Column(db.Boolean, default=False)
    created_at           = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at           = db.Column(db.DateTime, default=datetime.utcnow,
                                     onupdate=datetime.utcnow)

    def to_dict(self, show_sensitive=False):
        data = {
            "id":                   self.id,
            "restaurant_id":        self.restaurant_id,
            "pix_key":              self.pix_key,
            "pix_key_type":         self.pix_key_type,
            "bank_name":            self.bank_name,
            "bank_code":            self.bank_code,
            "bank_agency":          self.bank_agency,
            "bank_account":         self.bank_account,
            "bank_account_type":    self.bank_account_type,
            "bank_holder_name":     self.bank_holder_name,
            "bank_holder_document": self.bank_holder_document,
            "mp_collector_id":      self.mp_collector_id,
            "is_verified":          self.is_verified,
        }
        if show_sensitive:
            data["mp_access_token"] = self.mp_access_token
            data["mp_public_key"]   = self.mp_public_key
        return data


# ──────────────────────────────────────────────────────────────
# SPLIT DE PAGAMENTO (registro de cada transação)
# ──────────────────────────────────────────────────────────────
class PaymentSplit(db.Model):
    __tablename__ = "payment_splits"

    id                   = db.Column(db.Integer, primary_key=True)
    payment_id           = db.Column(db.Integer, db.ForeignKey("payments.id"), nullable=False)
    order_id             = db.Column(db.Integer, db.ForeignKey("orders.id"),   nullable=False)
    restaurant_id        = db.Column(db.Integer, db.ForeignKey("restaurants.id"), nullable=False)
    total_amount         = db.Column(db.Numeric(10,2), nullable=False, comment="Valor total pago")
    platform_fee_percent = db.Column(db.Numeric(5,2),  nullable=False)
    platform_amount      = db.Column(db.Numeric(10,2), nullable=False, comment="Valor retido pela plataforma")
    restaurant_amount    = db.Column(db.Numeric(10,2), nullable=False, comment="Valor repassado ao restaurante")
    mp_payment_id        = db.Column(db.String(200), comment="ID da transação no Mercado Pago")
    status               = db.Column(db.Enum("pending","processed","failed"), default="pending")
    processed_at         = db.Column(db.DateTime)
    created_at           = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id":                   self.id,
            "order_id":             self.order_id,
            "total_amount":         float(self.total_amount),
            "platform_fee_percent": float(self.platform_fee_percent),
            "platform_amount":      float(self.platform_amount),
            "restaurant_amount":    float(self.restaurant_amount),
            "status":               self.status,
            "mp_payment_id":        self.mp_payment_id,
            "created_at":           self.created_at.isoformat() if self.created_at else None,
        }

# ──────────────────────────────────────────────────────────────
# CONTA DE USUARIO (cliente registrado)
# ──────────────────────────────────────────────────────────────
class UserAccount(db.Model):
    __tablename__ = "user_accounts"

    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(150), nullable=False)
    email         = db.Column(db.String(200), unique=True, nullable=False)
    phone         = db.Column(db.String(20))
    password_hash = db.Column(db.String(255), nullable=False)
    is_active     = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at    = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "name": self.name,
            "email": self.email, "phone": self.phone,
        }


# ──────────────────────────────────────────────────────────────
# QR CODES DE MESA (gerados pelo restaurante)
# ──────────────────────────────────────────────────────────────
class TableQRCode(db.Model):
    __tablename__ = "table_qrcodes"

    id            = db.Column(db.Integer, primary_key=True)
    food_court_id = db.Column(db.Integer, db.ForeignKey("food_courts.id"), nullable=False)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurants.id"), nullable=True)
    table_number  = db.Column(db.String(20), nullable=False)
    qr_token      = db.Column(db.String(64), unique=True, nullable=False)
    label         = db.Column(db.String(100))
    is_active     = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "table_number": self.table_number,
            "qr_token": self.qr_token,
            "label": self.label,
            "restaurant_id": self.restaurant_id,
            "food_court_id": self.food_court_id,
            "is_active": self.is_active,
        }
