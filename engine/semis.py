"""NEXORA · SEMIS vs SOFTWARE (ratio SMH/IGV) y grandes del Nasdaq. Gratis (Yahoo/Nasdaq.com/Invesco), sin IA.

CRITERIO NEXORA (reglas fijas y documentadas; umbrales no optimizados):
  · Tendencia del ratio R = SMH / IGV: R por encima de su media de 50 y de 200 sesiones = LIDERAZGO SEMIS; por debajo de las dos = LIDERAZGO SOFTWARE;
    en medio = SIN TENDENCIA CLARA.
  · Escenario del día (cierre a cierre, con SMH e IGV):
      DEBILIDAD TECNOLÓGICA  si SMH ≤ −0,5 % y IGV ≤ −0,5 %   (cae toda la tecnología: nada compensa dentro del sector)
      CONFIRMACIÓN           si SMH ≥ +0,5 % y IGV ≥ +0,5 %   (suben las dos mitades: la subida tiene participación amplia)
      ROTACIÓN               si |SMH − IGV| ≥ 1,0 pp           (una mitad lidera y la otra no acompaña: el dinero cambia de sitio dentro de tecnología)
      SIN SEÑAL CLARA        en cualquier otro caso
  · Impacto relativo en NQ, ES y YM: regresión por mínimos cuadrados de la rentabilidad diaria de ^NDX, ^GSPC y ^DJI sobre SMH e IGV
    (últimas 250 sesiones). Es una sensibilidad estadística histórica, no causalidad ni previsión.
Fuentes: Yahoo Finance (respaldo Nasdaq.com), Invesco (pesos de QQQ)."""
from __future__ import annotations

import datetime as dt
import statistics

import fuentes
import precios

MOV = 0.5          # % por mitad para CONFIRMACIÓN / DEBILIDAD
DIF = 1.0          # pp de diferencia para ROTACIÓN
VENTANA = 250
FRED_IDX = {"^NDX": "NASDAQ100", "^GSPC": "SP500", "^DJI": "DJIA"}
INDICES = [("NQ", "Nasdaq-100", "^NDX"), ("ES", "S&P 500", "^GSPC"), ("YM", "Dow Jones", "^DJI")]

GRANDES = [("NVDA", "NVIDIA", "Semis"), ("AAPL", "Apple", "Hardware"), ("MSFT", "Microsoft", "Software"), ("AMZN", "Amazon", "Consumo"),
           ("AVGO", "Broadcom", "Semis"), ("GOOGL", "Alphabet (A)", "Comunicación"), ("META", "Meta", "Comunicación"), ("TSLA", "Tesla", "Consumo"),
           ("NFLX", "Netflix", "Comunicación"), ("COST", "Costco", "Consumo básico"), ("AMD", "AMD", "Semis"), ("PLTR", "Palantir", "Software"),
           ("ADBE", "Adobe", "Software"), ("QCOM", "Qualcomm", "Semis"), ("MU", "Micron", "Semis"), ("AMAT", "Applied Materials", "Semis")]
# clasificación NEXORA de los componentes del Nasdaq-100 (para sumar pesos reales de Invesco)
SEMIS = {"NVDA", "AVGO", "AMD", "QCOM", "TXN", "INTC", "MU", "AMAT", "LRCX", "KLAC", "ADI", "MRVL", "ASML", "ARM", "NXPI", "MCHP", "ON", "MPWR", "GFS", "TER"}
SOFTWARE = {"MSFT", "ADBE", "PLTR", "INTU", "CDNS", "SNPS", "PANW", "CRWD", "WDAY", "ADSK", "FTNT", "DDOG", "TEAM", "ZS", "APP", "TTD", "ROP", "ANSS", "CTSH"}
URL_QQQ = "https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/holdings/fund?idType=ticker&productType=ETF"


def _n(x, d=2, signo=False):
    """Número con coma decimal (es-ES) para los textos deterministas."""
    t = f"{x:+,.{d}f}" if signo else f"{x:,.{d}f}"
    return t.replace(",", "§").replace(".", ",").replace("§", ".")


def _sma(v, n):
    return sum(v[-n:]) / n if len(v) >= n else None


def _ret(c):
    return [(c[i] / c[i - 1] - 1) * 100 for i in range(1, len(c))]


def _cierres(sym, rango, clase):
    b, origen = precios.diario(sym, rango, nasdaq_clase=clase)
    precios.pausa()
    return {x["fecha"]: x["c"] for x in b}, origen


def _indice(sym):
    """Cierres del índice: Yahoo; respaldo FRED (con retraso, la fecha va en el dato)."""
    try:
        return _cierres(sym, "2y", None)
    except Exception as e:  # noqa: BLE001
        if sym not in FRED_IDX:
            raise
        import liquidez_cripto as LQ
        s = LQ.fred(FRED_IDX[sym], (dt.date.today() - dt.timedelta(days=800)).isoformat())
        return {d: v for d, v in s}, f"FRED {FRED_IDX[sym]} (respaldo: Yahoo no respondió: {type(e).__name__})"


def _ols2(y, x1, x2):
    """y = a + b1·x1 + b2·x2 (mínimos cuadrados, 2 regresores). Devuelve (b1, b2, r2) o None."""
    n = len(y)
    if n < 60:
        return None
    my, m1, m2 = statistics.fmean(y), statistics.fmean(x1), statistics.fmean(x2)
    a11 = sum((a - m1) ** 2 for a in x1)
    a22 = sum((a - m2) ** 2 for a in x2)
    a12 = sum((a - m1) * (b - m2) for a, b in zip(x1, x2))
    c1 = sum((a - m1) * (b - my) for a, b in zip(x1, y))
    c2 = sum((a - m2) * (b - my) for a, b in zip(x2, y))
    det = a11 * a22 - a12 * a12
    if abs(det) < 1e-12:
        return None
    b1 = (c1 * a22 - c2 * a12) / det
    b2 = (c2 * a11 - c1 * a12) / det
    a0 = my - b1 * m1 - b2 * m2
    sst = sum((v - my) ** 2 for v in y)
    sse = sum((v - (a0 + b1 * p + b2 * q)) ** 2 for v, p, q in zip(y, x1, x2))
    return b1, b2, (1 - sse / sst if sst else 0.0)


def _escenario(smh, igv, ndx):
    d = smh - igv
    if smh <= -MOV and igv <= -MOV:
        et, tono = "DEBILIDAD TECNOLÓGICA", "neg"
        txt = (f"Semis ({_n(smh, 2, True)} %) y software ({_n(igv, 2, True)} %) caen a la vez: no hay compensación dentro del sector. "
               "Hipótesis: venta de la tecnología en bloque (tipos, beneficios o riesgo macro) más que una rotación.")
    elif smh >= MOV and igv >= MOV:
        et, tono = "CONFIRMACIÓN", "pos"
        txt = (f"Semis ({_n(smh, 2, True)} %) y software ({_n(igv, 2, True)} %) suben a la vez: la subida tiene participación amplia en tecnología. "
               f"{'Lideran los semis.' if d > 0.3 else 'Lidera el software.' if d < -0.3 else 'Sin liderazgo marcado.'}")
    elif abs(d) >= DIF:
        et, tono = ("ROTACIÓN HACIA SEMIS" if d > 0 else "ROTACIÓN HACIA SOFTWARE"), "amb"
        txt = (f"SMH {_n(smh, 2, True)} % frente a IGV {_n(igv, 2, True)} % (diferencial {_n(d, 2, True)} pp): "
               f"el dinero se mueve dentro de tecnología hacia {'los semiconductores (hardware / ciclo de inversión)' if d > 0 else 'el software (menos intensivo en capital)'}.")
    else:
        et, tono = "SIN SEÑAL CLARA", "sin"
        txt = f"Semis {_n(smh, 2, True)} % e IGV {_n(igv, 2, True)} %: ni se cumplen los umbrales de confirmación o debilidad ni el diferencial llega a {_n(DIF, 1)} pp."
    return {"etiqueta": et, "tono": tono, "texto": txt, "diferencial_pp": round(d, 2)}


def _pesos_qqq():
    j = fuentes.json_(URL_QQQ, tries=2, timeout=40)
    h = j["holdings"]
    w = {}
    for x in h:
        t = (x.get("ticker") or "").strip()
        p = x.get("percentageOfTotalNetAssets")
        if t and p is not None:
            w[t] = w.get(t, 0.0) + float(p)
    if len(w) < 50:
        raise RuntimeError("holdings de QQQ incompletos")
    s = sum(v for k, v in w.items() if k in SEMIS)
    f = sum(v for k, v in w.items() if k in SOFTWARE)
    return w, {"fecha": j.get("effectiveBusinessDate"), "semis_pct": round(s, 2), "software_pct": round(f, 2), "otros_pct": round(sum(w.values()) - s - f, 2),
               "n_componentes": len(w), "semis": sorted([k for k in w if k in SEMIS], key=lambda k: -w[k]),
               "software": sorted([k for k in w if k in SOFTWARE], key=lambda k: -w[k]),
               "fuente": "Invesco · holdings de QQQ (Nasdaq-100)", "url": "https://www.invesco.com/qqq-etf/en/about.html"}


def medir():
    err = {}
    smh, o1 = _cierres("SMH", "2y", "etf")
    igv, o2 = _cierres("IGV", "2y", "etf")
    com = sorted(set(smh) & set(igv))
    if len(com) < 250:
        raise RuntimeError(f"SMH/IGV: solo {len(com)} sesiones comunes")
    rs = [smh[d] / igv[d] for d in com]
    last = com[-1]

    def pct_chg(k):
        return round((rs[-1] / rs[-1 - k] - 1) * 100, 2) if len(rs) > k else None
    s50, s200 = _sma(rs, 50), _sma(rs, 200)
    serie50 = [[com[i].isoformat(), round(sum(rs[i - 49:i + 1]) / 50, 5)] for i in range(49, len(rs))]
    serie200 = [[com[i].isoformat(), round(sum(rs[i - 199:i + 1]) / 200, 5)] for i in range(199, len(rs))]
    # último cruce de la media de 50 con la de 200
    cruce = None
    dif = [(com[i], sum(rs[i - 49:i + 1]) / 50 - sum(rs[i - 199:i + 1]) / 200) for i in range(199, len(rs))]
    for (d0, a), (d1, b) in zip(dif, dif[1:]):
        if a * b < 0:
            cruce = {"fecha": d1.isoformat(), "tipo": "ALCISTA (media 50 cruza por encima de la 200)" if b > 0 else "BAJISTA (media 50 cruza por debajo de la 200)"}
    if rs[-1] > s50 and rs[-1] > s200:
        tend = "LIDERAZGO SEMIS"
    elif rs[-1] < s50 and rs[-1] < s200:
        tend = "LIDERAZGO SOFTWARE"
    else:
        tend = "SIN TENDENCIA CLARA"
    ratio = {"valor": round(rs[-1], 4), "fecha": last.isoformat(), "sma50": round(s50, 4), "sma200": round(s200, 4),
             "vs_sma50_pct": round((rs[-1] / s50 - 1) * 100, 2), "vs_sma200_pct": round((rs[-1] / s200 - 1) * 100, 2), "tendencia": tend, "cruce_medias": cruce,
             "cambios_pct": {"1m": pct_chg(21), "3m": pct_chg(63), "6m": pct_chg(126), "12m": pct_chg(250)},
             "percentil_1a": round(100 * sum(1 for x in rs[-252:] if x <= rs[-1]) / len(rs[-252:])),
             "serie": [[d.isoformat(), round(v, 5)] for d, v in zip(com, rs)][-520:], "sma50_serie": serie50[-520:], "sma200_serie": serie200[-520:]}

    # hoy y semana
    def mov(c, k=1):
        ds = sorted(c)
        return (c[ds[-1]] / c[ds[-1 - k]] - 1) * 100
    hoy_smh, hoy_igv = mov({d: smh[d] for d in com}), mov({d: igv[d] for d in com})
    sem_smh, sem_igv = mov({d: smh[d] for d in com}, 5), mov({d: igv[d] for d in com}, 5)

    # índices y regresión
    impacto, origenes = {}, {"SMH": o1, "IGV": o2}
    rets_smh = {com[i]: (smh[com[i]] / smh[com[i - 1]] - 1) * 100 for i in range(1, len(com))}
    rets_igv = {com[i]: (igv[com[i]] / igv[com[i - 1]] - 1) * 100 for i in range(1, len(com))}
    ndx_hoy = None
    for clave, nombre, sym in INDICES:
        try:
            c, org = _indice(sym)
            origenes[sym] = org
            ds = sorted(d for d in c if d in smh and d in igv)
            ret = {ds[i]: (c[ds[i]] / c[ds[i - 1]] - 1) * 100 for i in range(1, len(ds))}
            fechas = [d for d in sorted(ret) if d in rets_smh][-VENTANA:]
            y, x1, x2 = [ret[d] for d in fechas], [rets_smh[d] for d in fechas], [rets_igv[d] for d in fechas]
            fit = _ols2(y, x1, x2)
            real = ret.get(fechas[-1]) if fechas else None
            if clave == "NQ":
                ndx_hoy = real
            if not fit:
                raise RuntimeError("regresión no resoluble")
            b1, b2, r2 = fit
            impacto[clave] = {"nombre": nombre, "indice": sym, "fecha": fechas[-1].isoformat(), "beta_semis": round(b1, 3), "beta_software": round(b2, 3), "r2": round(r2, 3),
                              "n": len(fechas), "real_pct": round(real, 2) if real is not None else None,
                              "contrib_semis_pp": round(b1 * rets_smh[fechas[-1]], 2), "contrib_software_pp": round(b2 * rets_igv[fechas[-1]], 2),
                              "explicado_pp": round(b1 * rets_smh[fechas[-1]] + b2 * rets_igv[fechas[-1]], 2),
                              "efecto_diferencial_pp": round((b1 - b2) * 1.0, 3), "fuente": org}
        except Exception as e:  # noqa: BLE001
            err[clave] = f"{type(e).__name__}: {str(e)[:100]}"
    esc = _escenario(hoy_smh, hoy_igv, ndx_hoy)
    esc_sem = _escenario(sem_smh, sem_igv, None)

    # pesos de QQQ y tabla de grandes
    pesos, pesos_info = {}, None
    try:
        pesos, pesos_info = _pesos_qqq()
    except Exception as e:  # noqa: BLE001
        err["Invesco QQQ"] = f"{type(e).__name__}: {str(e)[:100]}"
    qqq = None
    try:
        qqq, _ = _cierres("QQQ", "1y", "etf")
    except Exception as e:  # noqa: BLE001
        err["QQQ"] = f"{type(e).__name__}: {str(e)[:80]}"
    grandes = []
    for sym, nom, sec in GRANDES:
        try:
            c, org = _cierres(sym, "1y", "stocks")
            ds = sorted(c)
            v = [c[d] for d in ds]
            ch = lambda k: round((v[-1] / v[-1 - k] - 1) * 100, 2) if len(v) > k else None  # noqa: E731
            rs21 = None
            if qqq:
                qd = sorted(qqq)
                if len(qd) > 21 and ds[-1] == qd[-1] and len(v) > 21:
                    rs21 = round(ch(21) - (qqq[qd[-1]] / qqq[qd[-22]] - 1) * 100, 2)
            w = pesos.get(sym) if pesos else None
            if sym == "GOOGL" and pesos:
                w = (pesos.get("GOOGL") or 0) or None
            grandes.append({"simbolo": sym, "nombre": nom, "sector": sec, "peso_pct": round(w, 2) if w else None, "precio": round(v[-1], 2), "fecha": ds[-1].isoformat(),
                            "d1_pct": ch(1), "d5_pct": ch(5), "d21_pct": ch(21), "d63_pct": ch(63),
                            "vs_sma50_pct": round((v[-1] / _sma(v, 50) - 1) * 100, 1) if len(v) >= 50 else None,
                            "vs_sma200_pct": round((v[-1] / _sma(v, 200) - 1) * 100, 1) if len(v) >= 200 else None,
                            "rs21_vs_qqq_pp": rs21, "contrib_hoy_pp": round(w * ch(1) / 100, 3) if w and ch(1) is not None else None,
                            "serie": [[d.isoformat(), round(c[d], 2)] for d in ds[-90:]], "fuente": org})
        except Exception as e:  # noqa: BLE001
            err[sym] = f"{type(e).__name__}: {str(e)[:100]}"
            grandes.append({"simbolo": sym, "nombre": nom, "sector": sec, "sin_dato": True})

    # texto «lo esencial»
    cambio = (f"Ratio SMH/IGV {_n(ratio['valor'], 3)} ({last.strftime('%d/%m/%Y')}): {_n(ratio['vs_sma50_pct'], 2, True)} % sobre su media de 50 sesiones y "
              f"{_n(ratio['vs_sma200_pct'], 2, True)} % sobre la de 200 → {tend}. Hoy: SMH {_n(hoy_smh, 2, True)} %, IGV {_n(hoy_igv, 2, True)} % → {esc['etiqueta']}.")
    im = impacto.get("NQ")
    significa = esc["texto"]
    if im and im.get("real_pct") is not None:
        significa += (f" Sensibilidad histórica del Nasdaq-100 (250 sesiones): β semis {_n(im['beta_semis'])}, β software {_n(im['beta_software'])} (R² {_n(im['r2'])}); "
                      f"con los movimientos de hoy los dos ETF explican {_n(im['explicado_pp'], 2, True)} pp de los {_n(im['real_pct'], 2, True)} % del índice.")
    if pesos_info:
        significa += (f" Peso en el Nasdaq-100 (Invesco, {dt.date.fromisoformat(pesos_info['fecha']).strftime('%d/%m/%Y')}): "
                      f"semis {_n(pesos_info['semis_pct'], 1)} % · software {_n(pesos_info['software_pct'], 1)} %.")
    vigilar = ("Cierre diario de SMH e IGV: un diferencial ≥ 1 pp mantenido varios días consolida la rotación; si el ratio recupera su media de 50 sesiones cambia la lectura de tendencia."
               + (f" Último cruce de medias del ratio: {cruce['tipo']} el {dt.date.fromisoformat(cruce['fecha']).strftime('%d/%m/%Y')}." if cruce else ""))
    return {"fecha": last.isoformat(), "ratio": ratio, "hoy": {"smh_pct": round(hoy_smh, 2), "igv_pct": round(hoy_igv, 2), "fecha": last.isoformat(),
                                                           "smh": round(smh[last], 2), "igv": round(igv[last], 2)},
            "semana": {"smh_pct": round(sem_smh, 2), "igv_pct": round(sem_igv, 2), "escenario": esc_sem},
            "escenario": esc, "impacto": impacto, "pesos_ndx": pesos_info, "grandes": grandes,
            "esencial": {"cambio": cambio, "significa": significa, "vigilar": vigilar},
            "reglas": [f"DEBILIDAD TECNOLÓGICA: SMH ≤ −{MOV} % e IGV ≤ −{MOV} % en la sesión.", f"CONFIRMACIÓN: SMH ≥ +{MOV} % e IGV ≥ +{MOV} %.",
                       f"ROTACIÓN: |SMH − IGV| ≥ {DIF} pp (hacia semis si SMH > IGV).", "SIN SEÑAL CLARA: cualquier otro caso.",
                       "Tendencia del ratio: por encima de la media de 50 y de 200 sesiones = liderazgo semis; por debajo de las dos = liderazgo software."],
            "origenes": origenes, "errores": err, "fuente": "Yahoo Finance (SMH, IGV, índices, acciones) · Invesco (pesos QQQ)",
            "url": "https://finance.yahoo.com/quote/SMH", "etiqueta": "CRITERIO NEXORA"}


if __name__ == "__main__":
    import json
    M = medir()
    r = M["ratio"]
    print(r["valor"], r["tendencia"], r["vs_sma50_pct"], r["vs_sma200_pct"], r["cruce_medias"], r["cambios_pct"])
    print(M["hoy"], M["escenario"])
    print(json.dumps(M["impacto"], ensure_ascii=False, indent=1))
    print(M["pesos_ndx"] and {k: v for k, v in M["pesos_ndx"].items() if k not in ("semis", "software")})
    for g in M["grandes"]:
        print(g.get("simbolo"), g.get("peso_pct"), g.get("precio"), g.get("d1_pct"), g.get("d21_pct"), g.get("vs_sma50_pct"), g.get("rs21_vs_qqq_pp"), g.get("sin_dato"))
    print(M["esencial"]); print(M["errores"], M["origenes"])
