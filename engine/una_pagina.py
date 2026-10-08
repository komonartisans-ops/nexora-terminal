#!/usr/bin/env python3
"""
NEXORA · Página 1 de todos los informes: QUÉ LO HA MOVIDO → QUÉ SIGNIFICA → QUÉ VIGILAR → TESIS → EN PALABRAS SENCILLAS.

Regla: explicar el PORQUÉ (causa → efecto) con el dato que lo prueba. Nunca describir precios que el usuario ya ve
en su gráfico. Todo lo demás del informe pasa a «Anexo».

Motores (causas) medidos en la sesión (h=1) o en la semana (h=5):
  Fed (FedWatch propio: probabilidad de subida en la próxima reunión y tipo esperado), bono a 2 años, tipo real a 10 años,
  dólar (réplica DXY), miedo (VIX) y crédito de riesgo (high yield).
Efectos: Nasdaq 100, S&P 500, oro (LBMA), bitcoin (Coinbase).
Umbrales: CRITERIO NEXORA (fijos, abajo). Relación causa → efecto = mecanismo económico estándar; se marca cuando el
activo se mueve EN CONTRA de lo que explicaría la macro (motor propio).

Uso: python una_pagina.py --foco indices|oro|cripto|regimen|nexora [--h 1|5] [--fedwatch F.json] [--calendario C.json] [--out DIR]
→ out/una_pagina_FOCO_YYYYMMDD.json / .html (bloque listo para insertar tras la portada) / .md
"""
from __future__ import annotations

import argparse
import datetime as dt
import html as H
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from liquidez_cripto import coinbase, dxy_replica, ecb_fx, fred, get, safe  # noqa: E402
from oro_xau import lbma, okx_ohlc, treasury  # noqa: E402

# umbrales (sesión, semana) — CRITERIO NEXORA
UMB = {"fed": (10, 15), "t2y": (5, 10), "real": (4, 8), "dxy": (0.3, 0.6), "vix": (8, 12), "hy": (8, 15)}
MOV = {"Nasdaq 100": (0.8, 1.5), "S&P 500": (0.6, 1.2), "Oro": (0.7, 1.5), "Bitcoin": (2.0, 4.0),
       "US30 · Dow Jones": (0.6, 1.2), "Russell 2000": (1.0, 2.0)}
# sensibilidad de cada activo a que el motor SUBA (−2 fuerte en contra … +1 a favor)
SENS = {
    "Nasdaq 100": {"fed": -1.5, "t2y": -1, "real": -2, "dxy": -0.5, "vix": -1, "hy": -1},
    "S&P 500": {"fed": -1, "t2y": -1, "real": -1, "dxy": -0.5, "vix": -1, "hy": -1.5},
    "Oro": {"fed": -1, "t2y": -1, "real": -2, "dxy": -2, "vix": 0.5, "hy": 0},
    "Bitcoin": {"fed": -1.5, "t2y": -1, "real": -1, "dxy": -1.5, "vix": -1, "hy": -1},
    # Índices del monitor de índices (Cboe DJX y RUT). CRITERIO NEXORA: el Dow (valor, ciclo, multinacionales) es menos sensible a los tipos
    # que el Nasdaq; el Russell 2000 (pequeñas empresas, más deuda a tipo variable y financiación bancaria) es el más sensible a Fed, 2Y y crédito.
    "US30 · Dow Jones": {"fed": -0.75, "t2y": -0.5, "real": -1, "dxy": -0.5, "vix": -1, "hy": -1.25},
    "Russell 2000": {"fed": -2, "t2y": -1.5, "real": -1.5, "dxy": 0, "vix": -1, "hy": -2},
}
FOCO = {"indices": ["Nasdaq 100", "S&P 500"], "oro": ["Oro"], "cripto": ["Bitcoin"],
        "regimen": ["Nasdaq 100", "S&P 500", "Oro", "Bitcoin"], "nexora": ["Oro", "Nasdaq 100", "S&P 500", "Bitcoin", "US30 · Dow Jones", "Russell 2000"]}
AFECTA = {"indices": "índices", "oro": "oro", "cripto": "cripto", "regimen": "", "nexora": ""}
NAVY, GOLD, GREEN, RED, AMBER, GREY = "#0d1b2e", "#c9a961", "#1e6b4f", "#9b2d3a", "#a8741a", "#8b95a8"


_DIA = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
_MES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def f_dia(iso, hora=None):
    """«jue 8 oct · 14:30» en una sola línea."""
    d = dt.date.fromisoformat(iso)
    return f"{_DIA[d.weekday()]} {d.day} {_MES[d.month - 1]}" + (f" · {hora}" if hora else "")


def n(x, d=1, sg=True):
    s = f"{x:+,.{d}f}" if sg else f"{x:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def ch(s, k, pct=True):
    if not s or len(s) <= k:
        return None
    a, b = s[-1][1], s[-1 - k][1]
    return (a / b - 1) * 100 if pct else a - b


def cboe(sym):
    import csv
    import io
    raw = get(f"https://cdn.cboe.com/api/global/us_indices/daily_prices/{sym}_History.csv", timeout=60).decode()
    out = []
    for row in csv.reader(io.StringIO(raw)):
        try:
            out.append((dt.datetime.strptime(row[0], "%m/%d/%Y").date(), float(row[-1])))
        except (ValueError, IndexError):
            continue
    return out[-40:]


def nasdaq100():
    from indices import nq_hist
    return [(x[0], x[4]) for x in nq_hist("NDX", "index", 1)][-40:]


def medir(h=1, fw=None):
    E, err = {}, {}

    def g(k, fn, *a):
        v, e = safe(fn, *a)
        if e:
            err[k] = e
        return v
    nom, real = g("tesoro_nominal", treasury, "nominal", 1), g("tesoro_real", treasury, "real", 1)
    fx = g("bce", ecb_fx, 40)
    vix, spx, ndx = g("vix", cboe, "VIX"), g("spx", cboe, "SPX"), g("ndx", nasdaq100)
    oro = g("lbma", lbma)
    if not oro:  # LBMA falla a veces: proxy XAUT (OKX, oro tokenizado 1:1)
        x = g("xaut", okx_ohlc, "XAUT-USDT", 30)
        oro = [(r[0], r[4]) for r in x] if x else None
    btc = g("btc", coinbase, "BTC-USD", 20)
    djx, rut = g("cboe_djx", cboe, "DJX"), g("cboe_rut", cboe, "RUT")  # mismas series que el monitor de índices (indices.py)
    hy = g("hy", fred, "BAMLH0A0HYM2", (dt.date.today() - dt.timedelta(days=40)).isoformat())
    M = {}
    if nom:
        s = [(d, v["2 Yr"]) for d, v in nom.items() if "2 Yr" in v]
        M["t2y"] = {"valor": s[-1][1], "delta": ch(s, h, False) * 100, "fecha": s[-1][0].isoformat()}
    if real:
        s = [(d, v["10 YR"]) for d, v in real.items() if "10 YR" in v]
        M["real"] = {"valor": s[-1][1], "delta": ch(s, h, False) * 100, "fecha": s[-1][0].isoformat()}
    if fx:
        s = dxy_replica(fx)
        M["dxy"] = {"valor": s[-1][1], "delta": ch(s, h), "fecha": s[-1][0].isoformat()}
    if vix:
        M["vix"] = {"valor": vix[-1][1], "delta": ch(vix, h), "fecha": vix[-1][0].isoformat()}
    if hy:
        M["hy"] = {"valor": hy[-1][1] * 100, "delta": ch(hy, h, False) * 100, "fecha": hy[-1][0].isoformat()}
    if fw and fw.get("reuniones"):
        r0 = fw["reuniones"][0]
        k = min(2, len(fw["reuniones"]) - 1)
        hist = fw.get("historial") or []
        p_ant = hist[-1 - h]["prox_subida"] if len(hist) > h and hist[-1 - h]["reunion"] == r0["reunion"] else None
        d_tipo = fw["reuniones"][k]["tipo_1d_pb"] if h == 1 else fw["reuniones"][k]["tipo_5d_pb"]
        M["fed"] = {"valor": r0["prob_reunion"]["subida"], "antes": p_ant, "reunion": r0["reunion"],
                    "delta": (r0["prob_reunion"]["subida"] - p_ant) if p_ant is not None else None, "tipo_delta_pb": d_tipo,
                    "bajada": r0["prob_reunion"]["bajada"], "fecha": fw["fecha_precios"]}
    A = {}
    for nm, s in (("Nasdaq 100", ndx), ("S&P 500", spx), ("Oro", oro), ("Bitcoin", [(d, c) for d, c, _ in btc] if btc else None),
                  ("US30 · Dow Jones", [(d, v * 100) for d, v in djx] if djx else None), ("Russell 2000", rut)):
        if s:
            A[nm] = {"delta": ch(s, h), "fecha": s[-1][0].isoformat(), "valor": s[-1][1]}
    return {"h": h, "motores": M, "activos": A, "errores": err}


def texto_motor(k, m, sube):
    if k == "fed":
        base = f"la probabilidad de que la Fed SUBA tipos el {f_dia(m['reunion'])} pasa de {m['antes']:.0f} % a {m['valor']:.0f} %"
        return base
    if k == "t2y":
        return f"el bono a 2 años {'sube' if sube else 'baja'} {abs(m['delta']):.0f} pb (hasta {n(m['valor'], 2, False)} %)"
    if k == "real":
        return f"el tipo real a 10 años {'sube' if sube else 'baja'} {abs(m['delta']):.0f} pb"
    if k == "dxy":
        return f"el dólar {'se fortalece' if sube else 'se debilita'} {n(abs(m['delta']), 2, False)} %"
    if k == "vix":
        return f"el miedo (VIX) {'sube' if sube else 'baja'} {abs(m['delta']):.0f} %"
    if k == "hy":
        return f"financiarse le cuesta {'más' if sube else 'menos'} a las empresas de riesgo ({n(m['delta'], 0)} pb)"


RAZON = {("fed", True): "la Fed se ve más dura", ("fed", False): "la Fed se ve menos dura",
         ("t2y", True): "suben los tipos a corto plazo", ("t2y", False): "bajan los tipos a corto plazo",
         ("real", True): "sube el tipo real (lo que más les pesa)", ("real", False): "baja el tipo real (lo que más les ayuda)",
         ("dxy", True): "el dólar se fortalece", ("dxy", False): "el dólar se debilita",
         ("vix", True): "sube el miedo", ("vix", False): "baja el miedo",
         ("hy", True): "el crédito se encarece", ("hy", False): "el crédito se abarata"}

SENCILLO = {
    "fed": "La Fed pone el precio del dinero. Cuando el mercado deja de esperar que lo suba, los bonos pasan a pagar menos y el dinero busca rentabilidad en bolsa, oro y cripto; cuando espera subidas, ocurre lo contrario.",
    "t2y": "El bono a 2 años es la apuesta del mercado sobre lo que hará la Fed. Si baja, el mercado espera dinero más barato y eso ayuda a la bolsa, al oro y a cripto; si sube, los frena.",
    "real": "El tipo real es lo que paga un bono después de descontar la inflación. Si sube, guardar el dinero en bonos se vuelve atractivo y pierden atractivo lo que no paga intereses (oro, bitcoin) y las tecnológicas.",
    "dxy": "Oro y bitcoin se compran en dólares: si el dólar se fortalece, suelen bajar; si se debilita, suelen subir. Un dólar fuerte también endurece la financiación en todo el mundo.",
    "vix": "El VIX mide cuánto pagan los inversores por protegerse. Si sube, hay miedo y se vende riesgo; si baja, vuelve la calma.",
    "hy": "Es lo que pagan las empresas más endeudadas por financiarse. Si se encarece, el mercado de crédito se preocupa, y suele adelantarse a la bolsa.",
}


def construir(D, foco="regimen", cal=None, fw=None):
    h = D["h"]
    i = 0 if h == 1 else 1
    M, A = D["motores"], D["activos"]
    per = "hoy" if h == 1 else "esta semana"
    # 1) motores significativos
    sig = []
    for k, m in M.items():
        d = m.get("delta") if k != "fed" else m.get("delta")
        if d is None:
            continue
        sc = abs(d) / UMB[k][i]
        if sc >= 1:
            sig.append((sc, k, d > 0))
    sig.sort(reverse=True)
    # 2) viento por activo
    viento, razones, contrib = {}, {}, {}
    for a, sens in SENS.items():
        cs = []
        for sc, k, sube in sig:
            c = sens[k] * (1 if sube else -1) * min(sc, 3)
            if c:
                cs.append((c, k, sube))
        tot = sum(c for c, _, _ in cs)
        contrib[a] = cs
        viento[a] = "A FAVOR" if tot > 0.75 else "EN CONTRA" if tot < -0.75 else "SIN VIENTO CLARO"
        pos = sorted([x for x in cs if x[0] > 0], reverse=True)
        neg = sorted([x for x in cs if x[0] < 0])
        if viento[a] == "A FAVOR":
            razones[a] = RAZON[(pos[0][1], pos[0][2])] + (f" (pesa más que: {RAZON[(neg[0][1], neg[0][2])]})" if neg else "")
        elif viento[a] == "EN CONTRA":
            razones[a] = RAZON[(neg[0][1], neg[0][2])] + (f" (pesa más que: {RAZON[(pos[0][1], pos[0][2])]})" if pos else "")
        elif pos and neg:
            razones[a] = f"fuerzas opuestas: {RAZON[(pos[0][1], pos[0][2])]}, pero {RAZON[(neg[0][1], neg[0][2])]}"
        else:
            razones[a] = "la macro no ha cambiado lo suficiente"
    # 3) qué lo ha movido
    if sig:
        cadena = [texto_motor(k, M[k], sube) for _, k, sube in sig[:3]]
        neto = sum((1 if sube else -1) * (1 if k != "vix" else 0.5) for _, k, sube in sig[:3])
        concl = "el dinero se encarece" if neto > 0 else "el dinero se abarata" if neto < 0 else "señales mezcladas"
        movido = "; ".join(c[0].upper() + c[1:] if j == 0 else c for j, c in enumerate(cadena)) + f". En conjunto: {concl}."
    else:
        movido = f"Sin cambio macro relevante {per}: ni la Fed, ni los tipos, ni el dólar, ni el miedo se han movido por encima de los umbrales. Lo que se mueva {per} lo explican flujos o noticias concretas, no un cambio de fondo."
    # 4) qué significa (activos del foco primero)
    orden = FOCO.get(foco, FOCO["regimen"]) + [a for a in SENS if a not in FOCO.get(foco, [])]
    sign = []
    for a in orden[:6]:
        mv = (A.get(a) or {}).get("delta")
        if mv is None:
            coh = ""
        else:
            umbral = MOV[a][i]
            if abs(mv) < umbral:
                coh = ""
            elif (mv > 0 and viento[a] == "A FAVOR") or (mv < 0 and viento[a] == "EN CONTRA"):
                coh = " Su movimiento lo explica la macro."
            elif viento[a] == "SIN VIENTO CLARO":
                coh = " Se mueve por motivos propios, no por la macro."
            else:
                coh = " Se mueve EN CONTRA de la macro: el motor es propio (flujos, noticias), vigilar si se sostiene."
        sign.append({"activo": a, "viento": viento[a], "texto": f"{viento[a].capitalize()}: {razones[a]}.{coh}"})
    # 5) qué vigilar (máx. 3): próxima reunión de la Fed + datos de importancia ALTA que afectan al foco
    vig = []
    from zoneinfo import ZoneInfo
    ahora = dt.datetime.now(ZoneInfo("Europe/Madrid")).strftime("%Y-%m-%d %H:%M")
    if M.get("fed"):
        f = M["fed"]
        vig.append(f"Fed {f_dia(f['reunion'])}: hoy {f['valor']:.0f} % de subida" + (f", {f['bajada']:.0f} % de bajada" if f['bajada'] else "") +
                   ". Si esta cifra se mueve más de 15 puntos, cambia el viento para todo.")
    af = AFECTA.get(foco, "")
    for e in (cal or {}).get("eventos", []):
        if len(vig) >= 3:
            break
        if f"{e['fecha']} {e['hora_madrid'] or '23:59'}" > ahora and e["importancia"] == "ALTA" and (not af or af in e["afecta"]) and "FOMC" not in e["evento"]:
            vig.append(f"{f_dia(e['fecha'], e['hora_madrid'] or None)} · {e['evento']}: {e['que_mirar']}")
    # 6) tesis y palabras sencillas
    NOM = {"Oro": "el oro", "Bitcoin": "bitcoin", "Nasdaq 100": "el Nasdaq", "S&P 500": "el S&P 500"}
    fa = NOM[FOCO.get(foco, FOCO["regimen"])[0]]
    fa_k = FOCO.get(foco, FOCO["regimen"])[0]
    gira = vig[1].split(' · ')[-1].split(':')[0] if len(vig) > 1 else "el próximo dato de empleo o inflación"
    v_fa = viento.get(fa_k, "SIN VIENTO CLARO")
    cs = contrib.get(fa_k, [])
    pos = sorted([x for x in cs if x[0] > 0], reverse=True)
    neg = sorted([x for x in cs if x[0] < 0])
    if v_fa == "A FAVOR":
        tesis = f"Viento macro A FAVOR de {fa}: {RAZON[(pos[0][1], pos[0][2])]}" + (f", y eso pesa más que el freno ({RAZON[(neg[0][1], neg[0][2])]})" if neg else "") + f". Lo que puede girarlo: {gira}."
    elif v_fa == "EN CONTRA":
        tesis = f"Viento macro EN CONTRA de {fa}: {RAZON[(neg[0][1], neg[0][2])]}" + (f", y eso pesa más que el apoyo ({RAZON[(pos[0][1], pos[0][2])]})" if pos else "") + f". Lo que puede girarlo: {gira}."
    else:
        tesis = f"Sin viento macro claro para {fa}" + (f": {RAZON[(pos[0][1], pos[0][2])]}, pero {RAZON[(neg[0][1], neg[0][2])]}" if pos and neg else "") + f". Lo que puede inclinarlo: {gira}."
    COLA = {"indices": " En la bolsa, las tecnológicas son las más sensibles porque valen por beneficios que llegarán dentro de años.",
            "oro": " El oro no paga intereses: cuanto menos pagan los bonos, más atractivo resulta guardarlo.",
            "cripto": " Bitcoin es de lo primero que se compra cuando sobra dinero barato y de lo primero que se vende cuando se encarece."}
    sencillo = (SENCILLO[sig[0][1]] + COLA.get(foco, "")) if sig else "Hoy la macro no ha cambiado. Si ves movimientos en el gráfico, se deben a flujos o noticias concretas, no a un cambio de fondo: no hay que leer en ellos más de lo que son."
    fechas = sorted({m["fecha"] for m in M.values() if m.get("fecha")} | {a_["fecha"] for a_ in A.values() if a_.get("fecha")})
    corte = (f"Datos al {fechas[-1]}" if len(fechas) == 1 else f"Datos entre el {fechas[0]} y el {fechas[-1]} (cada fuente publica a su hora)") if fechas else ""
    tesis = tesis.replace(" de el ", " del ")
    return {"periodo": per, "corte": corte, "movido": movido, "significa": sign, "vigilar": vig[:3], "tesis": tesis, "sencillo": sencillo,
            "motores_significativos": [k for _, k, _ in sig], "errores": D.get("errores"),
            "detalle_viento": {a: [{"motor": k, "sube": sube, "peso": round(c, 2), "razon": RAZON[(k, sube)]} for c, k, sube in cs] for a, cs in contrib.items()},
            "motores": {k: {kk: vv for kk, vv in m.items() if kk in ("valor", "delta", "fecha", "antes", "reunion")} for k, m in M.items()},
            "activos": A,
            "fuente": "Tesoro de EE. UU. (2Y, 10Y real), BCE (réplica del dólar), Cboe (VIX, S&P 500), Nasdaq (Nasdaq 100), LBMA o XAUT/OKX si LBMA falla (oro), Coinbase (bitcoin), ICE BofA vía FRED (crédito), FedWatch NEXORA (futuros ZQ)."}


def color(v):
    return GREEN if v == "A FAVOR" else RED if v == "EN CONTRA" else AMBER


def html(P, titulo="Lo esencial"):
    E = H.escape
    filas = "".join(f"<tr><td style='padding:1.6mm 2mm;border-bottom:.5px solid #d0d0d0;width:24%'><b>{E(s['activo'])}</b></td>"
                    f"<td style='padding:1.6mm 2mm;border-bottom:.5px solid #d0d0d0'><span style='color:#fff;background:{color(s['viento'])};font-size:6.5pt;font-weight:bold;padding:.4mm 1.4mm;border-radius:1.5px'>{E(s['viento'])}</span> "
                    f"{E(s['texto'].split(': ', 1)[1] if ': ' in s['texto'] else s['texto'])}</td></tr>" for s in P["significa"])
    vig = "".join(f"<li style='margin:.8mm 0'>{E(v)}</li>" for v in P["vigilar"]) or "<li>Sin datos de importancia alta en los próximos días.</li>"
    return f"""<div style='page-break-after:always'>
<div style='font-size:7.5pt;letter-spacing:.25em;color:{GOLD};font-weight:bold'>{E(titulo.upper())} · LÉELO PRIMERO</div>
<div style='font-family:"DejaVu Serif",serif;font-size:15pt;color:{NAVY};margin:1mm 0 3mm'>Qué ha pasado {E(P['periodo'])}, por qué y qué vigilar</div>
<div style='border-left:3px solid {GOLD};background:{NAVY};color:#fff;padding:3.5mm 4.5mm;margin:0 0 4mm;font-size:9.5pt;line-height:1.5'>
<div style='color:{GOLD};font-size:7pt;letter-spacing:.15em;font-weight:bold;margin-bottom:1mm'>1 · QUÉ LO HA MOVIDO</div>{E(P['movido'])}</div>
<div style='color:{GOLD};font-size:7pt;letter-spacing:.15em;font-weight:bold;margin:2mm 0 1mm'>2 · QUÉ SIGNIFICA</div>
<table style='width:100%;border-collapse:collapse;font-size:8.8pt'>{filas}</table>
<div style='color:{GOLD};font-size:7pt;letter-spacing:.15em;font-weight:bold;margin:4mm 0 1mm'>3 · QUÉ VIGILAR</div>
<ul style='font-size:8.8pt;margin:0 0 3mm 4mm;padding:0'>{vig}</ul>
<div style='border:1px solid {NAVY};padding:3mm 4mm;margin:3mm 0;font-size:9.5pt'><b style='color:{NAVY}'>TESIS:</b> {E(P['tesis'])}</div>
<div style='border-left:3px solid {GOLD};background:#f7f4ec;padding:3mm 4mm;margin:3mm 0;font-size:9pt;line-height:1.5'><b>En palabras sencillas:</b> {E(P['sencillo'])}</div>
<div style='font-size:6.5pt;color:{GREY};margin-top:3mm'>{E(P.get('corte', ''))}. {E(P['fuente'])} Umbrales fijos CRITERIO NEXORA. Correlación ≠ causalidad: el «porqué» es el mecanismo económico estándar y se avisa cuando el precio va en contra. No es recomendación de inversión. Todo lo demás de este informe es ANEXO de consulta.</div>
</div>"""


def md(P):
    L = [f"## Lo esencial ({P['periodo']})", "", f"**1 · Qué lo ha movido:** {P['movido']}", "", "**2 · Qué significa:**"]
    L += [f"- **{s['activo']}** — {s['texto']}" for s in P["significa"]]
    L += ["", "**3 · Qué vigilar:**"] + [f"- {v}" for v in P["vigilar"]]
    L += ["", f"**Tesis:** {P['tesis']}", "", f"**En palabras sencillas:** {P['sencillo']}", "", "---", "_Anexo de consulta: todo lo que sigue._", ""]
    return "\n".join(L)


def generar(foco="regimen", h=1, fw_path=None, cal_path=None):
    fw = json.load(open(fw_path, encoding="utf-8")) if fw_path and os.path.exists(fw_path) else None
    if fw is None:
        try:
            import fedwatch
            fw = fedwatch.medir()
        except Exception:  # noqa: BLE001
            fw = None
    cal = json.load(open(cal_path, encoding="utf-8")) if cal_path and os.path.exists(cal_path) else None
    D = medir(h, fw)
    P = construir(D, foco, cal, fw)
    P["datos"] = D
    return P


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--foco", default="regimen", choices=list(FOCO))
    ap.add_argument("--h", type=int, default=1)
    ap.add_argument("--fedwatch")
    ap.add_argument("--calendario")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    P = generar(a.foco, a.h, a.fedwatch, a.calendario)
    os.makedirs(a.out, exist_ok=True)
    p = os.path.join(a.out, f"una_pagina_{a.foco}_{dt.date.today():%Y%m%d}.json")
    json.dump(P, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    open(p.replace(".json", ".html"), "w", encoding="utf-8").write(html(P))  # para insertar en informes que no usan los renders (NEXORA)
    open(p.replace(".json", ".md"), "w", encoding="utf-8").write(md(P))
    print(p)
    print(md(P))


if __name__ == "__main__":
    main()
