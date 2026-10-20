#!/usr/bin/env python3
"""Pruebas de #/gamma con 4 activos: US30 (DIA → DJI/YM), ORO normalizado (XAU/GC), Max Gamma con signo y «qué ha cambiado». Sin red. Uso: PYTHONUTF8=1 python tools/prueba_gamma_activos.py"""
import csv
import datetime as dt
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
import csvlog  # noqa: E402
import gamma  # noqa: E402
import gamma_oro as GO  # noqa: E402
import gamma_us30 as US  # noqa: E402

UTC = dt.timezone.utc
T = tempfile.mkdtemp(prefix="act_")
csvlog.DATA = os.path.join(T, "data")          # el histórico de gamma.py va a la carpeta temporal
os.makedirs(csvlog.DATA)
os.makedirs(os.path.join(T, "site", "data"))


def cadena(spot, k0, paso, n, ultima="2026-10-19T15:59:59", ctr=1.0):
    ops = []
    for exp in ("261030", "261106", "261120", "261201"):
        for i in range(n):
            k = k0 + i * paso
            for cp in "CP":
                oi = 3000.0 * (2.718 ** (-((k - (spot * 1.03 if cp == "C" else spot * 0.97)) / (spot * 0.03)) ** 2)) + 40
                ops.append({"option": f"X{exp}{cp}{int(k * 1000):08d}", "iv": 0.17, "open_interest": round(oi * ctr), "gamma": 0.0})
    return {"options": ops, "current_price": spot, "last_trade_time": ultima}, "ts"


# ---------------------------------------------------------------- 1) US30: DIA → DJI → YM
gamma._cargar = lambda s: cadena(520.0, 440, 2, 80)
f = {"cierre": lambda sym, ses: 51966.03 if sym == "^DJI" else 519.98, "base": lambda fut, idx, ses: {"base": 224.0, "fut": 52190.0, "idx": 51966.0, "momento_et": "x", "metodo": "intradía 5 min", "aproximada": False, "fuente": "Yahoo", "errores": []},
     "vol": (16.0, "2026-10-19")}
M = US.medir(f)
k = 51966.03 / 519.98
assert M["clave"] == "YM" and M["contado"] == "DJI" and M["futuro"] == "YM" and M["etiqueta"] == "DIA, referencia" and M["spot_idx"] == 51966.03
assert abs(M["ratio_contado"] - round(k, 5)) < 1e-9
for n in ("call_wall", "put_wall", "flip", "max_gamma"):
    o = M[n]
    assert o and abs(o["idx"] - round(o["etf"] * k, 1)) < 0.11 and abs(o["fut"] - round(o["idx"] + 224.0, 1)) < 0.11, (n, o)
assert M["call_wall"]["idx"] >= M["spot_idx"] and M["put_wall"]["idx"] <= M["spot_idx"] and M["max_gamma"]["tipo"] in ("pin", "acelera")
assert M["max_gamma"]["tipo"] == ("pin" if M["max_gamma"]["neto_musd"] > 0 else "acelera"), "pin solo con gamma neta del tramo positiva"
assert M["spot_fut"] == round(51966.03 + 224.0, 2) and M["em"]["vol_simbolo"] == "VXD" and abs(M["em"]["puntos"] - round(52190.0 * 16 / 100 / 252 ** 0.5, 1)) < 0.06
assert all("fut" in p for p in M["perfil"]) and abs(M["perfil"][5]["k"] - round(M["perfil"][5]["k_etf"] * k, 1)) < 0.11 and abs(M["curva"][0][0] - M["curva"][0][0]) == 0
print("1) OK US30: niveles DIA × (DJI/DIA) = DJI y + base = YM; Max Gamma con signo; EM con VXD; «DIA, referencia»")

# ---------------------------------------------------------------- 2) etapa US30: escribe histórico solo al cierre del día; SIN DATO si no hay datos; intradía conserva
barras = [{"fecha": dt.date(2026, 10, 19), "o": 52000, "h": 52300, "l": 51900, "c": 52100}, {"fecha": dt.date(2026, 10, 20), "o": 52150, "h": 52400, "l": 52000, "c": 52350}]
J = US.etapa(escribir_cierre=True, hoy="2026-10-19", stamp="s", f=f, hist=[], barras=barras)
assert J["ok"] and J["historico_escrito"] is True
filas = list(csv.DictReader(open(os.path.join(csvlog.DATA, "historico_gamma.csv"), encoding="utf-8")))
assert len(filas) == 1 and filas[0]["indice"] == "YM" and float(filas[0]["base"]) == 224.0 and float(filas[0]["call_wall_fut"]) == J["call_wall"]["fut"]
J2 = US.etapa(escribir_cierre=True, hoy="2026-10-19", stamp="s2", f=f, hist=filas, barras=barras)
assert len(list(csv.DictReader(open(os.path.join(csvlog.DATA, "historico_gamma.csv"), encoding="utf-8")))) == 1, "una fila por sesión"
assert J2["revision"]["sesiones"][0]["estado"] == "EVALUADA" and J2["sesiones_guardadas"] == 1 and J2["anterior"] is None, "primera sesión: sin «anterior»; la revisión usa la barra siguiente del YM"
J3 = US.etapa(escribir_cierre=True, hoy="2026-10-20", stamp="s3", f=f, hist=filas, barras=barras)
assert J3["historico_escrito"] is False, "la sesión no es la de hoy: no escribe"
gamma._cargar = lambda s: cadena(520.0, 500, 10, 4)          # cadena pobre → SIN DATO, no se inventa
S = US.etapa(escribir_cierre=True, hoy="2026-10-19", stamp="s", f=f, hist=[], barras=barras)
assert S["sin_dato"] is True and "SIN DATO" in S["motivo"] and "No se inventa" in S["motivo"] and S["etiqueta"] == "DIA, referencia"
S2 = US.etapa(escribir_cierre=True, hoy="2026-10-19", stamp="s", f=f, previo=J, hist=[], barras=barras)
assert S2 is J and "error_ultimo" in J, "si falla pero hay un cierre válido previo, se conserva"
gamma._cargar = lambda s: cadena(520.0, 440, 2, 80, ultima="2026-10-20T11:00:00")
I = US.etapa(escribir_cierre=True, hoy="2026-10-20", stamp="s", f=f, previo=J, hist=[], barras=barras)
assert I is J and "descartado_intradia" in J
print("2) OK etapa US30: histórico YM solo al cierre del día y una fila por sesión; SIN DATO con cadena pobre; conserva el último cierre; revisión a T+1 con YM")

# ---------------------------------------------------------------- 3) «qué ha cambiado» y Max Gamma con signo
prev = {"fecha": "2026-10-16", "call_wall": "52000.0", "put_wall": "51000.0", "flip": "51500.0", "regimen": "NEGATIVA"}
x = {"call_wall": {"fut": 52298.2}, "put_wall": {"fut": 51296.8}, "flip": {"fut": 51937.7}, "regimen": "POSITIVA"}
c = gamma.cambios(prev, x)
assert c["niveles"]["call_wall"]["dif"] == 298.2 and c["niveles"]["flip"]["dif"] == 437.7 and c["regimen"] == {"antes": "NEGATIVA", "ahora": "POSITIVA", "cambio": True} and gamma.cambios(None, x) is None
h = [{"fecha_sesion": "2026-10-15", "indice": "ES", "call_wall_fut": "1", "put_wall_fut": "2", "flip_fut": "3", "regimen": "POSITIVA"}, {"fecha_sesion": "2026-10-16", "indice": "ES", "call_wall_fut": "10", "put_wall_fut": "20", "flip_fut": "30", "regimen": "NEGATIVA"},
     {"fecha_sesion": "2026-10-19", "indice": "ES", "call_wall_fut": "99", "put_wall_fut": "99", "flip_fut": "99", "regimen": "NEGATIVA"}]
assert gamma.prev_de_historico(h, "ES", "2026-10-19")["call_wall"] == "10" and gamma.prev_de_historico(h, "NQ", "2026-10-19") is None
perfil = [{"k": 1, "call": 50.0, "put": -10.0, "net": 40.0}, {"k": 2, "call": 10.0, "put": -80.0, "net": -70.0}]
mg = gamma.max_gamma_de(perfil)
assert mg["idx"] == 2 and mg["tipo"] == "acelera" and mg["neto_musd"] == -70.0
M0 = {"indices": {"ES": {"perfil": perfil, "max_gamma": {"idx": 2, "musd": 90.0, "fut": 52}, "em": {"puntos": 1}, "base": {"base": 50}}}}
gamma.enriquecer(M0)
assert M0["indices"]["ES"]["max_gamma"]["tipo"] == "acelera" and M0["indices"]["ES"]["max_gamma"]["fut"] == 52, "gamma.json antiguo: se añade el signo sin recalcular la cadena"
print("3) OK cambios vs sesión anterior (con cambio de régimen), sesión anterior del histórico por índice y Max Gamma pin / acelera también retroactivo")

# ---------------------------------------------------------------- 4) ORO normalizado: contado XAU, futuro GC con base, mismas claves que ES
gamma._cargar = lambda s: cadena(380.0, 330, 1, 100)
TG = tempfile.mkdtemp(prefix="oro_")
os.makedirs(os.path.join(TG, "data"))
os.makedirs(os.path.join(TG, "site", "data"))
xau = lambda: (4140.8, "2026-10-19 21:30", "gold-api")  # noqa: E731
gc = lambda hora: (4160.3, "2026-10-19 21:25")  # noqa: E731
bg = [{"fecha": dt.date(2026, 10, 19), "o": 380, "h": 382, "l": 378, "c": 379.69}, {"fecha": dt.date(2026, 10, 20), "o": 380.0, "h": 386.0, "l": 379.0, "c": 385.5}]
J = GO.etapa(escribir_cierre=True, hoy="2026-10-19", stamp="s", raiz=TG, fuentes_={"vol": (22.0, "2026-10-19"), "gld_cierre": lambda d: 379.69, "xau": xau, "gc": gc, "barras": bg[:1]}, ahora=dt.datetime(2026, 10, 19, 21, 30, tzinfo=UTC))
r = 4140.8 / 379.69
assert J["contado"] == "XAU" and J["futuro"] == "GC" and J["etiqueta"] == "GLD, referencia" and J["spot_idx"] == 4140.8 and abs(J["base"]["base"] - 19.5) < 1e-9 and J["spot_fut"] == round(4140.8 + 19.5, 2)
for n in ("call_wall", "put_wall", "flip", "max_gamma"):
    o = J[n]
    assert abs(o["idx"] - round(o["etf"] * r, 1)) < 0.11 and abs(o["fut"] - round(o["idx"] + 19.5, 1)) < 0.11, (n, o)
assert abs(J["em"]["puntos"] - round(J["em_gld"]["puntos"] * r, 1)) < 0.06 and J["max_gamma"]["tipo"] in ("pin", "acelera") and all("fut" in p for p in J["perfil"])
lv = {x["corto"]: x for x in J["niveles"]}
assert lv["flip"]["xau"] == J["flip"]["idx"] and lv["flip"]["gld"] == J["flip"]["etf"], "los niveles de la línea ORO (xau) son los mismos que los del contado de la página"
assert [r_["base"] for r_ in csv.DictReader(open(os.path.join(TG, "data", "xau_gc_base.csv"), encoding="utf-8"))] == ["19.5"]
assert len(list(csv.DictReader(open(os.path.join(TG, "data", "historico_gamma_oro.csv"), encoding="utf-8")))) == 1 and J["anterior"] is None
# sin ratio: queda en GLD con SIN DATO en XAU/GC
J0 = GO.etapa(escribir_cierre=False, hoy="2026-10-19", stamp="s", raiz=nueva if False else tempfile.mkdtemp(prefix="oro0_"), fuentes_={"vol": (22.0, "2026-10-19"), "barras": []})
assert J0["contado"] == "GLD" and J0["futuro"] is None and J0["spot_fut"] is None
print("4) OK ORO: contado XAU y futuro GC con la base del día (anotada con el ratio), niveles idénticos a los de la línea ORO; sin ratio, solo GLD con SIN DATO")

for d in (T, TG):
    shutil.rmtree(d, ignore_errors=True)
print("\nTODO OK")
