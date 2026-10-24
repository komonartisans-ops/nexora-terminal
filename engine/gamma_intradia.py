#!/usr/bin/env python3
"""NEXORA · GAMMA INTRADÍA (ES y NQ): avisos por Telegram con velas de 5 min, marcador «gamma intradía» y línea de niveles de las 15:00 Madrid. Sin IA, gratis.
CONTEXTO, NO ENTRADAS: ningún texto dice «compra» ni «vende»; cada aviso es un hecho de precio frente a niveles de gamma, con su invalidación.

Niveles: los del último gamma.json (cadena de opciones de Cboe con 15 min de retraso de la SESIÓN ANTERIOR, en precios de futuro), más el EM del día
(precio × VIX/VXN / 100 / √252, volatilidad del cierre de esa sesión) y el Max Gamma (tramo de mayor gamma absoluta). Velas de 5 min del futuro (Yahoo Finance, con su retraso).

REGLAS (FIJAS; congeladas hasta que cada regla tenga n ≥ 20 señales evaluadas; no se ajustan umbrales con menos muestra):
  1. CAMBIO DE RÉGIMEN: 2 cierres de 5 min consecutivos al otro lado del Gamma Flip respecto al lado vigente (el del último cierre antes de las 09:30 ET). Por encima del flip = gamma
     positiva; por debajo = negativa. Tras el aviso, el nuevo lado pasa a ser el vigente.
  2. TECHO EN GAMMA POSITIVA: con régimen vigente positivo, el cierre de 5 min queda por debajo del Call Wall a una distancia ≤ 0,25 × EM (aviso al ENTRAR en esa zona).
  3. PÉRDIDA DEL PUT WALL EN GAMMA NEGATIVA: con régimen vigente negativo, 2 cierres de 5 min consecutivos por debajo del Put Wall tras haber estado por encima (cruce desde arriba;
     se rearma con un cierre por encima).
  4. EM AGOTADO: el rango del día (máximo − mínimo desde las 09:30 ET, sesión regular) ≥ 100 % del EM. Una vez por día e índice.
  Solo en sesión regular (09:30-16:00 ET), de lunes a viernes. Máx. 6 avisos al día; el mismo tipo en el mismo índice no se repite en 60 min; un disparo con más de 20 min de antigüedad
  no se envía. Cada aviso lleva: hecho, régimen, invalidación, retraso de los datos y si hay un dato de importancia ALTA a ±15 min.
MARCADOR «gamma intradía»: cada aviso enviado queda en data/gamma_intradia_senales.csv (solo-añadir) y se mide a 15, 30 y 60 min con barras de 5 min: MFE (máxima excursión a favor) y MAE
  (máxima excursión en contra) en puntos y en múltiplos del EM, frente al cierre de la vela de disparo. Dirección hipotética de cada regla (no es una recomendación): 1 = la del cruce;
  2 = bajista (rechazo en el techo); 3 = bajista (continuación); 4 = contraria al lado del rango en que está el precio (agotamiento), sin dirección si está en el tercio central.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import json
import math
import os
import re
import statistics
import sys
import time
import urllib.parse
import urllib.request
import zoneinfo

HERE = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(HERE)
sys.path.insert(0, HERE)
UTC, NY, MAD = dt.timezone.utc, zoneinfo.ZoneInfo("America/New_York"), zoneinfo.ZoneInfo("Europe/Madrid")

BARRA_MIN = 5
RTH_INI, RTH_FIN = dt.time(9, 30), dt.time(16, 0)
CIERRES_CONF = 2
UMBRAL_TECHO_EM = 0.25
UMBRAL_EM_AGOTADO = 1.0
MAX_AVISOS_DIA = 6
SIN_REPETIR_MIN = 60
EVENTO_ALTA_MIN = 15
MAX_TARDIO_MIN = 20
HORIZONTES = (15, 30, 60)
MIN_N = 20
INDICES = {"ES": "ES=F", "NQ": "NQ=F"}
CAMPOS_SEN = ["id", "fecha_et", "indice", "regla", "direccion", "t_disparo_utc", "precio_ref", "nivel", "em", "regimen", "evento_alta", "enviado_utc", "origen"]
CAMPOS_RES = ["id", "horizonte", "direccion", "precio_ref", "mfe_pts", "mae_pts", "mfe_em", "mae_em", "cierre_pts", "exc_arriba_pts", "exc_abajo_pts", "n_barras", "evaluado_utc"]
REGLAS = {"cambio_regimen": "Cambio de régimen de gamma", "techo_gamma_positiva": "Techo en gamma positiva (Call Wall cerca)",
          "perdida_put_wall": "Pérdida del Put Wall en gamma negativa", "em_agotado": "Movimiento esperado (EM) agotado"}
PALABRAS_PROHIBIDAS = re.compile(r"\b(compra|compras|comprar|compre|vende|vendes|vender|venda|venta|ventas)\b", re.I)


def P(raiz, *a):
    return os.path.join(raiz, *a)


def _leer_json(ruta):
    try:
        return json.load(open(ruta, encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------- velas de 5 min (inyectables en pruebas)
def barras_yahoo(sym, rango="5d", tries=3):
    """[{t0 (inicio de la vela, UTC), o, h, l, c}] ordenadas; sin velas vacías."""
    q = urllib.parse.quote(sym, safe="")
    ultimo = None
    for k in range(tries):
        for host in ("query2", "query1"):
            try:
                req = urllib.request.Request(f"https://{host}.finance.yahoo.com/v8/finance/chart/{q}?range={rango}&interval=5m", headers={"User-Agent": "Mozilla/5.0"})
                r = json.loads(urllib.request.urlopen(req, timeout=40).read())["chart"]["result"][0]
                qt = r["indicators"]["quote"][0]
                out = []
                for i, t in enumerate(r["timestamp"]):
                    o, h, l, c = qt["open"][i], qt["high"][i], qt["low"][i], qt["close"][i]
                    if None in (o, h, l, c):
                        continue
                    out.append({"t0": dt.datetime.fromtimestamp(t, UTC), "o": float(o), "h": float(h), "l": float(l), "c": float(c)})
                if not out:
                    raise RuntimeError("sin velas")
                return sorted(out, key=lambda b: b["t0"])
            except Exception as e:  # noqa: BLE001
                ultimo = e
        time.sleep(1.5 * (k + 1))
    raise RuntimeError(f"Yahoo sin velas de {sym} ({type(ultimo).__name__})")


def completas(barras, ahora):
    """Quita la vela en curso: una vela está cerrada cuando t0 + 5 min ≤ ahora. Además descarta las que no son múltiplo de 5 min (Yahoo añade una vela parcial)."""
    return [b for b in barras if b["t0"] + dt.timedelta(minutes=BARRA_MIN) <= ahora and b["t0"].minute % BARRA_MIN == 0 and b["t0"].second == 0]


def sesion_rth(barras, fecha_et):
    """(velas de la sesión regular de `fecha_et`, cierre de la última vela anterior a las 09:30 ET de ese día o None)."""
    ini = dt.datetime.combine(fecha_et, RTH_INI, NY).astimezone(UTC)
    fin = dt.datetime.combine(fecha_et, RTH_FIN, NY).astimezone(UTC)
    rth = [b for b in barras if ini <= b["t0"] < fin]
    antes = [b for b in barras if b["t0"] < ini]
    return rth, (antes[-1]["c"] if antes else None)


# ---------------------------------------------------------------- niveles
def niveles(J, clave):
    """Niveles de futuro de un índice desde gamma.json. None si no hay Gamma Flip utilizable."""
    x = ((J or {}).get("indices") or {}).get(clave)
    if not x:
        return None
    g = lambda k: ((x.get(k) or {}).get("fut"))  # noqa: E731
    em = (x.get("em") or {}).get("puntos")
    n = {"clave": clave, "flip": g("flip"), "cw": g("call_wall"), "pw": g("put_wall"), "maxg": g("max_gamma"), "em": em, "spot_fut": x.get("spot_fut"), "sesion": x.get("sesion"),
         "regimen_cierre": x.get("regimen"), "base": (x.get("base") or {}).get("base"), "em_info": x.get("em"), "ultima_operacion_et": x.get("ultima_operacion_et")}
    return n if n["flip"] is not None else None


# ---------------------------------------------------------------- detección (funciones puras)
def lado(c, flip, vigente):
    return 1 if c > flip else -1 if c < flip else vigente


def detectar(niv, barras_rth, previo):
    """Eventos de la sesión en orden: [{regla, t_barra, t_cierre, precio, ...}]. Función pura: la misma entrada da siempre la misma salida (idempotente)."""
    if not niv or not barras_rth:
        return []
    flip, cw, pw, em = niv["flip"], niv.get("cw"), niv.get("pw"), niv.get("em")
    vig = lado(previo, flip, 0) if previo is not None else lado(barras_rth[0]["c"], flip, 0)
    vig = vig or 1
    cont, pw_cont, hi, lo, em_hecho = 0, 0, -math.inf, math.inf, False
    ref0 = previo if previo is not None else barras_rth[0]["c"]
    techo = vig == 1 and cw is not None and bool(em) and 0 <= cw - ref0 <= UMBRAL_TECHO_EM * em      # si ya estaba en la zona antes de abrir, no es una entrada nueva
    armado = pw is not None and ref0 >= pw                                                          # «pérdida» = cruce desde arriba: si abre ya por debajo, no avisa hasta recuperarlo
    out = []

    def ev(regla, b, **kw):
        out.append({"regla": regla, "t_barra": b["t0"], "t_cierre": b["t0"] + dt.timedelta(minutes=BARRA_MIN), "precio": b["c"], "regimen": "positiva" if vig == 1 else "negativa", **kw})

    for b in barras_rth:
        c = b["c"]
        l = lado(c, flip, vig)
        if l != vig:
            cont += 1
            if cont >= CIERRES_CONF:
                previo_lado, vig, cont, pw_cont, techo = vig, l, 0, 0, False
                ev("cambio_regimen", b, nivel=flip, de=previo_lado, a=l, direccion="ALCISTA" if l == 1 else "BAJISTA")
        else:
            cont = 0
        if vig == 1 and cw is not None and em:
            d = cw - c
            cond = 0 <= d <= UMBRAL_TECHO_EM * em
            if cond and not techo:
                ev("techo_gamma_positiva", b, nivel=cw, distancia=d, direccion="BAJISTA")
            techo = cond
        else:
            techo = False
        if pw is not None and c >= pw:
            armado, pw_cont = True, 0
        elif vig == -1 and pw is not None and c < pw and armado:
            pw_cont += 1
            if pw_cont == CIERRES_CONF:
                ev("perdida_put_wall", b, nivel=pw, direccion="BAJISTA")
                armado = False
        else:
            pw_cont = 0
        hi, lo = max(hi, b["h"]), min(lo, b["l"])
        if em and not em_hecho and hi - lo >= UMBRAL_EM_AGOTADO * em:
            em_hecho = True
            tercio = (c - lo) / (hi - lo) if hi > lo else 0.5
            ev("em_agotado", b, nivel=em, rango=hi - lo, hi=hi, lo=lo, direccion="BAJISTA" if tercio >= 2 / 3 else "ALCISTA" if tercio <= 1 / 3 else "NINGUNA")
    return out


# ---------------------------------------------------------------- agenda: dato ALTA a ±15 min
def eventos_alta(raiz, fecha_et):
    A = ((_leer_json(P(raiz, "site", "data", "agenda.json")) or {}).get("agenda")) or {}
    out, vistos = [], set()
    for e in (A.get("hoy") or []) + (A.get("proximos_7_dias") or []):
        if e.get("importancia") != "ALTA" or not e.get("hora_ny"):
            continue
        f = e.get("fecha_et") or e.get("fecha")
        try:
            h, m = map(int, e["hora_ny"].split(":"))
            t = dt.datetime.combine(dt.date.fromisoformat(f), dt.time(h, m), NY).astimezone(UTC)
        except (TypeError, ValueError):
            continue
        k = (f, e["hora_ny"], e.get("evento"))
        if k not in vistos:
            vistos.add(k)
            out.append({"t": t, "evento": e.get("evento", ""), "hora_madrid": t.astimezone(MAD).strftime("%H:%M")})
    return out


def evento_cercano(evs, t):
    c = [e for e in evs if abs((e["t"] - t).total_seconds()) <= EVENTO_ALTA_MIN * 60]
    return min(c, key=lambda e: abs((e["t"] - t).total_seconds())) if c else None


# ---------------------------------------------------------------- mensajes
def _n(x, d=1):
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def mensaje(ev, niv, clave, ahora, ultima_barra_cierre, evento):
    """Texto de Telegram (HTML). Hecho, régimen, invalidación, retraso de datos y evento ALTA ±15 min. Nunca dice «compra» ni «vende»."""
    e = html.escape
    hm = lambda t: t.astimezone(NY).strftime("%H:%M")  # noqa: E731
    flip, cw, pw, em = niv["flip"], niv.get("cw"), niv.get("pw"), niv.get("em")
    c = ev["precio"]
    r = ev["regla"]
    if r == "cambio_regimen":
        sobre = ev["a"] == 1
        hecho = f"2 cierres de 5 min {'por encima' if sobre else 'por debajo'} del Gamma Flip ({_n(flip)}); último cierre {_n(c)} a las {hm(ev['t_cierre'])} ET."
        reg = (f"gamma POSITIVA (precio sobre el flip): hipótesis del método = los creadores de mercado amortiguan los movimientos." if sobre
               else "gamma NEGATIVA (precio bajo el flip): hipótesis del método = los creadores de mercado amplifican los movimientos.")
        inv = f"se invalida si 2 cierres de 5 min vuelven {'por debajo' if sobre else 'por encima'} del flip ({_n(flip)})."
    elif r == "techo_gamma_positiva":
        hecho = f"el cierre {_n(c)} queda a {_n(ev['distancia'])} pts del Call Wall ({_n(cw)}), dentro de 0,25 × EM ({_n(UMBRAL_TECHO_EM * em)} pts; EM {_n(em)})."
        reg = "gamma POSITIVA (precio sobre el flip): el Call Wall es el nivel de mayor gamma de calls por encima; hipótesis = zona donde el movimiento suele frenarse."
        inv = f"se invalida si 2 cierres de 5 min quedan por encima del Call Wall ({_n(cw)}) o por debajo del flip ({_n(flip)})."
    elif r == "perdida_put_wall":
        hecho = f"2 cierres de 5 min por debajo del Put Wall ({_n(pw)}); último cierre {_n(c)} a las {hm(ev['t_cierre'])} ET."
        reg = "gamma NEGATIVA (precio bajo el flip): perder el Put Wall quita el nivel de mayor gamma de puts como referencia; hipótesis = los movimientos se amplían."
        inv = f"se invalida si un cierre de 5 min vuelve por encima del Put Wall ({_n(pw)}) o si el precio recupera el flip ({_n(flip)})."
    else:
        hecho = f"rango del día {_n(ev['rango'])} pts = {_n(ev['rango'] / em * 100, 0)} % del EM ({_n(em)} pts), desde las 09:30 ET (máx. {_n(ev['hi'])} / mín. {_n(ev['lo'])})."
        reg = f"régimen vigente: gamma {ev['regimen'].upper()} (precio {'sobre' if ev['regimen'] == 'positiva' else 'bajo'} el flip {_n(flip)})."
        inv = f"el EM es una referencia estadística (~68 %), no un techo: se invalida como agotamiento si el rango del día llega a {_n(1.5 * em)} pts (1,5 × EM)."
    delay = (ahora - ultima_barra_cierre).total_seconds() / 60 if ultima_barra_cierre else None
    ret = (f"velas de 5 min de Yahoo Finance; la última cerró a las {hm(ultima_barra_cierre)} ET (hace {delay:.0f} min). " if delay is not None else "velas de 5 min de Yahoo Finance. ")
    ret += f"Niveles de la cadena de Cboe (15 min de retraso) de la sesión {niv['sesion'][8:10]}-{niv['sesion'][5:7]}, en precio de futuro."
    ev_txt = (f"dato de importancia ALTA a ±{EVENTO_ALTA_MIN} min: {e(evento['evento'])} ({evento['hora_madrid']} Madrid)." if evento else f"sin dato de importancia ALTA a ±{EVENTO_ALTA_MIN} min.")
    txt = (f"<b>NEXORA · Gamma intradía · {e(clave)}</b>\n<b>{e(REGLAS[r])}</b>\nHecho: {e(hecho)}\nRégimen: {e(reg)}\nInvalidación: {e(inv)}\n"
           f"Retraso de datos: {e(ret)}\nEvento: {ev_txt}\nContexto de mercado, no una entrada. CRITERIO NEXORA (reglas congeladas hasta n ≥ {MIN_N}).")
    assert not PALABRAS_PROHIBIDAS.search(txt), "el aviso no puede decir compra/vende"
    return txt


# ---------------------------------------------------------------- estado y registro (solo-añadir)
def _estado(raiz):
    return _leer_json(P(raiz, "data", "estado_gamma_intradia.json")) or {"creado_utc": None, "avisos": {}}


def _guardar_estado(raiz, nuevos):
    """Solo-añadir: relee y añade las claves nuevas; una clave existente nunca se modifica."""
    est = _estado(raiz)
    est["creado_utc"] = est.get("creado_utc") or dt.datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    for k, v in nuevos.items():
        est["avisos"].setdefault(k, v)
    os.makedirs(P(raiz, "data"), exist_ok=True)
    json.dump(est, open(P(raiz, "data", "estado_gamma_intradia.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def _anadir_csv(ruta, filas, campos, clave):
    vistas = set()
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8", newline="") as f:
            vistas = {clave(r) for r in csv.DictReader(f)}
    nuevas = [r for r in filas if clave(r) not in vistas]
    if nuevas:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        existe = os.path.exists(ruta)
        with open(ruta, "a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
            if not existe:
                w.writeheader()
            w.writerows(nuevas)
    return nuevas


def _leer_csv(ruta):
    if not os.path.exists(ruta):
        return []
    with open(ruta, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _id(fecha, clave, regla, t_cierre):
    return f"gi-{clave.lower()}-{regla}-{t_cierre.strftime('%Y%m%d%H%M')}"


def decidir(evs_todos, est_avisos, ahora, fecha_et):
    """Filtra los eventos detectados con las reglas de envío. evs_todos = [(clave, ev)] ordenados por t_cierre. Devuelve [(clave, ev, id)] a enviar, y el dict de omitidos {id: motivo}.
    est_avisos = avisos ya registrados {id: {estado, ...}} (enviados o suprimidos antes)."""
    enviar, omitidos = [], {}
    enviados_hoy = [v for v in est_avisos.values() if v.get("estado") == "ENVIADO" and v.get("fecha_et") == fecha_et]
    n_hoy = len(enviados_hoy)
    ultimos = {}
    for v in enviados_hoy:
        ultimos.setdefault((v["indice"], v["regla"]), []).append(dt.datetime.fromisoformat(v["t_cierre_utc"]).replace(tzinfo=UTC))
    for clave, ev in sorted(evs_todos, key=lambda x: x[1]["t_cierre"]):
        i = _id(fecha_et, clave, ev["regla"], ev["t_cierre"])
        if i in est_avisos:
            continue
        if (ahora - ev["t_cierre"]).total_seconds() > MAX_TARDIO_MIN * 60:
            omitidos[i] = "TARDÍO"
            continue
        if any(abs((ev["t_cierre"] - t).total_seconds()) < SIN_REPETIR_MIN * 60 for t in ultimos.get((clave, ev["regla"]), [])):
            omitidos[i] = "REPETIDO"
            continue
        if n_hoy >= MAX_AVISOS_DIA:
            omitidos[i] = "TOPE DIARIO"
            continue
        enviar.append((clave, ev, i))
        ultimos.setdefault((clave, ev["regla"]), []).append(ev["t_cierre"])
        n_hoy += 1
    return enviar, omitidos


def pasada(raiz=RAIZ, ahora=None, fuentes=None, enviar_fn=None, seco=False, push=False):
    """Una pasada del monitor. fuentes = {'barras': fn(sym)→velas, 'gamma': fn()→gamma.json}. Devuelve [(id, estado, texto)]. seco=True: no envía ni escribe nada."""
    ahora = ahora or dt.datetime.now(UTC)
    F = {"barras": barras_yahoo, "gamma": lambda: _leer_json(P(raiz, "site", "data", "gamma.json")), **(fuentes or {})}
    hoy_et = ahora.astimezone(NY)
    fecha_et = hoy_et.date()
    if fecha_et.weekday() >= 5:
        return []
    ini = dt.datetime.combine(fecha_et, RTH_INI, NY).astimezone(UTC)
    fin = dt.datetime.combine(fecha_et, RTH_FIN, NY).astimezone(UTC)
    if not (ini <= ahora <= fin + dt.timedelta(minutes=MAX_TARDIO_MIN)):
        return []
    J = F["gamma"]()
    if not J:
        print("gamma intradía: gamma.json no disponible (SIN DATO)")
        return []
    evs_alta = eventos_alta(raiz, fecha_et)
    todos, ultima_cierre, errores, nivs = [], {}, {}, {}
    for clave, sym in INDICES.items():
        niv = niveles(J, clave)
        if not niv:
            errores[clave] = "sin Gamma Flip en gamma.json"
            continue
        try:
            bs = completas(F["barras"](sym), ahora)
        except Exception as e:  # noqa: BLE001
            errores[clave] = f"{type(e).__name__}: {str(e)[:80]}"
            continue
        rth, previo = sesion_rth(bs, fecha_et)
        if not rth:
            continue
        ultima_cierre[clave] = rth[-1]["t0"] + dt.timedelta(minutes=BARRA_MIN)
        for ev in detectar(niv, rth, previo):
            todos.append((clave, ev))
        nivs[clave] = niv
    est = _estado(raiz)
    por_enviar, omitidos = decidir(todos, est["avisos"], ahora, fecha_et.isoformat())
    out, nuevos, filas = [], {}, []
    for i, motivo in omitidos.items():
        nuevos[i] = {"estado": motivo, "fecha_et": fecha_et.isoformat()}
    for clave, ev, i in por_enviar:
        niv = nivs[clave]
        txt = mensaje(ev, niv, clave, ahora, ultima_cierre.get(clave), evento_cercano(evs_alta, ev["t_cierre"]))
        if seco:
            out.append((i, "SECO", txt))
            continue
        import telegram
        ok, err = (enviar_fn or telegram.enviar)(txt)
        if not ok:
            print("gamma intradía: Telegram no aceptó el aviso (se reintenta):", err)
            out.append((i, "ERROR", err or ""))
            continue
        evc = evento_cercano(evs_alta, ev["t_cierre"])
        nuevos[i] = {"estado": "ENVIADO", "fecha_et": fecha_et.isoformat(), "indice": clave, "regla": ev["regla"], "t_cierre_utc": ev["t_cierre"].strftime("%Y-%m-%dT%H:%M:%S"),
                     "enviado_utc": ahora.strftime("%Y-%m-%d %H:%M UTC")}
        filas.append({"id": i, "fecha_et": fecha_et.isoformat(), "indice": clave, "regla": ev["regla"], "direccion": ev.get("direccion", "NINGUNA"), "t_disparo_utc": ev["t_cierre"].strftime("%Y-%m-%d %H:%M"),
                      "precio_ref": ev["precio"], "nivel": ev.get("nivel", ""), "em": nivs[clave].get("em") or "", "regimen": ev["regimen"], "evento_alta": (evc or {}).get("evento", ""),
                      "enviado_utc": ahora.strftime("%Y-%m-%d %H:%M"), "origen": "vivo"})
        out.append((i, "ENVIADO", txt))
    if not seco and (nuevos or filas):
        _anadir_csv(P(raiz, "data", "gamma_intradia_senales.csv"), filas, CAMPOS_SEN, lambda r: r["id"])
        _guardar_estado(raiz, nuevos)
        if push and os.environ.get("GITHUB_ACTIONS"):
            import subprocess
            subprocess.run([sys.executable, os.path.join(HERE, "push_seguro.py"), "gamma intradia " + ahora.strftime("%Y-%m-%d %H:%M") + " UTC [skip ci]"], check=False, timeout=180)
    for k, v in errores.items():
        print(f"gamma intradía {k}: {v}")
    return out


_ULTIMA = {"t": 0.0}


def pasada_si_toca(minimo_s=270, **kw):
    """Para el bucle de espera de reaccion.py: como mucho una pasada cada ~4,5 min en el proceso. Un fallo nunca interrumpe al monitor."""
    if time.time() - _ULTIMA["t"] < minimo_s:
        return []
    _ULTIMA["t"] = time.time()
    try:
        return pasada(push=True, **kw)
    except Exception as e:  # noqa: BLE001
        print("gamma intradía: error (el monitor sigue):", type(e).__name__, str(e)[:80])
        return []


def en_rth(ahora):
    n = ahora.astimezone(NY)
    return n.weekday() < 5 and RTH_INI <= n.time() < RTH_FIN


def ventana(minutos=13, paso_s=270, **kw):
    """Vigila durante `minutos` (una pasada cada ~4,5 min) mientras haya sesión regular. Los crones de reacciones arrancan cada 15 min: así la cobertura es casi continua sin que un
    job dure más que el siguiente. Un fallo nunca interrumpe al monitor."""
    fin = time.time() + minutos * 60
    while en_rth(dt.datetime.now(UTC)):
        pasada_si_toca(minimo_s=0, **kw)
        if time.time() + paso_s > fin:
            return
        time.sleep(paso_s)


# ---------------------------------------------------------------- prueba en seco: qué habría salido en una sesión
def repetir_sesion(raiz, fecha_et, fuentes, hasta_utc=None, retraso_min=10, enviar_fn=None):
    """Reproduce la sesión barra a barra (una pasada por cada vela cerrada, con `retraso_min` de retraso de los datos) con estado en memoria: no envía ni escribe nada.
    Devuelve [(hora ET de la pasada, id, texto)] de los avisos que habrían salido, aplicando tope diario, no repetir y antigüedad."""
    F = {"barras": barras_yahoo, "gamma": lambda: _leer_json(P(raiz, "site", "data", "gamma.json")), **(fuentes or {})}
    J = F["gamma"]()
    cache = {c: F["barras"](s) for c, s in INDICES.items()}
    evs_alta = eventos_alta(raiz, fecha_et)
    ini = dt.datetime.combine(fecha_et, RTH_INI, NY).astimezone(UTC)
    fin = dt.datetime.combine(fecha_et, RTH_FIN, NY).astimezone(UTC)
    todas = sorted({b["t0"] + dt.timedelta(minutes=BARRA_MIN) for bs in cache.values() for b in bs if ini <= b["t0"] < fin})
    est, salida = {}, []
    for t in todas:
        if hasta_utc and t > hasta_utc:
            break
        ahora = t + dt.timedelta(minutes=retraso_min)
        todos, ult, nivs = [], {}, {}
        for clave in INDICES:
            niv = niveles(J, clave)
            if not niv:
                continue
            bs = [b for b in cache[clave] if b["t0"] + dt.timedelta(minutes=BARRA_MIN) <= t and b["t0"].minute % 5 == 0]
            rth, previo = sesion_rth(bs, fecha_et)
            if not rth:
                continue
            nivs[clave], ult[clave] = niv, rth[-1]["t0"] + dt.timedelta(minutes=BARRA_MIN)
            todos += [(clave, ev) for ev in detectar(niv, rth, previo)]
        por_enviar, omit = decidir(todos, est, ahora, fecha_et.isoformat())
        for i, m in omit.items():
            est[i] = {"estado": m, "fecha_et": fecha_et.isoformat()}
        for clave, ev, i in por_enviar:
            est[i] = {"estado": "ENVIADO", "fecha_et": fecha_et.isoformat(), "indice": clave, "regla": ev["regla"], "t_cierre_utc": ev["t_cierre"].strftime("%Y-%m-%dT%H:%M:%S")}
            salida.append((ahora.astimezone(NY).strftime("%H:%M"), i, mensaje(ev, nivs[clave], clave, ahora, ult.get(clave), evento_cercano(evs_alta, ev["t_cierre"]))))
    return salida, {k: v["estado"] for k, v in est.items() if v["estado"] != "ENVIADO"}


# ---------------------------------------------------------------- marcador «gamma intradía»: MFE / MAE a 15, 30 y 60 min
def excursiones(barras, t0, ref, direccion, h_min, em):
    """MFE / MAE (puntos y × EM) de las velas con inicio en [t0, t0 + h). direccion: ALCISTA / BAJISTA / NINGUNA. Devuelve None si aún no hay todas las velas de la ventana."""
    fin = t0 + dt.timedelta(minutes=h_min)
    ventana = [b for b in barras if t0 <= b["t0"] < fin]
    if len(ventana) < h_min // BARRA_MIN or ventana[-1]["t0"] + dt.timedelta(minutes=BARRA_MIN) < fin:
        return None
    arriba = max(b["h"] for b in ventana) - ref
    abajo = ref - min(b["l"] for b in ventana)
    cierre = ventana[-1]["c"] - ref
    r = {"exc_arriba_pts": round(arriba, 2), "exc_abajo_pts": round(abajo, 2), "n_barras": len(ventana), "mfe_pts": "", "mae_pts": "", "mfe_em": "", "mae_em": "", "cierre_pts": ""}
    if direccion in ("ALCISTA", "BAJISTA"):
        mfe, mae = (arriba, abajo) if direccion == "ALCISTA" else (abajo, arriba)
        r.update({"mfe_pts": round(mfe, 2), "mae_pts": round(mae, 2), "cierre_pts": round(cierre if direccion == "ALCISTA" else -cierre, 2)})
        if em:
            r.update({"mfe_em": round(mfe / float(em), 3), "mae_em": round(mae / float(em), 3)})
    return r


def evaluar(raiz=RAIZ, ahora=None, fuentes=None):
    """Mide las señales enviadas (origen vivo) que ya tienen cerrada la ventana de 15/30/60 min. Solo-añadir. Devuelve las filas nuevas."""
    ahora = ahora or dt.datetime.now(UTC)
    F = {"barras": barras_yahoo, **(fuentes or {})}
    sen = _leer_csv(P(raiz, "data", "gamma_intradia_senales.csv"))
    ya = {(r["id"], r["horizonte"]) for r in _leer_csv(P(raiz, "data", "gamma_intradia_resultados.csv"))}
    cache, nuevas = {}, []
    for s in sen:
        t0 = dt.datetime.strptime(s["t_disparo_utc"], "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
        for h in HORIZONTES:
            if (s["id"], str(h)) in ya or ahora < t0 + dt.timedelta(minutes=h + BARRA_MIN):
                continue
            if s["indice"] not in cache:
                try:
                    cache[s["indice"]] = F["barras"](INDICES[s["indice"]])
                except Exception as e:  # noqa: BLE001
                    print("gamma intradía evaluar:", s["indice"], type(e).__name__)
                    cache[s["indice"]] = []
            r = excursiones(cache[s["indice"]], t0, float(s["precio_ref"]), s["direccion"], h, s.get("em") or None)
            if r:
                nuevas.append({"id": s["id"], "horizonte": h, "direccion": s["direccion"], "precio_ref": s["precio_ref"], **r, "evaluado_utc": ahora.strftime("%Y-%m-%d %H:%M")})
    return _anadir_csv(P(raiz, "data", "gamma_intradia_resultados.csv"), nuevas, CAMPOS_RES, lambda r: (r["id"], str(r["horizonte"])))


def resumen(raiz=RAIZ, ahora=None):
    """site/data/gamma_intradia.json para la página del marcador: por regla, n de señales, n evaluadas por horizonte y medianas de MFE/MAE (solo descriptivo; sin acierto/fallo)."""
    ahora = ahora or dt.datetime.now(UTC)
    sen = _leer_csv(P(raiz, "data", "gamma_intradia_senales.csv"))
    res = _leer_csv(P(raiz, "data", "gamma_intradia_resultados.csv"))
    por = {}
    for r in REGLAS:
        ss = [s for s in sen if s["regla"] == r]
        d = {"regla": r, "nombre": REGLAS[r], "n_senales": len(ss), "horizontes": {}}
        for h in HORIZONTES:
            rr = [x for x in res if x["horizonte"] == str(h) and any(s["id"] == x["id"] and s["regla"] == r for s in ss)]
            dirs = [x for x in rr if x["mfe_pts"] != ""]
            f = lambda k: [float(x[k]) for x in dirs]  # noqa: E731
            d["horizontes"][str(h)] = {"n": len(rr), "n_con_direccion": len(dirs), "mfe_mediana_pts": round(statistics.median(f("mfe_pts")), 2) if dirs else None,
                                       "mae_mediana_pts": round(statistics.median(f("mae_pts")), 2) if dirs else None,
                                       "mfe_mediana_em": round(statistics.median(f("mfe_em")), 3) if dirs and all(x["mfe_em"] != "" for x in dirs) else None,
                                       "mae_mediana_em": round(statistics.median(f("mae_em")), 3) if dirs and all(x["mae_em"] != "" for x in dirs) else None,
                                       "mfe_mayor_que_mae_pct": round(100 * sum(1 for x in dirs if float(x["mfe_pts"]) > float(x["mae_pts"])) / len(dirs)) if dirs else None}
        d["fiable"] = min((d["horizontes"][str(h)]["n"] for h in HORIZONTES), default=0) >= MIN_N
        d["estado"] = "CONGELADA" if not d["fiable"] else "EVALUABLE"
        por[r] = d
    return {"version": 1, "ok": True, "generado_utc": ahora.strftime("%Y-%m-%d %H:%M UTC"), "min_n": MIN_N, "horizontes_min": list(HORIZONTES), "n_senales": len(sen), "por_regla": por,
            "reglas": [x.strip() for x in __doc__.split("REGLAS (FIJAS; congeladas hasta que cada regla tenga n ≥ 20 señales evaluadas; no se ajustan umbrales con menos muestra):")[1].split("MARCADOR")[0].strip().split("\n  ")],
            "metodo": "MFE = máxima excursión a favor y MAE = máxima excursión en contra de la dirección hipotética de la regla, frente al cierre de la vela de disparo, con barras de 5 min de Yahoo Finance. "
                      "Solo se miden los avisos enviados en vivo. No hay acierto/fallo: con n < 20 por regla no se concluye nada y las reglas no se tocan.",
            "ultimas": [{k: s[k] for k in ("fecha_et", "indice", "regla", "direccion", "precio_ref", "regimen", "evento_alta")} for s in sen[-8:]][::-1],
            "fuente": "gamma_intradia.py (data/gamma_intradia_senales.csv, data/gamma_intradia_resultados.csv)"}


def etapa():
    """Para build.py: evalúa lo pendiente y escribe el resumen del marcador."""
    try:
        evaluar()
    except Exception as e:  # noqa: BLE001
        print("gamma intradía evaluar:", type(e).__name__, str(e)[:80])
    return resumen()


# ---------------------------------------------------------------- línea de niveles de las 15:00 Madrid
def _v(x, d=1):
    return "na" if x is None else (f"{x:.{d}f}")


def linea_niveles(J):
    """«ES flip=…;cw=…;pw=…;em=…;maxg=…;rf=AAAA-MM-DD | NQ …» en precio de FUTURO, punto decimal, sin separadores de miles (la lee el indicador de TradingView). rf = sesión de la cadena de
    opciones de la que salen los niveles (Fase 21: el indicador la compara con la línea que toca hoy y avisa si está caducada)."""
    seg = []
    for clave in INDICES:
        n = niveles(J, clave)
        if not n:
            seg.append(f"{clave} flip=na;cw=na;pw=na;em=na;maxg=na;rf=na")
            continue
        seg.append(f"{clave} flip={_v(n['flip'])};cw={_v(n['cw'])};pw={_v(n['pw'])};em={_v(n['em'])};maxg={_v(n['maxg'])};rf={n.get('sesion') or 'na'}")
    return " | ".join(seg)


def mensaje_niveles(J, ahora, oro=None):
    e = html.escape
    ses = {c: (niveles(J, c) or {}).get("sesion") for c in INDICES}
    fecha = max([s for s in ses.values() if s] or [""])
    antiguo = ""
    if fecha:
        dias = (ahora.astimezone(NY).date() - dt.date.fromisoformat(fecha)).days
        if dias > 4:
            antiguo = f"\nAVISO: los niveles son de la sesión {fecha[8:10]}-{fecha[5:7]}, hace {dias} días (SIN actualizar)."
    em = (((J or {}).get("indices") or {}).get("ES") or {}).get("em") or {}
    txt = (f"<b>NEXORA · Niveles gamma para TradingView</b> · {ahora.astimezone(MAD).strftime('%H:%M')} Madrid\n<code>{e(linea_niveles(J))}</code>\n"
           f"Precios de FUTURO (ES/NQ). Sesión de la cadena de Cboe: {fecha[8:10] + '-' + fecha[5:7] if fecha else 'SIN DATO'} (15 min de retraso; niveles = Gamma Flip, Call Wall, Put Wall, Max Gamma). "
           f"EM = precio × VIX (ES) o VXN (NQ) / 100 / √252 del cierre de esa sesión. Fuente: NEXORA (CRITERIO NEXORA, método propio), Cboe y Yahoo Finance.{antiguo}\n"
           + (f"\n{oro}\n" if oro else "")
           + "Pega la línea en el indicador NEXORA de TradingView (la de ORO, en NEXORA Oro). Contexto de mercado, no una entrada.")
    assert not PALABRAS_PROHIBIDAS.search(txt)
    return txt


def niveles_15h(raiz=RAIZ, ahora=None, forzar=False, enviar_fn=None, J=None):
    """Telegram de lunes a viernes a las 15:00 Madrid (una vez al día; dos crones por el cambio de hora)."""
    ahora = ahora or dt.datetime.now(UTC)
    m = ahora.astimezone(MAD)
    ruta = P(raiz, "data", "estado_niveles_gamma.json")
    est = _leer_json(ruta) or {"enviados": []}
    if m.weekday() >= 5 and not forzar:
        print("fin de semana: sin niveles")
        return 0
    if m.date().isoformat() in est["enviados"] and not forzar:
        print("ya enviados hoy")
        return 0
    if m.hour < 15 and not forzar:
        print(f"{m:%H:%M} Madrid: aún no son las 15:00; lo enviará el otro cron")
        return 0
    J = J or _leer_json(P(raiz, "site", "data", "gamma.json"))
    if not J:
        print("gamma.json no disponible")
        return 1
    try:
        import gamma_oro
        oro = gamma_oro.mensaje_oro(raiz, ahora)
    except Exception as e:  # noqa: BLE001  — el oro no debe impedir los niveles de ES/NQ
        oro = f"ORO: SIN DATO ({type(e).__name__})."
    txt = mensaje_niveles(J, ahora, oro)
    print(txt)
    import telegram
    if enviar_fn is None and not telegram.configurado():
        print("Telegram sin configurar")
        return 0
    ok, err = (enviar_fn or telegram.enviar)(txt)
    if ok:
        est["enviados"] = (est["enviados"] + [m.date().isoformat()])[-30:]
        os.makedirs(P(raiz, "data"), exist_ok=True)
        json.dump(est, open(ruta, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    else:
        print("Telegram:", err)
    return 0 if ok else 1


def gamma_historico(raiz, fecha_et):
    """gamma.json «de época» para repetir una sesión pasada: los niveles son los de la sesión ANTERIOR (data/historico_gamma.csv, solo cierres confirmados) y el EM sale del VIX/VXN de esa
    sesión. No trae Max Gamma (el histórico no lo guardaba). Solo para pruebas en seco."""
    import gamma
    filas = _leer_csv(P(raiz, "data", "historico_gamma.csv"))
    previas = sorted({r["fecha_sesion"] for r in filas if r["fecha_sesion"] < fecha_et.isoformat()})
    if not previas:
        return None
    ses = previas[-1]
    f = lambda x: (float(x) if x not in (None, "") else None)  # noqa: E731
    out = {"indices": {}}
    for r in (r for r in filas if r["fecha_sesion"] == ses):
        c = r["indice"]
        x = {"sesion": ses, "spot_fut": f(r["spot_fut"]), "regimen": r["regimen"], "call_wall": {"fut": f(r["call_wall_fut"])}, "put_wall": {"fut": f(r["put_wall_fut"])}, "flip": {"fut": f(r["flip_fut"])},
             "max_gamma": None, "base": {"base": f(r["base"])}, "ultima_operacion_et": r["ultima_operacion_et"]}
        x["em"] = gamma.calcular_em(c, x)
        out["indices"][c] = x
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vivo", action="store_true", help="una pasada de avisos (envía a Telegram)")
    ap.add_argument("--seco", action="store_true", help="reproduce una sesión y muestra qué avisos habrían salido (no envía ni escribe)")
    ap.add_argument("--fecha", default="", help="fecha ET de la sesión para --seco (por defecto hoy)")
    ap.add_argument("--niveles", action="store_true", help="envía la línea de niveles (15:00 Madrid)")
    ap.add_argument("--forzar", action="store_true")
    ap.add_argument("--historico", action="store_true", help="con --seco --fecha: usa los niveles guardados de la sesión anterior (data/historico_gamma.csv)")
    ap.add_argument("--evaluar", action="store_true")
    a = ap.parse_args()
    if a.niveles:
        return niveles_15h(forzar=a.forzar)
    if a.evaluar:
        n = evaluar()
        J = resumen()
        json.dump(J, open(P(RAIZ, "site", "data", "gamma_intradia.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("evaluaciones nuevas:", len(n))
        return 0
    if a.seco:
        ahora = dt.datetime.now(UTC)
        f = dt.date.fromisoformat(a.fecha) if a.fecha else ahora.astimezone(NY).date()
        fuentes = {"gamma": (lambda: gamma_historico(RAIZ, f))} if a.historico else None
        sal, omit = repetir_sesion(RAIZ, f, fuentes, hasta_utc=ahora if not a.fecha else None)
        print(f"== sesión {f} · avisos que habrían salido: {len(sal)} · omitidos: {omit or 'ninguno'}")
        for hm, i, txt in sal:
            print(f"\n[{hm} ET] {i}\n{re.sub('<[^>]+>', '', txt)}")
        return 0
    if a.vivo:
        for i, e, t in pasada(push=True):
            print(i, e)
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
