#!/usr/bin/env bash
# P1 · Configuración completa y reproducible del clúster para el dominio banca.
# Uso (HOST, raíz del repo):
#   p1/setup.sh            primera vez, o para completar lo que falte (idempotente)
#   p1/setup.sh --reset    vuelve a cargar los datos del seed desde cero
set -euo pipefail
cd "$(dirname "$0")/.."

RUN=(docker compose --progress quiet --profile lab1 run --rm --no-deps -T app-crdb)
PSQL=(psql -X -q -v ON_ERROR_STOP=1)

paso() { printf '\n== %s\n' "$*"; }

if [[ ! -f .env ]]; then
  echo "AVISO: no existe .env; sin COCKROACH_LICENSE solo funciona durante la gracia de 7 días."
fi

paso "1/7 Levantar clúster (3 nodos)"
make -s lab1-up

paso "2/7 Esperar a que los 3 nodos estén vivos"
for _ in $(seq 1 30); do
  vivos=$(docker exec ti4601-crdb-1 cockroach node status --insecure --format=csv 2>/dev/null \
          | awk -F, 'NR > 1 && $NF == "true"' | wc -l)
  [[ "$vivos" -eq 3 ]] && break
  sleep 2
done
echo "nodos vivos: $vivos"
[[ "$vivos" -eq 3 ]] || { echo "ERROR: no hay 3 nodos vivos; revise make lab1-status"; exit 1; }

paso "3/7 Licencia"
"${RUN[@]}" python3 labs/lab1-cluster/install_license.py

paso "4/7 Base p1_banca y regiones"
"${RUN[@]}" "${PSQL[@]}" -d defaultdb -f p1/sql/00_database.sql

paso "5/7 Esquema y tabla de E4"
"${RUN[@]}" "${PSQL[@]}" -d p1_banca -f p1/sql/01_schema.sql
"${RUN[@]}" "${PSQL[@]}" -d defaultdb -f p1/sql/02_e4_table.sql

paso "6/7 Datos (seed determinista)"
"${RUN[@]}" python3 p1/gen/seed.py "$@"

paso "7/7 Verificación"
"${RUN[@]}" python3 p1/check.py
