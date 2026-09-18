#!/usr/bin/env python3
"""E5 · Baseline: el mismo benchmark de p1/bench/latency.py contra PostgreSQL de un nodo.

Reutiliza de p1/bench/latency.py las cuatro operaciones (leer_saldo, transferir con doble
asiento), la selección de cuentas y el cálculo de percentiles. Mismo n, mismo warm-up, mismo
orden aleatorio por ronda (misma semilla), mismo reloj y mismo aislamiento (SERIALIZABLE, que en
CockroachDB es el único y en PostgreSQL hay que pedirlo).

Lo que no existe en un solo nodo: región del gateway y leaseholders. Los casos "local" y
"remota" se conservan con el mismo significado sobre las filas (cuenta hogar cr-sj frente a
cuenta hogar cr-limon), pero aquí la región es solo un dato: las cuatro operaciones tocan el
mismo nodo. Que local ≈ remota en PostgreSQL es el resultado esperado, no un defecto.

Uso (HOST, raíz del repo), después de seed_pg.py:
  docker compose run --rm app python3 p1/baseline/latency_pg.py

Espere unos minutos tras el seed, igual que con CockroachDB: justo después de la carga corren
autovacuum/ANALYZE y el checkpointer, y las escrituras salen ~10x más lentas que en reposo.
"""

from __future__ import annotations

import argparse
import csv
import os
import platform
import random
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench"))
import latency  # noqa: E402  (p1/bench/latency.py)

REGION_LOCAL = "cr-sj"     # misma región hogar que el gateway de E3
REGION_REMOTA = "cr-limon"


def conectar() -> psycopg.Connection:
    # Variables PG* del servicio `app` (PGHOST=postgres). Una conexión persistente, como en E3.
    conn = psycopg.connect(dbname="p1_banca", connect_timeout=5, autocommit=True)
    conn.execute("SET default_transaction_isolation = 'serializable'")
    return conn


def entorno(conn, args) -> list[str]:
    version = conn.execute("SELECT version()").fetchone()[0].split(" on ")[0]
    aislamiento = conn.execute("SHOW default_transaction_isolation").fetchone()[0]
    memoria = next((l.split()[1] for l in Path("/proc/meminfo").read_text().splitlines()
                    if l.startswith("MemTotal")), "?")
    return [
        f"fecha_utc: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"motor: {version} (un solo nodo, contenedor ti4601-postgres)",
        f"aislamiento: {aislamiento}",
        f"filas hogar: local={REGION_LOCAL}, remota={REGION_REMOTA} (la región es un dato; no hay gateway ni leaseholders)",
        f"corridas por caso: {args.corridas}; warm-up descartado por caso: {args.warmup}",
        f"orden de casos: aleatorio por ronda (semilla {args.semilla})",
        f"cpus: {os.cpu_count()}; memoria: {int(memoria) // 1024} MiB; python {platform.python_version()}; "
        f"psycopg {psycopg.__version__}",
        "perfil: imagen postgres:16 del docker-compose.yml del curso, sin ajustes; misma máquina que E3",
        "reloj: time.perf_counter_ns() alrededor de la operación completa (incluye COMMIT y reintentos)",
        "conexión: una conexión persistente; no incluye tiempo de conexión",
        "p99: nearest rank",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corridas", type=int, default=100)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--semilla", type=int, default=4601)
    parser.add_argument("--salida", default="evidence/p1")
    parser.add_argument("--prefijo", default="e5-latency-postgres")
    args = parser.parse_args()
    if args.corridas < 30:
        parser.error("el enunciado exige al menos 30 corridas por caso")

    conn = conectar()
    locales = latency.cuentas_de(conn, REGION_LOCAL, 2)
    remota = latency.cuentas_de(conn, REGION_REMOTA, 1)[0]

    def ejecutar(caso: str, ronda: int) -> int:
        ida = ronda % 2 == 0
        if caso == "lectura-local":
            latency.leer_saldo(conn, locales[0])
        elif caso == "lectura-remota":
            latency.leer_saldo(conn, remota)
        elif caso == "escritura-local":
            return (latency.transferir(conn, locales[0], locales[1]) if ida
                    else latency.transferir(conn, locales[1], locales[0]))
        else:
            return (latency.transferir(conn, locales[1], remota) if ida
                    else latency.transferir(conn, remota, locales[1]))
        return 0

    rng = random.Random(args.semilla)
    muestras = {caso: [] for caso in latency.CASOS}
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    ruta_csv = salida / f"{args.prefijo}.csv"

    for ronda in range(args.warmup):
        for caso in latency.CASOS:
            ejecutar(caso, ronda)

    hogares = {"lectura-local": REGION_LOCAL, "lectura-remota": REGION_REMOTA,
               "escritura-local": REGION_LOCAL, "escritura-cruza": f"{REGION_LOCAL}+{REGION_REMOTA}"}
    with ruta_csv.open("w", newline="") as f:
        escritor = csv.writer(f)
        escritor.writerow(["ronda", "orden", "caso", "operacion", "localidad", "motor",
                           "regiones_hogar", "inicio_utc", "latencia_ms", "reintentos"])
        for ronda in range(args.corridas):
            orden = list(latency.CASOS)
            rng.shuffle(orden)
            for posicion, caso in enumerate(orden):
                inicio_utc = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
                t0 = time.perf_counter_ns()
                reintentos = ejecutar(caso, args.warmup + ronda)
                ms = (time.perf_counter_ns() - t0) / 1e6
                muestras[caso].append(ms)
                operacion, localidad = caso.split("-")
                escritor.writerow([ronda + 1, posicion + 1, caso, operacion, localidad, "postgres-1-nodo",
                                   hogares[caso], inicio_utc, f"{ms:.3f}", reintentos])

    lineas = [f"=== P1 · E5 baseline PostgreSQL 1 nodo · {args.prefijo} ===", *entorno(conn, args), ""]
    lineas.append(f"{'caso':<16} {'fila hogar':<17} {'n':>4} {'p50_ms':>8} {'p99_ms':>8} "
                  f"{'media_ms':>9} {'max_ms':>8}")
    destinos = {"lectura-local": REGION_LOCAL, "lectura-remota": REGION_REMOTA,
                "escritura-local": REGION_LOCAL, "escritura-cruza": f"{REGION_LOCAL}+{REGION_REMOTA}"}
    for caso in latency.CASOS:
        v = muestras[caso]
        lineas.append(f"{caso:<16} {destinos[caso]:<17} {len(v):>4} {latency.percentil(v, 0.50):>8.3f} "
                      f"{latency.percentil(v, 0.99):>8.3f} {statistics.fmean(v):>9.3f} {max(v):>8.3f}")
    lineas += ["", f"Muestras crudas: {ruta_csv}"]

    texto = "\n".join(lineas)
    print(texto)
    (salida / f"{args.prefijo}-summary.txt").write_text(texto + "\n")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
