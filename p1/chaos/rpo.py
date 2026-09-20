#!/usr/bin/env python3
"""E4 · RPO de una corrida: ¿se perdió alguna escritura confirmada?

La sonda pide folios consecutivos (ultimo_folio + 1) y guarda el folio que cada intento OK
recibió. Eso convierte el RPO en una comprobación aritmética sobre la evidencia:

  1. Los folios confirmados forman una secuencia sin huecos ni repeticiones. Un folio repetido
     o que retrocede significaría que el clúster olvidó una escritura ya confirmada.
  2. El primer folio confirmado después del stop es el último confirmado antes + 1 (+ k, si k
     intentos con timeout llegaron a confirmarse en el servidor sin que el cliente lo supiera:
     el hueco los delata y así se resuelve su resultado "desconocido").
  3. El folio final en la base (-despues.txt) es el último folio confirmado por la sonda.

RPO para escrituras confirmadas = 0 si las tres se cumplen. Los intentos con error tienen
resultado desconocido y no cuentan como perdidos; el punto 2 dice cuáles sí se confirmaron.

Uso (HOST o app-crdb, raíz del repo), después de p1/chaos/falla.sh:
  python3 p1/chaos/rpo.py evidence/p1/e4-corrida1.csv evidence/p1/e4-corrida1-stop.epoch \\
      evidence/p1/e4-corrida1-despues.txt | tee evidence/p1/e4-corrida1-rpo.txt
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path


def folio_final(despues: Path) -> int:
    # Fila de psql:  TRANSFERENCIAS |          279 | 2026-09-19 03:02:22...
    texto = despues.read_text(encoding="utf-8")
    bloque = texto[texto.index("folio confirmado al final"):]
    m = re.search(r"^\s*TRANSFERENCIAS\s*\|\s*(\d+)\s*\|", bloque, re.M)
    if not m:
        sys.exit(f"No se encontró el folio final en {despues}")
    return int(m.group(1))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv")
    parser.add_argument("epoch", help="archivo con la época del docker stop")
    parser.add_argument("despues", help="archivo -despues.txt con el folio final en la base")
    args = parser.parse_args()

    stop = float(Path(args.epoch).read_text().strip())
    final = folio_final(Path(args.despues))
    with open(args.csv, newline="") as f:
        filas = list(csv.DictReader(f))
    for fila in filas:
        fila["inicio"], fila["fin"] = float(fila["inicio_epoch"]), float(fila["fin_epoch"])
        fila["folio"] = int(fila["folio"]) if fila["folio"] else None

    oks = [f for f in filas if f["estado"] == "ok"]
    errores = [f for f in filas if f["estado"] == "error"]
    fallas = 0
    print(f"CSV: {args.csv} ({len(filas)} intentos: {len(oks)} ok, {len(errores)} error)")
    print(f"docker stop terminó: {stop:.6f}")

    # 1. Secuencia de folios confirmados.
    print("\n1. Secuencia de folios confirmados")
    print(f"   primero {oks[0]['folio']} (intento {oks[0]['intento']}), último {oks[-1]['folio']} "
          f"(intento {oks[-1]['intento']})")
    huecos, retrocesos = [], []
    for a, b in zip(oks, oks[1:]):
        if b["folio"] <= a["folio"]:
            retrocesos.append((a, b))
        elif b["folio"] != a["folio"] + 1:
            huecos.append((a, b))
    if retrocesos:
        fallas += 1
        for a, b in retrocesos:
            print(f"   [FAIL] folio {b['folio']} (intento {b['intento']}) no avanza sobre {a['folio']} "
                  f"(intento {a['intento']}): una escritura confirmada fue olvidada")
    else:
        print("   [ OK ] ningún folio se repite ni retrocede")
    for a, b in huecos:
        # Un hueco solo puede venir de intentos con error entre a y b que sí confirmaron.
        entre = [e for e in errores if a["fin"] < e["inicio"] and e["fin"] <= b["fin"]]
        k = b["folio"] - a["folio"] - 1
        print(f"   [INFO] hueco de {k} folio(s) entre {a['folio']} y {b['folio']}: "
              f"{len(entre)} intento(s) con error en ese tramo; {k} de ellos sí confirmaron en el servidor")
        if k > len(entre):
            fallas += 1
            print("   [FAIL] el hueco es mayor que los intentos con error: folios asignados fuera de la sonda")
    if not huecos:
        print("   [ OK ] sin huecos: ningún intento con error llegó a confirmarse")

    # 2. Cruce del stop.
    print("\n2. Cruce de la falla")
    antes = [f for f in oks if f["fin"] < stop]
    despues = [f for f in oks if f["inicio"] >= stop]
    if not antes or not despues:
        fallas += 1
        print("   [FAIL] no hay OK antes y después del stop; la corrida no sirve para el RPO")
    else:
        ua, pd = antes[-1], despues[0]
        dudosos = [e for e in errores if ua["fin"] < e["inicio"] and e["fin"] <= pd["fin"]]
        k = pd["folio"] - ua["folio"] - 1
        print(f"   último OK antes del stop:    intento {ua['intento']}, folio {ua['folio']}")
        print(f"   primer OK después del stop:  intento {pd['intento']}, folio {pd['folio']}")
        print(f"   intentos con resultado desconocido entre ambos: {len(dudosos)} "
              f"({', '.join(sorted({e['error'].split(':')[0] for e in dudosos})) or '-'})")
        if k < 0:
            fallas += 1
            print(f"   [FAIL] el folio retrocedió: se perdieron {-k} escritura(s) confirmada(s)")
        else:
            print(f"   [ OK ] {pd['folio']} = {ua['folio']} + 1 + {k}: el folio {ua['folio']} sobrevivió a la falla; "
                  f"de los {len(dudosos)} intentos dudosos, {k} confirmaron y {len(dudosos) - k} no")

    # 3. Folio final en la base.
    print("\n3. Folio final en la base")
    print(f"   base: {final} · último confirmado por la sonda: {oks[-1]['folio']}")
    if final < oks[-1]["folio"]:
        fallas += 1
        print(f"   [FAIL] la base perdió {oks[-1]['folio'] - final} folio(s) confirmado(s)")
    elif final == oks[-1]["folio"]:
        print("   [ OK ] coinciden: todo lo confirmado está en la base y nada más")
    else:
        print(f"   [INFO] la base tiene {final - oks[-1]['folio']} folio(s) más: escrituras posteriores a la sonda")

    print(f"\nRPO para escrituras confirmadas: {'0 — ninguna escritura confirmada se perdió' if fallas == 0 else 'MAYOR QUE 0'}"
          f" ({3 - fallas}/3 comprobaciones)")
    return 0 if fallas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
