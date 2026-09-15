-- p1/sql/01_postgres_schema.sql
DROP TABLE IF EXISTS movimiento;
DROP TABLE IF EXISTS cuenta;
DROP TABLE IF EXISTS cliente;

CREATE TABLE cliente (
    cliente_id UUID PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    documento VARCHAR(50) NOT NULL,
    region VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE cuenta (
    cuenta_id UUID PRIMARY KEY,
    cliente_id UUID NOT NULL REFERENCES cliente(cliente_id),
    region VARCHAR(20) NOT NULL,
    saldo DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE movimiento (
    movimiento_id UUID PRIMARY KEY,
    cuenta_id UUID NOT NULL REFERENCES cuenta(cuenta_id),
    tipo VARCHAR(20) NOT NULL,
    monto DECIMAL(12, 2) NOT NULL,
    region VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_cuenta_cliente ON cuenta(cliente_id);
CREATE INDEX idx_movimiento_cuenta ON movimiento(cuenta_id);