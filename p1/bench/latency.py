#!/usr/bin/env python3
"""E3 · Latencia p50/p99 de operaciones del dominio banca desde un gateway fijo.

Definición: una operación es LOCAL si todas las filas que toca tienen como región
hogar la región del gateway SQL; CRUZA REGIÓN si alguna fila tiene otra región hogar.

Casos (operaciones del E1 §1):
  lectura-local    O1 consultar saldo de una cuenta de la región del gateway
  lectura-remota   O1 consultar saldo de una cuenta de otra región
  escritura-local  O4 transferencia entre dos cuentas de la región del gateway
  escritura-cruza  O5 transferencia entre una cuenta del gateway y una de otra región

Las dos escrituras hacen el mismo trabajo (2 UPDATE de cuenta + 2 INSERT de movimiento
en una transacción); solo cambia la región hogar de la contraparte.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import platform
import random
import statistics
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import psycopg
from psycopg import errors

CASOS = ("lectura-local", "lectura-remota", "escritura-local", "escritura-cruza")
MONTO = Decimal("1.00")
MAX_REINTENTOS = 10


def conectar(host: str) -> psycopg.Connection:
    # Host fijo, no la lista PGHOST: si el gateway cambiara entre muestras,
    # "local" y "remoto" dejarían de significar lo mismo.
    return psycopg.connect(host=host, port=26257, dbname="p1_banca", user="root",
                           sslmode="disable", connect_timeout=5, autocommit=True)


def cuentas_de(conn, region: str, n: int) -> list:
    # Orden por cuenta_id: con el seed determinista siempre salen las mismas cuentas.
    filas = conn.execute(
        """SELECT cuenta_id FROM cuenta
           WHERE region = %s AND moneda = 'CRC' AND estado = 'ACTIVA' AND saldo >= 10000
           ORDER BY cuenta_id LIMIT %s""",
        (region, n),
    ).fetchall()
    if len(filas) < n:
        sys.exit(f"No hay {n} cuentas CRC con saldo en {region}; ejecute p1/setup.sh")
    return [(region, cuenta_id) for (cuenta_id,) in filas]


def esperar_leaseholders(conn, cuentas, limite_s: int = 120) -> list[str]:
    """Espera a que el leaseholder de cada cuenta esté en su región hogar.

    Justo después de cargar datos el motor todavía puede estar moviendo leases; medir
    en ese momento compararía una colocación transitoria y no la diseñada.
    """
    fin = time.monotonic() + limite_s
    while True:
        estado = []
        for region, cuenta_id in cuentas:
            localidad = conn.execute(
                "SELECT lease_holder_locality FROM [SHOW RANGE FROM TABLE cuenta FOR ROW (%s::public.crdb_internal_region, %s::UUID)]",
                (region, cuenta_id),
            ).fetchone()[0]
            estado.append((region, localidad, f"region={region}," in localidad))
        if all(ok for *_, ok in estado) or time.monotonic() > fin:
            return [f"leaseholder cuenta {r}: {loc} ({'en región hogar' if ok else 'FUERA de región hogar'})"
                    for r, loc, ok in estado]
        time.sleep(5)


def leer_saldo(conn, cuenta) -> None:
    region, cuenta_id = cuenta
    conn.execute("SELECT saldo FROM cuenta WHERE region = %s AND cuenta_id = %s", (region, cuenta_id)).fetchone()


def transferir(conn, origen, destino) -> int:
    """Transfiere MONTO con doble asiento. Devuelve cuántos reintentos necesitó."""
    for intento in range(MAX_REINTENTOS):
        try:
            with conn.transaction():
                saldo_origen = conn.execute(
                    """UPDATE cuenta SET saldo = saldo - %s
                       WHERE region = %s AND cuenta_id = %s AND saldo >= %s RETURNING saldo""",
                    (MONTO, *origen, MONTO),
                ).fetchone()
                if saldo_origen is None:
                    raise RuntimeError(f"saldo insuficiente en {origen}")
                saldo_destino = conn.execute(
                    """UPDATE cuenta SET saldo = saldo + %s
                       WHERE region = %s AND cuenta_id = %s RETURNING saldo""",
                    (MONTO, *destino),
                ).fetchone()
                conn.execute(
                    """INSERT INTO movimiento (region, cuenta_id, tipo, monto, moneda, saldo_resultante,
                                               contraparte_region, contraparte_cuenta_id)
                       VALUES (%s, %s, 'TRANSF_ENVIO', %s, 'CRC', %s, %s, %s),
                              (%s, %s, 'TRANSF_RECIBO', %s, 'CRC', %s, %s, %s)""",
                    (*origen, MONTO, saldo_origen[0], *destino,
                     *destino, MONTO, saldo_destino[0], *origen),
                )
            return intento
        except errors.SerializationFailure:
            # CockroachDB es SERIALIZABLE: un 40001 se reintenta y cuenta dentro de la latencia.
            time.sleep(0.001 * 2 ** intento)
    raise RuntimeError(f"transferencia {origen} -> {destino} agotó {MAX_REINTENTOS} reintentos")


def percentil(valores: list[float], p: float) -> float:
    ordenados = sorted(valores)
    return ordenados[max(1, math.ceil(p * len(ordenados))) - 1]  # nearest rank


def entorno(conn, args, region_gw: str, region_remota: str) -> list[str]:
    version = conn.execute("SELECT version()").fetchone()[0].split(" (")[0]
    memoria = next((l.split()[1] for l in Path("/proc/meminfo").read_text().splitlines()
                    if l.startswith("MemTotal")), "?")
    return [
        f"fecha_utc: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"motor: {version}",
        f"gateway: {args.gateway} (gateway_region={region_gw}); región remota: {region_remota}",
        f"corridas por caso: {args.corridas}; warm-up descartado por caso: {args.warmup}",
        f"orden de casos: aleatorio por ronda (semilla {args.semilla})",
        f"cpus: {os.cpu_count()}; memoria: {int(memoria) // 1024} MiB; python {platform.python_version()}; "
        f"psycopg {psycopg.__version__}",
        "perfil: clúster completo del Lab 1 (3 nodos, --cache=256MiB, --max-sql-memory=256MiB), una sola máquina",
        "latencia inyectada: ninguna (regiones lógicas)",
        "reloj: time.perf_counter_ns() alrededor de la operación completa (incluye COMMIT y reintentos)",
        "conexión: una conexión persistente al gateway; no incluye tiempo de conexión",
        "p99: nearest rank",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gateway", default="crdb-1", help="nodo SQL fijo (por defecto crdb-1, cr-sj)")
    parser.add_argument("--remota", default=None, help="región remota (por defecto cr-limon, o cr-sj)")
    parser.add_argument("--corridas", type=int, default=100)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--semilla", type=int, default=4601)
    parser.add_argument("--salida", default="evidence/p1", help="carpeta para CSV y resumen")
    parser.add_argument("--prefijo", default="e3-latency")
    args = parser.parse_args()

    if args.corridas < 30:
        parser.error("el enunciado exige al menos 30 corridas por caso")

    conn = conectar(args.gateway)
    region_gw = conn.execute("SELECT gateway_region()").fetchone()[0]
    region_remota = args.remota or ("cr-limon" if region_gw != "cr-limon" else "cr-sj")

    locales = cuentas_de(conn, region_gw, 2)
    remota = cuentas_de(conn, region_remota, 1)[0]
    leases = esperar_leaseholders(conn, [*locales, remota])
    print("\n".join(leases))

    def ejecutar(caso: str, ronda: int) -> int:
        # La dirección se alterna por ronda para que los saldos no se agoten.
        ida = ronda % 2 == 0
        if caso == "lectura-local":
            leer_saldo(conn, locales[0])
        elif caso == "lectura-remota":
            leer_saldo(conn, remota)
        elif caso == "escritura-local":
            return transferir(conn, locales[0], locales[1]) if ida else transferir(conn, locales[1], locales[0])
        else:
            return transferir(conn, locales[1], remota) if ida else transferir(conn, remota, locales[1])
        return 0

    rng = random.Random(args.semilla)
    muestras = {caso: [] for caso in CASOS}
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    ruta_csv = salida / f"{args.prefijo}.csv"

    # Warm-up: mismas operaciones, sin registrar (conexión, cachés y planes en frío).
    for ronda in range(args.warmup):
        for caso in CASOS:
            ejecutar(caso, ronda)

    with ruta_csv.open("w", newline="") as f:
        escritor = csv.writer(f)
        escritor.writerow(["ronda", "orden", "caso", "operacion", "localidad", "gateway_region",
                           "regiones_hogar", "inicio_utc", "latencia_ms", "reintentos"])
        for ronda in range(args.corridas):
            # Orden aleatorio por ronda: una deriva temporal (compactación, GC)
            # no favorece siempre al mismo caso.
            orden = list(CASOS)
            rng.shuffle(orden)
            for posicion, caso in enumerate(orden):
                inicio_utc = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
                t0 = time.perf_counter_ns()
                reintentos = ejecutar(caso, args.warmup + ronda)
                ms = (time.perf_counter_ns() - t0) / 1e6
                muestras[caso].append(ms)
                operacion, localidad = caso.split("-")
                hogares = {"lectura-local": region_gw, "lectura-remota": region_remota,
                           "escritura-local": region_gw, "escritura-cruza": f"{region_gw}+{region_remota}"}[caso]
                escritor.writerow([ronda + 1, posicion + 1, caso, operacion, localidad, region_gw,
                                   hogares, inicio_utc, f"{ms:.3f}", reintentos])

    lineas = [f"=== P1 · E3 latencia · {args.prefijo} ===", *entorno(conn, args, region_gw, region_remota),
              *leases, ""]
    lineas.append(f"{'caso':<16} {'desde':<8} {'hacia':<17} {'n':>4} {'p50_ms':>8} {'p99_ms':>8} "
                  f"{'media_ms':>9} {'max_ms':>8}")
    destinos = {"lectura-local": region_gw, "lectura-remota": region_remota,
                "escritura-local": region_gw, "escritura-cruza": region_remota}
    for caso in CASOS:
        v = muestras[caso]
        lineas.append(f"{caso:<16} {region_gw:<8} {destinos[caso]:<17} {len(v):>4} {percentil(v, 0.50):>8.3f} "
                      f"{percentil(v, 0.99):>8.3f} {statistics.fmean(v):>9.3f} {max(v):>8.3f}")
    lineas += ["", f"Muestras crudas: {ruta_csv}"]

    texto = "\n".join(lineas)
    print(texto)
    (salida / f"{args.prefijo}-summary.txt").write_text(texto + "\n")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
