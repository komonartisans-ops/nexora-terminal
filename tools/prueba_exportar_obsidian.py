#!/usr/bin/env python3
"""Pruebas del exportador a Obsidian (Fase 20). Sin red, sin Telegram real y sin tocar la bóveda de verdad: todo en carpetas temporales
(un repo git sintético con commits fechados, una bóveda con notas «escritas a mano» y un repo privado simulado con una carpeta).
Uso: PYTHONUTF8=1 python tools/prueba_exportar_obsidian.py"""
import csv
import datetime as dt
import gzip
import hashlib
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(RAIZ, "engine"))
import exportar_obsidian as X  # noqa: E402
import integridad as I  # noqa: E402

UTC = dt.timezone.utc
TMP = tempfile.mkdtemp(prefix="nexora_obs_")
REPO, BOV, PRIV, EST = (os.path.join(TMP, x) for x in ("repo", "boveda", "priv", "estado.json"))


def sh(cwd, *a, fecha=None):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    if fecha:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = fecha
    r = subprocess.run(["git", "-C", cwd, *a], capture_output=True, text=True, encoding="utf-8", env=env)
    assert r.returncode == 0, (a, r.stderr)
    return r.stdout


def w(ruta, texto, modo="w"):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, modo, encoding="utf-8", newline="") as f:
        f.write(texto)


def ctx(dia, hora, etiqueta, gen=None):
    return {"generado_utc": gen or f"{dia} {hora[:2]}:{hora[2:]} UTC",
            "mercado": {"activos": {"dxy": {"valor": 101.5}, "vix": {"valor": 18.0}}},
            "tesis": {"tesis_por_activo": [{"activo": "Oro", "etiqueta": etiqueta, "viento_semana": "A FAVOR", "motor_propio": "dólar", "veredicto_motor_propio": "MIXTO",
                                            "a_favor": ["baja el dólar"], "en_contra": ["sube el tipo real"], "tesis": f"Texto de la tesis {etiqueta}"}], "vigilar": ["Fed 28-oct"]},
            "regimen_macro": {"cuadrante": "REFLACIÓN", "fuerza": "crecimiento +1", "riesgo": "RISK-ON", "liquidez": "NEUTRAL", "concordancia_monitores": "X", "motor": "Y", "contradicciones": []},
            "agenda": {"hoy": [{"fecha": dia, "importancia": "ALTA", "hora_madrid": "14:30", "evento": "IPC"}]},
            "fedwatch_y_tipos": {"reuniones": [{"reunion": "2026-10-28", "prob_subida_pct": 8.0, "prob_mantiene_pct": 92.0, "prob_bajada_pct": 0}], "tipos_tesoro": {}},
            "credito": {"estado": "NORMAL", "diferenciales": {"hy": {"pb": 300, "d5_pb": 1}}}}


def gz(ruta, obj):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with gzip.open(ruta, "wt", encoding="utf-8") as f:
        json.dump(obj, f)


def snap_arbol(raiz):
    out = {}
    for dp, _, fs in os.walk(raiz):
        for f in fs:
            p = os.path.join(dp, f)
            out[os.path.relpath(p, raiz)] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return out


# ---------------------------------------------------------------- escenario: repo sintético con historia real de git
sh(TMP, "init", "-q", "-b", "main", REPO)
w(os.path.join(REPO, "docs", "A.md"), "# Doc A\n\nversión 1\n")
w(os.path.join(REPO, "data", "registro_tesis.csv"), "fecha,activo,tesis,puntuacion,motores,precio_referencia,capturado_utc\n"
  "2026-10-19,Oro,SIN TESIS,0,,4000,2026-10-19 10:00 UTC\n2026-10-20,Oro,ALCISTA DÉBIL,3,dolar,4010,2026-10-20 10:00 UTC\n2026-10-21,Oro,ALCISTA DÉBIL,3,dolar,4020,2026-10-21 10:00 UTC\n")
w(os.path.join(REPO, "data", "ejecuciones.csv"), "capturado_utc,modo,evento,etapas_ok,etapas_fallo,duracion_s,run_id\n"
  "2026-10-20 21:30 UTC,cierre,workflow_dispatch,\"precios,gamma\",,500,1\n2026-10-21 05:30 UTC,diario,workflow_dispatch,\"precios\",fedwatch,100,2\n")
w(os.path.join(REPO, "data", "vigilar_cierre.csv"), "fecha,ejecutado_utc,resultado,run_id_cierre,detalle\n2026-10-20,2026-10-20 22:15 UTC,OK,1,16/16\n")
w(os.path.join(REPO, "data", "discrepancias_revisadas.csv"), "id,registrada_utc,clave,estado,motivo,revisor,dif_pct_ref,signo_ref,nota\nX|1,2026-10-20 07:18 UTC,BRENT,REVISADA,físico frente a futuro,Ruiz,16.19,-1,\n")
w(os.path.join(REPO, "data", "xau_spot_contraste.csv"), "fecha,hora_utc,spot_principal,estado,spot_fuente,spot_usado,ratio_fuente,swiss_precio,dif_swiss_pct,spot_gc_implicito,dif_gc_pct\n2026-10-20,21:31,4025.3,OK,gold-api,4025.3,SESION,4024.9,-0.01,,\n")
gz(os.path.join(REPO, "data", "historico_contexto", "2026-10-20", "0600.json.gz"), ctx("2026-10-20", "0600", "SIN TESIS"))
gz(os.path.join(REPO, "data", "historico_contexto", "2026-10-20", "2357.json.gz"), ctx("2026-10-20", "2357", "ALCISTA DÉBIL"))
gz(os.path.join(REPO, "data", "historico_contexto", "2026-10-21", "2357.json.gz"), ctx("2026-10-21", "2357", "ALCISTA DÉBIL"))
w(os.path.join(REPO, "site", "data", "gamma_oro.json"), json.dumps({"sesion": "2026-10-19", "regimen": "NEGATIVA", "niveles": [], "linea": "XAU viejo"}))
w(os.path.join(REPO, "site", "data", "integridad.json"), json.dumps({"resumen": {"texto": "Integridad: 27/28 al día"}, "discrepancias_abiertas": []}))
sh(REPO, "add", "-A")
sh(REPO, "commit", "-q", "-m", "Fase 1: arranque\n\nPorque hace falta una base.", fecha="2026-10-20T10:00:00+00:00")
# el cierre del 20-oct corre pasada la medianoche UTC (como el del 22-oct real): la sesión 2026-10-20 llega a las 00:18 del día 21
w(os.path.join(REPO, "site", "data", "gamma_oro.json"), json.dumps({"sesion": "2026-10-20", "regimen": "POSITIVA", "niveles": [{"clave": "flip", "xau": 4100.0}, {"clave": "call_wall", "xau": 4150.0}, {"clave": "put_wall", "xau": 3900.0}],
                                                                  "max_gamma": {"idx": 3900.0, "tipo": "acelera"}, "em_xau": 55.0, "em": {"pct": 1.4}, "linea": "XAU tesis=alcista;flip=4100.0;spot=dudoso"}))
sh(REPO, "commit", "-q", "-am", "datos cierre 2026-10-21 00:18 UTC [skip ci]", fecha="2026-10-21T00:18:00+00:00")
w(os.path.join(REPO, "site", "data", "gamma_oro.json"), json.dumps({"sesion": "2026-10-21", "regimen": "NEGATIVA", "niveles": [], "linea": "XAU sesion 21"}))
sh(REPO, "commit", "-q", "-am", "datos cierre 2026-10-21 21:32 UTC [skip ci]", fecha="2026-10-21T21:32:00+00:00")
w(os.path.join(REPO, "tools", "x.py"), "# nada\n")
sh(REPO, "add", "-A")
sh(REPO, "commit", "-q", "-m", "Corrige el error del ratio\n\nEl ratio salía con la fecha equivocada.\n\nCo-Authored-By: x", fecha="2026-10-21T22:00:00+00:00")

# ---------------------------------------------------------------- bóveda con notas escritas a mano
HAND = {
    "60_Market_Intelligence/07_Sistema_NEXORA/Bitácora NEXORA 2026-10.md": "---\ntags: [nexora]\n---\n# Bitácora a mano\n\nLo escribí yo. Commit viejo `abcdef0`.\n",
    "60_Market_Intelligence/07_Sistema_NEXORA/Estado y pendientes.md": "---\ntags: [nexora]\n---\n# Estado a mano\n- [ ] cosa mía\n",
    "60_Market_Intelligence/07_Sistema_NEXORA/00 Sistema NEXORA (MOC).md": "# MOC a mano\n- [[Estado y pendientes]]\n",
    "60_Market_Intelligence/01_State/Global Market State.md": "---\nas_of: \"2026-10-01\"\n---\n# Estado viejo\n",
    "60_Market_Intelligence/00_MOC/Market Intelligence.md": "# MOC de Market Intelligence\n",
    "60_Market_Intelligence/04_Theses/T-20261001-ORO.md": "# tesis vieja del sistema anterior\n",
    "60_Market_Intelligence/02_Daily_Snapshots/2026-10-01.md": "# snapshot viejo\n",
}
for rel, t in HAND.items():
    w(os.path.join(BOV, *rel.split("/")), t)
ANTES = snap_arbol(BOV)
HOY = "2026-10-22"


def pasada(hoy=HOY, privado=None):
    return X.exportar({"boveda": BOV, "publico": REPO, "privado": privado, "estado": EST, "hoy": hoy}, lambda m: None)


def cambios(r):
    q = r["res"]
    return len(q["creadas"]) + len(q["actualizadas"]) + len(q["ampliadas"]) + len(q["v2"])


def leer(rel):
    return open(os.path.join(BOV, *rel.split("/")), encoding="utf-8", newline="").read()


# 0) zona permitida y secretos
b = X.Boveda(BOV, X.Estado(EST))
for malo in ("00_sistema/x.md", "60_Market_Intelligence/../00_sistema/x.md", "10_Diario/otro/x.md", "Petróleo.md"):
    try:
        b.ruta(malo)
        raise AssertionError("debió rechazar " + malo)
    except ValueError:
        pass
b.ruta("10_Diario/Premercado/2026-10-22 Premercado.md")
b.ruta("60_Market_Intelligence/05_Analisis/x.md")
assert "ghp_" not in X.limpiar("fatal: https://x-access-token:ghp_AbCdEf1234567890AbCdEf@github.com/a/b y ghp_AbCdEf1234567890AbCdEf12") and "github_pat_" not in X.limpiar("github_pat_11ABCDEFG0123456789_abcdefghij")
print("0) OK solo se escribe en 60_Market_Intelligence/ y 10_Diario/Premercado/ (rutas fuera o con «..» rechazadas); los tokens se enmascaran en el log")

# 1) primera pasada: snapshots (SIN DATO y con datos), tesis, docs, registros, bitácora; la nota de ayer cerrada, hoy no
r1 = pasada()
assert r1["dias_cerrados"] == 20 and r1["snapshots_nuevos"] == 20, r1             # del 02-oct al 21-oct (el 22 es «hoy» y no tiene cierre)
s_sin = leer("60_Market_Intelligence/02_Daily_Snapshots/2026-10-05.md")
assert "SIN DATO" in s_sin and "No se reconstruye nada" in s_sin
s20 = leer("60_Market_Intelligence/02_Daily_Snapshots/2026-10-20.md")
assert 'tesis_oro: "ALCISTA DÉBIL"' in s20 and "IPC" in s20 and "REFLACIÓN" in s20 and "14:30" in s20, s20
assert "POSITIVA" in s20 and "acelera" in s20 and "spot=dudoso" in s20, "el cierre pasada la medianoche UTC debe usarse (sesión 2026-10-20 del commit de las 00:18)"
assert "OK" in s20 and "verificado" in s20 and "4025" in s20.replace(",", "").replace(".", ""), s20      # estado del spot (OK = verificado) y fuentes
assert not os.path.exists(os.path.join(BOV, "60_Market_Intelligence", "02_Daily_Snapshots", "2026-10-22.md")), "hoy no está cerrado: no se escribe"
print("1) OK primera pasada: 20 snapshots (del 02-oct al 21-oct; los días sin datos son «SIN DATO», nada reconstruido), hoy sin escribir hasta el cierre; cierre tardío (00:18 UTC) usado")

# 2) tesis: una nota solo cuando cambia, con enlace a la anterior (la del sistema anterior para la primera)
t1 = leer("60_Market_Intelligence/04_Theses/T-20261019-ORO.md")
t2 = leer("60_Market_Intelligence/04_Theses/T-20261020-ORO.md")
assert "T-20261001-ORO" in t1 and "primera" not in t1.lower().split("anterior")[1][:30], t1[:600]
assert "[[04_Theses/T-20261019-ORO" in t2 and "SIN TESIS → ALCISTA DÉBIL" in t2, t2[:800]
assert not os.path.exists(os.path.join(BOV, "60_Market_Intelligence", "04_Theses", "T-20261021-ORO.md")), "el 21 la tesis no cambió: no hay nota"
print("2) OK tesis: notas el 19 (enlaza a la del sistema anterior) y el 20 (enlaza a la anterior); el 21 no cambió y no hay nota")

# 3) las notas escritas a mano solo se amplían (el principio de cada archivo no cambia)
for rel, original in HAND.items():
    nuevo = leer(rel)
    if rel.endswith("T-20261001-ORO.md") or rel.endswith("2026-10-01.md"):
        assert nuevo == original, rel
    else:
        assert nuevo.startswith(original.rstrip("\n")), f"{rel}: lo escrito a mano se reescribió"
bit = leer("60_Market_Intelligence/07_Sistema_NEXORA/Bitácora NEXORA 2026-10.md")
assert "Corrige el error del ratio" in bit and "[fix]" in bit and "por qué: El ratio salía con la fecha equivocada." in bit and "Co-Authored" not in bit
assert "datos cierre" not in bit, "los commits automáticos de datos no van a la bitácora"
assert "[fallo de datos] la etapa «fedwatch»" in bit and "[revisión de datos] BRENT" in bit
print("3) OK lo escrito a mano queda intacto (solo se añade al final); bitácora: commit fix con su porqué, fallo de etapa y revisión de datos; sin commits de bots")

# 4) idempotente: sin novedades no se toca nada
arbol = snap_arbol(BOV)
r2 = pasada()
assert cambios(r2) == 0 and snap_arbol(BOV) == arbol, (r2["res"])
print("4) OK idempotente: segunda pasada sin cambios, ni un byte distinto en la bóveda")

# 5) snapshot inmutable aunque cambien los datos de origen; no se borra nada
w(os.path.join(REPO, "data", "registro_tesis.csv"), "fecha,activo,tesis,puntuacion,motores,precio_referencia,capturado_utc\n2026-10-20,Oro,BAJISTA,9,x,1,x\n")
w(os.path.join(REPO, "site", "data", "gamma_oro.json"), "{}")
s20b = leer("60_Market_Intelligence/02_Daily_Snapshots/2026-10-20.md")
pasada()
assert leer("60_Market_Intelligence/02_Daily_Snapshots/2026-10-20.md") == s20b == s20
assert set(ANTES) <= set(snap_arbol(BOV)), "no se borra nada"
sh(REPO, "checkout", "--", ".")
w(os.path.join(REPO, "data", "registro_tesis.csv"), open(os.path.join(REPO, "data", "registro_tesis.csv"), encoding="utf-8").read())
sh(REPO, "checkout", "--", "data/registro_tesis.csv")
print("5) OK snapshot ya escrito: no se vuelve a tocar aunque cambie el origen; ningún archivo previo desaparece")

# 6) nota gestionada editada por Ruiz → la pasada siguiente crea «(NEXORA v2)» y no pisa su edición
doc = "60_Market_Intelligence/07_Sistema_NEXORA/Docs/A.md"
assert "versión 1" in leer(doc)
editada = leer(doc) + "\nMI COMENTARIO PERSONAL\n"
w(os.path.join(BOV, *doc.split("/")), editada)
w(os.path.join(REPO, "docs", "A.md"), "# Doc A\n\nversión 2\n")
sh(REPO, "add", "-A")
sh(REPO, "commit", "-q", "-m", "docs: version 2", fecha="2026-10-21T22:10:00+00:00")
r3 = pasada()
v2 = doc[:-3] + " (NEXORA v2).md"
assert leer(doc) == editada, "la edición de Ruiz se pisó"
assert "versión 2" in leer(v2) and v2 in r3["res"]["v2"] and any("fue editada" in a for a in r3["res"]["avisos"]), r3["res"]
r3b = pasada()
assert cambios(r3b) == 0 and leer(doc) == editada
w(os.path.join(REPO, "docs", "A.md"), "# Doc A\n\nversión 3\n")
sh(REPO, "add", "-A")
sh(REPO, "commit", "-q", "-m", "docs: version 3", fecha="2026-10-21T22:20:00+00:00")
pasada()
assert "versión 3" in leer(v2) and leer(doc) == editada, "la v2 (nuestra) se actualiza; la editada sigue intacta"
print("6) OK nota editada a mano: la siguiente pasada crea «… (NEXORA v2).md», avisa y no pisa su edición; la v2 se mantiene al día y la pasada siguiente no cambia nada")

# 7) un nota gestionada sin editar sí se actualiza cuando cambia el origen (Registros)
reg = "60_Market_Intelligence/07_Sistema_NEXORA/Registros/Discrepancias revisadas.md"
a = leer(reg)
with open(os.path.join(REPO, "data", "discrepancias_revisadas.csv"), "a", encoding="utf-8", newline="") as f:
    f.write("X|2,2026-10-21 07:18 UTC,JOLTS,REVISADA,pendiente,Ruiz,,,\n")
pasada()
assert leer(reg) != a and "JOLTS" in leer(reg) and "github.com/komonartisans-ops/nexora-terminal/blob/main/data/discrepancias_revisadas.csv" in leer(reg)
assert open(os.path.join(REPO, "data", "discrepancias_revisadas.csv"), encoding="utf-8").read().count("\n") == 3, "el CSV no se edita desde el exportador"
print("7) OK registro sin editar: se actualiza con las últimas filas y enlaza al CSV (que no se toca)")

# 8) bitácora: sin duplicados al repetir, y un commit nuevo añade UNA línea al final
n0 = leer("60_Market_Intelligence/07_Sistema_NEXORA/Bitácora NEXORA 2026-10.md")
pasada()
assert leer("60_Market_Intelligence/07_Sistema_NEXORA/Bitácora NEXORA 2026-10.md") == n0
w(os.path.join(REPO, "tools", "y.py"), "# y\n")
sh(REPO, "add", "-A")
sh(REPO, "commit", "-q", "-m", "Nueva función de prueba", fecha="2026-10-21T22:30:00+00:00")
pasada()
n1 = leer("60_Market_Intelligence/07_Sistema_NEXORA/Bitácora NEXORA 2026-10.md")
assert n1.startswith(n0) and n1.count("Nueva función de prueba") == 1 and len(n1.splitlines()) == len(n0.splitlines()) + 1
print("8) OK bitácora: solo se añade al final, una línea por commit nuevo, sin duplicar")

# 9) informes de Ruiz: texto completo + cotejo + resultado (repo privado simulado con una carpeta)
w(os.path.join(PRIV, "analisis", "2026", "2026-10-20_ORO_MACRO.md"), '---\nfecha: 2026-10-20\ncorte_madrid: 07:00\ntipo: ORO_MACRO\nvisibilidad: privado\nsesgo_oro: alcista\nversion: 1\ncorte_origen: CABECERA\nprecio_base: 4010.5\n---\n\n# Mi informe\nTexto íntegro del informe. ÚNICO-SECRETO-123\n')
w(os.path.join(PRIV, "analisis", "2026", "2026-10-20_ORO_MACRO.json"), json.dumps({"cotejo": {"panel": [{"nombre": "10Y", "valor": 4.1, "nexora": 4.12, "fuente": "FRED DGS10", "fecha_nexora": "2026-10-19", "tolerancia": "±3 pb", "estado": "✅"},
                                                                                                       {"nombre": "DXY", "valor": 99.0, "nexora": 101.5, "fuente": "Yahoo", "fecha_nexora": "2026-10-19", "tolerancia": "±0,3", "estado": "⚠️"}],
                                                                            "calendario": [], "resumen": {"ok": 1, "dif": 1, "sin": 0}, "resumen_calendario": {"ok": 0, "dif": 0, "sin": 0}}}))
w(os.path.join(REPO, "data", "analisis_indice.csv"), "id,fecha,tipo,version,visibilidad,sesgo_oro,corte_madrid,corte_origen,publicado_utc,precio_base,precio_base_hora,precio_base_fuente,hash,estado,registrada_utc,nota\n"
  "2026-10-20_ORO_MACRO,2026-10-20,ORO_MACRO,1,privado,alcista,07:00,CABECERA,2026-10-20 12:00 UTC,4010.5,2026-10-20 05:00,GC=F,h,VIGENTE,2026-10-20 12:00 UTC,\n")
w(os.path.join(REPO, "data", "analisis_resultados.csv"), "id,fecha,tipo,sesgo_oro,horizonte,fecha_t,oro_pct,dxy_var,dfii10_pb,umbral,umbral_pct,em_sesion,precio_base,precio_base_hora,precio_fin,veredicto,evaluado_utc\n"
  "2026-10-20_ORO_MACRO,2026-10-20,ORO_MACRO,alcista,T+1,2026-10-20,0.9,-0.2,-3,EM,0.42,1.4,4010.5,x,4047,CUMPLIDO,x\n2026-10-20_ORO_MACRO,2026-10-20,ORO_MACRO,alcista,T+5,2026-10-27,-0.1,0,0,FIJO,0.25,,4010.5,x,4006,MIXTO,x\n")
pasada(privado=PRIV)
inf = leer("60_Market_Intelligence/05_Analisis/2026/2026-10-20_ORO_MACRO.md")
assert "ÚNICO-SECRETO-123" in inf and "T+1" in inf and "CUMPLIDO" in inf and "MIXTO" in inf and "EM" in inf and "FIJO" in inf, inf
assert "✅ 10Y" in inf and "⚠️ DXY" in inf and 'resultado: "T+1 CUMPLIDO / T+5 MIXTO"' in inf, inf
assert "2026-10-20_ORO_MACRO" in leer("60_Market_Intelligence/05_Analisis/00 Índice de análisis.md")
assert "ÚNICO-SECRETO-123" not in "".join(open(os.path.join(REPO, "data", f), encoding="utf-8").read() for f in os.listdir(os.path.join(REPO, "data")) if f.endswith(".csv"))
print("9) OK informe: texto completo (bóveda privada) + cotejo ✅/⚠️ + resultado CUMPLIDO/MIXTO con su umbral EM/FIJO; el texto no pasa al repo público")

# 10) un día «de hoy» cuenta como cerrado solo con un cierre de >= 21:30 UTC de ese día Y una foto de contexto posterior; el cierre de las 00:18 UTC es de la sesión anterior
with open(os.path.join(REPO, "data", "ejecuciones.csv"), "a", encoding="utf-8", newline="") as f:
    f.write("2026-10-25 00:18 UTC,cierre,workflow_dispatch,x,,1,3\n")
gz(os.path.join(REPO, "data", "historico_contexto", "2026-10-25", "0600.json.gz"), ctx("2026-10-25", "0600", "ALCISTA DÉBIL"))
assert not X.Datos(REPO, "2026-10-25").cerrado("2026-10-25"), "un cierre a las 00:18 UTC pertenece a la sesión anterior"
with open(os.path.join(REPO, "data", "ejecuciones.csv"), "a", encoding="utf-8", newline="") as f:
    f.write("2026-10-25 21:30 UTC,cierre,workflow_dispatch,x,,1,4\n")
assert not X.Datos(REPO, "2026-10-25").cerrado("2026-10-25"), "hay cierre pero la última foto de contexto (06:00) es anterior: aún no está cerrado"
gz(os.path.join(REPO, "data", "historico_contexto", "2026-10-25", "2200.json.gz"), ctx("2026-10-25", "2200", "ALCISTA DÉBIL", gen="2026-10-25 22:00 UTC"))
assert X.Datos(REPO, "2026-10-25").cerrado("2026-10-25") is True
assert X.Datos(REPO, "2026-10-25").cerrado("2026-10-26") is False and X.Datos(REPO, "2026-10-26").cerrado("2026-10-25") is True
print("10) OK un día cuenta como cerrado solo con su cierre de las >= 21:30 UTC y una foto de contexto posterior (el cierre de las 00:18 UTC es de la sesión anterior)")

# 11) debida(): última hora programada (08:30 / 23:45 locales)
assert X.debida(dt.datetime(2026, 10, 23, 9, 0)) == dt.datetime(2026, 10, 23, 8, 30)
assert X.debida(dt.datetime(2026, 10, 23, 8, 0)) == dt.datetime(2026, 10, 22, 23, 45)
assert X.debida(dt.datetime(2026, 10, 23, 23, 50)) == dt.datetime(2026, 10, 23, 23, 45)
print("11) OK lógica «si se perdió la última»: la hora debida es la última de las 08:30 / 23:45 ya pasada")

# 12) latido: se sube al repo público (origen simulado con un repo bare) y reintenta si el origen se movió
ORIGEN = os.path.join(TMP, "origen.git")
sh(TMP, "init", "-q", "--bare", "-b", "main", ORIGEN)
sh(REPO, "remote", "add", "origin", ORIGEN)
sh(REPO, "add", "-A")
sh(REPO, "commit", "-q", "-m", "estado de la prueba", fecha="2026-10-22T08:00:00+00:00")
sh(REPO, "push", "-q", "-u", "origin", "main")
OTRO = os.path.join(TMP, "otro")
sh(TMP, "clone", "-q", ORIGEN, OTRO)
w(os.path.join(OTRO, "data", "algo.csv"), "a\n")
sh(OTRO, "add", "-A")
sh(OTRO, "commit", "-q", "-m", "un bot escribe a la vez", fecha="2026-10-22T08:01:00+00:00")
sh(OTRO, "push", "-q", "origin", "main")
logs = []
ok = X.latido(REPO, "OK", dt.datetime(2026, 10, 22, 6, 30, tzinfo=UTC), logs.append)
assert ok, logs
sh(OTRO, "pull", "-q", "--rebase")
lat = open(os.path.join(OTRO, "data", "obsidian_latido.csv"), encoding="utf-8").read()
assert lat == "fecha,hora_utc,estado\n2026-10-22,06:30,OK\n", lat
assert "latido obsidian 2026-10-22 06:30 UTC [skip ci]" in sh(OTRO, "log", "--format=%s", "-3")
print("12) OK latido: fila «fecha,hora,estado» subida al repo (con un push concurrente de otro proceso resuelto con rebase); sin datos personales")

# 13) integridad: 2 días seguidos sin latido correcto → alerta; un solo aviso por racha; el ERROR no cuenta como pasada
T = tempfile.mkdtemp(prefix="nexora_int_")
os.makedirs(os.path.join(T, "data"))
os.makedirs(os.path.join(T, "site", "data"))
hoy = dt.datetime(2026, 10, 27, 10, 0, tzinfo=UTC)
assert I.estado_latido_obsidian(T, hoy)["alerta"] is False and "SIN DATO" in I.estado_latido_obsidian(T, hoy)["texto"]
w(os.path.join(T, "data", "obsidian_latido.csv"), "fecha,hora_utc,estado\n2026-10-23,06:30,OK\n2026-10-23,21:45,OK\n2026-10-24,06:30,ERROR\n")
e = I.estado_latido_obsidian(T, hoy)       # ayer = 26 y anteayer = 25: ninguno tiene pasada OK/AVISO; el 24 solo tiene ERROR
assert e["alerta"] and e["racha_dias"] == 3 and e["racha_desde"] == "2026-10-24" and e["ultimo_ok"] == "2026-10-23 21:45 UTC", e
e2 = I.estado_latido_obsidian(T, dt.datetime(2026, 10, 25, 10, 0, tzinfo=UTC))      # ayer = 24 (solo ERROR): 1 día sin exportar, aún no alerta
assert e2["alerta"] is False and e2["racha_dias"] == 1, e2
enviados = []
env = lambda m: (enviados.append(m), (True, None))[1]  # noqa: E731
out = I.vigilar(T, hoy, enviar=env)
assert [o for o in out if o[0].startswith("obsidian|")] and len([m for m in enviados if "Obsidian" in m]) == 1, (out, enviados)
assert "obsidian|2026-10-24" in open(os.path.join(T, "data", "vigilante_estado.json"), encoding="utf-8").read()
I.vigilar(T, hoy + dt.timedelta(hours=3), enviar=env)
assert len([m for m in enviados if "Obsidian" in m]) == 1, "un solo aviso por racha"
with open(os.path.join(T, "data", "obsidian_latido.csv"), "a", encoding="utf-8", newline="") as f:
    f.write("2026-10-27,08:30,OK\n")
assert I.estado_latido_obsidian(T, dt.datetime(2026, 10, 28, 9, 0, tzinfo=UTC))["alerta"] is False
assert I.construir(T, hoy)["obsidian"]["racha_dias"] == 3
print("13) OK integridad: 2 días seguidos sin pasada OK/AVISO → alerta en #/integridad y UN Telegram por racha (simulado); ERROR no cuenta; una pasada OK corta la racha")

# 14) no hay secretos en lo escrito ni en el log de la propia pasada
log = os.path.join(TMP, "log.txt")
r = subprocess.run([sys.executable, os.path.join(HERE, "exportar_obsidian.py"), "--boveda", BOV, "--publico", REPO, "--privado", PRIV, "--estado", EST, "--log", log, "--sin-git", "--sin-latido", "--hoy", HOY],
                   capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})
assert r.returncode == 0, r.stderr
assert "sin cambios" in open(log, encoding="utf-8").read() or "0 creadas" in open(log, encoding="utf-8").read()
todo = open(log, encoding="utf-8").read() + "".join(open(os.path.join(dp, f), encoding="utf-8", errors="ignore").read() for dp, _, fs in os.walk(BOV) for f in fs)
assert "ghp_" not in todo and "github_pat_" not in todo and "Bearer " not in todo
print("14) OK ejecución desde la línea de órdenes: 0 cambios en la pasada repetida; ni log ni notas contienen tokens")
# 15) ejecución ANCLADA: la tarea ejecuta una copia fija; si el exportador cambia en main no se ejecuta la versión nueva, se avisa (integridad + Telegram) y se aprueba con --aprobar
X.ANCLADO_DIR = os.path.join(TMP, "aprobado")
X.ANCLADO = os.path.join(X.ANCLADO_DIR, "exportar_obsidian.py")
X.ANCLADO_META = os.path.join(X.ANCLADO_DIR, "aprobado.json")
w(os.path.join(REPO, "tools", "exportar_obsidian.py"), open(os.path.join(HERE, "exportar_obsidian.py"), encoding="utf-8").read())
sh(REPO, "add", "-A")
sh(REPO, "commit", "-q", "-m", "exportador v1", fecha="2026-10-22T09:00:00+00:00")
sh(REPO, "push", "-q", "origin", "main")
assert X.comprobar_actualizacion(REPO)["aprobado"] is None, "sin aprobación previa, todo es pendiente"
def aprobar_ok(confirmar="APROBAR"):
    return X.aprobar(REPO, lambda m: None, X.blob_git(os.path.join(REPO, "tools", "exportar_obsidian.py"))[:12], confirmar)


b0 = X.blob_git(os.path.join(REPO, "tools", "exportar_obsidian.py"))
assert X.aprobar(REPO, lambda m: None) == 2 and not os.path.exists(X.ANCLADO), "sin hash solo muestra el diff"
assert X.aprobar(REPO, lambda m: None, "0" * 12, "APROBAR") == 1 and not os.path.exists(X.ANCLADO), "hash distinto: rechazado"
assert X.aprobar(REPO, lambda m: None, b0[:12], "") == 1 and not os.path.exists(X.ANCLADO), "sin escribir APROBAR no se ancla"
with open(os.path.join(REPO, "tools", "exportar_obsidian.py"), "a", encoding="utf-8", newline="") as f:
    f.write("# manipulado en el árbol de trabajo")
assert X.aprobar(REPO, lambda m: None, X.blob_git(os.path.join(REPO, "tools", "exportar_obsidian.py"))[:12], "APROBAR") == 1, "el archivo del clon no coincide con HEAD"
sh(REPO, "checkout", "--", "tools/exportar_obsidian.py")
assert aprobar_ok() == 0 and os.path.exists(X.ANCLADO) and X.comprobar_actualizacion(REPO) is None
assert X.blob_git(X.ANCLADO) == b0, "la copia anclada es exactamente el objeto git"
fijo = open(X.ANCLADO, "rb").read()
with open(os.path.join(REPO, "tools", "exportar_obsidian.py"), "a", encoding="utf-8", newline="") as f:
    f.write("\nimport os; os.system('ghp_AbCdEf1234567890AbCdEf12')\n")
sh(REPO, "commit", "-q", "-am", "exportador v2 (cambio no aprobado)", fecha="2026-10-22T10:00:00+00:00")
p = X.comprobar_actualizacion(REPO)
assert p and p["pendiente"] and p["resumen"]["anade"] == 2 and any("os.system" in x for x in p["resumen"]["lineas"]), p
assert not any("ghp_AbCdEf" in x for x in p["resumen"]["lineas"]), "el resumen del diff no lleva secretos"
assert open(X.ANCLADO, "rb").read() == fijo, "la copia anclada no cambia sola"
assert X.escribir_pendiente(REPO, p) is True and X.escribir_pendiente(REPO, p) is False
T2 = tempfile.mkdtemp(prefix="nexora_int2_")
os.makedirs(os.path.join(T2, "data"))
os.makedirs(os.path.join(T2, "site", "data"))
w(os.path.join(T2, "data", "obsidian_latido.csv"), "fecha,hora_utc,estado\n2026-10-26,06:30,OK\n2026-10-27,06:30,PENDIENTE@" + str(p["aprobado"])[:7] + "\n")
shutil_copy = open(os.path.join(REPO, "data", "obsidian_pendiente.json"), encoding="utf-8").read()
w(os.path.join(T2, "data", "obsidian_pendiente.json"), shutil_copy)
ahora2 = dt.datetime(2026, 10, 27, 10, 0, tzinfo=UTC)
e = I.estado_latido_obsidian(T2, ahora2)
assert e["pendiente_aprobar"] and e["alerta"] is False and e["racha_dias"] == 0, e
env2 = []
I.vigilar(T2, ahora2, enviar=lambda m: (env2.append(m), (True, None))[1])
I.vigilar(T2, ahora2 + dt.timedelta(hours=5), enviar=lambda m: (env2.append(m), (True, None))[1])
pend_msgs = [m for m in env2 if "pendiente de aprobar" in m]
assert len(pend_msgs) == 1 and "--aprobar" in pend_msgs[0] and "os.system" in pend_msgs[0] and "ghp_" not in pend_msgs[0], env2
assert I.construir(T2, ahora2)["obsidian"]["pendiente_aprobar"]["blob"] == p["blob"]
assert aprobar_ok() == 0 and X.comprobar_actualizacion(REPO) is None and open(X.ANCLADO, "rb").read() != fijo
assert X.escribir_pendiente(REPO, None) is True and json.load(open(os.path.join(REPO, "data", "obsidian_pendiente.json"), encoding="utf-8")) == {"pendiente": False}
print("15) OK ejecución anclada: copia fija aprobada; un cambio en main NO se ejecuta, queda pendiente con su diff (sin secretos), un solo Telegram «pendiente de aprobar» y banner en #/integridad; --aprobar lo ancla")
# 16) Diario de operaciones: 10_Diario/Operaciones/AAAA-MM.md, solo añadir; corrección → fila REVISADA; borrado → ANULADA; resumen con n, acierto, esperanza y profit factor por setup
def diario(trades, borrados=None):
    w(os.path.join(PRIV, "diario", "2026-10.json"), json.dumps({"version": 2, "mes": "2026-10", "trades": trades, "notas": {}, "notasMod": {}, "borrados": borrados or {}}, ensure_ascii=False))


FOTO = {"estado": "OK", "contexto_utc": "2026-10-14 13:40 UTC", "tesis": {"etiqueta": "ALCISTA DÉBIL"}, "gamma": {"signo": "NEGATIVA"}, "regimen": {"cuadrante": "REFLACIÓN"}, "evento_alta_2h": {"si": False}}
T1 = {"id": "a1", "fecha": "2026-10-14", "hora": "13:45", "activo": "Nasdaq 100", "lado": "Largo", "pnl": 120.0, "setup": "Barrido+vuelta", "conf": ["absorcion", "fvg"], "foto": FOTO, "mod": "x"}
T2 = {"id": "b2", "fecha": "2026-10-15", "hora": "14:10", "activo": "Oro", "lado": "Corto", "pnl": -80.0, "setup": "Ruptura+continuación", "conf": [], "mod": "x"}
T3 = {"id": "c3", "fecha": "2026-10-16", "hora": "15:00", "activo": "Bitcoin", "lado": "Largo", "pnl": 40.0, "mod": "x"}
OP = "10_Diario/Operaciones/2026-10.md"
diario([T1, T2, T3])
pasada(privado=PRIV)
op = leer(OP)
filas = [l for l in op.splitlines() if l.startswith("| ALTA")]
assert len(filas) == 3 and "Barrido LIT" not in op and "Absorción, FVG" in op and "ALCISTA DÉBIL" in op and "gamma NEGATIVA" in op and "| A |" in op and "| B |" in op and "sin setup" in op, op
assert "Operaciones: **3**" in op and "acierto: **67 %**" in op and "SIN DATO: el Diario guarda el resultado en $" in op and "n<20: sin conclusión" in op
assert "A · Barrido+vuelta | 1 | 100 % | +120,00 $ | ∞ (sin pérdidas)" in op and "B · Ruptura+continuación | 1 | 0 % | -80,00 $ | 0,00" in op, op
arbol = snap_arbol(BOV)
assert cambios(pasada(privado=PRIV)) == 0 and snap_arbol(BOV) == arbol, "idempotente"
# corrijo una operación (resultado) y añado otra: las filas anteriores no se tocan; la corrección es una fila REVISADA
antes = [l for l in op.splitlines() if l.startswith("| ALTA")]
T2b = dict(T2, pnl=-30.0)
T4 = {"id": "d4", "fecha": "2026-10-19", "hora": "09:00", "activo": "Oro", "lado": "Largo", "pnl": 200.0, "setup": "Ruptura+continuación", "r": 2.0}
diario([T1, T2b, T3, T4])
pasada(privado=PRIV)
op2 = leer(OP)
assert [l for l in op2.splitlines() if l.startswith("| ALTA")][:3] == antes, "las filas ya escritas no se tocan"
assert sum(l.startswith("| REVISADA") for l in op2.splitlines()) == 1 and "-30,00" in [l for l in op2.splitlines() if l.startswith("| REVISADA")][0]
assert "-80,00" in op2 and op2.index("| ALTA | 2026-10-19") > op2.index("| REVISADA"), "se conserva la fila antigua y lo nuevo va al final"
assert "Operaciones: **4**" in op2 and "+2,00 R" in op2 and "(1 de 4 operaciones con R)" in op2
# borrado: lápida → fila ANULADA, nada se elimina
diario([T1, T2b, T3, T4], {"c3": "2026-10-20T10:00:00.000Z"})
pasada(privado=PRIV)
op3 = leer(OP)
assert any(l.startswith("| ANULADA") and "c3" in l for l in op3.splitlines()) and "| c3 |" in op2 and op3.startswith(op2.split("<!-- NEXORA:auto:resumen -->")[0])
assert "Operaciones: **3**" in op3
a3 = snap_arbol(BOV)
assert cambios(pasada(privado=PRIV)) == 0 and snap_arbol(BOV) == a3
print("16) OK Diario de operaciones: una fila por operación (setup A/B, dirección, R=SIN DATO si no hay, resultado, confirmaciones, foto NEXORA); resumen del mes con n, acierto, esperanza y profit factor por setup; solo se añade (REVISADA al corregir, ANULADA al borrar); idempotente")
print("\nTODAS LAS PRUEBAS DEL EXPORTADOR A OBSIDIAN PASARON")
