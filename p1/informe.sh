#!/usr/bin/env bash
# P1 · Arma el informe de entrega a partir de los documentos del repositorio y lo pasa a PDF.
#
# El informe NO se escribe aparte: se concatena de p1/informe/ y p1/docs/, así que nunca queda
# desincronizado de los entregables. Antes de generar el PDF se comprueba que la licencia de
# CockroachDB no aparezca en el texto (requisito de entrega).
#
# Uso (HOST, raíz del repo):  p1/informe.sh
# Salida: entregas/p1/INFORME.md y, si hay un conversor, entregas/p1/INFORME.pdf
set -euo pipefail
cd "$(dirname "$0")/.."

OUT=entregas/p1
MD=$OUT/INFORME.md
mkdir -p "$OUT"

# Orden del informe (estructura sugerida por el enunciado §4).
# Cada documento entra con sus títulos bajados un nivel, para que el informe tenga una sola
# jerarquía: # parte del informe, ## sección del entregable.
partes=(
  "p1/informe/00-portada.md:0:"
  "p1/docs/E1-diseno.md:1:E1 — Diseño de fragmentación y asignación (25 %)"
  "p1/README.md:1:E2 — Implementación y reproducción (20 %)"
  "p1/docs/E3-mediciones.md:1:E3 — Mediciones de latencia (20 %)"
  "p1/docs/E4-falla.md:1:E4 — Falla de nodo y de región (15 %)"
  "p1/docs/E5-comparacion.md:1:E5 — Crítica: ¿hacía falta distribuir? (15 %)"
  "p1/informe/99-apendice.md:0:"
)

python3 - "${partes[@]}" > "$MD" <<'PY'
import re
import sys

for parte in sys.argv[1:]:
    ruta, nivel, titulo = parte.split(":", 2)
    nivel = int(nivel)
    texto = open(ruta, encoding="utf-8").read()
    # Los diagramas mermaid solo se ven en GitHub; en el PDF quedarían como código ilegible.
    # El diagrama ASCII equivalente sí se conserva.
    texto = re.sub(r"```mermaid\n.*?```\n", "", texto, flags=re.S)
    if titulo:
        # Se descarta el título propio del documento y se pone el del informe.
        texto = re.sub(r"\A#\s+.*?\n", "", texto)
        print(f"\n# {titulo}\n")
    if nivel:
        # Bajar los encabezados: ## → ###, etc. (solo fuera de bloques de código).
        fuera = True
        salida = []
        for linea in texto.splitlines():
            if linea.lstrip().startswith("```"):
                fuera = not fuera
            if fuera and re.match(r"#{1,5} ", linea):
                linea = "#" + linea
            salida.append(linea)
        texto = "\n".join(salida)
    print(texto)
    print("\n---\n")
PY

echo "ok  $MD ($(wc -l < "$MD") líneas)"

# --- Comprobación obligatoria: la licencia no puede aparecer en la entrega ---
fallas=0
if [[ -f .env ]]; then
  licencia=$(grep -E '^COCKROACH_LICENSE=' .env | cut -d= -f2- | tr -d '"' | tr -d "'" || true)
  if [[ -n ${licencia// } ]] && grep -qF -- "$licencia" "$MD"; then
    echo "ERROR: la licencia de .env aparece en $MD" >&2
    fallas=1
  fi
fi
# Patrón de las licencias de CockroachDB, por si la pegaron en otro archivo del informe.
if grep -nEi 'crl-0-[A-Za-z0-9+/=]{20,}' "$MD"; then
  echo "ERROR: hay algo con forma de licencia en $MD" >&2
  fallas=1
fi
if git ls-files --error-unmatch .env > /dev/null 2>&1; then
  echo "ERROR: .env está versionado en git" >&2
  fallas=1
fi
[[ $fallas -eq 0 ]] && echo "ok  sin licencia en el informe y .env fuera de git"
[[ $fallas -eq 0 ]] || exit 1

# --- PDF (lo mejor que haya en la máquina) ---
if command -v pandoc > /dev/null; then
  pandoc "$MD" -o "$OUT/INFORME.pdf" --toc -V geometry:margin=2.2cm -V fontsize=10pt \
    --pdf-engine=xelatex 2> /dev/null \
    || pandoc "$MD" -o "$OUT/INFORME.pdf" --toc -V geometry:margin=2.2cm
  echo "ok  $OUT/INFORME.pdf (pandoc)"
elif python3 -c 'import markdown_it' 2> /dev/null && command -v libreoffice > /dev/null; then
  python3 p1/informe/render.py "$MD" "$OUT/INFORME.html"
  libreoffice --headless --convert-to pdf --outdir "$OUT" "$OUT/INFORME.html" > /dev/null 2>&1
  echo "ok  $OUT/INFORME.pdf (markdown-it-py + libreoffice)"
else
  echo "AVISO: sin pandoc ni markdown-it-py+libreoffice; exporte $MD a PDF a mano."
fi
