# E5 — Comparación: clúster CockroachDB frente a PostgreSQL de un nodo

Baseline: `p1/baseline/` (mismo esquema traducido, mismos datos —huella `ad995e29a16440f7`—, mismas
cuatro operaciones de `p1/bench/latency.py`, mismo método y aislamiento `SERIALIZABLE`).
Evidencia: `evidence/p1/e5-latency-postgres-summary.txt`, `e5-latency-postgres.csv`,
`e5-docker-stats.txt`. La comparación se hace sobre la **misma máquina** (12 CPU / 7,9 GiB): CockroachDB
en `evidence/p1/otra-maquina/e3-latency-summary.txt`, PostgreSQL en `e5-latency-postgres-summary.txt`.

## Latencia (n = 100 por caso, warm-up 10, ms)

| Operación | CockroachDB ×3 p50 | p99 | PostgreSQL ×1 p50 | p99 | Razón p50 | Razón p99 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Lectura local (O1, fila `cr-sj`) | 0.770 | 6.458 | 0.171 | 0.250 | 4.5× | 26× |
| Lectura remota (O1, fila `cr-limon`) | 1.520 | 17.342 | 0.172 | 0.348 | 8.8× | 50× |
| Escritura local (O4) | 16.467 | 31.236 | 1.400 | 1.700 | 11.8× | 18× |
| Escritura que cruza región (O5) | 15.073 | 37.296 | 1.426 | 1.785 | 10.6× | 21× |

Lectura:

- En PostgreSQL local = remota (0,17 ms): la región es un dato de la fila; no hay gateway ni
  leaseholder al que ir. En CockroachDB la lectura remota paga el salto al leaseholder de
  `cr-limon`, y su cola (p99 17 ms, 17/100 muestras > 10 ms) es 50× la de PostgreSQL.
- La escritura en CockroachDB cuesta ~11× la de un nodo. Es el precio de replicar en 3 votantes y
  esperar la mayoría 2/3 antes de confirmar (E3 §2); en PostgreSQL el `COMMIT` solo espera el
  `fsync` local del WAL (~0,7 ms medido con `synchronous_commit = on`).
- Las dos escrituras de CockroachDB cuestan lo mismo entre sí por la topología de un nodo por
  región (E3 §2); en PostgreSQL cuestan lo mismo porque no hay distribución. El motivo es distinto.

## Costo en la misma máquina (`e5-docker-stats.txt`)

| Recurso | CockroachDB ×3 | PostgreSQL ×1 | Razón |
| --- | ---: | ---: | ---: |
| Memoria en reposo | 634 + 605 + 624 ≈ 1 863 MiB | 88 MiB | 21× |
| CPU bajo carga (8 000 operaciones, pico) | 188 % + 154 % + 132 % ≈ 474 % | 42 % | 11× |
| Tiempo para esas 8 000 operaciones | ≈ 130 s (66 muestras de 2 s) | ≈ 10 s (5 muestras) | 13× |
| Disco (volúmenes; ambos incluyen la base `ti4601` del curso) | 3 × 1,27 GB ≈ 3,8 GB | 134 MB | 28× |
| Tiempo de carga del seed (97 527 filas) | 36,1 s | 6,3 s | 5.7× |

## Complejidad operativa

| | CockroachDB ×3 | PostgreSQL ×1 |
| --- | --- | --- |
| Piezas | 3 contenedores + 1 de `init`, 3 volúmenes, red | 1 contenedor, 1 volumen |
| Configuración | licencia, región primaria + 2 regiones, `LOCALITY` por tabla, `SURVIVE ZONE FAILURE`, zona RF=3 para E4; 7 pasos en `setup.sh` | un `CREATE DATABASE` y el esquema; 2 comandos |
| Cosas que hay que saber para operar | `node_id` ≠ número de contenedor, leaseholders, subreplicación RBR con un nodo por región, gracia de licencia | `autovacuum`/checkpoint tras cargas masivas |
| Reproducción en otra máquina | verificada (E2) | verificada (este baseline) |

## Lo que esta comparación no dice sola

Los números anteriores miden lo que **cuesta** distribuir. Lo que **compra** está en otros
entregables y es lo que la conclusión de E5 tiene que poner en la balanza: sobrevivir a la caída de
un nodo confirmando escrituras con 2 de 3 y RPO 0 para lo confirmado (E4), región hogar y
leaseholder por región para la PII (E1 §4, con su límite declarado), y `SERIALIZABLE` sin pedirlo.
PostgreSQL de un nodo no tiene ninguna de las tres; con una réplica de lectura gana lecturas
escalables y un respaldo, pero no confirmación con mayoría ni RPO 0 ante la pérdida del primario.
