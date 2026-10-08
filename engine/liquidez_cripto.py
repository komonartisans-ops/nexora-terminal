#!/usr/bin/env python3
"""
NEXORA · Monitor de liquidez cripto — v2 (fiel a las 3 guías del usuario).

Documentos de referencia (Liquidez_Cripto/fuentes_pdf):
  G  = "Guía para leer la liquidez Bitcoin y criptomonedas"
  C1 = "Chuleta — cómo leer los 13 indicadores de liquidez"
  C2 = "Chuleta explicada — cómo leer los 13 indicadores"

Estructura de la evaluación (cada bloque indica de qué documento sale):
  A. CHECKLIST DE GIRO (G, "Cómo detectar que la liquidez empieza a girar"): 8 condiciones.
  B. SECUENCIA ①→⑦ (C2, "Secuencia para aprenderla"): hasta dónde llega la cadena.
  C. SEMÁFORO DE LOS 13 (C1/C2), separado en NÚCLEO DIARIO y CONTEXTO (C1/C2 "Revisión diaria":
     TGA → RRP → reservas → 2Y → 10Y → NFCI → FedWatch → DXY → BTC; M2, H.4.1 y Treasury = contexto).
     SOFR = detector de estrés (C1/C2).
  D. DATOS ADICIONALES NO PEDIDOS POR LAS GUÍAS (etiquetados): stablecoins, apalancamiento
     (funding y open interest), prima Coinbase, amplitud de altcoins, flujos ETF (web).

Los UMBRALES numéricos NO están en las guías (solo dan direcciones ↑/↓): son CRITERIO NEXORA,
fijos y publicados en el informe para que cualquier lectura sea reproducible.

Solo biblioteca estándar. Sin claves. Uso: python liquidez_cripto.py [--out DIR]
Unidades: T$ = billones (trillion) USD; B$ = miles de millones (billion) USD.
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
import time
import urllib.request

UA = {"User-Agent": "curl/8.0"}  # FRED corta UAs de navegador o personalizados
TODAY = dt.date.today()

# ----------------------------------------------------------------- UMBRALES (CRITERIO NEXORA)
UMBRAL = {
    "reservas_pct_4s": 0.5,      # % en 4 semanas; además mismo signo a 3 meses ("↑ sostenido")
    "tga_b_4s": 25.0,            # B$ en 4 semanas
    "rrp_b_4s": 0.0,             # la guía solo pide dirección: cualquier caída cuenta (se avisa si el saldo < 50 B$)
    "rrp_agotado_b": 50.0,
    "t2y_pb_4s": 10.0,           # "estable" = ±10 pb en 4 semanas
    "t10y_pb_4s": 10.0,          # "estable" = hasta +10 pb; "↑ fuerte" = >+20 pb en 4s o >+15 pb en 1s
    "t10y_fuerte_4s": 20.0,
    "t10y_fuerte_1s": 15.0,
    "nfci_4s": 0.02,
    "sofr_salto_pb": 10.0,       # 5 días, descontando cambios del IORB
    "dxy_pct_4s": 0.5,
    "h41_pct_4s": 0.2,
    "subasta_btc_rel": 0.95,     # bid-to-cover < 95 % de la media de las 6 previas = absorción débil
    "alts_amplitud": 0.6,        # ≥60 % de la cesta bate a BTC en 30 días
}
ALTS = ["SOL", "ADA", "XRP", "AVAX", "LINK", "DOT", "DOGE"]  # G: "ADA, SOL y resto"
# ----------------------------------------------------------------- utilidades de red
def get(url: str, timeout: int = 45, tries: int = 3) -> bytes:
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (k + 1))
    raise last


def get_json(url: str, tries: int = 3):
    """JSON con reintento también si el servidor devuelve una página de error en vez de JSON (fallo transitorio)."""
    last = None
    for k in range(tries):
        try:
            return json.loads(get(url).decode("utf-8"))
        except ValueError as e:
            last = e
            time.sleep(3 * (k + 1))
    raise last


def fred(series: str, start: str = "2024-01-01") -> list[tuple[dt.date, float]]:
    """Serie FRED vía fredgraph.csv (sin clave). Devuelve [(fecha, valor)] ordenado."""
    raw = get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd={start}").decode()
    out = []
    for row in csv.DictReader(io.StringIO(raw)):
        v = row.get(series)
        if v in (None, "", "."):
            continue
        out.append((dt.date.fromisoformat(row["observation_date"]), float(v)))
    return out


def at_or_before(series, date):
    """Último valor con fecha <= date."""
    cand = [x for x in series if x[0] <= date]
    return cand[-1] if cand else None


def change(series, days: int):
    """(último, valor hace `days` días naturales, delta absoluto, delta %)."""
    if not series:
        return None
    last = series[-1]
    prev = at_or_before(series, last[0] - dt.timedelta(days=days))
    if not prev:
        return None
    d = last[1] - prev[1]
    pct = (d / prev[1] * 100) if prev[1] else None
    return {"fecha": last[0].isoformat(), "valor": last[1], "fecha_ref": prev[0].isoformat(),
            "valor_ref": prev[1], "delta": d, "delta_pct": pct}


def arrow(delta, tol):
    if delta is None:
        return "?"
    return "↑" if delta > tol else "↓" if delta < -tol else "→"


def safe(fn, *a, **k):
    try:
        return fn(*a, **k), None
    except Exception as e:  # noqa: BLE001 — se registra y el informe marca NO CONFIRMADO
        return None, f"{type(e).__name__}: {e}"


# ----------------------------------------------------------------- descargas específicas
def dts_tga(days_back: int = 120):
    start = (TODAY - dt.timedelta(days=days_back)).isoformat()
    url = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/"
           f"operating_cash_balance?filter=record_date:gte:{start}&sort=record_date&page[size]=1000"
           "&fields=record_date,account_type,open_today_bal,close_today_bal")
    rows = get_json(url)["data"]
    by = {}
    for r in rows:
        d = dt.date.fromisoformat(r["record_date"])
        at = r["account_type"]
        val = r["open_today_bal"] if r["open_today_bal"] not in ("null", None) else r["close_today_bal"]
        if val in ("null", None):
            continue
        rec = by.setdefault(d, {})
        if "Closing Balance" in at:
            rec["cierre"] = float(val)
        elif "Total TGA Deposits" in at:
            rec["ingresos"] = float(val)
        elif "Total TGA Withdrawals" in at:
            rec["gastos"] = float(val)
    # millones de USD
    return [(d, v) for d, v in sorted(by.items()) if "cierre" in v]


def dts_debt(days_back: int = 10):
    """Emisión y amortización de deuda en efectivo (tabla IIIB) de los últimos días hábiles."""
    start = (TODAY - dt.timedelta(days=days_back)).isoformat()
    url = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/"
           f"deposits_withdrawals_operating_cash?filter=record_date:gte:{start}&page[size]=2000"
           "&fields=record_date,transaction_type,transaction_catg,transaction_today_amt")
    out = {}
    for r in get_json(url)["data"]:
        c = r["transaction_catg"]
        if "Public Debt Cash" not in c:
            continue
        rec = out.setdefault(r["record_date"], {"emision": 0.0, "amortizacion": 0.0})
        v = float(r["transaction_today_amt"]) if r["transaction_today_amt"] not in ("null", None) else 0.0
        if r["transaction_type"] == "Deposits":
            rec["emision"] += v
        else:
            rec["amortizacion"] += v
    return dict(sorted(out.items()))


def nyfed_rrp(days_back: int = 120):
    start = (TODAY - dt.timedelta(days=days_back)).isoformat()
    j = get_json(f"https://markets.newyorkfed.org/api/rp/reverserepo/propositions/search.json?startDate={start}")
    ops = [(dt.date.fromisoformat(o["operationDate"]), o["totalAmtAccepted"] / 1e9)
           for o in j["repo"]["operations"] if o.get("operationType") == "Reverse Repo"]
    agg = {}
    for d, v in ops:  # puede haber más de una operación por día
        agg[d] = agg.get(d, 0) + v
    return sorted(agg.items())  # miles de millones USD


def nyfed_sofr(n: int = 70):
    j = get_json(f"https://markets.newyorkfed.org/api/rates/secured/sofr/last/{n}.json")
    rows = [(dt.date.fromisoformat(r["effectiveDate"]), r["percentRate"], r.get("percentPercentile99"),
             r.get("volumeInBillions")) for r in j["refRates"]]
    return sorted(rows)


def auctions(days_back: int = 14):
    start = (TODAY - dt.timedelta(days=days_back)).isoformat()
    hist_start = (TODAY - dt.timedelta(days=400)).isoformat()
    base = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query"
    f = ("&fields=auction_date,security_type,security_term,offering_amt,bid_to_cover_ratio,"
         "high_yield,high_discnt_rate,primary_dealer_accepted,total_accepted")
    recent = get_json(f"{base}?filter=auction_date:gte:{start}&sort=-auction_date&page[size]=200{f}")["data"]
    upcoming = [{"fecha": a["auction_date"], "tipo": a["security_type"], "plazo": a["security_term"],
                 "importe_mm": float(a["offering_amt"]) / 1e6 if a["offering_amt"] not in ("null", None) else None}
                for a in recent if a["bid_to_cover_ratio"] in ("null", None) and a["auction_date"] >= TODAY.isoformat()]
    hist = get_json(f"{base}?filter=auction_date:gte:{hist_start}&sort=-auction_date&page[size]=2000{f}")["data"]
    out = []
    for a in recent:
        if a["bid_to_cover_ratio"] in ("null", None):
            continue  # anunciada, no celebrada
        term, typ = a["security_term"], a["security_type"]
        peers = [float(h["bid_to_cover_ratio"]) for h in hist
                 if h["security_term"] == term and h["security_type"] == typ
                 and h["auction_date"] < a["auction_date"] and h["bid_to_cover_ratio"] not in ("null", None)][:6]
        btc = float(a["bid_to_cover_ratio"])
        avg = statistics.mean(peers) if peers else None
        pd_share = None
        try:
            pd_share = float(a["primary_dealer_accepted"]) / float(a["total_accepted"]) * 100
        except (TypeError, ValueError, ZeroDivisionError):
            pass
        out.append({"fecha": a["auction_date"], "tipo": typ, "plazo": term,
                    "importe_mm": float(a["offering_amt"]) / 1e6 if a["offering_amt"] not in ("null", None) else None,
                    "bid_to_cover": btc, "media_6_previas": avg,
                    "rendimiento": a["high_yield"] if a["high_yield"] not in ("null", None) else a["high_discnt_rate"],
                    "primary_dealers_pct": pd_share})
    return {"celebradas": out, "proximas": sorted(upcoming, key=lambda x: x["fecha"])}


def coinbase(product: str, days: int = 120):
    end = dt.datetime.utcnow().replace(microsecond=0)
    start = end - dt.timedelta(days=days)
    url = (f"https://api.exchange.coinbase.com/products/{product}/candles?granularity=86400"
           f"&start={start.isoformat()}Z&end={end.isoformat()}Z")
    rows = get_json(url)  # [time, low, high, open, close, volume]
    today_utc = dt.datetime.utcnow().date()  # la vela del día en curso está incompleta: se excluye
    return sorted((dt.datetime.utcfromtimestamp(r[0]).date(), float(r[4]), float(r[5])) for r in rows
                  if dt.datetime.utcfromtimestamp(r[0]).date() < today_utc)


def coingecko_global():
    d = get_json("https://api.coingecko.com/api/v3/global")["data"]
    return {"mcap_total_usd": d["total_market_cap"]["usd"], "volumen_24h_usd": d["total_volume"]["usd"],
            "dominancia_btc_pct": d["market_cap_percentage"]["btc"],
            "dominancia_eth_pct": d["market_cap_percentage"]["eth"],
            "mcap_cambio_24h_pct": d.get("market_cap_change_percentage_24h_usd")}


def stablecoins():
    rows = get_json("https://stablecoins.llama.fi/stablecoincharts/all")
    s = [(dt.datetime.utcfromtimestamp(int(r["date"])).date(), r["totalCirculatingUSD"]["peggedUSD"] / 1e9)
         for r in rows if r.get("totalCirculatingUSD", {}).get("peggedUSD")]
    return s[-200:]




# ----------------------------------------------------------------- descargas adicionales (v2)
def ecb_fx(days_back: int = 150):
    """Tipos de referencia BCE (divisa por EUR), diarios. Base de la réplica del DXY."""
    start = (TODAY - dt.timedelta(days=days_back)).isoformat()
    raw = get("https://data-api.ecb.europa.eu/service/data/EXR/D.USD+JPY+GBP+CAD+SEK+CHF.EUR.SP00.A"
              f"?startPeriod={start}&format=csvdata").decode()
    out = {}
    for row in csv.DictReader(io.StringIO(raw)):
        if row.get("OBS_VALUE"):
            out.setdefault(row["CURRENCY"], {})[dt.date.fromisoformat(row["TIME_PERIOD"])] = float(row["OBS_VALUE"])
    return out


def dxy_replica(fx):
    """Fórmula pública de ICE: DXY = 50,14348112 · EURUSD^-0,576 · USDJPY^0,136 · GBPUSD^-0,119 ·
    USDCAD^0,091 · USDSEK^0,042 · USDCHF^0,036. Aplicada a los fixings del BCE (14:15 CET), no al cierre de ICE."""
    dates = sorted(set.intersection(*[set(v) for v in fx.values()]))
    out = []
    for d in dates:
        u = fx["USD"][d]
        eurusd, usdjpy, gbpusd = u, fx["JPY"][d] / u, u / fx["GBP"][d]
        usdcad, usdsek, usdchf = fx["CAD"][d] / u, fx["SEK"][d] / u, fx["CHF"][d] / u
        v = (50.14348112 * eurusd ** -0.576 * usdjpy ** 0.136 * gbpusd ** -0.119 *
             usdcad ** 0.091 * usdsek ** 0.042 * usdchf ** 0.036)
        out.append((d, v))
    return out


def okx_funding(inst: str):
    rows = get_json(f"https://www.okx.com/api/v5/public/funding-rate-history?instId={inst}&limit=100")["data"]
    return sorted((dt.datetime.utcfromtimestamp(int(r["fundingTime"]) / 1000), float(r["realizedRate"] or r["fundingRate"]))
                  for r in rows)


def okx_oi(ccy: str = "BTC"):
    rows = get_json(f"https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-volume?ccy={ccy}&period=1D")["data"]
    return sorted((dt.datetime.utcfromtimestamp(int(r[0]) / 1000).date(), float(r[1])) for r in rows)


def okx_close(inst: str = "BTC-USDT", limit: int = 40):
    rows = get_json(f"https://www.okx.com/api/v5/market/history-candles?instId={inst}&bar=1Dutc&limit={limit}")["data"]
    return {dt.datetime.utcfromtimestamp(int(r[0]) / 1000).date(): float(r[4]) for r in rows if r[8] == "1"}




# ----------------------------------------------------------------- descargas v3 (contexto global y riesgo)
def treasury_curve(years: int = 2):
    """Curva oficial del Tesoro (Daily Par Yield Curve). Más reciente que FRED (sin desfase de un día)."""
    out = {}
    for y in range(TODAY.year - years + 1, TODAY.year + 1):
        raw = get("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/"
                  f"{y}/all?type=daily_treasury_yield_curve&field_tdr_date_value={y}&page&_format=csv").decode()
        for row in csv.DictReader(io.StringIO(raw)):
            try:
                d = dt.datetime.strptime(row["Date"], "%m/%d/%Y").date()
                out[d] = {"2Y": float(row["2 Yr"]), "10Y": float(row["10 Yr"])}
            except (ValueError, KeyError):
                continue
    s = sorted(out.items())
    return [(d, v["2Y"]) for d, v in s], [(d, v["10Y"]) for d, v in s]


def g3_liquidez():
    """Balances Fed + BCE + BoJ en USD (T$), mensual. PBoC excluido: sin serie gratuita fiable."""
    fed = fred("WALCL", "2023-01-01")            # mill. USD
    ecb = fred("ECBASSETSW", "2023-01-01")       # mill. EUR
    boj = fred("JPNASSETS", "2023-01-01")        # 100 mill. JPY
    eur = fred("DEXUSEU", "2023-01-01")          # USD por EUR
    jpy = fred("DEXJPUS", "2023-01-01")          # JPY por USD
    months = sorted({(d.year, d.month) for d, _ in boj})
    rows = []
    for (y, m) in months:
        end = (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1))
        f, e, b = at_or_before(fed, end), at_or_before(ecb, end), at_or_before(boj, end)
        fx_e, fx_j = at_or_before(eur, end), at_or_before(jpy, end)
        if not all((f, e, b, fx_e, fx_j)):
            continue
        usd = f[1] / 1e6 + e[1] * fx_e[1] / 1e6 + b[1] * 1e8 / fx_j[1] / 1e12
        local = {"fed": f[1], "ecb": e[1], "boj": b[1]}
        rows.append((end, usd, local))
    return rows


def cftc_yen():
    url = ("https://publicreporting.cftc.gov/resource/gpe5-46if.json?$where=contract_market_name=%27JAPANESE%20YEN%27"
           "&$order=report_date_as_yyyy_mm_dd%20DESC&$limit=6&$select=report_date_as_yyyy_mm_dd,lev_money_positions_long,lev_money_positions_short")
    rows = get_json(url)
    return sorted((r["report_date_as_yyyy_mm_dd"][:10], int(r["lev_money_positions_long"]) - int(r["lev_money_positions_short"])) for r in rows)


def deribit_dvol(days: int = 370):
    end = int(time.time() * 1000)
    start = end - days * 86400 * 1000
    j = get_json(f"https://www.deribit.com/api/v2/public/get_volatility_index_data?currency=BTC&resolution=1D"
                 f"&start_timestamp={start}&end_timestamp={end}")
    return sorted((dt.datetime.utcfromtimestamp(r[0] / 1000).date(), float(r[4])) for r in j["result"]["data"])


def deribit_opciones():
    res = get_json("https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency=BTC&kind=option")["result"]
    puts = sum(r["open_interest"] for r in res if r["instrument_name"].endswith("-P"))
    calls = sum(r["open_interest"] for r in res if r["instrument_name"].endswith("-C"))
    px = next((r.get("estimated_delivery_price") for r in res if r.get("estimated_delivery_price")), None)
    by_exp = {}
    for r in res:
        exp = r["instrument_name"].split("-")[1]
        by_exp[exp] = by_exp.get(exp, 0) + r["open_interest"]
    def parse(e):
        try:
            return dt.datetime.strptime(e, "%d%b%y").date()
        except ValueError:
            return None
    exps = sorted(((parse(e), oi) for e, oi in by_exp.items() if parse(e)), key=lambda x: x[0])
    prox = [(d, oi) for d, oi in exps if TODAY <= d <= TODAY + dt.timedelta(days=35)]
    top = sorted(prox, key=lambda x: -x[1])[:3]
    return {"put_call_oi": puts / calls if calls else None, "oi_total_btc": puts + calls, "precio_ref": px,
            "vencimientos": [{"fecha": d.isoformat(), "oi_btc": oi, "nocional_B": oi * (px or 0) / 1e9} for d, oi in top]}


def stable_asset(asset_id: int):
    rows = get_json(f"https://stablecoins.llama.fi/stablecoincharts/all?stablecoin={asset_id}")
    return [(dt.datetime.utcfromtimestamp(int(r["date"])).date(), r["totalCirculatingUSD"]["peggedUSD"] / 1e9)
            for r in rows[-120:] if r.get("totalCirculatingUSD", {}).get("peggedUSD")]


def corr(a, b):
    n = len(a)
    if n < 20:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    va = math.sqrt(sum((x - ma) ** 2 for x in a)); vb = math.sqrt(sum((y - mb) ** 2 for y in b))
    return cov / (va * vb) if va and vb else None


def medir_contexto(M, cr):
    """Capa E (no está en las guías): liquidez global, yen, tipos reales, riesgo, opciones, stablecoins por emisor."""
    errors = M["errores"]
    K = {}

    def load(key, fn, *a):
        v, e = safe(fn, *a)
        if e:
            errors[key] = e
        return v

    g3 = load("G3", g3_liquidez)
    if g3 and len(g3) >= 4:
        last, m3 = g3[-1], g3[-4]
        loc = sum((last[2][k] / m3[2][k] - 1) for k in ("fed", "ecb", "boj")) / 3 * 100
        K["g3"] = {"mes": last[0].strftime("%Y-%m"), "valor_T": last[1], "pct_3m_usd": (last[1] / m3[1] - 1) * 100,
                   "pct_3m_local": loc}
    fx = load("DEXJPUS", fred, "DEXJPUS")
    yen = load("CFTC_JPY", cftc_yen)
    if fx:
        a, b = change(fx, 14), change(fx, 28)
        K["yen"] = {"fecha": a["fecha"], "usdjpy": a["valor"], "pct_2s": a["delta_pct"], "pct_4s": b["delta_pct"]}
        if yen and len(yen) >= 2:
            K["yen"].update({"cftc_fecha": yen[-1][0], "cftc_neto": yen[-1][1], "cftc_delta_1s": yen[-1][1] - yen[-2][1]})
    for key, sid in (("real10", "DFII10"), ("be10", "T10YIE"), ("hy", "BAMLH0A0HYM2"), ("vix", "VIXCLS"), ("nasdaq", "NASDAQCOM")):
        s = load(sid, fred, sid)
        if s:
            a = change(s, 28)
            K[key] = {"fecha": a["fecha"], "valor": a["valor"], "delta_4s": a["delta"], "pct_4s": a["delta_pct"]}
            if key == "nasdaq" and cr.get("BTC"):
                nd = dict(s)
                bt = {d: c for d, c, _ in cr["BTC"]}
                common = sorted(set(nd) & set(bt))[-61:]
                ra = [math.log(bt[common[i]] / bt[common[i - 1]]) for i in range(1, len(common))]
                rb = [math.log(nd[common[i]] / nd[common[i - 1]]) for i in range(1, len(common))]
                K[key]["corr_btc_60d"] = corr(ra, rb)
    dv = load("DVOL", deribit_dvol)
    if dv:
        vals = [v for _, v in dv]
        K["dvol"] = {"fecha": dv[-1][0].isoformat(), "valor": vals[-1], "media_30d": statistics.mean(vals[-30:]),
                     "percentil_1a": sum(v <= vals[-1] for v in vals) / len(vals) * 100}
    op = load("DERIBIT_OPC", deribit_opciones)
    if op:
        K["opciones"] = op
    for k, i in (("usdt", 1), ("usdc", 2)):
        s = load(f"STABLE_{k.upper()}", stable_asset, i)
        if s:
            a = change(s, 30)
            K[k] = {"valor_B": a["valor"], "delta_30d_B": a["delta"], "pct_30d": a["delta_pct"]}
    M["contexto"] = K


PANEL_U = {"g3_pct_3m": 1.0, "real10_pb": 10.0, "nasdaq_pct": 5.0, "vix_alto": 25.0, "vix_bajo": 18.0,
           "hy_pb": 25.0, "yen_pct_2s": 3.0, "pc_alto": 1.0, "pc_bajo": 0.6}


def evaluar_contexto(M):
    """Panel E: CRITERIO NEXORA. No entra en la lectura de las guías; se muestra al lado."""
    K = M.get("contexto", {})
    U = PANEL_U
    P = []

    def add(nombre, estado, valor, lectura, fuente):
        P.append({"nombre": nombre, "estado": estado, "valor": valor, "lectura": lectura, "fuente": fuente})
    g = K.get("g3")
    if g:
        s = FAV if g["pct_3m_local"] > U["g3_pct_3m"] else DES if g["pct_3m_local"] < -U["g3_pct_3m"] else NEU
        add("Liquidez global G3 (Fed + BCE + BoJ)", s, f"{g['valor_T']:.2f} T$",
            f"3m en moneda local {g['pct_3m_local']:+.2f}% · en USD {g['pct_3m_usd']:+.2f}% ({g['mes']}); PBoC no incluido",
            "FRED: WALCL, ECBASSETSW, JPNASSETS, DEXUSEU, DEXJPUS")
    y = K.get("yen")
    if y:
        s = DES if y["pct_2s"] < -U["yen_pct_2s"] else NEU
        extra = f" · CFTC fondos apalancados neto {y['cftc_neto']:+,} ({y['cftc_delta_1s']:+,} en 1s, {y['cftc_fecha']})" if "cftc_neto" in y else ""
        add("Carry trade del yen", s, f"USDJPY {y['usdjpy']:.2f}",
            f"2s {y['pct_2s']:+.2f}% · 4s {y['pct_4s']:+.2f}%{extra}. Yen apreciándose más de un 3% en 2 semanas = riesgo de deshacer carry",
            "Fed H.10 (DEXJPUS) + CFTC TFF")
    r = K.get("real10")
    if r:
        pb = r["delta_4s"] * 100
        be = K.get("be10")
        s = FAV if pb < -U["real10_pb"] else DES if pb > U["real10_pb"] else NEU
        add("Tipo real 10Y (TIPS)", s, f"{r['valor']:.2f}%",
            f"4s {pb:+.0f} pb" + (f" · breakeven 10Y {be['valor']:.2f}% ({be['delta_4s']*100:+.0f} pb): la subida del 10Y es "
                                  f"{'sobre todo real' if abs(pb) > abs(be['delta_4s']*100) else 'sobre todo inflación'}" if be else ""),
            "FRED DFII10, T10YIE")
    n = K.get("nasdaq")
    if n:
        s = FAV if n["pct_4s"] > 0 else DES if n["pct_4s"] < -U["nasdaq_pct"] else NEU
        c = n.get("corr_btc_60d")
        add("Nasdaq", s, f"{n['valor']:,.0f}", f"4s {n['pct_4s']:+.1f}%" + (f" · correlación con BTC a 60 días {c:+.2f}" if c is not None else ""),
            "FRED NASDAQCOM")
    v = K.get("vix")
    if v:
        s = DES if v["valor"] > U["vix_alto"] else FAV if v["valor"] < U["vix_bajo"] else NEU
        add("VIX", s, f"{v['valor']:.2f}", f"4s {v['delta_4s']:+.2f} ({v['fecha']})", "CBOE vía FRED VIXCLS")
    h = K.get("hy")
    if h:
        pb = h["delta_4s"] * 100
        s = FAV if pb < 0 else DES if pb > U["hy_pb"] else NEU
        add("Diferencial high yield", s, f"{h['valor']*100:.0f} pb", f"4s {pb:+.0f} pb", "ICE BofA vía FRED BAMLH0A0HYM2")
    d = K.get("dvol")
    if d:
        add("Volatilidad implícita BTC (DVOL)", NEU, f"{d['valor']:.1f}",
            f"media 30d {d['media_30d']:.1f} · percentil 1 año {d['percentil_1a']:.0f}", "Deribit")
    o = K.get("opciones")
    if o and o["put_call_oi"]:
        s = DES if o["put_call_oi"] > U["pc_alto"] else FAV if o["put_call_oi"] < U["pc_bajo"] else NEU
        vto = "; ".join(f"{x['fecha']} {x['oi_btc']:,.0f} BTC (~{x['nocional_B']:.1f} B$)" for x in o["vencimientos"])
        add("Opciones BTC: put/call (open interest)", s, f"{o['put_call_oi']:.2f}", f"vencimientos grandes: {vto}", "Deribit")
    for k, nm in (("usdt", "USDT"), ("usdc", "USDC")):
        x = K.get(k)
        if x:
            s = FAV if x["pct_30d"] > 1 else DES if x["pct_30d"] < -1 else NEU
            add(f"Oferta {nm}", s, f"{x['valor_B']:,.1f} B$", f"30d {x['delta_30d_B']:+,.1f} B$ ({x['pct_30d']:+.2f}%)"
                + (" · USDC ≈ demanda regulada/EE. UU." if k == "usdc" else " · USDT ≈ demanda offshore"), "DefiLlama")
    return {"panel": P, "fav": sum(p["estado"] == FAV for p in P), "des": sum(p["estado"] == DES for p in P), "umbrales": U}


# ----------------------------------------------------------------- estados
FAV, NEU, DES, NA = "FAVORABLE", "NEUTRAL", "DESFAVORABLE", "NO CONFIRMADO"
OK, NO, PARC, SD = "CUMPLE", "NO CUMPLE", "PARCIAL", "SIN DATO"


def tri(x, lo, hi):
    """Clasifica en ↓ / → / ↑ con banda de estabilidad [lo, hi]."""
    if x is None:
        return None
    return "↓" if x < lo else "↑" if x > hi else "→"


def perf(ser, days):
    if not ser:
        return None
    last = ser[-1]
    ref = at_or_before([(d, c) for d, c, _ in ser], last[0] - dt.timedelta(days=days))
    return (last[1] / ref[1] - 1) * 100 if ref else None


def sma(ser, n):
    closes = [c for _, c, _ in ser[-n:]]
    return statistics.mean(closes) if len(closes) == n else None


# ----------------------------------------------------------------- 1) MÉTRICAS (solo números, sin juicio)
def medir():
    errors, raw = {}, {}

    def load(key, fn, *a, **k):
        v, e = safe(fn, *a, **k)
        if e:
            errors[key] = e
        raw[key] = v
        return v

    walcl = load("WALCL", fred, "WALCL"); wshotsl = load("WSHOTSL", fred, "WSHOTSL")
    wresbal = load("WRESBAL", fred, "WRESBAL"); m2 = load("M2SL", fred, "M2SL", "2023-01-01")
    curva = load("TREASURY_CURVE", treasury_curve)
    if curva and curva[0]:
        dgs2, dgs10 = curva
        src_curva = "U.S. Treasury Daily Par Yield Curve"
    else:
        dgs2 = load("DGS2", fred, "DGS2"); dgs10 = load("DGS10", fred, "DGS10")
        src_curva = "Fed H.15 vía FRED"
    nfci = load("NFCI", fred, "NFCI", "2023-01-01"); iorb = load("IORB", fred, "IORB")
    broad = load("DTWEXBGS", fred, "DTWEXBGS")
    tga = load("TGA_DTS", dts_tga); debt = load("DTS_DEUDA", dts_debt)
    rrp = load("RRP", nyfed_rrp); sofr = load("SOFR", nyfed_sofr); auc = load("SUBASTAS", auctions)
    fx = load("ECB_FX", ecb_fx)
    glob = load("GLOBAL", coingecko_global); stb = load("STABLES", stablecoins)
    fund_btc = load("FUNDING_BTC", okx_funding, "BTC-USDT-SWAP")
    fund_eth = load("FUNDING_ETH", okx_funding, "ETH-USDT-SWAP")
    oi = load("OI_BTC", okx_oi, "BTC"); okx_btc = load("OKX_BTC", okx_close, "BTC-USDT")
    cr = {}
    for k, prod in [("BTC", "BTC-USD"), ("ETH", "ETH-USD"), ("ETH/BTC", "ETH-BTC")] + [(a, f"{a}-USD") for a in ALTS]:
        cr[k] = load(k, coinbase, prod)

    M = {"generado_utc": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z", "errores": errors}

    if wresbal:
        a, b = change(wresbal, 28), change(wresbal, 91)
        M["reservas"] = {"fecha": a["fecha"], "valor_T": a["valor"] / 1e6, "pct_4s": a["delta_pct"], "pct_3m": b["delta_pct"]}
    if tga:
        s = [(d, v["cierre"]) for d, v in tga]
        a, b, w = change(s, 28), change(s, 91), change(s, 7)
        last5 = tga[-5:]
        M["tga"] = {"fecha": a["fecha"], "valor_B": a["valor"] / 1000, "delta_4s_B": a["delta"] / 1000,
                    "delta_3m_B": b["delta"] / 1000 if b else None, "delta_1s_B": w["delta"] / 1000 if w else None}
        M["dts"] = {"desde": last5[0][0].isoformat(), "hasta": last5[-1][0].isoformat(),
                    "ingresos_B": sum(v.get("ingresos", 0) for _, v in last5) / 1000,
                    "gastos_B": sum(v.get("gastos", 0) for _, v in last5) / 1000,
                    "deuda_neta_B": (sum(v["emision"] - v["amortizacion"] for v in debt.values()) / 1000) if debt else None}
    if rrp:
        a = change(rrp, 28)
        M["rrp"] = {"fecha": a["fecha"], "valor_B": a["valor"], "delta_4s_B": a["delta"]}
    if m2 and len(m2) >= 14:
        yoy = (m2[-1][1] / m2[-13][1] - 1) * 100
        prev = (m2[-2][1] / m2[-14][1] - 1) * 100
        M["m2"] = {"mes": m2[-1][0].strftime("%Y-%m"), "valor_T": m2[-1][1] / 1000, "yoy": yoy, "yoy_prev": prev,
                   "ann_3m": ((m2[-1][1] / m2[-4][1]) ** 4 - 1) * 100}
    for key, ser in (("t2y", dgs2), ("t10y", dgs10)):
        if ser:
            a, w = change(ser, 28), change(ser, 7)
            M[key] = {"fecha": a["fecha"], "valor": a["valor"], "pb_4s": a["delta"] * 100, "pb_1s": w["delta"] * 100,
                      "pb_1d": (ser[-1][1] - ser[-2][1]) * 100 if len(ser) > 1 else None, "fuente": src_curva}
    if nfci:
        a = change(nfci, 28)
        M["nfci"] = {"fecha": a["fecha"], "valor": a["valor"], "delta_4s": a["delta"]}
    if sofr:
        last, ref = sofr[-1], (sofr[-6] if len(sofr) >= 6 else sofr[0])
        il = at_or_before(iorb, last[0]) if iorb else None
        ir = at_or_before(iorb, ref[0]) if iorb else None
        M["sofr"] = {"fecha": last[0].isoformat(), "valor": last[1], "iorb": il[1] if il else None,
                     "spread_pb": (last[1] - il[1]) * 100 if il else None,
                     "salto_5d_pb": (last[1] - ref[1]) * 100 - ((il[1] - ir[1]) * 100 if il and ir else 0),
                     "p99": last[2], "volumen_B": last[3], "max_20d": max(x[1] for x in sofr[-20:])}
    if walcl:
        a, b = change(walcl, 28), change(walcl, 91)
        t = change(wshotsl, 28) if wshotsl else None
        M["h41"] = {"fecha": a["fecha"], "activos_T": a["valor"] / 1e6, "pct_4s": a["delta_pct"], "pct_3m": b["delta_pct"],
                    "treasuries_4s_B": t["delta"] / 1000 if t else None}
    if auc is not None:
        cel = [x for x in auc["celebradas"] if x["tipo"] != "Bill"]
        M["subastas"] = {"cupon": cel, "letras_n": len([x for x in auc["celebradas"] if x["tipo"] == "Bill"]),
                         "debiles": [x for x in cel if x["media_6_previas"] and x["bid_to_cover"] < x["media_6_previas"] * UMBRAL["subasta_btc_rel"]],
                         "importe_14d_B": sum((x["importe_mm"] or 0) for x in auc["celebradas"]) / 1000,
                         "proximas": auc["proximas"],
                         "importe_proximas_B": sum((x["importe_mm"] or 0) for x in auc["proximas"]) / 1000}
    if fx and all(k in fx for k in ("USD", "JPY", "GBP", "CAD", "SEK", "CHF")):
        dx = dxy_replica(fx)
        a, w = change(dx, 28), change(dx, 7)
        M["dxy"] = {"fecha": a["fecha"], "valor": a["valor"], "pct_4s": a["delta_pct"], "pct_1s": w["delta_pct"],
                    "metodo": "Réplica DXY (fórmula ICE) sobre fixings BCE 14:15 CET"}
    if broad:
        a = change(broad, 28)
        M["dolar_amplio"] = {"fecha": a["fecha"], "valor": a["valor"], "pct_4s": a["delta_pct"]}

    C = {}
    for k, ser in cr.items():
        if ser:
            s50 = sma(ser, 50)
            C[k] = {"precio": ser[-1][1], "fecha": ser[-1][0].isoformat(), "1d": perf(ser, 1), "7d": perf(ser, 7),
                    "30d": perf(ser, 30), "90d": perf(ser, 90), "sma50": s50,
                    "sobre_sma50": (ser[-1][1] > s50) if s50 else None,
                    "vol7d_vs_30d": (statistics.mean(v for *_, v in ser[-7:]) / statistics.mean(v for *_, v in ser[-30:]))
                    if len(ser) >= 30 else None}
    M["cripto"] = C

    X = {}
    if stb:
        a, w = change(stb, 30), change(stb, 7)
        X["stablecoins"] = {"valor_B": a["valor"], "delta_30d_B": a["delta"], "pct_30d": a["delta_pct"], "delta_7d_B": w["delta"]}
    for k, f in (("funding_btc", fund_btc), ("funding_eth", fund_eth)):
        if f:
            last7 = [r for t, r in f if t >= f[-1][0] - dt.timedelta(days=7)]
            X[k] = {"anualizado_7d_pct": statistics.mean(last7) * 3 * 365 * 100,
                    "anualizado_30d_pct": statistics.mean(r for _, r in f) * 3 * 365 * 100,
                    "hasta": f[-1][0].isoformat(timespec="minutes")}
    if oi:
        a, w = change(oi, 30), change(oi, 7)
        X["oi_btc"] = {"valor_B": a["valor"] / 1e9, "pct_30d": a["delta_pct"], "pct_7d": w["delta_pct"] if w else None}
    if okx_btc and cr.get("BTC"):
        cb = {d: c for d, c, _ in cr["BTC"]}
        common = sorted(set(cb) & set(okx_btc))[-7:]
        if common:
            X["prima_coinbase"] = {"media_7d_pct": statistics.mean((cb[d] / okx_btc[d] - 1) * 100 for d in common),
                                   "ultimo_pct": (cb[common[-1]] / okx_btc[common[-1]] - 1) * 100, "fecha": common[-1].isoformat()}
    if glob:
        X["mercado"] = glob
    M["adicionales"] = X
    medir_contexto(M, cr)
    return M


def cargar_evidencia():
    """evidencia.json (lo genera backtest.py) junto al script o en la ruta de LIQ_EVIDENCIA."""
    for p in (os.environ.get("LIQ_EVIDENCIA", ""), os.path.join(os.path.dirname(os.path.abspath(__file__)), "evidencia.json"), "evidencia.json"):
        if p and os.path.exists(p):
            try:
                return json.load(open(p, encoding="utf-8"))
            except (OSError, ValueError):
                pass
    return {}


# ----------------------------------------------------------------- 2) EVALUACIÓN (reglas de las guías + umbrales NEXORA)
def evaluar(M, fedwatch=None):
    """fedwatch: None | {"cambio": "RELAJACION"|"ENDURECIMIENTO"|"SIN CAMBIO", "valor": str, "detalle": str, "fuente": str}"""
    if fedwatch is None:  # FedWatch NEXORA (método CME) automático si no se pasa
        try:
            import fedwatch as _fw
            fedwatch = _fw.para_monitor(_fw.cargar())
        except Exception:  # noqa: BLE001
            fedwatch = None
    U = UMBRAL
    g = lambda k: M.get(k)
    d = {}  # direcciones
    if g("reservas"):
        r = g("reservas")
        d["reservas"] = "↑" if r["pct_4s"] > U["reservas_pct_4s"] and r["pct_3m"] > 0 else \
                        "↓" if r["pct_4s"] < -U["reservas_pct_4s"] and r["pct_3m"] < 0 else "→"
    if g("tga"):
        d["tga"] = tri(g("tga")["delta_4s_B"], -U["tga_b_4s"], U["tga_b_4s"])
    if g("rrp"):
        d["rrp"] = tri(g("rrp")["delta_4s_B"], -U["rrp_b_4s"], U["rrp_b_4s"])
    if g("m2"):
        m = g("m2")
        d["m2"] = "↑" if m["yoy"] > 0 and m["yoy"] >= m["yoy_prev"] else "↓" if m["yoy"] < 0 or m["yoy"] < m["yoy_prev"] else "→"
    if g("t2y"):
        d["t2y"] = tri(g("t2y")["pb_4s"], -U["t2y_pb_4s"], U["t2y_pb_4s"])
    if g("t10y"):
        t = g("t10y")
        d["t10y"] = "↑↑" if t["pb_4s"] > U["t10y_fuerte_4s"] or t["pb_1s"] > U["t10y_fuerte_1s"] else \
                    tri(t["pb_4s"], -U["t10y_pb_4s"], U["t10y_pb_4s"])
    if g("nfci"):
        d["nfci"] = tri(g("nfci")["delta_4s"], -U["nfci_4s"], U["nfci_4s"])
    if g("dxy"):
        d["dxy"] = tri(g("dxy")["pct_4s"], -U["dxy_pct_4s"], U["dxy_pct_4s"])
    if g("h41"):
        d["h41"] = tri(g("h41")["pct_4s"], -U["h41_pct_4s"], U["h41_pct_4s"])
    fw = (fedwatch or {}).get("cambio")
    d["fedwatch"] = {"RELAJACION": "relajación ↑", "ENDURECIMIENTO": "endurecimiento ↑", "SIN CAMBIO": "→"}.get(fw)

    def est(fav, des, known=True):
        return NA if not known else FAV if fav else DES if des else NEU

    ind = []

    def add(n, id_, nombre, nivel, estado, valor, detalle, fuente, frec, nota=""):
        ind.append({"n": n, "id": id_, "nombre": nombre, "nivel": nivel, "estado": estado, "dir": (d.get(id_) or "?") if id_ in d or id_ in ("fedwatch",) else "—",
                    "valor": valor, "detalle": detalle + (f" · {nota}" if nota else ""), "fuente": fuente, "frecuencia": frec})

    r = g("reservas")
    add(1, "reservas", "Reservas bancarias (WRESBAL)", "núcleo", est(d.get("reservas") == "↑", d.get("reservas") == "↓", bool(r)),
        f"{r['valor_T']:.3f} T$" if r else "—", f"4s {r['pct_4s']:+.2f}% · 3m {r['pct_3m']:+.2f}% (semana al {r['fecha']})" if r else "",
        "Fed H.4.1 vía FRED WRESBAL", "semanal")
    t = g("tga")
    add(2, "tga", "TGA — cuenta del Tesoro", "núcleo", est(d.get("tga") == "↓", d.get("tga") == "↑", bool(t)),
        f"{t['valor_B']:,.1f} B$" if t else "—",
        f"1s {t['delta_1s_B']:+,.1f} B$ · 4s {t['delta_4s_B']:+,.1f} B$ · 3m {t['delta_3m_B']:+,.1f} B$ (DTS {t['fecha']})" if t else "",
        "U.S. Treasury Daily Treasury Statement", "diaria")
    q = g("rrp")
    agot = bool(q) and q["valor_B"] < U["rrp_agotado_b"]
    add(3, "rrp", "Reverse Repo (ON RRP)", "núcleo", est(d.get("rrp") == "↓", d.get("rrp") == "↑", bool(q)),
        f"{q['valor_B']:,.1f} B$" if q else "—", f"4s {q['delta_4s_B']:+,.1f} B$ ({q['fecha']})" if q else "",
        "NY Fed Markets API", "diaria",
        "AVISO: saldo < 50 B$, colchón agotado; la dirección cumple la regla pero su efecto sobre la liquidez es despreciable" if agot else "")
    combo = [d.get("tga") == "↓", d.get("rrp") == "↓", d.get("reservas") == "↑"]
    combo_d = [d.get("tga") == "↑", d.get("rrp") == "↑", d.get("reservas") == "↓"]
    add(4, "combo", "Combo TGA + RRP + reservas", "núcleo", est(all(combo), all(combo_d), all(k in d for k in ("tga", "rrp", "reservas"))),
        f"{sum(combo)}/3 liberación · {sum(combo_d)}/3 drenaje",
        f"TGA {d.get('tga')} · RRP {d.get('rrp')} · reservas {d.get('reservas')}. Regla: TGA↓+RRP↓+reservas↑ = liberación; TGA↑+RRP↑+reservas↓ = drenaje",
        "Derivado de 1-3", "—")
    m = g("m2")
    add(5, "m2", "M2", "contexto", est(d.get("m2") == "↑", d.get("m2") == "↓", bool(m)), f"{m['valor_T']:.2f} T$" if m else "—",
        f"interanual {m['yoy']:+.2f}% (mes previo {m['yoy_prev']:+.2f}%) · 3m anualizado {m['ann_3m']:+.2f}% ({m['mes']})" if m else "",
        "Fed H.6 vía FRED M2SL", "mensual")
    for n, k, nm, src in ((6, "t2y", "Treasury 2Y", "DGS2"), (7, "t10y", "Treasury 10Y", "DGS10")):
        x = g(k)
        fav = d.get(k) in ("↓", "→") if k == "t10y" else d.get(k) == "↓"
        des = d.get(k) == "↑↑" if k == "t10y" else d.get(k) == "↑"
        add(n, k, nm, "núcleo", est(fav, des, bool(x)), f"{x['valor']:.2f}%" if x else "—",
            f"1d {x['pb_1d']:+.0f} pb · 1s {x['pb_1s']:+.0f} pb · 4s {x['pb_4s']:+.0f} pb ({x['fecha']})" if x else "",
            x.get("fuente", f"FRED {src}") if x else f"FRED {src}", "diaria")
    x = g("nfci")
    add(8, "nfci", "Chicago Fed NFCI", "núcleo", est(d.get("nfci") == "↓", d.get("nfci") == "↑", bool(x)), f"{x['valor']:+.3f}" if x else "—",
        f"4s {x['delta_4s']:+.3f} (semana al {x['fecha']}); nivel <0 = más laxo que la media histórica" if x else "",
        "Chicago Fed vía FRED NFCI", "semanal")
    s = g("sofr")
    tension = bool(s) and ((s["spread_pb"] is not None and s["spread_pb"] > 0) or s["salto_5d_pb"] > U["sofr_salto_pb"])
    add(9, "sofr", "SOFR", "detector de estrés", est(not tension, tension, bool(s)), f"{s['valor']:.2f}%" if s else "—",
        f"SOFR−IORB {s['spread_pb']:+.0f} pb · salto 5d {s['salto_5d_pb']:+.0f} pb · p99 {s['p99']}% · volumen {s['volumen_B']} B$ ({s['fecha']})" if s else "",
        "NY Fed (SOFR) + Fed (IORB)", "diaria")
    add(10, "fedwatch", "CME FedWatch", "núcleo",
        {"RELAJACION": FAV, "ENDURECIMIENTO": DES, "SIN CAMBIO": NEU}.get(fw, NA),
        (fedwatch or {}).get("valor", "pendiente"),
        (fedwatch or {}).get("detalle", "Sin dato accesible de CME. Nunca se estima."), (fedwatch or {}).get("fuente", "CME Group"), "diaria")
    sb = g("subastas")
    t10 = d.get("t10y")
    if sb:
        weak = bool(sb["debiles"])
        est_sb = DES if weak and t10 == "↑↑" else FAV if not weak and t10 in ("↓", "→") else NEU
        det = (f"14 días: {len(sb['cupon'])} de cupón + {sb['letras_n']} de letras, {sb['importe_14d_B']:,.0f} B$ · "
               f"{len(sb['debiles'])} de cupón con demanda débil · próximos 14 días: {len(sb['proximas'])} subastas anunciadas, "
               f"{sb['importe_proximas_B']:,.0f} B$ · deuda neta en efectivo ≈10 días "
               f"{(g('dts') or {}).get('deuda_neta_B') or 0:+,.1f} B$")
        add(11, "subastas", "Emisiones / subastas Treasury", "contexto", est_sb, "absorción débil" if weak else "absorción normal", det,
            "U.S. Treasury Fiscal Data (auctions_query, DTS IIIB)", "según calendario")
    else:
        add(11, "subastas", "Emisiones / subastas Treasury", "contexto", NA, "—", "", "U.S. Treasury Fiscal Data", "")
    ds = g("dts")
    add(12, "dts", "Daily Treasury Statement", "contexto", est(bool(ds) and ds["gastos_B"] > ds["ingresos_B"],
        bool(ds) and ds["ingresos_B"] > ds["gastos_B"], bool(ds)),
        f"gasta {ds['gastos_B']:,.0f} / ingresa {ds['ingresos_B']:,.0f} B$" if ds else "—",
        f"5 días hábiles {ds['desde']} → {ds['hasta']}: el Tesoro {'gasta más de lo que ingresa' if ds['gastos_B'] > ds['ingresos_B'] else 'acumula caja'}" if ds else "",
        "U.S. Treasury DTS (tablas II y IIIB)", "diaria")
    h = g("h41")
    add(13, "h41", "H.4.1 — balance Fed", "contexto", est(d.get("h41") == "↑", d.get("h41") == "↓", bool(h)),
        f"{h['activos_T']:.3f} T$" if h else "—",
        f"activos 4s {h['pct_4s']:+.2f}% · 3m {h['pct_3m']:+.2f}% · Treasuries 4s {h['treasuries_4s_B']:+,.1f} B$ (semana al {h['fecha']})" if h else "",
        "Fed H.4.1 vía FRED WALCL / WSHOTSL", "semanal")

    # ---- A. Checklist de giro (G)
    def chk(cond, known):
        return SD if not known else OK if cond else NO
    checklist = [
        {"n": 1, "condicion": "Reservas ↑", "estado": chk(d.get("reservas") == "↑", "reservas" in d)},
        {"n": 2, "condicion": "TGA ↓", "estado": chk(d.get("tga") == "↓", "tga" in d)},
        {"n": 3, "condicion": "RRP ↓", "estado": chk(d.get("rrp") == "↓", "rrp" in d),
         "nota": "saldo agotado: efecto despreciable" if agot else ""},
        {"n": 4, "condicion": "M2 ↑", "estado": chk(d.get("m2") == "↑", "m2" in d)},
        {"n": 5, "condicion": "2Y ↓ / estable", "estado": chk(d.get("t2y") in ("↓", "→"), "t2y" in d)},
        {"n": 6, "condicion": "10Y ↓ / estable", "estado": chk(d.get("t10y") in ("↓", "→"), "t10y" in d)},
        {"n": 7, "condicion": "NFCI ↓", "estado": chk(d.get("nfci") == "↓", "nfci" in d)},
        {"n": 8, "condicion": "FedWatch más relajado", "estado": chk(fw == "RELAJACION", fw is not None)},
    ]
    EV = cargar_evidencia()
    for c, cid in zip(checklist, ("reservas", "tga", "rrp", "m2", "t2y", "t10y", "nfci", "fedwatch")):
        c["id"] = cid
        e = (EV.get("condiciones") or {}).get(cid)
        if e:
            c["evidencia"] = (f"2018-hoy: BTC a 8 semanas mediana {e['med8_cumple']:+.1f}% cuando cumple vs {e['med8_no']:+.1f}% cuando no "
                              f"({e['n_cumple']} semanas cumpliendo)")
    n_ok = sum(c["estado"] == OK for c in checklist)
    n_sd = sum(c["estado"] == SD for c in checklist)
    drenaje = [d.get("reservas") == "↓", d.get("tga") == "↑", d.get("rrp") == "↑", d.get("m2") == "↓",
               d.get("t2y") == "↑", d.get("t10y") == "↑↑", d.get("nfci") == "↑", fw == "ENDURECIMIENTO"]
    n_dren = sum(drenaje)

    # ---- B. Secuencia ①→⑦ (C2)
    C = M.get("cripto", {})
    btc, eb = C.get("BTC"), C.get("ETH/BTC")
    alts = {a: C[a]["30d"] - btc["30d"] for a in ALTS if a in C and btc and C[a]["30d"] is not None}
    amp = (sum(v > 0 for v in alts.values()) / len(alts)) if alts else None

    def paso(conds, known=True):
        if not known:
            return SD
        k = sum(conds)
        return OK if k == len(conds) else PARC if k else NO
    secuencia = [
        {"n": 1, "paso": "TGA ↓ + RRP ↓ + reservas ↑", "estado": paso(combo, all(k in d for k in ("tga", "rrp", "reservas"))),
         "detalle": f"{sum(combo)}/3"},
        {"n": 2, "paso": "NFCI ↓ + 2Y ↓ + 10Y estable/↓",
         "estado": paso([d.get("nfci") == "↓", d.get("t2y") == "↓", d.get("t10y") in ("↓", "→")], all(k in d for k in ("nfci", "t2y", "t10y"))),
         "detalle": f"NFCI {d.get('nfci')} · 2Y {d.get('t2y')} · 10Y {d.get('t10y')}"},
        {"n": 3, "paso": "FedWatch más relajado", "estado": paso([fw == "RELAJACION"], fw is not None), "detalle": d.get("fedwatch") or "sin dato"},
        {"n": 4, "paso": "DXY ↓", "estado": paso([d.get("dxy") == "↓"], "dxy" in d),
         "detalle": f"réplica DXY 4s {M['dxy']['pct_4s']:+.2f}%" if g("dxy") else ""},
        {"n": 5, "paso": "BTC confirma", "estado": paso([btc["30d"] > 0, bool(btc["sobre_sma50"])], bool(btc)) if btc else SD,
         "detalle": f"30d {btc['30d']:+.1f}% · {'sobre' if btc['sobre_sma50'] else 'bajo'} media 50d" if btc else ""},
        {"n": 6, "paso": "ETH/BTC ↑", "estado": paso([eb["30d"] > 0, bool(eb["sobre_sma50"])], bool(eb)) if eb else SD,
         "detalle": f"30d {eb['30d']:+.1f}% · {'sobre' if eb['sobre_sma50'] else 'bajo'} media 50d" if eb else ""},
        {"n": 7, "paso": "Altcoins con fuerza relativa", "estado": (OK if amp >= U["alts_amplitud"] else PARC if amp > 0 else NO) if amp is not None else SD,
         "detalle": f"{sum(v > 0 for v in alts.values())}/{len(alts)} baten a BTC en 30d" if alts else ""},
    ]
    hasta = 0
    for p in secuencia:
        if p["estado"] == OK:
            hasta = p["n"]
        else:
            break
    macro_ok = secuencia[0]["estado"] == OK and secuencia[1]["estado"] == OK
    cripto_ok = sum(p["estado"] == OK for p in secuencia[4:])

    # ---- Lectura (CRITERIO NEXORA, con el lenguaje de las guías)
    if ind[3]["estado"] == DES or n_dren >= 5:
        lectura = "DRENAJE DE LIQUIDEZ"
    elif macro_ok and n_ok >= 6:
        lectura = "GIRO DE LIQUIDEZ EN CURSO"
    elif secuencia[0]["estado"] == OK or n_ok >= 4:
        lectura = "SEÑALES INICIALES DE GIRO"
    else:
        lectura = "SIN GIRO DE LIQUIDEZ"
    avisos = []
    if cripto_ok >= 2 and not macro_ok:
        e = EV.get("sin_soporte")
        avisos.append("Cripto (pasos 5-7) responde sin que la liquidez macro (pasos 1-2) lo confirme: movimiento sin soporte de liquidez según las guías."
                      + (f" Evidencia 2018-hoy: en {e['n']} semanas así, BTC a 8 semanas mediana {e['med8']:+.1f}% "
                         f"(positivo {e['pos8']:.0f}% de las veces) frente a {EV['base']['med8']:+.1f}% de media en todo el periodo." if e else ""))
    if agot:
        avisos.append("ON RRP agotado: la condición «RRP ↓» ya no aporta liquidez aunque se cumpla.")
    if tension:
        avisos.append("SOFR en tensión: posible estrés de financiación.")
    if n_sd:
        avisos.append(f"{n_sd} condición(es) sin dato: la lectura es incompleta.")

    return {"indicadores": ind, "direcciones": d, "checklist": checklist,
            "checklist_resumen": {"cumple": n_ok, "sin_dato": n_sd, "total": 8, "drenaje": n_dren},
            "secuencia": secuencia, "secuencia_hasta": hasta, "secuencia_cumplidos": sum(p["estado"] == OK for p in secuencia), "lectura": lectura, "avisos": avisos,
            "nucleo": {"fav": sum(i["estado"] == FAV for i in ind if i["nivel"] == "núcleo"),
                       "des": sum(i["estado"] == DES for i in ind if i["nivel"] == "núcleo"),
                       "n": sum(i["estado"] != NA for i in ind if i["nivel"] == "núcleo")},
            "contexto_13": {"fav": sum(i["estado"] == FAV for i in ind if i["nivel"] == "contexto"),
                         "des": sum(i["estado"] == DES for i in ind if i["nivel"] == "contexto")},
            "umbrales": UMBRAL, "contexto": evaluar_contexto(M), "evidencia": EV}


def to_md(M, E):
    ico = {FAV: "🟢", NEU: "🟠", DES: "🔴", NA: "⚪", OK: "🟢", NO: "🔴", PARC: "🟠", SD: "⚪"}
    cs = E["checklist_resumen"]
    L = [f"# Monitor de liquidez cripto — datos base ({M['generado_utc']})", "",
         f"**Lectura (CRITERIO NEXORA): {E['lectura']}** · checklist de giro {cs['cumple']}/8 (sin dato {cs['sin_dato']}) · "
         f"condiciones de drenaje {cs['drenaje']}/8 · secuencia {E['secuencia_cumplidos']}/7 pasos cumplidos, en orden hasta el paso {E['secuencia_hasta']}", ""]
    L += [f"- ⚠️ {a}" for a in E["avisos"]] + [""]
    L += ["## A. Checklist de giro (Guía)", "", "| # | Condición | Estado |", "|---|---|---|"]
    L += [f"| {c['n']} | {c['condicion']} | {ico[c['estado']]} {c['estado']} {c.get('nota','')} |" for c in E["checklist"]]
    L += ["", "## B. Secuencia ①→⑦ (Chuleta explicada)", "", "| # | Paso | Estado | Detalle |", "|---|---|---|---|"]
    L += [f"| {p['n']} | {p['paso']} | {ico[p['estado']]} {p['estado']} | {p['detalle']} |" for p in E["secuencia"]]
    L += ["", "## C. Semáforo de los 13", "", "| # | Nivel | Indicador | Estado | Dir. | Valor | Detalle | Fuente |", "|---|---|---|---|---|---|---|---|"]
    L += [f"| {i['n']} | {i['nivel']} | {i['nombre']} | {ico[i['estado']]} {i['estado']} | {i['dir']} | {i['valor']} | {i['detalle']} | {i['fuente']} |"
          for i in E["indicadores"]]
    X = M.get("adicionales", {})
    L += ["", "## D. Datos adicionales (no pedidos por las guías)", ""]
    if M.get("dxy"):
        L.append(f"- DXY réplica: {M['dxy']['valor']:.2f} · 1s {M['dxy']['pct_1s']:+.2f}% · 4s {M['dxy']['pct_4s']:+.2f}% ({M['dxy']['fecha']}; {M['dxy']['metodo']})")
    if "stablecoins" in X:
        s = X["stablecoins"]; L.append(f"- Stablecoins: {s['valor_B']:,.1f} B$ · 7d {s['delta_7d_B']:+,.1f} B$ · 30d {s['delta_30d_B']:+,.1f} B$ (DefiLlama)")
    for k in ("funding_btc", "funding_eth"):
        if k in X:
            L.append(f"- Funding {k[-3:].upper()} (OKX, anualizado): 7d {X[k]['anualizado_7d_pct']:+.1f}% · 30d {X[k]['anualizado_30d_pct']:+.1f}%")
    if "oi_btc" in X:
        L.append(f"- Open interest BTC (OKX): {X['oi_btc']['valor_B']:,.2f} B$ · 7d {X['oi_btc']['pct_7d']:+.1f}% · 30d {X['oi_btc']['pct_30d']:+.1f}%")
    if "prima_coinbase" in X:
        L.append(f"- Prima Coinbase vs OKX: media 7d {X['prima_coinbase']['media_7d_pct']:+.3f}% · último {X['prima_coinbase']['ultimo_pct']:+.3f}%")
    if M["errores"]:
        L += ["", "## Descargas fallidas (⚪ NO CONFIRMADO)", ""] + [f"- {k}: {v}" for k, v in M["errores"].items()]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    M = medir()
    E = evaluar(M)
    stamp = TODAY.strftime("%Y%m%d")
    jp = os.path.join(a.out, f"liquidez_cripto_{stamp}.json")
    mp = os.path.join(a.out, f"liquidez_cripto_{stamp}.md")
    with open(jp, "w", encoding="utf-8") as f:
        json.dump({"metricas": M, "evaluacion": E}, f, ensure_ascii=False, indent=2, default=str)
    md = to_md(M, E)
    with open(mp, "w", encoding="utf-8") as f:
        f.write(md)
    print(md)
    print(f"\nGuardado: {jp}\n          {mp}")
    return 0 if len(M["errores"]) < 8 else 1


if __name__ == "__main__":
    sys.exit(main())
