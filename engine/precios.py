"""NEXORA · precios históricos gratuitos para los módulos de la fase 6 (Semis/Software y Gamma).

Yahoo Finance (sin clave) como fuente principal; Nasdaq.com como respaldo para acciones y ETF (las IP compartidas de GitHub Actions
reciben a veces 429 de Yahoo). Si ninguna responde se lanza la excepción: quien llama decide qué es SIN DATO. Nada se interpola."""
from __future__ import annotations

import datetime as dt
import time

import fuentes


def _yahoo(sym, rango, intervalo):
    q = sym.replace("^", "%5E").replace("=", "%3D")
    last = None
    for host in ("query2", "query1"):
        try:
            j = fuentes.json_(f"https://{host}.finance.yahoo.com/v8/finance/chart/{q}?range={rango}&interval={intervalo}", tries=2, timeout=40)
            return j["chart"]["result"][0]
        except Exception as e:  # noqa: BLE001
            last = e
    raise last


def diario(sym, rango="2y", nasdaq_clase=None):
    """Barras diarias [{fecha, o, h, l, c}] ordenadas. `nasdaq_clase` ('etf'|'stocks'|'index') activa el respaldo de Nasdaq.com."""
    try:
        r = _yahoo(sym, rango, "1d")
        off = r["meta"].get("gmtoffset", 0)
        q = r["indicators"]["quote"][0]
        out = []
        for i, t in enumerate(r["timestamp"]):
            c = q["close"][i]
            if c is None:
                continue
            f = dt.datetime.fromtimestamp(t + off, dt.timezone.utc).date()
            o, h, l = q["open"][i], q["high"][i], q["low"][i]
            out.append({"fecha": f, "o": o if o is not None else c, "h": h if h is not None else c, "l": l if l is not None else c, "c": float(c)})
        if len(out) < 5:
            raise RuntimeError("serie vacía")
        return out, "Yahoo Finance"
    except Exception as e_y:  # noqa: BLE001
        if not nasdaq_clase:
            raise
        try:
            return _nasdaq(sym, nasdaq_clase, rango), f"Nasdaq.com (respaldo: Yahoo no respondió: {type(e_y).__name__})"
        except Exception as e_n:  # noqa: BLE001
            raise RuntimeError(f"Yahoo: {type(e_y).__name__}: {str(e_y)[:60]} · Nasdaq.com: {type(e_n).__name__}: {str(e_n)[:60]}") from e_n


def _nasdaq(sym, clase, rango):
    dias = {"1mo": 35, "3mo": 100, "6mo": 190, "1y": 370, "2y": 740}.get(rango, 370)
    hoy = dt.date.today()
    url = (f"https://api.nasdaq.com/api/quote/{sym}/historical?assetclass={clase}&fromdate={(hoy - dt.timedelta(days=dias)).isoformat()}"
           f"&limit=9999&todate={hoy.isoformat()}")
    j = fuentes.json_(url, tries=2, timeout=40, accept="application/json")
    filas = ((j.get("data") or {}).get("tradesTable") or {}).get("rows") or []
    out = []
    for r in filas:
        try:
            f = dt.datetime.strptime(r["date"], "%m/%d/%Y").date()
            n = lambda s: float(str(s).replace("$", "").replace(",", ""))  # noqa: E731
            c = n(r["close"])
            out.append({"fecha": f, "o": n(r.get("open", c)), "h": n(r.get("high", c)), "l": n(r.get("low", c)), "c": c})
        except (KeyError, ValueError):
            continue
    if len(out) < 5:
        raise RuntimeError("Nasdaq.com sin filas")
    out.sort(key=lambda x: x["fecha"])
    return out


def intradia(sym, rango="5d", intervalo="5m"):
    """Barras intradía [(datetime naive en la hora local del mercado, cierre)] sin los huecos None."""
    r = _yahoo(sym, rango, intervalo)
    off = r["meta"].get("gmtoffset", 0)
    c = r["indicators"]["quote"][0]["close"]
    out = [(dt.datetime.fromtimestamp(t + off, dt.timezone.utc).replace(tzinfo=None), float(v)) for t, v in zip(r["timestamp"], c) if v is not None]
    if not out:
        raise RuntimeError("sin barras")
    return out


def pausa(s=0.7):
    time.sleep(s)
