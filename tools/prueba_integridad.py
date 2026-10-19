#!/usr/bin/env python3
"""Prueba de integridad de datos con datos SIMULADOS en carpeta temporal. Telegram es una función falsa (nada se envía), BLS y ALFRED son simulados (sin red).
Uso:  python tools/prueba_integridad.py"""
import csv
import datetime as dt
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import integridad as I  # noqa: E402

for k in ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"):
    os.environ.pop(k, None)
UTC = dt.timezone.utc


def nueva():
    T = tempfile.mkdtemp(prefix="integ_")
    os.makedirs(os.path.join(T, "site/data"))
    os.makedirs(os.path.join(T, "data"))
    return T


def wj(T, rel, obj):
    json.dump(obj, open(os.path.join(T, rel), "w", encoding="utf-8"), ensure_ascii=False)


def wcsv(T, rel, filas):
    with open(os.path.join(T, rel), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys())); w.writeheader(); w.writerows(filas)


def en(f, h):
    return dt.datetime.fromisoformat(f + "T" + h).replace(tzinfo=UTC)


ENV = []
def falso_ok(t):
    ENV.append(t); return True, None
def falso_fallo(t):
    return False, "HTTP 500 simulado"
def prohibido(t):
    raise AssertionError("en modo seco no se puede enviar")


def agenda(T, evs):
    wj(T, "site/data/agenda.json", {"agenda": {"hoy": evs, "proximos_7_dias": []}})


def pub(T, periodos_cpi, periodos_core=None):
    mk = lambda ps: {"periodos": [{"periodo": p, "valor": 3.0} for p in ps]}
    wj(T, "site/data/publicados.json", {"series": {"IPC EE. UU. (CPI)": mk(periodos_cpi), "IPC subyacente": mk(periodos_core if periodos_core is not None else periodos_cpi)}})


CPI = {"fecha": "2026-10-14", "fecha_et": "2026-10-14", "hora_ny": "08:30", "evento": "IPC EE. UU. (CPI)", "importancia": "ALTA"}       # 12:30 UTC, 14:30 Madrid
T0 = en("2026-10-14", "12:30:00")

# ================================================================ 1) periodos esperados por tipo de dato
d = dt.date
assert I.periodo_esperado("mes", 1, d(2026, 10, 14)) == d(2026, 9, 1)                      # IPC de octubre-14 → septiembre
assert I.periodo_esperado("mes", 1, d(2026, 10, 2)) == d(2026, 9, 1)                       # NFP
assert I.periodo_esperado("mes", 2, d(2026, 10, 6)) == d(2026, 8, 1)                       # JOLTS (dos meses)
assert I.periodo_esperado("mes", 1, d(2026, 1, 14)) == d(2025, 12, 1)                      # cambio de año
assert I.periodo_esperado("semana", 1, d(2026, 10, 15)) == d(2026, 10, 10)                 # peticiones (jueves → sábado anterior)
assert I.periodo_esperado("semana", 1, d(2026, 10, 14)) == d(2026, 10, 10)                 # si se adelanta al miércoles
assert I.periodo_esperado("trimestre", 1, d(2026, 10, 29)) == d(2026, 7, 1)                # PIB avance T3
assert I.periodo_esperado("trimestre", 1, d(2026, 1, 29)) == d(2025, 10, 1)                # PIB avance T4 (cambio de año)
print("1) OK periodos esperados: IPC, NFP, JOLTS (2 meses), peticiones (sábado), PIB (trimestre) y cambios de año")

# ================================================================ 2) vigilante: dato que NO llega
T = nueva(); agenda(T, [CPI]); pub(T, ["2026-08-01"])           # septiembre NO está registrado
for m, n in ((119, 0), (120, 2), (47 * 60, 2), (49 * 60, 0)):
    r = I.vigilar(T, T0 + dt.timedelta(minutes=m), seco=True, enviar=prohibido)
    assert len(r) == n, (m, r)
print("2) OK ventana del vigilante: 1 h 59 → nada · 2 h → avisa · 47 h → avisa · 49 h → ya no")
ENV.clear()
r = I.vigilar(T, T0 + dt.timedelta(hours=2, minutes=5), enviar=falso_ok)
assert sorted(x[1] for x in r) == ["AVISADO", "AVISADO"] and len(ENV) == 2, "IPC general y subyacente: un aviso por dato"
txt = ENV[0]
assert "DATO NO REGISTRADO" in txt and "septiembre 2026" in txt and "14:30" in txt and "IPC" in txt
print("   mensaje:", txt.replace("\n", " | "))
assert I.vigilar(T, T0 + dt.timedelta(hours=3), enviar=falso_ok) == [] and len(ENV) == 2, "un solo aviso por dato"
est = json.load(open(os.path.join(T, "data/vigilante_estado.json"), encoding="utf-8"))
k = list(est["avisos"])[0]; antes = dict(est["avisos"][k])
I._guardar_v(T, est, {k: {"estado": "OTRA"}, "x|y": {"estado": "AVISADO"}})
est2 = json.load(open(os.path.join(T, "data/vigilante_estado.json"), encoding="utf-8"))
assert est2["avisos"][k] == antes and "x|y" in est2["avisos"]
print("   OK un solo aviso por dato; el estado solo añade claves")

# dato a tiempo: septiembre sí está registrado → sin aviso
T = nueva(); agenda(T, [CPI]); pub(T, ["2026-08-01", "2026-09-01"])
assert I.vigilar(T, T0 + dt.timedelta(hours=3), seco=True, enviar=prohibido) == []
print("3) OK dato a tiempo: periodo en publicados.json → sin aviso")
# solo el IPC general llega; el subyacente no → un único aviso, del subyacente
T = nueva(); agenda(T, [CPI]); pub(T, ["2026-08-01", "2026-09-01"], ["2026-08-01"])
r = I.vigilar(T, T0 + dt.timedelta(hours=3), seco=True, enviar=prohibido)
assert len(r) == 1 and "IPC subyacente" in r[0][2]
# Telegram falla → no se marca y se reintenta
r = I.vigilar(T, T0 + dt.timedelta(hours=3), enviar=falso_fallo)
assert r[0][1] == "ERROR" and not json.load(open(os.path.join(T, "data/vigilante_estado.json"), encoding="utf-8"))["avisos"]
assert I.vigilar(T, T0 + dt.timedelta(hours=3, minutes=5), enviar=falso_ok)[0][1] == "AVISADO"
print("   OK avisa solo del dato que falta; si Telegram falla se reintenta")
# peticiones semanales (jueves 08:30 ET) y PIB trimestral
T = nueva()
agenda(T, [{"fecha_et": "2026-10-15", "hora_ny": "08:30", "evento": "Peticiones semanales de paro", "importancia": "MEDIA"}, {"fecha_et": "2026-10-29", "hora_ny": "08:30", "evento": "PIB EE. UU. (avance)", "importancia": "ALTA"}])
wj(T, "site/data/publicados.json", {"series": {"Peticiones semanales de paro": {"periodos": [{"periodo": "2026-10-03"}]}, "PIB EE. UU.": {"periodos": [{"periodo": "2026-04-01"}]}}})
p1 = I.pendientes_vigilante(T, en("2026-10-15", "16:00:00"))
assert [(s["sid"], p.isoformat()) for s, e, p in p1] == [("ICSA", "2026-10-10")]
p2 = I.pendientes_vigilante(T, en("2026-10-29", "16:00:00"))
assert [(s["sid"], p.isoformat()) for s, e, p in p2] == [("GDPC1", "2026-07-01")]
assert I.texto_periodo(dt.date(2026, 7, 1), "trimestre") == "T3 2026" and I.texto_periodo(dt.date(2026, 10, 10), "semana") == "semana del 10 oct 2026"
print("   OK peticiones (semana del 10 oct) y PIB (T3 2026)")

# ================================================================ 4) segunda fuente: BLS
class RedFalsa:
    def __init__(self, bls=None, alf=None):
        self.b, self.a, self.n = bls, alf, 0
    def bls(self, ids, anio):
        self.n += 1
        if isinstance(self.b, Exception):
            raise self.b
        return self.b
    def alfred_tiene(self, sid, periodo, vintage):
        return self.a(sid, periodo, vintage)

T = nueva()
wcsv(T, "data/publicaciones_macro.csv", [
    {"fecha_captura": "2026-10-15", "serie": "CPIAUCSL", "periodo": "2026-09-01", "valor": "336.298", "tipo": "PRIMERA"},
    {"fecha_captura": "2026-10-15", "serie": "CPILFESL", "periodo": "2026-09-01", "valor": "338.896", "tipo": "PRIMERA"},
    {"fecha_captura": "2026-10-16", "serie": "PPIFIS", "periodo": "2026-09-01", "valor": "159.78", "tipo": "PRIMERA"}])
ok = {"CUSR0000SA0": {(2026, 9): 336.298, (2026, 8): 334.131}, "CUSR0000SA0L1E": {(2026, 9): 338.896}, "WPSFD4": {(2026, 9): 159.78}}
ahora = en("2026-10-18", "12:00:00")
assert I.cotejar_bls(T, ahora, RedFalsa(ok)) == [], "valores iguales: sin discrepancia"
print("4) OK FRED = BLS (IPC, subyacente, IPP): sin discrepancia")
# diferencia 0,10 % > 0,05 % → ABIERTA, manda BLS
mal = {**ok, "CUSR0000SA0": {(2026, 9): 336.298 * 1.001}}
nuevas = I.cotejar_bls(T, ahora + dt.timedelta(hours=1), RedFalsa(mal), forzar=True)
assert [(r["serie"], r["tipo"], r["estado"]) for r in nuevas] == [("CPIAUCSL", "VALOR", "ABIERTA")]
assert nuevas[0]["primaria"].startswith("BLS") and float(nuevas[0]["dif_pct"]) > 0.05 and "Manda BLS" in nuevas[0]["nota"]
print("   OK diferencia %s %% > 0,05 %% → DISCREPANCIA abierta (primaria BLS)" % nuevas[0]["dif_pct"][:6])
# 0,03 % no es discrepancia
tol = {**mal, "CUSR0000SA0L1E": {(2026, 9): 338.896 * 1.0003}}
assert I.cotejar_bls(T, ahora + dt.timedelta(hours=2), RedFalsa(tol), forzar=True) == []
# no se duplica la abierta
assert I.cotejar_bls(T, ahora + dt.timedelta(hours=3), RedFalsa(mal), forzar=True) == []
# se cierra cuando coinciden (fila nueva; la anterior no se toca)
antes_csv = open(os.path.join(T, "data/discrepancias.csv"), "rb").read()
cerr = I.cotejar_bls(T, ahora + dt.timedelta(hours=4), RedFalsa(ok), forzar=True)
assert [(r["serie"], r["estado"]) for r in cerr if r["serie"] == "CPIAUCSL"] == [("CPIAUCSL", "CERRADA")]
assert open(os.path.join(T, "data/discrepancias.csv"), "rb").read().startswith(antes_csv), "append-only"
assert not [1 for r in I.discrepancias(T).values() if r["estado"] == "ABIERTA"]
print("   OK no se duplica y se cierra con una fila CERRADA (append-only)")
# periodo distinto: BLS ya tiene octubre y FRED no
T2 = nueva()
wcsv(T2, "data/publicaciones_macro.csv", [{"fecha_captura": "2026-10-15", "serie": "CPIAUCSL", "periodo": "2026-09-01", "valor": "336.298", "tipo": "PRIMERA"}])
nuevo = {"CUSR0000SA0": {(2026, 9): 336.298, (2026, 10): 337.5}, "CUSR0000SA0L1E": {}, "WPSFD4": {}}
r = I.cotejar_bls(T2, en("2026-11-12", "15:00:00"), RedFalsa(nuevo), forzar=True)
assert [(x["tipo"], x["estado"]) for x in r] == [("PERIODO", "ABIERTA")] and r[0]["fred_valor"] == "2026-09" and r[0]["primaria_valor"] == "2026-10"
print("   OK periodo distinto (FRED sep, BLS oct) → DISCREPANCIA de periodo")
# BLS cae: no rompe ni inventa; el cupo diario se respeta
T3 = nueva()
wcsv(T3, "data/publicaciones_macro.csv", [{"fecha_captura": "2026-10-15", "serie": "CPIAUCSL", "periodo": "2026-09-01", "valor": "336.298", "tipo": "PRIMERA"}])
rf = RedFalsa(RuntimeError("BLS caído"))
assert I.cotejar_bls(T3, ahora, rf, forzar=True) == []
for i in range(12):
    I.cotejar_bls(T3, ahora + dt.timedelta(minutes=i), rf, forzar=True)
assert rf.n <= I.BLS_MAX_DIA, rf.n
assert "BEA" in I.BEA_SIN_DATO and I.SEGUNDA_FUENTE["PCEPI"] == "BEA" and I.SEGUNDA_FUENTE["GDPC1"] == "BEA"
print("   OK BLS caído → sin datos inventados; cupo diario respetado (%d consultas); PIB/PCE: BEA exige clave → SIN DATO" % rf.n)

# ================================================================ 5) publicación oficial (ALFRED) simulada
publicada = dt.date(2026, 10, 14)
alf = lambda sid, per, vint: vint >= publicada
f = I.fecha_publicacion_alfred("CPIAUCSL", dt.date(2026, 9, 1), "mes", dt.date(2026, 10, 18), RedFalsa(alf=alf))
assert f == publicada, f
assert I.fecha_publicacion_alfred("CPIAUCSL", dt.date(2026, 10, 1), "mes", dt.date(2026, 11, 5), RedFalsa(alf=lambda s, p, v: False)) is None
def rota(s, p, v):
    raise OSError("sin red")
assert I.fecha_publicacion_alfred("CPIAUCSL", dt.date(2026, 9, 1), "mes", dt.date(2026, 10, 18), RedFalsa(alf=rota)) is None
print("5) OK ALFRED: encuentra el primer día de publicación (14-oct); aún no publicado → None; sin red → None (SIN DATO, no se estima)")

# ================================================================ 6) retraso de registro + tabla publicados + próximo dato
T = nueva()
mk = lambda ps: {"periodos": [{"periodo": p, "valor": 3.1} for p in ps]}
wj(T, "site/data/publicados.json", {"series": {"IPC EE. UU. (CPI)": mk(["2026-08-01", "2026-09-01"]), "IPP EE. UU. (PPI)": mk(["2026-09-01"])}})
wcsv(T, "data/publicaciones_macro.csv", [
    {"fecha_captura": "2026-10-08", "serie": "CPIAUCSL", "periodo": "2026-08-01", "valor": "334.131", "tipo": "HISTÓRICO (carga inicial)"},
    {"fecha_captura": "2026-10-15", "serie": "CPIAUCSL", "periodo": "2026-09-01", "valor": "336.298", "tipo": "PRIMERA"},
    {"fecha_captura": "2026-10-16", "serie": "PPIFIS", "periodo": "2026-09-01", "valor": "159.78", "tipo": "PRIMERA"}])
wcsv(T, "data/publicacion_oficial.csv", [{"serie": "CPIAUCSL", "periodo": "2026-08-01", "publicado": "2026-09-11", "fuente": "ALFRED", "capturado_utc": "x"},
                                         {"serie": "CPIAUCSL", "periodo": "2026-09-01", "publicado": "2026-10-14", "fuente": "ALFRED", "capturado_utc": "x"},
                                         {"serie": "PPIFIS", "periodo": "2026-09-01", "publicado": "2026-10-15", "fuente": "ALFRED", "capturado_utc": "x"}])
agenda(T, [{"fecha_et": "2026-11-12", "hora_ny": "08:30", "evento": "IPC EE. UU. (CPI)", "importancia": "ALTA"}])
tab = {(x["serie"], x["periodo"]): x for x in I.tabla_publicaciones(T, en("2026-10-18", "12:00:00"))}
c = tab[("CPIAUCSL", "2026-09-01")]
assert c["dato_de"] == "septiembre 2026" and c["publicado"] == "2026-10-14" and c["registrado"] == "2026-10-15" and c["retraso_dias"] == 1
assert tab[("PPIFIS", "2026-09-01")]["retraso_dias"] == 1
assert tab[("CPIAUCSL", "2026-08-01")]["retraso_dias"] is None and tab[("CPIAUCSL", "2026-08-01")]["registro_origen"] == "carga inicial"
assert c["proximo"]["texto"] == "IPC de octubre · 12-nov", c["proximo"]
print("6) OK IPC sep: publicado 14-oct, registrado 15-oct → retraso 1 d; IPP 1 d; carga inicial sin retraso; próximo = «%s»" % c["proximo"]["texto"])

# ================================================================ 7) semáforo por bloque
T = nueva()
ahora = en("2026-10-17", "10:00:00")             # sábado 10:00 UTC
meta = {"etapas": {"precios": {"ok": True, "ultimo_ok_utc": "2026-10-16 22:07 UTC"},          # viernes 22:07: última programada → verde
                   "fedwatch": {"ok": True, "ultimo_ok_utc": "2026-10-15 09:07 UTC"},          # 37 h de retraso → ámbar
                   "ciclo": {"ok": True, "ultimo_ok_utc": "2026-10-17 05:31 UTC"},             # diario de hoy → verde
                   "liquidez": {"ok": False, "ultimo_ok_utc": "2026-10-17 05:31 UTC"},         # falló la última ejecución → ámbar
                   "cot": {"ok": False, "ultimo_ok_utc": None}}}                              # nunca → gris
wj(T, "site/data/meta.json", {"etapas": meta["etapas"]})
col = {b["etapa"]: b for b in I.estado_bloques(T, ahora, 0)}
assert col["precios"]["color"] == "verde" and col["fedwatch"]["color"] == "ambar" and col["ciclo"]["color"] == "verde" and col["liquidez"]["color"] == "ambar" and col["cot"]["color"] == "gris"
assert col["tipos"]["color"] == "gris", "una etapa que no está en meta es SIN DATO"
assert I.ultima_programada("horario", en("2026-10-17", "10:00:00")) == en("2026-10-16", "22:07:00")
assert I.proxima_programada("horario", en("2026-10-17", "10:00:00")) == en("2026-10-19", "06:07:00")
print("7) OK semáforo: verde / ámbar (retrasado o falló la última) / gris (SIN DATO); el fin de semana no cuenta como retraso (próximo: lunes 06:07 UTC)")
J = I.construir(T, ahora)
assert J["resumen"]["texto"].startswith("Integridad: 2/") and J["resumen"]["al_dia"] == 2
wcsv(T, "data/discrepancias.csv", [{"id": "a", "detectada_utc": "x", "serie": "CPIAUCSL", "periodo": "2026-09-01", "tipo": "VALOR", "fred_valor": "1", "primaria": "BLS X", "primaria_valor": "2", "dif_pct": "9", "estado": "ABIERTA", "nota": "n"}])
wj(T, "site/data/integridad.json", I.construir(T, ahora))
B = I.bloque_contexto(T)
assert B["DISCREPANCIAS_ABIERTAS"][0]["serie"] == "CPIAUCSL" and "BLS" in B["nota_discrepancias"] and B["resumen"].startswith("Integridad:")
assert [b for b in I.estado_bloques(T, ahora, 1) if b["etapa"] == "publicados"][0]["discrepancias_abiertas"] == 1
print("   OK resumen «%s»; la discrepancia abierta llega a contexto.json" % J["resumen"]["texto"])
# ================================================================ 8) calendario oficial anual (BLS/BEA) como respaldo del «próximo dato»
import calendario_oficial as CO  # noqa: E402

BLS_HTML = lambda filas: ('<table class="release-list"><thead><tr><th>Reference Month</th><th>Release Date</th><th>Release Time</th></tr></thead><tbody>'
                          + "".join(f'<tr class="release-list-even-row"><td>{m}</td><td>{f}</td><td>{h}</td></tr>' for m, f, h in filas) + "</tbody></table>")
BEA_HTML = lambda filas: ('<table id="release-schedule-table"><thead><tr><th id="x">Year 2026</th><th></th><th>Release</th></tr></thead><tbody>'
                          + "".join(f'<tr class="scheduled-releases-type-press"><td class="scheduled-date no-wrap"><div class="release-date">{d}</div> <small class="text-muted">{h}</small></td>'
                                    f'<td class="views-field"><div class="icon-letter"><span>N</span></div></td><td class="release-title views-field" headers="y">{t} </td></tr>' for d, h, t in filas) + "</tbody></table>")
PAG = {"cpi": BLS_HTML([("October 2026", "Nov. 10, 2026", "08:30 AM"), ("November 2026", "Dec. 10, 2026", "08:30 AM")]),
       "ppi": BLS_HTML([("October 2026", "Nov. 13, 2026", "08:30 AM")]), "empsit": BLS_HTML([("October 2026", "Nov. 06, 2026", "08:30 AM")]),
       "jolts": BLS_HTML([("October 2026", "Dec. 01, 2026", "10:00 AM")])}
BEA = BEA_HTML([("October 29", "8:30 AM", "GDP (Advance Estimate), 3rd Quarter 2026"), ("October 29", "8:30 AM", "Personal Income and Outlays, September 2026"),
                ("November 4", "8:30 AM", "GDP by State and Personal Income by State, 2nd Quarter 2026"), ("November 25", "8:30 AM", "Personal Income and Outlays, October 2026")])


def get_ok(url):
    if "bea.gov" in url:
        return BEA
    return PAG[url.rsplit("/", 1)[1].replace(".htm", "")]


T = nueva()
ahora = en("2026-10-18", "12:00:00")
C = CO.descargar(T, ahora, get_ok)
assert C["descargado_utc"] == "2026-10-18 12:00 UTC" and C["fuentes"]["BLS cpi"]["url"].startswith("https://www.bls.gov") and C["fuentes"]["BEA schedule"]["url"] == "https://www.bea.gov/news/schedule"
assert os.path.exists(os.path.join(T, "data/calendario_oficial_anual.json")) and not C["errores"]
assert CO.proximo(T, "CPIAUCSL", dt.date(2026, 10, 18))["fecha"] == "2026-11-10" and CO.proximo(T, "PPIFIS", dt.date(2026, 10, 18))["fecha"] == "2026-11-13"
assert CO.proximo(T, "PAYEMS", dt.date(2026, 10, 18))["fecha"] == "2026-11-06" and CO.proximo(T, "GDPC1", dt.date(2026, 10, 18))["periodo"] == "2026-07-01"
assert CO.proximo(T, "PCEPI", dt.date(2026, 10, 18))["fecha"] == "2026-10-29" and CO.proximo(T, "PCEPI", dt.date(2026, 10, 30))["fecha"] == "2026-11-25"
assert not [e for e in C["eventos"] if "State" in e["evento"]], "PIB por estados no es el PIB nacional"
assert CO.proximo(T, "ICSA", dt.date(2026, 10, 18)) is None, "una serie que no es de BLS/BEA no tiene respaldo oficial: SIN DATO"
print("8) OK calendario oficial: IPC 10-nov, IPP 13-nov, NFP 6-nov, PCE 29-oct, PIB T3 29-oct (con fuente y fecha de descarga)")
llamadas = []


def get_cuenta(u):
    llamadas.append(u)
    return get_ok(u)


CO.descargar(T, ahora + dt.timedelta(days=3), get_cuenta)
assert not llamadas, "dentro de la semana no se vuelve a descargar"


def get_roto(u):
    raise OSError("sin red")


C2 = CO.descargar(T, ahora + dt.timedelta(days=8), get_roto)
assert len(C2["eventos"]) == len(C["eventos"]) and C2["descargado_utc"] == "2026-10-18 12:00 UTC"
print("   OK una descarga por semana; si falla se conserva la copia anterior (no se pierde ni se inventa nada)")

T = nueva()
CO.descargar(T, ahora, get_ok)
mk = lambda ps: {"periodos": [{"periodo": p, "valor": 1.0} for p in ps]}
wj(T, "site/data/publicados.json", {"series": {"IPC EE. UU. (CPI)": mk(["2026-09-01"]), "IPP EE. UU. (PPI)": mk(["2026-09-01"]), "Empleo · nóminas no agrícolas": mk(["2026-09-01"]),
                                                  "Gasto personal (PCE)": mk(["2026-08-01"]), "PIB EE. UU.": mk(["2026-04-01"]), "Peticiones semanales de paro": mk(["2026-10-10"])}})
agenda(T, [])
g = lambda s: [x for x in I.tabla_publicaciones(T, ahora) if x["serie"] == s and x["proximo"]][0]["proximo"]
assert g("CPIAUCSL")["texto"] == "IPC de octubre · 10-nov" and "BLS" in g("CPIAUCSL")["fuente"] and "2026-10-18" in g("CPIAUCSL")["fuente"], g("CPIAUCSL")
assert g("PPIFIS")["texto"] == "IPP de octubre · 13-nov" and g("PAYEMS")["texto"] == "Nóminas (NFP) de octubre · 6-nov"
assert g("PCEPI")["texto"] == "PCE de septiembre · 29-oct" and g("PCEPI")["hora_madrid"] == "13:30" and "BEA" in g("PCEPI")["fuente"]
assert g("GDPC1")["texto"] == "PIB de T3 2026 · 29-oct"
assert [x for x in I.tabla_publicaciones(T, ahora) if x["serie"] == "ICSA" and x["proximo"]] == [], "sin calendario FRED ni oficial: SIN DATO"
print("   próximos con respaldo oficial → " + " | ".join(f"{k}: {g(k)['texto']} [{g(k)['fuente'].split(' (')[0]}]" for k in ("CPIAUCSL", "PPIFIS", "PAYEMS", "PCEPI", "GDPC1")))
agenda(T, [{"fecha_et": "2026-11-12", "hora_ny": "08:30", "evento": "IPC EE. UU. (CPI)", "importancia": "ALTA"}])
x = g("CPIAUCSL")
assert x["texto"].endswith("12-nov") and x["otra_fuente"]["texto"].endswith("10-nov") and "BLS" in x["otra_fuente"]["fuente"]
assert "fechas distintas" in x["discrepancia_calendario"], x
# JOLTS: FRED dice septiembre (3-nov) y BLS solo lista octubre (1-dic) → discrepancia de calendario por periodo
CO_J = CO.leer(T)
CO_J["eventos"].append({"organismo": "BLS", "series": ["JTSJOL"], "evento": "Vacantes JOLTS", "periodo": "2026-10-01", "fecha": "2026-12-01", "hora_et": "10:00", "url": "https://www.bls.gov/schedule/news_release/jolts.htm"})
json.dump(CO_J, open(os.path.join(T, "data/calendario_oficial_anual.json"), "w", encoding="utf-8"), ensure_ascii=False)
wj(T, "site/data/publicados.json", {"series": {"Ofertas de empleo (JOLTS)": mk(["2026-08-01"])}})
agenda(T, [{"fecha_et": "2026-11-03", "hora_ny": "10:00", "evento": "Vacantes JOLTS", "importancia": "MEDIA"}])
xj = [x for x in I.tabla_publicaciones(T, ahora) if x["serie"] == "JTSJOL" and x["proximo"]][0]["proximo"]
assert xj["texto"] == "JOLTS de septiembre · 3-nov" and xj["otra_fuente"]["texto"] == "JOLTS de octubre · 1-dic" and "no lista el periodo «septiembre 2026»" in xj["discrepancia_calendario"], xj
JJ = I.construir(T, ahora)
assert JJ["discrepancias_calendario"][0]["dato"] == "Ofertas de empleo (JOLTS)"
print("   OK JOLTS: FRED «septiembre · 3-nov» y BLS «octubre · 1-dic» → se dejan las dos y se marca DISCREPANCIA DE CALENDARIO (el oficial no lista septiembre)")
print("   OK si FRED dice 12-nov y BLS 10-nov se enseñan los dos (FRED en primer lugar, BLS como «calendario oficial»)")

# ================================================================ 9) hora de registro (registrado_utc) sin reescribir filas antiguas
import csvlog  # noqa: E402

T = nueva()
csvlog.DATA = os.path.join(T, "data")
cab = "fecha_captura,serie,nombre,periodo,valor,tipo,valor_previo_mismo_periodo,unidad,organismo,fuente"
viejo = cab + "\n2026-10-15,CPIAUCSL,IPC,2026-09-01,336.298,PRIMERA,,índice,BLS,FRED CPIAUCSL\n"
open(os.path.join(T, "data/publicaciones_macro.csv"), "w", encoding="utf-8", newline="").write(viejo)
filas_viejas = viejo.split("\n", 1)[1]
assert csvlog.asegurar_columna("publicaciones_macro.csv", "registrado_utc") is True and csvlog.asegurar_columna("publicaciones_macro.csv", "registrado_utc") is False
nuevo = open(os.path.join(T, "data/publicaciones_macro.csv"), encoding="utf-8", newline="").read()
assert nuevo.split("\n", 1)[0] == cab + ",registrado_utc" and nuevo.split("\n", 1)[1] == filas_viejas, "solo cambia la cabecera; las filas antiguas quedan idénticas"
csvlog.anadir("publicaciones_macro.csv", [{"fecha_captura": "2026-11-10", "serie": "CPIAUCSL", "nombre": "IPC", "periodo": "2026-10-01", "valor": "337.5", "tipo": "PRIMERA", "valor_previo_mismo_periodo": "", "unidad": "índice",
                                           "organismo": "BLS", "fuente": "FRED CPIAUCSL", "registrado_utc": "2026-11-10 14:07 UTC"}], ("serie", "periodo", "valor", "tipo"))
fl = I.leer_csv(os.path.join(T, "data/publicaciones_macro.csv"))
assert (fl[0].get("registrado_utc") or "") == "" and fl[1]["registrado_utc"] == "2026-11-10 14:07 UTC"
open(os.path.join(T, "data/otra.csv"), "wb").write(b"a,b\r\n1,2\r\n")
csvlog.asegurar_columna("otra.csv", "c")
assert open(os.path.join(T, "data/otra.csv"), "rb").read() == b"a,b,c\r\n1,2\r\n"
print("9) OK columna registrado_utc: solo cambia la cabecera (también con CRLF); filas antiguas intactas («solo fecha»); filas nuevas con fecha y hora")
T = nueva()
wj(T, "site/data/publicados.json", {"series": {"IPC EE. UU. (CPI)": mk(["2026-09-01", "2026-10-01"])}})
wcsv(T, "data/publicaciones_macro.csv", [
    {"fecha_captura": "2026-10-15", "serie": "CPIAUCSL", "periodo": "2026-09-01", "valor": "336.298", "tipo": "PRIMERA", "registrado_utc": ""},
    {"fecha_captura": "2026-11-10", "serie": "CPIAUCSL", "periodo": "2026-10-01", "valor": "337.5", "tipo": "PRIMERA", "registrado_utc": "2026-11-10 14:07 UTC"}])
wcsv(T, "data/publicacion_oficial.csv", [{"serie": "CPIAUCSL", "periodo": "2026-09-01", "publicado": "2026-10-14", "fuente": "ALFRED", "capturado_utc": "x"},
                                         {"serie": "CPIAUCSL", "periodo": "2026-10-01", "publicado": "2026-11-10", "fuente": "ALFRED", "capturado_utc": "x"}])
wcsv(T, "data/eventos_macro.csv", [{"fecha": "2026-10-14", "hora_madrid": "14:30", "evento": "IPC EE. UU. (CPI)", "importancia": "ALTA", "fuente": "x", "visto_utc": "x"}])
CO.descargar(T, en("2026-11-10", "20:00:00"), get_ok)
tb = {x["periodo"]: x for x in I.tabla_publicaciones(T, en("2026-11-11", "08:00:00")) if x["serie"] == "CPIAUCSL"}
assert tb["2026-10-01"]["registrado_utc"] == "2026-11-10 14:07 UTC" and tb["2026-10-01"]["retraso_horas"] == 0.6, tb["2026-10-01"]
assert tb["2026-09-01"]["registrado_utc"] is None and tb["2026-09-01"]["retraso_horas"] is None and tb["2026-09-01"]["retraso_dias"] == 1
print("   OK retraso en horas cuando hay hora (0,6 h = 14:07 − 13:30 UTC); filas antiguas: solo días (1 d)")

# ================================================================ 10) BEA opcional (PCE y PIB) con BEA_API_KEY
T = nueva()
wcsv(T, "data/publicaciones_macro.csv", [
    {"fecha_captura": "2026-10-30", "serie": "PCEPI", "periodo": "2026-09-01", "valor": "128.5", "tipo": "PRIMERA"},
    {"fecha_captura": "2026-10-30", "serie": "PCEPILFE", "periodo": "2026-09-01", "valor": "127.0", "tipo": "PRIMERA"},
    {"fecha_captura": "2026-10-29", "serie": "GDPC1", "periodo": "2026-07-01", "valor": "23500.5", "tipo": "PRIMERA"}])


class RedBEA:
    def __init__(self, tablas, falla=None):
        self.t, self.f, self.n = tablas, falla, 0

    def bea(self, clave, tabla, freq, anio):
        self.n += 1
        if self.f:
            raise self.f
        return self.t[tabla]


ok_b = {"T20804": [("Personal consumption expenditures (PCE)", (2026, 9), 128.5), ("PCE excluding food and energy", (2026, 9), 127.0), ("Personal consumption expenditures (PCE)", (2026, 8), 128.1)],
        "T10106": [("Gross domestic product", (2026, 3), 23500.5)]}
sin = RedBEA(ok_b)
assert I.cotejar_bea(T, en("2026-10-31", "10:00:00"), sin, clave="") == [] and sin.n == 0, "sin BEA_API_KEY: no se llama a nadie (SIN DATO)"
os.environ.pop("BEA_API_KEY", None)
sf = I.construir(T, en("2026-10-31", "10:00:00"))["segunda_fuente"]
assert "SIN DATO" in sf["BEA"] and sf["bea_activa"] is False
assert I.cotejar_bea(T, en("2026-10-31", "10:00:00"), RedBEA(ok_b), clave="SECRETO123", forzar=True) == []
mal_b = {**ok_b, "T10106": [("Gross domestic product", (2026, 3), 23700.0)]}
nb = I.cotejar_bea(T, en("2026-10-31", "11:00:00"), RedBEA(mal_b), clave="SECRETO123", forzar=True)
assert [(r["serie"], r["tipo"], r["estado"], r["primaria"]) for r in nb] == [("GDPC1", "VALOR", "ABIERTA", "BEA T10106")] and "Manda BEA" in nb[0]["nota"]
print("10) OK BEA: sin clave → SIN DATO y no se llama a la API; con clave → compara PCE y PIB (diferencia de 0,85 % → DISCREPANCIA, primaria BEA T10106)")
real = I.Red()
orig = I._get


def get_url_en_error(url, *a, **k):
    raise OSError("fallo con " + url)


I._get = get_url_en_error
try:
    real.bea("SECRETO123", "T10106", "Q", 2026)
    raise AssertionError("debía fallar")
except RuntimeError as e:
    assert "SECRETO123" not in str(e) and "http" not in str(e).lower(), str(e)
finally:
    I._get = orig
I.cotejar_bea(T, en("2026-10-31", "12:00:00"), RedBEA(ok_b, falla=RuntimeError("BEA no respondió (OSError)")), clave="SECRETO123", forzar=True)
estado_txt = open(os.path.join(T, "data/integridad_estado.json"), encoding="utf-8").read() + open(os.path.join(T, "data/discrepancias.csv"), encoding="utf-8").read()
assert "SECRETO123" not in estado_txt
print("    OK la clave no aparece en mensajes de error, estado ni CSV (el error solo dice «BEA no respondió (OSError)»)")

assert "telegram" not in sys.modules or not os.environ.get("TELEGRAM_TOKEN")
print("\nTODO OK · sin red, sin envíos reales")
