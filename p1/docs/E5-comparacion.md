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

## Conclusión: justificado solo por residencia

**Veredicto.** Para este dominio y este volumen, distribuir en tres regiones **no se justifica por
rendimiento ni por costo**. Tampoco lo justifica la disponibilidad sola. **Se justifica solo por la
regla de residencia**: la PII de cada cliente debe vivir en su región de apertura, y ningún
diseño de un solo primario puede cumplirla. Además, el montaje de este proyecto (un nodo por
región) todavía no la cumple del todo.

**1. Latencia: el nodo único gana en todas las operaciones.** En la misma máquina, PostgreSQL lee
un saldo en 0,17 ms y CockroachDB en 0,77 ms (local) o 1,52 ms (remota): entre 4,5× y 8,8× más lento
en la mediana, y entre 26× y 50× en el p99. Una transferencia cuesta 1,4 ms en un nodo y 15–16 ms en
el clúster, ~11×. Nada de eso es un defecto de configuración: es el precio de que cada commit espere
a una mayoría de 2 de 3 réplicas (E3 §2). Con 97 527 filas y un día de operaciones que un solo
servidor atiende en segundos, no hay carga que repartir. Distribuir no acerca los datos a ningún
usuario que hoy esté lejos, porque las regiones son lógicas y no hay WAN entre ellas.

**2. Costo y operación: el clúster cuesta un orden de magnitud más.** En reposo usa 21× la memoria
(≈ 1 863 MiB frente a 88 MiB) y 28× el disco. Bajo la misma carga de 8 000 operaciones usa 11× la
CPU y tarda 13× más. Operar exige saber cosas que un nodo no pide: la licencia, las regiones, que
`node_id` no es el número del contenedor, dónde está cada leaseholder y por qué la configuración
RBR declarada no coincide con la observada. Todas quedaron documentadas en E1 §4, E3 §4 y E4.

**3. Disponibilidad: el clúster sí compra algo, pero no lo suficiente para justificarlo solo.** Al
detener el nodo que tenía el lease, el clúster volvió a confirmar escrituras en **4,6 s** (cota
superior de la sonda; el real está entre ~3,9 y 4,6 s), **sin intervención humana**. Siguió
atendiendo con 2 de 3 nodos durante los 15 s de la falla (E4, corrida 1). En esa corrida, los folios
confirmados siguen continuos: el último antes del stop fue el 29 y el primero después, el 30 (la
verificación formal del RPO sigue pendiente en E4). La alternativa de **1 primario + réplica de
lectura** no ofrece eso. Si la réplica es asíncrona, perder el primario puede perder transacciones
ya confirmadas (RPO > 0). Además, promoverla es una decisión manual o de una herramienta externa,
con un RTO de minutos. La réplica sí le da lecturas escalables y una copia para recuperarse. Aun
así, si el único requisito fuera sobrevivir a la caída de un servidor, habría un camino mucho más
barato que el multi-región: un primario con una réplica **síncrona** en la misma región y
conmutación automática. Tendría RPO 0 y un RTO de segundos a pocos minutos, conservaría las
latencias del nodo único para las lecturas (el commit solo esperaría a una réplica cercana) y no
necesitaría regiones, licencia ni `LOCALITY`. La disponibilidad pide replicar, no distribuir.

**4. Residencia: el único requisito que un primario único no puede cumplir.** Con un solo primario,
toda la PII vive donde esté ese servidor. Si está en San José, los nombres y documentos de los
clientes de `us-east` salen de su región de apertura. Ponerlo en otra región solo cambia a quién le
toca. Una réplica de lectura lo empeora, porque copia **toda** la PII a un segundo sitio. La
residencia exige que el dato de cada cliente viva en una región distinta según su fila, y eso es
fragmentación horizontal por `region` con asignación por región (E1 §3–§6). Es justo lo que ofrece
`REGIONAL BY ROW`, y ningún motor de un solo nodo lo hace.

**El límite que hay que decir en la defensa.** Este montaje demuestra la mitad de la residencia: la
región hogar de cada fila y su leaseholder están en la región de apertura (E2, E3). Pero con **un
nodo por región**, cada rango RBR tiene votantes en las tres regiones, así que hoy existen copias
físicas de la PII fuera de su región (E1 §4). Para cumplir la regla del todo hacen falta al menos 3
nodos por región (9 en total) y `PLACEMENT RESTRICTED`, de modo que los 3 votantes de cada partición
quepan en su región hogar. El costo medido aquí, de ~20× en memoria, se multiplicaría otra vez por 3.

**En resumen:** si el banco no tuviera clientes cuya PII deba quedarse en otra jurisdicción, lo
correcto sería **no distribuir**. Bastaría con PostgreSQL de un nodo con réplica síncrona para la
disponibilidad y una réplica de lectura si las lecturas crecieran. Como la regla de residencia es
parte del enunciado, la distribución por región está **justificada, pero solo por ella**, y solo si
se despliega con los nodos por región que la hacen efectiva. Ni la latencia, ni el costo, ni la
disponibilidad medidos en este proyecto la justifican por sí solos.
