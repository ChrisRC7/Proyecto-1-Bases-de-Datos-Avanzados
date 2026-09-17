# TODO: Proyecto 1

Dominio: **Opción A, Banca / billetera regional** (`cr-sj`, `cr-limon`, `us-east`). Defensa: **Semana 8**.

## 1. E1: Diseño de fragmentación (25 %)
- [x] Requisitos y regiones: operaciones típicas y frecuencia estimada
- [x] Esquema lógico `cliente`, `cuenta`, `movimiento` (+ tabla pequeña candidata a `GLOBAL`) con PK/FK
- [x] Predicados de fragmentación horizontal (`region = 'cr-sj'`…) y derivada para `cuenta` / `movimiento`
- [ ] Decidir si hay fragmentación vertical de la PII
- [ ] Tabla de verificación: completitud, reconstrucción, disyunción (con consulta SQL de prueba)
- [ ] Tabla de réplica: qué tabla, factor y criterio de costo (`GLOBAL` vs `REGIONAL BY ROW`)
- [ ] Distinguir réplica Raft de réplica de Özsu
- [ ] Asignación fragmento → nodo/región + diagrama
- [ ] Evaluar `PLACEMENT RESTRICTED` y declarar el límite de residencia

## 2. E2: Implementación (20 %)
- [ ] Crear la carpeta `p1/` (sql, gen, bench, chaos, baseline)
- [ ] Usar una base de datos propia (`p1_banca`)
- [ ] `00_database.sql`: región primaria + regiones (idempotente)
- [ ] `01_schema.sql`: tablas con `LOCALITY`
- [ ] `02_e4_table.sql`: tabla del dominio con RF=3 y 3 votantes verificados
- [ ] `gen/seed.py`: generador con semilla fija y volumen justificado
- [ ] Script único de configuración (levantar → licencia → SQL → seed → verificar)
- [ ] Verificador propio del P1
- [ ] Evidencia generada por script en `evidence/p1/` (`SHOW REGIONS`, `SHOW CREATE`, `SHOW RANGES`, conteos)
- [ ] `p1/README.md` para reproducir en una máquina limpia
- [ ] Probar en la máquina de otro integrante

## 3. E3: Mediciones (20 %)
- [ ] Definir "local" vs. "cruza región" en una frase
- [ ] `bench/latency.py` con operaciones del dominio y gateway fijo (`crdb-1`)
  - [ ] Lectura local / lectura remota
  - [ ] Escritura local / escritura que cruza región
- [ ] Warm-up descartado, n ≥ 30 (ideal 100), p50 y p99, CSV crudo
- [ ] Registrar el entorno (máquina, recursos, versión, sin latencia inyectada)
- [ ] Tabla de resultados + interpretación (por qué el p99 remoto es mayor o no)

## 4. E4: Falla de nodo (15 %)
- [ ] Script de falla: escritura sana → mover lease → `docker stop` con época → sonda → `docker start`
- [ ] Buscar nodo y `store_id` por localidad (no asumir que el número del contenedor es el del nodo)
- [ ] Calcular el RTO desde el CSV y mostrar la resta
- [ ] Verificar y discutir el RPO (commits confirmados)
- [ ] Repetir la falla 3 veces
- [ ] (Opcional) Caída de una región y efecto en sus filas RBR

## 5. E5: Crítica (15 %)
- [x] Correr el mismo benchmark contra Postgres de un nodo
- [x] Comparar latencia, complejidad operativa y costo (`docker stats`)
- [ ] Describir la alternativa con réplica de lectura
- [ ] Conclusión: justificado / no justificado / solo por residencia (≥ 1 página)

## 7. Informe PDF
- [ ] Portada, requisitos, E1, E2, E3, E4, E5, apéndice con roles
- [ ] Revisar que no aparezca la licencia
- [ ] Entregar en TEC Digital + `git tag entrega-p1`


