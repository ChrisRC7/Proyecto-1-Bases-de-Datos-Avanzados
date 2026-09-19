-- P1 · E1 §5 · Consultas de prueba de la tabla de verificación (solo lectura).
-- Lo ejecuta p1/evidence.sh; la salida va a evidence/p1/e1-verificacion.txt.
-- Cada consulta devuelve el número que el E1 cita en su justificación.

\echo '== 1. Completitud: toda fila cae en algún fragmento'
-- Un fragmento es region = 'r'. Una fila queda fuera de todos si su región es nula o
-- no es ninguna de las tres. Debe dar 0 en las tres tablas.
SELECT 'cliente' AS tabla, count(*) FILTER (WHERE region IS NULL
           OR region NOT IN ('cr-sj', 'cr-limon', 'us-east')) AS fuera_de_fragmento
FROM cliente
UNION ALL
SELECT 'cuenta', count(*) FILTER (WHERE region IS NULL
           OR region NOT IN ('cr-sj', 'cr-limon', 'us-east'))
FROM cuenta
UNION ALL
SELECT 'movimiento', count(*) FILTER (WHERE region IS NULL
           OR region NOT IN ('cr-sj', 'cr-limon', 'us-east'))
FROM movimiento;

\echo '== 2. Reconstrucción: la unión de los fragmentos es la relación'
-- EXCEPT en los dos sentidos: filas de la tabla que no salen de la unión y al revés.
-- Deben dar 0; además la suma de fragmentos debe igualar el total.
SELECT 'cliente' AS tabla,
       (SELECT count(*) FROM cliente) AS total,
       (SELECT count(*) FROM cliente WHERE region = 'cr-sj')
     + (SELECT count(*) FROM cliente WHERE region = 'cr-limon')
     + (SELECT count(*) FROM cliente WHERE region = 'us-east') AS suma_fragmentos,
       (SELECT count(*) FROM (
            SELECT region, cliente_id FROM cliente
            EXCEPT
            SELECT region, cliente_id FROM (
                SELECT region, cliente_id FROM cliente WHERE region = 'cr-sj'
                UNION ALL SELECT region, cliente_id FROM cliente WHERE region = 'cr-limon'
                UNION ALL SELECT region, cliente_id FROM cliente WHERE region = 'us-east') u)) AS faltan
UNION ALL
SELECT 'cuenta',
       (SELECT count(*) FROM cuenta),
       (SELECT count(*) FROM cuenta WHERE region = 'cr-sj')
     + (SELECT count(*) FROM cuenta WHERE region = 'cr-limon')
     + (SELECT count(*) FROM cuenta WHERE region = 'us-east'),
       (SELECT count(*) FROM (
            SELECT region, cuenta_id FROM cuenta
            EXCEPT
            SELECT region, cuenta_id FROM (
                SELECT region, cuenta_id FROM cuenta WHERE region = 'cr-sj'
                UNION ALL SELECT region, cuenta_id FROM cuenta WHERE region = 'cr-limon'
                UNION ALL SELECT region, cuenta_id FROM cuenta WHERE region = 'us-east') u))
UNION ALL
SELECT 'movimiento',
       (SELECT count(*) FROM movimiento),
       (SELECT count(*) FROM movimiento WHERE region = 'cr-sj')
     + (SELECT count(*) FROM movimiento WHERE region = 'cr-limon')
     + (SELECT count(*) FROM movimiento WHERE region = 'us-east'),
       (SELECT count(*) FROM (
            SELECT region, movimiento_id FROM movimiento
            EXCEPT
            SELECT region, movimiento_id FROM (
                SELECT region, movimiento_id FROM movimiento WHERE region = 'cr-sj'
                UNION ALL SELECT region, movimiento_id FROM movimiento WHERE region = 'cr-limon'
                UNION ALL SELECT region, movimiento_id FROM movimiento WHERE region = 'us-east') u));

\echo '== 3. Disyunción: ninguna entidad está en dos fragmentos'
-- La PK es (region, id): la misma id con dos regiones sería la misma entidad en dos
-- fragmentos. Deben dar 0.
SELECT 'cliente' AS tabla, count(*) AS ids_en_mas_de_un_fragmento
FROM (SELECT cliente_id FROM cliente GROUP BY cliente_id HAVING count(DISTINCT region) > 1)
UNION ALL
SELECT 'cuenta', count(*)
FROM (SELECT cuenta_id FROM cuenta GROUP BY cuenta_id HAVING count(DISTINCT region) > 1)
UNION ALL
SELECT 'movimiento', count(*)
FROM (SELECT movimiento_id FROM movimiento GROUP BY movimiento_id HAVING count(DISTINCT region) > 1);

\echo '== 4. Derivada: cada fila está en el fragmento de su padre'
-- cuenta_r = cuenta ⋉ cliente_r solo si ninguna cuenta tiene otra región que su dueño
-- (igual para movimiento y su cuenta). Deben dar 0.
SELECT 'cuenta vs cliente' AS relacion, count(*) AS filas_fuera_del_fragmento_del_padre
FROM cuenta c JOIN cliente k ON k.cliente_id = c.cliente_id
WHERE k.region <> c.region
UNION ALL
SELECT 'movimiento vs cuenta', count(*)
FROM movimiento m JOIN cuenta c ON c.cuenta_id = m.cuenta_id
WHERE c.region <> m.region;

\echo '== 5. Doble asiento: una transferencia entre regiones deja un movimiento por fragmento'
-- Si un movimiento perteneciera a las dos cuentas, estaría en dos fragmentos. Cada envío
-- tiene su recibo en el fragmento de la contraparte.
SELECT m.region AS region_envio, m.contraparte_region AS region_recibo, count(*) AS transferencias
FROM movimiento m
WHERE m.tipo = 'TRANSF_ENVIO' AND m.contraparte_region <> m.region
GROUP BY 1, 2
ORDER BY 1, 2;
