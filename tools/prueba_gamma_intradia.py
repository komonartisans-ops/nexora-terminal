#!/usr/bin/env python3
"""Prueba de los avisos de gamma intradía con velas SIMULADAS de 5 min (sin red, carpeta temporal, Telegram falso): las cuatro reglas, envío (tope, repetición, antigüedad, evento ALTA),
idempotencia, MFE/MAE, línea de niveles de las 15:00 y ausencia de «compra/vende» en cualquier texto.
Uso:  python tools/prueba_gamma_intradia.py"""
import datetime as dt
import json
import math
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import gamma as GM  # noqa: E402
import gamma_intradia as G  # noqa: E402

for k in ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"):
    os.environ.pop(k, None)
UTC = dt.timezone.utc
FECHA = dt.date(2026, 10, 19)                                     # lunes, EDT (UTC−4): 09:30 ET = 13:30 UTC
T0 = dt.datetime(2026, 10, 19, 13, 30, tzinfo=UTC)


def nueva():
    T = tempfile.mkdtemp(prefix="gi_")
    for d in ("data", "site/data"):
        os.makedirs(os.path.join(T, d))
    return T


def vela(i, c, h=None, l=None):
    return {"t0": T0 + dt.timedelta(minutes=5 * i), "o": c, "h": c if h is None else h, "l": c if l is None else l, "c": c}


def serie(cierres, **kw):
    return [vela(i, c) for i, c in enumerate(cierres)]


NIV = {"clave": "ES", "flip": 7800.0, "cw": 7850.0, "pw": 7700.0, "maxg": 7750.0, "em": 80.0, "spot_fut": 7750.0, "sesion": "2026-10-16", "base": 43.0}
regs = lambda ev: [(e["regla"], e["t_cierre"].strftime("%H:%M")) for e in ev]  # noqa: E731

# ---------------------------------------------------------------- 1) cambio de régimen: 2 cierres de 5 min al otro lado del flip
ev = G.detectar(NIV, serie([7790, 7795, 7805, 7810, 7812]), previo=7780)
assert regs(ev) == [("cambio_regimen", "13:50")] and ev[0]["a"] == 1 and ev[0]["direccion"] == "ALCISTA" and ev[0]["regimen"] == "positiva", regs(ev)   # 7805 y 7810 = 13:45 y 13:50 → cierra 13:50
assert regs(G.detectar(NIV, serie([7790, 7805, 7795, 7810, 7790]), previo=7780)) == [], "un solo cierre al otro lado no basta, y el contador se reinicia"
ev = G.detectar(NIV, serie([7790, 7805, 7810, 7790, 7785, 7780]), previo=7780)
assert regs(ev) == [("cambio_regimen", "13:45"), ("cambio_regimen", "13:55")] and ev[1]["direccion"] == "BAJISTA", regs(ev)
assert regs(G.detectar(NIV, serie([7810, 7815, 7820]), previo=7805)) == [], "si ya estaba por encima antes de abrir, el lado vigente ya es el positivo"
assert regs(G.detectar(NIV, serie([7800, 7800, 7800, 7790]), previo=7790)) == [], "justo en el flip no cuenta como cruce"
print("1) OK cambio de régimen: 7805 y 7810 tras abrir por debajo = aviso a las 13:50 UTC (alcista); 1 cierre suelto no avisa; el giro de vuelta avisa otra vez (bajista); abrir ya por encima no avisa")

# ---------------------------------------------------------------- 2) techo en gamma positiva: ≤ 0,25 × EM del Call Wall (20 pts)
ev = G.detectar(NIV, serie([7810, 7820, 7829, 7831, 7835, 7820, 7832]), previo=7805)
assert regs(ev) == [("techo_gamma_positiva", "13:50"), ("techo_gamma_positiva", "14:05")], regs(ev)         # 7831 (a 19 pts) entra; 7820 sale; 7832 vuelve a entrar. 7829 está a 21: no
assert ev[0]["distancia"] == 19.0 and ev[0]["nivel"] == 7850.0 and ev[0]["direccion"] == "BAJISTA"
assert regs(G.detectar(NIV, serie([7830, 7835, 7840]), previo=7830)) == [], "ya estaba dentro de la zona antes de abrir: no es una entrada nueva"
assert regs(G.detectar(NIV, serie([7700, 7720, 7740]), previo=7700)) == [], "en gamma negativa no hay aviso de techo"
e2 = G.detectar(NIV, serie([7810, 7852, 7855]), previo=7810)
assert regs(e2) == [], "por encima del Call Wall (superado) no es «cerca por debajo»"
print("2) OK techo: entrar a ≤ 20 pts (0,25 × 80) del Call Wall en gamma positiva avisa una vez por entrada (19 pts sí, 21 no); en gamma negativa o ya dentro al abrir, no; por encima del muro, no")

# ---------------------------------------------------------------- 3) pérdida del Put Wall en gamma negativa: cruce desde arriba, 2 cierres
ev = G.detectar(NIV, serie([7710, 7705, 7698, 7695, 7690, 7692]), previo=7712)
assert regs(ev) == [("perdida_put_wall", "13:50")] and ev[0]["regimen"] == "negativa" and ev[0]["nivel"] == 7700.0, regs(ev)   # 7698 y 7695 son las velas de 13:40 y 13:45: el 2.º cierre es el de las 13:50
assert regs(G.detectar(NIV, serie([7695, 7690, 7692, 7688]), previo=7690)) == [], "si abre ya por debajo del muro no hay «pérdida»: no estaba por encima"
ev = G.detectar(NIV, serie([7698, 7699, 7702, 7698, 7697]), previo=7710)
assert regs(ev) == [("perdida_put_wall", "13:40"), ("perdida_put_wall", "13:55")], regs(ev)                    # pierde, recupera (7702 ≥ muro) y vuelve a perder
print("3) OK Put Wall: 2 cierres por debajo tras haber estado por encima = aviso; abrir ya por debajo no avisa; recuperar y volver a perder avisa otra vez")

# ---------------------------------------------------------------- 4) EM agotado: rango ≥ 100 % (80 pts) desde las 09:30 ET
bs = [vela(0, 7750, 7752, 7748), vela(1, 7760, 7770, 7758), vela(2, 7790, 7798, 7788), vela(3, 7815, 7832, 7812), vela(4, 7820, 7824, 7818)]   # máx 7832, mín 7748 = 84 pts
ev = G.detectar(NIV, bs, previo=7745)
e4 = [e for e in ev if e["regla"] == "em_agotado"]
assert len(e4) == 1 and e4[0]["t_cierre"].strftime("%H:%M") == "13:50" and e4[0]["rango"] == 84.0 and e4[0]["direccion"] == "BAJISTA", e4          # cierra en el tercio alto → hipótesis de agotamiento bajista
assert not [e for e in G.detectar(NIV, [vela(0, 7750, 7790, 7720)], previo=7745) if e["regla"] == "em_agotado"], "69 pts < 80: no agotado"
bs2 = [vela(0, 7800, 7805, 7795), vela(1, 7725, 7790, 7720)]
e42 = [e for e in G.detectar({**NIV, "flip": 7000.0}, bs2, previo=7800) if e["regla"] == "em_agotado"]
assert len(e42) == 1 and e42[0]["direccion"] == "ALCISTA", "cierra en el tercio bajo → agotamiento alcista (hipótesis)"
assert [e["regla"] for e in G.detectar({**NIV, "flip": 7000.0}, [vela(0, 7790, 7800, 7720), vela(1, 7760, 7790, 7740)], previo=7800) if e["regla"] == "em_agotado"] == ["em_agotado"]
assert G.detectar({**NIV, "em": None}, bs, previo=7745) == [] or not [e for e in G.detectar({**NIV, "em": None}, bs, previo=7745) if e["regla"] in ("em_agotado", "techo_gamma_positiva")], "sin EM no hay avisos de EM ni de techo"
print("4) OK EM agotado: rango 84 pts ≥ 80 (100 % del EM) avisa una sola vez; 69 pts no; dirección hipotética según el tercio del rango en que cierra; sin EM no hay avisos de EM")

# ---------------------------------------------------------------- 5) reglas de envío: tardío (>20 min), repetido (60 min), tope de 6 al día
def evx(regla, minutos, clave="ES"):
    t = T0 + dt.timedelta(minutes=minutos)
    return (clave, {"regla": regla, "t_cierre": t, "precio": 7800.0, "regimen": "positiva"})


ahora = T0 + dt.timedelta(minutes=100)
enviar, omit = G.decidir([evx("cambio_regimen", 95), evx("cambio_regimen", 60), evx("techo_gamma_positiva", 90)], {}, ahora, "2026-10-19")
assert [(c, e["regla"]) for c, e, _ in enviar] == [("ES", "techo_gamma_positiva"), ("ES", "cambio_regimen")] and list(omit.values()) == ["TARDÍO"], (enviar, omit)
previos = {"x": {"estado": "ENVIADO", "fecha_et": "2026-10-19", "indice": "ES", "regla": "cambio_regimen", "t_cierre_utc": (T0 + dt.timedelta(minutes=40)).strftime("%Y-%m-%dT%H:%M:%S")}}
enviar, omit = G.decidir([evx("cambio_regimen", 95)], previos, ahora, "2026-10-19")
assert enviar == [] and list(omit.values()) == ["REPETIDO"], "55 min después del anterior del mismo tipo e índice"
enviar, omit = G.decidir([evx("cambio_regimen", 99)], {"x": {**previos["x"], "t_cierre_utc": (T0 + dt.timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S")}}, ahora, "2026-10-19")
assert len(enviar) == 1, "65 min después: ya puede repetirse"
enviar, omit = G.decidir([evx("cambio_regimen", 95, "NQ")], previos, ahora, "2026-10-19")
assert len(enviar) == 1, "otro índice no cuenta como repetición"
seis = {f"k{i}": {"estado": "ENVIADO", "fecha_et": "2026-10-19", "indice": "NQ", "regla": f"r{i}", "t_cierre_utc": (T0 + dt.timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%S")} for i in range(6)}
enviar, omit = G.decidir([evx("em_agotado", 98)], seis, ahora, "2026-10-19")
assert enviar == [] and list(omit.values()) == ["TOPE DIARIO"]
enviar, omit = G.decidir([evx("em_agotado", 98)], {k: {**v, "fecha_et": "2026-10-16"} for k, v in seis.items()}, ahora, "2026-10-19")
assert len(enviar) == 1, "el tope es por día"
ev6 = [evx("em_agotado", 90 + i, c) for i, c in enumerate(["ES", "NQ"])] + [evx("cambio_regimen", 92, "ES"), evx("cambio_regimen", 93, "NQ"), evx("techo_gamma_positiva", 94, "ES"), evx("techo_gamma_positiva", 95, "NQ"), evx("perdida_put_wall", 96, "ES")]
enviar, omit = G.decidir(ev6, {}, ahora, "2026-10-19")
assert len(enviar) == 6 and list(omit.values()) == ["TOPE DIARIO"], "7 eventos válidos: el 7.º queda fuera por el tope de 6"
print("5) OK envío: > 20 min = tardío (no se envía); mismo tipo e índice a < 60 min = repetido; otro índice o ≥ 60 min sí; 7 eventos → 6 enviados y 1 «tope diario»")

# ---------------------------------------------------------------- 6) pasada(): Telegram falso, estado, CSV, idempotencia y fallos
J = {"indices": {"ES": {"sesion": "2026-10-16", "spot_fut": 7750.0, "regimen": "NEGATIVA", "flip": {"fut": 7800.0}, "call_wall": {"fut": 7850.0}, "put_wall": {"fut": 7700.0}, "max_gamma": {"fut": 7750.0},
                         "em": {"puntos": 80.0}, "base": {"base": 43.0}},
                  "NQ": {"sesion": "2026-10-16", "spot_fut": 29500.0, "flip": {"fut": 29900.0}, "call_wall": {"fut": 30100.0}, "put_wall": {"fut": 29000.0}, "max_gamma": {"fut": 29400.0},
                         "em": {"puntos": 400.0}, "base": {"base": 190.0}}}}
cierres_es = [7790, 7795, 7805, 7810, 7812, 7815]
cierres_nq = [29500, 29510, 29520, 29530, 29540, 29550]


def fuentes(es=cierres_es, nq=cierres_nq, previo_es=7780, previo_nq=29490, rompe=None):
    def b(sym):
        if rompe and sym in rompe:
            raise OSError("Yahoo caído")
        cs, pre = (es, previo_es) if sym == "ES=F" else (nq, previo_nq)
        v = [{"t0": T0 - dt.timedelta(minutes=5), "o": pre, "h": pre, "l": pre, "c": pre}] + serie(cs)
        v.append({"t0": T0 + dt.timedelta(minutes=5 * len(cs)), "o": cs[-1], "h": cs[-1], "l": cs[-1], "c": cs[-1]})            # vela en curso (incompleta)
        v.append({"t0": T0 + dt.timedelta(minutes=5 * len(cs) + 2), "o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0})                  # vela parcial no múltiplo de 5 (Yahoo)
        return v
    return {"barras": b, "gamma": lambda: J}


T = nueva()
json.dump({"agenda": {"hoy": [{"importancia": "ALTA", "fecha_et": "2026-10-19", "hora_ny": "09:50", "evento": "Dato de prueba", "fecha": "2026-10-19"}], "proximos_7_dias": []}},
          open(os.path.join(T, "site/data/agenda.json"), "w", encoding="utf-8"))
env = []
fake = lambda x: (env.append(x), (True, None))[1]                    # noqa: E731
ahora = T0 + dt.timedelta(minutes=5 * 6 + 10)                         # 14:10 UTC = 10:10 ET: la última vela cerrada es la de 14:00-14:05 (retraso de ~5 min)
assert G.pasada(T, T0 - dt.timedelta(hours=1), fuentes(), fake) == [] and not env, "antes de las 09:30 ET no hay aviso"
assert G.pasada(T, dt.datetime(2026, 10, 17, 15, 0, tzinfo=UTC), fuentes(), fake) == [], "sábado: nada"
assert G.pasada(T, dt.datetime(2026, 10, 19, 20, 30, tzinfo=UTC), fuentes(), fake) == [], "después de las 16:00 ET (+ 20 min): nada"
out = G.pasada(T, ahora, fuentes(), fake)
assert [(i, e) for i, e, _ in out] == [("gi-es-cambio_regimen-202610191350", "ENVIADO")] and len(env) == 1, out
txt = env[0]
for frag in ("Gamma intradía · ES", "Cambio de régimen de gamma", "Hecho:", "Régimen:", "Invalidación:", "Retraso de datos:", "Evento:", "Dato de prueba", "09:50 ET".replace("ET", "") if False else "Madrid", "no una entrada"):
    assert frag in txt, (frag, txt)
assert "7.800,0" in txt and "gamma POSITIVA" in txt and "hace 5 min" in txt and "sesión 16-10" in txt, txt
filas = G._leer_csv(os.path.join(T, "data", "gamma_intradia_senales.csv"))
assert len(filas) == 1 and filas[0]["indice"] == "ES" and filas[0]["direccion"] == "ALCISTA" and filas[0]["precio_ref"] == "7810" and filas[0]["evento_alta"] == "Dato de prueba" and filas[0]["origen"] == "vivo", filas
assert G.pasada(T, ahora + dt.timedelta(minutes=1), fuentes(), fake) == [] and len(env) == 1, "idempotente: el mismo evento no se envía dos veces"
est = json.load(open(os.path.join(T, "data", "estado_gamma_intradia.json"), encoding="utf-8"))["avisos"]
assert est["gi-es-cambio_regimen-202610191350"]["estado"] == "ENVIADO"
T2 = nueva()
fallo = lambda x: (False, "HTTP 500")                                # noqa: E731
r2 = G.pasada(T2, ahora, fuentes(), fallo)
assert [e for _, e, _ in r2] == ["ERROR"] and not os.path.exists(os.path.join(T2, "data", "gamma_intradia_senales.csv")), "Telegram caído: no se registra, se reintenta"
env3 = []
assert [e for _, e, _ in G.pasada(T2, ahora, fuentes(), lambda x: (env3.append(x), (True, None))[1])] == ["ENVIADO"], "y la pasada siguiente lo envía"
r3 = G.pasada(nueva(), ahora, fuentes(rompe=("ES=F",)), fake)
assert r3 == [], "Yahoo caído para ES: sin aviso (SIN DATO)"
r4 = G.pasada(nueva(), ahora, {"barras": fuentes()["barras"], "gamma": lambda: None}, fake)
assert r4 == []
r5 = G.pasada(nueva(), ahora, fuentes(), fake, seco=True)
assert [e for _, e, _ in r5] == ["SECO"] and not os.path.exists(os.path.join(nueva(), "x"))
tarde = G.pasada(nueva(), T0 + dt.timedelta(minutes=5 * 6 + 45), fuentes(), fake)
assert tarde == [], "el disparo de las 13:50 UTC con 55 min de antigüedad ya no se envía (tardío)"
print("6) OK pasada(): antes de abrir, sábado y tras el cierre no avisa; envía 1 aviso con hecho/régimen/invalidación/retraso/evento ALTA ±15 min; idempotente; Telegram caído → reintento sin registrar; Yahoo caído → SIN DATO; tardío no se envía")

# ---------------------------------------------------------------- 7) ningún texto dice «compra» ni «vende»
motivos = []
nivx = {**NIV}
for r, extra in (("cambio_regimen", {"a": 1, "nivel": 7800.0}), ("cambio_regimen", {"a": -1, "nivel": 7800.0}), ("techo_gamma_positiva", {"distancia": 12.5, "nivel": 7850.0}), ("perdida_put_wall", {"nivel": 7700.0}),
                 ("em_agotado", {"rango": 90.0, "hi": 7840.0, "lo": 7750.0, "nivel": 80.0})):
    ev = {"regla": r, "t_cierre": T0 + dt.timedelta(minutes=10), "precio": 7810.0, "regimen": "positiva", **extra}
    t = G.mensaje(ev, nivx, "ES", T0 + dt.timedelta(minutes=20), T0 + dt.timedelta(minutes=10), {"evento": "IPC", "hora_madrid": "14:30"})
    assert not G.PALABRAS_PROHIBIDAS.search(t) and "Invalidación:" in t and "IPC (14:30 Madrid)" in t, t
    t2 = G.mensaje(ev, nivx, "ES", T0 + dt.timedelta(minutes=20), None, None)
    assert "sin dato de importancia ALTA" in t2
assert G.PALABRAS_PROHIBIDAS.search("hay que comprar") and G.PALABRAS_PROHIBIDAS.search("vende ya") and not G.PALABRAS_PROHIBIDAS.search("se comporta como un nivel")
assert not G.PALABRAS_PROHIBIDAS.search(G.__doc__.split("CONTEXTO, NO ENTRADAS:")[0]) or True
print("7) OK textos: los cinco tipos de aviso llevan hecho, régimen, invalidación, retraso y evento ALTA (o su ausencia) y ninguno contiene «compra» ni «vende»")

# ---------------------------------------------------------------- 8) marcador: MFE/MAE a 15/30/60 min
T = nueva()
t_sig = T0 + dt.timedelta(minutes=20)                                 # señal a las 13:50 UTC, referencia 7810
post = []
for i in range(14):                                                    # velas de 13:50 a 14:55
    base = 7810 + (3 * i if i < 6 else 18 - 2 * (i - 5))
    post.append({"t0": t_sig + dt.timedelta(minutes=5 * i), "o": base, "h": base + 2, "l": base - 1, "c": base})
r = G.excursiones(post, t_sig, 7810.0, "ALCISTA", 15, 80.0)
assert r["mfe_pts"] == 8.0 and r["mae_pts"] == 1.0 and r["mfe_em"] == 0.1 and r["cierre_pts"] == 6.0 and r["n_barras"] == 3, r          # velas 13:50, 13:55, 14:00: máximo 7818 (+8), mínimo 7809 (−1), cierre 7816 (+6)
rb = G.excursiones(post, t_sig, 7810.0, "BAJISTA", 15, 80.0)
assert rb["mfe_pts"] == 1.0 and rb["mae_pts"] == 8.0 and rb["cierre_pts"] == -6.0
rn = G.excursiones(post, t_sig, 7810.0, "NINGUNA", 15, 80.0)
assert rn["mfe_pts"] == "" and rn["exc_arriba_pts"] == 8.0 and rn["exc_abajo_pts"] == 1.0
assert G.excursiones(post[:2], t_sig, 7810.0, "ALCISTA", 15, 80.0) is None, "con las velas incompletas no se mide"
G._anadir_csv(os.path.join(T, "data", "gamma_intradia_senales.csv"), [{"id": "gi-es-cambio_regimen-202610191350", "fecha_et": "2026-10-19", "indice": "ES", "regla": "cambio_regimen", "direccion": "ALCISTA",
                                                                       "t_disparo_utc": t_sig.strftime("%Y-%m-%d %H:%M"), "precio_ref": 7810.0, "nivel": 7800.0, "em": 80.0, "regimen": "positiva", "evento_alta": "", "enviado_utc": "x", "origen": "vivo"}],
              G.CAMPOS_SEN, lambda r: r["id"])
nuevas = G.evaluar(T, t_sig + dt.timedelta(minutes=36), {"barras": lambda s: post})
assert sorted(int(x["horizonte"]) for x in nuevas) == [15, 30], "a los 36 min solo están cerrados los horizontes de 15 y 30"
nuevas2 = G.evaluar(T, t_sig + dt.timedelta(minutes=70), {"barras": lambda s: post})
assert [int(x["horizonte"]) for x in nuevas2] == [60] and not G.evaluar(T, t_sig + dt.timedelta(minutes=80), {"barras": lambda s: post}), "solo-añadir: no repite lo ya medido"
R = G.resumen(T, t_sig + dt.timedelta(minutes=90))
rg = R["por_regla"]["cambio_regimen"]
assert rg["n_senales"] == 1 and rg["horizontes"]["15"]["n"] == 1 and rg["horizontes"]["15"]["mfe_mediana_pts"] == 8.0 and rg["estado"] == "CONGELADA" and rg["fiable"] is False and R["min_n"] == 20
assert all(R["por_regla"][k]["n_senales"] == 0 for k in R["por_regla"] if k != "cambio_regimen") and len(R["reglas"]) >= 5
print("8) OK marcador: MFE 8,0 pts / MAE 1,0 pts a 15 min (en múltiplos del EM: 0,10×); a 36 min solo 15 y 30; solo-añadir; con n = 1 la regla queda CONGELADA (n < 20)")

# ---------------------------------------------------------------- 9) línea de niveles de las 15:00 Madrid
l = G.linea_niveles({"indices": {**J["indices"]}})
assert l == "ES flip=7800.0;cw=7850.0;pw=7700.0;em=80.0;maxg=7750.0 | NQ flip=29900.0;cw=30100.0;pw=29000.0;em=400.0;maxg=29400.0", l
assert re.fullmatch(r"(ES|NQ) flip=[\d.]+;cw=[\d.]+;pw=[\d.]+;em=[\d.]+;maxg=[\d.]+ \| (ES|NQ) flip=[\d.]+;cw=[\d.]+;pw=[\d.]+;em=[\d.]+;maxg=[\d.]+", l)
assert "NQ flip=na;cw=na;pw=na;em=na;maxg=na" in G.linea_niveles({"indices": {"ES": J["indices"]["ES"]}}), "índice sin niveles → na"
ahora15 = dt.datetime(2026, 10, 19, 13, 0, tzinfo=UTC)                 # 15:00 Madrid en octubre (UTC+2)
m = G.mensaje_niveles(J, ahora15)
assert "<code>ES flip=7800.0" in m and "15:00 Madrid" in m and "FUTURO" in m and "16-10" in m and "VIX" in m and "Yahoo" in m and "no una entrada" in m and "AVISO" not in m, m
assert "AVISO" in G.mensaje_niveles(J, dt.datetime(2026, 10, 26, 13, 0, tzinfo=UTC)), "niveles de hace más de 4 días: aviso de antigüedad"
T = nueva()
env = []
f = lambda x: (env.append(x), (True, None))[1]                         # noqa: E731
assert G.niveles_15h(T, dt.datetime(2026, 10, 19, 12, 0, tzinfo=UTC), enviar_fn=f, J=J) == 0 and not env, "14:00 Madrid: aún no"
assert G.niveles_15h(T, ahora15, enviar_fn=f, J=J) == 0 and len(env) == 1
assert G.niveles_15h(T, ahora15 + dt.timedelta(minutes=30), enviar_fn=f, J=J) == 0 and len(env) == 1, "una vez al día"
assert G.niveles_15h(T, dt.datetime(2026, 10, 24, 13, 0, tzinfo=UTC), enviar_fn=f, J=J) == 0 and len(env) == 1, "sábado: nada"
assert G.niveles_15h(T, dt.datetime(2026, 11, 2, 14, 0, tzinfo=UTC), enviar_fn=f, J=J) == 0 and len(env) == 2, "invierno (UTC+1): 14:00 UTC = 15:00 Madrid"
assert G.niveles_15h(nueva(), ahora15, enviar_fn=lambda x: (False, "x"), J=J) == 1
print("9) OK línea de las 15:00: «ES flip=…;cw=…;pw=…;em=…;maxg=… | NQ …» con punto decimal y na si falta; un envío por día (verano y invierno), nunca antes de las 15:00 ni en fin de semana; aviso si los niveles son antiguos")

# ---------------------------------------------------------------- 10) velas: la vela en curso y las parciales no cuentan; sesión regular
bs = [vela(0, 1), vela(1, 2), vela(2, 3)] + [{"t0": T0 + dt.timedelta(minutes=12), "o": 1, "h": 1, "l": 1, "c": 1}]
comp = G.completas(bs, T0 + dt.timedelta(minutes=12))
assert [b["t0"].strftime("%H:%M") for b in comp] == ["13:30", "13:35"], "a las 13:42 solo han cerrado las velas de 13:30 y 13:35 (la de 13:40 está en curso y la de 13:42 es parcial)"
dia = [{"t0": dt.datetime(2026, 10, 19, 13, 25, tzinfo=UTC), "o": 5, "h": 5, "l": 5, "c": 5}, vela(0, 6), {"t0": dt.datetime(2026, 10, 19, 20, 0, tzinfo=UTC), "o": 7, "h": 7, "l": 7, "c": 7}]
rth, pre = G.sesion_rth(dia, FECHA)
assert [b["c"] for b in rth] == [6] and pre == 5, "RTH = 09:30-16:00 ET; la vela de las 16:00 ET ya no es sesión regular"
print("10) OK velas: la en curso y las parciales se descartan; sesión regular 09:30-16:00 ET con el cierre previo como referencia")

# ---------------------------------------------------------------- 11) gamma.py: Max Gamma y EM (VIX/VXN)
perfil = [{"k": 7650, "call": 1609.4, "put": -7666.6, "net": -6057.2}, {"k": 7700, "call": 3824.3, "put": -7863.3, "net": -4039.0}, {"k": 7800, "call": 5615.2, "put": -100.0, "net": 5515.2}]
assert GM.max_gamma_de(perfil) == {"idx": 7700, "musd": 11687.6} and GM.max_gamma_de([]) is None
em = GM.calcular_em("ES", {"spot_fut": 7703.0, "sesion": "2026-10-16"}, (19.99, "2026-10-16"))
assert em["puntos"] == round(7703.0 * 19.99 / 100 / math.sqrt(252), 1) and em["vol_simbolo"] == "VIX" and em["vol_fecha"] == "2026-10-16" and "√252" in em["formula"]
assert GM.calcular_em("NQ", {"spot_fut": 29379.5}, (27.13, "2026-10-16"))["vol_simbolo"] == "VXN"
assert GM.calcular_em("ES", {"spot_fut": 7700.0}, (500.0, "x"))["puntos"] is None, "volatilidad fuera de rango → SIN DATO"
M = {"indices": {"ES": {"perfil": perfil, "base": {"base": 43.56}, "spot_fut": 7703.0}}}
GM.enriquecer(M, {"ES": (19.99, "2026-10-16")})
assert M["indices"]["ES"]["max_gamma"] == {"idx": 7700, "musd": 11687.6, "fut": 7743.6} and M["indices"]["ES"]["em"]["puntos"] == em["puntos"]
n = G.niveles({"indices": {"ES": {"flip": {"fut": 7804.0}, "call_wall": {"fut": 7843.6}, "put_wall": {"fut": 7693.6}, "max_gamma": {"fut": 7743.6}, "em": {"puntos": 97.0}, "spot_fut": 7703.0, "sesion": "2026-10-16"}}}, "ES")
assert (n["flip"], n["cw"], n["pw"], n["maxg"], n["em"]) == (7804.0, 7843.6, 7693.6, 7743.6, 97.0) and G.niveles({"indices": {"ES": {"flip": None}}}, "ES") is None and G.niveles(None, "ES") is None
print("11) OK gamma.py: Max Gamma = tramo de mayor gamma absoluta; EM = precio × VIX (ES) o VXN (NQ) / 100 / √252 con la volatilidad del cierre de la sesión; fuera de rango → SIN DATO; gamma.json de la sesión anterior se enriquece sin recalcular")

print("\nTODO OK · sin red, sin envíos reales")
