#!/usr/bin/env python3
"""Pruebas de la Fase 19 (contraste del spot del oro). Sin red y sin Telegram real: fuentes inyectadas y envío simulado.
Uso: PYTHONUTF8=1 python tools/prueba_spot_oro.py"""
import csv
import datetime as dt
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
import gamma_oro as GO  # noqa: E402
import integridad as IG  # noqa: E402
import spot_oro as SO  # noqa: E402

UTC = dt.timezone.utc
BASE_ANTERIOR = 14.5                                  # base GC−XAU de la sesión anterior (22-oct, dato real)


def raiz(base=True, ratio_previo=True):
    T = tempfile.mkdtemp(prefix="spot_")
    os.makedirs(os.path.join(T, "data"))
    if base:
        with open(os.path.join(T, "data", "xau_gc_base.csv"), "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(GO.CAMPOS_BASE)
            w.writerow(["2026-10-22", 4025.3, 4039.8, BASE_ANTERIOR, "2026-10-22 20:59", "GC=F", "x"])
    if ratio_previo:
        with open(os.path.join(T, "data", "xau_gld_ratio.csv"), "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(GO.CAMPOS_RATIO)
            w.writerow(["2026-10-22", 369.0, 4025.3, 10.90867, "2026-10-22 21:31", "gold-api.com (XAU/USD al contado)", "x"])
    return T


def csv_(T, n):
    p = os.path.join(T, "data", n)
    return list(csv.DictReader(open(p, encoding="utf-8"))) if os.path.exists(p) else []


def F(principal=4030.0, hp="2026-10-23 12:55", swiss=4031.0, hs="2026-10-23 12:56", gc=4044.5, hg="2026-10-23 12:54"):
    """Fuentes inyectadas. None = esa fuente no está disponible (cae)."""
    def caida():
        raise ConnectionError("caída simulada")
    return {"xau": (lambda: (principal, hp, "gold-api.com (XAU/USD al contado)")) if principal is not None else caida,
            "swiss": (lambda: (swiss, hs, "Swissquote")) if swiss is not None else caida,
            "gc": (lambda h: (gc, hg)) if gc is not None else caida,
            "gld_cierre": lambda d: 379.69}


def dec(T, f, sesion="2026-10-23"):
    fs = GO.fuentes_spot(f)
    return SO.decidir(T, sesion, fs["principal"], fs["gc"], fs["swiss"], medido_utc="t")


# 1) spot correcto → OK, se usa la principal, el ratio se anota
T = raiz()
d = dec(T, F())
assert d["estado"] == "OK" and d["spot_fuente"] == "GOLD_API" and d["ratio_fuente"] == "SESION" and d["gc_sinc"] == "SI" and d["swiss_sinc"] == "SI", d
assert abs(float(d["dif_gc_pct"])) <= 0.3 and abs(float(d["dif_swiss_pct"])) <= 0.3 and float(d["spot_gc_implicito"]) == round(4044.5 - BASE_ANTERIOR, 2), d
fr = GO.anotar_ratio(T, "2026-10-23", F(), "t")
assert fr and fr["xau_spot"] == 4030.0 and len(csv_(T, "xau_gld_ratio.csv")) == 2, fr
print(f"1) OK spot correcto: gold-api 4030,00 · GC implícito {d['spot_gc_implicito']} ({d['dif_gc_pct']} %) · Swissquote 4031,00 ({d['dif_swiss_pct']} %) → {d['estado']}, ratio anotado")

# 2) spot desviado un 1 % → ⚠️ DUDOSO, ratio NO actualizado, línea ORO con ;spot=dudoso
T = raiz()
f2 = F(principal=4030.0 * 1.01, swiss=4031.0)                  # la principal se desvía +1 % de las otras dos
d = dec(T, f2)
assert d["estado"] == "DUDOSO" and d["ratio_fuente"] == "ANTERIOR" and abs(float(d["dif_swiss_pct"])) > 0.3, d
n_antes = len(csv_(T, "xau_gld_ratio.csv"))
assert GO.anotar_ratio(T, "2026-10-23", f2, "t") is None and len(csv_(T, "xau_gld_ratio.csv")) == n_antes and not csv_(T, "xau_gc_base.csv")[1:], "ratio y base sin actualizar"
r = GO.ratio_para(T, "2026-10-23")
assert r["fecha"] == "2026-10-22" and r["exacto"] is False, r
J = {"niveles": [], "ratio": {**r, "ratio_fuente": "ANTERIOR"}, "spot_contraste": SO.resumen_fila(SO.fila_de(T, "2026-10-23"))}
L = GO.linea_oro(T, dt.datetime(2026, 10, 23, 13, 0, tzinfo=UTC), J)
assert L.endswith(";spot=dudoso") and "rf=2026-10-22" in L, L
J["spot_contraste"] = SO.resumen_fila(dec(raiz(), F(), "2026-10-23"))
assert ";spot=" not in GO.linea_oro(T, dt.datetime(2026, 10, 23, 13, 0, tzinfo=UTC), J), "con OK la línea no cambia"
print(f"2) OK desviado +1 %: dif Swissquote {d['dif_swiss_pct']} % → {d['estado']}, ratio no actualizado (ratio_fuente={d['ratio_fuente']}, se usa el del 22-oct), línea acaba en ;spot=dudoso")

# 2b) el borde: exactamente 0,3 % es OK; por encima, DUDOSO
assert dec(raiz(), F(principal=4000.0, swiss=4012.0, gc=None))["estado"] == "OK"
assert dec(raiz(), F(principal=4000.0, swiss=4013.0, gc=None))["estado"] == "DUDOSO"
print("2b) OK umbral: 0,300 % → OK · 0,325 % → DUDOSO")

# 3) principal caída → GC implícito, marcado; no se anota la base (sería circular)
T = raiz()
f3 = F(principal=None)
d = dec(T, f3)
assert d["estado"] == "GC_IMPLICITO" and d["spot_fuente"] == "GC_IMPLICITO" and float(d["spot_usado"]) == round(4044.5 - BASE_ANTERIOR, 2), d
fr = GO.anotar_ratio(T, "2026-10-23", f3, "t")
assert fr and fr["fuente_xau"].startswith("GC_IMPLICITO") and fr["xau_spot"] == round(4044.5 - BASE_ANTERIOR, 2), fr
assert GO.anotar_base(T, "2026-10-23", fr, f3, "t") is None and len(csv_(T, "xau_gc_base.csv")) == 1, "la base de hoy no se anota con el GC implícito"
assert dec(raiz(), F(principal=None, gc=None, swiss=None)) is None, "sin principal, sin GC y sin Swissquote no hay spot (no se inventa)"
print(f"3) OK principal caída → spot {d['spot_usado']} = GC 4044,50 − base {BASE_ANTERIOR} (spot_fuente={d['spot_fuente']})")

# 3b) último recurso: sin principal ni GC implícito → Swissquote; spot_fuente=SWISSQUOTE; ratio y base NO se actualizan (últimos OK); no falla
T = raiz()
f3b = F(principal=None, gc=None, swiss=4031.0)
d = dec(T, f3b)
assert d["estado"] == "SWISSQUOTE" and d["spot_fuente"] == "SWISSQUOTE" and float(d["spot_usado"]) == 4031.0 and d["ratio_fuente"] == "ANTERIOR", d
n0 = len(csv_(T, "xau_gld_ratio.csv"))
assert GO.anotar_ratio(T, "2026-10-23", f3b, "t") is None and len(csv_(T, "xau_gld_ratio.csv")) == n0 and len(csv_(T, "xau_gc_base.csv")) == 1, "ni ratio ni base"
assert GO.ratio_para(T, "2026-10-23")["fecha"] == "2026-10-22"
E = SO.etapa(escribir_cierre=True, hoy="2026-10-24", stamp="s", raiz=raiz(), fuentes_=F(principal=None, gc=None, swiss=4031.0))
assert E["decision"]["spot_fuente"] == "SWISSQUOTE", "la etapa NO falla: hay niveles ORO con el ratio anterior"
print("3b) OK último recurso: principal y GC caídos → spot Swissquote 4031,00, ratio y base sin actualizar (ratio_fuente=ANTERIOR), la etapa no falla")

# 4) fuentes desfasadas en hora → NO_SINCRONIZADO (no se compara ni se acusa); con solo una fuera de hora, la otra decide
T = raiz()
d = dec(T, F(hs="2026-10-23 13:30", hg="2026-10-23 12:30", swiss=4100.0))     # Swissquote «tiene» 4100 pero es de 35 min después: NO se compara
assert d["estado"] == "NO_SINCRONIZADO" and d["swiss_sinc"] == "NO" and d["gc_sinc"] == "NO" and not d.get("dif_swiss_pct") and d["spot_fuente"] == "GOLD_API", d
assert GO.anotar_ratio(T, "2026-10-23", F(hs="2026-10-23 13:30", hg="2026-10-23 12:30"), "t") is not None, "NO_SINCRONIZADO no es ⚠️: sin evidencia en contra, el ratio se actualiza"
d = dec(raiz(), F(hg="2026-10-23 12:30"))
assert d["estado"] == "OK" and d["gc_sinc"] == "NO" and d["swiss_sinc"] == "SI", d
assert dec(raiz(), F(swiss=None, gc=None))["estado"] == "SIN_CONTRASTE"
assert SO.sincronizadas("2026-10-23 12:50", "2026-10-23 12:55") and not SO.sincronizadas("2026-10-23 12:50", "2026-10-23 12:56")
print("4) OK desfasadas (Swissquote +35 min, GC −25 min) → NO_SINCRONIZADO sin falsa alarma · una sola fuera de hora → decide la otra · ±5 min exactos")

# 5) la primera decisión del día manda (solo añadir)
T = raiz()
d1 = dec(T, F())
d2 = dec(T, F(principal=4030.0 * 1.01))
assert d2["estado"] == "OK" and len(csv_(T, "xau_spot_contraste.csv")) == 1 and d1["estado"] == "OK"
print("5) OK registro de solo añadir: una fila por sesión, la primera decisión manda")

# 6) 2 días seguidos en ⚠️ → UN aviso por Telegram (simulado); no se repite ni con el tercer día
T = raiz()
for ses, hp_ in (("2026-10-22", "2026-10-22 21:31"), ("2026-10-23", "2026-10-23 21:31")):
    dec(T, F(principal=4030.0 * 1.01, hp=hp_, hs=hp_[:11] + "21:32", hg=hp_[:11] + "21:30"), ses)
n, ini = SO.racha_dudoso(T)
assert (n, ini) == (2, "2026-10-22"), (n, ini)
enviados = []
env = lambda m: (enviados.append(m), (True, None))[1]  # noqa: E731
ahora = dt.datetime(2026, 10, 23, 21, 40, tzinfo=UTC)
IG.vigilar(T, ahora, enviar=env)
IG.vigilar(T, ahora + dt.timedelta(minutes=5), enviar=env)
dec(T, F(principal=4030.0 * 1.01), "2026-10-26")
IG.vigilar(T, ahora + dt.timedelta(days=3), enviar=env)
sp = [m for m in enviados if "Spot del oro" in m]
assert len(sp) == 1 and "2 sesiones seguidas" in sp[0] and "desde 2026-10-22" in sp[0], enviados
assert SO.racha_dudoso(T)[0] == 3
T2 = raiz()
dec(T2, F(principal=4030.0 * 1.01), "2026-10-22")
dec(T2, F(), "2026-10-23")
assert SO.racha_dudoso(T2)[0] == 0
env2 = []
IG.vigilar(T2, ahora, enviar=lambda m: (env2.append(m), (True, None))[1])
assert not [m for m in env2 if "Spot del oro" in m], "un solo ⚠️ no avisa"
print("6) OK 2 sesiones seguidas en ⚠️ → 1 aviso (Telegram simulado); la tercera no lo repite; un solo ⚠️ no avisa")

T_RACHA = T

# 6b) Swissquote sin responder 3 sesiones seguidas → UN aviso por racha (Telegram simulado); SIN_CONTRASTE/NO_SINCRONIZADO no frenan el ratio
T = raiz()
for ses in ("2026-10-21", "2026-10-22"):
    d = dec(T, F(swiss=None), ses)
    assert d["estado"] in ("OK", "NO_SINCRONIZADO", "SIN_CONTRASTE") and not d.get("swiss_precio")
assert SO.racha_swiss_caido(T) == (2, "2026-10-21")
env3 = []
envf = lambda m: (env3.append(m), (True, None))[1]  # noqa: E731
IG.vigilar(T, dt.datetime(2026, 10, 22, 22, 0, tzinfo=UTC), enviar=envf)
assert not [m for m in env3 if "Swissquote" in m], "con 2 sesiones aún no avisa"
dec(T, F(swiss=None), "2026-10-23")
IG.vigilar(T, dt.datetime(2026, 10, 23, 22, 0, tzinfo=UTC), enviar=envf)
IG.vigilar(T, dt.datetime(2026, 10, 23, 22, 5, tzinfo=UTC), enviar=envf)
dec(T, F(swiss=None), "2026-10-26")
IG.vigilar(T, dt.datetime(2026, 10, 26, 22, 0, tzinfo=UTC), enviar=envf)
sw = [m for m in env3 if "Swissquote" in m]
assert len(sw) == 1 and "3 sesiones seguidas" in sw[0] and "desde 2026-10-21" in sw[0], env3
assert SO.racha_swiss_caido(T)[0] == 4 and IG._resumen_spot(T)["racha_swiss_caido"] == 4
dec(T, F(), "2026-10-27")
assert SO.racha_swiss_caido(T)[0] == 0, "una respuesta de Swissquote corta la racha"
T = raiz()      # filas de sábado/domingo (cierre tardío de las 00:01 UTC con el mercado cerrado) no cuentan como sesiones
dec(T, F(swiss=None), "2026-10-23")
for ses in ("2026-10-24", "2026-10-25"):
    dec(T, F(swiss=None), ses)
assert SO.racha_swiss_caido(T) == (1, "2026-10-23"), SO.racha_swiss_caido(T)
d = dec(raiz(), F(swiss=None, gc=None))
assert d["estado"] == "SIN_CONTRASTE" and GO.anotar_ratio(raiz(), "2026-10-23", F(swiss=None, gc=None), "t") is not None, "SIN_CONTRASTE no frena el ratio"
d = dec(raiz(), F(hg="2026-10-23 12:40", swiss=None))
assert d["estado"] == "NO_SINCRONIZADO" and "informativo (retraso ~10 min)" in SO.texto_fuentes(d), SO.texto_fuentes(d)
print("6b) OK Swissquote sin responder: 2 sesiones no avisa, 3 avisan UNA vez (la 4.ª no repite), una respuesta corta la racha; SIN_CONTRASTE/NO_SINCRONIZADO no frenan el ratio; el GC se etiqueta «informativo (retraso ~10 min)»")

# 7) integridad.json lleva la tarjeta y la web la pinta; la etapa figura en el cierre
res = IG._resumen_spot(T_RACHA)
assert res["racha_dudoso"] == 3 and res["ultimo"]["estado"] == "DUDOSO" and len(res["historial"]) == 3 and "gold-api" in res["ultimo"]["texto_fuentes"], res
sys.path.insert(0, HERE)
import vigilar_cierre as V  # noqa: E402
ESP = V.etapas_cierre()
assert "spot_oro" in ESP and ESP.index("spot_oro") < ESP.index("gamma_oro"), ESP
print(f"7) OK integridad.spot_oro (racha {res['racha_dudoso']}) · el vigilante del cierre exige la etapa spot_oro ({len(ESP)} etapas)")

# 8) etapa spot_oro completa: cierre escribe, no-cierre no escribe; sin spot lanza (el vigilante la verá como fallo)
T = raiz()
E = SO.etapa(escribir_cierre=False, hoy="2026-10-23", stamp="s", raiz=T, fuentes_=F())
assert E["decision"]["estado"] == "OK" and not csv_(T, "xau_spot_contraste.csv"), "fuera del cierre no se registra"
E = SO.etapa(escribir_cierre=True, hoy="2026-10-23", stamp="s", raiz=T, fuentes_=F())
assert E["registra"] is True and len(csv_(T, "xau_spot_contraste.csv")) == 1 and E["resumen"]["sesiones_registradas"] == 1
try:
    SO.etapa(escribir_cierre=True, hoy="2026-10-24", stamp="s", raiz=raiz(), fuentes_=F(principal=None, gc=None, swiss=None))
    raise SystemExit("debía fallar")
except RuntimeError as e:
    assert "sin spot" in str(e)
print("8) OK etapa: cierre registra, fuera del cierre no; sin ninguna fuente → error (fallo visible en el vigilante)")

# 9) Fase 20 · el spot es el de la hora del cierre del GLD (16:00 America/New_York): 20:00 UTC antes del 1-nov y 21:00 UTC después; ±5 min; el futuro sigue abierto
assert SO.cierre_gld_utc("2026-10-30") == dt.datetime(2026, 10, 30, 20, 0, tzinfo=UTC), SO.cierre_gld_utc("2026-10-30")
assert SO.cierre_gld_utc("2026-10-23") == dt.datetime(2026, 10, 23, 20, 0, tzinfo=UTC) and SO.cierre_gld_utc("2026-11-02") == dt.datetime(2026, 11, 2, 21, 0, tzinfo=UTC)
assert SO.cierre_gld_utc("2026-11-27") == dt.datetime(2026, 11, 27, 18, 0, tzinfo=UTC), "cierre anticipado de la NYSE (13:00 ET)"
assert SO.cierre_gld_utc("2026-03-06") == dt.datetime(2026, 3, 6, 21, 0, tzinfo=UTC) and SO.cierre_gld_utc("2026-03-10") == dt.datetime(2026, 3, 10, 20, 0, tzinfo=UTC), "el cambio de marzo también"
print("9a) OK hora del cierre del GLD con America/New_York: 20:00 UTC hasta el 31-oct, 21:00 UTC desde el 2-nov (cambio del 1-nov), 18:00 UTC el 27-nov (cierre anticipado); también marzo")


def FF(hora, principal=4030.0, swiss=4031.0, gc=4044.5, hora_swiss=None, hora_gc=None):
    h = lambda m: hora if m is None else m  # noqa: E731
    return {"xau": lambda: (principal, hora, "gold-api"), "swiss": lambda: (swiss, h(hora_swiss), "Swissquote"), "gc": lambda t: (gc, h(hora_gc)), "gld_cierre": lambda d: 379.69}


def U(s):
    return dt.datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=UTC)


# 9b) captura dentro de la ventana: verano (20:00 UTC) e invierno (21:00 UTC); fuera de ella no hace nada; fin de semana tampoco
T = raiz()
assert SO.capturar(T, U("2026-10-30 19:40"), FF("2026-10-30 19:40")) == "FUERA_DE_VENTANA" and not csv_(T, "xau_spot_contraste.csv")
assert SO.capturar(T, U("2026-10-30 20:07"), FF("2026-10-30 20:07")) == "FUERA_DE_VENTANA"
assert SO.capturar(T, U("2026-10-31 20:00"), FF("2026-10-31 20:00")) == "FIN_DE_SEMANA"
r = SO.capturar(T, U("2026-10-30 19:56"), FF("2026-10-30 19:56"), "s")
f = csv_(T, "xau_spot_contraste.csv")
assert r == "REGISTRADA OK" and len(f) == 1 and f[0]["fecha"] == "2026-10-30" and f[0]["nota"].startswith("VENTANA_GLD") and "20:00 UTC" in f[0]["nota"] and f[0]["estado"] == "OK" and f[0]["swiss_sinc"] == "SI", f
assert SO.capturar(T, U("2026-10-30 20:03"), FF("2026-10-30 20:03", principal=3000.0)) == "YA_REGISTRADA" and len(csv_(T, "xau_spot_contraste.csv")) == 1, "la primera captura válida manda"
assert SO.capturar(T, U("2026-11-02 20:00"), FF("2026-11-02 20:00")) == "FUERA_DE_VENTANA", "tras el 1-nov las 20:00 UTC ya no son el cierre del GLD"
assert SO.capturar(T, U("2026-11-02 21:03"), FF("2026-11-02 21:03"), "s") == "REGISTRADA OK" and csv_(T, "xau_spot_contraste.csv")[1]["fecha"] == "2026-11-02"
assert SO.capturar(T, U("2026-11-03 21:00"), FF("2026-11-03 20:20")) == "SIN_PRINCIPAL_EN_VENTANA" and len(csv_(T, "xau_spot_contraste.csv")) == 2, "si la hora del spot no está en la ventana no se registra"
print("9b) OK captura: 19:56 UTC (30-oct, verano) y 21:03 UTC (2-nov, invierno) se registran con nota VENTANA_GLD y estado OK (Swissquote de la misma hora); 19:40, 20:07, sábado y 20:00 UTC tras el cambio de hora no; la primera captura manda; spot de otra hora no se registra")

# 9c) sin captura en la ventana: el cierre (21:30 UTC) reconstruye el spot de esa hora con el GC=F de entonces menos la base anterior; y el ratio usa ESE spot
for sesion, hora_c in (("2026-10-30", "2026-10-30 20:00"), ("2026-11-02", "2026-11-02 21:00")):
    T = raiz()
    with open(os.path.join(T, "data", "xau_gc_base.csv"), "a", encoding="utf-8", newline="") as fh:      # base de la sesión anterior dentro de los 5 días
        csv.writer(fh).writerow(["2026-10-30" if sesion == "2026-11-02" else "2026-10-29", 4000.0, 4014.5, BASE_ANTERIOR, "x", "GC=F", "x"])
    gc_cierre = lambda t, hc=hora_c: (4044.5, hc)  # noqa: E731
    f2 = {"xau": lambda: (4100.0, sesion + " 21:31", "gold-api"), "swiss": lambda: (4101.0, sesion + " 21:31", "Swissquote"), "gc": gc_cierre, "gld_cierre": lambda d: 379.69}
    fr = GO.anotar_ratio(T, sesion, f2, "t", ventana=True)
    f = csv_(T, "xau_spot_contraste.csv")[0]
    esperado = round(4044.5 - BASE_ANTERIOR, 2)
    assert f["estado"] == "GC_IMPLICITO" and f["nota"].startswith("FUERA_DE_VENTANA") and float(f["spot_usado"]) == esperado and f["hora_utc"] == hora_c and f["spot_principal"] == "", f
    assert fr and fr["xau_spot"] == esperado and fr["xau_hora_utc"] == hora_c and fr["ratio"] == round(esperado / 379.69, 5), fr
    assert 4100.0 != fr["xau_spot"], "el spot de las 21:31 UTC no se usa para el ratio"
print("9c) OK sin captura en la ventana: spot = GC=F de las 20:00 UTC (30-oct) / 21:00 UTC (2-nov) − base anterior (GC_IMPLICITO, FUERA_DE_VENTANA) y el ratio usa ese spot, no el de las 21:31")
T = raiz()
f3 = {"xau": lambda: (4100.0, "2026-10-30 21:31", "gold-api"), "swiss": lambda: (4101.0, "2026-10-30 21:31", "Swissquote"), "gc": None, "gld_cierre": lambda d: 379.69}
n_r = len(csv_(T, "xau_gld_ratio.csv"))
assert GO.anotar_ratio(T, "2026-10-30", f3, "t", ventana=True) is None and len(csv_(T, "xau_gld_ratio.csv")) == n_r
g = csv_(T, "xau_spot_contraste.csv")[0]
assert g["ratio_fuente"] == "ANTERIOR" and g["nota"].startswith("FUERA_DE_VENTANA"), g
print("9d) OK sin captura y sin GC=F para reconstruir: el ratio NO se actualiza (ANTERIOR, nota FUERA_DE_VENTANA); nunca se usa el spot de otra hora")

# 9e) corrección hacia atrás: solo se AÑADEN filas REVISADA (la cabecera gana «estado» al final); las lecturas usan la última fila; idempotente; antes y después del 1-nov
sys.path.insert(0, HERE)
import revisar_ratio_cierre_gld as RV  # noqa: E402
T = tempfile.mkdtemp(prefix="spot_")
os.makedirs(os.path.join(T, "data"))
with open(os.path.join(T, "data", "xau_gld_ratio.csv"), "w", encoding="utf-8", newline="") as fh:
    w_ = csv.writer(fh)
    w_.writerow(GO.CAMPOS_RATIO)
    w_.writerow(["2026-10-29", 380.0, 4100.0, 10.78947, "2026-10-29 21:31", "gold-api.com (XAU/USD al contado)", "x"])
    w_.writerow(["2026-11-03", 370.0, 4070.0, 11.0, "2026-11-03 21:31", "gold-api.com (XAU/USD al contado)", "x"])
    w_.writerow(["2026-10-19", 379.69, 4140.8, 10.90574, "2026-10-19 21:00", "PROVISIONAL: proxy", "x"])
with open(os.path.join(T, "data", "xau_gc_base.csv"), "w", encoding="utf-8", newline="") as fh:
    w_ = csv.writer(fh)
    w_.writerow(GO.CAMPOS_BASE)
    w_.writerow(["2026-10-29", 4100.0, 4114.0, 14.0, "2026-10-29 20:59", "GC=F", "x"])
    w_.writerow(["2026-11-03", 4070.0, 4082.0, 12.0, "2026-11-03 20:59", "GC=F", "x"])
barras = {}
def gc_hist(h):  # noqa: E306
    barras.setdefault("pedidas", []).append(h)
    return {"2026-10-29 20:00": (4090.0, "2026-10-29 20:00"), "2026-11-03 21:00": (4075.0, "2026-11-03 21:00")}[h]
antes = open(os.path.join(T, "data", "xau_gld_ratio.csv"), "rb").read()
sim = RV.revisar(T, False, gc_hist)
assert open(os.path.join(T, "data", "xau_gld_ratio.csv"), "rb").read() == antes, "la simulación no escribe"
assert barras["pedidas"] == ["2026-10-29 20:00", "2026-11-03 21:00"], barras
res = RV.revisar(T, True, gc_hist, "t")
d_ = {x["fecha"]: x for x in res}
assert d_["2026-10-29"]["estado"] == "REVISADA" and d_["2026-11-03"]["estado"] == "REVISADA" and d_["2026-10-19"]["estado"] == "OMITIDA", res
despues = open(os.path.join(T, "data", "xau_gld_ratio.csv"), "rb").read()
cab, _, resto = despues.partition(b"\n")
assert cab.decode().strip().endswith(",estado") and resto.startswith(antes.partition(b"\n")[2]), "las filas antiguas no se tocan; solo se añade al final y a la cabecera"
filas_r = csv_(T, "xau_gld_ratio.csv")
assert len(filas_r) == 5 and [x["estado"] for x in filas_r if x["estado"]] == ["REVISADA", "REVISADA"]
vig = {x["fecha"]: x for x in GO.leer_ratios(T)}
assert vig["2026-10-29"]["ratio"] == str(round((4090.0 - 14.0) / 380.0, 5)) and vig["2026-11-03"]["ratio"] == str(round((4075.0 - 12.0) / 370.0, 5)) and GO.ratio_para(T, "2026-11-03")["valor"] == float(vig["2026-11-03"]["ratio"])
assert "antes 10.78947" in vig["2026-10-29"]["fuente_xau"] and vig["2026-10-29"]["xau_hora_utc"] == "2026-10-29 20:00"
res2 = RV.revisar(T, True, gc_hist, "t")
assert len(csv_(T, "xau_gld_ratio.csv")) == 5 and all(x["estado"] in ("OMITIDA",) for x in res2), res2
assert GO.anotar_ratio(T, "2026-11-04", {"gld_cierre": lambda d: 372.0, "xau": lambda: (4080.0, "2026-11-04 21:01", "g"), "swiss": lambda: (4081.0, "2026-11-04 21:01", "s"), "gc": lambda h: (4093.0, "2026-11-04 21:00")}, "t", ventana=False) is not None
nuevas = csv_(T, "xau_gld_ratio.csv")
assert len(nuevas) == 6 and nuevas[-1]["fecha"] == "2026-11-04" and nuevas[-1]["estado"] == "", nuevas[-1]
print("9e) OK corrección hacia atrás: usa GC=F de las 20:00 UTC (29-oct) y de las 21:00 UTC (3-nov); solo AÑADE filas REVISADA (cabecera +estado al final, filas antiguas intactas); lo provisional no se toca; las lecturas usan la última fila; repetirla no añade nada; las filas nuevas siguen con la cabecera ampliada")

for d in os.listdir(tempfile.gettempdir()):
    if d.startswith("spot_"):
        shutil.rmtree(os.path.join(tempfile.gettempdir(), d), ignore_errors=True)
print("\nFASE 19 · TODAS LAS PRUEBAS OK")
