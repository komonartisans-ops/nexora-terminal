#!/usr/bin/env python3
"""NEXORA · vigilante del cierre de 21:30 UTC. Comprueba que TODAS las etapas del modo «cierre» corrieron y terminaron OK en ESE run.

La fuente es data/ejecuciones.csv (una fila por ejecución: etapas_ok y etapas_fallo, con run_id desde el 21-oct-2026), NO site/data/meta.json: meta.json lo sobrescribe la ejecución
horaria siguiente (que solo lleva las etapas del modo horario), y comprobar ahí daba falsos negativos («no hay ejecución de petroleo») aunque el cierre sí las hubiera corrido.

Uso:  python tools/vigilar_cierre.py [--fecha AAAA-MM-DD] [--run-id N] [--csv RUTA | --gh] [--esperar] [--avisar]
  --run-id  filas de ese run_id (el del cierre); sin él, la primera ejecución de la fecha cuyo modo contiene «cierre» y que empieza a las 21:30 UTC o después
  --gh      lee data/ejecuciones.csv del repositorio con `gh api` (sin clonar); --esperar sondea hasta que aparezca el cierre (límite 23:30 UTC)
  --avisar  envía la alerta por Telegram SOLO si hay problema (sin --avisar solo imprime). Nada se escribe en el repositorio.
Código de salida: 0 = todo OK; 1 = alerta."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import os
import subprocess
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "engine"))
REPO = "komonartisans-ops/nexora-terminal"
HORA_CIERRE = "21:30"
LIMITE_UTC = "23:30"


def etapas_cierre():
    """Las etapas que debe llevar el modo de cierre (una sola fuente de verdad: build.MODOS)."""
    import build
    return list(build.MODOS["cierre"])


def _csv(texto):
    return list(csv.DictReader(io.StringIO(texto)))


def leer_local(ruta=None):
    p = ruta or os.path.join(RAIZ, "data", "ejecuciones.csv")
    with open(p, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def leer_gh():
    r = subprocess.run(["gh", "api", f"repos/{REPO}/contents/data/ejecuciones.csv", "-H", "Accept: application/vnd.github.raw"], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError("gh api no pudo leer data/ejecuciones.csv: " + r.stderr[:120])
    return _csv(r.stdout)


def _lista(s):
    return [x for x in (s or "").split(",") if x]


def fila_del_cierre(filas, fecha, run_id=None):
    """La ejecución de cierre de `fecha`: por run_id si se da; si no, la primera de ese día con «cierre» en el modo y capturada a las 21:30 UTC o después. None si no hay."""
    if run_id:
        c = [r for r in filas if str(r.get("run_id") or "") == str(run_id)]
        return c[0] if c else None
    c = [r for r in filas if "cierre" in (r.get("modo") or "") and (r.get("capturado_utc") or "")[:10] == fecha and (r.get("capturado_utc") or "")[11:16] >= HORA_CIERRE]
    c.sort(key=lambda r: r["capturado_utc"])
    return c[0] if c else None


def comprobar(filas, fecha, esperadas=None, run_id=None):
    """Compara las etapas esperadas con las de esa fila: OK si están en etapas_ok; FALLO si están en etapas_fallo; FALTA si no figuran en ninguna."""
    esperadas = esperadas if esperadas is not None else etapas_cierre()
    f = fila_del_cierre(filas, fecha, run_id)
    if f is None:
        return {"ok": False, "fecha": fecha, "run": None, "motivo": "SIN_EJECUCION", "faltan": [], "fallan": [],
                "mensaje": f"NEXORA · cierre {fecha}: no hay ninguna ejecución de cierre registrada{f' con run_id {run_id}' if run_id else ' a partir de las 21:30 UTC'} en data/ejecuciones.csv."}
    ok, fallo = set(_lista(f.get("etapas_ok"))), set(_lista(f.get("etapas_fallo")))
    fallan = [e for e in esperadas if e in fallo]
    faltan = [e for e in esperadas if e not in ok and e not in fallo]
    res = {"ok": not fallan and not faltan, "fecha": fecha, "run": {"run_id": f.get("run_id") or None, "capturado_utc": f["capturado_utc"], "modo": f["modo"], "duracion_s": f.get("duracion_s")},
           "motivo": "OK" if not fallan and not faltan else "ETAPAS", "fallan": fallan, "faltan": faltan, "esperadas": len(esperadas), "ok_n": len([e for e in esperadas if e in ok])}
    res["mensaje"] = (f"NEXORA · cierre {fecha} OK: {res['ok_n']}/{len(esperadas)} etapas en el run {f.get('run_id') or f['capturado_utc']}." if res["ok"] else
                      f"NEXORA · cierre {fecha}: {res['ok_n']}/{len(esperadas)} etapas OK en el run {f.get('run_id') or f['capturado_utc']}."
                      + (f" Con error: {', '.join(fallan)}." if fallan else "") + (f" Sin registrar (no corrieron): {', '.join(faltan)}." if faltan else ""))
    return res


def vigilar(fecha=None, run_id=None, filas=None, enviar_fn=None, avisar=False, esperadas=None):
    """Devuelve el resultado; si hay problema y `avisar`, lo envía por `enviar_fn` (Telegram). Con todo OK no se envía nada."""
    fecha = fecha or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    res = comprobar(filas if filas is not None else leer_local(), fecha, esperadas, run_id)
    res["avisado"] = False
    if not res["ok"] and avisar and enviar_fn:
        ok, err = enviar_fn(res["mensaje"])
        res["avisado"], res["error_aviso"] = bool(ok), err
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fecha")
    ap.add_argument("--run-id")
    ap.add_argument("--csv")
    ap.add_argument("--gh", action="store_true")
    ap.add_argument("--esperar", action="store_true")
    ap.add_argument("--avisar", action="store_true")
    a = ap.parse_args()
    fecha = a.fecha or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    enviar = None
    if a.avisar:
        import telegram
        enviar = telegram.enviar if telegram.configurado() else None
    while True:
        filas = leer_gh() if (a.gh or a.esperar) else leer_local(a.csv)
        res = comprobar(filas, fecha, None, a.run_id)
        if res["motivo"] != "SIN_EJECUCION" or not a.esperar or dt.datetime.now(dt.timezone.utc).strftime("%H:%M") >= LIMITE_UTC:
            break
        time.sleep(240)
    print(res["mensaje"])
    if not res["ok"] and a.avisar and enviar:
        ok, err = enviar(res["mensaje"])
        print("aviso enviado" if ok else f"aviso NO enviado: {err}")
    sys.exit(0 if res["ok"] else 1)


if __name__ == "__main__":
    main()
