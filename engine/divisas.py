"""NEXORA · sesgo macro de divisas (USD, EUR, JPY, GBP, CHF, CAD, AUD, NZD). Solo fuentes gratuitas y oficiales.

Seis factores, cada uno con una regla fija y documentada. Cada celda vale +1 (favorable), 0 o −1 (desfavorable) y el sesgo es
la suma. Es una lectura de fortaleza macro RELATIVA, no una recomendación de compra o venta, y no se estima ningún dato:
si una fuente falla, la celda queda SIN DATO y no puntúa.

  1. Tipo oficial          nivel del tipo de política (BIS; yen desde la web del Banco de Japón). Top-3 de las 8 → +1, bottom-3 → −1.
  2. Tipo real             tipo oficial − inflación del año (FMI WEO). Mismo reparto por posiciones.
  3. Bono a 10 años        diferencial del 10Y frente al 10Y de EE. UU. (Tesoro/FRED, BCE, OCDE vía FRED). Mismo reparto.
  4. Crecimiento           PIB real del año, previsión del FMI WEO. Mismo reparto.
  5. Giro del banco central  variación del tipo oficial en 6 meses: ≥ +0,20 pp → +1; ≤ −0,20 pp → −1; si no, 0.
  6. Riesgo                VIX ≥ 22 (aversión): USD/JPY/CHF +1, AUD/NZD/CAD −1; VIX ≤ 16 (apetito): al revés; entre medias 0. EUR y GBP 0.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os

import fuentes
import liquidez_cripto as LQ

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_DATA = os.path.join(ROOT, "site", "data")

# clave, nombre, banco, BIS, IMF, serie FRED 10Y OCDE, (serie FX FRED, USD por divisa?)
MONEDAS = [
    ("USD", "Dólar de EE. UU.", "Fed", "US", "USA", None, None),
    ("EUR", "Euro", "BCE", "XM", "EURO", None, ("DEXUSEU", True)),
    ("JPY", "Yen japonés", "Banco de Japón", "JP", "JPN", "IRLTLT01JPM156N", ("DEXJPUS", False)),
    ("GBP", "Libra esterlina", "Banco de Inglaterra", "GB", "GBR", "IRLTLT01GBM156N", ("DEXUSUK", True)),
    ("CHF", "Franco suizo", "Banco Nacional Suizo", "CH", "CHE", "IRLTLT01CHM156N", ("DEXSZUS", False)),
    ("CAD", "Dólar canadiense", "Banco de Canadá", "CA", "CAN", "IRLTLT01CAM156N", ("DEXCAUS", False)),
    ("AUD", "Dólar australiano", "Banco de la Reserva de Australia", "AU", "AUS", "IRLTLT01AUM156N", ("DEXUSAL", True)),
    ("NZD", "Dólar neozelandés", "Banco de la Reserva de Nueva Zelanda", "NZ", "NZL", "IRLTLT01NZM156N", ("DEXUSNZ", True)),
]
PERFIL = {"USD": 1, "JPY": 1, "CHF": 1, "AUD": -1, "NZD": -1, "CAD": -1, "EUR": 0, "GBP": 0}  # +1 refugio, −1 pro-cíclica
URL_BIS = "https://data.bis.org/topics/CBPOL"
URL_IMF = "https://www.imf.org/external/datamapper/NGDP_RPCH@WEO"
FACTORES = [("tipo", "Tipo oficial"), ("real", "Tipo real"), ("bono", "Bono 10Y vs EE. UU."), ("crec", "Crecimiento"), ("giro", "Giro del banco central"), ("riesgo", "Riesgo (VIX)")]


def _leer_precios():
    try:
        with open(os.path.join(SITE_DATA, "precios.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def _bis(areas, dias=250):
    """{área: [(fecha, valor)]} tipos de política diarios del BIS (por defecto los últimos ~8 meses)."""
    desde = (dt.date.today() - dt.timedelta(days=dias)).isoformat()
    t = fuentes.texto(f"https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/D.{'+'.join(areas)}?startPeriod={desde}&format=csv", timeout=90)
    out = {}
    for r in csv.DictReader(io.StringIO(t)):
        try:
            v = float(r["OBS_VALUE"])
            if v != v:  # «NaN» de fines de semana y festivos: no es dato
                continue
            out.setdefault(r["REF_AREA"], []).append((dt.date.fromisoformat(r["TIME_PERIOD"]), v))
        except ValueError:
            continue
    return {k: sorted(v) for k, v in out.items()}


def _imf(ind):
    j = fuentes.json_(f"https://www.imf.org/external/datamapper/api/v1/{ind}", ua="python-requests/2.31", timeout=90)
    return j["values"][ind]


def _mes(s, d):
    """Media del mes de `d` en la serie diaria s."""
    v = [x for f, x in s if (f.year, f.month) == (d.year, d.month)]
    return sum(v) / len(v) if v else None


def _puntos_por_posicion(vals):
    """vals {clave: valor|None} → {clave: +1/0/−1}: 3 mejores +1, 3 peores −1. Los None no puntúan."""
    ok = sorted([(v, k) for k, v in vals.items() if v is not None], key=lambda x: (-x[0], x[1]))
    n = len(ok)
    out = {k: None for k in vals}
    for i, (_, k) in enumerate(ok):
        out[k] = 1 if i < 3 and n >= 6 else -1 if i >= n - 3 and n >= 6 else 0
    return out


def medir():
    hoy = dt.date.today()
    err = {}
    celdas = {m[0]: {} for m in MONEDAS}

    # 1 · tipo oficial (BIS) + yen desde la web del BoJ
    try:
        bis = _bis([m[3] for m in MONEDAS])
    except Exception as e:  # noqa: BLE001
        bis, err["BIS"] = {}, f"{type(e).__name__}: {e}"
    boj_web = None
    try:
        import boj
        boj_web = boj.tipo_oficial()
    except Exception as e:  # noqa: BLE001
        err["Banco de Japón (web)"] = f"{type(e).__name__}: {e}"
    tipo, giro, fecha_tipo, fuente_tipo = {}, {}, {}, {}
    for k, nom, banco, b, imf, fred10, fx in MONEDAS:
        s = bis.get(b)
        if s:
            v, f = s[-1][1], s[-1][0]
            ref = [x for x in s if x[0] <= f - dt.timedelta(days=183)]
            tipo[k], fecha_tipo[k], fuente_tipo[k] = v, f.isoformat(), "BIS · tipos de política (WS_CBPOL)"
            giro[k] = round(v - ref[-1][1], 3) if ref else None
        else:
            tipo[k] = giro[k] = None
    if boj_web:  # el dato oficial del BoJ manda sobre el del BIS
        if "JPY" in giro and giro["JPY"] is not None and tipo.get("JPY") is not None:
            giro["JPY"] = round(boj_web["valor"] - (tipo["JPY"] - giro["JPY"]), 3)
        tipo["JPY"], fecha_tipo["JPY"], fuente_tipo["JPY"] = boj_web["valor"], boj_web["fecha"] or "", boj_web["fuente"]
        if bis.get("JP") and abs(bis["JP"][-1][1] - boj_web["valor"]) > 1e-9:
            err["aviso yen"] = f"BIS marca {bis['JP'][-1][1]} y la web del BoJ {boj_web['valor']}: se usa la del BoJ"

    # inflación y crecimiento (FMI WEO, año en curso)
    infl, crec, anio = {}, {}, str(hoy.year)
    try:
        pi, pg = _imf("PCPIPCH"), _imf("NGDP_RPCH")
        for k, nom, banco, b, imf, *_ in MONEDAS:
            infl[k] = (pi.get(imf) or {}).get(anio)
            crec[k] = (pg.get(imf) or {}).get(anio)
    except Exception as e:  # noqa: BLE001
        err["FMI WEO"] = f"{type(e).__name__}: {e}"
    real = {k: (round(tipo[k] - infl[k], 2) if tipo.get(k) is not None and infl.get(k) is not None else None) for k in tipo}

    # bono 10Y y diferencial frente a EE. UU.
    rend, fecha_rend, fuente_rend = {}, {}, {}
    try:
        us = LQ.fred("DGS10", (hoy - dt.timedelta(days=200)).isoformat())
        rend["USD"], fecha_rend["USD"], fuente_rend["USD"] = us[-1][1], us[-1][0].isoformat(), "Tesoro de EE. UU. vía FRED DGS10"
    except Exception as e:  # noqa: BLE001
        us = []
        err["DGS10"] = f"{type(e).__name__}: {e}"
    dif = {"USD": 0.0 if us else None}
    try:
        t = fuentes.texto("https://data-api.ecb.europa.eu/service/data/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y?lastNObservations=3&format=csvdata")
        fila = list(csv.DictReader(io.StringIO(t)))[-1]
        f = dt.date.fromisoformat(fila["TIME_PERIOD"])
        rend["EUR"], fecha_rend["EUR"], fuente_rend["EUR"] = float(fila["OBS_VALUE"]), f.isoformat(), "BCE · curva AAA de la zona euro (10Y)"
        ref = LQ.at_or_before(us, f) if us else None
        dif["EUR"] = round(rend["EUR"] - ref[1], 3) if ref else None
    except Exception as e:  # noqa: BLE001
        dif["EUR"] = None
        err["BCE 10Y"] = f"{type(e).__name__}: {e}"
    for k, nom, banco, b, imf, fred10, fx in MONEDAS:
        if not fred10:
            continue
        try:
            s = LQ.fred(fred10, (hoy - dt.timedelta(days=200)).isoformat())
            f, v = s[-1]
            if (hoy - f).days > 75:
                raise RuntimeError(f"última observación {f}: demasiado antigua")
            rend[k], fecha_rend[k], fuente_rend[k] = v, f.isoformat(), f"OCDE vía FRED {fred10} (mensual)"
            ref = _mes(us, f) if us else None
            dif[k] = round(v - ref, 3) if ref is not None else None
        except Exception as e:  # noqa: BLE001
            dif[k] = None
            err[fred10] = f"{type(e).__name__}: {e}"

    # variación 3 meses frente al USD (informativa, no puntúa)
    fx3 = {}
    P = _leer_precios()
    dxy = ((P.get("activos") or {}).get("dxy") or {}).get("serie") or []
    if dxy:
        ult = dxy[-1]
        ref = [x for x in dxy if x[0] <= (dt.date.fromisoformat(ult[0]) - dt.timedelta(days=91)).isoformat()]
        fx3["USD"] = round((ult[1] / ref[-1][1] - 1) * 100, 2) if ref else None
    for k, nom, banco, b, imf, fred10, fx in MONEDAS:
        if not fx:
            continue
        try:
            s = LQ.fred(fx[0], (hoy - dt.timedelta(days=140)).isoformat())
            f, v = s[-1]
            ref = LQ.at_or_before(s, f - dt.timedelta(days=91))
            if ref:
                a, b0 = (v, ref[1]) if fx[1] else (1 / v, 1 / ref[1])
                fx3[k] = round((a / b0 - 1) * 100, 2)
        except Exception as e:  # noqa: BLE001
            err[fx[0]] = f"{type(e).__name__}: {e}"

    # riesgo
    vix = ((P.get("activos") or {}).get("vix") or {})
    vv = vix.get("valor")
    reg = None if vv is None else "AVERSIÓN" if vv >= 22 else "APETITO" if vv <= 16 else "NEUTRAL"
    pts_riesgo = {k: (None if reg is None else (0 if reg == "NEUTRAL" else (PERFIL[k] if reg == "AVERSIÓN" else -PERFIL[k]))) for k in PERFIL}

    pts = {"tipo": _puntos_por_posicion(tipo), "real": _puntos_por_posicion(real), "bono": _puntos_por_posicion(dif), "crec": _puntos_por_posicion(crec),
           "giro": {k: (None if giro.get(k) is None else 1 if giro[k] >= 0.2 else -1 if giro[k] <= -0.2 else 0) for k in tipo}, "riesgo": pts_riesgo}
    valores = {"tipo": tipo, "real": real, "bono": dif, "crec": crec, "giro": giro, "riesgo": {k: vv for k in tipo}}
    fechas = {"tipo": fecha_tipo, "bono": fecha_rend, "crec": {k: f"WEO {anio}" for k in tipo}, "real": {k: f"WEO {anio}" for k in tipo}, "giro": fecha_tipo,
              "riesgo": {k: vix.get("fecha") for k in tipo}}
    fuentes_f = {"tipo": fuente_tipo, "bono": fuente_rend}
    monedas = []
    for k, nom, banco, b, imf, *_ in MONEDAS:
        fac = {}
        for fk, _ in FACTORES:
            fac[fk] = {"valor": valores[fk].get(k), "puntos": pts[fk].get(k), "fecha": (fechas[fk] or {}).get(k), "fuente": (fuentes_f.get(fk) or {}).get(k)}
        usados = [fac[fk]["puntos"] for fk, _ in FACTORES if fac[fk]["puntos"] is not None]
        total = sum(usados)
        monedas.append({"clave": k, "nombre": nom, "banco": banco, "factores": fac, "total": total if usados else None, "n_factores": len(usados),
                        "sesgo": ("SIN DATO" if not usados else "FUERTE" if total >= 3 else "MODERADO" if total >= 1 else "NEUTRAL" if total == 0 else "DÉBIL" if total >= -2 else "MUY DÉBIL"),
                        "fx_3m_pct": fx3.get(k), "inflacion": infl.get(k)})
    monedas.sort(key=lambda m: (m["total"] is None, -(m["total"] or 0), m["clave"]))
    con = [m for m in monedas if m["total"] is not None]
    top, low = (con[0], con[-1]) if con else (None, None)
    esencial = {
        "cambio": (f"Sesgo macro más fuerte: {top['clave']} ({top['total']:+d}); más débil: {low['clave']} ({low['total']:+d}). Riesgo {reg.lower() if reg else 'SIN DATO'}"
                   + (f" (VIX {vv:.1f})." if vv is not None else ".")) if top else "SIN DATO: no se pudo puntuar ninguna divisa.",
        "significa": ("Hecho: la suma de seis factores objetivos coloca a esa divisa arriba y a la otra abajo. Interpretación: la combinación de tipos, crecimiento y giro "
                      "de política respalda a la primera frente a la segunda; no dice que vaya a subir ni a bajar.") if top else "",
        "vigilar": "Próximas reuniones de bancos centrales (calendario), la sorpresa de inflación y el VIX: un VIX por encima de 22 o por debajo de 16 cambia el factor de riesgo de golpe.",
    }
    return {"monedas": monedas, "factores": [{"clave": a, "nombre": b} for a, b in FACTORES], "riesgo": {"vix": vv, "fecha": vix.get("fecha"), "regimen": reg},
            "boj": boj_web, "anio_weo": anio, "esencial": esencial, "errores": err,
            "reglas": [l.strip() for l in __doc__.split("\n") if l.strip()[:2] in ("1 ", "2 ", "3 ", "4 ", "5 ", "6 ")],
            "fuentes": [{"nombre": "BIS · tipos de política", "url": URL_BIS}, {"nombre": "Banco de Japón", "url": "https://www.boj.or.jp/en/"},
                        {"nombre": "FMI · WEO (inflación y PIB)", "url": URL_IMF}, {"nombre": "BCE · curva de tipos", "url": "https://www.ecb.europa.eu/stats/financial_markets_and_interest_rates/euro_area_yield_curves/html/index.en.html"},
                        {"nombre": "FRED (Tesoro, OCDE, tipos de cambio)", "url": "https://fred.stlouisfed.org/"}]}


if __name__ == "__main__":
    r = medir()
    for m in r["monedas"]:
        print(m["clave"], m["total"], m["sesgo"], {k: (v["valor"], v["puntos"]) for k, v in m["factores"].items()}, m["fx_3m_pct"])
    print(r["errores"], r["riesgo"])
