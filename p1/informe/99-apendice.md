---

# Apéndice A — Scripts del proyecto

Todo lo que produce un número en este informe lo genera un script versionado. Ninguna cifra se
escribió a mano.

| Archivo | Qué hace | Qué genera |
| --- | --- | --- |
| `p1/setup.sh` | Levanta el clúster, licencia, regiones, esquema, datos y verificación (7 pasos, idempotente) | — |
| `p1/check.py` | Verificador de solo lectura: 10 comprobaciones de clúster, esquema, fragmentación y datos | `e2-check.txt` |
| `p1/evidence.sh` | Evidencia de E1 y E2 | `e2-node-status.txt`, `e2-inspect.txt`, `e2-check.txt`, `e1-verificacion.txt`, `e1-asignacion.txt` |
| `p1/sql/00_database.sql` | Base `p1_banca`, región primaria y regiones | — |
| `p1/sql/01_schema.sql` | Esquema del dominio con `LOCALITY` (`GLOBAL` y `REGIONAL BY ROW`) | — |
| `p1/sql/02_e4_table.sql` | Tabla de folios en base sin regiones con RF=3 (E4) | — |
| `p1/sql/inspect.sql` | `SHOW REGIONS`, `SHOW CREATE`, zonas y `SHOW RANGES` | `e2-inspect.txt` |
| `p1/sql/verificacion.sql` | Completitud, reconstrucción, disyunción, derivada y doble asiento | `e1-verificacion.txt` |
| `p1/sql/asignacion.sql` | Fragmento → rango → leaseholder y votantes (asignación observada) | `e1-asignacion.txt` |
| `p1/gen/seed.py` | Generador determinista (semilla 4601) con huella de datos | — |
| `p1/bench/latency.py` | Benchmark de E3: 4 casos, p50/p99, CSV crudo | `e3-latency.csv`, `e3-latency-summary.txt` |
| `p1/chaos/falla.sh` | Falla de un nodo: escritura sana → lease → stop → sonda → start → RTO | `e4-corrida<N>-*` |
| `p1/chaos/sonda.py` | Sonda de escrituras (folios) cada 0,2 s con `statement_timeout` de 2 s | `e4-corrida<N>.csv` |
| `p1/chaos/rto.py` | RTO desde el CSV y la época del stop, mostrando la resta | `e4-corrida<N>-rto.txt` |
| `p1/chaos/rpo.py` | RPO: secuencia de folios, cruce de la falla y folio final | `e4-corrida<N>-rpo.txt` |
| `p1/chaos/region.sh` · `region.py` | Caída de una región completa; 6 casos en paralelo | `e4-region-<region>-*` |
| `p1/baseline/seed_pg.py` | Mismos datos en PostgreSQL (misma huella) | — |
| `p1/baseline/latency_pg.py` | Mismo benchmark contra PostgreSQL de un nodo | `e5-latency-postgres*` |
| `p1/baseline/docker_stats.sh` | Costo comparado: CPU, memoria, disco y piezas a operar | `e5-docker-stats.txt` |
| `p1/informe.sh` | Arma este informe y comprueba que no contenga la licencia | `entregas/p1/INFORME.md` y `.pdf` |

# Apéndice B — Evidencia

Todos los archivos están en `evidence/p1/` y llevan marca de tiempo y nombre de host.

| Grupo | Archivos | Entregable |
| --- | --- | --- |
| Clúster y esquema | `e2-node-status.txt`, `e2-inspect.txt`, `e2-check.txt` | E2 |
| Fragmentación | `e1-verificacion.txt`, `e1-asignacion.txt` | E1 |
| Latencia | `e3-latency.csv`, `e3-latency-summary.txt` | E3 |
| Reproducción en otra máquina | `otra-maquina/e2-check.txt`, `otra-maquina/e2-node-status.txt`, `otra-maquina/e3-latency-summary.txt` | E2, E3 |
| Falla de nodo (3 corridas) | `e4-corrida{1,2,3}{-antes.txt,.csv,-sonda.txt,-stop.epoch,-stop.txt,-despues.txt,-rto.txt,-rpo.txt}` | E4 |
| Caída de región | `e4-region-cr-limon-*`, `e4-region-diagnostico.txt` | E4 |
| PostgreSQL y costo | `e5-latency-postgres.csv`, `e5-latency-postgres-summary.txt`, `e5-docker-stats.txt` | E5 |

**Reproducir desde cero en una máquina limpia:** `p1/setup.sh`, luego `p1/evidence.sh`, el
benchmark de E3, `p1/chaos/falla.sh` y el baseline de E5. Los comandos exactos están en el
entregable E2 de este informe (`p1/README.md`).

# Apéndice C — Roles del equipo

*(Completar el rol y los entregables de cada integrante antes de entregar: la rúbrica evalúa
participación individual y la contrasta con los commits. `git shortlog -sne` lista los commits por
integrante.)*

| Integrante | Carné | Rol principal | Entregables en los que trabajó | Qué debe poder defender |
| --- | --- | --- | --- | --- |
| Christopher Rodriguez C. | 2022040771 | | | |
| Fabricio Mena M. | 2019042722 | | | |
| Alisson Redondo M. | 2021510425 | | | |

# Apéndice D — Límites declarados

Se listan juntos porque son la parte del trabajo que más se pregunta en la defensa.

1. **Las regiones son lógicas.** Tres contenedores en una máquina, sin latencia inyectada. Ninguna
   cifra de E3 representa una WAN.
2. **Las particiones `REGIONAL BY ROW` no cumplen su configuración de zona.** Piden 3 votantes
   dentro de su región hogar; con un nodo por región, los 3 votantes quedan repartidos entre las
   tres. Por eso la escritura "local" también espera a otra región (E3) y por eso la residencia
   física no se cumple (E1 §4).
3. **La prueba de falla usa una tabla en una base sin regiones** con RF=3, que sí cumple lo que
   declara, para que la mayoría 2/3 medida sea la declarada.
4. **El RTO medido es una cota superior**, con resolución de un intento de la sonda (0,2 s más el
   `statement_timeout` de 2 s).
5. **La caída de región se corrió una vez** (era opcional) y, con un nodo por región, coincide con
   la caída de un nodo.
6. **E5 compara contra PostgreSQL con configuración por defecto**, sin los límites de memoria de
   los nodos CockroachDB; la réplica de lectura de la alternativa se describe pero no se montó.
7. **El volumen de PostgreSQL incluye la base `ti4601` de los labs**, así que su tamaño en disco es
   una cota superior.
