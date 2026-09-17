-- P1 · Esquema del dominio banca (E1 §2, anexo de DDL).
-- Se ejecuta conectado a p1_banca, después de 00_database.sql.
-- Idempotente: CREATE TABLE IF NOT EXISTS.

-- Catálogo pequeño, leído desde las tres regiones y escrito ~1 vez al día (O7).
CREATE TABLE IF NOT EXISTS moneda (
    codigo         CHAR(3)       PRIMARY KEY,
    nombre         STRING        NOT NULL,
    tasa_crc       DECIMAL(12,4) NOT NULL CHECK (tasa_crc > 0),
    actualizado_en TIMESTAMPTZ   NOT NULL DEFAULT now()
) LOCALITY GLOBAL;

-- Fragmentación horizontal primaria por region. Única relación con PII.
-- region no tiene DEFAULT: toda fila debe declarar su región de apertura.
CREATE TABLE IF NOT EXISTS cliente (
    region     public.crdb_internal_region NOT NULL,
    cliente_id UUID        NOT NULL DEFAULT gen_random_uuid(),
    documento  STRING      NOT NULL,
    nombre     STRING      NOT NULL,
    email      STRING      NOT NULL,
    creado_en  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (region, cliente_id),
    UNIQUE (documento)
) LOCALITY REGIONAL BY ROW AS region;

-- Fragmentación derivada de cliente: la FK compuesta obliga a que la cuenta
-- viva en la región de su dueño.
CREATE TABLE IF NOT EXISTS cuenta (
    region     public.crdb_internal_region NOT NULL,
    cuenta_id  UUID          NOT NULL DEFAULT gen_random_uuid(),
    cliente_id UUID          NOT NULL,
    moneda     CHAR(3)       NOT NULL REFERENCES moneda (codigo),
    saldo      DECIMAL(18,2) NOT NULL CHECK (saldo >= 0),
    estado     STRING        NOT NULL DEFAULT 'ACTIVA'
                             CHECK (estado IN ('ACTIVA', 'BLOQUEADA', 'CERRADA')),
    abierta_en TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (region, cuenta_id),
    FOREIGN KEY (region, cliente_id) REFERENCES cliente (region, cliente_id)
) LOCALITY REGIONAL BY ROW AS region;

-- Fragmentación derivada de cuenta. contraparte_* no lleva FK (doble asiento, E1 §3).
CREATE TABLE IF NOT EXISTS movimiento (
    region                public.crdb_internal_region NOT NULL,
    movimiento_id         UUID          NOT NULL DEFAULT gen_random_uuid(),
    cuenta_id             UUID          NOT NULL,
    tipo                  STRING        NOT NULL
                          CHECK (tipo IN ('DEPOSITO', 'RETIRO', 'TRANSF_ENVIO', 'TRANSF_RECIBO')),
    monto                 DECIMAL(18,2) NOT NULL CHECK (monto > 0),
    moneda                CHAR(3)       NOT NULL REFERENCES moneda (codigo),
    saldo_resultante      DECIMAL(18,2) NOT NULL CHECK (saldo_resultante >= 0),
    contraparte_region    public.crdb_internal_region,
    contraparte_cuenta_id UUID,
    creado_en             TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (region, movimiento_id),
    FOREIGN KEY (region, cuenta_id) REFERENCES cuenta (region, cuenta_id),
    INDEX movimiento_por_cuenta (region, cuenta_id, creado_en DESC)  -- O2
) LOCALITY REGIONAL BY ROW AS region;
