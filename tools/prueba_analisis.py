#!/usr/bin/env python3
"""Pruebas de la Fase 18 (Análisis diario). Sin red, sin GitHub (el repo privado se simula con una carpeta local) y sin Telegram. Uso: PYTHONUTF8=1 python tools/prueba_analisis.py
El informe de prueba es SINTÉTICO (no es el de Ruiz)."""
import csv
import datetime as dt
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
import analisis as A  # noqa: E402
import publicar_analisis as PU  # noqa: E402

UTC = dt.timezone.utc
FRASE_PRIVADA = "FRASE-PRIVADA-DE-PRENSA-XYZ"
INFORME = f"""INFORME DIARIO · 20-10-2026 · corte 09:30 (Madrid)

TESIS CENTRAL
El oro consolida bajo la presión del tipo real y el mercado espera el IPC sin dirección clara. {FRASE_PRIVADA}.

A. Panel de mercado
A.1 Resumen
Sesión asiática tranquila; los tipos reales siguen altos.
A.2 Panel
| Indicador | Valor |
| US 2Y | 4,65 % |
| US 5Y | 4,78 % |
| US 10Y | 4,99 % |
| US 30Y | 5,33 % |
| DFII10 | 2,64 % |
| Breakeven 10Y | 2,32 % |
| DXY | 101,76 |
| Oro (XAU) 20-oct | 4.126,10 |
| Brent | 115,22 |
| WTI | 107,89 |
| VIX | 19,6 |
| TGA | 945,2 B |
| ON RRP | 0,4 B |
| Reservas | 2,963T |
| SOFR | 3,88 % |
| COT oro neto | 107.089 |
Probabilidad Fed (CME FedWatch): 92% mantener, 8% subida en la reunión del 28-oct. {FRASE_PRIVADA}

B. Calendario
B.3 Calendario de la semana
Martes 21-oct
14:30 IPC EE. UU.
16:00 Discurso de Powell {FRASE_PRIVADA}

G. Oro
Escenario 1: Base
- Condiciones: tipo real estable y DXY sin cambios
- Confirmación: cierre diario sobre 4.150
- Invalidación: cierre diario bajo 4.050
Escenario 2: Bajista
- Condiciones: DFII10 sobre 2,75 %
- Confirmación: pérdida de 4.050
- Invalidación: recuperación de 4.150

J. Riesgos
Red team: el IPC podría sorprender al alza.
Data gaps: sin dato de flujos ETF del día.

K.2 Tesis final
Neutral, con sesgo alcista débil si el IPC sale en línea.
VEREDICTO: Neutral
"""


def nueva_raiz():
    t = tempfile.mkdtemp(prefix="an_")
    for d in ("data", "site/data"):
        os.makedirs(os.path.join(t, d))

    def w(nombre, filas, campos):
        with open(os.path.join(t, "data", nombre), "w", encoding="utf-8", newline="") as f:
            x = csv.DictWriter(f, fieldnames=campos)
            x.writeheader()
            x.writerows(filas)
    w("historico_tipos.csv", [{"capturado_utc": "x", "serie": s, "valor": v, "fecha_dato": "2026-10-20", "d1_pb": 0, "fuente": "Tesoro de EE. UU."} for s, v in (("t2y", 4.65), ("n10", 4.96), ("real10", 2.64))],
      ["capturado_utc", "serie", "valor", "fecha_dato", "d1_pb", "fuente"])
    w("historico_precios.csv", [{"capturado_utc": "x", "activo": a, "valor": v, "fecha_dato": "2026-10-20", "cambio_1d_pct": 0, "fuente": "Yahoo Finance"} for a, v in (("dxy", 101.76), ("brent", 115.22), ("wti", 107.89), ("vix", 19.03), ("oro", 4142.5))],
      ["capturado_utc", "activo", "valor", "fecha_dato", "cambio_1d_pct", "fuente"])
    w("xau_gld_ratio.csv", [{"fecha": "2026-10-20", "gld_cierre": 377.65, "xau_spot": 4126.1, "ratio": 10.92573, "xau_hora_utc": "2026-10-20 21:32", "fuente_xau": "gold-api.com (XAU/USD al contado)", "medido_utc": "x"}],
      ["fecha", "gld_cierre", "xau_spot", "ratio", "xau_hora_utc", "fuente_xau", "medido_utc"])
    w("historico_cot.csv", [{"fecha_informe": "2026-10-13", "contrato": "088691", "clave": "oro", "tipo": "gestores", "neto": 107089, "largos": 1, "cortos": 1, "percentil_3a": 27}], ["fecha_informe", "contrato", "clave", "tipo", "neto", "largos", "cortos", "percentil_3a"])
    w("eventos_macro.csv", [], ["fecha", "hora_madrid", "evento", "importancia", "fuente", "visto_utc"])
    json.dump({"metricas": {"tga": {"valor_B": 945.2, "fecha": "2026-10-20"}, "rrp": {"valor_B": 0.4, "fecha": "2026-10-20"}, "reservas": {"valor_T": 2.963, "fecha": "2026-10-20"}, "sofr": {"valor": 3.88, "fecha": "2026-10-20"}}},
              open(os.path.join(t, "site", "data", "oro.json"), "w", encoding="utf-8"))
    json.dump({"agenda": {"hoy": [], "proximos_7_dias": [{"fecha": "2026-10-21", "hora_madrid": "14:30", "evento": "IPC EE. UU. (CPI)", "importancia": "ALTA"}, {"fecha": "2026-10-21", "hora_madrid": "20:00", "evento": "Actas del FOMC", "importancia": "ALTA"},
                                                    {"fecha": "2026-10-27", "hora_madrid": "14:30", "evento": "PCE (BEA)", "importancia": "ALTA"}]}}, open(os.path.join(t, "site", "data", "agenda.json"), "w", encoding="utf-8"))
    json.dump({"fecha_precios": "2026-10-20", "fuente": "x", "reuniones": [{"reunion": "2026-10-28", "prob_reunion": {"subida": 8.0, "mantiene": 92.0, "bajada": 0}}]}, open(os.path.join(t, "site", "data", "fedwatch.json"), "w", encoding="utf-8"))
    return t


# ---------------------------------------------------------------- 1) extracción tolerante; el sesgo NO se deduce del texto
P = A.parse(INFORME)
assert P["reconocido"] and P["fecha_detectada"] == "2026-10-20" and P["corte_detectado"] == "09:30"
assert FRASE_PRIVADA in P["tesis_central"] and P["veredicto"] == "Neutral" and P["tesis_final"].startswith("Neutral, con sesgo alcista débil")
assert set(P["secciones"]) >= {"TESIS", "A", "A.1", "A.2", "B", "B.3", "G", "J", "K.2", "VEREDICTO"}, sorted(P["secciones"])
assert "US 2Y" in P["panel"] and "Discurso de Powell" in P["calendario"] and "Escenario 1" in P["oro_texto"] and "Red team" in P["j_texto"]
e1, e2 = P["escenarios"][0], P["escenarios"][1]
assert e1["nombre"] == "Escenario 1: Base" and e1["condiciones"] == "tipo real estable y DXY sin cambios" and e1["confirmacion"] == "cierre diario sobre 4.150" and e1["invalidacion"] == "cierre diario bajo 4.050", e1
assert e2["condiciones"] == "DFII10 sobre 2,75 %" and e2["invalidacion"] == "recuperación de 4.150"
assert P["red_team"] == ["el IPC podría sorprender al alza."] and P["data_gaps"] == ["sin dato de flujos ETF del día."]
assert "sesgo" not in P and "sesgo_oro" not in P, "el sesgo lo da Ruiz; el parser no lo deduce (el texto dice «sesgo alcista débil» y se publica neutral)"
# informe sin cabeceras reconocibles: no inventa nada, conserva el texto
P0 = A.parse("Hoy el oro cae un poco y no hay nada más que decir.\nOtra línea.")
assert P0["reconocido"] is False and P0["secciones"] == {} and P0["tesis_central"] == "" and P0["escenarios"] == [] and P0["panel"] == ""
# «A favor del oro» no es la sección A
_s = A.parse("A favor del oro: el tipo real cae.\nA. Panel\ntexto")["secciones"]
assert list(_s) == ["A"] and _s["A"].startswith("A. Panel"), "«A favor del oro» no es la sección A; «A. Panel» sí"
print("1) OK extracción: TESIS, A.1, A.2, B.3, G, J, K.2 y VEREDICTO; escenarios literales; sin cabeceras no inventa nada; el sesgo no se deduce del texto")

# ---------------------------------------------------------------- 2) números y tolerancias (en el borde exacto)
assert A.num("4,15 %") == 4.15 and A.num("4.152,30") == 4152.3 and A.num("1,234.5") == 1234.5 and A.num("−0,3") == -0.3 and A.num("sin número") is None and A.num("4.140", miles=True) == 4140.0 and A.num("4.140") == 4.14
assert A.a_miles_de_millones(2.963, "2,963T") == 2963.0 and A.a_miles_de_millones(945.2, "945,2 B") == 945.2 and A.a_miles_de_millones(400, "400 M") == 0.4
assert A.comparar("t10", 4.99, 4.96)[0] == "✅" and A.comparar("t10", 4.9901, 4.96)[0] == "⚠️", "tipos ±3 pb: justo 3 pb ✅"
assert A.comparar("dxy", 102.06, 101.76)[0] == "✅" and A.comparar("dxy", 102.07, 101.76)[0] == "⚠️"
assert A.comparar("oro", 4120.0 * 1.005, 4120.0)[0] == "✅" and A.comparar("oro", 4120.0 * 1.0051, 4120.0)[0] == "⚠️"
assert A.comparar("brent", 100 * 1.015, 100)[0] == "✅" and A.comparar("wti", 100 * 1.0151, 100)[0] == "⚠️"
assert A.comparar("vix", 19.53, 19.03)[0] == "✅" and A.comparar("vix", 19.6, 19.03)[0] == "⚠️"
assert A.comparar("tga", 1010.0, 1000.0)[0] == "✅" and A.comparar("sofr", 3.91, 3.88)[0] == "✅" and A.comparar("cot_oro", 108159, 107089)[0] == "✅" and A.comparar("cot_oro", 108200, 107089)[0] == "⚠️"
print("2) OK números (coma/punto, miles, T/B/M) y tolerancias exactas: tipos ±3 pb, DXY ±0,3, oro ±0,5 %, Brent/WTI ±1,5 %, VIX ±0,5, resto ±1 %")

# ---------------------------------------------------------------- 3) cotejo del panel contra los datos de NEXORA de la MISMA fecha
R = nueva_raiz()
C = A.cotejar(P, "2026-10-20", R)
f = {x["id"]: x for x in C["panel"]}
assert f["t2"]["estado"] == "✅" and f["t10"]["estado"] == "✅" and f["t30"]["estado"] == "—", "5Y y 30Y: NEXORA no tiene histórico de esa fecha → «—», nunca se rellena"
assert f["t5"]["estado"] == "—" and f["t5"]["nexora"] is None
assert f["dfii10"]["estado"] == "✅" and f["be10"]["estado"] == "✅" and f["be10"]["nexora"] == 2.32 and f["dxy"]["estado"] == "✅"
assert f["oro"]["valor"] == 4126.1 and f["oro"]["nexora"] == 4126.1 and "gold-api" in f["oro"]["fuente"] and f["oro"]["estado"] == "✅", "oro contado: el spot de gold-api de esa fecha, no el futuro"
assert f["brent"]["estado"] == "✅" and f["wti"]["estado"] == "✅"
assert f["vix"]["estado"] == "⚠️" and f["vix"]["valor"] == 19.6 and f["vix"]["nexora"] == 19.03 and "Yahoo" in f["vix"]["fuente"] and f["vix"]["dif"] == 0.57, "difiere: ambos valores y la fuente de NEXORA"
assert f["tga"]["estado"] == "✅" and f["rrp"]["estado"] == "✅" and f["reservas"]["valor"] == 2963.0 and f["reservas"]["estado"] == "✅" and f["sofr"]["estado"] == "✅"
assert f["cot_oro"]["valor"] == 107089.0 and f["cot_oro"]["estado"] == "✅" and f["cot_oro"]["fecha_nexora"] == "2026-10-13"
assert C["resumen"] == {"ok": 13, "dif": 1, "sin": 2}, C["resumen"]
_o = [x["id"] for x in A.cotejar(P, "2026-10-19", R)["panel"] if x["estado"] == "✅"]
assert _o == ["cot_oro"], "otra fecha: NEXORA no tiene esos datos → «—»; solo el COT semanal (informe del martes anterior, ≤ 7 días) sigue valiendo; ningún ✅ inventado"
print(f"3) OK cotejo del panel: {C['resumen']['ok']} ✅ · {C['resumen']['dif']} ⚠️ · {C['resumen']['sin']} — (VIX: informe 19,6 frente a NEXORA 19,03 con su fuente); otra fecha → todo «—»")

# ---------------------------------------------------------------- 4) calendario B.3 y Fed lado a lado
cal = {(x["fecha"], x["hora"]): x for x in C["calendario"] if x["hora"]}
assert cal[("2026-10-21", "14:30")]["estado"] == "✅" and cal[("2026-10-21", "16:00")]["estado"] == "—"
falta = [x for x in C["calendario"] if "falta en el informe" in x["nota"]]
assert len(falta) == 1 and falta[0]["nexora"]["evento"] == "Actas del FOMC" and falta[0]["estado"] == "⚠️"
cal2 = A.cotejar_calendario("Martes 27-oct\n15:30 PCE", "2026-10-26", R)
assert cal2[0]["estado"] == "⚠️" and "cambio de hora" in cal2[0]["nota"] and "1 h" in cal2[0]["nota"] and cal2[0]["nexora"]["hora_madrid"] == "14:30"
assert A.en_semana_de_cambio("2026-10-27") and not A.en_semana_de_cambio("2026-10-21") and not A.en_semana_de_cambio("2026-11-02")
fed = C["fed"]
assert fed["informe"] and "92% mantener" in fed["informe"][0] and fed["nexora"]["mantiene"] == 92.0 and fed["nexora"]["subida"] == 8.0 and "ZQ" in fed["nexora"]["fuente"]
print("4) OK calendario (evento que falta en el informe, evento que NEXORA no tiene, hora distinta con la nota del cambio de hora) y Fed lado a lado con cada fuente")

# ---------------------------------------------------------------- 5) publicación: privado → ningún texto del informe en el repo público; solo añadir; versiones
PRIV = tempfile.mkdtemp(prefix="priv_")
ahora = dt.datetime(2026, 10, 20, 8, 0, tzinfo=UTC)
r = PU.publicar(INFORME, "neutral", "ORO_MACRO", "privado", raiz=R, solo_local=PRIV, ahora=ahora)
assert r["estado"] == "PUBLICADO" and r["id"] == "2026-10-20_ORO_MACRO" and r["ruta_publica"] is None
priv = open(os.path.join(PRIV, "analisis", "2026", "2026-10-20_ORO_MACRO.md"), encoding="utf-8").read()
assert priv.startswith("---\nfecha: 2026-10-20\ncorte_madrid: 09:30\ntipo: ORO_MACRO\nvisibilidad: privado\nsesgo_oro: neutral\nescenarios: [\"Escenario 1: Base\", \"Escenario 2: Bajista\"]\nhash: sha256:") and FRASE_PRIVADA in priv
fugas = []
for dp, _d, fs in os.walk(R):
    for n in fs:
        if FRASE_PRIVADA in open(os.path.join(dp, n), encoding="utf-8", errors="ignore").read():
            fugas.append(os.path.join(dp, n))
assert not fugas and not os.path.exists(os.path.join(R, "data", "analisis")), fugas
pub_c = json.load(open(os.path.join(R, "site", "data", "analisis.json"), encoding="utf-8"))["entradas"][0]["cotejo"]
assert all("texto" not in x for x in pub_c["calendario"]) and pub_c["fed"]["informe"] == [] and pub_c["fed"]["informe_n"] >= 1 and pub_c["fed"]["nexora"]["mantiene"] == 92.0, "público: sin el texto de los eventos ni las líneas de la Fed del informe"
_pj = json.load(open(os.path.join(PRIV, "analisis", "2026", "2026-10-20_ORO_MACRO.json"), encoding="utf-8"))
assert any(FRASE_PRIVADA in (x.get("texto") or "") for x in _pj["cotejo"]["calendario"]) and any(FRASE_PRIVADA in l for l in _pj["cotejo"]["fed"]["informe"]), "los textos literales sí están en el JSON privado"
J = json.load(open(os.path.join(R, "site", "data", "analisis.json"), encoding="utf-8"))
assert J["n"] == 1 and J["entradas"][0]["visibilidad"] == "privado" and J["entradas"][0]["resumen_publico"] is None and J["entradas"][0]["sesgo_oro"] == "neutral" and J["entradas"][0]["cotejo"]["resumen"]["ok"] == 13
assert all("texto" not in x for x in J["entradas"][0]["cotejo"]["panel"]), "el cotejo público no lleva el texto de las filas del informe"
sal = PU.salida(r)
assert os.path.normpath(sal.split("Archivo: ")[1].split(" · ")[0]) == os.path.normpath(os.path.join(PRIV, "analisis", "2026", "2026-10-20_ORO_MACRO.md")) and "13 ✅ · 1 ⚠️ · 2 —" in sal and "⚠️ VIX: informe 19.6 · NEXORA 19.03" in sal and FRASE_PRIVADA not in sal
print("5) OK privado: informe completo solo en el repo privado (simulado); en el público solo índice y cotejo; el texto privado no aparece en NINGÚN archivo público; salida = ruta + cotejo + ⚠️")

# 5b) mismo hash: no hace nada; otro texto: _v2 y el anterior REVISADA; nunca sobrescribe
assert PU.publicar(INFORME, "neutral", "ORO_MACRO", "privado", raiz=R, solo_local=PRIV, ahora=ahora)["estado"] == "YA_PUBLICADO"
r2 = PU.publicar(INFORME.replace("Neutral, con sesgo", "Neutral (revisado), con sesgo"), "alcista", "ORO_MACRO", "resumen", raiz=R, solo_local=PRIV, ahora=ahora + dt.timedelta(minutes=30))
assert r2["id"] == "2026-10-20_ORO_MACRO_v2" and os.path.exists(os.path.join(PRIV, "analisis", "2026", "2026-10-20_ORO_MACRO.md")) and os.path.exists(os.path.join(PRIV, "analisis", "2026", "2026-10-20_ORO_MACRO_v2.md"))
assert FRASE_PRIVADA in open(os.path.join(PRIV, "analisis", "2026", "2026-10-20_ORO_MACRO.md"), encoding="utf-8").read(), "el original no se toca"
ind = {x["id"]: x for x in A.indice_vigente(R)}
assert ind["2026-10-20_ORO_MACRO"]["estado"] == "REVISADA" and ind["2026-10-20_ORO_MACRO_v2"]["estado"] == "VIGENTE"
filas_ind = A.leer_csv(os.path.join(R, "data", "analisis_indice.csv"))
assert [(x["id"], x["estado"]) for x in filas_ind] == [("2026-10-20_ORO_MACRO", "VIGENTE"), ("2026-10-20_ORO_MACRO", "REVISADA"), ("2026-10-20_ORO_MACRO_v2", "VIGENTE")], "solo añadir: la VIGENTE antigua sigue en el CSV"
pub = open(r2["ruta_publica"], encoding="utf-8").read()
assert "# RESUMEN (el informe completo es privado)" in pub and "Escenario 1: Base" in pub and "cierre diario sobre 4.150" in pub and "Sesión asiática" not in pub and "| US 2Y |" not in pub and FRASE_PRIVADA in pub, "resumen: tesis, veredicto, K.2 y escenarios; sin los bloques A–K (la tesis central es parte del resumen)"
try:
    PU.escribir_privado("analisis/2026/2026-10-20_ORO_MACRO.md", "otro contenido", PRIV)
    raise SystemExit("debía negarse a sobrescribir")
except RuntimeError as e:
    assert "no se sobrescribe" in str(e)
print("5b) OK mismo hash no escribe; edición → _v2 y el anterior REVISADA (fila nueva, nada se borra ni se sobrescribe); visibilidad resumen: solo tesis, veredicto, K.2 y escenarios")

# ---------------------------------------------------------------- 6) resultado del sesgo a T+1 y T+5 (reglas fijas) y acumulado
V = A.veredicto
assert V("alcista", 1, 0.3, -0.2, -5) == "CUMPLIDO" and V("alcista", 1, 0.26, 0.2, 5) == "MIXTO" and V("alcista", 1, 0.25, -0.2, -5) == "MIXTO" and V("alcista", 1, -0.26, -0.2, -5) == "FALLIDO"
assert V("alcista", 1, 0.3, 0.2, -5) == "CUMPLIDO", "solo uno de DXY/DFII10 en contra no degrada"
assert V("bajista", 5, -1.0, 0.1, 3) == "CUMPLIDO" and V("bajista", 5, -1.0, -0.1, -3) == "MIXTO" and V("bajista", 5, 0.5, 0, 0) == "FALLIDO"
assert V("neutral", 1, 0.5, None, None) == "CUMPLIDO" and V("neutral", 1, 0.51, None, None) == "FALLIDO" and V("neutral", 5, -1.5, 0, 0) == "CUMPLIDO" and V("neutral", 5, 1.51, 0, 0) == "FALLIDO"
with open(os.path.join(R, "data", "historico_precios.csv"), "a", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh)
    for d, o, x in (("2026-10-21", 4150.0, 101.6), ("2026-10-22", 4160.0, 101.5), ("2026-10-23", 4170.0, 101.4), ("2026-10-26", 4180.0, 101.3), ("2026-10-27", 4190.0, 101.2), ("2026-10-28", 4200.0, 101.1)):
        w.writerow(["x", "oro", o, d, 0, "t"])
        w.writerow(["x", "dxy", x, d, 0, "t"])
with open(os.path.join(R, "data", "historico_tipos.csv"), "a", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh)
    for d, v in (("2026-10-21", 2.60), ("2026-10-28", 2.50)):
        w.writerow(["x", "real10", v, d, 0, "t"])
# el análisis vigente del 20-oct es v2 (alcista); oro 20-oct = 4142,5 (histórico propio)
n = A.evaluar(R, ahora + dt.timedelta(days=9))
res = A.leer_csv(os.path.join(R, "data", "analisis_resultados.csv"))
t1 = next(x for x in res if x["horizonte"] == "1")
t5 = next(x for x in res if x["horizonte"] == "5")
assert n == 2 and t1["fecha_t"] == "2026-10-21" and t1["id"] == "2026-10-20_ORO_MACRO_v2|T+1" and t1["sesgo_oro"] == "alcista" and abs(float(t1["oro_pct"]) - round((4150 / 4142.5 - 1) * 100, 3)) < 1e-9
assert t5["fecha_t"] == "2026-10-27" and t5["veredicto"] == "CUMPLIDO" and t5["dfii10_pb"] == "" and float(t5["oro_pct"]) > 1.0, "T+5 (27-oct): oro +1,15 %; sin DFII10 de esa fecha queda vacío, no se inventa"
assert t1["dxy_var"] == str(round(101.6 - 101.76, 3)) and t1["dfii10_pb"] == str(round((2.60 - 2.64) * 100, 1)) and t1["veredicto"] == "MIXTO", "T+1: oro +0,18 % (menos de 0,25 %) → MIXTO"
assert A.evaluar(R, ahora + dt.timedelta(days=10)) == 0 and len(A.leer_csv(os.path.join(R, "data", "analisis_resultados.csv"))) == 2, "idempotente: solo añadir"
assert all(x["id"].split("|")[0] != "2026-10-20_ORO_MACRO" for x in res), "el análisis REVISADA no se evalúa; solo el vigente"
ac = A.acumulado(res)
assert ac["T+1"]["n"] == 1 and ac["T+1"]["conclusion"] == "n<20: sin conclusión" and ac["T+5"]["acierto_pct"] in (0.0, 100.0)
J = A.etapa(R, ahora + dt.timedelta(days=10))
assert J["acumulado"]["T+1"]["conclusion"] == "n<20: sin conclusión" and J["resultados_nuevos"] == 0 and next(e for e in J["entradas"] if e["id"].endswith("_v2"))["resultados"][0]["horizonte"] in ("1", 1)
print("6) OK resultado del sesgo: reglas fijas en los bordes, T+1 y T+5 con oro, DXY y DFII10, solo añadir, solo el análisis vigente, acumulado «n<20: sin conclusión»")

# ---------------------------------------------------------------- 7) umbral = EM del oro de ese día (T+5: EM × √5); sin EM, % fijos y umbral FIJO
V = A.veredicto
r5 = 5 ** 0.5
# EM bajo (0,8 %): umbral direccional 0,3 × 0,8 = 0,24 %
assert V("alcista", 1, 0.24, 0, 0, 0.8) == "CUMPLIDO" and V("alcista", 1, 0.2399, 0, 0, 0.8) == "MIXTO" and V("alcista", 1, -0.24, 0, 0, 0.8) == "FALLIDO" and V("alcista", 1, -0.2399, 0, 0, 0.8) == "MIXTO"
assert V("bajista", 1, -0.24, 0, 0, 0.8) == "CUMPLIDO" and V("bajista", 1, 0.24, 0, 0, 0.8) == "FALLIDO" and V("bajista", 1, 0.2399, 0, 0, 0.8) == "MIXTO"
assert V("alcista", 5, 0.54, 0, 0, 0.8) == "CUMPLIDO" and V("alcista", 5, 0.53, 0, 0, 0.8) == "MIXTO" and V("alcista", 5, -0.54, 0, 0, 0.8) == "FALLIDO", "T+5: 0,3 × 0,8 × √5 = 0,5367 %"
assert V("neutral", 1, 0.4, 0, 0, 0.8) == "CUMPLIDO" and V("neutral", 1, 0.41, 0, 0, 0.8) == "MIXTO" and V("neutral", 1, -0.8, 0, 0, 0.8) == "MIXTO" and V("neutral", 1, 0.81, 0, 0, 0.8) == "FALLIDO"
# EM alto (2,0 %): umbral 0,6 %; con +0,5 % el % fijo daría CUMPLIDO y con EM es MIXTO
assert V("alcista", 1, 0.5, 0, 0, 2.0) == "MIXTO" and V("alcista", 1, 0.5, 0, 0, None) == "CUMPLIDO" and V("alcista", 1, 0.6, 0, 0, 2.0) == "CUMPLIDO" and V("alcista", 1, -0.6, 0, 0, 2.0) == "FALLIDO"
assert V("neutral", 1, 1.0, 0, 0, 2.0) == "CUMPLIDO" and V("neutral", 1, 1.5, 0, 0, 2.0) == "MIXTO" and V("neutral", 1, 2.0, 0, 0, 2.0) == "MIXTO" and V("neutral", 1, 2.01, 0, 0, 2.0) == "FALLIDO"
assert V("neutral", 5, 2.2, 0, 0, 2.0) == "CUMPLIDO" and V("neutral", 5, 4.4, 0, 0, 2.0) == "MIXTO" and V("neutral", 5, 4.5, 0, 0, 2.0) == "FALLIDO", "T+5 neutral: 0,5 × 2 × √5 = 2,236 %; 1 × 2 × √5 = 4,472 %"
# se mantiene la degradación a MIXTO si DXY y DFII10 van ambos en contra
assert V("alcista", 1, 1.0, 0.2, 5, 0.8) == "MIXTO" and V("alcista", 1, 1.0, 0.2, -5, 0.8) == "CUMPLIDO" and V("bajista", 1, -1.0, -0.2, -5, 0.8) == "MIXTO" and V("neutral", 1, 0.1, 0.2, 5, 0.8) == "CUMPLIDO"
# sin EM: los % fijos de siempre
assert V("alcista", 1, 0.26, 0, 0) == "CUMPLIDO" and V("alcista", 1, 0.25, 0, 0) == "MIXTO" and V("neutral", 5, 1.5, 0, 0) == "CUMPLIDO" and V("neutral", 5, 1.51, 0, 0) == "FALLIDO"
# de extremo a extremo: día de EM alto, día de EM bajo y día sin EM, mismo movimiento del oro (+0,5 %)
R3 = nueva_raiz()
with open(os.path.join(R3, "data", "historico_precios.csv"), "a", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh)
    for d, o, x in (("2026-10-21", 4163.2, 101.6), ("2026-10-22", 4184.0, 101.5), ("2026-10-23", 4204.9, 101.4)):
        w.writerow(["x", "oro", o, d, 0, "t"])
        w.writerow(["x", "dxy", x, d, 0, "t"])
with open(os.path.join(R3, "data", "historico_tipos.csv"), "a", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh)
    for d, v in (("2026-10-21", 2.60), ("2026-10-22", 2.55), ("2026-10-23", 2.50)):
        w.writerow(["x", "real10", v, d, 0, "t"])
with open(os.path.join(R3, "data", "historico_gamma_oro.csv"), "w", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["fecha_sesion", "gld_spot", "em_gld"])
    w.writerow(["2026-10-20", 377.77, 7.5554])      # EM 2,0 % (alto)
    w.writerow(["2026-10-21", 380.0, 3.04])         # EM 0,8 % (bajo)
PRIV3 = tempfile.mkdtemp(prefix="priv3_")
for fch in ("2026-10-20", "2026-10-21", "2026-10-22"):
    PU.publicar(INFORME.replace("20-10-2026", fch[8:] + "-10-2026") + f"\nvariante {fch}", "alcista", "ORO_MACRO", "privado", fecha=fch, raiz=R3, solo_local=PRIV3, ahora=dt.datetime(2026, 10, 23, 8, 0, tzinfo=UTC))
A.evaluar(R3, dt.datetime(2026, 10, 24, 8, 0, tzinfo=UTC))
rr = {x["id"]: x for x in A.leer_csv(os.path.join(R3, "data", "analisis_resultados.csv"))}
alto, bajo, sin = rr["2026-10-20_ORO_MACRO|T+1"], rr["2026-10-21_ORO_MACRO|T+1"], rr["2026-10-22_ORO_MACRO|T+1"]
assert alto["umbral"] == "EM" and float(alto["umbral_pct"]) == 2.0 and float(alto["oro_pct"]) > 0.49 and alto["veredicto"] == "MIXTO", "EM alto: +0,5 % no llega a 0,3 × 2,0 = 0,6 % → MIXTO"
assert bajo["umbral"] == "EM" and float(bajo["umbral_pct"]) == 0.8 and bajo["veredicto"] == "CUMPLIDO", "EM bajo: +0,5 % supera 0,3 × 0,8 = 0,24 % → CUMPLIDO (DXY y DFII10 a favor)"
assert sin["umbral"] == "FIJO" and sin["umbral_pct"] == "" and sin["veredicto"] == "CUMPLIDO", "sin EM ese día: % fijos y umbral FIJO"
assert float(A.leer_csv(os.path.join(R3, "data", "analisis_resultados.csv"))[0]["umbral_pct"] or 0) >= 0
assert "umbral" in A.CAMPOS_RES and "0,3 × EM" in A.construir(R3)["reglas"] and "EM × √5" in A.construir(R3)["reglas"]
print("7) OK umbral = EM del oro del día (T+5: EM × √5): día de EM alto (+0,5 % → MIXTO) y de EM bajo (+0,5 % → CUMPLIDO), neutral con MIXTO entre 0,5 y 1 × EM, degradación por DXY y DFII10, y sin EM → % fijos con umbral FIJO")

for d in (R, PRIV, R3, PRIV3):
    shutil.rmtree(d, ignore_errors=True)
print("\nTODO OK · sin red, sin GitHub, sin Telegram")
