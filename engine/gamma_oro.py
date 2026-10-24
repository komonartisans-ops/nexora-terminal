"""NEXORA · GAMMA DEL ORO (Fase 17) — CRITERIO NEXORA (método propio; NO es un dato oficial de ningún proveedor).

No existe una cadena de opciones de XAU/USD con acceso gratuito. La referencia que sí existe es la del ETF GLD (SPDR Gold Shares) en la cadena con 15 min de retraso de Cboe.
Por eso TODOS los niveles se etiquetan «GLD, referencia»: son niveles de GLD pasados a precio de XAU/USD con un ratio, no niveles de opciones sobre el oro al contado.

Método (el mismo que SPX/NDX en gamma.py, con una sola cadena y sin escalar ETF):
  1. Cadena GLD de Cboe: vencimientos de 1 a 45 días, strikes a ±15 %, IV por (vencimiento, strike), gamma recalculada con Black-Scholes, GEX$ = gamma × OI × 100 × S² × 1 %.
     Convención de signo (HIPÓTESIS): calls +, puts −.
  2. Tramos de 1 $ de GLD. Call Wall = tramo por encima del precio con más GEX de calls; Put Wall = por debajo con más GEX de puts; Gamma Flip = precio de GLD al que el GEX neto
     cambia de signo (barrido ±12 %); Max Gamma = tramo con más gamma absoluta (calls + |puts|).
  3. EM (movimiento esperado de UN día) = precio de GLD × GVZ / 100 / √252 (GVZ = índice de volatilidad implícita del oro de Cboe, cierre de la sesión de la cadena).
  4. Conversión a precio XAU/USD: nivel XAU = nivel GLD × ratio, con ratio = XAU spot / cierre de GLD de ESA sesión. El ratio se anota cada cierre en data/xau_gld_ratio.csv
     (solo añadir) con su fecha: GLD al cierre de Nueva York (16:00 ET) y XAU al contado a la hora de la ejecución de cierre (21:30 UTC, ≈ cierre diario del oro al contado, 17:00 ET).
     Si falta el ratio de la sesión se usa el último anotado (≤ 5 días) y se avisa con su fecha; sin ratio los niveles quedan solo en GLD (SIN DATO en XAU). El ratio no es constante:
     deriva despacio (comisiones del fondo) y varía unas décimas entre momentos del día, así que un nivel en XAU es una aproximación de unos pocos dólares.
  5. Solo se guarda histórico con snapshot del cierre de Nueva York y desde la ejecución de cierre.

MARCADOR «gamma oro»: ¿reaccionó el oro (medido en GLD, donde están los niveles) a ±0,25×EM del nivel en la sesión SIGUIENTE (T+1)?
  Zona = nivel ± 0,25 × EM. TOCADO si el rango [mínimo, máximo] de T+1 entra en la zona. Si se toca: RECHAZADO (cierra fuera de la zona del mismo lado por el que llegó, lado = apertura de T+1
  frente al nivel), ATRAVESADO (cierra fuera de la zona del lado contrario) o DENTRO (cierra dentro de la zona). Descriptivo: sin acierto/fallo ni cambios de umbral con n < 20."""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import csv
import statistics
import unicodedata

import fuentes
import gamma
import gamma_intradia as GI
import precios
import spot_oro as SO

UTC, MAD, NY = GI.UTC, GI.MAD, GI.NY
RAIZ = GI.RAIZ
P = GI.P
ETIQUETA = "GLD, referencia"
CFG = {"nombre": "Oro → GLD (referencia) → XAU/USD", "indice": "GLD", "cadenas": ["GLD"], "tramo": 1}
URL_XAU = "https://api.gold-api.com/price/XAU"
FACTOR_ZONA = 0.25
MIN_N = 20
DIAS_RATIO_MAX = 5
NIVELES = (("flip", "Gamma Flip", "flip"), ("call_wall", "Call Wall", "cw"), ("put_wall", "Put Wall", "pw"), ("max_gamma", "Max Gamma", "maxg"))
CAMPOS_RATIO = ["fecha", "gld_cierre", "xau_spot", "ratio", "xau_hora_utc", "fuente_xau", "medido_utc"]
CAMPOS_BASE = ["fecha", "xau_spot", "gc_precio", "base", "gc_barra_utc", "fuente", "medido_utc"]
CAMPOS_HIST = ["fecha_sesion", "gld_spot", "flip_gld", "call_wall_gld", "put_wall_gld", "max_gamma_gld", "em_gld", "ratio", "ratio_fecha", "flip_xau", "call_wall_xau", "put_wall_xau", "max_gamma_xau",
               "em_xau", "gex_neto_musd", "regimen", "ultima_operacion_et", "medido_utc"]
CAMPOS_RES = ["id", "fecha_sesion", "nivel", "nivel_gld", "em_gld", "zona_lo", "zona_hi", "fecha_t1", "o", "h", "l", "c", "tocado", "resultado", "evaluado_utc"]
PALABRAS_PROHIBIDAS = GI.PALABRAS_PROHIBIDAS


# ---------------------------------------------------------------- XAU spot y ratio
def xau_spot():
    """(precio, 'AAAA-MM-DD HH:MM', fuente) del oro al contado (gold-api.com, gratis, sin clave). Falla si no es reciente o está fuera de rango."""
    j = fuentes.json_(URL_XAU, tries=3, timeout=30)
    p = float(j["price"])
    t = dt.datetime.fromisoformat(str(j["updatedAt"]).replace("Z", "+00:00")).astimezone(UTC)
    if not 300 <= p <= 20000:
        raise ValueError(f"XAU fuera de rango: {p}")
    if (dt.datetime.now(UTC) - t).total_seconds() > 3 * 3600:
        raise ValueError("XAU/USD sin actualizar en más de 3 h")
    return p, t.strftime("%Y-%m-%d %H:%M"), "gold-api.com (XAU/USD al contado)"


def gld_cierre(sesion):
    barras, _ = precios.diario("GLD", "1mo")
    for b in barras:
        if b["fecha"] == sesion:
            return float(b["c"])
    raise RuntimeError(f"sin cierre de GLD de {sesion}")


def gc_en(hora_utc, rango="5d"):
    """(precio, 'AAAA-MM-DD HH:MM' UTC) de la barra de 5 min de GC=F (futuro del oro de COMEX) más cercana, sin pasarse, a `hora_utc` ('AAAA-MM-DD HH:MM')."""
    objetivo = dt.datetime.strptime(hora_utc, "%Y-%m-%d %H:%M").replace(tzinfo=UTC).timestamp()
    r = precios._yahoo("GC=F", rango, "5m")
    c = r["indicators"]["quote"][0]["close"]
    cand = [(t, v) for t, v in zip(r["timestamp"], c) if v is not None and t <= objetivo]
    if not cand or objetivo - cand[-1][0] > 5400:
        raise RuntimeError("sin barra de GC=F en los 90 min previos (el futuro del oro para de 21:00 a 22:00 UTC, y el spot sigue)")
    t, v = cand[-1]
    return float(v), dt.datetime.fromtimestamp(t, UTC).strftime("%Y-%m-%d %H:%M")


def fuentes_spot(fuentes_):
    """Funciones de spot para el contraste. Con fuentes inyectadas (pruebas) solo se usan las que se pasan: no se llama a la red por una fuente ausente."""
    f = fuentes_ or {}
    if fuentes_ is None:
        return {"principal": xau_spot, "gc": gc_en, "swiss": SO.swiss}
    return {"principal": f.get("xau"), "gc": f.get("gc"), "swiss": f.get("swiss")}


def anotar_base(raiz, sesion, fila_ratio, fuentes_=None, medido_utc=""):
    """Base del día del futuro GC = GC − XAU en el mismo momento que el ratio (solo añadir). None si falta algún dato o si el spot del día es el GC implícito (sería circular)."""
    f = fuentes_ or {}
    if str(fila_ratio.get("fuente_xau", "")).startswith("GC_IMPLICITO"):
        print("base GC sin anotar: el spot de hoy es el GC implícito")
        return None
    try:
        gc, barra = (f.get("gc") or gc_en)(fila_ratio["xau_hora_utc"])
    except Exception as e:  # noqa: BLE001
        print("base GC sin anotar:", type(e).__name__, str(e)[:100])
        return None
    fila = {"fecha": sesion, "xau_spot": fila_ratio["xau_spot"], "gc_precio": round(gc, 2), "base": round(gc - float(fila_ratio["xau_spot"]), 2), "gc_barra_utc": barra,
            "fuente": "GC=F (Yahoo, barra de 5 min) − XAU/USD al contado", "medido_utc": medido_utc}
    GI._anadir_csv(P(raiz, "data", "xau_gc_base.csv"), [fila], CAMPOS_BASE, lambda r: r["fecha"])
    return fila


def base_para(raiz, sesion):
    """Base GC − XAU de la sesión (o la última de hasta 5 días antes, avisándolo). None si no hay."""
    filas = sorted((r for r in GI._leer_csv(P(raiz, "data", "xau_gc_base.csv")) if r.get("base")), key=lambda r: r["fecha"])
    filas = [r for r in filas if r["fecha"] <= sesion]
    if not filas:
        return None
    r = filas[-1]
    dias = (dt.date.fromisoformat(sesion) - dt.date.fromisoformat(r["fecha"])).days
    if dias > DIAS_RATIO_MAX:
        return None
    b = float(r["base"])
    return {"base": b, "fut": float(r["gc_precio"]), "idx": float(r["xau_spot"]), "momento_et": None, "aproximada": r["fecha"] != sesion,
            "metodo": ("GC=F − XAU/USD al contado (última barra de 5 min de GC=F de Yahoo previa al spot, " + r["gc_barra_utc"] + " UTC)") + ("" if r["fecha"] == sesion else f" · APROXIMADA: base del {r['fecha']}"),
            "fuente": "Yahoo Finance (GC=F) y gold-api.com (XAU/USD)", "errores": []}


def leer_ratios(raiz=RAIZ):
    """Ratio de cada fecha. Si una fecha tiene varias filas manda la ÚLTIMA (una fila REVISADA corrige a la anterior sin borrarla)."""
    ult = {}
    for r in GI._leer_csv(P(raiz, "data", "xau_gld_ratio.csv")):
        if r.get("ratio"):
            ult[r["fecha"]] = r
    return sorted(ult.values(), key=lambda r: r["fecha"])


def _campos_ratio(raiz):
    """Cabecera real del CSV del ratio (puede tener la columna «estado» añadida por una revisión)."""
    ruta = P(raiz, "data", "xau_gld_ratio.csv")
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8", newline="") as f:
            cab = f.readline().strip().split(",")
        if cab and cab[0] == "fecha":
            return cab
    return CAMPOS_RATIO


def revisar_ratio(raiz, fecha, xau, xau_hora, fuente, gld_cierre, medido_utc=""):
    """Añade (solo añadir) una fila REVISADA con el ratio corregido de una fecha; la fila antigua queda. La columna «estado» se añade al final de la cabecera la primera vez
    (las filas antiguas no se tocan). Devuelve la fila o None si el ratio no cambia."""
    ruta = P(raiz, "data", "xau_gld_ratio.csv")
    viejo = next((r for r in reversed(GI._leer_csv(ruta)) if r["fecha"] == fecha and r.get("ratio")), None)
    nuevo = round(float(xau) / float(gld_cierre), 5)
    if viejo and abs(float(viejo["ratio"]) - nuevo) < 0.000005:
        return None
    cab = _campos_ratio(raiz)
    if "estado" not in cab:
        with open(ruta, "rb") as f:
            datos = f.read()
        i = datos.find(b"\n")
        fin = b"\r\n" if datos[i - 1:i] == b"\r" else b"\n"
        with open(ruta, "wb") as f:
            f.write(datos[:i].rstrip(b"\r") + b",estado" + fin + datos[i + 1:])
        cab = cab + ["estado"]
    fila = {"fecha": fecha, "gld_cierre": round(float(gld_cierre), 4), "xau_spot": round(float(xau), 2), "ratio": nuevo, "xau_hora_utc": xau_hora,
            "fuente_xau": fuente + (f" · antes {viejo['ratio']} con el spot de las {viejo['xau_hora_utc'][11:]} UTC" if viejo else ""), "medido_utc": medido_utc, "estado": "REVISADA"}
    with open(ruta, "a", encoding="utf-8", newline="") as f:
        csv.DictWriter(f, fieldnames=cab, extrasaction="ignore").writerow({c: fila.get(c, "") for c in cab})
    return fila


def ratio_para(raiz, sesion):
    """Ratio XAU/GLD de la sesión; si no hay, el último anotado de hasta 5 días antes (aproximado, con su fecha); si no, None."""
    filas = [r for r in leer_ratios(raiz) if r["fecha"] <= sesion]
    if not filas:
        return None
    r = filas[-1]
    dias = (dt.date.fromisoformat(sesion) - dt.date.fromisoformat(r["fecha"])).days
    if dias > DIAS_RATIO_MAX:
        return None
    return {"valor": float(r["ratio"]), "fecha": r["fecha"], "exacto": r["fecha"] == sesion, "gld_cierre": float(r["gld_cierre"]), "xau": float(r["xau_spot"]),
            "xau_hora_utc": r["xau_hora_utc"], "fuente_xau": r["fuente_xau"]}


def anotar_ratio(raiz, sesion, fuentes_=None, medido_utc="", ventana=None):
    """Anota (solo añadir) el ratio de la sesión. Devuelve la fila o None si falta algún cierre (sin inventar) o si el spot de hoy es DUDOSO (Fase 19: el ratio no se actualiza ese día).
    ventana (Fase 20, por defecto solo en producción): el spot es el de la hora del cierre del GLD (16:00 ET); si no se capturó entonces se reconstruye con el GC=F de esa hora."""
    ventana = (fuentes_ is None) if ventana is None else ventana
    try:
        g = ((fuentes_ or {}).get("gld_cierre") or gld_cierre)(dt.date.fromisoformat(sesion))
        fs = fuentes_spot(fuentes_)
        d = SO.decidir(raiz, sesion, fs["principal"], fs["gc"], fs["swiss"], medido_utc=medido_utc, ventana=ventana)
        if d is None:
            raise RuntimeError("sin spot del oro (principal caída y sin GC implícito)")
    except Exception as e:  # noqa: BLE001
        print("ratio XAU/GLD sin anotar:", type(e).__name__, str(e)[:100])
        return None
    if d["estado"] in ("DUDOSO", "SWISSQUOTE") or d.get("ratio_fuente") == "ANTERIOR":
        print(f"ratio XAU/GLD NO actualizado: spot {'dudoso' if d['estado'] == 'DUDOSO' else 'solo de Swissquote, último recurso' if d['estado'] == 'SWISSQUOTE' else 'fuera de la ventana del cierre del GLD'} ({SO.texto_fuentes(d)}); se usa el último ratio OK (ratio_fuente=ANTERIOR)")
        return None
    x, hora = float(d["spot_usado"]), d["hora_utc"] if d["spot_fuente"] == "GC_IMPLICITO" else d["principal_hora_utc"]
    fuente = ("gold-api.com (XAU/USD al contado)" if d["spot_fuente"] == "GOLD_API"
              else f"GC_IMPLICITO: GC=F {d['gc_precio']} − base {d['base_usada']} del {d['base_fecha']} (principal caída)")
    fila = {"fecha": sesion, "gld_cierre": round(float(g), 4), "xau_spot": round(x, 2), "ratio": round(x / float(g), 5), "xau_hora_utc": hora, "fuente_xau": fuente, "medido_utc": medido_utc}
    GI._anadir_csv(P(raiz, "data", "xau_gld_ratio.csv"), [fila], _campos_ratio(raiz), lambda r: r["fecha"])
    return fila


# ---------------------------------------------------------------- cálculo
def calcular(vol=None):
    M = gamma._calcular("GLD", CFG)
    M.pop("sesion_dt", None)
    M["em"] = gamma.calcular_em("GLD", M, vol)
    M["etiqueta"] = ETIQUETA
    return M


def convertir(M, r):
    """Añade los niveles en XAU. r = dict de ratio_para o None."""
    k = r["valor"] if r else None
    niv = []
    for clave, nombre, corto in NIVELES:
        x = M.get(clave)
        g = x["idx"] if x else None
        niv.append({"clave": clave, "corto": corto, "nombre": nombre, "gld": g, "xau": round(g * k, 1) if (g is not None and k) else None, "musd": (x or {}).get("musd")})
    em = (M.get("em") or {}).get("puntos")
    M["niveles"] = niv
    M["em_xau"] = round(em * k, 1) if (em and k) else None
    M["ratio"] = ({**r, "ratio_fuente": "SESION" if r["exacto"] else "ANTERIOR",
                   "nota": ("ratio de la sesión" if r["exacto"] else f"APROXIMADO: ratio del {r['fecha']} (no hay el de la sesión)")} if r else None)
    return M


# ---------------------------------------------------------------- marcador «gamma oro»
def reaccion(nivel, em, barra):
    """Resultado de T+1 frente a la zona nivel ± 0,25 × EM (en GLD). barra = {o,h,l,c}."""
    z = FACTOR_ZONA * em
    lo, hi = round(nivel - z, 4), round(nivel + z, 4)
    tocado = barra["l"] <= hi and barra["h"] >= lo
    if not tocado:
        return {"zona_lo": lo, "zona_hi": hi, "tocado": False, "resultado": "NO TOCADO"}
    llega_de_arriba = barra["o"] > nivel
    c = barra["c"]
    if lo <= c <= hi:
        res = "DENTRO"
    elif (c > hi) == llega_de_arriba:
        res = "RECHAZADO"
    else:
        res = "ATRAVESADO"
    return {"zona_lo": lo, "zona_hi": hi, "tocado": True, "resultado": res}


def evaluar(raiz=RAIZ, barras=None, ahora=None):
    """Evalúa cada sesión guardada contra la sesión SIGUIENTE (solo añadir). barras = [{fecha,o,h,l,c}] de GLD (inyectable)."""
    ahora = ahora or dt.datetime.now(UTC)
    hist = GI._leer_csv(P(raiz, "data", "historico_gamma_oro.csv"))
    if not hist:
        return 0
    if barras is None:
        barras, _ = precios.diario("GLD", "3mo")
    by = sorted(barras, key=lambda b: b["fecha"])
    nuevas = []
    for r in hist:
        d = dt.date.fromisoformat(r["fecha_sesion"])
        sig = next((b for b in by if b["fecha"] > d), None)
        try:
            em = float(r["em_gld"])
        except (TypeError, ValueError):
            continue
        if sig is None:
            continue
        for clave, nombre, corto in NIVELES:
            try:
                L = float(r[clave + "_gld"])
            except (TypeError, ValueError):
                continue
            x = reaccion(L, em, sig)
            nuevas.append({"id": f"go-{r['fecha_sesion']}-{corto}", "fecha_sesion": r["fecha_sesion"], "nivel": nombre, "nivel_gld": L, "em_gld": em, "zona_lo": x["zona_lo"], "zona_hi": x["zona_hi"],
                           "fecha_t1": sig["fecha"].isoformat(), "o": round(sig["o"], 2), "h": round(sig["h"], 2), "l": round(sig["l"], 2), "c": round(sig["c"], 2),
                           "tocado": "SI" if x["tocado"] else "NO", "resultado": x["resultado"], "evaluado_utc": ahora.strftime("%Y-%m-%d %H:%M UTC")})
    return len(GI._anadir_csv(P(raiz, "data", "gamma_oro_resultados.csv"), nuevas, CAMPOS_RES, lambda r: r["id"]))


def resumen_marcador(raiz=RAIZ):
    res = GI._leer_csv(P(raiz, "data", "gamma_oro_resultados.csv"))
    hist = GI._leer_csv(P(raiz, "data", "historico_gamma_oro.csv"))
    por = {}
    for clave, nombre, corto in NIVELES:
        rr = [x for x in res if x["nivel"] == nombre]
        tocados = [x for x in rr if x["tocado"] == "SI"]
        por[clave] = {"nivel": nombre, "evaluadas": len(rr), "tocadas": len(tocados),
                      "rechazadas": sum(1 for x in tocados if x["resultado"] == "RECHAZADO"), "atravesadas": sum(1 for x in tocados if x["resultado"] == "ATRAVESADO"),
                      "dentro": sum(1 for x in tocados if x["resultado"] == "DENTRO")}
    n = min((v["evaluadas"] for v in por.values()), default=0)
    return {"sesiones_guardadas": len(hist), "evaluadas": n, "min_n": MIN_N, "estado": "EVALUABLE" if n >= MIN_N else "CONGELADA", "por_nivel": por,
            "ultimas": [{k: x[k] for k in ("fecha_sesion", "nivel", "nivel_gld", "fecha_t1", "tocado", "resultado")} for x in res[-8:]][::-1],
            "criterio": f"Zona = nivel ± {FACTOR_ZONA}×EM (EM = GLD × GVZ / 100 / √252). TOCADO si el rango de la sesión siguiente entra en la zona; RECHAZADO / ATRAVESADO / DENTRO según dónde cierra. "
                        "Medido sobre GLD (donde están los niveles). Descriptivo: con n < 20 no se concluye nada ni se tocan los umbrales."}


# ---------------------------------------------------------------- etapa de build
def _guardar_historico(raiz, M, medido_utc):
    por = {x["corto"]: x for x in M["niveles"]}
    g = lambda c: "" if por[c]["gld"] is None else por[c]["gld"]  # noqa: E731
    x_ = lambda c: "" if por[c]["xau"] is None else por[c]["xau"]  # noqa: E731
    r = M.get("ratio") or {}
    fila = {"fecha_sesion": M["sesion"], "gld_spot": M.get("spot_gld", M["spot_idx"]), "flip_gld": g("flip"), "call_wall_gld": g("cw"), "put_wall_gld": g("pw"), "max_gamma_gld": g("maxg"),
            "em_gld": (M.get("em_gld") or {}).get("puntos") or "", "ratio": r.get("valor", ""), "ratio_fecha": r.get("fecha", ""),
            "flip_xau": x_("flip"), "call_wall_xau": x_("cw"), "put_wall_xau": x_("pw"), "max_gamma_xau": x_("maxg"), "em_xau": M.get("em_xau") or "",
            "gex_neto_musd": M["gex_neto_musd"], "regimen": M["regimen"], "ultima_operacion_et": M["ultima_operacion_et"], "medido_utc": medido_utc}
    return len(GI._anadir_csv(P(raiz, "data", "historico_gamma_oro.csv"), [fila], CAMPOS_HIST, lambda r: r["fecha_sesion"]))


def _a_contado(M, r, base):
    """Pasa M (unidades de GLD) a la forma de una entrada de gamma.json: idx = XAU/USD al contado, fut = futuro GC con la base del día. Sin ratio se queda en GLD (SIN DATO en XAU)."""
    M["spot_gld"], M["em_gld"] = M["spot_idx"], M["em"]
    M["nombre"] = "Oro (GLD, referencia) → XAU/USD y futuro GC"
    M["etiqueta"] = ETIQUETA
    if not r:
        M.update({"clave": "GC", "contado": "GLD", "futuro": None, "indice": "GLD", "unidad": "GLD", "spot_fut": None, "base": {"base": None, "metodo": "SIN DATO: sin ratio XAU/GLD, los niveles quedan en GLD", "fuente": "—"}})
        return M
    k = r["valor"]
    gamma.escalar(M, k, spot_cash=r["xau"])
    em = M["em_gld"]
    M["em"] = ({**em, "puntos": round(em["puntos"] * k, 1), "ref": round(r["xau"], 2), "unidad": "XAU/USD", "formula": "GLD × GVZ / 100 / √252 × ratio XAU/GLD"} if em.get("puntos") else em)
    if base:
        gamma._a_futuro(M, base)
    else:
        gamma._a_futuro(M, {"base": None, "metodo": "SIN DATO: no hay base GC − XAU de esa sesión", "fuente": "—"})
    M.update({"clave": "GC", "contado": "XAU", "futuro": "GC", "indice": "XAU", "unidad": "XAU"})
    return M


def etapa(escribir_cierre=False, hoy=None, stamp="", raiz=RAIZ, previo=None, fuentes_=None, ahora=None):
    """site/data/gamma_oro.json. `escribir_cierre` (solo la ejecución de cierre): anota el ratio, la base GC y el histórico de la sesión del día. Con snapshot intradía conserva el último cierre válido."""
    f = fuentes_ or {}
    M = f["calcular"]() if f.get("calcular") else calcular(f.get("vol"))
    if not M["cierre_confirmado"] and previo and previo.get("cierre_confirmado"):
        previo["descartado_intradia"] = {"snapshot_et": M["ultima_operacion_et"], "motivo": "snapshot intradía: se conserva el último cierre de Nueva York"}
        return previo
    escribe = bool(escribir_cierre and M["cierre_confirmado"] and M["sesion"] == (hoy or dt.datetime.now(UTC).strftime("%Y-%m-%d")))
    if escribe:
        fr = anotar_ratio(raiz, M["sesion"], fuentes_, stamp)
        if fr:
            anotar_base(raiz, M["sesion"], fr, fuentes_, stamp)
    r = ratio_para(raiz, M["sesion"])
    convertir(M, r)
    M["spot_contraste"] = SO.resumen_fila(SO.fila_de(raiz, M["sesion"]))      # Fase 19: contraste del spot de ESTA sesión (None si no se ha contrastado)
    M["spot_gld"] = M["spot_idx"]
    M["em_gld"] = M["em"]
    M["historico_escrito"] = False
    if escribe:
        _guardar_historico(raiz, M, stamp)
        M["historico_escrito"] = True
    barras = f.get("barras")
    if barras is None:
        try:
            barras, _ = precios.diario("GLD", "3mo")
        except Exception as e:  # noqa: BLE001
            M["error_evaluar"] = f"{type(e).__name__}: {str(e)[:100]}"
    try:
        if barras is not None:
            evaluar(raiz, barras, ahora)
    except Exception as e:  # noqa: BLE001
        M["error_evaluar"] = f"{type(e).__name__}: {str(e)[:100]}"
    M["marcador"] = resumen_marcador(raiz)
    hist = GI._leer_csv(P(raiz, "data", "historico_gamma_oro.csv"))
    filas = [{"fecha_sesion": h["fecha_sesion"], "indice": "ORO", "spot_fut": h["gld_spot"], "call_wall_fut": h["call_wall_gld"], "put_wall_fut": h["put_wall_gld"], "flip_fut": h["flip_gld"],
              "regimen": h["regimen"]} for h in hist]
    try:
        M["revision"] = gamma.revisar("ORO", filas, barras, roll=False) if barras is not None else {"sesiones": [], "resumen": {}, "sin_dato": True}
    except Exception as e:  # noqa: BLE001
        M["revision"] = {"sesiones": [], "resumen": {}, "sin_dato": True}
        M["error_revision"] = f"{type(e).__name__}: {str(e)[:100]}"
    M["revision_unidad"] = "GLD ($): los niveles se miden sobre el ETF, donde están"
    prev = gamma.prev_de_historico([{**h, "indice": "ORO"} for h in hist], "ORO", M["sesion"], "xau")
    _a_contado(M, r, base_para(raiz, M["sesion"]) if r else None)
    M["anterior"] = gamma.cambios(prev, M, "idx") if r else None
    M["sesiones_guardadas"] = len(hist)
    M["perfil"] = [{k: p[k] for k in ("k", "call", "put", "net", "fut") if k in p} for p in M["perfil"]]
    M["curva"] = M["curva"][::2]
    M["resumen_texto"] = texto(M)
    try:
        M["linea"] = linea_oro(raiz, ahora, M)      # la de la última actualización; el Telegram de las 15:00 la recompone con el evento del día
    except Exception as e:  # noqa: BLE001
        M["linea"] = None
        M["error_linea"] = f"{type(e).__name__}: {str(e)[:100]}"
    M["fuente"] = "Cboe · cadena de opciones de GLD con 15 min de retraso (cdn-api.cboe.com), GVZ y GLD de Yahoo Finance, XAU/USD de gold-api.com contrastado con GC=F − base y Swissquote (Fase 19)"
    M["metodo"] = re.sub(r"\n {2,}", " ", __doc__.split("Método (")[1].split("MARCADOR")[0]).strip()
    M["ok"] = True
    return M


def texto(M):
    n = {x["corto"]: x for x in M["niveles"]}
    f = lambda c: ("—" if n[c]["xau"] is None else f"{n[c]['xau']:,.0f}".replace(",", "."))  # noqa: E731
    r = M.get("ratio")
    base = f"GLD, referencia · Gamma Flip {f('flip')}, Call Wall {f('cw')}, Put Wall {f('pw')}, Max Gamma {f('maxg')} (XAU/USD) · gamma {'positiva' if M['regimen'] == 'POSITIVA' else 'negativa'}"
    return base + (f" · ratio XAU/GLD {r['valor']:.3f} del {r['fecha'][8:10]}-{r['fecha'][5:7]}" if r else " · SIN ratio XAU/GLD: niveles solo en GLD")


# ---------------------------------------------------------------- línea ORO para TradingView (15:00 Madrid)
def _slug(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def _tok(s):
    """Texto sin espacios ni «; = |» (con acentos conservados) para la línea que lee el indicador."""
    return re.sub(r"[^\w.+\-@]+", "_", str(s)).strip("_") or "na"


def _v(x, d=1):
    return "na" if x is None else f"{x:.{d}f}"


def _leer(raiz, *a):
    return GI._leer_json(P(raiz, *a))


def linea_oro(raiz=RAIZ, ahora=None, J=None):
    """«XAU tesis=…;int=…;flip=…;cw=…;pw=…;em=…;maxg=…;ratio=…;rf=…;cot=…;etf=…;evento=…» (punto decimal, sin espacios). Lo que falta va como na."""
    ahora = ahora or dt.datetime.now(UTC)
    J = J or _leer(raiz, "site", "data", "gamma_oro.json") or {}
    n = {x["corto"]: x for x in J.get("niveles") or []}
    R = _leer(raiz, "site", "data", "resumen.json") or {}
    O = (_leer(raiz, "site", "data", "oro.json") or {}).get("metricas") or {}
    et = (((R.get("tesis_activos") or {}).get("Oro")) or {}).get("etiqueta") or ""
    partes = _slug(et).split("_")
    if not et or "sin" in partes:
        tesis, inten = "sin_tesis", "na"
    else:
        tesis, inten = partes[0], (partes[1] if len(partes) > 1 else "na")
    raw = (O.get("cot") or {}).get("mm_etiqueta") or ""
    cot = _tok(re.sub(r"\s+", "-", re.sub(r",\s*percentil\s*", "_p", raw))) if raw and raw != "SIN DATO" else "na"      # «largo bajo, percentil 27» → largo-bajo_p27
    e5 = (O.get("etf") or {}).get("5d_t")
    etf = "na" if e5 is None else f"{e5:+.1f}"
    fecha_mad = ahora.astimezone(MAD).date()
    evs = [(e["t"], f"{_slug(e['evento'])[:36]}@{e['hora_madrid']}") for e in GI.eventos_alta(raiz, None) if e["t"].astimezone(MAD).date() == fecha_mad]
    A = (_leer(raiz, "site", "data", "agenda.json") or {}).get("agenda") or {}
    for e in (A.get("hoy") or []) + (A.get("proximos_7_dias") or []):       # ALTA del día sin hora publicada: se indica con @na (no se inventa la hora)
        if e.get("importancia") == "ALTA" and not e.get("hora_ny") and (e.get("fecha_et") or e.get("fecha")) == fecha_mad.isoformat():
            evs.append((dt.datetime.max.replace(tzinfo=UTC), f"{_slug(e.get('evento', ''))[:36]}@na"))
    evs.sort(key=lambda x: x[0])
    evento = "+".join(x[1] for x in evs[:2]) or "no"
    r = J.get("ratio") or {}
    return (f"XAU tesis={tesis};int={inten};flip={_v((n.get('flip') or {}).get('xau'))};cw={_v((n.get('cw') or {}).get('xau'))};pw={_v((n.get('pw') or {}).get('xau'))};"
            f"em={_v(J.get('em_xau'))};maxg={_v((n.get('maxg') or {}).get('xau'))};ratio={_v(r.get('valor'), 4)};rf={r.get('fecha') or 'na'};cot={cot};etf={etf};evento={evento}"
            + (";spot=dudoso" if (J.get("spot_contraste") or {}).get("estado") == "DUDOSO" else ""))


def mensaje_oro(raiz=RAIZ, ahora=None):
    """Bloque de texto (HTML de Telegram) con la línea ORO y su aviso de método. Cadena vacía si no hay gamma del oro."""
    import html
    J = _leer(raiz, "site", "data", "gamma_oro.json")
    if not J or not J.get("niveles"):
        return "ORO: gamma de GLD no disponible (SIN DATO)."
    r = J.get("ratio")
    nota = (f"ratio XAU/GLD {r['valor']:.3f} del {r['fecha'][8:10]}-{r['fecha'][5:7]}" + ("" if r.get("exacto") else " (APROXIMADO, no es el de la sesión)")) if r else "SIN ratio XAU/GLD: niveles solo en GLD"
    txt = (f"<code>{html.escape(linea_oro(raiz, ahora))}</code>\n"
           f"ORO · niveles de GLD, referencia (cadena de Cboe de la sesión {J['sesion'][8:10]}-{J['sesion'][5:7]}), pasados a precio XAU/USD: {nota}. "
           "EM = GLD × GVZ / 100 / √252. cot = posicionamiento del dinero gestionado en COMEX (lado, nivel frente a 3 años y percentil); etf = toneladas del trust GLD en 5 sesiones; "
           "evento = ALTA del día@hora de Madrid. CRITERIO NEXORA, no oficial.")
    assert not PALABRAS_PROHIBIDAS.search(txt), "palabra prohibida en el mensaje del oro"
    return txt


if __name__ == "__main__":
    M = etapa(escribir_cierre=False)
    print(M["resumen_texto"])
    print(json.dumps({k: M[k] for k in ("sesion", "spot_idx", "niveles", "em", "em_xau", "ratio", "regimen", "gex_neto_musd")}, ensure_ascii=False, indent=1))
