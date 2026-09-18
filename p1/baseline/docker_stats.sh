#!/usr/bin/env bash
# E5 · Costo en la misma máquina: docker stats de los 3 nodos CockroachDB frente al nodo PostgreSQL,
# en reposo y mientras corre cada benchmark, más tamaño de volúmenes y número de piezas a operar.
# Requiere ambos motores arriba (make lab1-up y make up) con datos cargados.
# Uso (HOST, raíz del repo): p1/baseline/docker_stats.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
OUT=evidence/p1/e5-docker-stats.txt
CRDB=(ti4601-crdb-1 ti4601-crdb-2 ti4601-crdb-3)
PG=(ti4601-postgres)
FMT='table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}'
CRDB_RUN=(docker compose --progress quiet --profile lab1 run --rm --no-deps -T app-crdb)
PG_RUN=(docker compose --progress quiet run --rm -T app)

muestra() { docker stats --no-stream --format "$FMT" "$@"; }

# Lanza un benchmark hacia una carpeta descartable dentro del contenedor (no genera evidencia
# nueva; solo produce carga) y, mientras corre, toma muestras de stats cada ~2 s. Se conserva la
# muestra con mayor CPU total: la que captura el benchmark en ejecución y no el arranque del
# contenedor ni el reposo posterior.
bajo_carga() {
  local titulo=$1; shift
  local contenedores=$1; shift
  "$@" >/dev/null 2>&1 &
  local pid=$! mejor="" mejor_cpu=-1 n=0
  while kill -0 "$pid" 2>/dev/null; do
    # shellcheck disable=SC2086
    local m; m=$(muestra $contenedores)
    local cpu; cpu=$(echo "$m" | awk 'NR>1 {gsub("%","",$2); s+=$2} END {printf "%d", s*100}')
    n=$((n+1))
    if (( cpu > mejor_cpu )); then mejor_cpu=$cpu; mejor=$m; fi
  done
  wait "$pid" || echo "(el benchmark de carga terminó con error; la muestra sigue siendo válida)"
  echo "== bajo carga: $titulo (mejor de $n muestras tomadas durante el benchmark)"
  echo "$mejor"
  echo
}

{
  echo "# Generado: $(date --iso-8601=seconds) · host: $(hostname)"
  echo "# cpus: $(nproc) · memoria total: $(awk '/MemTotal/ {printf "%d MiB", $2/1024}' /proc/meminfo)"
  echo
  echo "== reposo"
  muestra "${CRDB[@]}" "${PG[@]}"
  echo
  # Mismo número de operaciones en ambos (2000 rondas x 4 casos); PostgreSQL las termina mucho antes.
  bajo_carga "CockroachDB, latency.py" "${CRDB[*]}" \
    "${CRDB_RUN[@]}" python3 p1/bench/latency.py --salida /tmp/carga --corridas 2000 --warmup 10
  bajo_carga "PostgreSQL, latency_pg.py" "${PG[*]}" \
    "${PG_RUN[@]}" python3 p1/baseline/latency_pg.py --salida /tmp/carga --corridas 2000 --warmup 10
  echo "== volúmenes de datos"
  docker system df -v | awk '/^ti4601_(crdb|pgdata)/ {printf "%-16s %s\n", $1, $NF}' | sort
  echo
  echo "== piezas que hay que operar"
  printf 'CockroachDB : %s contenedores de datos + 1 init, %s volúmenes, licencia, regiones, %s pasos en p1/setup.sh\n' \
    "${#CRDB[@]}" "$(docker volume ls -q | grep -c '^ti4601_crdb')" "$(grep -c '^paso ' p1/setup.sh)"
  printf 'PostgreSQL  : %s contenedor, %s volumen, sin licencia ni regiones, 2 comandos (seed_pg.py, latency_pg.py)\n' \
    "${#PG[@]}" "$(docker volume ls -q | grep -c '^ti4601_pgdata')"
} | tee "$OUT"
echo "ok  $OUT"
