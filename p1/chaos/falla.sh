#!/usr/bin/env bash
# P1 · E4: caída de un nodo con escrituras del dominio en curso.
# Escritura sana → lease al nodo que caerá → sonda → docker stop (con época) → docker start
# → estado final → RTO calculado desde el CSV.
#
# Uso (HOST, raíz del repo, clúster arriba y p1/setup.sh ya ejecutado):
#   p1/chaos/falla.sh                          corrida 1, cae el nodo de cr-limon
#   p1/chaos/falla.sh --corrida 2              otra corrida, sin pisar la evidencia anterior
#   p1/chaos/falla.sh --region us-east --caido 20
# Evidencia: evidence/p1/e4-corrida<N>{-antes.txt,.csv,-sonda.txt,-stop.epoch,-stop.txt,-despues.txt,-rto.txt}
set -euo pipefail
cd "$(dirname "$0")/../.."

REGION=cr-limon   # región del nodo que se detiene
CORRIDA=1
CAIDO=15          # segundos con el nodo detenido
BASE=5            # segundos de escrituras sanas antes del stop
DURACION=60       # segundos totales de la sonda
GATEWAY=crdb-1    # la sonda escribe por aquí; no puede ser el nodo que cae
while [[ $# -gt 0 ]]; do
  case $1 in
    --region) REGION=$2; shift 2 ;;
    --corrida) CORRIDA=$2; shift 2 ;;
    --caido) CAIDO=$2; shift 2 ;;
    *) echo "opción desconocida: $1" >&2; exit 2 ;;
  esac
done

RUN=(docker compose --progress quiet --profile lab1 run --rm --no-deps -T app-crdb)
SQL=("${RUN[@]}" psql -X -q -v ON_ERROR_STOP=1 -h "$GATEWAY" -d p1_control)
TABLA=p1_control.public.folio_comprobante
PFX=evidence/p1/e4-corrida$CORRIDA
mkdir -p evidence/p1

paso() { printf '\n== %s\n' "$*"; }
sello() { echo "# Generado: $(date --iso-8601=seconds) · host: $(hostname) · corrida $CORRIDA"; }
valor() { "${SQL[@]}" -At -c "$1"; }
rangos() { "${SQL[@]}" -c "SELECT range_id, lease_holder, lease_holder_locality, voting_replicas
                          FROM [SHOW RANGES FROM TABLE $TABLA WITH DETAILS]"; }

if [[ -e $PFX.csv ]]; then
  echo "ERROR: ya existe $PFX.csv; use otra --corrida para no ocultar el resultado anterior" >&2
  exit 1
fi

paso "1/7 Tres nodos vivos"
vivos=$(docker exec ti4601-crdb-1 cockroach node status --insecure --format=csv \
        | awk -F, 'NR > 1 && $NF == "true"' | wc -l)
echo "nodos vivos: $vivos"
[[ "$vivos" -eq 3 ]] || { echo "ERROR: se necesitan 3 nodos vivos (make lab1-status)"; exit 1; }

paso "2/7 Nodo, store y contenedor de $REGION (por localidad, no por número de contenedor)"
# node_id lo asigna el clúster al unirse cada nodo; en otra máquina crdb-2 fue el nodo 2
# y aquí es el 3 (E3 §4). RELOCATE LEASE recibe un store_id, no un node_id.
IFS='|' read -r NODO STORE HOST_NODO < <(valor "
  SELECT g.node_id, s.store_id, split_part(g.address, ':', 1)
  FROM crdb_internal.gossip_nodes g JOIN crdb_internal.kv_store_status s ON s.node_id = g.node_id
  WHERE g.locality LIKE 'region=$REGION,%'")
[[ -n ${NODO:-} ]] || { echo "ERROR: ningún nodo con region=$REGION"; exit 1; }
# El contenedor se busca por el hostname que anuncia el nodo, no por su nombre.
CONTENEDOR=$(for c in $(docker ps --format '{{.Names}}' --filter name=ti4601-crdb); do
               [[ $(docker inspect -f '{{.Config.Hostname}}' "$c") == "$HOST_NODO" ]] && echo "$c"
             done; true)   # `true`: el estado del for es el de su última comparación y set -e abortaría
[[ -n $CONTENEDOR ]] || { echo "ERROR: ningún contenedor con hostname $HOST_NODO"; exit 1; }
[[ $HOST_NODO != "$GATEWAY" ]] || { echo "ERROR: $REGION es la región del gateway de la sonda"; exit 1; }
echo "region=$REGION → node_id=$NODO, store_id=$STORE, dirección=$HOST_NODO, contenedor=$CONTENEDOR"
# Pase lo que pase después, el nodo vuelve a arrancar.
trap 'docker start "$CONTENEDOR" >/dev/null 2>&1 || true' EXIT

paso "3/7 Escritura sana y lease al nodo que va a caer"
{
  sello
  echo "region=$REGION → node_id=$NODO, store_id=$STORE, dirección=$HOST_NODO, contenedor=$CONTENEDOR"
  echo; echo "== nodos y stores"
  "${SQL[@]}" -c "SELECT g.node_id, s.store_id, g.address, g.locality, g.is_live
                  FROM crdb_internal.gossip_nodes g JOIN crdb_internal.kv_store_status s ON s.node_id = g.node_id
                  ORDER BY g.node_id"
  echo "== escritura sana (antes de mover el lease)"
  "${SQL[@]}" -c "UPDATE $TABLA SET ultimo_folio = ultimo_folio + 1, actualizado_en = now()
                  WHERE serie = 'TRANSFERENCIAS' RETURNING serie, ultimo_folio, actualizado_en"
  echo "== rango antes de mover el lease"
  rangos
} > "$PFX-antes.txt"
"${SQL[@]}" -c "ALTER RANGE RELOCATE LEASE TO $STORE
                FOR SELECT range_id FROM [SHOW RANGES FROM TABLE $TABLA]" > /dev/null
for _ in $(seq 1 15); do
  lh=$(valor "SELECT DISTINCT lease_holder FROM [SHOW RANGES FROM TABLE $TABLA WITH DETAILS]")
  [[ $lh == "$NODO" ]] && break
  sleep 2
done
{ echo "== rango después de mover el lease al store $STORE"; rangos; } >> "$PFX-antes.txt"
echo "lease_holder=$lh"
[[ $lh == "$NODO" ]] || { echo "ERROR: el lease no llegó al nodo $NODO; vea $PFX-antes.txt"; exit 1; }

paso "4/7 Sonda de escrituras (gateway $GATEWAY, $DURACION s)"
"${RUN[@]}" python3 p1/chaos/sonda.py --gateway "$GATEWAY" --duracion "$DURACION" --csv "$PFX.csv" \
  > "$PFX-sonda.txt" 2>&1 &
SONDA=$!
# Se espera a ver escrituras OK reales antes de provocar la falla (el contenedor tarda en arrancar).
for _ in $(seq 1 60); do
  [[ -f $PFX.csv ]] && (( $(grep -c ',ok,' "$PFX.csv" || true) >= 3 )) && break
  sleep 0.5
done
sleep "$BASE"
echo "escrituras OK antes de la falla: $(grep -c ',ok,' "$PFX.csv" || true)"

paso "5/7 docker stop $CONTENEDOR (${CAIDO} s detenido)"
docker stop --timeout 0 "$CONTENEDOR" > /dev/null
date +%s.%N > "$PFX-stop.epoch"
{ echo "stop:  $(date --iso-8601=ns)  ($CONTENEDOR, node_id=$NODO, region=$REGION, leaseholder del rango)"; } > "$PFX-stop.txt"
cat "$PFX-stop.txt"
sleep "$CAIDO"
docker start "$CONTENEDOR" > /dev/null
echo "start: $(date --iso-8601=ns)  ($CONTENEDOR)" | tee -a "$PFX-stop.txt"
wait "$SONDA"
tail -1 "$PFX-sonda.txt"

paso "6/7 Estado después de la falla"
for _ in $(seq 1 30); do
  vivos=$(docker exec ti4601-crdb-1 cockroach node status --insecure --format=csv \
          | awk -F, 'NR > 1 && $NF == "true"' | wc -l)
  [[ "$vivos" -eq 3 ]] && break
  sleep 2
done
{
  sello
  echo "== nodos"
  docker exec ti4601-crdb-1 cockroach node status --insecure
  echo; echo "== rango (lease y votantes tras la recuperación)"
  rangos
  echo "== folio confirmado al final"
  "${SQL[@]}" -c "SELECT serie, ultimo_folio, actualizado_en FROM $TABLA"
} > "$PFX-despues.txt"
echo "nodos vivos: $vivos"

paso "7/7 RTO desde el CSV"
"${RUN[@]}" python3 p1/chaos/rto.py "$PFX.csv" "$PFX-stop.epoch" | tee "$PFX-rto.txt"
echo
echo "ok  $PFX-{antes.txt,.csv,sonda.txt,stop.epoch,stop.txt,despues.txt,rto.txt}"
