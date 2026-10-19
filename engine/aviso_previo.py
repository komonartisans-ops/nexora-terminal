#!/usr/bin/env python3
"""NEXORA · aviso previo por Telegram 30 min antes de cada evento de importancia ALTA de la agenda. Sin IA, sin red salvo el envío a Telegram, gratis.

Cuándo: si un evento ALTA con hora confirmada (site/data/agenda.json) empieza dentro de 25-35 min y no se ha avisado, se envía UN mensaje (máx. 10 líneas).
Quién lo ejecuta: el workflow «reacciones» (antes del monitor y dentro de sus esperas, cada vez que el disparo externo lo arranca) y el run horario de «actualizar».
Si ningún run cayó en la ventana, NO se inventa nada: el evento se registra como «SIN AVISO» en data/avisos_previos.json.

Estado: data/avisos_previos.json es SOLO-AÑADIR (una clave por evento; nunca se modifica una clave existente). El modo seco (--seco) imprime el mensaje y no envía ni escribe.
No cambia reglas v3 ni umbrales: solo LEE agenda.json, fedwatch.json, contexto.json, reacciones_eventos.csv y reacciones.json.
El token de Telegram solo viene del entorno (telegram.py); aquí no se lee ni se imprime.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import statistics
import subprocess
import sys
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(HERE)
sys.path.insert(0, HERE)

NY, MAD, UTC = ZoneInfo("America/New_York"), ZoneInfo("Europe/Madrid"), dt.timezone.utc
VENTANA_MIN = (25, 35)          # el aviso sale si faltan entre 25 y 35 minutos
CONTAMINACION_MIN = 120         # otro ALTA a ±2 h contamina las fases (regla v3: T+120 es la última fase intradía)
MIN_N_HISTORIAL = 5
MAX_LINEAS = 10
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
TIPOS = [("FOMC", "FOMC"), ("Actas", "ACTAS"), ("Discurso", "DISCURSO"), ("IPC", "IPC"), ("PCE", "PCE"), ("Empleo", "NFP"), ("NFP", "NFP"), ("PPI", "PPI"),
         ("Ventas minoristas", "VENTAS"), ("ISM", "ISM"), ("PIB", "PIB")]
# Resultados de empresas: la agenda no trae hora. Si la fuente (Nasdaq/Zacks, vía calendario.json) dice «antes de la apertura» o «después del cierre» y la FECHA está
# confirmada, se usa una hora TÍPICA (marcada en el aviso como no confirmada). Sin indicación de momento, o con fecha estimada, no se avisa.
HORA_TIPICA = {"antes de la apertura": "08:00", "después del cierre": "16:05"}
TIPOS_FED = {"FOMC", "ACTAS", "DISCURSO"}    # para estos se muestra FedWatch; para el resto, consenso (solo si una fuente oficial lo trae)


def P(raiz, *a):
    return os.path.join(raiz, *a)


def leer_json(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def leer_csv(ruta):
    if not os.path.exists(ruta):
        return []
    with open(ruta, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def es(v, d=1):
    """Número con coma decimal (como el resto del terminal); SIN DATO si falta."""
    try:
        return f"{float(v):.{d}f}".replace(".", ",")
    except (TypeError, ValueError):
        return "SIN DATO"


def pc(v):
    return "SIN DATO" if v is None else es(v, 0) + " %"


def fdate(iso):
    return f"{iso[8:10]}-{iso[5:7]}-{iso[:4]}" if iso and len(iso) >= 10 else "SIN DATO"


def tipo_de(nombre):
    for k, t in TIPOS:
        if k.lower() in nombre.lower():
            return t
    return None


# ---------------------------------------------------------------- eventos de la agenda
def eventos_alta(raiz):
    """Eventos ALTA con hora de Nueva York confirmada: [{key, evento, tipo, t (UTC), fecha_et, hora_ny}]. Sin hora no se puede avisar y no se inventa."""
    A = (leer_json(P(raiz, "site", "data", "agenda.json")) or {}).get("agenda") or {}
    out, vistos = [], set()
    for e in (A.get("hoy") or []) + (A.get("proximos_7_dias") or []):
        if e.get("importancia") != "ALTA" or not e.get("hora_ny"):
            continue
        fecha = e.get("fecha_et") or e.get("fecha")
        key = f"{fecha}|{e['hora_ny']}|{e['evento']}"
        if key in vistos:
            continue
        vistos.add(key)
        h, m = map(int, e["hora_ny"].split(":"))
        t = dt.datetime.combine(dt.date.fromisoformat(fecha), dt.time(h, m), NY).astimezone(UTC)
        out.append({"key": key, "evento": e["evento"], "tipo": tipo_de(e["evento"]), "t": t, "fecha_et": fecha, "hora_ny": e["hora_ny"], "nota": e.get("nota"), "consenso": e.get("consenso")})
    # resultados de empresas ALTA sin hora en la agenda: hora típica según el momento que publica la fuente
    C = leer_json(P(raiz, "site", "data", "calendario.json")) or {}
    for e in C.get("eventos") or []:
        if e.get("importancia") != "ALTA" or not str(e.get("evento", "")).startswith("Resultados") or e.get("hora_ny"):
            continue
        momento = next((m for m in HORA_TIPICA if m in str(e.get("que_mirar", ""))), None)
        if not momento or "CONFIRMADA" not in str(e.get("nota", "")).upper() or "NO CONFIRMADA" in str(e.get("nota", "")).upper():
            continue
        hora = HORA_TIPICA[momento]
        key = f"{e['fecha']}|{hora}|{e['evento']}"
        if key in vistos:
            continue
        vistos.add(key)
        h, m = map(int, hora.split(":"))
        t = dt.datetime.combine(dt.date.fromisoformat(e["fecha"]), dt.time(h, m), NY).astimezone(UTC)
        out.append({"key": key, "evento": e["evento"], "tipo": "RESULTADOS", "t": t, "fecha_et": e["fecha"], "hora_ny": hora, "nota": e.get("nota"), "consenso": None,
                    "hora_tipica": momento, "fuente_hora": e.get("fuente") or "Nasdaq / Zacks", "que_mirar": e.get("que_mirar")})
    return sorted(out, key=lambda x: x["t"])


# ---------------------------------------------------------------- contenido
def contaminacion(ev, todos):
    cerca = []
    for o in todos:
        if o["key"] == ev["key"]:
            continue
        d = (o["t"] - ev["t"]).total_seconds() / 60
        if abs(d) <= CONTAMINACION_MIN:
            cerca.append((d, o))
    if not cerca:
        return f"Sin otro dato de importancia alta a ±{CONTAMINACION_MIN // 60} h: las fases no quedan contaminadas por la agenda."
    txt = "; ".join(f"{o['evento']} ({o['t'].astimezone(MAD).strftime('%H:%M')} Madrid, {'+' if d >= 0 else '−'}{abs(d):.0f} min)" for d, o in sorted(cerca, key=lambda x: x[0]))
    return f"Coincide con otro dato de importancia alta: {txt}. Las fases entre ambos se marcan contaminadas (regla v3)."


def linea_mercado(ev, raiz):
    """Qué descuenta el mercado. Fed: FedWatch de fedwatch.json. Resto: consenso solo si la agenda o una fuente oficial lo trae; si no, SIN DATO."""
    if ev["tipo"] in TIPOS_FED:
        F = leer_json(P(raiz, "site", "data", "fedwatch.json")) or {}
        R = F.get("reuniones") or []
        if not R:
            return ["Mercado: FedWatch SIN DATO (fedwatch.json no disponible)."]
        r = next((x for x in R if x.get("reunion") == ev["fecha_et"]), R[0])
        pr = r.get("prob_reunion") or {}
        dic = next((x for x in R if str(x.get("reunion", ""))[5:7] == "12"), None)
        fp = F.get("fecha_precios")
        l = [f"FedWatch (reunión {fdate(r['reunion'])}): subida {pc(pr.get('subida'))} · mantener {pc(pr.get('mantiene'))} · bajada {pc(pr.get('bajada'))} "
             f"[FedWatch NEXORA, futuros ZQ, precios del {fdate(fp)}]."]
        if dic and dic.get("tipo_esperado") is not None:
            l.append(f"Tipo esperado en diciembre ({fdate(dic['reunion'])}): {es(dic['tipo_esperado'], 2)} % frente al {es(F.get('effr'), 2)} % actual.")
        return l
    if ev["tipo"] == "RESULTADOS":
        bpa = str(ev.get("que_mirar") or "").split("·")[0].strip()
        return [f"Consenso: {bpa} [{ev.get('fuente_hora')}]." if "BPA" in bpa else "Consenso: SIN DATO (la fuente no publica BPA estimado)."]
    cons = None
    for k in ("consenso", "prevision", "previsión"):
        if ev.get(k):
            cons = ev[k]
    return [f"Consenso: {cons}." if cons else "Consenso: SIN DATO (ninguna fuente oficial gratuita lo publica; la agenda no lo trae)."]


def linea_contexto(raiz):
    C = leer_json(P(raiz, "site", "data", "contexto.json"))
    if not C:
        return ["Contexto: SIN DATO (contexto.json no disponible)."]
    g = (C.get("generado_utc") or "SIN DATO").replace(" UTC", "")
    hora = (f"{g[8:10]}-{g[5:7]} {g[11:16]}" if len(g) >= 16 else g) + " UTC"
    R = C.get("regimen_macro") or {}
    tes = {t.get("activo"): t.get("etiqueta") for t in ((C.get("tesis") or {}).get("tesis_por_activo") or [])}
    corto = {"Oro": "Oro", "Nasdaq 100": "NQ", "S&P 500": "ES", "Bitcoin": "BTC"}
    gam = ((C.get("gamma_indices") or {}).get("indices")) or {}
    gtxt = " · ".join(f"{k} {str(gam[k].get('regimen_gamma', 'SIN DATO')).lower()}" for k in ("NQ", "ES") if k in gam) or "SIN DATO"
    ses = {gam[k].get("sesion") for k in ("NQ", "ES") if k in gam and gam[k].get("sesion")}
    if ses:
        gtxt += f" (sesión del {', '.join(fdate(x) for x in sorted(ses))})"
    return [f"Régimen: {R.get('cuadrante', 'SIN DATO')} (riesgo {R.get('riesgo', 'SIN DATO')}) · liquidez {(C.get('liquidez') or {}).get('lectura', 'SIN DATO')}.",
            "Tesis: " + " · ".join(f"{v} {tes.get(k, 'SIN DATO')}" for k, v in corto.items()) + f" · gamma {gtxt} [contexto.json de {hora}]."]


def historial(ev, raiz):
    """n, mediana del 2Y a T+5 y T+60 y % de SE CONFIRMA vs INVERSIÓN para ese tipo de evento. Con n < 5: «historial insuficiente»."""
    tipo = ev["tipo"]
    if tipo == "RESULTADOS":
        return "Historia: el monitor de reacción mide datos macro y la Fed, no resultados de empresas (SIN DATO)."
    if not tipo:
        return "Historia: tipo de evento no reconocido (SIN DATO)."
    filas = [r for r in leer_csv(P(raiz, "data", "reacciones_eventos.csv")) if r.get("origen") != "anulación" and tipo in (r.get("tipo") or "").split("+")]
    por = {}
    for r in filas:
        por.setdefault(r["evento_id"], {})[r["fase"]] = r
    def v(r, f):
        try:
            return float(por[r][f]["d_y2_pb"])
        except (KeyError, ValueError, TypeError):
            return None
    t5 = [x for x in (v(i, "T+5") for i in por) if x is not None]
    t60 = [x for x in (v(i, "T+60") for i in por) if x is not None]
    n = len(t5)
    if n < MIN_N_HISTORIAL:
        return f"Historia ({tipo}): historial insuficiente (n={n})."
    J = leer_json(P(raiz, "site", "data", "reacciones.json")) or {}
    clases = []
    for e in J.get("eventos") or []:
        if tipo in str(e.get("tipo", "")).split("+"):
            gf = e.get("giro_fases") or {}
            c = next((gf[f] for f in ("T+1", "CIERRE", "T+120", "T+60") if gf.get(f)), None)
            if c:
                clases.append(c)
    k = len(clases)
    conf = sum(c == "SE CONFIRMA" for c in clases)
    inv = sum(str(c).startswith("INVERSIÓN") for c in clases)
    tail = f" · SE CONFIRMA {conf / k * 100:.0f} % vs INVERSIÓN {inv / k * 100:.0f} % (n={k} con clase)" if k else " · SE CONFIRMA vs INVERSIÓN SIN DATO"
    med = lambda L: f"{statistics.median(L):+.1f}".replace(".", ",") + f" pb (n={len(L)})" if L else "SIN DATO"  # noqa: E731
    return f"Historia ({tipo}, n={n}): mediana del 2Y a T+5 {med(t5)}, a T+60 {med(t60)}{tail} [reacciones_eventos.csv]."


def mensaje(ev, minutos, todos, raiz=RAIZ):
    """Texto en HTML de Telegram (solo <b>), máximo 10 líneas, sin recomendaciones ni niveles de precio."""
    from telegram import esc
    h_mad, h_ny = ev["t"].astimezone(MAD), ev["t"].astimezone(NY)
    hora = f"Empieza en {minutos:.0f} min: {h_mad.strftime('%H:%M')} Madrid · {h_ny.strftime('%H:%M')} ET ({DIAS[h_ny.weekday()]} {h_ny.strftime('%d-%m-%Y')})."
    if ev.get("hora_tipica"):
        hora = (f"Hora típica, no confirmada ({ev['hora_tipica']} → {h_ny.strftime('%H:%M')} ET; la empresa no ha publicado la hora): {h_mad.strftime('%H:%M')} Madrid · "
                f"{h_ny.strftime('%H:%M')} ET ({DIAS[h_ny.weekday()]} {h_ny.strftime('%d-%m-%Y')}), en {minutos:.0f} min. Fuente del momento: {ev.get('fuente_hora')}.")
    L = [f"<b>Aviso previo · {esc(ev['evento'])}</b>", hora]
    if str(ev.get("nota") or "").startswith("manual"):
        L.append(f"Evento MANUAL ({ev['nota']}): no viene del calendario oficial; comprueba la fuente en la Agenda.")
    L.append(contaminacion(ev, todos))
    L += linea_mercado(ev, raiz)
    L += linea_contexto(raiz)
    L.append(historial(ev, raiz))
    L.append("Hecho y fuente en cada cifra; lectura de contexto, no una recomendación de compra o venta.")
    L = L[:MAX_LINEAS]
    return "\n".join(esc_linea(x) for x in L)


def esc_linea(x):
    """Escapa el texto menos las etiquetas <b> propias."""
    from telegram import esc
    if x.startswith("<b>") and x.count("</b>") == 1:
        i, j = x.index("<b>") + 3, x.index("</b>")
        return "<b>" + esc(x[i:j]) + "</b>" + esc(x[j + 4:])
    return esc(x)


# ---------------------------------------------------------------- estado solo-añadir
def leer_estado(raiz):
    return leer_json(P(raiz, "data", "avisos_previos.json")) or {"creado_utc": None, "avisos": {}}


def guardar_estado(raiz, est, nuevos):
    """Solo-añadir: relee el archivo y añade las claves nuevas; una clave existente nunca se modifica."""
    actual = leer_estado(raiz)
    if not actual.get("creado_utc"):
        actual["creado_utc"] = est.get("creado_utc")
    for k, v in nuevos.items():
        actual["avisos"].setdefault(k, v)
    os.makedirs(P(raiz, "data"), exist_ok=True)
    with open(P(raiz, "data", "avisos_previos.json"), "w", encoding="utf-8") as f:
        json.dump(actual, f, ensure_ascii=False, indent=1)


def _push(msg):
    """En Actions: commit inmediato del estado (otro job concurrente verá el aviso y no lo repetirá). Fuera de Actions no hace nada."""
    if not os.environ.get("GITHUB_ACTIONS"):
        return
    try:
        subprocess.run([sys.executable, os.path.join(HERE, "push_seguro.py"), msg], check=False, timeout=180)
    except Exception as e:  # noqa: BLE001
        print("aviso previo: no se pudo hacer push del estado:", type(e).__name__)


def ejecutar(ahora=None, seco=False, raiz=RAIZ, push=False, enviar=None):
    """Una pasada. Devuelve la lista de resultados [(clave, estado, texto)]. seco=True: imprime y no envía ni escribe nada."""
    ahora = ahora or dt.datetime.now(UTC)
    est = leer_estado(raiz)
    if not est.get("creado_utc"):
        est["creado_utc"] = ahora.strftime("%Y-%m-%d %H:%M UTC")     # los eventos cuya ventana ya había pasado no se marcan «sin aviso»: son anteriores a la función
        if not seco:
            guardar_estado(raiz, est, {})
    creado = dt.datetime.strptime(est["creado_utc"], "%Y-%m-%d %H:%M UTC").replace(tzinfo=UTC)
    evs = eventos_alta(raiz)
    out, nuevos = [], {}
    for ev in evs:
        if ev["key"] in est["avisos"]:
            continue
        minutos = (ev["t"] - ahora).total_seconds() / 60
        if VENTANA_MIN[0] <= minutos <= VENTANA_MIN[1]:
            texto = mensaje(ev, minutos, evs, raiz)
            if seco:
                print("[seco · no se envía]\n" + texto + "\n")
                out.append((ev["key"], "SECO", texto))
                continue
            import telegram
            ok, err = (enviar or telegram.enviar)(texto)
            if ok:
                nuevos[ev["key"]] = {"estado": "ENVIADO", "enviado_utc": ahora.strftime("%Y-%m-%d %H:%M UTC"), "evento": ev["evento"], "minutos_antes": round(minutos, 1),
                                     "empieza_utc": ev["t"].strftime("%Y-%m-%d %H:%M UTC")}
                out.append((ev["key"], "ENVIADO", texto))
            else:
                print("aviso previo: Telegram no aceptó el mensaje (se reintenta en la siguiente pasada):", err)
                out.append((ev["key"], "ERROR", err or ""))
        elif minutos < VENTANA_MIN[0] and ev["t"] - dt.timedelta(minutes=VENTANA_MIN[0]) >= creado:
            # la ventana ya pasó y ningún run cayó dentro: se registra, no se inventa un aviso tardío
            if not seco:
                nuevos[ev["key"]] = {"estado": "SIN AVISO", "registrado_utc": ahora.strftime("%Y-%m-%d %H:%M UTC"), "evento": ev["evento"],
                                     "empieza_utc": ev["t"].strftime("%Y-%m-%d %H:%M UTC"),
                                     "motivo": f"ningún run cayó en la ventana de {VENTANA_MIN[0]}-{VENTANA_MIN[1]} min antes (primera pasada posterior: {minutos:.0f} min antes del evento)"}
            out.append((ev["key"], "SIN AVISO", ""))
    if nuevos and not seco:
        guardar_estado(raiz, est, nuevos)
        if push:
            _push("aviso previo " + ahora.strftime("%Y-%m-%d %H:%M") + " UTC [skip ci]")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seco", action="store_true", help="imprime el mensaje; no envía ni escribe estado")
    ap.add_argument("--push", action="store_true", help="en Actions, commit inmediato del estado")
    ap.add_argument("--ahora", help="instante simulado 'AAAA-MM-DD HH:MM' en UTC (pruebas)")
    ap.add_argument("--raiz", default=RAIZ)
    a = ap.parse_args()
    ahora = dt.datetime.strptime(a.ahora, "%Y-%m-%d %H:%M").replace(tzinfo=UTC) if a.ahora else None
    r = ejecutar(ahora, a.seco, a.raiz, a.push)
    print("pasada:", [(k, e) for k, e, _ in r] or "nada que avisar")
    return 0


if __name__ == "__main__":
    sys.exit(main())
