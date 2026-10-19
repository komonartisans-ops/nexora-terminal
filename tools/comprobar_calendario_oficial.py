#!/usr/bin/env python3
"""Comprueba que el parser de engine/calendario_oficial.py no omite filas de las páginas de calendario de BLS.
Descarga cada página, cuenta las filas de la tabla «release-list» con una expresión INDEPENDIENTE del parser, compara con lo que devuelve el parser y lista
todas las filas con fecha de publicación de octubre a diciembre de 2026. Uso:  python tools/comprobar_calendario_oficial.py"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import calendario_oficial as C  # noqa: E402

fallos = 0
for pagina in C.BLS_PAGINAS:
    h = C._get(f"https://www.bls.gov/schedule/news_release/{pagina}.htm")
    tabla = re.search(r'<table class="release-list".*?</table>', h, re.S)
    crudas = []
    for fila in re.findall(r"<tr[^>]*>(.*?)</tr>", tabla.group(0) if tabla else "", re.S):
        celdas = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", fila, re.S)]
        if len(celdas) >= 3:
            crudas.append(celdas[:3])
    parseadas = C.parsear_bls(h, pagina)
    ok = len(crudas) == len(parseadas)
    fallos += not ok
    print(f"\n== {pagina.upper():7} filas en la página: {len(crudas)} · filas del parser: {len(parseadas)} → {'IGUAL, no omite ninguna' if ok else 'DIFERENTE: el parser omite filas'}")
    for ref, fecha, hora in crudas:
        f = C._fecha_bls(fecha)
        if f and (2026, 10) <= (f.year, f.month) <= (2026, 12):
            print(f"   publicación {f.isoformat()} {hora:8} · periodo de referencia: {ref}")
    meses_ref = [r for r, _, _ in crudas if r.endswith("2026")]
    print("   periodos de referencia de 2026 listados:", ", ".join(r.split()[0] for r in meses_ref) or "ninguno")
sys.exit(1 if fallos else 0)
