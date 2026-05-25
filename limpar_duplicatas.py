# =============================================================
#  EASYFOOD - Limpeza de emails duplicados no banco MySQL
#  Uso: python limpar_duplicatas.py
# =============================================================

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pymysql

DB = dict(
    host     = "easypanel.pontocomdesconto.com.br",
    port     = 4006,
    user     = "mysql",
    password = "upg97an05jzr1y9djex2",
    database = "easyfood_bd",
    charset  = "utf8mb4",
    autocommit = False,
)

print("\n  EASYFOOD - Limpeza de emails duplicados\n")

conn   = pymysql.connect(**DB)
cursor = conn.cursor()

tables = {
    "user_accounts": "Usuários (clientes)",
    "employees":     "Funcionários",
    "admin_users":   "Administradores",
}

total_removidos = 0

for table, label in tables.items():
    print(f"--- {label} ({table}) ---")

    # Encontra emails duplicados
    cursor.execute(f"""
        SELECT email, COUNT(*) as qtd
        FROM {table}
        GROUP BY email
        HAVING qtd > 1
        ORDER BY qtd DESC
    """)
    dupes = cursor.fetchall()

    if not dupes:
        print(f"  Sem duplicatas\n")
        continue

    print(f"  {len(dupes)} email(s) duplicado(s):")
    for email, qtd in dupes:
        print(f"    {email}: {qtd} contas")

        # Mantém a conta mais recente (maior ID), remove as antigas
        cursor.execute(f"""
            DELETE FROM {table}
            WHERE email = %s
            AND id NOT IN (
                SELECT id FROM (
                    SELECT MAX(id) as id FROM {table} WHERE email = %s
                ) as t
            )
        """, (email, email))
        removidos = cursor.rowcount
        total_removidos += removidos
        print(f"    → {removidos} conta(s) antiga(s) removida(s), mantida a mais recente")

    print()

conn.commit()

# Adiciona constraint UNIQUE para evitar futuros duplicados
print("--- Adicionando restrição UNIQUE nos emails ---")
for table in tables.keys():
    try:
        cursor.execute(f"""
            ALTER TABLE {table}
            ADD CONSTRAINT uq_{table}_email UNIQUE (email)
        """)
        print(f"  ✓ {table}: UNIQUE adicionado")
    except pymysql.err.OperationalError as e:
        if "Duplicate key name" in str(e) or "1061" in str(e):
            print(f"  ✓ {table}: UNIQUE já existe")
        elif "Duplicate entry" in str(e) or "1062" in str(e):
            print(f"  ⚠ {table}: ainda há duplicatas, rode este script novamente")
        else:
            print(f"  ⚠ {table}: {e}")

conn.commit()
cursor.close()
conn.close()

print(f"\n  Total de contas duplicadas removidas: {total_removidos}")
print(f"  Banco limpo e protegido contra novos duplicados!")
print()
