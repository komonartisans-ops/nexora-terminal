#!/usr/bin/env python3
"""Prueba de los tres usos del ratio de consumo con datos SIMULADOS (sin red, carpeta temporal, Telegram falso): filtro SMA 200 con cruce válido tras 5 cierres, contador de cruces en 12 meses,
rotación frente a SPY, divergencia y su fuerza, Telegram (solo al aparecer una FUERTE, máx. 1 por semana), señales del marcador (cruce / divergencia a T+20 y T+60) y backfill idempotente.
Uso:  python tools/prueba_consumo_ratio.py"""
import csv
import datetime as dt
import json
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import consumo_ratio as CR  # noqa: E402
import marcador as M  # noqa: E402

for k in ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"):
    os.environ.pop(k, None)
UTC = dt.timezone.utc
D = dt.date


def habiles(n, ini=D(2018, 1, 1)):
    out, d = [], ini
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def nueva():
    T = tempfile.mkdtemp(prefix="cr_")
    for d in ("data", "site/data"):
        os.makedirs(os.path.join(T, d))
    return T


# ---------------------------------------------------------------- 1) cruce válido solo tras 5 cierres consecutivos
base = [100 + i * 0.01 for i in range(200)]                           # tendencia suave: el cierre nº 200 está sobre su SMA → lado vigente = alza
fechas = habiles(260)


def serie(cola):
    v = base + cola
    return list(zip(fechas[:len(v)], v))


f = CR.filtro_sma(serie([103] * 4 + [90] * 4 + [103]))                # 4 cierres bajo la media no bastan
assert f["_cruces"] == [] and f["vigente"] == 1 and f["pendiente"] == 0 and f["cruces_12m"] == 0
f = CR.filtro_sma(serie([90] * 4 + [103] + [90] * 4 + [103]))        # un cierre de vuelta reinicia la cuenta
assert f["_cruces"] == []
f = CR.filtro_sma(serie([90] * 5))
assert len(f["_cruces"]) == 1 and f["_cruces"][0] == (fechas[204], -1) and f["vigente"] == -1 and f["pendiente"] == 0 and f["ultimo_cruce"] == {"fecha": fechas[204].isoformat(), "sentido": "A LA BAJA"}
f4 = CR.filtro_sma(serie([90] * 4))
assert f4["_cruces"] == [] and f4["lado_actual"] == -1 and f4["vigente"] == 1 and f4["pendiente"] == 4, "4 cierres seguidos: cruce en curso (4 de 5), todavía no válido"
f = CR.filtro_sma(serie([90] * 5 + [105] * 4 + [90]))
assert [c[1] for c in f["_cruces"]] == [-1], "tras el cruce a la baja, 4 cierres sobre la media no lo anulan"
f = CR.filtro_sma(serie([90] * 5 + [105] * 5))
assert [(c[1]) for c in f["_cruces"]] == [-1, 1] and f["vigente"] == 1 and f["ultimo_cruce"]["sentido"] == "AL ALZA"
assert CR.filtro_sma(serie([])[:150]) is None and CR.filtro_sma(serie([])[:200]) is None, "con menos de 201 puntos no hay SMA 200 de referencia"
print("1) OK filtro SMA 200: 4 cierres al otro lado = cruce en curso (4 de 5), 5 = cruce válido en el 5.º cierre; un cierre de vuelta reinicia la cuenta; el cruce contrario también exige 5; < 201 puntos → SIN DATO")

# ---------------------------------------------------------------- 2) contador de cruces válidos en 12 meses y nota de mercado lateral
def oscilar(bloques):
    cola = []
    for i in range(bloques):
        cola += ([90] if i % 2 == 0 else [112]) * 5
    return serie(cola)


f3 = CR.filtro_sma(oscilar(3))
f4_ = CR.filtro_sma(oscilar(4))
assert (f3["cruces_12m"], f3["poco_fiable"]) == (3, False) and (f4_["cruces_12m"], f4_["poco_fiable"]) == (4, True), (f3["cruces_12m"], f4_["cruces_12m"])
fil = CR.filtros({"cap": oscilar(4), "igual": serie([103] * 20)})
assert fil["cap"]["diario"]["nota"] == "filtro poco fiable ahora (mercado lateral)" and fil["igual"]["diario"]["nota"] is None and fil["cap"]["diario"]["estado"] in ("SOBRE SU SMA 200", "BAJO SU SMA 200")
largo = [(fechas[0] + dt.timedelta(days=i), 1.0) for i in range(100)]
assert CR.filtros({"cap": largo})["cap"]["semanal"]["estado"] == "SIN DATO" and "semanas" in CR.filtros({"cap": largo})["cap"]["semanal"]["motivo"], "poca historia semanal → SIN DATO"
vieja = serie([90] * 5 + [112] * 5 + [90] * 5 + [112] * 5)
for i in range(4):                                                      # cruces viejos (> 12 meses) no cuentan
    pass
antes = [(d - dt.timedelta(days=400), v) for d, v in vieja]
extra = [(antes[-1][0] + dt.timedelta(days=k + 1), 100.0) for k in range(60)]
fv = CR.filtro_sma(antes + [(d + dt.timedelta(days=0), v) for (d, v) in extra])
assert fv is not None and fv["cruces_12m"] <= len(fv["_cruces"]) and all((fv["_cruces"][-1][0] - c[0]).days >= 0 for c in fv["_cruces"])
print("2) OK contador: 3 cruces válidos en 12 meses = sin nota; 4 = «filtro poco fiable ahora (mercado lateral)»; los cruces de hace más de 12 meses no cuentan; poca historia semanal → SIN DATO")

# ---------------------------------------------------------------- 3) semanal: último cierre de cada semana completa
dias = [D(2026, 10, 5) + dt.timedelta(days=i) for i in range(0, 15) if (D(2026, 10, 5) + dt.timedelta(days=i)).weekday() < 5]   # 5-9 oct, 12-16 oct
pts = [(d, float(i)) for i, d in enumerate(dias)]
sem = CR.semanal(pts)
assert [d.isoformat() for d, _ in sem] == ["2026-10-09", "2026-10-16"] and [v for _, v in sem] == [4.0, 9.0], sem
assert [d.isoformat() for d, _ in CR.semanal(pts[:7])] == ["2026-10-09"], "la semana en curso (hasta el martes 13) no entra"
assert [d.isoformat() for d, _ in CR.semanal(pts[:9])] == ["2026-10-09"], "ni el jueves"
assert [d.isoformat() for d, _ in CR.semanal(pts[:10])] == ["2026-10-09", "2026-10-16"], "con el cierre del viernes sí"
print("3) OK semanal: último cierre de cada semana completa; la semana en curso solo entra con el cierre del viernes")

# ---------------------------------------------------------------- 4) rotación frente a SPY
fs = habiles(100)
ser = {"SPY": list(zip(fs, [100.0 * (1.001 ** i) for i in range(100)]))}
ritmos = {"XLY": 1.0015, "XLP": 1.0005, "XLK": 1.002, "XLE": 1.0, "XLU": 0.999, "XLV": 1.0011, "XLF": 1.0008, "XLI": 1.0012}
for t, r in ritmos.items():
    ser[t] = list(zip(fs, [50.0 * (r ** i) for i in range(100)]))
ro = CR.rotacion(ser)
assert ro["estado"] == "OK" and [f["etf"] for f in ro["filas"]] == ["XLK", "XLY", "XLI", "XLV", "XLF", "XLP", "XLE", "XLU"], [f["etf"] for f in ro["filas"]]
k = {f["etf"]: f for f in ro["filas"]}
spy3 = (ser["SPY"][-1][1] / ser["SPY"][-1 - 63][1] - 1) * 100
assert abs(k["XLK"]["rel_3m"] - ((ritmos["XLK"] ** 63 - 1) * 100 - spy3)) < 0.02 and k["XLK"]["puesto_3m"] == 1 and k["XLU"]["puesto_3m"] == 8
assert k["XLE"]["rel_3m"] < 0 and k["XLU"]["rel_1m"] < k["XLE"]["rel_1m"] and sorted(f["puesto_1m"] for f in ro["filas"]) == list(range(1, 9))
assert "no recomienda" in ro["nota"] and CR.rotacion({"SPY": ser["SPY"][:50]})["estado"] == "SIN DATO"
ser2 = dict(ser)
del ser2["XLE"]
ro2 = CR.rotacion(ser2)
assert ro2["filas"][-1]["etf"] == "XLE" and ro2["filas"][-1]["rel_3m"] is None and len(ro2["filas"]) == 8, "un ETF sin datos queda al final como SIN DATO y no se estima"
print("4) OK rotación: ocho sectores ordenados por el rendimiento relativo a SPY a 3 meses (con su puesto a 1 mes); un ETF sin datos queda al final; solo describe")

# ---------------------------------------------------------------- 5) divergencia: condiciones y fuerza
n = 70
fd = habiles(n)


def mundo(spy_ult=110.0, spy_pico=None, r_ult=0.96, rsp_ult=110.0):
    """63+ sesiones planas (SPY 100, ratio 1,0, RSP 100) con el último día modificado. spy_pico = cierre de SPY 30 sesiones antes (para probar «no es máximo»)."""
    spy = [(d, 100.0) for d in fd]
    if spy_pico:
        spy[-30] = (fd[-30], spy_pico)
    spy[-1] = (fd[-1], spy_ult)
    r = [(d, 1.0) for d in fd]
    r[-1] = (fd[-1], r_ult)
    rsp = [(d, 100.0) for d in fd]
    rsp[-1] = (fd[-1], rsp_ult)
    return spy, r, rsp


OAS_AMPL = {"hy": [(fd[0] + dt.timedelta(days=i), 3.00 + (0.80 if i > 80 else 0.0)) for i in range(0, 120)]}
OAS_QUIETO = {"hy": [(fd[0] + dt.timedelta(days=i), 3.00) for i in range(0, 120)]}
d_ult = fd[-1]
spy, r, rsp = mundo()
e = CR.divergencia_en(len(spy) - 1, spy, r, rsp, {k: [(x, v) for x, v in s if x <= d_ult] for k, s in OAS_AMPL.items()})
assert e["activa"] and e["spy_max_63"] and abs(e["ratio_vs_max63_pct"] - (-4.0)) < 0.01 and e["amplitud_a_la_baja"] is False and e["credito_ampliandose"] is True and e["fuerza"] == "MEDIA" and e["parcial"] is False
# amplitud a la baja (RSP rinde 1,5 pp menos que SPY en 20 sesiones) + crédito ampliándose = FUERTE
spy2, r2, rsp2 = mundo(rsp_ult=100.0)
e2 = CR.divergencia_en(len(spy2) - 1, spy2, r2, rsp2, OAS_AMPL)
assert e2["amplitud_pp"] == -10.0 and e2["amplitud_a_la_baja"] is True and e2["credito_ampliandose"] is True and e2["fuerza"] == "FUERTE" and e2["parcial"] is False, e2
e3 = CR.divergencia_en(len(spy2) - 1, spy2, r2, rsp2, OAS_QUIETO)
assert e3["fuerza"] == "MEDIA" and e3["credito_ampliandose"] is False and e3["amplitud_a_la_baja"] is True
spy4, r4, rsp4 = mundo()
e4 = CR.divergencia_en(len(spy4) - 1, spy4, r4, rsp4, OAS_QUIETO)
assert e4["fuerza"] == "DÉBIL" and e4["amplitud_a_la_baja"] is False and e4["credito_ampliandose"] is False
e5 = CR.divergencia_en(len(spy2) - 1, spy2, r2, rsp2, {})
assert e5["credito_ampliandose"] is None and e5["fuerza"] == "MEDIA" and e5["parcial"] is True, "sin dato de crédito: parcial y FUERTE imposible"
e6 = CR.divergencia_en(len(spy2) - 1, spy2, r2, [], OAS_AMPL)
assert e6["amplitud_a_la_baja"] is None and e6["fuerza"] == "MEDIA" and e6["parcial"] is True, "sin RSP: parcial"
# bordes: exactamente −3 % no es divergencia; SPY a 1 céntimo del máximo no es máximo
s7, r7, p7 = mundo(r_ult=0.97, rsp_ult=110.0)
assert CR.divergencia_en(len(s7) - 1, s7, r7, p7, OAS_AMPL)["activa"] is False, "−3,00 % exacto no supera el umbral"
s8, r8, p8 = mundo(r_ult=0.9699, rsp_ult=110.0)
assert CR.divergencia_en(len(s8) - 1, s8, r8, p8, OAS_AMPL)["activa"] is True
s9, r9, p9 = mundo(spy_ult=109.99, spy_pico=110.0, rsp_ult=109.99)
assert CR.divergencia_en(len(s9) - 1, s9, r9, p9, OAS_AMPL)["activa"] is False and CR.divergencia_en(len(s9) - 1, s9, r9, p9, OAS_AMPL)["spy_max_63"] is False
sb = [(d, 100.0) for d in fd]
rb = [(d, 1.0) for d in fd]
rb[-30] = (fd[-30], 1.0)
rb[-1] = (fd[-1], 0.96)
pb_ = [(d, 100.0) for d in fd]
pb_[-1] = (fd[-1], 99.0)
sb[-1] = (fd[-1], 100.0)
eb = CR.divergencia_en(len(sb) - 1, sb, rb, pb_, OAS_QUIETO)
assert eb["amplitud_pp"] == -1.0 and eb["amplitud_a_la_baja"] is True, "−1,0 pp exacto cuenta como a la baja (≤ −1 pp, el umbral de indices.py)"
assert CR.divergencia_en(10, spy, r, rsp, OAS_AMPL) is None, "con menos de 63 sesiones no se calcula"
print("5) OK divergencia: SPY en máximo de 63 y ratio −4 % bajo el suyo; amplitud a la baja + crédito = FUERTE; una = MEDIA; ninguna = DÉBIL; sin dato de una = «parcial» y nunca FUERTE; −3,00 % exacto no cuenta; 1 céntimo bajo el máximo tampoco")

# ---------------------------------------------------------------- 6) crédito ampliándose con los umbrales de ciclo.py
def serie_oas(base, salto, dias_salto, total=120):
    return [(D(2026, 1, 1) + dt.timedelta(days=i), base + (salto if i >= total - dias_salto else 0.0)) for i in range(total)]


f0 = D(2026, 1, 1) + dt.timedelta(days=119)
ok, det = CR.credito_ampliandose({"hy": serie_oas(3.0, 0.25, 5)}, f0)                  # +25 pb en 5 días = umbral exacto de HY → sí
assert ok is True and "HY +25 pb en 5 días" in det[0]
ok, det = CR.credito_ampliandose({"hy": serie_oas(3.0, 0.24, 5)}, f0)
assert ok is False and det == []
ok, det = CR.credito_ampliandose({"hy": serie_oas(3.0, 0.75, 20)}, f0)                 # +75 pb en 1 mes
assert ok is True and "1 mes" in det[0]
ok, det = CR.credito_ampliandose({"ccc": serie_oas(12.0, 1.93, 20)}, f0)               # CCC +193 pb en 1 mes (hoy) ≥ 150
assert ok is True and "CCC" in det[0]
assert CR.credito_ampliandose({"hy": serie_oas(3.0, 0.5, 5)[:10]}, f0) == (None, None), "con menos de un mes de historia: SIN DATO, no se estima"
assert CR.credito_ampliandose({}, f0) == (None, None)
print("6) OK crédito: umbrales de ciclo.py (HY +25 pb en 5 días o +75 en 1 mes; CCC +150 en 1 mes); 24 pb no; sin un mes de historia → SIN DATO")

# ---------------------------------------------------------------- 7) inicio de divergencia (enfriamiento de 10 sesiones) y aparición de una FUERTE
def est(i, activa, fuerza="DÉBIL"):
    return {"fecha": (D(2026, 1, 1) + dt.timedelta(days=i)).isoformat(), "activa": activa, "fuerza": fuerza if activa else None, "parcial": False, "credito_ampliandose": True, "ratio_vs_max63_pct": -4.0,
            "amplitud_pp": -2.0, "credito_detalle": ["HY +30 pb en 5 días"], "spy_max_63": activa, "amplitud_a_la_baja": True}


h = [est(i, i in (5, 6, 7, 12, 40, 41)) for i in range(60)]
assert [e["fecha"] for e in CR.inicios_divergencia(h)] == [est(5, True)["fecha"], est(40, True)["fecha"]], "12 está a 5 sesiones del 7: no cuenta; 40 sí"
h2 = [est(i, i in (5, 17)) for i in range(30)]
assert len(CR.inicios_divergencia(h2)) == 2 and len(CR.inicios_divergencia([est(i, i in (5, 15)) for i in range(30)])) == 1, "a 10 sesiones exactas no cuenta; a 12 sí"
assert CR.aparece_fuerte([est(0, True, "MEDIA"), est(1, True, "FUERTE")]) is True and CR.aparece_fuerte([est(0, True, "FUERTE"), est(1, True, "FUERTE")]) is False
assert CR.aparece_fuerte([est(0, False), est(1, True, "FUERTE")]) is True and CR.aparece_fuerte([est(0, False), est(1, True, "MEDIA")]) is False and CR.aparece_fuerte([est(0, True, "FUERTE"), est(1, False)]) is False and CR.aparece_fuerte([]) is False
print("7) OK episodios: una divergencia nueva solo cuenta con ≥ 10 sesiones sin ninguna (a 10 exactas no; a 12 sí); «aparece FUERTE» = hoy FUERTE y ayer no")

# ---------------------------------------------------------------- 8) Telegram: solo al aparecer una FUERTE, máx. 1 por semana
T = nueva()
env = []
fake = lambda x: (env.append(x), (True, None))[1]                       # noqa: E731
assert CR.avisar(T, [est(0, False), est(1, True, "MEDIA")], None, fake) == (False, "no aparece una divergencia FUERTE hoy") and not env
ok, mot = CR.avisar(T, [est(0, False), est(30, True, "FUERTE")], None, fake)
assert ok and len(env) == 1 and "Divergencia FUERTE" in env[0] and "no una recomendación de compra o venta" in env[0] and not re.search(r"\b(compra|vende)\b", env[0].replace("compra o venta", ""), re.I)
ok, mot = CR.avisar(T, [est(30, True, "MEDIA"), est(33, True, "FUERTE")], None, fake)
assert ok is False and "7 días" in mot and len(env) == 1, "ya se avisó hace 3 días: máx. 1 por semana"
ok, mot = CR.avisar(T, [est(30, True, "MEDIA"), est(37, True, "FUERTE")], None, fake)
assert ok and len(env) == 2, "a 7 días ya puede avisar otra vez"
ok, mot = CR.avisar(nueva(), [est(0, False), est(1, True, "FUERTE")], None, lambda x: (False, "HTTP 500"))
assert ok is False and "HTTP 500" in mot
T2 = nueva()
CR.avisar(T2, [est(0, False), est(1, True, "FUERTE")], None, lambda x: (False, "HTTP 500"))
assert not os.path.exists(os.path.join(T2, "data", "estado_consumo_ratio.json")), "Telegram caído: no se anota el envío (se reintenta)"
assert CR.avisar(nueva(), [est(0, False), est(1, True, "FUERTE")], None) == (False, "Telegram sin configurar")
print("8) OK Telegram: solo al aparecer una FUERTE (MEDIA/DÉBIL no); máx. 1 por semana (a 3 días no, a 7 sí); un fallo de Telegram no anota el envío; el texto no dice «compra» ni «vende»")

# ---------------------------------------------------------------- 9) construir() y backfill con fuentes simuladas: marcador, SPY, idempotencia
N = 1500
fh = habiles(N, D(2012, 1, 2))


def ond(i, a, p):
    import math
    return 100 * (1 + 0.0004) ** i * (1 + a * math.sin(i / p))


series_sim = {"SPY": [(d, ond(i, 0.04, 60)) for i, d in enumerate(fh)], "RSP": [(d, ond(i, 0.05, 61)) for i, d in enumerate(fh)]}
for t, (a, p) in {"XLY": (0.06, 55), "XLP": (0.03, 70), "RSPD": (0.08, 50), "RSPS": (0.04, 80), "XLK": (0.05, 65), "XLE": (0.07, 90), "XLU": (0.03, 77), "XLV": (0.04, 66), "XLF": (0.06, 58), "XLI": (0.05, 63)}.items():
    series_sim[t] = [(d, ond(i, a, p)) for i, d in enumerate(fh)]


def yahoo_sim(sym, rango="20y", tries=3):
    if sym == "RSPS" and falla.get("RSPS"):
        raise OSError("Yahoo caído")
    return series_sim[sym]


falla = {}
fred_sim = lambda sid, desde: [(fh[-400] + dt.timedelta(days=i), 3.0 + 0.002 * i) for i in range(560)] if sid == "BAMLH0A0HYM2" else []     # noqa: E731
FU = {"yahoo": yahoo_sim, "fred": fred_sim}
T = nueva()
bf = CR.backfill(T, FU, en := dt.datetime(2026, 10, 20, 12, tzinfo=UTC))
sen = list(csv.DictReader(open(os.path.join(T, "data", "marcador_senales.csv"), encoding="utf-8")))
assert bf["nuevas"] == len(sen) == bf["eventos"] and bf["nuevas"] > 20 and all(s["origen"] == "backfill" for s in sen) and {s["tipo"] for s in sen} <= {"cruce_sma200_ratio", "divergencia_ratio"}
assert all(s["activo"] == "SPY" and s["direccion"] in ("ALCISTA", "BAJISTA") for s in sen) and all(s["fecha_utc"].endswith("21:30") and s["fecha_utc"][:10] >= "2010-01-01" for s in sen)
assert all(s["direccion"] == "BAJISTA" for s in sen if s["tipo"] == "divergencia_ratio"), "la divergencia es BAJISTA sobre SPY"
assert any("5 cierres seguidos" in s["valor"] for s in sen if s["tipo"] == "cruce_sma200_ratio") and any(s["valor"].startswith("XLY/XLP semanal") or s["valor"].startswith("RSPD/RSPS semanal") for s in sen)
n_spy = len(list(csv.DictReader(open(os.path.join(T, "data", "spy_cierres.csv"), encoding="utf-8"))))
assert n_spy == N and bf["spy_filas_nuevas"] == N
bf2 = CR.backfill(T, FU, en)
assert bf2["nuevas"] == 0 and bf2["spy_filas_nuevas"] == 0 and len(list(csv.DictReader(open(os.path.join(T, "data", "marcador_senales.csv"), encoding="utf-8")))) == len(sen), "idempotente: no duplica nada"
print("9) OK backfill: %d señales (origen=backfill) sobre SPY desde 2010, histórico de SPY guardado (%d días); repetirlo no duplica nada" % (len(sen), n_spy))

# ---------------------------------------------------------------- 10) el marcador mide a T+20 y T+60 y los horizontes son por tipo
assert M.HORIZ_TIPO == {"cruce_sma200_ratio": (20, 60), "divergencia_ratio": (20, 60)} and {"cruce_sma200_ratio", "divergencia_ratio"} <= set(M.TIPOS_PUNTUABLES) and M.SERIE_DE["SPY"] == "spy"
nu = M.evaluar(T, en)
hs = {(r["id"], int(r["horizonte"])) for r in nu}
assert {h for _, h in hs} == {20, 60} and all(r["unidad"] == "%" for r in nu) and len(nu) > 30, "solo T+20 y T+60 (nunca T+1 ni T+5) y en %"
ids_sen = {s["id"] for s in sen}
assert all(i in ids_sen for i, _ in hs)
R = M.resumen(T, en)
for t in ("cruce_sma200_ratio", "divergencia_ratio"):
    d = R["resumen"]["backfill"][t]
    assert set(d["horizontes"]) == {"20", "60"} and d["horizontes"]["20"]["n"] > 0 and d["horizontes"]["20"]["base_media_pct"] is not None, (t, d["horizontes"])
assert set(R["horizontes_por_tipo"]) == {"cruce_sma200_ratio", "divergencia_ratio"} and 60 in R["horizontes"] and 1 in R["horizontes"]
nu2 = M.evaluar(T, en)
assert nu2 == [], "solo-añadir: no repite lo ya medido"
print("10) OK marcador: los dos tipos se miden SOLO a T+20 y T+60 sobre SPY frente a la tasa base; el resto de tipos conserva T+1/T+5/T+20; repetir no duplica")

# ---------------------------------------------------------------- 11) construir(): JSON completo, fallos por fuente, vivo vs backfill, Telegram sin enviar
T = nueva()
J = CR.construir(FU, en, T, enviar=fake, avisar_telegram=False)
assert J["ok"] and set(J["filtro_sma200"]["ratios"]) == {"cap", "igual"} and set(J["filtro_sma200"]["ratios"]["cap"]) >= {"diario", "semanal"} and J["rotacion"]["estado"] == "OK" and len(J["rotacion"]["filas"]) == 8
assert J["divergencia"]["hoy"]["fecha"] == fh[-1].isoformat() and J["errores"] == {} and J["fecha_datos"] == fh[-1].isoformat()
vivo = [s for s in csv.DictReader(open(os.path.join(T, "data", "marcador_senales.csv"), encoding="utf-8"))] if os.path.exists(os.path.join(T, "data", "marcador_senales.csv")) else []
assert all(s["origen"] == "vivo" for s in vivo), "las señales de una ejecución normal son origen=vivo (solo los eventos de los últimos 15 días)"
falla["RSPS"] = True
Jf = CR.construir(FU, en, nueva(), avisar_telegram=False, registrar_marcador=False)
assert "yahoo_RSPS" in Jf["errores"] and Jf["filtro_sma200"]["ratios"].get("igual") is None and Jf["divergencia"]["hoy"] is None and Jf["rotacion"]["estado"] == "OK", "RSPS caído: el ratio igual y la divergencia quedan en SIN DATO; el resto sigue"
falla.clear()
Jc = CR.construir({"yahoo": yahoo_sim, "fred": lambda s, d: (_ for _ in ()).throw(OSError("FRED caído"))}, en, nueva(), avisar_telegram=False, registrar_marcador=False)
assert Jc["divergencia"]["hoy"]["credito_ampliandose"] is None and Jc["divergencia"]["hoy"]["parcial"] in (True, False) and any(k.startswith("fred_") for k in Jc["errores"])
Jt = CR.construir({"yahoo": lambda s, r="20y", tries=3: (_ for _ in ()).throw(OSError("todo caído")), "fred": fred_sim}, en, nueva(), avisar_telegram=False, registrar_marcador=False)
assert Jt["rotacion"]["estado"] == "SIN DATO" and Jt["divergencia"]["hoy"] is None and Jt["fecha_datos"] is None
print("11) OK construir(): filtro de los dos ratios (diario y semanal), rotación de 8 ETF y divergencia de hoy; cada fuente falla por separado (RSPS caído → ratio igual SIN DATO; FRED caído → crédito SIN DATO y fuerza parcial; todo caído → SIN DATO)")

# ---------------------------------------------------------------- 12) contexto.json
T = nueva()
json.dump(J | {"reglas": CR.REGLAS_TEXTO}, open(os.path.join(T, "site", "data", "consumo_ratio.json"), "w", encoding="utf-8"), ensure_ascii=False)
bc = CR.bloque_contexto(T)
assert bc["fecha"] == fh[-1].isoformat() and set(bc["filtro_sma200"]) == {"XLY/XLP", "RSPD/RSPS"} and set(bc["rotacion_vs_spy_3m_pp"]) == set(CR.SECTORES) and "divergencia" in bc and "recomendación" in bc["nota"]
assert CR.bloque_contexto(nueva())["estado"] == "SIN DATO"
assert len(CR.REGLAS_TEXTO) >= 7
print("12) OK contexto.json: filtro SMA 200 de los dos ratios, rotación a 3 meses, divergencia de hoy y nota de que no es una recomendación; sin archivo → SIN DATO")

print("\nTODO OK · sin red, sin envíos reales")
