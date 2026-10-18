#!/usr/bin/env python3
"""Prueba del marcador con datos SIMULADOS en una carpeta temporal. No toca data/ ni site/data/ reales y no llama a Telegram ni a la red.
Uso:  python tools/prueba_marcador.py"""
import csv
import datetime as dt
import gzip
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import marcador as M  # noqa: E402

assert "telegram" not in sys.modules, "el marcador no debe importar telegram"
T = tempfile.mkdtemp(prefix="marcador_")
for d in ("data", "site/data", "data/historico_contexto"):
    os.makedirs(os.path.join(T, d), exist_ok=True)


def w(rel, obj):
    p = os.path.join(T, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def wcsv(rel, filas):
    p = os.path.join(T, rel)
    with open(p, "w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        wr.writeheader()
        wr.writerows(filas)


def dias(ini, n):
    d = dt.date.fromisoformat(ini)
    out = []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


# ---- series simuladas: SPX sube +1 % por sesión desde 100 (retornos conocidos); NDX plano salvo un salto; ORO baja 1 % por sesión; BTC sube todos los días naturales; 2Y sube 2 pb por sesión
SES = dias("2026-01-01", 200)
spx = [[d, round(100 * 1.01 ** i, 6)] for i, d in enumerate(SES)]
ndx = [[d, 100.0 if i < 150 else 100.0 + 0.05 * (i - 149)] for i, d in enumerate(SES)]      # +0,05 pts/sesión = ~0,05 % → NEUTRAL (< 0,1 %)
oro = [[d, round(100 * 0.99 ** i, 6)] for i, d in enumerate(SES)]
nat = [(dt.date(2026, 1, 1) + dt.timedelta(days=i)).isoformat() for i in range(290)]
btc = [[d, round(100 * 1.02 ** i, 6)] for i, d in enumerate(nat)]
y2 = [[d, round(4.0 + 0.02 * i, 4)] for i, d in enumerate(SES)]
HOY = dt.datetime(2026, 10, 12, 22, 0, tzinfo=dt.timezone.utc)   # lunes 12-oct, tras el cierre de EE. UU.
ult = SES[-1]
print("última sesión simulada:", ult, "· hoy simulado:", HOY.strftime("%Y-%m-%d %H:%M UTC"))
w("site/data/precios.json", {"activos": {"spx": {"serie": spx}, "ndx": {"serie": ndx}, "oro": {"serie": oro}, "btc": {"serie": btc}}})
w("site/data/tipos.json", {"t2y": {"serie": y2}})

# ---- contexto histórico: cambios de tesis, de régimen y de liquidez
fechas = {"2026-09-01 10:00": ("SIN TESIS", "SIN GIRO DE LIQUIDEZ", "SIN RÉGIMEN CLARO", "MIXTO"),
          "2026-09-03 10:00": ("ALCISTA DÉBIL", "SIN GIRO DE LIQUIDEZ", "SIN RÉGIMEN CLARO", "MIXTO"),
          "2026-09-10 22:00": ("ALCISTA DÉBIL", "SEÑALES INICIALES DE GIRO", "EXPANSIÓN DESINFLACIONISTA", "FAVORABLE"),      # tras las 21:30: cuenta el cierre de ese día
          "2026-09-14 10:00": ("BAJISTA", "SEÑALES INICIALES DE GIRO", "ESTANFLACIÓN", "DESFAVORABLE")}
for ts, (tes, liq, reg, ries) in fechas.items():
    ctx = {"generado_utc": ts + " UTC", "tesis": {"tesis_por_activo": [{"activo": a, "etiqueta": tes if a in ("Oro", "S&P 500", "Bitcoin", "Nasdaq 100") else "SIN TESIS"} for a in ("Oro", "S&P 500", "Bitcoin", "Nasdaq 100", "US30 · Dow Jones")]},
           "regimen_macro": {"cuadrante": reg, "riesgo": ries}, "liquidez": {"lectura": liq}}
    d, hm = ts.split(" ")
    p = os.path.join(T, "data/historico_contexto", d)
    os.makedirs(p, exist_ok=True)
    open(os.path.join(p, hm.replace(":", "") + ".json.gz"), "wb").write(gzip.compress(json.dumps(ctx, ensure_ascii=False).encode()))

# ---- alertas y reacciones ya emitidas
wcsv("data/historico_alertas.csv", [
    {"fecha_utc": "2026-09-08 16:00 UTC", "clave": "fed", "titulo": "Fed", "enviada": "True", "error": "", "l1": "Fed mié 28 oct: subida 20 % → 38 %, bajada 0 % → 0 %; resultado más probable: mantener (FedWatch NEXORA)."},
    {"fecha_utc": "2026-09-09 16:00 UTC", "clave": "fed", "titulo": "Fed", "enviada": "True", "error": "", "l1": "Fed: el resultado más probable de la reunión del 28 oct pasa de «mantener» a «bajada» (subida 5 %, mantener 30 %, bajada 65 %; contrato ZQV26) (FedWatch NEXORA)."},
    {"fecha_utc": "2026-09-08 09:00 UTC", "clave": "skew_rel_2026-09-01", "titulo": "Riesgo de cola (SKEW)", "enviada": "True", "error": "", "l1": "El SKEW cierra en 154 ...; confirmaciones encendidas 2 de 3 (Cboe, ciclo.py, FRED/OFR)."},
    {"fecha_utc": "2026-09-08 10:00 UTC", "clave": "skew_rel_2026-08-01", "titulo": "Riesgo de cola (SKEW)", "enviada": "True", "error": "", "l1": "El SKEW cierra en 150 ...; confirmaciones encendidas 1 de 3 (Cboe, ciclo.py, FRED/OFR)."},
    {"fecha_utc": "2026-09-08 11:00 UTC", "clave": "vix", "titulo": "Miedo (VIX)", "enviada": "True", "error": "", "l1": "El VIX está en 30"},
    {"fecha_utc": "2026-09-08 11:30 UTC", "clave": "prueba", "titulo": "Alerta de prueba", "enviada": "True", "error": "", "l1": "prueba"}])
wcsv("data/reacciones_eventos.csv", [
    {"evento_id": "IPC-X", "fase": "T+5", "clasificacion": "SE CONFIRMA", "objetivo_utc": "2026-09-08 12:35", "origen": "vivo", "version_regla": "3.0"},
    {"evento_id": "IPC-X", "fase": "CIERRE", "clasificacion": "INVERSIÓN · NQ cae", "objetivo_utc": "2026-09-08 20:00", "origen": "vivo", "version_regla": "3.0"},
    {"evento_id": "IPC-X", "fase": "T+60", "clasificacion": "PARCIAL", "objetivo_utc": "2026-09-08 13:30", "origen": "vivo", "version_regla": "3.0"}])

# ================================================================ 1) BACKFILL
n = M.backfill(T)
S = M.leer_csv(os.path.join(T, "data/marcador_senales.csv"))
por = {}
for s in S:
    por.setdefault(s["tipo"], []).append(s)
assert all(s["origen"] == "backfill" and s["run_id"] == "backfill" and s["estado"] == "ACTIVA" for s in S)
assert len(por["skew"]) == 1, "solo cuenta el SKEW con ≥ 2 confirmaciones"
assert {s["direccion"] for s in por["fed"]} == {"ALCISTA", "BAJISTA"}, [s["direccion"] for s in por["fed"]]    # más subidas descontadas / pasa a «bajada»
assert len(por["reaccion"]) == 2 and all(s["direccion"] == "NINGUNA" for s in por["reaccion"]), "reacción: solo T+5 y CIERRE, solo registro"
assert not [s for s in S if s["tipo"] in ("vix", "prueba")]
print("1) backfill:", len(S), "señales →", {k: len(v) for k, v in por.items()})
tes = [s for s in por["tesis"]]
assert {s["activo"] for s in tes} == {"ORO", "ES", "BTC", "NQ"} and len(tes) == 8, len(tes)   # 4 activos × 2 cambios (la primera observación es referencia, no señal)
assert [s for s in por["regimen"]][0]["direccion"] == "ALCISTA" and [s for s in por["regimen"]][1]["direccion"] == "BAJISTA"
assert [s["direccion"] for s in por["liquidez"]] == ["ALCISTA"]
# idempotente
assert M.backfill(T) == [] and len(M.leer_csv(os.path.join(T, "data/marcador_senales.csv"))) == len(S)
print("   OK: idempotente (segunda pasada = 0 señales nuevas), SKEW con 1 confirmación y alertas ajenas excluidas")

# ================================================================ 2) EVALUACIÓN con retornos conocidos
M.evaluar(T, HOY)
Rz = M.leer_csv(os.path.join(T, "data/marcador_resultados.csv"))
by = {(r["id"], r["horizonte"]): r for r in Rz}
sp = next(s for s in tes if s["activo"] == "ES" and s["direccion"] == "ALCISTA" and "SIN TESIS → ALCISTA" in s["valor"])
r1, r5, r20 = by[(sp["id"], "1")], by[(sp["id"], "5")], by[(sp["id"], "20")]
assert r1["resultado"] == "ACIERTO" and abs(float(r1["ret"]) - 1.0) < 0.01 and float(r1["mae"]) == 0.0, r1
assert abs(float(r5["ret"]) - (1.01 ** 5 - 1) * 100) < 0.01 and abs(float(r20["ret"]) - (1.01 ** 20 - 1) * 100) < 0.01
print("2) SPX +1 %%/sesión, señal ALCISTA: T+1 %.2f %% · T+5 %.2f %% · T+20 %.2f %% (ACIERTO, MAE 0)" % (float(r1["ret"]), float(r5["ret"]), float(r20["ret"])))
base = float(r1["base_pct"])
assert base == 100.0, "SPX siempre sube +1 %/sesión: el azar acierta el 100 % de las ventanas"
# fallo y MAE: ORO baja 1 %/sesión; tesis ALCISTA débil sobre oro → FALLO, MAE = peor retorno de la ruta
og = next(s for s in tes if s["activo"] == "ORO" and "SIN TESIS → ALCISTA" in s["valor"])
f5 = by[(og["id"], "5")]
assert f5["resultado"] == "FALLO" and abs(float(f5["ret"]) - (0.99 ** 5 - 1) * 100) < 0.01 and abs(float(f5["mae"]) - float(f5["ret"])) < 1e-6, f5
print("   ORO −1 %%/sesión con tesis ALCISTA: T+5 %.2f %% → FALLO, retorno máximo adverso %.2f %%" % (float(f5["ret"]), float(f5["mae"])))
# BAJISTA sobre SPX que sube: FALLO; sobre ORO que baja: ACIERTO
ob = next(s for s in tes if s["activo"] == "ORO" and s["direccion"] == "BAJISTA")
assert by[(ob["id"], "5")]["resultado"] == "ACIERTO"
# NEUTRAL: NDX +0,05 % por sesión (sin señales en el tiempo del salto → se comprueba con medir)
m = M.medir([(d, v) for d, v in ndx], "ndx", "2026-09-30 10:00", 1, 1)
print("   NDX +0,05 %/sesión: medir() →", m["resultado"], m["ret"])
assert m["resultado"] == "NEUTRAL" or SES.index(m["fecha_ref"]) < 150
m2 = M.medir([(d, v) for d, v in ndx], "ndx", SES[170] + " 10:00", 1, 1)
assert m2["resultado"] == "NEUTRAL" and 0 < m2["ret"] < 0.1, m2
# 2Y en pb: la alerta Fed ALCISTA (más subidas) con el 2Y subiendo 2 pb/sesión → ACIERTO en pb
fa = next(s for s in por["fed"] if s["direccion"] == "ALCISTA")
fr = by[(fa["id"], "5")]
assert fr["unidad"] == "pb" and abs(float(fr["ret"]) - 10.0) < 0.01 and fr["resultado"] == "ACIERTO", fr
fb = next(s for s in por["fed"] if s["direccion"] == "BAJISTA")
assert by[(fb["id"], "1")]["resultado"] == "FALLO"          # esperaba que el 2Y bajase y sube
print("   Fed: 2Y +2 pb/sesión → alerta de subidas T+5 = +%.1f pb ACIERTO; alerta de recortes T+1 FALLO (unidad pb)" % float(fr["ret"]))

# ---- cierres oficiales: la barra del día en curso no cuenta antes de las 21:30 UTC ni para cripto
bar_hoy = [(d, v) for d, v in spx] + [("2026-10-12", 999.0)]
assert M.completas(bar_hoy, "spx", dt.datetime(2026, 10, 12, 15, 0, tzinfo=dt.timezone.utc))[-1][0] == ult
assert M.completas(bar_hoy, "spx", dt.datetime(2026, 10, 12, 22, 0, tzinfo=dt.timezone.utc))[-1][0] == "2026-10-12"
assert M.completas([("2026-10-12", 1.0)], "btc", dt.datetime(2026, 10, 12, 23, 59, tzinfo=dt.timezone.utc)) == []
print("   OK: barra del día en curso excluida (US antes de 21:30 UTC; cripto siempre)")

# ---- PENDIENTE: señal reciente sin cierres a T+20 → no se escribe nada; sin serie → nada
rec = M.senal("tesis", "ES", "ALCISTA", f"{SES[-3]} 10:00", "SIN TESIS → ALCISTA", "x", "x", "test", "vivo")
assert M.medir(M.completas(spx, "spx", HOY), "spx", rec["fecha_utc"], 1, 20) is None and M.medir(M.completas(spx, "spx", HOY), "spx", rec["fecha_utc"], 1, 1) is not None
print("   OK: sin sesiones suficientes a T+20 → PENDIENTE (None), nunca estimado")
# regla de las 21:30: tras el cierre cuenta el cierre de ese día
a = M.indice_ref(spx, "spx", "2026-09-10 10:00"); b = M.indice_ref(spx, "spx", "2026-09-10 22:00")
assert SES[b] == "2026-09-10" and SES[a] == "2026-09-09"
assert btc[M.indice_ref([(d, v) for d, v in btc], "btc", "2026-09-10 23:00")][0] == "2026-09-09"
print("   OK: referencia = último cierre completo anterior (US tras 21:30 UTC cuenta el del día; cripto nunca el del día)")

# ---- idempotencia y solo-añadir de resultados
antes = open(os.path.join(T, "data/marcador_resultados.csv"), "rb").read()
assert M.evaluar(T, HOY) == []
assert open(os.path.join(T, "data/marcador_resultados.csv"), "rb").read() == antes
print("   OK: re-evaluar no reescribe nada (%d resultados guardados)" % len(Rz))

# ================================================================ 3) ANULACIÓN (corrección sin editar)
antes_s = open(os.path.join(T, "data/marcador_senales.csv"), "rb").read()
M.anular(T, og["id"], "prueba de corrección")
despues_s = open(os.path.join(T, "data/marcador_senales.csv"), "rb").read()
assert despues_s.startswith(antes_s), "una corrección no puede tocar filas anteriores"
R1 = M.resumen(T, HOY)
assert R1["n_anuladas"] == 1 and og["id"] not in [x["id"] for x in R1["senales"]]
print("3) OK: anulación = fila nueva ANULADA (bytes anteriores intactos); la señal desaparece del marcador")

# ================================================================ 4) REGISTRO VIVO (origen=vivo, sin Telegram)
w("site/data/resumen.json", {"tesis_activos": {"Oro": {"etiqueta": "BAJISTA DÉBIL"}, "S&P 500": {"etiqueta": "BAJISTA"}, "Nasdaq 100": {"etiqueta": "BAJISTA"}, "Bitcoin": {"etiqueta": "BAJISTA"}}})
w("site/data/regimen.json", {"evaluacion": {"cuadrante": "ESTANFLACIÓN", "riesgo": "DESFAVORABLE"}})
w("site/data/liquidez.json", {"evaluacion": {"lectura": "SEÑALES INICIALES DE GIRO"}})
ant = len(M.leer_csv(os.path.join(T, "data/marcador_senales.csv")))
v1 = M.registrar(T, HOY, "run-1")
print("4) registro vivo con el mismo estado que el último del backfill:", [(s["tipo"], s["activo"]) for s in v1])
assert [s["tipo"] for s in v1] == ["tesis"] and v1[0]["activo"] == "ORO"        # solo oro cambió (BAJISTA → BAJISTA DÉBIL); el resto sigue igual
w("site/data/liquidez.json", {"evaluacion": {"lectura": "SIN GIRO DE LIQUIDEZ"}})
v2 = M.registrar(T, HOY + dt.timedelta(hours=1), "run-2")
assert [(s["tipo"], s["direccion"], s["origen"], s["run_id"]) for s in v2] == [("liquidez", "NINGUNA", "vivo", "run-2")]
assert M.registrar(T, HOY + dt.timedelta(hours=2), "run-3") == [], "sin cambios no hay señales"
print("   OK: solo se registran CAMBIOS; origen=vivo y run_id propios; sin cambios no se añade nada")

# ================================================================ 5) RESUMEN: separación vivas/backfill, n<20, base
R2 = M.resumen(T, HOY)
assert set(R2["resumen"]) == {"backfill", "vivo"}
t = R2["resumen"]["backfill"]["tesis"]["horizontes"]["5"]
assert t["muestra_insuficiente"] is True and t["n"] < 20
assert t["base_media_pct"] is not None and t["acierto_pct"] is not None
assert R2["resumen"]["backfill"]["reaccion"]["no_puntuables"] == 2
print("5) OK: vivas y backfill separadas; n=%d < 20 → muestra_insuficiente; acierto %.1f %% frente a azar %.1f %%" % (t["n"], t["acierto_pct"], t["base_media_pct"]))
with open(os.path.join(T, "site/data/marcador.json"), "w", encoding="utf-8") as f:
    json.dump(R2, f, ensure_ascii=False)
B = M.bloque_contexto(T)
assert "por_origen_y_tipo" in B and "backfill" in B["por_origen_y_tipo"] and B["lectura"]
print("   OK: bloque de contexto.json:", json.dumps(B["por_origen_y_tipo"]["backfill"]["tesis"]["T+5"], ensure_ascii=False))
print("\nTODO OK · carpeta temporal:", T)
