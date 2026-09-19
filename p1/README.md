# Proyecto 1: banca / billetera regional sobre CockroachDB

Grupo 3 · TI-4601 Bases de Datos Avanzadas. Dominio: **Opción A**. Regiones: `cr-sj`, `cr-limon`, `us-east`.
Diseño de fragmentación: [`docs/E1-diseno.md`](docs/E1-diseno.md).

Esta guía permite levantar el sistema, cargar los datos y repetir las mediciones en una
máquina limpia. Todos los comandos se ejecutan en el **host**, desde la **raíz del repositorio**.

## Requisitos

- Docker Engine + Docker Compose v2 (`docker compose version`).
- Puertos libres `26257` y `8080` (y `5458` para PostgreSQL en E5).
- Recomendado: 4 CPU, 4 GiB de RAM libres y 5 GiB de disco.
- Archivo `.env` en la raíz con `COCKROACH_LICENSE=<licencia del docente>` (ver `.env.example`).
  Sin licencia, `REGIONAL BY ROW` / `GLOBAL` solo funcionan los primeros 7 días del clúster.
  **No versionar `.env`.**

No hace falta instalar Python ni psycopg en el host: todo corre dentro del contenedor `app-crdb`.

## 1. Configurar todo (E2)

```bash
p1/setup.sh
```

| Paso | Qué hace | Archivo |
| --- | --- | --- |
| 1 | Levanta los 3 nodos del clúster del curso (`make lab1-up`) | `docker-compose.yml` |
| 2 | Espera a que los 3 nodos estén vivos | — |
| 3 | Instala la licencia sin imprimirla | `labs/lab1-cluster/install_license.py` |
| 4 | Crea `p1_banca` con región primaria `cr-sj` y las otras dos regiones | [`sql/00_database.sql`](sql/00_database.sql) |
| 5 | Crea `moneda` (GLOBAL); `cliente`, `cuenta` y `movimiento` (REGIONAL BY ROW); y la tabla de E4 | [`sql/01_schema.sql`](sql/01_schema.sql), [`sql/02_e4_table.sql`](sql/02_e4_table.sql) |
| 6 | Genera y carga los datos con semilla fija | [`gen/seed.py`](gen/seed.py) |
| 7 | Verifica clúster, esquema, fragmentación y datos | [`check.py`](check.py) |

Tiempo aproximado: menos de 1 minuto con las imágenes ya descargadas.

**Resultado esperado:**

```text
Generado en … s: 3000 clientes, 4527 cuentas, 90000 movimientos
Huella de datos (semilla=4601, clientes=3000): ad995e29a16440f7
…
Resultado: 10/10 verificaciones.
```

La **huella** debe ser exactamente `ad995e29a16440f7`: indica que se generaron los mismos datos que en
nuestras mediciones. El script es idempotente: si se ejecuta otra vez, no duplica nada.
Para recargar los datos desde cero: `p1/setup.sh --reset`.

El proyecto usa sus propias bases (`p1_banca` y `p1_control`) y no modifica `ti4601`, que usan los labs.

## 2. Evidencia de la implementación

```bash
p1/evidence.sh
```

Genera, con marca de tiempo:

| Archivo | Contenido |
| --- | --- |
| `evidence/p1/e2-node-status.txt` | Contenedores y `cockroach node status` |
| `evidence/p1/e2-inspect.txt` | `SHOW REGIONS`, localidad de cada tabla, `SHOW CREATE TABLE`, filas por fragmento, configuración de zona y `SHOW RANGES … WITH DETAILS` |
| `evidence/p1/e2-check.txt` | Salida del verificador (10 comprobaciones) |
| `evidence/p1/e1-verificacion.txt` | Completitud, reconstrucción, disyunción y derivada de la tabla de verificación del E1 (`sql/verificacion.sql`) |

## 3. Mediciones de latencia (E3)

Espere a que el clúster esté en reposo: unos minutos después de `setup.sh`, o hasta que
`docker stats` muestre poca CPU en los nodos. Justo después de cargar datos o de borrar una base,
el motor hace trabajo de fondo que infla las escrituras.

```bash
docker compose --profile lab1 run --rm --no-deps app-crdb python3 p1/bench/latency.py
```

Genera `evidence/p1/e3-latency.csv` (400 muestras crudas) y `evidence/p1/e3-latency-summary.txt`
(entorno, método y tabla p50/p99). Opciones: `--corridas` (por defecto 100, mínimo 30),
`--warmup` (10), `--gateway` (`crdb-1`) y `--prefijo` (para no sobrescribir una corrida anterior).

**Definición:** una operación es *local* si todas las filas que toca tienen como región hogar la
región del gateway SQL; *cruza región* si alguna fila tiene otra región hogar.

| Caso | Operación del E1 | Filas |
| --- | --- | --- |
| lectura-local | O1: saldo de una cuenta `cr-sj` desde `crdb-1` | 1 lectura |
| lectura-remota | O1: saldo de una cuenta `cr-limon` desde `crdb-1` | 1 lectura |
| escritura-local | O4: transferencia `cr-sj` ↔ `cr-sj` | 2 UPDATE + 2 INSERT |
| escritura-cruza | O5: transferencia `cr-sj` ↔ `cr-limon` | 2 UPDATE + 2 INSERT |

**Método:**
- Gateway fijo (`crdb-1`) y una conexión persistente.
- Warm-up descartado.
- Orden de los casos aleatorio en cada ronda.
- `perf_counter_ns` alrededor de la operación completa, incluidos el COMMIT y los reintentos.
- p99 por *nearest rank*.
- Antes de medir, se comprueba que el leaseholder de cada cuenta usada esté en su región hogar.
- Las transferencias alternan de dirección para que los saldos no se agoten.

## 4. Falla de un nodo (E4)

```bash
p1/chaos/falla.sh                  # corrida 1: cae el nodo de cr-limon durante 15 s
p1/chaos/falla.sh --corrida 2      # repeticiones, sin pisar la evidencia anterior
```

| Paso | Qué hace |
| --- | --- |
| 1 | Comprueba que haya 3 nodos vivos |
| 2 | Busca por **localidad** el `node_id`, el `store_id` y el contenedor del nodo que caerá (el número del contenedor no es el del nodo) |
| 3 | Hace una escritura sana y mueve el lease de `folio_comprobante` a ese nodo (`ALTER RANGE RELOCATE LEASE`) |
| 4 | Lanza la sonda: toma folios cada 0,2 s por `crdb-1`, con `statement_timeout` de 2 s |
| 5 | `docker stop --timeout 0` y guarda la época del stop; `CAIDO` segundos después, `docker start` |
| 6 | Guarda el estado final: nodos, lease y último folio confirmado |
| 7 | Calcula el RTO desde el CSV y muestra la resta (`chaos/rto.py`) |

Genera `evidence/p1/e4-corrida<N>-antes.txt`, `.csv`, `-sonda.txt`, `-stop.epoch`, `-stop.txt`,
`-despues.txt` y `-rto.txt`. Si el script se interrumpe, vuelve a arrancar el nodo al salir. Opciones:
`--region` (por defecto `cr-limon`), `--caido` (15 s) y `--corrida`. Resultados en
[`docs/E4-falla.md`](docs/E4-falla.md).

## 5. Comparación con PostgreSQL de un nodo (E5)

Requiere el clúster arriba y con datos (sección 2), porque la foto de costo mide los dos motores a la vez.

```bash
make up
docker compose run --rm app python3 p1/baseline/seed_pg.py      # huella esperada: ad995e29a16440f7
docker compose run --rm app python3 p1/baseline/latency_pg.py
p1/baseline/docker_stats.sh
```

Corre contra PostgreSQL **el mismo esquema, los mismos datos y las mismas cuatro operaciones** de
E2/E3, para que la diferencia medida venga del motor y no de otros datos u otras operaciones.

| Paso | Qué hace | Archivo |
| --- | --- | --- |
| 1 | Levanta PostgreSQL 16 | `docker-compose.yml` |
| 2 | Crea `p1_banca` con el esquema traducido (sin `LOCALITY`) y carga los datos con las funciones de `gen/seed.py` | [`baseline/seed_pg.py`](baseline/seed_pg.py), [`baseline/01_schema_pg.sql`](baseline/01_schema_pg.sql) |
| 3 | Mide con las operaciones de `bench/latency.py`, en `SERIALIZABLE` como CockroachDB | [`baseline/latency_pg.py`](baseline/latency_pg.py) |
| 4 | `docker stats` en reposo y bajo carga, volúmenes y piezas a operar | [`baseline/docker_stats.sh`](baseline/docker_stats.sh) |

Genera `evidence/p1/e5-latency-postgres.csv`, `evidence/p1/e5-latency-postgres-summary.txt` y
`evidence/p1/e5-docker-stats.txt`. La comparación está en [`docs/E5-comparacion.md`](docs/E5-comparacion.md).

**Cómo leer los casos en PostgreSQL:** todas las filas están en el mismo servidor. Los cuatro casos se
conservan para comparar operación por operación con E3, pero *local* y *cruza* solo describen la región
hogar de las filas, no una distancia.

## 6. Límites que hay que declarar

- **Las regiones son lógicas.** Los 3 nodos corren en la misma máquina y no hay latencia inyectada,
  así que la diferencia local/remoto medida no representa una WAN.
- **Las particiones REGIONAL BY ROW no cumplen su configuración de zona.** Cada una pide 5 réplicas
  y 3 votantes dentro de su región hogar (`SHOW ZONE CONFIGURATIONS`), pero hay un solo nodo por
  región. Lo observado en `SHOW RANGES` es: 3 votantes, uno por nodo, con el leaseholder en la
  región hogar. Por eso las escrituras locales también esperan la confirmación de nodos de otras regiones.
- **No hay garantía de residencia.** Por el punto anterior, hay copias de la PII en las tres
  regiones. Este montaje demuestra la región hogar, no el cumplimiento de la regla de residencia.
- **La prueba de falla (E4) usa `p1_control.folio_comprobante`**, que está en una base sin regiones
  con `num_replicas = 3` y sí cumple su configuración (mayoría 2/3).
- **E5 compara contra un PostgreSQL con configuración por defecto**, sin los límites de memoria de los
  nodos (`--cache=256MiB`). La réplica de lectura de la alternativa no se montó: con replicación
  asíncrona no cambia la latencia de escritura del primario.
- **El volumen `ti4601_pgdata` también contiene la base `ti4601` de los labs**, así que su tamaño es
  una cota superior del costo en disco de `p1_banca`.

## Estructura

```text
p1/
├── README.md          esta guía
├── setup.sh           configuración completa (E2)
├── evidence.sh        evidencia de E1 (verificación) y E2
├── check.py           verificador de solo lectura
├── docs/              E1-diseno, E3-mediciones, E4-falla, E5-comparacion
├── chaos/             falla de un nodo, sonda y RTO (E4)
├── baseline/          PostgreSQL de un nodo (E5)
├── sql/               00_database, 01_schema, 02_e4_table, inspect, verificacion
├── gen/seed.py        generador determinista
└── bench/latency.py   mediciones de E3
evidence/p1/           salidas generadas por los scripts
```

## Problemas comunes

| Síntoma | Qué hacer |
| --- | --- |
| `ERROR: no hay 3 nodos vivos` | `make lab1-status`; esperar 20 s y repetir `p1/setup.sh` |
| Error de licencia en multi-región | Revisar `.env` y repetir `p1/setup.sh` |
| La huella no coincide | Verificar que no se pasaron `--semilla` o `--clientes` distintos |
| `[FAIL] folio_comprobante … votantes` | Esperar 1–2 minutos (reubicación de réplicas) y ejecutar `check.py` otra vez |
| Un nodo quedó detenido | `docker start ti4601-crdb-1 ti4601-crdb-2 ti4601-crdb-3` |
| Escrituras con p99 de cientos de ms | Clúster aún ocupado tras la carga; esperar y repetir con otro `--prefijo` |
