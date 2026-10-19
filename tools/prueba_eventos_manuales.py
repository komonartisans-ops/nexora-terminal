#!/usr/bin/env python3
"""Prueba de los eventos MANUALES (data/eventos_manuales.csv) con datos SIMULADOS (sin red, carpeta temporal, Telegram falso): validación de filas, calendario, agenda,
aviso previo y contaminación de las fases. Uso:  python tools/prueba_eventos_manuales.py"""
import datetime as dt
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import agenda as AG  # noqa: E402
import aviso_previo as A  # noqa: E402
import calendario as C  # noqa: E402
import eventos_manuales as EM  # noqa: E402
import reaccion as RE  # noqa: E402

for k in ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"):
    os.environ.pop(k, None)
UTC = dt.timezone.utc
D = dt.date


def nueva(csv_txt):
    T = tempfile.mkdtemp(prefix="man_")
    for d in ("data", "site/data"):
        os.makedirs(os.path.join(T, d))
    open(os.path.join(T, "data", "eventos_manuales.csv"), "w", encoding="utf-8", newline="").write(csv_txt)
    for f in ("fedwatch.json", "contexto.json", "reacciones.json"):
        open(os.path.join(T, "site/data", f), "wb").write(open(os.path.join(ROOT, "site/data", f), "rb").read())
    open(os.path.join(T, "data/reacciones_eventos.csv"), "wb").write(open(os.path.join(ROOT, "data/reacciones_eventos.csv"), "rb").read())
    return T


CAB = "fecha,hora_et,evento,importancia,url,añadido_por\n"
BUENO = (CAB + "2026-11-05,10:00,Reunión ministerial OPEP+,ALTA,https://www.opec.org/,ruiz\n"
         '2026-11-06,,"Discurso, presidente del BCE",MEDIA,https://www.ecb.europa.eu/,ruiz\n'
         "2026-11-07,15:30,Dato menor,baja,https://example.org/dato,ruiz\n")

# ---------------------------------------------------------------- 1) lectura y validación de filas
E, err = EM.leer(nueva(BUENO))
assert not err and [(e["fecha"].isoformat(), e["hora_et"], e["evento"], e["importancia"]) for e in E] == [
    ("2026-11-05", "10:00", "Reunión ministerial OPEP+", "ALTA"), ("2026-11-06", "", "Discurso, presidente del BCE", "MEDIA"), ("2026-11-07", "15:30", "Dato menor", "BAJA")], (E, err)
malas = [("2026-13-40,10:00,X,ALTA,https://a.org/,yo", "fecha"), ("2026-11-05,25:00,X,ALTA,https://a.org/,yo", "hora_et"), ("2026-11-05,10:00,,ALTA,https://a.org/,yo", "evento"),
         ("2026-11-05,10:00,X,CRÍTICA,https://a.org/,yo", "importancia"), ("2026-11-05,10:00,X,ALTA,,yo", "url"), ("2026-11-05,10:00,X,ALTA,http://a.org/,yo", "url"),
         ("2026-11-05,10:00,X,ALTA,javascript:alert(1),yo", "url"), ("2026-11-05,10:00,X,ALTA,https://a.org/,", "añadido_por"), ("2026-11-05,10:00," + "x" * 121 + ",ALTA,https://a.org/,yo", "evento")]
for fila, campo in malas:
    E, err = EM.leer(nueva(CAB + fila + "\n"))
    assert E == [] and len(err) == 1 and "línea 2" in err[0] and campo in err[0], (fila, err)
E, err = EM.leer(nueva(CAB + "2026-11-05,10:00,Bueno,ALTA,https://a.org/,yo\n2026-11-05,10:00,Malo,ALTA,,yo\n2026-11-05,10:00,Bueno,ALTA,https://a.org/,yo\n\n"))
assert [e["evento"] for e in E] == ["Bueno"] and len(err) == 1 and "línea 3" in err[0], (E, err)           # una fila mala no rompe las demás; el duplicado y la línea vacía se ignoran
E, err = EM.leer(nueva("fecha,evento\n2026-11-05,X\n"))
assert E == [] and "falta" in err[0] and "hora_et" in err[0]
assert EM.leer(tempfile.mkdtemp(prefix="vacia_")) == ([], []), "sin archivo: nada y sin error"
assert EM.leer(nueva(CAB)) == ([], []), "solo cabecera: nada"
print("1) OK lectura: 3 filas válidas (con comillas y hora vacía); 9 tipos de fila inválida se rechazan con su línea y motivo (fecha, hora, evento, importancia, URL https obligatoria, añadido_por); una fila mala no rompe las demás")

# ---------------------------------------------------------------- 2) calendario: «manual», hora ET → Madrid, ventana de fechas
T = nueva(BUENO)
ev, err = EM.para_calendario(T, D(2026, 11, 1), D(2026, 11, 30), C.ev)
assert not err and [(x["fecha"], x["hora_ny"], x["hora_madrid"], x["importancia"], x["origen"]) for x in ev] == [
    ("2026-11-05", "10:00", "16:00", "ALTA", "manual"), ("2026-11-06", "", "", "MEDIA", "manual"), ("2026-11-07", "15:30", "21:30", "BAJA", "manual")], ev       # 5-nov: EST (UTC−5) y Madrid CET: +6 h
assert ev[0]["fuente"] == "Manual · añadido por ruiz" and ev[0]["url"] == "https://www.opec.org/" and ev[0]["nota"] == "manual · añadido por ruiz" and "hora sin confirmar" in ev[1]["nota"]
assert [x["fecha"] for x in EM.para_calendario(T, D(2026, 11, 6), D(2026, 11, 6), C.ev)[0]] == ["2026-11-06"]
ev_dst, _ = EM.para_calendario(nueva(CAB + "2026-10-28,10:00,Antes del cambio de hora,ALTA,https://a.org/,yo\n"), D(2026, 10, 1), D(2026, 12, 1), C.ev)
assert ev_dst[0]["hora_madrid"] == "15:00", "28-oct: EDT (UTC−4) y Madrid CET (+1 h tras el 25-oct): +5 h"
print("2) OK calendario: los eventos entran con origen «manual», fuente «Manual · añadido por …», su URL y hora de Madrid correcta (+6 h en noviembre, +5 h el 28-oct); sin hora queda «hora sin confirmar»")

# ---------------------------------------------------------------- 3) agenda: ALTA y MEDIA salen marcadas; BAJA no
cal = {"eventos": ev, "fed_vigilar": []}
B = AG.bloque(cal, hoy=D(2026, 11, 4), dias=7)
vis = B["hoy"] + B["proximos_7_dias"]
assert [(x["evento"], x["importancia"], x.get("origen"), x["hora_ny"]) for x in vis] == [("Reunión ministerial OPEP+", "ALTA", "manual", "10:00"), ("Discurso, presidente del BCE", "MEDIA", "manual", None)], vis
assert vis[0]["url"] == "https://www.opec.org/" and vis[0]["nota"].startswith("manual") and "Dato menor" not in json.dumps(vis, ensure_ascii=False)
assert any(t["tipo"] == "MANUAL" for t in AG.tabla_importancia())
print("3) OK agenda: la reunión ALTA y el discurso MEDIA salen con «origen: manual», URL y nota; la BAJA no se muestra (igual que los oficiales); la tabla de importancia explica el tipo MANUAL")

# ---------------------------------------------------------------- 4) aviso previo: un evento ALTA manual con hora avisa 30 min antes, marcado como manual
json.dump({"agenda": B}, open(os.path.join(T, "site/data/agenda.json"), "w", encoding="utf-8"), ensure_ascii=False)
av = A.eventos_alta(T)
assert [(x["evento"], x["hora_ny"], x["tipo"]) for x in av] == [("Reunión ministerial OPEP+", "10:00", None)], av
t_evento = dt.datetime(2026, 11, 5, 15, 0, tzinfo=UTC)               # 10:00 ET = 15:00 UTC
enviados = []
fake = lambda x: (enviados.append(x), (True, None))[1]                # noqa: E731
r = A.ejecutar(t_evento - dt.timedelta(minutes=30), raiz=T, enviar=fake)
assert len(r) == 1 and len(enviados) == 1, r
txt = enviados[0]
assert "Aviso previo · Reunión ministerial OPEP+" in txt and "Evento MANUAL" in txt and "manual · añadido por ruiz" in txt and "tipo de evento no reconocido" in txt and len(txt.splitlines()) <= 10, txt
assert A.ejecutar(t_evento - dt.timedelta(minutes=29), raiz=T, enviar=fake) == [] or len(enviados) == 1, "un aviso por evento"
assert A.ejecutar(t_evento - dt.timedelta(minutes=120), raiz=T, enviar=fake, seco=True) == [], "fuera de la ventana de 25-35 min no avisa"
# sin hora no hay aviso (no se inventa)
sin_hora = [x for x in vis if not x["hora_ny"]]
assert sin_hora and A.eventos_alta(T) and all(x["hora_ny"] for x in A.eventos_alta(T))
print("4) OK aviso previo: la reunión ALTA con hora avisa 30 min antes con la línea «Evento MANUAL (manual · añadido por ruiz)»; un solo aviso; el evento sin hora no avisa")

# ---------------------------------------------------------------- 5) contaminación: un ALTA manual entre el dato y la fase marca la fase como contaminada
oficial = {"id": "IPC-2026-11-05", "tipo": "IPC", "evento": "IPC", "fecha": D(2026, 11, 5), "hora_ny": "08:30"}
altos = RE._con_manuales([oficial], raiz=T)
assert [x["id"] for x in altos] == ["IPC-2026-11-05", "MANUAL-2026-11-05-1000"] and altos[1]["manual"] is True, altos
t_fase = RE.t_evento(oficial) + dt.timedelta(minutes=120)            # T+120 = 10:30 ET: la reunión de las 10:00 ET cae entre el dato y la fase
assert RE.contaminantes(oficial, t_fase, altos) == ["MANUAL-2026-11-05-1000"]
assert RE.contaminantes(oficial, RE.t_evento(oficial) + dt.timedelta(minutes=60), altos) == [], "T+60 = 09:30 ET: aún no ha llegado la reunión de las 10:00"
assert RE.contaminantes(oficial, t_fase, [oficial]) == [], "sin el manual, la fase queda limpia"
assert [x["id"] for x in RE._con_manuales([oficial], raiz=nueva(CAB + "2026-11-05,,Sin hora,ALTA,https://a.org/,yo\n2026-11-05,09:00,Media,MEDIA,https://a.org/,yo\n"))] == ["IPC-2026-11-05"], "sin hora o con importancia MEDIA no contamina"
print("5) OK contaminación: la reunión manual ALTA de las 10:00 ET contamina el T+120 de un IPC de las 8:30 ET (no el T+60); sin hora o MEDIA no contamina; no se mide como evento propio")

# ---------------------------------------------------------------- 6) el archivo real del repositorio es válido
E, err = EM.leer(ROOT)
assert not err, err
print("6) OK data/eventos_manuales.csv del repositorio: %d evento(s) válidos, sin errores" % len(E))
print("\nTODO OK · sin red, sin envíos reales")
