"""Confianza del consumidor (U. Michigan): fuente PRIMARIA = tablas públicas de la propia Universidad (sca.isr.umich.edu); FRED (UMCSENT) = respaldo y segunda fuente.

Por qué: FRED publica UMCSENT con 1-2 meses de retraso por licencia; Michigan publica el preliminar a mitad de mes y el final dos semanas después.
Fuentes (URLs verificadas en la página «Tables and CSVs», sca.isr.umich.edu/tables.html):
  · /files/tbmics.csv  Mes,Año,ICS_ALL  → histórico mensual, datos FINALES.
  · /files/tbcics.csv  tabla «Current» → últimos 12 meses; el mes en curso lleva «(P)» = preliminar (p. ej. «October (P),2026,,,46.3»).
  · portada /          «Preliminary|Final Results for <mes> <año>» y «Next data release: <día>, <fecha> for Preliminary|Final <mes> data at 10am ET».
La web de Michigan NO publica un calendario de lanzamientos ni la fecha de un dato ya salido: la fecha de publicación solo se conoce si NEXORA la anotó antes
(línea «Next data release» de la portada o calendario de FRED, release 91, para los finales); si no, SIN DATO (no se infiere).

Ficheros (solo-añadir): data/michigan.csv (cada lectura nueva de un periodo y tipo, con la hora en que NEXORA la vio),
data/michigan_calendario.csv (fechas de publicación anunciadas). Nada se estima.
"""
import csv
import datetime as dt
import io
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(HERE)
UTC = dt.timezone.utc
BASE = "https://www.sca.isr.umich.edu"
URL_MENSUAL, URL_ACTUAL, URL_PORTADA = BASE + "/files/tbmics.csv", BASE + "/files/tbcics.csv", BASE + "/"
FUENTE = "Universidad de Michigan (sca.isr.umich.edu)"
UMBRAL_ANTIGUEDAD_DIAS = 45        # ámbar si el dato tiene más de 45 días
UMBRAL_DIF_PCT = 0.05              # mismo umbral que las demás segundas fuentes
DESDE_REGISTRO = "2025-01-01"      # el registro solo guarda los meses recientes (el histórico completo se descarga cada vez)
MESES_EN = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
CAMPOS_REG = ["periodo", "tipo", "valor", "fuente", "capturado_utc"]
CAMPOS_CAL = ["fecha", "hora_et", "tipo", "periodo", "fuente", "visto_utc"]


def P(raiz, *a):
    return os.path.join(raiz, *a)


def _get(url, t=40):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (nexora-terminal; datos publicos)"})
    return urllib.request.urlopen(req, timeout=t).read().decode("utf-8-sig", "replace")


def texto_periodo(p):
    return f"{MESES[p.month - 1]} {p.year}"


def _mes(nombre):
    n = re.sub(r"\(.*?\)", "", nombre).strip().lower()
    return MESES_EN.index(n) + 1 if n in MESES_EN else None


# ---------------------------------------------------------------- lectura de las tres páginas
def parse_mensual(texto):
    """tbmics.csv → [(fecha, valor)] (final). Las filas antiguas son trimestrales; se leen todas tal cual vienen."""
    out = []
    for r in csv.reader(io.StringIO(texto)):
        if len(r) < 3 or not r[1].strip().isdigit():
            continue
        m = _mes(r[0])
        try:
            v = float(r[2])
        except ValueError:
            continue
        if m:
            out.append((dt.date(int(r[1]), m, 1), v))
    return out


def parse_actual(texto):
    """tbcics.csv → [(fecha, valor, tipo)], tipo = «preliminar» si el mes lleva «(P)», si no «final»."""
    out = []
    for r in csv.reader(io.StringIO(texto)):
        if len(r) < 5 or not r[1].strip().isdigit():
            continue
        m = _mes(r[0])
        try:
            v = float(r[4])
        except ValueError:
            continue
        if m:
            out.append((dt.date(int(r[1]), m, 1), v, "preliminar" if "(P)" in r[0].upper() else "final"))
    return out


def parse_portada(html):
    """Portada → {'resultados': {'tipo', 'periodo'}, 'proximo': {'fecha', 'hora_et', 'tipo', 'periodo'}}; lo que no aparece queda en None."""
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    out = {"resultados": None, "proximo": None}
    m = re.search(r"(Preliminary|Final) Results for ([A-Za-z]+) (\d{4})", txt)
    if m and _mes(m.group(2)):
        out["resultados"] = {"tipo": "preliminar" if m.group(1) == "Preliminary" else "final", "periodo": dt.date(int(m.group(3)), _mes(m.group(2)), 1).isoformat()}
    m = re.search(r"Next data release:\s*(?:[A-Za-z]+,\s*)?([A-Za-z]+) (\d{1,2}), (\d{4}) for (Preliminary|Final) ([A-Za-z]+) data(?: at (\d{1,2})(?::(\d{2}))?\s*(am|pm)\s*ET)?", txt)
    if m and _mes(m.group(1)) and _mes(m.group(5)):
        f = dt.date(int(m.group(3)), _mes(m.group(1)), int(m.group(2)))
        pm = _mes(m.group(5))
        hora = None
        if m.group(6):
            h = int(m.group(6)) % 12 + (12 if m.group(8) == "pm" else 0)
            hora = f"{h:02d}:{int(m.group(7) or 0):02d}"
        out["proximo"] = {"fecha": f.isoformat(), "hora_et": hora, "tipo": "preliminar" if m.group(4) == "Preliminary" else "final",
                          "periodo": dt.date(f.year - (1 if pm > f.month else 0), pm, 1).isoformat()}
    return out


def combinar(mensual, actual):
    """Serie única [(fecha, valor, tipo)]: histórico final + últimos 12 meses (la tabla «Current» manda donde coinciden, porque marca el preliminar)."""
    d = {f: (v, "final") for f, v in mensual}
    for f, v, t in actual:
        d[f] = (v, t)
    return [(f, v, t) for f, (v, t) in sorted(d.items())]


def leer(red=None):
    """Descarga las tres páginas. Cada una falla por separado. → {'serie': [(fecha, valor, tipo)], 'portada': {...}, 'errores': {...}}"""
    red = red or _get
    err, mensual, actual, portada = {}, [], [], {"resultados": None, "proximo": None}
    for nombre, url, fn in (("tbmics", URL_MENSUAL, parse_mensual), ("tbcics", URL_ACTUAL, parse_actual), ("portada", URL_PORTADA, parse_portada)):
        try:
            r = fn(red(url))
            if not r or (nombre == "portada" and not (r["resultados"] or r["proximo"])):
                raise ValueError("la página no tiene el formato esperado")
            if nombre == "tbmics":
                mensual = r
            elif nombre == "tbcics":
                actual = r
            else:
                portada = r
        except Exception as e:  # noqa: BLE001
            err[nombre] = f"{type(e).__name__}: {str(e)[:100]}"
    return {"serie": combinar(mensual, actual), "portada": portada, "errores": err}


# ---------------------------------------------------------------- registro y calendario (solo-añadir)
def _csv(ruta):
    if not os.path.exists(ruta):
        return []
    with open(ruta, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _anadir(ruta, filas, campos, clave):
    import integridad as I
    return I.anadir_csv(ruta, filas, campos, clave)


def registro(raiz):
    return _csv(P(raiz, "data", "michigan.csv"))


def calendario(raiz):
    """Fechas de publicación conocidas: michigan_calendario.csv + eventos de Michigan del calendario de FRED (solo finales; hora 10:00 ET por la propia web)."""
    out = {}
    try:
        C = json.load(open(P(raiz, "site", "data", "calendario.json"), encoding="utf-8")).get("eventos") or []
    except (OSError, ValueError):
        C = []
    for e in C:
        if "michigan" in (e.get("evento") or "").lower() and e.get("fecha"):
            f = dt.date.fromisoformat(e["fecha"])
            out[(f.isoformat(), "final")] = {"fecha": f.isoformat(), "hora_et": e.get("hora_ny") or "10:00", "tipo": "final", "periodo": dt.date(f.year, f.month, 1).isoformat(), "fuente": "FRED Release Calendar"}
    for r in _csv(P(raiz, "data", "michigan_calendario.csv")):
        out[(r["fecha"], r["tipo"])] = r
    return sorted(out.values(), key=lambda x: x["fecha"])


def fecha_publicacion(raiz, periodo, tipo):
    """Fecha anunciada del lanzamiento de (periodo, tipo), o None."""
    return next((e["fecha"] for e in calendario(raiz) if e["periodo"] == periodo and e["tipo"] == tipo), None)


def actualizar(raiz=RAIZ, ahora=None, red=None, forzar=False):
    """Descarga Michigan, anota lecturas nuevas y fechas anunciadas (solo-añadir) y devuelve el resultado de leer() + 'nuevas'. Con red=None usa la red real."""
    ahora = ahora or dt.datetime.now(UTC)
    L = leer(red)
    stamp = ahora.strftime("%Y-%m-%d %H:%M UTC")
    filas = [{"periodo": f.isoformat(), "tipo": t, "valor": v, "fuente": FUENTE, "capturado_utc": stamp} for f, v, t in L["serie"] if f.isoformat() >= DESDE_REGISTRO]
    L["nuevas"] = _anadir(P(raiz, "data", "michigan.csv"), filas, CAMPOS_REG, lambda r: (r["periodo"], r["tipo"])) if L["serie"] else []
    pr = L["portada"].get("proximo")
    if pr:
        _anadir(P(raiz, "data", "michigan_calendario.csv"), [{**pr, "fuente": "sca.isr.umich.edu (Next data release)", "visto_utc": stamp}], CAMPOS_CAL, lambda r: (r["fecha"], r["tipo"]))
    return L


def hay_pendiente(raiz, ahora):
    """True si algún lanzamiento anunciado está en su ventana (2-48 h después de la hora) y sin registrar → conviene descargar. Sirve para no pedir la web cada hora."""
    return bool(pendientes(raiz, ahora))


def pendientes(raiz, ahora):
    """[(tipo, periodo (date), t_evento UTC, fecha, fuente)] lanzamientos de Michigan publicados hace 2-48 h y no registrados. Un preliminar queda cubierto si ya consta el final de ese mes."""
    from zoneinfo import ZoneInfo
    NY = ZoneInfo("America/New_York")
    reg = {(r["periodo"], r["tipo"]) for r in registro(raiz)}
    out = []
    for e in calendario(raiz):
        h, m = map(int, (e.get("hora_et") or "10:00").split(":"))
        t = dt.datetime.combine(dt.date.fromisoformat(e["fecha"]), dt.time(h, m), NY).astimezone(UTC)
        dt_h = (ahora - t).total_seconds() / 3600
        if not (2 <= dt_h <= 48):
            continue
        if (e["periodo"], e["tipo"]) in reg or (e["tipo"] == "preliminar" and (e["periodo"], "final") in reg):
            continue
        out.append((e["tipo"], dt.date.fromisoformat(e["periodo"]), t, e["fecha"], e.get("fuente") or ""))
    return out


# ---------------------------------------------------------------- estado para la web (consumo + integridad)
def antiguedad(periodo, hoy):
    """Días desde el cierre del mes de referencia (0 si el mes no ha terminado)."""
    fin = dt.date(periodo.year + periodo.month // 12, periodo.month % 12 + 1, 1) - dt.timedelta(days=1)
    return max(0, (hoy - fin).days)


def estado(raiz, serie, fred, ahora, errores=None):
    """Estado del dato de ánimo: último valor (con su tipo), último final, fechas, antigüedad y contraste con FRED.
    serie = [(fecha, valor, tipo)] de Michigan (puede estar vacía); fred = [(fecha, valor)] o []."""
    hoy = ahora.date()
    reg = {}
    for r in registro(raiz):
        reg.setdefault((r["periodo"], r["tipo"]), r["capturado_utc"])
    base = {"fuente_primaria": FUENTE, "umbral_antiguedad_dias": UMBRAL_ANTIGUEDAD_DIAS, "errores": errores or {}}
    if serie:
        f, v, t = serie[-1]
        ult = {"periodo": f.isoformat(), "texto": texto_periodo(f), "tipo": t, "valor": round(v, 1), "publicado": fecha_publicacion(raiz, f.isoformat(), t),
               "visto_utc": reg.get((f.isoformat(), t))}
        fin = next(((a, b) for a, b, c in reversed(serie) if c == "final"), None)
        ultf = None if not fin else {"periodo": fin[0].isoformat(), "texto": texto_periodo(fin[0]), "valor": round(fin[1], 1), "publicado": fecha_publicacion(raiz, fin[0].isoformat(), "final"),
                                     "visto_utc": reg.get((fin[0].isoformat(), "final"))}
        edad = antiguedad(f, hoy)
        base.update({"origen": "michigan", "ultimo": ult, "ultimo_final": ultf, "antiguedad_dias": edad, "ambar": edad > UMBRAL_ANTIGUEDAD_DIAS})
    elif fred:
        f, v = fred[-1]
        edad = antiguedad(f, hoy)
        base.update({"origen": "fred", "ultimo": {"periodo": f.isoformat(), "texto": texto_periodo(f), "tipo": "final", "valor": round(v, 1), "publicado": None, "visto_utc": None},
                     "ultimo_final": None, "antiguedad_dias": edad, "ambar": edad > UMBRAL_ANTIGUEDAD_DIAS})
    else:
        return {**base, "origen": None, "ultimo": None, "ultimo_final": None, "antiguedad_dias": None, "ambar": False, "fred": None, "estado": "SIN DATO"}
    base["estado"] = "OK"
    base["fred"] = None
    if fred:
        ff, fv = fred[-1]
        comunes = {a: b for a, b, c in serie if c == "final"}
        base["fred"] = {"periodo": ff.isoformat(), "texto": texto_periodo(ff), "valor": round(fv, 1), "antiguedad_dias": antiguedad(ff, hoy),
                        "meses_de_retraso": ((serie[-1][0].year - ff.year) * 12 + serie[-1][0].month - ff.month) if serie else None,
                        "coincide": (None if ff not in comunes else abs(comunes[ff] - fv) / comunes[ff] * 100 <= UMBRAL_DIF_PCT),
                        "michigan_mismo_periodo": comunes.get(ff)}
    return base


def cotejar_fred(raiz, serie, fred, ahora):
    """Segunda fuente: FRED contra Michigan en el último periodo FINAL que tienen en común (FRED solo trae finales). Abre/cierra discrepancias en data/discrepancias.csv."""
    import integridad as I
    if not serie or not fred:
        return []
    mich = {f: v for f, v, t in serie if t == "final"}
    comunes = [(f, v) for f, v in fred if f in mich]
    if not comunes:
        return []
    f, fv = comunes[-1]
    mv = mich[f]
    dif = abs(fv - mv) / mv * 100
    hay = dif > UMBRAL_DIF_PCT
    stamp = ahora.strftime("%Y-%m-%d %H:%M UTC")
    ya = I.discrepancias(raiz).get(("UMCSENT", f.isoformat(), "VALOR"))
    base = {"detectada_utc": stamp, "serie": "UMCSENT", "periodo": f.isoformat(), "tipo": "VALOR", "fred_valor": fv, "primaria": "U. Michigan (sca.isr.umich.edu)", "primaria_valor": mv, "dif_pct": f"{dif:.4f}"}
    filas = []
    if hay and (not ya or ya["estado"] != "ABIERTA"):
        filas.append({**base, "id": f"UMCSENT|{f.isoformat()}|VALOR|{stamp}|ABIERTA", "estado": "ABIERTA", "nota": "diferencia entre FRED y la Universidad de Michigan para el mismo periodo. Manda Michigan."})
    elif not hay and ya and ya["estado"] == "ABIERTA":
        filas.append({**base, "id": f"UMCSENT|{f.isoformat()}|VALOR|{stamp}|CERRADA", "estado": "CERRADA", "nota": "ya coinciden"})
    return I.anadir_csv(P(raiz, "data", "discrepancias.csv"), filas, I.CAMPOS_DISC, lambda r: r["id"])


if __name__ == "__main__":
    L = actualizar()
    print("últimos:", [(f.isoformat()[:7], v, t) for f, v, t in L["serie"][-3:]], "· portada:", L["portada"], "· errores:", L["errores"] or "ninguno", "· nuevas:", len(L["nuevas"]))
    sys.exit(0)
