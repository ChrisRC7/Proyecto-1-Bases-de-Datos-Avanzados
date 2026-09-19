# E4 — Falla de un nodo

Script: `p1/chaos/falla.sh` (orquesta), `p1/chaos/sonda.py` (escribe), `p1/chaos/rto.py` (calcula).
Evidencia de la corrida 1: `evidence/p1/e4-corrida1-*`. Cómo repetirla: `p1/README.md §4`.

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

## Pendiente (TODO.md §4)

- Verificar y discutir el RPO con los folios: `-despues.txt` y el CSV tienen lo necesario (último
  folio confirmado antes del stop, folios confirmados después y folio final).
- Repetir la falla 3 veces (`--corrida 2`, `--corrida 3`) y reportar el RTO de cada una.
