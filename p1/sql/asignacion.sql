-- P1 · E1 §8 · Asignación observada: fragmento → rango → leaseholder y votantes (solo lectura).
-- Lo ejecuta p1/evidence.sh; la salida va a evidence/p1/e1-asignacion.txt.
--
-- Cómo se obtiene: cada fila se codifica a su clave física con crdb_internal.encode_key y se
-- busca el rango que la contiene. No se deduce de start_key: CockroachDB fusiona rangos vacíos
-- y un rango puede empezar antes del prefijo de su partición (ver SHOW RANGES en e2-inspect §6).
-- El resultado muestra qué rango guarda cada fragmento, qué nodo tiene su lease (quién lo
-- atiende) y dónde están sus votantes (quién lo replica).

\echo '== 1. Nodos: node_id, contenedor y región'
SELECT node_id, split_part(address, ':', 1) AS contenedor, locality, is_live
FROM crdb_internal.gossip_nodes ORDER BY node_id;

\echo '== 2. Fragmento → rango → leaseholder y votantes'
WITH filas AS (
    SELECT 'cliente' AS tabla, region::STRING AS fragmento,
           crdb_internal.encode_key('cliente'::REGCLASS::OID::INT8, 1, (region, cliente_id)) AS k
    FROM cliente
    UNION ALL
    SELECT 'cuenta', region::STRING,
           crdb_internal.encode_key('cuenta'::REGCLASS::OID::INT8, 1, (region, cuenta_id))
    FROM cuenta
    UNION ALL
    SELECT 'movimiento', region::STRING,
           crdb_internal.encode_key('movimiento'::REGCLASS::OID::INT8, 1, (region, movimiento_id))
    FROM movimiento
    UNION ALL
    SELECT 'moneda', 'completa (GLOBAL)',
           crdb_internal.encode_key('moneda'::REGCLASS::OID::INT8, 1, (codigo,))
    FROM moneda
), rangos AS (
    SELECT range_id, start_key, end_key FROM crdb_internal.ranges_no_leases
), detalle AS (
    SELECT 'cliente' AS tabla, range_id, lease_holder, lease_holder_locality, voting_replicas, replica_localities
    FROM [SHOW RANGES FROM TABLE cliente WITH DETAILS]
    UNION ALL SELECT 'cuenta', range_id, lease_holder, lease_holder_locality, voting_replicas, replica_localities
    FROM [SHOW RANGES FROM TABLE cuenta WITH DETAILS]
    UNION ALL SELECT 'movimiento', range_id, lease_holder, lease_holder_locality, voting_replicas, replica_localities
    FROM [SHOW RANGES FROM TABLE movimiento WITH DETAILS]
    UNION ALL SELECT 'moneda', range_id, lease_holder, lease_holder_locality, voting_replicas, replica_localities
    FROM [SHOW RANGES FROM TABLE moneda WITH DETAILS]
)
SELECT f.tabla, f.fragmento, r.range_id, count(*) AS filas,
       d.lease_holder AS lh_nodo,
       split_part(split_part(d.lease_holder_locality, ',', 1), '=', 2) AS lh_region,
       d.voting_replicas AS votantes,
       CASE WHEN f.tabla = 'moneda' THEN NULL  -- GLOBAL: sin región hogar por fila
            ELSE split_part(split_part(d.lease_holder_locality, ',', 1), '=', 2) = f.fragmento
       END AS lh_en_hogar
FROM filas f
JOIN rangos r ON f.k >= r.start_key AND f.k < r.end_key
JOIN detalle d ON d.tabla = f.tabla AND d.range_id = r.range_id
GROUP BY f.tabla, f.fragmento, r.range_id, d.lease_holder, d.lease_holder_locality, d.voting_replicas
ORDER BY f.tabla, f.fragmento, r.range_id;

\echo '== 3. Resumen: fragmentos cuyo leaseholder NO está en su región hogar (debe dar 0 filas RBR)'
-- Se repite la consulta resumida por fragmento. moneda se excluye: GLOBAL no tiene región hogar
-- por fila; la sirve la réplica local de cada nodo.
WITH filas AS (
    SELECT 'cliente' AS tabla, region::STRING AS fragmento,
           crdb_internal.encode_key('cliente'::REGCLASS::OID::INT8, 1, (region, cliente_id)) AS k
    FROM cliente
    UNION ALL
    SELECT 'cuenta', region::STRING,
           crdb_internal.encode_key('cuenta'::REGCLASS::OID::INT8, 1, (region, cuenta_id))
    FROM cuenta
    UNION ALL
    SELECT 'movimiento', region::STRING,
           crdb_internal.encode_key('movimiento'::REGCLASS::OID::INT8, 1, (region, movimiento_id))
    FROM movimiento
), rangos AS (
    SELECT range_id, start_key, end_key FROM crdb_internal.ranges_no_leases
), lh AS (
    SELECT 'cliente' AS tabla, range_id, lease_holder_locality FROM [SHOW RANGES FROM TABLE cliente WITH DETAILS]
    UNION ALL SELECT 'cuenta', range_id, lease_holder_locality FROM [SHOW RANGES FROM TABLE cuenta WITH DETAILS]
    UNION ALL SELECT 'movimiento', range_id, lease_holder_locality FROM [SHOW RANGES FROM TABLE movimiento WITH DETAILS]
)
SELECT f.tabla, f.fragmento, count(*) AS filas_con_lease_fuera_de_hogar
FROM filas f
JOIN rangos r ON f.k >= r.start_key AND f.k < r.end_key
JOIN lh ON lh.tabla = f.tabla AND lh.range_id = r.range_id
WHERE split_part(split_part(lh.lease_holder_locality, ',', 1), '=', 2) <> f.fragmento
GROUP BY 1, 2 ORDER BY 1, 2;
