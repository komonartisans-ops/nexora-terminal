#!/usr/bin/env python3
"""Reconstruye data/historico_contexto/ con las versiones de site/data/contexto.json que ya existen en el historial de Git.

Son versiones REALES que se publicaron en su día (cada una con su propio `generado_utc`); no se estima ni se interpola nada.
Una versión se guarda en el archivo que le corresponde por su `generado_utc`; si ya existe, no se toca (solo-añadir).
Uso:  python tools/backfill_historico_contexto.py            (desde la raíz del repo)"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import historico_contexto as H  # noqa: E402


def git(*a):
    return subprocess.run(["git", "-C", ROOT, *a], capture_output=True, encoding="utf-8", errors="replace")


def main():
    commits = [c for c in git("log", "--reverse", "--format=%H", "--", "site/data/contexto.json").stdout.split() if c]
    nuevos = invalidos = 0
    for c in commits:
        r = git("show", f"{c}:site/data/contexto.json")
        try:
            ctx = json.loads(r.stdout)
        except ValueError:
            invalidos += 1
            continue
        if H.guardar(ctx):
            nuevos += 1
    total = H.regenerar_indice()
    print(f"{len(commits)} versiones en Git · {nuevos} nuevas en el histórico · {invalidos} ilegibles · {total} fotos en total")


if __name__ == "__main__":
    main()
