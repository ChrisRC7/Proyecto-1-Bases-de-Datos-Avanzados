# E4 — Falla de un nodo

Script: `p1/chaos/falla.sh` (orquesta), `p1/chaos/sonda.py` (escribe), `p1/chaos/rto.py` (RTO),
`p1/chaos/rpo.py` (RPO) y `p1/chaos/region.sh` / `region.py` (caída de una región, opcional).
Evidencia: `evidence/p1/e4-corrida{1,2,3}-*` y `evidence/p1/e4-region-cr-limon-*`. Cómo repetirla: `p1/README.md §4`.

## Qué se escribe y sobre qué tabla

La sonda toma el siguiente folio de la serie `TRANSFERENCIAS` en `p1_control.folio_comprobante`:

```sql
UPDATE folio_comprobante SET ultimo_folio = ultimo_folio + 1, actualizado_en = now()
WHERE serie = 'TRANSFERENCIAS' RETURNING ultimo_folio;
```

Es la escritura que haría cada transferencia para numerar su comprobante: es del dominio y cada
confirmación devuelve un número verificable después. La tabla está en una base sin regiones con
`num_replicas = 3` (`p1/sql/02_e4_table.sql`): 3 votantes, uno por nodo, así que la mayoría 2/3
que se pone a prueba es la que declara su configuración. Sobre las tablas RBR no se podría decir
lo mismo (E1 §6: declarado ≠ observado).

## Protocolo (`falla.sh`)

| # | Paso del enunciado | Cómo se hace | Evidencia |
| --- | --- | --- | --- |
| 1 | Estado sano | 3 nodos vivos + una escritura de prueba `UPDATE … RETURNING` antes de tocar nada | `-antes.txt` |
| — | Precondición | El lease del rango se mueve al nodo que va a caer y se comprueba que llegó | `-antes.txt` |
| 2 | Detener **un** nodo | `docker stop --timeout 0` del contenedor, y la época justo al terminar (`date +%s.%N`) | `-stop.epoch`, `-stop.txt` |
| 3 | Cronometrar | La sonda intenta un folio cada 0,2 s por `crdb-1`; cada intento guarda inicio, fin, estado y folio | `.csv`, `-sonda.txt` |
| — | Restaurar | `docker start` 15 s después; se espera a que haya 3 nodos vivos | `-stop.txt`, `-despues.txt` |
| 4 | RTO | `rto.py` cruza el CSV con la época y muestra la resta | `-rto.txt` |

**Por qué mover el lease al nodo que cae.** Si cae un nodo que no tiene el lease, la escritura
sigue confirmándose con los otros dos votantes sin interrupción: el RTO mediría casi nada. Al
detener al leaseholder, el rango se queda sin quien coordine las escrituras hasta que otro votante
toma el lease. Ese intervalo es el que se mide. Antes de la corrida el lease estaba en el nodo 2
(`us-east`); `RELOCATE LEASE` lo llevó al nodo 3 (`cr-limon`), como muestra `-antes.txt`.

**Por qué el gateway es otro nodo.** La sonda escribe siempre por `crdb-1` (`cr-sj`), que sigue
vivo. Si el gateway fuera el nodo detenido, se mediría también cuánto tarda el cliente en
reconectarse a otro, que es un problema del cliente, no del clúster.

**Por qué `statement_timeout = 2 s`.** Sin límite, el primer intento después del stop quedaría
bloqueado hasta la recuperación y el CSV tendría una sola fila larga en lugar de mostrar la ventana
sin servicio. El precio es la resolución: el RTO se conoce con un error de hasta un intento
(ver abajo).

## Nodo y `store_id` por localidad

El número del contenedor no es el número del nodo. `node_id` lo asigna el clúster según el orden
en que cada nodo se une, y cambia entre máquinas: en la de la corrida principal `crdb-2` es el
nodo 3; en la de la reproducción de E3 era el nodo 2 (E3 §4). Además, `RELOCATE LEASE` recibe un
`store_id`, no un `node_id`. `falla.sh` no asume ninguno de los dos:

```sql
SELECT g.node_id, s.store_id, split_part(g.address, ':', 1)
FROM crdb_internal.gossip_nodes g JOIN crdb_internal.kv_store_status s ON s.node_id = g.node_id
WHERE g.locality LIKE 'region=cr-limon,%';
--  3 | 3 | crdb-2
```

Con la dirección que anuncia el nodo (`crdb-2`), busca el contenedor cuyo hostname coincide
(`docker inspect -f '{{.Config.Hostname}}'`). Salida de la corrida 1:

```text
region=cr-limon → node_id=3, store_id=3, dirección=crdb-2, contenedor=ti4601-crdb-2
```

## Corrida 1 — 2026-09-18, 4 CPU / 11,8 GiB

Línea de tiempo (UTC; filas del CSV `evidence/p1/e4-corrida1.csv`):

| Momento | Intento | Inicio → fin | Estado | Folio | Latencia |
| --- | ---: | --- | --- | ---: | ---: |
| Último OK antes de la falla | 28 | 03:01:27.453 → 27.461 | ok | 29 | 7,8 ms |
| **`docker stop` termina** | — | **03:01:27.798** | — | — | — |
| En curso durante el stop | 29 | 03:01:27.653 → 29.656 | error (timeout) | — | 2 003 ms |
| Primero que empieza después | 30 | 03:01:29.657 → 31.659 | error (timeout) | — | 2 003 ms |
| **Primer OK después del stop** | 31 | 03:01:31.660 → **32.418** | ok | 30 | 758 ms |
| Siguiente | 32 | 03:01:32.418 → 32.424 | ok | 31 | 5,7 ms |
| `docker start` | — | 03:01:43.046 | — | — | — |

**Cálculo del RTO** (`evidence/p1/e4-corrida1-rto.txt`):

```text
RTO = fin_epoch del primer OK que empezó después del stop − época del stop
    = 1789786892.417700 − 1789786887.797719
    = 4.620 s  →  4 620 ms
```

Cómo se ubica en el CSV: (1) leer `e4-corrida1-stop.epoch`; (2) buscar la primera fila con
`inicio_epoch` ≥ esa época y `estado = ok` (intento 31); (3) restar la época a su `fin_epoch`.
Se exige que el intento **empiece** después del stop: el intento 29 empezó 0,145 s antes y un OK
suyo no probaría que el clúster se recuperó, solo que el nodo viejo alcanzó a confirmar.

**Resolución.** El intento 30 estuvo bloqueado de 29,657 a 31,659 sin confirmarse, y el 31 se
confirmó a las 32,418 tras esperar 758 ms. El rango volvió a tener leaseholder en algún momento
entre ~31,66 y 32,42: el RTO real está entre **~3,9 y 4,6 s**, y 4,62 s es la cota superior que da
esta sonda. Del intento 32 en adelante la latencia vuelve a la normal (5–8 ms, igual que antes de la
falla), aunque el nodo siguió detenido hasta las 43,046. Es decir, el clúster atendió escrituras
con **2 de 3 nodos**. Después de la falla, el lease quedó en el nodo 1 (`cr-sj`) y el rango
conserva sus 3 votantes (`-despues.txt`).

**Errores durante la ventana.** 2 intentos fallaron, los dos con
`QueryCanceled: query execution canceled due to statement timeout`: la escritura esperaba al
leaseholder y la sonda la canceló a los 2 s. No hubo errores de conexión, porque el gateway nunca
cayó. Esos dos intentos tienen resultado desconocido para el cliente: no se cuentan como
confirmados.

## Repeticiones: 3 corridas

La misma prueba se repitió con `p1/chaos/falla.sh --corrida 2` y `--corrida 3`. Esas dos corridas se
hicieron en la máquina de otro integrante (`iQuick-DESKTOP`). Allí `crdb-2` es el **nodo 2** y no el
3, y `falla.sh` lo encontró igual por localidad (`-antes.txt`), sin cambiar el script.

| Corrida | Fecha · máquina | Nodo caído (`cr-limon`) | Último OK antes | Primer OK después | Errores (timeout) | RTO |
| --- | --- | --- | --- | --- | ---: | ---: |
| 1 | 2026-09-18 · chris-HP (4 CPU) | nodo 3 / `crdb-2` | intento 28, folio 29 | intento 31, folio 30 | 2 | **4,620 s** |
| 2 | 2026-09-19 · iQuick-DESKTOP | nodo 2 / `crdb-2` | intento 28, folio 29 | intento 32, folio 30 | 3 | **6,530 s** |
| 3 | 2026-09-19 · iQuick-DESKTOP | nodo 2 / `crdb-2` | intento 28, folio 297 | intento 31, folio 298 | 2 | **5,156 s** |

Restas (de `-rto.txt`):

```text
corrida 1: 1789786892.417700 − 1789786887.797719 = 4.620 s
corrida 2: 1789882573.314526 − 1789882566.784132 = 6.530 s
corrida 3: 1789882696.788324 − 1789882691.632364 = 5.156 s
```

**RTO observado: 4,6–6,5 s; mediana 5,2 s.** Siempre es una cota superior: la sonda con
`statement_timeout = 2 s` solo ve la recuperación cuando termina un intento (resolución ≈ un
intento). La variación entre corridas cabe en esa resolución, más la diferencia de hardware y de
cuándo expira la *liveness* del nodo caído respecto al último latido. El orden de magnitud es
estable. El RTO no depende de un operador: lo marca el tiempo en que el clúster declara muerto al
nodo y otro votante toma el lease.

En la corrida 3, 12 escrituras posteriores al stop tardaron más de 100 ms (máx. 1,47 s). El
lease se recuperó, pero el rango siguió funcionando sin un votante hasta el `docker start`, en una
máquina ocupada. Ninguna de esas escrituras falló.

## RPO: ninguna escritura confirmada se perdió

`p1/chaos/rpo.py` convierte el RPO en una comprobación aritmética. La sonda pide folios
consecutivos y guarda el folio que recibió cada intento OK. Si el clúster "olvidara" una
escritura confirmada, un folio se repetiría o retrocedería. Tres pruebas por corrida
(`-rpo.txt`):

| Prueba | Corrida 1 | Corrida 2 | Corrida 3 |
| --- | --- | --- | --- |
| 1. Folios confirmados sin repetir ni retroceder | OK (2 → 279) | OK (2 → 268) | OK (270 → 543) |
| 2. Primer OK tras el stop = último antes + 1 | 30 = 29 + 1 | 30 = 29 + 1 | 298 = 297 + 1 |
| 3. Folio final en la base = último confirmado | 279 = 279 | 268 = 268 | 543 = 543 |
| **RPO para lo confirmado** | **0** | **0** | **0** |

**Qué significa y qué no.** RPO = 0 se refiere a las escrituras **confirmadas** al cliente. Es la
garantía de Raft: un commit se confirma solo cuando la entrada está persistida en la mayoría (2 de
3). Cualquier mayoría futura intersecta con esa, así que el nuevo leaseholder tiene la escritura.
Los intentos con timeout (2, 3 y 2) tienen resultado **desconocido** para el cliente. La prueba 2
lo resuelve: si alguno se hubiera confirmado en el servidor, el folio siguiente saltaría (29 → 31).
No saltó en ninguna corrida, así que ninguno se confirmó. Una aplicación real tendría que reintentar
esos intentos de forma idempotente, porque desde el cliente no se distingue "no se hizo" de "se hizo
y no me enteré".

---

## Caída de una región (opcional) y efecto en sus filas RBR

Script: `p1/chaos/region.sh` (orquesta) y `p1/chaos/region.py` (sonda, leases y resumen).
Evidencia: `evidence/p1/e4-region-cr-limon-*`. Corrida: 2026-09-20, chris-HP (4 CPU / 11,8 GiB).

**Qué cambia respecto a la prueba anterior.** Con un nodo por región, detener `crdb-2` es perder
`cr-limon` completa. Aquí **no se mueve ningún lease**: se observa la colocación diseñada en E1 §8
(cada fragmento con su leaseholder en casa) y se mide cada fragmento por separado. Hay seis casos,
cada uno en su hilo y su conexión a `crdb-1`, cada 0,2 s y con `statement_timeout = 2 s`. Así, un
caso bloqueado no retrasa a los demás. Las escrituras son las transferencias de E3 (doble asiento),
y `check.py` dio 10/10 después de la prueba (`-despues.txt`).

**Quién atiende cada fragmento** (`-antes.txt`, `-durante.txt`, `-despues.txt`):

| Momento | `cuenta_sj` | `cuenta_limon` | `moneda` |
| --- | --- | --- | --- |
| Antes | `cr-sj` | `cr-limon` (hogar) | `cr-sj` (coordina escrituras; cada región lee su copia) |
| 15 s después del stop | `cr-sj` | **`us-east`** (fuera de hogar) | `cr-sj` |
| Tras `docker start` | `cr-sj` | `cr-limon`, de vuelta en 30 s | `cr-sj` |

**Resultado por caso** (`-resumen.txt`; región caída 31,8 s):

| Caso | p50 antes (ms) | Errores durante | Vuelve a responder (s) | Estable desde (s) | p50 estable (ms) | Errores al reintegrarse |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `lee-limon` (O1, región caída) | 1,61 | 3 | **5,9** | 10,0 | 1,56 | 2 |
| `escribe-limon` (O4, región caída) | 26,75 | 4 | **6,3** | 11,8 | 24,14 | 2 |
| `escribe-cruza` (O5, `cr-sj`↔`cr-limon`) | 54,29 | 4 | **9,5** | 12,4 | 23,79 | 2 |
| `lee-sj` (O1, región viva) | 1,10 | 2 | 0,04 | 12,0 | 14,16 | 2 |
| `escribe-sj` (O4, región viva) | 23,10 | 2 | 0,07 | 12,2 | 23,16 | 2 |
| `lee-moneda` (O7, `GLOBAL`) | 1,07 | **0** | 0,04 | 0 | 0,95 | 1 |

**Interpretación.**

1. **Las filas de la región caída no se pierden ni quedan inaccesibles: quedan ~6 s sin
   servicio y después las atiende otra región.** Sus votantes Raft están repartidos uno por
   región (E1 §7–§8), así que al caer `cr-limon` cada rango `*_limon` conserva 2 de 3 votantes. El
   lease pasa a `us-east` y las operaciones O1/O4 sobre cuentas de `cr-limon` vuelven a los ~6 s,
   lo mismo que el RTO de la prueba anterior. Durante la caída leer una cuenta de `cr-limon` cuesta
   lo mismo que antes (1,56 frente a 1,61 ms): sin latencia inyectada, ir a `us-east` o a `cr-limon`
   cuesta igual desde `cr-sj`.
2. **Esa disponibilidad es la otra cara del límite de residencia.** Las filas de `cr-limon`
   sobreviven a la pérdida de su región *porque* tienen copias fuera de ella. Con la topología que
   exige la residencia (3 nodos por región + `PLACEMENT RESTRICTED`, E1 §4), los 3 votantes de
   `cliente_limon` estarían en `cr-limon`. Perder la región dejaría sus filas **sin servicio**
   hasta que vuelva, mientras que `cr-sj` y `us-east` seguirían intactas. Residencia estricta y
   supervivencia a la pérdida de región son incompatibles para un mismo fragmento. Para tener las
   dos, CockroachDB ofrece `SURVIVE REGION FAILURE`, que coloca réplicas en otras regiones, es decir,
   renuncia a la residencia estricta.
3. **`moneda` (GLOBAL) no se interrumpió** durante la caída: cero errores y la misma latencia. Cada
   región lee su propia copia (E1 §6). Es la tabla que justifica su replicación completa.
4. **La transferencia que cruza regiones es la última en volver (9,5 s)**, porque necesita que
   estén disponibles los rangos de las dos regiones que toca. Con la región caída, su p50 bajó de 54
   a 24 ms: ya no espera al leaseholder en `crdb-2`, sino a uno en `us-east`, en una máquina con un
   nodo menos compitiendo por CPU.
5. **Las regiones vivas también notaron la falla.** `lee-sj` y `escribe-sj` tuvieron 2 timeouts
   cada uno entre los 6 y 12 s, y `lee-sj` quedó en ~14 ms hasta la reintegración. Hay dos causas
   plausibles: el clúster reubica los leases de rangos de sistema que estaban en `crdb-2`, y cada
   rango `*_sj` queda con 2 votantes, así que cada escritura necesita a los dos. El aumento de
   `lee-sj` no se reproduce aislado: con `crdb-2` detenido, una lectura `cr-sj` sin escritores o con
   uno sigue en ~1 ms (`e4-region-diagnostico.txt`). Aparece solo con la caída más los seis casos
   concurrentes, que comparten filas (`escribe-sj` y `escribe-cruza` escriben la misma cuenta). Se
   declara como observado, no como explicado del todo.
6. **Volver a tres nodos tampoco es gratis.** Entre 13 y 21 s después del `docker start`, **todos**
   los casos, incluso `moneda`, tuvieron 1–2 timeouts: el nodo reintegrado se pone al día (Raft) y
   los leases de `cr-limon` vuelven a su región por `lease_preferences`, lo que tardó 30 s. Una
   reintegración real conviene hacerla fuera de horas pico.

**Límites.** Una sola corrida de la caída de región, porque la tarea es opcional. Con un nodo por
región, "región" y "nodo" coinciden, y las regiones son lógicas, sin latencia inyectada.
