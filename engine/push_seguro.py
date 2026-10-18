#!/usr/bin/env python3
"""NEXORA · commit + push de data/ y site/data/ que sobrevive a ejecuciones simultáneas (actualizar y reacciones escriben a la vez).

En un conflicto de rebase: los CSV (solo-añadir) se fusionan por unión de líneas; estado_reacciones.json une sus avisos; el resto de JSON se queda
con la versión del commit que se aplica (la más reciente de esta ejecución)."""
from __future__ import annotations

import json
import subprocess
import sys


def sh(*a, check=False, inp=None):
    return subprocess.run(a, capture_output=True, text=True, check=check, encoding="utf-8")


def resolver(f):
    up = sh("git", "show", f":2:{f}").stdout    # remoto (upstream)
    mine = sh("git", "show", f":3:{f}").stdout  # commit que se aplica
    if f.endswith(".csv"):
        L = up.splitlines()
        vistos = set(L)
        L += [x for x in mine.splitlines() if x not in vistos]
        out = "\n".join(L) + "\n"
    elif f.endswith("vigilante_estado.json"):    # solo-añadir: unión de las claves de ambos lados
        try:
            a, b = json.loads(up), json.loads(mine)
            for k, v in b.get("avisos", {}).items():
                a.setdefault("avisos", {}).setdefault(k, v)
            a["creado_utc"] = a.get("creado_utc") or b.get("creado_utc")
            out = json.dumps(a, ensure_ascii=False, indent=1)
        except Exception:  # noqa: BLE001
            out = mine
    elif f.endswith("avisos_previos.json"):      # solo-añadir: unión de las claves de ambos lados (una clave existente no se modifica)
        try:
            a, b = json.loads(up), json.loads(mine)
            for k, v in b.get("avisos", {}).items():
                a.setdefault("avisos", {}).setdefault(k, v)
            a["creado_utc"] = a.get("creado_utc") or b.get("creado_utc")
            out = json.dumps(a, ensure_ascii=False, indent=1)
        except Exception:  # noqa: BLE001
            out = mine
    elif f.endswith("estado_reacciones.json"):
        try:
            a, b = json.loads(up), json.loads(mine)
            a["avisados"] = sorted(set(a.get("avisados", [])) | set(b.get("avisados", [])))
            out = json.dumps(a, ensure_ascii=False, indent=1)
        except Exception:  # noqa: BLE001
            out = mine
    else:
        out = mine
    open(f, "w", encoding="utf-8", newline="").write(out)
    sh("git", "add", f)


def main(msg):
    sh("git", "config", "user.name", "nexora-bot")
    sh("git", "config", "user.email", "nexora-bot@users.noreply.github.com")
    sh("git", "add", "data", "site/data")
    if sh("git", "diff", "--cached", "--quiet").returncode == 0:
        print("sin cambios")
        return 0
    sh("git", "commit", "-m", msg)
    for i in range(5):
        r = sh("git", "pull", "--rebase", "origin", "main")
        n = 0
        while r.returncode != 0 and n < 10:
            n += 1
            sin = [x for x in sh("git", "diff", "--name-only", "--diff-filter=U").stdout.split("\n") if x]
            if not sin:
                break
            for f in sin:
                resolver(f)
            r = subprocess.run(["git", "-c", "core.editor=true", "rebase", "--continue"], capture_output=True, text=True, encoding="utf-8")
        if r.returncode != 0:
            sh("git", "rebase", "--abort")
            print("rebase fallido:", r.stderr[-300:])
            continue
        p = sh("git", "push", "origin", "HEAD:main")
        if p.returncode == 0:
            print("push ok")
            return 0
        print("push rechazado, reintento", i + 1)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "datos"))
