#!/usr/bin/env python3
"""
NEXORA · Activo por activo (Oro, Nasdaq 100, S&P 500, Bitcoin) para la nota premercado y el cerebro.

Junta en un bloque por activo:
  1) viento macro común (una_pagina: hoy y semana),
  2) el veredicto del monitor PROPIO del activo (oro_xau, indices, liquidez_cripto) con los datos que más
     empujan a favor y en contra,
  3) la huella institucional de ese activo,
  4) una tesis propia y lo que la rompería.
Si un monitor falla: SIN DATO (nunca se estima). No toca los informes.
"""
from __future__ import annotations

import concurrent.futures as cf
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ACTIVOS = ["Oro", "Nasdaq 100", "S&P 500", "Bitcoin"]
# NEXORA Terminal (web): mismo motor, más US30 y Russell 2000 con el motor de índices (por_indice de indices.py).
# El informe diario sigue usando ACTIVOS (cuatro); la web pasa activos=ACTIVOS_WEB a construir().
ACTIVOS_WEB = ACTIVOS + ["US30 · Dow Jones", "Russell 2000"]
INDICE_NOMBRE = {"Nasdaq 100": "Nasdaq 100", "S&P 500": "S&P 500", "US30 · Dow Jones": "Dow Jones (US30)", "Russell 2000": "Russell 2000"}
VIENTO_N = {"A FAVOR": 1, "EN CONTRA": -1, "SIN VIENTO CLARO": 0}
# veredicto del monitor propio → (+1 a favor, 0 neutro, −1 en contra)
VEREDICTO_N = {
    "CONFLUENCIA FAVORABLE": 1, "PREDOMINIO FAVORABLE": 1, "CONFLUENCIA CONTRARIA": -1, "PREDOMINIO CONTRARIO": -1, "MIXTO": 0,
    "RISK-ON": 1, "PREDOMINIO RISK-ON": 1, "RISK-OFF": -1, "PREDOMINIO RISK-OFF": -1,
    "GIRO DE LIQUIDEZ EN CURSO": 1, "SEÑALES INICIALES DE GIRO": 0, "SIN GIRO DE LIQUIDEZ": -1, "DRENAJE DE LIQUIDEZ": -1,
}
# palabras para filtrar las líneas de la huella de cada activo
HUELLA_KEY = {"Oro": ("GLD",), "Nasdaq 100": ("Nasdaq 100",), "S&P 500": ("S&P 500", "OPEX", "MSCI", "triple"),
              "Bitcoin": ("IBIT", "Bitcoin (CME)", "Strategy"), "US30 · Dow Jones": ("Dow",), "Russell 2000": ("Russell",)}
MOTOR_PROPIO = {"Oro": "dólar, tipo real, flujos de ETF y posicionamiento COMEX",
                "Nasdaq 100": "tipos, amplitud, beneficios y volatilidad",
                "S&P 500": "tipos, amplitud, beneficios y volatilidad",
                "US30 · Dow Jones": "ciclo, industriales, financieras y empresas maduras",
                "Russell 2000": "tipos, crédito high yield, condiciones financieras y economía doméstica",
                "Bitcoin": "liquidez en dólares (Tesoro, Fed, stablecoins) y apetito de riesgo"}
FAV_W = ("FAVORABLE", "RISK-ON")
CON_W = ("DESFAVORABLE", "RISK-OFF")


def _correr(mod):
    m = __import__(mod)
    M = m.medir()
    return M, m.evaluar(M)


def monitores():
    """Ejecuta los tres monitores en paralelo. Devuelve {nombre: (M, E) | Exception}."""
    out = {}
    with cf.ThreadPoolExecutor(3) as ex:
        fut = {ex.submit(_correr, k): k for k in ("oro_xau", "indices", "liquidez_cripto")}
        for f in cf.as_completed(fut):
            try:
                out[fut[f]] = f.result()
            except Exception as e:  # noqa: BLE001
                out[fut[f]] = e
    return out


def _nombres(lista, nombre_k, estados):
    """Nombres de los datos que empujan (se excluyen los marcados como sin efecto real)."""
    return [p[nombre_k] for p in lista if p.get("estado") in estados and p.get("valor")
            and not any(w in str(p.get("lectura", "")) for w in ("agotado", "despreciable"))]


def _items(lista, nombre_k, estados, n=2):
    r = []
    for p in lista:
        if p.get("estado") in estados and p.get("valor"):
            r.append(f"{p[nombre_k]} {p['valor']}" + (f" ({p['lectura']})" if p.get("lectura") else ""))
    return r[:n]


def _rotacion(E):
    """Rotación cíclico vs defensivo (XLY/XLP) con su validación histórica, del monitor de índices."""
    c = E.get("consumo") or {}
    if not c.get("valor"):
        return None
    return f"{c['lectura']} · {c['valor']}" + (f" · {c['aviso']}" if c.get("aviso") else "")


def _propio(a, R):
    """Veredicto + datos clave del monitor propio del activo."""
    if a == "Oro":
        x = R.get("oro_xau")
        if not isinstance(x, tuple):
            return None
        M, E = x
        c = E["confluencia"]
        nuc_ids = {p["id"] for p in c.get("nucleo", [])}
        P = [p for p in E["panel"] if p.get("estado") in FAV_W + CON_W]
        P.sort(key=lambda p: p["id"] not in nuc_ids)
        return {"veredicto": c["lectura"], "detalle": f"{c['favorables']} a favor / {c['contrarias']} en contra de {c['disponibles']} datos núcleo · precio: {c['precio']}",
                "favor": _items(P, "dato", ("FAVORABLE",)), "contra": _items(P, "dato", ("DESFAVORABLE",)), "favor_n": _nombres(P, "dato", ("FAVORABLE",)), "contra_n": _nombres(P, "dato", ("DESFAVORABLE",)), "avisos": E.get("avisos", [])}
    if a in ("Nasdaq 100", "S&P 500", "US30 · Dow Jones", "Russell 2000"):
        x = R.get("indices")
        if not isinstance(x, tuple):
            return None
        M, E = x
        en = E["entorno"]
        P = E["panel"]
        # amplitud y beneficios primero: son lo propio de la bolsa
        P = sorted(P, key=lambda p: p["id"] not in ("amplitud", "earnings", "vix_ts", "vix"))
        pi = next((x for x in (E.get("por_indice") or []) if x.get("indice") == INDICE_NOMBRE.get(a, a)), {})
        fac = " · ".join(f"{f['factor']} {f['estado'].lower()}" for f in pi.get("factores", []))
        extra = (f" · lo propio del {a}: {fac}" if fac else "") + (f" ({pi['que_lo_mueve']})" if pi.get("que_lo_mueve") else "")
        return {"veredicto": pi.get("entorno") or en["lectura"], "detalle": f"{en['risk_on']} risk-on / {en['risk_off']} risk-off de {en['disponibles']} · liquidez {en['liquidez']} · amplitud {en['breadth']}{extra}",
                "favor": _items(P, "dato", ("FAVORABLE",)), "contra": _items(P, "dato", ("DESFAVORABLE",)), "favor_n": _nombres(P, "dato", ("FAVORABLE",)), "contra_n": _nombres(P, "dato", ("DESFAVORABLE",)), "avisos": E.get("avisos", []), "rotacion": _rotacion(E)}
    if a == "Bitcoin":
        x = R.get("liquidez_cripto")
        if not isinstance(x, tuple):
            return None
        M, E = x
        ind = [dict(i, lectura=i.get("detalle")) for i in E["indicadores"]] + E.get("contexto", {}).get("panel", [])
        core = sorted(ind, key=lambda i: i.get("nivel") != "núcleo")
        cr = E["checklist_resumen"]
        return {"veredicto": E["lectura"], "detalle": f"checklist de liquidez {cr['cumple']}/{cr['total']} (drenan {cr['drenaje']}) · secuencia {E['secuencia_cumplidos']}/{len(E['secuencia'])} pasos",
                "favor": _items(core, "nombre", ("FAVORABLE",)), "contra": _items(core, "nombre", ("DESFAVORABLE",)), "favor_n": _nombres(core, "nombre", ("FAVORABLE",)), "contra_n": _nombres(core, "nombre", ("DESFAVORABLE",)), "avisos": E.get("avisos", [])}


def _tesis(a, v_sem, propio):
    """Tesis propia del activo: viento macro semanal + veredicto del monitor propio."""
    m = VIENTO_N.get(v_sem, 0)
    if not propio:
        p, ver = 0, "SIN DATO"
    else:
        ver = propio["veredicto"]
        p = VEREDICTO_N.get(ver, 0)
    s = m + p
    rompe = (propio or {}).get("favor_n" if s < 0 else "contra_n") or []
    rompe_t = f" Lo que la rompería: que ganen peso {' y '.join(rompe[:2])} (hoy ya empujan en sentido contrario)." if rompe else ""
    if m and p and m == p:
        sesgo = "ALCISTA" if s > 0 else "BAJISTA"
        return sesgo, f"{sesgo} con confluencia: la macro de la semana ({v_sem.lower()}) y su motor propio ({ver}) apuntan igual.{rompe_t}"
    if m and p and m != p:
        return "SIN TESIS", (f"SIN TESIS: choque de fuerzas. La macro de la semana va {v_sem.lower()}, pero su motor propio dice {ver}. "
                             f"Hasta que una gane, no hay ventaja.")
    if s:
        sesgo = "ALCISTA" if s > 0 else "BAJISTA"
        quien = f"la macro de la semana ({v_sem.lower()})" if m else f"su motor propio ({ver})"
        return f"{sesgo} DÉBIL", f"{sesgo} DÉBIL: solo lo empuja {quien}; lo otro está neutral.{rompe_t}"
    return "SIN TESIS", f"SIN TESIS: ni la macro ni su motor propio ({ver}) marcan dirección."


def construir(P1, P5, R, HU_md="", activos=None):
    """P1/P5: salida de una_pagina.construir (hoy / semana). R: monitores(). HU_md: texto de huella.md()."""
    s1 = {s["activo"]: s for s in P1.get("significa", [])}
    s5 = {s["activo"]: s for s in (P5 or {}).get("significa", [])}
    hl = [ln[2:] for ln in HU_md.splitlines() if ln.startswith("- ")]
    out = {}
    for a in (activos or ACTIVOS):
        pr = _propio(a, R)
        v5 = (s5.get(a) or {}).get("viento", "SIN VIENTO CLARO")
        sesgo, tesis = _tesis(a, v5, pr)
        out[a] = {"hoy": (s1.get(a) or {}).get("texto", "SIN DATO"), "semana": (s5.get(a) or {}).get("texto", "SIN DATO"), "viento_semana": v5,
                  "propio": pr, "huella": [h for h in hl if any(k in h for k in HUELLA_KEY.get(a, ()))], "sesgo": sesgo, "tesis": tesis}
    return out


EMO = {"Oro": "🥇", "Nasdaq 100": "💻", "S&P 500": "🏛️", "Bitcoin": "₿", "US30 · Dow Jones": "🏭", "Russell 2000": "🏪"}


def md(X):
    L = ["## 🔎 Activo por activo", ""]
    for a in [k for k in ACTIVOS_WEB if k in X]:
        x = X[a]
        pr = x["propio"]
        L += [f"### {EMO[a]} {a} · {x['sesgo']}", "",
              f"- **Macro hoy:** {x['hoy']}",
              f"- **Macro semana:** {x['semana']}"]
        if pr:
            L.append(f"- **Su motor propio** ({MOTOR_PROPIO[a]}): **{pr['veredicto']}** · {pr['detalle']}")
            if pr["favor"]:
                L.append("  - A favor: " + " · ".join(pr["favor"]))
            if pr["contra"]:
                L.append("  - En contra: " + " · ".join(pr["contra"]))
            if pr.get("rotacion"):
                L.append(f"  - 🔄 Rotación cíclico vs defensivo (XLY/XLP): {pr['rotacion']}")
            for av in pr["avisos"][:2]:
                L.append(f"  - ⚠️ {av}")
        else:
            L.append(f"- **Su motor propio:** SIN DATO hoy (el monitor no respondió; nunca se estima).")
        for h in x["huella"][:3]:
            L.append(f"- **Grandes:** {h}")
        L += [f"- **Tesis {a}:** {x['tesis']}", ""]
    return "\n".join(L)


def tesis_md(X):
    return "\n".join(f"- **{a}:** {X[a]['tesis']}" for a in ACTIVOS_WEB if a in X)


def sencillo(X):
    al = [a for a in ACTIVOS_WEB if a in X and X[a]["sesgo"].startswith("ALCISTA")]
    ba = [a for a in ACTIVOS_WEB if a in X and X[a]["sesgo"].startswith("BAJISTA")]
    st = [a for a in ACTIVOS_WEB if a in X and X[a]["sesgo"] == "SIN TESIS"]
    j = lambda xs: ", ".join(xs[:-1]) + " y " + xs[-1] if len(xs) > 1 else xs[0]
    p = []
    if al:
        p.append(f"Empujan a favor: {j(al)}")
    if ba:
        p.append(f"empujan en contra: {j(ba)}")
    if st:
        p.append(f"sin ventaja clara: {j(st)} (sus fuerzas se anulan; mejor esperar a que una gane)")
    t = "; ".join(p)
    return (t[0].upper() + t[1:] + ". " if t else "") + \
        "Cada activo tiene su propio motor: el oro mira al dólar y al tipo real, la bolsa a los beneficios y a cuántas empresas suben, y bitcoin a si entra o sale dinero del sistema."


def main():
    """CLI: python por_activo.py --fedwatch out/fedwatch_X.json --calendario out/calendario_X.json --huella out/huella_X.md --out out
    Escribe out/por_activo_AAAAMMDD.md y .json (bloque por activo + 4 tesis + en palabras sencillas)."""
    import argparse
    import datetime as dt
    import json
    import una_pagina
    ap = argparse.ArgumentParser()
    ap.add_argument("--fedwatch")
    ap.add_argument("--calendario")
    ap.add_argument("--huella")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    fw = json.load(open(a.fedwatch)) if a.fedwatch and os.path.exists(a.fedwatch) else None
    if fw is None:
        try:
            import fedwatch
            fw = fedwatch.medir()
        except Exception:  # noqa: BLE001
            fw = None
    cal = json.load(open(a.calendario)) if a.calendario and os.path.exists(a.calendario) else None
    hu = open(a.huella, encoding="utf-8").read() if a.huella and os.path.exists(a.huella) else ""
    P1 = una_pagina.construir(una_pagina.medir(1, fw), "nexora", cal, fw)
    try:
        P5 = una_pagina.construir(una_pagina.medir(5, fw), "nexora", cal, fw)
    except Exception:  # noqa: BLE001
        P5 = {}
    X = construir(P1, P5, monitores(), hu)
    os.makedirs(a.out, exist_ok=True)
    base = os.path.join(a.out, f"por_activo_{dt.date.today():%Y%m%d}")
    txt = md(X) + "\n\n## 🎯 Tesis (una por activo)\n\n" + tesis_md(X) + "\n\n## 🧠 En palabras sencillas\n\n" + sencillo(X) + "\n"
    open(base + ".md", "w", encoding="utf-8").write(txt)
    json.dump(X, open(base + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print(base + ".md")


if __name__ == "__main__":
    main()
