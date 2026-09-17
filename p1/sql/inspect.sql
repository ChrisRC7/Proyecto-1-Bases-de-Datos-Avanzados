-- P1 · Consultas de inspección para la evidencia de E2 (solo lectura).
-- Lo ejecuta p1/evidence.sh; la salida completa va a evidence/p1/e2-inspect.txt.

\echo '== 1. Regiones y meta de supervivencia'
SHOW REGIONS FROM DATABASE p1_banca;
SHOW SURVIVAL GOAL FROM DATABASE p1_banca;

\echo '== 2. Localidad de cada tabla'
SELECT table_name, locality FROM [SHOW TABLES] WHERE schema_name = 'public' ORDER BY table_name;

\echo '== 3. DDL generado por CockroachDB'
SHOW CREATE TABLE moneda;
SHOW CREATE TABLE cliente;
SHOW CREATE TABLE cuenta;
SHOW CREATE TABLE movimiento;
SHOW CREATE TABLE p1_control.public.folio_comprobante;

\echo '== 4. Filas por fragmento'
SELECT 'cliente' AS tabla, region, count(*) AS filas FROM cliente GROUP BY region
UNION ALL SELECT 'cuenta', region, count(*) FROM cuenta GROUP BY region
UNION ALL SELECT 'movimiento', region, count(*) FROM movimiento GROUP BY region
ORDER BY tabla, region;
SELECT codigo, nombre, tasa_crc FROM moneda ORDER BY codigo;

\echo '== 5. Configuración de zona (declarada)'
SELECT target, raw_config_sql FROM [SHOW ZONE CONFIGURATIONS]
WHERE target LIKE 'DATABASE p1_%' OR target LIKE '%p1_banca.public.%' OR target LIKE '%p1_control.%'
ORDER BY target;

\echo '== 6. Rangos y réplicas (observado)'
\echo '-- moneda (GLOBAL)'
SELECT range_id, lease_holder, lease_holder_locality, voting_replicas, non_voting_replicas, replica_localities
FROM [SHOW RANGES FROM TABLE moneda WITH DETAILS];
\echo '-- cliente (RBR)'
SELECT range_id, lease_holder, lease_holder_locality, voting_replicas, non_voting_replicas, replica_localities
FROM [SHOW RANGES FROM TABLE cliente WITH DETAILS];
\echo '-- cuenta (RBR)'
SELECT range_id, lease_holder, lease_holder_locality, voting_replicas, non_voting_replicas, replica_localities
FROM [SHOW RANGES FROM TABLE cuenta WITH DETAILS];
\echo '-- movimiento (RBR)'
SELECT range_id, lease_holder, lease_holder_locality, voting_replicas, non_voting_replicas, replica_localities
FROM [SHOW RANGES FROM TABLE movimiento WITH DETAILS];
\echo '-- p1_control.folio_comprobante (E4, RF=3)'
SELECT range_id, lease_holder, lease_holder_locality, voting_replicas, non_voting_replicas, replica_localities
FROM [SHOW RANGES FROM TABLE p1_control.public.folio_comprobante WITH DETAILS];

\echo '== 7. Nodos: node_id no coincide con el número del contenedor'
SELECT node_id, address, locality, is_live FROM crdb_internal.gossip_nodes ORDER BY node_id;
