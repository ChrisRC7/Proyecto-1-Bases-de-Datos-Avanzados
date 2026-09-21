#!/usr/bin/env bash
# P1 · E4 (opcional): caída de una región completa y efecto sobre sus filas REGIONAL BY ROW.
# Con un nodo por región, detener ese nodo es perder la región. A diferencia de falla.sh, aquí
# NO se mueve ningún lease: se observa la colocación diseñada en E1 §8 (cada fragmento con su
# leaseholder en su región hogar) y qué pasa con cada fragmento cuando cae su región.
#
# Uso (HOST, raíz del repo, clúster arriba y p1/setup.sh ya ejecutado):
#   p1/chaos/region.sh                      cae cr-limon durante 30 s
#   p1/chaos/region.sh --region us-east --caido 20
# Evidencia: evidence/p1/e4-region-<region>{-antes.txt,.csv,-sonda.txt,-stop.epoch,-start.epoch,
#            -durante.txt,-despues.txt,-resumen.txt}
set -euo pipefail
cd "$(dirname "$0")/../.."

REGION=cr-limon   # región que se pierde
CAIDO=30          # segundos con la región caída
BASE=5            # segundos de operaciones sanas antes del stop
DURACION=60       # segundos totales de la sonda
GATEWAY=crdb-1    # la sonda entra por aquí; no puede ser la región que cae
while [[ $# -gt 0 ]]; do
  case $1 in
    --region) REGION=$2; shift 2 ;;
    --caido) CAIDO=$2; shift 2 ;;
    *) echo "opción desconocida: $1" >&2; exit 2 ;;
  esac
done

RUN=(docker compose --progress quiet --profile lab1 run --rm --no-deps -T app-crdb)
PFX=evidence/p1/e4-region-$REGION
mkdir -p evidence/p1

paso() { printf '\n== %s\n' "$*"; }
sello() { echo "# Generado: $(date --iso-8601=seconds) · host: $(hostname) · región caída: $REGION"; }
vivos() { docker exec ti4601-crdb-1 cockroach node status --insecure --format=csv \
            | awk -F, 'NR > 1 && $NF == "true"' | wc -l; }

if [[ -e $PFX.csv ]]; then
  echo "ERROR: ya existe $PFX.csv; muévalo antes de repetir para no ocultar el resultado anterior" >&2
  exit 1
fi

paso "1/7 Tres nodos vivos"
n=$(vivos); echo "nodos vivos: $n"
[[ $n -eq 3 ]] || { echo "ERROR: se necesitan 3 nodos vivos (make lab1-status)"; exit 1; }

paso "2/7 Nodo y contenedor de $REGION (por localidad)"
IFS='|' read -r NODO HOST_NODO < <("${RUN[@]}" psql -X -q -At -h "$GATEWAY" -d p1_banca -c "
  SELECT node_id, split_part(address, ':', 1) FROM crdb_internal.gossip_nodes
  WHERE locality LIKE 'region=$REGION,%'")
[[ -n ${NODO:-} ]] || { echo "ERROR: ningún nodo con region=$REGION"; exit 1; }
[[ $HOST_NODO != "$GATEWAY" ]] || { echo "ERROR: $REGION es la región del gateway de la sonda"; exit 1; }
CONTENEDOR=$(for c in $(docker ps --format '{{.Names}}' --filter name=ti4601-crdb); do
               [[ $(docker inspect -f '{{.Config.Hostname}}' "$c") == "$HOST_NODO" ]] && echo "$c"
             done; true)
[[ -n $CONTENEDOR ]] || { echo "ERROR: ningún contenedor con hostname $HOST_NODO"; exit 1; }
echo "region=$REGION → node_id=$NODO, contenedor=$CONTENEDOR"
trap 'docker start "$CONTENEDOR" >/dev/null 2>&1 || true' EXIT

paso "3/7 Colocación antes de la falla (sin mover leases)"
{ sello; echo "region=$REGION → node_id=$NODO, contenedor=$CONTENEDOR"; echo
  "${RUN[@]}" python3 p1/chaos/region.py leases --gateway "$GATEWAY"; } > "$PFX-antes.txt"
cat "$PFX-antes.txt"

paso "4/7 Sonda: 6 casos en paralelo por $GATEWAY ($DURACION s)"
"${RUN[@]}" python3 p1/chaos/region.py sondear --gateway "$GATEWAY" --duracion "$DURACION" --csv "$PFX.csv" \
  > "$PFX-sonda.txt" 2>&1 &
SONDA=$!
for _ in $(seq 1 60); do
  [[ -f $PFX.csv ]] && (( $(grep -c ',ok,' "$PFX.csv" || true) >= 12 )) && break
  sleep 0.5
done
sleep "$BASE"

paso "5/7 docker stop $CONTENEDOR: la región $REGION queda sin nodos (${CAIDO} s)"
docker stop --timeout 0 "$CONTENEDOR" > /dev/null
date +%s.%N > "$PFX-stop.epoch"
echo "stop:  $(date --iso-8601=ns)"
# A mitad de la caída: ¿quién atiende ahora los fragmentos de la región caída?
sleep $(( CAIDO / 2 ))
{ sello; echo "== leases con $REGION caída ($(( CAIDO / 2 )) s después del stop)"
  "${RUN[@]}" python3 p1/chaos/region.py leases --gateway "$GATEWAY"; } > "$PFX-durante.txt" 2>&1 || true
cat "$PFX-durante.txt"
sleep $(( CAIDO - CAIDO / 2 ))
docker start "$CONTENEDOR" > /dev/null
date +%s.%N > "$PFX-start.epoch"
echo "start: $(date --iso-8601=ns)"
wait "$SONDA"
cat "$PFX-sonda.txt"

paso "6/7 Recuperación: nodos, vuelta de los leases a su región hogar y verificador"
for _ in $(seq 1 30); do [[ $(vivos) -eq 3 ]] && break; sleep 2; done
{ sello
  echo "== nodos"; docker exec ti4601-crdb-1 cockroach node status --insecure; echo
  echo "== leases tras volver la región"
  "${RUN[@]}" python3 p1/chaos/region.py leases --gateway "$GATEWAY" --esperar-hogar 300; echo
  echo "== verificador (saldos y doble asiento tras las transferencias de la prueba)"
  "${RUN[@]}" python3 p1/check.py || true; } > "$PFX-despues.txt" 2>&1
cat "$PFX-despues.txt"

paso "7/7 Resumen por fragmento"
"${RUN[@]}" python3 p1/chaos/region.py resumir "$PFX.csv" "$PFX-stop.epoch" "$PFX-start.epoch" | tee "$PFX-resumen.txt"
echo
echo "ok  $PFX-{antes.txt,.csv,sonda.txt,stop.epoch,start.epoch,durante.txt,despues.txt,resumen.txt}"
