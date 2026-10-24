"""NEXORA · CONTRASTE DEL SPOT DEL ORO (Fase 19) — CRITERIO NEXORA.

Objetivo: que ningún dato derivado del spot XAU/USD (ratio XAU/GLD, base GC−XAU, niveles de la pestaña ORO, línea ORO) dependa de una sola fuente.

Fuentes (todas con su hora, y solo se comparan si son de la misma hora ±5 min; si no, NO_SINCRONIZADO):
  · PRINCIPAL  gold-api.com (XAU/USD al contado), la de siempre.
  · A          GC=F (futuro COMEX, barra de 5 min de Yahoo) − base GC−XAU de la sesión anterior (data/xau_gc_base.csv) = spot implícito.
  · B          Swissquote (feed público de cotizaciones de bróker, XAU/USD; bid/ask con marca de tiempo propia): se usa el punto medio. Stooq se descartó: su CSV está
               tras un desafío JavaScript anti-bot y no responde a un script.

Regla (umbral FIJO 0,3 %, no se ajusta):
  · Diferencia ≤ 0,3 % con las fuentes sincronizadas → OK, se usa la principal.
  · Diferencia > 0,3 % con alguna → DUDOSO (⚠️): el ratio XAU/GLD y la base GC−XAU de ese día NO se actualizan (se usa el último ratio OK, ratio_fuente=ANTERIOR) y la línea ORO añade ;spot=dudoso.
  · Si la principal falla → se usa el contraste A (spot_fuente=GC_IMPLICITO); en ese caso no se anota la base del día (sería circular).
  · Ninguna fuente de contraste utilizable → SIN_CONTRASTE (hay datos de contraste pero ninguno de la misma hora → NO_SINCRONIZADO): se usa la principal y se dice que no se pudo verificar.
Nota: el futuro GC para de 21:00 a 22:00 UTC, así que a las 21:30 UTC (cierre) el contraste A casi siempre sale NO_SINCRONIZADO y verifica B.

Registro de solo añadir: data/xau_spot_contraste.csv (una fila por sesión; la primera decisión del día manda, igual que el ratio y la base)."""
from __future__ import annotations

import datetime as dt
import json
import os
from zoneinfo import ZoneInfo

import fuentes

UTC = dt.timezone.utc
UMBRAL_PCT = 0.3
TOL_SINC_S = 300
DIAS_BASE_MAX = 5
URL_SWISS = "https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/XAU/USD"
CAMPOS = ["fecha", "hora_utc", "spot_principal", "principal_hora_utc", "gc_precio", "gc_barra_utc", "base_usada", "base_fecha", "spot_gc_implicito", "gc_sinc", "dif_gc_pct",
          "swiss_precio", "swiss_hora_utc", "swiss_sinc", "dif_swiss_pct", "estado", "spot_fuente", "spot_usado", "ratio_fuente", "nota", "medido_utc"]
ESTADOS = ("OK", "DUDOSO", "GC_IMPLICITO", "SWISSQUOTE", "NO_SINCRONIZADO", "SIN_CONTRASTE")
SESIONES_SWISS_CAIDO = 3                                       # Swissquote sin responder tantas sesiones seguidas → aviso (una vez por racha)


def P(raiz, *a):
    return os.path.join(raiz, *a)


def _leer_csv(ruta):
    import csv
    if not os.path.exists(ruta):
        return []
    with open(ruta, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _anadir(ruta, fila):
    import csv
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    existe = os.path.exists(ruta)
    with open(ruta, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS, extrasaction="ignore")
        if not existe:
            w.writeheader()
        w.writerow({c: fila.get(c, "") for c in CAMPOS})


def _t(s):
    return dt.datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=UTC)


def sincronizadas(h1, h2, tol=TOL_SINC_S):
    """¿Dos horas 'AAAA-MM-DD HH:MM' UTC distan como mucho tol segundos?"""
    return bool(h1 and h2) and abs((_t(h1) - _t(h2)).total_seconds()) <= tol


def dif_pct(x, ref):
    return round((x / ref - 1) * 100, 3)


# ---------------------------------------------------------------- fuentes
def swiss():
    """(precio medio, 'AAAA-MM-DD HH:MM' UTC, fuente) de XAU/USD en el feed público de Swissquote (perfil «prime»; si falta, el primero). Falla si está fuera de rango o sin actualizar en 3 h."""
    j = fuentes.json_(URL_SWISS, tries=3, timeout=30)
    cand = []
    for e in j:
        perf = {p["spreadProfile"]: p for p in e.get("spreadProfilePrices", []) if "bid" in p and "ask" in p}
        p = perf.get("prime") or next(iter(perf.values()), None)
        if p and e.get("ts"):
            cand.append((int(e["ts"]), (float(p["bid"]) + float(p["ask"])) / 2))
    if not cand:
        raise ValueError("Swissquote sin cotización de XAU/USD")
    ts, px = max(cand)
    t = dt.datetime.fromtimestamp(ts / 1000, UTC)
    if not 300 <= px <= 20000:
        raise ValueError(f"XAU fuera de rango: {px}")
    if (dt.datetime.now(UTC) - t).total_seconds() > 3 * 3600:
        raise ValueError("Swissquote XAU/USD sin actualizar en más de 3 h")
    return round(px, 2), t.strftime("%Y-%m-%d %H:%M"), "Swissquote (XAU/USD, punto medio bid/ask)"


def base_previa(raiz, sesion):
    """Última base GC−XAU ANTERIOR a la sesión (hasta 5 días antes): (base, fecha) o None."""
    filas = sorted((r for r in _leer_csv(P(raiz, "data", "xau_gc_base.csv")) if r.get("base") and r["fecha"] < sesion), key=lambda r: r["fecha"])
    if not filas:
        return None
    r = filas[-1]
    if (dt.date.fromisoformat(sesion) - dt.date.fromisoformat(r["fecha"])).days > DIAS_BASE_MAX:
        return None
    return float(r["base"]), r["fecha"]


# ---------------------------------------------------------------- contraste
def contrastar(raiz, sesion, principal=None, gc=None, swiss_fn=None, ahora=None, medido_utc=""):
    """Compara las fuentes y decide. principal/gc/swiss_fn son funciones (None = no disponible):
    principal() → (precio, hora, fuente) · gc(hora_utc) → (precio, hora_barra) · swiss_fn() → (precio, hora, fuente).
    Devuelve la fila del registro (dict) o None si no hay ningún spot utilizable (ni principal ni GC implícito)."""
    ahora = ahora or dt.datetime.now(UTC)
    nota = []
    pp = hp = None
    if principal:
        try:
            pp, hp, _ = principal()
            pp = float(pp)
        except Exception as e:  # noqa: BLE001
            pp = hp = None
            nota.append(f"principal caída: {type(e).__name__} {str(e)[:60]}")
    ref = hp or ahora.strftime("%Y-%m-%d %H:%M")
    # B
    sp = hs = None
    if swiss_fn:
        try:
            sp, hs, _ = swiss_fn()
            sp = float(sp)
        except Exception as e:  # noqa: BLE001
            sp = hs = None
            nota.append(f"Swissquote sin dato: {type(e).__name__} {str(e)[:60]}")
    # A
    base = base_previa(raiz, sesion)
    gp = hg = impl = None
    if gc and base:
        try:
            gp, hg = gc(ref)
            gp = float(gp)
            impl = round(gp - base[0], 2)
        except Exception as e:  # noqa: BLE001
            gp = hg = impl = None
            nota.append(f"GC=F sin barra: {type(e).__name__} {str(e)[:60]}")
    elif gc and not base:
        nota.append("sin base GC−XAU de la sesión anterior (≤ 5 días)")
    fila = {"fecha": sesion, "hora_utc": ref, "spot_principal": "" if pp is None else round(pp, 2), "principal_hora_utc": hp or "", "gc_precio": "" if gp is None else round(gp, 2),
            "gc_barra_utc": hg or "", "base_usada": "" if not base else base[0], "base_fecha": "" if not base else base[1], "spot_gc_implicito": "" if impl is None else impl,
            "swiss_precio": "" if sp is None else sp, "swiss_hora_utc": hs or "", "medido_utc": medido_utc}
    if pp is None:                                              # principal caída → contraste A (GC implícito)
        if impl is None:
            if sp is None:
                return None
            # último recurso: ni principal ni GC implícito → Swissquote, para tener niveles ORO; el ratio y la base NO se actualizan (se usan los últimos OK)
            nota.append("último recurso: spot = Swissquote; ratio y base sin actualizar")
            fila.update({"spot_fuente": "SWISSQUOTE", "spot_usado": sp, "hora_utc": hs, "ratio_fuente": "ANTERIOR", "estado": "SWISSQUOTE", "nota": " · ".join(nota)})
            return fila
        usado, hora = impl, hg
        fila.update({"spot_fuente": "GC_IMPLICITO", "spot_usado": usado, "hora_utc": hora, "ratio_fuente": "SESION"})
        estado = "GC_IMPLICITO"
        nota.append(f"spot = GC=F {gp} − base {base[0]} del {base[1]}; la hora es la de la barra de GC=F (el futuro no es el spot)")
        if sp is not None and sincronizadas(hg, hs):
            fila.update({"swiss_sinc": "SI", "dif_swiss_pct": dif_pct(sp, usado)})
            if abs(fila["dif_swiss_pct"]) > UMBRAL_PCT:
                estado = "DUDOSO"
                fila["ratio_fuente"] = "ANTERIOR"
        elif sp is not None:
            fila["swiss_sinc"] = "NO"
        fila.update({"estado": estado, "nota": " · ".join(nota)})
        return fila
    fila.update({"spot_fuente": "GOLD_API", "spot_usado": round(pp, 2), "ratio_fuente": "SESION"})
    comp = []                                                   # (sincronizada, dif)
    if impl is not None:
        ok = sincronizadas(hp, hg)
        fila["gc_sinc"] = "SI" if ok else "NO"
        if ok:
            fila["dif_gc_pct"] = dif_pct(impl, pp)
        else:
            nota.append(f"GC=F de las {hg} frente a la principal de las {hp}: más de {TOL_SINC_S // 60} min")
        comp.append((ok, fila.get("dif_gc_pct")))
    if sp is not None:
        ok = sincronizadas(hp, hs)
        fila["swiss_sinc"] = "SI" if ok else "NO"
        if ok:
            fila["dif_swiss_pct"] = dif_pct(sp, pp)
        else:
            nota.append(f"Swissquote de las {hs} frente a la principal de las {hp}: más de {TOL_SINC_S // 60} min")
        comp.append((ok, fila.get("dif_swiss_pct")))
    sinc = [d for ok, d in comp if ok]
    if any(abs(d) > UMBRAL_PCT for d in sinc):
        estado = "DUDOSO"
        fila["ratio_fuente"] = "ANTERIOR"
    elif sinc:
        estado = "OK"
    elif comp:
        estado = "NO_SINCRONIZADO"
    else:
        estado = "SIN_CONTRASTE"
    fila.update({"estado": estado, "nota": " · ".join(nota)})
    return fila


def fila_de(raiz, sesion):
    filas = [r for r in _leer_csv(P(raiz, "data", "xau_spot_contraste.csv")) if r["fecha"] == sesion]
    return filas[-1] if filas else None


# ---------------------------------------------------------------- hora del cierre del GLD (Fase 20)
# El ratio XAU/GLD = spot del oro / cierre de GLD, así que el spot debe ser el de la hora del cierre de GLD: 16:00 hora de Nueva York (America/New_York: 20:00 UTC con horario
# de verano de EE. UU., 21:00 UTC sin él; el cambio de 2026 es el 1-nov). Cierres anticipados de la NYSE (13:00 ET) conocidos; el resto de festivos no tiene sesión.
NY = ZoneInfo("America/New_York")
VENTANA_S = 300
CIERRES_ANTICIPADOS = {"2026-11-27": (13, 0), "2026-12-24": (13, 0)}


def cierre_gld_utc(sesion):
    """Instante (UTC) del cierre de GLD de la sesión 'AAAA-MM-DD'."""
    h, m = CIERRES_ANTICIPADOS.get(sesion, (16, 0))
    d = dt.date.fromisoformat(sesion)
    return dt.datetime(d.year, d.month, d.day, h, m, tzinfo=NY).astimezone(UTC)


def en_ventana(instante, sesion):
    return abs((instante - cierre_gld_utc(sesion)).total_seconds()) <= VENTANA_S


def _con_marca(f, marca):
    f["nota"] = marca + (" · " + f["nota"] if f.get("nota") else "")
    return f


def reconstruir_en_cierre(raiz, sesion, principal, gc, swiss_fn, ahora, medido_utc=""):
    """No hubo captura en la ventana del cierre del GLD: el spot de esa hora se reconstruye con el GC=F de entonces (barra de 5 min, el futuro sigue abierto) menos la base de la sesión
    anterior (GC_IMPLICITO, sin verificar). Sin barra o sin base: contraste de «ahora» marcado y con el ratio SIN actualizar. Nunca se usa el spot de otra hora para el ratio."""
    cierre = cierre_gld_utc(sesion)
    hora_c = cierre.strftime("%Y-%m-%d %H:%M")
    base = base_previa(raiz, sesion)
    if gc and base:
        try:
            gp, hg = gc(hora_c)
            if abs((_t(hg) - cierre).total_seconds()) <= 2 * VENTANA_S:
                impl = round(float(gp) - base[0], 2)
                return {"fecha": sesion, "hora_utc": hg, "spot_principal": "", "principal_hora_utc": "", "gc_precio": round(float(gp), 2), "gc_barra_utc": hg, "base_usada": base[0], "base_fecha": base[1],
                        "spot_gc_implicito": impl, "swiss_precio": "", "swiss_hora_utc": "", "spot_fuente": "GC_IMPLICITO", "spot_usado": impl, "ratio_fuente": "SESION", "estado": "GC_IMPLICITO",
                        "nota": f"FUERA_DE_VENTANA: no se capturó el spot a la hora del cierre del GLD ({hora_c} UTC); spot = GC=F de las {hg} − base {base[0]} del {base[1]}, sin verificar",
                        "medido_utc": medido_utc}
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__} {str(e)[:60]}"
        else:
            err = "barra de GC=F lejos de la hora del cierre"
    else:
        err = "sin GC=F o sin base de la sesión anterior"
    f = contrastar(raiz, sesion, principal, gc, swiss_fn, ahora, medido_utc)
    if f:
        f["ratio_fuente"] = "ANTERIOR"
        _con_marca(f, f"FUERA_DE_VENTANA: no se capturó el spot a la hora del cierre del GLD ({hora_c} UTC) y no se pudo reconstruir ({err}); ratio y base sin actualizar")
    return f


def decidir(raiz, sesion, principal=None, gc=None, swiss_fn=None, ahora=None, medido_utc="", escribir=True, ventana=False):
    """La decisión del día: si ya hay fila de esa sesión manda la primera (solo añadir); si no, contrasta y, con escribir=True, la registra. None si no hay spot.
    ventana=True (producción): el spot debe ser el de la hora del cierre del GLD (±5 min); fuera de ella se reconstruye con GC=F (ver reconstruir_en_cierre)."""
    ex = fila_de(raiz, sesion)
    if ex:
        return ex
    ahora = ahora or dt.datetime.now(UTC)
    if ventana and not en_ventana(ahora, sesion):
        f = reconstruir_en_cierre(raiz, sesion, principal, gc, swiss_fn, ahora, medido_utc)
    else:
        f = contrastar(raiz, sesion, principal, gc, swiss_fn, ahora, medido_utc)
        if f and ventana:
            _con_marca(f, f"VENTANA_GLD: captura a las {ahora.strftime('%H:%M')} UTC, dentro de ±{VENTANA_S // 60} min del cierre del GLD ({cierre_gld_utc(sesion).strftime('%H:%M')} UTC)")
    if f and escribir:
        _anadir(P(raiz, "data", "xau_spot_contraste.csv"), f)
    return f


def capturar(raiz=None, ahora=None, fuentes_=None, stamp=""):
    """Captura del spot a la hora del cierre del GLD, para llamarla cada pocos minutos (reacciones.yml): solo actúa en días de semana y dentro de ±5 min de ese cierre, y solo si el día aún no
    tiene fila (la primera captura válida manda). La hora del spot (la de la principal) también debe estar en la ventana. Devuelve un texto de estado."""
    import gamma_oro as GO
    raiz = raiz or GO.RAIZ
    ahora = ahora or dt.datetime.now(UTC)
    sesion = ahora.astimezone(NY).date().isoformat()
    if dt.date.fromisoformat(sesion).weekday() >= 5:
        return "FIN_DE_SEMANA"
    if not en_ventana(ahora, sesion):
        return "FUERA_DE_VENTANA"
    if fila_de(raiz, sesion):
        return "YA_REGISTRADA"
    fn = GO.fuentes_spot(fuentes_)
    f = contrastar(raiz, sesion, fn["principal"], fn["gc"], fn["swiss"], ahora, stamp)
    if not f or not f.get("principal_hora_utc") or not en_ventana(_t(f["principal_hora_utc"]), sesion):
        return "SIN_PRINCIPAL_EN_VENTANA"          # no se registra: otra ejecución dentro de la ventana puede conseguirlo; si no, el cierre reconstruye
    _con_marca(f, f"VENTANA_GLD: captura a las {ahora.strftime('%H:%M')} UTC, dentro de ±{VENTANA_S // 60} min del cierre del GLD ({cierre_gld_utc(sesion).strftime('%H:%M')} UTC)")
    _anadir(P(raiz, "data", "xau_spot_contraste.csv"), f)
    return f"REGISTRADA {f['estado']}"


# ---------------------------------------------------------------- lectura para la web, la línea y el aviso
def filas(raiz):
    return sorted(_leer_csv(P(raiz, "data", "xau_spot_contraste.csv")), key=lambda r: r["fecha"])


def racha_dudoso(raiz):
    """Sesiones DUDOSO consecutivas hasta la última registrada: (n, fecha de inicio de la racha)."""
    n, ini = 0, None
    for r in reversed(filas(raiz)):
        if r["estado"] != "DUDOSO":
            break
        n, ini = n + 1, r["fecha"]
    return n, ini


def racha_swiss_caido(raiz):
    """Sesiones consecutivas, hasta la última registrada, en las que Swissquote no respondió: (n, fecha de inicio de la racha)."""
    n, ini = 0, None
    for r in reversed(filas(raiz)):
        if dt.date.fromisoformat(r["fecha"][:10]).weekday() >= 5:       # el cierre tardío (00:01 UTC) deja filas en sábado/domingo con el mercado cerrado: no son sesiones y no alargan ni cortan la racha
            continue
        if r.get("swiss_precio") != "":
            break
        n, ini = n + 1, r["fecha"]
    return n, ini


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def texto_fuentes(r):
    """Las fuentes de una fila, para el ⓘ y la tarjeta de integridad."""
    if not r:
        return "SIN DATO: todavía no hay contraste registrado."
    e = []
    if r.get("spot_principal") != "":
        e.append(f"gold-api {r['spot_principal']} ({r['principal_hora_utc'][11:]} UTC)")
    else:
        e.append("gold-api CAÍDA")
    if r.get("spot_gc_implicito") != "":
        e.append(f"GC=F {r['gc_precio']} − base {r['base_usada']} = {r['spot_gc_implicito']} implícito ({r['gc_barra_utc'][11:]} UTC; " + (f"dif {r['dif_gc_pct']} %" if r.get("dif_gc_pct") not in ("", None) else "informativo (retraso ~10 min)") + ")")
    else:
        e.append("GC implícito: sin dato")
    if r.get("swiss_precio") != "":
        e.append(f"Swissquote {r['swiss_precio']} ({r['swiss_hora_utc'][11:]} UTC; " + (f"dif {r['dif_swiss_pct']} %" if r.get("dif_swiss_pct") not in ("", None) else "NO SINCRONIZADO") + ")")
    else:
        e.append("Swissquote: sin dato")
    return " · ".join(e)


def resumen_fila(r):
    if not r:
        return None
    return {**{k: r.get(k, "") for k in CAMPOS}, "texto_fuentes": texto_fuentes(r), "verificado": r["estado"] == "OK", "dudoso": r["estado"] == "DUDOSO",
            "umbral_pct": UMBRAL_PCT}


def resumen(raiz):
    """Para integridad.json: último contraste, racha de ⚠️, historial."""
    fs = filas(raiz)
    n, ini = racha_dudoso(raiz)
    ns, inis = racha_swiss_caido(raiz)
    return {"ultimo": resumen_fila(fs[-1]) if fs else None, "racha_dudoso": n, "racha_desde": ini, "racha_swiss_caido": ns, "racha_swiss_desde": inis,
            "sesiones_swiss_aviso": SESIONES_SWISS_CAIDO, "sesiones_registradas": len(fs),
            "historial": [{k: r.get(k, "") for k in ("fecha", "hora_utc", "spot_principal", "spot_gc_implicito", "swiss_precio", "dif_gc_pct", "dif_swiss_pct", "estado", "spot_fuente", "ratio_fuente")}
                          for r in reversed(fs[-10:])],
            "regla": f"OK si la diferencia entre fuentes de la misma hora (±{TOL_SINC_S // 60} min) es ≤ {str(UMBRAL_PCT).replace('.', ',')} %; DUDOSO si la supera (el ratio no se actualiza); "
                     "GC_IMPLICITO si la principal cae (SWISSQUOTE si tampoco hay GC: último recurso, ratio y base sin actualizar); NO_SINCRONIZADO si las fuentes no son de la misma hora. "
                     "El GC=F es informativo (Yahoo lo da con ≈ 10 min de retraso) y respaldo si cae la principal.",
            "fuente": "data/xau_spot_contraste.csv · engine/spot_oro.py (gold-api, GC=F − base, Swissquote)"}


def mensaje_racha(n, ini, r):
    return (f"<b>NEXORA · Spot del oro</b>\nEl contraste del spot del oro lleva {n} sesiones seguidas en ⚠️ (desde {ini}). El ratio XAU/GLD y la base GC−XAU no se actualizan mientras dure. "
            f"Último contraste ({r['fecha']}): {texto_fuentes(r)}. Revisa gold-api.com y el feed de Swissquote.")


def mensaje_swiss_caido(n, ini):
    return (f"<b>NEXORA · Spot del oro</b>\nSwissquote, la segunda fuente del spot del oro, lleva {n} sesiones seguidas sin responder (desde {ini}). "
            "Mientras dure, el spot depende solo de gold-api (y del GC=F, que es informativo). Revisa el feed público de Swissquote.")


# ---------------------------------------------------------------- etapa de build
def etapa(escribir_cierre=False, hoy=None, stamp="", raiz=None, fuentes_=None, ahora=None):
    """site/data/spot_oro.json. Solo la ejecución de cierre registra la decisión del día; las demás muestran un contraste en vivo sin escribir."""
    import gamma_oro as GO
    raiz = raiz or GO.RAIZ
    ahora = ahora or dt.datetime.now(UTC)
    hoy = hoy or ahora.strftime("%Y-%m-%d")
    f = fuentes_
    fn = GO.fuentes_spot(f)
    dec = decidir(raiz, hoy, fn["principal"], fn["gc"], fn["swiss"], ahora, stamp, escribir=escribir_cierre, ventana=fuentes_ is None)
    R = resumen(raiz)
    out = {"generado_utc": ahora.strftime("%Y-%m-%d %H:%M UTC"), "sesion": hoy, "registra": bool(escribir_cierre),
           "decision": resumen_fila(dec), "resumen": R, "umbral_pct": UMBRAL_PCT, "tolerancia_min": TOL_SINC_S // 60, "metodo": __doc__.split("Fuentes (")[1].split("Registro de solo")[0].strip()}
    if dec is None:
        raise RuntimeError("sin spot del oro: la fuente principal falló y no hay contraste A (GC=F − base) utilizable")
    return out


if __name__ == "__main__":
    import sys
    if "--capturar" in sys.argv:
        print("captura del spot a la hora del cierre del GLD:", capturar(stamp=dt.datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")))
    else:
        print(json.dumps(etapa(escribir_cierre=False), ensure_ascii=False, indent=1))
