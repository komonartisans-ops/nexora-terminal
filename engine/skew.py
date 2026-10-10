"""NEXORA · RIESGO DE COLA (índice SKEW de Cboe). Todo gratuito: CSV públicos de Cboe, FRED y la OFR. Sin IA.

Qué es: el SKEW mide cuánto más caras están las puts muy fuera de dinero del S&P 500 que las calls equivalentes. Subido = el mercado
paga por cubrirse de una caída fuerte e improbable («cola»). NO predice la fecha ni la magnitud de una caída.

CRITERIO NEXORA (fijo, no optimizado):
  · Zonas: NORMAL < 135 · ELEVADO ≥ 135 · ALTO ≥ 140.
  · Episodio: primer cierre en zona ALTA tras ≥ 10 sesiones sin estarlo (evita contar como entradas distintas las oscilaciones alrededor de 140).
  · Resultado: rentabilidad del S&P 500 a 5, 20 y 60 sesiones (≈ 1, 4 y 12 semanas) y peor caída desde el cierre de entrada dentro de las 60 sesiones.
    FALSA ALARMA = el S&P 500 no llegó a caer un 5 % o más desde el cierre de entrada en esas 60 sesiones.
  · Confirmaciones (de 3): VIX ≥ 20 o curva de volatilidad invertida (VIX/VIX3M ≥ 1) · crédito en TENSIÓN (ciclo.py) ·
    entradas fuertes en fondos monetarios (variación a 13 semanas en el percentil ≥ 80 de su historia desde 2018).
Fuentes: Cboe (SKEW, VIX, VIX3M, SPX), FRED WRMFNS, OFR MMF-MMF_TOT-M, ciclo.json de este mismo terminal."""
from __future__ import annotations

import csv
import datetime as dt
import io
import statistics

import csvlog
import fuentes

CBOE = "https://cdn-api.cboe.com/api/global/us_indices/daily_prices/{}_History.csv"
URL_CBOE = "https://www.cboe.com/us/indices/dashboard/skew/"
Z_ELEVADO, Z_ALTO = 135.0, 140.0
ENFRIAMIENTO = 10            # sesiones (2 semanas) sin zona ALTA para considerar una entrada nueva
HORIZONTES = (5, 20, 60)     # sesiones ≈ 1, 4 y 12 semanas
CAIDA_FALSA = -5.0           # % : por encima de esta caída máxima a 60 sesiones, la entrada se cuenta como falsa alarma
VIX_ESTRES = 20.0
FM_PCT_FUERTE = 80


def _fecha(s):
    m, d, a = s.split("/")
    return dt.date(int(a), int(m), int(d))


def _csv(nombre, col_cierre):
    """[(fecha, cierre)] ordenado y, si el CSV tiene OHLC, también apertura/máximo/mínimo en un dict por fecha."""
    t = fuentes.texto(CBOE.format(nombre), tries=3, timeout=60)
    out = []
    for r in csv.DictReader(io.StringIO(t)):
        try:
            out.append((_fecha(r["DATE"]), float(r[col_cierre])))
        except (KeyError, ValueError):
            continue
    if len(out) < 200:
        raise RuntimeError(f"Cboe {nombre}: serie demasiado corta ({len(out)} filas)")
    out.sort()
    return out


def _n(x, d=1):
    """Número con coma decimal (es-ES) para los textos deterministas."""
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _dmy(iso):
    d = dt.date.fromisoformat(iso) if isinstance(iso, str) else iso
    return d.strftime("%d/%m/%Y")


def zona(v):
    return "ALTO" if v >= Z_ALTO else "ELEVADO" if v >= Z_ELEVADO else "NORMAL"


def _pct(vals, v):
    return round(100 * sum(1 for x in vals if x <= v) / len(vals)) if vals else None


def _med(v):
    return round(statistics.median(v), 2) if v else None


# ---------------------------------------------------------------- estudio histórico propio
def estudio(skew, spx):
    """Qué hizo el S&P 500 tras entrar el SKEW en zona ALTA (incluye las falsas alarmas) frente a la tasa base de cualquier día."""
    fechas = [d for d, _ in spx]
    px = [v for _, v in spx]
    idx = {d: i for i, d in enumerate(fechas)}
    n = len(px)
    vixd = {}
    entradas, ultimo = [], None
    for d, v in skew:
        i = idx.get(d)
        if i is None:
            continue
        if v >= Z_ALTO:
            if ultimo is None or i - ultimo > ENFRIAMIENTO:
                entradas.append((d, i, v))
            ultimo = i
    hmax = max(HORIZONTES)

    def perfil(i):
        r = {}
        for h in HORIZONTES:
            r[h] = round((px[i + h] / px[i] - 1) * 100, 2) if i + h < n else None
        ventana = px[i:i + hmax + 1]
        completo = i + hmax < n
        dd = round((min(ventana) / px[i] - 1) * 100, 2)
        return r, dd, completo

    eps = []
    for d, i, v in entradas:
        r, dd, completo = perfil(i)
        clase = "EN CURSO" if not completo else ("CAÍDA ≥ 5 %" if dd <= CAIDA_FALSA else "FALSA ALARMA")
        eps.append({"fecha": d.isoformat(), "skew": round(v, 2), "spx": round(px[i], 2), "ret": {str(h): r[h] for h in HORIZONTES},
                    "peor_caida_60s": dd, "completo": completo, "clase": clase})
    # tasa base: todos los días con horizonte completo
    base = {}
    for h in HORIZONTES:
        rs = [(px[i + h] / px[i] - 1) * 100 for i in range(n - h)]
        base[str(h)] = {"n": len(rs), "media": round(statistics.fmean(rs), 2), "mediana": _med(rs), "pct_positivos": round(100 * sum(1 for x in rs if x > 0) / len(rs), 1)}
    dds = [(min(px[i:i + hmax + 1]) / px[i] - 1) * 100 for i in range(n - hmax)]
    base["caida_5_60s_pct"] = round(100 * sum(1 for x in dds if x <= CAIDA_FALSA) / len(dds), 1)
    resumen = {}
    comp = [e for e in eps if e["completo"]]
    for h in HORIZONTES:
        rs = [e["ret"][str(h)] for e in eps if e["ret"][str(h)] is not None]
        resumen[str(h)] = ({"n": len(rs), "media": round(statistics.fmean(rs), 2), "mediana": _med(rs), "pct_positivos": round(100 * sum(1 for x in rs if x > 0) / len(rs), 1),
                            "peor": min(rs), "mejor": max(rs)} if rs else {"n": 0})
    resumen["episodios"] = len(eps)
    resumen["completos"] = len(comp)
    resumen["caidas"] = sum(1 for e in comp if e["clase"].startswith("CAÍDA"))
    resumen["falsas_alarmas"] = sum(1 for e in comp if e["clase"] == "FALSA ALARMA")
    resumen["pct_falsas"] = round(100 * resumen["falsas_alarmas"] / len(comp), 1) if comp else None
    resumen["desde"] = eps[0]["fecha"] if eps else None
    return {"episodios": eps[::-1], "resumen": resumen, "tasa_base": base, "horizontes": list(HORIZONTES), "umbral_caida_pct": CAIDA_FALSA,
            "enfriamiento": ENFRIAMIENTO, "umbral_skew": Z_ALTO,
            "sesgo_del_estudio": "Rentabilidad del índice de precios (sin dividendos). Los episodios son pocos y no independientes del todo (crisis largas); "
                                 "una media no es una regla. Correlación con caídas ≠ causalidad ni predicción."}


# ---------------------------------------------------------------- confirmaciones
def _fondos_monetarios():
    """Activos en fondos monetarios: FRED WRMFNS (minoristas, semanal) y OFR (total, mensual, N-MFP de la SEC)."""
    import liquidez_cripto as LQ
    out, err = {}, {}
    try:
        s = LQ.fred("WRMFNS", "2018-01-01")
        if len(s) < 30:
            raise RuntimeError("serie corta")
        def var(k):
            return round((s[-1][1] / s[-1 - k][1] - 1) * 100, 2) if len(s) > k else None
        c13 = [(s[i][1] / s[i - 13][1] - 1) * 100 for i in range(13, len(s))]
        p13 = _pct(c13, c13[-1])
        edad = (dt.date.today() - s[-1][0]).days
        out["minoristas"] = {"fecha": s[-1][0].isoformat(), "valor_mm": round(s[-1][1], 1), "var_4s_pct": var(4), "var_13s_pct": var(13), "var_52s_pct": var(52),
                             "percentil_var_13s": p13, "edad_dias": edad, "fuente": "FRED WRMFNS (fondos monetarios minoristas, semanal)",
                             "url": "https://fred.stlouisfed.org/series/WRMFNS",
                             "serie": [[d.isoformat(), v] for d, v in s[-156:]],
                             "estado": "ENTRADAS FUERTES" if p13 is not None and p13 >= FM_PCT_FUERTE else "SIN ENTRADAS FUERTES"}
    except Exception as e:  # noqa: BLE001
        err["WRMFNS"] = f"{type(e).__name__}: {e}"
    try:
        j = fuentes.json_("https://data.financialresearch.gov/v1/series/timeseries?mnemonic=MMF-MMF_TOT-M", tries=2, timeout=40)
        o = [(dt.date.fromisoformat(f), v / 1e12) for f, v in j if v is not None]
        if len(o) < 14:
            raise RuntimeError("serie corta")
        out["total"] = {"fecha": o[-1][0].isoformat(), "valor_bill": round(o[-1][1], 3),
                        "var_1m_pct": round((o[-1][1] / o[-2][1] - 1) * 100, 2), "var_3m_pct": round((o[-1][1] / o[-4][1] - 1) * 100, 2),
                        "var_12m_pct": round((o[-1][1] / o[-13][1] - 1) * 100, 2), "edad_dias": (dt.date.today() - o[-1][0]).days,
                        "fuente": "OFR · Money Market Fund Monitor (SEC N-MFP), total de inversiones, mensual",
                        "url": "https://www.financialresearch.gov/money-market-funds/",
                        "serie": [[d.isoformat(), round(v, 4)] for d, v in o[-60:]]}
    except Exception as e:  # noqa: BLE001
        err["OFR MMF"] = f"{type(e).__name__}: {e}"
    return out, err


def _confirmaciones(vix, vix3m, ciclo, fm):
    c = []
    # 1 · VIX y estructura de plazos
    if vix:
        ratio = round(vix["valor"] / vix3m["valor"], 3) if vix3m and vix3m.get("valor") else None
        on = vix["valor"] >= VIX_ESTRES or (ratio is not None and ratio >= 1)
        c.append({"clave": "vix", "nombre": "VIX y estructura de plazos", "encendida": on,
                  "estado": "ESTRÉS" if on else "CALMA", "valor": f"VIX {vix['valor']:.1f}" + (f" · VIX/VIX3M {ratio:.2f}" if ratio is not None else ""),
                  "regla": f"Encendida si VIX ≥ {VIX_ESTRES:.0f} o VIX/VIX3M ≥ 1 (curva invertida).", "fecha": vix["fecha"],
                  "fuente": "Cboe (VIX y VIX3M)", "url": "https://www.cboe.com/tradable_products/vix/"})
    else:
        c.append({"clave": "vix", "nombre": "VIX y estructura de plazos", "encendida": None, "estado": "SIN DATO", "valor": "SIN DATO", "regla": "", "fecha": None, "fuente": "Cboe", "url": ""})
    # 2 · crédito (reglas y umbrales de ciclo.py)
    if ciclo and ciclo.get("estado_credito"):
        est = ciclo["estado_credito"]
        on = "TENSI" in est.upper()
        hy, ccc = (ciclo.get("credito") or {}).get("hy") or {}, (ciclo.get("credito") or {}).get("ccc") or {}
        c.append({"clave": "credito", "nombre": "Crédito de riesgo (ciclo.py)", "encendida": on, "estado": "TENSIÓN" if on else "SIN TENSIÓN",
                  "valor": est, "regla": "Encendida si CCC, HY, BBB o IG superan sus umbrales de alerta de ciclo.py (5 días o 1 mes).",
                  "fecha": ccc.get("fecha") or hy.get("fecha"), "fuente": "ICE BofA vía FRED · reglas de ciclo.py", "url": "#/ciclo",
                  "detalle": {"hy_pb": hy.get("pb"), "ccc_pb": ccc.get("pb"), "hy_pct1a": hy.get("percentil_1a"), "ccc_pct1a": ccc.get("percentil_1a")}})
    else:
        c.append({"clave": "credito", "nombre": "Crédito de riesgo (ciclo.py)", "encendida": None, "estado": "SIN DATO", "valor": "SIN DATO", "regla": "", "fecha": None, "fuente": "ciclo.json", "url": "#/ciclo"})
    # 3 · fondos monetarios
    m = fm.get("minoristas")
    if m:
        on = m["estado"] == "ENTRADAS FUERTES"
        c.append({"clave": "fondos", "nombre": "Activos en fondos monetarios", "encendida": on, "estado": m["estado"],
                  "valor": f"{m['valor_mm'] / 1000:.2f} bill. $ · 13 sem. {m['var_13s_pct']:+.2f} % (percentil {m['percentil_var_13s']})",
                  "regla": f"Encendida si la variación a 13 semanas está en el percentil ≥ {FM_PCT_FUERTE} de su historia desde 2018.",
                  "fecha": m["fecha"], "fuente": m["fuente"], "url": m["url"], "retraso_dias": m["edad_dias"]})
    else:
        c.append({"clave": "fondos", "nombre": "Activos en fondos monetarios", "encendida": None, "estado": "SIN DATO", "valor": "SIN DATO", "regla": "", "fecha": None, "fuente": "FRED WRMFNS", "url": ""})
    return c


# ---------------------------------------------------------------- medición
def medir(ciclo=None):
    err = {}
    skew = _csv("SKEW", "SKEW")
    spx, vixc, vix3 = None, None, None
    try:
        spx = _csv("SPX", "SPX")
    except Exception as e:  # noqa: BLE001
        err["Cboe SPX"] = f"{type(e).__name__}: {e}"
    try:
        vixc = _csv("VIX", "CLOSE")
    except Exception as e:  # noqa: BLE001
        err["Cboe VIX"] = f"{type(e).__name__}: {e}"
    try:
        vix3 = _csv("VIX3M", "CLOSE")
    except Exception as e:  # noqa: BLE001
        err["Cboe VIX3M"] = f"{type(e).__name__}: {e}"

    f, v = skew[-1]
    z = zona(v)
    vals = [x for _, x in skew]
    p_hist = _pct(vals, v)
    p_10a = _pct([x for d, x in skew if d >= f - dt.timedelta(days=3652)], v)
    p_1a = _pct(vals[-252:], v)
    # racha en la zona actual y fecha de entrada en zona ALTA
    racha = 0
    for _, x in reversed(skew):
        if zona(x) == z:
            racha += 1
        else:
            break
    entrada_alta = None
    if z == "ALTO":
        i = len(skew) - racha
        entrada_alta = skew[i][0].isoformat()
    # zona previa a la sesión anterior (para detectar el cruce)
    prev = skew[-2][1] if len(skew) > 1 else None
    ult_alto = next((d for d, x in reversed(skew[:-1]) if x >= Z_ALTO), None) if z != "ALTO" else None
    max_hist = max(skew, key=lambda t: t[1])
    max_1a = max(skew[-252:], key=lambda t: t[1])

    vx = {"valor": round(vixc[-1][1], 2), "fecha": vixc[-1][0].isoformat(), "cambio_5d": round(vixc[-1][1] - vixc[-6][1], 2),
          "percentil_1a": _pct([x for _, x in vixc[-252:]], vixc[-1][1])} if vixc else None
    v3 = {"valor": round(vix3[-1][1], 2), "fecha": vix3[-1][0].isoformat()} if vix3 else None
    fm, e_fm = _fondos_monetarios()
    err.update(e_fm)
    conf = _confirmaciones(vx, v3, ciclo, fm)
    validas = [c for c in conf if c["encendida"] is not None]
    encendidas = sum(1 for c in validas if c["encendida"])

    est = None
    if spx:
        est = estudio(skew, spx)
        # episodio actual: rentabilidad del S&P desde la entrada
        if entrada_alta:
            pe = dict(spx)
            d0 = dt.date.fromisoformat(entrada_alta)
            if d0 in pe:
                est["episodio_actual"] = {"entrada": entrada_alta, "sesiones": racha, "spx_entrada": round(pe[d0], 2), "spx_ultimo": round(spx[-1][1], 2),
                                          "ret_desde_entrada_pct": round((spx[-1][1] / pe[d0] - 1) * 100, 2), "fecha_ultimo": spx[-1][0].isoformat()}

    # entrada del episodio vigente (con enfriamiento): clave de la alerta de Telegram, una por episodio
    entrada_ep = est["episodios"][0]["fecha"] if (z == "ALTO" and est and est["episodios"]) else None

    # texto determinista de «lo esencial»
    zt = {"NORMAL": "en zona normal", "ELEVADO": "en zona elevada (≥ 135)", "ALTO": "en zona alta (≥ 140)"}[z]
    cambio = (f"El SKEW de Cboe cerró en {_n(v)} el {_dmy(f)} (percentil {p_hist} de su historia desde 1990; {p_1a} del último año), {zt}"
              + (f"; entró en zona alta el {_dmy(entrada_alta)} y lleva {racha} sesiones seguidas" if z == "ALTO" else "")
              + (f". Sesión previa: {_n(prev)}." if prev is not None else "."))
    if z == "ALTO":
        s1 = ("Interpretación: se paga una prima inusual por cubrirse de una caída fuerte del S&P 500 (cola izquierda). "
              f"Confirmaciones encendidas: {encendidas} de {len(validas)}. "
              + ("El VIX no refleja miedo generalizado: es cobertura de cola sin estrés visible en la volatilidad corriente (hipótesis: posicionamiento institucional, no pánico)."
                 if conf[0]["encendida"] is False else "El VIX y/o su curva muestran estrés: la cobertura de cola no es un hecho aislado."))
    else:
        s1 = (f"Interpretación: la demanda de cobertura de cola no es extrema. Confirmaciones encendidas: {encendidas} de {len(validas)}. "
              "Un SKEW normal no descarta caídas: mide el precio de la cobertura, no su probabilidad.")
    if est and est["resumen"].get("completos"):
        r = est["resumen"]
        s1 += (f" Histórico propio: tras {r['completos']} entradas en zona alta con 60 sesiones cumplidas, el S&P 500 cayó ≥ 5 % en {r['caidas']} ({_n(100 - r['pct_falsas'], 0)} %) "
               f"y en {r['falsas_alarmas']} ({_n(r['pct_falsas'], 0)} %) no (falsas alarmas); en cualquier otra sesión la tasa base de esa caída es del {_n(est['tasa_base']['caida_5_60s_pct'], 0)} %.")
    vig = "Cierre del SKEW (Cboe, cada sesión): si baja de 140 la señal se apaga; si el VIX/VIX3M se invierte o el crédito (CCC/HY) sigue ampliándose, la cobertura gana confirmación."
    anual = {}
    for d, x in skew:
        a = anual.setdefault(d.year, [0, 0])
        a[0] += 1
        a[1] += x >= Z_ALTO
    distrib = [{"anio": y, "pct_alto": round(100 * c[1] / c[0], 1), "sesiones": c[0]} for y, c in sorted(anual.items())]
    return {"fecha": f.isoformat(), "valor": round(v, 2), "zona": z, "previo": round(prev, 2) if prev is not None else None,
            "entrada_episodio": entrada_ep, "percentil_hist": p_hist, "percentil_10a": p_10a, "percentil_1a": p_1a, "racha_sesiones": racha, "entrada_zona_alta": entrada_alta,
            "ultima_vez_alto": ult_alto.isoformat() if ult_alto else None,
            "maximo_hist": {"fecha": max_hist[0].isoformat(), "valor": round(max_hist[1], 2)}, "maximo_1a": {"fecha": max_1a[0].isoformat(), "valor": round(max_1a[1], 2)},
            "umbrales": {"elevado": Z_ELEVADO, "alto": Z_ALTO}, "vix": vx, "vix3m": v3,
            "confirmaciones": conf, "confirmaciones_encendidas": encendidas, "confirmaciones_validas": len(validas),
            "fondos_monetarios": fm, "estudio": est, "distribucion_anual": distrib,
            "series": {"skew": [[d.isoformat(), round(x, 2)] for d, x in skew[-1300:]],
                       "spx": [[d.isoformat(), round(x, 2)] for d, x in spx[-1300:]] if spx else None,
                       "vix": [[d.isoformat(), round(x, 2)] for d, x in vixc[-1300:]] if vixc else None},
            "esencial": {"cambio": cambio, "significa": s1, "vigilar": vig},
            "fuente": "Cboe · SKEW, VIX, VIX3M y SPX (cdn-api.cboe.com, CSV públicos)", "url": URL_CBOE, "errores": err,
            "metodo": ("CRITERIO NEXORA. Zonas: normal < 135, elevado ≥ 135, alto ≥ 140. Episodio = primer cierre en zona alta tras 10 sesiones sin estarlo. "
                       "Falsa alarma = el S&P 500 no cae ≥ 5 % desde el cierre de entrada en las siguientes 60 sesiones. Los umbrales son convenciones fijas, no optimizadas.")}


def guardar_historico(M):
    """Memoria permanente (solo se añade): una fila por sesión del SKEW de los últimos 15 días hábiles (cubre días sin ejecución)."""
    sk = M["series"]["skew"][-15:]
    vx = dict(M["series"]["vix"] or [])
    filas = [{"fecha_dato": d, "skew": v, "zona": zona(v), "vix": vx.get(d, "")} for d, v in sk]
    return csvlog.anadir("historico_skew.csv", filas, ("fecha_dato",))


if __name__ == "__main__":
    import json
    M = medir()
    e = M.pop("estudio", None)
    M.pop("series")
    print(json.dumps({k: v for k, v in M.items() if k not in ("fondos_monetarios",)}, ensure_ascii=False, indent=1)[:3500])
    if e:
        print("RESUMEN", json.dumps(e["resumen"], ensure_ascii=False))
        print("BASE", json.dumps(e["tasa_base"], ensure_ascii=False))
        for x in e["episodios"][:8]:
            print(x)
