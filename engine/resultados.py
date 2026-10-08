#!/usr/bin/env python3
"""
NEXORA · Resultados de las grandes empresas que mueven los índices (mega caps + bancos que abren la temporada).

Fuente: Nasdaq Data (datos de Zacks Investment Research), sin clave:
  · /api/analyst/{SYM}/earnings-date      → próxima fecha (CONFIRMADA o ESTIMADA por algoritmo), momento (antes/después de apertura), BPA estimado.
  · /api/company/{SYM}/earnings-surprise  → últimos 4 trimestres: BPA publicado vs consenso (% sorpresa) y fecha.
  · /api/analyst/{SYM}/earnings-forecast  → consenso del trimestre en curso y revisiones al alza/baja en 4 semanas.
  · Reacción del precio: cierre de la sesión anterior al informe → cierre de la sesión siguiente (2 sesiones; cubre
    publicaciones antes de la apertura y después del cierre, porque Nasdaq no siempre informa del momento).

    python resultados.py [--out DIR]  → resultados_YYYYMMDD.json / .md
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from indices import nq_get, nq_hist  # noqa: E402

EMPRESAS = {"NVDA": "NVIDIA", "MSFT": "Microsoft", "AAPL": "Apple", "AMZN": "Amazon", "GOOGL": "Alphabet", "META": "Meta Platforms",
            "AVGO": "Broadcom", "TSLA": "Tesla", "JPM": "JPMorgan Chase", "LLY": "Eli Lilly", "NFLX": "Netflix", "GS": "Goldman Sachs"}
CLAVE = {"NVDA", "MSFT", "AAPL", "AMZN", "GOOGL", "META", "AVGO", "TSLA"}   # las que más pesan en S&P 500 / Nasdaq 100
HOY = dt.date.today()


def _f(x):
    try:
        return float(str(x).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def proxima(sym):
    url = f"https://api.nasdaq.com/api/analyst/{sym}/earnings-date"
    d = nq_get(url)["data"]
    t = d.get("reportText") or ""
    m = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", t)
    if not m:
        return None
    f = dt.datetime.strptime(m.group(1), "%m/%d/%Y").date()
    confirmada = "algorithm" not in t and "estimated" not in t
    momento = "antes de la apertura" if "before market open" in t else "después del cierre" if "after market close" in t else "momento no publicado"
    b = re.search(r"consensus EPS forecast for the quarter is \$(-?\d+(?:\.\d+)?)", t)
    return {"simbolo": sym, "empresa": EMPRESAS.get(sym, sym), "fecha": f.isoformat(), "confirmada": confirmada, "momento": momento,
            "bpa_estimado": f"${b.group(1)}" if b else "—", "url": f"https://www.nasdaq.com/market-activity/stocks/{sym.lower()}/earnings"}


def historico(sym):
    d = nq_get(f"https://api.nasdaq.com/api/company/{sym}/earnings-surprise")["data"]
    rows = ((d or {}).get("earningsSurpriseTable") or {}).get("rows") or []
    out = []
    for r in rows:
        try:
            out.append({"trimestre": r["fiscalQtrEnd"], "fecha": dt.datetime.strptime(r["dateReported"], "%m/%d/%Y").date().isoformat(),
                        "bpa": _f(r["eps"]), "consenso": _f(r["consensusForecast"]), "sorpresa_pct": _f(r["percentageSurprise"])})
        except (KeyError, ValueError):
            continue
    return out


def revisiones(sym):
    d = nq_get(f"https://api.nasdaq.com/api/analyst/{sym}/earnings-forecast")["data"]
    q = (((d or {}).get("quarterlyForecast") or {}).get("rows") or [])
    if not q:
        return None
    r = q[0]
    return {"trimestre": r.get("fiscalEnd"), "consenso": r.get("consensusEPSForecast"), "n": r.get("noOfEstimates"),
            "revisiones_alza_4s": r.get("up"), "revisiones_baja_4s": r.get("down")}


def reaccion(ohlc, fecha):
    """Cierre anterior al día del informe → cierre de la sesión siguiente."""
    f = dt.date.fromisoformat(fecha)
    ds = [x[0] for x in ohlc]
    antes = [i for i, d in enumerate(ds) if d < f]
    despues = [i for i, d in enumerate(ds) if d > f]
    if not antes or not despues:
        return None
    return round((ohlc[despues[0]][4] / ohlc[antes[-1]][4] - 1) * 100, 2)


def medir():
    out, err = [], {}
    for sym in EMPRESAS:
        rec = {"simbolo": sym, "empresa": EMPRESAS[sym]}
        for k, fn in (("proxima", proxima), ("historico", historico), ("revisiones", revisiones)):
            try:
                rec[k] = fn(sym)
            except Exception as e:  # noqa: BLE001
                err[f"{sym}_{k}"] = f"{type(e).__name__}: {e}"
            time.sleep(0.3)
        try:
            o = nq_hist(sym, "stocks", 2)
            for h in rec.get("historico") or []:
                h["reaccion_2s_pct"] = reaccion(o, h["fecha"])
            if o:
                rec["precio"] = o[-1][4]
                rec["precio_fecha"] = o[-1][0].isoformat()
        except Exception as e:  # noqa: BLE001
            err[f"{sym}_precio"] = f"{type(e).__name__}: {e}"
        out.append(rec)
    return out, err


def proximos(hasta):
    """Solo las próximas fechas (para el calendario)."""
    R = []
    for sym in EMPRESAS:
        try:
            p = proxima(sym)
            if p and HOY <= dt.date.fromisoformat(p["fecha"]) <= hasta:
                R.append(p)
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.2)
    return R


def resumen(E):
    """Lectura agregada: sorpresas del último trimestre publicado y reacción media."""
    sorp, reac, pos_con_caida = [], [], 0
    for r in E:
        h = (r.get("historico") or [None])[0]
        if h and h.get("sorpresa_pct") is not None:
            sorp.append(h["sorpresa_pct"])
            if h.get("reaccion_2s_pct") is not None:
                reac.append(h["reaccion_2s_pct"])
                if h["sorpresa_pct"] > 0 and h["reaccion_2s_pct"] < 0:
                    pos_con_caida += 1
    rev_up = sum((r.get("revisiones") or {}).get("revisiones_alza_4s") or 0 for r in E)
    rev_dn = sum((r.get("revisiones") or {}).get("revisiones_baja_4s") or 0 for r in E)
    return {"empresas": len(E), "baten_estimacion": sum(x > 0 for x in sorp), "con_dato": len(sorp),
            "sorpresa_mediana_pct": round(statistics.median(sorp), 1) if sorp else None,
            "reaccion_mediana_pct": round(statistics.median(reac), 2) if reac else None,
            "baten_pero_caen": pos_con_caida, "revisiones_alza_4s": rev_up, "revisiones_baja_4s": rev_dn,
            "lectura": _lectura(sorp, reac)}


def _lectura(sorp, reac):
    """CRITERIO NEXORA: «baten» si ≥ 70 % supera el consenso; «premia» si la reacción mediana > +0,5 %, «castiga» si < −0,5 %."""
    if not sorp:
        return "Sin datos suficientes"
    baten = sum(x > 0 for x in sorp) >= len(sorp) * 0.7
    rm = statistics.median(reac) if reac else None
    if not baten:
        return "Resultados mixtos: menos del 70 % bate la estimación"
    if rm is None:
        return "Las grandes baten estimaciones (reacción del precio sin dato)"
    if rm > 0.5:
        return "Las grandes baten estimaciones y el mercado lo premia"
    if rm < -0.5:
        return "Baten estimaciones pero el mercado las castiga (puede indicar expectativas muy altas)"
    return "Baten estimaciones, pero la reacción del mercado es neutra (puede indicar que ya estaba descontado)"


def to_md(E, S, err):
    L = ["# Resultados de las grandes empresas (mega caps)", "",
         f"Último trimestre publicado: {S['baten_estimacion']}/{S['con_dato']} baten la estimación · sorpresa mediana {S['sorpresa_mediana_pct']} % · reacción mediana 2 sesiones {S['reaccion_mediana_pct']} % · "
         f"{S['baten_pero_caen']} baten pero caen · revisiones 4 semanas: {S['revisiones_alza_4s']} al alza / {S['revisiones_baja_4s']} a la baja. **{S['lectura']}.**", "",
         "| Empresa | Próximos resultados | BPA estimado | Último trimestre | Sorpresa | Reacción 2 ses. | Revisiones 4s ↑/↓ |", "|---|---|---|---|---|---|---|"]
    for r in sorted(E, key=lambda r: (r.get("proxima") or {}).get("fecha", "9999")):
        p, h, v = r.get("proxima") or {}, (r.get("historico") or [{}])[0], r.get("revisiones") or {}
        L.append(f"| {r['empresa']} ({r['simbolo']}) | {(p['fecha'] + (' (confirmada, ' + p['momento'] + ')' if p.get('confirmada') else ' (estimada)')) if p.get('fecha') else 'sin fecha publicada'} | {p.get('bpa_estimado', '—')} | "
                 f"{h.get('trimestre', '—')} ({h.get('fecha', '')}) | {h.get('sorpresa_pct', '—')} % | {h.get('reaccion_2s_pct', '—')} % | {v.get('revisiones_alza_4s', '—')}/{v.get('revisiones_baja_4s', '—')} |")
    if err:
        L += ["", "SIN DATO: " + "; ".join(f"{k}: {v}" for k, v in err.items())]
    L += ["", "Fuente: Nasdaq Data (Zacks Investment Research). Fechas «estimadas» = algoritmo de Zacks basado en fechas históricas; pueden cambiar hasta que la empresa las confirme."]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    E, err = medir()
    S = resumen(E)
    os.makedirs(a.out, exist_ok=True)
    p = os.path.join(a.out, f"resultados_{HOY.strftime('%Y%m%d')}.json")
    json.dump({"generado": dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "empresas": E, "resumen": S, "errores": err},
              open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(p.replace(".json", ".md"), "w", encoding="utf-8").write(to_md(E, S, err))
    print(p)
    print(json.dumps(S, ensure_ascii=False))
    if err:
        print("ERRORES:", err)


if __name__ == "__main__":
    main()
