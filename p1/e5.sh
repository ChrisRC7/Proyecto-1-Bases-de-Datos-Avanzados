#!/usr/bin/env bash
# P1 · E5: mismo esquema, mismo seed y mismo benchmark de E3 contra PostgreSQL de un nodo.
# Uso (HOST, raíz del repo):
#   p1/e5.sh            carga lo que falte y mide
#   p1/e5.sh --reset    vuelve a cargar los datos del seed desde cero antes de medir
# Para comparar costo en reposo con el clúster, levántelo antes (p1/setup.sh): la foto de
# docker stats del paso 4 incluye todos los contenedores ti4601 que estén corriendo.
set -euo pipefail
cd "$(dirname "$0")/.."

# Servicio app: TI4601_ENGINE=postgres y PGHOST=postgres (docker-compose.yml).
RUN=(docker compose --progress quiet run --rm -T app)
OUT=evidence/p1
mkdir -p "$OUT"

paso() { printf '\n== %s\n' "$*"; }

paso "1/4 Levantar PostgreSQL"
make -s up

paso "2/4 Base p1_banca y esquema"
"${RUN[@]}" psql -X -q -v ON_ERROR_STOP=1 -f p1/sql/01_postgres_schema.sql

paso "3/4 Datos (mismo seed determinista que E2)"
"${RUN[@]}" python3 p1/gen/seed.py "$@"

paso "4/4 Benchmark de E3 y costo en reposo"
"${RUN[@]}" python3 p1/bench/latency.py
{
  echo "# Generado: $(date --iso-8601=seconds) · host: $(hostname) · nproc: $(nproc)"
  docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.BlockIO}}' \
    $(docker ps --filter name=ti4601- --format '{{.Names}}')
  echo
  echo "# Tamaño de los volúmenes de datos"
  docker system df -v | grep -E '^(VOLUME NAME|ti4601_)' || true
} > "$OUT/e5-docker-stats.txt"
echo "ok  $OUT/e5-docker-stats.txt"
