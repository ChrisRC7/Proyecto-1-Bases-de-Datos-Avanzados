# E1 — Diseño de fragmentación y asignación

**Dominio:** Opción A, banca / billetera regional · **Regiones:** `cr-sj`, `cr-limon`, `us-east` · **Motor:** CockroachDB ×3 (clúster del Lab 1)

---

## 1. Requisitos y regiones

| Región | En el dominio | Nodo |
| --- | --- | --- |
| `cr-sj` | Sede central, San José; concentra la mayoría de clientes | `crdb-1` (gateway de E3) |
| `cr-limon` | Sucursal regional, Limón | `crdb-2` |
| `us-east` | Clientes residentes en EE. UU. (remesas) | `crdb-3` |

La **región de apertura** es donde el cliente firmó su contrato y no cambia. Es la región hogar de su fila de `cliente`, de sus cuentas y de sus movimientos. **Regla de residencia (enunciado):** la PII (`nombre`, `documento`) solo existe en la región de apertura.

Frecuencias estimadas (supuestos de diseño, por cada 1 000 operaciones de una región en un día):

| # | Operación | Tipo | Frec. ‰ | Local / cruza región |
| --- | --- | --- | ---: | --- |
| O1 | Consultar saldo | lectura | 400 | local |
| O2 | Últimos *N* movimientos de una cuenta | lectura | 250 | local |
| O3 | Depósito o retiro | escritura | 150 | local |
| O4 | Transferencia, misma región | escritura | 100 | local |
| O5 | Transferencia, regiones distintas | escritura | 30 | **cruza región** |
| O6 | Identificar cliente por `documento` | lectura | 40 | local; la PII no sale |
| O7 | Consultar tasa / catálogo de monedas | lectura | 300 (dentro de O3–O5) | desde **todas** las regiones |
| O8 | Alta de cliente y cuenta | escritura | 5 | local (unicidad de `documento` cruza) |
| O9 | Reporte consolidado | lectura | < 1 | cruza todas (batch) |

Conclusiones que gobiernan el diseño: **~95 % de las operaciones tocan solo su región** → fragmentar por región. **O5 es la única escritura frecuente que cruza región** → es la "escritura que cruza región" de E3; O4 es la "escritura local". **`moneda` se lee desde todas las regiones y se escribe ~1 vez al día** → candidata a `GLOBAL`.

Volumen supuesto para el seed (E2 puede ajustarlo justificándolo): 3 000 clientes (50 / 30 / 20 % por región), ~4 500 cuentas, ~90 000 movimientos, 3 monedas (`CRC`, `USD`, `EUR`).

---

## 2. Esquema lógico

PK en **negrita**; `→` FK; (PII) datos personales.

| Relación | Columnas | Localidad |
| --- | --- | --- |
| `moneda` | **`codigo`** CHAR(3), `nombre`, `tasa_crc` DECIMAL > 0, `actualizado_en` | `GLOBAL` |
| `cliente` | **`region`**, **`cliente_id`** UUID, `documento` UNIQUE (PII), `nombre` (PII), `email` (PII), `creado_en` | RBR, primaria |
| `cuenta` | **`region`**, **`cuenta_id`** UUID, `cliente_id`, `moneda → moneda`, `saldo` ≥ 0, `estado`, `abierta_en`; FK `(region, cliente_id) → cliente` | RBR, derivada |
| `movimiento` | **`region`**, **`movimiento_id`** UUID, `cuenta_id`, `tipo`, `monto` > 0, `moneda → moneda`, `saldo_resultante`, `contraparte_region`, `contraparte_cuenta_id` (sin FK), `creado_en`; FK `(region, cuenta_id) → cuenta` | RBR, derivada |

```text
 moneda (GLOBAL)        cliente (RBR, primaria)
 ┌────────────┐         ┌───────────────────────────┐
 │ codigo PK  │         │ region, cliente_id   PK   │
 │ tasa_crc   │         │ documento UNIQUE    (PII) │
 └─────┬──────┘         │ nombre, email       (PII) │
       │                └─────────────┬─────────────┘
       │                              │ (region, cliente_id)
       │                cuenta (RBR, derivada)
       ├───────────────►┌─────────────┴─────────────┐
       │                │ region, cuenta_id    PK   │
       │                │ cliente_id FK · moneda FK │
       │                │ saldo, estado             │
       │                └─────────────┬─────────────┘
       │                              │ (region, cuenta_id)
       │                movimiento (RBR, derivada)
       └───────────────►┌─────────────┴─────────────┐
                        │ region, movimiento_id PK  │
                        │ cuenta_id FK · moneda FK  │
                        │ tipo, monto, contraparte_*│
                        └───────────────────────────┘
```

Tres decisiones:

- **`region` va primero en la PK de las tres relaciones fragmentadas.** Lección del Lab 1: `REGIONAL BY ROW AS region` reparte por esa columna y, al ir primero en la clave, las filas de una región quedan juntas. Toda operación O1–O8 conoce la región, así que filtra por ella y no hay *scatter*.
- **Las FK de `cuenta` y `movimiento` son compuestas e incluyen `region`.** No es solo integridad referencial: **obliga** a que una cuenta viva en la región de su dueño, y un movimiento en la de su cuenta. Es la FK la que hace cumplir la fragmentación derivada de §3 dentro del motor.
- **La PII vive solo en `cliente`**; `cuenta` y `movimiento` referencian `cliente_id`, nunca copian nombre ni documento. La residencia se reduce a controlar una relación. `documento` es `UNIQUE` global: el alta (O8, 5 ‰) paga una verificación entre regiones para que lo frecuente siga siendo local.

---

## 3. Predicados de fragmentación

Condiciones escritas como en SQL, según pide el enunciado. $\ltimes$ = semi-join.

| Relación | Tipo | Fragmento | Predicado / definición |
| --- | --- | --- | --- |
| `cliente` | horizontal **primaria** | `cliente_sj` | `region = 'cr-sj'` — clientes que abrieron en San José |
| | | `cliente_limon` | `region = 'cr-limon'` — ... en Limón |
| | | `cliente_us` | `region = 'us-east'` — ... en Estados Unidos |
| `cuenta` | horizontal **derivada** | `cuenta_r` | $cuenta \ltimes_{(region,\,cliente\_id)} cliente\_r$ — cuentas cuyo dueño está en `r` |
| `movimiento` | horizontal **derivada** | `movimiento_r` | $movimiento \ltimes_{(region,\,cuenta\_id)} cuenta\_r$ — movimientos de cuentas de `r` |
| `moneda` | ninguna | `moneda` | replicación completa en las tres regiones (`GLOBAL`) |

**Por qué `region`.** Es el atributo del predicado de todas las operaciones frecuentes, fija la regla de residencia y es estable. Sus tres valores son los minterms del atributo: el tipo `crdb_internal_region` no admite otro valor y la columna es `NOT NULL`. Sobre eso se apoya la tabla de verificación (completitud, reconstrucción y disyunción) de `cliente`. Descartados: `moneda` (partiría las operaciones de un mismo cliente) y rango de `documento` (no se relaciona con dónde se originan las operaciones).

**Derivada = selección directa.** CockroachDB no ejecuta semi-joins para colocar filas; necesita la columna `region`. Gracias a la FK compuesta, `cuenta.region` es siempre igual a la del dueño, por lo que

```text
cuenta_r  =  cuenta ⋉ cliente_r  =  σ region = 'r' (cuenta)        (igual para movimiento)
```

La igualdad se sostiene **porque existe la FK compuesta**. Por transitividad, toda la historia de un cliente queda en su región hogar. En la tabla de verificación esto se comprueba con una consulta: cuentas cuya `region` no coincide con la de su cliente → debe dar cero.

**Doble asiento en transferencias.** Una transferencia de A (`cr-sj`) a B (`cr-limon`) genera **dos** movimientos en la misma transacción: `TRANSF_ENVIO` en la región de A y `TRANSF_RECIBO` en la de B, cada uno con `contraparte_* ` apuntando al otro. Si un movimiento pudiera pertenecer a dos cuentas de regiones distintas estaría en dos fragmentos y se rompería la disyunción. Por eso `contraparte_cuenta_id` no lleva FK. Para E3: O5 escribe en dos fragmentos de dos regiones (la "escritura que cruza región"); O4 escribe las mismas cuatro filas en un solo fragmento (la "escritura local").

---

## 4. Decisiones sobre la PII y la residencia

**Fragmentación vertical de la PII: no se aplica.** `cliente` se mantiene como una sola relación.
La PII ya está confinada a ella por diseño (§2): `cuenta` y `movimiento` solo referencian
`cliente_id`. Lo que la regla de residencia exige —que `nombre` y `documento` vivan en la región de
apertura— lo cumple la fragmentación horizontal de `cliente`; separar `cliente_identidad` de
`cliente_base` no agregaría residencia, solo columnas repartidas dentro de la misma región. Además,
las dos operaciones que leen PII (O6, identificar por `documento`; O8, alta) leen la fila completa,
así que la vertical añadiría un join en cada una sin ahorrar ninguna lectura.

**`PLACEMENT RESTRICTED`: evaluado y no aplicado.** Esta sentencia ordena colocar todas las réplicas
de cada partición `REGIONAL BY ROW` dentro de su región hogar. Con un nodo por región no hay dónde
poner tres votantes en una sola región: la restricción no puede satisfacerse y el motor deja los
rangos como están. La evidencia de E2 lo muestra: la configuración de zona declara `num_voters = 3`
con `voter_constraints` en la región hogar (`e2-inspect.txt §5`), pero `SHOW RANGES` observa tres
votantes repartidos en `cr-sj`, `cr-limon` y `us-east` (§6). Aplicar la sentencia cambiaría lo
declarado sin cambiar lo observado.

**Límite que se declara.** Los datos de identificación del cliente tienen región hogar en su región
de apertura y su leaseholder se coloca allí. En este clúster de un nodo por región **no** puede
afirmarse que las copias físicas de la PII no salgan de la región: hoy existen réplicas en las tres.
Ninguna de las dos decisiones altera la evidencia de E2/E3 ni bloquea E4.

## Anexo — Borrador de DDL (No es el schema.sql final, pero es basado en la propuesta presentada)

```sql
CREATE TABLE moneda (
    codigo         CHAR(3)       PRIMARY KEY,
    nombre         STRING        NOT NULL,
    tasa_crc       DECIMAL(12,4) NOT NULL CHECK (tasa_crc > 0),
    actualizado_en TIMESTAMPTZ   NOT NULL DEFAULT now()
) LOCALITY GLOBAL;

CREATE TABLE cliente (
    region     crdb_internal_region NOT NULL,
    cliente_id UUID        NOT NULL DEFAULT gen_random_uuid(),
    documento  STRING      NOT NULL,
    nombre     STRING      NOT NULL,
    email      STRING      NOT NULL,
    creado_en  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (region, cliente_id),
    UNIQUE (documento)
) LOCALITY REGIONAL BY ROW AS region;

CREATE TABLE cuenta (
    region     crdb_internal_region NOT NULL,
    cuenta_id  UUID          NOT NULL DEFAULT gen_random_uuid(),
    cliente_id UUID          NOT NULL,
    moneda     CHAR(3)       NOT NULL REFERENCES moneda (codigo),
    saldo      DECIMAL(18,2) NOT NULL CHECK (saldo >= 0),
    estado     STRING        NOT NULL DEFAULT 'ACTIVA'
                             CHECK (estado IN ('ACTIVA','BLOQUEADA','CERRADA')),
    abierta_en TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (region, cuenta_id),
    FOREIGN KEY (region, cliente_id) REFERENCES cliente (region, cliente_id)
) LOCALITY REGIONAL BY ROW AS region;

CREATE TABLE movimiento (
    region                crdb_internal_region NOT NULL,
    movimiento_id         UUID          NOT NULL DEFAULT gen_random_uuid(),
    cuenta_id             UUID          NOT NULL,
    tipo                  STRING        NOT NULL
                          CHECK (tipo IN ('DEPOSITO','RETIRO','TRANSF_ENVIO','TRANSF_RECIBO')),
    monto                 DECIMAL(18,2) NOT NULL CHECK (monto > 0),
    moneda                CHAR(3)       NOT NULL REFERENCES moneda (codigo),
    saldo_resultante      DECIMAL(18,2) NOT NULL CHECK (saldo_resultante >= 0),
    contraparte_region    crdb_internal_region,
    contraparte_cuenta_id UUID,
    creado_en             TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (region, movimiento_id),
    FOREIGN KEY (region, cuenta_id) REFERENCES cuenta (region, cuenta_id),
    INDEX movimiento_por_cuenta (region, cuenta_id, creado_en DESC)   -- sirve a O2
) LOCALITY REGIONAL BY ROW AS region;
```
