#!/usr/bin/env python3
"""P1 · Markdown del informe → HTML con estilo de documento, para convertirlo a PDF.

Lo usa p1/informe.sh cuando no hay pandoc. No se llama html.py: ese nombre tapa el módulo html
    de la biblioteca estándar, que markdown_it importa. LibreOffice convierte este HTML a PDF conservando
tablas, monoespaciado y saltos de página entre entregables.
"""

from __future__ import annotations

import html as html_std
import re
import sys
from pathlib import Path

from markdown_it import MarkdownIt

# Ancho útil de una página A4 con los márgenes del CSS, en puntos, y avance de la fuente
# monoespaciada (0,6 em en Liberation Mono). Sirven para que cada bloque de código elija un
# tamaño con el que su línea más larga quepa en una sola línea: los diagramas ASCII de E1
# pierden el sentido si se envuelven.
ANCHO_UTIL_PT = 595.3 - 2 * 56.7 - 16  # A4 − márgenes de 2 cm − padding del <pre>
AVANCE = 0.6
CUERPO_PT = 8.0


def ajustar_bloques(html: str) -> str:
    def reemplazo(m: re.Match) -> str:
        contenido = m.group(2)
        largo = max((len(l) for l in html_std.unescape(contenido).splitlines()), default=0)
        if largo * AVANCE * CUERPO_PT <= ANCHO_UTIL_PT:
            return m.group(0)
        pt = max(4.5, round(ANCHO_UTIL_PT / (largo * AVANCE) * 0.98, 1))
        return f'<pre style="font-size: {pt}pt"{m.group(1)}>{contenido}</pre>'

    return re.sub(r"<pre([^>]*)>(.*?)</pre>", reemplazo, html, flags=re.S)

CSS = """
@page { size: A4; margin: 2cm; }
body { font-family: "Liberation Serif", Georgia, serif; font-size: 10.5pt; line-height: 1.38; color: #111; }
h1 { font-size: 17pt; border-bottom: 2px solid #333; padding-bottom: 4px; page-break-before: always; }
h1:first-of-type { page-break-before: avoid; }
h2 { font-size: 13pt; margin-top: 16px; }
h3 { font-size: 11.5pt; }
h4 { font-size: 10.5pt; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 9pt; }
th, td { border: 1px solid #999; padding: 3px 5px; text-align: left; vertical-align: top; }
th { background: #eee; }
code { font-family: "Liberation Mono", monospace; font-size: 8.8pt; background: #f2f2f2; }
pre { font-family: "Liberation Mono", monospace; font-size: 8pt; background: #f6f6f6;
      border: 1px solid #ddd; padding: 6px; white-space: pre; }
blockquote { border-left: 3px solid #bbb; margin-left: 0; padding-left: 10px; color: #444; }
hr { border: 0; border-top: 1px solid #ccc; }
"""


def main() -> int:
    origen, destino = Path(sys.argv[1]), Path(sys.argv[2])
    md = MarkdownIt("commonmark", {"html": False}).enable("table").enable("strikethrough")
    cuerpo = ajustar_bloques(md.render(origen.read_text(encoding="utf-8")))
    destino.write_text(
        f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>TI-4601 · Proyecto 1</title><style>{CSS}</style></head><body>{cuerpo}</body></html>",
        encoding="utf-8",
    )
    print(f"ok  {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
