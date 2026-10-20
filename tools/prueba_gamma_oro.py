#!/usr/bin/env python3
"""Pruebas de la Fase 17 (gamma del oro). Sin red: cadena de Cboe sintética, ratio y precios inyectados, Telegram simulado. Uso: PYTHONUTF8=1 python tools/prueba_gamma_oro.py"""
import csv
import datetime as dt
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
import gamma  # noqa: E402
import gamma_intradia as GI  # noqa: E402
import gamma_oro as GO  # noqa: E402

UTC = dt.timezone.utc


def nueva():
    t = tempfile.mkdtemp(prefix="gold_")
    os.makedirs(os.path.join(t, "data"))
    os.makedirs(os.path.join(t, "site", "data"))
    return t


def escribir(raiz, nombre, obj):
    with open(os.path.join(raiz, "site", "data", nombre), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def leer_csv(raiz, nombre):
    with open(os.path.join(raiz, "data", nombre), encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------- cadena sintética de GLD
def cadena(spot=380.0, ultima="2026-10-19T15:59:59"):
    ops = []
    for exp in ("261030", "261106", "261120", "261201"):
        for k in range(330, 431):
            for cp in "CP":
                oi = 4000.0 * (2.718 ** (-((k - (392 if cp == "C" else 368)) / 12.0) ** 2)) + 50
                ops.append({"option": f"GLD{exp}{cp}{k * 1000:08d}", "iv": 0.22, "open_interest": round(oi), "gamma": 0.0, "volume": 10})
    return {"options": ops, "current_price": spot, "last_trade_time": ultima, "symbol": "GLD"}, "2026-10-19 20:00:00"


gamma._cargar = lambda simbolo: cadena()       # sustituye la descarga de Cboe

# ---------------------------------------------------------------- 1) una sola cadena (sin ETF que escalar)
M = GO.calcular(vol=(22.0, "2026-10-19"))
assert M["clave"] == "GLD" and M["sesion"] == "2026-10-19" and M["cierre_confirmado"] is True and M["ratio_etf"] == 1.0, "una cadena: ratio de ETF 1"
assert list(M["cadenas"]) == ["GLD"] and M["n_grupos"] >= 200
assert M["call_wall"]["idx"] >= 380 and M["put_wall"]["idx"] <= 380, "Call Wall por encima y Put Wall por debajo del precio"
assert M["flip"] is not None and M["max_gamma"]["idx"] > 0 and M["etiqueta"] == "GLD, referencia"
assert abs(M["em"]["puntos"] - round(380 * 22 / 100 / 252 ** 0.5, 1)) < 0.06 and M["em"]["vol_simbolo"] == "GVZ" and "ratio_etf" in M
# ES/NQ intactos: el cálculo de dos cadenas sigue dando ratio de ETF distinto de 1
assert gamma.INDICES["ES"]["cadenas"] == ["_SPX", "SPY"] and gamma.VOL_DE["ES"] == ("^VIX", "VIX")
print("1) OK GLD con una sola cadena: Call/Put Wall, Flip, Max Gamma y EM = GLD × GVZ / 100 / √252; ES/NQ sin cambios")

# ---------------------------------------------------------------- 2) ratio XAU/GLD con fecha (solo añadir)
T = nueva()
xau = lambda: (4140.8, "2026-10-19 21:30", "gold-api.com (XAU/USD al contado)")  # noqa: E731
f = GO.anotar_ratio(T, "2026-10-19", {"gld_cierre": lambda d: 379.69, "xau": xau}, "2026-10-19 21:30 UTC")
assert f["ratio"] == round(4140.8 / 379.69, 5)
GO.anotar_ratio(T, "2026-10-19", {"gld_cierre": lambda d: 1.0, "xau": xau}, "otra")
assert len(leer_csv(T, "xau_gld_ratio.csv")) == 1 and leer_csv(T, "xau_gld_ratio.csv")[0]["gld_cierre"] == "379.69", "solo añadir: no se reescribe la sesión"
r = GO.ratio_para(T, "2026-10-19")
assert r["exacto"] and abs(r["valor"] - 10.90574) < 1e-5
r2 = GO.ratio_para(T, "2026-10-23")
assert r2 and not r2["exacto"] and r2["fecha"] == "2026-10-19", "hasta 5 días: ratio aproximado con su fecha"
assert GO.ratio_para(T, "2026-10-25") is None and GO.ratio_para(T, "2026-10-01") is None, "más de 5 días o anterior al primer ratio: SIN DATO"


def cae(*a):
    raise RuntimeError("sin red")


assert GO.anotar_ratio(T, "2026-10-20", {"gld_cierre": lambda d: 380.0, "xau": cae}) is None and len(leer_csv(T, "xau_gld_ratio.csv")) == 1, "sin XAU no se anota ni se inventa"
print("2) OK ratio XAU/GLD anotado con fecha, solo añadir; aproximado ≤ 5 días con su fecha; sin dato → no se inventa")

# ---------------------------------------------------------------- 3) conversión a XAU
M = GO.calcular(vol=(22.0, "2026-10-19"))
GO.convertir(M, GO.ratio_para(T, "2026-10-19"))
n = {x["corto"]: x for x in M["niveles"]}
assert n["flip"]["xau"] == round(n["flip"]["gld"] * 10.90574, 1) and M["em_xau"] == round(M["em"]["puntos"] * 10.90574, 1) and M["ratio"]["nota"] == "ratio de la sesión"
GO.convertir(M, GO.ratio_para(T, "2026-10-23"))
assert "APROXIMADO" in M["ratio"]["nota"] and "2026-10-19" in M["ratio"]["nota"]
GO.convertir(M, None)
assert all(x["xau"] is None for x in M["niveles"]) and M["em_xau"] is None and M["ratio"] is None and all(x["gld"] is not None for x in M["niveles"]), "sin ratio: solo GLD"
print("3) OK conversión nivel XAU = nivel GLD × ratio; aproximado avisa con la fecha; sin ratio los niveles quedan en GLD y XAU = SIN DATO")

# ---------------------------------------------------------------- 4) reacción a ±0,25×EM (T+1)
em = 4.0                                          # zona = nivel ± 1,0
b = lambda o, h, l, c: {"o": o, "h": h, "l": l, "c": c}  # noqa: E731
assert GO.reaccion(100, em, b(103, 104, 101.5, 102.5))["resultado"] == "NO TOCADO", "mínimo 101,5 > 101 (borde superior): no tocó"
assert GO.reaccion(100, em, b(103, 104, 101.0, 102.5))["tocado"] is True, "justo en el borde de la zona: tocado"
assert GO.reaccion(100, em, b(103, 104, 100.5, 102.5))["resultado"] == "RECHAZADO", "llega de arriba, toca y cierra por encima de la zona"
assert GO.reaccion(100, em, b(97, 99.6, 96, 97.5))["resultado"] == "RECHAZADO", "llega de abajo, toca y cierra por debajo de la zona"
assert GO.reaccion(100, em, b(103, 104, 98, 98.0))["resultado"] == "ATRAVESADO", "llega de arriba y cierra por debajo de la zona"
assert GO.reaccion(100, em, b(97, 102, 96, 101.9))["resultado"] == "ATRAVESADO", "llega de abajo y cierra por encima de la zona"
assert GO.reaccion(100, em, b(103, 104, 99, 100.4))["resultado"] == "DENTRO"
x = GO.reaccion(380.0, 5.3, b(381, 383, 379, 382))
assert (x["zona_lo"], x["zona_hi"]) == (378.675, 381.325), x
print("4) OK reacción: zona = nivel ± 0,25×EM; NO TOCADO / RECHAZADO / ATRAVESADO / DENTRO (también en el borde exacto)")

# ---------------------------------------------------------------- 5) histórico, evaluación a T+1 y marcador (solo añadir)
T = nueva()
escribir(T, "gamma_oro.json", {})
GO.anotar_ratio(T, "2026-10-19", {"gld_cierre": lambda d: 379.69, "xau": xau}, "s")
barras = [{"fecha": dt.date(2026, 10, 19), "o": 380, "h": 382, "l": 378, "c": 379.69}, {"fecha": dt.date(2026, 10, 20), "o": 380.0, "h": 386.0, "l": 379.0, "c": 385.5}]
prev = None
J = GO.etapa(escribir_cierre=True, hoy="2026-10-19", stamp="s1", raiz=T, previo=prev, fuentes_={"vol": (22.0, "2026-10-19"), "barras": barras[:1]}, ahora=dt.datetime(2026, 10, 19, 21, 30, tzinfo=UTC))
assert J["historico_escrito"] is True and J["ok"] is True and len(leer_csv(T, "historico_gamma_oro.csv")) == 1 and J["marcador"]["evaluadas"] == 0, "sin T+1 todavía: pendiente"
h = leer_csv(T, "historico_gamma_oro.csv")[0]
assert h["fecha_sesion"] == "2026-10-19" and float(h["flip_xau"]) == [x["xau"] for x in J["niveles"] if x["corto"] == "flip"][0] and h["ratio_fecha"] == "2026-10-19"
# otra pasada con T+1 disponible
J = GO.etapa(escribir_cierre=False, hoy="2026-10-20", stamp="s2", raiz=T, previo=J, fuentes_={"vol": (22.0, "2026-10-19"), "barras": barras}, ahora=dt.datetime(2026, 10, 20, 21, 30, tzinfo=UTC))
res = leer_csv(T, "gamma_oro_resultados.csv")
assert len(res) == 4 and {r["nivel"] for r in res} == {"Gamma Flip", "Call Wall", "Put Wall", "Max Gamma"} and all(r["fecha_t1"] == "2026-10-20" for r in res)
assert J["marcador"]["evaluadas"] == 1 and J["marcador"]["estado"] == "CONGELADA" and J["marcador"]["min_n"] == 20 and "no se concluye nada" in J["marcador"]["criterio"]
antes = open(os.path.join(T, "data", "gamma_oro_resultados.csv"), encoding="utf-8").read()
GO.etapa(escribir_cierre=False, hoy="2026-10-20", stamp="s3", raiz=T, previo=J, fuentes_={"vol": (22.0, "2026-10-19"), "barras": barras})
assert open(os.path.join(T, "data", "gamma_oro_resultados.csv"), encoding="utf-8").read() == antes, "idempotente: no reescribe ni duplica resultados"
assert len(leer_csv(T, "historico_gamma_oro.csv")) == 1
print("5) OK histórico solo al cierre del día; evaluación a T+1 con 4 niveles; idempotente; CONGELADA hasta n ≥ 20")

# ---------------------------------------------------------------- 6) etapa: snapshot intradía conserva el cierre; sin cierre de hoy no escribe
T = nueva()
gamma._cargar = lambda s: cadena(ultima="2026-10-20T11:30:00")
prev = {"cierre_confirmado": True, "sesion": "2026-10-19", "niveles": []}
J = GO.etapa(escribir_cierre=True, hoy="2026-10-20", stamp="s", raiz=T, previo=prev, fuentes_={"vol": (22.0, "2026-10-19")})
assert J is prev and "descartado_intradia" in J and not os.path.exists(os.path.join(T, "data", "historico_gamma_oro.csv")) and not os.path.exists(os.path.join(T, "data", "xau_gld_ratio.csv")), "intradía: se conserva el cierre y no se escribe nada"
gamma._cargar = lambda s: cadena()      # sesión 19-oct, pero «hoy» es 20-oct (ejecución de diario o cierre antiguo)
J = GO.etapa(escribir_cierre=True, hoy="2026-10-20", stamp="s", raiz=T, previo=None, fuentes_={"vol": (22.0, "2026-10-19"), "gld_cierre": lambda d: 379.69, "xau": xau, "barras": []})
assert J["historico_escrito"] is False and not os.path.exists(os.path.join(T, "data", "historico_gamma_oro.csv")), "la sesión no es la de hoy: no se escribe histórico"
print("6) OK intradía conserva el último cierre; el histórico y el ratio solo se escriben con la sesión del día en la ejecución de cierre")

# ---------------------------------------------------------------- 7) línea ORO
T = nueva()
GO.anotar_ratio(T, "2026-10-19", {"gld_cierre": lambda d: 379.69, "xau": xau}, "s")
J = GO.etapa(escribir_cierre=False, hoy="2026-10-19", stamp="s", raiz=T, fuentes_={"vol": (22.0, "2026-10-19"), "barras": []})
escribir(T, "gamma_oro.json", J)
escribir(T, "resumen.json", {"tesis_activos": {"Oro": {"etiqueta": "ALCISTA DÉBIL"}}})
escribir(T, "oro.json", {"metricas": {"cot": {"mm_etiqueta": "largo bajo, percentil 27"}, "etf": {"5d_t": 3.06}}})
escribir(T, "agenda.json", {"agenda": {"hoy": [{"fecha": "2026-10-21", "hora_ny": "08:30", "evento": "IPC EE. UU. (CPI)", "importancia": "ALTA", "fecha_et": "2026-10-21"}, {"fecha": "2026-10-21", "hora_ny": None, "evento": "Resultados Tesla (TSLA)", "importancia": "ALTA"},
                                                {"fecha": "2026-10-21", "hora_ny": "10:00", "evento": "Vivienda", "importancia": "MEDIA"}], "proximos_7_dias": []}})
ahora = dt.datetime(2026, 10, 21, 13, 0, tzinfo=UTC)
L = GO.linea_oro(T, ahora)
assert L.startswith("XAU tesis=alcista;int=debil;flip="), L
kv = dict(p.split("=") for p in L[4:].split(";"))
assert list(kv) == ["tesis", "int", "flip", "cw", "pw", "em", "maxg", "ratio", "rf", "cot", "etf", "evento"], list(kv)
assert kv["cot"] == "largo-bajo_p27" and kv["etf"] == "+3.1" and kv["rf"] == "2026-10-19" and kv["ratio"] == "10.9057"
assert kv["evento"] == "ipc_ee_uu_cpi@14:30+resultados_tesla_tsla@na", kv["evento"]
assert all(" " not in v and ";" not in v and "|" not in v for v in kv.values()) and L.count(" ") == 1, "valores sin espacios ni separadores: el indicador los lee con split"
fl = float(kv["flip"])
assert abs(fl - [x["xau"] for x in J["niveles"] if x["corto"] == "flip"][0]) < 1e-9 and fl > 1000, "los niveles de la línea están en precio XAU"
# sin evento, sin tesis, sin COT, sin ETF, sin gamma
L0 = GO.linea_oro(T, dt.datetime(2026, 10, 22, 13, 0, tzinfo=UTC))
assert L0.endswith("evento=no")
escribir(T, "resumen.json", {"tesis_activos": {"Oro": {"etiqueta": "SIN TESIS"}}})
escribir(T, "oro.json", {"metricas": {"cot": {}, "etf": {}}})
L1 = GO.linea_oro(T, ahora)
assert "tesis=sin_tesis;int=na" in L1 and "cot=na" in L1 and "etf=na" in L1
escribir(T, "resumen.json", {"tesis_activos": {"Oro": {"etiqueta": "BAJISTA FUERTE"}}})
assert "tesis=bajista;int=fuerte" in GO.linea_oro(T, ahora)
os.remove(os.path.join(T, "site", "data", "gamma_oro.json"))
Lna = GO.linea_oro(T, ahora)
assert "flip=na;cw=na;pw=na;em=na;maxg=na;ratio=na;rf=na" in Lna, Lna
print("7) OK línea ORO: " + L)

# ---------------------------------------------------------------- 8) Telegram 15:00: ES/NQ intactos + línea ORO; sin palabras de compra/venta
escribir(T, "gamma_oro.json", J)
txt = GO.mensaje_oro(T, ahora)
assert "<code>XAU tesis=" in txt and "GLD, referencia" in txt and "no oficial" in txt and not GI.PALABRAS_PROHIBIDAS.search(txt)
escribir(T, "agenda.json", {"agenda": {"hoy": [{"fecha": "2026-10-21", "hora_ny": "08:30", "evento": "Ventas minoristas", "importancia": "ALTA"}], "proximos_7_dias": []}})
txt = GO.mensaje_oro(T, ahora)
assert "ventas_minoristas@14:30" in txt and not GI.PALABRAS_PROHIBIDAS.search(txt), "un evento llamado «Ventas…» no dispara la regla de palabras prohibidas (va en la línea, con guiones bajos)"
J_es = {"indices": {"ES": {"sesion": "2026-10-19", "flip": {"fut": 7804.0}, "call_wall": {"fut": 7843.6}, "put_wall": {"fut": 7693.6}, "max_gamma": {"fut": 7743.6}, "em": {"puntos": 97.0}},
                    "NQ": {"sesion": "2026-10-19", "flip": {"fut": 29920.4}, "call_wall": {"fut": 29892.0}, "put_wall": {"fut": 28592.0}, "max_gamma": {"fut": 29392.0}, "em": {"puntos": 502.1}}}}
base = GI.mensaje_niveles(J_es, ahora)
assert "XAU" not in base and "ES flip=7804.0" in base, "sin oro, el mensaje de ES/NQ no cambia"
con = GI.mensaje_niveles(J_es, ahora, txt)
assert con.count("<code>") == 2 and "ES flip=7804.0;cw=7843.6;pw=7693.6;em=97.0;maxg=7743.6 | NQ flip=29920.4" in con and "XAU tesis=" in con and "compra" not in con.lower()
enviados = []
os.makedirs(os.path.join(T, "data"), exist_ok=True)
escribir(T, "gamma.json", J_es)
import telegram  # noqa: E402
rc = GI.niveles_15h(raiz=T, ahora=ahora, forzar=True, enviar_fn=lambda m: (enviados.append(m), (True, None))[1])
assert rc == 0 and len(enviados) == 1 and "XAU tesis=" in enviados[0] and "ES flip=7804.0" in enviados[0]
print("8) OK el Telegram de las 15:00 lleva las líneas ES/NQ y la línea ORO en un solo mensaje, sin palabras de compra/venta")

# ---------------------------------------------------------------- 9) el indicador Pine: parseo equivalente en Python y casos de compilación estáticos
src = open(os.path.join(os.path.dirname(HERE), "plataformas", "tradingview", "NexoraOro.pine"), encoding="utf-8").read()
assert src.startswith("//@version=6") and 'request.security(simDXY, "D"' in src and "FRED:DFII10" in src and "TVC:DXY" in src and "GLD ref." in src
for clave in ("tesis", "int", "flip", "cw", "pw", "em", "maxg", "ratio", "rf", "cot", "etf", "evento"):
    assert f'"{clave}"' in src, clave
print("9) OK el indicador lee las mismas claves que escribe el motor (compilación real: tools/validar_pine_tradingview.py)")

shutil.rmtree(T, ignore_errors=True)
print("\nTODAS LAS PRUEBAS DE LA FASE 17 PASAN")
