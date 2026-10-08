#!/usr/bin/env python3
"""NEXORA · DATOS PUBLICADOS con revisiones (original → revisado).

Lógica y formato del datos_macro.py original de NEXORA: data/publicaciones_macro.csv es memoria permanente (solo se añade):
  PRIMERA   = primera vez que aparece un periodo · REVISIÓN = el organismo cambia un periodo ya guardado (con el valor previo)
  HISTÓRICO (carga inicial) = punto de partida de una serie nueva (no es una publicación nueva).
Sobre esa base la web muestra las series con su transformación (interanual, mensual…) y marca los periodos revisados.

Límites visibles: el registro empieza el día de la primera ejecución (ALFRED sin clave no responde y no se inventan vintages);
«visto por primera vez» es la hora de NUESTRA captura; la publicación oficial sale del calendario. Periodo ≠ publicación.
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csvlog  # noqa: E402
from liquidez_cripto import fred  # noqa: E402

# serie FRED → (nombre, unidad, organismo)  [lista del script original]
SERIES = {
    "PAYEMS": ("Nóminas no agrícolas (nivel)", "miles", "BLS"),
    "UNRATE": ("Tasa de paro", "%", "BLS"),
    "CES0500000003": ("Salario medio por hora", "US$", "BLS"),
    "CIVPART": ("Tasa de participación laboral", "%", "BLS"),
    "JTSJOL": ("Vacantes JOLTS", "miles", "BLS"),
    "ICSA": ("Peticiones iniciales de subsidio (semanal)", "personas", "Dpto. de Trabajo"),
    "CCSA": ("Peticiones continuadas de subsidio (semanal)", "personas", "Dpto. de Trabajo"),
    "CPIAUCSL": ("IPC general (índice)", "índice", "BLS"),
    "CPILFESL": ("IPC subyacente (índice)", "índice", "BLS"),
    "PCEPI": ("Deflactor PCE (índice)", "índice", "BEA"),
    "PCEPILFE": ("Deflactor PCE subyacente (índice)", "índice", "BEA"),
    "PPIFIS": ("Precios de producción, demanda final (índice)", "índice", "BLS"),
    "GDPC1": ("PIB real (trimestral)", "miles de M US$ 2017", "BEA"),
    "PCEC96": ("Consumo real (PCE real)", "miles de M US$ 2017", "BEA"),
    "RSAFS": ("Ventas minoristas", "M US$", "Census"),
    "INDPRO": ("Producción industrial (índice)", "índice", "Fed"),
    "DGORDER": ("Pedidos de bienes duraderos", "M US$", "Census"),
    "HOUST": ("Viviendas iniciadas", "miles (anualizado)", "Census"),
    "PERMIT": ("Permisos de construcción", "miles (anualizado)", "Census"),
    "UMCSENT": ("Confianza del consumidor (U. Michigan)", "índice", "U. Michigan"),
    "FEDFUNDS": ("Tipo efectivo de fondos federales (mensual)", "%", "Fed"),
}
CAB_PUB = ["fecha_captura", "serie", "nombre", "periodo", "valor", "tipo", "valor_previo_mismo_periodo", "unidad", "organismo", "fuente"]

# series que la web muestra: (nombre, serie, transformación, decimales, unidad, descripción, palabras del evento en el calendario, n periodos)
VISTA = [
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
    out = []
    for i in range(len(s)):
        v = None
        try:
            if modo == "nivel":
                v = s[i][1]
            elif modo == "yoy" and i >= 12:
                v = (s[i][1] / s[i - 12][1] - 1) * 100
            elif modo == "mom" and i >= 1:
                v = (s[i][1] / s[i - 1][1] - 1) * 100
            elif modo == "diff" and i >= 1:
                v = s[i][1] - s[i - 1][1]
            elif modo == "qoq_anual" and i >= 1:
                v = ((s[i][1] / s[i - 1][1]) ** 4 - 1) * 100
        except ZeroDivisionError:
            v = None
        if v is not None:
            out.append((s[i][0], v))
    return out


def actualizar(calendario=None):
    ahora = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    hoy = dt.date.today().isoformat()
    previas = csvlog.leer("publicaciones_macro.csv")
    conocido = {(r["serie"], r["periodo"]): r["valor"] for r in previas}  # último valor conocido por serie y periodo
    desde = (dt.date.today() - dt.timedelta(days=800)).isoformat()
    filas, err, datos = [], {}, {}
    for sid, (nom, uni, org) in SERIES.items():
        try:
            s = fred(sid, desde)
        except Exception as e:  # noqa: BLE001
            err[sid] = f"{type(e).__name__}: {e}"
            continue
        datos[sid] = s
        serie_nueva = not any(k[0] == sid for k in conocido)
        for fch, v in (s if serie_nueva else s[-8:]):  # serie nueva: guarda su historia reciente como punto de partida
            per, val = fch.isoformat(), f"{v:.10g}"
            prev = conocido.get((sid, per))
            if prev is None:
                filas.append({"fecha_captura": hoy, "serie": sid, "nombre": nom, "periodo": per, "valor": val,
                              "tipo": "HISTÓRICO (carga inicial)" if serie_nueva else "PRIMERA", "valor_previo_mismo_periodo": "",
                              "unidad": uni, "organismo": org, "fuente": f"FRED {sid}"})
            elif abs(float(prev) - float(val)) > 1e-9 * max(1, abs(v)):
                filas.append({"fecha_captura": hoy, "serie": sid, "nombre": nom, "periodo": per, "valor": val, "tipo": "REVISIÓN",
                              "valor_previo_mismo_periodo": prev, "unidad": uni, "organismo": org, "fuente": f"FRED {sid}"})
            conocido[(sid, per)] = val
    csvlog.anadir("publicaciones_macro.csv", filas, ("serie", "periodo", "valor", "tipo"))
    todas = csvlog.leer("publicaciones_macro.csv")
    # historia por (serie, periodo): primer valor registrado → último
    hist = {}
    for r in todas:
        hist.setdefault((r["serie"], r["periodo"]), []).append(r)
    out = {}
    for nombre, sid, modo, dec, unidad, desc, claves, n in VISTA:
        if sid not in datos:
            out[nombre] = {"sin_dato": True, "fuente": f"FRED {sid}", "url": f"https://fred.stlouisfed.org/series/{sid}", "error": err.get(sid, "SIN DATO")}
            continue
        per = []
        for fecha, v in transformar(datos[sid], modo)[-n:]:
            h = hist.get((sid, fecha.isoformat()), [])
            revs = [x for x in h if x["tipo"] == "REVISIÓN"]
            orig = float(h[0]["valor"]) if h else None  # nivel original registrado (unidad de la serie FRED)
            per.append({"periodo": fecha.isoformat(), "valor": round(v, dec), "nivel_original": orig,
                        "nivel_actual": float(h[-1]["valor"]) if h else None, "revisado": bool(revs), "n_revisiones": len(revs),
                        "visto_primera_vez": h[0]["fecha_captura"] if h else None, "tipo_primer_registro": h[0]["tipo"] if h else None})
        pub = None
        for e in (calendario or {}).get("eventos", []):
            if e["fecha"] <= hoy and any(c in e["evento"].lower() for c in claves):
                pub = max(pub or "", e["fecha"])
        out[nombre] = {"serie": sid, "modo": modo, "unidad": unidad, "descripcion": desc, "decimales": dec, "fuente": f"FRED {sid}",
                       "url": f"https://fred.stlouisfed.org/series/{sid}", "periodos": per, "fecha_publicacion_calendario": pub}
    nombres = {sid: SERIES[sid][0] for sid in SERIES}
    revisiones = sorted(({"serie": nombres[r["serie"]], "id": r["serie"], "periodo": r["periodo"], "original": float(r["valor_previo_mismo_periodo"]), "revisado": float(r["valor"]),
                          "visto": r["fecha_captura"], "unidad": r["unidad"]} for r in todas if r["tipo"] == "REVISIÓN"), key=lambda r: r["visto"], reverse=True)
    return {"series": out, "revisiones": revisiones[:60], "n_revisiones": len(revisiones), "filas_registro": len(todas),
            "registro_desde": min((r["fecha_captura"] for r in todas), default=hoy), "nuevas_filas": len(filas),
            "nuevos": sum(1 for f in filas if f["tipo"] == "PRIMERA"), "errores": err,
            "nota": "El registro de revisiones empieza el día de la primera ejecución: antes de esa fecha no hay vintages guardados y no se inventan."}


if __name__ == "__main__":
    R = actualizar()
    print(R["filas_registro"], "filas;", R["n_revisiones"], "revisiones;", R["errores"])
