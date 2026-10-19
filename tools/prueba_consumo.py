#!/usr/bin/env python3
"""Prueba de #/consumo con datos SIMULADOS (sin red). Comprueba las reglas de la tesis, los cálculos de ratios y de FRED, la concentración y el tipo de señal «consumo» del marcador.
Uso:  python tools/prueba_consumo.py"""
import datetime as dt
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import consumo as C  # noqa: E402
import marcador as M  # noqa: E402
C.michigan_real = lambda raiz, ahora: {"serie": [], "errores": {}}   # ninguna prueba toca la web de Michigan (la cubre prueba_michigan.py)

# ---------------------------------------------------------------- 1) matriz de la tesis (9 combinaciones) e intensidad
esperado = {("ALZA", "ALZA"): ("CONSUMO FUERTE", "FUERTE"), ("ALZA", "MIXTO"): ("CONSUMO FUERTE", "DÉBIL"), ("MIXTO", "ALZA"): ("CONSUMO FUERTE", "DÉBIL"),
            ("ALZA", "BAJA"): ("DIVERGENCIA MERCADO ADELANTADO", "FUERTE"), ("MIXTO", "BAJA"): ("SE ENFRÍA", "FUERTE"), ("BAJA", "BAJA"): ("CONSUMO DÉBIL", "FUERTE"),
            ("BAJA", "ALZA"): ("DIVERGENCIA MERCADO DEFENSIVO", "FUERTE"), ("BAJA", "MIXTO"): ("DIVERGENCIA MERCADO DEFENSIVO", "DÉBIL"), ("MIXTO", "MIXTO"): ("SIN TESIS", None)}
for (m, r), (res, inten) in esperado.items():
    t = C.tesis(m, r, "MIXTA")
    assert (t["resultado"], t["intensidad"]) == (res, inten), (m, r, t)
    assert t["confirmaria"] and t["invalidaria"], "cada resultado lleva «qué lo confirmaría» y «qué lo invalidaría»"
print("1) OK las 9 combinaciones (mercado, real) dan su resultado e intensidad; todas con «confirmaría» e «invalidaría»")
# la capacidad contradice → intensidad DÉBIL
assert C.tesis("ALZA", "ALZA", "NO RESPALDA")["intensidad"] == "DÉBIL" and C.tesis("ALZA", "ALZA", "RESPALDA")["intensidad"] == "FUERTE"
assert C.tesis("BAJA", "BAJA", "RESPALDA")["intensidad"] == "DÉBIL" and C.tesis("MIXTO", "BAJA", "RESPALDA")["intensidad"] == "DÉBIL" and C.tesis("MIXTO", "BAJA", "NO RESPALDA")["intensidad"] == "FUERTE"
assert C.tesis("SIN DATO", "ALZA", "MIXTA")["resultado"] == "SIN DATO" and C.tesis("BAJA", "SIN DATO", "MIXTA")["direccion_marcador"] == "NINGUNA"
print("   OK la capacidad que contradice baja la intensidad a DÉBIL; si falta una capa → SIN DATO (sin dirección)")
dirs = {r: C.tesis(m, rr, "MIXTA")["direccion_marcador"] for (m, rr), (r, _) in esperado.items()}
assert dirs["CONSUMO FUERTE"] == "ALCISTA" and dirs["DIVERGENCIA MERCADO DEFENSIVO"] == "ALCISTA" and dirs["SE ENFRÍA"] == "BAJISTA" and dirs["CONSUMO DÉBIL"] == "BAJISTA"
assert dirs["DIVERGENCIA MERCADO ADELANTADO"] == "BAJISTA" and dirs["SIN TESIS"] == "NINGUNA" and M.DIR_CONSUMO == {k: v for k, v in dirs.items() if v != "NINGUNA"}
print("   OK dirección esperada para el marcador (RSPD/RSPS a T+20) coincide entre consumo.py y marcador.py")

# ---------------------------------------------------------------- 2) ratios: medias de 50 y 200 (sobre todo el historial), recorte a 2 años, pendiente a 3 meses
def dias(n, fin=dt.date(2026, 10, 16)):
    out, d = [], fin
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= dt.timedelta(days=1)
    return out[::-1]


D = dias(760)
sube = [(d, 100 * 1.001 ** i) for i, d in enumerate(D)]
base = [(d, 100.0) for d in D]
r = C.ratio(sube, base)
g = C.grafico(r)
assert g["ratio"][0][0] >= "2024-10-16" and len(g["ratio"]) < len(r) and g["ratio"][-1][0] == "2026-10-16", "2 años de ratio"
assert len(g["sma200"]) == len(g["ratio"]) and g["sma200"][0][0] == g["ratio"][0][0], "la media de 200 se calcula sobre TODO el historial (existe ya en el primer día mostrado)"
m = C.metricas_ratio(r)
assert m["sobre_sma200"] and m["pendiente_3m_pct"] > 0 and C.estado_mercado(m) == "ALZA"
baja = C.ratio([(d, 100 * 0.999 ** i) for i, d in enumerate(D)], base)
assert C.estado_mercado(C.metricas_ratio(baja)) == "BAJA"
# sobre la media pero con pendiente negativa en 3 meses → MIXTO
curva = [(d, 100 + 0.2 * i if i < 690 else 238 - 0.1 * (i - 690)) for i, d in enumerate(D)]      # sube hasta el sesión 690 y luego cae poco: sigue sobre su media de 200 con pendiente negativa
mm = C.metricas_ratio(C.ratio(curva, base))
assert mm["sobre_sma200"] and mm["pendiente_3m_pct"] < 0 and C.estado_mercado(mm) == "MIXTO", mm
assert C.metricas_ratio(r[:100]) is None and C.estado_mercado(None) == "SIN DATO"
print("2) OK ratio: 2 años con medias de 50/200 (calculadas sobre todo el historial); ALZA / BAJA / MIXTO por media 200 y pendiente a 3 meses; poca historia → SIN DATO")

# ---------------------------------------------------------------- 3) series de FRED: % interanual, tendencia 3 meses, ahorro, trimestral
meses = [(dt.date(2023 + (i // 12), i % 12 + 1, 1), 100 * 1.004 ** i) for i in range(36)]              # +0,4 %/mes
x = C.metrica_fred("RRSFS", meses)
assert abs(x["valor"] - ((1.004 ** 12 - 1) * 100)) < 0.01 and abs(x["tendencia_3m"] - ((1.004 ** 3 - 1) * 100)) < 0.01 and x["periodo"] == "2025-12-01", x
ah = [(dt.date(2023 + (i // 12), i % 12 + 1, 1), 5.0 if i < 33 else 4.0) for i in range(36)]
p = C.metrica_fred("PSAVERT", ah)
assert p["valor"] == 4.0 and p["tendencia_3m"] == -1.0 and p["tendencia_unidad"] == "pp" and 4.0 < p["media_12m"] < 5.0
q = C.metrica_fred("DRCCLACBS", [(dt.date(2025, 1, 1), 3.0), (dt.date(2025, 4, 1), 3.1), (dt.date(2025, 7, 1), 3.2), (dt.date(2025, 10, 1), 3.25)])
assert q["frecuencia"] == "Q" and q["tendencia_3m"] == 0.05 and q["tendencia_unidad"] == "pp", q          # 3,25 frente al trimestre anterior (3,20)
assert C.metrica_fred("TOTALSL", [])["sin_dato"] is True
print("3) OK FRED: interanual +%.2f %%, tendencia 3 m +%.2f %%; ahorro con media de 12 meses; trimestral; serie vacía → SIN DATO" % (x["valor"], x["tendencia_3m"]))

# ---------------------------------------------------------------- 4) capas real y capacidad con reglas fijas
def fila(sid, **k):
    return {"serie": sid, "nombre": sid, "capa": "x", **k}
real_ok = {"RRSFS": fila("RRSFS", tendencia_3m=0.5), "PCEC96": fila("PCEC96", tendencia_3m=1.0)}
assert C.capa_real(real_ok)["estado"] == "ALZA"
assert C.capa_real({"RRSFS": fila("RRSFS", tendencia_3m=-0.5), "PCEC96": fila("PCEC96", tendencia_3m=-1.0)})["estado"] == "BAJA"
assert C.capa_real({"RRSFS": fila("RRSFS", tendencia_3m=0.5), "PCEC96": fila("PCEC96", tendencia_3m=-1.0)})["estado"] == "MIXTO"
assert C.capa_real({"RRSFS": fila("RRSFS", tendencia_3m=0.5), "PCEC96": {"serie": "PCEC96", "sin_dato": True}})["estado"] == "SIN DATO"
cap_ok = {"DSPIC96": fila("DSPIC96", tendencia_3m=0.6), "PSAVERT": fila("PSAVERT", valor=5.0, media_12m=4.5), "TOTALSL": fila("TOTALSL", valor=2.0), "DRCCLACBS": fila("DRCCLACBS", tendencia_3m=-0.1)}
assert C.capa_capacidad(cap_ok)["estado"] == "RESPALDA" and C.capa_capacidad(cap_ok)["suma"] == 4
cap_mal = {"DSPIC96": fila("DSPIC96", tendencia_3m=-0.6), "PSAVERT": fila("PSAVERT", valor=3.0, media_12m=4.5), "TOTALSL": fila("TOTALSL", valor=-1.0), "DRCCLACBS": fila("DRCCLACBS", tendencia_3m=0.3)}
assert C.capa_capacidad(cap_mal)["estado"] == "NO RESPALDA" and C.capa_capacidad(cap_mal)["suma"] == -4
assert C.capa_capacidad({"DSPIC96": fila("DSPIC96", tendencia_3m=0.6), "PSAVERT": fila("PSAVERT", valor=3.0, media_12m=4.5)})["estado"] == "MIXTA", "las series sin dato votan 0"
print("4) OK capa real (alza/baja/mixto/SIN DATO) y capacidad (+4 respalda, −4 no respalda, series ausentes votan 0)")

# ---------------------------------------------------------------- 5) concentración SIMÉTRICA: separación > 2 pp en 3 meses en cualquier sentido
c = lambda a, b: C.concentracion({"pendiente_3m_pct": a}, {"pendiente_3m_pct": b}, None)  # noqa: E731
arriba, abajo = c(6.0, -1.0), c(-2.0, 1.0)
assert arriba["aviso"].startswith("el ratio lo mueven AMZN+TSLA, no el consumo amplio: empujan XLY/XLP al alza") and arriba["sentido"] == "AL ALZA" and arriba["diferencia_3m_pp"] == 7.0
assert abajo["aviso"].startswith("el ratio lo mueven AMZN+TSLA, no el consumo amplio: empujan XLY/XLP a la baja") and abajo["sentido"] == "A LA BAJA" and "-3,00 pp" in abajo["aviso"]
assert c(3.0, 1.0)["aviso"] is None, "exactamente 2 pp no supera el umbral"
assert c(3.01, 1.0)["aviso"] is not None and c(-1.0, 1.01)["aviso"] is not None and c(4.0, 3.0)["aviso"] is None
hoy_ = C.concentracion({"pendiente_3m_pct": -4.97}, {"pendiente_3m_pct": -2.39}, None)
assert hoy_["diferencia_3m_pp"] == -2.58 and hoy_["aviso"] is not None and hoy_["sentido"] == "A LA BAJA", "con los datos de hoy (−2,58 pp) debe saltar"
w = C.peso_amzn_tsla({"fecha": "15-Oct-2026", "principales": [{"ticker": "AMZN", "peso": 22.97}, {"ticker": "TSLA", "peso": 17.34}, {"ticker": "HD", "peso": 5.2}], "fuente": "SSGA"})
assert w == {"fecha": "15-Oct-2026", "amzn": 22.97, "tsla": 17.34, "suma": 40.31, "fuente": "SSGA"}
assert C.peso_amzn_tsla({"principales": [{"ticker": "HD", "peso": 5.2}]}) is None
print("5) OK concentración simétrica: >2 pp al alza o a la baja avisa e indica el sentido; 2,00 pp exactos no; hoy (−2,58 pp) salta «a la baja»; peso AMZN+TSLA = 40,31 % con su fecha")

# ---------------------------------------------------------------- 5b) contexto de ánimo: percentil de UMCSENT desde 1978 (no puntúa)
hist = [(dt.date(1960 + i // 12, i % 12 + 1, 1), 50 + (i % 60)) for i in range(0, 12 * 66)]            # 1960-2025: valores 50..109
ult = lambda v: hist[:-1] + [(hist[-1][0], v)]  # noqa: E731
bajo = C.animo(ult(51), "ALZA")
assert bajo["estado"] == "OK" and bajo["zona_baja"] is True and bajo["nota"] == "la gente dice que está mal pero sigue gastando" and bajo["puntua"] is False
assert bajo["desde"] == "1978-01" and bajo["n"] == len([1 for d, v in hist if d.isoformat() >= "1978-01-01"]) and bajo["percentil"] <= 20
assert C.animo(ult(51), "BAJA")["nota"] is None and C.animo(ult(51), "MIXTO")["nota"] is None, "sin capa real al alza no hay nota"
alto = C.animo(ult(105), "ALZA")
assert alto["zona_baja"] is False and alto["nota"] is None and alto["percentil"] > 20
# percentil exacto: 200 valores 1..200 desde 1978, último = 10 → 10/200 = 5 %
lin = [(dt.date(1978 + i // 12, i % 12 + 1, 1), float(i + 1)) for i in range(200)]
lin[-1] = (lin[-1][0], 10.0)
assert C.animo(lin, "ALZA")["percentil"] == round(sum(1 for _, v in lin if v <= 10.0) / 200 * 100, 1)
assert C.animo(hist[-50:], "ALZA")["estado"] == "SIN DATO" and C.animo([], "ALZA")["estado"] == "SIN DATO"
print("5b) OK ánimo: UMCSENT en el percentil %.1f (≤ 20) con capa real AL ALZA → nota «la gente dice que está mal pero sigue gastando»; sin capa real al alza o fuera del 20 %% → sin nota; poca historia → SIN DATO; no puntúa" % bajo["percentil"])

# ---------------------------------------------------------------- 6) construir() con fuentes simuladas: cada fuente falla por separado
def y_ok(t):
    k = {"XLY": 1.002, "XLP": 1.0, "RSPD": 0.999, "RSPS": 1.0}[t]
    return [(d, 100 * k ** i) for i, d in enumerate(D)]


def f_ok(sid, desde):
    ritmo = {"RRSFS": 1.004, "PCEC96": 1.004, "DSPIC96": 1.003, "TOTALSL": 1.003, "PSAVERT": 1.0, "UMCSENT": 1.0, "DRCCLACBS": 1.0}[sid]
    if sid == "DRCCLACBS":
        return [(dt.date(2024 + i // 4, 3 * (i % 4) + 1, 1), 3.0 - 0.01 * i) for i in range(10)]
    return [(dt.date(2023 + (i // 12), i % 12 + 1, 1), (5.0 if sid == "PSAVERT" else 100) * (ritmo ** i if sid not in ("PSAVERT", "UMCSENT") else 1)) for i in range(34)]


ssga_ok = lambda tk: {"fecha": "15-Oct-2026", "principales": [{"ticker": "AMZN", "peso": 22.97}, {"ticker": "TSLA", "peso": 17.34}], "fuente": "SSGA XLY"}  # noqa: E731
J = C.construir({"yahoo": y_ok, "fred": f_ok, "ssga": ssga_ok}, dt.datetime(2026, 10, 18, tzinfo=dt.timezone.utc))
assert J["capas"]["mercado"]["estado"] == "BAJA" and J["capas"]["real"]["estado"] == "ALZA" and J["tesis"]["resultado"] == "DIVERGENCIA MERCADO DEFENSIVO", J["tesis"]
assert J["mercado"]["aviso"].startswith("el ratio lo mueven AMZN+TSLA, no el consumo amplio: empujan XLY/XLP al alza") and J["animo"]["estado"] in ("OK", "SIN DATO") and J["animo"]["puntua"] is False and J["mercado"]["pesos"]["suma"] == 40.31 and not J["errores"] and len(J["reglas"]) >= 5
print("6) OK construir() simulado: mercado BAJA + real ALZA → %s (%s); %d reglas impresas" % (J["tesis"]["resultado"], J["tesis"]["intensidad"], len(J["reglas"])))
# RSPD sin datos → SIN DATO (no se estima) y el resto sigue
def y_sin_rspd(t):
    if t == "RSPD":
        raise RuntimeError("sin datos")
    return y_ok(t)
J2 = C.construir({"yahoo": y_sin_rspd, "fred": f_ok, "ssga": ssga_ok})
assert J2["mercado"]["igual"] is None and J2["capas"]["mercado"]["estado"] == "SIN DATO" and J2["tesis"]["resultado"] == "SIN DATO" and "RSPD" in J2["errores"] and J2["mercado"]["cap"] is not None
def ssga_roto(tk):
    raise OSError("SSGA caído")
J3 = C.construir({"yahoo": y_ok, "fred": f_ok, "ssga": ssga_roto})
assert J3["mercado"]["pesos"] is None and "ssga_xly" in J3["errores"] and J3["tesis"]["resultado"] != "SIN DATO"
def f_sin_pce(sid, desde):
    if sid == "PCEC96":
        raise RuntimeError("FRED caído")
    return f_ok(sid, desde)
J4 = C.construir({"yahoo": y_ok, "fred": f_sin_pce, "ssga": ssga_ok})
assert J4["capas"]["real"]["estado"] == "SIN DATO" and J4["tesis"]["resultado"] == "SIN DATO"
print("   OK RSPD sin datos / PCE real sin datos → tesis SIN DATO; SSGA caído → peso SIN DATO pero la tesis se calcula (cada fuente falla por separado)")

# ---------------------------------------------------------------- 7) marcador: tipo de señal «consumo» (RSPD/RSPS a T+20)
T = tempfile.mkdtemp(prefix="cons_")
for d in ("data", "site/data"):
    os.makedirs(os.path.join(T, d))
ratio_sim = [[d.isoformat(), round(1.74 * (1.002 ** i), 5)] for i, d in enumerate(D)]       # el ratio sube 0,2 % por sesión


def escribe(res):
    json.dump({"tesis": {"resultado": res}, "graficos": {"igual": {"ratio": ratio_sim}}}, open(os.path.join(T, "site/data/consumo.json"), "w", encoding="utf-8"))


hoy = dt.datetime(2026, 8, 3, 12, 0, tzinfo=dt.timezone.utc)
escribe("SE ENFRÍA")
assert M.registrar(T, hoy, "run-1") == [], "la primera observación solo es referencia"
escribe("DIVERGENCIA MERCADO DEFENSIVO")
nuevas = M.registrar(T, hoy + dt.timedelta(hours=1), "run-2")
assert [(s["tipo"], s["activo"], s["direccion"], s["origen"]) for s in nuevas] == [("consumo", "RSPD/RSPS", "ALCISTA", "vivo")] and "SE ENFRÍA → DIVERGENCIA MERCADO DEFENSIVO" in nuevas[0]["valor"]
assert M.registrar(T, hoy + dt.timedelta(hours=2), "run-3") == [], "sin cambio no hay señal"
nr = M.evaluar(T, dt.datetime(2026, 10, 17, 22, 0, tzinfo=dt.timezone.utc))
by = {str(r["horizonte"]): r for r in nr}
assert set(by) == {"1", "5", "20"} and all(r["resultado"] == "ACIERTO" for r in by.values()) and by["20"]["unidad"] == "%" and abs(float(by["20"]["ret"]) - ((1.002 ** 20 - 1) * 100)) < 0.1, by
print("7) OK marcador: el cambio SE ENFRÍA → DIVERGENCIA MERCADO DEFENSIVO se registra como señal «consumo» ALCISTA sobre RSPD/RSPS y se mide a T+1/T+5/T+20 (T+20 = +%.2f %%, ACIERTO)" % float(by["20"]["ret"]))
print("\nTODO OK · sin red")
