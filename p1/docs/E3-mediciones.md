# E3 — Mediciones: tabla de resultados e interpretación

Datos: `evidence/p1/e3-latency-summary.txt` (corrida principal) y
`evidence/p1/otra-maquina/e3-latency-summary.txt` (reproducción en una segunda máquina).
Script: `p1/bench/latency.py`. Método completo en `p1/README.md §3`.

**Definición.** Una operación es *local* si todas las filas que toca tienen como región hogar la
región del gateway SQL (`crdb-1`, `cr-sj`); *cruza región* si alguna fila tiene otra región hogar
(`cr-limon`).

## Tabla de resultados (formato del enunciado)

Corrida principal — 2026-09-16, 4 CPU / 11,8 GiB, n = 100 por caso, warm-up 10 descartado:

| Desde región | Operación del dominio | p50 (ms) | p99 (ms) | n | Notas |
| --- | --- | ---: | ---: | ---: | --- |
| Lectura local · R1 | O1 saldo de cuenta `cr-sj` | 1.418 | 6.378 | 100 | 0 reintentos |
| Lectura remota · R1→R2 | O1 saldo de cuenta `cr-limon` | 1.971 | 18.897 | 100 | 17/100 por encima de 10 ms |
| Escritura local · R1 | O4 transferencia `cr-sj`↔`cr-sj` | 18.510 | 38.627 | 100 | 2 UPDATE + 2 INSERT, una transacción |
| Escritura que cruza región · R1→R2 | O5 transferencia `cr-sj`↔`cr-limon` | 19.071 | 37.310 | 100 | mismo trabajo que O4 |

Reproducción — 2026-09-17, otra máquina (12 CPU / 7,9 GiB), mismo script, misma semilla, misma huella de datos:

| Desde región | p50 (ms) | p99 (ms) | n | Notas |
| --- | ---: | ---: | ---: | --- |
| Lectura local · R1 | 0.770 | 6.458 | 100 | |
| Lectura remota · R1→R2 | 1.520 | 17.342 | 100 | 17/100 por encima de 10 ms |
| Escritura local · R1 | 16.467 | 31.236 | 100 | |
| Escritura que cruza región · R1→R2 | 15.073 | 37.296 | 100 | |

Razones remota/local (principal · reproducción): lectura p50 **1.4 · 2.0**, p99 **3.0 · 2.7**;
escritura p50 **1.03 · 0.92**, p99 **0.97 · 1.19**.

## Interpretación

**1. En lectura, el p99 remoto sí es mayor, y la diferencia está en la cola, no en la mediana.**
La mediana remota es apenas 1,4–2× la local, pero el p99 es ~3× y el patrón es idéntico en las dos
máquinas: 17 de 100 lecturas remotas tardan 11–19 ms en lugar de ~1,5 ms. Una lectura de una fila
con hogar en `cr-limon` entra por el gateway de `cr-sj` y debe ser atendida por el leaseholder de
ese rango, que está en `crdb-2` (comprobado antes de medir: "leaseholder cuenta cr-limon: en región
hogar"). Ese salto adicional gateway → leaseholder es lo que la lectura local no paga; en una
máquina compartida el costo aparece cuando el salto compite con el trabajo de fondo de los otros
nodos, es decir, en el p99. Es la razón por la que el enunciado pide mediana **y** p99: el promedio
(4,9 ms) no muestra ni lo típico ni la cola.

**2. En escritura, local ≈ cruza región. No es un error de medición: es la configuración de zona.**
Cada partición `REGIONAL BY ROW` declara `num_voters = 3` con `voter_constraints` en su región hogar
(`evidence/p1/e2-inspect.txt §5`), pero hay un solo nodo por región. Lo observado en `SHOW RANGES`
(§6) son 3 votantes, uno por nodo, en tres regiones distintas. Un commit necesita mayoría 2 de 3, así
que la transferencia "local" `cr-sj`↔`cr-sj` también espera la confirmación de un nodo de otra
región — el mismo viaje que la transferencia que cruza. Con esta topología, "escritura local" es
local en el hogar de las filas pero no en el quórum. Con varios nodos por región (lo que RBR
espera), los votantes cabrían en la región hogar y la diferencia aparecería.

**3. La diferencia dominante es lectura frente a escritura: 13–21× en la mediana.** Es el costo de
replicar la entrada y esperar que una mayoría la persista (consenso + durabilidad), igual que en el
Lab 1. Ninguna transferencia necesitó reintento por `SerializationFailure` (columna `reintentos` = 0
en las 400 muestras de cada corrida).

**4. La reproducción confirma el método.** Otra máquina, con el triple de CPU y menos memoria, dio
las mismas razones y el mismo 17/100 en la cola remota. Las medianas absolutas bajan (0,77 vs
1,42 ms en lectura local) porque cambia el hardware; las relaciones entre casos no. Un detalle
operativo de esa máquina: allí `node 2 = cr-limon` y `node 3 = us-east`, al revés que en la corrida
principal; el `node_id` lo asigna el clúster, no Compose, y E4 debe buscar nodo y `store_id` por
localidad.

## Límites que se declaran

- Las regiones son lógicas: tres contenedores en una computadora, sin latencia inyectada. Ninguna
  de estas cifras representa una WAN; la razón remota/local en escritura ≈ 1 sería distinta con
  distancia real.
- Misma máquina y mismos límites de recursos dentro de cada corrida (`--cache=256MiB`,
  `--max-sql-memory=256MiB`); perfil: clúster completo del Lab 1.
- Warm-up de 10 rondas descartado; orden de casos aleatorio por ronda; una conexión persistente al
  gateway (no se mide el tiempo de conexión); reloj `perf_counter_ns` alrededor de la operación
  completa, COMMIT y reintentos incluidos; p99 por *nearest rank*.
- Con n = 100, el p99 por *nearest rank* es la 99.ª muestra ordenada (una sola observación por
  encima). Por eso el resumen reporta también p90 y máximo, y los CSV conservan las 400 muestras.
