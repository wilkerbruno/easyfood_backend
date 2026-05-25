# =============================================================
#  EASYFOOD - Script de Migracao do Banco MySQL
#  Uso: python migrar.py
#
#  Adiciona colunas novas sem apagar dados existentes.
# =============================================================

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_DIR)
sys.path.insert(0, PROJECT_DIR)

# Verifica dependencias
import importlib.util
REQUIRED = {
    "flask":             "flask",
    "flask_sqlalchemy":  "flask-sqlalchemy",
    "flask_jwt_extended":"flask-jwt-extended",
    "flask_cors":        "flask-cors",
    "bcrypt":            "bcrypt",
    "pymysql":           "pymysql",
}
missing = [pkg for mod, pkg in REQUIRED.items() if importlib.util.find_spec(mod) is None]
if missing:
    os.system(f"{sys.executable} -m pip install {' '.join(missing)}")
    os.execv(sys.executable, [sys.executable] + sys.argv)

import pymysql
from backend.config import config

# Pega URL do MySQL
cfg      = config["development"]
db_url   = cfg.SQLALCHEMY_DATABASE_URI
# Extrai dados da URL: mysql+pymysql://user:pass@host:port/dbname
import re
m = re.match(r"mysql\+pymysql://([^:]+):([^@]+)@([^:]+):(\d+)/([^?]+)", db_url)
if not m:
    print("[ERRO] Nao foi possivel parsear a URL do banco.")
    sys.exit(1)

DB_USER, DB_PASS, DB_HOST, DB_PORT, DB_NAME = m.groups()
DB_PORT = int(DB_PORT)

print(f"""
  ============================================
   EasyFood - Migrador de Banco MySQL
   Host: {DB_HOST}:{DB_PORT}
   Banco: {DB_NAME}
  ============================================
""")


def connect():
    return pymysql.connect(
        host=DB_HOST, port=DB_PORT,
        user=DB_USER, password=DB_PASS,
        database=DB_NAME, charset="utf8mb4",
        autocommit=True,
    )


def column_exists(cursor, table, column):
    cursor.execute(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema=%s AND table_name=%s AND column_name=%s",
        (DB_NAME, table, column)
    )
    return cursor.fetchone()[0] > 0


def table_exists(cursor, table):
    cursor.execute(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema=%s AND table_name=%s",
        (DB_NAME, table)
    )
    return cursor.fetchone()[0] > 0


def run(cursor, sql, desc):
    try:
        cursor.execute(sql)
        print(f"  [OK] {desc}")
    except Exception as e:
        print(f"  [SKIP] {desc} — {e}")


conn   = connect()
cursor = conn.cursor()
ok = 0
skip = 0

print("--- Migrando tabela: food_courts ---")
migrations_fc = [
    ("city",     "ALTER TABLE food_courts ADD COLUMN city     VARCHAR(100)  AFTER address"),
    ("state",    "ALTER TABLE food_courts ADD COLUMN state    VARCHAR(2)    AFTER city"),
    ("zip_code", "ALTER TABLE food_courts ADD COLUMN zip_code VARCHAR(10)   AFTER state"),
    ("phone",    "ALTER TABLE food_courts ADD COLUMN phone    VARCHAR(20)   AFTER zip_code"),
    ("email",    "ALTER TABLE food_courts ADD COLUMN email    VARCHAR(200)  AFTER phone"),
]
for col, sql in migrations_fc:
    if not column_exists(cursor, "food_courts", col):
        run(cursor, sql, f"food_courts.{col} adicionada")
        ok += 1
    else:
        print(f"  [JA EXISTE] food_courts.{col}")
        skip += 1

print("\n--- Migrando tabela: restaurants ---")
migrations_rest = [
    ("cnpj",          "ALTER TABLE restaurants ADD COLUMN cnpj          VARCHAR(18)  AFTER name"),
    ("razao_social",  "ALTER TABLE restaurants ADD COLUMN razao_social   VARCHAR(200) AFTER cnpj"),
    ("owner_name",    "ALTER TABLE restaurants ADD COLUMN owner_name     VARCHAR(150) AFTER razao_social"),
    ("owner_phone",   "ALTER TABLE restaurants ADD COLUMN owner_phone    VARCHAR(20)  AFTER owner_name"),
    ("owner_email",   "ALTER TABLE restaurants ADD COLUMN owner_email    VARCHAR(200) AFTER owner_phone"),
    ("phone",         "ALTER TABLE restaurants ADD COLUMN phone          VARCHAR(20)  AFTER owner_email"),
    ("opening_hours", "ALTER TABLE restaurants ADD COLUMN opening_hours  VARCHAR(200) AFTER phone"),
]
for col, sql in migrations_rest:
    if not column_exists(cursor, "restaurants", col):
        run(cursor, sql, f"restaurants.{col} adicionada")
        ok += 1
    else:
        print(f"  [JA EXISTE] restaurants.{col}")
        skip += 1

print("\n--- Criando tabelas novas ---")

# admin_users
if not table_exists(cursor, "admin_users"):
    run(cursor, """
        CREATE TABLE admin_users (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            name          VARCHAR(150) NOT NULL,
            email         VARCHAR(200) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            is_active     BOOLEAN NOT NULL DEFAULT TRUE,
            created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB
    """, "Tabela admin_users criada")
    ok += 1
else:
    print("  [JA EXISTE] Tabela admin_users")
    skip += 1

# user_accounts
if not table_exists(cursor, "user_accounts"):
    run(cursor, """
        CREATE TABLE user_accounts (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            name          VARCHAR(150) NOT NULL,
            email         VARCHAR(200) UNIQUE NOT NULL,
            phone         VARCHAR(20),
            password_hash VARCHAR(255) NOT NULL,
            is_active     BOOLEAN NOT NULL DEFAULT TRUE,
            created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB
    """, "Tabela user_accounts criada")
    ok += 1
else:
    print("  [JA EXISTE] Tabela user_accounts")
    skip += 1

# table_qrcodes
if not table_exists(cursor, "table_qrcodes"):
    run(cursor, """
        CREATE TABLE table_qrcodes (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            food_court_id INT NOT NULL,
            restaurant_id INT,
            table_number  VARCHAR(20) NOT NULL,
            qr_token      VARCHAR(64) UNIQUE NOT NULL,
            label         VARCHAR(100),
            is_active     BOOLEAN NOT NULL DEFAULT TRUE,
            created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_qr_court FOREIGN KEY (food_court_id) REFERENCES food_courts(id),
            CONSTRAINT fk_qr_rest  FOREIGN KEY (restaurant_id) REFERENCES restaurants(id) ON DELETE SET NULL
        ) ENGINE=InnoDB
    """, "Tabela table_qrcodes criada")
    ok += 1
else:
    print("  [JA EXISTE] Tabela table_qrcodes")
    skip += 1

# inventory_alerts (pode ter faltado)
if not table_exists(cursor, "inventory_alerts"):
    run(cursor, """
        CREATE TABLE inventory_alerts (
            id                INT AUTO_INCREMENT PRIMARY KEY,
            inventory_item_id INT NOT NULL,
            restaurant_id     INT NOT NULL,
            alert_type        ENUM('low_stock','expiry_warning','expired') NOT NULL,
            message           VARCHAR(300) NOT NULL,
            is_resolved       BOOLEAN NOT NULL DEFAULT FALSE,
            resolved_at       DATETIME,
            created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_alert_item  FOREIGN KEY (inventory_item_id) REFERENCES inventory_items(id) ON DELETE CASCADE,
            CONSTRAINT fk_alert_rest  FOREIGN KEY (restaurant_id)     REFERENCES restaurants(id)    ON DELETE CASCADE
        ) ENGINE=InnoDB
    """, "Tabela inventory_alerts criada")
    ok += 1
else:
    print("  [JA EXISTE] Tabela inventory_alerts")
    skip += 1

# reviews
if not table_exists(cursor, "reviews"):
    run(cursor, """
        CREATE TABLE reviews (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            order_id      INT NOT NULL UNIQUE,
            customer_id   INT NOT NULL,
            restaurant_id INT NOT NULL,
            rating        TINYINT NOT NULL,
            comment       TEXT,
            created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_review_order FOREIGN KEY (order_id)      REFERENCES orders(id),
            CONSTRAINT fk_review_cust  FOREIGN KEY (customer_id)   REFERENCES customers(id),
            CONSTRAINT fk_review_rest  FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
        ) ENGINE=InnoDB
    """, "Tabela reviews criada")
    ok += 1
else:
    print("  [JA EXISTE] Tabela reviews")
    skip += 1

cursor.close()
conn.close()

print(f"""
  ============================================
   Migracao concluida!
   {ok} alteracao(s) aplicada(s)
   {skip} ja existia(m) (ignoradas)
  ============================================
""")

# Cria admin padrao se nao existir
print("--- Verificando admin padrao ---")
try:
    import bcrypt
    from backend import create_app
    from backend.models import db, AdminUser

    app = create_app("development")
    with app.app_context():
        if not AdminUser.query.first():
            pwd = bcrypt.hashpw(b"admin@easyfood", bcrypt.gensalt()).decode()
            admin = AdminUser(
                name="Administrador EasyFood",
                email="admin@easyfood.com",
                password_hash=pwd,
            )
            db.session.add(admin)
            db.session.commit()
            print("  [OK] Admin criado: admin@easyfood.com / admin@easyfood")
        else:
            print("  [JA EXISTE] Admin padrao")
except Exception as e:
    print(f"  [AVISO] Nao foi possivel criar admin padrao: {e}")

print("""
  Agora rode: python iniciar.py
""")


# ─────────────────────────────────────────────────────────────
# MIGRACOES v2: Pagamento, Split, Conta Bancaria
# ─────────────────────────────────────────────────────────────
print("\n--- Migrando: roles de funcionarios ---")
try:
    cursor.execute("""
        ALTER TABLE employees
        MODIFY COLUMN role ENUM('admin','manager','attendant') NOT NULL DEFAULT 'attendant'
    """)
    print("  [OK] employees.role atualizado (adicionado 'manager')")
except Exception as e:
    print(f"  [SKIP] {e}")

print("\n--- Criando: platform_config ---")
if not table_exists(cursor, "platform_config"):
    run(cursor, """
        CREATE TABLE platform_config (
            id                      INT AUTO_INCREMENT PRIMARY KEY,
            platform_fee_percent    DECIMAL(5,2) NOT NULL DEFAULT 10.00,
            mp_access_token         VARCHAR(500),
            mp_public_key           VARCHAR(500),
            mp_collector_id         VARCHAR(100),
            pix_key                 VARCHAR(200),
            pix_key_type            ENUM('cpf','cnpj','email','phone','random'),
            bank_name               VARCHAR(100),
            bank_agency             VARCHAR(20),
            bank_account            VARCHAR(30),
            bank_account_type       ENUM('checking','savings') DEFAULT 'checking',
            bank_holder_name        VARCHAR(150),
            bank_holder_document    VARCHAR(18),
            updated_at              DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB
    """, "Tabela platform_config criada")
    # Insere config padrao
    try:
        cursor.execute("INSERT INTO platform_config (platform_fee_percent) VALUES (10.00)")
        print("  [OK] Config padrao inserida (10%)")
    except Exception as e:
        print(f"  [SKIP] {e}")
else:
    print("  [JA EXISTE] platform_config")

print("\n--- Criando: restaurant_bank_accounts ---")
if not table_exists(cursor, "restaurant_bank_accounts"):
    run(cursor, """
        CREATE TABLE restaurant_bank_accounts (
            id                   INT AUTO_INCREMENT PRIMARY KEY,
            restaurant_id        INT NOT NULL UNIQUE,
            mp_access_token      VARCHAR(500),
            mp_public_key        VARCHAR(500),
            mp_collector_id      VARCHAR(100),
            pix_key              VARCHAR(200),
            pix_key_type         ENUM('cpf','cnpj','email','phone','random'),
            bank_name            VARCHAR(100),
            bank_code            VARCHAR(10),
            bank_agency          VARCHAR(20),
            bank_account         VARCHAR(30),
            bank_account_type    ENUM('checking','savings') DEFAULT 'checking',
            bank_holder_name     VARCHAR(150),
            bank_holder_document VARCHAR(18),
            is_verified          BOOLEAN DEFAULT FALSE,
            created_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at           DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            CONSTRAINT fk_bank_restaurant FOREIGN KEY (restaurant_id)
                REFERENCES restaurants(id) ON DELETE CASCADE
        ) ENGINE=InnoDB
    """, "Tabela restaurant_bank_accounts criada")
else:
    print("  [JA EXISTE] restaurant_bank_accounts")

print("\n--- Criando: payment_splits ---")
if not table_exists(cursor, "payment_splits"):
    run(cursor, """
        CREATE TABLE payment_splits (
            id                   INT AUTO_INCREMENT PRIMARY KEY,
            payment_id           INT NOT NULL,
            order_id             INT NOT NULL,
            restaurant_id        INT NOT NULL,
            total_amount         DECIMAL(10,2) NOT NULL,
            platform_fee_percent DECIMAL(5,2)  NOT NULL,
            platform_amount      DECIMAL(10,2) NOT NULL,
            restaurant_amount    DECIMAL(10,2) NOT NULL,
            mp_payment_id        VARCHAR(200),
            status               ENUM('pending','processed','failed') DEFAULT 'pending',
            processed_at         DATETIME,
            created_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_split_payment    FOREIGN KEY (payment_id)    REFERENCES payments(id),
            CONSTRAINT fk_split_order      FOREIGN KEY (order_id)      REFERENCES orders(id),
            CONSTRAINT fk_split_restaurant FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
        ) ENGINE=InnoDB
    """, "Tabela payment_splits criada")
else:
    print("  [JA EXISTE] payment_splits")

cursor.close()
conn.close()
print("\n  Migracao v2 concluida!")
