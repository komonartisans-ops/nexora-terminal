#!/usr/bin/env python3
"""Prueba del aviso previo con eventos y reacciones SIMULADOS en carpeta temporal. Telegram es una función falsa: NADA se envía y no se lee ningún token.
Uso:  python tools/prueba_aviso_previo.py"""
import csv
import datetime as dt
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import aviso_previo as A  # noqa: E402

for k in ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"):
    os.environ.pop(k, None)
UTC = dt.timezone.utc


def nueva_raiz():
    T = tempfile.mkdtemp(prefix="aviso_")
    os.makedirs(os.path.join(T, "site/data"))
    os.makedirs(os.path.join(T, "data"))
    for f in ("fedwatch.json", "contexto.json", "reacciones.json"):
        open(os.path.join(T, "site/data", f), "wb").write(open(os.path.join(ROOT, "site/data", f), "rb").read())
    open(os.path.join(T, "data/reacciones_eventos.csv"), "wb").write(open(os.path.join(ROOT, "data/reacciones_eventos.csv"), "rb").read())
    return T


def agenda(T, eventos):
    json.dump({"agenda": {"hoy": eventos, "proximos_7_dias": []}}, open(os.path.join(T, "site/data/agenda.json"), "w", encoding="utf-8"), ensure_ascii=False)


def ev(fecha, hora, nombre, imp="ALTA", **kw):
    return {"fecha": fecha, "fecha_et": fecha, "hora_ny": hora, "evento": nombre, "importancia": imp, **kw}


def en(fecha, hora_utc):
    return dt.datetime.fromisoformat(fecha + "T" + hora_utc).replace(tzinfo=UTC)


ENVIADOS = []


def falso_ok(txt):
    ENVIADOS.append(txt)
    return True, None


def falso_fallo(txt):
    return False, "HTTP 500 simulado"


def prohibido(txt):
    raise AssertionError("en modo seco NO se puede enviar")


FOMC = ev("2026-10-28", "14:00", "Decisión FOMC (Fed)")          # 14:00 ET = 18:00 UTC (EDT) = 19:00 Madrid (CET desde el 25-oct)
T0 = en("2026-10-28", "18:00:00")

# ---------------------------------------------------------------- 1) huso horario
T = nueva_raiz()
agenda(T, [FOMC, ev("2026-11-04", "14:00", "Decisión FOMC (Fed)")])
E = A.eventos_alta(T)
assert E[0]["t"] == T0 and E[0]["t"].astimezone(A.MAD).strftime("%H:%M") == "19:00"
assert E[1]["t"].astimezone(A.MAD).strftime("%H:%M") == "20:00", "tras el 1-nov Nueva York pasa a EST y Madrid sigue en CET: 14:00 ET = 20:00 Madrid"
print("1) OK husos: FOMC 28-oct 14:00 ET = 19:00 Madrid; 4-nov 14:00 ET = 20:00 Madrid")

# ---------------------------------------------------------------- 2) ventana 25-35 min, seco = no envía ni escribe
for m, esperado in ((36, 0), (35, 1), (30, 1), (25, 1), (24, 0)):
    T = nueva_raiz(); agenda(T, [FOMC])
    r = A.ejecutar(T0 - dt.timedelta(minutes=m), seco=True, raiz=T, enviar=prohibido)
    assert len([x for x in r if x[1] == "SECO"]) == esperado, (m, r)
    assert not os.path.exists(os.path.join(T, "data/avisos_previos.json")), "el modo seco no debe escribir estado"
print("2) OK ventana: 36 min no · 35, 30 y 25 min sí · 24 min no; modo seco no envía ni escribe")

# ---------------------------------------------------------------- 3) mensaje: contenido, ≤ 10 líneas, sin niveles ni recomendaciones
T = nueva_raiz(); agenda(T, [FOMC])
txt = A.ejecutar(T0 - dt.timedelta(minutes=30), seco=True, raiz=T)[0][2]
L = txt.split("\n")
assert len(L) <= 10, len(L)
t = txt
assert "19:00 Madrid" in t and "14:00 ET" in t and "FedWatch" in t and "futuros ZQ" in t and "diciembre" in t
assert "Régimen:" in t and "Tesis:" in t and "gamma" in t and "contexto.json" in t
assert "historial insuficiente (n=1)" in t
assert "comprar" not in t.lower().replace("recomendación de compra o venta", "") and "vender" not in t.lower()
print("3) OK mensaje de %d líneas:\n%s" % (len(L), txt))

# ---------------------------------------------------------------- 4) envío único y estado solo-añadir
T = nueva_raiz(); agenda(T, [FOMC])
ENVIADOS.clear()
r1 = A.ejecutar(T0 - dt.timedelta(minutes=31), raiz=T, enviar=falso_ok)
r2 = A.ejecutar(T0 - dt.timedelta(minutes=29), raiz=T, enviar=falso_ok)
assert [x[1] for x in r1] == ["ENVIADO"] and r2 == [] and len(ENVIADOS) == 1, "un único mensaje por evento"
est = json.load(open(os.path.join(T, "data/avisos_previos.json"), encoding="utf-8"))
k = list(est["avisos"])[0]
assert est["avisos"][k]["estado"] == "ENVIADO" and est["avisos"][k]["minutos_antes"] == 31.0
# solo-añadir: una clave existente no se modifica aunque otra pasada intente escribir otra cosa
antes = dict(est["avisos"][k])
A.guardar_estado(T, est, {k: {"estado": "OTRA COSA"}, "otra|clave": {"estado": "SIN AVISO"}})
est2 = json.load(open(os.path.join(T, "data/avisos_previos.json"), encoding="utf-8"))
assert est2["avisos"][k] == antes and "otra|clave" in est2["avisos"]
print("4) OK un solo mensaje por evento; el estado solo añade claves (la existente no cambia)")

# ---------------------------------------------------------------- 5) Telegram falla: no se da por avisado (se reintenta)
T = nueva_raiz(); agenda(T, [FOMC])
r = A.ejecutar(T0 - dt.timedelta(minutes=30), raiz=T, enviar=falso_fallo)
assert r[0][1] == "ERROR" and not json.load(open(os.path.join(T, "data/avisos_previos.json"), encoding="utf-8"))["avisos"]
r = A.ejecutar(T0 - dt.timedelta(minutes=28), raiz=T, enviar=falso_ok)
assert r[0][1] == "ENVIADO"
print("5) OK si Telegram falla no se marca como avisado y se reintenta dentro de la ventana")

# ---------------------------------------------------------------- 6) SIN AVISO: ningún run cayó en la ventana
T = nueva_raiz(); agenda(T, [FOMC])
A.ejecutar(T0 - dt.timedelta(hours=5), raiz=T, enviar=prohibido)         # primera pasada (fija creado_utc); aún no hay ventana
r = A.ejecutar(T0 - dt.timedelta(minutes=12), raiz=T, enviar=prohibido)    # el siguiente run llega tarde: ventana perdida
assert r[0][1] == "SIN AVISO"
est = json.load(open(os.path.join(T, "data/avisos_previos.json"), encoding="utf-8"))["avisos"]
v = est[list(est)[0]]
assert v["estado"] == "SIN AVISO" and "ningún run cayó" in v["motivo"] and "12 min" in v["motivo"]
assert A.ejecutar(T0 - dt.timedelta(minutes=5), raiz=T, enviar=prohibido) == [], "no se repite ni se envía tarde"
print("6) OK ventana perdida → «SIN AVISO» con motivo, sin aviso tardío inventado:", v["motivo"])
# función activada DESPUÉS de empezar la ventana: no se marca (no es un fallo de cobertura)
T = nueva_raiz(); agenda(T, [FOMC])
assert A.ejecutar(T0 - dt.timedelta(minutes=20), raiz=T, enviar=prohibido) == []
assert not json.load(open(os.path.join(T, "data/avisos_previos.json"), encoding="utf-8"))["avisos"]
print("   OK eventos anteriores a la activación de la función no se marcan «sin aviso»")

# ---------------------------------------------------------------- 7) contaminación
T = nueva_raiz(); agenda(T, [ev("2026-10-28", "08:30", "IPC EE. UU. (CPI)"), ev("2026-10-28", "09:15", "Precios de producción (PPI)")])
tx = A.ejecutar(en("2026-10-28", "12:00:00"), seco=True, raiz=T)[0][2]       # IPC 12:30 UTC → faltan 30 min
assert "Coincide con otro dato de importancia alta" in tx and "Precios de producción (PPI)" in tx and "+45 min" in tx and "contaminadas" in tx
print("7) OK contaminación: el IPC avisa del PPI 45 min después")

# ---------------------------------------------------------------- 8) consenso: SIN DATO salvo que la agenda lo traiga
assert "Consenso: SIN DATO" in tx
T = nueva_raiz(); agenda(T, [ev("2026-10-28", "08:30", "IPC EE. UU. (CPI)", consenso="0,3 % m/m (fuente oficial X)")])
tx2 = A.ejecutar(en("2026-10-28", "12:00:00"), seco=True, raiz=T)[0][2]
assert "Consenso: 0,3 % m/m (fuente oficial X)" in tx2 and "FedWatch" not in tx2
print("8) OK consenso SIN DATO si no lo trae la agenda; si lo trae, se cita; IPC no muestra FedWatch")

# ---------------------------------------------------------------- 9) evento sin hora confirmada: no se avisa ni se inventa
T = nueva_raiz(); agenda(T, [{"fecha": "2026-10-28", "fecha_et": "2026-10-28", "hora_ny": None, "evento": "Resultados Microsoft (MSFT)", "importancia": "ALTA"}])
assert A.eventos_alta(T) == []
print("9) OK ALTA sin hora confirmada: se ignora (no se inventa hora)")

# ---------------------------------------------------------------- 10) historial con n ≥ 5: medianas del 2Y y SE CONFIRMA vs INVERSIÓN
T = nueva_raiz(); agenda(T, [ev("2026-10-28", "08:30", "IPC EE. UU. (CPI)")])
filas = []
d5 = [2.0, 4.0, 6.0, 8.0, 10.0, 12.0]
d60 = [1.0, 3.0, 5.0, 7.0, 9.0, 11.0]
for i, (a, b) in enumerate(zip(d5, d60)):
    for fase, val in (("T+5", a), ("T+60", b)):
        filas.append({"evento_id": f"IPC-SIM-{i}", "tipo": "IPC", "fase": fase, "d_y2_pb": val, "origen": "vivo"})
with open(os.path.join(T, "data/reacciones_eventos.csv"), "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["evento_id", "tipo", "fase", "d_y2_pb", "origen"]); w.writeheader(); w.writerows(filas)
giro = ["SE CONFIRMA", "SE CONFIRMA", "SE CONFIRMA", "INVERSIÓN · NQ cae", "PARCIAL", "SE CONFIRMA"]
json.dump({"eventos": [{"id": f"IPC-SIM-{i}", "tipo": "IPC", "giro_fases": {"CIERRE": g}} for i, g in enumerate(giro)]}, open(os.path.join(T, "site/data/reacciones.json"), "w", encoding="utf-8"), ensure_ascii=False)
h = A.ejecutar(en("2026-10-28", "12:00:00"), seco=True, raiz=T)[0][2].split("\n")[-2]
assert "n=6" in h and "+7,0 pb" in h and "+6,0 pb" in h and "SE CONFIRMA 67 % vs INVERSIÓN 17 %" in h, h
print("10) OK historial n=6:", h)
# n < 5 → insuficiente
with open(os.path.join(T, "data/reacciones_eventos.csv"), "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["evento_id", "tipo", "fase", "d_y2_pb", "origen"]); w.writeheader(); w.writerows(filas[:6])    # 3 eventos
h = A.ejecutar(en("2026-10-28", "12:00:00"), seco=True, raiz=T)[0][2].split("\n")[-2]
assert "historial insuficiente (n=3)" in h, h
print("    OK con 3 eventos:", h)

# ---------------------------------------------------------------- 11) varios eventos y concurrencia lógica
T = nueva_raiz(); agenda(T, [FOMC, ev("2026-10-28", "08:30", "IPC EE. UU. (CPI)")])
ENVIADOS.clear()
A.ejecutar(en("2026-10-28", "12:00:00"), raiz=T, enviar=falso_ok)      # avisa el IPC
A.ejecutar(en("2026-10-28", "17:30:00"), raiz=T, enviar=falso_ok)      # avisa el FOMC
A.ejecutar(en("2026-10-28", "17:31:00"), raiz=T, enviar=falso_ok)
assert len(ENVIADOS) == 2 and "IPC" in ENVIADOS[0] and "FOMC" in ENVIADOS[1]
print("11) OK dos eventos el mismo día: un mensaje cada uno, en su ventana")
# ---------------------------------------------------------------- 12) resultados de empresas: hora típica solo si la fuente da el momento y la fecha está confirmada
T = nueva_raiz(); agenda(T, [])
def emp(nombre, fecha, momento, nota, imp="ALTA"):
    return {"fecha": fecha, "hora_ny": "", "evento": nombre, "importancia": imp, "que_mirar": f"BPA estimado $6.67 · {momento}", "fuente": "Nasdaq / Zacks", "nota": nota}
json.dump({"eventos": [emp("Resultados Meta Platforms (META)", "2026-10-21", "después del cierre", "fecha CONFIRMADA"),
                       emp("Resultados Microsoft (MSFT)", "2026-10-28", "antes de la apertura", "fecha CONFIRMADA"),
                       emp("Resultados Tesla (TSLA)", "2026-10-21", "momento no publicado", "fecha CONFIRMADA"),
                       emp("Resultados Alphabet (GOOGL)", "2026-10-28", "después del cierre", "fecha ESTIMADA"),
                       emp("Resultados Netflix (NFLX)", "2026-10-20", "después del cierre", "fecha CONFIRMADA", imp="MEDIA")]},
          open(os.path.join(T, "site/data/calendario.json"), "w", encoding="utf-8"), ensure_ascii=False)
E = {e["evento"]: e for e in A.eventos_alta(T)}
assert set(E) == {"Resultados Meta Platforms (META)", "Resultados Microsoft (MSFT)"}, set(E)
meta, msft = E["Resultados Meta Platforms (META)"], E["Resultados Microsoft (MSFT)"]
assert meta["t"] == en("2026-10-21", "20:05:00") and msft["t"] == en("2026-10-28", "12:00:00"), (meta["t"], msft["t"])      # 16:05 ET y 08:00 ET en horario de verano
for e in (meta, msft):
    ini = (e["t"] - dt.timedelta(minutes=35)).hour
    assert 11 <= ini <= 21, "la ventana de aviso debe caer dentro de la franja 11-21 UTC de la tarea B1"
tx = A.ejecutar(meta["t"] - dt.timedelta(minutes=30), seco=True, raiz=T)[0][2]
assert "Hora típica, no confirmada" in tx and "después del cierre" in tx and "16:05 ET" in tx and "Consenso: BPA estimado $6,67" not in tx
assert "Consenso: BPA estimado $6.67 [Nasdaq / Zacks]" in tx and "no resultados de empresas" in tx
tx2 = A.ejecutar(msft["t"] - dt.timedelta(minutes=30), seco=True, raiz=T)[0][2]
assert "antes de la apertura" in tx2 and "08:00 ET" in tx2 and "13:00 Madrid" in tx2 and len(tx.splitlines()) <= 10
print("12) OK resultados: META «después del cierre» → 16:05 ET (hora típica, no confirmada) y MSFT «antes de la apertura» → 08:00 ET; TSLA sin momento y GOOGL con fecha estimada NO se avisan")
print("    aviso de META (ejemplo):"); print(tx)
assert "telegram" not in sys.modules or not os.environ.get("TELEGRAM_TOKEN")
print("\nTODO OK · sin envíos reales ni lectura de token")
