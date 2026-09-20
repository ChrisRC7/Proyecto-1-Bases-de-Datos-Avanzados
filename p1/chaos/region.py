#!/usr/bin/env python3
"""E4 (opcional) · Caída de una región: qué filas RBR siguen disponibles y cuándo vuelven.

Con un nodo por región, detener crdb-2 es perder la región cr-limon completa. La pregunta ya
no es solo "¿vuelve a confirmarse una escritura?" (eso lo mide falla.sh sobre p1_control), sino
qué le pasa a cada fragmento del E1 según su región hogar:

  lee-sj         O1 saldo de una cuenta cr-sj            fragmento de otra región, vivo
  lee-limon      O1 saldo de una cuenta cr-limon         fragmento de la región caída
  lee-moneda     O7 tasa de cambio (moneda, GLOBAL)      copia local en cada región
  escribe-sj     O4 transferencia cr-sj ↔ cr-sj
  escribe-limon  O4 transferencia cr-limon ↔ cr-limon
  escribe-cruza  O5 transferencia cr-sj ↔ cr-limon

Cada caso corre en su propio hilo con su propia conexión al gateway (crdb-1, vivo) y
statement_timeout de 2 s. Así, que un caso quede bloqueado no retrasa la línea de tiempo de los
demás, y el CSV muestra por separado la ventana sin servicio de cada fragmento. Las operaciones
son las de p1/bench/latency.py: las transferencias conservan el doble asiento y check.py sigue
pasando después de la prueba.

Subcomandos (los lanza p1/chaos/region.sh dentro de app-crdb):
  sondear  --csv X --duracion S     escribe una fila por intento
  leases   [--esperar-hogar S]      leaseholder de cada cuenta usada
  resumir  CSV EPOCH_STOP EPOCH_START
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench"))
import latency  # noqa: E402  (p1/bench/latency.py)

CASOS = ("lee-sj", "lee-limon", "lee-moneda", "escribe-sj", "escribe-limon", "escribe-cruza")
COLUMNAS = ("caso", "intento", "inicio_utc", "inicio_epoch", "fin_epoch", "estado", "latencia_ms", "error")


def conectar(host: str) -> psycopg.Connection:
    return psycopg.connect(host=host, port=26257, dbname="p1_banca", user="root", sslmode="disable",
                           connect_timeout=2, autocommit=True, options="-c statement_timeout=2000")


def cuentas(conn) -> dict[str, list]:
    # Las mismas cuentas CRC que usa E3 (orden por cuenta_id, seed determinista).
    return {"cr-sj": latency.cuentas_de(conn, "cr-sj", 2), "cr-limon": latency.cuentas_de(conn, "cr-limon", 2)}


def operacion(caso: str, c: dict[str, list]):
    sj, li = c["cr-sj"], c["cr-limon"]
    ronda = {"n": 0}

    def ejecutar(conn) -> None:
        # La dirección de cada transferencia alterna para que los saldos no se agoten.
        ida = ronda["n"] % 2 == 0
        ronda["n"] += 1
        if caso == "lee-sj":
            latency.leer_saldo(conn, sj[0])
        elif caso == "lee-limon":
            latency.leer_saldo(conn, li[0])
        elif caso == "lee-moneda":
            conn.execute("SELECT tasa_crc FROM moneda WHERE codigo = 'USD'").fetchone()
        elif caso == "escribe-sj":
            latency.transferir(conn, *((sj[0], sj[1]) if ida else (sj[1], sj[0])))
        elif caso == "escribe-limon":
            latency.transferir(conn, *((li[0], li[1]) if ida else (li[1], li[0])))
        else:
            latency.transferir(conn, *((sj[1], li[1]) if ida else (li[1], sj[1])))

    return ejecutar


def sondear(args) -> int:
    with conectar(args.gateway) as conn:
        c = cuentas(conn)
    salida = Path(args.csv)
    salida.parent.mkdir(parents=True, exist_ok=True)
    candado = threading.Lock()
    fin = time.time() + args.duracion
    totales = {caso: [0, 0] for caso in CASOS}

    with salida.open("w", newline="") as f:
        escritor = csv.writer(f)
        escritor.writerow(COLUMNAS)

        def hilo(caso: str) -> None:
            ejecutar = operacion(caso, c)
            conn: psycopg.Connection | None = None
            intento = 0
            while time.time() < fin:
                intento += 1
                inicio = time.time()
                t0 = time.perf_counter_ns()
                error = ""
                try:
                    if conn is None or conn.closed:
                        conn = conectar(args.gateway)
                    ejecutar(conn)
                    estado = "ok"
                except (psycopg.Error, RuntimeError) as exc:
                    # Resultado desconocido: no cuenta como confirmado ni como perdido.
                    estado = "error"
                    error = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"[:200]
                    if conn is not None and conn.broken:
                        conn = None
                ms = (time.perf_counter_ns() - t0) / 1e6
                with candado:
                    escritor.writerow([caso, intento,
                                       datetime.fromtimestamp(inicio, timezone.utc).isoformat(timespec="milliseconds"),
                                       f"{inicio:.6f}", f"{time.time():.6f}", estado, f"{ms:.3f}", error])
                    f.flush()
                    totales[caso][estado == "error"] += 1
                time.sleep(max(0.0, args.intervalo - (time.time() - inicio)))

        hilos = [threading.Thread(target=hilo, args=(caso,), daemon=True) for caso in CASOS]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()

    for caso, (ok, err) in totales.items():
        print(f"{caso:<14} ok={ok:4d} error={err:3d}")
    print(f"CSV: {salida}")
    return 0


def leases(args) -> int:
    with conectar(args.gateway) as conn:
        c = cuentas(conn)
        usadas = [c["cr-sj"][0], c["cr-sj"][1], c["cr-limon"][0], c["cr-limon"][1]]
        if args.esperar_hogar:
            t0 = time.monotonic()
            lineas = latency.esperar_leaseholders(conn, usadas, args.esperar_hogar)
            print(f"(espera de leases en región hogar: {time.monotonic() - t0:.0f} s, límite {args.esperar_hogar} s)")
        else:
            lineas = latency.esperar_leaseholders(conn, usadas, 0)
        print("\n".join(lineas))
        moneda = conn.execute(
            "SELECT lease_holder_locality FROM [SHOW RANGE FROM TABLE moneda FOR ROW ('USD')]").fetchone()[0]
        print(f"leaseholder moneda (GLOBAL): {moneda}")
    return 0


def resumir(args) -> int:
    stop = float(Path(args.stop).read_text().strip())
    start = float(Path(args.start).read_text().strip())
    with open(args.csv, newline="") as f:
        filas = list(csv.DictReader(f))
    for fila in filas:
        fila["inicio"], fila["fin"], fila["ms"] = float(fila["inicio_epoch"]), float(fila["fin_epoch"]), float(fila["latencia_ms"])

    print(f"CSV: {args.csv} ({len(filas)} intentos)")
    print(f"docker stop terminó:  {stop:.6f} ({datetime.fromtimestamp(stop, timezone.utc).isoformat(timespec='milliseconds')})")
    print(f"docker start terminó: {start:.6f} ({datetime.fromtimestamp(start, timezone.utc).isoformat(timespec='milliseconds')})"
          f" → región caída {start - stop:.1f} s")
    print("""
Columnas (segundos relativos al stop, salvo 'reintegración', relativa al start):
  primer OK    fin del primer OK que empezó después del stop (como rto.py): cuándo el caso vuelve a responder
  estable      fin del último intento con error o > 1 s antes del start: desde ahí el caso ya no se interrumpe
  p50 estable  mediana de los OK entre 'estable' y el start: costo del caso con la región caída
  reintegr.    fin del último intento con error o > 1 s después del start: cuánto dura volver a 3 nodos
""")
    print(f"{'caso':<14} {'p50 antes':>9} {'err':>4} {'primer OK':>9} {'estable':>8} {'p50 estable':>11} "
          f"{'err':>4} {'reintegr.':>9}  error típico")
    print(f"{'':<14} {'(ms)':>9} {'caída':>4} {'(s)':>9} {'(s)':>8} {'(ms)':>11} {'tras':>4} {'(s)':>9}")
    for caso in CASOS:
        propias = [f for f in filas if f["caso"] == caso]
        antes = [f for f in propias if f["fin"] < stop and f["estado"] == "ok"]
        caida = [f for f in propias if f["inicio"] < start and f["fin"] >= stop]
        despues = [f for f in propias if f["inicio"] >= start]
        malo = lambda f: f["estado"] == "error" or f["ms"] > 1000  # noqa: E731
        primer_ok = next((f for f in propias if f["inicio"] >= stop and f["estado"] == "ok"), None)
        ultimo_malo = max((f["fin"] for f in caida if malo(f)), default=stop)
        estables = [f for f in caida if f["estado"] == "ok" and f["inicio"] >= ultimo_malo]
        reintegra = max((f["fin"] for f in despues if malo(f)), default=start)
        err_caida = [f for f in caida if f["estado"] == "error"]
        err_desp = [f for f in despues if f["estado"] == "error"]

        p50_antes = f"{statistics.median(f['ms'] for f in antes):.2f}" if antes else "-"
        p_ok = f"{primer_ok['fin'] - stop:.3f}" if primer_ok else "no volvió"
        p50_est = f"{statistics.median(f['ms'] for f in estables):.2f}" if estables else "-"
        tipico = (err_caida or err_desp)[0]["error"].split(":")[0] if (err_caida or err_desp) else "-"
        print(f"{caso:<14} {p50_antes:>9} {len(err_caida):>4} {p_ok:>9} {ultimo_malo - stop:>8.3f} {p50_est:>11} "
              f"{len(err_desp):>4} {reintegra - start:>9.3f}  {tipico}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sondear")
    s.add_argument("--gateway", default="crdb-1")
    s.add_argument("--duracion", type=float, default=60)
    s.add_argument("--intervalo", type=float, default=0.2)
    s.add_argument("--csv", required=True)
    le = sub.add_parser("leases")
    le.add_argument("--gateway", default="crdb-1")
    le.add_argument("--esperar-hogar", type=int, default=0, help="segundos máximos esperando leases en su región")
    r = sub.add_parser("resumir")
    r.add_argument("csv")
    r.add_argument("stop", help="archivo con la época del docker stop")
    r.add_argument("start", help="archivo con la época del docker start")
    args = parser.parse_args()
    return {"sondear": sondear, "leases": leases, "resumir": resumir}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
