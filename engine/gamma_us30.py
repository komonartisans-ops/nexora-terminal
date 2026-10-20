"""NEXORA · GAMMA DE US30 (Dow Jones) — CRITERIO NEXORA (método propio; NO es un dato oficial de ningún proveedor).

No hay cadena de opciones de DJI con acceso gratuito. La referencia es el ETF DIA (SPDR Dow Jones) en la cadena con 15 min de retraso de Cboe, por eso se etiqueta siempre «DIA, referencia».
Método (el mismo que SPX/NDX en gamma.py, con una sola cadena): GEX$ = gamma × OI × 100 × S² × 1 %, calls +, puts − (hipótesis), tramos de 1 $ de DIA, Call/Put Wall, Gamma Flip (barrido ±12 %),
Max Gamma (tramo con más gamma absoluta; «pin» si su gamma neta es positiva, «acelera» si es negativa) y EM = precio × VXD / 100 / √252 (VXD = volatilidad implícita del Dow de Cboe).
Conversión: nivel DJI = nivel DIA × (cierre de DJI / cierre de DIA de la misma sesión, ambos a las 16:00 ET); nivel YM = nivel DJI + base del día (YM − DJI en el mismo minuto, barras de 5 min de Yahoo).
Sin datos suficientes (menos de 200 grupos de opciones válidos, sin cierre de DJI o de DIA) → SIN DATO: no se inventa nada.
Histórico: data/historico_gamma.csv con indice «YM» (solo el cierre de Nueva York, ejecución de cierre); su revisión a T+1 es la misma que la de ES/NQ, sobre la barra del futuro YM=F."""
from __future__ import annotations

import datetime as dt
import re

import csvlog
import gamma
import precios

CFG = {"nombre": "Dow Jones (DIA, referencia) → futuro YM", "indice": "DJI", "cadenas": ["DIA"], "tramo": 1}
ETIQUETA = "DIA, referencia"
MIN_GRUPOS = 200


def _cierre(sym, sesion):
    barras, _ = precios.diario(sym, "1mo")
    for b in barras:
        if b["fecha"] == sesion:
            return float(b["c"])
    raise RuntimeError(f"sin cierre de {sym} de {sesion}")


def medir(f=None):
    """Entrada de US30 con la misma forma que una de gamma.json (idx = DJI, fut = YM). Lanza si no hay datos suficientes."""
    f = f or {}
    M = gamma._calcular("DIA", CFG)
    sesion = M.pop("sesion_dt")
    if M["n_grupos"] < MIN_GRUPOS:
        raise RuntimeError(f"solo {M['n_grupos']} grupos válidos de opciones de DIA")
    dji = (f.get("cierre") or _cierre)("^DJI", sesion)
    dia = (f.get("cierre") or _cierre)("DIA", sesion)
    k = dji / dia
    gamma.escalar(M, k, spot_cash=dji)
    base = (f.get("base") or gamma._base_futuro)("YM=F", "^DJI", sesion)
    gamma._a_futuro(M, base)
    M.update({"clave": "YM", "contado": "DJI", "futuro": "YM", "nombre": CFG["nombre"], "etiqueta": ETIQUETA, "indice": "DJI"})
    M["em"] = gamma.calcular_em("DIA", M, f.get("vol"))
    M["resumen_texto"] = gamma._texto(M)
    return M


def sin_dato(motivo):
    return {"ok": False, "sin_dato": True, "clave": "YM", "contado": "DJI", "futuro": "YM", "etiqueta": ETIQUETA, "nombre": CFG["nombre"],
            "motivo": f"SIN DATO: {motivo}. No se inventa ningún nivel.", "fuente": "Cboe · cadena de opciones de DIA (cdn-api.cboe.com)"}


def etapa(escribir_cierre=False, hoy=None, stamp="", previo=None, f=None, hist=None, barras=None):
    """site/data/gamma_us30.json. Conserva el último cierre válido si la descarga es intradía; el histórico solo lo escribe el cierre del día."""
    f = f or {}
    try:
        M = medir(f)
    except Exception as e:  # noqa: BLE001
        if previo and previo.get("cierre_confirmado"):
            previo["error_ultimo"] = f"{type(e).__name__}: {str(e)[:100]}"
            return previo
        return sin_dato(f"{type(e).__name__}: {str(e)[:100]}")
    if not M["cierre_confirmado"] and previo and previo.get("cierre_confirmado"):
        previo["descartado_intradia"] = {"snapshot_et": M["ultima_operacion_et"], "motivo": "snapshot intradía: se conserva el último cierre de Nueva York"}
        return previo
    escribe = bool(escribir_cierre and M["cierre_confirmado"] and M["sesion"] == (hoy or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")))
    if escribe:
        gamma.guardar_historico({"indices": {"YM": M}}, stamp)
    M["historico_escrito"] = escribe
    hist = csvlog.leer("historico_gamma.csv") if hist is None else hist
    try:
        bars = barras if barras is not None else precios.diario("YM=F", "3mo")[0]
        M["revision"] = gamma.revisar("YM", hist, bars)
    except Exception as e:  # noqa: BLE001
        M["revision"] = {"sesiones": [], "resumen": {}, "sin_dato": True}
        M["error_revision"] = f"{type(e).__name__}: {str(e)[:100]}"
    M["anterior"] = gamma.cambios(gamma.prev_de_historico(hist, "YM", M["sesion"]), M)
    M["sesiones_guardadas"] = len({r["fecha_sesion"] for r in hist if r.get("indice") == "YM"})
    M["fuente"] = "Cboe · cadena de opciones de DIA con 15 min de retraso (cdn-api.cboe.com), DJI, DIA, YM=F y VXD de Yahoo Finance"
    M["metodo"] = re.sub(r"\s*\n\s*", " ", __doc__.split("Método")[1]).strip()
    M["ok"] = True
    return M


if __name__ == "__main__":
    M = etapa()
    print(M.get("resumen_texto") or M["motivo"])
