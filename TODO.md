# Proyecto 1: lista de tareas

> Base de datos distribuida a pequeña escala (20 %). **Defensa y entrega: Semana 8.**
> Grupo 3: Fabricio Mena · Christopher Rodriguez · Alisson Redondo.
> Fuente: [`Proyecto1.pdf`](Proyecto1.pdf), [`labs/lab1-cluster/README.md`](labs/lab1-cluster/README.md) (§10, "Contrato para el Proyecto 1") y el reporte entregado del Lab 1, [`entregas/lab1/REPORTE.pdf`](entregas/lab1/REPORTE.pdf) (§7, "Puente al Proyecto 1").

Cada tarea tiene una casilla y un **Por qué**. El porqué sirve para dos cosas: que el equipo
no haga pasos sin entenderlos y que pueda responder en la defensa. El PDF dice: *"quien no
sepa responder sobre su parte pierde puntos individuales"*.

---

## 0. Estado actual del repositorio (actualizado el 2026-09-12)

| Qué | Estado | Consecuencia para el P1 |
| --- | --- | --- |
| Base del repo | Igual al commit `9b97a2a` (2026-09-02) de `main` en el repo del curso, [`manu3193/BDA-TI4601`](https://github.com/manu3193/BDA-TI4601). Único cambio local: puerto de Postgres 5433 → 5458 | Está actualizado. Cuando publiquen el Lab 2 hay que traer los cambios de ese repo. |
| Lab 1 | **Entregado.** Reporte y evidencia archivados en [`entregas/lab1/`](entregas/lab1/) | El entorno funciona (6/6, RTO ≈ 4 s). Se reutiliza el **método**, no los archivos. |
| Git | ✅ Repo local iniciado (rama `main`) con el commit inicial. Falta el remoto del equipo | El rubro "Proceso (commits)" vale 5 % y la participación individual se revisa en los commits. |
| `.env.example` | ✅ Licencia removida (sigue en `.env`, que está en `.gitignore`) | Ya se puede hacer el primer commit sin publicarla. |
| `docs/fases-postgres-cockroach.md`, `labs/lab2-queries/` | Se mencionan en el README pero **tampoco existen en el repo del curso** | Preguntar al docente; el Lab 2 (S7) usa el mismo clúster. |
| Latencia del Lab 1 | Local ≈ remoto (escritura local p50 7,07 ms, remota 6,07 ms) | **Decidido:** se mide sin latencia inyectada y se declara el límite (ver 3.4). |
| Nota del Lab 1 | Aún no publicada | Cuando salga, revisar comentarios: lo que se haya rebajado en mediciones o falla aplica a E3/E4. |
| Repo remoto del equipo | Aún no existe en GitHub | Crearlo y hacer `git push` antes de empezar E1 (tarea 1.3). |

### Lecciones del Lab 1 que aplican al P1

Salen del reporte y la bitácora entregados:

1. **En el Lab 1 se perdieron dos salidas** (`SHOW ZONE CONFIGURATION` y `SHOW RANGES FROM TABLE pedido`); la bitácora lo reconoce en el Paso 8. → En el P1, **toda la evidencia la escribe un script directo a archivo**, nunca se copia a mano desde la terminal.
2. **El `node_id` no coincide con el número del contenedor**: `crdb-2` (cr-limon) fue el nodo 3 y `crdb-3` (us-east) el nodo 2. → El script de E4 debe **buscar el nodo y el `store_id` por localidad**, no asumir que `crdb-2` es el nodo 2.
3. **Los 2 errores de Chaos A fueron `QueryCanceled`** por el `statement_timeout` de 2 s de la sonda, así que el RTO medido (4037,6 ms) depende de ese timeout y del intervalo de 0,5 s. → En E4, declarar el timeout y el intervalo de la sonda propia y explicar cómo afectan la resolución del RTO.
4. **La configuración se aplicó a mano en `psql`** (el reporte lo dice en §7). → El P1 necesita un script reproducible (ver 3.3).
5. **Pendientes que el equipo ya se comprometió a hacer en §7 del reporte:** dominio con predicados y localidades propios, tabla RF=3 propia distinta de `raft_probe`, seed y generador propios, benchmark del dominio, orquestación de la falla, contraste E5 contra un nodo, y declarar los límites (regiones lógicas, RBR subreplicado, sin garantía de residencia). La lista de abajo cubre todos.

---

## 1. Arranque del equipo (hacer primero, ~1 día)

- [x] **1.1 Quitar la licencia de `.env.example`**: ahora dice `# COCKROACH_LICENSE=`, como en el repo del curso. Solo `.env` tiene el valor.
  - **Por qué:** `.env` está en `.gitignore`, pero `.env.example` no. El primer `git add .` publicaría la licencia que dio el docente. Es más fácil corregirlo antes del primer commit que borrarla del historial después.

- [x] **1.2 Agregar `*.tar.gz` y `*.zip` a `.gitignore`** (`**/__pycache__/` ya estaba).
  - **Por qué:** los respaldos comprimidos pueden traer `.env` con la licencia (`todo.tar.gz` la traía) y duplican archivos que ya están en el repo.

- [x] **1.2b Borrar los respaldos redundantes**: `lab1.tar.gz`, `evidencia.tar.gz`, `todo.tar.gz`, `Lab1_BasesDeDatosAvanzados.zip`, `evidence/*` (la copia vieja), `transactions/__pycache__/` y las carpetas vacías `evidence/` y `scripts/`.
  - **Por qué se pueden borrar sin perder nada** (verificado):
    - `lab1.tar.gz` es idéntico a `labs/lab1-cluster/`.
    - `evidencia.tar.gz` es idéntico a la carpeta `evidence/` actual.
    - `todo.tar.gz` es un clon del repo del curso en el mismo commit que `main` en GitHub. Solo aporta el historial de git, que se recupera clonando de nuevo, y trae el `.env` con la licencia.
    - El `.zip` ya está descomprimido y verificado en `entregas/lab1/`.
    - `evidence/` tiene la misma evidencia que la entregada, pero con fines de línea de Windows (CRLF) y un `cluster-inspect.txt` **vacío**. La versión buena es la del zip.
    - `__pycache__` lo genera Python solo.
    - Las carpetas vacías no las guarda git. Los scripts del P1 crean `evidence/p1/` con `mkdir -p` al generar evidencia.

- [x] **1.2c Conectar el repo del curso como `upstream`**: `git remote add upstream https://github.com/manu3193/BDA-TI4601.git`. (Cada integrante que clone el repo del equipo debe repetir este comando, porque los remotos no viajan con el clon.)
  - **Por qué:** el Lab 2 (S7) se va a publicar ahí. Con `git fetch upstream` + `git merge upstream/main` se traen los cambios sin copiar archivos a mano.

- [ ] **1.3 `git init`, primer commit y subir al repositorio del equipo.** Poner la URL en el PDF.
  - [x] `git init -b main` y commit inicial (base del curso + Lab 1 archivado + TODO).
  - [ ] Crear el repo en GitHub (privado), `git remote add origin <url>` y `git push -u origin main`.
  - [ ] Invitar a los otros dos integrantes como colaboradores.
  - **Por qué:** el enunciado pide "TEC Digital + repo del equipo". Además, *"Incremental + defensa coherente"* se evalúa con el historial. Los commits deben ser pequeños y frecuentes, no uno solo al final.

- [ ] **1.4 Cada integrante hace commits con su propio usuario de git** (`git config user.name/user.email`).
  - **Por qué:** *"Quien no aparezca en commits … pierde puntos individuales"*. Si una persona hace commit del trabajo de todos, los otros dos quedan como "fantasmas".
  - **Regla del equipo:** los commits **no** llevan líneas `Co-Authored-By` de herramientas de IA. **Por qué:** la autoría en GitHub debe reflejar solo a los integrantes, que son quienes se evalúan y defienden el trabajo.

- [x] **1.5 Archivar el Lab 1 en `entregas/lab1/`** (`REPORTE.pdf` + `evidence/`, exactamente lo entregado). La evidencia del P1 irá en `evidence/p1/`.
  - **Por qué:** el Lab 1 y el P1 producen archivos con nombres parecidos (`latency.csv`, `chaos-a.csv`). Si se mezclan, se puede entregar evidencia del lab como si fuera del proyecto, y el lab dice que eso **no cumple** el P1. Se guarda la versión **entregada** (no la copia de trabajo) porque es la que calificaron y la que se puede citar.

- [ ] **1.6 Repartir roles** (propuesta; todos deben entender todo):

  | Persona | Responsable principal | Apoya en |
  | --- | --- | --- |
  | A | E1 diseño + diagrama + E5 crítica | Defensa de la shard key |
  | B | E2 implementación (DDL, generador de datos, scripts, README) | E4 |
  | C | E3 benchmark + E4 falla (sondas, evidencia, RTO/RPO) | E5 números |

  - **Por qué:** en la defensa preguntan por *shard key, p99 remoto, qué pasó al matar el nodo y la conclusión de E5*. Tener un responsable por tema garantiza que alguien lo domine. Rotar la revisión (A revisa a B, B a C, C a A) evita que alguien no sepa responder sobre otra parte.

---

## 2. Decisiones de diseño (Fase A, Entregable 1, 25 %)

> **No escribir DDL todavía.** El PDF lo dice: primero el diseño, luego el clúster.
> E1 es el rubro con más peso y lo que se defiende oralmente.

### 2.1 Elegir dominio

- [x] **Dominio elegido: Opción A (Banca / billetera regional)** (decidido el 2026-09-12).
  - Regiones: `cr-sj`, `cr-limon`, `us-east`. Entidades: cuenta, movimiento, cliente. Residencia: PII del cliente (nombre, documento) solo en la región de apertura.
  - **Por qué A:** sus regiones son **exactamente** las `--locality` que ya tiene [`docker-compose.yml`](docker-compose.yml), así que no hay que tocar el stack obligatorio ni justificar un mapeo de nombres. Además, la regla de residencia de la PII se traduce directo a `REGIONAL BY ROW` y da una buena discusión para E5 (*"justificado solo por residencia"*).

### 2.2 Esquema lógico con PK/FK

- [ ] Definir entidades, atributos, PK y FK. Para la opción A, un punto de partida (ajustarlo):
  - `cliente(region, cliente_id, nombre, documento, …)` → **PII**
  - `cuenta(region, cuenta_id, cliente_id → cliente, saldo, moneda, …)`
  - `movimiento(region, movimiento_id, cuenta_id → cuenta, monto, tipo, creado_en, …)`
  - Tabla pequeña y compartida, p. ej. `tipo_cambio` o `sucursal` → candidata a `GLOBAL`.
  - **Por qué `region` va en la PK:** en `REGIONAL BY ROW`, CockroachDB antepone la región a la clave primaria. Así cada rango físico queda en una sola región. Si `region` no está en la PK, no se puede ubicar la fila sin buscar en todas las regiones. Esa columna **es la shard key** y es lo primero que preguntan en la defensa.
  - **Por qué pensar las FK con cuidado:** una FK de `movimiento` (región X) a una fila en región Y obliga a verificar remotamente en cada escritura. Conviene que la cuenta y sus movimientos compartan región (fragmentación **derivada**) para que las FK y los joins sean locales.

### 2.3 Fragmentación horizontal (predicados)

- [ ] Para cada tabla fragmentada, escribir el predicado en lenguaje natural **y** en SQL:
  - `cliente_SJ = σ(region = 'cr-sj')(cliente)`, igual para `cr-limon` y `us-east`.
  - `cuenta` y `movimiento`: fragmentación **derivada** (semi-join con el fragmento del cliente/cuenta dueño).
  - **Por qué:** la rúbrica pide *"Predicados + 3 propiedades"* para el 100 %. Sin predicados formales la nota queda en 50 ("Informal o incompleto").

- [ ] **Decidir si hay fragmentación vertical para la PII** (separar `nombre, documento` de los datos operativos del cliente).
  - **Por qué:** permite que datos no sensibles (p. ej. saldo agregado) se lean desde otras regiones sin mover la PII. Si no la hacen, justificar por qué no hace falta.

### 2.4 Tabla de verificación (Completitud, Reconstrucción, Disyunción)

- [ ] Llenar la tabla del PDF con 2–4 líneas por propiedad:
  - **Completitud:** toda fila tiene exactamente una `region` válida (`NOT NULL` + tipo enum `crdb_internal_region`) → ninguna fila queda fuera de un fragmento.
  - **Reconstrucción:** `cliente = cliente_SJ ∪ cliente_LIMON ∪ cliente_USEAST` (en SQL, un `SELECT` sin filtro sobre la tabla).
  - **Disyunción:** los predicados `region = 'x'` son mutuamente excluyentes; en las derivadas, se cumple si cada cuenta pertenece a un solo cliente.
  - **Por qué:** estas tres propiedades son las que garantizan que fragmentar no pierde ni duplica datos (Özsu). Se debe poder **demostrar** cada una con una consulta, no solo afirmarla. Guardar esas consultas como evidencia.

### 2.5 Réplica y asignación

- [ ] **Tabla de réplica:** qué fragmento/tabla se replica, factor y criterio de costo.
  - `GLOBAL` para tablas pequeñas que se leen mucho y se escriben poco (catálogos, tipos de cambio). **Por qué:** evita joins remotos. Cada región lee su copia local rápido, a cambio de escrituras más lentas.
  - `REGIONAL BY ROW` para datos que pertenecen a una región. **Por qué:** lecturas y escrituras locales para el caso común (cliente opera en su región) y cumplimiento de residencia.
  - **Distinguir explícitamente** réplica Raft (RF=3, durabilidad y consenso) de réplica selectiva de Özsu (decisión de diseño sobre qué copiar y dónde). **Por qué:** el Lab 1 advierte que *"una réplica Raft no es la réplica selectiva de Özsu"*. Confundirlas es un error conceptual que se nota en la defensa.

- [ ] **Descripción de la asignación + diagrama** (fragmento → nodo/región: `crdb-1`=cr-sj, `crdb-2`=cr-limon, `crdb-3`=us-east).
  - **Por qué:** es un requisito explícito del E1 y del informe ("Diseño E1 + diagrama de asignación").

- [ ] **Declarar el límite de residencia.** Evaluar (y documentar la decisión) `ALTER DATABASE … PLACEMENT RESTRICTED`.
  - **Por qué:** el Lab 1 (§2) dice que `REGIONAL BY ROW` fija la región hogar y el leaseholder, **pero no garantiza que las copias no salgan de la región**. No se puede afirmar "la PII nunca sale de la región" basándose solo en el Compose. `PLACEMENT RESTRICTED` intenta dejar las réplicas en la región hogar, pero con **un solo nodo por región** eso deja una sola copia: si cae el nodo, se pierde la disponibilidad de esa región. Es un trade-off residencia vs. disponibilidad y sirve directo para E5. Probarlo con `SHOW RANGES … WITH DETAILS` antes de afirmar nada.

- [ ] **Sección "Requisitos y regiones"** (½–1 página): operaciones típicas (abrir cuenta, depositar, consultar saldo, transferir entre regiones) y su frecuencia estimada.
  - **Por qué:** la frecuencia de acceso es el insumo para justificar fragmentación y réplica con **costo**. Sin ella, la tabla de réplica es opinión.

- [ ] **Revisión cruzada del E1 y commit** (`docs/p1/E1-diseno.md` o sección del informe).

---

## 3. Implementación (Fases B–C, E2, 20 %)

### 3.1 Estructura propia del P1

- [ ] Crear una carpeta propia, por ejemplo:

  ```text
  p1/
  ├── README.md            ← cómo reproducir todo en una máquina limpia
  ├── sql/
  │   ├── 00_database.sql  ← CREATE DATABASE + PRIMARY REGION + ADD REGION
  │   ├── 01_schema.sql    ← tablas con LOCALITY
  │   └── 02_e4_table.sql  ← tabla RF=3 para la prueba de falla
  ├── gen/seed.py          ← generador de datos determinista
  ├── bench/latency.py     ← E3
  ├── chaos/e4.sh + probe.py
  └── baseline/            ← E5 (nodo único)
  evidence/p1/
  ```

  - **Por qué una carpeta aparte:** (1) el lab dice que **entregar sus archivos renombrados no cumple el P1**; (2) el repo del curso va a recibir actualizaciones (Lab 2 en S7) y tener el P1 separado evita conflictos al traerlas; (3) el corrector encuentra todo en un solo lugar.

- [ ] **Usar una base de datos propia** (p. ej. `p1_banca`) en vez de `ti4601`.
  - **Por qué:** `ti4601` tiene las tablas del Lab 1 y el Lab 2 (S7) usa el mismo clúster. Una base separada permite recrear el P1 (`DROP DATABASE p1_banca CASCADE`) sin romper los labs ni tener que usar `make lab1-down-v`, que borra todos los volúmenes.

### 3.2 Esquema y datos

- [ ] **`00_database.sql`**: primary region + las otras dos regiones. Idempotente (`IF NOT EXISTS` / verificar con `SHOW REGIONS`).
  - **Por qué idempotente:** "reproducible" significa que se puede correr dos veces sin errores. El Lab 1 mostró que repetir `ADD REGION` falla si ya existe.

- [ ] **`01_schema.sql`**: tablas con `LOCALITY REGIONAL BY ROW AS region` o `LOCALITY GLOBAL`, según E1.
  - **Por qué:** es literalmente lo que pide E2 (*"Tablas creadas con locality / particionamiento por región"*) y lo que revisa la rúbrica (*"3 nodos + schema locality"*).

- [ ] **`gen/seed.py`**: generador en Python (psycopg) con **semilla fija** (`random.seed(…)`), N clientes por región, cuentas y movimientos. Justificar el volumen en el README.
  - **Por qué semilla fija:** con la misma semilla, otra máquina genera exactamente los mismos datos, así las mediciones se pueden repetir y comparar.
  - **Por qué justificar volumen:** con muy pocas filas todo cabe en caché y en un solo rango, y la medición no representa nada. Con demasiadas, la carga tarda y el equipo no podrá repetirla. El lab lo pide explícitamente.
  - Usar inserciones por lotes (varias filas por `INSERT` o `COPY`). **Por qué:** una transacción por fila con consenso Raft hace la carga muy lenta.

- [ ] **Tabla para E4 con RF=3 y 3 votantes reales** (`02_e4_table.sql`). Debe ser del dominio (p. ej. `bitacora_operaciones` o un contador de transferencias), no una copia de `raft_probe`.
  - **Por qué:** el lab advierte que los rangos `REGIONAL BY ROW` pueden quedar **subreplicados** con un nodo por región. Si se mide la falla sobre una tabla RBR subreplicada y se concluye "sobrevive a la caída", la conclusión es falsa. Hay que **verificar** con `SHOW RANGES FROM TABLE … WITH DETAILS` que `voting_replicas` tiene 3 IDs antes de usarla.

### 3.3 Automatización y README

- [ ] **Script único de configuración** (p. ej. `p1/setup.sh` o targets `p1-*` en un `p1.mk` incluido desde el `Makefile`): levantar clúster → licencia → SQL → seed → verificación.
  - **Por qué:** la rúbrica da 50 a lo que *"corre en mi máquina sin guía"*. El 100 exige que un tercero lo reproduzca. Un script elimina los pasos manuales que se olvidan.

- [ ] **Verificador propio** (tipo `verify_cluster.py` pero con las tablas del P1): nodos vivos, 3 regiones, cada tabla con su `LOCALITY`, filas por región, votantes de la tabla E4.
  - **Por qué:** permite saber rápido si el entorno está listo antes de medir. Medir sobre un clúster mal configurado invalida E3 y E4.

- [ ] **`p1/README.md`**: requisitos, comandos exactos para levantar, cargar, medir y provocar la falla, tiempo estimado y problemas comunes. **Sin la licencia.**
  - **Por qué:** es un entregable explícito de E2 (*"README del equipo: cómo levantar, cargar datos y repetir mediciones en una máquina limpia"*).

- [ ] **Guardar evidencia de E2** en `evidence/p1/`: `SHOW REGIONS`, `SHOW CREATE TABLE` de cada tabla, `SHOW RANGES … WITH DETAILS`, conteo por región, salida del verificador.
  - **Por qué:** E2 pide *"capturas o salidas de SHOW RANGES / equivalente + SHOW CREATE"*. Los archivos de texto con fecha son mejor evidencia que capturas de pantalla y se pueden versionar. En el Lab 1 se perdieron dos de estas salidas por copiarlas a mano (lección 1). Por eso aquí las genera el script.

- [ ] **Prueba en máquina limpia** (la laptop de otro integrante): clonar y seguir solo el README.
  - **Por qué:** es la única forma de detectar pasos que funcionan por estado previo (volúmenes viejos, `.env` local, tablas creadas a mano). Si falla, se corrige el README, no la máquina.

### 3.4 Decisión sobre latencia inyectada

- [x] **Decisión: medir sin latencia inyectada** (2026-09-12).
  - **Por qué:** el docente no ha indicado nada sobre inyectar latencia, y el repo no trae ninguna herramienta para hacerlo. Inyectarla (p. ej. `tc netem`) exigiría cambiar el `docker-compose.yml` (`cap_add: NET_ADMIN`), que es parte del stack obligatorio, y eso arriesga el criterio "otro stack no aprobado" de E2. La guía del Lab 1 (§6) ya define qué hacer en este caso: reportar lo medido y declarar que (i) las regiones son lógicas, (ii) la máquina, los recursos y el número de corridas se mantuvieron constantes, y (iii) inferir el costo de una WAN requeriría latencia controlada.
  - **Consecuencia que hay que asumir en el informe:** E3 probablemente mostrará local ≈ remoto (como en el Lab 1), y **la diferencia visible será lectura vs. escritura, no local vs. remoto**. En E5 esto pesa a favor del nodo único en latencia, y la conclusión probable es *"justificado solo por residencia"*. Tiene que salir de los números, no escribirse antes.
  - **Qué sí se puede argumentar sin inyectar:** el costo *estructural* de cruzar región, que no depende de la red: número de rangos y grupos Raft que toca cada operación, dónde está el leaseholder (`SHOW RANGES`) y si una transacción entre dos regiones toca más rangos que una local. Eso explica **por qué** en una WAN real el p99 remoto sería mayor, aunque aquí no se vea.
  - Si en clase el docente llega a mencionar latencia inyectada, se reabre esta decisión.

---

## 4. Mediciones (E3, 20 %)

- [ ] **Definir en una frase "local" vs. "cruza región".** Propuesta: *"Local: el gateway SQL y la región hogar de la fila son la misma región. Cruza región: son distintas."*
  - **Por qué:** es obligatorio en la metodología y todo lo demás depende de esa definición.

- [ ] **Escribir `bench/latency.py` propio** con **operaciones del dominio** (no los UUID del lab):
  - Lectura local: consultar saldo de una cuenta `cr-sj` conectando a `crdb-1`.
  - Lectura remota: consultar saldo de una cuenta `cr-limon` conectando a `crdb-1`.
  - Escritura local: insertar un movimiento en `cr-sj` desde `crdb-1`.
  - Escritura que cruza región: insertar un movimiento en `cr-limon` desde `crdb-1`.
  - *(Opcional, suma a E5)* transferencia entre cuentas de dos regiones y lectura/escritura sobre la tabla `GLOBAL`.
  - **Por qué conectar a un host fijo:** en `app-crdb`, `PGHOST=crdb-1,crdb-2,crdb-3` deja que la conexión vaya a cualquier nodo. Si el gateway cambia, "local" y "remoto" pierden significado. Registrar `gateway_region()` en cada muestra lo confirma.
  - **Por qué operaciones del dominio:** el lab lo exige, y así los números de E5 hablan del sistema real.

- [ ] **Método:** warm-up descartado (p. ej. 10 corridas), **n ≥ 30 por caso (recomendado 100)**, `time.perf_counter()`, p50 y p99 con *nearest rank*, CSV crudo con timestamp, mismo perfil de recursos para todo.
  - **Por qué warm-up:** las primeras corridas incluyen conexión, caché fría y planes sin compilar, y distorsionan el p99.
  - **Por qué n=100 y no 30:** con n=30 el p99 por *nearest rank* es simplemente el valor máximo. Con 100 empieza a significar algo. La rúbrica da 50 a *"solo promedios o n<10"*.
  - **Por qué p99 y no promedio:** la cola (p99) es lo que sufren los usuarios y lo que la latencia remota y el consenso empeoran. El promedio lo esconde.
  - **Por qué CSV crudo:** permite recalcular y demuestra que los números no se escribieron a mano.

- [ ] **Registrar el entorno:** CPU/RAM de la máquina, perfil (lab completo, `--cache=256MiB`), versión CRDB, fecha/hora de inicio, latencia inyectada (si aplica).
  - **Por qué:** es obligatorio ("declarar perfil") y hace comparables las repeticiones.

- [ ] **Llenar la tabla** (Desde región / p50 / p99 / n / Notas) e **interpretar**: por qué p99 remoto > p99 local (viaje de ida y vuelta al leaseholder remoto + consenso Raft con quórum en otra región + variabilidad de red). Si no salió mayor, explicar por qué (misma máquina, sin WAN).
  - **Por qué:** es una de las cuatro preguntas fijas de la defensa.

---

## 5. Falla de nodo (E4, 15 %)

- [ ] **Escribir `chaos/e4.sh` + sonda propia** que siga el protocolo del PDF:
  1. Estado sano: escritura de prueba OK (con timestamp).
  2. Registrar leaseholder y votantes (`SHOW RANGES … WITH DETAILS`) → `evidence/p1/e4-before.txt`.
  3. `docker stop --timeout 0 <contenedor>` y guardar la época exacta (`date +%s.%N`).
  4. La sonda escribe cada ~0,5 s y registra `ok/error` + `completed_epoch` hasta que vuelve a confirmar (o timeout documentado).
  5. `docker start` del nodo, verificar `is_live`.
  6. Verificar RPO: la última escritura **confirmada** antes de la falla sigue presente.
  - **Por qué script y no comandos a mano:** el lab exige *"automatización reproducible de la falla"*. Además, entre el `docker stop` y el `date` a mano se pueden perder cientos de ms, y eso contamina el RTO.
  - **Por qué detener el nodo que tiene el lease:** si se detiene un nodo sin lease, las escrituras casi no se ven afectadas y el RTO sale ~0, así que no se demuestra la conmutación. Mover el lease antes (`ALTER RANGE RELOCATE LEASE TO <store_id>`) hace que el experimento muestre la elección de un nuevo leaseholder.

- [ ] **Calcular RTO a partir del CSV** (`completed_epoch` del primer `after-stop ok` − época de la falla) y mostrar el cálculo.
  - **Por qué:** el Lab 1 pide explícitamente no copiar el valor impreso por la sonda. En el PDF debe verse la resta.

- [ ] **Discutir RPO:** 0 para commits confirmados (Raft solo confirma con mayoría 2/3), y los intentos con error tienen **resultado desconocido**, no son "pérdida".
  - **Por qué:** es el criterio del 100 en la rúbrica (*"Bitácora + RTO/RPO discutidos"*) y una pregunta de defensa ("qué pasó al matar el nodo").

- [ ] **Repetir la falla al menos 3 veces** y reportar cada RTO (o el rango).
  - **Por qué:** un solo RTO puede ser casualidad (depende de cuándo expira el lease). Tres corridas muestran si es estable. No lo pide el PDF, pero hace la conclusión más defendible.

- [ ] *(Opcional)* Detener el nodo de una región y observar qué pasa con las filas RBR de **esa** región.
  - **Por qué:** conecta E4 con la discusión de residencia/`PLACEMENT RESTRICTED` y con E5: muestra el costo de disponibilidad de la localidad.

- [ ] *(Bonus)* Partición de red entre regiones: solo si sobra tiempo (materia del Lab 3).

---

## 6. Crítica "¿hacía falta distribuir?" (E5, 15 %)

- [ ] **Medir la alternativa con números**, no solo describirla. Opción práctica: correr **las mismas operaciones de `bench/latency.py`** contra el servicio `postgres` del mismo Compose (un nodo, misma máquina).
  - **Por qué:** la rúbrica pide *"comparación 1-nodo con números"*. El Postgres del Compose ya es parte del stack permitido y corre con los mismos recursos, así que la comparación es justa. Para la **réplica de lectura** basta con describir su efecto (lecturas locales posibles, escrituras siempre van al primario, lag asíncrono → RPO > 0) si no se puede montar.

- [ ] **Comparar en tres ejes:** latencia (tabla E3 vs. nodo único), complejidad operativa (nº de pasos del setup, licencia, subreplicación, depuración de leases) y costo (CPU/RAM de 3 nodos vs. 1 en la misma máquina, medible con `docker stats`).
  - **Por qué:** son los tres ejes exactos que pide el PDF. `docker stats` da un número real de costo en vez de una opinión.

- [ ] **Conclusión explícita:** *justificado / no justificado / justificado solo por residencia*, apoyada en los números.
  - **Por qué:** una conclusión vaga vale 50. Con la PII de la opción A y los números locales, lo más probable es *"justificado solo por residencia"*, pero **la conclusión debe salir de los datos**, no escribirse antes.

- [ ] Mínimo 1 página.

---

## 7. Informe PDF

- [ ] Estructura del PDF (§4 del enunciado):
  1. Portada (equipo, carnés, dominio, motor, URL del repo)
  2. Requisitos y regiones (½–1 pág)
  3. Diseño E1 (2–4 pág) + diagrama de asignación
  4. Implementación E2 (cómo reproducir)
  5. Mediciones E3 (tablas + interpretación + metodología)
  6. Falla de nodo E4 (línea temporal + cálculo RTO/RPO)
  7. Crítica E5
  8. Apéndice: scripts, salidas, **roles del equipo**
  - **Por qué seguir este orden:** es la estructura que el docente espera leer, y facilita encontrar cada criterio de la rúbrica.
- [ ] Revisar que **ningún** archivo ni captura muestre `COCKROACH_LICENSE`.
- [ ] Subir a TEC Digital + tag en git (`git tag entrega-p1`).
  - **Por qué el tag:** marca exactamente qué versión del código produjo los números del PDF.

---

## 8. Preparar la defensa (S8, ~10 min + preguntas)

- [ ] Ensayar respuestas cortas (1–2 min cada una) a las cuatro preguntas fijas:
  1. **¿Cuál es la shard key y por qué?**
  2. **¿Por qué el p99 remoto es mayor?** (o por qué no lo fue en su medición)
  3. **¿Qué pasó al matar el nodo?** (lease, mayoría 2/3, RTO, RPO = 0 para commits confirmados)
  4. **¿Cuál es la conclusión de E5 y con qué números?**
- [ ] Cada integrante debe poder contestar las cuatro, no solo la suya.
  - **Por qué:** el interrogatorio puede dirigirse a cualquiera y los puntos se pierden de forma individual.
- [ ] Preguntas probables extra: diferencia réplica Raft vs. réplica de Özsu; por qué con 2 nodos caídos no hay quórum; qué garantiza y qué no `REGIONAL BY ROW` sobre residencia; `GLOBAL` vs. `REGIONAL BY ROW`.
- [ ] Tener el clúster levantado y un comando listo para mostrar `SHOW RANGES` en vivo (por si lo piden).

---

## Cronograma sugerido

> Fechas aproximadas según la evidencia del Lab 1 (2 de sept. ≈ S5). **Confirmar con el calendario del curso.**

| Semana | Objetivo | Tareas |
| --- | --- | --- |
| **S6 (esta semana)** | Repo sano + diseño cerrado | §1 completo (repo del equipo creado), §2 completo |
| **S7** | Implementación + mediciones | §3 completo, §4 completo, §5 primera corrida. *Cuidado: el Lab 2 usa el mismo clúster.* |
| **S7 → S8** | Falla, crítica, informe | §5 repeticiones, §6, §7, prueba en máquina limpia |
| **S8** | Defensa | §8 |

**Regla del equipo:** al terminar cada casilla → commit con un mensaje que diga qué se hizo
(p. ej. `E1: predicados de fragmentación derivada para movimiento`).
