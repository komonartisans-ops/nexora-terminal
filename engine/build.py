#!/usr/bin/env python3
"""NEXORA TERMINAL · build.py
Ejecuta los monitores y escribe site/data/*.json (+ memoria permanente en data/*.csv).

Reglas: coste cero, sin LLM, sin claves de pago. Una fuente que falla NO rompe la web:
el JSON de esa etapa lleva ok=false, el error y, si existe, la última copia válida con su fecha.

Uso:  python engine/build.py --modo diario|horario|todo [--solo etapa,etapa]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
import time
import traceback
import warnings

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SITE_DATA = os.path.join(ROOT, "site", "data")
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
os.makedirs(SITE_DATA, exist_ok=True)
os.makedirs(DATA, exist_ok=True)

import liquidez_cripto as LQ  # noqa: E402

NOW = dt.datetime.now(dt.timezone.utc)
STAMP = NOW.strftime("%Y-%m-%d %H:%M UTC")


# ------------------------------------------------------------------ utilidades
def ruta(nombre):
    return os.path.join(SITE_DATA, nombre)


def leer(nombre):
    try:
        with open(ruta(nombre), encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def escribir(nombre, obj):
    with open(ruta(nombre), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, default=str)


def con_respaldo(nombre, fn):
    """Ejecuta fn(); si falla conserva la última copia válida marcándola como caducada. Nunca inventa."""
    t0 = time.time()
    try:
        out = fn()
        out["ok"] = True
        out["generado_utc"] = STAMP
        out["duracion_s"] = round(time.time() - t0, 1)
        escribir(nombre, out)
        return {"ok": True, "duracion_s": out["duracion_s"], "error": None}
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
        print(f"[{nombre}] FALLO {err}\n{traceback.format_exc()}", file=sys.stderr)
        prev = leer(nombre) or {}
        prev["ok"] = False
        prev["error"] = err
        prev["ultimo_dato_valido_utc"] = prev.get("generado_utc_ok") or prev.get("generado_utc")
        prev.setdefault("generado_utc", None)
        escribir(nombre, prev)
        return {"ok": False, "duracion_s": round(time.time() - t0, 1), "error": err}


def serie_json(s, desde_dias=None):
    """[(fecha, valor)] -> [[iso, valor]] recortada."""
    if desde_dias:
        corte = dt.date.today() - dt.timedelta(days=desde_dias)
        s = [x for x in s if x[0] >= corte]
    return [[d.isoformat(), round(v, 4)] for d, v in s]


def csv_append(nombre, fila, claves):
    """Memoria permanente: solo se añade, una fila por clave (fecha) si no existe."""
    p = os.path.join(DATA, nombre)
    existe = os.path.exists(p)
    vistas = set()
    if existe:
        with open(p, encoding="utf-8", newline="") as f:
            vistas = {r.get(claves[0]) for r in csv.DictReader(f)}
    if fila.get(claves[0]) in vistas:
        return
    with open(p, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fila.keys()))
        if not existe:
            w.writeheader()
        w.writerow(fila)


# ------------------------------------------------------------------ precios (Yahoo, sin clave)
ACTIVOS = [
    ("oro", "Oro", "GC=F", "Futuros oro COMEX (Yahoo Finance)"),
    ("btc", "Bitcoin", "BTC-USD", "BTC-USD (Yahoo Finance)"),
    ("spx", "S&P 500", "^GSPC", "S&P 500 (Yahoo Finance)"),
    ("ndx", "Nasdaq 100", "^NDX", "Nasdaq 100 (Yahoo Finance)"),
    ("dji", "US30 · Dow Jones", "^DJI", "Dow Jones (Yahoo Finance)"),
    ("rut", "Russell 2000", "^RUT", "Russell 2000 (Yahoo Finance)"),
    ("vix", "VIX", "^VIX", "Cboe VIX (Yahoo Finance)"),
    ("dxy", "Índice dólar (DXY)", "DX-Y.NYB", "ICE DXY (Yahoo Finance)"),
]


UA_WEB = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
          "Accept": "application/json"}
# Respaldo si Yahoo devuelve 429 desde las IP compartidas de Actions: serie FRED (con retraso, la fecha del dato se muestra siempre)
RESPALDO_FRED = {"^GSPC": "SP500", "^NDX": "NASDAQ100", "^DJI": "DJIA", "^VIX": "VIXCLS"}


def _get_web(url, tries=3):
    import urllib.request
    last = None
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA_WEB), timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (k + 1))
    raise last


def yahoo(sym, rango="1y"):
    q = sym.replace("^", "%5E")
    last = None
    for host in ("query2", "query1"):
        try:
            j = _get_web(f"https://{host}.finance.yahoo.com/v8/finance/chart/{q}?range={rango}&interval=1d", tries=2)
            r = j["chart"]["result"][0]
            pts = [(dt.datetime.fromtimestamp(t, dt.timezone.utc).date(), float(c))
                   for t, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]) if c is not None]
            if len(pts) < 5:
                raise RuntimeError("serie vacía")
            return pts, "Yahoo Finance"
        except Exception as e:  # noqa: BLE001
            last = e
    if sym in RESPALDO_FRED:
        pts = LQ.fred(RESPALDO_FRED[sym], (dt.date.today() - dt.timedelta(days=400)).isoformat())
        return pts, f"FRED {RESPALDO_FRED[sym]} (respaldo: Yahoo no respondió)"
    if sym == "BTC-USD":
        pts = [(d, c) for d, c, *_ in LQ.coinbase("BTC-USD", 300)]
        return pts, "Coinbase (respaldo: Yahoo no respondió)"
    raise last


def etapa_precios():
    out, err = {}, {}
    for k, nombre, sym, fuente in ACTIVOS:
        try:
            pts, origen = yahoo(sym)
            time.sleep(0.8)
            ult, prev = pts[-1], pts[-2]
            def cambio(n):
                ref = pts[-1 - n] if len(pts) > n else None
                return round((ult[1] / ref[1] - 1) * 100, 2) if ref else None
            sma50 = sum(v for _, v in pts[-50:]) / min(50, len(pts))
            out[k] = {"nombre": nombre, "simbolo": sym, "valor": round(ult[1], 2), "fecha": ult[0].isoformat(),
                      "cambio_1d_pct": cambio(1), "cambio_5d_pct": cambio(5), "cambio_21d_pct": cambio(21), "cambio_63d_pct": cambio(63),
                      "sma50": round(sma50, 2), "fuente": fuente if origen == "Yahoo Finance" else origen, "serie": serie_json(pts, 400)}
        except Exception as e:  # noqa: BLE001
            err[k] = f"{type(e).__name__}: {e}"
            out[k] = {"nombre": nombre, "simbolo": sym, "valor": None, "fuente": fuente, "sin_dato": True}
    if len(err) == len(ACTIVOS):
        raise RuntimeError("Yahoo Finance no responde: " + json.dumps(err)[:300])
    return {"activos": out, "errores": err}


# ------------------------------------------------------------------ FedWatch + bancos centrales
def etapa_fedwatch():
    import fedwatch
    F = fedwatch.medir(6)
    hoy = dt.date.today()
    hist = {}
    for clave, sid in (("fed_max", "DFEDTARU"), ("fed_min", "DFEDTARL"), ("effr", "EFFR"), ("bce_deposito", "ECBDFR"),
                       ("boj_politica", "IRSTCB01JPM156N")):
        try:
            hist[clave] = serie_json(LQ.fred(sid, (hoy - dt.timedelta(days=900)).isoformat()), 900) or None  # FRED ignora cosd en series muertas: se recorta aquí; sin datos recientes = SIN DATO
        except Exception as e:  # noqa: BLE001
            hist[clave] = None
            F.setdefault("errores", {})[sid] = f"{type(e).__name__}: {e}"
    F["tipos_historico"] = hist
    # tipo actual por banco (valor + fecha del dato; no se estima nada)
    def ult(k):
        s = hist.get(k)
        return {"valor": s[-1][1], "fecha": s[-1][0]} if s else None
    F["tipos_actuales"] = {"Fed": {"rango": F["rango_objetivo"], "effr": F["effr"], "fuente": "FRED DFEDTARL/DFEDTARU/EFFR"},
                           "BCE": {**(ult("bce_deposito") or {}), "fuente": "FRED ECBDFR (facilidad de depósito)"} if ult("bce_deposito") else None,
                           "BoJ": {**(ult("boj_politica") or {}), "fuente": "FRED IRSTCB01JPM156N (OCDE, mensual)"} if ult("boj_politica") else None}
    return F


# ------------------------------------------------------------------ calendario
# Series FRED para mostrar «dato anterior» y «último publicado» (periodo ≠ publicación). Sin consenso: es de pago.
PUBLICADOS = [
    ("IPC EE. UU. (CPI)", "CPIAUCSL", "yoy", "IPC general, % interanual"),
    ("Empleo (Employment Situation)", "PAYEMS", "diff", "Nóminas no agrícolas, variación en miles"),
    ("Peticiones de paro semanales", "ICSA", "nivel", "Peticiones iniciales, personas"),
    ("Ventas minoristas", "RSAFS", "mom", "Ventas minoristas, % mensual"),
    ("IPP EE. UU. (PPI)", "PPIFIS", "yoy", "IPP demanda final, % interanual"),
    ("PIB EE. UU.", "GDPC1", "qoq_anual", "PIB real, % trimestral anualizado"),
    ("Gasto personal (PCE)", "PCEPI", "yoy", "Deflactor PCE, % interanual"),
    ("Producción industrial", "INDPRO", "mom", "Producción industrial, % mensual"),
]


def valor_publicado(sid, modo):
    s = LQ.fred(sid, (dt.date.today() - dt.timedelta(days=900)).isoformat())
    if modo == "nivel":
        a, b = s[-1], s[-2]
        return {"periodo": a[0].isoformat(), "valor": a[1], "anterior": b[1], "anterior_periodo": b[0].isoformat()}
    def f(i):
        if modo == "yoy":
            return (s[i][1] / s[i - 12][1] - 1) * 100
        if modo == "mom":
            return (s[i][1] / s[i - 1][1] - 1) * 100
        if modo == "diff":
            return s[i][1] - s[i - 1][1]
        if modo == "qoq_anual":
            return ((s[i][1] / s[i - 1][1]) ** 4 - 1) * 100
    return {"periodo": s[-1][0].isoformat(), "valor": round(f(-1), 2), "anterior": round(f(-2), 2), "anterior_periodo": s[-2][0].isoformat()}


def etapa_calendario():
    import calendario
    C = calendario.construir(21, 40, True)
    pub = {}
    for nombre, sid, modo, desc in PUBLICADOS:
        try:
            v = valor_publicado(sid, modo)
            v.update({"descripcion": desc, "fuente": f"FRED {sid}", "url": f"https://fred.stlouisfed.org/series/{sid}"})
            pub[nombre] = v
        except Exception as e:  # noqa: BLE001
            pub[nombre] = {"sin_dato": True, "error": f"{type(e).__name__}: {e}", "fuente": f"FRED {sid}"}
    hoy_iso = dt.date.today().isoformat()
    for e in C["eventos"]:
        for nombre, v in pub.items():
            if nombre.split(" (")[0].lower() in e["evento"].lower():
                e["publicado"] = v
                if e["fecha"] <= hoy_iso and not v.get("sin_dato"):
                    v["fecha_publicacion"] = max(v.get("fecha_publicacion", ""), e["fecha"])  # periodo ≠ publicación: se muestran las dos
                break
    C["ultimos_publicados"] = pub
    return C


# ------------------------------------------------------------------ liquidez
def etapa_liquidez():
    M = LQ.medir()
    try:
        import fedwatch
        F = leer("fedwatch.json")
        fw = fedwatch.para_monitor(F) if F and F.get("ok") else None
    except Exception:  # noqa: BLE001
        fw = None
    E = LQ.evaluar(M, fw)
    hoy = dt.date.today()
    desde = (hoy - dt.timedelta(days=800)).isoformat()
    ser, errs = {}, {}
    for k, sid in (("WALCL", "WALCL"), ("WTREGEN", "WTREGEN"), ("RRP", "RRPONTSYD"), ("WRESBAL", "WRESBAL"), ("SP500", "SP500"),
                   ("ECB", "ECBASSETSW"), ("BOJ", "JPNASSETS"), ("EURUSD", "DEXUSEU"), ("JPYUSD", "DEXJPUS"), ("NFCI", "NFCI"), ("M2", "M2SL")):
        try:
            ser[k] = LQ.fred(sid, desde)
        except Exception as e:  # noqa: BLE001
            errs[sid] = f"{type(e).__name__}: {e}"
    hist = {}
    if all(k in ser for k in ("WALCL", "WTREGEN")):
        rrp = {d: v for d, v in ser.get("RRP", [])}
        tga = {d: v for d, v in ser["WTREGEN"]}
        neta = []
        for d, v in ser["WALCL"]:
            if d in tga:
                r = LQ.at_or_before(ser["RRP"], d) if "RRP" in ser else None
                neta.append((d, v / 1e6 - tga[d] / 1e6 - (r[1] / 1000 if r else 0)))
        hist["liquidez_neta_T"] = serie_json(neta)
        hist["balance_fed_T"] = serie_json([(d, v / 1e6) for d, v in ser["WALCL"]])
        hist["tga_T"] = serie_json([(d, v / 1e6) for d, v in ser["WTREGEN"]])
    if "RRP" in ser:
        hist["rrp_T"] = serie_json([(d, v / 1000) for d, v in ser["RRP"]])
    if "WRESBAL" in ser:
        hist["reservas_T"] = serie_json([(d, v / 1e6) for d, v in ser["WRESBAL"]])
    if "SP500" in ser:
        hist["sp500"] = serie_json(ser["SP500"])
    if "ECB" in ser and "EURUSD" in ser:
        hist["bce_T"] = serie_json([(d, v * (LQ.at_or_before(ser["EURUSD"], d) or (d, 0))[1] / 1e6) for d, v in ser["ECB"]
                                    if LQ.at_or_before(ser["EURUSD"], d)])
    if "BOJ" in ser and "JPYUSD" in ser:
        # JPNASSETS en 100 millones de yenes; DEXJPUS = yenes por dólar
        hist["boj_T"] = serie_json([(d, v * 1e8 / (LQ.at_or_before(ser["JPYUSD"], d) or (d, 1e18))[1] / 1e12) for d, v in ser["BOJ"]
                                    if LQ.at_or_before(ser["JPYUSD"], d)])
    if "NFCI" in ser:
        hist["nfci"] = serie_json(ser["NFCI"])
    # liquidez global = Fed + BCE + BoJ en T$ (solo fechas con los tres)
    if all(k in hist for k in ("balance_fed_T", "bce_T", "boj_T")):
        b, j = dict(hist["bce_T"]), dict(hist["boj_T"])
        glob = []
        for d, v in hist["balance_fed_T"]:
            e = next((b[x] for x in sorted(b, reverse=True) if x <= d), None)
            o = next((j[x] for x in sorted(j, reverse=True) if x <= d), None)
            if e is not None and o is not None:
                glob.append([d, round(v + e + o, 4)])
        hist["liquidez_global_T"] = glob
    # memoria permanente
    try:
        ln = hist.get("liquidez_neta_T") or []
        csv_append("historico_liquidez.csv", {"fecha_captura": hoy.isoformat(),
                                              "liquidez_neta_T": ln[-1][1] if ln else "",
                                              "liquidez_neta_fecha": ln[-1][0] if ln else "",
                                              "reservas_T": M.get("reservas", {}).get("valor_T", ""),
                                              "tga_B": M.get("tga", {}).get("valor_B", ""),
                                              "rrp_B": M.get("rrp", {}).get("valor_B", ""),
                                              "lectura": E.get("lectura", ""),
                                              "checklist_cumple": E.get("checklist_resumen", {}).get("cumple", "")}, ["fecha_captura"])
    except Exception as e:  # noqa: BLE001
        errs["csv"] = str(e)
    return {"metricas": M, "evaluacion": E, "historico": hist, "errores_historico": errs}


# ------------------------------------------------------------------ resumen (tesis por activo, plantillas deterministas)
def etapa_resumen():
    import una_pagina
    fwp = ruta("fedwatch.json")
    cap = ruta("calendario.json")
    P = una_pagina.generar("nexora", 1, fwp if (leer("fedwatch.json") or {}).get("ok") else None,
                           cap if (leer("calendario.json") or {}).get("ok") else None)
    # etiqueta de tesis por activo: suma firmada de los motores significativos (misma regla que 'viento' de una_pagina)
    tes = {}
    for a, cs in P.get("detalle_viento", {}).items():
        tot = round(sum(c["peso"] for c in cs), 2)
        if tot > 0.75:
            et = "ALCISTA"
        elif tot < -0.75:
            et = "BAJISTA"
        elif abs(tot) >= 0.25:
            et = "DÉBIL"
        else:
            et = "SIN TESIS"
        tes[a] = {"etiqueta": et, "puntuacion": tot, "motores": cs}
    P["tesis_activos"] = tes
    P.pop("datos", None)
    return P


# ------------------------------------------------------------------ principal
ETAPAS = {"precios": etapa_precios, "fedwatch": etapa_fedwatch, "calendario": etapa_calendario,
          "liquidez": etapa_liquidez, "resumen": etapa_resumen}
ORDEN = ["precios", "fedwatch", "calendario", "liquidez", "resumen"]
MODOS = {"horario": ["precios", "fedwatch"], "diario": ORDEN, "todo": ORDEN}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modo", default="diario", choices=list(MODOS))
    ap.add_argument("--solo", default="")
    a = ap.parse_args()
    etapas = [e for e in ORDEN if e in (a.solo.split(",") if a.solo else MODOS[a.modo])]
    t0 = time.time()
    estado = (leer("meta.json") or {}).get("etapas", {})
    for e in etapas:
        print(f"== {e}", flush=True)
        r = con_respaldo(f"{e}.json", ETAPAS[e])
        r["ejecutada_utc"] = STAMP
        if r["ok"]:
            r["ultimo_ok_utc"] = STAMP
        else:
            r["ultimo_ok_utc"] = estado.get(e, {}).get("ultimo_ok_utc")
        estado[e] = r
        print(f"   {'OK' if r['ok'] else 'FALLO'} {r['duracion_s']} s {r['error'] or ''}", flush=True)
    escribir("meta.json", {"actualizado_utc": STAMP, "modo": a.modo, "etapas": estado,
                           "duracion_total_s": round(time.time() - t0, 1)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
