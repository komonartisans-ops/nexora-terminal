"""NEXORA · TONO HAWKISH / DOVISH de Fed, BCE y BoJ. Solo webs oficiales de los bancos, diccionario de términos fijo, sin IA.

Qué mide: cuánto del vocabulario de un comunicado o discurso pertenece a un diccionario «hawkish» (endurecimiento, inflación alta,
riesgos al alza) frente a otro «dovish» (relajación, debilidad, riesgos a la baja). Es una lectura léxica: no entiende contexto ni ironía.

CRITERIO NEXORA (fijo, definido antes de mirar los resultados, no optimizado)
  · Puntuación de un texto = (H − D) / (H + D), con H y D = suma de pesos de los términos hawkish y dovish encontrados. Rango −1 … +1.
    Sin ningún término: SIN PUNTUACIÓN. Densidad = (H − D) por cada 1.000 palabras (solo informativa).
  · Se buscan las frases más largas primero y cada trozo de texto puntúa una sola vez.
  · Nivel: HAWKISH si ≥ +0,20 · DOVISH si ≤ −0,20 · NEUTRAL si no.   Cambio: ≥ +0,10 más hawkish · ≤ −0,10 más dovish · si no, SIN CAMBIO.
  · Discurso: puntúa solo si trae ≥ 4 términos del diccionario y ≥ 3 menciones de «monetary policy» o «inflation» (los de supervisión no puntúan).
  · Decisión de tipos = variación del tipo de política del BIS entre el día anterior a la reunión y 10 días después: SUBE ≥ +0,10 pp, BAJA ≤ −0,10 pp.
Validación obligatoria: tono de cada comunicado desde 2015 frente a la decisión de la reunión SIGUIENTE; se publica el % de aciertos, el tamaño
de la muestra y las líneas base (siempre «mantiene» y «repetir la decisión anterior»), tanto si el tono ayuda como si no.

Memoria permanente: data/tono_comunicados.csv y data/tono_discursos.csv (puntuación y términos de cada documento; el texto no se guarda)."""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import html
import io
import json
import re
import statistics

import bancos
import csvlog
import fuentes

DESDE_COMUNICADOS = 2015
DESDE_DISCURSOS = dt.date(2025, 1, 1)
UMBRAL_NIVEL = 0.20
UMBRAL_CAMBIO = 0.10
MIN_TERMINOS_DISCURSO = 4
MIN_MENCIONES_TEMA = 3
UMBRAL_DECISION = 0.10
VENTANA_DECISION = 10          # días tras la reunión en que se mide la variación del tipo
MAX_NUEVOS = 400
URL_ECB_CSV = "https://www.ecb.europa.eu/press/key/shared/data/all_ECB_speeches.csv"

# ---------------------------------------------------------------- diccionario (versionado)
HAWKISH = {
    2: ["further tightening", "additional tightening", "additional policy firming", "further policy firming", "policy firming", "firming",
        "tighter monetary policy", "tighten", "tightening", "tightened", "restrictive", "sufficiently restrictive", "more restrictive",
        "increase the target range", "raise the target range", "raised the target range", "increased the target range",
        "raise interest rates", "raise the policy rate", "raised the policy rate", "increase interest rates", "increased interest rates",
        "raise the key interest rates", "raise the three key", "raising the policy rate", "raise the guideline", "hike", "hikes", "rate increase", "rate increases",
        "further increases", "additional increases", "further rate increases", "upside risks", "upside risk", "elevated inflation",
        "inflation remains elevated", "inflation remained elevated", "inflation is too high", "inflation remains too high", "too high",
        "inflationary pressures", "price pressures", "persistent inflation", "inflation persistence", "wage pressures", "tight labor market",
        "tight labour market", "labor market remains tight", "overheating", "vigilant", "vigilance", "premature", "normalization", "normalisation",
        "reduce the degree of monetary accommodation", "remove policy accommodation", "remove monetary accommodation", "less accommodative",
        "gradually adjust the degree of monetary easing", "adjust the degree of monetary easing", "continue to raise", "will raise", "inflation above target"],
    1: ["strong", "solid", "robust", "resilient", "firm", "expanded at a solid pace", "above target", "upward pressure", "upward pressures",
        "reducing its holdings", "balance sheet reduction", "runoff", "quantitative tightening", "highly attentive", "determined", "gradual", "raise",
        "raising", "higher inflation", "strong labor market", "price stability is at risk"],
}
DOVISH = {
    2: ["cut", "cuts", "lower the target range", "reduce the target range", "lowered the target range", "reduced the target range", "cut the policy rate",
        "lower interest rates", "reduce interest rates", "lowered interest rates", "lower the three key", "lower the key interest rates", "rate cut", "rate cuts",
        "easing", "ease", "eased", "eases", "monetary easing", "accommodative", "accommodation", "highly accommodative", "downside risks", "downside risk",
        "weakening", "weakened", "weaker", "slowdown", "slowing", "slowed", "softening", "softened", "subdued", "sluggish", "deterioration",
        "deteriorated", "contraction", "recession", "negative interest rate", "quantitative easing", "asset purchase programme", "asset purchases",
        "stimulus", "patient", "patience", "downward", "disinflation", "disinflationary", "inflation has eased", "inflation has moderated",
        "unemployment has moved up", "unemployment rate has moved up", "lower for longer", "below target", "below the 2 percent", "well below"],
    1: ["support", "supportive", "moderate", "moderated", "moderating", "uncertainty", "uncertain", "wait", "reinvest", "reinvestment", "soft",
        "lower inflation", "fall in inflation", "decline in inflation", "cooling", "cooled"],
}


def _terminos():
    out = []
    for peso, ts in HAWKISH.items():
        out += [(t, +peso, "hawkish") for t in ts]
    for peso, ts in DOVISH.items():
        out += [(t, peso, "dovish") for t in ts]
    return sorted(set(out), key=lambda x: (-len(x[0]), x[0]))


TERMINOS = _terminos()
VERSION = "1." + hashlib.sha1(json.dumps(TERMINOS, ensure_ascii=False).encode()).hexdigest()[:8]
_RE = [(re.compile(r"(?<![a-z])" + re.escape(t) + r"(?![a-z])"), t, p, k) for t, p, k in TERMINOS]


def puntuar(texto):
    """→ dict con h, d, indice (None si no hay términos), palabras, densidad y {término: veces}."""
    t = texto.lower()
    t = re.sub(r"[‘’´`]", "'", t)
    usado = bytearray(len(t))
    h = d = 0
    cuenta = {}
    for rx, term, peso, tipo in _RE:
        for m in rx.finditer(t):
            a, b = m.span()
            if any(usado[a:b]):
                continue
            usado[a:b] = b"\x01" * (b - a)
            cuenta[term] = cuenta.get(term, 0) + 1
            if tipo == "hawkish":
                h += peso
            else:
                d += peso
    palabras = len(re.findall(r"[a-z']+", t))
    indice = round((h - d) / (h + d), 3) if (h + d) else None
    return {"h": h, "d": d, "indice": indice, "palabras": palabras, "densidad": round((h - d) / palabras * 1000, 2) if palabras else None,
            "terminos": cuenta, "n_terminos": sum(cuenta.values()),
            "menciones_tema": len(re.findall(r"monetary policy|inflation", t))}


def nivel(i):
    if i is None:
        return None
    return "HAWKISH" if i >= UMBRAL_NIVEL else "DOVISH" if i <= -UMBRAL_NIVEL else "NEUTRAL"


def cambio_txt(c):
    if c is None:
        return None
    return "MÁS HAWKISH" if c >= UMBRAL_CAMBIO else "MÁS DOVISH" if c <= -UMBRAL_CAMBIO else "SIN CAMBIO"


# ---------------------------------------------------------------- texto de páginas oficiales
def _plano(t):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t))).strip()


def _texto_fed(url):
    t = fuentes.texto("https://www.federalreserve.gov" + url if url.startswith("/") else url, tries=3)
    i = t.find('id="article"')
    if i < 0:
        raise RuntimeError("Fed: sin id=article")
    x = _plano(t[i:])
    x = re.split(r"For media inquiries|Implementation Note|Voting for the monetary policy action|Last Update:|Back to Top", x)[0]
    return x


def _texto_bce(url):
    t = fuentes.texto("https://www.ecb.europa.eu" + url if url.startswith("/") else url, tries=3)
    i = t.find("<main")
    if i < 0:
        raise RuntimeError("BCE: sin <main>")
    j = t.find("Are you happy with this page", i)
    x = _plano(t[i:j if j > 0 else None])
    # solo la declaración introductoria: el turno de preguntas lo contesta el presidente con otro registro y no es comunicado
    k = re.search(r"Questions? and answers?|Transcript of the questions|^Question:", x)
    return x[: k.start()] if k else x


def _texto_boj(url):
    u = "https://www.boj.or.jp" + url if url.startswith("/") else url
    if u.endswith(".pdf"):
        import pypdf
        r = pypdf.PdfReader(io.BytesIO(fuentes.get(u, tries=3)))
        return re.sub(r"\s+", " ", " ".join((p.extract_text() or "") for p in r.pages))
    t = fuentes.texto(u, tries=3)
    i = t.find('<div id="contents"')
    return _plano(t[i if i > 0 else 0:])


# ---------------------------------------------------------------- índices de documentos
def lista_fed():
    out = {}
    paginas = [f"https://www.federalreserve.gov/monetarypolicy/fomchistorical{y}.htm" for y in range(DESDE_COMUNICADOS, 2021)]
    paginas.append("https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm")
    for u in paginas:
        try:
            t = fuentes.texto(u, tries=3)
        except Exception:  # noqa: BLE001
            continue
        for ruta, ymd in re.findall(r'href="((?:https://www\.federalreserve\.gov)?/newsevents/pressreleases/monetary(\d{8})a\.htm)"', t):
            fecha = dt.date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:8]))
            if fecha.year >= DESDE_COMUNICADOS:
                out[fecha] = ruta.replace("https://www.federalreserve.gov", "")
    return [{"banco": "Fed", "fecha": f, "url": "https://www.federalreserve.gov" + u, "ruta": u, "tipo": "Comunicado FOMC"} for f, u in sorted(out.items())]


def lista_bce():
    out = {}
    for y in range(DESDE_COMUNICADOS, dt.date.today().year + 1):
        try:
            t = fuentes.texto(f"https://www.ecb.europa.eu/press/pressconf/{y}/html/index_include.en.html", tries=3)
        except Exception:  # noqa: BLE001
            continue
        for ruta, ymd in re.findall(r'href="(/press/press_conference/monetary-policy-statement/\d{4}/html/(?:ecb\.)?is(\d{6})[^"]*\.en\.html)"', t):
            fecha = dt.date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:6]))
            out[fecha] = ruta
    return [{"banco": "BCE", "fecha": f, "url": "https://www.ecb.europa.eu" + u, "ruta": u, "tipo": "Declaración introductoria"} for f, u in sorted(out.items())]


def lista_boj():
    out = {}
    for y in range(DESDE_COMUNICADOS, dt.date.today().year + 1):
        try:
            t = fuentes.texto(f"https://www.boj.or.jp/en/mopo/mpmdeci/state_{y}/index.htm", tries=3)
        except Exception:  # noqa: BLE001
            continue
        for ruta, ymd, ext in re.findall(r'href="(/en/mopo/mpmdeci/[a-z]+_\d{4}/k(\d{6})a\.(pdf|htm))"', t):
            fecha = dt.date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:6]))
            if fecha not in out or ext == "htm":
                out[fecha] = ruta
    return [{"banco": "BoJ", "fecha": f, "url": "https://www.boj.or.jp" + u, "ruta": u, "tipo": "Statement on Monetary Policy"} for f, u in sorted(out.items())]


TEXTO = {"Fed": _texto_fed, "BCE": _texto_bce, "BoJ": _texto_boj}


# ---------------------------------------------------------------- comunicados: puntuación incremental y memoria permanente
def actualizar_comunicados(limite, err):
    previos = {r["url"]: r for r in csvlog.leer("tono_comunicados.csv")}
    nuevas, intentos = [], 0
    for fn in (lista_fed, lista_bce, lista_boj):
        try:
            docs = fn()
        except Exception as e:  # noqa: BLE001
            err[fn.__name__] = f"{type(e).__name__}: {str(e)[:120]}"
            continue
        if not docs:
            err[fn.__name__] = "sin documentos"
        for d in docs:
            if d["url"] in previos and previos[d["url"]].get("diccionario") == VERSION:
                continue
            if intentos >= limite:
                break
            intentos += 1
            try:
                x = puntuar(TEXTO[d["banco"]](d["ruta"]))
                if x["palabras"] < 80:
                    raise RuntimeError(f"texto demasiado corto ({x['palabras']} palabras)")
            except Exception as e:  # noqa: BLE001
                err[f"{d['banco']} {d['fecha']}"] = f"{type(e).__name__}: {str(e)[:100]}"
                continue
            nuevas.append({"banco": d["banco"], "fecha": d["fecha"].isoformat(), "url": d["url"], "tipo": d["tipo"], "palabras": x["palabras"], "h": x["h"], "d": x["d"],
                           "indice": "" if x["indice"] is None else x["indice"], "terminos": json.dumps(x["terminos"], ensure_ascii=False, sort_keys=True), "diccionario": VERSION})
    if nuevas:
        csvlog.anadir("tono_comunicados.csv", nuevas, ("url", "diccionario"))
    filas = {}
    for r in csvlog.leer("tono_comunicados.csv"):
        if r.get("diccionario") == VERSION:
            filas[r["url"]] = r
    return sorted(filas.values(), key=lambda r: (r["banco"], r["fecha"]))


# ---------------------------------------------------------------- discursos
_TITULOS = re.compile(r"^(Vice Chair for Supervision|Vice Chair|Chair Pro Tempore|Chair|Governor|President|Member of the Policy Board|Deputy Governor)\s+", re.I)


def _orador_fed(s):
    s = html.unescape(s or "").strip()
    return _TITULOS.sub("", s).strip() or s


def _orador_boj(s):
    nom = html.unescape(s).split(",")[0].strip()
    p = nom.split()
    if len(p) >= 2 and p[0].isupper():
        return " ".join(p[1:]).title() + " " + p[0].title()
    return nom


def lista_discursos_fed():
    j = json.loads(fuentes.texto("https://www.federalreserve.gov/json/ne-speeches.json", tries=3).lstrip("﻿"))
    out = []
    for x in j:
        try:
            f = dt.datetime.strptime(x["d"].split()[0], "%m/%d/%Y").date()
        except (KeyError, ValueError):
            continue
        if f >= DESDE_DISCURSOS and x.get("l"):
            out.append({"banco": "Fed", "fecha": f, "orador": _orador_fed(x.get("s")), "titulo": html.unescape(x.get("t", "")), "ruta": x["l"],
                        "url": "https://www.federalreserve.gov" + x["l"]})
    return out


def lista_discursos_boj():
    out = []
    for y in range(DESDE_DISCURSOS.year, dt.date.today().year + 1):
        try:
            t = fuentes.texto(f"https://www.boj.or.jp/en/about/press/koen_{y}/index.htm", tries=3)
        except Exception:  # noqa: BLE001
            continue
        for fecha, quien, ruta, tit in re.findall(r"<tr>\s*<td>([^<]+)</td>\s*<td>([^<]+)</td>\s*<td><a href=\"(/en/about/press/koen_\d{4}/ko\d{6}[a-z]\.htm)\"[^>]*>(.*?)</a>", t, flags=re.S):
            try:
                f = dt.datetime.strptime(html.unescape(fecha).replace("\xa0", " ").replace("Sept.", "Sep.").replace("  ", " ").strip(), "%b. %d, %Y").date()
            except ValueError:
                try:
                    f = dt.datetime.strptime(html.unescape(fecha).replace("\xa0", " ").replace("  ", " ").strip(), "%B %d, %Y").date()
                except ValueError:
                    continue
            if f >= DESDE_DISCURSOS:
                out.append({"banco": "BoJ", "fecha": f, "orador": _orador_boj(quien), "titulo": _plano(tit), "ruta": ruta, "url": "https://www.boj.or.jp" + ruta})
    return out


def discursos_bce(err):
    """Texto y orador desde el CSV oficial del BCE (la primera parte del archivo, ordenado de más reciente a más antiguo)."""
    b = fuentes.get(URL_ECB_CSV, tries=2, timeout=180)
    txt = b[:16_000_000].decode("utf-8", "replace")
    try:
        rss = fuentes.texto("https://www.ecb.europa.eu/rss/press.html", tries=2, timeout=30)
        enlaces = re.findall(r"<link>(https://www\.ecb\.europa\.eu/+press/key/date/\d{4}/html/ecb\.sp(\d{6})[^<]*\.en\.html)</link>", rss)
    except Exception:  # noqa: BLE001
        enlaces = []
    por_dia = {}
    for u, ymd in enlaces:
        por_dia.setdefault(ymd, []).append(u.replace("eu//", "eu/"))
    out = []
    # el campo «contents» puede ocupar varias líneas: un registro nuevo empieza en una línea «AAAA-MM-DD|…»
    registros, actual = [], None
    for linea in txt.splitlines()[1:]:
        if re.match(r"\d{4}-\d{2}-\d{2}\|", linea):
            if actual is not None:
                registros.append(actual)
            actual = linea
        elif actual is not None:
            actual += " " + linea
    # el último registro puede estar cortado por el límite de descarga: se descarta
    for reg in registros:
        r = reg.split("|", 4)
        if len(r) < 5:
            continue
        try:
            f = dt.date.fromisoformat(r[0])
        except ValueError:
            continue
        if f < DESDE_DISCURSOS or not r[1].strip():
            continue
        ymd = f.strftime("%y%m%d")
        cand = por_dia.get(ymd, [])
        url = cand[0] if len(cand) == 1 else "https://www.ecb.europa.eu/press/key/date/html/index.en.html"
        out.append({"banco": "BCE", "fecha": f, "orador": r[1].split(",")[0].strip(), "titulo": r[2].strip(), "url": url, "texto": r[4]})
    return out


def actualizar_discursos(limite, err):
    previos = {(r["banco"], r["fecha"], r["orador"], r["titulo"]) for r in csvlog.leer("tono_discursos.csv") if r.get("diccionario") == VERSION}
    cand = []
    for nombre, fn in (("Fed", lista_discursos_fed), ("BoJ", lista_discursos_boj)):
        try:
            cand += fn()
        except Exception as e:  # noqa: BLE001
            err[f"discursos {nombre}"] = f"{type(e).__name__}: {str(e)[:120]}"
    try:
        cand += discursos_bce(err)
    except Exception as e:  # noqa: BLE001
        err["discursos BCE"] = f"{type(e).__name__}: {str(e)[:120]}"
    nuevas, n = [], 0
    for d in sorted(cand, key=lambda x: x["fecha"]):
        clave = (d["banco"], d["fecha"].isoformat(), d["orador"], d["titulo"])
        if clave in previos:
            continue
        if n >= limite:
            break
        n += 1
        try:
            texto = d["texto"] if "texto" in d else TEXTO[d["banco"]](d["ruta"])
            x = puntuar(texto)
            if x["palabras"] < 250:
                raise RuntimeError(f"texto demasiado corto ({x['palabras']} palabras)")
        except Exception as e:  # noqa: BLE001
            err[f"discurso {d['banco']} {d['fecha']} {d['orador']}"] = f"{type(e).__name__}: {str(e)[:90]}"
            continue
        puntua = x["n_terminos"] >= MIN_TERMINOS_DISCURSO and x["menciones_tema"] >= MIN_MENCIONES_TEMA and x["indice"] is not None
        nuevas.append({"banco": d["banco"], "fecha": d["fecha"].isoformat(), "orador": d["orador"], "titulo": d["titulo"], "url": d["url"], "palabras": x["palabras"],
                       "h": x["h"], "d": x["d"], "indice": "" if x["indice"] is None else x["indice"], "n_terminos": x["n_terminos"], "menciones_tema": x["menciones_tema"],
                       "puntua": int(puntua), "terminos": json.dumps(x["terminos"], ensure_ascii=False, sort_keys=True), "diccionario": VERSION})
    if nuevas:
        csvlog.anadir("tono_discursos.csv", nuevas, ("banco", "fecha", "orador", "titulo", "diccionario"))
    return [r for r in csvlog.leer("tono_discursos.csv") if r.get("diccionario") == VERSION]


# ---------------------------------------------------------------- validación frente a la decisión de tipos
AREA = {"Fed": "US", "BCE": "XM", "BoJ": "JP"}


def _decision(s, f):
    a = bancos._paso(s, f - dt.timedelta(days=1))
    b = bancos._paso(s, f + dt.timedelta(days=VENTANA_DECISION))
    if a is None or b is None:
        return None
    d = b - a
    return (1 if d >= UMBRAL_DECISION else -1 if d <= -UMBRAL_DECISION else 0), round(d, 3)


def _regla(pares, clave):
    """pares: [(prediccion, real)] → métricas. prediccion/real ∈ {−1, 0, +1}."""
    n = len(pares)
    if not n:
        return {"n": 0}
    ac = sum(1 for p, r in pares if p == r)
    mov = [(p, r) for p, r in pares if r != 0]
    return {"n": n, "aciertos": ac, "pct": round(100 * ac / n, 1),
            "mov_n": len(mov), "mov_aciertos": sum(1 for p, r in mov if p == r), "mov_opuestos": sum(1 for p, r in mov if p == -r),
            "mov_pct": round(100 * sum(1 for p, r in mov if p == r) / len(mov), 1) if mov else None,
            "dir_n": sum(1 for p, r in pares if p != 0), "dir_aciertos": sum(1 for p, r in pares if p != 0 and p == r),
            "dir_pct": round(100 * sum(1 for p, r in pares if p != 0 and p == r) / max(1, sum(1 for p, r in pares if p != 0)), 1) if any(p != 0 for p, r in pares) else None}


def validar(series, pasos):
    out = {}
    todos_n, todos_p = [], []
    todos_c = []
    for banco, area in AREA.items():
        ser = series.get(banco) or []
        s = pasos.get(area) or []
        if len(ser) < 5 or not s:
            out[banco] = {"n": 0, "motivo": "sin muestra suficiente"}
            continue
        # decisión de cada reunión i (misma reunión) y de la siguiente (i+1)
        dec = [_decision(s, dt.date.fromisoformat(r["fecha"])) for r in ser]
        par_nivel, par_cambio, base_rep, base_mant = [], [], [], []
        xs, ys = [], []
        for i in range(len(ser) - 1):
            if dec[i + 1] is None or ser[i]["indice"] is None:
                continue
            real, pp = dec[i + 1]
            pred = {"HAWKISH": 1, "DOVISH": -1, "NEUTRAL": 0}[ser[i]["nivel"]]
            par_nivel.append((pred, real))
            base_mant.append((0, real))
            if dec[i] is not None:
                base_rep.append((dec[i][0], real))
            xs.append(ser[i]["indice"])
            ys.append(pp)
            if i > 0 and ser[i - 1]["indice"] is not None:
                c = ser[i]["indice"] - ser[i - 1]["indice"]
                predc = 1 if c >= UMBRAL_CAMBIO else -1 if c <= -UMBRAL_CAMBIO else 0
                par_cambio.append((predc, real))
        corr = None
        if len(xs) >= 10 and statistics.pstdev(xs) > 0 and statistics.pstdev(ys) > 0:
            corr = round(statistics.correlation(xs, ys), 3)
        # decisión de la MISMA reunión (el comunicado ya refleja lo decidido): para ver cuánto del tono es simple eco
        par_misma = [({"HAWKISH": 1, "DOVISH": -1, "NEUTRAL": 0}[ser[i]["nivel"]], dec[i][0]) for i in range(len(ser)) if dec[i] is not None and ser[i]["indice"] is not None]
        reales = [r for _, r in par_nivel]
        out[banco] = {"n": len(par_nivel), "desde": ser[0]["fecha"], "hasta": ser[-1]["fecha"], "n_comunicados": len(ser),
                      "nivel": _regla(par_nivel, "nivel"), "cambio": _regla(par_cambio, "cambio"),
                      "base_mantiene": _regla(base_mant, "base"), "base_repite": _regla(base_rep, "base"), "misma_reunion": _regla(par_misma, "misma"),
                      "correlacion": corr, "reales": {"sube": reales.count(1), "mantiene": reales.count(0), "baja": reales.count(-1)}}
        todos_n += par_nivel
        todos_p += base_mant
        todos_c += par_cambio
    out["_total"] = {"nivel": _regla(todos_n, "nivel"), "cambio": _regla(todos_c, "cambio"), "base_mantiene": _regla(todos_p, "base")}
    return out


# ---------------------------------------------------------------- medición
def medir(limite=MAX_NUEVOS):
    err = {}
    hoy = dt.date.today()
    filas = actualizar_comunicados(limite, err)
    series = {}
    for banco in ("Fed", "BCE", "BoJ"):
        ser = []
        ant = None
        for r in [x for x in filas if x["banco"] == banco]:
            try:
                i = float(r["indice"]) if r["indice"] != "" else None
            except ValueError:
                i = None
            c = None if (i is None or ant is None) else round(i - ant, 3)
            ser.append({"fecha": r["fecha"], "indice": i, "nivel": nivel(i) if i is not None else "SIN PUNTUACIÓN", "cambio": c, "cambio_txt": cambio_txt(c),
                        "h": int(float(r["h"])), "d": int(float(r["d"])), "palabras": int(float(r["palabras"])), "url": r["url"], "tipo": r["tipo"],
                        "terminos": json.loads(r["terminos"] or "{}")})
            if i is not None:
                ant = i
        series[banco] = ser
    try:
        pasos = bancos._cargar_pasos()
    except Exception as e:  # noqa: BLE001
        pasos = {}
        err["pasos"] = f"{type(e).__name__}: {e}"
    val = validar(series, pasos)

    discursos = actualizar_discursos(limite, err)
    por_orador = {}
    for r in sorted(discursos, key=lambda x: x["fecha"]):
        try:
            i = float(r["indice"]) if r["indice"] != "" else None
        except ValueError:
            i = None
        puntua = r.get("puntua") in ("1", 1) and i is not None
        item = {"banco": r["banco"], "orador": r["orador"], "fecha": r["fecha"], "titulo": r["titulo"], "url": r["url"], "indice": i if puntua else None,
                "nivel": nivel(i) if puntua else "NO PUNTÚA", "n_terminos": int(float(r.get("n_terminos") or 0)), "menciones_tema": int(float(r.get("menciones_tema") or 0)),
                "palabras": int(float(r["palabras"])), "terminos": json.loads(r.get("terminos") or "{}")}
        prev = [x for x in por_orador.get((r["banco"], r["orador"]), []) if x["indice"] is not None]
        if puntua and prev:
            item["anterior_fecha"], item["anterior_indice"] = prev[-1]["fecha"], prev[-1]["indice"]
            item["cambio"] = round(i - prev[-1]["indice"], 3)
            item["cambio_txt"] = cambio_txt(item["cambio"])
        por_orador.setdefault((r["banco"], r["orador"]), []).append(item)
    lista = [x for v in por_orador.values() for x in v]
    lista.sort(key=lambda x: x["fecha"], reverse=True)
    oradores = []
    for (banco, quien), v in por_orador.items():
        p = [x for x in v if x["indice"] is not None]
        if not p:
            continue
        oradores.append({"banco": banco, "orador": quien, "n": len(p), "n_total": len(v), "ultimo": {"fecha": p[-1]["fecha"], "indice": p[-1]["indice"], "nivel": p[-1]["nivel"], "titulo": p[-1]["titulo"], "url": p[-1]["url"]},
                         "anterior": ({"fecha": p[-2]["fecha"], "indice": p[-2]["indice"]} if len(p) > 1 else None),
                         "cambio": p[-1].get("cambio"), "cambio_txt": p[-1].get("cambio_txt"), "media": round(statistics.fmean(x["indice"] for x in p), 3)})
    oradores.sort(key=lambda o: o["ultimo"]["fecha"], reverse=True)

    ult = {}
    for b, s in series.items():
        p = [x for x in s if x["indice"] is not None]
        ult[b] = ({**p[-1], "anterior": ({"fecha": p[-2]["fecha"], "indice": p[-2]["indice"]} if len(p) > 1 else None)} if p else None)
    if not any(series.values()):
        raise RuntimeError("sin comunicados puntuados: " + json.dumps(err)[:300])
    top = sorted(TERMINOS, key=lambda x: (x[2], -abs(x[1]), x[0]))
    return {"fecha": hoy.isoformat(), "diccionario": {"version": VERSION,
                                                       "hawkish": [{"termino": t, "peso": p} for t, p, k in TERMINOS if k == "hawkish"],
                                                       "dovish": [{"termino": t, "peso": abs(p)} for t, p, k in TERMINOS if k == "dovish"],
                                                       "n_terminos": len(TERMINOS)},
            "reglas": {"umbral_nivel": UMBRAL_NIVEL, "umbral_cambio": UMBRAL_CAMBIO, "min_terminos_discurso": MIN_TERMINOS_DISCURSO, "min_menciones_tema": MIN_MENCIONES_TEMA,
                       "umbral_decision_pp": UMBRAL_DECISION, "ventana_decision_dias": VENTANA_DECISION},
            "comunicados": series, "ultimo": ult, "validacion": val, "discursos": lista[:200], "oradores": oradores,
            "n_discursos_puntuados": len([x for x in lista if x["indice"] is not None]), "n_discursos": len(lista),
            "fuentes": {"Fed": "federalreserve.gov (comunicados FOMC y discursos de la Junta)", "BCE": "ecb.europa.eu (declaración introductoria y discursos)",
                        "BoJ": "boj.or.jp (Statement on Monetary Policy y discursos)"},
            "errores": err}


if __name__ == "__main__":
    import sys
    M = medir(limite=10_000 if "--backfill" in sys.argv else MAX_NUEVOS)
    print(M["diccionario"]["version"], M["diccionario"]["n_terminos"])
    for b, s in M["comunicados"].items():
        print(b, len(s), s[-1] if s else None)
    print(json.dumps(M["validacion"], ensure_ascii=False, indent=1)[:3500])
    print("discursos", M["n_discursos_puntuados"], "/", M["n_discursos"])
    print("errores", json.dumps(M["errores"], ensure_ascii=False)[:1500])
