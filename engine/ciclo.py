#!/usr/bin/env python3
"""NEXORA · CICLO Y CRÉDITO EE. UU.

Nueve señales encendidas/apagadas + fase del ciclo + probit de la Fed de Nueva York + diferenciales de crédito
(IG, BBB, HY, CCC) + prima de bono en exceso (EBP, Gilchrist-Zakrajšek, Reserva Federal).

Fuentes gratuitas y sin clave: FRED (fredgraph.csv), Reserva Federal de Nueva York (probit), Reserva Federal (EBP).
Umbrales = CRITERIO NEXORA (fijos, publicados en `umbrales` y en la web). No son datos oficiales ni una predicción:
una señal encendida es un hecho medido frente a un umbral; la fase es la cuenta de señales encendidas.
Si una fuente falla la señal queda SIN DATO (no cuenta ni como encendida ni como apagada). Nada se estima.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from liquidez_cripto import fred, get, safe  # noqa: E402

HOY = dt.date.today()
DESDE = (HOY - dt.timedelta(days=365 * 3 + 30)).isoformat()

U = {  # CRITERIO NEXORA
    "curva_10y3m_pb": 0,        # 10Y − 3M < 0 → invertida
    "probit_pct": 30.0,         # probabilidad de recesión a 12 meses ≥ 30 %
    "sahm_pp": 0.5,             # regla de Sahm en tiempo real ≥ 0,5 pp
    "paro_vs_min52_pct": 20.0,  # media 4 sem. de peticiones ≥ 20 % sobre su mínimo de 52 semanas
    "nominas_3m_miles": 50,     # media 3 meses de nóminas < 50 mil
    "indpro_yoy_pct": 0.0,      # producción industrial interanual < 0
    "hy_pb": 450,               # diferencial high yield ≥ 450 pb
    "ebp_pp": 0.5,              # prima de bono en exceso ≥ 0,5 pp
    "nfci": 0.0,                # NFCI > 0 → condiciones más duras que la media
}
FASES = [(1, "EXPANSIÓN", "pos"), (3, "DESACELERACIÓN", "amb"), (5, "RIESGO ALTO", "neg"), (99, "RECESIÓN PROBABLE", "neg")]
CREDITO = [("ig", "Grado de inversión (IG)", "BAMLC0A0CM"), ("bbb", "BBB", "BAMLC0A4CBBB"),
           ("hy", "High yield (HY)", "BAMLH0A0HYM2"), ("ccc", "CCC y inferiores", "BAMLH0A3HYC")]
URL_PROBIT = "https://www.newyorkfed.org/medialibrary/media/research/capital_markets/allmonth.xls"
URL_EBP = "https://www.federalreserve.gov/econres/notes/feds-notes/ebp_csv.csv"


def js(s, n=None):
    s = s[-n:] if n else s
    return [[d.isoformat(), round(v, 4)] for d, v in s]


def cambio(s, dias):
    """Delta absoluto frente al último dato con fecha <= (última − días). None si no hay referencia (no se interpola)."""
    if not s:
        return None
    lim = s[-1][0] - dt.timedelta(days=dias)
    ref = [x for x in s if x[0] <= lim]
    if not ref or (lim - ref[-1][0]).days > dias // 2 + 7:
        return None
    return s[-1][1] - ref[-1][1]


def probit_nyfed():
    """Hoja rec_prob del xls de la NY Fed: último mes con dato de mercado y probabilidad a 12 meses (última fila)."""
    import xlrd
    b = xlrd.open_workbook(file_contents=get(URL_PROBIT, timeout=90))
    sh = b.sheet_by_name("rec_prob")
    filas = []
    for r in range(1, sh.nrows):
        v = sh.row_values(r)
        if isinstance(v[0], float) and isinstance(v[5], float):
            fecha = xlrd.xldate_as_datetime(v[0], b.datemode).date()
            spread = v[4] if isinstance(v[4], float) else None
            filas.append((fecha, v[5] * 100, spread))
    if not filas:
        raise RuntimeError("hoja rec_prob sin probabilidades")
    datos = [f for f in filas if f[2] is not None]
    ult = filas[-1]
    return {"serie": [(f[0], f[1]) for f in filas if f[0] <= datos[-1][0] + dt.timedelta(days=366)][-120:],
            "probabilidad_12m_pct": round(ult[1], 1), "para_mes": ult[0].isoformat()[:7],
            "ultimo_mes_dato": datos[-1][0].isoformat()[:7], "spread_ultimo_pp": round(datos[-1][2], 2)}


def ebp_fed():
    raw = get(URL_EBP, timeout=60).decode()
    s, p = [], []
    for row in csv.DictReader(io.StringIO(raw)):
        try:
            d = dt.date.fromisoformat(row["date"])
            s.append((d, float(row["ebp"])))
            if row.get("est_prob") not in (None, ""):
                p.append((d, float(row["est_prob"]) * 100))
        except (ValueError, KeyError):
            continue
    return s, p


def medir():
    err, S = {}, {}

    def g(k, fn, *a):
        v, e = safe(fn, *a)
        if e:
            err[k] = e
        return v
    for k, sid in (("t10y3m", "T10Y3M"), ("sahm", "SAHMREALTIME"), ("icsa", "ICSA"), ("payems", "PAYEMS"), ("indpro", "INDPRO"),
                   ("nfci", "NFCI"), ("t10y2y", "T10Y2Y"), ("unrate", "UNRATE")):
        S[k] = g(sid, fred, sid, DESDE)
    cred = {}
    for k, nom, sid in CREDITO:
        s = g(sid, fred, sid, DESDE)
        cred[k] = s
    ebp = g("EBP", ebp_fed)
    probit = g("probit_nyfed", probit_nyfed)

    sen = []

    def senal(n, nombre, valor_txt, enc, umbral, fecha, fuente, url, margen=None, unidad=""):
        """enc True/False/None (SIN DATO). margen = distancia que falta para encenderse (negativa si ya la superó), en `unidad`."""
        sen.append({"n": n, "nombre": nombre, "valor": valor_txt, "encendida": enc, "umbral": umbral,
                    "fecha": fecha, "fuente": fuente, "url": url, "estado": "SIN DATO" if enc is None else ("ENCENDIDA" if enc else "APAGADA"),
                    "margen": None if margen is None else round(margen, 2), "unidad": unidad})

    s = S["t10y3m"]
    senal(1, "Curva 10 años − 3 meses invertida", f"{s[-1][1] * 100:+.0f} pb" if s else None, (s[-1][1] < 0) if s else None,
          "< 0 pb", s[-1][0].isoformat() if s else None, "FRED T10Y3M", "https://fred.stlouisfed.org/series/T10Y3M", s[-1][1] * 100 if s else None, "pb")
    senal(2, "Probit de recesión (NY Fed) a 12 meses", f"{probit['probabilidad_12m_pct']:.1f} % (para {probit['para_mes']})" if probit else None,
          (probit["probabilidad_12m_pct"] >= U["probit_pct"]) if probit else None, f"≥ {U['probit_pct']:.0f} %",
          probit["ultimo_mes_dato"] + " (último mes con diferencial)" if probit else None, "Fed de Nueva York, modelo probit", "https://www.newyorkfed.org/research/capital_markets/ycfaq",
          (U["probit_pct"] - probit["probabilidad_12m_pct"]) if probit else None, "pp")
    s = S["sahm"]
    senal(3, "Regla de Sahm (tiempo real)", f"{s[-1][1]:.2f} pp" if s else None, (s[-1][1] >= U["sahm_pp"]) if s else None,
          f"≥ {U['sahm_pp']} pp", s[-1][0].isoformat() if s else None, "FRED SAHMREALTIME", "https://fred.stlouisfed.org/series/SAHMREALTIME",
          (U["sahm_pp"] - s[-1][1]) if s else None, "pp")
    s = S["icsa"]
    if s and len(s) > 60:
        m4 = [(s[i][0], sum(x[1] for x in s[i - 3:i + 1]) / 4) for i in range(3, len(s))]
        ult = m4[-1]
        mn = min(v for d, v in m4 if d > ult[0] - dt.timedelta(days=364))
        pct = (ult[1] / mn - 1) * 100
        senal(4, "Peticiones de paro: media 4 sem. sobre su mínimo anual", f"{pct:+.1f} % ({ult[1] / 1000:,.0f} mil)", pct >= U["paro_vs_min52_pct"],
              f"≥ +{U['paro_vs_min52_pct']:.0f} %", ult[0].isoformat(), "FRED ICSA", "https://fred.stlouisfed.org/series/ICSA", U["paro_vs_min52_pct"] - pct, "pp")
    else:
        senal(4, "Peticiones de paro: media 4 sem. sobre su mínimo anual", None, None, f"≥ +{U['paro_vs_min52_pct']:.0f} %", None, "FRED ICSA", "https://fred.stlouisfed.org/series/ICSA")
    s = S["payems"]
    if s and len(s) > 4:
        m3 = (s[-1][1] - s[-4][1]) / 3
        senal(5, "Nóminas no agrícolas: media 3 meses", f"{m3:+.0f} mil", m3 < U["nominas_3m_miles"], f"< {U['nominas_3m_miles']} mil",
              s[-1][0].isoformat(), "FRED PAYEMS", "https://fred.stlouisfed.org/series/PAYEMS", m3 - U["nominas_3m_miles"], "mil")
    else:
        senal(5, "Nóminas no agrícolas: media 3 meses", None, None, f"< {U['nominas_3m_miles']} mil", None, "FRED PAYEMS", "https://fred.stlouisfed.org/series/PAYEMS")
    s = S["indpro"]
    if s and len(s) > 13:
        yo = (s[-1][1] / s[-13][1] - 1) * 100
        senal(6, "Producción industrial interanual", f"{yo:+.1f} %", yo < U["indpro_yoy_pct"], "< 0 %", s[-1][0].isoformat(), "FRED INDPRO", "https://fred.stlouisfed.org/series/INDPRO", yo, "pp")
    else:
        senal(6, "Producción industrial interanual", None, None, "< 0 %", None, "FRED INDPRO", "https://fred.stlouisfed.org/series/INDPRO")
    s = cred["hy"]
    senal(7, "Diferencial high yield", f"{s[-1][1] * 100:.0f} pb" if s else None, (s[-1][1] * 100 >= U["hy_pb"]) if s else None, f"≥ {U['hy_pb']} pb",
          s[-1][0].isoformat() if s else None, "FRED BAMLH0A0HYM2 (ICE BofA)", "https://fred.stlouisfed.org/series/BAMLH0A0HYM2", (U["hy_pb"] - s[-1][1] * 100) if s else None, "pb")
    e = ebp[0] if ebp else None
    senal(8, "Prima de bono en exceso (EBP)", f"{e[-1][1]:+.2f} pp" if e else None, (e[-1][1] >= U["ebp_pp"]) if e else None, f"≥ {U['ebp_pp']} pp",
          e[-1][0].isoformat()[:7] if e else None, "Reserva Federal (Gilchrist-Zakrajšek)", "https://www.federalreserve.gov/econres/notes/feds-notes/ebp_csv.csv", (U["ebp_pp"] - e[-1][1]) if e else None, "pp")
    s = S["nfci"]
    senal(9, "Condiciones financieras (NFCI) más duras que la media", f"{s[-1][1]:+.2f}" if s else None, (s[-1][1] > U["nfci"]) if s else None, "> 0",
          s[-1][0].isoformat() if s else None, "FRED NFCI (Fed de Chicago)", "https://fred.stlouisfed.org/series/NFCI", (U["nfci"] - s[-1][1]) if s else None, "")

    validas = [x for x in sen if x["encendida"] is not None]
    n_enc = sum(1 for x in validas if x["encendida"])
    fase, tono = next((f, t) for lim, f, t in FASES if n_enc <= lim)
    credito = {}
    for k, nom, sid in CREDITO:
        s = cred[k]
        if not s:
            credito[k] = {"nombre": nom, "serie_id": sid, "sin_dato": True, "fuente": f"FRED {sid}"}
            continue
        sp = [(d, v * 100) for d, v in s]
        credito[k] = {"nombre": nom, "serie_id": sid, "valor_pb": round(sp[-1][1], 0), "fecha": sp[-1][0].isoformat(),
                      "d5_pb": cambio(sp, 7), "d1m_pb": cambio(sp, 30), "d3m_pb": cambio(sp, 91),
                      "fuente": f"FRED {sid} (ICE BofA)", "url": f"https://fred.stlouisfed.org/series/{sid}", "serie": js(sp, 520)}
    return {
        "fase": fase, "tono": tono, "encendidas": n_enc, "validas": len(validas), "total": len(sen), "senales": sen, "umbrales": U,
        "probit": {**{k: v for k, v in probit.items() if k != "serie"}, "serie": js(probit["serie"])} if probit else None,
        "ebp": {"serie": js(ebp[0], 240), "prob_estimada": js(ebp[1], 240), "ultimo": js(ebp[0], 1)[0] if ebp[0] else None,
                "fuente": "Reserva Federal · Gilchrist-Zakrajšek (EBP)", "url": URL_EBP} if ebp else None,
        "credito": credito,
        "curva": {"t10y3m": js(S["t10y3m"] or [], 780), "t10y2y": js(S["t10y2y"] or [], 780)},
        "paro": js(S["unrate"] or [], 120), "sahm": js(S["sahm"] or [], 120), "nfci": js(S["nfci"] or [], 520),
        "errores": err,
    }


if __name__ == "__main__":
    import json
    M = medir()
    print(M["fase"], M["encendidas"], "/", M["validas"])
    for s_ in M["senales"]:
        print(s_["n"], s_["estado"], s_["nombre"], s_["valor"], s_["fecha"])
    print(M["errores"])
    print(json.dumps({k: {x: y for x, y in v.items() if x != "serie"} for k, v in M["credito"].items()}, ensure_ascii=False, indent=1)[:1500])
