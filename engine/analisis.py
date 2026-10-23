"""NEXORA · ANÁLISIS DIARIO (Fase 18). Sin IA: parser tolerante por reglas, cotejo numérico contra los datos de NEXORA y evaluación del sesgo a T+1 y T+5.

Ruiz envía cada día su informe (texto con tablas, secciones A–K; G = oro). tools/publicar_analisis.py lo guarda (solo añadir) y este módulo:
  1. EXTRAE (parse): TESIS CENTRAL, A.1, A.2 (panel), B.3 (calendario), G (oro y escenarios), J (escenarios, red team, data gaps), K.2 (tesis final) y Veredicto. Si no reconoce una sección no la inventa:
     la vista muestra el texto tal cual. El SESGO DE ORO lo indica Ruiz en el comando; nunca se deduce del texto.
  2. COTEJA cada fila del panel A.2 que NEXORA tenga con el valor de NEXORA en la MISMA fecha (históricos propios; si no hay histórico de esa fecha, el dato actual solo si es de esa fecha):
     ✅ coincide · ⚠️ difiere (ambos valores y la fuente de NEXORA) · — NEXORA no lo tiene (nunca se rellena). Tolerancias: tipos ±3 pb; DXY ±0,3; oro ±0,5 %; Brent/WTI ±1,5 %; VIX ±0,5; resto ±1 %.
     También el calendario B.3 frente a la agenda de NEXORA (eventos que faltan u horas distintas, con el cambio de hora: Europa 25-oct, EE. UU. 1-nov) y las probabilidades de la Fed lado a lado.
  3. RESULTADO del sesgo de oro a T+1 y T+5 sesiones (data/analisis_resultados.csv, solo añadir). Reglas FIJAS:
     ORO: alcista → sube más de un 0,25 %; bajista → baja más de un 0,25 %; neutral → se mueve como mucho un 0,5 % a T+1 o un 1,5 % a T+5.
     CUMPLIDO = el oro hace lo esperado y DXY o DFII10 no lo contradicen a la vez; MIXTO = el oro hace lo esperado pero DXY y DFII10 (ambos) fueron en contra, o el oro se movió menos de ±0,25 % con sesgo direccional;
     FALLIDO = el oro fue en contra (más de un 0,25 % al lado contrario) o, en neutral, se salió de la banda. DXY y DFII10 «a favor» = DXY y tipo real bajan para alcista, suben para bajista.
     Con menos de 20 resultados evaluados: «n<20: sin conclusión»."""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
import re
import statistics
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(HERE)
UTC = dt.timezone.utc
MIN_N = 20
CAMPOS_INDICE = ["id", "fecha", "tipo", "version", "visibilidad", "sesgo_oro", "corte_madrid", "hash", "estado", "registrada_utc", "nota"]
CAMPOS_RES = ["id", "fecha", "tipo", "sesgo_oro", "horizonte", "fecha_t", "oro_pct", "dxy_var", "dfii10_pb", "veredicto", "evaluado_utc"]
TIPOS = ("ORO_MACRO", "INDICES")
SESGOS = ("alcista", "bajista", "neutral")
VISIBILIDADES = ("privado", "resumen")


def P(raiz, *a):
    return os.path.join(raiz, *a)


def _norm(s):
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()


def leer_csv(ruta):
    if not os.path.exists(ruta):
        return []
    with open(ruta, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def anadir_csv(ruta, filas, campos, clave):
    vistas = {clave(r) for r in leer_csv(ruta)}
    nuevas = [r for r in filas if clave(r) not in vistas]
    if nuevas:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        nuevo = not os.path.exists(ruta) or os.path.getsize(ruta) == 0
        with open(ruta, "a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
            if nuevo:
                w.writeheader()
            w.writerows(nuevas)
    return len(nuevas)


def hash_texto(t):
    return "sha256:" + hashlib.sha256(t.replace("\r\n", "\n").encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- números
def num(s, miles=False, coma_decimal=False):
    """Primer número de un texto, tolerante a «4,15 %», «4.152,30», «1,234.5», «−0,3» y «(3,2)». None si no hay."""
    m = re.search(r"[-−+]?\(?\d[\d\s.,]*\d|[-−+]?\(?\d", str(s))
    if not m:
        return None
    t = m.group(0).replace("−", "-").replace("(", "-").replace(" ", "")
    if miles and re.fullmatch(r"[-+]?\d{1,3}\.\d{3}", t):      # «4.140» = 4140 (punto de miles) en importes y niveles grandes (oro, reservas…)
        t = t.replace(".", "")
    if "," in t and "." in t:
        dec = "," if t.rfind(",") > t.rfind(".") else "."
        t = t.replace("." if dec == "," else ",", "").replace(dec, ".")
    elif "," in t:
        miles_coma = re.fullmatch(r"[-+]?\d{1,3}(,\d{3})+", t) and not (coma_decimal and t.count(",") == 1)      # «2,963T» = 2,963 (decimal); «1,234,567» = miles
        t = t.replace(",", "") if miles_coma else t.replace(",", ".")
    elif t.count(".") > 1 or re.fullmatch(r"[-+]?\d{1,3}(\.\d{3}){2,}", t):
        t = t.replace(".", "")
    try:
        return float(t)
    except ValueError:
        return None


def a_miles_de_millones(valor, texto):
    """Normaliza un importe a $B (miles de millones) según el sufijo escrito junto a la cifra (T, B/bn/mm, M); sin sufijo se deja tal cual."""
    t = _norm(texto)
    if re.search(r"\d\s*(t\b|tn\b|billones|trillion)", t) or "$t" in t:
        return valor * 1000.0
    if re.search(r"\d\s*(m\b|millones)", t) and not re.search(r"\d\s*(mm|mil millones)", t):
        return valor / 1000.0
    return valor


# ---------------------------------------------------------------- extracción
RX_SEC = re.compile(r"^\s*(?:#{1,6}\s*|\*{1,2}\s*)?(?:SECCI[OÓ]N\s+)?([A-K])(?:\s*\.\s*(\d{1,2}))?(?=[\s\.\):–—:*-]|$)", re.I)
RX_TESIS = re.compile(r"^\s*(?:#{1,6}\s*)?(?:\*{1,2})?\s*TESIS\s+CENTRAL", re.I)
RX_VERED = re.compile(r"^\s*(?:#{1,6}\s*)?(?:\*{1,2})?\s*VEREDICTO\b", re.I)


def _titulos(lineas):
    """[(índice de línea, clave)] de cada cabecera reconocida: TESIS, A..K, A.1, A.2…, VEREDICTO."""
    out = []
    for i, l in enumerate(lineas):
        if RX_TESIS.match(l):
            out.append((i, "TESIS"))
        elif RX_VERED.match(l) and len(l.strip()) < 160:
            out.append((i, "VEREDICTO"))
        else:
            m = RX_SEC.match(l)
            if m and (m.group(2) or l.strip().upper().startswith(("#", "*", "SECCI", m.group(1).upper() + ".", m.group(1).upper() + ")", m.group(1).upper() + ":"))):
                out.append((i, m.group(1).upper() + (("." + m.group(2)) if m.group(2) else "")))
    return out


def parse(texto):
    """Devuelve {secciones: {clave: texto}, ...}. Cada sección va de su cabecera a la siguiente; una letra (G) incluye sus subsecciones (G.1, G.2…). Nada se inventa: lo no reconocido queda en `sin_clasificar`."""
    lineas = texto.replace("\r\n", "\n").split("\n")
    tit = _titulos(lineas)
    sec, orden = {}, []
    for k, (i, clave) in enumerate(tit):
        fin = tit[k + 1][0] if k + 1 < len(tit) else len(lineas)
        cuerpo = "\n".join(lineas[i:fin]).strip()
        if clave not in sec:
            sec[clave] = cuerpo
            orden.append(clave)
    # una letra agrupa sus subsecciones
    letras = {}
    for clave in orden:
        L = clave[0]
        if clave in "ABCDEFGHIJK" and len(clave) == 1 or clave[0] in "ABCDEFGHIJK" and "." in clave:
            letras.setdefault(L, []).append(clave)
    bloques = {L: "\n\n".join(sec[c] for c in cs) for L, cs in letras.items()}
    primera = tit[0][0] if tit else len(lineas)
    r = {"secciones": sec, "bloques": bloques, "orden": orden, "previo": "\n".join(lineas[:primera]).strip(), "reconocido": bool(tit)}
    r["tesis_central"] = _cuerpo(sec.get("TESIS"))
    r["veredicto"] = _cuerpo(sec.get("VEREDICTO"), una_linea=True)
    r["tesis_final"] = _cuerpo(sec.get("K.2")) or _cuerpo(sec.get("K"))
    r["panel"] = sec.get("A.2") or ""
    r["calendario"] = sec.get("B.3") or bloques.get("B") or ""
    r["oro_texto"] = bloques.get("G") or sec.get("G") or ""
    r["j_texto"] = bloques.get("J") or sec.get("J") or ""
    r["escenarios"] = escenarios(r["oro_texto"]) + [e for e in escenarios(r["j_texto"]) if e["origen"] == "J"]
    r["red_team"] = _lista_tras(r["j_texto"], r"red\s*team")
    r["data_gaps"] = _lista_tras(r["j_texto"], r"data\s*gaps|huecos\s+de\s+datos|vac[ií]os\s+de\s+datos|lagunas")
    r["fecha_detectada"], r["corte_detectado"] = detectar_fecha(texto)
    return r


def _cuerpo(t, una_linea=False):
    """Texto de una sección sin su línea de cabecera (o solo lo que sigue a «Veredicto:» en la misma línea)."""
    if not t:
        return ""
    ls = t.split("\n")
    cab = re.sub(r"^\s*(?:#{1,6}\s*|\*{1,2}\s*)?(?:TESIS\s+CENTRAL|VEREDICTO|K\s*\.\s*2|K)\s*[\.\)–—-]*\s*\**\s*", "", ls[0], flags=re.I).strip(" *")
    resto = "\n".join(ls[1:]).strip()
    if ":" in cab:                      # «VEREDICTO: Neutral», «TESIS CENTRAL: …» → lo que sigue a los dos puntos es contenido
        cab = cab.split(":", 1)[1].strip(" *")
    elif len(cab) <= 60:                # «K.2 Tesis final» → es un título, no contenido
        cab = ""
    if una_linea:
        return cab or next((x.strip() for x in ls[1:] if x.strip()), "")
    return (cab + ("\n" if cab and resto else "") + resto).strip()


def _lista_tras(texto, patron):
    """Líneas literales desde una cabecera (red team, data gaps…) hasta la primera línea en blanco o la siguiente cabecera."""
    out, dentro = [], False
    for l in texto.split("\n"):
        if re.search(patron, l, re.I) and len(l) < 200 and not dentro:
            dentro = True
            resto = re.sub(r"^.*?(?:" + patron + r")\s*[:\-–—]*\s*", "", l, flags=re.I).strip(" *#")
            if resto:
                out.append(resto)
            continue
        if dentro:
            if not l.strip() or RX_SEC.match(l) and len(l) < 80 or re.match(r"^\s*[-*•]?\s*\**\s*(?:red\s*team|data\s*gaps|huecos\s+de\s+datos|vac[ií]os\s+de\s+datos|lagunas|escenario)", l, re.I):
                break
            out.append(l.strip(" -•*\t"))
    return [x for x in out if x]


RX_ESC = re.compile(r"^\s*(?:[-*•]\s*|#{1,6}\s*)?\**\s*(?:escenario|caso)\s*([A-Za-z0-9ºª]+)?\s*[\.\):–—:-]*\s*(.*)$", re.I)
RX_ETQ = {"condiciones": re.compile(r"^\s*[-*•]?\s*\**\s*condici[oó]n(?:es)?\s*\**\s*[:\-–—]\s*(.*)$", re.I),
          "confirmacion": re.compile(r"^\s*[-*•]?\s*\**\s*confirmaci[oó]n\s*\**\s*[:\-–—]\s*(.*)$", re.I),
          "invalidacion": re.compile(r"^\s*[-*•]?\s*\**\s*invalidaci[oó]n\s*\**\s*[:\-–—]\s*(.*)$", re.I)}


def escenarios(texto):
    """Escenarios con sus condiciones / confirmación / invalidación LITERALES (el texto tras la etiqueta, sin tocar). Sin etiquetas, queda el bloque literal."""
    out, act = [], None
    for l in texto.split("\n"):
        m = RX_ESC.match(l)
        if m and len(l) < 240:
            act = {"nombre": ("Escenario " + (m.group(1) or "")).strip() + ((": " + m.group(2).strip(" *")) if m.group(2).strip(" *") else ""), "condiciones": "", "confirmacion": "", "invalidacion": "", "texto": l.strip(), "origen": "G"}
            out.append(act)
            continue
        if act is None:
            continue
        act["texto"] += "\n" + l
        for k, rx in RX_ETQ.items():
            mm = rx.match(l)
            if mm:
                act[k] = (act[k] + " " + mm.group(1).strip()).strip()
    for e in out:
        e["texto"] = e["texto"].strip()[:1500]
    return out


MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12}


def detectar_fecha(texto, ano_por_defecto=None):
    """(fecha ISO, corte HH:MM) de las primeras líneas del informe (p. ej. «20-10-2026», «20 oct 2026», «corte 09:30»). None si no aparece."""
    cab = "\n".join(texto.split("\n")[:25])
    f = None
    m = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](20\d{2})", cab)
    if m:
        f = f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    else:
        m = re.search(r"(20\d{2})-(\d{2})-(\d{2})", cab)
        if m:
            f = m.group(0)
        else:
            m = re.search(r"(\d{1,2})\s+(?:de\s+)?(ene|feb|mar|abr|may|jun|jul|ago|sep|set|oct|nov|dic)[a-z]*\.?\s+(?:de\s+)?(20\d{2})", _norm(cab))
            if m:
                f = f"{m.group(3)}-{MESES[m.group(2)]:02d}-{int(m.group(1)):02d}"
    c = re.search(r"(?:corte|cierre|hora|a las)\D{0,12}(\d{1,2})[:.h](\d{2})", _norm(cab))
    return f, (f"{int(c.group(1)):02d}:{c.group(2)}" if c else None)


# ---------------------------------------------------------------- cotejo del panel A.2
# (id, nombre, regex del rótulo, familia de tolerancia). El orden importa: lo específico primero.
INDICADORES = [
    ("cot_oro", "COT oro (neto dinero gestionado)", r"cot[^|\n]{0,25}oro|oro[^|\n]{0,25}(?:cot|posicionamiento|neto)|posicionamiento[^|\n]{0,20}oro", "pct1"),
    ("dfii10", "DFII10 · tipo real 10 años", r"dfii\s*10|tips|tipo\s+real|real\s*10|rendimiento\s+real", "tipo"),
    ("be10", "Breakeven 10 años", r"break\s*-?\s*even|\bbe\s*10\b|inflaci[oó]n\s+impl[ií]cita", "tipo"),
    ("t30", "US 30 años", r"\b(?:us\s*)?30\s*(?:y\b|a[nñ]os|yr)|\bust?\s*30|\bt30y", "tipo"),
    ("t10", "US 10 años", r"\b(?:us\s*)?10\s*(?:y\b|a[nñ]os|yr)|\bust?\s*10\b|\bt10y", "tipo"),
    ("t5", "US 5 años", r"\b(?:us\s*)?5\s*(?:y\b|a[nñ]os|yr)|\bust?\s*5\b|\bt5y", "tipo"),
    ("t2", "US 2 años", r"\b(?:us\s*)?2\s*(?:y\b|a[nñ]os|yr)|\bust?\s*2\b|\bt2y", "tipo"),
    ("dxy", "DXY", r"\bdxy\b|d[oó]lar\s+index|[ií]ndice\s+(?:del\s+)?d[oó]lar", "dxy"),
    ("brent", "Brent", r"\bbrent\b", "petroleo"),
    ("wti", "WTI", r"\bwti\b|crudo\s+texas", "petroleo"),
    ("vix", "VIX", r"\bvix\b", "vix"),
    ("tga", "TGA", r"\btga\b|cuenta\s+general\s+del\s+tesoro", "pct1"),
    ("rrp", "ON RRP", r"\bon\s*rrp\b|\brrp\b|reverse\s*repo", "pct1"),
    ("reservas", "Reservas bancarias", r"reservas", "pct1"),
    ("sofr", "SOFR", r"\bsofr\b", "tipo"),
    ("oro", "Oro contado (XAU/USD)", r"\bxau\b|oro\s+(?:contado|spot)|\bspot\s+gold|\boro\b|\bgold\b", "oro"),
]
TOLERANCIAS = {"tipo": ("pb", 3.0), "dxy": ("abs", 0.3), "oro": ("rel", 0.5), "petroleo": ("rel", 1.5), "vix": ("abs", 0.5), "pct1": ("rel", 1.0)}


def _alineado(l):
    """Normaliza (minúsculas, sin acentos) conservando la longitud de la línea, para usar los índices de la coincidencia sobre el texto original."""
    return "".join((_norm(c) or " ")[0] for c in l.lower())


RX_FECHA_SUELTA = re.compile(r"(?<![\d.,])(?:\d{1,2}\s*[/\-]\s*\d{1,2}(?:\s*[/\-]\s*\d{2,4})?|\d{1,2}\.\d{1,2}\.\d{2,4}|\d{1,2}\s*[-/ ]\s*(?:ene|feb|mar|abr|may|jun|jul|ago|sep|set|oct|nov|dic)[a-z]*\.?(?:\s*\d{2,4})?)(?![\d,])", re.I)
RX_COLA_ROTULO = re.compile(r"^\s*[|:]*\s*\d{1,2}\s*(?:y|yr|a[nñ]os?)\b[\s|:]*", re.I)       # «10Y», «10 años» que quedó tras el rótulo no es el valor


def extraer_panel(texto):
    """[{id, nombre, texto, valor}] de las filas del panel A.2 que NEXORA sabe cotejar: el primer número tras el rótulo; una fila por indicador (la primera)."""
    filas, vistos = [], set()
    for l in texto.split("\n"):
        ln = _alineado(l)
        for ind, nombre, rx, fam in INDICADORES:
            m = re.search(rx, ln)
            if not m or ind in vistos:
                continue
            resto = re.sub(r"\([^)]*[A-Za-z][^)]*\)", " ", l[m.end():])        # fuera «(XAU)», «(cierre)»…
            resto = RX_COLA_ROTULO.sub(" ", resto)
            resto = RX_FECHA_SUELTA.sub(" ", resto)                                # fuera fechas «20-oct», «20/10»
            v = num(resto, miles=ind in ("oro", "cot_oro", "reservas", "tga", "rrp"), coma_decimal=ind in ("reservas", "tga", "rrp"))
            if v is None:
                continue
            if ind in ("tga", "rrp", "reservas"):
                v = a_miles_de_millones(v, resto[:40])
            filas.append({"id": ind, "nombre": nombre, "texto": l.strip()[:200], "valor": v})
            vistos.add(ind)
            break
    return filas


def _ultimo_por_fecha(filas, col_fecha, fecha):
    c = [r for r in filas if r.get(col_fecha) == fecha]
    return c[-1] if c else None


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def valor_nexora(ind, fecha, raiz=RAIZ):
    """(valor, fecha_dato, fuente) de NEXORA para `ind` en `fecha`; None si NEXORA no lo tiene en esa fecha. Histórico propio primero; si no, el dato actual SOLO si es de esa fecha."""
    D = P(raiz, "data")
    tip = leer_csv(P(D, "historico_tipos.csv"))
    pre = leer_csv(P(D, "historico_precios.csv"))
    om = ((json.load(open(P(raiz, "site", "data", "oro.json"), encoding="utf-8")) if os.path.exists(P(raiz, "site", "data", "oro.json")) else {}).get("metricas")) or {}

    def tipos(serie):
        r = _ultimo_por_fecha([x for x in tip if x["serie"] == serie], "fecha_dato", fecha)
        return (_f(r["valor"]), fecha, "historico_tipos.csv · " + r["fuente"]) if r else None

    def precio(act):
        r = _ultimo_por_fecha([x for x in pre if x["activo"] == act], "fecha_dato", fecha)
        return (_f(r["valor"]), fecha, "historico_precios.csv · " + r["fuente"]) if r else None

    def actual(clave, campo="valor", fuente=""):
        m = om.get(clave) or {}
        return (_f(m.get(campo)), m.get("fecha"), fuente or m.get("fuente") or "oro.json") if m.get("fecha") == fecha and _f(m.get(campo)) is not None else None
    if ind == "t2":
        return tipos("t2y") or actual("t2Y")
    if ind == "t10":
        return tipos("n10") or actual("t10Y")
    if ind == "dfii10":
        return tipos("real10") or actual("real10Y")
    if ind == "t5":
        return actual("t5Y")
    if ind == "t30":
        return actual("t30Y")
    if ind == "be10":
        a, b = tipos("n10"), tipos("real10")
        if a and b:
            return (round(a[0] - b[0], 3), fecha, "nominal − real (historico_tipos.csv)")
        return actual("be10Y")
    if ind in ("dxy", "vix", "brent", "wti"):
        return precio(ind) or actual(ind)
    if ind == "oro":
        r = _ultimo_por_fecha(leer_csv(P(D, "xau_gld_ratio.csv")), "fecha", fecha)
        if r and r.get("xau_spot") and "PROVISIONAL" not in (r.get("fuente_xau") or ""):
            return (_f(r["xau_spot"]), fecha, "gold-api.com (XAU/USD al contado) · xau_gld_ratio.csv")
        p = precio("oro")
        return (p[0], p[1], "futuro GC=F (no contado): " + p[2]) if p else None
    if ind == "sofr":
        return actual("sofr")
    if ind == "tga":
        return actual("tga", "valor_B")
    if ind == "rrp":
        return actual("rrp", "valor_B")
    if ind == "reservas":
        v = actual("reservas", "valor_T")
        return (v[0] * 1000.0, v[1], v[2]) if v else None
    if ind == "cot_oro":
        c = [r for r in leer_csv(P(D, "historico_cot.csv")) if r["clave"] == "oro" and r["fecha_informe"] <= fecha]
        if c:
            r = max(c, key=lambda x: x["fecha_informe"])
            if (dt.date.fromisoformat(fecha) - dt.date.fromisoformat(r["fecha_informe"])).days <= 7:
                return (_f(r["neto"]), r["fecha_informe"], "CFTC · historico_cot.csv (informe del martes más reciente)")
        return None
    return None


def comparar(ind, informe, nexora):
    """(estado, diferencia, texto de tolerancia)."""
    fam = next(f for i, _n, _r, f in INDICADORES if i == ind)
    tipo, tol = TOLERANCIAS[fam]
    if tipo == "pb":
        d = round((informe - nexora) * 100, 2)
        return ("✅" if round(abs(d), 6) <= tol else "⚠️"), d, f"±{tol:g} pb"
    if tipo == "abs":
        d = round(informe - nexora, 3)
        return ("✅" if round(abs(d), 6) <= tol else "⚠️"), d, f"±{tol:g}"
    d = round((informe / nexora - 1) * 100, 3) if nexora else None
    if d is None:
        return "⚠️", None, f"±{tol:g} %"
    return ("✅" if round(abs(d), 6) <= tol else "⚠️"), d, f"±{tol:g} %"


def cotejar_panel(texto_panel, fecha, raiz=RAIZ):
    filas = []
    for f in extraer_panel(texto_panel):
        n = valor_nexora(f["id"], fecha, raiz)
        if not n or n[0] is None:
            filas.append({**f, "estado": "—", "nexora": None, "fecha_nexora": None, "fuente": None, "dif": None, "tolerancia": None})
            continue
        est, dif, tol = comparar(f["id"], f["valor"], n[0])
        filas.append({**f, "estado": est, "nexora": n[0], "fecha_nexora": n[1], "fuente": n[2], "dif": dif, "tolerancia": tol})
    return filas


# ---------------------------------------------------------------- calendario B.3 y Fed
SINONIMOS = {"ipc": "ipc", "cpi": "ipc", "ipp": "ipp", "ppi": "ipp", "nfp": "empleo", "nominas": "empleo", "empleo": "empleo", "payrolls": "empleo", "pce": "pce", "pib": "pib", "gdp": "pib", "fomc": "fomc",
             "ism": "ism", "jolts": "jolts", "peticiones": "claims", "claims": "claims", "paro": "claims", "minoristas": "ventas", "retail": "ventas", "ventas": "ventas", "actas": "actas", "minutes": "actas",
             "adp": "adp", "michigan": "michigan", "confianza": "confianza", "bce": "bce", "ecb": "bce", "boj": "boj", "beige": "beige", "durables": "durables", "vivienda": "vivienda", "inventarios": "eia", "eia": "eia"}


def _claves(texto):
    return {SINONIMOS[w] for w in re.findall(r"[a-z]+", _norm(texto)) if w in SINONIMOS}


RX_FECHA_CAL = re.compile(r"(\d{1,2})\s*[/\-.]\s*(\d{1,2})(?:\s*[/\-.]\s*(\d{2,4}))?|(\d{1,2})[\s\-/.]*(?:de\s+)?(ene|feb|mar|abr|may|jun|jul|ago|sep|set|oct|nov|dic)[a-z]*", re.I)
RX_HORA = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")


def extraer_calendario(texto, ano):
    """[{fecha, hora, texto}] del B.3: fecha + hora en la misma línea (fila de tabla) o una cabecera de día seguida de líneas con hora. Sin hora legible no se cuenta."""
    ev, dia = [], None
    for l in texto.split("\n"):
        if not l.strip() or set(l.strip()) <= set("|-: "):
            continue
        h = RX_HORA.search(l)
        quitada = RX_HORA.sub(" ", l) if h else l
        mf = RX_FECHA_CAL.search(_norm(quitada))
        if mf:
            if mf.group(5):
                d = (ano, MESES[mf.group(5)], int(mf.group(4)))
            else:
                a = int(mf.group(3)) if mf.group(3) else ano
                d = (a + 2000 if a < 100 else a, int(mf.group(2)), int(mf.group(1)))
            try:
                dia = dt.date(*d).isoformat()
            except ValueError:
                dia = dia
        if h and dia:
            ev.append({"fecha": dia, "hora": f"{int(h.group(1)):02d}:{h.group(2)}", "texto": re.sub(r"[|*#]+", " ", quitada).strip()[:160]})
    return ev


def eventos_nexora(raiz, fechas):
    """[{fecha, hora_madrid, evento, importancia}] de la agenda actual y del histórico eventos_macro.csv para esas fechas."""
    out, vistos = [], set()
    ruta = P(raiz, "site", "data", "agenda.json")
    A = ((json.load(open(ruta, encoding="utf-8")) if os.path.exists(ruta) else {}).get("agenda")) or {}
    for e in (A.get("hoy") or []) + (A.get("proximos_7_dias") or []):
        if (e.get("fecha") in fechas) and (e.get("fecha"), e.get("hora_madrid"), e.get("evento")) not in vistos:
            vistos.add((e["fecha"], e.get("hora_madrid"), e.get("evento")))
            out.append({"fecha": e["fecha"], "hora_madrid": e.get("hora_madrid"), "evento": e.get("evento"), "importancia": e.get("importancia")})
    for r in leer_csv(P(raiz, "data", "eventos_macro.csv")):
        if r["fecha"] in fechas and (r["fecha"], r["hora_madrid"], r["evento"]) not in vistos:
            vistos.add((r["fecha"], r["hora_madrid"], r["evento"]))
            out.append({"fecha": r["fecha"], "hora_madrid": r["hora_madrid"], "evento": r["evento"], "importancia": r["importancia"]})
    return out


def en_semana_de_cambio(fecha):
    """Entre el 25-oct (Europa vuelve al horario de invierno) y el 1-nov (EE. UU.), Nueva York–Madrid son 5 h en vez de 6."""
    return "2026-10-25" <= fecha < "2026-11-01"


def cotejar_calendario(texto, fecha, raiz=RAIZ):
    ano = int(fecha[:4])
    inf = extraer_calendario(texto, ano)
    nx = eventos_nexora(raiz, {e["fecha"] for e in inf} | set())
    filas, usados = [], set()
    for e in inf:
        ck = _claves(e["texto"])
        cand = [(i, n) for i, n in enumerate(nx) if n["fecha"] == e["fecha"] and ck and ck & _claves(n["evento"])]
        if not cand:
            filas.append({**e, "estado": "—", "nexora": None, "nota": "NEXORA no tiene este evento en su agenda para ese día"})
            continue
        i, n = cand[0]
        usados.add(i)
        if n["hora_madrid"] == e["hora"]:
            filas.append({**e, "estado": "✅", "nexora": n, "nota": ""})
        else:
            d = (int(e["hora"][:2]) * 60 + int(e["hora"][3:])) - (int(n["hora_madrid"][:2]) * 60 + int(n["hora_madrid"][3:])) if n.get("hora_madrid") else None
            nota = "hora distinta"
            if d is not None and abs(d) == 60 and (en_semana_de_cambio(e["fecha"]) or fecha_cambio_cerca(e["fecha"])):
                nota += ": 1 h de diferencia, típica de las semanas con cambio de hora (Europa 25-oct, EE. UU. 1-nov): revisa si el informe usa la hora de Madrid o la de Nueva York + 6 h"
            filas.append({**e, "estado": "⚠️", "nexora": n, "nota": nota})
    for i, n in enumerate(nx):
        if i not in usados and n.get("importancia") == "ALTA":
            filas.append({"fecha": n["fecha"], "hora": None, "texto": "", "estado": "⚠️", "nexora": n, "nota": "falta en el informe: NEXORA lo tiene como ALTA"})
    return filas


def fecha_cambio_cerca(f):
    return "2026-10-24" <= f <= "2026-11-02"


def cotejar_fed(texto_informe, raiz=RAIZ):
    """Lado a lado: líneas literales del informe sobre probabilidades de la Fed y la próxima reunión de NEXORA (fedwatch.py), cada una con su fuente. Sin veredicto: son dos métodos distintos."""
    lineas = [l.strip(" -•*|") for l in texto_informe.split("\n") if re.search(r"fed|fomc|cme|fedwatch", _norm(l)) and re.search(r"%", l) and re.search(r"prob|recorte|subida|mantener|mantiene|sin cambios", _norm(l))][:6]
    ruta = P(raiz, "site", "data", "fedwatch.json")
    nx = None
    if os.path.exists(ruta):
        F = json.load(open(ruta, encoding="utf-8"))
        r0 = (F.get("reuniones") or [None])[0]
        if r0:
            nx = {"reunion": r0.get("reunion"), "subida": (r0.get("prob_reunion") or {}).get("subida"), "mantiene": (r0.get("prob_reunion") or {}).get("mantiene"), "bajada": (r0.get("prob_reunion") or {}).get("bajada"),
                  "fecha_precios": F.get("fecha_precios"), "fuente": "fedwatch.py: futuros de fondos federales a 30 días (ZQ, vía Yahoo Finance), método propio"}
    return {"informe": lineas, "informe_fuente": "el informe de Ruiz (fuente citada en su texto)", "nexora": nx}


def resumen_cotejo(filas):
    return {"ok": sum(1 for f in filas if f["estado"] == "✅"), "dif": sum(1 for f in filas if f["estado"] == "⚠️"), "sin": sum(1 for f in filas if f["estado"] == "—")}


def cotejar(parsed, fecha, raiz=RAIZ):
    panel = cotejar_panel(parsed["panel"], fecha, raiz)
    cal = cotejar_calendario(parsed["calendario"], fecha, raiz) if parsed["calendario"] else []
    return {"fecha": fecha, "panel": panel, "calendario": cal, "fed": cotejar_fed(parsed["panel"] + "\n" + parsed["oro_texto"] + "\n" + parsed["calendario"], raiz),
            "resumen": resumen_cotejo(panel), "resumen_calendario": resumen_cotejo(cal),
            "tolerancias": "tipos ±3 pb; DXY ±0,3; oro ±0,5 %; Brent/WTI ±1,5 %; VIX ±0,5; resto ±1 %"}


# ---------------------------------------------------------------- resultado del sesgo (T+1, T+5)
def _diario(raiz, activo):
    """{fecha: valor} con el último valor de cada fecha de dato (históricos propios)."""
    d = {}
    if activo == "real10":
        for r in leer_csv(P(raiz, "data", "historico_tipos.csv")):
            if r["serie"] == "real10":
                d[r["fecha_dato"]] = _f(r["valor"])
    else:
        for r in leer_csv(P(raiz, "data", "historico_precios.csv")):
            if r["activo"] == activo:
                d[r["fecha_dato"]] = _f(r["valor"])
    return {k: v for k, v in d.items() if v is not None}


def veredicto(sesgo, h, oro_pct, dxy_var, dfii_pb):
    """CUMPLIDO / FALLIDO / MIXTO con las reglas fijas del docstring."""
    if sesgo == "neutral":
        banda = 0.5 if h == 1 else 1.5
        return "CUMPLIDO" if round(abs(oro_pct), 6) <= banda else "FALLIDO"
    signo = 1 if sesgo == "alcista" else -1
    mov = round(oro_pct * signo, 6)
    if mov < -0.25:
        return "FALLIDO"
    if mov <= 0.25:
        return "MIXTO"
    contra = (dxy_var is not None and dxy_var * signo > 0) and (dfii_pb is not None and dfii_pb * signo > 0)      # DXY y tipo real suben para alcista (o bajan para bajista): ambos en contra
    return "MIXTO" if contra else "CUMPLIDO"


def evaluar(raiz=RAIZ, ahora=None):
    """Añade a data/analisis_resultados.csv el resultado a T+1 y T+5 de cada análisis vigente con sesgo cuando ya hay esas sesiones en los históricos. Solo añadir."""
    ahora = ahora or dt.datetime.now(UTC)
    ind = indice_vigente(raiz)
    oro, dxy, dfi = _diario(raiz, "oro"), _diario(raiz, "dxy"), _diario(raiz, "real10")
    fechas = sorted(oro)
    nuevas = []
    for e in ind:
        if e["sesgo_oro"] not in SESGOS or e["estado"] != "VIGENTE":
            continue
        d0 = e["fecha"]
        if d0 not in oro:
            continue
        for h in (1, 5):
            sig = [f for f in fechas if f > d0]
            if len(sig) < h:
                continue
            ft = sig[h - 1]
            op = round((oro[ft] / oro[d0] - 1) * 100, 3)
            dv = round(dxy[ft] - dxy[d0], 3) if ft in dxy and d0 in dxy else None
            dp = round((dfi[ft] - dfi[d0]) * 100, 1) if ft in dfi and d0 in dfi else None
            nuevas.append({"id": f"{e['id']}|T+{h}", "fecha": d0, "tipo": e["tipo"], "sesgo_oro": e["sesgo_oro"], "horizonte": h, "fecha_t": ft, "oro_pct": op, "dxy_var": "" if dv is None else dv,
                           "dfii10_pb": "" if dp is None else dp, "veredicto": veredicto(e["sesgo_oro"], h, op, dv, dp), "evaluado_utc": ahora.strftime("%Y-%m-%d %H:%M UTC")})
    return anadir_csv(P(raiz, "data", "analisis_resultados.csv"), nuevas, CAMPOS_RES, lambda r: r["id"])


def acumulado(res):
    out = {}
    for h in (1, 5):
        rr = [r for r in res if str(r["horizonte"]) == str(h)]
        c = sum(1 for r in rr if r["veredicto"] == "CUMPLIDO")
        out[f"T+{h}"] = {"n": len(rr), "cumplidos": c, "fallidos": sum(1 for r in rr if r["veredicto"] == "FALLIDO"), "mixtos": sum(1 for r in rr if r["veredicto"] == "MIXTO"),
                         "acierto_pct": round(100 * c / len(rr), 1) if rr else None, "conclusion": "n<20: sin conclusión" if len(rr) < MIN_N else "n≥20: evaluable"}
    return out


# ---------------------------------------------------------------- índice (solo añadir), JSON de la web
def indice_vigente(raiz=RAIZ):
    """Último estado de cada id del índice (VIGENTE o REVISADA)."""
    ult = {}
    for r in leer_csv(P(raiz, "data", "analisis_indice.csv")):
        ult[r["id"]] = r
    return sorted(ult.values(), key=lambda r: (r["fecha"], r["tipo"], int(r["version"] or 1)))


def _frontmatter(d):
    ls = ["---"]
    for k, v in d.items():
        ls.append(f"{k}: {json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v}")
    ls.append("---")
    return "\n".join(ls)


def resumen_publico(parsed):
    """Lo único del texto que puede ir al repo público (visibilidad «resumen»): tesis, veredicto, K.2 y escenarios literales. Sin texto de prensa ni los bloques A–K."""
    return {"tesis_central": parsed["tesis_central"], "veredicto": parsed["veredicto"], "tesis_final": parsed["tesis_final"],
            "escenarios": [{k: e[k] for k in ("nombre", "condiciones", "confirmacion", "invalidacion")} for e in parsed["escenarios"]]}


def construir(raiz=RAIZ, ahora=None):
    """site/data/analisis.json: índice, cotejos, resúmenes públicos y resultados. El texto de los informes PRIVADOS no entra aquí."""
    ahora = ahora or dt.datetime.now(UTC)
    ind = indice_vigente(raiz)
    cot = {}
    ruta = P(raiz, "data", "analisis_cotejos.jsonl")
    if os.path.exists(ruta):
        for l in open(ruta, encoding="utf-8"):
            if l.strip():
                j = json.loads(l)
                cot[j["id"]] = j
    res = leer_csv(P(raiz, "data", "analisis_resultados.csv"))
    entradas = []
    previo = {}
    for e in ind:
        if e["estado"] == "VIGENTE":
            previo.setdefault(e["tipo"], []).append(e["id"])
    for e in ind:
        c = cot.get(e["id"]) or {}
        item = {k: e[k] for k in ("id", "fecha", "tipo", "version", "visibilidad", "sesgo_oro", "corte_madrid", "hash", "estado")}
        item["ruta_privada"] = f"analisis/{e['fecha'][:4]}/{e['id']}.md"
        item["ruta_publica"] = f"data/analisis/{e['fecha'][:4]}/{e['id']}.md" if e["visibilidad"] == "resumen" else None
        item["cotejo"] = {k: c.get(k) for k in ("panel", "calendario", "fed", "resumen", "resumen_calendario", "tolerancias")} if c else None
        item["resumen_publico"] = c.get("resumen_publico") if e["visibilidad"] == "resumen" else None
        item["resultados"] = [{k: r[k] for k in ("horizonte", "fecha_t", "oro_pct", "dxy_var", "dfii10_pb", "veredicto")} for r in res if r["id"].startswith(e["id"] + "|")]
        entradas.append(item)
    vig = [x for x in entradas if x["estado"] == "VIGENTE"]
    for x in vig:
        x["anterior"] = next((y["id"] for y in reversed(vig) if y["tipo"] == x["tipo"] and (y["fecha"], y["version"]) < (x["fecha"], x["version"])), None)
    return {"version": 1, "ok": True, "generado_utc": ahora.strftime("%Y-%m-%d %H:%M UTC"), "n": len(entradas), "entradas": entradas, "acumulado": acumulado(res), "min_n": MIN_N,
            "reglas": __doc__.split("3. RESULTADO")[1].strip() if "3. RESULTADO" in __doc__ else "",
            "fuente": "engine/analisis.py (data/analisis_indice.csv, data/analisis_cotejos.jsonl, data/analisis_resultados.csv; solo añadir)"}


def etapa(raiz=RAIZ, ahora=None):
    """Para build.py (modos cierre y diario): evalúa los análisis pendientes y reescribe analisis.json."""
    n = evaluar(raiz, ahora)
    J = construir(raiz, ahora)
    J["resultados_nuevos"] = n
    return J
