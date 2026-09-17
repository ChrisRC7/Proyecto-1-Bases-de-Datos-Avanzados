-- P1 · E5 · Esquema del dominio banca en PostgreSQL de un nodo.
-- Es el mismo esquema de 01_schema.sql (E1 §2) sin lo que solo tiene sentido en un clúster:
-- LOCALITY y el tipo de región de CockroachDB. region se conserva como columna y en las
-- llaves para que seed.py y bench/latency.py usen las mismas filas y las mismas consultas;
-- así la comparación de E5 mide el motor y no un modelo de datos distinto.
-- Se ejecuta con psql conectado a cualquier base (crea p1_banca y se conecta a ella).
-- Idempotente: se puede ejecutar varias veces.

SELECT 'CREATE DATABASE p1_banca'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'p1_banca')\gexec

\connect p1_banca
SET client_min_messages = warning;  -- oculta los "already exists, skipping" al repetir

-- Una versión anterior de este archivo creaba otras tablas con los mismos nombres.
-- CREATE TABLE IF NOT EXISTS las dejaría como están y el seed no cargaría nada; se detiene aquí.
DO $$
BEGIN
    IF to_regclass('public.cliente') IS NOT NULL AND NOT EXISTS (
        SELECT FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'cliente' AND column_name = 'email'
    ) THEN
        RAISE EXCEPTION 'p1_banca tiene el esquema anterior de E5; bórrela con DROP DATABASE p1_banca y repita p1/e5.sh';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS moneda (
    codigo         CHAR(3)       PRIMARY KEY,
    nombre         TEXT          NOT NULL,
    tasa_crc       DECIMAL(12,4) NOT NULL CHECK (tasa_crc > 0),
    actualizado_en TIMESTAMPTZ   NOT NULL DEFAULT now()
);

-- Las regiones pasan a ser un valor validado: en un solo servidor no ubican datos.
CREATE TABLE IF NOT EXISTS cliente (
    region     TEXT        NOT NULL CHECK (region IN ('cr-sj', 'cr-limon', 'us-east')),
    cliente_id UUID        NOT NULL DEFAULT gen_random_uuid(),
    documento  TEXT        NOT NULL,
    nombre     TEXT        NOT NULL,
    email      TEXT        NOT NULL,
    creado_en  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (region, cliente_id),
    UNIQUE (documento)
);

CREATE TABLE IF NOT EXISTS cuenta (
    region     TEXT          NOT NULL CHECK (region IN ('cr-sj', 'cr-limon', 'us-east')),
    cuenta_id  UUID          NOT NULL DEFAULT gen_random_uuid(),
    cliente_id UUID          NOT NULL,
    moneda     CHAR(3)       NOT NULL REFERENCES moneda (codigo),
    saldo      DECIMAL(18,2) NOT NULL CHECK (saldo >= 0),
    estado     TEXT          NOT NULL DEFAULT 'ACTIVA'
                             CHECK (estado IN ('ACTIVA', 'BLOQUEADA', 'CERRADA')),
    abierta_en TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (region, cuenta_id),
    FOREIGN KEY (region, cliente_id) REFERENCES cliente (region, cliente_id)
);

CREATE TABLE IF NOT EXISTS movimiento (
    region                TEXT          NOT NULL CHECK (region IN ('cr-sj', 'cr-limon', 'us-east')),
    movimiento_id         UUID          NOT NULL DEFAULT gen_random_uuid(),
    cuenta_id             UUID          NOT NULL,
    tipo                  TEXT          NOT NULL
                          CHECK (tipo IN ('DEPOSITO', 'RETIRO', 'TRANSF_ENVIO', 'TRANSF_RECIBO')),
    monto                 DECIMAL(18,2) NOT NULL CHECK (monto > 0),
    moneda                CHAR(3)       NOT NULL REFERENCES moneda (codigo),
    saldo_resultante      DECIMAL(18,2) NOT NULL CHECK (saldo_resultante >= 0),
    contraparte_region    TEXT          CHECK (contraparte_region IN ('cr-sj', 'cr-limon', 'us-east')),
    contraparte_cuenta_id UUID,
    creado_en             TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (region, movimiento_id),
    FOREIGN KEY (region, cuenta_id) REFERENCES cuenta (region, cuenta_id)
);

CREATE INDEX IF NOT EXISTS movimiento_por_cuenta ON movimiento (region, cuenta_id, creado_en DESC);  -- O2
