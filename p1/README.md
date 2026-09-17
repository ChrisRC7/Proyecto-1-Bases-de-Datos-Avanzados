# Proyecto 1: banca / billetera regional sobre CockroachDB

Grupo 3 · TI-4601 Bases de Datos Avanzadas. Dominio: **Opción A**. Regiones: `cr-sj`, `cr-limon`, `us-east`.
Diseño de fragmentación: [`docs/E1-diseno.md`](docs/E1-diseno.md).

Esta guía permite levantar el sistema, cargar los datos y repetir las mediciones en una
máquina limpia. Todos los comandos se ejecutan en el **host**, desde la **raíz del repositorio**.

## Requisitos

- Docker Engine + Docker Compose v2 (`docker compose version`).
- Puertos libres `26257` y `8080`.
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

## 4. Límites que hay que declarar

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

## Estructura

```text
p1/
├── README.md          esta guía
├── setup.sh           configuración completa (E2)
├── evidence.sh        evidencia de E2
├── check.py           verificador de solo lectura
├── docs/E1-diseno.md  diseño de fragmentación
├── sql/               00_database, 01_schema, 02_e4_table, inspect
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
