#!/usr/bin/env python3
"""E4 · RTO de una corrida, calculado desde el CSV de la sonda y la época del docker stop.

Muestra la resta, no solo el resultado:
  RTO = fin_epoch del primer intento OK que empezó después del stop − época del stop

Se toma el primer intento que **empezó** después del stop. Un intento que empezó antes y
terminó después pudo confirmarse contra el leaseholder viejo justo antes de que muriera, así
que no demuestra que el clúster se recuperó.

Uso (HOST o app-crdb, raíz del repo):
  python3 p1/chaos/rto.py evidence/p1/e4-corrida1.csv evidence/p1/e4-corrida1-stop.epoch
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def utc(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="milliseconds")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv")
    parser.add_argument("epoch", help="archivo con la época (date +%%s.%%N) tomada al terminar docker stop")
    args = parser.parse_args()

    stop = float(Path(args.epoch).read_text().strip())
    with open(args.csv, newline="") as f:
        filas = list(csv.DictReader(f))
    for fila in filas:
        fila["inicio"], fila["fin"] = float(fila["inicio_epoch"]), float(fila["fin_epoch"])

    antes = [f for f in filas if f["fin"] < stop]
    en_vuelo = [f for f in filas if f["inicio"] < stop <= f["fin"]]
    despues = [f for f in filas if f["inicio"] >= stop]
    ultimo_ok_antes = next((f for f in reversed(antes) if f["estado"] == "ok"), None)
    primer_ok = next((f for f in despues if f["estado"] == "ok"), None)

    print(f"CSV: {args.csv} ({len(filas)} intentos)")
    print(f"docker stop terminó: {stop:.6f} ({utc(stop)})")
    print(f"Intentos antes del stop: {len(antes)} "
          f"(ok {sum(f['estado'] == 'ok' for f in antes)}, error {sum(f['estado'] == 'error' for f in antes)})")
    if ultimo_ok_antes:
        print(f"Último OK antes del stop: intento {ultimo_ok_antes['intento']}, folio {ultimo_ok_antes['folio']}, "
              f"fin {ultimo_ok_antes['fin']:.6f}")

    for f in en_vuelo:
        print(f"En curso al detener el nodo: intento {f['intento']} (empezó {stop - f['inicio']:.3f} s antes), "
              f"{f['estado']}, {float(f['latencia_ms']):.1f} ms {f['error']}")

    errores = [f for f in en_vuelo + despues
               if f["estado"] == "error" and (primer_ok is None or f["fin"] <= primer_ok["fin"])]
    print(f"\nErrores entre el stop y la recuperación: {len(errores)}")
    for clase, n in Counter(f["error"].split(":")[0] for f in errores).most_common():
        ejemplo = next(f["error"] for f in errores if f["error"].startswith(clase))
        print(f"  {n:3d} × {ejemplo}")
    lentos = [f for f in despues if f["estado"] == "ok" and float(f["latencia_ms"]) > 100]
    if lentos:
        print(f"OK con latencia > 100 ms después del stop: {len(lentos)} "
              f"(máx {max(float(f['latencia_ms']) for f in lentos):.1f} ms)")

    if primer_ok is None:
        print("\nRTO no observado: ningún intento que empezó después del stop se confirmó.")
        return 1
    rto = primer_ok["fin"] - stop
    print(f"\nPrimer OK que empezó después del stop: intento {primer_ok['intento']}, folio {primer_ok['folio']}, "
          f"latencia {float(primer_ok['latencia_ms']):.1f} ms")
    print(f"  fin_epoch  = {primer_ok['fin']:.6f} ({utc(primer_ok['fin'])})")
    print(f"  stop_epoch = {stop:.6f} ({utc(stop)})")
    print(f"  RTO = {primer_ok['fin']:.6f} − {stop:.6f} = {rto:.3f} s = {rto * 1000:.0f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
