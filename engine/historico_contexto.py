#!/usr/bin/env python3
"""NEXORA · histórico solo-añadir de contexto.json.

Cada contexto.json generado se guarda comprimido en data/historico_contexto/AAAA-MM-DD/HHMM.json.gz (fecha y hora UTC de su
`generado_utc`). Sirve para reconstruir qué decía el sistema en cualquier hora pasada: el Diario de operaciones adjunta a cada
operación la «foto» del contexto más cercano ANTERIOR a su hora de entrada.

No contiene datos personales (es el mismo contenido que ya es público en site/data/contexto.json). Un archivo ya escrito no se
reescribe con otro contenido: si dos ejecuciones caen en el mismo minuto se conserva la primera. Sin IA, sin red.

Además se publica site/data/historico_contexto_indice.json (solo la lista de horas disponibles, ~15 bytes por foto) para que el
navegador sepa qué archivo pedir sin listar el repo; los archivos en sí se leen de raw.githubusercontent.com (no se despliegan en Pages).
"""
from __future__ import annotations

import gzip
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DIR = os.path.join(ROOT, "data", "historico_contexto")
INDICE = os.path.join(ROOT, "site", "data", "historico_contexto_indice.json")
BASE_RAW = "https://raw.githubusercontent.com/komonartisans-ops/nexora-terminal/main/data/historico_contexto/"
RE_STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2}) UTC$")
RE_DIA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RE_HORA = re.compile(r"^(\d{4})\.json\.gz$")


def _ruta(stamp):
    """('2026-10-16 11:20 UTC') -> (dia, 'HHMM', ruta absoluta) o None si el sello no es válido."""
    m = RE_STAMP.match(stamp or "")
    if not m:
        return None
    dia, hh, mm = m.group(1), m.group(2), m.group(3)
    return dia, hh + mm, os.path.join(DIR, dia, hh + mm + ".json.gz")


def comprimir(ctx):
    """gzip determinista (mtime=0): el mismo contexto da siempre los mismos bytes."""
    crudo = json.dumps(ctx, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    return gzip.compress(crudo, compresslevel=9, mtime=0)


def guardar(ctx, sobrescribir=False):
    """Guarda el contexto en su archivo de hora. Devuelve la ruta relativa o None si no se escribió."""
    r = _ruta((ctx or {}).get("generado_utc"))
    if not r:
        return None
    dia, hhmm, ruta = r
    if os.path.exists(ruta) and not sobrescribir:
        return None
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "wb") as f:
        f.write(comprimir(ctx))
    return f"{dia}/{hhmm}.json.gz"


def regenerar_indice():
    """Escribe site/data/historico_contexto_indice.json a partir de lo que hay en disco."""
    dias = {}
    if os.path.isdir(DIR):
        for d in sorted(os.listdir(DIR)):
            p = os.path.join(DIR, d)
            if not (RE_DIA.match(d) and os.path.isdir(p)):
                continue
            horas = sorted(m.group(1) for f in os.listdir(p) if (m := RE_HORA.match(f)))
            if horas:
                dias[d] = horas
    out = {
        "version": 1,
        "nota": "Horas UTC (HHMM) de cada contexto.json guardado. Archivo: base + AAAA-MM-DD/HHMM.json.gz",
        "base": BASE_RAW,
        "total": sum(len(v) for v in dias.values()),
        "primero": (min(dias) + " " + dias[min(dias)][0]) if dias else None,
        "dias": dias,
    }
    os.makedirs(os.path.dirname(INDICE), exist_ok=True)
    with open(INDICE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    return out["total"]


def archivar(ctx):
    """Guarda el contexto y refresca el índice. Nunca lanza: un fallo aquí no debe romper el build."""
    try:
        g = guardar(ctx)
        n = regenerar_indice()
        print(f"histórico de contexto: {'guardado ' + g if g else 'sin cambios'} · {n} fotos")
        return g
    except Exception as e:  # noqa: BLE001
        print("histórico de contexto: fallo (no rompe el build):", repr(e)[:200], file=sys.stderr)
        return None


if __name__ == "__main__":
    # sin argumentos: archiva el site/data/contexto.json actual
    with open(os.path.join(ROOT, "site", "data", "contexto.json"), encoding="utf-8") as f:
        archivar(json.load(f))
