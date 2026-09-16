#!/usr/bin/env python3
"""Verificador de solo lectura del P1: clúster, esquema, fragmentación y datos.

No crea ni modifica nada. Termina con código 0 solo si todas las comprobaciones pasan.
"""

from __future__ import annotations

import sys
import time

import psycopg

REGIONES = {"cr-sj", "cr-limon", "us-east"}
LOCALIDAD_ESPERADA = {
    "moneda": "GLOBAL",
    "cliente": "REGIONAL BY ROW AS region",
    "cuenta": "REGIONAL BY ROW AS region",
    "movimiento": "REGIONAL BY ROW AS region",
}
FRAGMENTADAS = ("cliente", "cuenta", "movimiento")


def uno(conn, sql: str):
    return conn.execute(sql).fetchone()[0]


def nodos_vivos(conn):
    filas = conn.execute("SELECT locality, is_live FROM crdb_internal.gossip_nodes").fetchall()
    vivas = {loc.split(",")[0].removeprefix("region=") for loc, vivo in filas if vivo}
    return vivas == REGIONES, f"regiones vivas: {sorted(vivas)}"


def regiones_base(conn):
    filas = conn.execute("SELECT region, \"primary\" FROM [SHOW REGIONS FROM DATABASE p1_banca]").fetchall()
    primaria = [r for r, p in filas if p]
    return {r for r, _ in filas} == REGIONES and primaria == ["cr-sj"], f"{len(filas)} regiones, primaria={primaria}"


def localidades(conn):
    reales = dict(conn.execute("SELECT table_name, locality FROM [SHOW TABLES] WHERE schema_name = 'public'").fetchall())
    malas = {t: reales.get(t) for t, loc in LOCALIDAD_ESPERADA.items() if reales.get(t) != loc}
    return not malas, "todas correctas" if not malas else f"incorrectas: {malas}"


def filas_por_region(conn):
    faltan = []
    for tabla in FRAGMENTADAS:
        presentes = {r for (r,) in conn.execute(f"SELECT DISTINCT region::STRING FROM {tabla}").fetchall()}
        if presentes != REGIONES:
            faltan.append(f"{tabla}: {sorted(presentes)}")
    return not faltan, "las tres tablas tienen filas en las 3 regiones" if not faltan else "; ".join(faltan)


def completitud(conn):
    # Toda fila pertenece a exactamente un fragmento: region no nula y dentro del dominio.
    sin_region = sum(uno(conn, f"SELECT count(*) FROM {t} WHERE region IS NULL") for t in FRAGMENTADAS)
    return sin_region == 0, f"filas sin región: {sin_region}"


def reconstruccion(conn):
    detalle = []
    ok = True
    for tabla in FRAGMENTADAS:
        total = uno(conn, f"SELECT count(*) FROM {tabla}")
        union = uno(conn, " UNION ALL ".join(
            f"SELECT count(*) AS n FROM {tabla} WHERE region = '{r}'" for r in sorted(REGIONES)
        ).join(["SELECT sum(n)::INT8 FROM (", ")"]))
        ok &= total == union
        detalle.append(f"{tabla} {union}/{total}")
    return ok, ", ".join(detalle)


def derivada(conn):
    # Si la fragmentación derivada se cumple, ninguna cuenta está fuera de la región
    # de su cliente ni ningún movimiento fuera de la región de su cuenta.
    cuentas = uno(conn, """
        SELECT count(*) FROM cuenta c JOIN cliente k ON k.cliente_id = c.cliente_id
        WHERE k.region <> c.region""")
    movimientos = uno(conn, """
        SELECT count(*) FROM movimiento m JOIN cuenta c ON c.cuenta_id = m.cuenta_id
        WHERE c.region <> m.region""")
    return cuentas == 0 and movimientos == 0, f"cuentas fuera de región: {cuentas}, movimientos: {movimientos}"


def doble_asiento(conn):
    envios = uno(conn, "SELECT count(*) FROM movimiento WHERE tipo = 'TRANSF_ENVIO'")
    recibos = uno(conn, "SELECT count(*) FROM movimiento WHERE tipo = 'TRANSF_RECIBO'")
    return envios == recibos, f"envíos={envios}, recibos={recibos}"


def saldos(conn):
    distintos = uno(conn, """
        SELECT count(*) FROM cuenta c
        JOIN LATERAL (
            SELECT saldo_resultante FROM movimiento m
            WHERE m.region = c.region AND m.cuenta_id = c.cuenta_id
            ORDER BY m.creado_en DESC LIMIT 1
        ) u ON true
        WHERE u.saldo_resultante <> c.saldo""")
    return distintos == 0, f"cuentas cuyo saldo no coincide con su último movimiento: {distintos}"


def votantes_e4(conn):
    # La reubicación de réplicas tarda tras crear la tabla; se reintenta hasta 90 s.
    limite = time.monotonic() + 90
    while True:
        filas = conn.execute("""
            SELECT voting_replicas FROM [SHOW RANGES FROM TABLE
                p1_control.public.folio_comprobante WITH DETAILS]""").fetchall()
        ok = bool(filas) and all(len(v) == 3 for (v,) in filas)
        if ok or time.monotonic() > limite:
            return ok, f"votantes por rango: {[list(v) for (v,) in filas]}"
        time.sleep(5)


COMPROBACIONES = (
    ("tres nodos vivos, uno por región", nodos_vivos),
    ("p1_banca tiene 3 regiones con cr-sj primaria", regiones_base),
    ("localidad de cada tabla (GLOBAL / RBR)", localidades),
    ("filas en las 3 regiones", filas_por_region),
    ("completitud: toda fila tiene región", completitud),
    ("reconstrucción: unión de fragmentos = tabla", reconstruccion),
    ("fragmentación derivada respetada", derivada),
    ("doble asiento de transferencias", doble_asiento),
    ("saldos consistentes con movimientos", saldos),
    ("folio_comprobante (E4) tiene 3 votantes", votantes_e4),
)


def main() -> int:
    aprobadas = 0
    with psycopg.connect(dbname="p1_banca", autocommit=True) as conn:
        for nombre, comprobar in COMPROBACIONES:
            try:
                ok, detalle = comprobar(conn)
            except psycopg.Error as exc:
                ok, detalle = False, f"error: {exc.diag.message_primary or exc}"
            aprobadas += ok
            print(f"[{' OK ' if ok else 'FAIL'}] {nombre} — {detalle}")
    print(f"\nResultado: {aprobadas}/{len(COMPROBACIONES)} verificaciones.")
    return 0 if aprobadas == len(COMPROBACIONES) else 1


if __name__ == "__main__":
    sys.exit(main())
