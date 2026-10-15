#!/usr/bin/env python3
"""NEXORA · FASE 8 · MONITOR DE REACCIÓN A EVENTOS (IPC, empleo NFP, PCE y decisión FOMC). Gratis, sin IA, nunca se inventa un dato.

Qué hace
  1. Eventos: fechas y horas del calendario oficial que ya usa calendario.py (FRED Release Calendar, que republica BLS y BEA; federalreserve.gov para el FOMC).
  2. Precios (Yahoo Finance, API v8 chart, barras de 5 min) en T-5, T+5, T+15, T+30, T+60, T+120 y cierre (16:00 ET):
       2Y  ← ZT=F (futuro del bono a 2 años). 2YY=F NO sirve: Yahoo solo da unas pocas barras al día. El cambio en pb = beta × Δprecio, con la beta
             calibrada contra la curva par OFICIAL del Tesoro (2 Yr, diario; se publica la beta y el R²).
       10Y ← ^TNX (rendimiento). ^TNX solo cotiza hasta las 15:00 ET: sin barra, se usa ZN=F × beta calibrada contra ^TNX, y se marca en el registro.
       DXY (DX-Y.NYB) · oro (GC=F) · NQ (NQ=F) · ES (ES=F) · BTC (BTC-USD).
       10Y real (FRED DFII10): solo se añade al día siguiente y se marca así.
  3. Sorpresa: salto del 2Y en T+5, en z-score frente a los eventos DEL MISMO TIPO de los últimos 60 días (n ≥ 4); si no hay muestra, en pb y marcado.
  4. Clasificación CRITERIO NEXORA en cada fase (reglas en REGLAS y en la página). Umbral de cada serie = máx(suelo, 0,5 × RMS de sus movimientos en
     la misma fase en los eventos de los 60 días previos, n ≥ 4); con menos muestra, solo el suelo y se marca «fijo».
  5. Giro: si la clasificación en T+60 o T+120 difiere de la de T+5 → alerta Telegram, una por evento y fase.
  6. Registro SOLO-AÑADIR: data/reacciones_eventos.csv (+ data/estado_reacciones.json con los avisos enviados).

Uso:  python reaccion.py --vivo          (job de GitHub Actions: espera dentro del job y registra en tiempo real)
      python reaccion.py --reconstruir   (siembra los eventos de los últimos 60 días que Yahoo permita reconstruir + REAL10 + JSON)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics
import sys
import time
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import csvlog  # noqa: E402
import precios  # noqa: E402

NY, UTC = ZoneInfo("America/New_York"), dt.timezone.utc
SITE_DATA = os.path.join(os.path.dirname(HERE), "site", "data")
CSV = "reacciones_eventos.csv"
ESTADO = os.path.join(csvlog.DATA, "estado_reacciones.json")

VERSION_REGLAS = "1.0"
YAHOO = {"zt": "ZT=F", "tnx": "^TNX", "zn": "ZN=F", "dxy": "DX-Y.NYB", "oro": "GC=F", "nq": "NQ=F", "es": "ES=F", "btc": "BTC-USD"}
FASES = [("T-5", -5), ("T+5", 5), ("T+15", 15), ("T+30", 30), ("T+60", 60), ("T+120", 120), ("CIERRE", None)]
HORA_EVENTO = {"IPC": "08:30", "NFP": "08:30", "PCE": "08:30", "FOMC": "14:00"}
VENTANA_DIAS = 60
MIN_N = 4                       # muestra mínima para usar z-score (umbrales y sorpresa)
K_UMBRAL = 0.5                  # umbral = 0,5 × RMS de los movimientos previos de esa serie y fase
SUELOS = {"y2": 2.0, "y10": 2.0, "dxy": 0.10, "nq": 0.20}   # pb, pb, %, %
TOL_BARRA_MIN = 10              # una barra más vieja que esto respecto al instante pedido no vale
RETRASO_VIVO_MIN = 15           # registrado más tarde que esto tras el instante objetivo → «reconstruido»
CLASES = ["FED MÁS DURA", "FED MÁS SUAVE", "REFUGIO", "EMPINAMIENTO POR PLAZO LARGO", "SIN REACCIÓN", "MIXTA (sin regla)"]

REGLAS = [
    {"clase": "FED MÁS DURA", "regla": "2Y sube, 10Y sube y DXY sube (los tres por encima de su umbral)."},
    {"clase": "FED MÁS SUAVE", "regla": "2Y baja, 10Y baja y DXY baja (los tres por debajo de −umbral)."},
    {"clase": "REFUGIO", "regla": "10Y baja y NQ baja (ambos más allá del umbral) y el DXY, tras una subida inicial ≥ su umbral, ha devuelto al menos la mitad."},
    {"clase": "EMPINAMIENTO POR PLAZO LARGO", "regla": "10Y sube (≥ umbral) y sube al menos un umbral más que el 2Y."},
    {"clase": "SIN REACCIÓN", "regla": "2Y, 10Y, DXY y NQ se mueven por debajo de su umbral."},
    {"clase": "MIXTA (sin regla)", "regla": "Hay movimiento por encima del umbral pero no encaja en ninguna de las anteriores."},
]
PRECEDENCIA = "Se evalúan en el orden de la lista: la primera que se cumple gana."
SENCILLO = {
    "FED MÁS DURA": "el mercado lee que la Fed será más dura: suben los tipos a corto y largo y sube el dólar",
    "FED MÁS SUAVE": "el mercado lee que la Fed será más blanda: bajan los tipos y baja el dólar",
    "REFUGIO": "los bonos suben y la bolsa cae: el dinero busca refugio, no es una Fed más blanda",
    "EMPINAMIENTO POR PLAZO LARGO": "suben más los tipos largos que el 2Y: preocupa más el largo plazo que la próxima reunión",
    "SIN REACCIÓN": "el mercado casi no se ha movido",
    "MIXTA (sin regla)": "hay movimiento pero sin un patrón claro",
}
CAMPOS = ["evento_id", "tipo", "evento", "fecha", "hora_ny", "fase", "objetivo_utc", "barra_utc", "edad_min", "zt", "tnx", "zn", "dxy", "oro", "nq", "es", "btc",
          "d_y2_pb", "d_y10_pb", "y10_fuente", "d_dxy_pct", "d_oro_pct", "d_nq_pct", "d_es_pct", "d_btc_pct", "dxy_pico_pct", "clasificacion", "umbral_origen",
          "th_y2", "th_y10", "th_dxy", "th_nq", "beta_2y", "r2_2y", "beta_10y", "r2_10y", "real10", "d_real10_pb", "origen", "registrado_utc", "fuente"]


def ahora():
    return dt.datetime.now(UTC)


def fnum(x, d=4):
    return "" if x is None else round(x, d)


def num(x):
    try:
        return float(x) if x not in ("", None) else None
    except ValueError:
        return None


# ------------------------------------------------------------------ eventos (calendario oficial de calendario.py)
def eventos(desde, hasta):
    import calendario as C
    years = sorted({desde.year, hasta.year})
    out = {}
    for rid, tipo in ((10, "IPC"), (50, "NFP"), (54, "PCE")):
        try:
            for d, h, nombre, url in C.fred_calendar(rid, years):
                if desde <= d <= hasta:
                    out[f"{tipo}-{d}"] = {"id": f"{tipo}-{d}", "tipo": tipo, "evento": C.FRED_RELEASES[rid][0], "fecha": d, "hora_ny": h or HORA_EVENTO[tipo],
                                          "fuente": f"FRED Release Calendar · {nombre} (BLS/BEA)", "url": url}
        except Exception as e:  # noqa: BLE001
            print(f"calendario {tipo}: {type(e).__name__}: {str(e)[:80]}")
    try:
        for d, sep, url in C.fomc():
            if desde <= d <= hasta:
                out[f"FOMC-{d}"] = {"id": f"FOMC-{d}", "tipo": "FOMC", "evento": "Decisión FOMC (Fed)", "fecha": d, "hora_ny": HORA_EVENTO["FOMC"],
                                    "fuente": "federalreserve.gov (calendario FOMC)", "url": url}
    except Exception as e:  # noqa: BLE001
        print(f"calendario FOMC: {type(e).__name__}: {str(e)[:80]}")
    return sorted(out.values(), key=lambda x: (x["fecha"], x["hora_ny"]))


def t_evento(ev):
    h, m = map(int, ev["hora_ny"].split(":"))
    return dt.datetime.combine(ev["fecha"], dt.time(h, m), NY).astimezone(UTC)


def objetivo(ev, minutos):
    if minutos is None:  # cierre de Nueva York 16:00 ET
        return dt.datetime.combine(ev["fecha"], dt.time(16, 0), NY).astimezone(UTC)
    return t_evento(ev) + dt.timedelta(minutes=minutos)


# ------------------------------------------------------------------ precios
def barras(rango="60d"):
    """{clave: {epoch_inicio_barra: cierre}} con barras de 5 min. Una serie que falla queda vacía (SIN DATO)."""
    out, err = {}, {}
    for k, sym in YAHOO.items():
        try:
            r = precios._yahoo(sym, rango, "5m")
            q = r["indicators"]["quote"][0]["close"]
            out[k] = {int(t): float(c) for t, c in zip(r["timestamp"], q) if c is not None and int(t) % 300 == 0}
        except Exception as e:  # noqa: BLE001
            out[k], err[k] = {}, f"{type(e).__name__}: {str(e)[:80]}"
        time.sleep(0.2)
    return out, err


def precio_en(B, k, t, tol=TOL_BARRA_MIN):
    """Precio de la serie k en el instante t (UTC): cierre de la barra de 5 min que EMPIEZA en t−5 min (su cierre es el precio en t).
    Devuelve (valor, inicio_de_barra_epoch, edad_min) o (None, None, None)."""
    s = int(t.timestamp()) - 300
    s -= s % 300
    for i in range(0, tol // 5 + 1):
        v = B.get(k, {}).get(s - 300 * i)
        if v is not None:
            return v, s - 300 * i, round(i * 5.0, 1)
    return None, None, None


def pico_dxy(B, t0, t1):
    """Máxima subida del DXY (en % frente a T-5) entre t0 (T-5) y t1."""
    v0, _, _ = precio_en(B, "dxy", t0)
    if v0 is None:
        return None
    mx, t = 0.0, t0
    while t <= t1:
        v, _, _ = precio_en(B, "dxy", t, tol=5)
        if v is not None:
            mx = max(mx, (v / v0 - 1) * 100)
        t += dt.timedelta(minutes=5)
    return mx


def _reg(x, y):
    n = len(x)
    if n < 20:
        return None, None
    mx, my = statistics.fmean(x), statistics.fmean(y)
    vx = sum((a - mx) ** 2 for a in x)
    if vx == 0:
        return None, None
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / vx, statistics.correlation(x, y) ** 2


def calibrar(B):
    """beta (pb por punto de precio) y R² de ZT=F contra la curva par OFICIAL del Tesoro (2 Yr, diaria, barra de las 15:30 ET) y de ZN=F contra ^TNX (5 min)."""
    out = {"beta_2y": None, "r2_2y": None, "n_2y": 0, "beta_10y": None, "r2_10y": None, "n_10y": 0}
    try:
        import oro_xau
        tr = {str(f): v.get("2 Yr") for f, v in oro_xau.treasury("nominal", 2).items() if v.get("2 Yr") is not None}
        pts = []
        for d in sorted({dt.datetime.fromtimestamp(s, NY).date() for s in B["zt"]}):
            k = int(dt.datetime(d.year, d.month, d.day, 15, 30, tzinfo=NY).timestamp())
            if k in B["zt"] and d.isoformat() in tr:
                pts.append((B["zt"][k], tr[d.isoformat()]))
        x = [b[0] - a[0] for a, b in zip(pts, pts[1:])]
        y = [(b[1] - a[1]) * 100 for a, b in zip(pts, pts[1:])]
        out["beta_2y"], out["r2_2y"] = _reg(x, y)
        out["n_2y"] = len(x)
    except Exception as e:  # noqa: BLE001
        out["error_2y"] = f"{type(e).__name__}: {str(e)[:80]}"
    ks = sorted(k for k in B["tnx"] if k in B["zn"])
    x = [B["zn"][b] - B["zn"][a] for a, b in zip(ks, ks[1:]) if b - a == 300]
    y = [(B["tnx"][b] - B["tnx"][a]) * 100 for a, b in zip(ks, ks[1:]) if b - a == 300]
    out["beta_10y"], out["r2_10y"] = _reg(x, y)
    out["n_10y"] = len(x)
    return out


# ------------------------------------------------------------------ umbrales y clasificación
def umbrales(prev, fase):
    """prev = filas (dict) de eventos previos. Devuelve ({y2,y10,dxy,nq}, origen)."""
    cols = {"y2": "d_y2_pb", "y10": "d_y10_pb", "dxy": "d_dxy_pct", "nq": "d_nq_pct"}
    th, ns = {}, []
    for k, c in cols.items():
        v = [num(r[c]) for r in prev if r["fase"] == fase and num(r[c]) is not None]
        ns.append(len(v))
        if len(v) >= MIN_N:
            th[k] = max(SUELOS[k], K_UMBRAL * (sum(a * a for a in v) / len(v)) ** 0.5)
        else:
            th[k] = SUELOS[k]
    n = min(ns) if ns else 0
    return th, (f"z-score vs {n} eventos previos (60 d)" if n >= MIN_N else f"fijo (muestra insuficiente: {n} eventos previos < {MIN_N})")


def clasificar(d, th, pico_dxy_pct):
    """d = {y2, y10, dxy, nq} movimientos frente a T-5. Devuelve la clase o None si falta alguna serie necesaria."""
    if any(d.get(k) is None for k in ("y2", "y10", "dxy", "nq")):
        return None
    up = {k: d[k] >= th[k] for k in th}
    dn = {k: d[k] <= -th[k] for k in th}
    if up["y2"] and up["y10"] and up["dxy"]:
        return "FED MÁS DURA"
    if dn["y2"] and dn["y10"] and dn["dxy"]:
        return "FED MÁS SUAVE"
    if dn["y10"] and dn["nq"] and pico_dxy_pct is not None and pico_dxy_pct >= th["dxy"] and d["dxy"] <= 0.5 * pico_dxy_pct:
        return "REFUGIO"
    if up["y10"] and (d["y10"] - d["y2"]) >= th["y10"]:
        return "EMPINAMIENTO POR PLAZO LARGO"
    if all(abs(d[k]) < th[k] for k in th):
        return "SIN REACCIÓN"
    return "MIXTA (sin regla)"


# ------------------------------------------------------------------ medición de un evento
def medir_evento(ev, B, cal, filas_previas, hasta=None, origen_base="reconstruido", ya=()):
    """Filas (dict CAMPOS) para las fases de `ev` ya cumplidas (objetivo + 5 min ≤ hasta) que no estén en `ya`."""
    hasta = hasta or ahora()
    t5 = objetivo(ev, -5)
    base = {k: precio_en(B, k, t5)[0] for k in YAHOO}
    rows = []
    prev = [r for r in filas_previas if r["evento_id"] != ev["id"] and 0 < (ev["fecha"] - dt.date.fromisoformat(r["fecha"])).days <= VENTANA_DIAS]
    for fase, mins in FASES:
        t = objetivo(ev, mins)
        if t + dt.timedelta(minutes=5) > hasta or fase in ya:
            continue
        vals, edades = {}, {}
        for k in YAHOO:
            v, s, e = precio_en(B, k, t)
            vals[k], edades[k] = v, e
        d = {"y2": None, "y10": None, "dxy": None, "oro": None, "nq": None, "es": None, "btc": None}
        fuente10 = ""
        if fase != "T-5":
            if vals["zt"] is not None and base["zt"] is not None and cal.get("beta_2y") is not None:
                d["y2"] = cal["beta_2y"] * (vals["zt"] - base["zt"])
            if vals["tnx"] is not None and base["tnx"] is not None:
                d["y10"], fuente10 = (vals["tnx"] - base["tnx"]) * 100, "^TNX"
            elif vals["zn"] is not None and base["zn"] is not None and cal.get("beta_10y") is not None:
                d["y10"], fuente10 = cal["beta_10y"] * (vals["zn"] - base["zn"]), "ZN=F×beta (^TNX sin barra)"
            for k in ("dxy", "oro", "nq", "es", "btc"):
                if vals[k] is not None and base[k] is not None:
                    d[k] = (vals[k] / base[k] - 1) * 100
        pico = pico_dxy(B, t5, t) if fase != "T-5" else None
        th, origen_umb = umbrales(prev, fase) if fase != "T-5" else ({}, "")
        clase = clasificar(d, th, pico) if fase != "T-5" else ""
        edad_max = max([e for e in edades.values() if e is not None] or [None]) if any(e is not None for e in edades.values()) else None
        barra = max((precio_en(B, k, t)[1] for k in YAHOO if vals[k] is not None), default=None)
        tarde = (hasta - t).total_seconds() / 60
        row = {"evento_id": ev["id"], "tipo": ev["tipo"], "evento": ev["evento"], "fecha": ev["fecha"].isoformat(), "hora_ny": ev["hora_ny"], "fase": fase,
               "objetivo_utc": t.strftime("%Y-%m-%d %H:%M"), "barra_utc": dt.datetime.fromtimestamp(barra, UTC).strftime("%Y-%m-%d %H:%M") if barra else "",
               "edad_min": fnum(edad_max, 1), **{k: fnum(vals[k], 4) for k in YAHOO},
               "d_y2_pb": fnum(d["y2"], 2), "d_y10_pb": fnum(d["y10"], 2), "y10_fuente": fuente10, "d_dxy_pct": fnum(d["dxy"], 3), "d_oro_pct": fnum(d["oro"], 3),
               "d_nq_pct": fnum(d["nq"], 3), "d_es_pct": fnum(d["es"], 3), "d_btc_pct": fnum(d["btc"], 3), "dxy_pico_pct": fnum(pico, 3),
               "clasificacion": clase if clase is not None else "SIN DATO", "umbral_origen": origen_umb,
               "th_y2": fnum(th.get("y2"), 2), "th_y10": fnum(th.get("y10"), 2), "th_dxy": fnum(th.get("dxy"), 3), "th_nq": fnum(th.get("nq"), 3),
               "beta_2y": fnum(cal.get("beta_2y"), 2), "r2_2y": fnum(cal.get("r2_2y"), 3), "beta_10y": fnum(cal.get("beta_10y"), 2), "r2_10y": fnum(cal.get("r2_10y"), 3),
               "real10": "", "d_real10_pb": "", "origen": origen_base if tarde > RETRASO_VIVO_MIN else "vivo",
               "registrado_utc": ahora().strftime("%Y-%m-%d %H:%M"), "fuente": "Yahoo Finance (API v8 chart, 5 min); calendario: " + ev["fuente"]}
        rows.append(row)
        filas_previas = filas_previas + [row]
    return rows


# ------------------------------------------------------------------ 10Y real al día siguiente (FRED DFII10)
def completar_real10(evs, filas):
    nuevas = []
    hoy = ahora().astimezone(NY).date()
    hechas = {r["evento_id"] for r in filas if r["fase"] == "REAL10"}
    try:
        import liquidez_cripto as LQ
        s = LQ.fred("DFII10", (hoy - dt.timedelta(days=VENTANA_DIAS + 15)).isoformat())
    except Exception as e:  # noqa: BLE001
        print("DFII10:", type(e).__name__, str(e)[:80])
        return nuevas
    serie = {d: v for d, v in s}
    for ev in evs:
        if ev["id"] in hechas or ev["fecha"] >= hoy or ev["fecha"] not in serie:
            continue
        ant = max((d for d in serie if d < ev["fecha"]), default=None)
        if ant is None:
            continue
        nuevas.append({k: "" for k in CAMPOS} | {"evento_id": ev["id"], "tipo": ev["tipo"], "evento": ev["evento"], "fecha": ev["fecha"].isoformat(), "hora_ny": ev["hora_ny"],
                       "fase": "REAL10", "real10": serie[ev["fecha"]], "d_real10_pb": round((serie[ev["fecha"]] - serie[ant]) * 100, 1),
                       "clasificacion": "", "origen": "FRED · añadido al día siguiente", "registrado_utc": ahora().strftime("%Y-%m-%d %H:%M"),
                       "fuente": f"FRED DFII10 (cierre del {ev['fecha']} frente al {ant}; es el cambio de TODO el día, no de la ventana del evento)"})
    return nuevas


def guardar(filas):
    return csvlog.anadir(CSV, filas, ("evento_id", "fase"))


# ------------------------------------------------------------------ reconstrucción (siembra)
def reconstruir():
    hoy = ahora().astimezone(NY).date()
    evs = eventos(hoy - dt.timedelta(days=VENTANA_DIAS - 1), hoy)
    B, err = barras("60d")
    cal = calibrar(B)
    existentes = csvlog.leer(CSV)
    nuevas = []
    for ev in evs:
        ya = {r["fase"] for r in existentes + nuevas if r["evento_id"] == ev["id"]}
        if all(f in ya for f, _ in FASES):
            continue
        # los eventos de hoy en curso los registra el job en vivo
        if objetivo(ev, 120) + dt.timedelta(minutes=60) > ahora() and t_evento(ev) - dt.timedelta(hours=3) <= ahora():
            continue
        r = medir_evento(ev, B, cal, existentes + nuevas, ya=ya)
        nuevas += r
    nuevas += completar_real10(evs, existentes + nuevas)
    n = guardar(nuevas)
    return n, err, cal


# ------------------------------------------------------------------ JSON de la página y de contexto.json
def construir_json():
    filas = csvlog.leer(CSV)
    ev = {}
    for r in filas:
        e = ev.setdefault(r["evento_id"], {"id": r["evento_id"], "tipo": r["tipo"], "evento": r["evento"], "fecha": r["fecha"], "hora_ny": r["hora_ny"], "fases": [], "real10": None})
        if r["fase"] == "REAL10":
            e["real10"] = {"valor": num(r["real10"]), "d_pb": num(r["d_real10_pb"]), "nota": r["fuente"], "origen": r["origen"]}
            continue
        e["fases"].append({"fase": r["fase"], "objetivo_utc": r["objetivo_utc"], "barra_utc": r["barra_utc"], "origen": r["origen"], "clasificacion": r["clasificacion"],
                           "d_y2_pb": num(r["d_y2_pb"]), "d_y10_pb": num(r["d_y10_pb"]), "y10_fuente": r["y10_fuente"], "d_dxy_pct": num(r["d_dxy_pct"]),
                           "d_oro_pct": num(r["d_oro_pct"]), "d_nq_pct": num(r["d_nq_pct"]), "d_es_pct": num(r["d_es_pct"]), "d_btc_pct": num(r["d_btc_pct"]),
                           "dxy_pico_pct": num(r["dxy_pico_pct"]), "umbral_origen": r["umbral_origen"],
                           "umbrales": {"y2": num(r["th_y2"]), "y10": num(r["th_y10"]), "dxy": num(r["th_dxy"]), "nq": num(r["th_nq"])},
                           "registrado_utc": r["registrado_utc"], "beta_2y": num(r["beta_2y"]), "r2_2y": num(r["r2_2y"]), "beta_10y": num(r["beta_10y"]), "r2_10y": num(r["r2_10y"])})
        e["fuente"] = r["fuente"]
    orden = {f: i for i, (f, _) in enumerate(FASES)}
    lista = sorted(ev.values(), key=lambda x: (x["fecha"], x["hora_ny"]))
    for e in lista:
        e["fases"].sort(key=lambda f: orden.get(f["fase"], 99))
        cl = {f["fase"]: f["clasificacion"] for f in e["fases"]}
        e["clase_t5"], e["clase_cierre"] = cl.get("T+5") or None, cl.get("CIERRE") or None
        e["reconstruido"] = any(f["origen"] == "reconstruido" for f in e["fases"])
        giros = [f["fase"] for f in e["fases"] if f["fase"] in ("T+60", "T+120") and e["clase_t5"] and f["clasificacion"] not in ("", "SIN DATO", e["clase_t5"])]
        e["giro_en"] = giros
        # sorpresa: salto del 2Y en T+5 frente a eventos del MISMO tipo en los 60 días previos
        f5 = next((f for f in e["fases"] if f["fase"] == "T+5"), None)
        if f5 and f5["d_y2_pb"] is not None:
            f0 = dt.date.fromisoformat(e["fecha"])
            prev = []
            for o in lista:
                if o["tipo"] == e["tipo"] and o["id"] != e["id"] and 0 < (f0 - dt.date.fromisoformat(o["fecha"])).days <= VENTANA_DIAS:
                    p5 = next((f for f in o["fases"] if f["fase"] == "T+5"), None)
                    if p5 and p5["d_y2_pb"] is not None:
                        prev.append(p5["d_y2_pb"])
            if len(prev) >= MIN_N and statistics.pstdev(prev) > 0:
                e["sorpresa"] = {"modo": "z", "z": round((f5["d_y2_pb"] - statistics.fmean(prev)) / statistics.pstdev(prev), 2), "pb": f5["d_y2_pb"], "n": len(prev)}
            else:
                e["sorpresa"] = {"modo": "pb", "pb": f5["d_y2_pb"], "n": len(prev),
                                 "nota": f"sin muestra suficiente: {len(prev)} eventos {e['tipo']} previos en 60 días (mínimo {MIN_N}); se muestra el salto en pb"}
        else:
            e["sorpresa"] = None
    # tabla histórica: qué clasificación en T+5 terminó imponiéndose al cierre
    cerr = [e for e in lista if e["clase_t5"] and e["clase_t5"] != "SIN DATO" and e["clase_cierre"] and e["clase_cierre"] != "SIN DATO"]
    tabla = {}
    for e in cerr:
        t = tabla.setdefault(e["clase_t5"], {"n": 0, "igual_cierre": 0, "cierre": {}, "eventos": []})
        t["n"] += 1
        t["igual_cierre"] += e["clase_t5"] == e["clase_cierre"]
        t["cierre"][e["clase_cierre"]] = t["cierre"].get(e["clase_cierre"], 0) + 1
        t["eventos"].append(e["id"])
    estado = {}
    try:
        estado = json.load(open(ESTADO, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    return {"generado_utc": ahora().strftime("%Y-%m-%d %H:%M UTC"), "version_reglas": VERSION_REGLAS, "ok": True,
            "ultimo": lista[-1]["id"] if lista else None, "eventos": lista[::-1], "tabla_t5_vs_cierre": tabla, "n_eventos": len(lista), "n_con_cierre": len(cerr),
            "avisos_enviados": estado.get("avisados", []),
            "reglas": {"clases": REGLAS, "precedencia": PRECEDENCIA, "suelos": {"2Y (pb)": SUELOS["y2"], "10Y (pb)": SUELOS["y10"], "DXY (%)": SUELOS["dxy"], "NQ (%)": SUELOS["nq"]},
                       "k_umbral": K_UMBRAL, "min_n": MIN_N, "ventana_dias": VENTANA_DIAS,
                       "umbral": f"Umbral de cada serie = máx(suelo, {K_UMBRAL} × RMS de sus movimientos en la misma fase en los eventos de los {VENTANA_DIAS} días previos); "
                                 f"con menos de {MIN_N} eventos previos solo se usa el suelo y se marca «fijo».",
                       "movimiento": "Todos los movimientos son frente al precio de T-5 (5 minutos antes de la publicación).",
                       "giro": "Si la clase en T+60 o T+120 difiere de la de T+5 se envía una alerta (una por evento y fase).",
                       "criterio": "CRITERIO NEXORA: convención fija y publicada, no un modelo ajustado."},
            "series": {"2Y": "ZT=F calibrado contra el 2 Yr del Tesoro (beta y R² en cada fila; 2YY=F descartado: sin barras intradía)",
                       "10Y": "^TNX (solo cotiza hasta las 15:00 ET; después, ZN=F × beta calibrada contra ^TNX, marcado)",
                       "DXY": "DX-Y.NYB", "oro": "GC=F", "NQ": "NQ=F", "ES": "ES=F", "BTC": "BTC-USD", "10Y real": "FRED DFII10, solo el día siguiente"},
            "fuente": "Yahoo Finance (API v8 chart, barras de 5 min, ~15 min de retraso posible) · calendario: FRED Release Calendar (BLS/BEA) y federalreserve.gov · FRED DFII10",
            "memoria": "data/reacciones_eventos.csv (solo se añade)"}


def escribir_json(J):
    os.makedirs(SITE_DATA, exist_ok=True)
    with open(os.path.join(SITE_DATA, "reacciones.json"), "w", encoding="utf-8") as f:
        json.dump(J, f, ensure_ascii=False, indent=1)


def etapa():
    """Para build.py (modo diario): reconstruye lo que falte, añade REAL10 y devuelve el JSON de la página."""
    n, err, cal = reconstruir()
    J = construir_json()
    J["errores"] = err
    J["calibracion"] = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in cal.items()}
    J["filas_nuevas"] = n
    return J


# ------------------------------------------------------------------ modo vivo (job de Actions)
def _estado():
    try:
        return json.load(open(ESTADO, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"avisados": []}


def _guardar_estado(e):
    os.makedirs(csvlog.DATA, exist_ok=True)
    json.dump(e, open(ESTADO, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def aviso_giro(ev, f5, f, cadena):
    import alertas
    import telegram
    est = _estado()
    clave = f"{ev['id']}|{f['fase']}"
    if clave in est["avisados"]:
        return None
    if not telegram.configurado():
        print("Telegram sin configurar: giro no enviado", clave)
        return False
    cal = alertas.leer("calendario.json") or {}
    sig = alertas.vigilar_fed(cal)
    a = {"titulo": "Reacción a evento", "l1": (f"{ev['evento']} ({ev['fecha']}): la interpretación ha cambiado. En T+5 era «{f5}» y en {f['fase']} es «{f['clasificacion']}». "
                                               f"Cadena frente a T-5: {cadena} (Yahoo Finance; 2Y vía ZT=F calibrado)."),
         "l2": f"Lectura inicial: {SENCILLO.get(f5, '—')}. Lectura actual: {SENCILLO.get(f['clasificacion'], '—')} (CRITERIO NEXORA, reglas en la página).",
         "l3": sig, "l4": (f"En los primeros minutos {SENCILLO.get(f5, 'el mercado dio una lectura')}; ahora, {SENCILLO.get(f['clasificacion'], 'otra distinta')}. "
                           "Es una lectura de precios, no una decisión de la Fed.")}
    ok, e = telegram.enviar(alertas.mensaje(a))
    if ok:
        est["avisados"].append(clave)
        _guardar_estado(est)
    else:
        print("Telegram:", e)
    return ok


def _cadena(f):
    def s(x, d, u):
        return "SIN DATO" if x is None else f"{x:+.{d}f} {u}"
    return (f"2Y {s(f['d_y2_pb'], 1, 'pb')} · 10Y {s(f['d_y10_pb'], 1, 'pb')} · DXY {s(f['d_dxy_pct'], 2, '%')} · oro {s(f['d_oro_pct'], 2, '%')} · "
            f"NQ {s(f['d_nq_pct'], 2, '%')} · BTC {s(f['d_btc_pct'], 2, '%')}")


def vivo(max_espera_min=150):
    n0 = ahora()
    hoy = n0.astimezone(NY).date()
    evs = [e for e in eventos(hoy, hoy)]
    pend = [e for e in evs if objetivo(e, 120) + dt.timedelta(minutes=45) > n0 and t_evento(e) - dt.timedelta(minutes=max_espera_min) <= n0]
    print("eventos de hoy:", [e["id"] for e in evs], "· a vigilar:", [e["id"] for e in pend])
    if not pend:
        return 0
    B, err = barras("60d")
    cal = calibrar(B)
    print("calibración:", cal, "errores:", err)
    for ev in pend:
        for fase, mins in FASES:
            filas = csvlog.leer(CSV)
            ya = {r["fase"] for r in filas if r["evento_id"] == ev["id"]}
            if fase in ya:
                continue
            t = objetivo(ev, mins)
            espera = (t + dt.timedelta(seconds=90) - ahora()).total_seconds()
            if espera > 0:
                print(f"{ev['id']} espera {espera / 60:.1f} min hasta {fase}", flush=True)
                time.sleep(espera)
            for intento in range(4):  # Yahoo puede tardar en publicar la barra
                B2, _ = barras("5d")
                if all(B2[k] or B[k] for k in ("zt", "dxy")):
                    for k in YAHOO:
                        if B2.get(k):
                            B[k].update(B2[k])
                v, _, _ = precio_en(B, "zt", t)
                if v is not None or intento == 3:
                    break
                time.sleep(60)
            filas = csvlog.leer(CSV)
            r = medir_evento(ev, B, cal, filas, ya=ya, origen_base="vivo-tardío")
            guardar(r)
            escribir_json(construir_json())
        # giro: T+60 y T+120 frente a T+5
        J = construir_json()
        e = next((x for x in J["eventos"] if x["id"] == ev["id"]), None)
        if e and e["clase_t5"]:
            for f in e["fases"]:
                if f["fase"] in ("T+60", "T+120") and f["clasificacion"] not in ("", "SIN DATO", e["clase_t5"]) and f["origen"] == "vivo":
                    aviso_giro(ev, e["clase_t5"], f, _cadena(f))
    guardar(completar_real10(evs, csvlog.leer(CSV)))
    escribir_json(construir_json())
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vivo", action="store_true")
    ap.add_argument("--reconstruir", action="store_true")
    a = ap.parse_args()
    if a.vivo:
        return vivo()
    n, err, cal = reconstruir()
    J = construir_json()
    J["errores"], J["calibracion"], J["filas_nuevas"] = err, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in cal.items()}, n
    escribir_json(J)
    print("filas nuevas:", n, "· eventos:", J["n_eventos"], "· calibración:", J["calibracion"], "· errores:", err)
    return 0


if __name__ == "__main__":
    sys.exit(main())
