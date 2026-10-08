#!/usr/bin/env python3
"""
NEXORA · FedWatch propio (método CME) — probabilidades de la Fed por reunión.

Mismo método que CME FedWatch: los futuros de fondos federales a 30 días (CBOT, código ZQ) liquidan contra la media
mensual del tipo efectivo (EFFR). Con el precio de cada mes se despeja el tipo esperado antes y después de cada reunión
del FOMC y, de ahí, la probabilidad de subida / mantenimiento / bajada.

Fuentes: precios de futuros ZQ (Yahoo Finance, fuente NO oficial, cierre diario, ~15 min de retraso en sesión),
tipo efectivo y rango objetivo (FRED: EFFR, DFEDTARL, DFEDTARU), calendario FOMC (federalreserve.gov).
Puede diferir unos puntos de CME (CME usa sus precios de liquidación y su árbol completo de escenarios).
Si falla una descarga: SIN DATO (nunca se estima).

Uso: python fedwatch.py [--out DIR] [--reuniones 6]
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from liquidez_cripto import fred  # noqa: E402

COD = "FGHJKMNQUVXZ"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
PASO = 0.25


def zq(y, m):
    return f"ZQ{COD[m - 1]}{y % 100:02d}.CBT"


def futuro(sym):
    """{fecha: tipo implícito (100 − precio)} de las últimas ~15 sesiones."""
    last = None
    for k in range(3):
        try:
            req = urllib.request.Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1mo&interval=1d", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                j = json.loads(r.read().decode())["chart"]["result"][0]
            out = {}
            for t, c in zip(j["timestamp"], j["indicators"]["quote"][0]["close"]):
                if c:
                    out[dt.datetime.utcfromtimestamp(t).date()] = round(100 - c, 4)
            return out
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (k + 1))
    raise last


def reuniones_fomc():
    from calendario import fomc
    return [d for d, _, _ in fomc()]


def at_or_before(d_map, fecha):
    ks = [k for k in d_map if k <= fecha]
    return d_map[max(ks)] if ks else None


def calcular(fecha, fut, effr, reuniones, n=6):
    """Probabilidades para las n reuniones posteriores a `fecha` con los precios de ese día."""
    base = at_or_before(effr, fecha - dt.timedelta(days=0))
    if base is None:
        return None
    prox = [r for r in reuniones if r > fecha][:n]
    meses_reunion = {(r.year, r.month) for r in reuniones}
    out, start = [], base
    for r in prox:
        y, m = r.year, r.month
        N = calendar.monthrange(y, m)[1]
        ny, nm = (y + (m == 12), m % 12 + 1)
        f_mes, f_sig = fut.get((y, m)) or {}, fut.get((ny, nm)) or {}
        if (ny, nm) not in meses_reunion and at_or_before(f_sig, fecha) is not None:
            end, metodo = at_or_before(f_sig, fecha), f"mes siguiente sin reunión ({zq(ny, nm)[:5]})"
        else:
            avg = at_or_before(f_mes, fecha)
            if avg is None:
                break
            d = r.day  # la decisión se aplica desde el día siguiente
            end, metodo = (avg * N - start * d) / (N - d), f"mes de la reunión ({zq(y, m)[:5]})"
        cambio = end - start
        pasos = cambio / PASO
        lo = int(pasos // 1)
        fr = pasos - lo
        dist = {}
        for k, p in ((lo, 1 - fr), (lo + 1, fr)):
            if p > 0.005:
                dist[k * 25] = round(p * 100, 1)
        acum = (end - base) / PASO
        alo = int(acum // 1)
        afr = acum - alo
        dist_acum = {}
        for k, p in ((alo, 1 - afr), (alo + 1, afr)):
            if p > 0.005:
                dist_acum[k * 25] = round(p * 100, 1)
        out.append({"reunion": r.isoformat(), "tipo_esperado": round(end, 4), "cambio_reunion_pb": round(cambio * 100, 1),
                    "cambio_acumulado_pb": round((end - base) * 100, 1), "metodo": metodo,
                    "prob_reunion": {"subida": round(sum(v for k, v in dist.items() if k > 0), 1), "mantiene": round(dist.get(0, 0.0), 1),
                                     "bajada": round(sum(v for k, v in dist.items() if k < 0), 1), "detalle_pb": dist},
                    "prob_acumulada": {"mas_alto_que_hoy": round(sum(v for k, v in dist_acum.items() if k > 0), 1),
                                       "igual": round(dist_acum.get(0, 0.0), 1),
                                       "mas_bajo_que_hoy": round(sum(v for k, v in dist_acum.items() if k < 0), 1), "detalle_pb": dist_acum}})
        start = end
    return {"fecha": fecha.isoformat(), "effr": base, "reuniones": out}


def medir(n=6):
    reun = reuniones_fomc()
    hoy = dt.date.today()
    prox = [r for r in reun if r > hoy - dt.timedelta(days=10)][: n + 1]
    meses = set()
    for r in prox:
        meses.add((r.year, r.month))
        meses.add((r.year + (r.month == 12), r.month % 12 + 1))
    fut, err = {}, {}
    for (y, m) in sorted(meses):
        try:
            fut[(y, m)] = futuro(zq(y, m))
        except Exception as e:  # noqa: BLE001
            err[zq(y, m)] = f"{type(e).__name__}: {e}"
        time.sleep(0.3)
    effr = {d: v for d, v in fred("EFFR", (hoy - dt.timedelta(days=60)).isoformat())}
    lo_, hi_ = fred("DFEDTARL", (hoy - dt.timedelta(days=30)).isoformat()), fred("DFEDTARU", (hoy - dt.timedelta(days=30)).isoformat())
    sesiones = sorted({d for f in fut.values() for d in f})[-6:]
    serie = [c for c in (calcular(d, fut, effr, reun, n) for d in sesiones) if c and c["reuniones"]]
    if not serie:
        raise RuntimeError("sin precios de futuros ZQ: " + json.dumps(err))
    act = serie[-1]
    prev = serie[-2] if len(serie) > 1 else None
    p5 = serie[0] if len(serie) > 1 else None
    R = act["reuniones"]

    def cambio(s0, idx, clave):
        if not s0:
            return None
        r0 = next((x for x in s0["reuniones"] if x["reunion"] == R[idx]["reunion"]), None)
        if not r0:
            return None
        a, b = R[idx], r0
        if clave == "subida":
            return round(a["prob_reunion"]["subida"] - b["prob_reunion"]["subida"], 1)
        if clave == "bajada":
            return round(a["prob_reunion"]["bajada"] - b["prob_reunion"]["bajada"], 1)
        return round((a["tipo_esperado"] - b["tipo_esperado"]) * 100, 1)
    for i, r in enumerate(R):
        r["subida_1d_pts"], r["bajada_1d_pts"], r["tipo_1d_pb"] = cambio(prev, i, "subida"), cambio(prev, i, "bajada"), cambio(prev, i, "tipo")
        r["subida_5d_pts"], r["tipo_5d_pb"] = cambio(p5, i, "subida"), cambio(p5, i, "tipo")
    # lectura: ¿el mercado descuenta una Fed más dura o más blanda que ayer / hace una semana? (tipo esperado a 3 reuniones)
    k = min(2, len(R) - 1)
    d1, d5 = R[k]["tipo_1d_pb"], R[k]["tipo_5d_pb"]
    lectura = ("MÁS DURA (el mercado espera tipos más altos)" if (d5 or 0) >= 5 else "MÁS BLANDA (el mercado espera tipos más bajos)" if (d5 or 0) <= -5 else "SIN CAMBIO RELEVANTE")
    nxt = R[0]
    frase = (f"Reunión del {nxt['reunion']}: subida {nxt['prob_reunion']['subida']:.0f} %, mantener {nxt['prob_reunion']['mantiene']:.0f} %, bajada {nxt['prob_reunion']['bajada']:.0f} %"
             + (f" (ayer subida {nxt['prob_reunion']['subida'] - nxt['subida_1d_pts']:.0f} %)" if nxt.get("subida_1d_pts") is not None else ""))
    return {"fecha_precios": act["fecha"], "generado_utc": dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            "rango_objetivo": [lo_[-1][1] if lo_ else None, hi_[-1][1] if hi_ else None], "effr": act["effr"],
            "reuniones": R, "lectura": lectura, "tipo_esperado_3_reuniones_1d_pb": d1, "tipo_esperado_3_reuniones_5d_pb": d5,
            "resumen": frase, "historial": [{"fecha": s["fecha"], "prox_subida": s["reuniones"][0]["prob_reunion"]["subida"],
                                             "prox_bajada": s["reuniones"][0]["prob_reunion"]["bajada"], "reunion": s["reuniones"][0]["reunion"]} for s in serie],
            "errores": err,
            "fuente": "Cálculo NEXORA con el método de CME FedWatch: futuros de fondos federales ZQ (CBOT, precios vía Yahoo Finance) + EFFR y rango objetivo (FRED) + calendario FOMC (Federal Reserve). Puede diferir unos puntos de CME."}


def para_monitor(F):
    """Formato que esperan evaluar() de los monitores (cripto, oro, índices): cambio de 5 sesiones del tipo esperado."""
    if not F or not F.get("reuniones"):
        return None
    r0 = F["reuniones"][0]
    d5 = F.get("tipo_esperado_3_reuniones_5d_pb")
    cambio = "RELAJACION" if (d5 or 0) <= -5 else "ENDURECIMIENTO" if (d5 or 0) >= 5 else "SIN CAMBIO"
    pr = r0["prob_reunion"]
    return {"cambio": cambio,
            "valor": f"{r0['reunion']}: subida {pr['subida']:.0f} % · mantener {pr['mantiene']:.0f} % · bajada {pr['bajada']:.0f} %",
            "detalle": (f"1 sesión {r0['subida_1d_pts']:+.0f} pts de subida; " if r0.get("subida_1d_pts") is not None else "") +
                       (f"tipo esperado a 3 reuniones {d5:+.0f} pb en 5 sesiones" if d5 is not None else ""),
            "fuente": "FedWatch NEXORA (futuros ZQ, método CME) " + F["fecha_precios"]}


_CACHE = {}


def cargar(path=None):
    """Lee un JSON de fedwatch.py o, si no hay, lo calcula. Devuelve None si falla (SIN DATO)."""
    try:
        if path and os.path.exists(path):
            return json.load(open(path, encoding="utf-8"))
        if "F" not in _CACHE:
            _CACHE["F"] = medir()
        return _CACHE["F"]
    except Exception:  # noqa: BLE001
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out")
    ap.add_argument("--reuniones", type=int, default=6)
    a = ap.parse_args()
    F = medir(a.reuniones)
    os.makedirs(a.out, exist_ok=True)
    p = os.path.join(a.out, f"fedwatch_{dt.date.today():%Y%m%d}.json")
    json.dump(F, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(p)
    print(F["resumen"], "·", F["lectura"])
    for r in F["reuniones"]:
        print(r["reunion"], f"tipo {r['tipo_esperado']:.3f}", r["prob_reunion"], "acum", r["prob_acumulada"]["mas_alto_que_hoy"], "1d", r["subida_1d_pts"])


if __name__ == "__main__":
    main()
