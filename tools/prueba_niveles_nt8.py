#!/usr/bin/env python3
"""Pruebas de la Fase 21 (niveles automáticos en NinjaTrader 8 + aviso de caducidad en TradingView). Sin red y sin Telegram real.
Uso: PYTHONUTF8=1 python tools/prueba_niveles_nt8.py

1) engine/niveles_nt8.py: el JSON con sesión de hoy, caducada y spot dudoso; micros; fuentes caídas; sin datos personales.
2) build: la etapa está en el cierre y en el diario, tras gamma_us30.
3) NexoraNiveles.cs: se compila con csc (C# 5) y se ejecuta de verdad la lógica (NexoraNivelesLogica) con un arnés: calendario de sesiones contra un cálculo independiente en Python,
   caducidad, spot dudoso y selección de niveles (Cercanos, Todos, SoloMasCercano). Sin csc en el equipo, esta parte se omite y se dice.
4) NexoraOro.pine: la lógica de caducidad se porta a Python (misma estructura que el Pine) y se contrasta con un cálculo independiente en todo un año; además, tabla de escenarios.
   (El Pine se compila con tools/validar_pine_tradingview.py; el aspecto en el gráfico solo se puede ver en TradingView.)"""
import copy
import datetime as dt
import glob
import json
import os
import subprocess
import sys
import tempfile
import zoneinfo

HERE = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(RAIZ, "engine"))
sys.path.insert(0, HERE)
import niveles_nt8 as N  # noqa: E402
import reaccion  # noqa: E402

UTC, NY, MAD = dt.timezone.utc, zoneinfo.ZoneInfo("America/New_York"), zoneinfo.ZoneInfo("Europe/Madrid")
FESTIVOS = reaccion.FESTIVOS_NY
TMP = tempfile.mkdtemp(prefix="nt8_")


def u(s):
    return dt.datetime.fromisoformat(s).replace(tzinfo=UTC)


# ---------------------------------------------------------------- fuentes de ejemplo con la forma real de gamma.json, gamma_us30.json y gamma_oro.json
def nivel(fut):
    return {"idx": fut - 10, "musd": 1.0, "fut": fut}


def bloque(sesion, regimen, flip, cw, pw, mg, tipo, em, base_aprox=False):
    return {"sesion": sesion, "regimen": regimen, "flip": nivel(flip), "call_wall": nivel(cw), "put_wall": nivel(pw), "max_gamma": dict(nivel(mg), tipo=tipo, neto_musd=-3.0),
            "em": {"puntos": em, "vol_simbolo": "VIX"}, "base": {"base": 37.3, "aproximada": base_aprox}, "perfil": [1, 2, 3], "top_calls": [4]}


def fuentes(sesion="2026-10-23", spot="verificado"):
    oro = bloque(sesion, "NEGATIVA", 4175.6, 4156.0, 3774.4, 3774.4, "acelera", 61.1)
    oro["spot_contraste"] = {"estado": "OK", "verificado": spot == "verificado", "dudoso": spot == "dudoso"}
    oro["generado_utc"] = "2026-10-24 09:39 UTC"
    return {"gamma": {"generado_utc": "2026-10-24 09:39 UTC", "indices": {"ES": bloque(sesion, "NEGATIVA", 7782.1, 7837.3, 7637.3, 7737.3, "acelera", 93.9),
                                                                           "NQ": bloque(sesion, "NEGATIVA", 30106.2, 29865.0, 28915.0, 29392.0, "pin", 519.2, base_aprox=True)}},
            "gamma_us30": dict(bloque(sesion, "POSITIVA", 52240.7, 54263.8, 51760.0, 51760.0, "acelera", 567.4), generado_utc="2026-10-24 09:39 UTC"),
            "gamma_oro": oro}


# ---------------------------------------------------------------- 1) el JSON
J = N.construir(fuentes())
assert set(J["instrumentos"]) == {"GC", "MGC", "ES", "MES", "NQ", "MNQ", "YM", "MYM"}, J["instrumentos"].keys()
CAMPOS = {"sesion", "regimen", "flip", "call_wall", "put_wall", "max_gamma", "max_gamma_tipo", "em", "spot_estado", "generado_utc"}
for k, v in J["instrumentos"].items():
    assert CAMPOS <= set(v) <= CAMPOS | {"alias_de"}, (k, set(v) ^ CAMPOS)
    assert v["spot_estado"] in N.ESTADOS_SPOT and v["max_gamma_tipo"] in ("pin", "acelera")
for micro, base in (("MGC", "GC"), ("MES", "ES"), ("MNQ", "NQ"), ("MYM", "YM")):
    a, b = dict(J["instrumentos"][micro]), J["instrumentos"][base]
    assert a.pop("alias_de") == base and a == b, micro
es, nq, ym, gc = (J["instrumentos"][k] for k in ("ES", "NQ", "YM", "GC"))
assert (es["flip"], es["call_wall"], es["put_wall"], es["max_gamma"], es["max_gamma_tipo"], es["em"], es["sesion"], es["regimen"]) == (7782.1, 7837.3, 7637.3, 7737.3, "acelera", 93.9, "2026-10-23", "NEGATIVA")
assert nq["max_gamma_tipo"] == "pin" and ym["regimen"] == "POSITIVA" and gc["flip"] == 4175.6
assert es["spot_estado"] == "verificado" and nq["spot_estado"] == "no_verificado" and ym["spot_estado"] == "verificado", "índices: base medida en el mismo minuto = verificado; aproximada = no verificado"
assert gc["spot_estado"] == "verificado"
assert N.construir(fuentes(spot="dudoso"))["instrumentos"]["GC"]["spot_estado"] == "dudoso" and N.construir(fuentes(spot="dudoso"))["instrumentos"]["MGC"]["spot_estado"] == "dudoso"
f = fuentes(spot="no")
assert N.construir(f)["instrumentos"]["GC"]["spot_estado"] == "no_verificado"
f["gamma_oro"].pop("spot_contraste")
assert N.construir(f)["instrumentos"]["GC"]["spot_estado"] == "no_verificado", "sin contraste → no verificado"
texto = json.dumps(J, ensure_ascii=False).lower()
for prohibido in ("token", "telegram", "chat_id", "password", "api_key", "@", "http://", "https://"):
    assert prohibido not in texto, prohibido
assert "perfil" not in texto and "top_calls" not in texto, "solo los niveles, no el perfil completo"
# una fuente caída: el instrumento falta con su motivo (no se inventa); todas caídas: la etapa falla y el build conserva la última copia
f = fuentes()
f["gamma_us30"] = None
Jp = N.construir(f)
assert "YM" not in Jp["instrumentos"] and "MYM" not in Jp["instrumentos"] and "YM" in Jp["errores"] and "ES" in Jp["instrumentos"]
f = fuentes()
f["gamma"]["indices"]["NQ"]["flip"] = None
assert "NQ" not in N.construir(f)["instrumentos"], "sin Gamma Flip no hay régimen utilizable"
try:
    N.construir({})
    raise AssertionError("debía fallar sin ninguna fuente")
except RuntimeError:
    pass
print("1) OK JSON: GC/ES/NQ/YM + micros, campos y spot_estado (verificado/dudoso/no_verificado), sin datos personales, fuentes caídas sin inventar")

# datos reales publicados (si existen): misma forma
real = os.path.join(RAIZ, "site", "data", "gamma.json")
if os.path.exists(real):
    ley = lambda n: json.load(open(os.path.join(RAIZ, "site", "data", n), encoding="utf-8"))  # noqa: E731
    JR = N.etapa(ley)
    assert {"GC", "ES", "NQ", "YM"} <= set(JR["instrumentos"]), JR["errores"]
    print("   (datos reales de site/data: " + ", ".join(f"{k} {v['sesion']}" for k, v in JR["instrumentos"].items() if "alias_de" not in v) + ")")

# ---------------------------------------------------------------- 2) build
import build  # noqa: E402
import vigilar_cierre as VC  # noqa: E402

for lista in (build.ORDEN, build.MODOS["cierre"], build.MODOS["diario"]):
    assert lista.index("niveles_nt8") == lista.index("gamma_us30") + 1, lista
assert "niveles_nt8" in build.ETAPAS and "niveles_nt8" in VC.etapas_cierre() and "niveles_nt8" not in build.MODOS["horario"]
print("2) OK build: la etapa niveles_nt8 va tras gamma_us30 en el cierre y en el diario, y el vigilante del cierre la exige")


# ---------------------------------------------------------------- 3) NexoraNiveles.cs
def csc():
    for p in glob.glob(r"C:\Windows\Microsoft.NET\Framework64\v4.*\csc.exe") + glob.glob(r"C:\Windows\Microsoft.NET\Framework\v4.*\csc.exe"):
        return p
    return None


def ultima_sesion_ref(t, gracia):
    """Cálculo INDEPENDIENTE del de C#: zoneinfo + festivos de reaccion.py. Último día de sesión cuyo cierre (16:00 ET) + gracia ya pasó."""
    ny = t.astimezone(NY)
    d = ny.date()
    if ny.replace(tzinfo=None) < dt.datetime(d.year, d.month, d.day) + dt.timedelta(hours=16 + gracia):
        d -= dt.timedelta(days=1)
    while d.weekday() >= 5 or d in FESTIVOS:
        d -= dt.timedelta(days=1)
    return d


def ejecutar(exe, ordenes):
    r = subprocess.run([exe], input="\n".join(ordenes) + "\n", capture_output=True, text=True, encoding="utf-8", timeout=300)
    assert r.returncode == 0, r.stderr
    sal = r.stdout.splitlines()
    assert len(sal) == len(ordenes), (len(sal), len(ordenes), sal[:3])
    for o, s in zip(ordenes, sal):
        assert not s.startswith("ERROR"), (o, s)
    return sal


def escribir_json(nombre, **kw):
    ruta = os.path.join(TMP, nombre)
    json.dump(dict(N.construir(fuentes(**kw)), generado_utc="2026-10-24 09:39 UTC"), open(ruta, "w", encoding="utf-8"), ensure_ascii=False)
    return ruta


exe_csc = csc()
if not exe_csc:
    print("3) OMITIDO: no hay compilador csc.exe de .NET Framework 4 en este equipo (la lógica C# no se ha ejecutado)")
else:
    exe = os.path.join(TMP, "PruebaNexoraNiveles.exe")
    fw = os.path.dirname(exe_csc)
    refs = ["System.dll", "System.Core.dll", "System.ComponentModel.DataAnnotations.dll", os.path.join(fw, "WPF", "PresentationCore.dll"), os.path.join(fw, "WPF", "WindowsBase.dll")]
    cmd = [exe_csc, "/nologo", "/target:exe", "/warn:4", f"/out:{exe}"] + [f"/r:{r}" for r in refs] + [os.path.join(RAIZ, "plataformas", "ninjatrader", "NexoraNiveles.cs"),
                                                                                                    os.path.join(HERE, "stubs_ninjatrader.cs"), os.path.join(HERE, "nt8_prueba", "PruebaNexoraNiveles.cs")]
    c = subprocess.run(cmd, capture_output=True, text=True, encoding="cp850", errors="replace")
    assert c.returncode == 0, c.stdout + c.stderr
    assert "warning" not in (c.stdout + c.stderr).lower(), c.stdout + c.stderr

    # 3a) calendario: festivos (todas las fechas de 2026-2027 contra reaccion.FESTIVOS_NY, y fechas conocidas de otros años)
    dias = [dt.date(2026, 1, 1) + dt.timedelta(days=i) for i in range(730)]
    sal = ejecutar(exe, [f"FESTIVO;{d.isoformat()}" for d in dias])
    mal = [d for d, s in zip(dias, sal) if (s == "1") != (d in FESTIVOS)]
    assert not mal, ("festivos distintos de reaccion.FESTIVOS_NY", mal[:5])
    conocidos = {"2028-01-17": 1, "2028-02-21": 1, "2028-04-14": 1, "2028-05-29": 1, "2028-06-19": 1, "2028-07-04": 1, "2028-09-04": 1, "2028-11-23": 1, "2028-12-25": 1,
                 "2027-12-31": 0, "2028-01-03": 0, "2029-01-01": 1, "2030-04-19": 1, "2025-04-18": 1, "2026-06-18": 0}
    sal = ejecutar(exe, [f"FESTIVO;{k}" for k in conocidos])
    assert [int(s) for s in sal] == list(conocidos.values()), dict(zip(conocidos, sal))

    # 3b) hora de Nueva York y última sesión: cada 30 min de 2026-10 a 2027-12, con 3 gracias distintas
    t, ts = u("2026-10-01T00:00"), []
    while t < u("2027-12-31T00:00"):
        ts.append(t)
        t += dt.timedelta(minutes=30)
    sal = ejecutar(exe, [f"NY;{x:%Y-%m-%dT%H:%M}" for x in ts])
    mal = [x for x, s in zip(ts, sal) if s != x.astimezone(NY).strftime("%Y-%m-%dT%H:%M")]
    assert not mal, ("hora de Nueva York distinta de zoneinfo", mal[:3])
    for g in (0, 5, 7):
        sal = ejecutar(exe, [f"ULTIMA;{x:%Y-%m-%dT%H:%M};{g}" for x in ts])
        mal = [(x, s, ultima_sesion_ref(x, g)) for x, s in zip(ts, sal) if s != ultima_sesion_ref(x, g).isoformat()]
        assert not mal, ("última sesión distinta del cálculo independiente", g, mal[:3])
    print(f"3a) OK C# (csc C# 5, sin advertencias): festivos NYSE y {len(ts)} instantes × 3 gracias de «última sesión» idénticos al cálculo independiente en Python (zoneinfo + festivos)")

    # 3c) claves de instrumento
    sal = ejecutar(exe, ["CLAVE;GC 12-26", "CLAVE;mgc 12-26", "CLAVE;ES 12-26", "CLAVE;MNQ", "CLAVE;YM 12-26", "CLAVE;MYM", "CLAVE;CL 12-26", "CLAVE;EURUSD", "CLAVE;"])
    assert sal == ["GC", "MGC", "ES", "MNQ", "YM", "MYM", "-", "-", "-"], sal

    # 3d) los tres casos del encargo: sesión de hoy, caducada y spot dudoso (con el calendario real: sábado, lunes, festivo)
    hoy = escribir_json("hoy.json")                     # sesión 23-10, spot verificado
    duda = escribir_json("dudoso.json", spot="dudoso")
    viejo = escribir_json("viejo.json", sesion="2026-10-20")
    sin = os.path.join(TMP, "sinfecha.json")
    J0 = copy.deepcopy(J)
    J0["instrumentos"]["ES"]["sesion"] = None
    json.dump(J0, open(sin, "w", encoding="utf-8"))
    casos = [  # (archivo, clave, ahora UTC, esperado)
        (hoy, "GC", "2026-10-24T12:00", "CAD=0;FECHA=23-10;SPOT=0"),                 # sábado: vale la sesión del viernes
        (hoy, "MGC", "2026-10-25T23:00", "CAD=0;FECHA=23-10;SPOT=0"),                # domingo noche
        (hoy, "ES", "2026-10-26T15:00", "CAD=0;FECHA=23-10;SPOT=0"),                 # lunes en sesión: la última sesión cerrada sigue siendo el viernes
        (hoy, "NQ", "2026-10-27T00:30", "CAD=0;FECHA=23-10;SPOT=0"),                 # lunes 20:30 ET: aún dentro de la gracia de 5 h
        (hoy, "YM", "2026-10-27T02:30", "CAD=1;FECHA=23-10;SPOT=0"),                 # lunes 22:30 ET: ya debería estar la sesión del lunes → CADUCADO 23-10
        (hoy, "ES", "2026-10-28T14:00", "CAD=1;FECHA=23-10;SPOT=0"),
        (viejo, "GC", "2026-10-26T15:00", "CAD=1;FECHA=20-10;SPOT=0"),               # sesión caducada
        (viejo, "MES", "2026-10-24T12:00", "CAD=1;FECHA=20-10;SPOT=0"),
        (duda, "GC", "2026-10-24T12:00", "CAD=0;FECHA=23-10;SPOT=1"),                # spot dudoso, sesión al día
        (duda, "MGC", "2026-10-24T12:00", "CAD=0;FECHA=23-10;SPOT=1"),
        (duda, "ES", "2026-10-24T12:00", "CAD=0;FECHA=23-10;SPOT=0"),                # el spot dudoso es del oro, no de ES
        (escribir_json("dudoso_viejo.json", sesion="2026-10-20", spot="dudoso"), "GC", "2026-10-26T15:00", "CAD=1;FECHA=20-10;SPOT=1"),
        (sin, "ES", "2026-10-24T12:00", "CAD=1;FECHA=sin fecha;SPOT=0"),             # sin fecha de sesión: se trata como caducado
        (escribir_json("fest.json", sesion="2026-11-25"), "GC", "2026-11-26T15:00", "CAD=0;FECHA=25-11;SPOT=0"),    # Acción de Gracias: la última sesión es el miércoles
        (escribir_json("fest.json", sesion="2026-11-25"), "GC", "2026-11-27T15:00", "CAD=0;FECHA=25-11;SPOT=0"),    # viernes 27 en sesión: el jueves fue festivo
        (escribir_json("fest.json", sesion="2026-11-25"), "GC", "2026-11-30T15:00", "CAD=1;FECHA=25-11;SPOT=0"),    # lunes: ya debía estar la del viernes 27 (cierre anticipado, sigue siendo sesión)
        (escribir_json("fest2.json", sesion="2026-11-27"), "GC", "2026-11-30T15:00", "CAD=0;FECHA=27-11;SPOT=0"),
        (escribir_json("dst.json", sesion="2026-10-30"), "ES", "2026-11-02T04:00", "CAD=0;FECHA=30-10;SPOT=0"),    # tras el cambio de hora de EE. UU. (1-nov): domingo noche, sesión = viernes
    ]
    ords = [f"EVALUAR;{a};{k};{t};5" for a, k, t, _ in casos]
    sal = ejecutar(exe, ords)
    for (a, k, t, esp), s in zip(casos, sal):
        assert s == esp, (os.path.basename(a), k, t, s, esp)
    print(f"3b) OK C#: caducidad con calendario real ({len(casos)} escenarios: sesión de hoy, fin de semana, festivo, caducada, spot dudoso, sin fecha, cambio de hora)")

    # 3e) qué niveles se dibujan (ES: flip 7782.1, CW 7837.3, PW 7637.3, MG 7737.3 acelera, EM 93.9; GC: PW = MG = 3774.4)
    def S(*a):
        return ejecutar(exe, ["SELECCIONAR;" + ";".join(str(x) for x in a)])[0]

    assert S(hoy, "ES", 7700, "Cercanos", 3, 1.0) == "MG 7737 · acelera@7737.3@ambar|PW 7637@7637.3@gris|FLIP 7782@7782.1@ambar"      # CW a 137 pt > 1 EM (93,9): fuera
    assert S(hoy, "ES", 7700, "Cercanos", 2, 1.0) == "MG 7737 · acelera@7737.3@ambar|PW 7637@7637.3@gris"
    assert S(hoy, "ES", 7700, "Cercanos", 3, 2.0).count("|") == 2, "con 2 EM entran los 4 niveles pero el tope es 3"
    todos = S(hoy, "ES", 7700, "Todos", 3, 1.0)
    assert todos.count("@ambar") + todos.count("@gris") == 4, todos
    assert S(hoy, "ES", 7700, "SoloMasCercano", 3, 1.0) == "MG 7737 · acelera@7737.3@ambar|PW 7637@7637.3@gris"                     # el más cercano arriba y abajo
    assert S(hoy, "ES", 7600, "SoloMasCercano", 3, 1.0) == "PW 7637@7637.3@gris", "precio bajo todos los niveles: solo el más cercano por encima"
    assert S(hoy, "ES", 7900, "SoloMasCercano", 3, 1.0) == "CW 7837@7837.3@gris", "precio sobre todos los niveles: solo el más cercano por debajo"
    assert S(hoy, "ES", 7700, "Cercanos", 3, 1.0) == S(hoy, "MES", 7700, "Cercanos", 3, 1.0), "los micros usan los mismos niveles"
    assert S(hoy, "ES", 9000, "Cercanos", 3, 1.0) == "", "ningún nivel a menos de 1 EM: nada que dibujar"
    assert S(hoy, "ES", "NaN", "Cercanos", 3, 1.0).count("|") == 3, "sin precio se muestran todos"
    assert S(hoy, "GC", 3780, "Cercanos", 3, 1.0) == "PW/MG 3774 · acelera@3774.4@ambar", "niveles en el mismo precio: una línea con las dos etiquetas"
    assert S(hoy, "GC", 4100, "Todos", 3, 1.0) == "FLIP 4176@4175.6@ambar|CW 4156@4156.0@gris|PW/MG 3774 · acelera@3774.4@ambar"
    assert S(hoy, "NQ", 29000, "Todos", 3, 1.0).split("|")[-1] == "MG 29392 · pin@29392.0@ambar"
    print("3c) OK C#: modos Cercanos (±1 EM, máx. 3), Todos y SoloMasCercano; etiquetas «CW 4144 · pin»; niveles coincidentes fusionados; ámbar/gris")


# ---------------------------------------------------------------- 4) Pine: la lógica de NexoraOro.pine portada 1:1 a Python y contrastada con un cálculo independiente
def f_texto(seg, clave):
    r = ""
    for p in seg.split(";"):
        ultimo = p.strip().split(" ")[-1]
        kv = ultimo.split("=")
        if len(kv) == 2 and kv[0].strip() == clave:
            r = kv[1].strip()
    return r


def sesiones_spy(desde, hasta):
    """Días de sesión (lunes-viernes salvo festivos) = las barras diarias de AMEX:SPY, cada una abierta a las 09:30 ET."""
    d, out = desde, []
    while d <= hasta:
        if d.weekday() < 5 and d not in FESTIVOS:
            out.append(dt.datetime(d.year, d.month, d.day, 9, 30, tzinfo=NY))
        d += dt.timedelta(days=1)
    return out


BARRAS = sesiones_spy(dt.date(2026, 9, 1), dt.date(2028, 1, 31))


def ymd(t, zona):
    t = t.astimezone(zona)
    return t.year * 10000 + t.month * 100 + t.day


def pine_relevo(ahora):
    """f_relevo del Pine: del mediodía de hoy en Madrid, hacia atrás, el primer lunes-viernes cuyas 15:30 de Madrid ya pasaron."""
    h = ahora.astimezone(MAD)
    mediodia = dt.datetime(h.year, h.month, h.day, 12, 0, tzinfo=MAD)
    for k in range(7):
        d = (mediodia.astimezone(UTC) - dt.timedelta(milliseconds=k * 86400000)).astimezone(MAD)   # el Pine resta k × 86 400 000 ms y lee la fecha en Madrid
        cand = dt.datetime(d.year, d.month, d.day, 15, 30, tzinfo=MAD)
        if d.weekday() < 5 and cand <= ahora:
            return cand
    return None


def pine_esperada(ahora, con_calendario=True):
    relevo = pine_relevo(ahora)
    ymdR = ymd(relevo, NY)
    abiertas = [b for b in BARRAS if b <= ahora]                    # calT0 = apertura de la última barra diaria de SPY existente; calT1 y calT2 = las dos anteriores
    if con_calendario and len(abiertas) >= 3:
        y0, y1, y2 = ymd(abiertas[-1], NY), ymd(abiertas[-2], NY), ymd(abiertas[-3], NY)
        return y0 if y0 < ymdR else y1 if y1 < ymdR else y2
    d = relevo.astimezone(NY)                                       # respaldo: lunes-viernes anterior
    mediodia = dt.datetime(d.year, d.month, d.day, 12, 0, tzinfo=NY)
    for k in range(1, 6):
        x = (mediodia.astimezone(UTC) - dt.timedelta(milliseconds=k * 86400000)).astimezone(NY)
        if x.weekday() < 5:
            return ymd(x, NY)


def esperada_independiente(ahora):
    """Definición en palabras: la última sesión cuyo cierre (16:00 ET) es anterior al último relevo (lunes-viernes 15:30 Madrid ≤ ahora)."""
    d = ahora.astimezone(MAD).date()
    while True:
        cand = dt.datetime(d.year, d.month, d.day, 15, 30, tzinfo=MAD)
        if d.weekday() < 5 and cand <= ahora:
            break
        d -= dt.timedelta(days=1)
    relevo = cand
    s = relevo.astimezone(NY).date()
    while True:
        cierre = dt.datetime(s.year, s.month, s.day, 16, 0, tzinfo=NY)
        if s.weekday() < 5 and s not in FESTIVOS and cierre < relevo:
            return s.year * 10000 + s.month * 100 + s.day
        s -= dt.timedelta(days=1)


t, n, malos, sin_cal = u("2026-10-01T00:00"), 0, [], 0
while t < u("2027-10-01T00:00"):
    a, b, c = pine_esperada(t), pine_esperada(t, con_calendario=False), esperada_independiente(t)
    if a != c:
        malos.append((t, a, c))
    sin_cal += b != c            # el respaldo (sin festivos) solo puede fallar en días posteriores a un festivo
    n += 1
    t += dt.timedelta(minutes=20)
assert not malos, ("el Pine (con calendario SPY) no coincide con la definición", malos[:3])


def pine_estado(linea, ahora):
    """Lo que muestra NexoraOro.pine en el último compás: fila roja (con su texto), líneas de gamma en gris, fila ámbar «SPOT DUDOSO»."""
    seg = next((s.strip() for s in linea.split("|") if s.strip().split(" ")[0].upper() == "XAU"), "")
    rf = f_texto(seg, "rf")
    try:
        y, m, d = (int(x) for x in rf.split("-"))
        rf_ymd = y * 10000 + m * 100 + d
    except ValueError:
        rf_ymd = None
    caducada = bool(seg) and rf_ymd is not None and rf_ymd < pine_esperada(ahora)
    return {"fila_roja": f"NIVELES DEL {rf[8:10]}-{rf[5:7]} · CADUCADOS, pega la línea de hoy" if caducada else None,
            "lineas": "gris discontinuo" if caducada else "colores",
            "fila_ambar": f_texto(seg, "spot") == "dudoso"}


L = "XAU tesis=alcista;int=debil;flip=4162.5;cw=4142.9;pw=3761.3;em=61.1;maxg=3761.3;ratio=10.9023;rf={rf};cot=largo-bajo_p24;etf=-8.3;evento=no{extra}"
ROJA = "NIVELES DEL {} · CADUCADOS, pega la línea de hoy"
ESC = [  # (ahora UTC, rf de la línea pegada, extra, fila roja, líneas, ámbar)
    ("2026-10-23T13:10", "2026-10-22", "", None, "colores", False),                                  # viernes 15:10 Madrid: la línea de hoy aún es la del jueves (relevo 15:30 sin pasar)
    ("2026-10-24T12:00", "2026-10-22", "", None, "colores", False),                                  # sábado: vale la última línea recibida (la del viernes trae rf = jueves)
    ("2026-10-25T20:00", "2026-10-22", "", None, "colores", False),                                  # domingo
    ("2026-10-26T13:00", "2026-10-22", "", None, "colores", False),                                  # lunes 14:00 Madrid (CET): aún no hay relevo
    ("2026-10-26T14:45", "2026-10-22", "", ROJA.format("22-10"), "gris discontinuo", False),         # lunes 15:45 Madrid: ya llegó la línea de hoy (rf = viernes) y esta no se ha pegado
    ("2026-10-26T14:45", "2026-10-23", "", None, "colores", False),                                  # …y si se pegó, todo en orden
    ("2026-10-27T10:00", "2026-10-23", "", None, "colores", False),                                  # martes mañana: sigue valiendo la de rf = viernes
    ("2026-10-27T15:00", "2026-10-23", "", ROJA.format("23-10"), "gris discontinuo", False),         # martes 16:00 Madrid: toca rf = lunes
    ("2026-11-26T15:00", "2026-11-24", "", ROJA.format("24-11"), "gris discontinuo", False),         # Acción de Gracias: la línea de hoy es rf = miércoles 25
    ("2026-11-26T15:00", "2026-11-25", "", None, "colores", False),
    ("2026-11-27T16:00", "2026-11-25", "", None, "colores", False),                                  # viernes tras un festivo: el jueves no hubo sesión, sigue valiendo rf = miércoles
    ("2026-11-30T15:00", "2026-11-25", "", ROJA.format("25-11"), "gris discontinuo", False),         # lunes: la línea de hoy es rf = viernes 27
    ("2026-10-24T12:00", "2026-10-22", ";spot=dudoso", None, "colores", True),                       # spot dudoso con la línea al día: fila ámbar, nada rojo
    ("2026-10-26T14:45", "2026-10-22", ";spot=dudoso", ROJA.format("22-10"), "gris discontinuo", True),   # las dos a la vez
]
for ahora, rf, extra, roja, lineas, ambar in ESC:
    r = pine_estado(L.format(rf=rf, extra=extra), u(ahora))
    assert r == {"fila_roja": roja, "lineas": lineas, "fila_ambar": ambar}, (ahora, rf, extra, r)
assert pine_estado("", u("2026-10-24T12:00")) == {"fila_roja": None, "lineas": "colores", "fila_ambar": False}, "sin línea pegada no hay alarma"
assert pine_estado("ES flip=1;cw=2", u("2026-10-24T12:00"))["fila_roja"] is None, "una línea que no empieza por XAU no se evalúa"
assert pine_estado(L.format(rf="na", extra=""), u("2026-10-24T12:00"))["fila_roja"] is None, "rf = na (sin ratio): fecha desconocida, sin alarma"
fuente_pine = open(os.path.join(RAIZ, "plataformas", "tradingview", "NexoraOro.pine"), encoding="utf-8").read()
for clave in ("f_relevo", "f_previo_laborable", "AMEX:SPY", "CADUCADOS, pega la línea de hoy", "SPOT DUDOSO", "line.style_dashed", "Europe/Madrid", "15, 30"):
    assert clave in fuente_pine, clave


# ---------------------------------------------------------------- 5) NexoraNiveles.pine (ES/NQ): misma regla del relevo; la línea de Telegram trae rf= por índice
def pine_estado_gex(linea, ahora, raiz):
    """Lo que muestra NexoraNiveles.pine: el segmento es el del índice del gráfico (MES → ES, MNQ → NQ); rf = sesión de los niveles de ese índice."""
    indice = "ES" if raiz in ("ES", "MES") else "NQ" if raiz in ("NQ", "MNQ") else ""
    seg = next((s.strip() for s in linea.split("|") if indice and s.strip().split(" ")[0].upper() == indice), "")
    rf = f_texto(seg, "rf")
    try:
        y, m, d = (int(x) for x in rf.split("-"))
        rf_ymd = y * 10000 + m * 100 + d
    except ValueError:
        rf_ymd = None
    caducada = bool(seg) and rf_ymd is not None and rf_ymd < pine_esperada(ahora)
    return {"fila_roja": ROJA.format(f"{rf[8:10]}-{rf[5:7]}") if caducada else None, "lineas": "gris discontinuo" if caducada else "colores"}


sys.path.insert(0, os.path.join(RAIZ, "engine"))
import gamma_intradia as GI  # noqa: E402

LG = "ES flip=7804.0;cw=7843.6;pw=7693.6;em=97.0;maxg=7743.6;rf={es} | NQ flip=29920.4;cw=29892.0;pw=28592.0;em=502.1;maxg=29392.0;rf={nq}"
ESC2 = [  # (ahora UTC, rf ES, rf NQ, gráfico, fila roja esperada (dd-mm) o None)
    ("2026-10-24T12:00", "2026-10-22", "2026-10-22", "ES", None),                  # sábado: vale la última línea recibida
    ("2026-10-24T12:00", "2026-10-22", "2026-10-22", "MNQ", None),
    ("2026-10-26T14:45", "2026-10-22", "2026-10-22", "ES", "22-10"),               # lunes tras el relevo: toca rf = viernes
    ("2026-10-26T14:45", "2026-10-22", "2026-10-22", "MNQ", "22-10"),
    ("2026-10-26T14:45", "2026-10-23", "2026-10-23", "MES", None),                 # línea de hoy pegada
    ("2026-10-26T14:45", "2026-10-23", "2026-10-20", "ES", None),                  # cada gráfico mira SU segmento
    ("2026-10-26T14:45", "2026-10-23", "2026-10-20", "NQ", "20-10"),
    ("2026-11-27T16:00", "2026-11-25", "2026-11-25", "ES", None),                  # tras el festivo de Acción de Gracias
    ("2026-11-30T15:00", "2026-11-25", "2026-11-25", "ES", "25-11"),
]
for ahora, a, b, g, roja in ESC2:
    r = pine_estado_gex(LG.format(es=a, nq=b), u(ahora), g)
    assert r == {"fila_roja": ROJA.format(roja) if roja else None, "lineas": "gris discontinuo" if roja else "colores"}, (ahora, a, b, g, r)
assert pine_estado_gex("ES flip=7804.0;cw=1;pw=2;em=3;maxg=4 | NQ flip=1;cw=2;pw=3;em=4;maxg=5", u("2026-10-26T14:45"), "ES")["fila_roja"] is None, "línea antigua sin rf=: no se evalúa"
assert pine_estado_gex(LG.format(es="na", nq="na"), u("2026-10-26T14:45"), "ES")["fila_roja"] is None, "rf = na: sin alarma"
assert pine_estado_gex("", u("2026-10-26T14:45"), "ES")["fila_roja"] is None and pine_estado_gex(LG.format(es="2026-10-01", nq="2026-10-01"), u("2026-10-26T14:45"), "CL")["fila_roja"] is None
# la línea que genera NEXORA lleva rf= por índice, y la del Telegram y la de la web son la misma
lin = GI.linea_niveles({"indices": {"ES": {"sesion": "2026-10-23", "flip": {"fut": 7782.1}, "call_wall": {"fut": 7837.3}, "put_wall": {"fut": 7637.3}, "max_gamma": {"fut": 7737.3}, "em": {"puntos": 93.9}},
                                   "NQ": {"sesion": "2026-10-22", "flip": {"fut": 30106.2}, "call_wall": {"fut": 29865.0}, "put_wall": {"fut": 28915.0}, "max_gamma": {"fut": 29392.0}, "em": {"puntos": 519.2}}}})
assert lin == "ES flip=7782.1;cw=7837.3;pw=7637.3;em=93.9;maxg=7737.3;rf=2026-10-23 | NQ flip=30106.2;cw=29865.0;pw=28915.0;em=519.2;maxg=29392.0;rf=2026-10-22", lin
assert "rf=na" in GI.linea_niveles({"indices": {}}) and pine_estado_gex(lin, u("2026-10-26T14:45"), "NQ")["fila_roja"] == ROJA.format("22-10")
src = open(os.path.join(RAIZ, "plataformas", "tradingview", "NexoraNiveles.pine"), encoding="utf-8").read()
for clave in ("f_relevo", "f_previo_laborable", "AMEX:SPY", "CADUCADOS, pega la línea de hoy", "line.style_dashed", "Europe/Madrid", "15, 30", "[calT0, calT1, calT2]", 'f_texto(seg, "rf")'):
    assert clave in src, clave
for f in ("f_relevo", "f_previo_laborable", "f_ymd", "f_ymd_txt"):      # las funciones de calendario son idénticas en los dos Pine
    ini = lambda t: t[t.index(f + "("):]  # noqa: E731
    cuerpo = lambda t: ini(t)[:ini(t).index("\n\n")]  # noqa: E731
    assert cuerpo(src) == cuerpo(fuente_pine), f
print(f"4b) OK NexoraNiveles.pine (ES/NQ): misma regla; {len(ESC2)} escenarios (cada gráfico lee su segmento rf=), línea sin rf = sin alarma, línea de NEXORA con rf= por índice, funciones de calendario idénticas a las del Pine del oro")
print(f"4) OK Pine: la lógica portada coincide con la definición independiente en {n} instantes (1 año, cada 20 min, con festivos y cambios de hora) y {len(ESC)} escenarios (fila roja, líneas en gris, fila ámbar)")
print(f"   (respaldo sin calendario de la bolsa: acierta en {n - sin_cal} de {n} instantes; solo falla justo después de un festivo, por eso el calendario de SPY es lo principal)")
print("OK · Fase 21: JSON, build, lógica C# de NexoraNiveles y lógica de caducidad de NexoraOro.pine")
