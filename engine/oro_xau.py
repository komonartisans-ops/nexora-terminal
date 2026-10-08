#!/usr/bin/env python3
"""
NEXORA · Monitor XAU/USD — fiel a la «Chuleta completa — Cómo leer el oro (XAU/USD)» del usuario.

Documento de referencia (Oro_XAU/fuentes_pdf): CH = Chuleta completa, 7 secciones.
  §1 Panel principal: 17 datos con su lectura si baja / si sube (direcciones literales de CH).
  §2 Comparaciones clave: 8 pares.
  §3 Confluencia favorable / contraria / mixto.
  §4 De la macro a la entrada: 8 pasos (1-6 automatizables; 7-8 manuales: footprint/DOM).
  §5 Frecuencia de revisión.
  §6 Las 10 preguntas antes de una operación (1-8 se responden con datos; 9 con niveles; 10 manual).
  §7 Chuleta de 60 segundos: ORO ↑ / ORO ↓.

Los UMBRALES numéricos NO están en la chuleta (solo da direcciones): son CRITERIO NEXORA, fijos y publicados.
Horizonte de las señales macro: 1 semana (5 sesiones), coherente con «cambio diario/semanal» de CH; la liquidez
usa 4 semanas y 3 meses (CH: «WRESBAL, tendencia 1M/3M»), con los mismos umbrales que el monitor cripto.

Precio: LBMA Gold Price PM (referencia oficial diaria, ICE Benchmark Administration vía LBMA) para cierres y
tendencia; XAUT (OKX) y PAXG (Coinbase) como proxy intradía y para máximos/mínimos (tokens respaldados por oro,
cotizan 24/7; se etiquetan como proxy). Uso: python oro_xau.py [--out DIR]. Requiere openpyxl (GLD).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from liquidez_cripto import (TODAY, UMBRAL as U_LIQ, at_or_before, change, dts_tga, dxy_replica, ecb_fx,  # noqa: E402
                             fred, get, get_json, nyfed_rrp, nyfed_sofr, safe)

# ----------------------------------------------------------------- UMBRALES (CRITERIO NEXORA)
U = {
    "dxy_pct_1s": 0.3,        # DXY ↑/↓ si varía más de ±0,3 % en 5 sesiones
    "t2y_pb_1s": 5.0,         # 2Y ↑/↓ si ±5 pb en 5 sesiones
    "t10y_pb_1s": 5.0,
    "t10y_rapido_pb_1s": 10.0,  # CH: «puede presionar, especialmente si sube rápido»
    "real_pb_1s": 5.0,
    "be_pb_1s": 3.0,
    "nfci_4s": 0.02,
    "vix_pct_1s": 20.0, "vix_alto": 25.0,
    "gld_t_1s": 3.0, "gld_t_4s": 10.0,
    "velocidad_z": 1.5,       # «rápido» si el cambio de 5 sesiones supera 1,5 desviaciones típicas del último año
    "oro_sma": 50,            # precio confirma: sobre/bajo la media de 50 sesiones y 20 sesiones en el mismo signo
    "petroleo_pct_1s": 5.0,
    "plata_pct_1s": 1.0,
}
U.update({k: U_LIQ[k] for k in ("reservas_pct_4s", "tga_b_4s", "rrp_b_4s", "rrp_agotado_b")})

FAV, CON, NEU, SD, CTX = "FAVORABLE", "DESFAVORABLE", "NEUTRAL", "SIN DATO", "CONTEXTO"


# ----------------------------------------------------------------- descargas
def treasury(kind: str, years: int = 2):
    """Curvas oficiales del Tesoro. kind: 'nominal' (Daily Par Yield Curve) o 'real' (Daily Par Real Yield Curve)."""
    typ = "daily_treasury_yield_curve" if kind == "nominal" else "daily_treasury_real_yield_curve"
    out = {}
    for y in range(TODAY.year - years + 1, TODAY.year + 1):
        raw = get("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/"
                  f"{y}/all?type={typ}&field_tdr_date_value={y}&page&_format=csv").decode()
        for row in csv.DictReader(io.StringIO(raw)):
            try:
                d = dt.datetime.strptime(row["Date"], "%m/%d/%Y").date()
            except (ValueError, KeyError):
                continue
            rec = {}
            for k, v in row.items():
                if k != "Date" and v not in ("", None):
                    try:
                        rec[k.strip()] = float(v)
                    except ValueError:
                        pass
            out[d] = rec
    return dict(sorted(out.items()))


def lbma(metal: str = "gold_pm", col: int = 0):
    """LBMA Precious Metal Prices (ICE Benchmark Administration). v = [USD, GBP, EUR] por onza."""
    rows = get_json(f"https://prices.lbma.org.uk/json/{metal}.json")
    return [(dt.date.fromisoformat(r["d"]), float(r["v"][col])) for r in rows
            if r.get("v") and len(r["v"]) > col and r["v"][col]]


def yahoo_gc(rango: str = "2y"):
    """Respaldo del oro cuando LBMA no responde (403): futuros COMEX GC=F, cierre diario, Yahoo Finance (sin clave)."""
    last = None
    for host in ("query2", "query1"):
        try:
            import json as _json
            import urllib.request as _ur
            rq = _ur.Request(f"https://{host}.finance.yahoo.com/v8/finance/chart/GC%3DF?range={rango}&interval=1d",
                             headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json"})
            with _ur.urlopen(rq, timeout=30) as _r:
                j = _json.loads(_r.read().decode("utf-8"))
            r = j["chart"]["result"][0]
            pts = [(dt.datetime.fromtimestamp(t, dt.timezone.utc).date(), float(c)) for t, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]) if c is not None]
            if len(pts) > 60:
                return pts
        except Exception as e:  # noqa: BLE001
            last = e
    raise last or RuntimeError("Yahoo GC=F sin datos")


def ecb_ccy(ccy: str, days_back: int = 420):
    """Tipo de referencia BCE (divisa por EUR)."""
    start = (TODAY - dt.timedelta(days=days_back)).isoformat()
    raw = get(f"https://data-api.ecb.europa.eu/service/data/EXR/D.{ccy}.EUR.SP00.A?startPeriod={start}&format=csvdata").decode()
    return {dt.date.fromisoformat(r["TIME_PERIOD"]): float(r["OBS_VALUE"]) for r in csv.DictReader(io.StringIO(raw)) if r.get("OBS_VALUE")}


def sge_shau():
    """Shanghai Gold Benchmark Price (SHAU), CNY/gramo, subasta de mediodía (14:15 Pekín). Shanghai Gold Exchange."""
    import urllib.request
    req = urllib.request.Request("https://en.sge.com.cn/graph/DayilyJzj", data=b"", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        j = json.loads(r.read().decode("utf-8"))
    tz = dt.timedelta(hours=8)  # marcas de tiempo a medianoche de Pekín
    return sorted(((dt.datetime.utcfromtimestamp(t / 1000) + tz).date(), float(v)) for t, v in j["wp"] if v)


def okx_ohlc(inst: str = "XAUT-USDT", n: int = 300):
    """Velas diarias UTC completas (sin la del día en curso). [(fecha, o, h, l, c)]"""
    out, after = {}, ""
    while len(out) < n:
        j = get_json(f"https://www.okx.com/api/v5/market/history-candles?instId={inst}&bar=1Dutc&limit=100{after}")["data"]
        if not j:
            break
        for r in j:
            if r[8] == "1":
                d = dt.datetime.utcfromtimestamp(int(r[0]) / 1000).date()
                out[d] = (d, float(r[1]), float(r[2]), float(r[3]), float(r[4]))
        after = f"&after={j[-1][0]}"
    return [out[d] for d in sorted(out)]


def okx_last(inst: str = "XAUT-USDT"):
    t = get_json(f"https://www.okx.com/api/v5/market/ticker?instId={inst}")["data"][0]
    return {"precio": float(t["last"]), "hora_utc": dt.datetime.utcfromtimestamp(int(t["ts"]) / 1000).strftime("%Y-%m-%d %H:%M"),
            "max24h": float(t["high24h"]), "min24h": float(t["low24h"])}


def coinbase_last(product: str = "PAXG-USD"):
    t = get_json(f"https://api.exchange.coinbase.com/products/{product}/ticker")
    return {"precio": float(t["price"]), "hora_utc": t["time"][:16].replace("T", " ")}


def cboe_vix():
    raw = get("https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv").decode()
    out = []
    for row in csv.DictReader(io.StringIO(raw)):
        try:
            out.append((dt.datetime.strptime(row["DATE"], "%m/%d/%Y").date(), float(row["CLOSE"])))
        except (ValueError, KeyError):
            continue
    return out[-400:]


def gld_holdings():
    """SPDR Gold Shares (GLD): toneladas de oro en el trust, diario desde 2004 (World Gold Trust Services)."""
    import openpyxl
    raw = get("https://api.spdrgoldshares.com/api/v1/historical-archive?product=gld&exchange=NYSE&lang=en", timeout=90)
    wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    ws = next(w for w in wb.worksheets if "Archive" in w.title or "Historical" in w.title)
    rows = list(ws.iter_rows(values_only=True))
    hdr = [str(h or "").strip() for h in rows[0]]
    it, iv = hdr.index("Tonnes of Gold"), hdr.index("Daily Share Volume")
    out = []
    for r in rows[1:]:
        try:
            d = dt.datetime.strptime(str(r[0]).strip(), "%d-%b-%Y").date()
            if r[it] not in (None, "", "HOLIDAY"):
                out.append((d, float(r[it]), float(r[iv] or 0)))
        except (ValueError, TypeError):
            continue
    return out


def cftc_gold(n: int = 160):
    """CFTC Disaggregated Futures Only, COMEX Gold (088691). Posiciones del martes, publicado el viernes."""
    rows = get_json("https://publicreporting.cftc.gov/resource/72hh-3qpy.json?cftc_contract_market_code=088691"
                    f"&$order=report_date_as_yyyy_mm_dd%20DESC&$limit={n}")
    out = []
    for r in rows:
        g = lambda k: int(float(r.get(k) or 0))  # noqa: E731
        out.append({"fecha": r["report_date_as_yyyy_mm_dd"][:10],
                    "mm_neto": g("m_money_positions_long_all") - g("m_money_positions_short_all"),
                    "mm_largos": g("m_money_positions_long_all"), "mm_cortos": g("m_money_positions_short_all"),
                    "comerciales_neto": (g("prod_merc_positions_long") + g("swap_positions_long_all"))
                                        - (g("prod_merc_positions_short") + g("swap__positions_short_all")),
                    "oi": g("open_interest_all")})
    return sorted(out, key=lambda x: x["fecha"])


# ----------------------------------------------------------------- utilidades
def serie(d: dict, key: str):
    return [(k, v[key]) for k, v in d.items() if key in v]


def delta_n(s, n: int):
    """Cambio entre la última observación y la de n observaciones antes."""
    if not s or len(s) <= n:
        return None
    return s[-1][1] - s[-1 - n][1]


def pct_n(s, n: int):
    if not s or len(s) <= n or not s[-1 - n][1]:
        return None
    return (s[-1][1] / s[-1 - n][1] - 1) * 100


def z_vel(s, n: int = 5, pct: bool = False, lookback: int = 250):
    """Velocidad: cambio de n sesiones frente a la desviación típica de cambios de n sesiones del último año."""
    if not s or len(s) < lookback + n + 1:
        return None
    vals = [x[1] for x in s[-(lookback + n + 1):]]
    ch = [((vals[i] / vals[i - n] - 1) * 100 if pct else vals[i] - vals[i - n]) for i in range(n, len(vals))]
    sd = statistics.pstdev(ch[:-1])
    return ch[-1] / sd if sd else None


def sma(s, n):
    return statistics.mean(x[1] for x in s[-n:]) if s and len(s) >= n else None


def dirv(x, tol):
    if x is None:
        return "?"
    return "↑" if x > tol else "↓" if x < -tol else "→"


def corr(a, b):
    if len(a) < 10:
        return None
    ma, mb = statistics.mean(a), statistics.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return num / den if den else None


def r2(x, d=2):
    return None if x is None else round(x, d)


# ----------------------------------------------------------------- medición
def medir():
    M, err = {"generado_utc": dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "fuente_chuleta": "Chuleta completa — Cómo leer el oro (XAU/USD)"}, {}

    def grab(name, fn, *a, **k):
        v, e = safe(fn, *a, **k)
        if e:
            err[name] = e
        return v

    gold = grab("lbma_oro", lbma, "gold_pm")
    oro_respaldo = False
    if not gold:  # LBMA da 403 desde algunas IP: se usa el oro COMEX (GC=F) y se indica en la fuente
        gold = grab("yahoo_gc_f", yahoo_gc)
        oro_respaldo = bool(gold)
    silver = grab("lbma_plata", lbma, "silver")
    nom = grab("tesoro_nominal", treasury, "nominal")
    real = grab("tesoro_real", treasury, "real")
    fx = grab("bce_fx", ecb_fx, 420)
    nfci = grab("nfci", fred, "NFCI", "2024-01-01")
    vix = grab("vix", cboe_vix)
    tga = grab("tga", dts_tga, 130)
    rrp = grab("rrp", nyfed_rrp, 130)
    res = grab("reservas", fred, "WRESBAL", "2024-06-01")
    m2 = grab("m2", fred, "M2SL", "2023-01-01")
    cot = grab("cftc_oro", cftc_gold)
    gld = grab("gld", gld_holdings)
    brent = grab("brent", fred, "DCOILBRENTEU", "2025-06-01")
    wti = grab("wti", fred, "DCOILWTICO", "2025-06-01")
    xaut = grab("xaut_ohlc", okx_ohlc, "XAUT-USDT", 380)
    xaut_last = grab("xaut_ultimo", okx_last)
    paxg_last = grab("paxg_ultimo", coinbase_last)
    sofr = grab("sofr", nyfed_sofr, 30)
    iorb = grab("iorb", fred, "IORB", "2025-01-01")
    gold_eur = grab("lbma_oro_eur", lbma, "gold_pm", 2)
    gold_gbp = grab("lbma_oro_gbp", lbma, "gold_pm", 1)
    gold_am = grab("lbma_oro_am", lbma, "gold_am", 0)
    cny = grab("bce_cny", ecb_ccy, "CNY", 420)
    shau = grab("sge_shau", sge_shau)
    effr = grab("effr", fred, "EFFR", "2025-01-01")

    # --- precio
    if gold:
        g = gold[-400:]
        M["oro"] = {"lbma_pm": g[-1][1], "fecha": g[-1][0].isoformat(), "1d_pct": r2(pct_n(g, 1)), "5d_pct": r2(pct_n(g, 5)),
                    "20d_pct": r2(pct_n(g, 20)), "60d_pct": r2(pct_n(g, 60)), "sma50": r2(sma(g, 50)), "sma200": r2(sma(g, 200)),
                    "max_52s": max(x[1] for x in g[-252:]), "min_52s": min(x[1] for x in g[-252:]),
                    "ytd_pct": r2((g[-1][1] / next(x[1] for x in g if x[0].year == g[-1][0].year) - 1) * 100),
                    "fuente": ("Futuros oro COMEX GC=F (Yahoo Finance), USD/oz · respaldo: LBMA no respondió" if oro_respaldo else "LBMA Gold Price PM (ICE Benchmark Administration), USD/oz"),
                    "respaldo": oro_respaldo}
        M["oro"]["vs_max_52s_pct"] = r2((g[-1][1] / M["oro"]["max_52s"] - 1) * 100)
    if xaut_last or paxg_last:
        M["oro_intradia"] = {"xaut_okx": xaut_last, "paxg_coinbase": paxg_last,
                             "nota": "Proxy: tokens respaldados por oro físico, cotizan 24/7; pueden desviarse unas décimas del spot XAU/USD."}
        if xaut_last and paxg_last:
            M["oro_intradia"]["divergencia_pct"] = r2((xaut_last["precio"] / paxg_last["precio"] - 1) * 100, 3)

    # --- DXY
    if fx:
        dx = dxy_replica(fx)
        M["dxy"] = {"valor": r2(dx[-1][1]), "fecha": dx[-1][0].isoformat(), "1d_pct": r2(pct_n(dx, 1)), "5d_pct": r2(pct_n(dx, 5)),
                    "20d_pct": r2(pct_n(dx, 20)), "vel_z": r2(z_vel(dx, 5, True)), "metodo": "Réplica ICE sobre tipos de referencia del BCE (14:15 CET)"}
        M["_dxy_serie"] = dx
    # --- tipos
    if nom:
        for k, lab in (("2 Yr", "2Y"), ("5 Yr", "5Y"), ("10 Yr", "10Y"), ("30 Yr", "30Y")):
            s = serie(nom, k)
            M[f"t{lab}"] = {"valor": s[-1][1], "fecha": s[-1][0].isoformat(), "1d_pb": r2(delta_n(s, 1) * 100, 0),
                            "5d_pb": r2(delta_n(s, 5) * 100, 0), "20d_pb": r2(delta_n(s, 20) * 100, 0),
                            "vel_z": r2(z_vel(s, 5)), "fuente": "U.S. Treasury, Daily Par Yield Curve"}
        M["_t10_serie"] = serie(nom, "10 Yr")
    if real:
        for k, lab in (("5 YR", "5Y"), ("10 YR", "10Y")):
            s = serie(real, k)
            M[f"real{lab}"] = {"valor": s[-1][1], "fecha": s[-1][0].isoformat(), "1d_pb": r2(delta_n(s, 1) * 100, 0),
                               "5d_pb": r2(delta_n(s, 5) * 100, 0), "20d_pb": r2(delta_n(s, 20) * 100, 0),
                               "vel_z": r2(z_vel(s, 5)), "fuente": "U.S. Treasury, Daily Par Real Yield Curve (TIPS)"}
        M["_real10_serie"] = serie(real, "10 YR")
    if nom and real:
        for n_k, r_k, lab in (("5 Yr", "5 YR", "5Y"), ("10 Yr", "10 YR", "10Y")):
            common = [d for d in nom if n_k in nom[d] and d in real and r_k in real[d]]
            s = [(d, nom[d][n_k] - real[d][r_k]) for d in common]
            M[f"be{lab}"] = {"valor": r2(s[-1][1]), "fecha": s[-1][0].isoformat(), "5d_pb": r2(delta_n(s, 5) * 100, 0),
                             "20d_pb": r2(delta_n(s, 20) * 100, 0), "fuente": "Nominal − real, U.S. Treasury (misma fecha)"}
    # --- condiciones y riesgo
    if nfci:
        M["nfci"] = {"valor": nfci[-1][1], "fecha": nfci[-1][0].isoformat(), "1s": r2(delta_n(nfci, 1), 3), "4s": r2(delta_n(nfci, 4), 3),
                     "fuente": "Chicago Fed NFCI (FRED), semanal; negativo = más laxo que la media"}
    if vix:
        M["vix"] = {"valor": vix[-1][1], "fecha": vix[-1][0].isoformat(), "5d_pct": r2(pct_n(vix, 5)), "1d_pct": r2(pct_n(vix, 1)),
                    "fuente": "Cboe, VIX History"}
    # --- liquidez (mismas reglas que el monitor cripto)
    if tga:
        c = change([(d, v["cierre"] / 1000) for d, v in tga], 28)
        c3 = change([(d, v["cierre"] / 1000) for d, v in tga], 91)
        M["tga"] = {"valor_B": r2(c["valor"], 1), "fecha": c["fecha"], "4s_B": r2(c["delta"], 1), "3m_B": r2(c3["delta"], 1) if c3 else None,
                    "fuente": "U.S. Treasury, Daily Treasury Statement"}
    if rrp:
        c = change(rrp, 28)
        M["rrp"] = {"valor_B": r2(c["valor"], 1), "fecha": c["fecha"], "4s_B": r2(c["delta"], 1), "fuente": "Fed de Nueva York, ON RRP"}
    if res:
        c, c3 = change(res, 28), change(res, 91)
        M["reservas"] = {"valor_T": r2(c["valor"] / 1e6, 3), "fecha": c["fecha"], "4s_pct": r2(c["delta_pct"]), "3m_pct": r2(c3["delta_pct"]) if c3 else None,
                         "fuente": "Fed H.4.1, WRESBAL (FRED), semanal"}
    if m2:
        yoy = [(m2[i][0], (m2[i][1] / m2[i - 12][1] - 1) * 100) for i in range(12, len(m2))]
        M["m2"] = {"yoy_pct": r2(yoy[-1][1]), "yoy_prev_pct": r2(yoy[-2][1]), "mes": m2[-1][0].strftime("%Y-%m"), "fuente": "Fed H.6, M2SL (FRED), mensual"}
    if sofr and iorb:
        M["sofr"] = {"valor": sofr[-1][1], "fecha": sofr[-1][0].isoformat(), "iorb": iorb[-1][1]}
    # --- posicionamiento y flujos
    if cot:
        last, prev = cot[-1], cot[-2]
        hist = [x["mm_neto"] for x in cot[-52:]]
        M["cot"] = {"fecha": last["fecha"], "mm_neto": last["mm_neto"], "mm_neto_1s": last["mm_neto"] - prev["mm_neto"],
                    "mm_largos_1s": last["mm_largos"] - prev["mm_largos"], "mm_cortos_1s": last["mm_cortos"] - prev["mm_cortos"],
                    "mm_percentil_52s": round(sum(h <= last["mm_neto"] for h in hist) / len(hist) * 100),
                    "comerciales_neto": last["comerciales_neto"], "comerciales_1s": last["comerciales_neto"] - prev["comerciales_neto"],
                    "oi": last["oi"], "oi_1s": last["oi"] - prev["oi"], "oi_1s_pct": r2((last["oi"] / prev["oi"] - 1) * 100),
                    "fecha_previa": prev["fecha"], "fuente": "CFTC Disaggregated Futures Only, COMEX Gold 088691 (posiciones del martes)"}
    if gld:
        s = [(d, t) for d, t, _ in gld]
        M["etf"] = {"gld_t": s[-1][1], "fecha": s[-1][0].isoformat(), "1d_t": r2(delta_n(s, 1)), "5d_t": r2(delta_n(s, 5)),
                    "20d_t": r2(delta_n(s, 20)), "ytd_t": r2(s[-1][1] - next(t for d, t in s if d.year == s[-1][0].year)),
                    "volumen_acciones": gld[-1][2], "volumen_media20": round(statistics.mean(v for _, _, v in gld[-20:])),
                    "fuente": "SPDR Gold Shares (GLD), toneladas en el trust — mayor ETF de oro; WGC global en la narrativa"}
        M["_gld_serie"] = s
    # --- plata y petróleo
    if silver and gold:
        gs = dict(gold)
        ratio = [(d, gs[d] / v) for d, v in silver if d in gs and v]
        M["plata"] = {"lbma": silver[-1][1], "fecha": silver[-1][0].isoformat(), "5d_pct": r2(pct_n(silver, 5)), "20d_pct": r2(pct_n(silver, 20)),
                      "ratio_oro_plata": r2(ratio[-1][1]), "ratio_20d": r2(delta_n(ratio, 20)), "fuente": "LBMA Silver Price (USD/oz)"}
    for nm, s in (("brent", brent), ("wti", wti)):
        if s:
            M[nm] = {"valor": s[-1][1], "fecha": s[-1][0].isoformat(), "5d_pct": r2(pct_n(s, 5)), "20d_pct": r2(pct_n(s, 20)),
                     "fuente": "EIA vía FRED (DCOILBRENTEU / DCOILWTICO); publica con unos días de retraso"}
    # --- correlaciones de 60 sesiones (cambios diarios): contexto de si la relación se cumple ahora
    if gold and M.get("_real10_serie") and M.get("_dxy_serie"):
        gd = dict(gold)
        for key, s, lab in (("corr_real10", M["_real10_serie"], "10Y real"), ("corr_dxy", M["_dxy_serie"], "DXY")):
            sd = dict(s)
            ds = [d for d in sorted(set(gd) & set(sd))][-61:]
            a = [gd[ds[i]] / gd[ds[i - 1]] - 1 for i in range(1, len(ds))]
            b = [sd[ds[i]] - sd[ds[i - 1]] for i in range(1, len(ds))]
            M[key] = r2(corr(a, b))
    # --- (A) oro en otras monedas: separa demanda de oro de efecto dólar
    if gold and gold_eur and fx:
        usdjpy = sorted((d, fx["JPY"][d] / fx["USD"][d]) for d in fx["USD"] if d in fx.get("JPY", {}))
        gjpy = []
        for d, v in gold[-400:]:
            fxj = at_or_before(usdjpy, d)
            if fxj and (d - fxj[0]).days <= 4:
                gjpy.append((d, v * fxj[1]))
        mon = {"USD": gold[-400:], "EUR": gold_eur[-400:], "JPY": gjpy}
        if gold_gbp:
            mon["GBP"] = gold_gbp[-400:]
        M["oro_monedas"] = {k: {"valor": round(v[-1][1], 2), "fecha": v[-1][0].isoformat(), "5d_pct": r2(pct_n(v, 5)), "20d_pct": r2(pct_n(v, 20))}
                            for k, v in mon.items() if v}
        M["oro_monedas"]["fuente"] = "LBMA Gold Price PM en USD, EUR y GBP; JPY = USD × USDJPY del BCE"
    # --- (D) prima de Shanghái: demanda física china
    if shau and cny and fx and gold_am:
        usd = fx["USD"]
        gam = dict(gold_am)
        rows = []
        for d, v in shau[-400:]:
            c, u = at_or_before(sorted(cny.items()), d), at_or_before(sorted(usd.items()), d)
            if c and u and d in gam and (d - c[0]).days <= 4:
                usdcny = c[1] / u[1]
                usd_oz = v * 31.1034768 / usdcny
                rows.append((d, (usd_oz / gam[d] - 1) * 100, usd_oz))
        if rows:
            prem = [(d, p) for d, p, _ in rows]
            last = rows[-1]
            hist = [p for _, p in prem[-250:]]
            M["prima_shanghai"] = {"fecha": last[0].isoformat(), "prima_pct": r2(last[1]), "shau_usd_oz": r2(last[2], 1),
                                   "media_5d": r2(statistics.mean(p for _, p in prem[-5:])), "media_20d": r2(statistics.mean(p for _, p in prem[-20:])),
                                   "percentil_1a": round(sum(h <= last[1] for h in hist) / len(hist) * 100),
                                   "fuente": "Shanghai Gold Exchange (SHAU mediodía, CNY/g) vs LBMA Gold AM; USDCNY del BCE",
                                   "nota": "Diferencia horaria de unas 3 horas entre ambas referencias: mirar medias de 5 y 20 días, no el dato aislado."}
    # --- (E) expectativas de tipos implícitas en letras del Tesoro (proxy, NO FedWatch)
    if nom and effr:
        rows = []
        for d, rec in nom.items():
            e = at_or_before(effr, d)
            if e and "1 Yr" in rec and (d - e[0]).days <= 5:
                rows.append((d, (rec["1 Yr"] - e[1]) * 100, (rec.get("6 Mo", float("nan")) - e[1]) * 100))
        if len(rows) > 21:
            s1 = [(d, a) for d, a, _ in rows]
            M["expectativas_letras"] = {"fecha": rows[-1][0].isoformat(), "1a_menos_effr_pb": r2(rows[-1][1], 0), "6m_menos_effr_pb": r2(rows[-1][2], 0),
                                        "5d_pb": r2(delta_n(s1, 5), 0), "20d_pb": r2(delta_n(s1, 20), 0), "effr": effr[-1][1],
                                        "fuente": "U.S. Treasury (letra 6M y 1A) − EFFR (Fed NY vía FRED)",
                                        "nota": "PROXY de expectativas, no es FedWatch: incluye prima por plazo y efectos de oferta de letras."}
    # --- (B) ¿se cumple la relación? correlación de cambios diarios a 60 y 250 sesiones
    if gold and M.get("_real10_serie") and M.get("_dxy_serie"):
        gd = dict(gold)
        for key, s_ in (("real10", M["_real10_serie"]), ("dxy", M["_dxy_serie"])):
            sd_ = dict(s_)
            ds = sorted(set(gd) & set(sd_))
            out = {}
            for n in (20, 60, 250):
                dd = ds[-(n + 1):]
                a = [gd[dd[i]] / gd[dd[i - 1]] - 1 for i in range(1, len(dd))]
                b = [sd_[dd[i]] - sd_[dd[i - 1]] for i in range(1, len(dd))]
                out[f"corr_{n}"] = r2(corr(a, b))
            c60 = out["corr_60"]
            out["estado"] = ("SIN DATO" if c60 is None else "ROTA" if c60 > 0.10 else "DÉBIL" if c60 > -0.15 else "SE CUMPLE")
            M.setdefault("relaciones", {})[key] = out
    # --- niveles HTF y pools de liquidez (proxy XAUT)
    if xaut:
        M["niveles"] = niveles(xaut)
    M["errores"] = err
    return M


def niveles(o):
    """Máximos/mínimos del día, semana y mes anteriores, 20 y 52 semanas, y números redondos cercanos (pools de liquidez)."""
    last = o[-1]
    d0 = last[0]
    wk = d0 - dt.timedelta(days=d0.weekday())               # lunes de la semana en curso
    prev_w = [x for x in o if wk - dt.timedelta(days=7) <= x[0] < wk]
    m0 = d0.replace(day=1)
    pm_end = m0 - dt.timedelta(days=1)
    prev_m = [x for x in o if x[0].year == pm_end.year and x[0].month == pm_end.month]
    cw = [x for x in o if x[0] >= wk]
    out = {"fuente": "XAUT-USDT (OKX), velas diarias UTC completas — proxy del spot; verificar en el gráfico de XAU/USD",
           "ultimo_cierre": last[4], "fecha": d0.isoformat(),
           "PDH": last[2], "PDL": last[3],
           "PWH": max(x[2] for x in prev_w) if prev_w else None, "PWL": min(x[3] for x in prev_w) if prev_w else None,
           "PMH": max(x[2] for x in prev_m) if prev_m else None, "PML": min(x[3] for x in prev_m) if prev_m else None,
           "semana_actual_max": max(x[2] for x in cw) if cw else None, "semana_actual_min": min(x[3] for x in cw) if cw else None,
           # XAUT cotiza 7 días a la semana: las ventanas se miden en días naturales, no en número de velas
           "max_20s": max(x[2] for x in o if x[0] > d0 - dt.timedelta(weeks=20)), "min_20s": min(x[3] for x in o if x[0] > d0 - dt.timedelta(weeks=20)),
           "max_52s": max(x[2] for x in o if x[0] > d0 - dt.timedelta(weeks=52)) if o[0][0] <= d0 - dt.timedelta(weeks=50) else None,
           "min_52s": min(x[3] for x in o if x[0] > d0 - dt.timedelta(weeks=52)) if o[0][0] <= d0 - dt.timedelta(weeks=50) else None}
    px = last[4]
    step = 50 if px < 3000 else 100
    base = math.floor(px / step) * step
    out["redondos"] = [base - step, base, base + step, base + 2 * step]
    tr = [max(x[2], p[4]) - min(x[3], p[4]) for p, x in zip(o[-15:-1], o[-14:])]
    out["atr14"] = r2(statistics.mean(tr), 1)
    # estructura HTF: máximos y mínimos semanales (últimas 6 semanas cerradas)
    semanas = {}
    for x in o:
        k = x[0] - dt.timedelta(days=x[0].weekday())
        s = semanas.setdefault(k, [x[2], x[3]])
        s[0], s[1] = max(s[0], x[2]), min(s[1], x[3])
    ks = sorted(k for k in semanas if k < wk)[-6:]
    out["semanales"] = [{"semana": k.isoformat(), "max": semanas[k][0], "min": semanas[k][1]} for k in ks]
    hh = sum(semanas[ks[i]][0] > semanas[ks[i - 1]][0] for i in range(1, len(ks)))
    hl = sum(semanas[ks[i]][1] > semanas[ks[i - 1]][1] for i in range(1, len(ks)))
    n = len(ks) - 1
    est = ("ALCISTA (máximos y mínimos crecientes)" if hh >= n - 1 and hl >= n - 1 else
           "BAJISTA (máximos y mínimos decrecientes)" if hh <= 1 and hl <= 1 else
           "MÁXIMOS DECRECIENTES, mínimos sin tendencia" if hh <= 1 else
           "MÍNIMOS CRECIENTES, máximos sin tendencia" if hl >= n - 1 else "LATERAL")
    est += f" · {hh}/{n} máximos y {hl}/{n} mínimos crecientes en las últimas {n + 1} semanas cerradas"
    if cw and ks:
        if out["semana_actual_min"] < semanas[ks[-1]][1]:
            est += " · la semana en curso ya perfora el mínimo de la anterior"
        if out["semana_actual_max"] > semanas[ks[-1]][0]:
            est += " · la semana en curso ya supera el máximo de la anterior"
    out["estructura_semanal"] = est
    return out


def pools(M):
    """Clasifica los niveles por posición respecto al último precio (no por su nombre)."""
    niv = M.get("niveles") or {}
    if not niv:
        return None
    ref = ((M.get("oro_intradia") or {}).get("xaut_okx") or {}).get("precio") or niv["ultimo_cierre"]
    nombres = {"PDH": "máx. día anterior", "PDL": "mín. día anterior", "PWH": "máx. semana anterior", "PWL": "mín. semana anterior",
               "PMH": "máx. mes anterior", "PML": "mín. mes anterior", "max_20s": "máx. 20 semanas", "min_20s": "mín. 20 semanas",
               "max_52s": "máx. 52 semanas", "min_52s": "mín. 52 semanas", "semana_actual_max": "máx. semana en curso",
               "semana_actual_min": "mín. semana en curso"}
    L = [(k, niv[k]) for k in nombres if niv.get(k)]
    atr = niv.get("atr14") or 1
    uniq = {}
    for k, v in L:  # niveles idénticos (p. ej. máx. del día anterior = máx. de la semana en curso) se agrupan
        uniq.setdefault(round(v, 1), []).append(k)
    L = [("+".join(ks), v) for v, ks in uniq.items()]
    nombres.update({"+".join(ks): " / ".join(nombres[k] for k in ks) for ks in uniq.values() if len(ks) > 1})
    enc = sorted(((k, v) for k, v in L if v > ref), key=lambda x: x[1])
    deb = sorted(((k, v) for k, v in L if v <= ref), key=lambda x: -x[1])
    f = lambda k, v: {"id": k, "nombre": nombres[k], "nivel": round(v, 1), "dist_pct": round((v / ref - 1) * 100, 2), "dist_atr": round((v - ref) / atr, 1)}  # noqa: E731
    return {"referencia": ref, "atr14": atr, "encima": [f(k, v) for k, v in enc], "debajo": [f(k, v) for k, v in deb]}


def pools_txt(M):
    p = pools(M)
    if not p:
        return "Sin dato"
    e = " · ".join(f"{x['nombre']} {x['nivel']:,.1f} ({x['dist_atr']:+.1f} ATR)" for x in p["encima"][:4])
    d = " · ".join(f"{x['nombre']} {x['nivel']:,.1f} ({x['dist_atr']:+.1f} ATR)" for x in p["debajo"][:4])
    return f"Ref. {p['referencia']:,.1f} (ATR14 {p['atr14']:,.1f}) — encima: {e or 'ninguno'} — debajo: {d or 'ninguno'}"


# ----------------------------------------------------------------- evaluación (literal a la chuleta)
def cargar_evidencia():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "evidencia_oro.json")
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def cargar_eventos():
    """Resumen del registro propio de reacciones del oro a datos macro (eventos_oro.csv), si existe."""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eventos_oro.csv")
    if not os.path.exists(p):
        return None
    try:
        from eventos_oro import leer, resumen_dict
        return resumen_dict(leer(p))
    except Exception:  # noqa: BLE001
        return None


def evaluar(M, fedwatch=None):
    """fedwatch = {"cambio": "RELAJACION|ENDURECIMIENTO|SIN CAMBIO", ...} (solo CME; si falta, SIN DATO)."""
    if fedwatch is None:  # FedWatch NEXORA (método CME) automático si no se pasa
        try:
            import fedwatch as _fw
            fedwatch = _fw.para_monitor(_fw.cargar())
        except Exception:  # noqa: BLE001
            fedwatch = None
    g = M.get("oro") or {}
    P = []  # panel §1

    def add(id_, nombre, que_mirar, dir_, valor, estado, lectura, fuente, puntua=True):
        P.append({"id": id_, "dato": nombre, "que_mirar": que_mirar, "dir": dir_, "valor": valor, "estado": estado,
                  "lectura": lectura, "fuente": fuente, "puntua": puntua})

    # DXY
    dx = M.get("dxy")
    if dx:
        d = dirv(dx["5d_pct"], U["dxy_pct_1s"])
        rap = dx["vel_z"] is not None and abs(dx["vel_z"]) >= U["velocidad_z"]
        est = FAV if d == "↓" else CON if d == "↑" else NEU
        add("dxy", "DXY", "Nivel, dirección y velocidad", d, f"{dx['valor']:.2f} · 5d {dx['5d_pct']:+.2f}% · 1d {dx['1d_pct']:+.2f}%",
            est, ("Baja: suele favorecer al oro" if d == "↓" else "Sube: suele presionarlo" if d == "↑" else "Estable") +
            (f" · velocidad ALTA ({dx['vel_z']:+.1f}σ)" if rap else f" · velocidad normal ({(dx['vel_z'] or 0):+.1f}σ)"), dx["metodo"])
    else:
        add("dxy", "DXY", "Nivel, dirección y velocidad", "?", "—", SD, "Sin dato", "BCE")
    # 2Y
    t2 = M.get("t2Y")
    if t2:
        d = dirv(t2["5d_pb"], U["t2y_pb_1s"])
        add("t2y", "US 2Y", "Yield y cambio diario/semanal", d, f"{t2['valor']:.2f}% · 5d {t2['5d_pb']:+.0f} pb · 1d {t2['1d_pb']:+.0f} pb",
            FAV if d == "↓" else CON if d == "↑" else NEU,
            "Baja: menor presión de tipos" if d == "↓" else "Sube: mayor presión de tipos" if d == "↑" else "Estable: expectativas Fed sin cambio", t2["fuente"])
    # 10Y
    t10 = M.get("t10Y")
    if t10:
        d = dirv(t10["5d_pb"], U["t10y_pb_1s"])
        rap = t10["5d_pb"] > U["t10y_rapido_pb_1s"] or ((t10["vel_z"] or 0) >= U["velocidad_z"] and d == "↑")
        add("t10y", "US 10Y", "Yield y velocidad", d, f"{t10['valor']:.2f}% · 5d {t10['5d_pb']:+.0f} pb · 1d {t10['1d_pb']:+.0f} pb",
            FAV if d == "↓" else CON if d == "↑" else NEU,
            ("Baja: suele aliviar presión" if d == "↓" else ("Sube RÁPIDO: presiona" if rap else "Sube: puede presionar") if d == "↑" else "Estable")
            + " · condiciones financieras", t10["fuente"], puntua=False)
    # 10Y real
    rl = M.get("real10Y")
    if rl:
        d = dirv(rl["5d_pb"], U["real_pb_1s"])
        add("real10", "10Y REAL / TIPS (PRIORIDAD ALTA)", "Nivel + dirección", d, f"{rl['valor']:.2f}% · 5d {rl['5d_pb']:+.0f} pb · 20d {rl['20d_pb']:+.0f} pb",
            FAV if d == "↓" else CON if d == "↑" else NEU,
            "Baja: generalmente favorable (menor coste de oportunidad)" if d == "↓" else
            "Sube: generalmente desfavorable (mayor coste de oportunidad)" if d == "↑" else "Estable", rl["fuente"])
    # FedWatch
    if fedwatch and fedwatch.get("cambio"):
        c = fedwatch["cambio"].upper()
        est = FAV if c.startswith("RELAJ") else CON if c.startswith("ENDUR") else NEU
        add("fedwatch", "FedWatch", "Probabilidades de recortes/subidas", "↓" if est == FAV else "↑" if est == CON else "→",
            fedwatch.get("valor", ""), est, (fedwatch.get("detalle") or "") + " · " + ("Más relajación descontada" if est == FAV else
            "Más restricción descontada" if est == CON else "Sin cambio"), fedwatch.get("fuente", "CME FedWatch"))
    else:
        add("fedwatch", "FedWatch", "Probabilidades de recortes/subidas", "?", "—", SD,
            "CME FedWatch no tiene API gratuita. Nunca se estima.", "CME FedWatch")
    # NFCI
    nf = M.get("nfci")
    if nf:
        d = dirv(nf["4s"], U["nfci_4s"])
        add("nfci", "NFCI", "Nivel + tendencia", d, f"{nf['valor']:+.3f} · 4s {nf['4s']:+.3f} · 1s {nf['1s']:+.3f}",
            FAV if d == "↓" else CON if d == "↑" else NEU,
            "Baja: condiciones más fáciles" if d == "↓" else "Sube: condiciones más tensas" if d == "↑" else "Estable", nf["fuente"])
    # VIX
    vx = M.get("vix")
    if vx:
        d = dirv(vx["5d_pct"], U["vix_pct_1s"])
        add("vix", "VIX", "Nivel + aceleración", d, f"{vx['valor']:.2f} · 5d {vx['5d_pct']:+.1f}%", CTX,
            ("Más estrés" if d == "↑" or vx["valor"] > U["vix_alto"] else "Menos estrés" if d == "↓" else "Sin aceleración") +
            ". Riesgo/aversión, NO señal automática (CH).", vx["fuente"], puntua=False)
    # TGA / RRP / reservas
    tg, rp, rs = M.get("tga"), M.get("rrp"), M.get("reservas")
    if tg:
        d = dirv(tg["4s_B"], U["tga_b_4s"])
        add("tga", "TGA", "Saldo + dirección", d, f"{tg['valor_B']:,.1f} B$ · 4s {tg['4s_B']:+,.1f} B$",
            FAV if d == "↓" else CON if d == "↑" else NEU, "Baja: puede liberar liquidez" if d == "↓" else "Sube: puede drenar liquidez" if d == "↑" else "Estable", tg["fuente"])
    if rp:
        d = dirv(rp["4s_B"], U["rrp_b_4s"])
        agot = rp["valor_B"] < U["rrp_agotado_b"]
        add("rrp", "RRP", "Saldo + dirección", d, f"{rp['valor_B']:,.1f} B$ · 4s {rp['4s_B']:+,.1f} B$",
            (NEU if agot else FAV) if d == "↓" else CON if d == "↑" else NEU,
            ("Baja: puede liberar efectivo aparcado" if d == "↓" else "Sube: más efectivo aparcado" if d == "↑" else "Estable") +
            (f". Saldo < {U['rrp_agotado_b']:.0f} B$: colchón agotado, no aporta liquidez (se trata como neutral)" if agot else ""), rp["fuente"])
    if rs:
        up = rs["4s_pct"] > U["reservas_pct_4s"] and (rs["3m_pct"] or 0) > 0
        dn = rs["4s_pct"] < -U["reservas_pct_4s"] and (rs["3m_pct"] or 0) < 0
        add("reservas", "RESERVAS", "WRESBAL, tendencia 1M/3M", "↑" if up else "↓" if dn else "→",
            f"{rs['valor_T']:.3f} T$ · 1M {rs['4s_pct']:+.2f}% · 3M {rs['3m_pct']:+.2f}%",
            FAV if up else CON if dn else NEU, "Suben: más reservas" if up else "Bajan: puede indicar drenaje" if dn else "Planas", rs["fuente"])
    m2 = M.get("m2")
    if m2:
        up = m2["yoy_pct"] > 0 and m2["yoy_pct"] >= m2["yoy_prev_pct"]
        dn = m2["yoy_pct"] < m2["yoy_prev_pct"]
        add("m2", "M2", "Crecimiento + aceleración", "↑" if up else "↓" if dn else "→", f"{m2['yoy_pct']:+.2f}% a/a (previo {m2['yoy_prev_pct']:+.2f}%) · {m2['mes']}",
            CTX, ("Más expansión" if up else "Régimen menos expansivo" if dn else "Estable") + ". Medio/largo plazo: régimen, no entrada.", m2["fuente"], puntua=False)
    # COT
    ct = M.get("cot")
    pr5 = g.get("5d_pct")
    if ct:
        quien = ("managed money AUMENTA neto" if ct["mm_neto_1s"] > 0 else "managed money REDUCE neto") + \
                (" (salen largos)" if ct["mm_largos_1s"] < 0 and ct["mm_neto_1s"] < 0 else " (cubren cortos)" if ct["mm_cortos_1s"] < 0 and ct["mm_neto_1s"] > 0 else "")
        add("cot", "COT GOLD", "Managed Money + Commercials", "↑" if ct["mm_neto_1s"] > 0 else "↓",
            f"MM neto {ct['mm_neto']:+,} ({ct['mm_neto_1s']:+,} en 1s · percentil 52s {ct['mm_percentil_52s']}%) · comerciales {ct['comerciales_neto']:+,} ({ct['comerciales_1s']:+,})",
            CTX, f"{quien}. Depende de quién reduce/aumenta (CH). Posiciones del {ct['fecha']}.", ct["fuente"], puntua=False)
    # ETF
    et = M.get("etf")
    if et:
        d = dirv(et["5d_t"], U["gld_t_1s"])
        add("etf", "ETF GOLD FLOWS", "Entradas/salidas de ETF de oro", d, f"GLD {et['gld_t']:,.1f} t · 5d {et['5d_t']:+.1f} t · 20d {et['20d_t']:+.1f} t · año {et['ytd_t']:+.1f} t",
            FAV if d == "↑" else CON if d == "↓" else NEU, "Entradas: mayor demanda financiera" if d == "↑" else
            "Salidas: menor demanda financiera" if d == "↓" else "Sin flujo relevante", et["fuente"], puntua=False)
    # COMEX OI/volumen
    if ct and pr5 is not None:
        oi_up = ct["oi_1s"] > 0
        pu = pr5 > 0
        lect = ("Precio ↑ + OI ↑: entran posiciones nuevas a favor (participación que confirma)" if pu and oi_up else
                "Precio ↑ + OI ↓: subida por cierre de cortos (menos convicción)" if pu else
                "Precio ↓ + OI ↑: entran cortos nuevos (presión)" if oi_up else "Precio ↓ + OI ↓: liquidación de largos (puede agotarse)")
        add("comex", "COMEX OI/VOLUMEN", "Open Interest + volumen", "↑" if oi_up else "↓",
            f"OI {ct['oi']:,} ({ct['oi_1s_pct']:+.2f}% en 1s) · volumen diario: SIN DATO (CME no accesible)", CTX,
            lect + " — interpretación NEXORA de «depende del precio + OI».", "CFTC (OI semanal)", puntua=False)
    # plata
    pl = M.get("plata")
    if pl and pr5 is not None:
        conf = (pl["5d_pct"] > 0) == (pr5 > 0)
        add("plata", "PLATA", "XAG/USD y relación oro/plata", dirv(pl["5d_pct"], U["plata_pct_1s"]),
            f"{pl['lbma']:.2f} $ · 5d {pl['5d_pct']:+.1f}% · ratio oro/plata {pl['ratio_oro_plata']:.1f} ({pl['ratio_20d']:+.1f} en 20d)", CTX,
            ("Confirma el movimiento del metal" if conf else "No confirma: diverge del oro") + ". Confirmación secundaria; no aislar.", pl["fuente"], puntua=False)
    # petróleo
    br = M.get("brent")
    if br:
        d = dirv(br["5d_pct"], U["petroleo_pct_1s"])
        add("petroleo", "PETRÓLEO", "Brent/WTI + velocidad", d, f"Brent {br['valor']:.2f} $ · 5d {br['5d_pct']:+.1f}% · 20d {br['20d_pct']:+.1f}% ({br['fecha']})",
            CTX, ("Sube: puede aumentar expectativas de inflación" if d == "↑" else "Baja: menor presión inflacionaria" if d == "↓" else "Estable") +
            ". Contexto inflación/Fed.", br["fuente"], puntua=False)
    be = M.get("be10Y")
    if be:
        d = dirv(be["5d_pb"], U["be_pb_1s"])
        b5 = M.get("be5Y") or {}
        add("breakevens", "BREAKEVENS", "5Y/10Y inflación esperada", d, f"10Y {be['valor']:.2f}% ({be['5d_pb']:+.0f} pb 5d) · 5Y {b5.get('valor', 0):.2f}% ({b5.get('5d_pb', 0):+.0f} pb)",
            CTX, ("Mayor inflación esperada" if d == "↑" else "Menor inflación esperada" if d == "↓" else "Estable") + ". Explica parte del nominal.", be["fuente"], puntua=False)

    by = {p["id"]: p for p in P}

    # ---------------- §3 confluencia
    nucleo_ids = ["dxy", "t2y", "real10", "fedwatch", "nfci"]
    nuc = [by[i] for i in nucleo_ids if i in by]
    fav = sum(p["estado"] == FAV for p in nuc)
    con = sum(p["estado"] == CON for p in nuc)
    sd = sum(p["estado"] == SD for p in nuc)
    disp = len(nucleo_ids) - sd
    liq_f = sum(by.get(i, {}).get("estado") == FAV for i in ("tga", "rrp", "reservas"))
    liq_c = sum(by.get(i, {}).get("estado") == CON for i in ("tga", "rrp", "reservas"))
    drena = by.get("reservas", {}).get("dir") == "↓" and by.get("tga", {}).get("dir") == "↑"
    liquidez = "DRENA" if drena else "ACOMPAÑA" if liq_f >= 2 and liq_c == 0 else "NO ACOMPAÑA" if liq_c >= 2 else "NEUTRAL"
    mixto = by.get("t10y", {}).get("dir") == "↑" and by.get("real10", {}).get("dir") == "↓"
    # precio
    precio = "SIN DATO"
    if g.get("sma50") and g.get("20d_pct") is not None:
        if g["lbma_pm"] > g["sma50"] and g["20d_pct"] > 0:
            precio = "CONFIRMA FUERZA"
        elif g["lbma_pm"] < g["sma50"] and g["20d_pct"] < 0:
            precio = "CONFIRMA DEBILIDAD"
        else:
            precio = "NO CONFIRMA"
    if disp and fav == disp:
        lectura = "CONFLUENCIA FAVORABLE"
    elif disp and con == disp:
        lectura = "CONFLUENCIA CONTRARIA"
    elif fav >= 3 and con <= 1:
        lectura = "PREDOMINIO FAVORABLE"
    elif con >= 3 and fav <= 1:
        lectura = "PREDOMINIO CONTRARIO"
    else:
        lectura = "MIXTO"
    avisos = []
    if sd:
        avisos.append(f"Confluencia evaluada sobre {disp} de 5 condiciones: FedWatch sin dato hoy (fallo de descarga).")
    if mixto:
        avisos.append("MIXTO (CH §3): el 10Y nominal sube pero el 10Y real baja. No es automáticamente negativo: la inflación esperada "
                      f"(breakeven 10Y {M.get('be10Y', {}).get('5d_pb', 0):+.0f} pb en 5 sesiones) explica parte del nominal.")
    if lectura in ("CONFLUENCIA CONTRARIA", "PREDOMINIO CONTRARIO") and precio == "CONFIRMA FUERZA":
        avisos.append("DIVERGENCIA: la macro de la chuleta presiona, pero el precio del oro mantiene fuerza. El oro no está respondiendo a "
                      "dólar + real yield: buscar el driver alternativo (bancos centrales, geopolítica, flujos ETF/COT) antes de asumir que corrige.")
    if lectura in ("CONFLUENCIA FAVORABLE", "PREDOMINIO FAVORABLE") and precio == "CONFIRMA DEBILIDAD":
        avisos.append("DIVERGENCIA: la macro acompaña pero el precio no confirma. CH §7: esperar a que el precio confirme.")
    if by.get("t10y", {}).get("lectura", "").startswith("Sube RÁPIDO"):
        avisos.append("10Y subiendo rápido: CH lo señala como presión especial sobre el oro.")
    if by.get("dxy", {}).get("lectura", "").find("velocidad ALTA") >= 0:
        avisos.append("DXY moviéndose a velocidad alta (más de 1,5σ): CH pide mirar dirección y velocidad.")
    if M.get("sofr") and M["sofr"]["valor"] > M["sofr"]["iorb"]:
        avisos.append(f"SOFR {M['sofr']['valor']:.2f}% por encima del IORB {M['sofr']['iorb']:.2f}%: tensión de financiación (detector de estrés).")

    sesgo60 = ("ORO ↑" if lectura in ("CONFLUENCIA FAVORABLE", "PREDOMINIO FAVORABLE") and precio == "CONFIRMA FUERZA" else
               "ORO ↓" if lectura in ("CONFLUENCIA CONTRARIA", "PREDOMINIO CONTRARIO") and precio == "CONFIRMA DEBILIDAD" else "SIN CONFLUENCIA COMPLETA")

    # ---------------- §2 comparaciones
    Cmp = []

    def cmpar(par, busca, ok, detalle, lectura_ch):
        Cmp.append({"par": par, "busca": busca, "estado": ok, "detalle": detalle, "lectura": lectura_ch})

    def rel(a, b_up):  # a = dirección del factor; b_up = precio sube
        return None if a in ("?", None) or pr5 is None else a

    gd = "↑" if (pr5 or 0) > 0 else "↓"
    if dx and pr5 is not None:
        dd = by["dxy"]["dir"]
        st = "CUMPLE" if dd == "↓" and gd == "↑" else "INVERSA EN CONTRA" if dd == "↑" and gd == "↓" else "NO SE CUMPLE" if dd == gd else "NEUTRAL"
        cmpar("DXY ↔ ORO", "DXY ↓ mientras XAU/USD ↑", st, f"DXY {dx['5d_pct']:+.2f}% · oro {pr5:+.2f}% (5 sesiones) · correlación 60d {M.get('corr_dxy')}",
              "Confirmación de la relación inversa")
    if rl and pr5 is not None:
        dd = by["real10"]["dir"]
        st = "CUMPLE" if dd == "↓" and gd == "↑" else "INVERSA EN CONTRA" if dd == "↑" and gd == "↓" else "NO SE CUMPLE" if dd == gd else "NEUTRAL"
        cmpar("10Y REAL ↔ ORO", "Real yield ↓ mientras oro ↑", st, f"10Y real {rl['5d_pb']:+.0f} pb · oro {pr5:+.2f}% · correlación 60d {M.get('corr_real10')}",
              "Una de las relaciones macro más importantes")
    if t2:
        fw = by.get("fedwatch", {}).get("estado")
        st = ("CUMPLE" if by["t2y"]["dir"] == "↓" and fw == FAV else "PARCIAL" if by["t2y"]["dir"] == "↓" and fw == SD
              else "NO SE CUMPLE")
        cmpar("2Y ↔ FedWatch", "2Y ↓ + más recortes descontados", st, f"2Y {t2['5d_pb']:+.0f} pb · FedWatch {by['fedwatch']['estado']}",
              "Expectativas de tipos más relajadas")
    if tg and rs:
        st = "CUMPLE" if by["tga"]["dir"] == "↓" and by["reservas"]["dir"] == "↑" else "PARCIAL" if by["tga"]["dir"] == "↓" or by["reservas"]["dir"] == "↑" else "NO SE CUMPLE"
        cmpar("TGA ↔ RESERVAS", "TGA ↓ + reservas ↑", st, f"TGA {tg['4s_B']:+,.1f} B$ · reservas {rs['4s_pct']:+.2f}% (4 semanas)", "Posible liberación de liquidez")
    if rp and rs:
        st = ("CUMPLE" if by["rrp"]["dir"] == "↓" and by["reservas"]["dir"] == "↑" else
              "PARCIAL" if by["rrp"]["dir"] == "↓" or by["reservas"]["dir"] == "↑" else "NO SE CUMPLE")
        cmpar("RRP ↔ RESERVAS", "RRP ↓ + reservas ↑", st, f"RRP {rp['4s_B']:+,.1f} B$ (saldo {rp['valor_B']:.1f}) · reservas {rs['4s_pct']:+.2f}%",
              "Efectivo saliendo del aparcamiento")
    if t10 and rl:
        st = "CUMPLE" if mixto else "NO SE CUMPLE"
        cmpar("10Y nominal ↔ 10Y real", "Nominal ↑ pero real ↓", st, f"10Y {t10['5d_pb']:+.0f} pb · real {rl['5d_pb']:+.0f} pb · breakeven {M.get('be10Y', {}).get('5d_pb', 0):+.0f} pb",
              "La inflación esperada puede explicar el nominal")
    if vx and pr5 is not None:
        st = "CUMPLE" if by["vix"]["dir"] == "↑" and gd == "↑" else "NO SE CUMPLE"
        cmpar("VIX ↔ ORO", "VIX ↑ + oro ↑", st, f"VIX {vx['5d_pct']:+.1f}% · oro {pr5:+.2f}%", "Posible demanda defensiva; comprobar causa")
    if pr5 is not None and (et or ct):
        acomp = []
        if et:
            acomp.append(("ETF", (et["5d_t"] > 0) == (pr5 > 0)))
        if ct:
            acomp.append(("COT", (ct["mm_neto_1s"] > 0) == (pr5 > 0)))
        n_ok = sum(x[1] for x in acomp)
        st = "CUMPLE" if n_ok == len(acomp) else "PARCIAL" if n_ok else "NO SE CUMPLE"
        cmpar("COT/ETF ↔ PRECIO", "Precio y flujos/posicionamiento en la misma dirección", st,
              " · ".join(f"{k} {'acompaña' if v else 'no acompaña'}" for k, v in acomp) + f" · oro {pr5:+.2f}% (5 sesiones)",
              "Mayor confirmación, aunque no garantía")

    # ---------------- DATOS ADICIONALES NEXORA (no están en la chuleta; no puntúan)
    AD = []
    om = M.get("oro_monedas")
    if om and om.get("USD") and om.get("EUR"):
        tol = 0.25
        sig = {k: (1 if (om[k]["5d_pct"] or 0) > tol else -1 if (om[k]["5d_pct"] or 0) < -tol else 0) for k in ("USD", "EUR", "JPY", "GBP") if k in om}
        otras = [v for k, v in sig.items() if k != "USD"]
        if sig["USD"] > 0 and all(v > 0 for v in otras):
            lec, est = "DEMANDA DE ORO: sube en todas las monedas. No es solo un dólar débil.", "DEMANDA DE ORO"
        elif sig["USD"] < 0 and all(v < 0 for v in otras):
            lec, est = "VENTA DE ORO: cae en todas las monedas. No es solo un dólar fuerte.", "VENTA DE ORO"
        elif sig["USD"] > 0 and any(v <= 0 for v in otras):
            lec, est = "EFECTO DÓLAR: sube en dólares pero no en otras monedas. La subida la explica sobre todo el dólar débil.", "EFECTO DÓLAR"
        elif sig["USD"] < 0 and any(v >= 0 for v in otras):
            lec, est = "EFECTO DÓLAR: cae en dólares pero aguanta en otras monedas. La caída la explica sobre todo el dólar fuerte.", "EFECTO DÓLAR"
        else:
            lec, est = "Sin movimiento relevante en ninguna moneda.", NEU
        AD.append({"id": "multidivisa", "dato": "ORO EN OTRAS MONEDAS", "valor": " · ".join(f"{k} {om[k]['5d_pct']:+.1f}%" for k in ("USD", "EUR", "GBP", "JPY") if k in om) + " (5 sesiones)",
                   "estado": est, "lectura": lec, "fuente": om["fuente"]})
    ps = M.get("prima_shanghai")
    if ps:
        lec = ("Descuento: demanda física china débil" if ps["media_20d"] < 0 else
               "Prima alta respecto al último año: demanda física china fuerte" if ps["percentil_1a"] >= 80 else
               "Prima baja respecto al último año: demanda física china floja" if ps["percentil_1a"] <= 20 else "Prima en rango normal del último año")
        AD.append({"id": "shanghai", "dato": "PRIMA DE SHANGHÁI", "valor": f"{ps['prima_pct']:+.2f}% ({ps['fecha']}) · media 5d {ps['media_5d']:+.2f}% · 20d {ps['media_20d']:+.2f}% · percentil 1 año {ps['percentil_1a']}%",
                   "estado": CTX, "lectura": lec + ". Mide la compra física en China (demanda estructural). " + ps["nota"], "fuente": ps["fuente"]})
    ex = M.get("expectativas_letras")
    if ex:
        d = dirv(ex["5d_pb"], 5)
        AD.append({"id": "expectativas", "dato": "EXPECTATIVAS DE TIPOS (proxy letras)", "valor": f"1A − EFFR {ex['1a_menos_effr_pb']:+.0f} pb · 5d {ex['5d_pb']:+.0f} pb · 20d {ex['20d_pb']:+.0f} pb",
                   "estado": CTX, "lectura": ("El mercado descuenta MÁS recortes que hace una semana (relajación)" if d == "↓" else
                                              "El mercado descuenta MENOS recortes o subidas (endurecimiento)" if d == "↑" else "Sin cambio relevante en expectativas") +
                   ". " + ex["nota"] + " No sustituye a FedWatch en la confluencia.", "fuente": ex["fuente"]})
    rl_ = M.get("relaciones") or {}
    for k, nm in (("real10", "10Y real"), ("dxy", "DXY")):
        r = rl_.get(k)
        if r:
            AD.append({"id": f"rel_{k}", "dato": f"¿SE CUMPLE ORO ↔ {nm}?", "valor": f"corr. 20d {r['corr_20']} · 60d {r['corr_60']} · 250d {r['corr_250']}",
                       "estado": r["estado"],
                       "lectura": {"SE CUMPLE": "Relación inversa vigente: la chuleta es fiable para este factor.",
                                   "DÉBIL": "Relación débil: dar menos peso a este factor en la lectura.",
                                   "ROTA": "RELACIÓN ROTA: el oro se mueve en la misma dirección que el factor. La chuleta pierde fiabilidad; buscar el driver alternativo (bancos centrales, geopolítica, flujos)."}.get(r["estado"], "Sin dato"),
                       "fuente": "Cálculo NEXORA con cambios diarios (LBMA PM vs Tesoro / réplica DXY)"})
            if r["estado"] == "ROTA":
                avisos.append(f"RELACIÓN ROTA oro ↔ {nm} (correlación 60 sesiones {r['corr_60']:+.2f}): la chuleta asume relación inversa y ahora no se cumple. "
                              "Leer la confluencia con cautela y buscar el driver alternativo.")

    # ---------------- §4 macro → entrada
    niv = M.get("niveles") or {}
    pasos = [
        {"n": 1, "paso": "MACRO", "que": "DXY → 2Y → 10Y → 10Y real → FedWatch → NFCI",
         "estado": FAV if lectura in ("CONFLUENCIA FAVORABLE", "PREDOMINIO FAVORABLE") else CON if lectura in ("CONFLUENCIA CONTRARIA", "PREDOMINIO CONTRARIO") else NEU,
         "detalle": f"{lectura}: {fav} a favor, {con} en contra, {sd} sin dato de 5"},
        {"n": 2, "paso": "LIQUIDEZ", "que": "TGA → RRP → reservas (M2/H.4.1 = régimen)",
         "estado": FAV if liquidez == "ACOMPAÑA" else CON if liquidez in ("DRENA", "NO ACOMPAÑA") else NEU, "detalle": f"Liquidez {liquidez}"},
        {"n": 3, "paso": "POSICIONAMIENTO", "que": "COT + ETF flows + COMEX OI/volumen", "estado": CTX,
         "detalle": next((c["estado"] + " · " + c["detalle"] for c in Cmp if c["par"].startswith("COT/ETF")), "Sin dato")},
        {"n": 4, "paso": "CONTEXTO", "que": "VIX + petróleo + breakevens + calendario", "estado": CTX,
         "detalle": " · ".join(by[i]["lectura"].split(".")[0] for i in ("vix", "petroleo", "breakevens") if i in by)},
        {"n": 5, "paso": "PRECIO (HTF)", "que": "Tendencia, máximos/mínimos, zonas y niveles clave",
         "estado": FAV if precio == "CONFIRMA FUERZA" else CON if precio == "CONFIRMA DEBILIDAD" else NEU,
         "detalle": (f"LBMA {g.get('lbma_pm', 0):,.2f} vs media 50 {g.get('sma50') or 0:,.0f} / 200 {g.get('sma200') or 0:,.0f} · 20 sesiones {g.get('20d_pct') or 0:+.1f}% · "
                     f"estructura semanal {niv.get('estructura_semanal', 'sin dato')}")},
        {"n": 6, "paso": "LIQUIDEZ DEL GRÁFICO", "que": "Pools de liquidez; sweep/inducción (modelo ICT)", "estado": CTX,
         "detalle": pools_txt(M)},
        {"n": 7, "paso": "EJECUCIÓN", "que": "Footprint/DOM/delta: absorción, agresión, desplazamiento", "estado": "MANUAL",
         "detalle": "No automatizable con datos gratuitos: requiere tu plataforma de order flow."},
        {"n": 8, "paso": "ENTRADA", "que": "Contexto + nivel + liquidez + estructura + ejecución coinciden", "estado": "MANUAL",
         "detalle": "Decisión tuya. El informe solo aporta contexto, niveles y sesgo; no es una orden."},
    ]

    # ---------------- §6 diez preguntas
    Q = [
        (1, "¿DXY sube o baja y a qué velocidad?", by.get("dxy", {}).get("valor", "—") + " · " + by.get("dxy", {}).get("lectura", "")),
        (2, "¿El 2Y está cambiando las expectativas de tipos?", by.get("t2y", {}).get("valor", "—") + " · " + by.get("t2y", {}).get("lectura", "")),
        (3, "¿El 10Y real sube o baja?", by.get("real10", {}).get("valor", "—") + " · " + by.get("real10", {}).get("lectura", "")),
        (4, "¿FedWatch se mueve hacia recortes o subidas?", by.get("fedwatch", {}).get("lectura", "")),
        (5, "¿NFCI se relaja o se endurece?", by.get("nfci", {}).get("valor", "—") + " · " + by.get("nfci", {}).get("lectura", "")),
        (6, "¿TGA/RRP/reservas están liberando o absorbiendo liquidez?", f"Liquidez {liquidez}: " + " · ".join(f"{by[i]['dato']} {by[i]['dir']}" for i in ("tga", "rrp", "reservas") if i in by)),
        (7, "¿COT y ETF flows confirman o contradicen?", next((c["estado"] + " · " + c["detalle"] for c in Cmp if c["par"].startswith("COT/ETF")), "Sin dato")),
        (8, "¿El movimiento del oro tiene sentido con dólar + real yield?",
         " · ".join(f"{c['par']}: {c['estado']}" for c in Cmp if c["par"] in ("DXY ↔ ORO", "10Y REAL ↔ ORO"))),
        (9, "¿Dónde está la liquidez en el gráfico y qué nivel puede barrerse?", pasos[5]["detalle"] + " (proxy XAUT; verificar en tu gráfico)"),
        (10, "¿Tengo confirmación de estructura + ejecución o estoy anticipándome?", "MANUAL: solo tú puedes verificarlo en tu gráfico y en el footprint."),
    ]
    preguntas = [{"n": a, "pregunta": b, "respuesta": c} for a, b, c in Q]

    return {"panel": P, "comparaciones": Cmp,
            "confluencia": {"lectura": lectura, "favorables": fav, "contrarias": con, "sin_dato": sd, "disponibles": disp,
                            "nucleo": [{"id": p["id"], "dato": p["dato"], "dir": p["dir"], "estado": p["estado"]} for p in nuc],
                            "liquidez": liquidez, "mixto_nominal_real": mixto, "precio": precio},
            "chuleta_60s": sesgo60, "pools": pools(M), "adicionales": AD, "eventos": cargar_eventos(), "avisos": avisos, "pasos": pasos, "preguntas": preguntas, "umbrales": U,
            "evidencia": cargar_evidencia()}


# ----------------------------------------------------------------- salida
def to_md(M, E):
    c = E["confluencia"]
    L = [f"# NEXORA · Monitor XAU/USD (chuleta) · datos {M['generado_utc']}", "",
         f"**{c['lectura']}** ({c['favorables']} a favor / {c['contrarias']} en contra / {c['sin_dato']} sin dato) · liquidez {c['liquidez']} · precio {c['precio']} · chuleta 60 s: {E['chuleta_60s']}", ""]
    L += [f"⚠️ {a}" for a in E["avisos"]] + ["", "## Panel principal", "", "| Dato | Dir. | Valor | Estado | Lectura |", "|---|---|---|---|---|"]
    L += [f"| {p['dato']} | {p['dir']} | {p['valor']} | {p['estado']} | {p['lectura']} |" for p in E["panel"]]
    L += ["", "## Datos adicionales NEXORA (no puntúan)", ""] + [f"- {a['dato']}: {a['valor']} · {a['lectura']}" for a in E.get("adicionales", [])]
    L += ["", "## Comparaciones clave", ""] + [f"- {x['par']} — {x['estado']} · {x['detalle']}" for x in E["comparaciones"]]
    L += ["", "## De la macro a la entrada", ""] + [f"{p['n']}. {p['paso']} — {p['estado']} · {p['detalle']}" for p in E["pasos"]]
    L += ["", "## Las 10 preguntas", ""] + [f"{q['n']}) {q['pregunta']} → {q['respuesta']}" for q in E["preguntas"]]
    if M.get("errores"):
        L += ["", "Descargas fallidas (SIN DATO): " + "; ".join(f"{k}: {v}" for k, v in M["errores"].items())]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    M = medir()
    E = evaluar(M)
    os.makedirs(a.out, exist_ok=True)
    stamp = TODAY.strftime("%Y%m%d")
    Mout = {k: v for k, v in M.items() if not k.startswith("_")}
    p = os.path.join(a.out, f"oro_xau_{stamp}.json")
    json.dump({"metricas": Mout, "evaluacion": E}, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=str)
    open(os.path.join(a.out, f"oro_xau_{stamp}.md"), "w", encoding="utf-8").write(to_md(Mout, E))
    print(p)
    print(E["confluencia"])
    if M["errores"]:
        print("ERRORES:", json.dumps(M["errores"], ensure_ascii=False))


if __name__ == "__main__":
    main()
