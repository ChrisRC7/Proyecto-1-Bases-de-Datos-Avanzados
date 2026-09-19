#!/usr/bin/env python3
"""E5 · Baseline: carga en PostgreSQL de un nodo exactamente los mismos datos que p1/gen/seed.py.

Reutiliza generar(), insertar() y huella() de p1/gen/seed.py, con la misma semilla y el mismo
número de clientes, así que la huella impresa debe coincidir con la de CockroachDB
(ad995e29a16440f7 con los valores por defecto). Solo cambia la conexión y el UPSERT de moneda,
que en PostgreSQL es INSERT ... ON CONFLICT.

Uso (HOST, raíz del repo):
  make up
  docker compose run --rm app python3 p1/baseline/seed_pg.py [--reset]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import psycopg
from psycopg import sql

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gen"))
import seed  # noqa: E402  (p1/gen/seed.py)

BASE = "p1_banca"
ESQUEMA = Path(__file__).with_name("01_schema_pg.sql")


def crear_base_si_falta() -> None:
    # PostgreSQL no tiene CREATE DATABASE IF NOT EXISTS; se conecta a la base del curso solo
    # para crear p1_banca. ti4601 no se toca.
    with psycopg.connect(autocommit=True) as conn:
        existe = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (BASE,)).fetchone()
        if not existe:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(BASE)))
            print(f"Base {BASE} creada en PostgreSQL")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--semilla", type=int, default=4601)
    parser.add_argument("--clientes", type=int, default=3000)
    parser.add_argument("--lote", type=int, default=500)
    parser.add_argument("--reset", action="store_true", help="vacía las tablas antes de cargar")
    args = parser.parse_args()

    inicio = time.perf_counter()
    clientes, cuentas, movimientos = seed.generar(args.semilla, args.clientes)
    print(f"Generado en {time.perf_counter() - inicio:.1f} s: {len(clientes)} clientes, "
          f"{len(cuentas)} cuentas, {len(movimientos)} movimientos")
    print(f"Huella de datos (semilla={args.semilla}, clientes={args.clientes}): "
          f"{seed.huella(clientes, cuentas, movimientos)}")

    crear_base_si_falta()
    with psycopg.connect(dbname=BASE, autocommit=True) as conn:
        conn.execute(ESQUEMA.read_text(encoding="utf-8"))
        existentes = conn.execute("SELECT count(*) FROM cliente").fetchone()[0]
        if existentes and not args.reset:
            print(f"cliente ya tiene {existentes} filas; no se carga nada. Use --reset para recargar.")
            return 0
        if args.reset:
            conn.execute("TRUNCATE movimiento, cuenta, cliente")

        conn.execute(
            "INSERT INTO moneda (codigo, nombre, tasa_crc, actualizado_en) VALUES "
            + ",".join(["(%s, %s, %s, %s)"] * len(seed.MONEDAS))
            + " ON CONFLICT (codigo) DO UPDATE SET nombre = EXCLUDED.nombre, "
              "tasa_crc = EXCLUDED.tasa_crc, actualizado_en = EXCLUDED.actualizado_en",
            [v for m in seed.MONEDAS for v in (*m, seed.INICIO)],
        )

        inicio = time.perf_counter()
        seed.insertar(conn, "cliente", "region, cliente_id, documento, nombre, email, creado_en",
                      clientes, args.lote)
        seed.insertar(conn, "cuenta", "region, cuenta_id, cliente_id, moneda, saldo, estado, abierta_en",
                      cuentas, args.lote)
        seed.insertar(conn, "movimiento",
                      "region, movimiento_id, cuenta_id, tipo, monto, moneda, saldo_resultante, "
                      "contraparte_region, contraparte_cuenta_id, creado_en",
                      movimientos, args.lote)
        print(f"Cargado en {time.perf_counter() - inicio:.1f} s")

        print("\nFilas por región:")
        for tabla in ("cliente", "cuenta", "movimiento"):
            filas = conn.execute(
                f"SELECT region, count(*) FROM {tabla} GROUP BY region ORDER BY region"
            ).fetchall()
            print(f"  {tabla:<10} " + "  ".join(f"{r}={n}" for r, n in filas))
    return 0


if __name__ == "__main__":
    sys.exit(main())
