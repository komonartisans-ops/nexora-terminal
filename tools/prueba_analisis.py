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

BARRAS = {}          # hora UTC → precio del futuro del oro (barras de 5 min de la prueba)


def precio_en(t0):
    """La barra de 5 min más cercana ANTERIOR al corte (como la de Yahoo); los datos posteriores existen en BARRAS para comprobar que no se usan."""
    cand = sorted((h, v) for h, v in BARRAS.items() if A._utc(h) <= t0)
    if not cand:
        raise RuntimeError("sin barra anterior al corte")
    return cand[-1][1], cand[-1][0], "GC=F (barra de 5 min de la prueba)"


A.precio_base_yahoo = precio_en      # sin red: el precio base de los informes de prueba sale de BARRAS (vacío = sin barra → sin precio base)


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

# ---------------------------------------------------------------- 6) veredicto: reglas fijas en los bordes (EM, √5, neutral con MIXTO, degradación, FIJO)
V = A.veredicto
r5 = 5 ** 0.5
assert V("alcista", 1, 0.24, 0, 0, 0.8) == "CUMPLIDO" and V("alcista", 1, 0.2399, 0, 0, 0.8) == "MIXTO" and V("alcista", 1, -0.24, 0, 0, 0.8) == "FALLIDO" and V("alcista", 1, -0.2399, 0, 0, 0.8) == "MIXTO"
assert V("bajista", 1, -0.24, 0, 0, 0.8) == "CUMPLIDO" and V("bajista", 1, 0.24, 0, 0, 0.8) == "FALLIDO" and V("bajista", 1, 0.2399, 0, 0, 0.8) == "MIXTO"
assert V("alcista", 5, 0.54, 0, 0, 0.8) == "CUMPLIDO" and V("alcista", 5, 0.53, 0, 0, 0.8) == "MIXTO" and V("alcista", 5, -0.54, 0, 0, 0.8) == "FALLIDO"
assert V("neutral", 1, 0.4, 0, 0, 0.8) == "CUMPLIDO" and V("neutral", 1, 0.41, 0, 0, 0.8) == "MIXTO" and V("neutral", 1, -0.8, 0, 0, 0.8) == "MIXTO" and V("neutral", 1, 0.81, 0, 0, 0.8) == "FALLIDO"
assert V("alcista", 1, 0.5, 0, 0, 2.0) == "MIXTO" and V("alcista", 1, 0.5, 0, 0, None) == "CUMPLIDO" and V("alcista", 1, 0.6, 0, 0, 2.0) == "CUMPLIDO" and V("alcista", 1, -0.6, 0, 0, 2.0) == "FALLIDO"
assert V("neutral", 5, 2.2, 0, 0, 2.0) == "CUMPLIDO" and V("neutral", 5, 4.4, 0, 0, 2.0) == "MIXTO" and V("neutral", 5, 4.5, 0, 0, 2.0) == "FALLIDO"
assert V("alcista", 1, 1.0, 0.2, 5, 0.8) == "MIXTO" and V("alcista", 1, 1.0, 0.2, -5, 0.8) == "CUMPLIDO" and V("bajista", 1, -1.0, -0.2, -5, 0.8) == "MIXTO" and V("neutral", 1, 0.1, 0.2, 5, 0.8) == "CUMPLIDO"
assert V("alcista", 1, 0.26, 0, 0) == "CUMPLIDO" and V("alcista", 1, 0.25, 0, 0) == "MIXTO" and V("neutral", 5, 1.5, 0, 0) == "CUMPLIDO" and V("neutral", 5, 1.51, 0, 0) == "FALLIDO"
print("6) OK veredicto: umbral 0,3 × EM (×√5 a T+5), neutral 0,5/1 × EM con MIXTO, degradación por DXY y DFII10, sin EM → % fijos")

# ---------------------------------------------------------------- utilidades de los datos de prueba
def raiz_con_historico(oro, em_rows, dxy=None, real=None):
    t = nueva_raiz()
    for nombre in ("historico_precios.csv", "historico_tipos.csv"):
        os.remove(os.path.join(t, "data", nombre))
    with open(os.path.join(t, "data", "historico_precios.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["capturado_utc", "activo", "valor", "fecha_dato", "cambio_1d_pct", "fuente"])
        for d, v in oro.items():
            w.writerow([f"{d} 21:07 UTC", "oro", v, d, 0, "t"])
        for d, v in (dxy or {}).items():
            w.writerow([f"{d} 21:07 UTC", "dxy", v, d, 0, "t"])
    with open(os.path.join(t, "data", "historico_tipos.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["capturado_utc", "serie", "valor", "fecha_dato", "d1_pb", "fuente"])
        for d, v in (real or {}).items():
            w.writerow([f"{d} 21:07 UTC", "real10", v, d, 0, "t"])
    with open(os.path.join(t, "data", "historico_gamma_oro.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["fecha_sesion", "gld_spot", "em_gld", "medido_utc"])
        for ses, pct in em_rows.items():
            w.writerow([ses, 400.0, round(400.0 * pct / 100, 4), f"{ses} 21:30 UTC"])
    return t


def pub(R, texto, sesgo, tipo, fecha, ahora, priv, corte=None):
    return PU.publicar(texto, sesgo, tipo, "privado", fecha=fecha, corte=corte, raiz=R, solo_local=priv, ahora=ahora)


def rrd(R):
    return {x["id"]: x for x in A.leer_csv(os.path.join(R, "data", "analisis_resultados.csv"))}


def informe(fecha_ddmmaaaa, corte=None, extra=""):
    t = INFORME.replace("20-10-2026", fecha_ddmmaaaa).replace(" · corte 09:30 (Madrid)", f" · Corte: {corte}, hora de Madrid" if corte else "") + extra
    return t


# ---------------------------------------------------------------- 7) CORTE ≠ PUBLICACIÓN: informe del día D con corte 07:00 publicado a las 14:00
OROS = {"2026-10-21": 4020.0, "2026-10-22": 4020.0, "2026-10-23": 4030.0, "2026-10-26": 4040.0, "2026-10-27": 4050.0, "2026-10-28": 4060.0, "2026-10-29": 4070.0, "2026-10-30": 4040.0, "2026-11-02": 4045.0}
R4 = raiz_con_historico(OROS, {"2026-10-21": 0.8, "2026-10-22": 5.0, "2026-10-19": 3.0})        # EM de D-1 (21-oct) = 0,8 %; el de D (22-oct, 21:30 UTC) = 5,0 % es POSTERIOR al corte
BARRAS.update({"2026-10-22 04:55": 4000.0, "2026-10-22 05:00": 4001.0, "2026-10-22 05:05": 4010.0, "2026-10-22 12:00": 4100.0, "2026-10-22 14:00": 4105.0})      # 07:00 Madrid = 05:00 UTC
PRIV4 = tempfile.mkdtemp(prefix="priv4_")
r = pub(R4, informe("22-10-2026", "07:00"), "alcista", "DIARIO", None, dt.datetime(2026, 10, 22, 14, 0, tzinfo=UTC), PRIV4)
assert r["id"] == "2026-10-22_ORO_MACRO" and r["corte"] == "07:00" and r["corte_origen"] == "INFORME", "DIARIO = ORO_MACRO; el corte sale de «Corte: 07:00, hora de Madrid»"
ind = A.leer_csv(os.path.join(R4, "data", "analisis_indice.csv"))[0]
assert ind["corte_madrid"] == "07:00" and ind["corte_origen"] == "INFORME" and ind["publicado_utc"] == "2026-10-22 14:00 UTC" and ind["precio_base"] == "4001.0" and ind["precio_base_hora"] == "2026-10-22 05:00", "precio de las 07:00 (05:00 UTC), no el de las 14:00"
A.evaluar(R4, dt.datetime(2026, 11, 3, 8, 0, tzinfo=UTC))
t1 = rrd(R4)["2026-10-22_ORO_MACRO|T+1"]
assert t1["em_sesion"] == "2026-10-21" and t1["umbral"] == "EM" and float(t1["umbral_pct"]) == 0.8, "EM del cierre de D-1, nunca el posterior al corte (5,0 %)"
assert float(t1["precio_base"]) == 4001.0 and t1["precio_base_hora"] == "2026-10-22 05:00" and float(t1["precio_fin"]) == 4020.0 and t1["fecha_t"] == "2026-10-22", "T+1 = cierre de la primera sesión que termina después del corte (la del propio día D)"
assert abs(float(t1["oro_pct"]) - round((4020.0 / 4001.0 - 1) * 100, 3)) < 1e-9 and t1["veredicto"] == "CUMPLIDO", "+0,475 % frente a 0,3 × 0,8 = 0,24 % → CUMPLIDO"
t5 = rrd(R4)["2026-10-22_ORO_MACRO|T+5"]
assert t5["fecha_t"] == "2026-10-28" and float(t5["precio_fin"]) == 4060.0 and abs(float(t5["umbral_pct"]) - round(0.8 * r5, 3)) < 1e-9
# publicar a otra hora NO cambia nada de lo que se evalúa (mismo corte): solo cambia publicado_utc
R5 = raiz_con_historico(OROS, {"2026-10-21": 0.8, "2026-10-22": 5.0})
pub(R5, informe("22-10-2026", "07:00"), "alcista", "DIARIO", None, dt.datetime(2026, 10, 22, 19, 30, tzinfo=UTC), tempfile.mkdtemp(prefix="p5_"))
A.evaluar(R5, dt.datetime(2026, 11, 3, 8, 0, tzinfo=UTC))
a5 = rrd(R5)["2026-10-22_ORO_MACRO|T+1"]
assert (a5["precio_base"], a5["em_sesion"], a5["oro_pct"], a5["veredicto"]) == (t1["precio_base"], t1["em_sesion"], t1["oro_pct"], t1["veredicto"]) and A.leer_csv(os.path.join(R5, "data", "analisis_indice.csv"))[0]["publicado_utc"] == "2026-10-22 19:30 UTC"
# sin corte en el informe: la hora de publicación y corte_origen = ESTIMADO
R6 = raiz_con_historico(OROS, {"2026-10-21": 0.8})
r6 = pub(R6, informe("22-10-2026", None), "neutral", "DIARIO", None, dt.datetime(2026, 10, 22, 7, 10, tzinfo=UTC), tempfile.mkdtemp(prefix="p6_"))
i6 = A.leer_csv(os.path.join(R6, "data", "analisis_indice.csv"))[0]
assert r6["corte_origen"] == "ESTIMADO" and i6["corte_madrid"] == "09:10" and i6["corte_origen"] == "ESTIMADO" and "corte=ESTIMADO" in PU.salida(r6), "corte = hora de publicación en Madrid (07:10 UTC = 09:10)"
# precio base ausente: no se inventa y no se evalúa
BARRAS_COPIA = dict(BARRAS)
BARRAS.clear()
R7 = raiz_con_historico(OROS, {"2026-10-21": 0.8})
r7 = pub(R7, informe("22-10-2026", "07:00"), "alcista", "DIARIO", None, dt.datetime(2026, 10, 22, 14, 0, tzinfo=UTC), tempfile.mkdtemp(prefix="p7_"))
assert r7["precio_base"] is None and "sin precio base" in PU.salida(r7) and A.evaluar(R7, dt.datetime(2026, 11, 3, tzinfo=UTC)) == 0
BARRAS.update(BARRAS_COPIA)
print("7) OK corte ≠ publicación: informe del 22-oct con corte 07:00 publicado a las 14:00 usa el EM del cierre del 21-oct y el precio de las 07:00 (05:00 UTC), nunca datos posteriores; sin corte → ESTIMADO; sin precio base → no se evalúa")

# ---------------------------------------------------------------- 8) EM antiguo → FIJO; EM alto y bajo
R8 = raiz_con_historico(OROS, {"2026-10-20": 2.0, "2026-10-21": 0.8})
BARRAS.update({"2026-10-21 05:00": 4000.0, "2026-10-29 05:00": 4000.0, "2026-10-30 05:00": 4000.0})
PRIV8 = tempfile.mkdtemp(prefix="priv8_")
pub(R8, informe("21-10-2026", "07:00"), "alcista", "DIARIO", None, dt.datetime(2026, 10, 21, 8, 0, tzinfo=UTC), PRIV8)       # EM 20-oct = 2,0 % (alto): +0,5 % → MIXTO
pub(R8, informe("22-10-2026", "07:00"), "alcista", "DIARIO", None, dt.datetime(2026, 10, 22, 8, 0, tzinfo=UTC), PRIV8)       # EM 21-oct = 0,8 % (bajo): +0,5 % → CUMPLIDO
pub(R8, informe("30-10-2026", "07:00"), "alcista", "DIARIO", None, dt.datetime(2026, 10, 30, 8, 0, tzinfo=UTC), PRIV8)       # el EM más reciente (21-oct) tiene 7 días hábiles → FIJO
A.evaluar(R8, dt.datetime(2026, 11, 4, 8, 0, tzinfo=UTC))
o = rrd(R8)
alto, bajo, fijo = o["2026-10-21_ORO_MACRO|T+1"], o["2026-10-22_ORO_MACRO|T+1"], o["2026-10-30_ORO_MACRO|T+1"]
assert alto["umbral"] == "EM" and alto["em_sesion"] == "2026-10-20" and float(alto["umbral_pct"]) == 2.0 and abs(float(alto["oro_pct"]) - 0.5) < 1e-9 and alto["veredicto"] == "MIXTO", alto
assert bajo["umbral"] == "EM" and bajo["em_sesion"] == "2026-10-21" and float(bajo["umbral_pct"]) == 0.8 and bajo["veredicto"] == "CUMPLIDO", bajo
assert fijo["umbral"] == "FIJO" and fijo["em_sesion"] == "" and fijo["umbral_pct"] == "", "EM con más de 3 días hábiles → umbral FIJO"
assert A.em_oro_antes(R8, A.t0_utc("2026-10-26", "07:00"), "2026-10-26")[1] == "2026-10-21" and A.em_oro_antes(R8, A.t0_utc("2026-10-27", "07:00"), "2026-10-27") is None, "3 días hábiles de antigüedad aún valen (21→26); 4 ya no (21→27)"
assert A.em_oro_antes(R8, A.t0_utc("2026-10-21", "07:00"), "2026-10-21")[1] == "2026-10-20", "el EM del 21-oct (medido a las 21:30 UTC) es posterior al corte de las 07:00 del propio 21-oct"
print("8) OK EM: último guardado antes del corte; EM alto (+0,5 % → MIXTO) y bajo (→ CUMPLIDO); más de 3 días hábiles de antigüedad → umbral FIJO con em_sesion vacío")

# ---------------------------------------------------------------- 9) SEMANAL: archivo _semanal, base = cierre del viernes, umbral = EM del viernes × √5, acumulado aparte, enlace «Semanal vigente»
R9 = raiz_con_historico(OROS, {"2026-10-23": 1.0, "2026-10-22": 0.9})
BARRAS.update({"2026-10-23 20:55": 4000.0, "2026-10-25 15:00": 4000.0})
PRIV9 = tempfile.mkdtemp(prefix="priv9_")
inf_sem = informe("25-10-2026", "18:00")
rs = pub(R9, inf_sem, "alcista", "SEMANAL", None, dt.datetime(2026, 10, 25, 19, 0, tzinfo=UTC), PRIV9)
assert rs["id"] == "2026-10-25_semanal" and os.path.exists(os.path.join(PRIV9, "analisis", "2026", "2026-10-25_semanal.md")), "archivo AAAA-MM-DD_semanal.md"
assert "tipo: SEMANAL" in open(os.path.join(PRIV9, "analisis", "2026", "2026-10-25_semanal.md"), encoding="utf-8").read()
# diario del martes 27-oct (sesgo bajista, diverge del semanal alcista) y del lunes 26 (alcista, coincide)
pub(R9, informe("27-10-2026", "07:00"), "bajista", "DIARIO", None, dt.datetime(2026, 10, 27, 8, 0, tzinfo=UTC), PRIV9)
BARRAS.update({"2026-10-26 05:00": 4000.0})
pub(R9, informe("26-10-2026", "07:00"), "alcista", "DIARIO", None, dt.datetime(2026, 10, 26, 8, 0, tzinfo=UTC), PRIV9)
A.evaluar(R9, dt.datetime(2026, 11, 4, 8, 0, tzinfo=UTC))
o = rrd(R9)
sem = [k for k in o if k.startswith("2026-10-25_semanal")]
assert sem == ["2026-10-25_semanal|T+5"], "el semanal tiene UN resultado: la semana siguiente (sin T+1)"
w = o["2026-10-25_semanal|T+5"]
assert w["fecha_t"] == "2026-10-30" and float(w["precio_base"]) == 4000.0 and w["precio_base_hora"] == "2026-10-25 15:00" and float(w["precio_fin"]) == 4040.0 and abs(float(w["umbral_pct"]) - round(1.0 * r5, 3)) < 1e-9 and w["em_sesion"] == "2026-10-23"
assert w["veredicto"] == "CUMPLIDO" and abs(float(w["oro_pct"]) - 1.0) < 1e-9, "semana lunes-viernes: +1,0 % ≥ 0,3 × 1,0 × √5 = 0,67 %"
J = A.construir(R9, dt.datetime(2026, 11, 4, 8, 0, tzinfo=UTC))
ent = {e["id"]: e for e in J["entradas"]}
assert ent["2026-10-27_ORO_MACRO"]["semanal"] == {"id": "2026-10-25_semanal", "fecha": "2026-10-25", "sesgo_oro": "alcista", "coincide": False}, "diario bajista frente a semanal alcista: diverge"
assert ent["2026-10-26_ORO_MACRO"]["semanal"]["coincide"] is True and ent["2026-10-25_semanal"]["semanal"] is None and ent["2026-10-25_semanal"]["tipo"] == "SEMANAL"
ac = J["acumulado"]
assert ac["semanal"]["semana"]["n"] == 1 and ac["diario"]["T+1"]["n"] == 2 and ac["diario"]["T+5"]["n"] == 1 and ac["semanal"]["semana"]["conclusion"] == "n<20: sin conclusión", "acumulado del semanal separado del diario"
assert A.tipo_normal("diario") == "ORO_MACRO" and A.tipo_normal("SEMANAL") == "SEMANAL" and A.sufijo_tipo("SEMANAL") == "semanal" and A.sufijo_tipo("INDICES") == "INDICES"
print("9) OK SEMANAL: archivo _semanal, un resultado a la semana siguiente (base = último precio antes del corte, umbral = EM del viernes × √5), acumulado separado, y los diarios de la semana enlazan «Semanal vigente» (coincide / diverge)")

for d in (R, PRIV, R4, PRIV4, R5, R6, R7, R8, PRIV8, R9, PRIV9):
    shutil.rmtree(d, ignore_errors=True)
print("\nTODO OK · sin red, sin GitHub, sin Telegram")
