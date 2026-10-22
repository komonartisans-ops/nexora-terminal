#!/usr/bin/env python3
"""NEXORA · vigilante del cierre de 21:30 UTC. Comprueba que TODAS las etapas del modo «cierre» corrieron y terminaron OK en ESE run.

La fuente es data/ejecuciones.csv (una fila por ejecución: etapas_ok y etapas_fallo, con run_id desde el 21-oct-2026), NO site/data/meta.json: meta.json lo sobrescribe la ejecución
horaria siguiente (que solo lleva las etapas del modo horario), y comprobar ahí daba falsos negativos («no hay ejecución de petroleo») aunque el cierre sí las hubiera corrido.

Uso:  python tools/vigilar_cierre.py [--fecha AAAA-MM-DD] [--run-id N] [--csv RUTA | --gh] [--esperar] [--avisar] [--sin-registro]
  --run-id  filas de ese run_id (el del cierre); sin él, la primera ejecución de la fecha cuyo modo contiene «cierre» y que empieza a las 21:30 UTC o después
  --gh      lee data/ejecuciones.csv del repositorio con `gh api` (sin clonar); --esperar sondea hasta que aparezca el cierre (límite 23:30 UTC)
  --avisar  envía la alerta por Telegram SOLO si hay problema. Si el propio vigilante no puede comprobar (excepción, sin acceso al CSV) avisa «vigilante sin poder comprobar».
  --sin-registro  no escribe data/vigilar_cierre.csv (el registro de ejecuciones del vigilante, que el vigilante de integridad usa para saber que corre)
Días sin cierre (sábado y domingo, según el cron del cierre en actualizar.yml): sale con OK y sin avisar. Los festivos de la bolsa SÍ ejecutan el cierre (cron lun-vie) y se comprueban.
Código de salida: 0 = OK (o día sin cierre); 1 = alerta de etapas; 2 = el vigilante no pudo comprobar."""
from __future__ import annotations

import argparse
import ast
import csv
import datetime as dt
import io
import os
import re
import subprocess
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "engine"))
REPO = "komonartisans-ops/nexora-terminal"
HORA_CIERRE = "21:30"
LIMITE_UTC = "23:30"
CAMPOS_LOG = ["fecha", "ejecutado_utc", "resultado", "run_id_cierre", "detalle"]


def etapas_cierre():
    """Las etapas que debe llevar el modo de cierre, leídas del literal MODOS de engine/build.py (una sola fuente de verdad; sin importar build, que necesita dependencias)."""
    arbol = ast.parse(open(os.path.join(RAIZ, "engine", "build.py"), encoding="utf-8").read())
    for n in ast.walk(arbol):
        if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "MODOS" for t in n.targets) and isinstance(n.value, ast.Dict):
            for k, v in zip(n.value.keys, n.value.values):
                if isinstance(k, ast.Constant) and k.value == "cierre":
                    return list(ast.literal_eval(v))
    raise RuntimeError("no se encontró MODOS['cierre'] en engine/build.py")


def dias_de_cierre():
    """Días de la semana (0 = lunes) en los que corre el cierre, del cron de 21:30 de actualizar.yml (lun-vie); por defecto lun-vie."""
    try:
        t = open(os.path.join(RAIZ, ".github", "workflows", "actualizar.yml"), encoding="utf-8").read()
        m = re.search(r'cron:\s*"30 21 \* \* ([^"]+)"', t)
        dow = m.group(1).strip() if m else "1-5"
    except OSError:
        dow = "1-5"
    dias = set()
    for p in dow.split(","):
        a, _, b = p.partition("-")
        for d in range(int(a), int(b or a) + 1):
            dias.add((d - 1) % 7)       # cron: 1 = lunes … 7/0 = domingo
    return dias


def toca_cierre(fecha):
    return dt.date.fromisoformat(fecha).weekday() in dias_de_cierre()


def _csv(texto):
    return list(csv.DictReader(io.StringIO(texto)))


def leer_local(ruta=None):
    p = ruta or os.path.join(RAIZ, "data", "ejecuciones.csv")
    with open(p, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def leer_gh():
    r = subprocess.run(["gh", "api", f"repos/{REPO}/contents/data/ejecuciones.csv", "-H", "Accept: application/vnd.github.raw"], capture_output=True, text=True, encoding="utf-8", timeout=120)
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError("gh api no pudo leer data/ejecuciones.csv: " + (r.stderr or "respuesta vacía")[:120])
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


def _validar(filas):
    """Un CSV vacío o sin las columnas esperadas no es «no hay cierre»: es que no se puede comprobar (error del vigilante, no alerta de etapas)."""
    if not filas:
        raise RuntimeError("data/ejecuciones.csv vacío")
    faltan = [c for c in ("capturado_utc", "modo", "etapas_ok", "etapas_fallo") if c not in filas[0]]
    if faltan:
        raise RuntimeError("data/ejecuciones.csv sin las columnas " + ", ".join(faltan))


def _registrar(ruta, fecha, resultado, run, detalle, ahora):
    """Solo añadir: una fila por ejecución del vigilante (la lee el vigilante de integridad para saber que corre)."""
    nuevo = not os.path.exists(ruta) or os.path.getsize(ruta) == 0
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_LOG)
        if nuevo:
            w.writeheader()
        w.writerow({"fecha": fecha, "ejecutado_utc": ahora.strftime("%Y-%m-%d %H:%M UTC"), "resultado": resultado, "run_id_cierre": run or "", "detalle": detalle[:300]})


def _avisar(texto, enviar_fn):
    """Envía por Telegram; devuelve True si salió. Deja una marca (VIGILANTE_AVISADO_FILE) para que el workflow no repita el aviso en su paso de respaldo."""
    if not enviar_fn:
        return False
    ok, err = enviar_fn(texto)
    if ok and os.environ.get("VIGILANTE_AVISADO_FILE"):
        open(os.environ["VIGILANTE_AVISADO_FILE"], "w").write("1")
    if not ok:
        print("aviso NO enviado:", err)
    return bool(ok)


def ejecutar(fecha=None, run_id=None, leer_fn=None, enviar_fn=None, avisar=False, esperadas=None, ahora=None, log=None, espera_fn=None):
    """Una pasada completa. Devuelve (código de salida, resultado). Nunca lanza: cualquier fallo del propio vigilante se convierte en «vigilante sin poder comprobar» (código 2) y se avisa."""
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    fecha = fecha or ahora.strftime("%Y-%m-%d")
    try:
        if not toca_cierre(fecha):
            res = {"ok": True, "fecha": fecha, "run": None, "motivo": "NO_TOCA", "faltan": [], "fallan": [], "avisado": False,
                   "mensaje": f"NEXORA · {fecha} ({['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'][dt.date.fromisoformat(fecha).weekday()]}): hoy no hay cierre; nada que comprobar."}
            if log:
                _registrar(log, fecha, "NO_TOCA", None, res["mensaje"], ahora)
            return 0, res
        while True:
            filas = (leer_fn or leer_local)()
            _validar(filas)
            res = comprobar(filas, fecha, esperadas, run_id)
            if res["motivo"] != "SIN_EJECUCION" or not espera_fn or ahora.strftime("%H:%M") >= LIMITE_UTC:
                break
            ahora = espera_fn()                       # espera y devuelve la hora nueva
        res["avisado"] = False
        if not res["ok"] and avisar:
            res["avisado"] = _avisar(res["mensaje"], enviar_fn)
        if log:
            _registrar(log, fecha, "OK" if res["ok"] else "ALERTA", (res.get("run") or {}).get("run_id"), res["mensaje"], ahora)
        return (0 if res["ok"] else 1), res
    except Exception as e:  # noqa: BLE001  — un fallo silencioso no vale
        msg = f"NEXORA · vigilante sin poder comprobar el cierre {fecha}: {type(e).__name__}: {str(e)[:140]}"
        res = {"ok": False, "fecha": fecha, "run": None, "motivo": "SIN_COMPROBAR", "faltan": [], "fallan": [], "mensaje": msg, "avisado": False}
        if avisar:
            res["avisado"] = _avisar(msg, enviar_fn)
        try:
            if log:
                _registrar(log, fecha, "SIN_COMPROBAR", None, msg, ahora)
        except Exception:  # noqa: BLE001
            pass
        return 2, res


def vigilar(fecha=None, run_id=None, filas=None, enviar_fn=None, avisar=False, esperadas=None):
    """Compatibilidad con las pruebas: comprueba con las filas dadas (o las locales) y avisa solo si hay problema."""
    cod, res = ejecutar(fecha, run_id, (lambda: filas) if filas is not None else None, enviar_fn, avisar, esperadas)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fecha")
    ap.add_argument("--run-id")
    ap.add_argument("--csv")
    ap.add_argument("--gh", action="store_true")
    ap.add_argument("--esperar", action="store_true")
    ap.add_argument("--avisar", action="store_true")
    ap.add_argument("--sin-registro", action="store_true")
    a = ap.parse_args()
    enviar = None
    try:
        import telegram
        enviar = telegram.enviar if telegram.configurado() else None
    except Exception as e:  # noqa: BLE001
        print("telegram no disponible:", type(e).__name__)
    if a.avisar and not enviar:
        print("AVISO: --avisar pero TELEGRAM_TOKEN/TELEGRAM_CHAT_ID no están configurados: una alerta no llegaría")
    leer = leer_gh if (a.gh or a.esperar) else (lambda: leer_local(a.csv))

    def espera():
        time.sleep(240)
        return dt.datetime.now(dt.timezone.utc)
    cod, res = ejecutar(a.fecha, a.run_id, leer, enviar, a.avisar, None, None, None if a.sin_registro else os.path.join(RAIZ, "data", "vigilar_cierre.csv"), espera if a.esperar else None)
    print(res["mensaje"])
    if res.get("avisado"):
        print("aviso enviado por Telegram")
    sys.exit(cod)


if __name__ == "__main__":
    main()
