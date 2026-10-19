#!/usr/bin/env python3
"""NEXORA · comprobación manual de la API de BEA (solo lectura). No envía Telegram, no escribe datos, no hace commit.

Consulta NIPA T20804 (índice de precios PCE, mensual) y T10106 (PIB real, trimestral) con la clave BEA_API_KEY (variable de entorno), imprime las líneas disponibles, la que usa
engine/integridad.py para cada serie, los 3 últimos valores y la diferencia % frente a FRED (PCEPI, PCEPILFE, GDPC1).
NUNCA imprime la clave ni la respuesta cruda (la API de BEA devuelve en «Request» los parámetros enviados, incluida la clave): solo campos concretos de las filas de datos."""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import integridad as I  # noqa: E402
from liquidez_cripto import fred  # noqa: E402

CLAVE = os.environ.get("BEA_API_KEY", "")


def consulta(tabla, freq, anios):
    url = f"https://apps.bea.gov/api/data?UserID={CLAVE}&method=GetData&datasetname=NIPA&TableName={tabla}&Frequency={freq}&Year={anios}&ResultFormat=JSON"
    try:
        j = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "nexora-terminal/1.0"}), timeout=60).read().decode("utf-8", "replace"))
    except Exception as e:  # noqa: BLE001
        sys.exit(f"BEA no respondió ({type(e).__name__}) para {tabla}")
    res = (j.get("BEAAPI") or {}).get("Results") or {}
    if isinstance(res, list):
        res = res[0] if res else {}
    err = (j.get("BEAAPI") or {}).get("Error") or res.get("Error")
    if err:
        sys.exit(f"BEA devolvió un error para {tabla}: código {err.get('APIErrorCode')}, {str(err.get('APIErrorDescription') or '')[:160]}")
    datos = res.get("Data") or []
    if not datos:
        sys.exit(f"BEA no devolvió datos para {tabla} (¿clave inválida?)")
    return datos


def num(v):
    v = (v or "").replace(",", "").strip()
    return float(v) if re.fullmatch(r"-?\d+(\.\d+)?", v) else None


def main():
    if not CLAVE:
        sys.exit("BEA_API_KEY no está definida en el entorno: nada que comprobar (SIN DATO).")
    print("Clave BEA presente (no se imprime). Sin Telegram, sin escritura de datos.\n")
    tablas = {}
    for sid, (tabla, freq, claves) in I.BEA_TABLAS.items():
        if (tabla, freq) not in tablas:
            tablas[(tabla, freq)] = consulta(tabla, freq, "2026,2025")
    resumen = []
    for (tabla, freq), datos in tablas.items():
        lineas = {}
        for r in datos:
            lineas.setdefault(int(r["LineNumber"]), (r.get("LineDescription", ""), r.get("CL_UNIT", ""), r.get("UNIT_MULT", "")))
        print(f"== NIPA {tabla} · frecuencia {freq} · {len(lineas)} líneas · periodos {sorted({r['TimePeriod'] for r in datos})[0]} … {sorted({r['TimePeriod'] for r in datos})[-1]}")
        for n, (d, cu, um) in sorted(lineas.items())[:8]:
            print(f"   línea {n:>2}: {d}   [unidad: {cu}, UNIT_MULT={um}]")
    print()
    for sid, (tabla, freq, claves) in I.BEA_TABLAS.items():
        datos = tablas[(tabla, freq)]
        cand = {}
        for r in datos:
            d = r.get("LineDescription", "")
            if all(c in d.lower() for c in claves) and (sid != "PCEPI" or "excluding" not in d.lower()):
                cand.setdefault(int(r["LineNumber"]), d)
        if not cand:
            print(f"== {sid}: NINGUNA línea de {tabla} coincide con {claves}: las líneas del código NO son correctas")
            resumen.append((sid, None))
            continue
        ln = min(cand)                                     # la primera línea que coincide (la más agregada)
        print(f"== {sid} ← {tabla} línea {ln}: «{cand[ln]}»" + (f" (otras que también coinciden: {sorted(set(cand) - {ln})})" if len(cand) > 1 else ""))
        filas = sorted(((r["TimePeriod"], num(r["DataValue"])) for r in datos if int(r["LineNumber"]) == ln and num(r["DataValue"]) is not None))[-3:]
        f = {}
        for fecha, v in fred(sid, "2024-01-01"):
            f[(fecha.year, fecha.month if freq == "M" else (fecha.month - 1) // 3 + 1)] = v
        malos = 0
        for tp, v in filas:
            m = re.fullmatch(r"(\d{4})[MQ](\d{1,2})", tp)
            k = (int(m.group(1)), int(m.group(2)))
            fv = f.get(k)
            if fv is None:
                print(f"   {tp}: BEA {v}   FRED SIN DATO para ese periodo")
                malos += 1
                continue
            dif = abs(fv - v) / v * 100
            malos += dif > I.UMBRAL_DISCREPANCIA_PCT
            print(f"   {tp}: BEA {v:>12}   FRED {fv:>12}   diferencia {dif:.4f} %  {'OK' if dif <= I.UMBRAL_DISCREPANCIA_PCT else '← SUPERA 0,05 %'}")
        resumen.append((sid, malos == 0))
    print("\nRESUMEN:", " · ".join(f"{s}: {'SIN LÍNEA' if ok is None else 'coincide con FRED' if ok else 'NO coincide'}" for s, ok in resumen))
    sys.exit(0 if all(ok for _, ok in resumen) else 1)


if __name__ == "__main__":
    main()
