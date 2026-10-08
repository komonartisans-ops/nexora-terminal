#!/usr/bin/env python3
"""
NEXORA · Monitor de Índices USA (S&P 500 · Nasdaq 100 · Dow Jones/US30 · Russell 2000).

Fiel a la «Chuleta completa — Cómo leer los índices» del usuario (Indices/fuentes_pdf). CH = chuleta:
  §1 Panel principal: 18 datos con su lectura si baja / si sube.
  §2 Diferencias entre índices: qué mueve a cada uno y qué añadir al panel.
  §3 Comparaciones rápidas: 9 pares.
  §4 Entorno macro: RISK-ON / RISK-OFF / MIXTO (+ liquidez acompaña/drena).
  §5 De la macro a la entrada: 9 pasos (1-7 calculables; 8-9 manuales: footprint/DOM y decisión).
  §6 Qué mirar según horizonte.  §7 10 preguntas.  §8 Chuleta 60 segundos.
Los UMBRALES numéricos no están en la chuleta: son CRITERIO NEXORA, fijos y publicados (METODOLOGIA_INDICES.md).

Fuentes sin clave: Cboe (SPX, DJX, RUT, VIX, VIX9D, VIX3M, VVIX, SKEW, VXN, RVX), FRED (NASDAQ100, macro),
Nasdaq Data API (OHLC y volumen de ETF: SPY, QQQ, DIA, IWM, RSP, QQEW, SOXX, XLI, XLF, XLY, XLP; NDX y SOX; amplitud del
mercado con el screener de acciones), U.S. Treasury (curvas nominal y real), BCE (réplica DXY), NY Fed, DTS,
CFTC (TFF: futuros de índices), FactSet Earnings Insight (beneficios y revisiones, PDF semanal público),
State Street SSGA (posiciones diarias de XLY/XLP), FRED RRSFS (ventas minoristas reales).
Uso: python indices.py [--out DIR]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import math
import os
import re
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from liquidez_cripto import (TODAY, UMBRAL as U_LIQ, at_or_before, change, dts_tga, dxy_replica, ecb_fx,  # noqa: E402
                             fred, get, get_json, nyfed_rrp, nyfed_sofr, safe)
from oro_xau import corr, delta_n, dirv, pct_n, r2, serie, sma, treasury, z_vel  # noqa: E402

BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
HERE = os.path.dirname(os.path.abspath(__file__))

# ----------------------------------------------------------------- UMBRALES (CRITERIO NEXORA)
U = {
    "t2y_pb_1s": 5.0, "t10y_pb_1s": 5.0, "t10y_rapido_pb_1s": 10.0, "real_pb_1s": 5.0, "be_pb_1s": 3.0,
    "dxy_pct_1s": 0.3, "nfci_4s": 0.02, "vix_pct_1s": 10.0, "vix_alto": 25.0, "velocidad_z": 1.5,
    "vix_ts_backw": 1.0,           # VIX/VIX3M > 1 = backwardation (estrés)
    "rs_pp_20d": 2.0,              # fuerza relativa: > 2 pp en 20 sesiones = supera claramente
    "amplitud_rsp_pp_20d": 1.0,    # RSP vs SPY: ±1 pp en 20 sesiones
    "ad_pct_alto": 60.0, "ad_pct_bajo": 40.0,   # % de grandes compañías al alza en la sesión
    "volumen_rel": 1.2,            # volumen > 1,2x media 20 = participación alta
    "hy_pb_4s": 25.0,              # spread high yield ±25 pb en 4 semanas
    "consumo_13s_pct": 5.0,        # ratio XLY/XLP ±5 % en 13 semanas (63 sesiones) = movimiento relevante
    "consumo_driver": 0.5,         # Amazon+Tesla explican ≥ 50 % del movimiento de XLY = «movido por 2 empresas»
    "sma": 50,
}
U.update({k: U_LIQ[k] for k in ("reservas_pct_4s", "tga_b_4s", "rrp_b_4s", "rrp_agotado_b")})
FAV, CON, NEU, SD, CTX = "FAVORABLE", "DESFAVORABLE", "NEUTRAL", "SIN DATO", "CONTEXTO"
ETFS = ["SPY", "QQQ", "DIA", "IWM", "RSP", "QQEW", "SOXX", "XLI", "XLF", "XLY", "XLP"]


# ----------------------------------------------------------------- descargas
def nq_get(url, timeout=60):
    last = None
    for k in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": BROWSER, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (k + 1))
    raise last


def _num(x):
    x = str(x).replace("$", "").replace(",", "").strip()
    return float(x) if x not in ("", "--", "N/A") else None


def nq_hist(symbol, assetclass="etf", years=10):
    """OHLC + volumen diario (Nasdaq Data). [(fecha, o, h, l, c, vol)] ordenado."""
    start = (TODAY - dt.timedelta(days=365 * years + 5)).isoformat()
    j = nq_get(f"https://api.nasdaq.com/api/quote/{symbol}/historical?assetclass={assetclass}&fromdate={start}&todate={TODAY.isoformat()}&limit=9999")
    rows = []
    for r in (j.get("data") or {}).get("tradesTable", {}).get("rows", []) or []:
        try:
            d = dt.datetime.strptime(r["date"], "%m/%d/%Y").date()
            rows.append((d, _num(r["open"]), _num(r["high"]), _num(r["low"]), _num(r["close"]), _num(r.get("volume", "")) or 0.0))
        except (ValueError, KeyError, TypeError):
            continue
    return sorted(x for x in rows if x[4])


def nq_info(symbol, assetclass="etf"):
    j = nq_get(f"https://api.nasdaq.com/api/quote/{symbol}/info?assetclass={assetclass}")
    p = j["data"]["primaryData"]
    return {"precio": _num(p["lastSalePrice"]), "cambio_pct": _num(str(p.get("percentageChange", "")).replace("%", "")),
            "hora": p.get("lastTradeTimestamp"), "estado_mercado": j["data"].get("marketStatus")}


def cboe(symbol):
    """Histórico diario de índices Cboe. Devuelve [(fecha, cierre)]."""
    raw = get(f"https://cdn.cboe.com/api/global/us_indices/daily_prices/{symbol}_History.csv", timeout=90).decode()
    out = []
    for row in csv.reader(io.StringIO(raw)):
        try:
            d = dt.datetime.strptime(row[0], "%m/%d/%Y").date()
            out.append((d, float(row[-1])))
        except (ValueError, IndexError):
            continue
    return out


def amplitud_mercado():
    """Amplitud de la última sesión: todas las acciones USA del screener de Nasdaq (una descarga)."""
    j = nq_get("https://api.nasdaq.com/api/screener/stocks?tableonly=true&download=true", timeout=120)
    rows = j["data"]["rows"]
    todo, grandes = [], []
    for r in rows:
        pc = _num(str(r.get("pctchange", "")).replace("%", ""))
        mc = _num(r.get("marketCap") or "")
        vol = _num(r.get("volume") or "") or 0
        px = _num(r.get("lastsale") or "")
        if pc is None or not px:
            continue
        todo.append((pc, vol * px))
        if mc and mc >= 10e9:
            grandes.append((pc, vol * px))

    def res(x):
        up = [v for p, v in x if p > 0]
        dn = [v for p, v in x if p < 0]
        tot = sum(v for _, v in x) or 1
        return {"n": len(x), "suben": len(up), "bajan": len(dn), "pct_suben": round(len(up) / len(x) * 100, 1) if x else None,
                "ad_neto": len(up) - len(dn), "volumen_alcista_pct": round(sum(up) / tot * 100, 1)}
    return {"todas": res(todo), "grandes_10B": res(grandes)}


def cftc_indices():
    """CFTC Traders in Financial Futures: fondos apalancados y gestores de activos en futuros de índices."""
    codes = {"S&P 500 (E-mini)": "13874A", "Nasdaq 100 (mini)": "209742", "Dow (x$5)": "124603", "Russell 2000 (E-mini)": "239742"}
    out = {}
    for nm, c in codes.items():
        rows = get_json("https://publicreporting.cftc.gov/resource/gpe5-46if.json?cftc_contract_market_code=" + c +
                        "&$order=report_date_as_yyyy_mm_dd%20DESC&$limit=60&$select=report_date_as_yyyy_mm_dd,lev_money_positions_long,"
                        "lev_money_positions_short,asset_mgr_positions_long,asset_mgr_positions_short,open_interest_all")
        h = sorted(rows, key=lambda r: r["report_date_as_yyyy_mm_dd"])
        g = lambda r, k: int(float(r.get(k) or 0))  # noqa: E731
        lev = [g(r, "lev_money_positions_long") - g(r, "lev_money_positions_short") for r in h]
        am = [g(r, "asset_mgr_positions_long") - g(r, "asset_mgr_positions_short") for r in h]
        last52 = lev[-52:]
        out[nm] = {"fecha": h[-1]["report_date_as_yyyy_mm_dd"][:10], "apalancados_neto": lev[-1], "apalancados_1s": lev[-1] - lev[-2],
                   "apalancados_percentil_52s": round(sum(x <= lev[-1] for x in last52) / len(last52) * 100),
                   "gestores_neto": am[-1], "gestores_1s": am[-1] - am[-2], "oi": g(h[-1], "open_interest_all")}
    return out


def factset_earnings():
    """FactSet Earnings Insight (PDF semanal público, viernes). Devuelve las métricas clave citadas literalmente."""
    for k in range(0, 5):
        d = TODAY - dt.timedelta(days=(TODAY.weekday() - 4) % 7 + 7 * k)
        url = ("https://advantage.factset.com/hubfs/Website/Resources%20Section/Research%20Desk/Earnings%20Insight/"
               f"EarningsInsight_{d.strftime('%m%d%y')}.pdf")
        try:
            raw = get(url, timeout=90, tries=1)
        except Exception:  # noqa: BLE001
            continue
        if not raw.startswith(b"%PDF"):
            continue
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "f.pdf")
            open(p, "wb").write(raw)
            txt = subprocess.run(["pdftotext", "-l", "15", p, "-"], capture_output=True, text=True).stdout
        txt1 = re.sub(r"\s+", " ", txt)
        km = re.search(r"Key Metrics(.*?)To receive this report", txt1)
        bullets = [b.strip() for b in (km.group(1).split("•") if km else []) if b.strip()]
        out = {"fecha_informe": d.isoformat(), "url": url, "metricas_clave": bullets}
        m = re.search(r"For (Q\d \d{4}), the estimated \(year-over-year\) earnings growth rate for the S&P 500 is (-?[\d.]+)%", txt1)
        if m:
            out["trimestre"], out["crecimiento_bpa_pct"] = m.group(1), float(m.group(2))
        m = re.search(r"On ([A-Z][a-z]+ \d+), the estimated \(year-over-year\) earnings growth rate for the S&P 500 for Q\d \d{4} was (-?[\d.]+)%", txt1)
        if m:
            out["referencia_fecha"], out["crecimiento_referencia_pct"] = m.group(1), float(m.group(2))
        m = re.search(r"forward 12-month P/E ratio for the S&P 500 is (\d+\.\d+)", txt1)
        if m:
            out["per_12m"] = float(m.group(1))
        m = re.search(r"5-year average \(?(\d+\.\d+)", txt1)
        if m:
            out["per_media_5a"] = float(m.group(1))
        m = re.search(r"(\d+) S&P 500 companies have issued negative EPS guidance and (\d+) S&P 500 companies have issued positive", txt1)
        if m:
            out["guias_negativas"], out["guias_positivas"] = int(m.group(1)), int(m.group(2))
        m = re.search(r"(The Q\d bottom-up EPS estimate.*?\.)\s", txt1)
        if m:
            out["frase_bpa_bottom_up"] = m.group(1)[:400]
        if "crecimiento_bpa_pct" in out and "crecimiento_referencia_pct" in out:
            dlt = out["crecimiento_bpa_pct"] - out["crecimiento_referencia_pct"]
            out["revision_pp"] = round(dlt, 1)
            out["revision"] = "AL ALZA" if dlt > 0.5 else "A LA BAJA" if dlt < -0.5 else "ESTABLE"
        return out
    raise RuntimeError("FactSet Earnings Insight no disponible en las últimas 5 semanas")


def ssga_pesos(tk, top=5):
    """Posiciones diarias oficiales del ETF (State Street SSGA, xlsx público). Devuelve fecha y principales pesos (%)."""
    import openpyxl
    req = urllib.request.Request(f"https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-{tk.lower()}.xlsx",
                                 headers={"User-Agent": BROWSER})
    with urllib.request.urlopen(req, timeout=60) as r:
        wb = openpyxl.load_workbook(io.BytesIO(r.read()), read_only=True, data_only=True)
    rows = list(wb.active.iter_rows(values_only=True))
    fecha = next((str(x[1]).replace("As of ", "") for x in rows[:6] if x and str(x[0]).startswith("Holdings")), None)
    hdr = next(i for i, x in enumerate(rows) if x and x[0] == "Name")
    pos = []
    for x in rows[hdr + 1:]:
        if not x or not x[1] or x[4] is None:
            continue
        try:
            pos.append({"ticker": str(x[1]), "nombre": str(x[0]).title(), "peso": round(float(x[4]), 2)})
        except (TypeError, ValueError):
            continue
    pos.sort(key=lambda z: -z["peso"])
    return {"fecha": fecha, "principales": pos[:top], "fuente": f"State Street SSGA, posiciones diarias de {tk}"}


def consumo_xly_xlp(xly, xlp, rrsfs=None, pesos=None, amzn=None, tsla=None):
    """Ratio XLY/XLP (consumo discrecional vs básico): nivel, media 200, 13 semanas, confirmación con consumo real
    y concentración (Amazon + Tesla). Indicador de CONTEXTO: no vota en el entorno."""
    r = ratio_series(closes(xly), closes(xlp))
    if len(r) < 210:
        return None
    v = [x[1] for x in r]
    sm = statistics.mean(v[-200:])
    serie_sma = [statistics.mean(v[i - 199:i + 1]) for i in range(len(v) - 30, len(v))]
    cruce = None
    for k in range(1, 30):
        a_, b_ = v[-k] - serie_sma[-k], v[-k - 1] - serie_sma[-k - 1]
        if (a_ > 0) != (b_ > 0):
            cruce = {"hace_sesiones": k - 1, "sentido": "AL ALZA" if a_ > 0 else "A LA BAJA", "fecha": r[-k][0].isoformat()}
            break
    c13 = (v[-1] / v[-64] - 1) * 100
    sobre = v[-1] > sm
    mercado = ("RISK-ON EN CONSUMO" if sobre and c13 > 0 else "DEFENSIVO" if not sobre and c13 < 0 else "MIXTO")
    out = {"ratio": round(v[-1], 4), "fecha": r[-1][0].isoformat(), "sma200": round(sm, 4), "dist_sma200_pct": r2((v[-1] / sm - 1) * 100),
           "20d_pct": r2((v[-1] / v[-21] - 1) * 100), "13s_pct": r2(c13), "max_52s_pct": r2((v[-1] / max(v[-252:]) - 1) * 100),
           "sobre_sma200": sobre, "cruce_reciente": cruce, "mercado": mercado,
           "xly_13s_pct": r2(pct_n(closes(xly), 63)), "xlp_13s_pct": r2(pct_n(closes(xlp), 63)),
           "fuente": "Nasdaq Data (cierres de XLY y XLP; ratio de precios, igual que TradingView)"}
    # consumo real (datos oficiales): media 3 meses vs 3 anteriores
    if rrsfs and len(rrsfs) >= 6:
        a3 = statistics.mean(x[1] for x in rrsfs[-3:])
        b3 = statistics.mean(x[1] for x in rrsfs[-6:-3])
        d = (a3 / b3 - 1) * 100
        out["consumo_real"] = {"mes": rrsfs[-1][0].strftime("%Y-%m"), "3m_vs_3m_pct": r2(d), "estado": "SE ENFRÍA" if d < 0 else "FIRME",
                               "fuente": "Census, ventas minoristas reales (FRED RRSFS), media 3 meses vs 3 anteriores"}
        frio = d < 0
        out["confirmacion"] = ("CONFIRMADO: el mercado se pone defensivo y el consumo real se enfría" if mercado == "DEFENSIVO" and frio else
                               "NO CONFIRMADO: el mercado se pone defensivo pero el consumo real sigue firme" if mercado == "DEFENSIVO" else
                               "CONFIRMADO: el mercado apuesta por el consumo y el consumo real está firme" if mercado == "RISK-ON EN CONSUMO" and not frio else
                               "NO CONFIRMADO: el mercado apuesta por el consumo pero el consumo real se enfría" if mercado == "RISK-ON EN CONSUMO" else
                               "SIN SEÑAL CLARA DEL MERCADO (ratio mixto)")
    else:
        out["confirmacion"] = "SIN DATO de consumo real"
    # concentración: ¿lo mueven Amazon y Tesla?
    if pesos and pesos.get("principales"):
        w = {x["ticker"]: x["peso"] for x in pesos["principales"]}
        C = {"fecha_pesos": pesos["fecha"], "pesos": pesos["principales"], "amzn_tsla_peso": r2(w.get("AMZN", 0) + w.get("TSLA", 0)), "fuente": pesos["fuente"]}
        ra = pct_n(closes(amzn), 63) if amzn and len(amzn) > 64 else None
        rt = pct_n(closes(tsla), 63) if tsla and len(tsla) > 64 else None
        if ra is not None and rt is not None and out["xly_13s_pct"] is not None:
            wa, wt = w.get("AMZN", 0) / 100, w.get("TSLA", 0) / 100
            contrib = wa * ra + wt * rt
            resto = (out["xly_13s_pct"] - contrib) / (1 - wa - wt) if wa + wt < 1 else None
            C.update({"amzn_13s_pct": r2(ra), "tsla_13s_pct": r2(rt), "contribucion_pp": r2(contrib), "xly_sin_amzn_tsla_13s_pct": r2(resto)})
            if resto is not None and out["xlp_13s_pct"] is not None:
                C["ratio_sin_amzn_tsla_13s_pct"] = r2(((1 + resto / 100) / (1 + out["xlp_13s_pct"] / 100) - 1) * 100)
            xm = out["xly_13s_pct"]
            C["lectura"] = ("MOVIDO SOBRE TODO POR AMAZON/TESLA" if abs(xm) > 0.5 and contrib * xm > 0 and abs(contrib) >= U["consumo_driver"] * abs(xm) else
                            "MOVIMIENTO AMPLIO (no depende solo de Amazon/Tesla)")
            C["nota"] = "ESTIMACIÓN con los pesos actuales (los pesos cambian con el precio); orientativa."
        out["concentracion"] = C
    return out


# ----------------------------------------------------------------- utilidades
def closes(o):
    return [(x[0], x[4]) for x in o]


def perf(s, n):
    return r2(pct_n(s, n))


def rel(a, b, n):
    """Diferencia de rendimiento a n sesiones (pp) entre dos series de cierres alineadas por fecha."""
    da, db = dict(a), dict(b)
    ds = sorted(set(da) & set(db))
    if len(ds) <= n:
        return None
    return round(((da[ds[-1]] / da[ds[-1 - n]]) - (db[ds[-1]] / db[ds[-1 - n]])) * 100, 2)


def ratio_series(a, b):
    da, db = dict(a), dict(b)
    return [(d, da[d] / db[d]) for d in sorted(set(da) & set(db)) if db[d]]


def estado_precio(s):
    """Precio confirma: sobre/bajo media de 50 sesiones con 20 sesiones del mismo signo."""
    if not s or len(s) < 60:
        return "SIN DATO"
    m = sma(s, U["sma"])
    p20 = pct_n(s, 20)
    if s[-1][1] > m and p20 > 0:
        return "CONFIRMA FUERZA"
    if s[-1][1] < m and p20 < 0:
        return "CONFIRMA DEBILIDAD"
    return "NO CONFIRMA"


def escalar_ohlc(etf, idx):
    """Lleva el OHLC de un ETF a nivel de índice con el factor cierre índice / cierre ETF de cada día (estimación)."""
    di = dict(idx)
    out = []
    for d, o, h, l, c, v in etf:
        if d in di and c:
            f = di[d] / c
            out.append((d, o * f, h * f, l * f, di[d], v))
    return out


def niveles(o):
    """Máximos/mínimos del día, semana y mes anteriores, 20 y 52 semanas, gaps abiertos y estructura semanal."""
    last = o[-1]
    d0 = last[0]
    wk = d0 - dt.timedelta(days=d0.weekday())
    prev_w = [x for x in o if wk - dt.timedelta(days=7) <= x[0] < wk]
    pm_end = d0.replace(day=1) - dt.timedelta(days=1)
    prev_m = [x for x in o if x[0].year == pm_end.year and x[0].month == pm_end.month]
    n = {"fecha": d0.isoformat(), "cierre": round(last[4], 2), "PDH": last[2], "PDL": last[3],
         "PWH": max((x[2] for x in prev_w), default=None), "PWL": min((x[3] for x in prev_w), default=None),
         "PMH": max((x[2] for x in prev_m), default=None), "PML": min((x[3] for x in prev_m), default=None),
         "max_20s": max(x[2] for x in o[-100:]), "min_20s": min(x[3] for x in o[-100:]),
         "max_52s": max(x[2] for x in o[-252:]), "min_52s": min(x[3] for x in o[-252:])}
    tr = [max(x[2], p[4]) - min(x[3], p[4]) for p, x in zip(o[-15:-1], o[-14:])]
    n["atr14"] = round(statistics.mean(tr), 2)
    gaps = []
    for i in range(max(1, len(o) - 60), len(o)):
        p, x = o[i - 1], o[i]
        if x[1] > p[2]:          # gap alcista: abre por encima del máximo anterior
            futuro_min = min((y[3] for y in o[i:]), default=x[3])
            if futuro_min > p[2]:
                gaps.append({"fecha": x[0].isoformat(), "tipo": "alcista", "desde": round(p[2], 2), "hasta": round(x[1], 2)})
        elif x[1] < p[3]:        # gap bajista
            futuro_max = max((y[2] for y in o[i:]), default=x[2])
            if futuro_max < p[3]:
                gaps.append({"fecha": x[0].isoformat(), "tipo": "bajista", "desde": round(x[1], 2), "hasta": round(p[3], 2)})
    n["gaps_abiertos"] = gaps[-4:]
    semanas = {}
    for x in o:
        k = x[0] - dt.timedelta(days=x[0].weekday())
        s_ = semanas.setdefault(k, [x[2], x[3]])
        s_[0], s_[1] = max(s_[0], x[2]), min(s_[1], x[3])
    ks = sorted(k for k in semanas if k < wk)[-6:]
    hh = sum(semanas[ks[i]][0] > semanas[ks[i - 1]][0] for i in range(1, len(ks)))
    hl = sum(semanas[ks[i]][1] > semanas[ks[i - 1]][1] for i in range(1, len(ks)))
    m_ = len(ks) - 1
    n["estructura_semanal"] = (("ALCISTA (máximos y mínimos crecientes)" if hh >= m_ - 1 and hl >= m_ - 1 else
                                "BAJISTA (máximos y mínimos decrecientes)" if hh <= 1 and hl <= 1 else
                                "MÁXIMOS DECRECIENTES" if hh <= 1 else "MÍNIMOS CRECIENTES" if hl >= m_ - 1 else "LATERAL")
                               + f" · {hh}/{m_} máximos y {hl}/{m_} mínimos crecientes")
    return n


def pools(niv, ref):
    nombres = {"PDH": "máx. día anterior", "PDL": "mín. día anterior", "PWH": "máx. semana anterior", "PWL": "mín. semana anterior",
               "PMH": "máx. mes anterior", "PML": "mín. mes anterior", "max_20s": "máx. 20 semanas", "min_20s": "mín. 20 semanas",
               "max_52s": "máx. 52 semanas", "min_52s": "mín. 52 semanas"}
    L = [(nombres[k], niv[k]) for k in nombres if niv.get(k)]
    L += [(f"gap {g['tipo']} {g['fecha']}", (g["desde"] + g["hasta"]) / 2) for g in niv.get("gaps_abiertos", [])]
    atr = niv.get("atr14") or 1
    f = lambda k, v: {"nombre": k, "nivel": round(v, 2), "dist_pct": round((v / ref - 1) * 100, 2), "dist_atr": round((v - ref) / atr, 1)}  # noqa: E731
    return {"referencia": round(ref, 2), "atr14": atr, "encima": [f(k, v) for k, v in sorted(((k, v) for k, v in L if v > ref), key=lambda x: x[1])][:5],
            "debajo": [f(k, v) for k, v in sorted(((k, v) for k, v in L if v <= ref), key=lambda x: -x[1])][:5]}


# ----------------------------------------------------------------- medición
def medir():
    M, err = {"generado_utc": dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
              "fuente_chuleta": "Chuleta completa — Cómo leer los índices (S&P 500 · Nasdaq 100 · US30 · Russell 2000)"}, {}

    def grab(name, fn, *a, **k):
        v, e = safe(fn, *a, **k)
        if e:
            err[name] = e
        return v

    # índices (Cboe / FRED) y ETF (Nasdaq Data)
    spx, djx, rut = grab("cboe_spx", cboe, "SPX"), grab("cboe_djx", cboe, "DJX"), grab("cboe_rut", cboe, "RUT")
    ndx_f = grab("fred_ndx", fred, "NASDAQ100", "2015-01-01")
    ndx_o = grab("nasdaq_ndx", nq_hist, "NDX", "index", 2)
    sox_o = grab("nasdaq_sox", nq_hist, "SOX", "index", 2)
    E = {}
    for s in ETFS:
        E[s] = grab(f"nasdaq_{s}", nq_hist, s, "etf", 2)
        time.sleep(0.4)
    vix = {s: grab(f"cboe_{s}", cboe, s) for s in ("VIX", "VIX9D", "VIX3M", "VVIX", "SKEW", "VXN", "RVX")}
    nom, real = grab("tesoro_nominal", treasury, "nominal"), grab("tesoro_real", treasury, "real")
    fx = grab("bce_fx", ecb_fx, 420)
    nfci = grab("nfci", fred, "NFCI", "2024-01-01")
    tga, rrp = grab("tga", dts_tga, 130), grab("rrp", nyfed_rrp, 130)
    res, m2 = grab("reservas", fred, "WRESBAL", "2024-06-01"), grab("m2", fred, "M2SL", "2023-01-01")
    effr = grab("effr", fred, "EFFR", "2025-01-01")
    hy, ig = grab("hy", fred, "BAMLH0A0HYM2", "2025-01-01"), grab("ig", fred, "BAMLC0A0CM", "2025-01-01")
    macro = {k: grab(k, fred, sid, "2022-01-01") for k, sid in (("payems", "PAYEMS"), ("unrate", "UNRATE"), ("ahe", "CES0500000003"),
                                                              ("icsa", "ICSA"), ("cpi", "CPIAUCSL"), ("cpi_core", "CPILFESL"),
                                                              ("pce_core", "PCEPILFE"), ("retail", "RSAFS"), ("philly", "GACDFSA066MSFRBPHI"),
                                                              ("empire", "GACDISA066MSFRBNY"), ("dallas", "BACTSAMFRBDAL"))}
    amp = grab("amplitud", amplitud_mercado)
    rrsfs = grab("rrsfs", fred, "RRSFS", "2023-01-01")
    pes = grab("ssga_xly", ssga_pesos, "XLY")
    amzn = grab("nasdaq_AMZN", nq_hist, "AMZN", "stocks", 1)
    tsla = grab("nasdaq_TSLA", nq_hist, "TSLA", "stocks", 1)
    cot = grab("cftc_indices", cftc_indices)
    earn = grab("factset", factset_earnings)
    live = {}
    for s in ("SPY", "QQQ", "DIA", "IWM"):
        live[s] = grab(f"info_{s}", nq_info, s, "etf")
    live["NDX"] = grab("info_NDX", nq_info, "NDX", "index")

    # ---------------- precios de los 4 índices
    IDX = {}
    series_idx = {"S&P 500": (spx, "SPY", "Cboe SPX (cierre oficial)"), "Nasdaq 100": (ndx_f, "QQQ", "FRED NASDAQ100 (Nasdaq)"),
                  "Dow Jones (US30)": ([(d, v * 100) for d, v in djx] if djx else None, "DIA", "Cboe DJX × 100 (cierre)"),
                  "Russell 2000": (rut, "IWM", "Cboe RUT (cierre)")}
    for nm, (s, etf, src) in series_idx.items():
        if not s:
            continue
        s = s[-600:]
        o_etf = E.get(etf) or []
        o = ndx_o if nm == "Nasdaq 100" and ndx_o else escalar_ohlc(o_etf, s)
        d = {"cierre": round(s[-1][1], 2), "fecha": s[-1][0].isoformat(), "1d_pct": perf(s, 1), "5d_pct": perf(s, 5), "20d_pct": perf(s, 20),
             "60d_pct": perf(s, 60), "ytd_pct": r2((s[-1][1] / next(v for dd, v in s if dd.year == s[-1][0].year) - 1) * 100),
             "sma50": r2(sma(s, 50)), "sma200": r2(sma(s, 200)), "vs_max_52s_pct": r2((s[-1][1] / max(v for _, v in s[-252:]) - 1) * 100),
             "precio": estado_precio(s), "fuente": src, "etf": etf}
        if o_etf and len(o_etf) > 21:
            v20 = statistics.mean(x[5] for x in o_etf[-21:-1])
            d["volumen_etf_rel"] = r2(o_etf[-1][5] / v20) if v20 else None
        if o and len(o) > 60:
            d["niveles"] = niveles(o)
            d["niveles"]["fuente"] = ("Nasdaq NDX (OHLC oficial)" if nm == "Nasdaq 100" and ndx_o else
                                      f"OHLC de {etf} escalado al índice con el factor cierre índice/cierre ETF (máx./mín. estimados)")
        IDX[nm] = d
    M["indices"] = IDX
    M["_spx"], M["_ndx"] = (spx or [])[-600:], (ndx_f or [])[-600:]
    M["tiempo_real"] = live

    # ---------------- tipos, dólar, condiciones
    if nom:
        for k, lab in (("2 Yr", "2Y"), ("10 Yr", "10Y"), ("30 Yr", "30Y")):
            s = serie(nom, k)
            M[f"t{lab}"] = {"valor": s[-1][1], "fecha": s[-1][0].isoformat(), "1d_pb": r2(delta_n(s, 1) * 100, 0), "5d_pb": r2(delta_n(s, 5) * 100, 0),
                            "20d_pb": r2(delta_n(s, 20) * 100, 0), "vel_z": r2(z_vel(s, 5)), "fuente": "U.S. Treasury, Daily Par Yield Curve"}
        M["_t10"] = serie(nom, "10 Yr")
    if real:
        s = serie(real, "10 YR")
        M["real10Y"] = {"valor": s[-1][1], "fecha": s[-1][0].isoformat(), "1d_pb": r2(delta_n(s, 1) * 100, 0), "5d_pb": r2(delta_n(s, 5) * 100, 0),
                        "20d_pb": r2(delta_n(s, 20) * 100, 0), "vel_z": r2(z_vel(s, 5)), "fuente": "U.S. Treasury, Daily Par Real Yield Curve (TIPS)"}
        M["_real10"] = s
    if nom and real:
        common = [d for d in nom if "10 Yr" in nom[d] and d in real and "10 YR" in real[d]]
        s = [(d, nom[d]["10 Yr"] - real[d]["10 YR"]) for d in common]
        M["be10Y"] = {"valor": r2(s[-1][1]), "5d_pb": r2(delta_n(s, 5) * 100, 0), "20d_pb": r2(delta_n(s, 20) * 100, 0),
                      "fuente": "Nominal − real, U.S. Treasury"}
    if fx:
        dx = dxy_replica(fx)
        M["dxy"] = {"valor": r2(dx[-1][1]), "fecha": dx[-1][0].isoformat(), "1d_pct": perf(dx, 1), "5d_pct": perf(dx, 5), "20d_pct": perf(dx, 20),
                    "vel_z": r2(z_vel(dx, 5, True)), "fuente": "Réplica ICE sobre tipos de referencia del BCE (14:15 CET)"}
        M["_dxy"] = dx
    if nfci:
        M["nfci"] = {"valor": nfci[-1][1], "fecha": nfci[-1][0].isoformat(), "1s": r2(delta_n(nfci, 1), 3), "4s": r2(delta_n(nfci, 4), 3),
                     "fuente": "Chicago Fed NFCI (FRED), semanal"}
    V = {}
    for k, s in vix.items():
        if s:
            V[k] = {"valor": s[-1][1], "fecha": s[-1][0].isoformat(), "1d_pct": perf(s, 1), "5d_pct": perf(s, 5),
                    "percentil_1a": round(sum(v <= s[-1][1] for _, v in s[-252:]) / len(s[-252:]) * 100)}
    if V.get("VIX") and V.get("VIX3M"):
        V["estructura"] = {"vix_vix3m": r2(V["VIX"]["valor"] / V["VIX3M"]["valor"], 3),
                           "vix9d_vix": r2(V["VIX9D"]["valor"] / V["VIX"]["valor"], 3) if V.get("VIX9D") else None}
    V["fuente"] = "Cboe (VIX, VIX9D, VIX3M, VVIX, SKEW, VXN, RVX)"
    M["volatilidad"] = V
    # liquidez
    if tga:
        c, c3 = change([(d, v["cierre"] / 1000) for d, v in tga], 28), change([(d, v["cierre"] / 1000) for d, v in tga], 91)
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
        M["m2"] = {"yoy_pct": r2(yoy[-1][1]), "yoy_prev_pct": r2(yoy[-2][1]), "mes": m2[-1][0].strftime("%Y-%m"), "fuente": "Fed H.6, M2SL (FRED)"}
    if nom and effr:
        rows = []
        for d, rec in nom.items():
            e = at_or_before(effr, d)
            if e and "1 Yr" in rec and (d - e[0]).days <= 5:
                rows.append((d, (rec["1 Yr"] - e[1]) * 100))
        if len(rows) > 21:
            M["expectativas_letras"] = {"1a_menos_effr_pb": r2(rows[-1][1], 0), "5d_pb": r2(delta_n(rows, 5), 0), "20d_pb": r2(delta_n(rows, 20), 0),
                                        "fuente": "U.S. Treasury (letra 1A) − EFFR", "nota": "PROXY de expectativas, no es FedWatch."}
    # crédito
    for nm, s in (("hy", hy), ("ig", ig)):
        if s:
            M[f"spread_{nm}"] = {"valor_pb": round(s[-1][1] * 100), "fecha": s[-1][0].isoformat(), "4s_pb": round(((change(s, 28) or {}).get("delta") or 0) * 100),
                                 "fuente": "ICE BofA vía FRED (" + ("high yield" if nm == "hy" else "grado de inversión") + ")"}
    # crecimiento, empleo, inflación (datos oficiales, período del dato ≠ fecha de publicación)
    G = {}
    p = macro.get("payems")
    if p:
        G["nfp"] = {"mes": p[-1][0].strftime("%Y-%m"), "cambio_miles": round(p[-1][1] - p[-2][1]), "previo_miles": round(p[-2][1] - p[-3][1]),
                    "media_3m": round((p[-1][1] - p[-4][1]) / 3), "fuente": "BLS vía FRED (PAYEMS)"}
    if macro.get("unrate"):
        u = macro["unrate"]
        G["paro"] = {"mes": u[-1][0].strftime("%Y-%m"), "valor": u[-1][1], "previo": u[-2][1], "fuente": "BLS vía FRED (UNRATE)"}
    if macro.get("ahe"):
        a = macro["ahe"]
        G["salarios"] = {"mes": a[-1][0].strftime("%Y-%m"), "yoy_pct": r2((a[-1][1] / a[-13][1] - 1) * 100), "mm_pct": r2((a[-1][1] / a[-2][1] - 1) * 100),
                         "fuente": "BLS vía FRED (ganancia media por hora)"}
    if macro.get("icsa"):
        c = macro["icsa"]
        G["peticiones_paro"] = {"semana": c[-1][0].isoformat(), "valor": int(c[-1][1]), "media_4s": round(statistics.mean(v for _, v in c[-4:])),
                                "media_4s_prev": round(statistics.mean(v for _, v in c[-8:-4])), "fuente": "DOL vía FRED (ICSA)"}
    for k, nm in (("cpi", "IPC general"), ("cpi_core", "IPC subyacente"), ("pce_core", "PCE subyacente")):
        s = macro.get(k)
        if s:
            G[k] = {"nombre": nm, "mes": s[-1][0].strftime("%Y-%m"), "yoy_pct": r2((s[-1][1] / s[-13][1] - 1) * 100), "mm_pct": r2((s[-1][1] / s[-2][1] - 1) * 100),
                    "mm_prev_pct": r2((s[-2][1] / s[-3][1] - 1) * 100), "tendencia_3m_anualizada": r2(((s[-1][1] / s[-4][1]) ** 4 - 1) * 100),
                    "fuente": "BLS/BEA vía FRED"}
    if macro.get("retail"):
        s = macro["retail"]
        G["ventas_minoristas"] = {"mes": s[-1][0].strftime("%Y-%m"), "mm_pct": r2((s[-1][1] / s[-2][1] - 1) * 100), "fuente": "Census vía FRED (RSAFS)"}
    reg = [(k, macro.get(k)) for k in ("philly", "empire", "dallas") if macro.get(k)]
    if reg:
        G["encuestas_fed"] = {"mes": max(s[-1][0] for _, s in reg).strftime("%Y-%m"),
                              "media_actual": r2(statistics.mean(s[-1][1] for _, s in reg), 1),
                              "media_3m_antes": r2(statistics.mean(s[-4][1] for _, s in reg), 1),
                              "detalle": {k: s[-1][1] for k, s in reg},
                              "fuente": "Encuestas manufactureras Fed Filadelfia, Nueva York y Dallas (FRED). PROXY del ISM: el ISM oficial se lee en ismworld.org"}
    M["macro"] = G
    # amplitud, volumen, fuerza relativa, sectores
    A = {}
    if amp:
        A["sesion"] = amp
    if E.get("RSP") and E.get("SPY"):
        A["rsp_vs_spy_20d_pp"] = rel(closes(E["RSP"]), closes(E["SPY"]), 20)
        A["rsp_vs_spy_60d_pp"] = rel(closes(E["RSP"]), closes(E["SPY"]), 60)
    if E.get("QQEW") and E.get("QQQ"):
        A["qqew_vs_qqq_20d_pp"] = rel(closes(E["QQEW"]), closes(E["QQQ"]), 20)
    A["fuente"] = "Nasdaq Data: screener de todas las acciones USA (sesión anterior) y ETF de igual peso (RSP, QQEW) frente a los ponderados por capitalización"
    M["amplitud"] = A
    RS = {}
    for a, b, k in (("QQQ", "SPY", "nasdaq_vs_sp"), ("IWM", "QQQ", "russell_vs_nasdaq"), ("DIA", "QQQ", "us30_vs_nasdaq"), ("IWM", "SPY", "russell_vs_sp"),
                    ("SOXX", "QQQ", "semis_vs_nasdaq"), ("XLI", "SPY", "industriales_vs_sp"), ("XLF", "SPY", "financieras_vs_sp")):
        if E.get(a) and E.get(b):
            RS[k] = {"5d_pp": rel(closes(E[a]), closes(E[b]), 5), "20d_pp": rel(closes(E[a]), closes(E[b]), 20), "60d_pp": rel(closes(E[a]), closes(E[b]), 60)}
    RS["fuente"] = "ETF (Nasdaq Data): diferencia de rendimiento en puntos porcentuales"
    M["fuerza_relativa"] = RS
    if E.get("XLY") and E.get("XLP"):
        cx, ce = safe(consumo_xly_xlp, E["XLY"], E["XLP"], rrsfs, pes, amzn, tsla)
        if ce:
            err["consumo_xly_xlp"] = ce
        M["consumo"] = cx
    M["cot"] = cot
    M["beneficios"] = earn
    # correlaciones de 60 sesiones (¿se cumple la relación?)
    RL = {}
    if M.get("_ndx") and M.get("_real10"):
        RL["nasdaq_real10"] = _corr_estado(M["_ndx"], M["_real10"], pct_a=True)
    if M.get("_spx") and M.get("_dxy"):
        RL["sp_dxy"] = _corr_estado(M["_spx"], M["_dxy"], pct_a=True)
    if M.get("_spx") and M.get("_t10"):
        RL["sp_10y"] = _corr_estado(M["_spx"], M["_t10"], pct_a=True)
    M["relaciones"] = RL
    M["errores"] = err
    return M


def _corr_estado(a, b, pct_a=True, n=60):
    da, db = dict(a), dict(b)
    ds = sorted(set(da) & set(db))
    out = {}
    for w in (20, n, 250):
        dd = ds[-(w + 1):]
        x = [(da[dd[i]] / da[dd[i - 1]] - 1) if pct_a else da[dd[i]] - da[dd[i - 1]] for i in range(1, len(dd))]
        y = [db[dd[i]] - db[dd[i - 1]] for i in range(1, len(dd))]
        out[f"corr_{w}"] = r2(corr(x, y))
    c = out[f"corr_{n}"]
    out["estado"] = "SIN DATO" if c is None else "ROTA" if c > 0.10 else "DÉBIL" if c > -0.15 else "SE CUMPLE"
    return out


# ----------------------------------------------------------------- evaluación (literal a la chuleta)
def consumo_resumen(cx, EV=None):
    """Texto fijo (generado con datos, no con la narrativa) para la tesis, el régimen y la guía llana."""
    if not cx:
        return None

    def n(x, d=2, sg=True):
        return (f"{x:+,.{d}f}" if sg else f"{x:,.{d}f}").replace(",", "X").replace(".", ",").replace("X", ".")
    cr = cx.get("consumo_real") or {}
    C = cx.get("concentracion") or {}
    ecx = (EV or {}).get("consumo_xly_xlp") or {}
    g = ecx.get("grupos") or {}
    if cr:
        key = ("Ratio sobre su media Y consumo real firme (confirmado)" if cx["sobre_sma200"] and cr["estado"] == "FIRME" else
               "Ratio sobre su media pero consumo real enfriándose" if cx["sobre_sma200"] else
               "Ratio bajo su media Y consumo real enfriándose (confirmado)" if cr["estado"] == "SE ENFRÍA" else
               "Ratio bajo su media pero consumo real firme (no confirmado)")
    else:
        key = "Ratio sobre su media de 200 sesiones" if cx["sobre_sma200"] else "Ratio bajo su media de 200 sesiones"
    h, b = g.get(key), g.get("Todas (referencia)")
    hist = (f"Histórico {ecx.get('periodo', '')} en situación comparable ({key.lower()}; {h['n']} semanas): S&P 500 a 13 semanas mediana "
            f"{n(h['med13'])} % y positivo el {h['pos13']} % (referencia {n(b['med13'])} % y {b['pos13']} %); caída típica en 13 semanas {n(h['dd13'])} % "
            f"(referencia {n(b['dd13'])} %).") if h and b else "Sin validación histórica cargada."
    pp = ecx.get("por_periodo") or {}
    cf = [(k, (v or {}).get("bajo_confirmado")) for k, v in pp.items()]
    aviso = ("Aviso: el ratio bajo su media CON el consumo real enfriándose solo anticipó caídas en 2000-2009 (recesiones de 2001 y 2008: " +
             ", ".join(f"{k} mediana 13 sem. {n(v['med13'])} %" for k, v in cf if v) + "). Es señal de riesgo de ciclo, no de momento de entrada."
             ) if any(v for _, v in cf) else ""
    conc = ""
    if C.get("lectura"):
        conc = (f"Amazon + Tesla pesan el {n(C['amzn_tsla_peso'], 1, False)} % de XLY ({C['fecha_pesos']}); en 13 semanas Amazon {n(C['amzn_13s_pct'], 1)} %, Tesla {n(C['tsla_13s_pct'], 1)} %. "
                f"Sin ellas, el ratio habría variado {n(C.get('ratio_sin_amzn_tsla_13s_pct') or 0, 1)} % (estimación): " + ("lo mueven sobre todo Amazon y Tesla." if C['lectura'].startswith('MOVIDO') else "el movimiento es amplio, no depende solo de Amazon y Tesla."))
    valor = (f"XLY/XLP {n(cx['ratio'], 4, False)} ({cx['fecha']}) · {n(cx['dist_sma200_pct'], 1)} % frente a su media de 200 sesiones · 13 semanas {n(cx['13s_pct'], 1)} %" +
             (f" · consumo real {cr['estado'].lower()} ({cr['mes']}, {n(cr['3m_vs_3m_pct'])} % media 3 meses vs 3 anteriores)" if cr else ""))
    lectura = f"{cx['mercado']} · {cx['confirmacion']}"
    if cx.get("cruce_reciente"):
        lectura += f" · cruzó su media de 200 {cx['cruce_reciente']['sentido'].lower()} el {cx['cruce_reciente']['fecha']}"
    return {"valor": valor, "lectura": lectura, "historico": hist, "aviso": aviso, "concentracion": conc,
            "tesis": f"{valor}. {lectura}. {conc} {hist} {aviso}".replace("  ", " ").strip(),
            "estado_mercado": cx["mercado"], "confirmacion": cx["confirmacion"]}


def cargar_json(nombre):
    try:
        return json.load(open(os.path.join(HERE, nombre), encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def evaluar(M, fedwatch=None, ism=None):
    """fedwatch = {"cambio": "RELAJACION|ENDURECIMIENTO|SIN CAMBIO", ...} (solo CME).
    ism = {"manufacturero": x, "servicios": y, "previo_manufacturero": ..., "previo_servicios": ..., "fuente": "..."} (solo ismworld.org)."""
    if fedwatch is None:  # FedWatch NEXORA (método CME) automático si no se pasa
        try:
            import fedwatch as _fw
            fedwatch = _fw.para_monitor(_fw.cargar())
        except Exception:  # noqa: BLE001
            fedwatch = None
    P = []

    def add(id_, dato, que, d, valor, est, lect, fuente, puntua=False):
        P.append({"id": id_, "dato": dato, "que_mirar": que, "dir": d, "valor": valor, "estado": est, "lectura": lect, "fuente": fuente, "puntua": puntua})

    t2, t10, rl, dx, nf = M.get("t2Y"), M.get("t10Y"), M.get("real10Y"), M.get("dxy"), M.get("nfci")
    V = M.get("volatilidad") or {}
    vx = V.get("VIX")
    if t2:
        d = dirv(t2["5d_pb"], U["t2y_pb_1s"])
        add("t2y", "US 2Y", "Yield + dirección + velocidad", d, f"{t2['valor']:.2f}% · 5d {t2['5d_pb']:+.0f} pb · 1d {t2['1d_pb']:+.0f} pb",
            FAV if d == "↓" else CON if d == "↑" else NEU, "Baja: suele aliviar presión de tipos" if d == "↓" else "Sube: suele endurecer condiciones" if d == "↑" else "Estable",
            t2["fuente"], True)
    if t10:
        d = dirv(t10["5d_pb"], U["t10y_pb_1s"])
        rap = d == "↑" and (t10["5d_pb"] > U["t10y_rapido_pb_1s"] or (t10["vel_z"] or 0) >= U["velocidad_z"])
        add("t10y", "US 10Y", "Yield + velocidad", d, f"{t10['valor']:.2f}% · 5d {t10['5d_pb']:+.0f} pb",
            FAV if d in ("↓", "→") else CON if rap else NEU,
            "Baja: suele aliviar valoraciones" if d == "↓" else ("Sube RÁPIDO: puede presionar índices" if rap else "Sube sin velocidad: presión moderada") if d == "↑" else "Estable (cuenta a favor en risk-on)",
            t10["fuente"], True)
    if rl:
        d = dirv(rl["5d_pb"], U["real_pb_1s"])
        add("real10", "10Y REAL / TIPS", "Real yield + dirección (clave para Nasdaq)", d, f"{rl['valor']:.2f}% · 5d {rl['5d_pb']:+.0f} pb · 20d {rl['20d_pb']:+.0f} pb",
            FAV if d == "↓" else CON if d == "↑" else NEU, "Baja: favorable para growth/Nasdaq" if d == "↓" else "Sube: presiona especialmente growth/Nasdaq" if d == "↑" else "Estable",
            rl["fuente"], True)
    if dx:
        d = dirv(dx["5d_pct"], U["dxy_pct_1s"])
        add("dxy", "DXY", "Nivel + dirección", d, f"{dx['valor']:.2f} · 5d {dx['5d_pct']:+.2f}%", FAV if d == "↓" else CON if d == "↑" else NEU,
            "Baja: suele aliviar activos de riesgo" if d == "↓" else "Sube: puede presionar condiciones financieras" if d == "↑" else "Estable", dx["fuente"], True)
    if nf:
        d = dirv(nf["4s"], U["nfci_4s"])
        add("nfci", "NFCI", "Nivel + tendencia", d, f"{nf['valor']:+.3f} · 4s {nf['4s']:+.3f}", FAV if d == "↓" else CON if d == "↑" else NEU,
            "Baja: condiciones más fáciles" if d == "↓" else "Sube: condiciones más tensas" if d == "↑" else "Estable", nf["fuente"], True)
    if vx:
        d = dirv(vx["5d_pct"], U["vix_pct_1s"])
        alto = vx["valor"] > U["vix_alto"]
        add("vix", "VIX", "Nivel + aceleración", d, f"{vx['valor']:.2f} · 5d {vx['5d_pct']:+.1f}% · percentil 1 año {vx['percentil_1a']}%",
            CON if d == "↑" or alto else FAV, ("Sube: más aversión al riesgo" if d == "↑" else "Baja: menos estrés" if d == "↓" else "Estable") +
            (" · nivel alto (> 25)" if alto else "") + ". Riesgo, no señal automática (CH).", V["fuente"], True)
    if fedwatch and fedwatch.get("cambio"):
        c = fedwatch["cambio"].upper()
        est = FAV if c.startswith("RELAJ") else CON if c.startswith("ENDUR") else NEU
        add("fedwatch", "FedWatch", "Recortes/subidas descontados", "↓" if est == FAV else "↑" if est == CON else "→", fedwatch.get("valor", ""), est,
            (fedwatch.get("detalle") or "") + " · " + ("Más relajación" if est == FAV else "Más restricción" if est == CON else "Sin cambio"),
            fedwatch.get("fuente", "CME FedWatch"), True)
    else:
        add("fedwatch", "FedWatch", "Recortes/subidas descontados", "?", "—", SD, "FedWatch no disponible hoy (fallo de descarga). Nunca se estima.", "CME FedWatch", True)
    tg, rp, rs = M.get("tga"), M.get("rrp"), M.get("reservas")
    if tg:
        d = dirv(tg["4s_B"], U["tga_b_4s"])
        add("tga", "TGA", "Saldo + dirección", d, f"{tg['valor_B']:,.1f} B$ · 4s {tg['4s_B']:+,.1f} B$", FAV if d == "↓" else CON if d == "↑" else NEU,
            "Baja: puede liberar liquidez" if d == "↓" else "Sube: puede drenar liquidez" if d == "↑" else "Estable", tg["fuente"])
    if rp:
        d = dirv(rp["4s_B"], U["rrp_b_4s"])
        agot = rp["valor_B"] < U["rrp_agotado_b"]
        add("rrp", "RRP", "Saldo + dirección", d, f"{rp['valor_B']:,.1f} B$ · 4s {rp['4s_B']:+,.1f} B$", (NEU if agot else FAV) if d == "↓" else CON if d == "↑" and not agot else NEU,
            ("Baja: puede liberar efectivo aparcado" if d == "↓" else "Sube: más efectivo aparcado" if d == "↑" else "Estable") +
            (f". Saldo < {U['rrp_agotado_b']:.0f} B$: colchón agotado (neutral)" if agot else ""), rp["fuente"])
    if rs:
        up = rs["4s_pct"] > U["reservas_pct_4s"] and (rs["3m_pct"] or 0) > 0
        dn = rs["4s_pct"] < -U["reservas_pct_4s"] and (rs["3m_pct"] or 0) < 0
        add("reservas", "RESERVAS", "WRESBAL, tendencia 1M/3M", "↑" if up else "↓" if dn else "→", f"{rs['valor_T']:.3f} T$ · 1M {rs['4s_pct']:+.2f}% · 3M {rs['3m_pct']:+.2f}%",
            FAV if up else CON if dn else NEU, "Suben: más reservas" if up else "Bajan: puede indicar drenaje" if dn else "Planas", rs["fuente"])
    m2 = M.get("m2")
    if m2:
        up = m2["yoy_pct"] > 0 and m2["yoy_pct"] >= m2["yoy_prev_pct"]
        add("m2", "M2", "Crecimiento + aceleración", "↑" if up else "↓", f"{m2['yoy_pct']:+.2f}% a/a (previo {m2['yoy_prev_pct']:+.2f}%) · {m2['mes']}", CTX,
            ("Más expansión" if up else "Régimen menos expansivo") + ". Medio/largo plazo.", m2["fuente"])
    er = M.get("beneficios")
    if er and er.get("revision"):
        d = {"AL ALZA": "↑", "A LA BAJA": "↓"}.get(er["revision"], "→")
        add("earnings", "EARNINGS", "Revisiones de beneficios", d,
            f"BPA {er.get('trimestre', '')} {er.get('crecimiento_bpa_pct', 0):+.1f}% a/a (el {er.get('referencia_fecha', '')}: {er.get('crecimiento_referencia_pct', 0):+.1f}%) · PER 12m {er.get('per_12m', '—')}",
            FAV if d == "↑" else CON if d == "↓" else NEU, ("Mejora: puede sostener índices" if d == "↑" else "Deterioro: puede pesar" if d == "↓" else "Estables"),
            f"FactSet Earnings Insight {er['fecha_informe']}")
    G = M.get("macro") or {}
    if ism and ism.get("manufacturero") is not None:
        mn = ism["manufacturero"]
        add("pmi", "PMI / ISM", "Actividad manufacturera/servicios", "↑" if mn > (ism.get("previo_manufacturero") or mn) else "↓",
            f"ISM manufacturero {mn} (previo {ism.get('previo_manufacturero', '—')}) · servicios {ism.get('servicios', '—')}",
            FAV if mn >= 50 else CON, "Expansión (≥ 50)" if mn >= 50 else "Contracción (< 50): puede señalar desaceleración", ism.get("fuente", "ISM"))
    elif G.get("encuestas_fed"):
        e = G["encuestas_fed"]
        d = dirv(e["media_actual"] - e["media_3m_antes"], 3)
        add("pmi", "PMI / ISM (proxy Fed regionales)", "Actividad manufacturera", d, f"media Filadelfia/NY/Dallas {e['media_actual']:+.1f} ({e['mes']}) vs {e['media_3m_antes']:+.1f} hace 3 meses",
            FAV if e["media_actual"] > 0 and d != "↓" else CON if e["media_actual"] < 0 and d != "↑" else NEU,
            ("Expansión" if e["media_actual"] > 0 else "Contracción") + " y " + ({"↑": "mejorando", "↓": "empeorando"}.get(d, "estable")) + ". ISM oficial: SIN DATO automático.", e["fuente"])
    if G.get("nfp"):
        n = G["nfp"]
        s_ = G.get("salarios", {})
        add("nfp", "NFP / EMPLEO", "Empleo + salarios", "↑" if n["cambio_miles"] > n["previo_miles"] else "↓",
            f"NFP {n['cambio_miles']:+,} mil ({n['mes']}; previo {n['previo_miles']:+,}; media 3m {n['media_3m']:+,}) · paro {G.get('paro', {}).get('valor', '—')}% · salarios {s_.get('yoy_pct', 0):+.1f}% a/a",
            CTX, "Hay que interpretar el motivo (CH): fuerte puede retrasar recortes pero apoya crecimiento; débil puede traer recortes pero también recesión.", n["fuente"])
    if G.get("cpi_core") or G.get("pce_core"):
        c = G.get("pce_core") or G.get("cpi_core")
        d = "↑" if c["mm_pct"] > c["mm_prev_pct"] + 0.05 else "↓" if c["mm_pct"] < c["mm_prev_pct"] - 0.05 else "→"
        cpi = G.get("cpi_core", {})
        add("inflacion", "CPI / PCE", "Inflación + tendencia", d,
            f"IPC subyacente {cpi.get('mm_pct', 0):+.2f}% m/m · {cpi.get('yoy_pct', 0):.1f}% a/a ({cpi.get('mes', '')}) · PCE subyacente {G.get('pce_core', {}).get('yoy_pct', 0):.1f}% a/a ({G.get('pce_core', {}).get('mes', '')}) · {c['nombre']} 3m anualizado {c['tendencia_3m_anualizada']:.1f}%",
            FAV if d == "↓" else CON if d == "↑" else NEU, "Baja: puede permitir más relajación" if d == "↓" else "Sube: puede retrasar recortes" if d == "↑" else "Estable", c["fuente"])
    I = M.get("indices") or {}
    sp = I.get("S&P 500") or {}
    if sp.get("volumen_etf_rel"):
        vr = sp["volumen_etf_rel"]
        add("volumen", "VOLUMEN", "Volumen relativo al promedio", "↑" if vr > 1 else "↓", f"SPY {vr:.2f}x media 20 sesiones · QQQ {(I.get('Nasdaq 100') or {}).get('volumen_etf_rel', 0):.2f}x · IWM {(I.get('Russell 2000') or {}).get('volumen_etf_rel', 0):.2f}x",
            CTX, ("Participación alta" if vr >= U["volumen_rel"] else "Participación normal/baja") + ": confirma (o no) el movimiento del día.", "Nasdaq Data (volumen de ETF; proxy del volumen del índice)")
    A = M.get("amplitud") or {}
    ses = (A.get("sesion") or {}).get("grandes_10B")
    if ses or A.get("rsp_vs_spy_20d_pp") is not None:
        pct = (ses or {}).get("pct_suben")
        rr = A.get("rsp_vs_spy_20d_pp")
        est = (FAV if (pct or 50) >= U["ad_pct_alto"] or (rr or 0) > U["amplitud_rsp_pp_20d"] else
               CON if (pct or 50) <= U["ad_pct_bajo"] or (rr or 0) < -U["amplitud_rsp_pp_20d"] else NEU)
        add("amplitud", "ADV/DECLINE (amplitud)", "Amplitud del mercado", "↑" if est == FAV else "↓" if est == CON else "→",
            (f"grandes compañías: {ses['suben']} suben / {ses['bajan']} bajan ({pct}% al alza; volumen alcista {ses['volumen_alcista_pct']}%) · " if ses else "") +
            (f"igual peso vs S&P {rr:+.2f} pp en 20 sesiones" if rr is not None else ""),
            est, "Fortaleza interna" if est == FAV else "Debilidad interna: pocas compañías sostienen el índice" if est == CON else "Amplitud neutra", A["fuente"])
    ts = V.get("estructura")
    if ts:
        bw = ts["vix_vix3m"] > U["vix_ts_backw"]
        add("vix_ts", "VIX TERM STRUCTURE", "Contango/backwardation", "↑" if bw else "↓", f"VIX/VIX3M {ts['vix_vix3m']:.3f} · VIX9D/VIX {ts.get('vix9d_vix') or 0:.3f}",
            CON if bw else FAV, "BACKWARDATION: posible estrés/shock" if bw else "Contango: estructura normal", V["fuente"])
    by = {p["id"]: p for p in P}

    # ---------------- §4 entorno macro
    cond = []

    def c_(id_, nombre, on, off):
        cond.append({"id": id_, "condicion": nombre, "estado": "RISK-ON" if on else "RISK-OFF" if off else ("SIN DATO" if by.get(id_, {}).get("estado") == SD else "NEUTRAL")})
    if "t2y" in by:
        c_("t2y", "2Y ↓", by["t2y"]["dir"] == "↓", by["t2y"]["dir"] == "↑")
    if "t10y" in by:
        c_("t10y", "10Y estable/↓ (risk-off: ↑ rápido)", by["t10y"]["dir"] in ("↓", "→"), by["t10y"]["estado"] == CON)
    if "real10" in by:
        c_("real10", "10Y real ↓", by["real10"]["dir"] == "↓", by["real10"]["dir"] == "↑")
    if "dxy" in by:
        c_("dxy", "DXY ↓", by["dxy"]["dir"] == "↓", by["dxy"]["dir"] == "↑")
    if "nfci" in by:
        c_("nfci", "NFCI ↓", by["nfci"]["dir"] == "↓", by["nfci"]["dir"] == "↑")
    if "vix" in by:
        c_("vix", "VIX ↓/estable", by["vix"]["dir"] in ("↓", "→") and by["vix"]["estado"] != CON, by["vix"]["dir"] == "↑")
    c_("fedwatch", "FedWatch más relajado", by["fedwatch"]["estado"] == FAV, by["fedwatch"]["estado"] == CON)
    on = sum(c["estado"] == "RISK-ON" for c in cond)
    off = sum(c["estado"] == "RISK-OFF" for c in cond)
    sd = sum(c["estado"] == "SIN DATO" for c in cond)
    disp = len(cond) - sd
    if disp and on == disp:
        lectura = "RISK-ON"
    elif disp and off == disp:
        lectura = "RISK-OFF"
    elif on >= disp - 2 and off <= 1:
        lectura = "PREDOMINIO RISK-ON"
    elif off >= disp - 2 and on <= 1:
        lectura = "PREDOMINIO RISK-OFF"
    else:
        lectura = "MIXTO"
    lf = sum(by.get(i, {}).get("estado") == FAV for i in ("tga", "rrp", "reservas"))
    lc = sum(by.get(i, {}).get("estado") == CON for i in ("tga", "rrp", "reservas"))
    drena = by.get("reservas", {}).get("dir") == "↓" and by.get("tga", {}).get("dir") == "↑"
    liquidez = "DRENA" if drena else "ACOMPAÑA" if lf >= 2 and lc == 0 else "NO ACOMPAÑA" if lc >= 2 else "NEUTRAL"
    amp_est = by.get("amplitud", {}).get("estado")
    breadth = "CONFIRMA" if amp_est == FAV else "SE DETERIORA" if amp_est == CON else "NEUTRA"
    avisos = []
    if sd:
        avisos.append(f"Entorno evaluado sobre {disp} de {len(cond)} condiciones: FedWatch sin dato hoy (fallo de descarga).")
    # MIXTO de la chuleta: yields por crecimiento vs por inflación
    be = M.get("be10Y") or {}
    if by.get("t10y", {}).get("dir") == "↑":
        motivo = ("INFLACIÓN (sube el breakeven)" if (be.get("5d_pb") or 0) >= U["be_pb_1s"] else "TIPO REAL (sube la parte real, no la inflación esperada)")
        crec = by.get("earnings", {}).get("dir") == "↑" or by.get("pmi", {}).get("estado") == FAV
        avisos.append(f"Los yields suben por {motivo}. " + ("Los beneficios/actividad mejoran: puede ser subida de yields «por crecimiento» (CH §4 MIXTO), menos dañina que por inflación persistente."
                                                           if crec and motivo.startswith("TIPO") else "No hay mejora clara de beneficios/actividad que lo compense: más presión sobre valoraciones."))
    if ts and ts["vix_vix3m"] > U["vix_ts_backw"]:
        avisos.append("VIX en BACKWARDATION (VIX > VIX3M): el mercado paga más por protección inmediata que a 3 meses. CH: puede indicar estrés/shock.")
    RL = M.get("relaciones") or {}
    for k, nm in (("nasdaq_real10", "Nasdaq ↔ 10Y real"), ("sp_dxy", "S&P ↔ DXY")):
        if (RL.get(k) or {}).get("estado") == "ROTA":
            avisos.append(f"RELACIÓN ROTA {nm} (correlación 60 sesiones {RL[k]['corr_60']:+.2f}): la regla de la chuleta no se está cumpliendo; buscar el driver (beneficios, flujos, temática).")
    spp = sp.get("precio")
    if lectura in ("RISK-OFF", "PREDOMINIO RISK-OFF") and spp == "CONFIRMA FUERZA":
        avisos.append("DIVERGENCIA: la macro de la chuleta es restrictiva pero el S&P mantiene fuerza. Buscar el motor (beneficios, IA/mega caps, recompras) antes de asumir corrección.")
    if lectura in ("RISK-ON", "PREDOMINIO RISK-ON") and spp == "CONFIRMA DEBILIDAD":
        avisos.append("DIVERGENCIA: la macro acompaña pero el precio no confirma. CH §8: dejar que el precio confirme.")
    if breadth == "SE DETERIORA" and spp == "CONFIRMA FUERZA":
        avisos.append("Subida ESTRECHA: el índice sube con amplitud débil (pocas mega caps). CH: confirmar breadth.")
    sesgo60 = ("RISK-ON" if lectura in ("RISK-ON", "PREDOMINIO RISK-ON") and liquidez != "DRENA" and breadth != "SE DETERIORA" else
               "RISK-OFF" if lectura in ("RISK-OFF", "PREDOMINIO RISK-OFF") and breadth != "CONFIRMA" else "SIN CONFLUENCIA COMPLETA")

    # ---------------- §2 lectura por índice
    RS = M.get("fuerza_relativa") or {}
    hy = M.get("spread_hy") or {}
    base = 1 if lectura.endswith("RISK-ON") else -1 if lectura.endswith("RISK-OFF") else 0
    PI = []
    for nm, clave, extra in (
            ("S&P 500", "Tipos + beneficios + amplitud + mega caps", [("amplitud", by.get("amplitud", {}).get("estado")), ("beneficios", by.get("earnings", {}).get("estado"))]),
            ("Nasdaq 100", "Tipos reales + yields + mega-cap growth/tech", [("10Y real", by.get("real10", {}).get("estado")),
                                                                           ("semiconductores", FAV if (RS.get("semis_vs_nasdaq") or {}).get("20d_pp", 0) > U["rs_pp_20d"] else CON if (RS.get("semis_vs_nasdaq") or {}).get("20d_pp", 0) < -U["rs_pp_20d"] else NEU)]),
            ("Dow Jones (US30)", "Ciclo, industriales, financieros, empresas maduras", [("industriales", FAV if (RS.get("industriales_vs_sp") or {}).get("20d_pp", 0) > 1 else CON if (RS.get("industriales_vs_sp") or {}).get("20d_pp", 0) < -1 else NEU),
                                                                                       ("financieras", FAV if (RS.get("financieras_vs_sp") or {}).get("20d_pp", 0) > 1 else CON if (RS.get("financieras_vs_sp") or {}).get("20d_pp", 0) < -1 else NEU)]),
            ("Russell 2000", "Tipos + crédito + condiciones financieras + economía doméstica", [("NFCI", by.get("nfci", {}).get("estado")),
                                                                                              ("crédito high yield", FAV if hy.get("4s_pb", 0) < -U["hy_pb_4s"] else CON if hy.get("4s_pb", 0) > U["hy_pb_4s"] else NEU)])):
        d = I.get(nm) or {}
        pts = base + sum(1 if e == FAV else -1 if e == CON else 0 for _, e in extra)
        PI.append({"indice": nm, "que_lo_mueve": clave, "cierre": d.get("cierre"), "fecha": d.get("fecha"), "5d_pct": d.get("5d_pct"), "20d_pct": d.get("20d_pct"),
                   "ytd_pct": d.get("ytd_pct"), "vs_max_52s_pct": d.get("vs_max_52s_pct"), "precio": d.get("precio"),
                   "factores": [{"factor": f, "estado": e or SD} for f, e in extra],
                   "entorno": "FAVORABLE" if pts >= 2 else "DESFAVORABLE" if pts <= -2 else "MIXTO", "puntos": pts,
                   "estructura": (d.get("niveles") or {}).get("estructura_semanal")})

    # ---------------- §3 comparaciones
    Cmp = []

    def cm(par, busca, est, det, lect):
        Cmp.append({"par": par, "busca": busca, "estado": est, "detalle": det, "lectura": lect})
    spx5 = sp.get("5d_pct")
    nd = I.get("Nasdaq 100") or {}
    if t2:
        fw = by["fedwatch"]["estado"]
        cm("2Y ↔ FedWatch", "2Y ↓ + más recortes descontados", "CUMPLE" if by["t2y"]["dir"] == "↓" and fw == FAV else "PARCIAL" if by["t2y"]["dir"] == "↓" else "NO SE CUMPLE",
           f"2Y {t2['5d_pb']:+.0f} pb · FedWatch {fw}", "Relajación de expectativas de tipos")
    if rl and nd.get("5d_pct") is not None:
        a, b = by["real10"]["dir"], "↑" if nd["5d_pct"] > 0 else "↓"
        cm("10Y REAL ↔ Nasdaq", "Real yield ↓ + Nasdaq ↑", "CUMPLE" if a == "↓" and b == "↑" else "INVERSA EN CONTRA" if a == "↑" and b == "↓" else "NO SE CUMPLE" if a == b else "NEUTRAL",
           f"10Y real {rl['5d_pb']:+.0f} pb · Nasdaq {nd['5d_pct']:+.2f}% · correlación 60d {(RL.get('nasdaq_real10') or {}).get('corr_60')}", "Entorno favorable para growth")
    if dx and spx5 is not None:
        a, b = by["dxy"]["dir"], "↑" if spx5 > 0 else "↓"
        cm("DXY ↔ índices", "DXY ↓ + índices ↑", "CUMPLE" if a == "↓" and b == "↑" else "INVERSA EN CONTRA" if a == "↑" and b == "↓" else "NO SE CUMPLE" if a == b else "NEUTRAL",
           f"DXY {dx['5d_pct']:+.2f}% · S&P {spx5:+.2f}%", "Condiciones generalmente más suaves")
    if nf and spx5 is not None:
        a, b = by["nfci"]["dir"], "↑" if spx5 > 0 else "↓"
        cm("NFCI ↔ índices", "NFCI ↓ + índices ↑", "CUMPLE" if a == "↓" and b == "↑" else "NO SE CUMPLE" if a == "↑" and b == "↑" else "NEUTRAL",
           f"NFCI 4s {nf['4s']:+.3f} · S&P {spx5:+.2f}%", "Liquidez/financiación acompañan")
    if vx and spx5 is not None:
        a, b = by["vix"]["dir"], "↑" if spx5 > 0 else "↓"
        cm("VIX ↔ precio", "VIX ↓ + índices ↑", "CUMPLE" if a == "↓" and b == "↑" else "INVERSA EN CONTRA" if a == "↑" and b == "↓" else "PARCIAL" if b == "↑" else "NO SE CUMPLE",
           f"VIX {vx['5d_pct']:+.1f}% · S&P {spx5:+.2f}%", "Risk-on más limpio; confirmar breadth")
    if "amplitud" in by and spx5 is not None:
        ae = by["amplitud"]["estado"]
        cm("ADV/DECLINE ↔ S&P", "Índice ↑ + breadth ↑",
           "CUMPLE" if spx5 > 0 and ae == FAV else "NO SE CUMPLE (subida estrecha)" if spx5 > 0 and ae == CON else
           "CAÍDA AMPLIA" if spx5 < 0 and ae == CON else "DIVERGENCIA POSITIVA (el índice cae pero la amplitud aguanta)" if spx5 < 0 and ae == FAV else "NEUTRAL",
           by["amplitud"]["valor"], "Movimiento más amplio y sano internamente")
    r1 = RS.get("russell_vs_nasdaq") or {}
    if r1:
        cm("Russell ↔ Nasdaq", "Russell supera a Nasdaq", "CUMPLE" if (r1.get("20d_pp") or 0) > U["rs_pp_20d"] else "NO SE CUMPLE",
           f"IWM vs QQQ {r1.get('20d_pp', 0):+.2f} pp (20 ses.) · {r1.get('5d_pp', 0):+.2f} pp (5 ses.)", "Puede indicar rotación hacia ciclo/small caps")
    r2_ = RS.get("us30_vs_nasdaq") or {}
    if r2_:
        v = r2_.get("20d_pp") or 0
        cm("US30 ↔ Nasdaq", "Uno supera claramente al otro", "US30 LIDERA" if v > U["rs_pp_20d"] else "NASDAQ LIDERA" if v < -U["rs_pp_20d"] else "SIN LÍDER CLARO",
           f"DIA vs QQQ {v:+.2f} pp (20 ses.)", "Rotación sectorial/estilo")
    cm("TGA/RRP/reservas ↔ índices", "Liquidez mejora + riesgo sube",
       "CUMPLE" if liquidez == "ACOMPAÑA" and (spx5 or 0) > 0 else "NO SE CUMPLE" if liquidez in ("DRENA", "NO ACOMPAÑA") else "NEUTRAL",
       f"Liquidez {liquidez} · S&P {spx5 or 0:+.2f}%", "Confirma régimen, no entrada")

    # ---------------- adicionales NEXORA
    AD = []
    for k in ("VVIX", "SKEW", "VXN", "RVX", "VIX9D"):
        if V.get(k):
            AD.append({"id": k.lower(), "dato": {"VVIX": "VVIX (volatilidad del VIX)", "SKEW": "SKEW (riesgo de cola)", "VXN": "VXN (volatilidad Nasdaq)",
                                                  "RVX": "RVX (volatilidad Russell)", "VIX9D": "VIX9D (volatilidad 9 días)"}[k],
                       "valor": f"{V[k]['valor']:.2f} · percentil 1 año {V[k]['percentil_1a']}%",
                       "estado": CON if V[k]["percentil_1a"] >= 80 else FAV if V[k]["percentil_1a"] <= 20 else NEU,
                       "lectura": "Alto respecto al último año" if V[k]["percentil_1a"] >= 80 else "Bajo respecto al último año" if V[k]["percentil_1a"] <= 20 else "En rango", "fuente": "Cboe"})
    for k, nm in (("spread_hy", "Spread high yield"), ("spread_ig", "Spread grado de inversión")):
        s = M.get(k)
        if s:
            AD.append({"id": k, "dato": nm, "valor": f"{s['valor_pb']} pb · 4s {s['4s_pb']:+d} pb", "estado": CON if s["4s_pb"] > U["hy_pb_4s"] else FAV if s["4s_pb"] < -U["hy_pb_4s"] else NEU,
                       "lectura": "Se amplía: estrés de crédito (clave para Russell)" if s["4s_pb"] > U["hy_pb_4s"] else "Se estrecha: crédito fácil" if s["4s_pb"] < -U["hy_pb_4s"] else "Estable",
                       "fuente": s["fuente"]})
    ex = M.get("expectativas_letras")
    if ex:
        d = dirv(ex["5d_pb"], 5)
        AD.append({"id": "letras", "dato": "Expectativas de tipos (proxy letras)", "valor": f"1A − EFFR {ex['1a_menos_effr_pb']:+.0f} pb · 5d {ex['5d_pb']:+.0f} pb",
                   "estado": CTX, "lectura": ("Más recortes descontados" if d == "↓" else "Menos recortes / subidas" if d == "↑" else "Sin cambio") + ". " + ex["nota"], "fuente": ex["fuente"]})
    for k, v in (M.get("cot") or {}).items():
        AD.append({"id": "cot_" + k, "dato": f"COT {k}", "valor": f"apalancados {v['apalancados_neto']:+,} ({v['apalancados_1s']:+,} 1s; percentil 52s {v['apalancados_percentil_52s']}%) · gestores {v['gestores_neto']:+,} ({v['gestores_1s']:+,})",
                   "estado": CTX, "lectura": ("Apalancados muy cortos: riesgo de cierre de cortos (short squeeze)" if v["apalancados_percentil_52s"] <= 10 else
                                              "Apalancados muy largos: posicionamiento saturado" if v["apalancados_percentil_52s"] >= 90 else "Posicionamiento sin extremos"),
                   "fuente": f"CFTC TFF, posiciones del {v['fecha']}"})
    for k, nm in (("nasdaq_real10", "¿SE CUMPLE Nasdaq ↔ 10Y real?"), ("sp_dxy", "¿SE CUMPLE S&P ↔ DXY?"), ("sp_10y", "Correlación S&P ↔ 10Y (bolsa-bonos)")):
        r = RL.get(k)
        if r:
            if k == "sp_10y":
                est, lec = CTX, ("Correlación negativa: suben yields y cae la bolsa (régimen de miedo a tipos/inflación)" if (r["corr_60"] or 0) < -0.15 else
                                 "Correlación positiva: yields y bolsa suben juntos (régimen de crecimiento)" if (r["corr_60"] or 0) > 0.15 else "Sin relación clara")
            else:
                est = r["estado"]
                lec = {"SE CUMPLE": "Relación vigente: la chuleta es fiable para este factor.", "DÉBIL": "Relación débil: dar menos peso a este factor.",
                       "ROTA": "RELACIÓN ROTA: buscar el driver alternativo."}.get(r["estado"], "Sin dato")
            AD.append({"id": "rel_" + k, "dato": nm, "valor": f"corr. 20d {r['corr_20']} · 60d {r['corr_60']} · 250d {r['corr_250']}", "estado": est, "lectura": lec,
                       "fuente": "Cálculo NEXORA con cambios diarios"})
    er = M.get("beneficios") or {}
    if er.get("guias_negativas") is not None:
        AD.append({"id": "guias", "dato": "Guías de beneficios (S&P 500)", "valor": f"{er['guias_negativas']} negativas / {er['guias_positivas']} positivas",
                   "estado": FAV if er["guias_positivas"] > er["guias_negativas"] else CON, "lectura": "Más empresas mejoran que empeoran sus previsiones" if er["guias_positivas"] > er["guias_negativas"] else "Más empresas rebajan previsiones",
                   "fuente": f"FactSet Earnings Insight {er['fecha_informe']}"})
    for k, nm in (("peticiones_paro", "Peticiones de paro semanales"), ("ventas_minoristas", "Ventas minoristas")):
        g = G.get(k)
        if g:
            if k == "peticiones_paro":
                AD.append({"id": k, "dato": nm, "valor": f"{g['valor']:,} ({g['semana']}) · media 4s {g['media_4s']:,} vs {g['media_4s_prev']:,}", "estado": CON if g["media_4s"] > g["media_4s_prev"] * 1.05 else NEU,
                           "lectura": "Suben: el empleo se enfría" if g["media_4s"] > g["media_4s_prev"] * 1.05 else "Estables", "fuente": g["fuente"]})
            else:
                AD.append({"id": k, "dato": nm, "valor": f"{g['mm_pct']:+.2f}% m/m ({g['mes']})", "estado": CTX, "lectura": "Consumo " + ("fuerte" if g["mm_pct"] > 0.3 else "débil" if g["mm_pct"] < 0 else "moderado"),
                           "fuente": g["fuente"]})

    EVI = cargar_json("evidencia_indices.json")
    CR = consumo_resumen(M.get("consumo"), EVI)
    if CR:
        AD.append({"id": "consumo", "dato": "Consumo: XLY/XLP (discrecional vs básico)", "valor": CR["valor"], "estado": CTX,
                   "lectura": CR["lectura"] + ". Contexto de ciclo: no vota en el entorno.", "fuente": M["consumo"]["fuente"] + "; " + ((M["consumo"].get("consumo_real") or {}).get("fuente") or "")})

    # ---------------- §5 pasos
    PIdx = {p["indice"]: p for p in PI}
    pasos = [
        {"n": 1, "paso": "MACRO", "que": "2Y → 10Y → 10Y real → DXY → NFCI → FedWatch → VIX", "estado": FAV if lectura.endswith("RISK-ON") else CON if lectura.endswith("RISK-OFF") else NEU,
         "detalle": f"{lectura}: {on} risk-on, {off} risk-off, {sd} sin dato de {len(cond)}"},
        {"n": 2, "paso": "LIQUIDEZ", "que": "TGA → RRP → reservas (M2/H.4.1 = régimen)", "estado": FAV if liquidez == "ACOMPAÑA" else CON if liquidez in ("DRENA", "NO ACOMPAÑA") else NEU, "detalle": f"Liquidez {liquidez}"},
        {"n": 3, "paso": "CRECIMIENTO", "que": "CPI/PCE + empleo + ISM/PMI + calendario", "estado": CTX,
         "detalle": " · ".join(f"{by[i]['dato']}: {by[i]['lectura'].split('.')[0]}" for i in ("inflacion", "nfp", "pmi") if i in by) +
                    (f" · Consumo XLY/XLP: {CR['estado_mercado']} ({CR['confirmacion'].split(':')[0].lower()})" if CR else "")},
        {"n": 4, "paso": "BENEFICIOS", "que": "Earnings y revisiones (S&P/Nasdaq)", "estado": by.get("earnings", {}).get("estado", SD), "detalle": by.get("earnings", {}).get("valor", "Sin dato")},
        {"n": 5, "paso": "RELATIVE STRENGTH", "que": "Nasdaq vs S&P, Russell vs Nasdaq, US30 vs Nasdaq", "estado": CTX,
         "detalle": " · ".join(f"{lab} {(RS.get(k) or {}).get('20d_pp', 0):+.2f} pp" for k, lab in (("nasdaq_vs_sp", "Nasdaq vs S&P"), ("russell_vs_nasdaq", "Russell vs Nasdaq"), ("us30_vs_nasdaq", "US30 vs Nasdaq")) if RS.get(k)) + " (20 sesiones)"},
        {"n": 6, "paso": "PRECIO (HTF)", "que": "Tendencia, máximos/mínimos, gaps, zonas", "estado": CTX,
         "detalle": " · ".join(f"{p['indice']}: {p['precio']}" for p in PI)},
        {"n": 7, "paso": "LIQUIDEZ DEL GRÁFICO", "que": "Pools, máximos/mínimos, sweeps/inducciones", "estado": CTX, "detalle": "Ver mapa de niveles por índice (máximos/mínimos previos y gaps abiertos)."},
        {"n": 8, "paso": "EJECUCIÓN", "que": "Footprint/DOM/delta", "estado": "MANUAL", "detalle": "No automatizable con datos gratuitos: tu plataforma de order flow."},
        {"n": 9, "paso": "ENTRADA", "que": "Contexto + nivel + liquidez + estructura + ejecución", "estado": "MANUAL", "detalle": "Decisión tuya. El informe aporta contexto y niveles; no es una orden."},
    ]
    niv = {nm: pools(d["niveles"], (M.get("tiempo_real") or {}).get("NDX", {}).get("precio") if nm == "Nasdaq 100" and (M.get("tiempo_real") or {}).get("NDX") else d["niveles"]["cierre"])
           for nm, d in I.items() if d.get("niveles")}
    lider = max(((nm, (I.get(nm) or {}).get("20d_pct") or -99) for nm in I), key=lambda x: x[1])[0] if I else None
    Q = [
        (1, "¿Qué están haciendo 2Y, 10Y y 10Y real?", " · ".join(f"{by[i]['dato']} {by[i]['dir']} ({by[i]['valor'].split(' · ')[1] if ' · ' in by[i]['valor'] else by[i]['valor']})" for i in ("t2y", "t10y", "real10") if i in by)),
        (2, "¿DXY confirma o contradice el movimiento?", next((c["estado"] + " · " + c["detalle"] for c in Cmp if c["par"] == "DXY ↔ índices"), "Sin dato")),
        (3, "¿FedWatch está relajándose o endureciéndose?", by["fedwatch"]["lectura"] + (f" Proxy letras: {ex['5d_pb']:+.0f} pb en 5 sesiones." if ex else "")),
        (4, "¿NFCI está aflojando o tensando?", by.get("nfci", {}).get("lectura", "Sin dato")),
        (5, "¿VIX está cayendo, estable o acelerándose?", by.get("vix", {}).get("valor", "—") + " · " + by.get("vix", {}).get("lectura", "")),
        (6, "¿La liquidez TGA/RRP/reservas acompaña?", f"Liquidez {liquidez}"),
        (7, "¿Los beneficios y datos macro apoyan o contradicen?", " · ".join(f"{by[i]['dato']}: {by[i]['estado']}" for i in ("earnings", "pmi", "inflacion") if i in by)),
        (8, "¿Hay amplitud o solo unas pocas mega caps?", by.get("amplitud", {}).get("lectura", "Sin dato") + " · " + by.get("amplitud", {}).get("valor", "")),
        (9, "¿Qué índice muestra relative strength?", f"Líder a 20 sesiones: {lider}. " + " · ".join(f"{nm} {(I.get(nm) or {}).get('20d_pct', 0):+.1f}%" for nm in I)),
        (10, "¿Tengo sweep + estructura + confirmación de footprint/DOM o me anticipo?", "MANUAL: solo tú puedes verificarlo en tu gráfico y en el footprint."),
    ]
    return {"panel": P, "entorno": {"lectura": lectura, "risk_on": on, "risk_off": off, "sin_dato": sd, "disponibles": disp, "condiciones": cond,
                                    "liquidez": liquidez, "breadth": breadth},
            "chuleta_60s": sesgo60, "por_indice": PI, "comparaciones": Cmp, "adicionales": AD, "avisos": avisos, "pasos": pasos,
            "preguntas": [{"n": a, "pregunta": b, "respuesta": c} for a, b, c in Q], "niveles": niv, "umbrales": U,
            "evidencia": EVI, "consumo": CR, "reacciones": reacciones_eventos()}


# ----------------------------------------------------------------- reacción de los índices a los datos macro (registro compartido con el oro)
def reacciones_eventos(path=None, etf_cache=None):
    """Lee eventos_oro.csv (fechas, horas y datos verificados) y mide la reacción diaria de SPY/QQQ/IWM/DIA con OHLC diario:
    datos de las 08:30 NY (antes de la apertura) → hueco de apertura y día completo; 10:00/14:00 NY → apertura→cierre."""
    path = path or os.path.join(HERE, "eventos_oro.csv")
    if not os.path.exists(path):
        return None
    try:
        rows = list(csv.DictReader(open(path, encoding="utf-8")))
    except Exception:  # noqa: BLE001
        return None
    rows = [r for r in rows if r.get("dato") and r.get("direccion") in ("SUBE", "BAJA")]
    if not rows:
        return None
    cache = etf_cache or {}
    for s in ("SPY", "QQQ", "IWM", "DIA"):
        if s not in cache:
            try:
                cache[s] = {x[0]: x for x in nq_hist(s, "etf", 3)}
            except Exception:  # noqa: BLE001
                cache[s] = {}
            time.sleep(0.3)
    import zoneinfo
    NY = zoneinfo.ZoneInfo("America/New_York")
    out = {}
    for r in rows:
        t = dt.datetime.strptime(r["hora_utc"], "%Y-%m-%dT%H:%M").replace(tzinfo=dt.timezone.utc).astimezone(NY)
        d = t.date()
        pre = t.hour < 9 or (t.hour == 9 and t.minute < 30)
        ev = out.setdefault(r["evento"], {})
        for s, c in cache.items():
            if d not in c:
                continue
            prev = [k for k in c if k < d]
            if not prev:
                continue
            p = c[max(prev)]
            x = c[d]
            mov = (x[4] / p[4] - 1) * 100 if pre else (x[4] / x[1] - 1) * 100
            ev.setdefault(s, {"SUBE": [], "BAJA": []})[r["direccion"]].append(mov)
    res = {}
    for ev, dd in out.items():
        res[ev] = {}
        for s, v in dd.items():
            res[ev][s] = {k: {"n": len(x), "mediana_pct": round(statistics.median(x), 2), "pct_positivo": round(sum(y > 0 for y in x) / len(x) * 100)} for k, x in v.items() if x}
    return {"por_evento": res, "nota": "Movimiento del día del dato (08:30 NY: cierre previo→cierre; 10:00 y 14:00 NY: apertura→cierre). «Sube/baja» = dato frente al previo. Mediana."}


# ----------------------------------------------------------------- salida
def to_md(M, E):
    e = E["entorno"]
    L = [f"# NEXORA · Monitor de Índices (chuleta) · datos {M['generado_utc']}", "",
         f"**{e['lectura']}** ({e['risk_on']} risk-on / {e['risk_off']} risk-off / {e['sin_dato']} sin dato) · liquidez {e['liquidez']} · breadth {e['breadth']} · chuleta 60 s: {E['chuleta_60s']}", ""]
    L += [f"⚠️ {a}" for a in E["avisos"]] + ["", "## Panel", ""] + [f"- {p['dato']} {p['dir']} — {p['valor']} · {p['estado']} · {p['lectura']}" for p in E["panel"]]
    L += ["", "## Por índice", ""] + [f"- {p['indice']}: {p['entorno']} · precio {p['precio']} · 20d {p['20d_pct']}%" for p in E["por_indice"]]
    L += ["", "## Comparaciones", ""] + [f"- {c['par']} — {c['estado']} · {c['detalle']}" for c in E["comparaciones"]]
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
    p = os.path.join(a.out, f"indices_{stamp}.json")
    json.dump({"metricas": Mout, "evaluacion": E}, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=str)
    open(os.path.join(a.out, f"indices_{stamp}.md"), "w", encoding="utf-8").write(to_md(Mout, E))
    # historial de amplitud (se acumula día a día: línea avance-descenso propia)
    amp = (Mout.get("amplitud") or {}).get("sesion")
    if amp:
        hp = os.path.join(HERE, "amplitud_hist.csv")
        rows = list(csv.DictReader(open(hp, encoding="utf-8"))) if os.path.exists(hp) else []
        fecha = (Mout.get("indices", {}).get("S&P 500") or {}).get("fecha", stamp)
        if not any(r["fecha"] == fecha for r in rows):
            g, t = amp["grandes_10B"], amp["todas"]
            rows.append({"fecha": fecha, "grandes_suben": g["suben"], "grandes_bajan": g["bajan"], "grandes_pct_suben": g["pct_suben"],
                         "todas_suben": t["suben"], "todas_bajan": t["bajan"], "todas_pct_suben": t["pct_suben"], "volumen_alcista_pct": t["volumen_alcista_pct"]})
            with open(hp, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[-1].keys()))
                w.writeheader()
                w.writerows(rows)
    er = Mout.get("beneficios")
    if er and er.get("crecimiento_bpa_pct") is not None:
        hp = os.path.join(HERE, "beneficios_hist.csv")
        rows = list(csv.DictReader(open(hp, encoding="utf-8"))) if os.path.exists(hp) else []
        if not any(r["fecha_informe"] == er["fecha_informe"] for r in rows):
            rows.append({"fecha_informe": er["fecha_informe"], "trimestre": er.get("trimestre", ""), "crecimiento_bpa_pct": er["crecimiento_bpa_pct"],
                         "per_12m": er.get("per_12m", ""), "guias_negativas": er.get("guias_negativas", ""), "guias_positivas": er.get("guias_positivas", "")})
            with open(hp, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[-1].keys()))
                w.writeheader()
                w.writerows(rows)
    print(p)
    print(json.dumps(E["entorno"], ensure_ascii=False))
    if M["errores"]:
        print("ERRORES:", json.dumps(M["errores"], ensure_ascii=False))


if __name__ == "__main__":
    main()
