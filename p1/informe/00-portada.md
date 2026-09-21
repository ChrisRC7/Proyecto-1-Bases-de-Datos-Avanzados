# Proyecto 1 — Base de datos distribuida a pequeña escala

**Instituto Tecnológico de Costa Rica · TI-4601 Bases de Datos Avanzadas**

| | |
| --- | --- |
| **Dominio** | Opción A — Banca / billetera regional |
| **Regiones** | `cr-sj` (primaria), `cr-limon`, `us-east` |
| **Motor** | CockroachDB v24.3.0, 3 nodos (clúster del Lab 1), un nodo por región |
| **Baseline de comparación** | PostgreSQL 16, un nodo |
| **Cliente** | Python 3 + psycopg 3, siempre dentro del contenedor del curso |
| **Repositorio** | rama `Development`; evidencia versionada en `evidence/p1/` |

| Integrante | Carné | Usuario de git |
| --- | --- | --- |
| Christopher Rodriguez C. | 2022040771 | `ChrisRC7` |
| Fabricio Mena M. | 2019042722 | `fabrimena` |
| Alisson Redondo M. | 2021510425 | `AlissonRM19` |

---

## Resumen

Se diseñó, implementó y midió una base de datos bancaria fragmentada horizontalmente por región
sobre un clúster CockroachDB de tres nodos, uno por región simulada.

- **Diseño (E1).** `cliente` se fragmenta por `region` (fragmentación primaria); `cuenta` y
  `movimiento` heredan esa partición por fragmentación derivada, forzada con claves foráneas
  compuestas. `moneda` se replica completa (`GLOBAL`). Se verifican completitud, reconstrucción y
  disyunción con consultas SQL sobre los datos cargados.
- **Implementación (E2).** Un solo script (`p1/setup.sh`) levanta el clúster, crea las regiones, el
  esquema con `LOCALITY`, carga datos deterministas (huella `ad995e29a16440f7`) y verifica 10
  propiedades. Reproducido en la máquina de otro integrante.
- **Mediciones (E3).** n = 100 por caso, warm-up descartado, p50 y p99. La lectura remota cuesta
  ~3× en el p99; las dos escrituras cuestan lo mismo, y el informe explica por qué
  (un nodo por región ⇒ el quórum siempre cruza regiones).
- **Falla (E4).** Tres corridas deteniendo el nodo que tenía el lease: **RTO 4,6 / 6,5 / 5,2 s** y
  **RPO 0** para escrituras confirmadas, demostrado con una serie de folios sin huecos. Además se
  midió la caída de una región completa y su efecto sobre las filas `REGIONAL BY ROW`.
- **Crítica (E5).** Contra PostgreSQL de un nodo en la misma máquina, el clúster es 4,5–11× más
  lento y usa ~21× la memoria. Conclusión: **justificado solo por la regla de residencia**.

**Convención de este informe.** Cada afirmación numérica cita el archivo de `evidence/p1/` que la
respalda, y todos esos archivos los genera un script del repositorio. Los límites del montaje
(regiones lógicas, sin latencia inyectada, subreplicación de `REGIONAL BY ROW` con un nodo por
región) se declaran en cada entregable en lugar de omitirse.

---

# Requisitos y regiones

El dominio es una billetera regional con tres regiones: `cr-sj` (sede central, San José),
`cr-limon` (sucursal regional) y `us-east` (clientes en Estados Unidos, remesas). Las entidades del
enunciado son `cliente`, `cuenta` y `movimiento`, más un catálogo pequeño (`moneda`) que sirve de
candidato a tabla replicada.

**Regla de residencia (enunciado).** La PII del cliente —`nombre` y `documento`— solo debe existir
en su región de apertura. La región de apertura es donde el cliente firmó el contrato y no cambia:
es la región hogar de su fila de `cliente`, de sus cuentas y de sus movimientos.

**Operaciones y frecuencias** estimadas están en el entregable 1, sección 1. Las dos conclusiones
que gobiernan todo el diseño: ~95 % de las operaciones tocan una sola región, y la única escritura
frecuente que cruza regiones es la transferencia entre clientes de regiones distintas (O5), que es
justamente la "escritura que cruza región" medida en E3.

**Perfil de ejecución.** Tres contenedores CockroachDB en una sola máquina, con
`--cache=256MiB --max-sql-memory=256MiB`, sin latencia inyectada entre regiones. Las regiones son
lógicas: las cifras de E3 no representan una WAN.

---
