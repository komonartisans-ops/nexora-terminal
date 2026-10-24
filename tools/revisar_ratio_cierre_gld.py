#!/usr/bin/env python3
"""NEXORA · corrige hacia atrás el ratio XAU/GLD de los días en que el spot no era el de la hora del cierre del GLD (Fase 20). SOLO AÑADE filas REVISADA a data/xau_gld_ratio.csv
(no borra ni edita ninguna fila; las lecturas usan la última fila de cada fecha).

Antes el ratio usaba el spot de las ~21:30 UTC; el cierre del GLD es a las 16:00 de Nueva York (20:00 UTC en verano, 21:00 UTC en invierno). Para cada día con spot de gold-api se estima
el spot de la hora del cierre con el GC=F de entonces (barra de 5 min de Yahoo, el futuro sigue abierto) menos la base GC−XAU anotada ese día, y se recalcula el ratio con el cierre del GLD.
Si el ratio cambia, se añade la fila REVISADA (fuente y valor anterior en `fuente_xau`).

Uso: python tools/revisar_ratio_cierre_gld.py            (solo muestra qué cambiaría)
     python tools/revisar_ratio_cierre_gld.py --aplicar  (añade las filas REVISADA)"""
from __future__ import annotations

import datetime as dt
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(RAIZ, "engine"))
import gamma_intradia as GI  # noqa: E402
import gamma_oro as GO  # noqa: E402
import spot_oro as SO  # noqa: E402

UTC = dt.timezone.utc
TOL_BARRA_S = 600


def revisar(raiz=RAIZ, aplicar=False, gc_fn=None, medido=""):
    """Devuelve la lista de resultados por fecha: dicts con fecha, antes, despues, estado (REVISADA | SIN_CAMBIO | OMITIDA) y motivo."""
    gc_fn = gc_fn or (lambda h: GO.gc_en(h, "60d"))
    bases = {r["fecha"]: r for r in GI._leer_csv(os.path.join(raiz, "data", "xau_gc_base.csv")) if r.get("base")}
    out = []
    for r in GO.leer_ratios(raiz):
        f = r["fecha"]
        if r.get("estado") == "REVISADA":
            continue
        if not str(r.get("fuente_xau", "")).startswith("gold-api"):
            out.append({"fecha": f, "antes": float(r["ratio"]), "despues": None, "estado": "OMITIDA", "motivo": "el spot no es de gold-api (provisional o implícito): no se corrige"})
            continue
        if f not in bases:
            out.append({"fecha": f, "antes": float(r["ratio"]), "despues": None, "estado": "OMITIDA", "motivo": "sin base GC−XAU de ese día"})
            continue
        cierre = SO.cierre_gld_utc(f)
        try:
            gp, hg = gc_fn(cierre.strftime("%Y-%m-%d %H:%M"))
        except Exception as e:  # noqa: BLE001
            out.append({"fecha": f, "antes": float(r["ratio"]), "despues": None, "estado": "OMITIDA", "motivo": f"sin barra de GC=F: {type(e).__name__} {str(e)[:60]}"})
            continue
        if abs((SO._t(hg) - cierre).total_seconds()) > TOL_BARRA_S:
            out.append({"fecha": f, "antes": float(r["ratio"]), "despues": None, "estado": "OMITIDA", "motivo": f"la barra de GC=F ({hg}) está lejos del cierre del GLD ({cierre:%H:%M} UTC)"})
            continue
        base = float(bases[f]["base"])
        xau = round(float(gp) - base, 2)
        fuente = f"GC=F de las {hg} UTC (cierre del GLD, 16:00 ET) {round(float(gp), 2)} − base {base} del {f}"
        if aplicar:
            fila = GO.revisar_ratio(raiz, f, xau, hg, fuente, r["gld_cierre"], medido)
            out.append({"fecha": f, "antes": float(r["ratio"]), "despues": float(fila["ratio"]) if fila else float(r["ratio"]), "estado": "REVISADA" if fila else "SIN_CAMBIO", "motivo": fuente})
        else:
            nuevo = round(xau / float(r["gld_cierre"]), 5)
            out.append({"fecha": f, "antes": float(r["ratio"]), "despues": nuevo, "estado": "REVISADA" if abs(nuevo - float(r["ratio"])) >= 0.000005 else "SIN_CAMBIO", "motivo": fuente})
    return out


def main():
    aplicar = "--aplicar" in sys.argv
    res = revisar(RAIZ, aplicar, medido=dt.datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"))
    for x in res:
        d = f"{x['despues']:.5f}" if x["despues"] is not None else "—"
        pct = f"{(x['despues'] / x['antes'] - 1) * 100:+.3f} %" if x["despues"] else ""
        print(f"{x['fecha']}  antes {x['antes']:.5f}  después {d}  {pct:>9}  {x['estado']}: {x['motivo']}")
    print(("Filas REVISADA añadidas." if aplicar else "Simulación: nada escrito (usa --aplicar)."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
