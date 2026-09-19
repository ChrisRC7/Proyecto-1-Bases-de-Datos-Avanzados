#!/usr/bin/env python3
"""E4 · Sonda de escrituras del dominio durante la caída de un nodo.

Cada intento toma el siguiente folio de la serie TRANSFERENCIAS en
p1_control.folio_comprobante (RF=3, ver p1/sql/02_e4_table.sql). Es la escritura que
haría cada transferencia antes de emitir su comprobante. Un intento OK devuelve el folio
confirmado; así el CSV sirve también para el RPO: todo folio confirmado debe seguir
existiendo después de la falla.

La sonda no sabe cuándo se detiene el nodo. Lo registra p1/chaos/falla.sh en un archivo
de época, y p1/chaos/rto.py cruza las dos cosas después. Así la medición no depende de
que la sonda lea una señal a tiempo.

Uso: la lanza p1/chaos/falla.sh dentro de app-crdb. A mano:
  docker compose --profile lab1 run --rm --no-deps app-crdb python3 p1/chaos/sonda.py --csv /tmp/x.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg

SERIE = "TRANSFERENCIAS"
COLUMNAS = ("intento", "inicio_utc", "inicio_epoch", "fin_epoch", "estado", "folio", "latencia_ms", "error")


def conectar(host: str) -> psycopg.Connection:
    # Gateway fijo y vivo durante la prueba (crdb-1, cr-sj): lo que se mide es cuánto tarda
    # el rango en tener un leaseholder nuevo, no la reconexión a otro gateway.
    # statement_timeout acota cada intento: sin él, el primer intento tras la caída quedaría
    # bloqueado hasta la recuperación y el CSV no mostraría la ventana sin servicio.
    return psycopg.connect(host=host, port=26257, dbname="p1_control", user="root", sslmode="disable",
                           connect_timeout=2, autocommit=True, options="-c statement_timeout=2000")


def tomar_folio(conn) -> int:
    fila = conn.execute(
        """UPDATE folio_comprobante SET ultimo_folio = ultimo_folio + 1, actualizado_en = now()
           WHERE serie = %s RETURNING ultimo_folio""",
        (SERIE,),
    ).fetchone()
    if fila is None:
        sys.exit(f"No existe la serie {SERIE}; ejecute p1/setup.sh")
    return fila[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gateway", default="crdb-1")
    parser.add_argument("--duracion", type=float, default=45, help="segundos")
    parser.add_argument("--intervalo", type=float, default=0.2, help="segundos entre inicios de intento")
    parser.add_argument("--csv", required=True)
    args = parser.parse_args()

    salida = Path(args.csv)
    salida.parent.mkdir(parents=True, exist_ok=True)
    conn: psycopg.Connection | None = None
    fin = time.time() + args.duracion
    ok = errores = 0

    with salida.open("w", newline="") as f:
        escritor = csv.writer(f)
        escritor.writerow(COLUMNAS)
        intento = 0
        while time.time() < fin:
            intento += 1
            inicio = time.time()
            t0 = time.perf_counter_ns()
            folio, error = "", ""
            try:
                if conn is None or conn.closed:
                    conn = conectar(args.gateway)
                folio = tomar_folio(conn)
                estado = "ok"
                ok += 1
            except psycopg.Error as exc:
                # Un intento con error tiene resultado desconocido: no cuenta como confirmado
                # ni como perdido. Se guarda la clase para discutir el tipo de falla.
                estado = "error"
                errores += 1
                error = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"[:200]
                if conn is not None and conn.broken:
                    conn = None
            ms = (time.perf_counter_ns() - t0) / 1e6
            escritor.writerow([intento, datetime.fromtimestamp(inicio, timezone.utc).isoformat(timespec="milliseconds"),
                               f"{inicio:.6f}", f"{time.time():.6f}", estado, folio, f"{ms:.3f}", error])
            f.flush()
            print(f"{intento:4d} {estado:5} {ms:9.3f} ms  folio={folio or '-'} {error}", flush=True)
            time.sleep(max(0.0, args.intervalo - (time.time() - inicio)))

    print(f"\nIntentos: {intento} · ok: {ok} · error: {errores} · CSV: {salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
