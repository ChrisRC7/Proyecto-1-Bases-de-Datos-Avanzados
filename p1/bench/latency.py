import os
import time
import csv
import random
import uuid
import psycopg

# Configuración de la cantidad de ejecuciones
WARMUP_RUNS = 5
MEASURED_RUNS = 50  # n >= 30 exigido por el enunciado

# Función para obtener la conexión a la base de datos PostgreSQL
def get_connection():
    return psycopg.connect(
        host=os.getenv("PGHOST", "postgres"),
        port=os.getenv("PGPORT", "5432"),
        user=os.getenv("PGUSER", "ti4601"),
        password=os.getenv("PGPASSWORD", "ti4601"),
        dbname=os.getenv("PGDATABASE", "p1_banca")
    )

# Función para calcular percentiles
def calculate_percentile(data, p):
    sorted_data = sorted(data)
    idx = int(len(sorted_data) * (p / 100.0))
    return sorted_data[min(idx, len(sorted_data) - 1)]

# Función principal para ejecutar el benchmark
def run_benchmark():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT cuenta_id FROM cuenta LIMIT 100;")
    cuentas = [row[0] for row in cur.fetchall()]

    read_latencies_ms = []
    write_latencies_ms = []

    print(f"Ejecutando warm-up ({WARMUP_RUNS} iteraciones)...")
    for _ in range(WARMUP_RUNS):
        cta = random.choice(cuentas)
        cur.execute("SELECT * FROM cuenta WHERE cuenta_id = %s", (cta,))
        cur.fetchone()

    print(f"Midiendo latencias en PostgreSQL ({MEASURED_RUNS} ejecuciones)...")

    for _ in range(MEASURED_RUNS):
        cta = random.choice(cuentas)

        # Lectura (SELECT)
        start_time = time.perf_counter()
        cur.execute(
            "SELECT c.cliente_id, c.nombre, cta.saldo FROM cliente c JOIN cuenta cta ON c.cliente_id = cta.cliente_id WHERE cta.cuenta_id = %s",
            (cta,)
        )
        cur.fetchone()
        read_latencies_ms.append((time.perf_counter() - start_time) * 1000)

        # Escritura (INSERT)
        mov_id = str(uuid.uuid4())
        start_time = time.perf_counter()
        cur.execute(
            "INSERT INTO movimiento (movimiento_id, cuenta_id, tipo, monto, region) VALUES (%s, %s, %s, %s, %s)",
            (mov_id, cta, 'DEPOSITO', 50.00, 'cr-sj')
        )
        conn.commit()
        write_latencies_ms.append((time.perf_counter() - start_time) * 1000)

    cur.close()
    conn.close()

    read_p50 = calculate_percentile(read_latencies_ms, 50)
    read_p99 = calculate_percentile(read_latencies_ms, 99)
    write_p50 = calculate_percentile(write_latencies_ms, 50)
    write_p99 = calculate_percentile(write_latencies_ms, 99)

    print("\n--- RESULTADOS POSTGRESQL BASELINE ---")
    print(f"Lectura   -> p50: {read_p50:.2f} ms | p99: {read_p99:.2f} ms")
    print(f"Escritura -> p50: {write_p50:.2f} ms | p99: {write_p99:.2f} ms")

    os.makedirs("evidence/p1", exist_ok=True)
    with open("evidence/p1/postgres_latency_raw.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["iteracion", "operacion", "latencia_ms"])
        for i, (r, w) in enumerate(zip(read_latencies_ms, write_latencies_ms)):
            writer.writerow([i + 1, "lectura", r])
            writer.writerow([i + 1, "escritura", w])

    print("Resultados guardados en evidence/p1/postgres_latency_raw.csv")

if __name__ == "__main__":
    run_benchmark()