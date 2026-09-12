# Bitácora Laboratorio 1

## Pasos 0 y 1: preparación y clúster

- Servicios: `crdb-1`, `crdb-2` y `crdb-3`.
- Localidades: `crdb-1 = region=cr-sj,zone=a`, `crdb-2 = region=cr-limon,zone=a`, `crdb-3 = region=us-east,zone=a`.
- Los tres nodos usan `--join=crdb-1,crdb-2,crdb-3` y un volumen persistente independiente (`crdb1`, `crdb2`, `crdb3`).
- `node-status-initial.txt` confirma tres nodos disponibles y vivos.

`--join` solo permite que los procesos encuentren y formen el clúster inicial; no configura una base multi-región. `--locality` asigna una etiqueta lógica. Si se eliminan los volúmenes, se pierde el estado persistente del clúster, incluidas regiones, tablas y datos.

## Paso 3: regiones

```sql
ALTER DATABASE ti4601 PRIMARY REGION "cr-sj";
ALTER DATABASE ti4601 ADD REGION "cr-limon";
ALTER DATABASE ti4601 ADD REGION "us-east";
SHOW REGIONS FROM DATABASE ti4601;
SELECT gateway_region();
```


Resultado: `cr-sj` (primaria), `cr-limon` y `us-east`. `gateway_region()` devolvió `cr-sj`,
la región del nodo que atendió la conexión.

**¿Por qué se define primero una región primaria?**
`PRIMARY REGION` es la sentencia que convierte la base en multi-región: crea el tipo
`crdb_internal_region` y fija la región por defecto. Sin ella no hay a qué agregar regiones,
y `schema.sql` fallaría al declarar `region crdb_internal_region`.

**¿Qué comando prueba la configuración resultante?**
`SHOW REGIONS FROM DATABASE ti4601`, que debe listar tres filas con `cr-sj` marcada como
primaria. `make lab1-check` lo comprueba de forma automática (`config-check.txt`).

**¿Agregar una región crea latencia WAN real?**
No. `ADD REGION` habilita colocación y ruteo sobre localidades ya declaradas en
`--locality`. Las tres regiones siguen corriendo en una sola computadora.

**Paso 3: OK.**

## Paso 4: esquema

Se aplicó `schema.sql` y se verificó con `SHOW CREATE TABLE`:

```text
catalogo_producto: LOCALITY GLOBAL
pedido: LOCALITY REGIONAL BY ROW AS region
```

`pedido.region` determina la región hogar y forma parte de la clave primaria `(region, pedido_id)`. `GLOBAL` es apropiada para el catálogo pequeño; RBR aproxima la fragmentación horizontal por región. Las copias físicas siguen siendo réplicas Raft, por lo que RBR y replicación no son el mismo concepto.

**Paso 4: OK.**

## Paso 5: seed

Se aplicó `seed.sql`. El resultado es una fila de `pedido` por región: `cr-sj`, `cr-limon` y `us-east`. El catálogo contiene `SKU-CAFE` y `SKU-CACAO`.

**Paso 5: OK.**

## Paso 6: tabla Raft

Se aplicó `raft_probe.sql`. La tabla `ti4601_raft.public.raft_probe` tiene una fila `id=1`, factor de replicación 3 y tres votantes. En la precondición de Chaos A el rango fue `76`, el leaseholder fue el nodo `3` (`cr-limon`) y los votantes fueron `{1,3,2}`.

**Paso 6: OK.**

## Paso 7: verificación

`verify_cluster.py` terminó con seis comprobaciones correctas:

```text
[ OK ] tres nodos/localities vivos
[ OK ] tres regiones configuradas
[ OK ] catalogo_producto es GLOBAL
[ OK ] pedido es REGIONAL BY ROW
[ OK ] hay una fila pedido por región
[ OK ] raft_probe tiene tres votantes
Resultado: 6/6 verificaciones.
```

**Paso 7: OK.**

## Paso 8: inspección

`cluster-inspect.txt` consolida las seis consultas exigidas: regiones, DDL de `pedido`, conteo por región, configuración de zona, rangos de `pedido` y rango/votantes/localidades de `raft_probe`. La salida literal de `SHOW ZONE CONFIGURATION` y `SHOW RANGES FROM TABLE pedido` no se conservó en la captura original y está identificada como tal en ese archivo.

**Paso 8: evidencia consolidada, pero falta recapturar literalmente dos consultas.**

## Paso 9: latencia

Lectura previa de `measure_latency.py`:

1. los cuatro casos son `read/write` × `local/remote`, sobre las filas hogar `cr-sj` y `cr-limon`;
2. el warm-up se ejecuta antes del bucle de muestras y sus tiempos no se guardan;
3. el reloj de cada observación es `time.perf_counter_ns()`;
4. p50 es la mediana y p99 se calcula por *nearest rank*;
5. las columnas del CSV son `operation, locality, home_region, run, latency_ms`.

Se ejecutó desde `crdb-1`, con warm-up de 5 y `n=50` por caso, para 200 muestras totales (201 líneas con cabecera):

```text
operation locality home_region n p50_ms p99_ms
read      local    cr-sj       50 0.690  1.934
read      remote   cr-limon    50 1.460  1.698
write     local    cr-sj       50 7.067 12.713
write     remote   cr-limon    50 6.072 11.792
```

Las regiones son lógicas. Se mantuvieron constantes la máquina, los recursos y el número de ejecuciones. No se puede inferir el costo de una WAN real porque no hubo latencia física controlada; por eso remoto puede ser parecido o incluso menor que local.

**Paso 9: OK.**

## Escenario A: falla y recuperación

Se movió el lease de `raft_probe` al store `3`, correspondiente a `crdb-2` en `region=cr-limon`, y se detuvo ese nodo. Antes de la falla la versión observada era `0` y había tres votantes. Después hubo 2 errores transitorios `QueryCanceled` por el timeout de 2 segundos; luego las escrituras volvieron a confirmar con dos nodos de tres.

```text
stop_epoch                 = 1788370667.521754
first after-stop ok        = 1788370671.559400 completed_epoch
RTO                       = (1788370671.559400 - 1788370667.521754) * 1000
RTO observado             = 4037.6 ms
```

La sonda imprimió `RTO observado hasta primer write OK: 4037.6 ms`, el mismo valor: la sonda usa las mismas dos marcas del CSV y solo redondea a un decimal.

El RPO observado para operaciones confirmadas es 0: no se perdió ni retrocedió el estado confirmado. La consulta posterior conserva `id=1` con `version=112`; los intentos con error no se cuentan como commits perdidos. `chaos-a-node-status.txt` confirma que los tres nodos fueron restaurados y están vivos.

## Escenario B: pérdida de quórum

En la evidencia opcional muestra 5 errores mientras estuvieron detenidos `crdb-2` y `crdb-3`, seguidos de escrituras correctas tras restaurarlos. Con un solo nodo activo queda 1/3, menor que la mayoría de 2/3, por lo que no se puede confirmar una escritura. Los procesos detenidos no constituyen una partición de red.



