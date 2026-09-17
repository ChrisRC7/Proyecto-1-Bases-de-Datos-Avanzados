-- P1 · Base de datos multi-región del dominio banca.
-- Base propia (p1_banca) para no tocar ti4601, que usan los labs 1 y 2.
-- Idempotente: se puede ejecutar varias veces.

CREATE DATABASE IF NOT EXISTS p1_banca;

-- cr-sj es la región primaria: concentra el 50 % de los clientes (E1 §1)
-- y es la región del gateway de las mediciones (crdb-1).
ALTER DATABASE p1_banca SET PRIMARY REGION "cr-sj";
ALTER DATABASE p1_banca ADD REGION IF NOT EXISTS "cr-limon";
ALTER DATABASE p1_banca ADD REGION IF NOT EXISTS "us-east";

-- SURVIVE ZONE FAILURE es el valor por defecto; se declara para que quede explícito
-- en la evidencia. SURVIVE REGION FAILURE necesitaría más nodos por región.
ALTER DATABASE p1_banca SURVIVE ZONE FAILURE;
