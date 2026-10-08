#!/usr/bin/env python3
"""NEXORA · DATOS PUBLICADOS con revisiones (original → revisado).

Cada ejecución descarga las series oficiales (FRED, sin clave) y compara cada periodo con lo que NEXORA ya había
registrado en data/publicaciones_macro.csv (solo se añade, nunca se duplica). Si el valor de un periodo cambia, se añade
una fila nueva: el primer valor registrado es el «original» y el último el «revisado».

Límites que se muestran siempre:
  · el registro empieza el día de la primera ejecución: no se inventan vintages anteriores (ALFRED sin clave no responde);
  · «visto por primera vez» es la hora de NUESTRA captura, no la hora oficial de publicación. La fecha de publicación oficial
    se toma del calendario (calendario.json) cuando existe; periodo ≠ publicación, y se muestran las dos.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csvlog  # noqa: E402
from liquidez_cripto import fred  # noqa: E402

# (nombre, serie FRED, transformación, decimales, unidad, descripción, palabras del evento en el calendario, n periodos)
SERIES = [
    ("IPC EE. UU. (CPI)", "CPIAUCSL", "yoy", 2, "%", "IPC general, % interanual", ["ipc ee. uu", "cpi"], 6),
    ("IPC subyacente", "CPILFESL", "yoy", 2, "%", "IPC sin alimentos ni energía, % interanual", ["ipc ee. uu", "cpi"], 6),
    ("Empleo · nóminas no agrícolas", "PAYEMS", "diff", 0, "mil", "Variación mensual de nóminas, miles", ["empleo", "employment"], 6),
    ("Tasa de paro", "UNRATE", "nivel", 1, "%", "Tasa de paro, %", ["empleo", "employment"], 6),
    ("Peticiones semanales de paro", "ICSA", "nivel", 0, "personas", "Peticiones iniciales, personas", ["peticiones", "claims"], 8),
    ("Ventas minoristas", "RSAFS", "mom", 2, "%", "Ventas minoristas, % mensual", ["ventas minoristas"], 6),
    ("IPP EE. UU. (PPI)", "PPIFIS", "yoy", 2, "%", "IPP demanda final, % interanual", ["ipp", "ppi"], 6),
    ("PIB EE. UU.", "GDPC1", "qoq_anual", 2, "%", "PIB real, % trimestral anualizado", ["pib", "gdp"], 4),
    ("Gasto personal (PCE)", "PCEPI", "yoy", 2, "%", "Deflactor PCE, % interanual", ["pce", "gasto personal"], 6),
    ("PCE subyacente", "PCEPILFE", "yoy", 2, "%", "Deflactor PCE subyacente, % interanual", ["pce", "gasto personal"], 6),
    ("Producción industrial", "INDPRO", "mom", 2, "%", "Producción industrial, % mensual", ["producción industrial"], 6),
    ("Ofertas de empleo (JOLTS)", "JTSJOL", "nivel", 0, "mil", "Ofertas de empleo, miles", ["jolts"], 6),
]


def transformar(s, modo):
    """[(fecha, valor)] → [(periodo, valor_transformado)] sin interpolar."""
    out = []
    for i in range(len(s)):
        try:
            if modo == "nivel":
                v = s[i][1]
            elif modo == "yoy":
                v = (s[i][1] / s[i - 12][1] - 1) * 100 if i >= 12 else None
            elif modo == "mom":
                v = (s[i][1] / s[i - 1][1] - 1) * 100 if i >= 1 else None
            elif modo == "diff":
                v = s[i][1] - s[i - 1][1] if i >= 1 else None
            elif modo == "qoq_anual":
                v = ((s[i][1] / s[i - 1][1]) ** 4 - 1) * 100 if i >= 1 else None
        except ZeroDivisionError:
            v = None
        if v is not None:
            out.append((s[i][0], v))
    return out


def actualizar(calendario=None):
    ahora = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    hoy = dt.date.today().isoformat()
    desde = (dt.date.today() - dt.timedelta(days=365 * 3)).isoformat()
    log = {}
    for r in csvlog.leer("publicaciones_macro.csv"):
        log.setdefault((r["serie"], r["periodo"]), []).append((float(r["valor"]), r["visto_utc"]))
    nuevas, out, errores, filas = [], {}, {}, []
    for nombre, sid, modo, dec, unidad, desc, claves, n in SERIES:
        try:
            tr = transformar(fred(sid, desde), modo)[-n:]
        except Exception as e:  # noqa: BLE001
            errores[sid] = f"{type(e).__name__}: {e}"
            out[nombre] = {"sin_dato": True, "fuente": f"FRED {sid}", "url": f"https://fred.stlouisfed.org/series/{sid}", "error": errores[sid]}
            continue
        per = []
        for fecha, v in tr:
            v = round(v, dec)
            k = (sid, fecha.isoformat())
            h = log.get(k, [])
            if not h or abs(h[-1][0] - v) > 0.5 * 10 ** (-dec):
                filas.append({"serie": sid, "periodo": fecha.isoformat(), "valor": v, "visto_utc": ahora})
                h = h + [(v, ahora)]
                log[k] = h
                if len(h) > 1:
                    nuevas.append({"serie": nombre, "periodo": fecha.isoformat(), "original": h[0][0], "revisado": v, "visto_utc": ahora})
            per.append({"periodo": fecha.isoformat(), "valor": v, "original": h[0][0], "revisado": len(h) > 1,
                        "vistas": [{"valor": x, "visto_utc": t} for x, t in h], "visto_primera_vez_utc": h[0][1]})
        # publicación oficial según el calendario: último evento ya ocurrido cuyo nombre coincide
        pub = None
        for e in (calendario or {}).get("eventos", []):
            if e["fecha"] <= hoy and any(c in e["evento"].lower() for c in claves):
                pub = max(pub or "", e["fecha"])
        out[nombre] = {"serie": sid, "modo": modo, "unidad": unidad, "descripcion": desc, "decimales": dec,
                       "fuente": f"FRED {sid}", "url": f"https://fred.stlouisfed.org/series/{sid}", "periodos": per,
                       "fecha_publicacion_calendario": pub}
    csvlog.anadir("publicaciones_macro.csv", filas, ("serie", "periodo", "valor"))
    todas = csvlog.leer("publicaciones_macro.csv")
    revisiones = []
    for (sid, per), h in log.items():
        if len(h) > 1:
            nm = next((x[0] for x in SERIES if x[1] == sid), sid)
            revisiones.append({"serie": nm, "periodo": per, "original": h[0][0], "revisado": h[-1][0], "visto_utc": h[-1][1], "versiones": len(h)})
    revisiones.sort(key=lambda r: r["visto_utc"], reverse=True)
    return {"series": out, "revisiones": revisiones[:60], "n_revisiones": len(revisiones), "filas_registro": len(todas),
            "registro_desde_utc": min((r["visto_utc"] for r in todas), default=ahora), "nuevas_filas": len(filas), "revisiones_nuevas": nuevas,
            "errores": errores,
            "nota": "El registro de revisiones empieza el día de la primera ejecución: antes de esa fecha no hay vintages guardados y no se inventan."}


if __name__ == "__main__":
    import json
    R = actualizar()
    print(R["filas_registro"], "filas;", R["n_revisiones"], "revisiones;", R["errores"])
    for k, v in R["series"].items():
        if not v.get("sin_dato"):
            print(k, [(p["periodo"], p["valor"]) for p in v["periodos"][-2:]])
