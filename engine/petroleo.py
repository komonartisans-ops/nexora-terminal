#!/usr/bin/env python3
"""NEXORA · Petróleo como activo completo (#/petroleo). Sin IA, gratis, SIN DATO si falta algo. Escribe site/data/petroleo.json.

Fuentes (todas públicas y verificadas):
  · Precio: Yahoo Finance CL=F (WTI) y BZ=F (Brent, futuro); respaldo y segunda fuente FRED DCOILWTICO / DCOILBRENTEU (precios al contado diarios de EIA, con unos días de retraso).
    OJO: FRED trae el Brent FECHADO (físico, Dated Brent) y Yahoo el futuro: pueden separarse mucho cuando el mercado está en escasez; se muestra la diferencia, no se corrige.
  · Curva: contratos reales de WTI por mes (Yahoo CL<mes><año>.NYM, p. ej. CLX26.NYM = nov-2026). Vencimiento de cada contrato = 3 días hábiles antes del día 25 del mes anterior a la entrega
    (si el 25 no es hábil, 3 días hábiles antes del hábil anterior); solo se descuentan sábados y domingos (los festivos de CME no se modelan).
  · Inventarios: EIA Weekly Petroleum Status Report. Con el secreto EIA_API_KEY usa la API v2 (api.eia.gov/v2/petroleum/stoc/wstk); sin él, las tablas públicas
    https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=PET&s=<serie>&f=W (historial) y https://ir.eia.gov/wpsr/table1.csv (semana en curso). Series: WCESTUS1 (crudo, sin SPR),
    WGTSTUS1 (gasolina total), WDISTUS1 (destilados). Calendario de publicación: https://www.eia.gov/petroleum/supply/weekly/schedule.php.
  · Posicionamiento: CFTC Disaggregated, WTI-PHYSICAL (código 067651), dinero gestionado, vía el motor de cot.py (site/data/cot.json).
  · Plataformas Baker Hughes: rigcount.bakerhughes.com NO responde (ni en local ni desde GitHub Actions, comprobado con tools/diagnostico_fuentes_petroleo.py) → SIN DATO.
  · Gasolina EE. UU.: FRED GASREGW. Relaciones: FRED T5YIE (breakeven a 5 años), DXY y XLE (Yahoo).

TESIS DE PETRÓLEO (reglas FIJAS, impresas también en la página; no usan umbrales de otros módulos). Cuatro factores, cada uno vota +1 / 0 / −1:
  PRECIO:       WTI (CL=F) sobre su media de 200 sesiones = +1; bajo ella = −1.
  CURVA:        diferencial 1.er–2.º vencimiento en % del 2.º: ≥ +0,5 % (backwardation, ESCASEZ) = +1; ≤ −0,5 % (contango, SOBRA) = −1; entre medias = PLANA = 0.
                Si al 1.er contrato le quedan menos de 5 días hábiles (lun-vie, festivos de CME no modelados) para vencer, se usa el diferencial 2.º–3.º con los mismos umbrales
                (la página dice qué par se ha usado y data/historico_curva_wti.csv lo registra en la columna «par»).
  INVENTARIOS:  crudo, gasolina y destilados frente a su media de 5 años de la misma semana: por debajo en más de un 2 % vota +1; por encima en más de un 2 % vota −1; si no, 0.
                La suma de los tres da el voto: ≥ +2 = +1; ≤ −2 = −1; si no, 0.
  COT:          percentil a 3 años del neto del dinero gestionado en WTI: ≥ 66 = +1; ≤ 34 = −1; si no, 0. (Ese criterio es propio de petróleo: NEXORA no tiene un voto de COT común a oro,
                índices y divisas; la página enseña las diferencias y qué voto saldría con cada una.)
  RESULTADO: suma de los cuatro votos (necesita dato en PRECIO y en al menos otros dos factores; si no, SIN TESIS por falta de dato). ≥ +2 ALCISTA; ≤ −2 BAJISTA; si no, SIN TESIS.
  INTENSIDAD: FUERTE si la suma es ±3 o más y ningún factor vota en contra; si no, DÉBIL.
  Dirección para el marcador (WTI a T+20): ALCISTA = sube; BAJISTA = baja; SIN TESIS = no puntuable.
Las relaciones con inflación esperada, DXY y XLE se muestran pero NO puntúan.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import math
import os
import re
import statistics
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(HERE)
sys.path.insert(0, HERE)
UTC = dt.timezone.utc

UMBRAL_CURVA_PCT = 0.5
DIAS_HABILES_MIN_M1 = 5            # con menos días hábiles hasta el vencimiento del 1.er contrato se usa el par 2.º–3.º
UMBRAL_BRENT_PCT = 10.0            # diferencia (Yahoo BZ=F frente a FRED DCOILBRENTEU, MISMO día) a partir de la cual se abre una discrepancia en #/integridad
UMBRAL_INV_PCT = 2.0
COT_ALTO, COT_BAJO = 66, 34
MIN_DATOS = 3                       # factores con dato necesarios (PRECIO incluido)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
EIA_SERIES = {"crudo": ("WCESTUS1", "Crudo (sin SPR)"), "gasolina": ("WGTSTUS1", "Gasolina total"), "destilados": ("WDISTUS1", "Destilados")}
EIA_SCHEDULE = "https://www.eia.gov/petroleum/supply/weekly/schedule.php"
EIA_TABLA1 = "https://ir.eia.gov/wpsr/table1.csv"
EIA_HIST = "https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=PET&s={}&f=W"
EIA_API = "https://api.eia.gov/v2/petroleum/stoc/wstk/data/"
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
CODIGOS_MES = "FGHJKMNQUVXZ"
BAKER_SIN_DATO = ("rigcount.bakerhughes.com no responde (tiempo de espera agotado o acceso denegado), comprobado en local y desde GitHub Actions el 2026-10-19 con "
                  "tools/diagnostico_fuentes_petroleo.py: SIN DATO (no se estima).")
CAMPOS_EIA = ["semana", "producto", "valor_kb", "fuente", "capturado_utc"]
CAMPOS_CAL = ["semana", "fecha", "hora_et", "fuente", "visto_utc"]


def P(raiz, *a):
    return os.path.join(raiz, *a)


# ---------------------------------------------------------------- descargas (inyectables en pruebas)
def _get(url, timeout=45, tries=3):
    ultimo = None
    for k in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read().decode("utf-8-sig", "replace")
        except Exception as e:  # noqa: BLE001
            ultimo = e
            time.sleep(2 * (k + 1))
    raise ultimo


def yahoo(sym, rango="2y", minimo=5, tries=3):
    q = urllib.parse.quote(sym, safe="")
    ultimo = None
    for k in range(tries):
        for host in ("query2", "query1"):
            try:
                req = urllib.request.Request(f"https://{host}.finance.yahoo.com/v8/finance/chart/{q}?range={rango}&interval=1d", headers=UA)
                r = json.loads(urllib.request.urlopen(req, timeout=40).read())["chart"]["result"][0]
                pts = [(dt.datetime.fromtimestamp(t, UTC).date(), float(c)) for t, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]) if c is not None]
                if len(pts) < minimo:
                    raise RuntimeError("serie demasiado corta")
                return pts
            except Exception as e:  # noqa: BLE001
                ultimo = e
        time.sleep(1.5 * (k + 1))
    raise RuntimeError(f"Yahoo sin datos de {sym} ({type(ultimo).__name__})")


def fred(sid, desde):
    from liquidez_cripto import fred as _f
    return _f(sid, desde)


def cot_json(raiz=RAIZ):
    try:
        return json.load(open(P(raiz, "site", "data", "cot.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------- cálculo básico
def sma(v, n):
    return [statistics.mean(v[i - n + 1:i + 1]) if i >= n - 1 else None for i in range(len(v))]


def cambio_pct(pts, n):
    return round((pts[-1][1] / pts[-1 - n][1] - 1) * 100, 2) if len(pts) > n and pts[-1 - n][1] else None


def grafico(pts, años=2):
    v = [x[1] for x in pts]
    s50, s200 = sma(v, 50), sma(v, 200)
    corte = (pts[-1][0] - dt.timedelta(days=365 * años)).isoformat()
    f = lambda xs: [[d.isoformat(), round(x, 3)] for (d, _), x in zip(pts, xs) if x is not None and d.isoformat() >= corte]  # noqa: E731
    return {"precio": f(v), "sma50": f(s50), "sma200": f(s200)}


def metricas_precio(pts):
    if len(pts) < 200:
        return None
    v = [x[1] for x in pts]
    s200, s50 = statistics.mean(v[-200:]), statistics.mean(v[-50:])
    return {"valor": round(v[-1], 2), "fecha": pts[-1][0].isoformat(), "sma50": round(s50, 2), "sma200": round(s200, 2), "dist_sma200_pct": round((v[-1] / s200 - 1) * 100, 2),
            "cambio_1d_pct": cambio_pct(pts, 1), "cambio_5d_pct": cambio_pct(pts, 5), "cambio_21d_pct": cambio_pct(pts, 21), "cambio_63d_pct": cambio_pct(pts, 63)}


def ajustar_roll(pw, wti, series_ct):
    """CL=F es una serie EMPALMADA: el día que Yahoo pasa del 1.er al 2.º vencimiento el cambio diario incluye el salto entre contratos (p. ej. −4 % por pasar de nov a dic).
    Si el último cierre de CL=F coincide con un contrato real vivo (±0,25 %), los cambios de 1 y 5 días se recalculan con ESE contrato. Devuelve (metricas, ticker o None, aviso o None)."""
    if not pw or not wti:
        return pw, None, None
    ult = wti[-1]
    cand = [(abs(dict(sc)[ult[0]] - ult[1]), t, sc) for t, sc in series_ct.items() if ult[0] in dict(sc) and len(sc) >= 5]
    for dif, t, sc in sorted(cand)[:1]:
        if dif <= 0.0025 * ult[1]:                           # el último cierre es intradía y los dos fetch no son simultáneos: tolerancia del 0,25 %
            pts = sorted(sc)
            ajust = {**pw, "cambio_1d_pct": cambio_pct(pts, 1), "cambio_5d_pct": cambio_pct(pts, 5)}
            hubo = (pw.get("cambio_1d_pct") is not None and ajust["cambio_1d_pct"] is not None and abs(pw["cambio_1d_pct"] - ajust["cambio_1d_pct"]) > 0.3)
            return ajust, t, (f"CL=F apunta hoy a {t}; el cambio de 1 día se mide sobre ese contrato ({_n(ajust['cambio_1d_pct'], 2)} %) y no sobre la serie empalmada ({_n(pw['cambio_1d_pct'], 2)} %), que mezcla dos contratos" if hubo else None)
    return pw, None, None


# ---------------------------------------------------------------- contratos de WTI y curva
def _habil_antes(d, n):
    """Día hábil (lun-vie) n días hábiles antes de d."""
    while n > 0:
        d -= dt.timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def vencimiento(anio, mes_entrega):
    """Último día de negociación del WTI de entrega (anio, mes): 3 días hábiles antes del día 25 del mes anterior (si el 25 no es hábil, antes del hábil anterior)."""
    m = mes_entrega - 1 or 12
    y = anio - (1 if mes_entrega == 1 else 0)
    d25 = dt.date(y, m, 25)
    while d25.weekday() >= 5:
        d25 -= dt.timedelta(days=1)
    return _habil_antes(d25, 3)


def nombre_contrato(tk):
    """CLX26.NYM → «nov-2026»."""
    m = re.match(r"CL([FGHJKMNQUVXZ])(\d\d)\.NYM", tk or "")
    return f"{['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'][CODIGOS_MES.index(m.group(1))]}-20{m.group(2)}" if m else str(tk)


def ticker_wti(anio, mes):
    return f"CL{CODIGOS_MES[mes - 1]}{str(anio)[2:]}.NYM"


def contratos(hoy, atras_meses=14, adelante_meses=3):
    """[(anio, mes, ticker, vencimiento)] de los contratos de entrega que cubren desde hace `atras_meses` hasta dentro de `adelante_meses` meses."""
    out = []
    y, m = hoy.year, hoy.month
    m -= atras_meses
    while m < 1:
        m += 12
        y -= 1
    for _ in range(atras_meses + adelante_meses + 1):
        out.append((y, m, ticker_wti(y, m), vencimiento(y, m)))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def primero_segundo(cts, d):
    """(M1, M2) a fecha d: el primer contrato con vencimiento ≥ d y el siguiente."""
    vivos = [c for c in cts if c[3] >= d]
    return (vivos[0], vivos[1]) if len(vivos) >= 2 else (None, None)


def estado_curva(pct):
    pct = round(pct, 6)
    return "ESCASEZ" if pct >= UMBRAL_CURVA_PCT else "SOBRA" if pct <= -UMBRAL_CURVA_PCT else "PLANA"


def dias_habiles(desde, hasta):
    """Días hábiles (lun-vie) en (desde, hasta]: los que quedan hasta el vencimiento incluido el propio día. Los festivos de CME no se modelan."""
    n, d = 0, desde
    while d < hasta:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def _diferencial(series_ct, c1, c2):
    """[(fecha, dif, dif%)] del par (c1, c2) en los días en que ambos cotizaron; [] si falta alguno."""
    if c1[2] not in series_ct or c2[2] not in series_ct:
        return []
    a, b = dict(series_ct[c1[2]]), dict(series_ct[c2[2]])
    return [(d, a[d] - b[d], (a[d] - b[d]) / b[d] * 100, a[d], b[d]) for d in sorted(set(a) & set(b)) if b[d]]


def curva(series_ct, hoy):
    """series_ct = {ticker: [(fecha, cierre)]} de los contratos VIVOS (Yahoo ya no sirve los vencidos). Estado de hoy: diferencial 1.er–2.º vencimiento y su % del 2.º; si al 1.er contrato
    le quedan menos de DIAS_HABILES_MIN_M1 días hábiles se usa el 2.º–3.º (y se dice). «histórico del par»: el mismo par en los días en que ambos cotizaron; NO es el de cada día pasado
    (los contratos vencidos no están disponibles: la EIA dejó de publicar sus series de futuros en abril de 2024). El histórico propio se acumula en data/historico_curva_wti.csv (columna par)."""
    vivos = [c for c in contratos(hoy) if c[3] >= hoy]
    if len(vivos) < 2:
        return None
    m1, m2, m3 = vivos[0], vivos[1], (vivos[2] if len(vivos) > 2 else None)
    dh = dias_habiles(hoy, m1[3])
    p12 = _diferencial(series_ct, m1, m2)
    p23 = _diferencial(series_ct, m2, m3) if m3 else []
    usar23 = dh < DIAS_HABILES_MIN_M1 and bool(p23)
    c1, c2, par, par_txt = (m2, m3, p23, "2-3") if usar23 else (m1, m2, p12, "1-2")
    if not par:
        return None
    d, dif, pct, pa, pb = par[-1]
    pcts = [x[2] for x in par]
    motivo = None
    if usar23:
        motivo = (f"al 1.er contrato ({nombre_contrato(m1[2])}) le quedan {dh} día{'s' if dh != 1 else ''} hábil{'es' if dh != 1 else ''} (< {DIAS_HABILES_MIN_M1}) para vencer el {m1[3].isoformat()}: "
                  f"se usa el 2.º–3.º ({nombre_contrato(m2[2])} / {nombre_contrato(m3[2])}) para evitar la distorsión del vencimiento")
    elif dh < DIAS_HABILES_MIN_M1:
        motivo = (f"al 1.er contrato le quedan {dh} día(s) hábil(es) pero no hay datos del 3.º: se usa el 1.º–2.º, que puede estar distorsionado por el vencimiento")
    info12 = None
    if p12 and usar23:
        e = p12[-1]
        info12 = {"m1": m1[2], "m2": m2[2], "diferencial": round(e[1], 2), "diferencial_pct": round(e[2], 2), "estado": estado_curva(e[2]), "fecha": e[0].isoformat()}
    return {"fecha": d.isoformat(), "par_usado": par_txt, "m1": c1[2], "m2": c2[2], "precio_m1": round(pa, 2), "precio_m2": round(pb, 2), "diferencial": round(dif, 2), "diferencial_pct": round(pct, 2),
            "estado": estado_curva(pct), "vence_m1": c1[3].isoformat(), "dias_a_vencimiento_m1": (c1[3] - d).days, "primer_vencimiento": {"ticker": m1[2], "vence": m1[3].isoformat(), "dias_habiles": dh},
            "motivo_par": motivo, "info_1_2": info12, "aviso": (motivo if not usar23 and motivo else None),
            "percentil_par": round(sum(1 for p in pcts if p <= pct) / len(pcts) * 100), "dias_par": len(pcts), "min_pct": round(min(pcts), 2), "max_pct": round(max(pcts), 2),
            "historico_par": [[x[0].isoformat(), round(x[2], 3)] for x in par[-260:]]}


CAMPOS_CURVA = ["fecha", "m1", "m2", "precio_m1", "precio_m2", "diferencial", "diferencial_pct", "capturado_utc", "par"]


def _asegurar_columna(ruta, columna):
    """Añade `columna` al FINAL de la cabecera de un CSV existente; solo cambia la primera línea (las filas antiguas quedan sin ese valor)."""
    if not os.path.exists(ruta) or os.path.getsize(ruta) == 0:
        return False
    datos = open(ruta, "rb").read()
    i = datos.find(b"\n")
    cab = datos[:i].rstrip(b"\r")
    if i < 0 or columna.encode() in cab.split(b","):
        return False
    fin = b"\r\n" if datos[i - 1:i] == b"\r" else b"\n"
    open(ruta, "wb").write(cab + b"," + columna.encode() + fin + datos[i + 1:])
    return True


def historico_propio(raiz, cur, ahora):
    """Memoria propia (solo-añadir): una fila por día y par con el diferencial usado ese día (columna «par»: 1-2 o 2-3; las filas anteriores a esa columna son 1-2).
    Devuelve {dias, desde, percentil, par} de hoy dentro de lo acumulado PARA ESE PAR."""
    import integridad as I
    ruta = P(raiz, "data", "historico_curva_wti.csv")
    _asegurar_columna(ruta, "par")
    if cur:
        I.anadir_csv(ruta, [{"fecha": cur["fecha"], "m1": cur["m1"], "m2": cur["m2"], "precio_m1": cur["precio_m1"], "precio_m2": cur["precio_m2"], "diferencial": cur["diferencial"],
                             "diferencial_pct": cur["diferencial_pct"], "capturado_utc": ahora.strftime("%Y-%m-%d %H:%M UTC"), "par": cur["par_usado"]}],
                     CAMPOS_CURVA, lambda r: (r["fecha"], r.get("par") or "1-2"))
    par = (cur or {}).get("par_usado") or "1-2"
    filas = [r for r in _csv(ruta) if (r.get("par") or "1-2") == par]
    todas = _csv(ruta)
    if not filas:
        return {"dias": 0, "desde": None, "percentil": None, "serie": [], "par": par, "pares_registrados": sorted({(r.get("par") or "1-2") for r in todas})}
    v = [float(r["diferencial_pct"]) for r in filas]
    return {"dias": len(v), "desde": filas[0]["fecha"], "percentil": (round(sum(1 for x in v if x <= v[-1]) / len(v) * 100) if len(v) >= 30 else None), "par": par,
            "pares_registrados": sorted({(r.get("par") or "1-2") for r in todas}), "serie": [[r["fecha"], float(r["diferencial_pct"])] for r in filas[-260:]]}


# ---------------------------------------------------------------- inventarios EIA
def parse_hist(html):
    """LeafHandler de EIA → [(fecha fin de semana, miles de barriles)] ordenado. Cada fila lleva «AAAA-Mes» y pares «mm/dd valor»."""
    t = re.sub(r"&nbsp;", " ", re.sub(r"<script.*?</script>", " ", html, flags=re.S))
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))
    out = []
    for p in re.split(r"(?=\b\d{4}-[A-Z][a-z]{2}\b)", t):
        m = re.match(r"(\d{4})-[A-Z][a-z]{2}\b(.*)", p)
        if not m:
            continue
        for md, v in re.findall(r"\b(\d\d/\d\d) ([\d,]+)", m.group(2)):
            mo, da = map(int, md.split("/"))
            try:
                out.append((dt.date(int(m.group(1)), mo, da), float(v.replace(",", ""))))
            except ValueError:
                continue
    return sorted(set(out))


def parse_api(texto, sid):
    """Respuesta JSON de la API v2 de EIA → [(fecha, miles de barriles)]."""
    out = []
    for r in (json.loads(texto).get("response") or {}).get("data") or []:
        if r.get("series") == sid and r.get("value") not in (None, ""):
            out.append((dt.date.fromisoformat(r["period"]), float(r["value"])))
    return sorted(set(out))


def eia_serie(sid, fetch, clave_api=None):
    """Historial semanal de una serie EIA. Con clave: API v2 (la clave solo va en la consulta; nunca se imprime ni se guarda). Sin clave: tabla pública."""
    if clave_api:
        q = {"api_key": clave_api, "frequency": "weekly", "data[0]": "value", "facets[series][]": sid, "sort[0][column]": "period", "sort[0][direction]": "desc", "length": "5000"}
        try:
            r = parse_api(fetch(EIA_API + "?" + urllib.parse.urlencode(q)), sid)
            if len(r) > 100:
                return r, "EIA API v2"
        except Exception:  # noqa: BLE001  (el error puede incluir la URL con la clave: no se propaga ni se imprime)
            pass
    return parse_hist(fetch(EIA_HIST.format(sid))), "EIA tablas públicas (Weekly Petroleum Status Report)"


def media_5a(serie, fecha):
    """Media de los valores de la misma semana de los 5 años anteriores (el dato más cercano a fecha−N años, a ≤ 3 días). None si faltan años."""
    d = dict(serie)
    vals = []
    for n in range(1, 6):
        obj = dt.date(fecha.year - n, fecha.month, min(fecha.day, 28)) if (fecha.month, fecha.day) != (2, 29) else dt.date(fecha.year - n, 2, 28)
        cand = [(abs((k - obj).days), v) for k, v in d.items() if abs((k - obj).days) <= 3]
        if cand:
            vals.append(min(cand)[1])
    return (statistics.mean(vals), len(vals)) if len(vals) >= 4 else (None, len(vals))


def inventario(serie):
    if len(serie) < 60:
        return None
    f, v = serie[-1]
    pf, pv = serie[-2]
    m5, n5 = media_5a(serie[:-1], f)
    r = {"semana": f.isoformat(), "valor_mb": round(v / 1000, 1), "cambio_semana_mb": round((v - pv) / 1000, 1), "semana_previa": pf.isoformat(), "dias_entre": (f - pf).days}
    if m5:
        dev = round((v / m5 - 1) * 100, 6)                 # redondeo: el umbral exacto (±2 %) no depende del error de coma flotante
        r.update({"media_5a_mb": round(m5 / 1000, 1), "vs_media_5a_pct": round(dev, 2), "vs_media_5a_mb": round((v - m5) / 1000, 1), "anios_media": n5,
                  "voto": 1 if dev < -UMBRAL_INV_PCT else -1 if dev > UMBRAL_INV_PCT else 0})
    else:
        r.update({"media_5a_mb": None, "vs_media_5a_pct": None, "voto": None})
    r["serie"] = [[a.isoformat(), round(b / 1000, 2)] for a, b in serie[-130:]]
    return r


def parse_tabla1(texto):
    """table1.csv → (semana, {producto: miles de barriles}) de la semana en curso (crudo comercial, gasolina total, destilados)."""
    filas = list(csv.reader(io.StringIO(texto)))
    if not filas or len(filas[0]) < 2:
        raise ValueError("table1.csv sin cabecera")
    mo, da, ya = filas[0][1].split("/")
    semana = dt.date(2000 + int(ya), int(mo), int(da))
    cl = {"Commercial (Excluding SPR)": "crudo", "Total Motor Gasoline": "gasolina", "Distillate Fuel Oil": "destilados"}
    out = {}
    for r in filas[1:]:
        if r and r[0] in cl and cl[r[0]] not in out:
            out[cl[r[0]]] = float(r[1].replace(",", "")) * 1000
    if len(out) < 3:
        raise ValueError("table1.csv sin los tres productos")
    return semana, out


# ---------------------------------------------------------------- calendario de la EIA (publicación oficial)
def parse_calendario_eia(html):
    """schedule.php → {fecha fin de semana (date): (fecha de publicación, 'HH:MM' ET)} solo de las EXCEPCIONES; el resto es el miércoles 10:30 ET."""
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    out = {}
    pat = r"([A-Z][a-z]+ \d{1,2}, \d{4}) ([A-Z][a-z]+ \d{1,2}, \d{4}) (Monday|Tuesday|Wednesday|Thursday|Friday) (\d{1,2}:\d{2}) (a\.m\.|p\.m\.)"
    for a, b, _, hm, ap in re.findall(pat, t):
        h, m = map(int, hm.split(":"))
        h = h % 12 + (12 if ap.startswith("p") else 0)
        out[dt.datetime.strptime(a, "%B %d, %Y").date()] = (dt.datetime.strptime(b, "%B %d, %Y").date(), f"{h:02d}:{m:02d}")
    return out


def publicacion_eia(semana, excepciones):
    """(fecha, hora ET) en que sale el informe de la semana que termina el viernes `semana`."""
    if semana in (excepciones or {}):
        return excepciones[semana]
    return semana + dt.timedelta(days=5), "10:30"


def proxima_publicacion(excepciones, hoy):
    """Próximo informe: (semana, fecha, hora ET) con fecha ≥ hoy."""
    f = hoy - dt.timedelta(days=((hoy.weekday() - 4) % 7))          # último viernes
    for k in range(-1, 6):
        s = f + dt.timedelta(days=7 * k)
        fecha, hm = publicacion_eia(s, excepciones)
        if fecha >= hoy:
            return s, fecha, hm
    return None


# ---------------------------------------------------------------- registro del informe EIA (solo-añadir) y vigilante
def _csv(ruta):
    if not os.path.exists(ruta):
        return []
    with open(ruta, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def registro_eia(raiz):
    return _csv(P(raiz, "data", "eia_inventarios.csv"))


def refrescar_eia(raiz=RAIZ, ahora=None, fetch=None, forzar=False):
    """Lee la tabla semanal pública de la EIA (6,5 kB) y anota la semana nueva (solo-añadir) más el calendario oficial de excepciones. Máx. 1 vez cada 20 h salvo informe pendiente."""
    import integridad as I
    ahora = ahora or dt.datetime.now(UTC)
    est = I._est_i(raiz)
    prev = (est.get("eia") or {}).get("ultimo_utc")
    try:
        hace_h = (ahora - dt.datetime.fromisoformat(prev).replace(tzinfo=UTC)).total_seconds() / 3600 if prev else None
    except ValueError:
        hace_h = None
    if not (forzar or hace_h is None or hace_h >= 20 or pendientes_eia(raiz, ahora)):
        return None
    f = fetch or _get
    err = {}
    stamp = ahora.strftime("%Y-%m-%d %H:%M UTC")
    try:
        semana, vals = parse_tabla1(f(EIA_TABLA1))
        I.anadir_csv(P(raiz, "data", "eia_inventarios.csv"), [{"semana": semana.isoformat(), "producto": k, "valor_kb": round(v, 1), "fuente": EIA_TABLA1, "capturado_utc": stamp}
                                                                for k, v in vals.items()], CAMPOS_EIA, lambda r: (r["semana"], r["producto"]))
    except Exception as e:  # noqa: BLE001
        err["tabla1"] = f"{type(e).__name__}: {str(e)[:100]}"
    try:
        exc = parse_calendario_eia(f(EIA_SCHEDULE))
        filas = [{"semana": s.isoformat(), "fecha": a.isoformat(), "hora_et": hm, "fuente": EIA_SCHEDULE, "visto_utc": stamp} for s, (a, hm) in exc.items()]
        I.anadir_csv(P(raiz, "data", "eia_calendario.csv"), filas, CAMPOS_CAL, lambda r: (r["semana"], r["fecha"], r["hora_et"]))
    except Exception as e:  # noqa: BLE001
        err["calendario"] = f"{type(e).__name__}: {str(e)[:100]}"
    est = I._est_i(raiz)
    est["eia"] = {"ultimo_utc": ahora.strftime("%Y-%m-%dT%H:%M:%S"), "ultimo_error": "; ".join(f"{k}: {v}" for k, v in err.items()) or None}
    I._guardar_i(raiz, est)
    return err


def excepciones_eia(raiz):
    """Excepciones del calendario oficial anotadas (la última lectura de cada semana manda)."""
    out = {}
    for r in _csv(P(raiz, "data", "eia_calendario.csv")):
        out[dt.date.fromisoformat(r["semana"])] = (dt.date.fromisoformat(r["fecha"]), r["hora_et"])
    return out


def pendientes_eia(raiz, ahora):
    """[(semana, instante UTC de publicación)] de informes publicados hace 2-48 h y NO registrados (la semana no consta en data/eia_inventarios.csv)."""
    from zoneinfo import ZoneInfo
    NY = ZoneInfo("America/New_York")
    exc = excepciones_eia(raiz)
    reg = {r["semana"] for r in registro_eia(raiz)}
    if not reg:                                         # sin ninguna semana registrada aún (primer uso o pruebas) el vigilante no avisa: no hay referencia
        return []
    out = []
    f = ahora.date() - dt.timedelta(days=((ahora.date().weekday() - 4) % 7))
    for k in range(-2, 2):
        s = f + dt.timedelta(days=7 * k)
        fecha, hm = publicacion_eia(s, exc)
        h, m = map(int, hm.split(":"))
        t = dt.datetime.combine(fecha, dt.time(h, m), NY).astimezone(UTC)
        if 2 <= (ahora - t).total_seconds() / 3600 <= 48 and s.isoformat() not in reg:
            out.append((s, t))
    return out


def eventos_agenda(raiz, hoy, dias=14):
    """Eventos para la agenda: informe semanal de inventarios de la EIA (MEDIA) con su fecha y hora oficiales."""
    from zoneinfo import ZoneInfo
    NY = ZoneInfo("America/New_York")
    exc = excepciones_eia(raiz)
    out = []
    f = hoy - dt.timedelta(days=((hoy.weekday() - 4) % 7))
    for k in range(-1, 4):
        s = f + dt.timedelta(days=7 * k)
        fecha, hm = publicacion_eia(s, exc)
        if hoy <= fecha <= hoy + dt.timedelta(days=dias):
            h, m = map(int, hm.split(":"))
            t = dt.datetime.combine(fecha, dt.time(h, m), NY)
            out.append({"fecha": fecha.isoformat(), "hora_ny": hm, "evento": "Inventarios de petróleo EIA (semana al " + s.strftime("%d-%m") + ")", "importancia": "MEDIA",
                        "afecta": "petróleo · índices", "que_mirar": "Cambio semanal de crudo, gasolina y destilados frente a la media de 5 años.", "fuente": "EIA · Weekly Petroleum Status Report (calendario oficial)",
                        "url": EIA_SCHEDULE, "hora_madrid": t.astimezone(ZoneInfo("Europe/Madrid")).strftime("%H:%M")})
    return out


# ---------------------------------------------------------------- reuniones de la OPEP/OPEP+ (calendario oficial)
OPEP_CALENDARIO = "https://www.opec.org/opec_web/en/press_room/calendar.htm"
OPEP_SIN_DATO = ("calendario oficial de la OPEP no accesible: opec.org/…/calendar.htm responde 403 a las consultas automáticas (comprobado en local y desde GitHub Actions el 2026-10-19). "
                 "La portada solo trae noticias con la fecha de publicación, no las fechas de las próximas reuniones: no se infiere ninguna. Sin reuniones OPEP+ en la agenda (SIN DATO).")


# ---------------------------------------------------------------- relaciones (no puntúan)
def _ret(pts):
    return {pts[i][0]: pts[i][1] / pts[i - 1][1] - 1 for i in range(1, len(pts)) if pts[i - 1][1]}


def _dif(pts):
    return {pts[i][0]: pts[i][1] - pts[i - 1][1] for i in range(1, len(pts))}


def correlacion(a, b, n=60):
    """Correlación de Pearson de los últimos n días comunes de dos dicts {fecha: variación}."""
    ks = sorted(set(a) & set(b))[-n:]
    if len(ks) < 30:
        return None
    x, y = [a[k] for k in ks], [b[k] for k in ks]
    mx, my = statistics.mean(x), statistics.mean(y)
    sx, sy = sum((i - mx) ** 2 for i in x), sum((i - my) ** 2 for i in y)
    return round(sum((i - mx) * (j - my) for i, j in zip(x, y)) / math.sqrt(sx * sy), 2) if sx and sy else None


def relaciones(wti, t5yie, dxy, xle):
    """WTI frente a breakeven 5 años, DXY y XLE: correlación de 60 sesiones de las variaciones diarias y cambio de cada uno en 3 meses. Solo se muestra."""
    out = []
    rw = _ret(wti)
    for clave, nombre, pts, tipo in (("t5yie", "Inflación esperada a 5 años (breakeven, FRED T5YIE)", t5yie, "pb"), ("dxy", "Dólar (DXY)", dxy, "%"), ("xle", "Energía EE. UU. (ETF XLE)", xle, "%")):
        if not pts or len(pts) < 70:
            out.append({"clave": clave, "nombre": nombre, "sin_dato": True})
            continue
        c = correlacion(rw, _dif(pts) if tipo == "pb" else _ret(pts))
        ch = round((pts[-1][1] - pts[-64][1]) * 100, 1) if tipo == "pb" else cambio_pct(pts, 63)
        out.append({"clave": clave, "nombre": nombre, "valor": round(pts[-1][1], 2), "fecha": pts[-1][0].isoformat(), "cambio_3m": ch, "unidad_cambio": "pb" if tipo == "pb" else "%", "correlacion_60d": c,
                    "lectura": (None if c is None else "se mueven juntos" if c >= 0.3 else "se mueven en sentido contrario" if c <= -0.3 else "sin relación clara en 60 sesiones")})
    cambio_wti = cambio_pct(wti, 63)
    return {"wti_cambio_3m_pct": cambio_wti, "filas": out}


# ---------------------------------------------------------------- COT del WTI (motor de cot.py)
def etiqueta_cot(neto, pct):
    """Lado de la posición (por el SIGNO del neto) y nivel frente a su historia (percentil a 3 años, con los mismos cortes del voto: ≤ 34 bajo, ≥ 66 alto). Un neto positivo nunca se llama «corto»:
    «largo bajo, percentil 14» = los fondos están largos, pero mucho menos que de costumbre."""
    lado = "largo" if neto > 0 else "corto" if neto < 0 else "plano"
    nivel = "bajo" if pct <= COT_BAJO else "alto" if pct >= COT_ALTO else "medio"
    return f"{lado} {nivel}, percentil {pct}" if lado != "plano" else f"plano, percentil {pct}"


def criterios_cot(g, serie):
    """Cómo trata NEXORA el COT en cada módulo y qué voto saldría HOY con cada criterio (solo informativo: el voto de la tesis no cambia). No existe un criterio de voto común."""
    p = g["percentil_3a"]
    valores = [x[1] for x in serie] if serie else []
    p52 = round(sum(1 for v in valores[-52:] if v <= g["neto"]) / len(valores[-52:]) * 100) if len(valores) >= 20 else None
    cs = g["cambio_semana"]
    return [
        {"clave": "petroleo", "criterio": "Petróleo (este módulo, Fase 15)", "donde": "petroleo.py", "regla": f"percentil a 3 años del neto del dinero gestionado: ≥ {COT_ALTO} = +1; ≤ {COT_BAJO} = −1; si no, 0",
         "vota": True, "voto_hoy": 1 if p >= COT_ALTO else -1 if p <= COT_BAJO else 0, "dato": f"percentil 3 años {p}"},
        {"clave": "cot_py", "criterio": "Página Posicionamiento (COT)", "donde": "cot.py · _estado", "regla": "zonas del percentil a 3 años: ≥ 90 extremo largo, ≥ 70 largo elevado, ≤ 30 corto elevado, ≤ 10 extremo corto. Solo etiqueta, SIN voto; "
         "y se llama «largo/corto» por el percentil, no por el signo del neto (por eso un neto positivo con percentil bajo aparece como «CORTO ELEVADO»)", "vota": False,
         "voto_hoy": 1 if p >= 70 else -1 if p <= 30 else 0, "dato": f"percentil 3 años {p} → «{g.get('estado')}»"},
        {"clave": "oro", "criterio": "Oro (monitor)", "donde": "oro_xau.py · COT GOLD", "regla": "dirección = signo del cambio semanal del neto de managed money (↑/↓); el percentil de 52 semanas se muestra pero no entra; no puntúa",
         "vota": False, "voto_hoy": 1 if cs > 0 else -1 if cs < 0 else 0, "dato": f"cambio semanal {cs:+,}"},
        {"clave": "indices", "criterio": "Índices (monitor)", "donde": "indices.py · COT", "regla": "percentil de 52 semanas de los fondos apalancados: ≤ 10 «muy cortos», ≥ 90 «muy largos»; fuera de esos extremos «sin extremos»; no puntúa",
         "vota": False, "voto_hoy": 1 if (p52 is not None and p52 >= 90) else -1 if (p52 is not None and p52 <= 10) else (0 if p52 is not None else None), "dato": f"percentil 52 semanas {p52}" if p52 is not None else "SIN DATO"},
        {"clave": "contexto", "criterio": "Apetito/aversión al riesgo", "donde": "contexto.py · _senal_cot", "regla": "media del percentil 3 años de AUD, NZD, CAD, SPX, NDX y RUT menos la de JPY y CHF: ≥ +15 apetito, ≤ −15 aversión; no aplica al petróleo",
         "vota": False, "voto_hoy": None, "dato": "no aplica"},
    ]

def cot_wti(J):
    if not J:
        return {"estado": "SIN DATO", "motivo": "cot.json no disponible"}
    c = next((x for x in J.get("contratos", []) if x.get("clave") == "wti"), None)
    g = c and (c.get("gestores") or c.get("no_comerciales"))
    if not g:
        return {"estado": "SIN DATO", "motivo": "el contrato WTI no está en la última lectura de la CFTC"}
    voto = 1 if g["percentil_3a"] >= COT_ALTO else -1 if g["percentil_3a"] <= COT_BAJO else 0
    serie = g.get("serie", [])[-104:]
    return {"estado": "OK", "fecha": g["fecha"], "informe": g.get("informe") or "No comerciales (Legacy)", "neto": g["neto"], "largos": g["largos"], "cortos": g["cortos"], "cambio_semana": g["cambio_semana"],
            "percentil_3a": g["percentil_3a"], "min_3a": g["min_3a"], "max_3a": g["max_3a"], "etiqueta": etiqueta_cot(g["neto"], g["percentil_3a"]), "zona_cot_py": g.get("estado"), "voto": voto,
            "criterios": criterios_cot(g, serie), "serie": serie, "fuente": "CFTC · Disaggregated, WTI-PHYSICAL NYMEX (código 067651)"}


# ---------------------------------------------------------------- tesis
def tesis(precio, curva_, inv, cot):
    """Aplica las reglas fijas del encabezado. Devuelve votos, resultado, intensidad y qué lo confirmaría / invalidaría (con las cifras de hoy)."""
    v = {}
    v["precio"] = None if not precio else (1 if precio["valor"] > precio["sma200"] else -1)
    v["curva"] = None if not curva_ else (1 if curva_["estado"] == "ESCASEZ" else -1 if curva_["estado"] == "SOBRA" else 0)
    votos_inv = [x["voto"] for x in inv.values() if x and x.get("voto") is not None]
    suma_inv = sum(votos_inv)
    v["inventarios"] = None if not votos_inv else (1 if suma_inv >= 2 else -1 if suma_inv <= -2 else 0)
    v["cot"] = cot.get("voto") if cot.get("estado") == "OK" else None
    con_dato = [k for k, x in v.items() if x is not None]
    base = {"votos": v, "suma_inventarios": suma_inv if votos_inv else None, "factores_con_dato": len(con_dato)}
    if v["precio"] is None or len(con_dato) < MIN_DATOS:
        return {**base, "resultado": "SIN TESIS", "intensidad": None, "puntos": None, "motivo": "faltan datos: hacen falta el precio y al menos otros dos factores",
                "confirmaria": ["que lleguen datos de al menos tres factores"], "invalidaria": ["—"]}
    pts = sum(x for x in v.values() if x is not None)
    res = "ALCISTA" if pts >= 2 else "BAJISTA" if pts <= -2 else "SIN TESIS"
    inten = None
    if res != "SIN TESIS":
        sg = 1 if res == "ALCISTA" else -1
        inten = "FUERTE" if abs(pts) >= 3 and not any(x == -sg for x in v.values() if x is not None) else "DÉBIL"
    conf, inv_ = _condiciones(res, precio, curva_, inv, cot, v)
    return {**base, "resultado": res, "intensidad": inten, "puntos": pts, "motivo": None, "confirmaria": conf, "invalidaria": inv_}


def _n(x, d=1):
    return str(f"{x:.{d}f}").replace(".", ",")


def _condiciones(res, precio, curva_, inv, cot, v):
    sp = f"su media de 200 sesiones ({_n(precio['sma200'], 2)} $)" if precio else "su media de 200 sesiones"
    cr = inv.get("crudo") or {}
    par_t = "2.º–3.º" if (curva_ or {}).get("par_usado") == "2-3" else "1.º–2.º"
    if res == "ALCISTA":
        c = [f"el WTI se mantiene por encima de {sp}", f"el diferencial {par_t} sigue en backwardation (≥ +0,5 %)", "el próximo informe de la EIA muestra otra caída de inventarios de crudo"]
        i = [f"un cierre del WTI por debajo de {sp}", "la curva pasa a contango (≤ −0,5 %)", "los inventarios de crudo suben por encima de su media de 5 años + 2 %" + (f" (hoy {_n(cr['vs_media_5a_pct'], 1)} %)" if cr.get("vs_media_5a_pct") is not None else ""),
             f"el neto del dinero gestionado cae al percentil {COT_BAJO} o menos"]
    elif res == "BAJISTA":
        c = [f"el WTI se mantiene por debajo de {sp}", "la curva pasa o sigue en contango (≤ −0,5 %)", "el próximo informe de la EIA muestra una acumulación de inventarios de crudo"]
        i = [f"un cierre del WTI por encima de {sp}", "la curva pasa a backwardation (≥ +0,5 %)", "los inventarios de crudo caen por debajo de su media de 5 años − 2 %" + (f" (hoy {_n(cr['vs_media_5a_pct'], 1)} %)" if cr.get("vs_media_5a_pct") is not None else ""),
             f"el neto del dinero gestionado sube al percentil {COT_ALTO} o más"]
    else:
        pos = [k for k, x in v.items() if x == 1]
        neg = [k for k, x in v.items() if x == -1]
        c = [f"que al menos dos factores más voten en la misma dirección (hoy a favor: {', '.join(pos) or 'ninguno'}; en contra: {', '.join(neg) or 'ninguno'})"]
        i = ["—"]
    return c, i


def tesis_por_criterio(pw, cur, inv, cot, T):
    """Qué tesis saldría con el voto de COT de cada criterio de NEXORA (solo informativo: la tesis usa el de petróleo). Rellena cot['criterios'][i]['tesis_con_este_criterio']."""
    for c in cot.get("criterios") or []:
        if c.get("voto_hoy") is None:
            continue
        T2 = tesis(pw, cur, inv, {"estado": "OK", "voto": c["voto_hoy"]})
        c["tesis_con_este_criterio"] = {"resultado": T2["resultado"], "intensidad": T2["intensidad"], "puntos": T2["puntos"], "cambia": (T2["resultado"], T2["intensidad"]) != (T["resultado"], T["intensidad"])}


def comparar_brent(yahoo, fred_, umbral=UMBRAL_BRENT_PCT):
    """Yahoo BZ=F (futuro) frente a FRED DCOILBRENTEU (Brent fechado) del MISMO día: FRED va retrasado, así que se compara en la última fecha que tienen en común y se muestra la fecha
    de la última lectura de cada uno. Discrepancia si la diferencia de ese día supera el umbral (10 %)."""
    if not yahoo or not fred_:
        return None
    dy, df = dict(yahoo), dict(fred_)
    comunes = sorted(set(dy) & set(df))
    out = {"yahoo": {"valor": round(yahoo[-1][1], 2), "fecha": yahoo[-1][0].isoformat()}, "fred": {"valor": round(fred_[-1][1], 2), "fecha": fred_[-1][0].isoformat()},
           "retraso_fred_dias": (yahoo[-1][0] - fred_[-1][0]).days, "umbral_pct": umbral, "mismo_dia": None, "discrepancia": False}
    if comunes:
        d = comunes[-1]
        dif = round((dy[d] / df[d] - 1) * 100, 6)                  # redondeo: el umbral exacto (10 %) no depende del error de coma flotante
        out["mismo_dia"] = {"fecha": d.isoformat(), "yahoo": round(dy[d], 2), "fred": round(df[d], 2), "dif_pct": round(dif, 2), "dif_usd": round(dy[d] - df[d], 2)}
        out["discrepancia"] = abs(dif) > umbral
    return out


def registrar_discrepancia_brent(raiz, comp, ahora):
    """Abre (o cierra) una discrepancia BRENT en data/discrepancias.csv (la que muestra #/integridad). Solo-añadir: una comparación nueva cierra la anterior con una fila CERRADA."""
    import integridad as I
    if not comp or not comp.get("mismo_dia"):
        return []
    m = comp["mismo_dia"]
    stamp = ahora.strftime("%Y-%m-%d %H:%M UTC")
    filas = []
    previo = {k: r for k, r in I.discrepancias(raiz).items() if k[0] == "BRENT"}
    base = {"detectada_utc": stamp, "serie": "BRENT", "tipo": "VALOR", "fred_valor": m["fred"], "primaria": "Yahoo BZ=F (futuro)", "primaria_valor": m["yahoo"], "dif_pct": f"{abs(m['dif_pct']):.4f}"}
    for (serie, per, tipo), r in previo.items():
        if r["estado"] == "ABIERTA" and per != m["fecha"]:
            filas.append({**base, "id": f"BRENT|{per}|VALOR|{stamp}|CERRADA", "periodo": per, "estado": "CERRADA", "nota": f"sustituida por la comparación del {m['fecha']}"})
    ya = previo.get(("BRENT", m["fecha"], "VALOR"))
    if comp["discrepancia"] and (not ya or ya["estado"] != "ABIERTA"):
        filas.append({**base, "id": f"BRENT|{m['fecha']}|VALOR|{stamp}|ABIERTA", "periodo": m["fecha"], "estado": "ABIERTA",
                      "nota": (f"el mismo día ({m['fecha']}) el futuro BZ=F ({m['yahoo']}) y el Brent fechado de FRED ({m['fred']}) difieren {m['dif_pct']:+.1f} % (> {comp['umbral_pct']:g} %): puede ser físico frente a futuro "
                               "(escasez física) o un dato mal leído. Revisar; no se corrige ninguno")})
    elif not comp["discrepancia"] and ya and ya["estado"] == "ABIERTA":
        filas.append({**base, "id": f"BRENT|{m['fecha']}|VALOR|{stamp}|CERRADA", "periodo": m["fecha"], "estado": "CERRADA", "nota": "ya coinciden (diferencia por debajo del umbral)"})
    return I.anadir_csv(P(raiz, "data", "discrepancias.csv"), filas, I.CAMPOS_DISC, lambda r: r["id"])


def causa_efecto(precio, curva_, inv, T):
    """Líneas deterministas «causa → efecto» para la tarjeta de #/resumen. Solo cifras de hoy; sin consejo."""
    out = []
    if curva_:
        o1, o2 = ("2.º", "3.º") if curva_.get("par_usado") == "2-3" else ("1.er", "2.º")
        out.append(("Curva " + curva_["estado"].lower(), f"el {o1} vencimiento ({nombre_contrato(curva_['m1'])}) cotiza {_n(curva_['diferencial'], 2)} $ ({_n(curva_['diferencial_pct'], 2)} %) frente al {o2} ({nombre_contrato(curva_['m2'])}): " + (
            "el mercado paga por tener petróleo ya (escasez a corto plazo)" if curva_["estado"] == "ESCASEZ" else "el mercado paga por tener petróleo más tarde (sobra a corto plazo)" if curva_["estado"] == "SOBRA" else "sin prima clara entre vencimientos")))
    cr = inv.get("crudo")
    if cr and cr.get("vs_media_5a_pct") is not None:
        out.append(("Inventarios de crudo", f"{_n(cr['valor_mb'], 1)} Mb, {_n(cr['vs_media_5a_pct'], 1)} % frente a su media de 5 años y {_n(cr['cambio_semana_mb'], 1)} Mb en la semana: " + (
            "por debajo de lo habitual (menos colchón de oferta)" if cr["vs_media_5a_pct"] < -UMBRAL_INV_PCT else "por encima de lo habitual (más colchón)" if cr["vs_media_5a_pct"] > UMBRAL_INV_PCT else "en la media")))
    if precio:
        out.append(("Precio frente a su media de 200", f"WTI {_n(precio['valor'], 2)} $, {_n(precio['dist_sma200_pct'], 1)} % frente a {_n(precio['sma200'], 2)} $: " + ("tendencia de fondo al alza" if precio["valor"] > precio["sma200"] else "tendencia de fondo a la baja")))
    return out


# ---------------------------------------------------------------- gasolina y consumo
def gasolina(pts, consumo_json=None):
    if not pts or len(pts) < 55:
        return {"estado": "SIN DATO"}
    u = pts[-1]
    ref4 = pts[-5] if len(pts) > 5 else None
    ya = min(pts, key=lambda x: abs((x[0] - (u[0] - dt.timedelta(days=364))).days))
    out = {"estado": "OK", "valor": round(u[1], 3), "fecha": u[0].isoformat(), "cambio_4s_pct": round((u[1] / ref4[1] - 1) * 100, 1) if ref4 else None,
           "interanual_pct": round((u[1] / ya[1] - 1) * 100, 1) if abs((ya[0] - (u[0] - dt.timedelta(days=364))).days) <= 7 else None, "serie": [[d.isoformat(), round(v, 3)] for d, v in pts[-104:]],
           "fuente": "FRED GASREGW (EIA): precio medio semanal de la gasolina regular en EE. UU. ($/galón)"}
    T = (consumo_json or {}).get("tesis") or {}
    out["consumo"] = {"tesis": T.get("resultado"), "intensidad": T.get("intensidad"), "fecha": (consumo_json or {}).get("fecha_datos")} if T else None
    return out


# ---------------------------------------------------------------- construcción
def _intentar(err, clave, fn, defecto=None):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        err[clave] = f"{type(e).__name__}: {str(e)[:120]}"
        return defecto


def construir(fuentes=None, ahora=None, raiz=None):
    """fuentes = {'yahoo': fn(sym, rango, minimo), 'fred': fn(sid, desde), 'eia': fn(url) → texto, 'cot': fn() → dict, 'consumo': fn() → dict}. Cada fuente falla por separado."""
    raiz = raiz or RAIZ
    ahora = ahora or dt.datetime.now(UTC)
    hoy = ahora.date()
    F = {"yahoo": yahoo, "fred": fred, "eia": _get, "cot": lambda: cot_json(raiz), "consumo": lambda: _leer(P(raiz, "site", "data", "consumo.json")), **(fuentes or {})}
    err = {}
    desde2 = (hoy - dt.timedelta(days=800)).isoformat()
    wti = _intentar(err, "yahoo_CL=F", lambda: F["yahoo"]("CL=F", "2y", 200), [])
    brent = _intentar(err, "yahoo_BZ=F", lambda: F["yahoo"]("BZ=F", "2y", 200), [])
    xle = _intentar(err, "yahoo_XLE", lambda: F["yahoo"]("XLE", "2y", 70), [])
    dxy = _intentar(err, "yahoo_DXY", lambda: F["yahoo"]("DX-Y.NYB", "2y", 70), [])
    f_wti = _intentar(err, "fred_DCOILWTICO", lambda: F["fred"]("DCOILWTICO", desde2), [])
    f_brent = _intentar(err, "fred_DCOILBRENTEU", lambda: F["fred"]("DCOILBRENTEU", desde2), [])
    if not wti and f_wti:                                    # respaldo: FRED (con retraso; la fecha del dato se muestra siempre)
        wti = f_wti
    if not brent and f_brent:
        brent = f_brent
    fuente_wti = "Yahoo Finance (CL=F, futuro continuo del primer vencimiento)" if (wti and wti is not f_wti) else "FRED DCOILWTICO (respaldo: Yahoo no respondió; precio al contado con retraso)"
    fuente_brent = "Yahoo Finance (BZ=F, futuro)" if (brent and brent is not f_brent) else "FRED DCOILBRENTEU (respaldo: Yahoo no respondió; Brent fechado con retraso)"
    pw, pb = metricas_precio(wti) if wti else None, metricas_precio(brent) if brent else None
    # segunda fuente: FRED frente a Yahoo en la última fecha común
    seg = {}
    for nom, y, f in (("wti", wti, f_wti), ("brent", brent, f_brent)):
        if y and f and y is not f:
            comunes = sorted(set(dict(y)) & set(dict(f)))
            if comunes:
                d = comunes[-1]
                a, b = dict(y)[d], dict(f)[d]
                seg[nom] = {"fecha": d.isoformat(), "yahoo": round(a, 2), "fred": round(b, 2), "dif_pct": round((a / b - 1) * 100, 2)}
    seg_nota = {"wti": "FRED trae el precio al contado de Cushing y Yahoo el futuro del primer vencimiento: en backwardation el contado queda por encima del futuro.",
                "brent": "FRED trae el Brent FECHADO (físico, Dated Brent) y Yahoo el futuro BZ=F: en escasez física el fechado puede cotizar muy por encima del futuro. No es un error de dato."}
    # curva con contratos reales
    series_ct = {}
    for c in contratos(hoy, atras_meses=1, adelante_meses=3):
        if c[3] < hoy:                                       # los contratos vencidos ya no están en Yahoo
            continue
        s = _intentar(err, "yahoo_" + c[2], lambda c=c: F["yahoo"](c[2], "2y", 5), None)
        if s:
            series_ct[c[2]] = s
        if F["yahoo"] is yahoo:
            time.sleep(0.4)
    cur = curva(series_ct, hoy) if series_ct else None
    pw, tk_clf, aviso_roll = ajustar_roll(pw, wti, series_ct)
    if not cur and not err.get("curva"):
        err["curva"] = "sin contratos mensuales de WTI en Yahoo: la curva queda en SIN DATO"
    prop = historico_propio(raiz, cur, ahora)
    if cur:
        cur["historico_propio"] = prop
    # inventarios EIA
    clave_api = os.environ.get("EIA_API_KEY") or None
    inv, origen_eia = {}, None
    for k, (sid, nombre) in EIA_SERIES.items():
        r = _intentar(err, "eia_" + sid, lambda sid=sid: eia_serie(sid, F["eia"], clave_api), None)
        if r:
            origen_eia = r[1]
            iv = inventario(r[0])
            inv[k] = {**iv, "nombre": nombre, "serie_id": sid} if iv else None
        else:
            inv[k] = None
    cot = cot_wti(_intentar(err, "cot", F["cot"], None))
    t5 = _intentar(err, "fred_T5YIE", lambda: F["fred"]("T5YIE", desde2), [])
    gas = _intentar(err, "fred_GASREGW", lambda: F["fred"]("GASREGW", (hoy - dt.timedelta(days=900)).isoformat()), [])
    rel = relaciones(wti, t5, dxy, xle) if wti else {"wti_cambio_3m_pct": None, "filas": []}
    T = tesis(pw, cur, inv, cot)
    tesis_por_criterio(pw, cur, inv, cot, T)
    brent_cmp = comparar_brent(brent if brent is not f_brent else None, f_brent)
    if brent_cmp:
        try:
            registrar_discrepancia_brent(raiz, brent_cmp, ahora)
        except Exception as e:  # noqa: BLE001
            err["brent_discrepancia"] = f"{type(e).__name__}: {str(e)[:80]}"
    exc = excepciones_eia(raiz)
    sem, fecha_pub, hm_pub = proxima_publicacion(exc, hoy) or (None, None, None)
    ult_eia = (inv.get("crudo") or {}).get("semana")
    return {"version": 1, "ok": True, "generado_utc": ahora.strftime("%Y-%m-%d %H:%M UTC"), "fecha_datos": pw["fecha"] if pw else None,
            "precios": {"wti": pw and {**pw, "fuente": fuente_wti, "contrato_cl_f": tk_clf, "aviso_empalme": aviso_roll}, "wti_spot_serie": [[d.isoformat(), v] for d, v in f_wti[-560:]], "brent": pb and {**pb, "fuente": fuente_brent}, "segunda_fuente": seg, "segunda_fuente_nota": seg_nota, "brent_comparacion": brent_cmp,
                        "spread_brent_wti": (round(pb["valor"] - pw["valor"], 2) if pw and pb else None)},
            "graficos": {"wti": grafico(wti) if wti and len(wti) >= 200 else None, "brent": grafico(brent) if brent and len(brent) >= 200 else None},
            "curva": cur, "inventarios": {**inv, "origen": origen_eia, "con_clave_api": bool(clave_api), "ultima_semana": ult_eia,
                                          "proximo_informe": ({"semana": sem.isoformat(), "fecha": fecha_pub.isoformat(), "hora_et": hm_pub} if sem else None)},
            "plataformas": {"estado": "SIN DATO", "motivo": BAKER_SIN_DATO, "fuente": "Baker Hughes · North America Rotary Rig Count (semanal)", "url": "https://rigcount.bakerhughes.com/na-rig-count"},
            "cot": cot, "gasolina": gasolina(gas, F["consumo"]() if F.get("consumo") else None), "relaciones": rel,
            "tesis": {**T, "causa_efecto": causa_efecto(pw, cur, inv, T)}, "reglas": [x.strip() for x in __doc__.split("cada uno vota +1 / 0 / −1:")[1].strip().split("\n  ") if x.strip()],
            "errores": err, "fuentes": "Yahoo Finance (CL=F, BZ=F, contratos CL<mes><año>.NYM, XLE, DXY) · FRED (DCOILWTICO, DCOILBRENTEU, GASREGW, T5YIE) · EIA (Weekly Petroleum Status Report) · CFTC (WTI-PHYSICAL)"}


def _leer(ruta):
    try:
        return json.load(open(ruta, encoding="utf-8"))
    except (OSError, ValueError):
        return None


def etapa():
    return construir()


def bloque_contexto(raiz=RAIZ):
    J = _leer(P(raiz, "site", "data", "petroleo.json"))
    if not J:
        return {"estado": "SIN DATO", "fuente": "petroleo.py"}
    T, p, c = J.get("tesis") or {}, (J.get("precios") or {}).get("wti") or {}, J.get("curva") or {}
    inv = J.get("inventarios") or {}
    return {"fecha": J.get("fecha_datos"), "wti": p.get("valor"), "brent": ((J.get("precios") or {}).get("brent") or {}).get("valor"),
            "tesis": {"resultado": T.get("resultado"), "intensidad": T.get("intensidad"), "puntos": T.get("puntos"), "votos": T.get("votos")},
            "curva": {"estado": c.get("estado"), "diferencial_pct": c.get("diferencial_pct")} if c else "SIN DATO",
            "inventarios_crudo": {k: (inv.get("crudo") or {}).get(k) for k in ("semana", "valor_mb", "cambio_semana_mb", "vs_media_5a_pct")} if inv.get("crudo") else "SIN DATO",
            "cot_wti_percentil_3a": (J.get("cot") or {}).get("percentil_3a"), "plataformas_baker_hughes": "SIN DATO",
            "que_lo_confirmaria": T.get("confirmaria"), "que_lo_invalidaria": T.get("invalidaria"),
            "nota": "Tesis de petróleo por reglas fijas (precio, curva, inventarios, COT). Hecho e interpretación separados; no es una recomendación de compra o venta.", "fuente": "petroleo.py (petroleo.json)"}


if __name__ == "__main__":
    J = construir()
    with open(P(RAIZ, "site", "data", "petroleo.json"), "w", encoding="utf-8") as f:
        json.dump(J, f, ensure_ascii=False, indent=1)
    t = J["tesis"]
    print("TESIS:", t["resultado"], t.get("intensidad"), "| puntos", t.get("puntos"), "| votos", t["votos"], "| errores:", J["errores"] or "ninguno")
