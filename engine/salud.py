#!/usr/bin/env python3
"""NEXORA · SALUD de los workflows: última ejecución de cada uno y cuántas de las esperadas se hicieron hoy (UTC).

Fuente: API de GitHub Actions (token del propio job si existe; si no, sin autenticar). «Esperadas» = el horario del disparo externo
(docs/DISPARO_EXTERNO.md), no el de los crones de GitHub, que son solo respaldo y no están garantizados.
Si `actualizar` lleva más de 2 h sin ejecutarse en horario laborable (06-22 UTC, lun-vie) → aviso por Telegram (una vez por parada).

    python salud.py            (escribe site/data/salud.json, como mucho cada 30 min salvo cambio de estado)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.request
import zoneinfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)
SITE_DATA, DATA = os.path.join(ROOT, "site", "data"), os.path.join(ROOT, "data")
SALIDA, ESTADO = os.path.join(SITE_DATA, "salud.json"), os.path.join(DATA, "estado_salud.json")
REPO = os.environ.get("GITHUB_REPOSITORY", "komonartisans-ops/nexora-terminal")
UTC, MAD = dt.timezone.utc, zoneinfo.ZoneInfo("Europe/Madrid")
UMBRAL_ACTUALIZAR_H = 2.0
MIN_ENTRE_ESCRITURAS = 10  # antes 30: la tarjeta de salud quedaba hasta media hora por detrás de la última ejecución (16-oct: 05:53 con actualizar ya corrido a las 06:07)


def _api(ruta):
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "nexora-salud"}
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    with urllib.request.urlopen(urllib.request.Request(f"https://api.github.com/repos/{REPO}/actions/{ruta}", headers=h), timeout=30) as r:
        return json.loads(r.read().decode())


# horario ESPERADO por workflow (disparo externo): función now_utc → nº de ejecuciones esperadas hasta ese instante hoy
def _esp_actualizar(n):   # cada hora, minuto 07, 06-22 UTC, lun-vie
    return 0 if n.weekday() >= 5 else sum(1 for h in range(6, 23) if dt.time(h, 7) <= n.time())


def _esp_reacciones(n):   # cada 5 min, 12:00-21:00 UTC, lun-vie
    if n.weekday() >= 5:
        return 0
    m = n.hour * 60 + n.minute
    return 0 if m < 12 * 60 else (min(m, 21 * 60) - 12 * 60) // 5 + 1


def _esp_agenda(n):       # 8:00 Madrid, lun-vie
    m = n.astimezone(MAD)
    return 0 if m.weekday() >= 5 else int(m.hour >= 8)


def _esp_vigilar(n):      # 22:15 UTC todos los días (el vigilante sale con OK los fines de semana)
    return int(n.time() >= dt.time(22, 15))


WORKFLOWS = [("actualizar", "actualizar.yml", _esp_actualizar, "cada hora, 06-22 UTC, lun-vie"),
             ("reacciones", "reacciones.yml", _esp_reacciones, "cada 5 min, 12:00-21:00 UTC, lun-vie"),
             ("agenda_diaria", "agenda_diaria.yml", _esp_agenda, "8:00 Madrid, lun-vie"),
             ("vigilar_cierre", "vigilar_cierre.yml", _esp_vigilar, "22:15 UTC, todos los días")]


def medir(ahora=None):
    ahora = ahora or dt.datetime.now(UTC)
    hoy = ahora.date().isoformat()
    out = []
    for nombre, archivo, esp, horario in WORKFLOWS:
        w = {"workflow": nombre, "horario_esperado": horario, "esperadas_hasta_ahora": esp(ahora)}
        try:
            rs, n_hoy, n_fall = [], 0, 0
            for evt in ("schedule", "workflow_dispatch"):  # solo disparos reales (un fallo de validación del YAML llega como «push» y no cuenta)
                base = f"workflows/{archivo}/runs?per_page=1&event={evt}"
                r = (_api(base).get("workflow_runs") or [None])[0]
                if r:
                    rs.append(r)
                n_hoy += _api(f"{base}&created=%3E%3D{hoy}").get("total_count") or 0
                n_fall += _api(f"{base}&created=%3E%3D{hoy}&status=failure").get("total_count") or 0
            w["hoy_ejecutadas"], w["hoy_fallidas"] = n_hoy, n_fall
            if rs:
                r = max(rs, key=lambda x: x["created_at"])
                w["ultima_utc"] = r["created_at"][:16].replace("T", " ")
                w["ultima_evento"], w["ultima_estado"] = r.get("event"), r.get("conclusion") or r.get("status")
                w["horas_desde_ultima"] = round((ahora - dt.datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))).total_seconds() / 3600, 1)
        except Exception as e:  # noqa: BLE001
            w["error"] = f"{type(e).__name__}: {str(e)[:80]}"
        out.append(w)
    return out


def alerta_actualizar(W, ahora):
    """True si `actualizar` lleva > 2 h sin ejecutarse en horario laborable (06-22 UTC, lun-vie)."""
    a = next((w for w in W if w["workflow"] == "actualizar"), {})
    if a.get("horas_desde_ultima") is None or ahora.weekday() >= 5 or not (6 <= ahora.hour < 23):
        return False
    # parada real: han pasado > 2 h y alguna ejecución esperada en ese intervalo no llegó
    return a["horas_desde_ultima"] > UMBRAL_ACTUALIZAR_H


def main():
    ahora = dt.datetime.now(UTC)
    W = medir(ahora)
    try:
        est = json.load(open(ESTADO, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        est = {"avisado_ultima": None}
    caida = alerta_actualizar(W, ahora)
    ult = next((w.get("ultima_utc") for w in W if w["workflow"] == "actualizar"), None)
    avisado = None
    if caida and est.get("avisado_ultima") != ult:
        import telegram
        if telegram.configurado():
            h = next(w["horas_desde_ultima"] for w in W if w["workflow"] == "actualizar")
            ok, err = telegram.enviar(f"<b>NEXORA · Salud</b>\nEl workflow <b>actualizar</b> lleva {h:.1f} h sin ejecutarse (última: {telegram.esc(ult)} UTC). "
                                      "Revisa el disparo externo (cron-job.org) y el token.")
            if ok:
                est["avisado_ultima"] = ult
                avisado = True
            else:
                print("Telegram:", err)
    elif not caida:
        est["avisado_ultima"] = None
    J = {"generado_utc": ahora.strftime("%Y-%m-%d %H:%M UTC"), "workflows": W, "actualizar_parada": bool(caida), "aviso_telegram_enviado": bool(avisado),
         "umbral_actualizar_h": UMBRAL_ACTUALIZAR_H,
         "nota": "Esperadas = horario del disparo externo (cron-job.org); los crones de GitHub son respaldo y no están garantizados. Ejecutadas = ejecuciones creadas hoy (UTC)."}
    try:
        prev = json.load(open(SALIDA, encoding="utf-8"))
        t = dt.datetime.strptime(prev["generado_utc"], "%Y-%m-%d %H:%M UTC").replace(tzinfo=UTC)
        reciente = (ahora - t).total_seconds() < MIN_ENTRE_ESCRITURAS * 60 and prev.get("actualizar_parada") == J["actualizar_parada"]
    except Exception:  # noqa: BLE001
        reciente = False
    if not reciente:
        os.makedirs(SITE_DATA, exist_ok=True)
        json.dump(J, open(SALIDA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.makedirs(DATA, exist_ok=True)
    json.dump(est, open(ESTADO, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for w in W:
        print(w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
