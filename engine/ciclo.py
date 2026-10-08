#!/usr/bin/env python3
"""
NEXORA · Ciclo económico y riesgo de crisis en EE. UU. (economía real + crédito).

Panel de señales adelantadas con validación histórica propia contra las recesiones oficiales (NBER, FRED USREC):
  curva 10Y-3M (probit NY Fed), prima de riesgo de los bonos corporativos (EBP, Gilchrist-Zakrajšek, Fed),
  diferencial Baa-10Y, condiciones de crédito de los bancos (SLOOS), condiciones financieras (NFCI),
  peticiones de subsidio por desempleo, regla de Sahm en tiempo real, permisos de construcción, empleo temporal.
Más estrés de crédito diario (ICE BofA: IG, BBB, HY, CCC; FRED solo da 3 años).

Reglas: nunca se estima un dato. La validación usa los datos tal como están HOY (no vintage, salvo la regla de Sahm
en tiempo real): sirve para comparar señales, no para afirmar qué se sabía entonces. Pocas recesiones desde 1960 (8):
la muestra es pequeña y se dice. Umbrales = CRITERIO NEXORA salvo los publicados (Sahm 0,5; probit NY Fed).

Uso: python ciclo.py --out out [--estado ciclo_estado.json]  → out/ciclo_AAAAMMDD.json / .md
     (con --estado también devuelve "alertas": cambios de señal o saltos de crédito desde la ejecución anterior)
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from liquidez_cripto import fred, get  # noqa: E402

INICIO = "1959-01-01"
HORIZONTE = 18  # meses: una señal "acierta" si empieza una recesión en los 18 meses siguientes a su activación (CRITERIO NEXORA)


# ------------------------------------------------------------------ utilidades
def mensual(serie, como="media"):
    """Serie diaria/semanal → mensual {AAAA-MM: valor} (media o último dato del mes)."""
    g = {}
    for d, v in serie:
        g.setdefault(f"{d:%Y-%m}", []).append(v)
    return {k: (statistics.mean(v) if como == "media" else v[-1]) for k, v in sorted(g.items())}


def trimestral_a_mensual(serie):
    """Dato trimestral → se aplica a los 3 meses del trimestre (desde su mes de referencia)."""
    out = {}
    for d, v in serie:
        for k in range(3):
            m = d.month + k
            out[f"{d.year + (m - 1) // 12}-{(m - 1) % 12 + 1:02d}"] = v
    return out


def yoy(m):
    ks = sorted(m)
    return {k: (m[k] / m[ks[i - 12]] - 1) * 100 for i, k in enumerate(ks) if i >= 12 and m[ks[i - 12]]}


def phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def ebp_fed():
    """Fed (FEDS Notes): GZ spread, excess bond premium y su probabilidad de recesión a 12 meses. Mensual desde 1973."""
    raw = get("https://www.federalreserve.gov/econres/notes/feds-notes/ebp_csv.csv", timeout=60).decode()
    out = {}
    for r in csv.DictReader(io.StringIO(raw)):
        try:
            try:  # la Fed publica hoy fechas ISO (AAAA-MM-DD); antes eran MM/DD/AAAA: se aceptan las dos
                d = dt.datetime.strptime(r["date"], "%Y-%m-%d")
            except ValueError:
                d = dt.datetime.strptime(r["date"], "%m/%d/%Y")
            out[f"{d:%Y-%m}"] = {"gz": float(r["gz_spread"]), "ebp": float(r["ebp"]), "prob": float(r["est_prob"]) * 100}
        except (ValueError, KeyError):
            continue
    return out


# ------------------------------------------------------------------ datos
def medir():
    err, S = {}, {}

    def f(k, *a, **kw):
        try:
            return fred(*a, **kw)
        except Exception as e:  # noqa: BLE001
            err[k] = f"{type(e).__name__}: {e}"
            return None
    rec = f("usrec", "USREC", INICIO)
    S["usrec"] = {f"{d:%Y-%m}": v for d, v in rec} if rec else {}
    # curva 10Y-3M: mensual GS10 - TB3MS (historia larga) y diario T10Y3M (dato de hoy)
    g10, t3 = f("gs10", "GS10", INICIO), f("tb3ms", "TB3MS", INICIO)
    if g10 and t3:
        a, b = mensual(g10), mensual(t3)
        S["curva"] = {k: a[k] - b[k] for k in a if k in b}
    S["curva_diaria"] = f("t10y3m", "T10Y3M", (dt.date.today() - dt.timedelta(days=120)).isoformat())
    sahm = f("sahm", "SAHMREALTIME", INICIO)
    S["sahm"] = {f"{d:%Y-%m}": v for d, v in sahm} if sahm else {}
    ic = f("claims", "IC4WSA", INICIO)
    S["claims_sem"] = ic
    S["claims"] = mensual(ic, "ultimo") if ic else {}
    baa = f("baa", "BAA10YM", INICIO)
    S["baa"] = {f"{d:%Y-%m}": v for d, v in baa} if baa else {}
    S["baa_diaria"] = f("baa_d", "BAA10Y", (dt.date.today() - dt.timedelta(days=200)).isoformat())
    sl = f("sloos", "DRTSCILM", INICIO)
    S["sloos"] = trimestral_a_mensual(sl) if sl else {}
    S["sloos_ultimo"] = sl[-1] if sl else None
    nf = f("nfci", "NFCI", INICIO)
    S["nfci"] = mensual(nf, "ultimo") if nf else {}
    S["nfci_sem"] = nf
    pe = f("permisos", "PERMIT", INICIO)
    S["permisos"] = yoy({f"{d:%Y-%m}": v for d, v in pe}) if pe else {}
    th = f("temporal", "TEMPHELPS", INICIO)
    S["temporal"] = yoy({f"{d:%Y-%m}": v for d, v in th}) if th else {}
    try:
        e = ebp_fed()
        S["ebp"] = {k: v["ebp"] for k, v in e.items()}
        S["ebp_prob"] = {k: v["prob"] for k, v in e.items()}
        S["gz"] = {k: v["gz"] for k, v in e.items()}
    except Exception as ex:  # noqa: BLE001
        err["ebp"] = f"{type(ex).__name__}: {ex}"
    # estrés de crédito diario (ICE BofA OAS, % → pb)
    desde = (dt.date.today() - dt.timedelta(days=400)).isoformat()
    for k, sid in (("ig", "BAMLC0A0CM"), ("bbb", "BAMLC0A4CBBB"), ("hy", "BAMLH0A0HYM2"), ("ccc", "BAMLH0A3HYC")):
        x = f(k, sid, desde)
        S[f"oas_{k}"] = [(d, v * 100) for d, v in x] if x else None
    return S, err


# ------------------------------------------------------------------ señales (función: mes → True/False/None)
def _sig_curva(S, k):
    v = S.get("curva", {}).get(k)
    return None if v is None else v < 0


def _sig_desinversion(S, k):
    """Curva vuelve a positiva tras ≥3 meses invertida en los 12 meses previos (la «re-steepening»)."""
    c = S.get("curva", {})
    ks = sorted(c)
    if k not in c:
        return None
    i = ks.index(k)
    prev = [c[x] for x in ks[max(0, i - 12):i]]
    return c[k] >= 0 and sum(p < 0 for p in prev) >= 3


def _sig_ebp(S, k):
    v = S.get("ebp", {}).get(k)
    return None if v is None else v > 0.5


def _sig_baa(S, k):
    """Diferencial Baa-10Y sube ≥ 0,5 pp en 6 meses."""
    b = S.get("baa", {})
    ks = sorted(b)
    if k not in b or ks.index(k) < 6:
        return None
    return b[k] - b[ks[ks.index(k) - 6]] >= 0.5


def _sig_sloos(S, k):
    v = S.get("sloos", {}).get(k)
    return None if v is None else v > 20


def _sig_nfci(S, k):
    v = S.get("nfci", {}).get(k)
    return None if v is None else v > 0


def _sig_claims(S, k):
    """Peticiones de subsidio (media 4 semanas) ≥ 20 % sobre su mínimo de 12 meses."""
    c = S.get("claims", {})
    ks = sorted(c)
    if k not in c or ks.index(k) < 12:
        return None
    mn = min(c[x] for x in ks[ks.index(k) - 12:ks.index(k) + 1])
    return c[k] >= mn * 1.20


def _sig_sahm(S, k):
    v = S.get("sahm", {}).get(k)
    return None if v is None else v >= 0.5


def _sig_permisos(S, k):
    v = S.get("permisos", {}).get(k)
    return None if v is None else v <= -20


def _sig_temporal(S, k):
    v = S.get("temporal", {}).get(k)
    return None if v is None else v <= -3


SENALES = [
    # id, nombre, función, tipo, qué mide, fuente
    ("curva", "Curva 10 años − 3 meses invertida", _sig_curva, "adelantada", "el mercado espera tipos más bajos en el futuro: históricamente, que la Fed tendrá que bajar por una recesión", "Fed H.15 (GS10, TB3MS)"),
    ("desinversion", "Curva se «desinvierte» tras estar invertida", _sig_desinversion, "adelantada", "la Fed empieza a bajar tipos o el mercado lo descuenta: suele llegar justo antes de la recesión", "Fed H.15"),
    ("ebp", "Prima de riesgo de bonos corporativos (EBP) > 0,5", _sig_ebp, "adelantada", "los inversores exigen más por prestar a empresas de lo que justifica su riesgo de impago: miedo en el crédito", "Fed, Gilchrist-Zakrajšek"),
    ("baa", "Diferencial Baa − 10 años sube ≥ 0,5 pp en 6 meses", _sig_baa, "adelantada", "financiarse se encarece para las empresas medianas", "Moody's vía FRED (BAA10YM)"),
    ("sloos", "Bancos endurecen el crédito (> 20 % neto)", _sig_sloos, "adelantada", "los bancos piden más requisitos para prestar a empresas", "Fed, encuesta SLOOS (DRTSCILM)"),
    ("nfci", "Condiciones financieras más duras que la media (NFCI > 0)", _sig_nfci, "coincidente", "tipos, crédito, volatilidad y apalancamiento en conjunto", "Chicago Fed (NFCI)"),
    ("claims", "Peticiones de subsidio +20 % sobre su mínimo de 12 meses", _sig_claims, "adelantada", "las empresas empiezan a despedir", "Departamento de Trabajo (IC4WSA)"),
    ("permisos", "Permisos de construcción −20 % interanual", _sig_permisos, "adelantada", "la vivienda, el sector más sensible a los tipos, se frena", "Census (PERMIT)"),
    ("temporal", "Empleo temporal −3 % interanual", _sig_temporal, "adelantada", "las empresas recortan primero a los temporales", "BLS (TEMPHELPS)"),
    ("sahm", "Regla de Sahm en tiempo real ≥ 0,5", _sig_sahm, "confirmación", "el paro sube 0,5 puntos sobre su mínimo: la recesión ya ha empezado", "FRED (SAHMREALTIME, dato en tiempo real)"),
]


def recesiones(S):
    r = S.get("usrec", {})
    ks = sorted(r)
    return [k for i, k in enumerate(ks) if r[k] == 1 and (i == 0 or r[ks[i - 1]] == 0)]


def _meses(a, b):
    ya, ma = map(int, a.split("-"))
    yb, mb = map(int, b.split("-"))
    return (yb - ya) * 12 + (mb - ma)


def validar(S):
    """Para cada señal, episodios de activación (encendido tras ≥ 12 meses sin encenderse, para no contar parpadeos):
    adelantadas/coincidentes → ¿empezó una recesión en los 18 meses siguientes? (acierto, antelación, falsa alarma);
    confirmación (Sahm) → ¿se encendió en los 12 meses tras el inicio de cada recesión? (retraso)."""
    recs = recesiones(S)
    meses = sorted(S.get("usrec", {}))
    out = {}
    for sid, nom, fn, tipo, *_ in SENALES:
        on, ultimo_on = [], None
        for k in meses:
            v = fn(S, k)
            if v:
                if ultimo_on is None or _meses(ultimo_on, k) > 12:
                    on.append(k)
                ultimo_on = k
        if not on:
            out[sid] = None
            continue
        primero = on[0]
        recs_valid = [r for r in recs if r >= primero]
        if tipo == "confirmación":
            ret = []
            for r in recs_valid:
                d = [_meses(r, a) for a in on if 0 <= _meses(r, a) <= 12]
                if d:
                    ret.append(min(d))
            falsas = sum(1 for a in on if not any(0 <= _meses(r, a) <= 12 for r in recs))
            out[sid] = {"desde": primero, "recesiones": len(recs_valid), "avisadas": len(ret), "falsas_alarmas": falsas,
                        "activaciones": len(on), "retraso_mediano_meses": statistics.median(ret) if ret else None,
                        "antelacion_mediana_meses": None}
            continue
        aciertos_ant, falsas, cubiertas = [], 0, []
        for a in on:
            nxt = [r for r in recs if 0 <= _meses(a, r) <= HORIZONTE]
            if nxt:
                aciertos_ant.append(_meses(a, nxt[0]))
            elif any(0 < _meses(r, a) <= 12 for r in recs):
                pass  # se enciende dentro de una recesión ya empezada: ni acierto ni falsa
            elif _meses(a, meses[-1]) >= HORIZONTE:
                falsas += 1
        for r in recs_valid:
            if any(0 <= _meses(a, r) <= HORIZONTE for a in on):
                cubiertas.append(r)
        pendiente = [a for a in on if _meses(a, meses[-1]) < HORIZONTE and not any(0 <= _meses(a, r) for r in recs if r >= a)]
        out[sid] = {"desde": primero, "recesiones": len(recs_valid), "avisadas": len(cubiertas), "falsas_alarmas": falsas,
                    "activaciones": len(on), "antelacion_mediana_meses": statistics.median(aciertos_ant) if aciertos_ant else None,
                    "recesiones_avisadas": cubiertas, "activacion_pendiente": pendiente}
    return out


# ------------------------------------------------------------------ estado actual
def ultimo(m):
    if not m:
        return None, None
    k = sorted(m)[-1]
    return k, m[k]


def estado(S):
    hoy = []
    for sid, nom, fn, tipo, que, fuente in SENALES:
        base = S.get({"curva": "curva", "desinversion": "curva", "ebp": "ebp", "baa": "baa", "sloos": "sloos", "nfci": "nfci",
                      "claims": "claims", "sahm": "sahm", "permisos": "permisos", "temporal": "temporal"}[sid], {})
        k, v = ultimo(base)
        enc = fn(S, k) if k else None
        hoy.append({"id": sid, "senal": nom, "tipo": tipo, "que_mide": que, "fuente": fuente, "mes": k, "valor": v,
                    "encendida": enc})
    return hoy


def _cambio(serie, dias):
    if not serie or len(serie) < 2:
        return None
    d0 = serie[-1][0] - dt.timedelta(days=dias)
    prev = [v for d, v in serie if d <= d0]
    return serie[-1][1] - prev[-1] if prev else None


def credito_diario(S):
    out = {}
    for k, nom in (("ig", "Grado de inversión (IG)"), ("bbb", "BBB (el escalón más bajo del grado de inversión)"),
                   ("hy", "High yield (HY)"), ("ccc", "CCC (las empresas más frágiles)")):
        s = S.get(f"oas_{k}")
        if not s:
            continue
        vals = [v for _, v in s]
        pct = round(sum(x <= s[-1][1] for x in vals) / len(vals) * 100)
        out[k] = {"nombre": nom, "fecha": s[-1][0].isoformat(), "pb": round(s[-1][1]), "5d_pb": _r(_cambio(s, 7)),
                  "1m_pb": _r(_cambio(s, 30)), "3m_pb": _r(_cambio(s, 91)), "percentil_1a": pct,
                  "min_1a_pb": round(min(vals[-260:]))}
    return out


def _r(x):
    return None if x is None else round(x)


UMB_CRED = {"ig": (10, 25), "bbb": (12, 30), "hy": (25, 75), "ccc": (60, 150)}  # (5 días, 1 mes) en pb · CRITERIO NEXORA


def construir(S, err):
    V = validar(S)
    H = estado(S)
    C = credito_diario(S)
    cur_d = S.get("curva_diaria")
    cur = cur_d[-1][1] if cur_d else ultimo(S.get("curva", {}))[1]
    prob_ny = round(phi(-0.5333 - 0.6330 * cur) * 100, 1) if cur is not None else None
    ebp_k, ebp_p = ultimo(S.get("ebp_prob", {}))
    adel = [h for h in H if h["tipo"] == "adelantada" and h["encendida"] is not None]
    n_on = sum(h["encendida"] for h in adel)
    sahm_on = next((h["encendida"] for h in H if h["id"] == "sahm"), None)
    # estrés de crédito diario
    estres = []
    for k, c in C.items():
        u5, u1 = UMB_CRED[k]
        if c["5d_pb"] is not None and c["5d_pb"] >= u5:
            estres.append(f"{c['nombre']} +{c['5d_pb']} pb en 5 días")
        elif c["1m_pb"] is not None and c["1m_pb"] >= u1:
            estres.append(f"{c['nombre']} +{c['1m_pb']} pb en 1 mes")
    if sahm_on:
        fase = "RECESIÓN PROBABLE (la regla de Sahm ya salta)"
    elif n_on >= 4:
        fase = "RIESGO ALTO DE RECESIÓN (12-18 meses)"
    elif n_on >= 2:
        fase = "DESACELERACIÓN · RIESGO EN AUMENTO"
    else:
        fase = "EXPANSIÓN · RIESGO BAJO"
    if estres:
        fase_cred = "TENSIÓN DE CRÉDITO: " + "; ".join(estres)
    else:
        hy = C.get("hy")
        fase_cred = "CRÉDITO TRANQUILO" + (f" (HY {hy['pb']} pb, percentil {hy['percentil_1a']} del último año)" if hy else "")
    return {"fecha": dt.date.today().isoformat(), "fase": fase, "senales_adelantadas_encendidas": n_on, "senales_adelantadas_total": len(adel),
            "prob_recesion_curva_nyfed": prob_ny, "curva_10y3m": cur, "prob_recesion_ebp_fed": round(ebp_p, 1) if ebp_p is not None else None,
            "prob_ebp_mes": ebp_k, "credito": C, "estado_credito": fase_cred, "senales": H, "validacion": V,
            "recesiones_nber": recesiones(S), "errores": err,
            "nota": "Validación con datos actuales (no vintage, salvo Sahm en tiempo real). Horizonte de acierto 18 meses. "
                    "Solo 8 recesiones desde 1960: muestra pequeña. Correlación histórica, no garantía."}


# ------------------------------------------------------------------ texto
def n(x, d=1, sg=False):
    if x is None:
        return "SIN DATO"
    s = f"{x:+,.{d}f}" if sg else f"{x:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_val(h):
    v = h["valor"]
    if v is None:
        return "SIN DATO"
    u = {"curva": " pp", "desinversion": " pp", "ebp": "", "baa": " pp", "sloos": " % neto", "nfci": "", "claims": "",
         "sahm": " pp", "permisos": " % a/a", "temporal": " % a/a"}[h["id"]]
    if h["id"] == "claims":
        return f"{v:,.0f}".replace(",", ".")
    return n(v, 2 if h["id"] in ("curva", "desinversion", "ebp", "baa", "nfci", "sahm") else 1) + u


def md(R):
    L = ["## 🧭 Ciclo y riesgo de crisis (EE. UU.)", "",
         f"**Fase: {R['fase']}** · {R['senales_adelantadas_encendidas']} de {R['senales_adelantadas_total']} señales adelantadas encendidas.",
         f"**Crédito: {R['estado_credito']}.**", "",
         f"- Probabilidad de recesión a 12 meses según la curva (modelo de la Fed de Nueva York): **{n(R['prob_recesion_curva_nyfed'])} %** (curva 10Y−3M {n(R['curva_10y3m'], 2)} pp).",
         f"- Según la prima de riesgo de los bonos corporativos (modelo de la Fed, {R['prob_ebp_mes']}): **{n(R['prob_recesion_ebp_fed'])} %**.", "",
         "| Señal | Dato | Estado | Historial (desde) | Avisó | Falsas alarmas | Antelación típica |", "|---|---|---|---|---|---|---|"]
    for h in R["senales"]:
        v = R["validacion"].get(h["id"]) or {}
        est = "🔴 encendida" if h["encendida"] else "🟢 apagada" if h["encendida"] is False else "SIN DATO"
        av = f"{v.get('avisadas', '—')}/{v.get('recesiones', '—')}" if v else "—"
        ant = (f"{v['antelacion_mediana_meses']:.0f} meses antes" if v and v.get("antelacion_mediana_meses") is not None else
               f"{v['retraso_mediano_meses']:.0f} meses después del inicio" if v and v.get("retraso_mediano_meses") is not None else "—")
        L.append(f"| {h['senal']} ({h['tipo']}) | {fmt_val(h)} ({h['mes']}) | {est} | {(v or {}).get('desde', '—')} | {av} | {(v or {}).get('falsas_alarmas', '—')} | {ant} |")
    if R["credito"]:
        L += ["", "**Crédito al día (diferencial sobre el Tesoro, ICE BofA):** " + " · ".join(
            f"{c['nombre'].split(' (')[0]} {c['pb']} pb ({n(c['5d_pb'], 0, True)} en 5 días, {n(c['1m_pb'], 0, True)} en 1 mes, percentil {c['percentil_1a']} del año)"
            for c in R["credito"].values())]
    L += ["", f"> {R['nota']} Umbrales: CRITERIO NEXORA salvo Sahm (0,5) y el probit de la Fed de Nueva York."]
    if R.get("errores"):
        L.append("> Sin dato hoy: " + ", ".join(R["errores"]) + " (nunca se estima).")
    return "\n".join(L)


# ------------------------------------------------------------------ alertas (para alertas_causas / tareas)
def alertas(R, estado_prev):
    A = []
    prev = (estado_prev or {}).get("senales", {})
    for h in R["senales"]:
        p = prev.get(h["id"])
        if h["encendida"] is True and p is False:
            A.append({"nivel": "ALTA" if h["tipo"] != "coincidente" else "MEDIA", "tipo": "ciclo",
                      "texto": f"Se enciende «{h['senal']}» ({fmt_val(h)}, {h['mes']}): {h['que_mide']}. Fuente: {h['fuente']}."})
        elif h["encendida"] is False and p is True:
            A.append({"nivel": "MEDIA", "tipo": "ciclo", "texto": f"Se apaga «{h['senal']}» ({fmt_val(h)}, {h['mes']})."})
    for k, c in R["credito"].items():
        u5, u1 = UMB_CRED[k]
        clave = f"{k}:{c['fecha']}"
        if c["5d_pb"] is not None and c["5d_pb"] >= u5 and clave not in (estado_prev or {}).get("avisado", []):
            A.append({"nivel": "ALTA", "tipo": "credito", "clave": clave,
                      "texto": f"Crédito {c['nombre']}: +{c['5d_pb']} pb en 5 días hasta {c['pb']} pb ({c['fecha']}, ICE BofA vía FRED). "
                               "Las empresas pagan más por financiarse: suele adelantarse a la bolsa."})
    if (estado_prev or {}).get("fase") and estado_prev["fase"] != R["fase"]:
        A.append({"nivel": "ALTA", "tipo": "ciclo", "texto": f"Cambio de fase del ciclo: {estado_prev['fase']} → {R['fase']}."})
    return A


def nuevo_estado(R, estado_prev, A):
    av = list((estado_prev or {}).get("avisado", []))[-50:] + [a["clave"] for a in A if a.get("clave")]
    return {"fecha": R["fecha"], "fase": R["fase"], "senales": {h["id"]: h["encendida"] for h in R["senales"]}, "avisado": av}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out")
    ap.add_argument("--estado")
    a = ap.parse_args()
    S, err = medir()
    R = construir(S, err)
    if a.estado:
        prev = json.load(open(a.estado)) if os.path.exists(a.estado) else {}
        R["alertas"] = alertas(R, prev) if prev else []
        json.dump(nuevo_estado(R, prev, R["alertas"]), open(a.estado, "w"), ensure_ascii=False, indent=1)
    os.makedirs(a.out, exist_ok=True)
    base = os.path.join(a.out, f"ciclo_{dt.date.today():%Y%m%d}")
    json.dump(R, open(base + ".json", "w"), ensure_ascii=False, indent=1, default=str)
    open(base + ".md", "w", encoding="utf-8").write(md(R))
    print(base + ".md")


if __name__ == "__main__":
    main()
