#!/usr/bin/env python3
"""NEXORA · «¿Está consumiendo la gente?» (#/consumo). Sin IA, gratis, SIN DATO si falta algo. Solo lee fuentes públicas y escribe site/data/consumo.json.

Fuentes: Yahoo Finance (cierres diarios de XLY, XLP, RSPD y RSPS), State Street SSGA (posiciones oficiales de XLY, con fecha) y FRED (RRSFS, PCEC96, DSPIC96, PSAVERT, TOTALSL,
UMCSENT como respaldo y, trimestral, DRCCLACBS). El ánimo del consumidor (U. Michigan) usa como fuente PRIMARIA las tablas de la Universidad (sca.isr.umich.edu, ver michigan.py),
porque FRED publica UMCSENT con 1-2 meses de retraso por licencia. Nada se estima: una fuente que falla deja su parte en SIN DATO.

TESIS DE CONSUMO (reglas FIJAS, impresas también en la página; no usan umbrales de otros módulos):
  Capa de MERCADO (ratio de PESO IGUAL RSPD/RSPS): AL ALZA si está sobre su media de 200 sesiones y su pendiente a 3 meses (63 sesiones) es positiva; A LA BAJA si está bajo su
    media de 200 y la pendiente es negativa; MIXTO en cualquier otro caso.
  Capa REAL (ventas minoristas reales RRSFS y consumo real PCEC96): AL ALZA si las dos suben en 3 meses; A LA BAJA si las dos bajan; MIXTO si no coinciden.
  Capa de CAPACIDAD (renta real, ahorro, crédito, morosidad): cada una vota +1 / −1 (renta real DSPIC96 sube en 3 meses; tasa de ahorro PSAVERT ≥ su media de 12 meses; crédito TOTALSL
    interanual positivo; morosidad DRCCLACBS no sube frente al trimestre anterior). Suma ≥ +2 = RESPALDA; ≤ −2 = NO RESPALDA; si no, MIXTA. Una serie sin dato vota 0.
  RESULTADO (mercado, real): (alza, alza) CONSUMO FUERTE · (baja, baja) CONSUMO DÉBIL · (mixto, baja) SE ENFRÍA · (alza, baja) DIVERGENCIA MERCADO ADELANTADO ·
    (baja, alza) DIVERGENCIA MERCADO DEFENSIVO · (alza, mixto) y (mixto, alza) CONSUMO FUERTE con intensidad DÉBIL · (baja, mixto) DIVERGENCIA MERCADO DEFENSIVO con intensidad DÉBIL ·
    (mixto, mixto) SIN TESIS. Intensidad DÉBIL si la regla se cumple solo parcialmente o si la capacidad la contradice (CONSUMO FUERTE con capacidad que NO RESPALDA;
    SE ENFRÍA o CONSUMO DÉBIL con capacidad que RESPALDA).
  Dirección esperada para el marcador (RSPD/RSPS a T+20): CONSUMO FUERTE y DIVERGENCIA MERCADO DEFENSIVO = sube; SE ENFRÍA, CONSUMO DÉBIL y DIVERGENCIA MERCADO ADELANTADO = baja.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import statistics
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(HERE)
sys.path.insert(0, HERE)

PARES = {"cap": ("XLY", "XLP", "XLY/XLP · consumo discrecional / básico (ponderado por capitalización)"),
         "igual": ("RSPD", "RSPS", "RSPD/RSPS · consumo discrecional / básico en peso igual")}
# serie FRED → (nombre, unidad, modo, frecuencia, capa)
SERIES = {
    "RRSFS": ("Ventas minoristas reales", "%", "yoy", "M", "real"), "PCEC96": ("Consumo real (PCE real)", "%", "yoy", "M", "real"),
    "DSPIC96": ("Renta personal disponible real", "%", "yoy", "M", "capacidad"), "PSAVERT": ("Tasa de ahorro personal", "%", "nivel", "M", "capacidad"),
    "TOTALSL": ("Crédito al consumo (total)", "%", "yoy", "M", "capacidad"), "UMCSENT": ("Confianza del consumidor (U. Michigan)", "índice", "nivel", "M", "contexto"),
    "DRCCLACBS": ("Morosidad de tarjetas de crédito (trimestral)", "%", "nivel", "Q", "capacidad"),
}
UMBRAL_CONCENTRACION_PP = 2.0  # aviso simétrico: XLY/XLP y RSPD/RSPS se separan más de 2 pp en 3 meses, en cualquier sentido
PERCENTIL_BAJO = 20.0          # contexto de ánimo: UMCSENT en el 20 % más bajo de su historia desde 1978
ANIMO_DESDE = "1978-01-01"
SESIONES_3M = 63

TEXTOS = {
    "CONSUMO FUERTE": ("el mercado de consumo y los datos reales suben a la vez",
                       "ventas minoristas reales y consumo real siguen subiendo a 3 meses y el ratio de peso igual se mantiene sobre su media de 200 sesiones",
                       "alguna de las dos series reales pasa a la baja en la próxima publicación, o el ratio RSPD/RSPS cae bajo su media de 200"),
    "SE ENFRÍA": ("los datos reales de consumo caen sin que el mercado lo haya descontado todavía",
                  "otra publicación con ventas reales y consumo real a la baja, o la renta real y el ahorro dejan de respaldar el gasto",
                  "las dos series reales vuelven a subir a 3 meses"),
    "CONSUMO DÉBIL": ("mercado y datos reales apuntan a la baja",
                      "el consumo real sigue cayendo y el ratio de peso igual no recupera su media de 200 sesiones",
                      "el ratio recupera su media de 200 con pendiente positiva y los datos reales dejan de caer"),
    "DIVERGENCIA MERCADO ADELANTADO": ("el mercado de consumo sube pero los datos reales caen: el mercado descuenta algo que los datos todavía no muestran",
                                       "los datos reales giran al alza en las próximas publicaciones (el mercado tenía razón)",
                                       "el ratio de peso igual cae bajo su media de 200 sesiones (la divergencia se cierra por la baja)"),
    "DIVERGENCIA MERCADO DEFENSIVO": ("el mercado de consumo cae pero los datos reales aguantan: el mercado descuenta un deterioro que los datos todavía no muestran",
                                      "el ratio de peso igual recupera su media de 200 sesiones con los datos reales firmes (el mercado se equivocaba)",
                                      "los datos reales giran a la baja en las próximas publicaciones (el mercado tenía razón)"),
    "SIN TESIS": ("mercado y datos reales no coinciden en ninguna dirección", "que mercado y datos reales apunten en la misma dirección", "—"),
}
DIRECCION = {"CONSUMO FUERTE": "ALCISTA", "DIVERGENCIA MERCADO DEFENSIVO": "ALCISTA", "SE ENFRÍA": "BAJISTA", "CONSUMO DÉBIL": "BAJISTA", "DIVERGENCIA MERCADO ADELANTADO": "BAJISTA"}
MATRIZ = {  # (mercado, real) → (resultado, cumple_completo)
    ("ALZA", "ALZA"): ("CONSUMO FUERTE", True), ("ALZA", "MIXTO"): ("CONSUMO FUERTE", False), ("MIXTO", "ALZA"): ("CONSUMO FUERTE", False),
    ("ALZA", "BAJA"): ("DIVERGENCIA MERCADO ADELANTADO", True), ("MIXTO", "BAJA"): ("SE ENFRÍA", True), ("BAJA", "BAJA"): ("CONSUMO DÉBIL", True),
    ("BAJA", "ALZA"): ("DIVERGENCIA MERCADO DEFENSIVO", True), ("BAJA", "MIXTO"): ("DIVERGENCIA MERCADO DEFENSIVO", False), ("MIXTO", "MIXTO"): ("SIN TESIS", True),
}


# ---------------------------------------------------------------- descargas (inyectables en pruebas)
def yahoo(sym, rango="3y", tries=3):
    q = sym.replace("^", "%5E")
    ultimo = None
    for k in range(tries):
        for host in ("query2", "query1"):
            try:
                req = urllib.request.Request(f"https://{host}.finance.yahoo.com/v8/finance/chart/{q}?range={rango}&interval=1d", headers={"User-Agent": "Mozilla/5.0"})
                r = json.loads(urllib.request.urlopen(req, timeout=40).read())["chart"]["result"][0]
                pts = [(dt.datetime.fromtimestamp(t, dt.timezone.utc).date(), float(c)) for t, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]) if c is not None]
                if len(pts) < 250:
                    raise RuntimeError("serie demasiado corta")
                return pts
            except Exception as e:  # noqa: BLE001
                ultimo = e
        time.sleep(2 * (k + 1))
    raise RuntimeError(f"Yahoo sin datos de {sym} ({type(ultimo).__name__})")


def fred(sid, desde):
    from liquidez_cripto import fred as _f
    return _f(sid, desde)


def ssga(tk):
    import indices
    return indices.ssga_pesos(tk, top=100)


# ---------------------------------------------------------------- cálculo
def sma(valores, n):
    return [statistics.mean(valores[i - n + 1:i + 1]) if i >= n - 1 else None for i in range(len(valores))]


def ratio(a, b):
    db = dict(b)
    return [(d, v / db[d]) for d, v in a if d in db and db[d]]


def grafico(r, años=2):
    """2 años de ratio con medias de 50 y 200 sesiones (calculadas sobre TODO el historial descargado, no solo sobre los 2 años)."""
    v = [x[1] for x in r]
    s50, s200 = sma(v, 50), sma(v, 200)
    corte = (r[-1][0] - dt.timedelta(days=365 * años)).isoformat()
    f = lambda xs: [[d.isoformat(), round(x, 5)] for (d, _), x in zip(r, xs) if x is not None and d.isoformat() >= corte]  # noqa: E731
    return {"ratio": f(v), "sma50": f(s50), "sma200": f(s200)}


def metricas_ratio(r):
    """Último valor, distancia a la media de 200 y pendiente a 3 meses (63 sesiones) de un ratio."""
    if len(r) < 200 + SESIONES_3M:
        return None
    v = [x[1] for x in r]
    m200 = statistics.mean(v[-200:])
    pend = (v[-1] / v[-1 - SESIONES_3M] - 1) * 100
    return {"fecha": r[-1][0].isoformat(), "ratio": round(v[-1], 5), "sma200": round(m200, 5), "dist_sma200_pct": round((v[-1] / m200 - 1) * 100, 2), "pendiente_3m_pct": round(pend, 2),
            "sobre_sma200": v[-1] > m200}


def estado_mercado(m):
    if not m:
        return "SIN DATO"
    if m["sobre_sma200"] and m["pendiente_3m_pct"] > 0:
        return "ALZA"
    if not m["sobre_sma200"] and m["pendiente_3m_pct"] < 0:
        return "BAJA"
    return "MIXTO"


def _hace(s, meses):
    """Valor de la serie `meses` meses antes de su último dato (por fecha, sin interpolar); None si no existe ese mes."""
    d = s[-1][0]
    y, m = d.year, d.month - meses
    while m < 1:
        m += 12
        y -= 1
    return next((v for f, v in s if f.year == y and f.month == m), None)


def metrica_fred(sid, s):
    nombre, unidad, modo, freq, capa = SERIES[sid]
    if not s:
        return {"serie": sid, "nombre": nombre, "capa": capa, "sin_dato": True}
    d, v = s[-1]
    h3 = _hace(s, 3)
    out = {"serie": sid, "nombre": nombre, "capa": capa, "unidad": unidad, "modo": modo, "frecuencia": freq, "periodo": d.isoformat(), "nivel": round(v, 4)}
    if modo == "yoy":
        h12 = _hace(s, 12)
        out["valor"] = round((v / h12 - 1) * 100, 2) if h12 else None                 # % interanual
        out["tendencia_3m"] = round((v / h3 - 1) * 100, 2) if h3 else None             # % frente a hace 3 meses
        out["tendencia_unidad"] = "%"
    else:
        out["valor"] = round(v, 2)
        out["tendencia_3m"] = round(v - h3, 2) if h3 is not None else None             # puntos frente a hace 3 meses (trimestral: frente al trimestre anterior)
        out["tendencia_unidad"] = "pp" if unidad == "%" else "pts"
    if sid == "PSAVERT":
        ult12 = [x for f, x in s if f > s[-1][0] - dt.timedelta(days=366)]
        out["media_12m"] = round(statistics.mean(ult12), 2) if len(ult12) >= 6 else None
    return out


def capa_real(m):
    r = [m.get(k) for k in ("RRSFS", "PCEC96")]
    if any(x is None or x.get("sin_dato") or x.get("tendencia_3m") is None for x in r):
        return {"estado": "SIN DATO", "detalle": "falta alguna serie real"}
    t = [x["tendencia_3m"] for x in r]
    est = "ALZA" if all(x > 0 for x in t) else "BAJA" if all(x < 0 for x in t) else "MIXTO"
    return {"estado": est, "detalle": f"ventas reales {t[0]:+.2f} % y consumo real {t[1]:+.2f} % en 3 meses"}


def capa_capacidad(m):
    votos, det = [], []
    def v(sid, cond, txt_si, txt_no):
        x = m.get(sid)
        if x is None or x.get("sin_dato") or cond(x) is None:
            votos.append(0); det.append(f"{sid}: SIN DATO (vota 0)")
            return
        votos.append(1 if cond(x) else -1)
        det.append(f"{sid}: {txt_si if cond(x) else txt_no}")
    v("DSPIC96", lambda x: None if x["tendencia_3m"] is None else x["tendencia_3m"] > 0, "renta real sube (+1)", "renta real no sube (−1)")
    v("PSAVERT", lambda x: None if x.get("media_12m") is None else x["valor"] >= x["media_12m"], "ahorro en o sobre su media de 12 meses (+1)", "ahorro bajo su media de 12 meses (−1)")
    v("TOTALSL", lambda x: None if x["valor"] is None else x["valor"] > 0, "crédito crece interanual (+1)", "crédito no crece (−1)")
    v("DRCCLACBS", lambda x: None if x["tendencia_3m"] is None else x["tendencia_3m"] <= 0, "morosidad no sube (+1)", "morosidad sube (−1)")
    s = sum(votos)
    return {"estado": "RESPALDA" if s >= 2 else "NO RESPALDA" if s <= -2 else "MIXTA", "suma": s, "detalle": " · ".join(det)}


def tesis(mercado, real, capacidad):
    if mercado == "SIN DATO" or real == "SIN DATO":
        return {"resultado": "SIN DATO", "intensidad": None, "direccion_marcador": "NINGUNA", "porque": "falta la capa de " + ("mercado" if mercado == "SIN DATO" else "real") + " (SIN DATO, no se estima)",
                "confirmaria": "—", "invalidaria": "—"}
    res, completo = MATRIZ[(mercado, real)]
    inten = "FUERTE" if completo else "DÉBIL"
    contradice = (res == "CONSUMO FUERTE" and capacidad == "NO RESPALDA") or (res in ("SE ENFRÍA", "CONSUMO DÉBIL") and capacidad == "RESPALDA")
    motivo = []
    if not completo:
        motivo.append("la regla se cumple solo en parte (una capa es MIXTA)")
    if contradice:
        inten = "DÉBIL"
        motivo.append(f"la capacidad {capacidad} contradice el resultado")
    t = TEXTOS[res]
    return {"resultado": res, "intensidad": inten if res != "SIN TESIS" else None, "direccion_marcador": DIRECCION.get(res, "NINGUNA"), "porque": t[0], "confirmaria": t[1], "invalidaria": t[2],
            "motivo_intensidad": "; ".join(motivo) or "cumple la regla completa"}


def concentracion(cap, igual, pesos):
    """Aviso SIMÉTRICO: si XLY/XLP y RSPD/RSPS se separan más de 2 pp en 3 meses (en cualquier sentido), el ratio ponderado lo mueven AMZN+TSLA y no el consumo amplio.
    Indica hacia dónde empujan (al alza si XLY/XLP va por encima de RSPD/RSPS, a la baja si va por debajo). No puntúa en la tesis."""
    out = {"pesos": pesos, "diferencia_3m_pp": None, "aviso": None, "sentido": None, "umbral_pp": UMBRAL_CONCENTRACION_PP}
    if cap and igual:
        d = round(cap["pendiente_3m_pct"] - igual["pendiente_3m_pct"], 2)
        out["diferencia_3m_pp"] = d
        if abs(d) > UMBRAL_CONCENTRACION_PP:
            out["sentido"] = "AL ALZA" if d > 0 else "A LA BAJA"
            out["aviso"] = ("el ratio lo mueven AMZN+TSLA, no el consumo amplio: empujan XLY/XLP " + ("al alza" if d > 0 else "a la baja")
                            + f" ({str(f'{d:+.2f}').replace('.', ',')} pp frente a RSPD/RSPS en 3 meses)")
    return out


def animo(serie, real_estado, dato=None):
    """Contexto de ánimo (NO puntúa): percentil histórico de la confianza U. Michigan desde 1978, con el dato MÁS RECIENTE (preliminar incluido). Si está en el 20 % más bajo mientras la capa
    real está al alza → nota. serie = [(fecha, valor)] o [(fecha, valor, tipo)]; dato = estado de michigan.estado() (fuente, tipo, fechas, antigüedad, contraste con FRED)."""
    base = {"serie": "UMCSENT", "nombre": "Confianza del consumidor (U. Michigan)", "puntua": False, "desde": ANIMO_DESDE[:7], "umbral_percentil": PERCENTIL_BAJO, "dato": dato}
    vals = [(x[0], x[1]) for x in (serie or []) if x[0].isoformat() >= ANIMO_DESDE]
    if len(vals) < 100:
        return {**base, "estado": "SIN DATO", "nota": None}
    d, v = vals[-1]
    pct = round(sum(1 for _, x in vals if x <= v) / len(vals) * 100, 1)
    zona_baja = pct <= PERCENTIL_BAJO
    return {**base, "estado": "OK", "periodo": d.isoformat(), "tipo": (serie[-1][2] if len(serie[-1]) > 2 else "final"), "valor": round(v, 1), "percentil": pct, "n": len(vals), "minimo": round(min(x for _, x in vals), 1), "maximo": round(max(x for _, x in vals), 1),
            "zona_baja": zona_baja, "nota": "la gente dice que está mal pero sigue gastando" if zona_baja and real_estado == "ALZA" else None}


def peso_amzn_tsla(w):
    pos = {p["ticker"]: p["peso"] for p in w.get("principales", [])}
    if "AMZN" not in pos or "TSLA" not in pos:
        return None
    return {"fecha": w.get("fecha"), "amzn": pos["AMZN"], "tsla": pos["TSLA"], "suma": round(pos["AMZN"] + pos["TSLA"], 2), "fuente": w.get("fuente", "State Street SSGA, posiciones diarias de XLY")}


def michigan_real(raiz, ahora):
    import michigan
    return michigan.actualizar(raiz, ahora)


def construir(fuentes=None, ahora=None, raiz=None):
    """fuentes = {'yahoo': fn, 'fred': fn, 'ssga': fn, 'michigan': fn} (por defecto, las reales). Cada fuente falla por separado."""
    raiz = raiz or RAIZ
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    F = {"yahoo": yahoo, "fred": fred, "ssga": ssga, "michigan": lambda: michigan_real(raiz, ahora), **(fuentes or {})}
    err, precios, graf, met = {}, {}, {}, {}
    for t in {x for a, b, _ in PARES.values() for x in (a, b)}:
        try:
            precios[t] = F["yahoo"](t)
        except Exception as e:  # noqa: BLE001
            err[t] = f"{type(e).__name__}: {str(e)[:100]}"
    for k, (a, b, nombre) in PARES.items():
        if a in precios and b in precios:
            r = ratio(precios[a], precios[b])
            if len(r) >= 200 + SESIONES_3M:
                graf[k] = {"nombre": nombre, **grafico(r)}
                met[k] = {"nombre": nombre, **(metricas_ratio(r) or {})}
                continue
        met[k] = None
    try:
        pesos = peso_amzn_tsla(F["ssga"]("XLY"))
        if not pesos:
            raise RuntimeError("AMZN o TSLA no aparecen en las posiciones")
    except Exception as e:  # noqa: BLE001
        pesos = None
        err["ssga_xly"] = f"{type(e).__name__}: {str(e)[:100]}"
    desde = (ahora.date() - dt.timedelta(days=365 * 3)).isoformat()
    fm = {}
    for sid in SERIES:
        try:
            fm[sid] = metrica_fred(sid, F["fred"](sid, desde))
        except Exception as e:  # noqa: BLE001
            err[sid] = f"{type(e).__name__}: {str(e)[:100]}"
            fm[sid] = metrica_fred(sid, [])
    import michigan
    mi, fr = {"serie": [], "errores": {}}, []
    try:
        mi = F["michigan"]()
        for k, v in (mi.get("errores") or {}).items():
            err["michigan_" + k] = v
    except Exception as e:  # noqa: BLE001
        err["michigan"] = f"{type(e).__name__}: {str(e)[:100]}"
    try:
        fr = F["fred"]("UMCSENT", ANIMO_DESDE)                       # respaldo y segunda fuente
    except Exception as e:  # noqa: BLE001
        err["UMCSENT_historia"] = f"{type(e).__name__}: {str(e)[:100]}"
    # la Universidad manda; FRED solo sustituye si la Universidad no dio ninguna serie (se avisa en el dato)
    am = mi["serie"] or [(d, v, "final") for d, v in fr]
    dato = michigan.estado(raiz, mi["serie"], fr, ahora, {k: v for k, v in err.items() if k.startswith("michigan") or k.startswith("UMCSENT")})
    try:
        if mi["serie"] and fr:
            michigan.cotejar_fred(raiz, mi["serie"], fr, ahora)
    except Exception as e:  # noqa: BLE001
        err["michigan_cotejo"] = f"{type(e).__name__}: {str(e)[:100]}"
    em, er, ec = estado_mercado(met.get("igual")), capa_real(fm), capa_capacidad(fm)
    t = tesis(em, er["estado"], ec["estado"])
    fechas = [x["fecha"] for x in met.values() if x] + [x["periodo"] for x in fm.values() if x.get("periodo")]
    return {"version": 1, "ok": True, "generado_utc": ahora.strftime("%Y-%m-%d %H:%M UTC"), "fecha_datos": max(fechas) if fechas else None,
            "mercado": {"cap": met.get("cap"), "igual": met.get("igual"), **concentracion(met.get("cap"), met.get("igual"), pesos)},
            "graficos": graf, "real": [fm[s] for s in SERIES],
            "capas": {"mercado": {"estado": em, "detalle": (f"RSPD/RSPS {met['igual']['dist_sma200_pct']:+.2f} % frente a su media de 200 y {met['igual']['pendiente_3m_pct']:+.2f} % en 3 meses" if met.get("igual") else "SIN DATO")},
                      "real": er, "capacidad": ec},
            "animo": animo(am, er["estado"], dato), "tesis": t, "reglas_contexto": REGLAS_CONTEXTO, "reglas": [x.strip() for x in __doc__.split("TESIS DE CONSUMO (reglas FIJAS, impresas también en la página; no usan umbrales de otros módulos):")[1].strip().split("\n  ") if x.strip()],
            "errores": err,
            "fuentes": "Yahoo Finance (XLY, XLP, RSPD, RSPS) · State Street SSGA (posiciones de XLY) · FRED (RRSFS, PCEC96, DSPIC96, PSAVERT, TOTALSL, DRCCLACBS; UMCSENT como respaldo) · Universidad de Michigan (sca.isr.umich.edu, ánimo del consumidor)"}


REGLAS_CONTEXTO = [
    f"Aviso de concentración (no puntúa): si XLY/XLP y RSPD/RSPS se separan más de {UMBRAL_CONCENTRACION_PP:g} pp en 3 meses, en cualquier sentido, el ratio lo mueven AMZN+TSLA y no el consumo amplio; "
    "se indica hacia dónde empujan (XLY/XLP por encima de RSPD/RSPS = al alza; por debajo = a la baja).",
    f"Contexto de ánimo (no puntúa): percentil de la confianza U. Michigan (tablas de la Universidad; FRED UMCSENT de respaldo) frente a su historia desde 1978, con el dato más reciente (preliminar o final); si está en el {PERCENTIL_BAJO:g} % más bajo mientras la capa real está al alza, "
    "nota «la gente dice que está mal pero sigue gastando».",
]


def etapa():
    return construir()


def bloque_contexto(raiz=RAIZ):
    try:
        with open(os.path.join(raiz, "site", "data", "consumo.json"), encoding="utf-8") as f:
            J = json.load(f)
    except Exception:  # noqa: BLE001
        return {"estado": "SIN DATO", "fuente": "consumo.py (consumo.json)"}
    m = J["mercado"]
    return {"actualizado_utc": J["generado_utc"], "fecha": J.get("fecha_datos"),
            "tesis": {k: J["tesis"].get(k) for k in ("resultado", "intensidad", "porque", "confirmaria", "invalidaria", "direccion_marcador")},
            "capas": {k: v["estado"] for k, v in J["capas"].items()},
            "mercado": {"RSPD_RSPS": m.get("igual"), "XLY_XLP": m.get("cap"), "diferencia_3m_pp": m.get("diferencia_3m_pp"), "aviso": m.get("aviso"), "sentido_concentracion": m.get("sentido"),
                        "peso_AMZN_TSLA_en_XLY": m.get("pesos")},
            "animo_no_puntua": J.get("animo"),
            "real": [{k: x.get(k) for k in ("serie", "nombre", "periodo", "valor", "unidad", "tendencia_3m", "tendencia_unidad")} for x in J["real"] if not x.get("sin_dato")],
            "sin_dato": [x["serie"] for x in J["real"] if x.get("sin_dato")] + list(J.get("errores", {}).keys()),
            "lectura": ["Reglas fijas e impresas en #/consumo. La tesis es contexto, no una orden de compra o venta.",
                        "Si aparece un aviso de concentración (XLY/XLP y RSPD/RSPS separados más de 2 pp en 3 meses), el ratio lo mueven AMZN+TSLA y no el consumo amplio; indica el sentido.",
                        "El contexto de ánimo (percentil de UMCSENT desde 1978) no puntúa en la tesis.",
                        "Cita siempre las fechas: los datos reales de consumo son mensuales y se publican semanas después del mes."],
            "fuente": J.get("fuentes")}


if __name__ == "__main__":
    J = construir()
    with open(os.path.join(RAIZ, "site", "data", "consumo.json"), "w", encoding="utf-8") as f:
        json.dump(J, f, ensure_ascii=False, indent=1)
    t = J["tesis"]
    print("TESIS:", t["resultado"], t.get("intensidad"), "| capas:", {k: v["estado"] for k, v in J["capas"].items()}, "| errores:", J["errores"] or "ninguno")
