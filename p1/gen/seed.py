#!/usr/bin/env python3
"""Genera y carga datos deterministas del dominio banca en p1_banca.

Volumen y proporciones salen del E1 (p1/docs/E1-diseno.md §1):
3 000 clientes (50/30/20 % por región), ~1,5 cuentas por cliente,
~30 movimientos por cliente y escrituras O3/O4/O5 en proporción 150/100/30.

Con la misma --semilla y --clientes, cualquier máquina genera exactamente las
mismas filas; la "huella" impresa al final permite comprobarlo.
"""

from __future__ import annotations

import argparse
import hashlib
import random
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import psycopg

REGIONES = ("cr-sj", "cr-limon", "us-east")
PESO_REGION = (0.50, 0.30, 0.20)

# Tasas fijas de referencia para el seed; no son tasas oficiales.
MONEDAS = (
    ("CRC", "Colón costarricense", Decimal("1.0000")),
    ("USD", "Dólar estadounidense", Decimal("505.0000")),
    ("EUR", "Euro", Decimal("550.0000")),
)

# Moneda de las cuentas según región: (moneda, peso).
MONEDA_POR_REGION = {
    "cr-sj": (("CRC", 0.75), ("USD", 0.20), ("EUR", 0.05)),
    "cr-limon": (("CRC", 0.85), ("USD", 0.15)),
    "us-east": (("USD", 1.00),),
}

# Montos en céntimos por moneda: (mínimo, máximo).
RANGO_MONTO = {"CRC": (1_000_00, 250_000_00), "USD": (5_00, 800_00), "EUR": (5_00, 800_00)}
RANGO_APERTURA = {"CRC": (50_000_00, 2_000_000_00), "USD": (100_00, 5_000_00), "EUR": (100_00, 5_000_00)}

# Escrituras del E1: O3 depósito/retiro, O4 transferencia local, O5 transferencia entre regiones.
PESO_EVENTO = (("O3", 150), ("O4", 100), ("O5", 30))

NOMBRES = ("Ana", "Luis", "María", "José", "Carmen", "Jorge", "Laura", "Diego", "Sofía", "Andrés",
           "Valeria", "Carlos", "Daniela", "Pablo", "Gabriela", "Mario", "Natalia", "Ricardo")
APELLIDOS = ("Mora", "Rojas", "Vargas", "Jiménez", "Solís", "Castro", "Araya", "Brenes", "Quesada",
             "Chaves", "Smith", "Johnson", "Brown", "Garcia", "Miller", "Davis", "Campos", "Salas")

INICIO = datetime(2026, 1, 1, tzinfo=timezone.utc)


@dataclass
class Cuenta:
    region: str
    cuenta_id: uuid.UUID
    cliente_id: uuid.UUID
    moneda: str
    abierta_en: datetime
    saldo: int = 0  # céntimos
    movimientos: int = field(default=0)


def nuevo_uuid(rng: random.Random) -> uuid.UUID:
    return uuid.UUID(int=rng.getrandbits(128), version=4)


def elegir(rng: random.Random, opciones) -> str:
    valores, pesos = zip(*opciones)
    return rng.choices(valores, weights=pesos, k=1)[0]


def centimos(valor: int) -> Decimal:
    return Decimal(valor).scaleb(-2)


def documento(region: str, n: int) -> str:
    if region == "us-east":
        return f"US-P{n:08d}"
    # Formato de cédula costarricense; único porque n < 10^8.
    return f"{n % 7 + 1}-{n // 10_000 % 10_000:04d}-{n % 10_000:04d}"


def generar(semilla: int, n_clientes: int):
    rng = random.Random(semilla)
    clientes, cuentas, movimientos = [], [], []

    # Clientes creados durante enero; cuentas abiertas minutos después.
    for n in range(n_clientes):
        region = rng.choices(REGIONES, weights=PESO_REGION, k=1)[0]
        cliente_id = nuevo_uuid(rng)
        nombre = f"{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)} {rng.choice(APELLIDOS)}"
        creado = INICIO + timedelta(seconds=rng.randrange(30 * 86_400))
        email = f"cliente{n:05d}@example.com"
        clientes.append((region, cliente_id, documento(region, n), nombre, email, creado))

        for _ in range(1 if rng.random() < 0.5 else 2):
            moneda = elegir(rng, MONEDA_POR_REGION[region])
            abierta = creado + timedelta(minutes=rng.randrange(1, 60))
            cuenta = Cuenta(region, nuevo_uuid(rng), cliente_id, moneda, abierta)
            cuentas.append(cuenta)
            monto = rng.randrange(*RANGO_APERTURA[moneda])
            cuenta.saldo = monto
            movimientos.append((region, nuevo_uuid(rng), cuenta.cuenta_id, "DEPOSITO", centimos(monto),
                                moneda, centimos(cuenta.saldo), None, None, abierta))

    # Índices para elegir contraparte de la misma moneda, en la misma región o en otra.
    por_region_moneda: dict[tuple[str, str], list[Cuenta]] = {}
    for cuenta in cuentas:
        por_region_moneda.setdefault((cuenta.region, cuenta.moneda), []).append(cuenta)

    objetivo = 30 * n_clientes
    eventos = objetivo - len(movimientos)
    paso = timedelta(seconds=(240 * 86_400) / max(eventos, 1))
    t = INICIO + timedelta(days=31)

    while len(movimientos) < objetivo:
        t += paso
        origen = rng.choice(cuentas)
        evento = elegir(rng, PESO_EVENTO)
        monto = rng.randrange(*RANGO_MONTO[origen.moneda])

        destino = None
        if evento == "O4":
            candidatas = por_region_moneda[(origen.region, origen.moneda)]
            if len(candidatas) > 1:
                destino = origen
                while destino is origen:
                    destino = rng.choice(candidatas)
        elif evento == "O5":
            otras = [r for r in REGIONES if r != origen.region and (r, origen.moneda) in por_region_moneda]
            if otras:
                destino = rng.choice(por_region_moneda[(rng.choice(otras), origen.moneda)])

        if destino is None or origen.saldo < monto:
            # Depósito o retiro (O3); también cubre transferencias sin contraparte o sin fondos.
            if rng.random() < 0.55 or origen.saldo < monto:
                origen.saldo += monto
                tipo = "DEPOSITO"
            else:
                origen.saldo -= monto
                tipo = "RETIRO"
            movimientos.append((origen.region, nuevo_uuid(rng), origen.cuenta_id, tipo, centimos(monto),
                                origen.moneda, centimos(origen.saldo), None, None, t))
            continue

        # Doble asiento (E1 §3): un movimiento en la región de cada cuenta.
        origen.saldo -= monto
        destino.saldo += monto
        movimientos.append((origen.region, nuevo_uuid(rng), origen.cuenta_id, "TRANSF_ENVIO", centimos(monto),
                            origen.moneda, centimos(origen.saldo), destino.region, destino.cuenta_id, t))
        movimientos.append((destino.region, nuevo_uuid(rng), destino.cuenta_id, "TRANSF_RECIBO", centimos(monto),
                            destino.moneda, centimos(destino.saldo), origen.region, origen.cuenta_id, t))

    filas_cuenta = [(c.region, c.cuenta_id, c.cliente_id, c.moneda, centimos(c.saldo), "ACTIVA", c.abierta_en)
                    for c in cuentas]
    return clientes, filas_cuenta, movimientos


def huella(*tablas) -> str:
    h = hashlib.sha256()
    for filas in tablas:
        for fila in filas:
            h.update(repr(fila).encode())
    return h.hexdigest()[:16]


def insertar(conn: psycopg.Connection, tabla: str, columnas: str, filas: list, lote: int) -> None:
    n_col = len(columnas.split(","))
    marcador = "(" + ",".join(["%s"] * n_col) + ")"
    # Ordenar por región hace que cada lote escriba en una sola región y evita
    # transacciones de carga que crucen regiones.
    filas = sorted(filas, key=lambda f: REGIONES.index(f[0]))
    for i in range(0, len(filas), lote):
        bloque = filas[i:i + lote]
        sql = f"INSERT INTO {tabla} ({columnas}) VALUES " + ",".join([marcador] * len(bloque))
        conn.execute(sql, [valor for fila in bloque for valor in fila])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--semilla", type=int, default=4601)
    parser.add_argument("--clientes", type=int, default=3000)
    parser.add_argument("--lote", type=int, default=500, help="filas por INSERT")
    parser.add_argument("--reset", action="store_true", help="vacía las tablas antes de cargar")
    args = parser.parse_args()

    inicio = time.perf_counter()
    clientes, cuentas, movimientos = generar(args.semilla, args.clientes)
    print(f"Generado en {time.perf_counter() - inicio:.1f} s: {len(clientes)} clientes, "
          f"{len(cuentas)} cuentas, {len(movimientos)} movimientos")
    print(f"Huella de datos (semilla={args.semilla}, clientes={args.clientes}): "
          f"{huella(clientes, cuentas, movimientos)}")

    with psycopg.connect(dbname="p1_banca", autocommit=True) as conn:
        existentes = conn.execute("SELECT count(*) FROM cliente").fetchone()[0]
        if existentes and not args.reset:
            print(f"cliente ya tiene {existentes} filas; no se carga nada. Use --reset para recargar.")
            return 0
        if args.reset:
            conn.execute("TRUNCATE movimiento, cuenta, cliente")

        conn.execute(
            "UPSERT INTO moneda (codigo, nombre, tasa_crc, actualizado_en) VALUES "
            + ",".join(["(%s, %s, %s, %s)"] * len(MONEDAS)),
            [v for m in MONEDAS for v in (*m, INICIO)],
        )

        inicio = time.perf_counter()
        insertar(conn, "cliente", "region, cliente_id, documento, nombre, email, creado_en", clientes, args.lote)
        insertar(conn, "cuenta", "region, cuenta_id, cliente_id, moneda, saldo, estado, abierta_en",
                 cuentas, args.lote)
        insertar(conn, "movimiento",
                 "region, movimiento_id, cuenta_id, tipo, monto, moneda, saldo_resultante, "
                 "contraparte_region, contraparte_cuenta_id, creado_en",
                 movimientos, args.lote)
        print(f"Cargado en {time.perf_counter() - inicio:.1f} s")

        print("\nFilas por región:")
        for tabla in ("cliente", "cuenta", "movimiento"):
            filas = conn.execute(
                f"SELECT region::STRING, count(*) FROM {tabla} GROUP BY region ORDER BY region"
            ).fetchall()
            print(f"  {tabla:<10} " + "  ".join(f"{r}={n}" for r, n in filas))
    return 0


if __name__ == "__main__":
    sys.exit(main())
