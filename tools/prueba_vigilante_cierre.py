#!/usr/bin/env python3
"""Pruebas del vigilante del cierre. Sin red y sin Telegram real. Uso: PYTHONUTF8=1 python tools/prueba_vigilante_cierre.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vigilar_cierre as V  # noqa: E402

ESP = V.etapas_cierre()
assert "petroleo" in ESP and "gamma_oro" in ESP and "gamma_us30" in ESP and "consumo_ratio" in ESP, ESP
HORARIO = "precios,fedwatch,tipos,calendario,etf,publicados,reevaluar,resumen,tesis,regimen,noticias,skew,alertas,gamma_intradia,marcador,integridad,contexto"


def fila(cuando, modo, ok, fallo="", run="", dur="512.2"):
    return {"capturado_utc": f"{cuando} UTC", "modo": modo, "evento": "workflow_dispatch", "etapas_ok": ",".join(ok), "etapas_fallo": fallo, "duracion_s": dur, "run_id": run}


H = lambda h: fila(f"2026-10-20 {h}", "horario", HORARIO.split(","), dur="637.3")  # noqa: E731
CIERRE_OK = fila("2026-10-20 21:30", "cierre", ESP, run="39500964936")
dia_ok = [H("20:07"), H("21:07"), CIERRE_OK, H("22:07"), H("23:07")]

# 1) FALSO NEGATIVO de antes: meta.json lo sobrescribe la ejecución horaria de las 22:07 (sin «petroleo»). La lógica antigua, que mira meta.json, avisaba; la nueva lee ejecuciones.csv
meta_sobrescrito = {"modo": "horario", "etapas": {e: {"ok": True, "ejecutada_utc": "2026-10-20 22:07 UTC"} for e in HORARIO.split(",")}}
antigua = (meta_sobrescrito["etapas"].get("petroleo") or {}).get("ejecutada_utc", "")[:16] >= "2026-10-20 21:30"
assert antigua is False, "la lógica antigua (meta.json) daba «no hay ejecución de petroleo» = falso negativo"
r = V.vigilar("2026-10-20", filas=dia_ok)
assert r["ok"] is True and r["ok_n"] == len(ESP) and r["run"]["run_id"] == "39500964936" and r["avisado"] is False and "OK" in r["mensaje"], r
print(f"1) OK meta.json sobrescrito por la hora de las 22:07: la lógica antigua daba falso negativo; la nueva comprueba ejecuciones.csv y da {r['ok_n']}/{len(ESP)} OK en el run {r['run']['run_id']}")

# 2) etapa fallida en el cierre → alerta, con su nombre; sin Telegram real (función simulada)
enviados = []
env = lambda m: (enviados.append(m), (True, None))[1]  # noqa: E731
mal = fila("2026-10-20 21:30", "cierre", [e for e in ESP if e != "petroleo"], fallo="petroleo", run="39500964936")
r = V.vigilar("2026-10-20", filas=[H("21:07"), mal, H("22:07")], enviar_fn=env, avisar=True)
assert r["ok"] is False and r["fallan"] == ["petroleo"] and r["faltan"] == [] and r["avisado"] is True and len(enviados) == 1 and "Con error: petroleo" in enviados[0], r
print("2) OK etapa fallida (petroleo en etapas_fallo) → alerta: " + enviados[0])

# 3) etapa que no figura en ningún lado (no corrió) → alerta como «sin registrar»
parcial = fila("2026-10-20 21:30", "cierre", [e for e in ESP if e not in ("gamma_us30", "consumo_ratio")], run="1")
r = V.vigilar("2026-10-20", filas=[parcial], enviar_fn=env, avisar=True)
assert r["ok"] is False and sorted(r["faltan"]) == ["consumo_ratio", "gamma_us30"] and r["fallan"] == [] and "Sin registrar" in enviados[-1] and "etapas OK" in r["mensaje"]
print("3) OK etapas que no corrieron → alerta: " + enviados[-1])

# 4) no hay ejecución de cierre ese día / solo antes de las 21:30 → alerta distinta
n0 = len(enviados)
r = V.vigilar("2026-10-20", filas=[H("21:07"), H("22:07"), fila("2026-10-20 05:30", "diario", ESP)], enviar_fn=env, avisar=True)
assert r["ok"] is False and r["motivo"] == "SIN_EJECUCION" and len(enviados) == n0 + 1 and "no hay ninguna ejecución de cierre" in enviados[-1]
r = V.vigilar("2026-10-21", filas=dia_ok, enviar_fn=env, avisar=True)
assert r["motivo"] == "SIN_EJECUCION", "el cierre de otro día no vale"
print("4) OK sin ejecución de cierre ese día → alerta")

# 5) filtro por run_id: con dos cierres el mismo día se evalúa el que se pide
buen, malo = fila("2026-10-20 21:30", "cierre", ESP, run="111"), fila("2026-10-20 22:07", "horario+cierre", [e for e in ESP if e != "gamma"], fallo="gamma", run="222")
assert V.comprobar([buen, malo], "2026-10-20", run_id="111")["ok"] is True and V.comprobar([buen, malo], "2026-10-20", run_id="222")["fallan"] == ["gamma"]
assert V.comprobar([buen, malo], "2026-10-20")["run"]["run_id"] == "111", "sin run_id: la primera de las 21:30 en adelante"
assert V.comprobar([buen], "2026-10-20", run_id="999")["motivo"] == "SIN_EJECUCION"
# filas antiguas sin run_id (columna vacía o ausente) siguen valiendo por hora
viejo = {k: v for k, v in CIERRE_OK.items() if k != "run_id"}
assert V.comprobar([viejo], "2026-10-20")["ok"] is True
print("5) OK filtro por run_id (y por hora para las filas anteriores a la columna run_id)")

# 6) sin --avisar no se envía nada aunque haya problema; con todo OK tampoco se envía
n = len(enviados)
V.vigilar("2026-10-20", filas=[mal], enviar_fn=env, avisar=False)
V.vigilar("2026-10-20", filas=dia_ok, enviar_fn=env, avisar=True)
assert len(enviados) == n
print("6) OK sin --avisar o con todo OK no se envía nada")

# 8) fines de semana: sale con OK y SIN avisar (aunque no haya ejecución de cierre ese día); lunes sin cierre sí alerta
import datetime as dt  # noqa: E402
import tempfile  # noqa: E402
LOG = os.path.join(tempfile.mkdtemp(prefix="vc_"), "vigilar_cierre.csv")
n = len(enviados)
UTC = dt.timezone.utc
cod, r = V.ejecutar("2026-10-24", leer_fn=lambda: [], enviar_fn=env, avisar=True, log=LOG, ahora=dt.datetime(2026, 10, 24, 22, 15, tzinfo=UTC))
assert cod == 0 and r["ok"] and r["motivo"] == "NO_TOCA" and r["avisado"] is False and len(enviados) == n and "sábado" in r["mensaje"]
cod, r = V.ejecutar("2026-10-25", leer_fn=lambda: [], enviar_fn=env, avisar=True, log=LOG, ahora=dt.datetime(2026, 10, 25, 22, 15, tzinfo=UTC))
assert cod == 0 and r["motivo"] == "NO_TOCA" and len(enviados) == n and "domingo" in r["mensaje"]
cod, r = V.ejecutar("2026-10-26", leer_fn=lambda: [H("21:07")], enviar_fn=env, avisar=True, log=LOG, ahora=dt.datetime(2026, 10, 26, 22, 15, tzinfo=UTC))
assert cod == 1 and r["motivo"] == "SIN_EJECUCION" and r["avisado"] is True and len(enviados) == n + 1, "el lunes sin cierre SÍ alerta"
assert V.dias_de_cierre() == {0, 1, 2, 3, 4} and V.toca_cierre("2026-10-23") and not V.toca_cierre("2026-10-24")
cod, r = V.ejecutar("2026-10-20", leer_fn=lambda: dia_ok, enviar_fn=env, avisar=True, log=LOG, ahora=dt.datetime(2026, 10, 20, 22, 15, tzinfo=UTC))
assert cod == 0 and len(enviados) == n + 1
filas_log = list(__import__("csv").DictReader(open(LOG, encoding="utf-8")))
assert [x["resultado"] for x in filas_log] == ["NO_TOCA", "NO_TOCA", "ALERTA", "OK"] and filas_log[3]["run_id_cierre"] == "39500964936"
assert V.etapas_cierre() == ESP and len(ESP) == 16
print("8) OK sábado y domingo: OK y sin aviso; lunes sin cierre: alerta; cada pasada deja su fila en el registro (NO_TOCA, NO_TOCA, ALERTA, OK)")

# 9) el propio vigilante falla (excepción, sin acceso al CSV, CSV mal formado) → «vigilante sin poder comprobar» por Telegram, código 2, nunca en silencio
def sin_acceso():
    raise RuntimeError("gh api no pudo leer data/ejecuciones.csv: HTTP 401")


n = len(enviados)
cod, r = V.ejecutar("2026-10-20", leer_fn=sin_acceso, enviar_fn=env, avisar=True, log=LOG, ahora=dt.datetime(2026, 10, 20, 22, 15, tzinfo=UTC))
assert cod == 2 and r["motivo"] == "SIN_COMPROBAR" and r["avisado"] is True and len(enviados) == n + 1 and "vigilante sin poder comprobar" in enviados[-1] and "HTTP 401" in enviados[-1]
cod, r = V.ejecutar("2026-10-20", leer_fn=lambda: [{"x": "1"}], enviar_fn=env, avisar=True, ahora=dt.datetime(2026, 10, 20, 22, 15, tzinfo=UTC))
assert cod == 2 and "vigilante sin poder comprobar" in enviados[-1], "CSV mal formado (sin columnas esperadas)"
assert [x["resultado"] for x in __import__("csv").DictReader(open(LOG, encoding="utf-8"))][-1] == "SIN_COMPROBAR"
cod, r = V.ejecutar("2026-10-20", leer_fn=sin_acceso, enviar_fn=lambda m: (False, "Telegram caído"), avisar=True, ahora=dt.datetime(2026, 10, 20, 22, 15, tzinfo=UTC))
assert cod == 2 and r["avisado"] is False, "si Telegram tampoco responde sale con código 2 (el workflow queda en rojo y su paso de respaldo intenta avisar)"
MARCA = os.path.join(tempfile.mkdtemp(prefix="vm_"), "avisado")
os.environ["VIGILANTE_AVISADO_FILE"] = MARCA
V.ejecutar("2026-10-20", leer_fn=sin_acceso, enviar_fn=env, avisar=True, ahora=dt.datetime(2026, 10, 20, 22, 15, tzinfo=UTC))
assert os.path.exists(MARCA), "deja una marca para que el paso de respaldo del workflow no repita el aviso"
del os.environ["VIGILANTE_AVISADO_FILE"]
print("9) OK fallo del propio vigilante → «vigilante sin poder comprobar» (" + enviados[-1][:90] + "…), código 2, con marca anti-duplicado")

# 10) integridad vigila al vigilante: ≥ 2 días hábiles sin correr → aviso (una vez)
import integridad as I  # noqa: E402
TR = tempfile.mkdtemp(prefix="vi_")
os.makedirs(os.path.join(TR, "data"))
est = lambda y, m, d: I.estado_vigilante_cierre(TR, dt.datetime(y, m, d, 9, 0, tzinfo=UTC))  # noqa: E731
assert est(2026, 10, 22)["alerta"] is False and est(2026, 10, 23)["alerta"] is False and "todavía no ha corrido" in est(2026, 10, 23)["texto"]
assert est(2026, 10, 24)["alerta"] is True and est(2026, 10, 24)["dias_habiles_sin_correr"] == 2, "alta el 22-oct sin ninguna ejecución: el sábado 24 ya van 2 días hábiles (22 y 23)"
with open(os.path.join(TR, "data", "vigilar_cierre.csv"), "w", encoding="utf-8") as f:
    f.write("fecha,ejecutado_utc,resultado,run_id_cierre,detalle\n2026-10-22,2026-10-22 22:16 UTC,OK,1,x\n")
assert est(2026, 10, 26)["alerta"] is False and est(2026, 10, 26)["dias_habiles_sin_correr"] == 1, "lunes por la mañana: falta el viernes 23 → 1"
assert est(2026, 10, 27)["alerta"] is True and est(2026, 10, 27)["dias_habiles_sin_correr"] == 2 and est(2026, 10, 27)["ultimo_resultado"] == "OK", "martes: faltan el viernes y el lunes"
with open(os.path.join(TR, "data", "vigilar_cierre.csv"), "a", encoding="utf-8") as f:
    f.write("2026-10-25,2026-10-25 22:16 UTC,NO_TOCA,,x\n2026-10-26,2026-10-26 22:16 UTC,OK,2,x\n")
assert est(2026, 10, 27)["alerta"] is False, "un sábado/domingo con NO_TOCA y el lunes OK lo ponen al día"
os.makedirs(os.path.join(TR, "site", "data"), exist_ok=True)
rec = []
fenviar = lambda m: (rec.append(m), (True, None))[1]  # noqa: E731
try:
    I.vigilar(TR, dt.datetime(2026, 10, 30, 9, 0, tzinfo=UTC), enviar=fenviar)
    I.vigilar(TR, dt.datetime(2026, 10, 30, 10, 0, tzinfo=UTC), enviar=fenviar)
except Exception as e:  # noqa: BLE001
    raise SystemExit("vigilar() en una carpeta vacía: " + type(e).__name__ + " " + str(e)[:100])
av = [m for m in rec if "vigilante del cierre" in m]
assert len(av) == 1 and "Revisa el disparo externo" in av[0], rec
print("10) OK integridad: aviso si el vigilante no corre en 2 días hábiles (una sola vez); fines de semana no cuentan")

# 7) los datos reales del repo: el cierre del 20-oct (21:30 UTC) corrió las 17 etapas
real = V.comprobar(V.leer_local(), "2026-10-20")
assert real["ok"] is True, real
print("7) OK data/ejecuciones.csv real:", real["mensaje"])
print("\nTODO OK · sin red, sin Telegram real")
