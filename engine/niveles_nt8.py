#!/usr/bin/env python3
"""NEXORA · NIVELES PARA NINJATRADER 8 (Fase 21): site/data/niveles_nt8.json.

Un JSON público, pequeño y sin datos personales ni claves, con los niveles de gamma en precio de FUTURO de GC, ES, NQ y YM (y de sus micros MGC, MES, MNQ y MYM, con los mismos
niveles) para que el indicador «NexoraNiveles» de NinjaTrader 8 los descargue solo. TradingView no puede descargar datos externos; NinjaTrader 8 sí.

Lo genera el cierre (etapa `niveles_nt8`, justo después de `gamma_us30`, con el resto del bloque de gamma) y el build diario; no recalcula nada: reempaqueta lo que ya publican
gamma.json (ES, NQ), gamma_us30.json (YM) y gamma_oro.json (GC). Si una fuente falla se conserva su última sesión y el indicador lo muestra como CADUCADO (no se inventa nada).

Campos por instrumento: sesion (la de la cadena de opciones de la que salen los niveles; en el oro, la del ratio XAU/GLD «rf»), regimen, flip, call_wall, put_wall, max_gamma,
max_gamma_tipo (pin | acelera), em (movimiento esperado de un día, en puntos), spot_estado y generado_utc (cuándo se calcularon esos niveles).

spot_estado:
  · GC: el contraste del spot del oro de la Fase 19/20 → «verificado» (≤ 0,3 % con una fuente de la misma hora), «dudoso» (> 0,3 %: el ratio de ese día no se actualizó) o
    «no_verificado» (sin contraste sincronizado).
  · ES, NQ, YM: «verificado» si la base futuro − índice se midió en el mismo minuto (no aproximada); «no_verificado» en otro caso. No hay contraste de spot para los índices, así que
    «dudoso» no aparece nunca en ellos.
"""
from __future__ import annotations

ESTADOS_SPOT = ("verificado", "dudoso", "no_verificado")
# (instrumento, archivo de origen, clave dentro de «indices» o None, micros que usan los mismos niveles)
INSTRUMENTOS = (("GC", "gamma_oro", None, ("MGC",)),
                ("ES", "gamma", "ES", ("MES",)),
                ("NQ", "gamma", "NQ", ("MNQ",)),
                ("YM", "gamma_us30", None, ("MYM",)))


def _num(x, d=1):
    return round(float(x), d) if isinstance(x, (int, float)) and not isinstance(x, bool) and x == x else None


def _fut(x, clave):
    return _num(((x or {}).get(clave) or {}).get("fut"))


def spot_estado_oro(x):
    """Estado del spot del oro de la sesión de los niveles (el contraste que guarda gamma_oro.json)."""
    c = (x or {}).get("spot_contraste") or {}
    if c.get("dudoso") is True:
        return "dudoso"
    return "verificado" if c.get("verificado") is True else "no_verificado"


def spot_estado_indice(x):
    base = (x or {}).get("base") or {}
    return "verificado" if base.get("base") is not None and base.get("aproximada") is False else "no_verificado"


def instrumento(x, es_oro, generado_utc):
    """Niveles de un instrumento desde su bloque de gamma. None si falta el Gamma Flip (sin él no hay régimen utilizable)."""
    if not x or _fut(x, "flip") is None:
        return None
    mg = x.get("max_gamma") or {}
    tipo = mg.get("tipo") if mg.get("tipo") in ("pin", "acelera") else None
    return {"sesion": x.get("sesion"), "regimen": x.get("regimen"), "flip": _fut(x, "flip"), "call_wall": _fut(x, "call_wall"), "put_wall": _fut(x, "put_wall"),
            "max_gamma": _fut(x, "max_gamma"), "max_gamma_tipo": tipo, "em": _num((x.get("em") or {}).get("puntos")),
            "spot_estado": spot_estado_oro(x) if es_oro else spot_estado_indice(x), "generado_utc": generado_utc}


def construir(fuentes):
    """fuentes = {"gamma": gamma.json, "gamma_us30": …, "gamma_oro": …} (los que falten van como None). Devuelve el contenido del JSON (sin ok/generado_utc, que añade el build)."""
    inst, errores = {}, {}
    for nombre, archivo, clave, micros in INSTRUMENTOS:
        J = fuentes.get(archivo) or {}
        x = ((J.get("indices") or {}).get(clave)) if clave else J
        n = instrumento(x, nombre == "GC", J.get("generado_utc"))
        if n is None:
            errores[nombre] = f"{archivo}.json sin niveles utilizables (SIN DATO)"
            continue
        inst[nombre] = n
        for m in micros:
            inst[m] = dict(n, alias_de=nombre)
    if not inst:
        raise RuntimeError("ninguna fuente de gamma con niveles: " + "; ".join(errores.values()))
    return {"version": 1, "unidad": "puntos de precio del contrato de futuro (GC, ES, NQ, YM; los micros usan los mismos niveles)", "instrumentos": inst, "errores": errores,
            "fuente": "NEXORA (CRITERIO NEXORA, método propio) con la cadena de opciones de Cboe (15 min de retraso) de la sesión indicada; GC, YM y el EM del oro son de ETF de referencia (GLD, DIA)",
            "aviso": "Contexto de mercado, no una entrada. Si «sesion» no es la última sesión de mercado, los niveles están caducados."}


def etapa(leer):
    """Etapa del build: lee los tres JSON ya publicados con `leer(nombre_de_archivo)` (build.leer)."""
    return construir({"gamma": leer("gamma.json"), "gamma_us30": leer("gamma_us30.json"), "gamma_oro": leer("gamma_oro.json")})


if __name__ == "__main__":
    import json
    import os
    import sys
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _leer(n):
        try:
            return json.load(open(os.path.join(raiz, "site", "data", n), encoding="utf-8"))
        except (OSError, ValueError):
            return None
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(etapa(_leer), ensure_ascii=False, indent=1))
