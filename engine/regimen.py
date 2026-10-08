#!/usr/bin/env python3
"""
NEXORA · MAPA DE RÉGIMEN MACRO CONJUNTO («el jefe» de los tres monitores).

Une los monitores de liquidez cripto, XAU/USD e índices USA con los datos macro oficiales y responde:
  · Macro Regime Map (§22 de las instrucciones del proyecto): crecimiento, inflación, empleo, liquidez, crédito,
    política monetaria, fiscal, condiciones financieras, curva, dólar, cross-asset y régimen conjunto.
  · ¿Los tres monitores cuentan la misma historia? (concordancia) y ¿hay un MOTOR COMÚN? (2Y, 10Y real, dólar, NFCI, liquidez).
  · Patrón cross-asset del último mes (shock de tipos reales, huida al refugio, liquidez, reflación, desinflación, estrés de crédito).
  · Contradicciones entre mercados (lo que un activo hace y la macro no explica).
  · Las preguntas del §34 respondidas con datos.
Todo es HECHO (dato con fuente) o CRITERIO NEXORA (umbral fijo, publicado en METODOLOGIA_REGIMEN.md). Nada se estima.

    python regimen.py [--cripto JSON] [--oro JSON] [--indices JSON] [--out DIR]
Sin JSON, ejecuta los tres monitores (≈ 6-8 min). Con JSON (salidas del día de cada monitor), solo descarga la macro.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from liquidez_cripto import fred, safe  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
HOY = dt.date.today()
U = {  # CRITERIO NEXORA
    "encuestas_3m": 3.0, "nfp_3m_miles": 25, "retail_pp": 1.0, "claims_pct": 5.0, "indpro_pp": 1.0,
    "infl_pp": 0.3, "be_20d_pb": 10, "mich_pp": 0.3, "sahm": 0.5, "sahm_3m": 0.1,
    "hy_4s_pb": 25, "ig_4s_pb": 10, "credito_pp": 1.0, "fed_6m_pb": 20, "mercado_pb": 25, "fiscal_pp": 0.5,
    "nfci_4s": 0.02, "curva_20d_pb": 5, "dxy_20d_pct": 1.0, "real_20d_pb": 15, "patron_min": 0.75,
}
F = ["PAYEMS", "ICSA", "RSAFS", "INDPRO", "CPILFESL", "PCEPILFE", "MICH", "SAHMREALTIME", "UNRATE", "TOTBKCR", "MTSDS133FMS", "GDP",
     "DFEDTARU", "EFFR", "WALCL", "T10Y3M", "DTWEXBGS", "CBBTCUSD", "CBETHUSD", "GACDFSA066MSFRBPHI", "GACDISA066MSFRBNY", "BACTSAMFRBDAL",
     "BAMLH0A0HYM2", "BAMLC0A0CM", "NFCI", "T10YIE"]


_DIA = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
_MES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _fd(iso, hora=None):
    d = dt.date.fromisoformat(iso)
    return f"{_DIA[d.weekday()]} {d.day} {_MES[d.month - 1]}" + (f" · {hora}" if hora else "")


def cargar(path):
    D = json.load(open(path, encoding="utf-8"))
    return D["metricas"], D["evaluacion"]


def medir(cripto=None, oro=None, indices=None):
    R, err = {"generado_utc": dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}, {}
    for nm, path, mod in (("cripto", cripto, "liquidez_cripto"), ("oro", oro, "oro_xau"), ("indices", indices, "indices")):
        if path:
            v, e = safe(cargar, path)
        else:
            def run(mod=mod):
                m = __import__(mod)
                M = m.medir()
                return M, m.evaluar(M)
            v, e = safe(run)
        if e:
            err[f"monitor_{nm}"] = e
        else:
            R[nm] = {"M": v[0], "E": v[1]}
    S = {}
    for sid in F:
        v, e = safe(fred, sid, "2018-01-01")
        if e:
            err[sid] = e
        else:
            S[sid] = v
    R["fred"] = S
    try:
        import fedwatch
        R["fedwatch"] = fedwatch.medir()
    except Exception as e:  # noqa: BLE001
        err["fedwatch"] = f"{type(e).__name__}: {e}"
    R["errores"] = err
    return R


# ----------------------------------------------------------------- utilidades
def last(s, k=1):
    return s[-k][1] if s and len(s) >= k else None


def yoy(s, k=12):
    return (s[-1][1] / s[-1 - k][1] - 1) * 100 if s and len(s) > k else None


def ann3(s):
    return ((s[-1][1] / s[-4][1]) ** 4 - 1) * 100 if s and len(s) > 4 else None


def asof(s, d):
    c = [v for x, v in s if x <= d]
    return c[-1] if c else None


def voto(x, tol):
    if x is None:
        return 0
    return 1 if x > tol else -1 if x < -tol else 0


def f1(x, d=1, s=True):
    return "—" if x is None else (f"{x:+.{d}f}" if s else f"{x:.{d}f}")


# ----------------------------------------------------------------- evaluación
def evaluar(R, calendario=None):
    S = R["fred"]
    I = (R.get("indices") or {}).get("M") or {}
    IE = (R.get("indices") or {}).get("E") or {}
    C = (R.get("cripto") or {}).get("M") or {}
    CE = (R.get("cripto") or {}).get("E") or {}
    O = (R.get("oro") or {}).get("M") or {}
    OE = (R.get("oro") or {}).get("E") or {}
    D = []

    def dim(n, estado, flecha, ev, fuente, puntos=None):
        D.append({"dimension": n, "estado": estado, "dir": flecha, "evidencia": ev, "fuente": fuente, "puntos": puntos})

    # 1 CRECIMIENTO
    ev, pts = [], 0
    reg = [S.get(k) for k in ("GACDFSA066MSFRBPHI", "GACDISA066MSFRBNY", "BACTSAMFRBDAL") if S.get(k)]
    if reg:
        a = statistics.mean(statistics.mean(x[1] for x in s[-3:]) for s in reg)
        b = statistics.mean(statistics.mean(x[1] for x in s[-6:-3]) for s in reg)
        v = voto(a - b, U["encuestas_3m"])
        pts += v
        ev.append(f"Encuestas manufactureras Fed (Filadelfia, NY, Dallas), media 3 meses {a:+.1f} vs {b:+.1f} los 3 anteriores")
    p = S.get("PAYEMS")
    if p and len(p) > 7:
        m3, m3p = (p[-1][1] - p[-4][1]) / 3, (p[-4][1] - p[-7][1]) / 3
        v = voto(m3 - m3p, U["nfp_3m_miles"])
        pts += v
        ev.append(f"Empleo (NFP) media 3 meses {m3:+.0f} mil vs {m3p:+.0f} mil ({p[-1][0]:%Y-%m})")
    r = S.get("RSAFS")
    if r and len(r) > 13:
        a3, a12 = ann3(r), yoy(r)
        pts += voto(a3 - a12, U["retail_pp"])
        ev.append(f"Ventas minoristas 3 meses anualizado {a3:+.1f} % vs {a12:+.1f} % interanual ({r[-1][0]:%Y-%m})")
    ip = S.get("INDPRO")
    if ip and len(ip) > 13:
        a3, a12 = ann3(ip), yoy(ip)
        pts += voto(a3 - a12, U["indpro_pp"])
        ev.append(f"Producción industrial 3 meses anualizado {a3:+.1f} % vs {a12:+.1f} % interanual ({ip[-1][0]:%Y-%m})")
    c = S.get("ICSA")
    if c and len(c) > 17:
        m4, m13 = statistics.mean(x[1] for x in c[-4:]), statistics.mean(x[1] for x in c[-17:-4])
        d = (m4 / m13 - 1) * 100
        pts -= voto(d, U["claims_pct"])
        ev.append(f"Peticiones de paro media 4 semanas {m4:,.0f} vs {m13:,.0f} las 13 anteriores ({d:+.1f} %)")
    # confirmación de mercado (no vota): consumo discrecional vs básico (XLY/XLP) + consumo real
    CONS = None
    if I.get("consumo"):
        try:
            from indices import cargar_json, consumo_resumen
            CONS = consumo_resumen(I["consumo"], cargar_json("evidencia_indices.json") or IE.get("evidencia")) or IE.get("consumo")
        except Exception:  # noqa: BLE001  (indices.py no disponible: se usa el resumen ya calculado por el monitor de índices)
            CONS = IE.get("consumo")
        if CONS:
            ev.append(f"Confirmación de mercado (no vota): {CONS['valor']} → {CONS['lectura']}")
    crec = "ACELERANDO" if pts >= 2 else "DESACELERANDO" if pts <= -2 else "ESTABLE"
    dim("CRECIMIENTO", crec, "↑" if pts >= 2 else "↓" if pts <= -2 else "→", ev, "Fed regionales, BLS, Census, Fed G.17, DOL vía FRED", pts)
    g_pts = pts

    # 2 INFLACIÓN
    ev, pts = [], 0
    for sid, nm in (("CPILFESL", "IPC subyacente"), ("PCEPILFE", "PCE subyacente")):
        s = S.get(sid)
        if s and len(s) > 13:
            a3, a12 = ann3(s), yoy(s)
            pts += voto(a3 - a12, U["infl_pp"])
            ev.append(f"{nm}: 3 meses anualizado {a3:.1f} % vs {a12:.1f} % interanual ({s[-1][0]:%Y-%m})")
    be = S.get("T10YIE")
    if be and len(be) > 21:
        d = (be[-1][1] - be[-21][1]) * 100
        pts += voto(d, U["be_20d_pb"])
        ev.append(f"Inflación esperada a 10 años (breakeven) {be[-1][1]:.2f} % ({d:+.0f} pb en 20 sesiones)")
    mi = S.get("MICH")
    if mi and len(mi) > 4:
        d = mi[-1][1] - mi[-4][1]
        pts += voto(d, U["mich_pp"])
        ev.append(f"Expectativas de inflación a 1 año (U. Michigan) {mi[-1][1]:.1f} % ({d:+.1f} pp en 3 meses)")
    infl = "ACELERANDO" if pts >= 2 else "DESACELERANDO" if pts <= -2 else "ESTABLE"
    dim("INFLACIÓN", infl, "↑" if pts >= 2 else "↓" if pts <= -2 else "→", ev, "BLS, BEA, U. Michigan, Tesoro vía FRED", pts)
    i_pts = pts

    # 3 EMPLEO
    ev, pts = [], 0
    sh = S.get("SAHMREALTIME")
    if sh and len(sh) > 3:
        pts -= 2 if sh[-1][1] >= U["sahm"] else 0
        pts -= voto(sh[-1][1] - sh[-4][1], U["sahm_3m"])
        ev.append(f"Regla de Sahm en tiempo real {sh[-1][1]:.2f} (umbral de recesión 0,50; hace 3 meses {sh[-4][1]:.2f})")
    un = S.get("UNRATE")
    if un and len(un) > 12:
        ev.append(f"Tasa de paro {un[-1][1]:.1f} % (mínimo de 12 meses {min(x[1] for x in un[-12:]):.1f} %)")
        pts -= voto(un[-1][1] - min(x[1] for x in un[-12:]), 0.3)
    if p and len(p) > 7:
        m3 = (p[-1][1] - p[-4][1]) / 3
        pts += 1 if m3 > 150 else -1 if m3 < 50 else 0
    lab = "FORTALECIENDO" if pts >= 2 else "DEBILITANDO" if pts <= -2 else "ESTABLE"
    dim("EMPLEO", lab, "↑" if pts >= 2 else "↓" if pts <= -2 else "→", ev, "BLS vía FRED; Sahm (Fed St. Louis)", pts)

    # 4 LIQUIDEZ
    ev, pts = [], 0
    lec = CE.get("lectura")
    if lec:
        pts += {"GIRO DE LIQUIDEZ EN CURSO": 2, "SEÑALES INICIALES DE GIRO": 1, "SIN GIRO DE LIQUIDEZ": 0, "DRENAJE DE LIQUIDEZ": -2}.get(lec, 0)
        cr = CE.get("checklist_resumen") or {}
        ev.append(f"Monitor de liquidez cripto: {lec} ({cr.get('cumple', '—')}/8 condiciones, {cr.get('drenaje', '—')} en drenaje)")
    w = S.get("WALCL")
    if w and len(w) > 13:
        d = (w[-1][1] / w[-14][1] - 1) * 100
        pts += voto(d, 1.0)
        ev.append(f"Balance de la Fed {w[-1][1] / 1e6:.2f} T$ ({d:+.1f} % en 13 semanas)")
    for k, nm in (("tga", "TGA"), ("rrp", "RRP")):
        x = I.get(k)
        if x:
            ev.append(f"{nm} {x['valor_B']:,.1f} B$ ({x['4s_B']:+,.1f} B$ en 4 semanas)")
    rs = I.get("reservas")
    if rs:
        ev.append(f"Reservas bancarias {rs['valor_T']:.3f} T$ (1 mes {rs['4s_pct']:+.2f} %, 3 meses {rs['3m_pct']:+.2f} %)")
    m2 = I.get("m2")
    if m2:
        ev.append(f"M2 {m2['yoy_pct']:+.2f} % interanual ({m2['mes']})")
    liq = "EXPANDIÉNDOSE" if pts >= 2 else "CONTRAYÉNDOSE" if pts <= -2 else "NEUTRAL"
    dim("LIQUIDEZ", liq, "↑" if pts >= 2 else "↓" if pts <= -2 else "→", ev, "Fed H.4.1, Tesoro DTS, NY Fed, H.6; monitor cripto NEXORA", pts)

    # 5 CRÉDITO
    ev, pts, estres = [], 0, False
    hy, ig = S.get("BAMLH0A0HYM2"), S.get("BAMLC0A0CM")
    if hy and len(hy) > 21:
        d = (hy[-1][1] - hy[-21][1]) * 100
        pts -= voto(d, U["hy_4s_pb"])
        estres = d > U["hy_4s_pb"]
        ev.append(f"Diferencial high yield {hy[-1][1] * 100:.0f} pb ({d:+.0f} pb en 20 sesiones)")
    if ig and len(ig) > 21:
        d = (ig[-1][1] - ig[-21][1]) * 100
        pts -= voto(d, U["ig_4s_pb"])
        ev.append(f"Diferencial grado de inversión {ig[-1][1] * 100:.0f} pb ({d:+.0f} pb en 20 sesiones)")
    tb = S.get("TOTBKCR")
    if tb and len(tb) > 53:
        a13 = ((tb[-1][1] / tb[-14][1]) ** 4 - 1) * 100
        a52 = (tb[-1][1] / tb[-53][1] - 1) * 100
        pts += voto(a13 - a52, U["credito_pp"])
        ev.append(f"Crédito bancario 13 semanas anualizado {a13:+.1f} % vs {a52:+.1f} % interanual (H.8)")
    cred = "SE RELAJA (más crédito, diferenciales ↓)" if pts >= 2 else "SE ENDURECE (menos crédito, diferenciales ↑)" if pts <= -2 else "ESTABLE"
    dim("CRÉDITO", cred + (" · ESTRÉS EN HIGH YIELD" if estres else ""), "↑" if pts >= 2 else "↓" if pts <= -2 else "→", ev, "ICE BofA y Fed H.8 vía FRED", pts)

    # 6 POLÍTICA MONETARIA
    ev = []
    tg, ef = S.get("DFEDTARU"), S.get("EFFR")
    fed = "SIN DATO"
    mercado = None
    if tg:
        hace6 = asof(tg, tg[-1][0] - dt.timedelta(days=182))
        d = (tg[-1][1] - hace6) * 100 if hace6 is not None else 0
        fed = "RELAJANDO" if d <= -U["fed_6m_pb"] else "ENDURECIENDO" if d >= U["fed_6m_pb"] else "EN PAUSA"
        ev.append(f"Tipo objetivo de la Fed (techo) {tg[-1][1]:.2f} % ({d:+.0f} pb en 6 meses)")
    t2 = I.get("t2Y")
    if ef and t2:
        spread = (t2["valor"] - ef[-1][1]) * 100
        mercado = "DESCUENTA SUBIDAS" if spread > U["mercado_pb"] else "DESCUENTA RECORTES" if spread < -U["mercado_pb"] else "SIN CAMBIOS DESCONTADOS"
        ev.append(f"Bono a 2 años {t2['valor']:.2f} % vs tipo efectivo {ef[-1][1]:.2f} % → {spread:+.0f} pb: el mercado {mercado.lower()} (proxy; no es FedWatch)")
    FW = R.get("fedwatch")
    if FW and FW.get("reuniones"):
        r0 = FW["reuniones"][0]
        k = min(2, len(FW["reuniones"]) - 1)
        rk = FW["reuniones"][k]
        dif = rk["cambio_acumulado_pb"]
        mercado = "DESCUENTA SUBIDAS" if dif >= 12.5 else "DESCUENTA RECORTES" if dif <= -12.5 else "SIN CAMBIOS DESCONTADOS"
        ev.insert(0 if not ev else 1, f"FedWatch NEXORA ({FW['fecha_precios']}): reunión del {r0['reunion']} subida {r0['prob_reunion']['subida']:.0f} % / mantener {r0['prob_reunion']['mantiene']:.0f} % / bajada {r0['prob_reunion']['bajada']:.0f} %"
                  + (f" ({r0['subida_1d_pts']:+.0f} pts en 1 sesión)" if r0.get("subida_1d_pts") is not None else "")
                  + f"; tipo esperado tras la reunión del {rk['reunion']} {dif:+.0f} pb vs hoy ({FW['lectura'].lower()} que hace 5 sesiones) → el mercado {mercado.lower()}")
    pc = S.get("PCEPILFE")
    if ef and pc and len(pc) > 12:
        rr = ef[-1][1] - yoy(pc)
        ev.append(f"Tipo real de la Fed (efectivo − PCE subyacente) {rr:+.2f} %")
    ex = I.get("expectativas_letras")
    if ex:
        ev.append(f"Letra 1 año − tipo efectivo {ex['1a_menos_effr_pb']:+.0f} pb ({ex['5d_pb']:+.0f} pb en 5 sesiones)")
    est_mp = fed + (f" · MERCADO {mercado}" if mercado else "")
    dim("POLÍTICA MONETARIA", est_mp, "↓" if fed == "RELAJANDO" else "↑" if fed == "ENDURECIENDO" else "→", ev, "Fed vía FRED, U.S. Treasury")

    # 7 FISCAL
    ev = []
    ms, gdp = S.get("MTSDS133FMS"), S.get("GDP")
    fis = "SIN DATO"
    if ms and gdp and len(ms) >= 24:
        d12 = sum(x[1] for x in ms[-12:]) / 1000
        d12p = sum(x[1] for x in ms[-24:-12]) / 1000
        pib = gdp[-1][1]
        a, b = d12 / pib * 100, d12p / asof(gdp, ms[-13][0]) * 100
        fis = "EXPANSIVA (el déficit aumenta)" if a - b < -U["fiscal_pp"] else "RESTRICTIVA (el déficit se reduce)" if a - b > U["fiscal_pp"] else "NEUTRAL"
        ev.append(f"Saldo federal 12 meses {d12:,.0f} B$ = {a:+.1f} % del PIB (hace un año {b:+.1f} %; {ms[-1][0]:%Y-%m})")
        ev.append("Impulso = cambio del saldo en % del PIB. Un déficit mayor añade demanda y emisión de deuda (presión sobre el 10Y).")
    dim("FISCAL", fis, "↑" if fis.startswith("EXPANSIVA") else "↓" if fis.startswith("RESTRICTIVA") else "→", ev, "U.S. Treasury Monthly Treasury Statement y BEA vía FRED")

    # 8 CONDICIONES FINANCIERAS
    ev = []
    nf = S.get("NFCI")
    fc = "SIN DATO"
    if nf and len(nf) > 4:
        d = nf[-1][1] - nf[-5][1]
        fc = ("ENDURECIÉNDOSE" if d > U["nfci_4s"] else "RELAJÁNDOSE" if d < -U["nfci_4s"] else "ESTABLES") + (" · más laxas que la media histórica" if nf[-1][1] < 0 else " · más tensas que la media histórica")
        ev.append(f"NFCI {nf[-1][1]:+.3f} ({d:+.3f} en 4 semanas; negativo = más laxas que la media) · {nf[-1][0]}")
    vx = ((I.get("volatilidad") or {}).get("VIX") or {})
    if vx:
        ev.append(f"VIX {vx['valor']:.1f} (percentil {vx['percentil_1a']} del último año)")
    dim("CONDICIONES FINANCIERAS", fc, "↑" if fc.startswith("ENDUR") else "↓" if fc.startswith("RELAJ") else "→", ev, "Chicago Fed NFCI vía FRED; Cboe")

    # 9 CURVA
    ev = []
    t10 = I.get("t10Y")
    curva = "SIN DATO"
    if t2 and t10:
        s210 = (t10["valor"] - t2["valor"]) * 100
        d2, d10 = t2["20d_pb"], t10["20d_pb"]
        ds = d10 - d2
        forma = "INVERTIDA" if s210 < 0 else "PLANA" if s210 < 25 else "POSITIVA"
        if ds > U["curva_20d_pb"]:
            din = "BEAR STEEPENING (sube más el largo: prima por plazo, fiscal o inflación)" if d10 > 0 else "BULL STEEPENING (baja más el corto: el mercado descuenta recortes)"
        elif ds < -U["curva_20d_pb"]:
            din = "BEAR FLATTENING (sube más el corto: el mercado espera una Fed más dura)" if d2 > 0 else "BULL FLATTENING (baja más el largo: miedo al crecimiento)"
        else:
            din = "SIN CAMBIO DE PENDIENTE"
        curva = f"{forma} · {din.split(' (')[0]}"
        ev.append(f"2s10s {s210:+.0f} pb ({ds:+.0f} pb en 20 sesiones: 2Y {d2:+.0f} pb, 10Y {d10:+.0f} pb) → {din}")
        t3 = S.get("T10Y3M")
        if t3:
            ev.append(f"10 años − 3 meses {t3[-1][1] * 100:+.0f} pb ({t3[-1][0]})")
    dim("CURVA DE TIPOS", curva, "", ev, "U.S. Treasury; FRED T10Y3M")

    # 10 DÓLAR
    ev = []
    dx = I.get("dxy")
    dol = "SIN DATO"
    if dx:
        dol = "SE FORTALECE" if dx["20d_pct"] > U["dxy_20d_pct"] else "SE DEBILITA" if dx["20d_pct"] < -U["dxy_20d_pct"] else "ESTABLE"
        ev.append(f"DXY (réplica BCE) {dx['valor']:.2f} ({dx['5d_pct']:+.2f} % 5 sesiones, {dx['20d_pct']:+.2f} % 20 sesiones)")
    bd = S.get("DTWEXBGS")
    if bd and len(bd) > 63:
        ev.append(f"Dólar amplio (Fed) {bd[-1][1]:.2f} ({(bd[-1][1] / bd[-64][1] - 1) * 100:+.1f} % en 3 meses)")
    dim("DÓLAR", dol, "↑" if dol == "SE FORTALECE" else "↓" if dol == "SE DEBILITA" else "→", ev, "BCE; Fed H.10 vía FRED")

    # 11 CROSS-ASSET (último mes)
    ix = I.get("indices") or {}
    btc, eth = (C.get("cripto") or {}).get("BTC") or {}, (C.get("cripto") or {}).get("ETH") or {}
    oro = O.get("oro") or {}
    rl = I.get("real10Y") or {}
    CA = [("S&P 500", (ix.get("S&P 500") or {}).get("5d_pct"), (ix.get("S&P 500") or {}).get("20d_pct"), "%"),
          ("Nasdaq 100", (ix.get("Nasdaq 100") or {}).get("5d_pct"), (ix.get("Nasdaq 100") or {}).get("20d_pct"), "%"),
          ("Russell 2000", (ix.get("Russell 2000") or {}).get("5d_pct"), (ix.get("Russell 2000") or {}).get("20d_pct"), "%"),
          ("Oro (LBMA)", oro.get("5d_pct"), oro.get("20d_pct"), "%"),
          ("Bitcoin", btc.get("7d"), btc.get("30d"), "%"),
          ("Ether", eth.get("7d"), eth.get("30d"), "%"),
          ("10Y nominal", (t10 or {}).get("5d_pb"), (t10 or {}).get("20d_pb"), "pb"),
          ("10Y real", rl.get("5d_pb"), rl.get("20d_pb"), "pb"),
          ("DXY", (dx or {}).get("5d_pct"), (dx or {}).get("20d_pct"), "%"),
          ("VIX", vx.get("5d_pct"), None, "%"),
          ("High yield", None, ((hy[-1][1] - hy[-21][1]) * 100) if hy and len(hy) > 21 else None, "pb")]
    ca = {k: {"semana": a, "mes": b, "unidad": u} for k, a, b, u in CA}
    m = {k: v["mes"] for k, v in ca.items()}
    up = lambda k, t=0: m.get(k) is not None and m[k] > t  # noqa: E731
    dn = lambda k, t=0: m.get(k) is not None and m[k] < -t  # noqa: E731
    vix5 = vx.get("5d_pct")
    pat = {
        "SHOCK DE TIPOS REALES": [up("10Y real", U["real_20d_pb"]), dn("Oro (LBMA)"), (m.get("Nasdaq 100") is not None and m["Nasdaq 100"] < 1),
                                  up("DXY"), dn("Russell 2000")],
        "HUIDA AL REFUGIO (risk-off clásico)": [dn("S&P 500", 2), up("Oro (LBMA)"), dn("10Y nominal", 5), vix5 is not None and vix5 > 10, up("High yield", 10)],
        "EXPANSIÓN DE LIQUIDEZ": [dn("DXY"), up("Oro (LBMA)"), up("Bitcoin", 5), up("S&P 500"), dn("10Y real")],
        "CRECIMIENTO / REFLACIÓN": [up("S&P 500"), up("10Y nominal", 5), up("Russell 2000") and (m.get("Russell 2000") or 0) > (m.get("Nasdaq 100") or 0), dn("High yield"),
                                    (I.get("be10Y") or {}).get("20d_pb", 0) > 0],
        "DESINFLACIÓN FAVORABLE (goldilocks)": [up("S&P 500"), dn("10Y nominal", 5), vix5 is not None and vix5 < 0, not up("DXY", 1), dn("High yield")],
        "ESTRÉS DE CRÉDITO": [up("High yield", U["hy_4s_pb"]), dn("Russell 2000", 2), vix5 is not None and vix5 > 10, dn("S&P 500")],
    }
    patrones = sorted(({"patron": k, "cumple": sum(bool(x) for x in v), "de": len(v), "pct": round(sum(bool(x) for x in v) / len(v) * 100)} for k, v in pat.items()),
                      key=lambda x: -x["pct"])
    dominante = [p for p in patrones if p["pct"] >= U["patron_min"] * 100]
    ev = [f"{k}: semana {f1(v['semana'])} · mes {f1(v['mes'])} {v['unidad']}" for k, v in ca.items() if v["semana"] is not None or v["mes"] is not None]
    dim("CROSS-ASSET", ("PATRÓN: " + " + ".join(p["patron"] for p in dominante)) if dominante else "SIN PATRÓN DOMINANTE", "", ev,
        "Cboe, FRED, LBMA, Coinbase, Tesoro, BCE (datos de los tres monitores)")

    # 12 RÉGIMEN (cuadrante crecimiento × inflación + superposición de liquidez y riesgo)
    NOMBRES = {(1, -1): "EXPANSIÓN DESINFLACIONISTA («goldilocks»)", (1, 1): "REFLACIÓN / SOBRECALENTAMIENTO",
               (-1, 1): "ESTANFLACIÓN (crecimiento ↓ + inflación ↑)", (-1, -1): "DESACELERACIÓN DESINFLACIONISTA"}
    sg = lambda x: 1 if x > 0 else -1 if x < 0 else 0  # noqa: E731
    if abs(g_pts) >= 2 and abs(i_pts) >= 2:
        cuad, fuerza = NOMBRES[(sg(g_pts), sg(i_pts))], "claro (crecimiento y inflación con ±2 votos o más)"
    elif g_pts and i_pts and (abs(g_pts) >= 2 or abs(i_pts) >= 2):
        cuad = f"TRANSICIÓN · inclina a {NOMBRES[(sg(g_pts), sg(i_pts))]}"
        fuerza = f"incipiente: crecimiento {g_pts:+d} e inflación {i_pts:+d} votos (régimen claro con ±2 en ambos)"
    else:
        cuad = "SIN RÉGIMEN CLARO (crecimiento o inflación sin dirección)"
        fuerza = f"crecimiento {g_pts:+d} e inflación {i_pts:+d} votos"
    riesgo = (IE.get("entorno") or {}).get("lectura", "SIN DATO")

    # ------------- los tres monitores
    def norm(txt, fav, con):
        if not txt:
            return "SIN DATO"
        return "FAVORABLE" if any(x in txt for x in fav) else "CONTRARIA" if any(x in txt for x in con) else "NEUTRAL"
    mon = [
        {"monitor": "Liquidez cripto", "lectura": CE.get("lectura", "SIN DATO"), "sentido": norm(CE.get("lectura"), ("GIRO DE LIQUIDEZ EN CURSO", "SEÑALES INICIALES"), ("DRENAJE",)),
         "precio": ("BTC CONFIRMA" if (CE.get("secuencia") or [{}] * 5)[4].get("estado") == "CUMPLE" else "BTC NO CONFIRMA") if CE.get("secuencia") else "SIN DATO",
         "detalle": f"checklist {(CE.get('checklist_resumen') or {}).get('cumple', '—')}/8 · BTC 30 días {f1(btc.get('30d'))} %"},
        {"monitor": "Oro (XAU/USD)", "lectura": (OE.get("confluencia") or {}).get("lectura", "SIN DATO"),
         "sentido": norm((OE.get("confluencia") or {}).get("lectura"), ("FAVORABLE",), ("CONTRARI",)),
         "precio": (OE.get("confluencia") or {}).get("precio", "SIN DATO"), "detalle": f"oro 20 sesiones {f1(oro.get('20d_pct'))} %"},
        {"monitor": "Índices USA", "lectura": riesgo, "sentido": norm(riesgo, ("RISK-ON",), ("RISK-OFF",)),
         "precio": (ix.get("S&P 500") or {}).get("precio", "SIN DATO"), "detalle": f"amplitud {(IE.get('entorno') or {}).get('breadth', '—')} · S&P 20 sesiones {f1((ix.get('S&P 500') or {}).get('20d_pct'))} %"},
    ]
    sent = [x["sentido"] for x in mon if x["sentido"] != "SIN DATO"]
    if len(sent) == 3 and len(set(sent)) == 1:
        conc = f"LOS TRES COINCIDEN: {sent[0]}"
    elif sent and max(sent.count(s_) for s_ in set(sent)) == 2:
        mayor = max(set(sent), key=sent.count)
        conc = f"2 DE 3: {mayor} (" + ", ".join(f"{x['monitor']}: {x['sentido']}" for x in mon if x["sentido"] != mayor and x["sentido"] != "SIN DATO") + ")"
    else:
        conc = "DIVIDIDOS"

    # ------------- motor común
    MOT = []
    for id_, nm, val, tol, uni in (("t2y", "Bono a 2 años", (t2 or {}).get("5d_pb"), 5, "pb"), ("real", "10Y real", rl.get("5d_pb"), 5, "pb"),
                                   ("dxy", "Dólar (DXY)", (dx or {}).get("5d_pct"), 0.3, "%"), ("nfci", "Condiciones financieras (NFCI)", ((I.get("nfci") or {}).get("4s")), 0.02, ""),
                                   ("vix", "VIX (aversión al riesgo)", vix5, 10, "%")):
        if val is None:
            MOT.append({"motor": nm, "valor": "SIN DATO", "efecto": "SIN DATO"})
            continue
        MOT.append({"motor": nm, "valor": f"{val:+.2f} {uni}".strip() if uni != "pb" else f"{val:+.0f} pb",
                    "efecto": "EN CONTRA de oro, bolsa y cripto" if val > tol else "A FAVOR de oro, bolsa y cripto" if val < -tol else "NEUTRAL"})
    lq = {"EXPANDIÉNDOSE": "A FAVOR de oro, bolsa y cripto", "CONTRAYÉNDOSE": "EN CONTRA de oro, bolsa y cripto"}.get(liq, "NEUTRAL")
    MOT.append({"motor": "Liquidez (TGA/RRP/reservas/Fed)", "valor": liq, "efecto": lq})
    fav_m = sum(x["efecto"].startswith("A FAVOR") for x in MOT)
    con_m = sum(x["efecto"].startswith("EN CONTRA") for x in MOT)
    # misma definición que la validación histórica (4 motores: 2Y, 10Y real, DXY, NFCI)
    f4 = sum(x["efecto"].startswith("A FAVOR") for x in MOT[:4])
    c4 = sum(x["efecto"].startswith("EN CONTRA") for x in MOT[:4])
    motor4 = ("MOTOR A FAVOR (≥3 a favor, 0 en contra)" if f4 >= 3 and c4 == 0 else "MOTOR EN CONTRA (≥3 en contra, 0 a favor)" if c4 >= 3 and f4 == 0 else "SIN MOTOR COMÚN")
    motor = ("MOTOR COMÚN EN CONTRA: " + ", ".join(x["motor"] for x in MOT if x["efecto"].startswith("EN CONTRA")) if con_m >= 3 and fav_m == 0 else
             "MOTOR COMÚN A FAVOR: " + ", ".join(x["motor"] for x in MOT if x["efecto"].startswith("A FAVOR")) if fav_m >= 3 and con_m == 0 else
             "SIN MOTOR COMÚN DOMINANTE")

    # ------------- contradicciones
    X = []
    if m.get("Bitcoin") is not None and m["Bitcoin"] > 5 and liq != "EXPANDIÉNDOSE" and (rl.get("20d_pb") or 0) > 0:
        X.append(f"Bitcoin sube {m['Bitcoin']:+.1f} % en 30 días sin soporte de liquidez y con el tipo real al alza: el motor es propio de cripto (flujos, posicionamiento), no macro. Históricamente estos movimientos son menos fiables (ver monitor cripto).")
    if m.get("Oro (LBMA)") is not None and m["Oro (LBMA)"] > 2 and (rl.get("20d_pb") or 0) > U["real_20d_pb"]:
        X.append("El oro sube a pesar de que el tipo real sube con fuerza: otro motor (bancos centrales, geopolítica, refugio).")
    if m.get("Nasdaq 100") is not None and m["Nasdaq 100"] > 1 and (rl.get("20d_pb") or 0) > U["real_20d_pb"]:
        X.append(f"El Nasdaq 100 sube {m['Nasdaq 100']:+.1f} % en 20 sesiones mientras el 10Y real sube {rl['20d_pb']:+.0f} pb: los beneficios/temática (semis, IA) se imponen a los tipos. Vulnerable si los beneficios decepcionan.")
    if estres and (ix.get("S&P 500") or {}).get("vs_max_52s_pct", -99) > -3:
        X.append("Divergencia bolsa-crédito: el high yield se amplía mientras el S&P sigue cerca de máximos. Históricamente el crédito suele adelantarse, aunque no siempre.")
    if mercado == "DESCUENTA SUBIDAS" and fed == "RELAJANDO":
        X.append("La Fed ha bajado tipos en los últimos 6 meses, pero el bono a 2 años ya descuenta subidas: el mercado duda de que la relajación continúe.")
    if mercado == "DESCUENTA SUBIDAS" and fed == "EN PAUSA":
        X.append("La Fed está en pausa, pero el bono a 2 años cotiza por encima del tipo oficial: el mercado se inclina por subidas.")
    if vx and vx.get("percentil_1a", 100) < 30 and estres:
        X.append("VIX bajo con el crédito empeorando: la bolsa no refleja el estrés del crédito.")
    if (IE.get("entorno") or {}).get("breadth") == "SE DETERIORA" and ((ix.get("S&P 500") or {}).get("vs_max_52s_pct") or -99) > -3:
        X.append("S&P cerca de máximos con amplitud débil: subida sostenida por pocas empresas.")
    if dol == "SE FORTALECE" and (t2 or {}).get("20d_pb", 0) < -10:
        X.append("El dólar sube aunque bajan los tipos a 2 años: demanda de refugio en dólares (señal de estrés).")

    if CONS and CONS["estado_mercado"] == "DEFENSIVO" and crec == "ACELERANDO":
        X.append("El mercado se pone defensivo en consumo (XLY/XLP bajo su media y cayendo) mientras los datos de crecimiento aceleran: la bolsa descuenta una desaceleración que los datos aún no muestran (o se equivoca).")
    if CONS and CONS["estado_mercado"] == "RISK-ON EN CONSUMO" and crec == "DESACELERANDO":
        X.append("El mercado apuesta por el consumo (XLY/XLP al alza) mientras los datos de crecimiento desaceleran: optimismo que los datos no respaldan todavía.")

    # ------------- preguntas §34
    acel = [d["dimension"].lower() for d in D if d["dir"] == "↑" and d["dimension"] in ("CRECIMIENTO", "INFLACIÓN", "EMPLEO", "LIQUIDEZ", "CRÉDITO")]
    desa = [d["dimension"].lower() for d in D if d["dir"] == "↓" and d["dimension"] in ("CRECIMIENTO", "INFLACIÓN", "EMPLEO", "LIQUIDEZ", "CRÉDITO")]
    estr = []
    if estres:
        estr.append("crédito high yield")
    if (IE.get("entorno") or {}).get("breadth") == "SE DETERIORA":
        estr.append("amplitud de la bolsa")
    if (rl.get("5d_pb") or 0) > 15 or (rl.get("vel_z") or 0) > 2:
        estr.append(f"tipos reales (velocidad {f1(rl.get('vel_z'))}σ)")
    if vx and vx.get("valor", 0) > 25:
        estr.append("volatilidad")
    if ((I.get("volatilidad") or {}).get("estructura") or {}).get("vix_vix3m", 0) > 1:
        estr.append("estructura del VIX invertida")
    cal = calendario or {}
    cb = cal.get("proximos_bancos_centrales") or {}
    Q = [
        ("¿En qué fase del ciclo estamos?", f"{cuad} ({fuerza}). Crecimiento {crec.lower()}, inflación {infl.lower()}, empleo {lab.lower()}."),
        ("¿Qué está acelerando?", ", ".join(acel) or "Nada con claridad."),
        ("¿Qué está desacelerando?", ", ".join(desa) or "Nada con claridad."),
        ("¿Dónde aparece estrés?", ", ".join(estr) or "Sin focos de estrés según los umbrales."),
        ("¿Entra o sale liquidez?", f"{liq}. " + (CE.get("lectura", "") and f"Monitor cripto: {CE['lectura']}.")),
        ("¿Qué hacen los bancos centrales?", f"Fed {fed.lower()}" + (f"; mercado {mercado.lower()}" if mercado else "") +
         (f"; FedWatch: {R['fedwatch']['resumen']}" if R.get("fedwatch") else "") +
         ("; próximas decisiones: " + ", ".join(f"{k} {v['fecha']}" for k, v in cb.items()) if cb else "")),
        ("¿Qué dice el consumo (mercado frente a datos reales)?", (CONS["lectura"] + ". " + CONS["historico"]) if CONS else "Sin dato."),
        ("¿Coinciden los tres monitores?", conc),
        ("¿Hay un motor común?", motor),
        ("¿Qué contradicciones hay?", f"{len(X)} (ver sección de contradicciones)" if X else "Ninguna según las reglas."),
        ("¿Qué datos pueden cambiarlo?", " · ".join(f"{_fd(e['fecha'], e['hora_madrid'])} · {e['evento']}"
                                                    for e in (cal.get("eventos") or []) if e["importancia"] == "ALTA" and e["fecha"] >= HOY.isoformat())[:600] or "Ver calendario."),
    ]
    EVI = None
    try:
        EVI = json.load(open(os.path.join(HERE, "evidencia_regimen.json"), encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    # cuadrante simplificado comparable con el histórico (encuesta Filadelfia + IPC subyacente)
    simp = None
    ph, cp = S.get("GACDFSA066MSFRBPHI"), S.get("CPILFESL")
    if ph and cp and len(ph) > 6 and len(cp) > 13:
        g = statistics.mean(x[1] for x in ph[-3:]) - statistics.mean(x[1] for x in ph[-6:-3])
        inf = ann3(cp) - yoy(cp)
        simp = {"crecimiento": "↑" if g > 0 else "↓", "inflacion": "↑" if inf > 0 else "↓",
                "cuadrante": {(True, False): "EXPANSIÓN DESINFLACIONISTA", (True, True): "REFLACIÓN", (False, True): "ESTANFLACIÓN", (False, False): "DESACELERACIÓN DESINFLACIONISTA"}[(g > 0, inf > 0)],
                "detalle": f"Filadelfia media 3 meses {g:+.1f} · IPC subyacente 3m anualizado − interanual {inf:+.2f} pp"}
    return {"mapa": D, "cuadrante": cuad, "fuerza": fuerza, "cuadrante_simple": simp, "riesgo": riesgo, "liquidez": liq,
            "monitores": mon, "concordancia": conc, "motor": MOT, "motor_lectura": motor, "motor_historico": motor4, "cross_asset": ca, "patrones": patrones,
            "patron_dominante": [p["patron"] for p in dominante], "contradicciones": X, "preguntas": [{"pregunta": a, "respuesta": b} for a, b in Q],
            "umbrales": U, "evidencia": EVI, "consumo": CONS, "fedwatch": R.get("fedwatch")}


def to_md(R, E):
    L = [f"# NEXORA · Mapa de régimen macro conjunto · {R['generado_utc']}", "",
         f"**Régimen: {E['cuadrante']}** ({E['fuerza']}) · riesgo (índices): {E['riesgo']} · liquidez: {E['liquidez']}",
         f"**Monitores: {E['concordancia']}** · {E['motor_lectura']}", ""]
    L += ["## Macro Regime Map", ""] + [f"- **{d['dimension']}**: {d['estado']} — " + " · ".join(d["evidencia"]) for d in E["mapa"]]
    L += ["", "## Los tres monitores", ""] + [f"- {x['monitor']}: {x['lectura']} ({x['sentido']}) · precio {x['precio']} · {x['detalle']}" for x in E["monitores"]]
    L += ["", "## Motor común", ""] + [f"- {x['motor']}: {x['valor']} → {x['efecto']}" for x in E["motor"]]
    L += ["", "## Patrón cross-asset (último mes)", ""] + [f"- {p['patron']}: {p['cumple']}/{p['de']} ({p['pct']} %)" for p in E["patrones"]]
    L += ["", "## Contradicciones", ""] + ([f"- {x}" for x in E["contradicciones"]] or ["- Ninguna según las reglas."])
    L += ["", "## Preguntas clave", ""] + [f"- **{q['pregunta']}** {q['respuesta']}" for q in E["preguntas"]]
    if R.get("errores"):
        L += ["", "SIN DATO: " + "; ".join(f"{k}: {v}" for k, v in R["errores"].items())]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cripto")
    ap.add_argument("--oro")
    ap.add_argument("--indices")
    ap.add_argument("--calendario", help="calendario_YYYYMMDD.json (calendario.py)")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    R = medir(a.cripto, a.oro, a.indices)
    cal = json.load(open(a.calendario, encoding="utf-8")) if a.calendario else None
    E = evaluar(R, cal)
    os.makedirs(a.out, exist_ok=True)
    stamp = HOY.strftime("%Y%m%d")
    # se guarda solo lo necesario de cada monitor (no las series completas)
    lite = {"generado_utc": R["generado_utc"], "errores": R["errores"],
            "monitores": {k: {"M": {kk: vv for kk, vv in R[k]["M"].items() if not kk.startswith("_")}, "E": R[k]["E"]} for k in ("cripto", "oro", "indices") if k in R}}
    p = os.path.join(a.out, f"regimen_{stamp}.json")
    json.dump({"datos": lite, "evaluacion": E, "calendario": cal}, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=str)
    open(p.replace(".json", ".md"), "w", encoding="utf-8").write(to_md(R, E))
    print(p)
    print(json.dumps({k: E[k] for k in ("cuadrante", "fuerza", "riesgo", "liquidez", "concordancia", "motor_lectura", "patron_dominante")}, ensure_ascii=False))
    if R["errores"]:
        print("ERRORES:", json.dumps(R["errores"], ensure_ascii=False))


if __name__ == "__main__":
    main()
