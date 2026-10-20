#!/usr/bin/env python3
"""NEXORA TERMINAL · build.py
Ejecuta los monitores y escribe site/data/*.json (+ memoria permanente en data/*.csv).

Reglas: coste cero, sin LLM, sin claves de pago. Una fuente que falla NO rompe la web:
el JSON de esa etapa lleva ok=false, el error y, si existe, la última copia válida con su fecha.

Uso:  python engine/build.py --modo diario|horario|cierre|todo [--solo etapa,etapa]
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
import mensual as MS  # noqa: E402

MODO_EFECTIVO = ""  # lo fija main(): horario, cierre, diario, horario+cierre…
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
    ("wti", "Petróleo WTI", "CL=F", "Futuros WTI NYMEX, primer vencimiento (Yahoo Finance CL=F; serie empalmada)"),
    ("brent", "Petróleo Brent", "BZ=F", "Futuros Brent ICE, primer vencimiento (Yahoo Finance BZ=F; serie empalmada)"),
    # volatilidad implícita de los bonos del Tesoro (ICE BofA MOVE). Sin respaldo gratuito (ni FRED ni Cboe lo publican): si Yahoo falla = SIN DATO
    ("move", "MOVE (volatilidad de bonos)", "^MOVE", "ICE BofA MOVE (Yahoo Finance ^MOVE)"),
]


UA_WEB = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
          "Accept": "application/json"}
# Respaldo si Yahoo devuelve 429 desde las IP compartidas de Actions: serie FRED (con retraso, la fecha del dato se muestra siempre)
RESPALDO_FRED = {"^GSPC": "SP500", "^NDX": "NASDAQ100", "^DJI": "DJIA", "^VIX": "VIXCLS", "CL=F": "DCOILWTICO", "BZ=F": "DCOILBRENTEU"}


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
    # histórico recalculado con la regla de contrato v2 (el CSV anterior se conserva tal cual, calculado con la regla v1)
    csvlog.anadir("historico_fedwatch_v2.csv", [{**x, "capturado_utc": STAMP} for x in F.get("recalculo", [])], ("fecha_precios", "reunion"))
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
    """Último valor y el anterior. El interanual se calcula contra el MISMO MES del año anterior (mensual.py): si la fuente no publicó ese mes
    (IPC de octubre de 2025) el resultado es SIN DATO, nunca una comparación contra otro mes."""
    s = LQ.fred(sid, (dt.date.today() - dt.timedelta(days=900)).isoformat())
    if modo == "nivel":
        a, b = s[-1], s[-2]
        return {"periodo": a[0].isoformat(), "valor": a[1], "anterior": b[1], "anterior_periodo": b[0].isoformat()}

    def f(i):
        if modo == "yoy":
            return MS.var_pct(s, i, 12)
        if modo == "mom":
            return (s[i][1] / s[i - 1][1] - 1) * 100
        if modo == "diff":
            return s[i][1] - s[i - 1][1]
        if modo == "qoq_anual":
            return ((s[i][1] / s[i - 1][1]) ** 4 - 1) * 100
    a, b = f(-1), f(-2)
    if a is None:
        raise RuntimeError(f"SIN DATO: falta el mismo mes de hace 12 meses en la serie de la fuente ({s[-1][0].strftime('%Y-%m')}); no se estima")
    return {"periodo": s[-1][0].isoformat(), "valor": round(a, 2), "anterior": round(b, 2) if b is not None else None, "anterior_periodo": s[-2][0].isoformat()}


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
    # periodo ≠ publicación: la fecha de publicación solo se asigna si el evento YA ha salido y corresponde al último periodo mostrado (mensual.fecha_publicacion)
    tipo_de = {"nivel": "semana", "qoq_anual": "trimestre"}
    for nombre, sid, modo, _ in PUBLICADOS:
        v = pub.get(nombre)
        if v and not v.get("sin_dato"):
            fp = MS.fecha_publicacion(C["eventos"], [nombre.split(" (")[0].lower()], v["periodo"], tipo_de.get(modo, "mes"))
            if fp:
                v["fecha_publicacion"] = fp
    for e in C["eventos"]:
        for nombre, v in pub.items():
            if nombre.split(" (")[0].lower() in e["evento"].lower():
                e["publicado"] = v
                break
    C["ultimos_publicados"] = pub
    csvlog.anadir("eventos_macro.csv", [{"fecha": e["fecha"], "hora_madrid": e.get("hora_madrid") or "", "evento": e["evento"], "importancia": e.get("importancia", ""),
                                         "fuente": e.get("fuente", ""), "visto_utc": STAMP} for e in C["eventos"]], ("fecha", "evento"))
    try:
        import agenda
        agenda.escribir_json(C)  # tabla de importancia + hoy y próximos 7 días (site/data/agenda.json)
    except Exception as e:  # noqa: BLE001
        print("agenda.json:", type(e).__name__, str(e)[:80])
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
                   ("ECB", "ECBASSETSW"), ("BOJ", "JPNASSETS"), ("EURUSD", "DEXUSEU"), ("JPYUSD", "DEXJPUS"), ("NFCI", "NFCI"), ("M2", "M2SL"),
                   ("SOFR", "SOFR"), ("EFFR", "EFFR"), ("WLRRAL", "WLRRAL"), ("WLRRAFOIAL", "WLRRAFOIAL")):
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
    # SOFR (secured, FRED SOFR) junto al tipo efectivo de fondos federales (EFFR) y su diferencial en la última fecha con los dos datos
    if "SOFR" in ser and "EFFR" in ser:
        hist["sofr"], hist["effr"] = serie_json(ser["SOFR"]), serie_json(ser["EFFR"])
        e_ = dict(ser["EFFR"])
        comun = [(d, v) for d, v in ser["SOFR"] if d in e_]
        if comun:
            d, v = comun[-1]
            hist["sofr_effr"] = {"fecha": d.isoformat(), "sofr": v, "effr": e_[d], "spread_pb": round((v - e_[d]) * 100, 1),
                                 "sofr_ultima_fecha": ser["SOFR"][-1][0].isoformat(), "effr_ultima_fecha": ser["EFFR"][-1][0].isoformat(),
                                 "fuente": "FRED SOFR y EFFR (NY Fed), diarios; el diferencial usa la última fecha con los dos datos"}
    # Repos inversos TOTALES del H.4.1 (pasivo de la Fed, miércoles; incluye la cuenta de oficiales extranjeros) ≠ ON RRP (facilidad con contrapartes, RRPONTSYD)
    if "WLRRAL" in ser:
        hist["repos_inversos_totales_B"] = serie_json([(d, v / 1000) for d, v in ser["WLRRAL"]])
        ult = ser["WLRRAL"][-1]
        ext = dict(ser.get("WLRRAFOIAL", [])).get(ult[0])
        on = LQ.at_or_before(ser["RRP"], ult[0]) if "RRP" in ser else None
        hist["repos_inversos"] = {"fecha": ult[0].isoformat(), "total_B": round(ult[1] / 1000, 1), "extranjeros_B": round(ext / 1000, 1) if ext is not None else None,
                                  "otros_B": round((ult[1] - ext) / 1000, 1) if ext is not None else None,
                                  "on_rrp_B": on[1] if on else None, "on_rrp_fecha": on[0].isoformat() if on else None,
                                  "fuente": "FRED WLRRAL (H.4.1, nivel del miércoles), WLRRAFOIAL (cuenta de oficiales extranjeros e internacionales) y RRPONTSYD (ON RRP)"}
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
        # Variación a 12 meses SIN efecto divisa: cada balance en su moneda (WALCL en USD, ECB en EUR, JPNASSETS en JPY), ponderada por su tamaño
        # en USD en la fecha de referencia. La serie en USD mezcla la política monetaria con la depreciación del yen o del euro frente al dólar.
        try:
            f1 = dt.date.fromisoformat(glob[-1][0])
            f0 = f1 - dt.timedelta(days=365)
            comp = {}
            for k, sk, hk in (("fed", "WALCL", "balance_fed_T"), ("bce", "ECB", "bce_T"), ("boj", "BOJ", "boj_T")):
                a = LQ.at_or_before(ser[sk], f1)
                # referencia a 365 días de la ÚLTIMA observación de ese balance (el del BoJ es mensual y el del BCE semanal con otro día)
                b0 = LQ.at_or_before(ser[sk], a[0] - dt.timedelta(days=365)) if a else None
                w = next((v for d, v in reversed(hist[hk]) if d <= f0.isoformat()), None)
                usd_a = next((v for d, v in reversed(hist[hk]) if d <= f1.isoformat()), None)
                if not (a and b0 and w and usd_a) or ((a[0] - dt.timedelta(days=365)) - b0[0]).days > 40:
                    raise ValueError(f"sin referencia a 12 meses para {sk}")
                comp[k] = {"fecha": a[0].isoformat(), "ref_fecha": b0[0].isoformat(), "var_local_pct": round((a[1] / b0[1] - 1) * 100, 2),
                           "peso_ref_T": round(w, 3), "valor_T": round(usd_a, 3), "var_usd_pct": round((usd_a / w - 1) * 100, 2)}
            tw = sum(c["peso_ref_T"] for c in comp.values())
            for c in comp.values():
                c["peso"] = round(c["peso_ref_T"] / tw, 3)
            hist["liquidez_global_12m"] = {"fecha": f1.isoformat(), "ref_fecha": f0.isoformat(), "componentes": comp,
                                           "var_local_ponderada_pct": round(sum(c["var_local_pct"] * c["peso"] for c in comp.values()), 2)}
        except Exception as e:  # noqa: BLE001
            errs["liquidez_global_12m"] = f"{type(e).__name__}: {e}"
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


# ------------------------------------------------------------------ reevaluar: los tres monitores con el FedWatch de ESTA ejecución (sin descargar nada)
def etapa_reevaluar():
    """liquidez.json, oro.json e indices.json guardan sus métricas (descargadas en el build diario) y su evaluación, que cita las probabilidades de la Fed.
    evaluar() es una función pura de (métricas, fedwatch): se recalcula cada hora con fedwatch.json, de modo que toda cifra de la Fed de la web
    (monitores, resumen, régimen, contexto) sale de la misma fuente y la misma hora. Las métricas y su fecha (`generado_utc`) no se tocan."""
    import fedwatch
    import indices as IDX
    import oro_xau
    F = leer("fedwatch.json")
    fw = fedwatch.para_monitor(F) if F and F.get("ok") else None
    est = {}
    for arch, ev in (("liquidez.json", lambda M: LQ.evaluar(M, fw)), ("oro.json", lambda M: oro_xau.evaluar(M, fw)), ("indices.json", lambda M: IDX.evaluar(M, fw))):
        J = leer(arch)
        if not J or not J.get("metricas"):
            est[arch] = "SIN DATO (no hay métricas guardadas)"
            continue
        J["evaluacion"] = json.loads(json.dumps(ev(J["metricas"]), default=str, ensure_ascii=False))
        J["evaluado_utc"] = STAMP
        J["fedwatch_fecha_precios"] = (F or {}).get("fecha_precios")
        escribir(arch, J)
        est[arch] = "ok"
    return {"monitores": est, "fedwatch_fecha_precios": (F or {}).get("fecha_precios")}


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


def etapa_etf():
    """Flujos diarios de los ETF spot de BTC y ETH (Farside, validados). Memoria: data/historico_etf_flujos.csv, solo-añadir; un valor distinto para la misma
    fecha se guarda como fila nueva (revisión visible)."""
    import etf_flujos
    R = etf_flujos.medir()
    filas = [{"fecha": d, "activo": k, "total_musd": t, "capturado_utc": STAMP, "fuente": x["fuente"]}
             for k, x in R["etf"].items() if not x.get("sin_dato") for d, t in x["serie"]]
    csvlog.anadir("historico_etf_flujos.csv", filas, ("fecha", "activo", "total_musd"))
    return R


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
    # los flujos de ETF salen de su propia etapa (etf.json, engine/etf_flujos.py): una única fuente, validada fila a fila
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


# ------------------------------------------------------------------ registro de tesis (verificación posterior)
def etapa_tesis():
    """Lee data/registro_tesis.csv (solo se añade) y comprueba cada tesis contra el precio a 1, 5 y 20 sesiones.
    Regla fija: ALCISTA acierta si el precio sube frente al de referencia; BAJISTA si baja; «SIN TESIS» no se evalúa.
    Si todavía no hay sesiones suficientes el horizonte queda PENDIENTE (nunca se estima)."""
    px = {"Oro": "oro", "Bitcoin": "btc", "S&P 500": "spx", "Nasdaq 100": "ndx", "US30 · Dow Jones": "dji", "Russell 2000": "rut"}
    pr = (leer("precios.json") or {}).get("activos", {})
    filas = csvlog.leer("registro_tesis.csv")
    HOR = (1, 5, 20)
    out, resumen = [], {}
    for r in sorted(filas, key=lambda x: (x["fecha"], x["activo"])):
        et = r.get("tesis", "")
        dire = 1 if et.startswith("ALCISTA") else -1 if et.startswith("BAJISTA") else 0
        serie = (pr.get(px.get(r["activo"])) or {}).get("serie") or []
        idx = next((i for i, (d, _) in enumerate(serie) if d >= r["fecha"]), None)
        try:
            ref = float(r.get("precio_referencia") or "")
        except ValueError:
            ref = serie[idx][1] if idx is not None else None
        h = {}
        for n in HOR:
            j = None if idx is None else idx + n
            if dire == 0:
                h[str(n)] = {"estado": "NO EVALUADA"}
            elif ref is None or j is None or j >= len(serie):
                h[str(n)] = {"estado": "PENDIENTE"}
            else:
                ret = (serie[j][1] / ref - 1) * 100
                h[str(n)] = {"estado": "ACIERTO" if ret * dire > 0 else "FALLO", "ret_pct": round(ret, 2), "fecha": serie[j][0], "precio": serie[j][1]}
        out.append({"fecha": r["fecha"], "activo": r["activo"], "tesis": et, "puntuacion": r.get("puntuacion"), "motores": r.get("motores"),
                    "precio_referencia": ref, "capturado_utc": r.get("capturado_utc"), "horizontes": h})
        if dire:
            for n in HOR:
                e = h[str(n)]["estado"]
                if e in ("ACIERTO", "FALLO"):
                    b = resumen.setdefault(r["activo"], {}).setdefault(str(n), {"aciertos": 0, "evaluadas": 0})
                    b["evaluadas"] += 1
                    b["aciertos"] += e == "ACIERTO"
    return {"filas": out[::-1], "n_filas": len(out), "resumen": resumen, "horizontes": list(HOR),
            "regla": "ALCISTA acierta si el precio a 1, 5 o 20 sesiones está por encima del precio de referencia del día de la tesis; BAJISTA si está por debajo. «SIN TESIS» no se evalúa. Sin sesiones suficientes: PENDIENTE.",
            "fuente": "data/registro_tesis.csv (solo se añade) + cierres de Yahoo Finance de precios.json"}


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
    R = regimen.medir(cripto=ruta_si("liquidez.json"), oro=ruta_si("oro.json"), indices=ruta_si("indices.json"), fedwatch_json=leer("fedwatch.json"))
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


# ------------------------------------------------------------------ fase 6: riesgo de cola (SKEW), semis vs software, gamma de índices
def etapa_skew():
    import skew
    M = skew.medir(leer("ciclo.json"))
    skew.guardar_historico(M)
    return M


def etapa_semis():
    import semis
    return semis.medir()


def etapa_gamma():
    """GEX de SPX+SPY (ES) y NDX+QQQ (NQ) desde la cadena retrasada de Cboe. Solo se guarda histórico con snapshot del CIERRE de Nueva York;
    si la ejecución cae en horario de mercado se conserva el último cierre válido en lugar de sobrescribirlo con un dato intradía."""
    import gamma
    import precios
    M = gamma.medir()
    prev = leer("gamma.json") or {}
    descartados = {}
    for k, x in list(M["indices"].items()):
        if not x["cierre_confirmado"]:
            p = (prev.get("indices") or {}).get(k)
            if p and p.get("cierre_confirmado"):
                descartados[k] = {"snapshot_et": x["ultima_operacion_et"], "motivo": "snapshot intradía: se conserva el último cierre de Nueva York"}
                M["indices"][k] = p
    M["descartados_intradia"] = descartados
    # el histórico solo lo escribe la ejecución de CIERRE (21:30 UTC, tras el cierre de NY y antes de la actualización matinal del interés abierto) y solo
    # con la sesión del día; el diario y el horario muestran la gamma en la web pero no escriben (el mismo cierre medido por la mañana da otro GEX)
    cierre_hoy = "cierre" in MODO_EFECTIVO and all(x.get("sesion") == NOW.strftime("%Y-%m-%d") for x in M["indices"].values())
    M["historico_escrito"] = bool(cierre_hoy)
    if cierre_hoy:
        gamma.guardar_historico(M, STAMP)
    hist = csvlog.leer("historico_gamma.csv")
    rev, err = {}, {}
    for clave, cfg in gamma.INDICES.items():
        try:
            bars, _ = precios.diario(cfg["yahoo_fut"], "3mo")
            precios.pausa()
            rev[clave] = gamma.revisar(clave, hist, bars)
        except Exception as e:  # noqa: BLE001
            err[clave] = f"{type(e).__name__}: {str(e)[:100]}"
            rev[clave] = {"sesiones": [], "resumen": {}, "sin_dato": True}
    M["revision"] = rev
    M["errores_revision"] = err
    M["sesiones_guardadas"] = len({r["fecha_sesion"] for r in hist})
    return M


# ------------------------------------------------------------------ fase 7: bancos centrales del mundo (mapa) y tono hawkish/dovish
def etapa_bancos():
    import bancos
    return bancos.medir(leer("liquidez.json"))


def etapa_tono():
    import tono
    M = tono.medir()
    errs = M.get("errores") or {}
    if len(errs) > 25:  # los fallos repetidos de textos sin contenido no deben inflar el JSON: se cuenta y se muestran los primeros
        M["errores_total"] = len(errs)
        M["errores"] = dict(list(errs.items())[:25])
    return M


# ------------------------------------------------------------------ fase 8: reacción a eventos (IPC, NFP, PCE, FOMC)
def etapa_reacciones():
    import reaccion
    return reaccion.etapa()


# ------------------------------------------------------------------ contexto.json: resumen compacto de todo el terminal (para informes)
def etapa_contexto():
    import contexto
    return contexto.construir()


# ------------------------------------------------------------------ consumo (#/consumo): XLY/XLP, RSPD/RSPS, datos reales de FRED y tesis de consumo
def etapa_consumo():
    import consumo
    return consumo.etapa()


# ------------------------------------------------------------------ consumo · tres usos del ratio (filtro SMA 200, rotación frente a SPY, divergencia) y sus señales del marcador
def etapa_consumo_ratio():
    import consumo_ratio
    return consumo_ratio.etapa()


# ------------------------------------------------------------------ petróleo (#/petroleo): WTI/Brent, curva, inventarios EIA, COT, tesis con reglas fijas
def etapa_petroleo():
    import petroleo
    return petroleo.etapa()


# ------------------------------------------------------------------ gamma del oro (GLD, referencia → XAU/USD)
def etapa_gamma_oro():
    import gamma_oro
    cierre = "cierre" in MODO_EFECTIVO
    return gamma_oro.etapa(escribir_cierre=cierre, hoy=NOW.strftime("%Y-%m-%d"), stamp=STAMP, previo=leer("gamma_oro.json"))


# ------------------------------------------------------------------ marcador «gamma intradía» (MFE/MAE a 15/30/60 min de los avisos enviados)
def etapa_gamma_intradia():
    import gamma_intradia
    return gamma_intradia.etapa()


# ------------------------------------------------------------------ marcador de aciertos de señales (registro solo-añadir + evaluación a T+1/T+5/T+20)
def etapa_marcador():
    import marcador
    return marcador.etapa(modo=MODO_EFECTIVO)


# ------------------------------------------------------------------ integridad de datos (vigilante de publicaciones, segunda fuente BLS, semáforo por bloque)
def etapa_integridad():
    import integridad
    return integridad.etapa()


# ------------------------------------------------------------------ alertas (Telegram)
def etapa_alertas():
    import alertas
    return alertas.ejecutar()


# ------------------------------------------------------------------ principal
ETAPAS = {"precios": etapa_precios, "fedwatch": etapa_fedwatch, "tipos": etapa_tipos, "calendario": etapa_calendario,
          "liquidez": etapa_liquidez, "monitores": etapa_monitores, "series": etapa_series, "etf": etapa_etf, "ciclo": etapa_ciclo, "publicados": etapa_publicados, "resumen": etapa_resumen, "tesis": etapa_tesis,
          "regimen": etapa_regimen, "reevaluar": etapa_reevaluar, "divisas": etapa_divisas, "cot": etapa_cot, "noticias": etapa_noticias,
          "bancos": etapa_bancos, "tono": etapa_tono,
          "skew": etapa_skew, "semis": etapa_semis, "gamma": etapa_gamma, "gamma_oro": etapa_gamma_oro, "alertas": etapa_alertas, "reacciones": etapa_reacciones, "consumo": etapa_consumo, "consumo_ratio": etapa_consumo_ratio, "petroleo": etapa_petroleo, "gamma_intradia": etapa_gamma_intradia, "marcador": etapa_marcador, "integridad": etapa_integridad, "contexto": etapa_contexto}
ORDEN = ["precios", "fedwatch", "tipos", "calendario", "liquidez", "monitores", "series", "etf", "ciclo", "publicados", "reevaluar", "resumen", "tesis", "regimen", "divisas", "cot", "noticias",
         "bancos", "tono", "skew", "semis", "gamma", "gamma_oro", "consumo", "consumo_ratio", "petroleo", "alertas", "reacciones", "gamma_intradia", "marcador", "integridad", "contexto"]
# horario: el SKEW (Cboe) se publica tras el cierre, por eso entra aquí para que la alerta salga en la hora siguiente; gamma NO (solo al cierre).
# cierre (cron 21:30 UTC, tras el cierre de Nueva York): snapshot de opciones, semis/software y SKEW del día.
# calendario y publicados entran en el horario porque el día de una publicación (IPC, PPI, ventas…) el dato sale a las 12:30-13:30 UTC y la web no puede esperar
# al build diario; calendario escribe también site/data/agenda.json (sin esto la página Agenda mostraba el «hoy» de ayer).
MODOS = {"horario": ["precios", "fedwatch", "tipos", "calendario", "publicados", "reevaluar", "resumen", "tesis", "regimen", "etf", "noticias", "skew", "alertas", "gamma_intradia", "marcador", "integridad", "contexto"],
         "cierre": ["precios", "semis", "bancos", "tono", "skew", "gamma", "gamma_oro", "consumo", "consumo_ratio", "petroleo", "alertas", "gamma_intradia", "marcador", "integridad", "contexto"], "diario": ORDEN, "todo": ORDEN}


def escalar(modo, estado, ahora=None):
    """Los crones de GitHub no están garantizados (el 15-oct el diario salió 4,6 h tarde y el cierre 2,3 h tarde; el 16-oct no salió el diario) y cron-job.org
    solo dispara el modo horario. Si ya toca el build DIARIO (≥ 05:30 UTC) o el CIERRE (≥ 21:30 UTC) y hoy todavía no se ha completado, la ejecución
    horaria incluye esas etapas. Devuelve (modo_efectivo, etapas_extra). Sin efecto fuera del modo horario ni con --solo."""
    if modo != "horario":
        return modo, []
    ahora = ahora or NOW
    hoy = ahora.strftime("%Y-%m-%d")
    hm = ahora.strftime("%H:%M")

    def hecho(etapa):  # «ejecutada» (no «ok»): una fuente caída no debe relanzar el build completo cada hora
        return str((estado.get(etapa) or {}).get("ejecutada_utc") or "")[:10] >= hoy
    if hm >= "05:30" and not hecho("ciclo"):
        return "horario+diario", MODOS["diario"]
    if hm >= "21:30" and not hecho("gamma"):
        return "horario+cierre", MODOS["cierre"]
    return modo, []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modo", default="diario", choices=list(MODOS))
    ap.add_argument("--solo", default="")
    a = ap.parse_args()
    estado = (leer("meta.json") or {}).get("etapas", {})
    modo_ef, extra = (a.modo, []) if a.solo else escalar(a.modo, estado)
    global MODO_EFECTIVO
    MODO_EFECTIVO = modo_ef
    if extra:
        print(f"== modo {a.modo} escalado a {modo_ef}: el build programado de hoy no se ha completado", flush=True)
    etapas = [e for e in ORDEN if e in (a.solo.split(",") if a.solo else MODOS[a.modo] + extra)]
    t0 = time.time()
    for e in etapas:
        print(f"== {e}", flush=True)
        r = con_respaldo(f"{e}.json", ETAPAS[e])
        r["ejecutada_utc"] = STAMP
        if r["ok"]:
            r["ultimo_ok_utc"] = STAMP
        else:
            r["ultimo_ok_utc"] = estado.get(e, {}).get("ultimo_ok_utc")
        estado[e] = r
        escribir("meta.json", {"actualizado_utc": STAMP, "modo": modo_ef, "etapas": estado, "duracion_total_s": round(time.time() - t0, 1)})  # contexto.json lee la frescura de aquí
        print(f"   {'OK' if r['ok'] else 'FALLO'} {r['duracion_s']} s {r['error'] or ''}", flush=True)
    dur = round(time.time() - t0, 1)
    escribir("meta.json", {"actualizado_utc": STAMP, "modo": modo_ef, "etapas": estado, "duracion_total_s": dur})
    if "contexto" in etapas and estado["contexto"]["ok"]:
        # memoria permanente: la foto del sistema de esta hora, tal como queda publicada (no rompe el build si falla)
        import historico_contexto
        publicado = leer("contexto.json")
        if publicado:
            historico_contexto.archivar(publicado)
    # una fila por ejecución (garantiza que data/ crece en cada run)
    ok = [e for e in etapas if estado[e]["ok"]]
    csvlog.anadir("ejecuciones.csv", [{"capturado_utc": STAMP, "modo": modo_ef, "evento": os.environ.get("GITHUB_EVENT_NAME", "local"),
                                       "etapas_ok": ",".join(ok), "etapas_fallo": ",".join(e for e in etapas if e not in ok), "duracion_s": dur}], ("capturado_utc", "modo"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
