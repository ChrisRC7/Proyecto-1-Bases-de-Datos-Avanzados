import os
import random
import uuid
from datetime import datetime, timezone
import psycopg

# Semilla fija para garantizar reproducibilidad[cite: 1]
SEED = 42
random.seed(SEED)

# Parámetros de volumen justificado[cite: 1]
NUM_CLIENTES = 1000
CUENTAS_POR_CLIENTE = 2
MOVIMIENTOS_POR_CUENTA = 5

REGIONES = ['cr-sj', 'cr-limon', 'us-east']
TIPOS_MOVIMIENTO = ['DEPOSITO', 'RETIRO', 'TRANSFERENCIA']

def get_connection():
    return psycopg.connect(
        host=os.getenv("PGHOST", "postgres"),
        port=os.getenv("PGPORT", "5432"),
        user=os.getenv("PGUSER", "ti4601"),
        password=os.getenv("PGPASSWORD", "ti4601"),
        dbname=os.getenv("PGDATABASE", "p1_banca")
    )

def seed_database():
    conn = get_connection()
    cur = conn.cursor()

    print(f"Poblando la base de datos p1_banca con semilla {SEED}...")

    # 1. Insertar Clientes
    clientes = []
    cliente_ids = []
    for i in range(1, NUM_CLIENTES + 1):
        c_id = str(uuid.uuid4())
        cliente_ids.append(c_id)
        region = random.choice(REGIONES)
        clientes.append((
            c_id,
            f"Cliente_{i}",
            f"DOC-{100000 + i}",
            region,
            datetime.now(timezone.utc)
        ))

    cur.executemany(
        "INSERT INTO cliente (cliente_id, nombre, documento, region, created_at) VALUES (%s, %s, %s, %s, %s)",
        clientes
    )
    print(f"✓ {len(clientes)} clientes insertados.")

    # 2. Insertar Cuentas
    cuentas = []
    cuenta_ids = []
    for c_id in cliente_ids:
        for _ in range(CUENTAS_POR_CLIENTE):
            cta_id = str(uuid.uuid4())
            cuenta_ids.append(cta_id)
            region = random.choice(REGIONES)
            saldo = round(random.uniform(100.0, 10000.0), 2)
            cuentas.append((
                cta_id,
                c_id,
                region,
                saldo,
                datetime.now(timezone.utc)
            ))

    cur.executemany(
        "INSERT INTO cuenta (cuenta_id, cliente_id, region, saldo, created_at) VALUES (%s, %s, %s, %s, %s)",
        cuentas
    )
    print(f"✓ {len(cuentas)} cuentas insertadas.")

    # 3. Insertar Movimientos
    movimientos = []
    for cta_id in cuenta_ids:
        for _ in range(MOVIMIENTOS_POR_CUENTA):
            mov_id = str(uuid.uuid4())
            region = random.choice(REGIONES)
            monto = round(random.uniform(5.0, 500.0), 2)
            tipo = random.choice(TIPOS_MOVIMIENTO)
            movimientos.append((
                mov_id,
                cta_id,
                tipo,
                monto,
                region,
                datetime.now(timezone.utc)
            ))

    cur.executemany(
        "INSERT INTO movimiento (movimiento_id, cuenta_id, tipo, monto, region, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
        movimientos
    )
    print(f"✓ {len(movimientos)} movimientos insertados.")

    conn.commit()
    cur.close()
    conn.close()
    print("Carga masiva completada exitosamente.")

if __name__ == "__main__":
    seed_database()