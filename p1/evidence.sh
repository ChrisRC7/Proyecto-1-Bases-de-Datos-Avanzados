#!/usr/bin/env bash
# P1 · Genera la evidencia de E1 (verificación y asignación) y E2 en evidence/p1/ (solo lectura sobre el clúster).
# Uso (HOST, raíz del repo): p1/evidence.sh
set -euo pipefail
cd "$(dirname "$0")/.."

RUN=(docker compose --progress quiet --profile lab1 run --rm --no-deps -T app-crdb)
OUT=evidence/p1
mkdir -p "$OUT"

sello() { echo "# Generado: $(date --iso-8601=seconds) · host: $(hostname)"; }

{ sello; make -s lab1-status; } > "$OUT/e2-node-status.txt" 2>&1
echo "ok  $OUT/e2-node-status.txt"

{ sello; "${RUN[@]}" psql -X -v ON_ERROR_STOP=1 -d p1_banca -f p1/sql/inspect.sql; } \
  > "$OUT/e2-inspect.txt" 2>&1
echo "ok  $OUT/e2-inspect.txt"

{ sello; "${RUN[@]}" psql -X -v ON_ERROR_STOP=1 -d p1_banca -f p1/sql/verificacion.sql; } \
  > "$OUT/e1-verificacion.txt" 2>&1
echo "ok  $OUT/e1-verificacion.txt"

{ sello; "${RUN[@]}" psql -X -v ON_ERROR_STOP=1 -d p1_banca -f p1/sql/asignacion.sql; } \
  > "$OUT/e1-asignacion.txt" 2>&1
echo "ok  $OUT/e1-asignacion.txt"

# El verificador devuelve código distinto de 0 si algo falla; se conserva la salida igual.
set +e
{ sello; "${RUN[@]}" python3 p1/check.py; } > "$OUT/e2-check.txt" 2>&1
estado=$?
set -e
echo "ok  $OUT/e2-check.txt ($(tail -1 "$OUT/e2-check.txt"))"
exit "$estado"
