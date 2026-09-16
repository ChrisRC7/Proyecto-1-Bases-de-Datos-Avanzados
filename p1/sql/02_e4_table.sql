-- P1 · Tabla operacional con RF=3 para la prueba de falla (E4).
--
-- No vive en p1_banca: en una base multi-región con SURVIVE ZONE FAILURE, cada
-- partición REGIONAL BY ROW pide num_replicas = 5 y num_voters = 3 con
-- voter_constraints en su región hogar (ver SHOW ZONE CONFIGURATIONS). Con un nodo
-- por región esa configuración no se puede cumplir: los rangos observados tienen
-- 3 votantes repartidos entre regiones, que es un respaldo del motor y no lo que
-- declara su configuración. Medir la falla sobre ellos mezclaría ambas cosas.
-- Una base sin regiones con num_replicas = 3 sí cumple su configuración: 3 votantes,
-- uno por nodo, y la mayoría 2/3 es exactamente la declarada.
--
-- Dominio: serie central de folios de comprobante. Cada transferencia toma el
-- siguiente folio; lo usa la sonda de E4 como escritura confirmada y verificable.

CREATE DATABASE IF NOT EXISTS p1_control;

CREATE TABLE IF NOT EXISTS p1_control.public.folio_comprobante (
    serie          STRING      PRIMARY KEY,
    ultimo_folio   INT8        NOT NULL DEFAULT 0 CHECK (ultimo_folio >= 0),
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Se declara RF=3 explícito para que la evidencia no dependa del valor por defecto.
ALTER TABLE p1_control.public.folio_comprobante CONFIGURE ZONE USING num_replicas = 3;

INSERT INTO p1_control.public.folio_comprobante (serie, ultimo_folio)
VALUES ('TRANSFERENCIAS', 0)
ON CONFLICT (serie) DO NOTHING;
