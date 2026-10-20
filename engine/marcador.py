#!/usr/bin/env python3
"""NEXORA · Marcador de aciertos de señales. Sin IA, sin red, gratis, SOLO AÑADIR.

Qué hace
  1. REGISTRA cada señal que emite el sistema en data/marcador_senales.csv (id, fecha_utc, tipo, activo, direccion, valor, umbral, fuente, run_id,
     origen, estado, anula_id, nota). Las correcciones nunca editan: se añade una fila ANULADA que apunta a la señal (anular()).
  2. EVALÚA cada señal con dirección a T+1, T+5 y T+20 sesiones con cierres oficiales y lo guarda, solo-añadir, en data/marcador_resultados_v2.csv
     (criterio v2, columna version_criterio=2). data/marcador_resultados.csv (criterio v1: neutral ±0,1 % fijo y SKEW por dirección del cierre) queda CONGELADO y
     no se vuelve a escribir ni a mostrar. Sin dato suficiente = PENDIENTE y no se escribe nunca una estimación.
  3. BACKFILL: reconstruye las señales pasadas desde data/historico_contexto/ y los CSV de memoria (origen = backfill, separadas de las vivas).
  4. Escribe site/data/marcador.json (página #/marcador y bloque «marcador» de contexto.json).

NO cambia ningún umbral ni criterio existente: las alertas, tesis, régimen, liquidez y reglas v3 del monitor de reacción se leen tal como salen.

Señales y su dirección esperada (reglas FIJAS de este módulo, impresas también en la página):
  tesis      cambia la etiqueta de tesis de Oro, NQ, ES o BTC. ALCISTA* = el activo sube; BAJISTA* = baja; SIN TESIS = no puntuable.
  fed        alerta Fed emitida (cambio del resultado más probable o tipo esperado a diciembre ≥ 10 pb). Activo US2Y (rendimiento del bono a 2 años, FRED):
             más subidas descontadas = el 2Y sube; más recortes = baja. La dirección se lee del texto de la alerta; si no se puede, no puntuable.
  regimen    cambia el cuadrante del régimen macro. Activo NQ: FAVORABLE = sube, DESFAVORABLE = baja (campo «riesgo» del propio régimen); MIXTO = no puntuable.
  liquidez   cambia la etiqueta del monitor de liquidez. Activo BTC: «SEÑALES INICIALES DE GIRO» / «GIRO DE LIQUIDEZ EN CURSO» = sube; «SIN GIRO» = no puntuable.
  skew       alerta SKEW en zona alta relativa con ≥ 2 confirmaciones. NO se puntúa por la dirección del cierre. ACIERTO si dentro del horizonte (T+1, T+5, T+20):
             (a) el S&P 500 tiene una caída máxima intrahorizonte ≥ 1 σ_h (peor cierre frente al cierre de referencia; σ_h = desviación típica de los
             retornos diarios de las últimas 250 sesiones × √h) O (b) el VIX sube ≥ 20 % (máximo de los cierres del horizonte frente al de referencia).
             Si no ocurre ninguno de los dos, FALLO. Se guardan los dos componentes. Tasa base = frecuencia de ese mismo evento en cualquier ventana de h sesiones
             de las 250 anteriores a la señal (con σ_h y umbral del VIX fijos en la referencia).
  cruce_sma200_ratio / divergencia_ratio   usos del ratio de consumo (#/consumo, consumo_ratio.py): un cruce VÁLIDO (5 cierres seguidos) de XLY/XLP o RSPD/RSPS sobre/bajo su SMA 200 (diario
             o semanal) = SPY sube/baja; una divergencia (SPY en máximo de 63 sesiones y RSPD/RSPS > 3 % bajo el suyo) = SPY baja. Se miden SOLO a T+20 y T+60 sobre SPY frente a la tasa base.
  consumo    cambia la tesis de consumo (#/consumo). Activo RSPD/RSPS (ratio de peso igual): CONSUMO FUERTE y DIVERGENCIA MERCADO DEFENSIVO = sube; SE ENFRÍA, CONSUMO DÉBIL y
             DIVERGENCIA MERCADO ADELANTADO = baja; SIN TESIS = no puntuable. Se mide a T+1, T+5 y T+20 igual que el resto (el horizonte que importa es T+20).
  petroleo   cambia la tesis de petróleo (#/petroleo). Activo WTI (precio al contado de Cushing, FRED DCOILWTICO: sin los saltos de vencimiento de los futuros empalmados): ALCISTA = sube;
             BAJISTA = baja; SIN TESIS = no puntuable. Se mide a T+1, T+5 y T+20 igual que el resto (el horizonte que importa es T+20).
  reaccion   clasificación del monitor de reacción a eventos (T+5 y CIERRE): SOLO REGISTRO, no se puntúa (reglas v3 congeladas).
Medición (criterio v2): referencia = último cierre COMPLETO anterior a la señal (si sale desde las 21:30 UTC y el activo no es cripto, cuenta el cierre de ese día);
T+n = cierre n sesiones después. Retorno en la dirección esperada. NEUTRAL si |retorno| < 0,25 × σ_h del activo (σ de los cambios diarios de las 250 sesiones
anteriores a la señal × √h; en pb para el 2Y). ACIERTO si el retorno ≥ +0,25 σ_h y FALLO si ≤ −0,25 σ_h. Con menos de 60 cambios diarios previos: PENDIENTE.
Retorno máximo adverso = el peor retorno (en la dirección esperada) de los cierres entre la referencia y T+n (≤ 0). Tasa base = % de ventanas de n sesiones
anteriores a la señal (hasta 250) en las que el activo habría «acertado» en esa dirección con el mismo umbral: lo que se acierta por azar.
Cambio de criterio (18-oct-2026): v1 usaba neutral ±0,1 % fijo y puntuaba el SKEW por la dirección del cierre. Los resultados v1 se conservan sin tocar en
data/marcador_resultados.csv; los resultados v2 se recalcularon para TODAS las señales (también las de backfill) como filas nuevas con version_criterio = 2.
"""
from __future__ import annotations

import csv
import datetime as dt
import glob
import gzip
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(HERE)

CAMPOS = ["id", "fecha_utc", "tipo", "activo", "direccion", "valor", "umbral", "fuente", "run_id", "origen", "estado", "anula_id", "nota"]
CAMPOS_RES = ["id", "version_criterio", "horizonte", "resultado", "ret", "mae", "unidad", "fecha_ref", "valor_ref", "fecha_fin", "valor_fin", "base_pct", "sigma_h", "umbral_neutral",
              "comp_caida", "comp_vix", "caida_max_pct", "vix_max_pct", "base_caida_pct", "base_vix_pct", "evaluado_utc"]
VERSION_CRITERIO = "2"
ARCHIVO_RES = "marcador_resultados_v2.csv"      # v1 (marcador_resultados.csv) queda congelado
K_NEUTRAL = 0.25                          # neutral: |retorno| < 0,25 × σ_h
K_CAIDA = 1.0                             # SKEW: caída máxima ≥ 1 × σ_h
VIX_SUBE_PCT = 20.0                       # SKEW: o el VIX sube ≥ 20 %
MIN_CAMBIOS_SIGMA = 60
HORIZONTES = (1, 5, 20)
CIERRE_UTC = "21:30"                      # a partir de esta hora UTC el cierre de ese día de EE. UU. ya es oficial
MIN_N = 20
VENTANA_BASE = 250
MIN_VENTANAS_BASE = 60
CRIPTO = {"btc"}
TIPOS_PUNTUABLES = ("tesis", "fed", "skew", "regimen", "liquidez", "consumo", "petroleo", "cruce_sma200_ratio", "divergencia_ratio")
HORIZ_TIPO = {"cruce_sma200_ratio": (20, 60), "divergencia_ratio": (20, 60)}   # los tipos del ratio de consumo se miden a T+20 y T+60 (el resto, a T+1, T+5 y T+20)
ACT = {"Oro": ("ORO", "oro"), "Nasdaq 100": ("NQ", "ndx"), "S&P 500": ("ES", "spx"), "Bitcoin": ("BTC", "btc")}
SERIE_DE = {"ORO": "oro", "NQ": "ndx", "ES": "spx", "BTC": "btc", "US2Y": "us2y", "RSPD/RSPS": "rsd", "WTI": "wti", "SPY": "spy"}
LIQ_ALCISTA = ("GIRO DE LIQUIDEZ EN CURSO", "SEÑALES INICIALES DE GIRO")
# Versiones de criterio de las SEÑALES de un tipo (las filas ya registradas no se reescriben: cada señal lleva su versión en la columna «umbral»; los resultados quedan donde están).
CRITERIOS_TIPO = {"petroleo": {"actual": 2, "versiones": {
    "1": {"desde": "2026-10-19", "hasta": "2026-10-20", "regla": "tesis de petróleo con COT a favor de la tendencia: percentil 3 años del dinero gestionado ≥ 66 → +1, ≤ 34 → −1 (Fase 15; sin señales registradas con esta versión)"},
    "2": {"desde": "2026-10-20", "hasta": None, "regla": "tesis de petróleo con el criterio ÚNICO de COT de NEXORA, solo extremos a la contra: percentil 3 años ≥ 90 → −1, ≤ 10 → +1, resto 0"}}}}
DIR_CONSUMO = {"CONSUMO FUERTE": "ALCISTA", "DIVERGENCIA MERCADO DEFENSIVO": "ALCISTA", "SE ENFRÍA": "BAJISTA", "CONSUMO DÉBIL": "BAJISTA", "DIVERGENCIA MERCADO ADELANTADO": "BAJISTA"}
PASOS = {"bajada": -1, "mantener": 0, "subida": 1}


def P(raiz, *a):
    return os.path.join(raiz, *a)


# ---------------------------------------------------------------- CSV solo-añadir
def leer_csv(ruta):
    if not os.path.exists(ruta):
        return []
    with open(ruta, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def anadir(ruta, filas, campos, clave):
    """Añade filas cuya clave no exista. Nunca modifica ni borra filas anteriores. Devuelve las añadidas."""
    vistas = {clave(r) for r in leer_csv(ruta)}
    nuevas = []
    for r in filas:
        k = clave(r)
        if k in vistas:
            continue
        vistas.add(k)
        nuevas.append(r)
    if not nuevas:
        return []
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    existe = os.path.exists(ruta)
    with open(ruta, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        if not existe:
            w.writeheader()
        for r in nuevas:
            w.writerow({c: r.get(c, "") for c in campos})
    return nuevas


def leer_json(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def _id(tipo, activo, fecha_utc, valor):
    h = hashlib.sha1(f"{tipo}|{activo}|{fecha_utc}|{valor}".encode("utf-8")).hexdigest()[:10]
    return f"{tipo}-{activo.lower()}-{fecha_utc[:10].replace('-', '')}{fecha_utc[11:16].replace(':', '')}-{h}"


def senal(tipo, activo, direccion, fecha_utc, valor, umbral, fuente, run_id, origen, nota=""):
    return {"id": _id(tipo, activo, fecha_utc, valor), "fecha_utc": fecha_utc, "tipo": tipo, "activo": activo, "direccion": direccion, "valor": valor,
            "umbral": umbral, "fuente": fuente, "run_id": run_id, "origen": origen, "estado": "ACTIVA", "anula_id": "", "nota": nota}


# ---------------------------------------------------------------- señales a partir de cambios de etiqueta
def dir_tesis(et):
    return "ALCISTA" if str(et).startswith("ALCISTA") else "BAJISTA" if str(et).startswith("BAJISTA") else "NINGUNA"


def senal_de_cambio(serie, ts, prev, valor, extra, run_id, origen, nota=""):
    if serie.startswith("tesis:"):
        cod, _ = ACT[serie[6:]]
        return senal("tesis", cod, dir_tesis(valor), ts, f"{prev} → {valor}", "cambio de la etiqueta de tesis", "por_activo.py (resumen.json)", run_id, origen, nota)
    if serie == "regimen":
        riesgo = (extra or {}).get("riesgo")
        d = "ALCISTA" if riesgo == "FAVORABLE" else "BAJISTA" if riesgo == "DESFAVORABLE" else "NINGUNA"
        return senal("regimen", "NQ", d, ts, f"{prev} → {valor} (riesgo {riesgo or 'SIN DATO'})", "cambio del cuadrante de régimen", "regimen.py (regimen.json)", run_id, origen, nota)
    if serie == "consumo":
        d = DIR_CONSUMO.get(valor, "NINGUNA")
        return senal("consumo", "RSPD/RSPS", d, ts, f"{prev} → {valor}", "cambio de la tesis de consumo", "consumo.py (consumo.json)", run_id, origen, nota)
    if serie == "petroleo":
        d = dir_tesis(valor)
        return senal("petroleo", "WTI", d, ts, f"{prev} → {valor}", f"cambio de la tesis de petróleo · criterio petróleo v{CRITERIOS_TIPO['petroleo']['actual']} (COT único a la contra 90/10)", "petroleo.py (petroleo.json)", run_id, origen, nota)
    if serie == "liquidez":
        d = "ALCISTA" if valor in LIQ_ALCISTA else "NINGUNA"
        return senal("liquidez", "BTC", d, ts, f"{prev} → {valor}", "cambio de la etiqueta de liquidez", "liquidez_cripto.py (liquidez.json)", run_id, origen, nota)
    return None


def detectar_cambios(obs, ultimo, run_id, origen):
    """obs = [(ts, serie, valor, extra, nota)] ordenado por ts. La primera observación de cada serie es solo referencia (no es un cambio)."""
    out = []
    for ts, serie, valor, extra, nota in sorted(obs, key=lambda x: x[0]):
        if valor in (None, "", "SIN DATO"):
            continue
        prev = ultimo.get(serie)
        if prev is None:
            ultimo[serie] = valor
            continue
        if valor != prev:
            s = senal_de_cambio(serie, ts, prev, valor, extra, run_id, origen, nota)
            if s:
                out.append(s)
            ultimo[serie] = valor
    return out


# ---------------------------------------------------------------- señales a partir de alertas y reacciones ya emitidas
def dir_fed(l1):
    """Dirección del rendimiento del 2Y que sugiere el texto de la alerta Fed; None si no se puede leer."""
    m = re.search(r"se mueve ([+\-−]\d+) pb en 5 sesiones", l1)
    if m:
        v = int(m.group(1).replace("−", "-"))
        return "ALCISTA" if v > 0 else "BAJISTA" if v < 0 else None
    m = re.search(r"pasa de «(\w+)» a «(\w+)»", l1)
    if m and m.group(1) in PASOS and m.group(2) in PASOS:
        d = PASOS[m.group(2)] - PASOS[m.group(1)]
        return "ALCISTA" if d > 0 else "BAJISTA" if d < 0 else None
    s = re.search(r"subida (\d+) % → (\d+) %", l1)
    b = re.search(r"bajada (\d+) % → (\d+) %", l1)
    if s and b:
        d = (int(s.group(2)) - int(s.group(1))) - (int(b.group(2)) - int(b.group(1)))
        return "ALCISTA" if d > 0 else "BAJISTA" if d < 0 else None
    return None


def senales_de_alertas(filas, run_id, origen):
    out = []
    for r in filas:
        clave, l1, ts = r.get("clave", ""), r.get("l1", ""), r.get("fecha_utc", "").replace(" UTC", "")[:16]
        if clave == "fed":
            d = dir_fed(l1)
            out.append(senal("fed", "US2Y", d or "NINGUNA", ts, re.sub(r"\s*\(FedWatch.*$", "", l1)[:200], "cambio del resultado más probable o ≥ 10 pb a diciembre",
                             "alertas.py (historico_alertas.csv)", run_id, origen, "" if d else "dirección no interpretable del texto de la alerta"))
        elif clave.startswith("skew_"):
            m = re.search(r"confirmaciones encendidas (\d+) de (\d+)", l1)
            if not m or int(m.group(1)) < 2:     # solo cuenta la regla vigente: zona alta relativa con ≥ 2 confirmaciones
                continue
            out.append(senal("skew", "ES", "BAJISTA", ts, f"SKEW alto relativo; confirmaciones {m.group(1)} de {m.group(2)}", "zona alta relativa (p ≥ 90) y ≥ 2 confirmaciones",
                             "alertas.py (historico_alertas.csv)", run_id, origen))
    return out


def senales_de_reacciones(filas, run_id, origen):
    out = []
    for r in filas:
        if r.get("fase") not in ("T+5", "CIERRE") or r.get("origen") == "anulación":
            continue
        cl = (r.get("clasificacion") or "").strip()
        ts = (r.get("objetivo_utc") or "").strip()
        if not cl or cl == "SIN DATO" or not ts:
            continue
        out.append(senal("reaccion", "EVENTO", "NINGUNA", ts[:16], f"{r['evento_id']} {r['fase']}: {cl}", f"reglas v{r.get('version_regla') or '3'} (congeladas)",
                         "reaccion.py (reacciones_eventos.csv)", run_id, origen, "solo registro: no se puntúa"))
    return out


# ---------------------------------------------------------------- observaciones (vivas y de backfill)
def obs_de_contexto(ctx, ts):
    """Observaciones de tesis, régimen y liquidez de un contexto.json (lo mismo que ve el Diario)."""
    obs = []
    for t in ((ctx.get("tesis") or {}).get("tesis_por_activo") or []):
        if t.get("activo") in ACT and t.get("etiqueta"):
            obs.append((ts, "tesis:" + t["activo"], t["etiqueta"], None, ""))
    R = ctx.get("regimen_macro") or {}
    if R.get("cuadrante"):
        obs.append((ts, "regimen", R["cuadrante"], {"riesgo": R.get("riesgo")}, ""))
    L = ctx.get("liquidez") or {}
    if L.get("lectura"):
        obs.append((ts, "liquidez", L["lectura"], None, ""))
    K = (ctx.get("consumo") or {}).get("tesis") or {}
    if K.get("resultado"):
        obs.append((ts, "consumo", K["resultado"], None, ""))
    K = (ctx.get("petroleo") or {}).get("tesis") or {}
    if K.get("resultado"):
        obs.append((ts, "petroleo", K["resultado"], None, ""))
    return obs


def obs_vivas(raiz, ts):
    sd = P(raiz, "site", "data")
    obs = []
    R = leer_json(P(sd, "resumen.json")) or {}
    for a, t in (R.get("tesis_activos") or {}).items():
        if a in ACT and t.get("etiqueta"):
            obs.append((ts, "tesis:" + a, t["etiqueta"], None, ""))
    G = ((leer_json(P(sd, "regimen.json")) or {}).get("evaluacion")) or {}
    if G.get("cuadrante"):
        obs.append((ts, "regimen", G["cuadrante"], {"riesgo": G.get("riesgo")}, ""))
    L = ((leer_json(P(sd, "liquidez.json")) or {}).get("evaluacion")) or {}
    if L.get("lectura"):
        obs.append((ts, "liquidez", L["lectura"], None, ""))
    K = (leer_json(P(sd, "consumo.json")) or {}).get("tesis") or {}
    if K.get("resultado"):
        obs.append((ts, "consumo", K["resultado"], None, ""))
    K = (leer_json(P(sd, "petroleo.json")) or {}).get("tesis") or {}
    if K.get("resultado"):
        obs.append((ts, "petroleo", K["resultado"], None, ""))
    return obs


def obs_de_csv_antiguos(raiz, antes_de):
    """Filas diarias de los CSV de memoria anteriores a la primera foto de contexto. Solo traen la fecha: se toma el FINAL del día y se anota."""
    obs, nota = [], "hora desconocida (la fuente solo trae la fecha): se toma el final del día"
    for r in leer_csv(P(raiz, "data", "registro_tesis.csv")):
        ts = (r.get("capturado_utc") or "")[:16] or f"{r['fecha']} 23:59"
        if r["activo"] in ACT and ts < antes_de:
            obs.append((ts, "tesis:" + r["activo"], r["tesis"], None, "" if r.get("capturado_utc") else nota))
    for r in leer_csv(P(raiz, "data", "historico_regimen.csv")):
        ts = f"{r['fecha_captura']} 23:59"
        if ts < antes_de:
            obs.append((ts, "regimen", r["cuadrante"], {"riesgo": r.get("riesgo")}, nota))
    for r in leer_csv(P(raiz, "data", "historico_liquidez.csv")):
        ts = f"{r['fecha_captura']} 23:59"
        if ts < antes_de:
            obs.append((ts, "liquidez", r["lectura"], None, nota))
    return obs


def _estado(raiz):
    return leer_json(P(raiz, "data", "estado_marcador.json")) or {"ultimo": {}}


def _guardar_estado(raiz, est):
    with open(P(raiz, "data", "estado_marcador.json"), "w", encoding="utf-8") as f:
        json.dump(est, f, ensure_ascii=False, indent=1)


def _reg(raiz, filas):
    return anadir(P(raiz, "data", "marcador_senales.csv"), filas, CAMPOS, lambda r: r["id"])


def backfill(raiz=RAIZ):
    """Reconstruye las señales pasadas (origen=backfill) desde el histórico de contexto y los CSV de memoria. Idempotente."""
    fotos = sorted(glob.glob(P(raiz, "data", "historico_contexto", "*", "*.json.gz")))
    obs = []
    for f in fotos:
        try:
            ctx = json.loads(gzip.decompress(open(f, "rb").read()))
        except Exception:  # noqa: BLE001
            continue
        d, hm = os.path.basename(os.path.dirname(f)), os.path.basename(f)[:4]
        obs += obs_de_contexto(ctx, f"{d} {hm[:2]}:{hm[2:]}")
    primera = min((o[0] for o in obs), default="9999")
    obs += obs_de_csv_antiguos(raiz, primera)
    est = {"ultimo": {}}
    nuevas = _reg(raiz, detectar_cambios(obs, est["ultimo"], "backfill", "backfill"))
    nuevas += _reg(raiz, senales_de_alertas(leer_csv(P(raiz, "data", "historico_alertas.csv")), "backfill", "backfill"))
    nuevas += _reg(raiz, senales_de_reacciones(leer_csv(P(raiz, "data", "reacciones_eventos.csv")), "backfill", "backfill"))
    prev = _estado(raiz)
    if not prev.get("backfill_utc"):   # el estado de las observaciones solo se fija en el primer backfill; después lo mueven las ejecuciones vivas
        prev["ultimo"] = est["ultimo"]
    prev["backfill_utc"] = prev.get("backfill_utc") or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    _guardar_estado(raiz, prev)
    return nuevas


def registrar(raiz=RAIZ, ahora=None, run_id=None):
    """Registro VIVO (origen=vivo): cambios de etiqueta desde la última observación guardada + alertas y reacciones nuevas."""
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    ts = ahora.strftime("%Y-%m-%d %H:%M")
    run_id = run_id or os.environ.get("GITHUB_RUN_ID") or "local"
    est = _estado(raiz)
    nuevas = _reg(raiz, detectar_cambios(obs_vivas(raiz, ts), est.setdefault("ultimo", {}), run_id, "vivo"))
    nuevas += _reg(raiz, senales_de_alertas(leer_csv(P(raiz, "data", "historico_alertas.csv")), run_id, "vivo"))
    nuevas += _reg(raiz, senales_de_reacciones(leer_csv(P(raiz, "data", "reacciones_eventos.csv")), run_id, "vivo"))
    _guardar_estado(raiz, est)
    return nuevas


def anular(raiz, id_, motivo, run_id="manual"):
    """Corrección: NO se edita ni se borra nada; se añade una fila ANULADA que apunta a la señal."""
    orig = next((r for r in leer_csv(P(raiz, "data", "marcador_senales.csv")) if r["id"] == id_), None)
    if not orig:
        raise ValueError("no existe la señal " + id_)
    fila = dict(orig, id=f"ANULADA-{id_}", estado="ANULADA", anula_id=id_, run_id=run_id, nota=motivo,
                fecha_utc=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M"))
    return _reg(raiz, [fila])


# ---------------------------------------------------------------- series de cierres
def cargar_series(raiz):
    sd = P(raiz, "site", "data")
    out = {}
    pr = ((leer_json(P(sd, "precios.json")) or {}).get("activos")) or {}
    for k in ("oro", "ndx", "spx", "btc", "vix"):
        s = (pr.get(k) or {}).get("serie") or []
        out[k] = [(d, float(v)) for d, v in s if v is not None]
    rsd = ((((leer_json(P(sd, "consumo.json")) or {}).get("graficos") or {}).get("igual") or {}).get("ratio")) or []     # ratio RSPD/RSPS (peso igual) de #/consumo
    out["rsd"] = [(d, float(v)) for d, v in rsd if v is not None]
    try:                                                       # SPY (cierres diarios guardados por consumo_ratio.py: histórico completo para medir el backfill desde 2010)
        with open(P(raiz, "data", "spy_cierres.csv"), encoding="utf-8", newline="") as f:
            out["spy"] = [(r["fecha"], float(r["cierre"])) for r in csv.DictReader(f)]
    except OSError:
        out["spy"] = []
    wsp = (((leer_json(P(sd, "petroleo.json")) or {}).get("precios") or {}).get("wti_spot_serie")) or []     # WTI al contado (FRED DCOILWTICO) de #/petroleo
    out["wti"] = [(d, float(v)) for d, v in wsp if v is not None]
    t = ((leer_json(P(sd, "tipos.json")) or {}).get("t2y") or {}).get("serie") or []
    out["us2y"] = [(d, float(v)) for d, v in t if v is not None]
    return out


def completas(serie, clave, ahora):
    """Quita las barras que aún no son cierre oficial: la del día en curso (cripto: siempre; resto: antes de las 21:30 UTC) y las futuras."""
    hoy, hm = ahora.strftime("%Y-%m-%d"), ahora.strftime("%H:%M")
    out = []
    for d, v in serie:
        if d > hoy or (d == hoy and (clave in CRIPTO or hm < CIERRE_UTC)):
            continue
        out.append((d, v))
    return out


def _unidad(clave):
    return "pb" if clave == "us2y" else "%"


def _mov(clave, v0, v1):
    return (v1 - v0) * 100 if clave == "us2y" else (v1 / v0 - 1) * 100


def indice_ref(serie, clave, ts):
    d, hm = ts[:10], ts[11:16]
    corte = d if (clave not in CRIPTO and hm >= CIERRE_UTC) else (dt.date.fromisoformat(d) - dt.timedelta(days=1)).isoformat()
    idx = None
    for i, (dd, _) in enumerate(serie):
        if dd <= corte:
            idx = i
        else:
            break
    if idx is None or (dt.date.fromisoformat(corte) - dt.date.fromisoformat(serie[idx][0])).days > 7:
        return None
    return idx


def cambios_diarios(serie, clave, hasta, n=VENTANA_BASE):
    """Cambios diarios (en % o en pb) de las n sesiones que terminan en `hasta` (incluida). Solo mira el pasado."""
    ini = max(1, hasta - n + 1)
    return [_mov(clave, serie[i - 1][1], serie[i][1]) for i in range(ini, hasta + 1)]


def sigma_h(serie, clave, idx, h):
    """σ de los cambios diarios de las 250 sesiones hasta la referencia × √h. None si hay menos de 60 cambios (no se estima)."""
    c = cambios_diarios(serie, clave, idx)
    if len(c) < MIN_CAMBIOS_SIGMA:
        return None
    m = sum(c) / len(c)
    sd = (sum((x - m) ** 2 for x in c) / (len(c) - 1)) ** 0.5
    return sd * h ** 0.5


def tasa_base(serie, clave, idx, n, dir_, umbral):
    """% de ventanas de n sesiones TERMINADAS en la referencia (sin mirar el futuro) cuyo retorno en la dirección esperada supera el umbral. None si hay pocas."""
    ini = max(0, idx - VENTANA_BASE)
    ok = tot = 0
    for i in range(ini, idx - n + 1):
        tot += 1
        ok += _mov(clave, serie[i][1], serie[i + n][1]) * dir_ >= umbral
    return round(ok / tot * 100, 1) if tot >= MIN_VENTANAS_BASE else None


def medir(serie, clave, ts, dir_, n):
    """Resultado v2 de una señal direccional a n sesiones; None = PENDIENTE (sin referencia, sin σ o aún sin el cierre n sesiones después)."""
    idx = indice_ref(serie, clave, ts)
    if idx is None or idx + n >= len(serie):
        return None
    sg = sigma_h(serie, clave, idx, n)
    if sg is None:
        return None
    umbral = K_NEUTRAL * sg
    ref = serie[idx]
    ruta = [_mov(clave, ref[1], serie[idx + k][1]) * dir_ for k in range(1, n + 1)]
    ret = ruta[-1]
    res = "ACIERTO" if ret >= umbral and ret > 0 else "FALLO" if ret <= -umbral and ret < 0 else "NEUTRAL"
    return {"resultado": res, "ret": round(ret, 3), "mae": round(min(0.0, min(ruta)), 3), "unidad": _unidad(clave), "fecha_ref": ref[0], "valor_ref": ref[1],
            "fecha_fin": serie[idx + n][0], "valor_fin": serie[idx + n][1], "base_pct": tasa_base(serie, clave, idx, n, dir_, umbral), "sigma_h": round(sg, 4),
            "umbral_neutral": round(umbral, 4)}


def _evento_skew(spx, vix_por_fecha, i, n, sg):
    """(caída máxima %, subida máxima del VIX %, hay caída ≥ 1σ_h, hay VIX ≥ +20 %) en la ventana de n sesiones que empieza en i. None si falta el VIX de algún día."""
    ref = spx[i][1]
    caida = min((spx[i + k][1] / ref - 1) * 100 for k in range(1, n + 1))
    v0 = vix_por_fecha.get(spx[i][0])
    vs = [vix_por_fecha.get(spx[i + k][0]) for k in range(1, n + 1)]
    if v0 is None or any(v is None for v in vs):
        return caida, None, caida <= -K_CAIDA * sg, None
    vmax = max((v / v0 - 1) * 100 for v in vs)
    return caida, vmax, caida <= -K_CAIDA * sg, vmax >= VIX_SUBE_PCT


def medir_skew(spx, vix, ts, n):
    """SKEW (criterio v2): ACIERTO si el S&P cae ≥ 1σ_h dentro del horizonte o el VIX sube ≥ 20 %; si no, FALLO. Guarda los dos componentes y la tasa base."""
    idx = indice_ref(spx, "spx", ts)
    if idx is None or idx + n >= len(spx):
        return None
    sg = sigma_h(spx, "spx", idx, n)
    if sg is None:
        return None
    vp = dict(vix)
    caida, vmax, c_caida, c_vix = _evento_skew(spx, vp, idx, n, sg)
    if c_vix is None:        # sin VIX en la ventana no se puede evaluar el componente (b): PENDIENTE, nunca se supone
        return None
    ini, tot, ok, okc, okv = max(0, idx - VENTANA_BASE), 0, 0, 0, 0
    for i in range(ini, idx - n + 1):
        c, v, a, b = _evento_skew(spx, vp, i, n, sg)
        if b is None:
            continue
        tot += 1
        ok += a or b
        okc += a
        okv += b
    base = lambda x: round(x / tot * 100, 1) if tot >= MIN_VENTANAS_BASE else None  # noqa: E731
    ref = spx[idx]
    return {"resultado": "ACIERTO" if (c_caida or c_vix) else "FALLO", "ret": round((spx[idx + n][1] / ref[1] - 1) * 100, 3), "mae": round(min(0.0, caida), 3), "unidad": "%",
            "fecha_ref": ref[0], "valor_ref": ref[1], "fecha_fin": spx[idx + n][0], "valor_fin": spx[idx + n][1], "base_pct": base(ok), "sigma_h": round(sg, 4), "umbral_neutral": "",
            "comp_caida": int(c_caida), "comp_vix": int(c_vix), "caida_max_pct": round(caida, 3), "vix_max_pct": round(vmax, 2), "base_caida_pct": base(okc), "base_vix_pct": base(okv)}


def evaluar(raiz=RAIZ, ahora=None):
    """Mide las señales (criterio v2) y añade a marcador_resultados_v2.csv los horizontes ya resueltos. Devuelve las filas nuevas."""
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    stamp = ahora.strftime("%Y-%m-%d %H:%M UTC")
    series = {k: completas(v, k, ahora) for k, v in cargar_series(raiz).items()}
    filas = leer_csv(P(raiz, "data", "marcador_senales.csv"))
    anuladas = {r["anula_id"] for r in filas if r.get("estado") == "ANULADA"}
    hechos = {(r["id"], r["horizonte"]) for r in leer_csv(P(raiz, "data", ARCHIVO_RES)) if r.get("version_criterio") == VERSION_CRITERIO}
    nuevos = []
    for s in filas:
        if s.get("estado") == "ANULADA" or s["id"] in anuladas or s["tipo"] not in TIPOS_PUNTUABLES:
            continue
        es_skew = s["tipo"] == "skew"
        if not es_skew and s["direccion"] not in ("ALCISTA", "BAJISTA"):
            continue
        clave = "spx" if es_skew else SERIE_DE.get(s["activo"])
        if not clave or not series.get(clave):
            continue
        d = 1 if s["direccion"] == "ALCISTA" else -1
        for n in HORIZ_TIPO.get(s["tipo"], HORIZONTES):
            if (s["id"], str(n)) in hechos:
                continue
            m = medir_skew(series["spx"], series.get("vix") or [], s["fecha_utc"], n) if es_skew else medir(series[clave], clave, s["fecha_utc"], d, n)
            if m:
                nuevos.append({"id": s["id"], "version_criterio": VERSION_CRITERIO, "horizonte": n, "evaluado_utc": stamp, **m})
    return anadir(P(raiz, "data", ARCHIVO_RES), nuevos, CAMPOS_RES, lambda r: (r["id"], str(r["horizonte"]), r["version_criterio"]))


# ---------------------------------------------------------------- resumen para la web y contexto.json
def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def resumen(raiz=RAIZ, ahora=None):
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    filas = leer_csv(P(raiz, "data", "marcador_senales.csv"))
    anuladas = {r["anula_id"] for r in filas if r.get("estado") == "ANULADA"}
    activas = [r for r in filas if r.get("estado") != "ANULADA" and r["id"] not in anuladas]
    res = {}
    for r in leer_csv(P(raiz, "data", ARCHIVO_RES)):
        if r.get("version_criterio") == VERSION_CRITERIO:    # solo criterio v2; v1 queda congelado en su archivo
            res.setdefault(r["id"], {})[int(r["horizonte"])] = r
    series_ok = bool(cargar_series(raiz).get("spx"))
    por = {}
    detalle = []
    for s in activas:
        o, t = s["origen"], s["tipo"]
        puntuable = t in TIPOS_PUNTUABLES and (t == "skew" or s["direccion"] in ("ALCISTA", "BAJISTA"))
        d = por.setdefault(o, {}).setdefault(t, {"n_senales": 0, "no_puntuables": 0, "horizontes": {str(h): {"n": 0, "aciertos": 0, "fallos": 0, "neutrales": 0, "pendientes": 0, "comp_caida": 0, "comp_vix": 0, "_ret": [], "_mae": [], "_base": []} for h in HORIZ_TIPO.get(t, HORIZONTES)}})
        d["n_senales"] += 1
        hs = {}
        if not puntuable:
            d["no_puntuables"] += 1
        for h in HORIZ_TIPO.get(t, HORIZONTES):
            x = res.get(s["id"], {}).get(h)
            if not puntuable:
                continue
            b = d["horizontes"][str(h)]
            if not x:
                b["pendientes"] += 1
                hs[str(h)] = {"estado": "PENDIENTE"}
                continue
            b["n"] += 1
            b["aciertos"] += x["resultado"] == "ACIERTO"
            b["fallos"] += x["resultado"] == "FALLO"
            b["neutrales"] += x["resultado"] == "NEUTRAL"
            if t == "skew":
                b["comp_caida"] += x.get("comp_caida") == "1"
                b["comp_vix"] += x.get("comp_vix") == "1"
            b["_ret"].append(_num(x["ret"]))
            b["_mae"].append(_num(x["mae"]))
            if _num(x["base_pct"]) is not None:
                b["_base"].append(_num(x["base_pct"]))
            hs[str(h)] = {"estado": x["resultado"], "ret": _num(x["ret"]), "mae": _num(x["mae"]), "unidad": x["unidad"], "base_pct": _num(x["base_pct"]), "fecha_fin": x["fecha_fin"], "sigma_h": _num(x.get("sigma_h")),
                          **({"comp_caida": x.get("comp_caida") == "1", "comp_vix": x.get("comp_vix") == "1", "caida_max_pct": _num(x.get("caida_max_pct")), "vix_max_pct": _num(x.get("vix_max_pct"))} if t == "skew" else {})}
        detalle.append({"id": s["id"], "fecha_utc": s["fecha_utc"], "tipo": t, "activo": s["activo"], "direccion": s["direccion"], "valor": s["valor"], "origen": o,
                        "run_id": s["run_id"], "nota": s["nota"], "criterio": (s.get("umbral") if t == "petroleo" else None), "horizontes": hs if puntuable else "SOLO REGISTRO" if t == "reaccion" else "NO PUNTUABLE"})
    for o, tipos in por.items():
        for t, d in tipos.items():
            for h, b in d["horizontes"].items():
                ret, mae, base = b.pop("_ret"), b.pop("_mae"), b.pop("_base")
                n = b["n"]
                b["acierto_pct"] = round(b["aciertos"] / n * 100, 1) if n else None
                b["ret_medio"] = round(sum(ret) / n, 3) if n else None
                b["peor_ret"] = round(min(ret), 3) if n else None
                b["peor_mae"] = round(min(mae), 3) if n else None
                b["base_media_pct"] = round(sum(base) / len(base), 1) if base else None
                b["diferencia_pp"] = round(b["acierto_pct"] - b["base_media_pct"], 1) if n and base else None
                b["muestra_insuficiente"] = n < MIN_N
    detalle.sort(key=lambda x: x["fecha_utc"], reverse=True)
    return {"version": 2, "version_criterio": 2, "generado_utc": ahora.strftime("%Y-%m-%d %H:%M UTC"), "ok": True, "min_n": MIN_N, "horizontes": sorted(set(HORIZONTES) | {h for v in HORIZ_TIPO.values() for h in v}), "horizontes_por_tipo": {k: list(v) for k, v in HORIZ_TIPO.items()},
            "criterio": {"version": 2, "neutral": f"|retorno| < {K_NEUTRAL} × σ_h (σ de 250 sesiones × √h; en pb para el 2Y)", "skew": f"caída máxima intrahorizonte ≥ {K_CAIDA:g} σ_h o VIX ≥ +{VIX_SUBE_PCT:g} %", "desde": "2026-10-18"},
            "cambio_criterio": "Criterio v2 (18-oct-2026): el neutral pasa de ±0,1 % fijo a |retorno| < 0,25 × σ_h del activo (σ de 250 sesiones × √h; σ en pb para el 2Y), y el SKEW deja de puntuarse por la dirección del cierre: acierto si el S&P tiene una caída máxima intrahorizonte ≥ 1 σ_h o el VIX sube ≥ 20 %. Todos los resultados, también los de backfill, se recalcularon como filas nuevas con version_criterio = 2; los de v1 se conservan sin tocar en data/marcador_resultados.csv y no se muestran aquí.",
            "series_disponibles": series_ok, "criterios_tipo": CRITERIOS_TIPO,
            "resumen": por, "n_senales": len(activas), "n_anuladas": len(anuladas), "senales": detalle[:400],
            "reglas": "Señales y su dirección esperada" + __doc__.split("Señales y su dirección esperada")[1].strip(),
            "nota": "Las señales se solapan en el tiempo (p. ej. cambios de tesis seguidos del mismo activo): no son observaciones independientes. Sin conclusiones automáticas."}


def etapa(raiz=RAIZ, modo="", ahora=None):
    """Para build.py: registra siempre; evalúa en cierre/diario/todo (hay cierres oficiales nuevos). Escribe site/data/marcador.json."""
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    n_reg = len(registrar(raiz, ahora))
    n_res = 0
    if any(m in modo for m in ("cierre", "diario", "todo")) or modo == "":
        n_res = len(evaluar(raiz, ahora))
    out = resumen(raiz, ahora)
    out["ultima_ejecucion"] = {"senales_nuevas": n_reg, "resultados_nuevos": n_res, "evaluo": bool(n_res or any(m in modo for m in ("cierre", "diario", "todo")))}
    return out


def bloque_contexto(raiz=RAIZ):
    """Resumen compacto para contexto.json (sin recalcular nada: lee site/data/marcador.json)."""
    M = leer_json(P(raiz, "site", "data", "marcador.json"))
    if not M or not M.get("resumen") and not M.get("n_senales"):
        return {"estado": "SIN DATO", "fuente": "marcador.py (data/marcador_senales.csv)"}
    comp = {}
    for o, tipos in (M.get("resumen") or {}).items():
        for t, d in tipos.items():
            comp.setdefault(o, {})[t] = {"senales": d["n_senales"], "no_puntuables": d["no_puntuables"],
                                         **{f"T+{h}": {k: b[k] for k in ("n", "acierto_pct", "base_media_pct", "diferencia_pp", "ret_medio", "peor_mae", "muestra_insuficiente", "pendientes", "comp_caida", "comp_vix")}
                                            for h, b in d["horizontes"].items()}}
    return {"version_criterio": 2, "criterio": M.get("criterio"), "cambio_criterio": M.get("cambio_criterio"), "actualizado_utc": M.get("generado_utc"), "n_senales": M.get("n_senales"), "n_anuladas": M.get("n_anuladas"), "por_origen_y_tipo": comp,
            "lectura": ["Cita siempre n y la tasa base; con muestra_insuficiente = true no se concluye nada.",
                        "origen 'backfill' = señales reconstruidas del pasado; 'vivo' = emitidas por el sistema en su momento: no se mezclan.",
                        "Las señales se solapan: no son independientes. Hecho = resultado medido; lo demás es interpretación."],
            "fuente": "marcador.py (data/marcador_senales.csv, data/marcador_resultados_v2.csv, criterio v2); cierres de Yahoo Finance y FRED"}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "evaluar"
    if cmd == "backfill":
        print("señales nuevas:", len(backfill()))
        print("resultados nuevos:", len(evaluar()))
    elif cmd == "registrar":
        print("señales nuevas:", len(registrar()))
    elif cmd == "evaluar":
        print("resultados nuevos:", len(evaluar()))
    elif cmd == "anular":
        print(anular(RAIZ, sys.argv[2], " ".join(sys.argv[3:]) or "corrección manual"))
    else:
        print(__doc__)
        sys.exit(2)
    with open(P(RAIZ, "site", "data", "marcador.json"), "w", encoding="utf-8") as f:
        json.dump(resumen(), f, ensure_ascii=False, indent=1)
