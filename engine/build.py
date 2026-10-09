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

import csvlog  # noqa: E402
import liquidez_cripto as LQ  # noqa: E402

NOW = dt.datetime.now(dt.timezone.utc)
STAMP = NOW.strftime("%Y-%m-%d %H:%M UTC")


# monitores ya calculados en este proceso: se ejecutan UNA sola vez y los reutilizan resumen y régimen
_MON = {}


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
    """Memoria permanente: solo se añade; una fila por clave (columnas `claves`), nunca duplicada."""
    return csvlog.anadir(nombre, [fila], claves)


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
    # memoria permanente: una fila por activo en CADA ejecución (la clave incluye el minuto de captura → crece sin duplicar)
    csvlog.anadir("historico_precios.csv", [{"capturado_utc": STAMP, "activo": k, "valor": a.get("valor", ""), "fecha_dato": a.get("fecha", ""),
                                             "cambio_1d_pct": a.get("cambio_1d_pct", ""), "fuente": a.get("fuente", "")}
                                            for k, a in out.items() if a.get("valor") is not None], ("capturado_utc", "activo"))
    return {"activos": out, "errores": err}


# ------------------------------------------------------------------ FedWatch + bancos centrales
def etapa_fedwatch():
    import fedwatch
    F = fedwatch.medir(6)
    hoy = dt.date.today()
    hist = {}
    for clave, sid in (("fed_max", "DFEDTARU"), ("fed_min", "DFEDTARL"), ("effr", "EFFR"), ("bce_deposito", "ECBDFR")):
        try:
            hist[clave] = serie_json(LQ.fred(sid, (hoy - dt.timedelta(days=900)).isoformat()), 900) or None  # FRED ignora cosd en series muertas: se recorta aquí; sin datos recientes = SIN DATO
        except Exception as e:  # noqa: BLE001
            hist[clave] = None
            F.setdefault("errores", {})[sid] = f"{type(e).__name__}: {e}"
    # BoJ: el tipo actual sale de la web oficial del Banco de Japón (FRED/OCDE va con años de retraso); el histórico, del BIS
    boj_web = None
    try:
        import boj
        boj_web = boj.tipo_oficial()
    except Exception as e:  # noqa: BLE001
        F.setdefault("errores", {})["BoJ (web)"] = f"{type(e).__name__}: {e}"
    try:
        import divisas
        jp = divisas._bis(["JP"], dias=900).get("JP") or []
        cambios = [x for i, x in enumerate(jp) if i == 0 or x[1] != jp[i - 1][1]]  # solo los cambios de tipo (serie en escalón)
        h_boj = [[d.isoformat(), v] for d, v in cambios]
        if boj_web:  # el dato de la web manda; si la decisión es posterior al último cambio del BIS se añade como último escalón
            if not h_boj or h_boj[-1][1] != boj_web["valor"]:
                h_boj.append([boj_web["fecha"] or hoy.isoformat(), boj_web["valor"]])
            elif boj_web["fecha"]:
                h_boj[-1][0] = boj_web["fecha"]  # el BIS fecha la entrada en vigor; la web del BoJ, la decisión
            h_boj.append([hoy.isoformat(), boj_web["valor"]])
        hist["boj_politica"] = h_boj or None
    except Exception as e:  # noqa: BLE001
        hist["boj_politica"] = None
        F.setdefault("errores", {})["BIS (histórico BoJ)"] = f"{type(e).__name__}: {e}"
    F["tipos_historico"] = hist
    # tipo actual por banco (valor + fecha del dato; no se estima nada)
    def ult(k):
        s = hist.get(k)
        return {"valor": s[-1][1], "fecha": s[-1][0]} if s else None
    F["tipos_actuales"] = {"Fed": {"rango": F["rango_objetivo"], "effr": F["effr"], "fuente": "FRED DFEDTARL/DFEDTARU/EFFR"},
                           "BCE": {**(ult("bce_deposito") or {}), "fuente": "FRED ECBDFR (facilidad de depósito)"} if ult("bce_deposito") else None,
                           "BoJ": {"valor": boj_web["valor"], "fecha": boj_web["fecha"], "fuente": boj_web["fuente"], "url": boj_web["url"], "nota": boj_web["nota"]} if boj_web else None}
    csvlog.anadir("historico_fedwatch.csv", [{"capturado_utc": STAMP, "reunion": r["reunion"], "tipo_esperado": r["tipo_esperado"],
                                              "prob_subida": r["prob_reunion"]["subida"], "prob_mantiene": r["prob_reunion"]["mantiene"],
                                              "prob_bajada": r["prob_reunion"]["bajada"], "fecha_precios": F["fecha_precios"]} for r in F["reuniones"]],
                  ("capturado_utc", "reunion"))
    return F


# ------------------------------------------------------------------ tipos oficiales (Tesoro de EE. UU.): 2Y, 10Y y 10Y real
def etapa_tipos():
    import oro_xau
    err, out = {}, {}
    def bloque(s):
        a, b = s[-1], s[-2]
        d5 = next((x for x in reversed(s[:-1]) if x[0] <= a[0] - dt.timedelta(days=7)), None)
        return {"valor": round(a[1], 3), "fecha": a[0].isoformat(), "d1_pb": round((a[1] - b[1]) * 100, 1),
                "d5_pb": round((a[1] - d5[1]) * 100, 1) if d5 else None, "serie": serie_json(s, 900)}
    try:
        nom = oro_xau.treasury("nominal", 2)
        real = oro_xau.treasury("real", 2)
        for k, d, col in (("t2y", nom, "2 Yr"), ("n10", nom, "10 Yr"), ("real10", real, "10 YR")):
            s = [(f, v[col]) for f, v in d.items() if col in v]
            if len(s) > 5:
                out[k] = {**bloque(s), "fuente": "Tesoro de EE. UU. (curva par diaria)", "url": "https://home.treasury.gov/resource-center/data-chart-center/interest-rates"}
    except Exception as e:  # noqa: BLE001
        err["tesoro"] = f"{type(e).__name__}: {e}"
    for k, sid in (("t2y", "DGS2"), ("n10", "DGS10"), ("real10", "DFII10")):  # respaldo FRED si el Tesoro no respondió
        if k not in out:
            try:
                s = LQ.fred(sid, (dt.date.today() - dt.timedelta(days=1100)).isoformat())
                out[k] = {**bloque(s), "fuente": f"FRED {sid} (respaldo: Tesoro no respondió)", "url": f"https://fred.stlouisfed.org/series/{sid}"}
            except Exception as e:  # noqa: BLE001
                err[sid] = f"{type(e).__name__}: {e}"
    if not out:
        raise RuntimeError("sin tipos: " + json.dumps(err)[:300])
    csvlog.anadir("historico_tipos.csv", [{"capturado_utc": STAMP, "serie": k, "valor": m["valor"], "fecha_dato": m["fecha"], "d1_pb": m["d1_pb"], "fuente": m["fuente"]}
                                          for k, m in out.items()], ("capturado_utc", "serie"))
    return {**out, "errores": err}


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
    csvlog.anadir("eventos_macro.csv", [{"fecha": e["fecha"], "hora_madrid": e.get("hora_madrid") or "", "evento": e["evento"], "importancia": e.get("importancia", ""),
                                         "fuente": e.get("fuente", ""), "visto_utc": STAMP} for e in C["eventos"]], ("fecha", "evento"))
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
    _MON["liquidez_cripto"] = (M, E)
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


# ------------------------------------------------------------------ monitores de oro e índices (una sola ejecución; los reutilizan resumen y régimen)
def _par(serie):
    return [[str(d), round(float(v), 4)] for d, v in (serie or [])]


def _guardar_monitor(nombre, M, E, extra):
    escribir(f"{nombre}.json", {"ok": True, "generado_utc": STAMP, "metricas": {k: v for k, v in M.items() if not k.startswith("_")},
                                "evaluacion": E, **extra})


def etapa_monitores():
    import concurrent.futures as cf
    import oro_xau
    gld = {}
    orig = oro_xau.gld_holdings

    def gld_cache():  # misma descarga del monitor: se guarda la serie completa para el gráfico de toneladas
        r = orig()
        gld["s"] = r
        return r
    oro_xau.gld_holdings = gld_cache

    def correr(mod):
        m = __import__(mod)
        M = m.medir()
        return M, m.evaluar(M)
    res, err = {}, {}
    with cf.ThreadPoolExecutor(2) as ex:
        fut = {ex.submit(correr, mod): k for k, mod in (("oro", "oro_xau"), ("indices", "indices"))}
        for f in cf.as_completed(fut):
            k = fut[f]
            try:
                res[k] = f.result()
            except Exception as e:  # noqa: BLE001
                err[k] = f"{type(e).__name__}: {e}"
                print(f"[{k}] FALLO {err[k]}\n{traceback.format_exc()}", file=sys.stderr)
    est = {}
    for k, (M, E) in res.items():
        _MON["oro_xau" if k == "oro" else "indices"] = (M, E)
        extra = {}
        if k == "oro":
            extra["series"] = {"gld_t": _par([(d, t) for d, t, _ in (gld.get("s") or [])][-900:]) or None}
        _guardar_monitor(k, M, E, extra)
        est[k] = {"ok": True}
    for k, e in err.items():
        prev = leer(f"{k}.json") or {}
        prev["ok"], prev["error"] = False, e
        escribir(f"{k}.json", prev)
        est[k] = {"ok": False, "error": e}
    if len(err) == 2:
        raise RuntimeError("ni oro ni índices respondieron: " + json.dumps(err)[:300])
    return {"monitores": est}


# ------------------------------------------------------------------ series para los gráficos de Oro, Índices y Cripto (solo fuentes gratuitas; si falla = SIN DATO)
SERIES_YAHOO = [("xly", "XLY", "Consumo discrecional (ETF XLY)"), ("xlp", "XLP", "Consumo básico (ETF XLP)"), ("rsp", "RSP", "S&P 500 igual peso (ETF RSP)"),
                ("spy", "SPY", "S&P 500 (ETF SPY)"), ("iwm", "IWM", "Russell 2000 (ETF IWM)"), ("qqq", "QQQ", "Nasdaq 100 (ETF QQQ)"),
                ("gld", "GLD", "SPDR Gold Shares (precio)"), ("vix3m", "^VIX3M", "VIX a 3 meses (Cboe)"), ("gdx", "GDX", "Mineras de oro (ETF GDX)")]


def etf_btc_serie():
    """Flujos diarios de los ETF de bitcoin de EE. UU. (Farside Investors, millones de $). Devuelve [(fecha, total)]."""
    import html as _h
    import re
    import urllib.request
    req = urllib.request.Request("https://farside.co.uk/btc/", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"})
    t = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "replace")
    out = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", t, flags=re.S):
        c = [re.sub(r"\s+", " ", _h.unescape(re.sub(r"<[^>]+>", "", x))).strip() for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, flags=re.S)]
        if len(c) >= 3 and re.match(r"\d{2} \w{3} \d{4}$", c[0]) and c[-1] not in ("-", ""):
            try:
                out.append((dt.datetime.strptime(c[0], "%d %b %Y").date(), float(c[-1].replace(",", "").replace("(", "-").replace(")", ""))))
            except ValueError:
                continue
    if not out:
        raise RuntimeError("Farside sin filas con dato")
    return out[-250:]


def etapa_series():
    err, out, cr = {}, {}, {}
    for k, sym, nombre in SERIES_YAHOO:
        try:
            pts, origen = yahoo(sym)
            time.sleep(0.8)
            out[k] = {"nombre": nombre, "simbolo": sym, "fecha": pts[-1][0].isoformat(), "valor": round(pts[-1][1], 4), "serie": serie_json(pts, 400), "fuente": origen}
        except Exception as e:  # noqa: BLE001
            err[k] = f"{type(e).__name__}: {e}"
    def toma(clave, fn, *a):
        try:
            return fn(*a)
        except Exception as e:  # noqa: BLE001
            err[clave] = f"{type(e).__name__}: {e}"
    btc, eth = toma("coinbase_btc", LQ.coinbase, "BTC-USD", 300), toma("coinbase_eth", LQ.coinbase, "ETH-USD", 300)
    if btc:
        cr["btc"] = serie_json([(d, c) for d, c, _ in btc])
    if eth:
        cr["eth"] = serie_json([(d, c) for d, c, _ in eth])
    if btc and eth:
        b = {d: c for d, c, _ in btc}
        cr["ethbtc"] = serie_json([(d, c / b[d]) for d, c, _ in eth if d in b])
    st = toma("stablecoins", LQ.stablecoins)
    if st:
        cr["stablecoins_B"] = serie_json(st)
    dv = toma("dvol", LQ.deribit_dvol, 370)
    if dv:
        cr["dvol"] = serie_json(dv)
    fu = toma("funding_btc", LQ.okx_funding, "BTC-USDT-SWAP")
    if fu:
        por_dia = {}
        for ts, r in fu:
            por_dia.setdefault(ts.date(), []).append(r)
        cr["funding_btc_anual_pct"] = serie_json([(d, sum(v) / len(v) * 3 * 365 * 100) for d, v in sorted(por_dia.items())])
    oi = toma("oi_btc", LQ.okx_oi, "BTC")
    if oi:
        cr["oi_btc"] = serie_json(oi)
    et = toma("etf_btc", etf_btc_serie)
    if et:
        cr["etf_btc_musd"] = serie_json(et)
    if not out and not cr:
        raise RuntimeError("ninguna serie respondió: " + json.dumps(err)[:300])
    return {"yahoo": out, "cripto": cr, "errores": err}


# ------------------------------------------------------------------ resumen (tesis por activo, plantillas deterministas)
def _monitor(nombre, archivo):
    """(M, E) del monitor: el calculado en este proceso o, si no, la última copia guardada (con su fecha)."""
    if nombre in _MON:
        return _MON[nombre], STAMP, True
    j = leer(archivo)
    if j and j.get("evaluacion"):
        return (j.get("metricas") or {}, j["evaluacion"]), j.get("generado_utc"), bool(j.get("ok"))
    return None, None, False


def etapa_resumen():
    """Tesis por activo con el MISMO motor del informe diario (por_activo.py): viento macro de la semana + veredicto del monitor propio
    (oro_xau, indices, liquidez_cripto). US30 y Russell salen del motor de índices (por_indice)."""
    import una_pagina
    import por_activo
    F, C = leer("fedwatch.json"), leer("calendario.json")
    fw = F if F and F.get("ok") else None
    if fw is None:
        try:
            import fedwatch
            fw = fedwatch.medir()
        except Exception:  # noqa: BLE001
            fw = None
    cal = C if C and C.get("eventos") else None
    P = una_pagina.construir(una_pagina.medir(1, fw), "nexora", cal, fw)
    try:
        P5 = una_pagina.construir(una_pagina.medir(5, fw), "nexora", cal, fw)
    except Exception:  # noqa: BLE001
        P5 = {}
    R, est = {}, {}
    for nombre, archivo in (("oro_xau", "oro.json"), ("indices", "indices.json"), ("liquidez_cripto", "liquidez.json")):
        v, cuando, ok = _monitor(nombre, archivo)
        if v:
            R[nombre] = v
        est[nombre] = {"calculado_utc": cuando, "ok": ok, "disponible": bool(v)}
    X = por_activo.construir(P, P5, R, "", por_activo.ACTIVOS_WEB)
    tes = {}
    for a, x in X.items():
        cs = (P.get("detalle_viento") or {}).get(a, [])
        tes[a] = {"etiqueta": x["sesgo"], "tesis": x["tesis"], "hoy": x["hoy"], "semana": x["semana"], "viento_semana": x["viento_semana"],
                  "propio": x["propio"], "motor_propio_nombre": por_activo.MOTOR_PROPIO.get(a), "motores": cs}
    P["tesis_activos"] = tes
    P["motores_propios"] = est
    P["sencillo_activos"] = por_activo.sencillo(X)
    P.pop("datos", None)
    # memoria permanente: tesis del día por activo (una fila por activo y día) para el registro de tesis y su verificación posterior
    px = {"Oro": "oro", "Bitcoin": "btc", "S&P 500": "spx", "Nasdaq 100": "ndx", "US30 · Dow Jones": "dji", "Russell 2000": "rut"}
    pr = (leer("precios.json") or {}).get("activos", {})
    csvlog.anadir("registro_tesis.csv", [{"fecha": dt.date.today().isoformat(), "activo": a, "tesis": t["etiqueta"],
                                          "puntuacion": por_activo.VIENTO_N.get(t["viento_semana"], 0) + por_activo.VEREDICTO_N.get((t["propio"] or {}).get("veredicto"), 0),
                                          "motores": f"viento semana: {t['viento_semana']}; motor propio: {(t['propio'] or {}).get('veredicto', 'SIN DATO')}",
                                          "precio_referencia": (pr.get(px.get(a)) or {}).get("valor", ""), "capturado_utc": STAMP}
                                         for a, t in tes.items()], ("fecha", "activo"))
    return P



# ------------------------------------------------------------------ ciclo y crédito
def etapa_ciclo():
    """Reglas y umbrales EXACTOS de ciclo.py (scripts originales de NEXORA). Aquí solo se añaden las series para los gráficos."""
    import ciclo
    S, err = ciclo.medir()
    R = ciclo.construir(S, err)
    if len(err) >= 6:
        raise RuntimeError("ciclo: demasiadas fuentes sin dato: " + json.dumps(err)[:300])

    def mm(m, n):  # serie mensual {AAAA-MM: v} → [[fecha, v]]
        return [[k + "-01", round(m[k], 4)] for k in sorted(m)[-n:]]
    curva = S.get("curva", {})
    R["series"] = {
        "oas": {k: serie_json(S[f"oas_{k}"]) for k in ("ig", "bbb", "hy", "ccc") if S.get(f"oas_{k}")},
        "ebp": mm(S.get("ebp", {}), 240), "ebp_prob": mm(S.get("ebp_prob", {}), 240), "curva_mensual": mm(curva, 240),
        "probit": [[k + "-01", round(ciclo.phi(-0.5333 - 0.6330 * curva[k]) * 100, 2)] for k in sorted(curva)[-240:]],
        "curva_diaria": serie_json(S["curva_diaria"]) if S.get("curva_diaria") else [],
        "nfci": serie_json(S["nfci_sem"][-260:]) if S.get("nfci_sem") else [], "sahm": mm(S.get("sahm", {}), 120),
        "claims": serie_json(S["claims_sem"][-260:]) if S.get("claims_sem") else []}
    R["umb_cred"] = ciclo.UMB_CRED
    R["tono"] = "neg" if R["fase"].startswith(("RECESIÓN", "RIESGO")) else "amb" if R["fase"].startswith("DESACEL") else "pos"
    cr = R["credito"]
    fila = {"fecha_captura": dt.date.today().isoformat(), "fase": R["fase"], "adelantadas_encendidas": R["senales_adelantadas_encendidas"],
            "adelantadas_total": R["senales_adelantadas_total"], "prob_curva_nyfed_pct": R["prob_recesion_curva_nyfed"] if R["prob_recesion_curva_nyfed"] is not None else "",
            "prob_ebp_fed_pct": R["prob_recesion_ebp_fed"] if R["prob_recesion_ebp_fed"] is not None else "",
            **{f"{k}_pb": (cr.get(k) or {}).get("pb", "") for k in ("ig", "bbb", "hy", "ccc")}, "estado_credito": R["estado_credito"],
            "senales": "".join("1" if x["encendida"] else "0" if x["encendida"] is not None else "?" for x in R["senales"])}
    csvlog.anadir("historico_ciclo.csv", [fila], ("fecha_captura",))
    return R


# ------------------------------------------------------------------ datos publicados con revisiones
def etapa_publicados():
    import datos_macro
    return datos_macro.actualizar(leer("calendario.json"))


# ------------------------------------------------------------------ régimen macro
def etapa_regimen():
    import regimen
    cal = leer("calendario.json")
    def ruta_si(n):  # los monitores ya calculados hoy se reutilizan (no se vuelven a descargar)
        return ruta(n) if (leer(n) or {}).get("evaluacion") else None
    R = regimen.medir(cripto=ruta_si("liquidez.json"), oro=ruta_si("oro.json"), indices=ruta_si("indices.json"))
    E = regimen.evaluar(R, cal if cal and cal.get("eventos") else None)
    E.pop("fedwatch", None)
    if "respaldo: LBMA no respondió" in json.dumps(E, ensure_ascii=False):  # que la etiqueta no diga LBMA si el oro viene de COMEX
        E = json.loads(json.dumps(E, ensure_ascii=False, default=str).replace("Oro (LBMA)", "Oro (COMEX GC=F, respaldo)"))
    csvlog.anadir("historico_regimen.csv", [{"fecha_captura": dt.date.today().isoformat(), "cuadrante": E["cuadrante"], "fuerza": E["fuerza"], "riesgo": E["riesgo"],
                                             "liquidez": E["liquidez"], "concordancia": E["concordancia"], "motor": E["motor_lectura"],
                                             "estados": " | ".join(f"{d['dimension']}={d['estado']}" for d in E["mapa"])}], ("fecha_captura",))
    return {"evaluacion": E, "errores": R.get("errores", {}), "monitores_fuente": {k: ("calculado en esta ejecución" if k in R else "SIN DATO") for k in ("cripto", "oro", "indices")}}


# ------------------------------------------------------------------ fase 4: sesgo de divisas, posicionamiento COT, noticias de bancos centrales
def etapa_divisas():
    import divisas
    D_ = divisas.medir()
    csvlog.anadir("historico_divisas.csv", [{"fecha_captura": dt.date.today().isoformat(), "divisa": m["clave"], "total": m["total"] if m["total"] is not None else "",
                                             "sesgo": m["sesgo"], "factores": " | ".join(f"{k}={v['puntos']}" for k, v in m["factores"].items())} for m in D_["monedas"]],
                  ("fecha_captura", "divisa"))
    return D_


def etapa_cot():
    import cot
    return cot.medir()


def etapa_noticias():
    import noticias
    return noticias.medir()


# ------------------------------------------------------------------ alertas (Telegram)
def etapa_alertas():
    import alertas
    return alertas.ejecutar()


# ------------------------------------------------------------------ principal
ETAPAS = {"precios": etapa_precios, "fedwatch": etapa_fedwatch, "tipos": etapa_tipos, "calendario": etapa_calendario,
          "liquidez": etapa_liquidez, "monitores": etapa_monitores, "series": etapa_series, "ciclo": etapa_ciclo, "publicados": etapa_publicados, "resumen": etapa_resumen,
          "regimen": etapa_regimen, "divisas": etapa_divisas, "cot": etapa_cot, "noticias": etapa_noticias, "alertas": etapa_alertas}
ORDEN = ["precios", "fedwatch", "tipos", "calendario", "liquidez", "monitores", "series", "ciclo", "publicados", "resumen", "regimen", "divisas", "cot", "noticias", "alertas"]
MODOS = {"horario": ["precios", "fedwatch", "tipos", "noticias", "alertas"], "diario": ORDEN, "todo": ORDEN}


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
    dur = round(time.time() - t0, 1)
    escribir("meta.json", {"actualizado_utc": STAMP, "modo": a.modo, "etapas": estado, "duracion_total_s": dur})
    # una fila por ejecución (garantiza que data/ crece en cada run)
    ok = [e for e in etapas if estado[e]["ok"]]
    csvlog.anadir("ejecuciones.csv", [{"capturado_utc": STAMP, "modo": a.modo, "evento": os.environ.get("GITHUB_EVENT_NAME", "local"),
                                       "etapas_ok": ",".join(ok), "etapas_fallo": ",".join(e for e in etapas if e not in ok), "duracion_s": dur}], ("capturado_utc", "modo"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
