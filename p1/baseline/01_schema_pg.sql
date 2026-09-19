-- P1 · E5 · Baseline: el mismo esquema de p1/sql/01_schema.sql en PostgreSQL de un nodo.
-- Traducción mecánica, sin cambios de diseño:
--   crdb_internal_region -> TEXT con CHECK sobre las tres regiones
--   STRING               -> TEXT
--   LOCALITY ...         -> (no existe: un solo nodo)
--   INDEX en línea       -> CREATE INDEX aparte
-- Se conservan PK compuestas, FK compuestas y UNIQUE (documento): el diseño de E1 es idéntico;
-- lo único que cambia entre los dos motores es la distribución.
-- Se ejecuta conectado a p1_banca (la crea seed_pg.py). Idempotente.

CREATE TABLE IF NOT EXISTS moneda (
    codigo         CHAR(3)       PRIMARY KEY,
    nombre         TEXT          NOT NULL,
    tasa_crc       DECIMAL(12,4) NOT NULL CHECK (tasa_crc > 0),
    actualizado_en TIMESTAMPTZ   NOT NULL DEFAULT now()
);

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
    contraparte_region    TEXT,
    contraparte_cuenta_id UUID,
    creado_en             TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (region, movimiento_id),
    FOREIGN KEY (region, cuenta_id) REFERENCES cuenta (region, cuenta_id)
);

CREATE INDEX IF NOT EXISTS movimiento_por_cuenta ON movimiento (region, cuenta_id, creado_en DESC);  -- O2
