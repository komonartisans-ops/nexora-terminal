#!/usr/bin/env python3
"""Prueba del ánimo del consumidor con la Universidad de Michigan como fuente primaria. Todo SIMULADO (sin red, carpeta temporal, Telegram falso).
Uso:  python tools/prueba_michigan.py"""
import datetime as dt
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import consumo as C  # noqa: E402
import integridad as I  # noqa: E402
import michigan as M  # noqa: E402

for k in ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"):
    os.environ.pop(k, None)
UTC = dt.timezone.utc
D = dt.date


def nueva():
    T = tempfile.mkdtemp(prefix="mich_")
    os.makedirs(os.path.join(T, "site/data"))
    os.makedirs(os.path.join(T, "data"))
    return T


def en(f, h):
    return dt.datetime.fromisoformat(f + "T" + h).replace(tzinfo=UTC)


# páginas simuladas con el formato real de sca.isr.umich.edu
MENSUAL = "Month,YYYY,ICS_ALL\nNovember,1952,86.2\n" + "".join(f"{m},{y},{70 + (i % 30)}.0\n" for i, (y, m) in enumerate(
    (y, m) for y in range(1978, 2026) for m in ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"))) \
    + "January,2026,56.4\nFebruary,2026,56.6\nJuly,2026,55.2\nAugust,2026,51.7\nSeptember,2026,48.1\n"
ACTUAL = ",,,THE INDEX OF CONSUMER SENTIMENT,,,,\n,,,,,,,,\nDATE OF SURVEY,,,,INDEX OF CONSUMER SENTIMENT,,,\n,,,,,,,\nAugust,2026,,,51.7,,,\nSeptember,2026,,,48.1,,,\nOctober (P),2026,,,46.3,,,\n,,,,,,,\n"
PORTADA_P = ("<html><body><h1>Preliminary Results for October 2026</h1><div class=\"next_release_note\">\n   Next data release: Friday, October 23, 2026 for Final October data at 10am ET\n</div></body></html>")
PORTADA_F = ("<html><body><h1>Final Results for October 2026</h1><div class=\"next_release_note\">Next data release: Friday, November 13, 2026 for Preliminary November data at 10am ET</div></body></html>")
MENSUAL_F = MENSUAL + "October,2026,45.9\n"
ACTUAL_F = ACTUAL.replace("October (P),2026,,,46.3", "October,2026,,,45.9")


def red(m=MENSUAL, a=ACTUAL, p=PORTADA_P, rompe=()):
    def f(url):
        for nombre, txt in (("tbmics", m), ("tbcics", a)):
            if url.endswith(nombre + ".csv"):
                if nombre in rompe:
                    raise OSError("caído")
                return txt
        if "portada" in rompe:
            raise OSError("caída")
        return p
    return f


# ---------------------------------------------------------------- 1) lectura de las tres páginas
m = M.parse_mensual(MENSUAL)
a = M.parse_actual(ACTUAL)
po = M.parse_portada(PORTADA_P)
assert m[0] == (D(1952, 11, 1), 86.2) and m[-1] == (D(2026, 9, 1), 48.1)
assert a[-1] == (D(2026, 10, 1), 46.3, "preliminar") and a[-2] == (D(2026, 9, 1), 48.1, "final"), a
assert po["resultados"] == {"tipo": "preliminar", "periodo": "2026-10-01"} and po["proximo"] == {"fecha": "2026-10-23", "hora_et": "10:00", "tipo": "final", "periodo": "2026-10-01"}, po
pf = M.parse_portada(PORTADA_F)
assert pf["resultados"] == {"tipo": "final", "periodo": "2026-10-01"} and pf["proximo"] == {"fecha": "2026-11-13", "hora_et": "10:00", "tipo": "preliminar", "periodo": "2026-11-01"}
assert M.parse_portada("<p>Next data release: Friday, January 9, 2026 for Preliminary January data at 2pm ET</p>")["proximo"]["hora_et"] == "14:00"
assert M.parse_portada("<p>Next data release: Friday, December 18, 2026 for Final December data</p>")["proximo"]["periodo"] == "2026-12-01"
ser = M.combinar(m, a)
assert ser[-1] == (D(2026, 10, 1), 46.3, "preliminar") and ser[-2][2] == "final"
print("1) OK lectura: tbmics (final) + tbcics con «October (P)» = PRELIMINAR + portada («Next data release … Final October data at 10am ET»); %d meses" % len(ser))

# ---------------------------------------------------------------- 2) cada página falla por separado y un formato inesperado no se traga
L = M.leer(red(rompe=("portada",)))
assert "portada" in L["errores"] and L["serie"][-1][2] == "preliminar" and L["portada"] == {"resultados": None, "proximo": None}
L = M.leer(red(rompe=("tbcics",)))
assert "tbcics" in L["errores"] and L["serie"][-1] == (D(2026, 9, 1), 48.1, "final")        # sin la tabla «Current» no se ve el preliminar: no se inventa
L = M.leer(red(p="<html>mantenimiento</html>"))
assert "portada" in L["errores"] and "formato" in L["errores"]["portada"]
L = M.leer(red(rompe=("tbmics", "tbcics", "portada")))
assert not L["serie"] and len(L["errores"]) == 3
print("2) OK cada página falla por separado; sin tablas, serie vacía (SIN DATO); página de mantenimiento = error, no dato")

# ---------------------------------------------------------------- 3) registro solo-añadir: preliminar y después final, con fecha
T = nueva()
t0 = en("2026-10-19", "09:00")
r1 = M.actualizar(T, t0, red())
reg = M.registro(T)
assert any(r["periodo"] == "2026-10-01" and r["tipo"] == "preliminar" and r["valor"] == "46.3" and r["capturado_utc"] == "2026-10-19 09:00 UTC" for r in reg)
n1 = len(reg)
M.actualizar(T, en("2026-10-19", "10:00"), red())
assert len(M.registro(T)) == n1, "repetir la lectura no añade nada"
cal = M.calendario(T)
assert [(e["fecha"], e["tipo"], e["periodo"]) for e in cal] == [("2026-10-23", "final", "2026-10-01")]
assert M.fecha_publicacion(T, "2026-10-01", "final") == "2026-10-23" and M.fecha_publicacion(T, "2026-10-01", "preliminar") is None
M.actualizar(T, en("2026-10-23", "16:00"), red(MENSUAL_F, ACTUAL_F, PORTADA_F))
reg = M.registro(T)
assert len(reg) == n1 + 1, "el final es una fila NUEVA; el preliminar queda intacto"
assert [r["valor"] for r in reg if r["periodo"] == "2026-10-01"] == ["46.3", "45.9"] and [r["tipo"] for r in reg if r["periodo"] == "2026-10-01"] == ["preliminar", "final"]
assert M.fecha_publicacion(T, "2026-11-01", "preliminar") == "2026-11-13", "la portada anuncia el siguiente preliminar"
print("3) OK registro solo-añadir: preliminar 46,3 (visto 19-oct) y final 45,9 (23-oct) en filas separadas; fechas anunciadas guardadas; el preliminar de noviembre queda en el calendario (13-nov)")

# ---------------------------------------------------------------- 4) estado: tipo, fechas, antigüedad (ámbar > 45 días), respaldo FRED
T = nueva()
os.makedirs(os.path.join(T, "data"), exist_ok=True)
M.actualizar(T, en("2026-10-19", "09:00"), red())
fred_ago = [(D(2026, 7, 1), 55.2), (D(2026, 8, 1), 51.7)]
E = M.estado(T, M.leer(red())["serie"], fred_ago, en("2026-10-19", "09:00"))
assert E["origen"] == "michigan" and E["ultimo"]["tipo"] == "preliminar" and E["ultimo"]["valor"] == 46.3 and E["ultimo"]["publicado"] is None
assert E["ultimo_final"]["texto"] == "septiembre 2026" and E["ultimo_final"]["valor"] == 48.1
assert E["antiguedad_dias"] == 0 and E["ambar"] is False
assert E["fred"]["texto"] == "agosto 2026" and E["fred"]["meses_de_retraso"] == 2 and E["fred"]["antiguedad_dias"] == 49 and E["fred"]["coincide"] is True
sin_p = M.leer(red(rompe=("tbcics", "portada")))["serie"]                        # solo hasta septiembre (final)
assert M.estado(T, sin_p, [], en("2026-10-15", "09:00"))["antiguedad_dias"] == 15
assert M.estado(T, sin_p, [], en("2026-11-14", "09:00"))["antiguedad_dias"] == 45 and M.estado(T, sin_p, [], en("2026-11-14", "09:00"))["ambar"] is False, "45 días exactos no es ámbar"
assert M.estado(T, sin_p, [], en("2026-11-15", "09:00"))["ambar"] is True, "46 días = ámbar"
EF = M.estado(T, [], fred_ago, en("2026-10-19", "09:00"))
assert EF["origen"] == "fred" and EF["ultimo"]["texto"] == "agosto 2026" and EF["antiguedad_dias"] == 49 and EF["ambar"] is True, "FRED solo: se usa de respaldo y sale ámbar"
assert M.estado(T, [], [], en("2026-10-19", "09:00"))["estado"] == "SIN DATO"
print("4) OK estado: octubre PRELIMINAR 46,3 (antigüedad 0 d), último final sep 48,1 (publicado SIN DATO→ fecha solo si se anunció); FRED va 2 meses atrás (49 d); 45 d no es ámbar, 46 d sí; FRED de respaldo; nada → SIN DATO")

# ---------------------------------------------------------------- 5) segunda fuente: FRED frente a Michigan (umbral 0,05 %)
T = nueva()
serie = M.leer(red())["serie"]
ahora = en("2026-10-19", "09:00")
assert M.cotejar_fred(T, serie, [(D(2026, 8, 1), 51.7)], ahora) == [] and not os.path.exists(os.path.join(T, "data", "discrepancias.csv"))
ab = M.cotejar_fred(T, serie, [(D(2026, 8, 1), 52.7)], ahora)
assert len(ab) == 1 and ab[0]["estado"] == "ABIERTA" and ab[0]["serie"] == "UMCSENT" and ab[0]["primaria_valor"] == 51.7 and "Manda Michigan" in ab[0]["nota"]
assert M.cotejar_fred(T, serie, [(D(2026, 8, 1), 52.7)], en("2026-10-19", "10:00")) == [], "una discrepancia abierta no se repite"
ce = M.cotejar_fred(T, serie, [(D(2026, 8, 1), 51.7)], en("2026-10-19", "11:00"))
assert len(ce) == 1 and ce[0]["estado"] == "CERRADA"
assert M.cotejar_fred(T, serie, [(D(2026, 10, 1), 46.3)], ahora) == [], "FRED no trae preliminares: solo se comparan finales"
print("5) OK segunda fuente: FRED = Michigan → nada; 52,7 frente a 51,7 → ABIERTA (manda Michigan); al coincidir → CERRADA; un preliminar no se contrasta con FRED")

# ---------------------------------------------------------------- 6) percentil con el dato más reciente (preliminar incluido)
hist = [(D(1978 + i // 12, i % 12 + 1, 1), 60.0 + (i % 50), "final") for i in range(12 * 40)]
con_p = hist + [(D(2018, 1, 1), 45.0, "preliminar")]
A1, A2 = C.animo(hist, "ALZA"), C.animo(con_p, "ALZA")
assert A2["periodo"] == "2018-01-01" and A2["tipo"] == "preliminar" and A2["valor"] == 45.0 and A2["percentil"] < A1["percentil"] and A2["zona_baja"] and A2["nota"]
assert A2["puntua"] is False
print("6) OK percentil recalculado con el dato más reciente: %.1f → %.1f al llegar el preliminar (tipo «preliminar» a la vista)" % (A1["percentil"], A2["percentil"]))

# ---------------------------------------------------------------- 7) consumo.construir: Michigan manda; FRED de respaldo; ambos caídos → SIN DATO
def fuentes(mich, fred_ok=True):
    d = lambda: C.__dict__  # noqa: E731
    sesiones = [dt.date(2025, 1, 1) + dt.timedelta(days=i) for i in range(500)]
    y = lambda t: [(s, 100.0 + i * 0.1) for i, s in enumerate(sesiones)]  # noqa: E731
    f = (lambda sid, desde: [(D(2018, 1, 1) + dt.timedelta(days=30 * i), 100.0 + i) for i in range(100)]) if fred_ok else (lambda sid, desde: (_ for _ in ()).throw(OSError("caído")))
    return {"yahoo": y, "fred": f, "ssga": lambda tk: {"fecha": "15-Oct-2026", "principales": [{"ticker": "AMZN", "peso": 20.0}, {"ticker": "TSLA", "peso": 15.0}], "fuente": "SSGA"}, "michigan": mich}


big = [(D(1978 + i // 12, i % 12 + 1, 1), 70.0 + (i % 40), "final") for i in range(12 * 48 + 9)] + [(D(2026, 10, 1), 46.3, "preliminar")]
big = [x for x in big if x[0] < D(2026, 10, 1)] + [(D(2026, 10, 1), 46.3, "preliminar")]
T = nueva()
J = C.construir(fuentes(lambda: {"serie": big, "portada": {}, "errores": {}}), en("2026-10-19", "09:00"), T)
an = J["animo"]
assert an["estado"] == "OK" and an["tipo"] == "preliminar" and an["periodo"] == "2026-10-01" and an["dato"]["origen"] == "michigan" and an["dato"]["fuente_primaria"].startswith("Universidad de Michigan")
assert an["dato"]["fred"]["periodo"].startswith("2026") or an["dato"]["fred"]["periodo"]
J2 = C.construir(fuentes(lambda: (_ for _ in ()).throw(OSError("web caída"))), en("2026-10-19", "09:00"), T)
assert J2["animo"]["estado"] == "OK" and J2["animo"]["dato"]["origen"] == "fred" and "michigan" in J2["errores"], "con Michigan caído se usa FRED y se avisa"
J3 = C.construir(fuentes(lambda: (_ for _ in ()).throw(OSError("web caída")), fred_ok=False), en("2026-10-19", "09:00"), T)
assert J3["animo"]["estado"] == "SIN DATO" and J3["animo"]["dato"]["estado"] == "SIN DATO"
print("7) OK consumo: Michigan manda (octubre preliminar); Michigan caído → FRED de respaldo con el error anotado; ambos caídos → SIN DATO")

# ---------------------------------------------------------------- 8) vigilante: evento Michigan (final y preliminar) con su fuente
T = nueva()
M.actualizar(T, en("2026-10-19", "09:00"), red())                          # calendario: final 23-oct 10:00 ET
enviados = []
fake = lambda txt: (enviados.append(txt), (True, None))[1]                  # noqa: E731
assert I.vigilar(T, en("2026-10-23", "14:30"), enviar=fake) == [] and not enviados, "10:30 ET = 30 min después: aún no"
assert I.vigilar(T, en("2026-10-21", "09:00"), enviar=fake) == [] and not enviados, "antes del lanzamiento: nada"
r = I.vigilar(T, en("2026-10-23", "16:30"), enviar=fake)                     # 12:30 ET: han pasado 2 h 30 min y no hay final registrado
assert [x[1] for x in r] == ["AVISADO"] and len(enviados) == 1
txt = enviados[0]
assert "DATO NO REGISTRADO" in txt and "Confianza U. Michigan (final)" in txt and "octubre 2026" in txt and "16:00 (Madrid)" in txt and "data/michigan.csv" in txt and "sca.isr.umich.edu" in txt
assert I.vigilar(T, en("2026-10-23", "17:30"), enviar=fake) == [] and len(enviados) == 1, "un aviso por dato"
av = json.load(open(os.path.join(T, "data", "vigilante_estado.json"), encoding="utf-8"))["avisos"]
assert list(av) == ["Confianza U. Michigan (final)|2026-10-01"] and av["Confianza U. Michigan (final)|2026-10-01"]["estado"] == "AVISADO"
# si el final SÍ consta, no hay aviso
T2 = nueva()
M.actualizar(T2, en("2026-10-19", "09:00"), red())
M.actualizar(T2, en("2026-10-23", "15:05"), red(MENSUAL_F, ACTUAL_F, PORTADA_F))
env2 = []
assert I.vigilar(T2, en("2026-10-23", "16:30"), enviar=lambda x: (env2.append(x), (True, None))[1]) == [] and not env2
# preliminar de noviembre: anunciado el 23-oct, sale el 13-nov a las 10:00 ET
# El 13-nov, sin ninguna ejecución del vigilante del cierre registrada, saltaría el aviso «el vigilante del cierre no corre» (alta posterior a esta prueba): aquí se le da una ejecución reciente
with open(os.path.join(T2, "data", "vigilar_cierre.csv"), "w", encoding="utf-8", newline="") as _f:
    _f.write("fecha,ejecutado_utc,resultado,run_id_cierre,detalle\n2026-11-12,2026-11-12 22:15 UTC,OK,1,prueba\n")
env3 = []
f3 = lambda x: (env3.append(x), (True, None))[1]                            # noqa: E731
assert I.vigilar(T2, en("2026-11-13", "14:00"), enviar=f3) == [], "a las 9:00 ET todavía no"
r3 = I.vigilar(T2, en("2026-11-13", "17:00"), enviar=f3)
assert [x[1] for x in r3] == ["AVISADO"] and "Confianza U. Michigan (preliminar)" in env3[0] and "noviembre 2026" in env3[0]
M.actualizar(T2, en("2026-11-13", "17:10"), red(MENSUAL_F + "November,2026,44.0\n", ACTUAL_F.replace("October,2026,,,45.9", "October,2026,,,45.9\nNovember (P),2026,,,44.0"), PORTADA_F.replace("Final Results for October", "Preliminary Results for November")))
assert I.vigilar(T2, en("2026-11-13", "18:00"), enviar=f3) == [] and len(env3) == 1
# un preliminar queda cubierto si el final de ese mes ya está (no se avisa de lo que ya se superó)
assert ("2026-11-01", "preliminar") in {(r["periodo"], r["tipo"]) for r in M.registro(T2)}
print("8) OK vigilante: final a +30 min no avisa; a +2 h 30 min sin registrar → un aviso «DATO NO REGISTRADO … (final)» con fuente Michigan; registrado → nada; preliminar de noviembre también")

# ---------------------------------------------------------------- 9) descarga con tope: una vez cada 20 h salvo lanzamiento pendiente; Red simulada sin Michigan no toca la red
class RedFalsa:
    def __init__(self, f):
        self.n = 0
        self._f = f

    def michigan(self, url):
        self.n += 1
        return self._f(url)


T = nueva()
rf = RedFalsa(red())
assert I.refrescar_michigan(T, en("2026-10-19", "09:00"), rf) is not None and rf.n == 3
assert I.refrescar_michigan(T, en("2026-10-19", "15:00"), rf) is None and rf.n == 3, "6 h después y sin lanzamiento pendiente: no se vuelve a pedir"
assert I.refrescar_michigan(T, en("2026-10-20", "09:00"), rf) is not None and rf.n == 6, "pasadas 20 h: se pide otra vez"
assert I.refrescar_michigan(T, en("2026-10-23", "16:30"), rf) is not None and rf.n == 9, "lanzamiento del 23-oct sin registrar: se pide en cada pasada"
assert I.refrescar_michigan(T, en("2026-10-23", "17:30"), rf) is not None and rf.n == 12
class RedSinMichigan:
    pass
assert I.refrescar_michigan(T, en("2026-10-24", "09:00"), RedSinMichigan()) is None
print("9) OK descarga con tope: 3 páginas por pasada, 1 vez cada 20 h; cada pasada mientras un lanzamiento anunciado siga sin registrar; sin red real en pruebas")

# ---------------------------------------------------------------- 10) #/integridad: bloque Michigan con antigüedad y próximo lanzamiento
T = nueva()
M.actualizar(T, en("2026-10-19", "09:00"), red())
B = I.bloque_michigan(T, en("2026-10-19", "09:30"))
assert B["ultimo"]["texto"] == "octubre 2026" and B["ultimo"]["tipo"] == "preliminar" and B["antiguedad_dias"] == 0 and B["ambar"] is False
assert B["proximo"]["fecha"] == "2026-10-23" and B["proximo"]["texto"] == "final de octubre 2026"
Bv = I.bloque_michigan(T, en("2026-12-30", "09:30"))
assert Bv["antiguedad_dias"] == 60 and Bv["ambar"] is True, "sin datos nuevos en dos meses → ámbar"
J = I.construir(T, en("2026-10-19", "09:30"))
assert J["michigan"]["ultimo"]["valor"] == 46.3
print("10) OK integridad.json: Michigan octubre PRELIMINAR (0 d, verde); dos meses sin datos nuevos → 60 d, ámbar; próximo: final de octubre el 2026-10-23")

print("\nTODO OK · sin red, sin envíos reales")
