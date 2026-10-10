#!/usr/bin/env python3
"""NEXORA · ALERTAS → Telegram. Sin LLM: todo el texto sale de plantillas deterministas.

Umbrales = los de las alertas NEXORA (CRITERIO NEXORA, fijos):
  Fed ±15 puntos de probabilidad o cambio del resultado más probable · 2Y ±12 pb · 10Y real ±8 pb · DXY ±0,7 %
  VIX > 25 o +20 % · diferenciales en 5 días: IG +10, BBB +12, HY +25, CCC +60 pb · cambio de señal o de fase del ciclo
  Oro ±2 % · BTC −7 % / +8 % · salidas de ETF de BTC > 500 M$ · SKEW de Cboe en zona alta relativa (percentil ≥ 90 de las últimas 500 sesiones; una alerta por episodio)
  Y al menos 2 de 3 confirmaciones encendidas (VIX/curva de plazos, crédito, fondos monetarios).
Cada alerta se envía UNA vez al día (estado en data/estado_alertas.json).
Mensaje de 4 líneas: 1 QUÉ HA CAMBIADO (dato + fuente) · 2 QUÉ SIGNIFICA (oro, índices, BTC) · 3 QUÉ VIGILAR (hora de Madrid)
· 4 EN PALABRAS SENCILLAS. No se describen precios que el usuario ya ve en su gráfico: se explica la causa.

Uso:  python engine/alertas.py            (evalúa con site/data/*.json y envía)
      python engine/alertas.py --prueba   (envía una alerta de prueba con datos reales actuales)
      python engine/alertas.py --seco     (evalúa e imprime, sin enviar)
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SITE_DATA = os.path.join(ROOT, "site", "data")
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)

import telegram  # noqa: E402
from una_pagina import RAZON, SENCILLO, SENS, UMB  # noqa: E402

URL = "https://komonartisans-ops.github.io/nexora-terminal/"
DIA = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
U = {"fed_pts": 15, "t2y_pb": 12, "real_pb": 8, "dxy_pct": 0.7, "vix_nivel": 25, "vix_pct": 20,
     "ig_pb": 10, "bbb_pb": 12, "hy_pb": 25, "ccc_pb": 60, "oro_pct": 2.0, "btc_baja_pct": -7.0, "btc_sube_pct": 8.0, "etf_btc_musd": -500, "skew_alto": 140, "skew_elevado": 135, "skew_percentil_alto": 90, "skew_percentil_elevado": 75, "skew_ventana": 500, "skew_confirmaciones_min": 2}


def leer(nombre, base=SITE_DATA):
    try:
        with open(os.path.join(base, nombre), encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def n(x, d=1):
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def sg(x, d=1):
    return ("+" if x > 0 else "−" if x < 0 else "") + n(abs(x), d)


def madrid_ahora():
    from zoneinfo import ZoneInfo
    return dt.datetime.now(ZoneInfo("Europe/Madrid"))


def fecha_linea(fecha_iso, hora=None):
    d = dt.date.fromisoformat(fecha_iso)
    return f"{DIA[d.weekday()]} {d.day} {MES[d.month - 1]}" + (f" · {hora}" if hora else "")


# ---------------------------------------------------------------- plantillas de significado
def significado(motor, sube):
    """Efecto del motor sobre oro, índices y BTC según las sensibilidades fijas NEXORA (interpretación, no hecho)."""
    s = 1 if sube else -1
    partes = []
    for nom, a in (("Oro", "Oro"), ("Índices", "Nasdaq 100"), ("BTC", "Bitcoin")):
        v = SENS[a].get(motor, 0) * s
        partes.append(f"{nom} {'a favor' if v > 0 else 'en contra' if v < 0 else 'neutro'}")
    return ", ".join(partes) + " (interpretación según sensibilidades fijas, no hecho)"


def vigilar(cal):
    ahora = madrid_ahora().strftime("%Y-%m-%d %H:%M")
    for e in (cal or {}).get("eventos", []):
        if e.get("importancia") == "ALTA" and f"{e['fecha']} {e.get('hora_madrid') or '23:59'}" > ahora:
            return f"{fecha_linea(e['fecha'], e.get('hora_madrid') or None)} (hora de Madrid) · {e['evento']}"
    return "sin dato de importancia alta en el calendario próximo"


def explicacion_macro(activo, mot):
    """¿La macro de hoy explica el movimiento del activo? mot = {motor: delta_sesion}."""
    tot, cs = 0.0, []
    for k, d in mot.items():
        if d is None or abs(d) < UMB[k][0]:
            continue
        c = SENS[activo].get(k, 0) * (1 if d > 0 else -1) * min(abs(d) / UMB[k][0], 3)
        if c:
            tot += c
            cs.append((abs(c), k, d > 0))
    if not cs:
        return "ningún motor macro supera su umbral hoy: el movimiento es propio (flujos o noticias), no macro"
    cs.sort(reverse=True)
    k, sube = cs[0][1], cs[0][2]
    return f"la macro empuja {'a favor' if tot > 0 else 'en contra'} ({RAZON[(k, sube)]})"


# ---------------------------------------------------------------- ETF de BTC (Farside, sin clave)
def etf_btc():
    """Último día con dato: (fecha, total M$) o None."""
    import urllib.request
    req = urllib.request.Request("https://farside.co.uk/btc/", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"})
    t = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "replace")
    ult = None
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", t, flags=re.S):
        c = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", x))).strip() for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, flags=re.S)]
        if len(c) >= 3 and re.match(r"\d{2} \w{3} \d{4}$", c[0]) and c[-1] not in ("-", ""):
            try:
                v = float(c[-1].replace(",", "").replace("(", "-").replace(")", ""))
                f = dt.datetime.strptime(c[0], "%d %b %Y").date()
                ult = (f, v)
            except ValueError:
                continue
    return ult


# ---------------------------------------------------------------- evaluación
def evaluar(D, estado):
    A, F, T, C, CAL = D.get("precios") or {}, D.get("fedwatch") or {}, D.get("tipos") or {}, D.get("ciclo") or {}, D.get("calendario")
    act = A.get("activos", {})
    out, no_eval = [], {}
    vig = vigilar(CAL)

    def al(clave, titulo, l1, l2, l4):
        out.append({"clave": clave, "titulo": titulo, "l1": l1, "l2": l2, "l3": vig, "l4": l4})

    mot = {"t2y": (T.get("t2y") or {}).get("d1_pb"), "real": (T.get("real10") or {}).get("d1_pb"),
           "dxy": (act.get("dxy") or {}).get("cambio_1d_pct"), "vix": (act.get("vix") or {}).get("cambio_1d_pct")}
    r0 = (F.get("reuniones") or [None])[0]
    if r0:
        mot["fed"] = r0.get("subida_1d_pts")

    # 2Y y tipo real
    for clave, key, nombre, umbral in (("t2y", "t2y", "Bono a 2 años", U["t2y_pb"]), ("real", "real10", "Tipo real a 10 años", U["real_pb"])):
        m = T.get(key)
        if not m or m.get("d1_pb") is None:
            no_eval[clave] = "SIN DATO (Tesoro de EE. UU.)"
            continue
        d = m["d1_pb"]
        if abs(d) >= umbral:
            al(clave, nombre, f"{nombre} {'sube' if d > 0 else 'baja'} {n(abs(d), 0)} pb en la sesión, hasta {n(m['valor'], 2)} % (Tesoro de EE. UU., dato del {fecha_linea(m['fecha'])}).",
               significado(clave, d > 0) + ".", SENCILLO[clave])
    # dólar
    d = mot["dxy"]
    if d is None:
        no_eval["dxy"] = "SIN DATO (Yahoo Finance DX-Y.NYB)"
    elif abs(d) >= U["dxy_pct"]:
        al("dxy", "Dólar", f"El índice dólar (DXY) {'sube' if d > 0 else 'baja'} {n(abs(d), 2)} % en la sesión (ICE vía Yahoo Finance, {fecha_linea(act['dxy']['fecha'])}).",
           significado("dxy", d > 0) + ".", SENCILLO["dxy"])
    # VIX
    v = act.get("vix")
    if not v or v.get("valor") is None:
        no_eval["vix"] = "SIN DATO (Cboe vía Yahoo Finance)"
    elif v["valor"] > U["vix_nivel"] or (v.get("cambio_1d_pct") or 0) >= U["vix_pct"]:
        al("vix", "Miedo (VIX)", f"El VIX está en {n(v['valor'], 1)} ({sg(v.get('cambio_1d_pct') or 0, 1)} % en la sesión; umbral: >25 o +20 %) (Cboe vía Yahoo Finance, {fecha_linea(v['fecha'])}).",
           significado("vix", True) + ".", SENCILLO["vix"])
    # Fed
    if r0:
        hist = [h for h in (F.get("historial") or []) if h.get("reunion") == r0["reunion"]]
        s1, b1 = r0["prob_reunion"]["subida"], r0["prob_reunion"]["bajada"]
        if len(hist) >= 2:
            s0, b0 = hist[-2]["prox_subida"], hist[-2]["prox_bajada"]
            ult = estado.get("fed_ultimo") or {}
            if ult.get("reunion") == r0["reunion"]:  # como alertas_causas.py: también frente al último aviso
                s0 = ult["subida"] if abs(s1 - ult["subida"]) > abs(s1 - s0) else s0
            dmax = max(abs(s1 - s0), abs(b1 - b0))
            rotulo = lambda s, b: max((s, "subida"), (100 - s - b, "mantener"), (b, "bajada"))[1]  # noqa: E731
            cambio = rotulo(s1, b1) != rotulo(s0, b0)
            if dmax >= U["fed_pts"] or cambio:
                sube = (s1 - s0) > (b1 - b0) or (s1 - s0) > 0
                al("fed", "Fed", f"Fed {fecha_linea(r0['reunion'])}: subida {n(s0, 0)} % → {n(s1, 0)} %, bajada {n(b0, 0)} % → {n(b1, 0)} %; resultado más probable: {rotulo(s1, b1)}"
                   f"{' (cambia frente a ayer)' if cambio else ''} (FedWatch NEXORA, futuros ZQ, precios del {fecha_linea(F['fecha_precios'])}).",
                   significado("fed", sube) + ".", SENCILLO["fed"])
            estado["fed_ultimo"] = {"reunion": r0["reunion"], "subida": s1}
        else:
            no_eval["fed"] = "sin sesión previa en el historial de FedWatch"
    else:
        no_eval["fed"] = "SIN DATO (FedWatch)"
    # oro y bitcoin: se explica la causa, no el precio
    g = act.get("oro") or {}
    if g.get("cambio_1d_pct") is not None and abs(g["cambio_1d_pct"]) >= U["oro_pct"]:
        al("oro", "Oro", f"El oro se mueve {sg(g['cambio_1d_pct'], 1)} % en una sesión: {explicacion_macro('Oro', mot)} (futuros COMEX vía Yahoo Finance, {fecha_linea(g['fecha'])}).",
           "Para el oro, un tipo real al alza y un dólar fuerte van en contra; a la baja, a favor (interpretación según sensibilidades fijas, no hecho).", SENCILLO["real"])
    b = act.get("btc") or {}
    pb = b.get("cambio_1d_pct")
    if pb is not None and (pb <= U["btc_baja_pct"] or pb >= U["btc_sube_pct"]):
        al("btc", "Bitcoin", f"Bitcoin {sg(pb, 1)} % en una sesión: {explicacion_macro('Bitcoin', mot)} (BTC-USD vía Yahoo Finance, {fecha_linea(b['fecha'])}).",
           "Cripto reacciona a liquidez y tipos reales; un movimiento sin motor macro suele ser de flujos y apalancamiento.", SENCILLO["real"])
    # ETF BTC
    try:
        e = etf_btc()
        if e is None:
            no_eval["etf_btc"] = "Farside sin día con dato"
        elif e[1] < U["etf_btc_musd"]:
            al("etf_btc", "ETF de BTC", f"Los ETF de bitcoin de EE. UU. registran salidas netas de {n(abs(e[1]), 0)} M$ el {fecha_linea(e[0].isoformat())} (Farside Investors).",
               "Salidas fuertes de ETF restan demanda al BTC; no afectan directamente a oro ni a índices (interpretación).",
               "Los ETF son la vía por la que entra y sale el dinero institucional en bitcoin: si salen cantidades grandes, falta demanda.")
    except Exception as ex:  # noqa: BLE001
        no_eval["etf_btc"] = f"Farside: {type(ex).__name__}"
    # ciclo y crédito: reglas de ciclo.py (saltos IG/BBB/HY/CCC en 5 días, señales que se encienden/apagan, cambio de fase)
    if C.get("senales"):
        import ciclo
        prev = estado.get("ciclo")
        Ac = ciclo.alertas(C, prev or {})
        for x in Ac:
            cred = x["tipo"] == "credito"
            al(f"ciclo_{x.get('clave') or x['texto'][:40]}", "Crédito" if cred else "Ciclo EE. UU.", x["texto"],
               (significado("hy", True) + "." if cred else "Más señales de recesión encendidas pesan sobre índices y BTC y favorecen al oro; si se apagan, al revés (interpretación, no hecho)."),
               SENCILLO["hy"] if cred else "El ciclo mide si la economía real y el crédito avisan de una recesión: cuantas más señales se encienden, más riesgo.")
        estado["ciclo"] = ciclo.nuevo_estado(C, prev, Ac)
    else:
        no_eval["ciclo"] = "SIN DATO (ciclo.json)"
    # riesgo de cola: el SKEW de Cboe en zona ALTA RELATIVA (percentil ≥ 90 de las últimas 500 sesiones) Y ≥ 2 confirmaciones. Una alerta por episodio
    # (enfriamiento de 10 sesiones, igual que el estudio histórico). Las zonas fijas 135/140 siguen en la página como referencia.
    S = D.get("skew") or {}
    if S.get("valor") is None or S.get("zona_relativa") is None:
        no_eval["skew"] = "SIN DATO (Cboe SKEW)"
    elif S.get("zona_relativa") == "ALTO" and S.get("entrada_episodio_relativa") and (S.get("confirmaciones_encendidas") or 0) < U["skew_confirmaciones_min"]:
        # regla: zona relativa alta Y >= 2 confirmaciones. Con menos, no se envía nada y queda constancia en no_eval (se reevalúa en cada ejecución del episodio)
        no_eval["skew"] = (f"RETENIDA: zona relativa alta pero solo {S.get('confirmaciones_encendidas')} de {S.get('confirmaciones_validas')} confirmaciones encendidas "
                           f"(mínimo {U['skew_confirmaciones_min']})")
    elif S.get("zona_relativa") == "ALTO" and S.get("entrada_episodio_relativa"):
        ep = S["entrada_episodio_relativa"]
        clave = f"rel_{ep}"
        if clave not in estado.setdefault("skew_avisados", []):
            er = S.get("estudio_relativo") or {}
            r = er.get("resumen") or {}
            tb = (er.get("tasa_base") or {}).get("caida_5_60s_pct")
            vx, v3 = S.get("vix") or {}, S.get("vix3m") or {}
            ratio = f" · VIX/VIX3M {n(vx['valor'] / v3['valor'], 2)}" if vx.get("valor") and v3.get("valor") else ""
            l1 = (f"El SKEW de Cboe cierra en {n(S['valor'], 1)} el {fecha_linea(S['fecha'])}: percentil {n(S.get('percentil_500'), 0)} de las últimas 500 sesiones "
                  f"(zona alta relativa, ≥ p90 = {n(S.get('umbral_alto_500'), 1)}); el episodio empezó el {fecha_linea(ep)}. "
                  f"VIX {n(vx.get('valor', 0), 1) if vx else 'SIN DATO'}{ratio}; confirmaciones encendidas "
                  f"{S.get('confirmaciones_encendidas')} de {S.get('confirmaciones_validas')} (Cboe, ciclo.py, FRED/OFR).")
            l2 = ("Se paga una prima inusual, incluso para el nivel reciente del SKEW, por cubrirse de una caída fuerte del S&P 500; no indica fecha ni magnitud (interpretación)."
                  + (f" Histórico propio con este criterio: tras {r.get('completos')} entradas, el S&P 500 cayó ≥ 5 % en {r.get('caidas')} ({n(100 - r['pct_falsas'], 0)} %) "
                     f"frente a una tasa base del {n(tb, 0)} % en cualquier sesión." if r.get("pct_falsas") is not None and tb is not None else ""))
            l4 = ("Los inversores pagan más de lo habitual en los últimos dos años por seguros contra una caída fuerte de la bolsa. No dice cuándo ni si ocurrirá"
                  + (": en el histórico, la mayoría de las veces no hubo una caída de ese tamaño." if (r.get("pct_falsas") or 0) >= 50 else "."))
            al(f"skew_{clave}", "Riesgo de cola (SKEW relativo)", l1, l2, l4)
    return out, no_eval


def mensaje(a, prueba=False):
    e = telegram.esc
    tag = "PRUEBA" if prueba else "ALERTA"
    return "\n".join([f"<b>[{tag} · {e(a['titulo'])}] 1 · Qué ha cambiado:</b> {e(a['l1'])}",
                      f"<b>2 · Qué significa:</b> {e(a['l2'])}",
                      f"<b>3 · Qué vigilar:</b> {e(a['l3'])}",
                      f"<b>4 · En palabras sencillas:</b> {e(a['l4'])}"])


def cargar_estado():
    return leer("estado_alertas.json", DATA) or {"enviadas": {}}


def guardar_estado(est):
    hoy = dt.date.today()
    est["enviadas"] = {d: v for d, v in est.get("enviadas", {}).items() if (hoy - dt.date.fromisoformat(d)).days <= 10}
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "estado_alertas.json"), "w", encoding="utf-8") as f:
        json.dump(est, f, ensure_ascii=False, indent=1)


def registrar_csv(fila):
    p = os.path.join(DATA, "historico_alertas.csv")
    existe = os.path.exists(p)
    with open(p, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fila.keys()))
        if not existe:
            w.writeheader()
        w.writerow(fila)


def cargar_datos():
    return {k: leer(f"{k}.json") for k in ("precios", "fedwatch", "tipos", "ciclo", "calendario", "resumen", "skew")}


def ejecutar(seco=False, prueba=False, max_envios=6):
    """Devuelve el JSON de estado para la web (site/data/alertas.json)."""
    D = cargar_datos()
    est = cargar_estado()
    ahora = dt.datetime.now(dt.timezone.utc)
    stamp = ahora.strftime("%Y-%m-%d %H:%M UTC")
    hoy = dt.date.today().isoformat()
    cand, no_eval = evaluar(D, est)
    prev = leer("alertas.json") or {}
    recientes = prev.get("recientes", [])
    ya = est["enviadas"].setdefault(hoy, {})
    enviadas = 0
    for a in cand:
        reg = {"fecha_utc": stamp, "clave": a["clave"], "titulo": a["titulo"], "l1": a["l1"], "l2": a["l2"], "l3": a["l3"], "l4": a["l4"]}
        if a["clave"] in ya:
            continue  # una vez al día
        if enviadas >= max_envios:
            break
        if seco:
            print("[seco]", mensaje(a))
            continue
        ok, err = telegram.enviar(mensaje(a))
        reg.update({"enviada": ok, "error": err})
        if ok:
            ya[a["clave"]] = ahora.strftime("%H:%M")
            if a["clave"].startswith("skew_"):  # un aviso por episodio: solo se marca si Telegram lo aceptó (si falla, se reintenta)
                est.setdefault("skew_avisados", []).append(a["clave"][5:])
            enviadas += 1
        registrar_csv({"fecha_utc": stamp, "clave": a["clave"], "titulo": a["titulo"], "enviada": ok, "error": err or "", "l1": a["l1"]})
        recientes.append(reg)
    if prueba and not seco:
        ok, err = enviar_prueba(D)
        recientes.append({"fecha_utc": stamp, "clave": "prueba", "titulo": "Alerta de prueba", "enviada": ok, "error": err,
                          "l1": "Alerta de prueba con datos actuales (no es una señal)."})
        registrar_csv({"fecha_utc": stamp, "clave": "prueba", "titulo": "Alerta de prueba", "enviada": ok, "error": err or "", "l1": "prueba"})
        print("prueba enviada:", ok, err or "")
    if not seco:
        guardar_estado(est)
    return {"recientes": recientes[-30:], "candidatas": [a["clave"] for a in cand], "no_evaluables": no_eval, "telegram_configurado": telegram.configurado(),
            "umbrales": U, "enviadas_hoy": sorted(ya.keys()), "ultima_evaluacion_utc": stamp}


def enviar_prueba(D):
    """Alerta de prueba en el formato de 4 líneas con datos reales actuales (no es una señal)."""
    C, F, A, T = D.get("ciclo") or {}, D.get("fedwatch") or {}, D.get("precios") or {}, D.get("tipos") or {}
    r0 = (F.get("reuniones") or [None])[0]
    t2 = T.get("t2y") or {}
    l1 = (f"Prueba del canal de alertas. Estado actual: ciclo {C.get('fase', 'SIN DATO')} ({C.get('encendidas', '—')} de {C.get('validas', '—')} señales encendidas, FRED/Fed)"
          + (f"; Fed {fecha_linea(r0['reunion'])}: subida {n(r0['prob_reunion']['subida'], 0)} %, bajada {n(r0['prob_reunion']['bajada'], 0)} % (FedWatch NEXORA)" if r0 else "")
          + (f"; bono a 2 años {n(t2['valor'], 2)} % ({fecha_linea(t2['fecha'])}, Tesoro de EE. UU.)" if t2.get("valor") is not None else "") + ".")
    a = {"titulo": "canal operativo", "l1": l1,
         "l2": "Si recibes este mensaje, GitHub Actions puede avisarte con el PC apagado. Las alertas reales siguen este mismo formato de cuatro líneas.",
         "l3": vigilar(D.get("calendario")),
         "l4": "Esto es solo una comprobación del canal: no indica nada sobre el mercado ni es una recomendación."}
    return telegram.enviar(mensaje(a, prueba=True))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prueba", action="store_true")
    ap.add_argument("--seco", action="store_true")
    a = ap.parse_args()
    R = ejecutar(seco=a.seco, prueba=a.prueba)
    print(json.dumps({k: R[k] for k in ("candidatas", "no_evaluables", "telegram_configurado", "enviadas_hoy")}, ensure_ascii=False))
    if a.prueba and not a.seco:
        os.makedirs(SITE_DATA, exist_ok=True)
        with open(os.path.join(SITE_DATA, "alertas.json"), "w", encoding="utf-8") as f:
            json.dump({**R, "ok": True}, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
