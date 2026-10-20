#!/usr/bin/env python3
"""NEXORA · tres usos del ratio de consumo (#/consumo). Sin IA, gratis, SIN DATO si falta algo. NO toca las 9 reglas ni los umbrales de la tesis de consumo (consumo.py).
Escribe site/data/consumo_ratio.json. Solo describe: no hay recomendaciones de acciones ni de compra o venta.

1) FILTRO SMA 200 de XLY/XLP y de RSPD/RSPS, en diario (200 sesiones) y semanal (200 cierres semanales).
   Estado = cierre del ratio frente a su SMA 200. CRUCE VÁLIDO solo tras 5 cierres consecutivos al otro lado del lado vigente (el lado vigente cambia en ese 5.º cierre); un cierre
   de vuelta antes reinicia la cuenta. Contador de cruces válidos en 12 meses: si ≥ 4 → «filtro poco fiable ahora (mercado lateral)». Semanal = último cierre de cada semana COMPLETA.
2) ROTACIÓN: rendimiento relativo frente a SPY (puntos porcentuales) a 1 mes (21 sesiones) y 3 meses (63) de XLY, XLP, XLK, XLE, XLU, XLV, XLF y XLI, ordenado. Solo describe.
3) DIVERGENCIA: SPY marca máximo de cierre de 63 sesiones Y RSPD/RSPS está más de un 3 % por debajo de su propio máximo de 63 sesiones.
   Confirmaciones: (a) AMPLITUD a la baja en 1 mes: RSP frente a SPY a 20 sesiones ≤ −1 pp (la misma medida y el mismo umbral de indices.py; NEXORA no calcula el % de valores del S&P sobre su
   SMA 200, así que se usa la amplitud que ya existe); (b) CRÉDITO ampliándose: algún diferencial ICE BofA (IG, BBB, HY, CCC) supera su umbral de ciclo.py (5 días o 1 mes).
   FUERTE = las dos; MEDIA = una; DÉBIL = ninguna. Si falta el dato de una confirmación (el crédito de FRED solo cubre 3 años) la fuerza se marca «parcial» y FUERTE es imposible.
   Una nueva divergencia solo cuenta si hace ≥ 10 sesiones que no había ninguna. Telegram solo al APARECER una FUERTE (la de hoy es FUERTE y la sesión anterior no lo era), máx. 1 por semana.
4) MARCADOR: tipos «cruce_sma200_ratio» (SPY ALCISTA/BAJISTA según el sentido del cruce) y «divergencia_ratio» (SPY BAJISTA), medidos a T+20 y T+60 sobre SPY frente a la tasa base.
   `--backfill` reconstruye los desde 2010 con los datos disponibles (origen=backfill)."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(HERE)
sys.path.insert(0, HERE)
UTC = dt.timezone.utc

RATIOS = {"cap": ("XLY", "XLP", "XLY/XLP"), "igual": ("RSPD", "RSPS", "RSPD/RSPS")}
SECTORES = ["XLY", "XLP", "XLK", "XLE", "XLU", "XLV", "XLF", "XLI"]
CIERRES_CRUCE = 5
SMA_N = 200
UMBRAL_CRUCES_12M = 4
NOTA_LATERAL = "filtro poco fiable ahora (mercado lateral)"
VENTANA_MAX = 63
UMBRAL_DIVERGENCIA_PCT = 3.0
AMPLITUD_SESIONES = 20
AMPLITUD_PP = 1.0                      # indices.py: UMBRAL «amplitud_rsp_pp_20d» (±1 pp)
ENFRIAMIENTO = 10                      # sesiones sin divergencia para contar una nueva
DESDE_BACKFILL = "2010-01-01"
OAS = {"ig": "BAMLC0A0CM", "bbb": "BAMLC0A4CBBB", "hy": "BAMLH0A0HYM2", "ccc": "BAMLH0A3HYC"}
UMB_CRED = {"ig": (10, 25), "bbb": (12, 30), "hy": (25, 75), "ccc": (60, 150)}   # ciclo.py (5 días, 1 mes) en pb · CRITERIO NEXORA (se importa de ciclo.py si está disponible)
HORIZONTES = (20, 60)
MAX_TELEGRAM_DIAS = 7


def P(raiz, *a):
    return os.path.join(raiz, *a)


# ---------------------------------------------------------------- series
def ratio(a, b):
    db = dict(b)
    return [(d, v / db[d]) for d, v in a if d in db and db[d]]


def semanal(pts):
    """Último cierre de cada semana ISO COMPLETA: la semana en curso solo entra si el último dato es de viernes."""
    sem = {}
    for d, v in pts:
        sem[d.isocalendar()[:2]] = (d, v)
    out = [sem[k] for k in sorted(sem)]
    if out and pts[-1][0].weekday() < 4 and out[-1][0] == pts[-1][0]:
        out = out[:-1]
    return out


def lado_vs(v, sma, vigente):
    return 1 if v > sma else -1 if v < sma else vigente


def filtro_sma(pts, confirmar=CIERRES_CRUCE, n=SMA_N):
    """Máquina de estados causal. pts = [(fecha, valor)]. → dict con el estado de hoy y todos los cruces válidos [(fecha, +1/−1)]; None si hay menos de n+1 puntos."""
    if len(pts) <= n:
        return None
    v = [x[1] for x in pts]
    ventana = sum(v[:n])
    vigente = 1 if v[n - 1] > ventana / n else -1 if v[n - 1] < ventana / n else 1
    cont, cruces = 0, []
    for i in range(n, len(v)):
        ventana += v[i] - v[i - n]
        l = lado_vs(v[i], ventana / n, vigente)
        if l != vigente:
            cont += 1
            if cont >= confirmar:
                vigente, cont = l, 0
                cruces.append((pts[i][0], l))
        else:
            cont = 0
    sma = ventana / n
    l_hoy = lado_vs(v[-1], sma, vigente)
    ult = pts[-1][0]
    c12 = [c for c in cruces if (ult - c[0]).days <= 365]
    return {"fecha": ult.isoformat(), "valor": round(v[-1], 5), "sma200": round(sma, 5), "dist_pct": round((v[-1] / sma - 1) * 100, 2), "lado_actual": l_hoy, "vigente": vigente,
            "pendiente": cont if (l_hoy != vigente and cont > 0) else 0, "cruces_12m": len(c12), "poco_fiable": len(c12) >= UMBRAL_CRUCES_12M,
            "ultimo_cruce": ({"fecha": cruces[-1][0].isoformat(), "sentido": "AL ALZA" if cruces[-1][1] > 0 else "A LA BAJA"} if cruces else None),
            "cruces_12m_fechas": [{"fecha": c[0].isoformat(), "sentido": "AL ALZA" if c[1] > 0 else "A LA BAJA"} for c in c12], "_cruces": cruces}


def filtros(ratios_d):
    """{'cap'|'igual': {'diario': …, 'semanal': …}} con los textos de estado."""
    out = {}
    for k, pts in ratios_d.items():
        out[k] = {}
        for tf, serie in (("diario", pts), ("semanal", semanal(pts))):
            f = filtro_sma(serie)
            if f is None:
                out[k][tf] = {"estado": "SIN DATO", "motivo": f"menos de {SMA_N + 1} {'sesiones' if tf == 'diario' else 'semanas'} de historia"}
                continue
            f["estado"] = "SOBRE SU SMA 200" if f["lado_actual"] > 0 else "BAJO SU SMA 200" if f["lado_actual"] < 0 else "EN SU SMA 200"
            f["vigente_texto"] = "AL ALZA" if f["vigente"] > 0 else "A LA BAJA"
            f["nota"] = NOTA_LATERAL if f["poco_fiable"] else None
            f["unidad_cierre"] = "sesiones" if tf == "diario" else "semanas"
            out[k][tf] = f
    return out


# ---------------------------------------------------------------- rotación
def rotacion(series, n1=21, n3=63):
    """Rendimiento (%) y rendimiento relativo frente a SPY (pp) a 1 y 3 meses de los ocho sectores, ordenado por el de 3 meses (con el puesto a 1 mes)."""
    spy = series.get("SPY") or []
    if len(spy) <= n3:
        return {"estado": "SIN DATO", "filas": []}

    def ret(s, n):
        return (s[-1][1] / s[-1 - n][1] - 1) * 100 if len(s) > n else None
    r = {"1m": ret(spy, n1), "3m": ret(spy, n3)}
    filas = []
    for t in SECTORES:
        s = series.get(t) or []
        a1, a3 = ret(s, n1), ret(s, n3)
        filas.append({"etf": t, "ret_1m": None if a1 is None else round(a1, 2), "ret_3m": None if a3 is None else round(a3, 2),
                      "rel_1m": None if a1 is None else round(a1 - r["1m"], 2), "rel_3m": None if a3 is None else round(a3 - r["3m"], 2), "fecha": s[-1][0].isoformat() if s else None})
    con = sorted([f for f in filas if f["rel_3m"] is not None and f["rel_1m"] is not None], key=lambda f: f["rel_3m"], reverse=True)
    r1 = sorted(con, key=lambda f: f["rel_1m"], reverse=True)
    for i, f in enumerate(con, 1):
        f["puesto_3m"] = i
        f["puesto_1m"] = r1.index(f) + 1
    sin = [f for f in filas if f not in con]
    return {"estado": "OK", "spy": {"ret_1m": round(r["1m"], 2), "ret_3m": round(r["3m"], 2), "fecha": spy[-1][0].isoformat()}, "filas": con + sin,
            "nota": "Rendimiento relativo = rendimiento del ETF menos el de SPY, en puntos porcentuales (21 sesiones = 1 mes; 63 = 3 meses). Solo describe lo que ha pasado; no recomienda ninguna acción ni sector."}


# ---------------------------------------------------------------- crédito (ciclo.py)
def credito_ampliandose(oas, d):
    """¿Algún diferencial supera su umbral de ciclo.py (5 días o 1 mes, en pb) a fecha d? oas = {tier: [(fecha, %)]}. (True/False, detalle) o (None, None) sin historia suficiente."""
    det, hay = [], False
    for k, s in oas.items():
        pts = [(x, v * 100) for x, v in s if x <= d]
        if len(pts) < 20 or (d - pts[0][0]).days < 31:
            continue
        hay = True
        ult = pts[-1]

        def cambio(dias):
            prev = [v for x, v in pts if x <= ult[0] - dt.timedelta(days=dias)]
            return ult[1] - prev[-1] if prev else None
        c5, c1 = cambio(7), cambio(30)
        u5, u1 = UMB_CRED[k]
        if c5 is not None and c5 >= u5:
            det.append(f"{k.upper()} +{round(c5)} pb en 5 días")
        elif c1 is not None and c1 >= u1:
            det.append(f"{k.upper()} +{round(c1)} pb en 1 mes")
    if not hay:
        return None, None
    return bool(det), det


# ---------------------------------------------------------------- divergencia
def divergencia_en(i, spy, rd, rsp, oas):
    """Estado de la divergencia en el índice i de la rejilla común. Funciones causales (solo miran el pasado)."""
    if i < VENTANA_MAX - 1:
        return None
    d = spy[i][0]
    ventana_s = [x[1] for x in spy[i - VENTANA_MAX + 1:i + 1]]
    ventana_r = [x[1] for x in rd[i - VENTANA_MAX + 1:i + 1]]
    spy_max = spy[i][1] >= max(ventana_s)
    desv = round((rd[i][1] / max(ventana_r) - 1) * 100, 6)                  # redondeo: los umbrales exactos no dependen del error de coma flotante
    activa = spy_max and desv < -UMBRAL_DIVERGENCIA_PCT
    amp = None
    if i >= AMPLITUD_SESIONES and rsp:
        amp = round(((rsp[i][1] / rsp[i - AMPLITUD_SESIONES][1]) - (spy[i][1] / spy[i - AMPLITUD_SESIONES][1])) * 100, 6)
    amp_ok = None if amp is None else amp <= -AMPLITUD_PP
    cred, det = credito_ampliandose(oas, d) if oas else (None, None)
    conf = [x for x in (amp_ok, cred) if x]
    parcial = amp_ok is None or cred is None
    fuerza = ("FUERTE" if (amp_ok and cred) else "MEDIA" if len(conf) == 1 else "DÉBIL") if activa else None
    return {"fecha": d.isoformat(), "activa": activa, "spy_max_63": spy_max, "ratio_vs_max63_pct": round(desv, 2), "amplitud_pp": None if amp is None else round(amp, 2), "amplitud_a_la_baja": amp_ok,
            "credito_ampliandose": cred, "credito_detalle": det, "fuerza": fuerza, "parcial": bool(activa and parcial)}


def alinear(series, claves):
    """Rejilla común de fechas: devuelve {clave: [(fecha, valor)]} con las mismas fechas para todas (las que tienen cierre en todas)."""
    comunes = None
    for c in claves:
        f = {d for d, _ in series.get(c, [])}
        comunes = f if comunes is None else comunes & f
    fechas = sorted(comunes or [])
    return {c: [(d, dict(series[c])[d]) for d in fechas] for c in claves}


def historia_divergencia(series, oas):
    """[(estado)] diario de la divergencia sobre la rejilla común SPY, RSPD/RSPS y RSP."""
    rd = ratio(series["RSPD"], series["RSPS"])
    g = alinear({"SPY": series["SPY"], "RSPD/RSPS": rd, "RSP": series.get("RSP", [])}, ["SPY", "RSPD/RSPS"] + (["RSP"] if series.get("RSP") else []))
    spy, r, rsp = g["SPY"], g["RSPD/RSPS"], g.get("RSP")
    out = []
    for i in range(len(spy)):
        e = divergencia_en(i, spy, r, rsp, oas)
        if e:
            out.append(e)
    return out


def inicios_divergencia(hist):
    """Fechas de INICIO de divergencia (con ≥ ENFRIAMIENTO sesiones sin ninguna), con su fuerza en ese día."""
    out, ultima = [], -10 ** 9
    for i, e in enumerate(hist):
        if e["activa"]:
            if i - ultima > ENFRIAMIENTO:
                out.append(e)
            ultima = i
    return out


def aparece_fuerte(hist):
    """¿La sesión de hoy es FUERTE y la anterior no lo era? (aparición de una divergencia FUERTE)."""
    if not hist:
        return False
    hoy = hist[-1]
    prev = hist[-2] if len(hist) > 1 else {}
    return bool(hoy["activa"] and hoy["fuerza"] == "FUERTE" and not (prev.get("activa") and prev.get("fuerza") == "FUERTE"))


# ---------------------------------------------------------------- descargas (inyectables en pruebas)
def yahoo(sym, rango="20y", tries=3):
    import consumo
    return consumo.yahoo(sym, rango, tries)


def fred(sid, desde):
    from liquidez_cripto import fred as _f
    return _f(sid, desde)


def _intentar(err, clave, fn, defecto):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        err[clave] = f"{type(e).__name__}: {str(e)[:100]}"
        return defecto


def cargar(F, err):
    series = {}
    for t in ["SPY", "RSP"] + SECTORES + ["RSPD", "RSPS"]:
        if t in series:
            continue
        series[t] = _intentar(err, "yahoo_" + t, lambda t=t: F["yahoo"](t, "20y"), [])
        if F["yahoo"] is yahoo:
            time.sleep(0.4)
    oas = {}
    for k, sid in OAS.items():
        oas[k] = _intentar(err, "fred_" + sid, lambda sid=sid: F["fred"](sid, "2000-01-01"), [])
    return series, {k: v for k, v in oas.items() if v}


# ---------------------------------------------------------------- señales del marcador
def senal_cruce(ratio_nombre, tf, fecha, sentido, run_id, origen):
    import marcador as M
    f = fecha.isoformat() if hasattr(fecha, "isoformat") else str(fecha)
    d = "ALCISTA" if sentido > 0 else "BAJISTA"
    return M.senal("cruce_sma200_ratio", "SPY", d, f"{f} 21:30", f"{ratio_nombre} {tf}: cierra {'sobre' if sentido > 0 else 'bajo'} su SMA 200 tras {CIERRES_CRUCE} cierres seguidos",
                   f"filtro SMA 200 con {CIERRES_CRUCE} cierres de confirmación", "consumo_ratio.py (consumo_ratio.json)", run_id, origen, "")


def senal_divergencia(e, run_id, origen):
    import marcador as M
    f = e["fecha"]
    return M.senal("divergencia_ratio", "SPY", "BAJISTA", f"{f} 21:30",
                   f"divergencia {e['fuerza']}{' (parcial: sin dato de ' + ('crédito' if e['credito_ampliandose'] is None else 'amplitud') + ')' if e['parcial'] else ''}: SPY en máximo de 63 sesiones y RSPD/RSPS {e['ratio_vs_max63_pct']:+.1f} % bajo el suyo",
                   f"SPY máx. 63 sesiones y RSPD/RSPS > {UMBRAL_DIVERGENCIA_PCT:g} % bajo su máx.; amplitud y crédito como confirmación", "consumo_ratio.py (consumo_ratio.json)", run_id, origen, "")


def eventos_marcador(filt, hist, desde=DESDE_BACKFILL):
    """[(tipo, fecha, objeto)] de los cruces válidos y los inicios de divergencia con fecha ≥ desde."""
    ev = []
    for k, tfs in filt.items():
        for tf, f in tfs.items():
            for fecha, sentido in (f.get("_cruces") or []):
                if fecha.isoformat() >= desde:
                    ev.append(("cruce", fecha, (RATIOS[k][2], tf, sentido)))
    for e in inicios_divergencia(hist):
        if e["fecha"] >= desde:
            ev.append(("divergencia", dt.date.fromisoformat(e["fecha"]), e))
    return sorted(ev, key=lambda x: x[1])


def registrar(raiz, filt, hist, origen, run_id, desde):
    """Anota (solo-añadir, idempotente por id) las señales de los eventos con fecha ≥ desde. Devuelve las filas nuevas."""
    import marcador as M
    filas = []
    for tipo, fecha, o in eventos_marcador(filt, hist, desde):
        filas.append(senal_cruce(o[0], o[1], fecha, o[2], run_id, origen) if tipo == "cruce" else senal_divergencia(o, run_id, origen))
    return M._reg(raiz, filas)


def guardar_spy(raiz, spy):
    """data/spy_cierres.csv (solo-añadir): cierres diarios de SPY para medir las señales a T+20 y T+60 (incluye el histórico completo en la primera ejecución)."""
    ruta = P(raiz, "data", "spy_cierres.csv")
    vistas = set()
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8", newline="") as f:
            vistas = {r["fecha"] for r in csv.DictReader(f)}
    nuevas = [(d.isoformat(), v) for d, v in spy if d.isoformat() not in vistas]
    if nuevas:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        existe = os.path.exists(ruta)
        with open(ruta, "a", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            if not existe:
                w.writerow(["fecha", "cierre"])
            w.writerows((d, round(v, 4)) for d, v in nuevas)
    return len(nuevas)


# ---------------------------------------------------------------- Telegram (solo al aparecer una FUERTE, máx. 1 por semana)
def mensaje(e, hist_hoy):
    from telegram import esc
    return (f"<b>NEXORA · Consumo · Divergencia FUERTE</b>\nSPY marca máximo de 63 sesiones y el consumo amplio (RSPD/RSPS) está {abs(e['ratio_vs_max63_pct']):.1f} % por debajo de su máximo de 63 sesiones.\n"
            f"Confirman las dos señales: amplitud a la baja en 1 mes (RSP frente a SPY {e['amplitud_pp']:+.1f} pp a 20 sesiones) y crédito ampliándose ({esc(', '.join(e['credito_detalle'] or []))}).\n"
            f"Hecho de mercado, no una recomendación de compra o venta. Fecha del dato: {esc(e['fecha'])}. Detalle en #/consumo.")


def avisar(raiz, hist, ahora, enviar=None):
    """Envía el Telegram si hoy aparece una divergencia FUERTE y no se envió otro en los últimos 7 días. Devuelve (enviado, motivo)."""
    if not aparece_fuerte(hist):
        return False, "no aparece una divergencia FUERTE hoy"
    est_ruta = P(raiz, "data", "estado_consumo_ratio.json")
    try:
        est = json.load(open(est_ruta, encoding="utf-8"))
    except (OSError, ValueError):
        est = {"enviados": []}
    hoy = dt.date.fromisoformat(hist[-1]["fecha"])
    if any((hoy - dt.date.fromisoformat(x)).days < MAX_TELEGRAM_DIAS for x in est["enviados"]):
        return False, "ya se avisó en los últimos 7 días (máx. 1 por semana)"
    txt = mensaje(hist[-1], hist)
    import telegram
    if enviar is None and not telegram.configurado():
        return False, "Telegram sin configurar"
    ok, err = (enviar or telegram.enviar)(txt)
    if ok:
        est["enviados"] = (est["enviados"] + [hoy.isoformat()])[-20:]
        os.makedirs(os.path.dirname(est_ruta), exist_ok=True)
        json.dump(est, open(est_ruta, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return ok, err or "enviado"


# ---------------------------------------------------------------- construcción
def construir(fuentes=None, ahora=None, raiz=None, enviar=None, registrar_marcador=True, avisar_telegram=True):
    """fuentes = {'yahoo': fn(sym, rango), 'fred': fn(sid, desde)}. Cada fuente falla por separado."""
    raiz = raiz or RAIZ
    ahora = ahora or dt.datetime.now(UTC)
    F = {"yahoo": yahoo, "fred": fred, **(fuentes or {})}
    err = {}
    series, oas = cargar(F, err)
    rd = {}
    for k, (a, b, _) in RATIOS.items():
        if series.get(a) and series.get(b):
            rd[k] = ratio(series[a], series[b])
    filt = filtros(rd)
    rot = rotacion(series)
    hist = historia_divergencia(series, oas) if series.get("SPY") and series.get("RSPD") and series.get("RSPS") else []
    hoy_e = hist[-1] if hist else None
    inicios = inicios_divergencia(hist)
    nuevas, tg = [], None
    if registrar_marcador and series.get("SPY"):
        guardar_spy(raiz, series["SPY"])
        try:
            desde = (ahora.date() - dt.timedelta(days=15)).isoformat()
            nuevas = registrar(raiz, filt, hist, "vivo", os.environ.get("GITHUB_RUN_ID") or "local", desde)
        except Exception as e:  # noqa: BLE001
            err["marcador"] = f"{type(e).__name__}: {str(e)[:100]}"
    if avisar_telegram and hist:
        try:
            tg = avisar(raiz, hist, ahora, enviar)
        except Exception as e:  # noqa: BLE001
            err["telegram"] = f"{type(e).__name__}: {str(e)[:100]}"
    limpio = {k: {tf: {kk: vv for kk, vv in f.items() if kk != "_cruces"} for tf, f in tfs.items()} for k, tfs in filt.items()}
    return {"version": 1, "ok": True, "generado_utc": ahora.strftime("%Y-%m-%d %H:%M UTC"), "fecha_datos": (series["SPY"][-1][0].isoformat() if series.get("SPY") else None),
            "filtro_sma200": {"ratios": {k: {"nombre": RATIOS[k][2], **v} for k, v in limpio.items()}, "cierres_para_cruce": CIERRES_CRUCE, "umbral_cruces_12m": UMBRAL_CRUCES_12M, "nota_lateral": NOTA_LATERAL},
            "rotacion": rot,
            "divergencia": {"hoy": hoy_e, "ultimos_30": hist[-30:], "inicios_recientes": [{"fecha": e["fecha"], "fuerza": e["fuerza"], "parcial": e["parcial"]} for e in inicios[-6:]], "umbral_pct": UMBRAL_DIVERGENCIA_PCT,
                            "ventana_sesiones": VENTANA_MAX, "amplitud": {"medida": "RSP frente a SPY a 20 sesiones (pp)", "umbral_pp": -AMPLITUD_PP, "origen": "misma medida y umbral que indices.py (NEXORA no calcula el % de valores del S&P sobre su SMA 200)"},
                            "credito": {"umbrales_pb": {k: list(v) for k, v in UMB_CRED.items()}, "origen": "ciclo.py (5 días, 1 mes); FRED solo da 3 años de los diferenciales ICE BofA"},
                            "telegram": ({"enviado": tg[0], "motivo": tg[1]} if tg else None)},
            "marcador": {"senales_nuevas": len(nuevas), "tipos": ["cruce_sma200_ratio", "divergencia_ratio"], "horizontes": list(HORIZONTES)},
            "reglas": None,
            "errores": err, "fuentes": "Yahoo Finance (XLY, XLP, RSPD, RSPS, SPY, RSP y ocho sectores SPDR) · FRED (diferenciales ICE BofA IG, BBB, HY, CCC) · reglas de indices.py y ciclo.py"}


def etapa():
    J = construir()
    J["reglas"] = REGLAS_TEXTO
    return J


REGLAS_TEXTO = [
    f"Filtro SMA 200: cierre del ratio frente a su media de {SMA_N} (sesiones en diario, cierres semanales en semanal). Un cruce solo es válido tras {CIERRES_CRUCE} cierres consecutivos al otro lado del lado vigente; un cierre de vuelta reinicia la cuenta.",
    f"Cruces válidos en 12 meses: si hay {UMBRAL_CRUCES_12M} o más, nota «{NOTA_LATERAL}».",
    "Rotación: rendimiento relativo frente a SPY (pp) a 1 mes (21 sesiones) y 3 meses (63) de XLY, XLP, XLK, XLE, XLU, XLV, XLF y XLI, ordenado por el de 3 meses. Solo describe.",
    f"Divergencia: SPY marca máximo de cierre de {VENTANA_MAX} sesiones y RSPD/RSPS está más de un {UMBRAL_DIVERGENCIA_PCT:g} % por debajo de su propio máximo de {VENTANA_MAX} sesiones.",
    f"Confirmaciones: amplitud a la baja en 1 mes (RSP frente a SPY a {AMPLITUD_SESIONES} sesiones ≤ −{AMPLITUD_PP:g} pp, medida y umbral de indices.py) y diferenciales de crédito ampliándose (umbrales de ciclo.py). Las dos = FUERTE; una = MEDIA; ninguna = DÉBIL; sin dato de una = «parcial».",
    f"Una divergencia nueva solo cuenta si hace {ENFRIAMIENTO} o más sesiones que no había ninguna. Telegram solo cuando APARECE una FUERTE (máx. 1 por semana).",
    "Marcador: «cruce_sma200_ratio» (SPY alcista tras un cruce al alza, bajista tras uno a la baja) y «divergencia_ratio» (SPY bajista), a T+20 y T+60 frente a la tasa base; el pasado desde 2010 es backfill.",
]


def backfill(raiz=RAIZ, fuentes=None, ahora=None):
    """Reconstruye desde 2010 los cruces válidos y los inicios de divergencia con los datos disponibles (origen=backfill) y guarda el histórico de SPY. Idempotente."""
    ahora = ahora or dt.datetime.now(UTC)
    F = {"yahoo": yahoo, "fred": fred, **(fuentes or {})}
    err = {}
    series, oas = cargar(F, err)
    rd = {k: ratio(series[a], series[b]) for k, (a, b, _) in RATIOS.items() if series.get(a) and series.get(b)}
    filt = filtros(rd)
    hist = historia_divergencia(series, oas)
    n_spy = guardar_spy(raiz, series["SPY"])
    nuevas = registrar(raiz, filt, hist, "backfill", "backfill", DESDE_BACKFILL)
    return {"nuevas": len(nuevas), "spy_filas_nuevas": n_spy, "errores": err, "eventos": len(eventos_marcador(filt, hist)),
            "cruces": {k: {tf: len([c for c in (f.get("_cruces") or []) if c[0].isoformat() >= DESDE_BACKFILL]) for tf, f in tfs.items()} for k, tfs in filt.items()},
            "inicios_divergencia": len([e for e in inicios_divergencia(hist) if e["fecha"] >= DESDE_BACKFILL]),
            "divergencias_por_fuerza": {f: len([e for e in inicios_divergencia(hist) if e["fecha"] >= DESDE_BACKFILL and e["fuerza"] == f]) for f in ("FUERTE", "MEDIA", "DÉBIL")},
            "divergencias_parciales": len([e for e in inicios_divergencia(hist) if e["fecha"] >= DESDE_BACKFILL and e["parcial"]]), "oas_desde": min((s[0][0].isoformat() for s in oas.values() if s), default=None)}


def bloque_contexto(raiz=RAIZ):
    try:
        J = json.load(open(P(raiz, "site", "data", "consumo_ratio.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return {"estado": "SIN DATO", "fuente": "consumo_ratio.py"}
    fs = (J.get("filtro_sma200") or {}).get("ratios") or {}
    d = (J.get("divergencia") or {}).get("hoy") or {}
    rot = (J.get("rotacion") or {}).get("filas") or []
    return {"fecha": J.get("fecha_datos"),
            "filtro_sma200": {v["nombre"]: {tf: ({"estado": x.get("estado"), "dist_pct": x.get("dist_pct"), "cruce_pendiente": x.get("pendiente"), "cruces_12m": x.get("cruces_12m"), "nota": x.get("nota")} if x.get("estado") != "SIN DATO" else "SIN DATO")
                                       for tf, x in v.items() if tf in ("diario", "semanal")} for v in fs.values()},
            "rotacion_vs_spy_3m_pp": {f["etf"]: f["rel_3m"] for f in rot if f.get("rel_3m") is not None} or "SIN DATO",
            "divergencia": ({"activa": d.get("activa"), "fuerza": d.get("fuerza"), "parcial": d.get("parcial"), "spy_en_maximo_63": d.get("spy_max_63"), "ratio_vs_max63_pct": d.get("ratio_vs_max63_pct"),
                             "amplitud_a_la_baja": d.get("amplitud_a_la_baja"), "credito_ampliandose": d.get("credito_ampliandose")} if d else "SIN DATO"),
            "nota": "Descriptivo: el filtro, la rotación y la divergencia no puntúan en la tesis de consumo ni son una recomendación de compra o venta.", "fuente": "consumo_ratio.py (consumo_ratio.json)"}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true")
    a = ap.parse_args()
    if a.backfill:
        r = backfill()
        print(json.dumps(r, ensure_ascii=False, indent=1))
        sys.exit(0)
    J = etapa()
    with open(P(RAIZ, "site", "data", "consumo_ratio.json"), "w", encoding="utf-8") as f:
        json.dump(J, f, ensure_ascii=False, indent=1)
    fs = J["filtro_sma200"]["ratios"]
    print({k: {tf: (x.get("estado"), x.get("pendiente"), x.get("cruces_12m")) for tf, x in v.items() if tf in ("diario", "semanal")} for k, v in fs.items()})
    print("divergencia hoy:", {k: (J["divergencia"]["hoy"] or {}).get(k) for k in ("activa", "spy_max_63", "ratio_vs_max63_pct", "amplitud_pp", "credito_ampliandose", "fuerza")})
    print("errores:", J["errores"] or "ninguno")
