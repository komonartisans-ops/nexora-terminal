#!/usr/bin/env python3
"""Prueba de #/petroleo con datos SIMULADOS (sin red, carpeta temporal, Telegram falso): contratos y curva, empalme de CL=F, inventarios y media de 5 años, calendario de la EIA,
reglas de la tesis (todas las ramas), vigilante de la EIA, marcador y fallo de cada fuente por separado.
Uso:  python tools/prueba_petroleo.py"""
import datetime as dt
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import integridad as I  # noqa: E402
import marcador as M  # noqa: E402
import petroleo as P  # noqa: E402

for k in ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID", "EIA_API_KEY"):
    os.environ.pop(k, None)
UTC = dt.timezone.utc
D = dt.date


def nueva():
    T = tempfile.mkdtemp(prefix="pet_")
    for d in ("data", "site/data"):
        os.makedirs(os.path.join(T, d))
    return T


def en(f, h):
    return dt.datetime.fromisoformat(f + "T" + h).replace(tzinfo=UTC)


def serie(n, fin, ini, f0=D(2024, 10, 1)):
    """n días hábiles de ini a fin (lineal) terminando en el último hábil ≤ hoy simulado."""
    out, d, i = [], f0, 0
    while len(out) < n:
        if d.weekday() < 5:
            out.append((d, round(ini + (fin - ini) * len(out) / (n - 1), 3)))
        d += dt.timedelta(days=1)
    return out


# ---------------------------------------------------------------- 1) vencimientos y contratos reales
assert P.vencimiento(2026, 11) == D(2026, 10, 20), P.vencimiento(2026, 11)      # 25-oct es domingo → viernes 23 → 3 días hábiles antes = martes 20
assert P.vencimiento(2026, 12) == D(2026, 11, 20)                              # 25-nov es miércoles → 3 días hábiles antes = viernes 20
assert P.vencimiento(2027, 1) == D(2026, 12, 22)                               # 25-dic es viernes: sin modelar el festivo de CME salen 3 días hábiles antes = martes 22 (CME: lunes 21); límite documentado
assert P.ticker_wti(2026, 11) == "CLX26.NYM" and P.ticker_wti(2026, 12) == "CLZ26.NYM" and P.ticker_wti(2027, 1) == "CLF27.NYM"
assert P.nombre_contrato("CLX26.NYM") == "nov-2026" and P.nombre_contrato("CLF27.NYM") == "ene-2027"
m1, m2 = P.primero_segundo(P.contratos(D(2026, 10, 19)), D(2026, 10, 19))
assert (m1[2], m2[2]) == ("CLX26.NYM", "CLZ26.NYM")
m1, m2 = P.primero_segundo(P.contratos(D(2026, 10, 21)), D(2026, 10, 21))
assert (m1[2], m2[2]) == ("CLZ26.NYM", "CLF27.NYM"), "el 21-oct el nov ya ha vencido"
print("1) OK contratos: CLX26 vence el 20-oct-2026 (el 25 es domingo), CLZ26 el 20-nov; el 21-oct el 1.º pasa a ser CLZ26 y el 2.º CLF27 (tickers verificados en Yahoo)")

# ---------------------------------------------------------------- 2) curva: escasez / sobra / plana y aviso de vencimiento
hoy = D(2026, 10, 19)
fechas = [hoy - dt.timedelta(days=k) for k in range(80, -1, -1) if (hoy - dt.timedelta(days=k)).weekday() < 5][-40:]


def ct(a, b, c=None):
    s = {"CLX26.NYM": [(d, a) for d in fechas], "CLZ26.NYM": [(d, b) for d in fechas]}
    return s


for a, b, est in ((100.0, 97.0, "ESCASEZ"), (97.0, 100.0, "SOBRA"), (100.2, 100.0, "PLANA"), (100.5, 100.0, "ESCASEZ"), (99.5, 100.0, "SOBRA")):
    c = P.curva(ct(a, b), hoy)
    assert c["estado"] == est and c["m1"] == "CLX26.NYM" and c["m2"] == "CLZ26.NYM", (a, b, c)
c = P.curva(ct(100.0, 97.0), hoy)
assert c["diferencial"] == 3.0 and c["diferencial_pct"] == round(3 / 97 * 100, 2) and c["dias_a_vencimiento_m1"] == 1 and c["aviso"] and c["dias_par"] == len(fechas)
antes = {k: [(d, v) for d, v in sr if d <= D(2026, 10, 12)] for k, sr in ct(100.0, 97.0).items()}
assert P.curva(antes, D(2026, 10, 12))["aviso"] is None and P.curva(antes, D(2026, 10, 12))["dias_a_vencimiento_m1"] == 8, "con más de 3 días al vencimiento no hay aviso"
assert P.curva({"CLX26.NYM": ct(1, 2)["CLX26.NYM"]}, hoy) is None, "sin el 2.º contrato no hay curva: SIN DATO"
print("2) OK curva: +3,09 % = ESCASEZ, −3 % = SOBRA, ±0,2 % = PLANA, umbral ±0,5 %; vence en 1 día → aviso; sin 2.º contrato → SIN DATO")

# ---------------------------------------------------------------- 3) empalme de CL=F (cambio de contrato) corregido
wti = serie(300, 97.3, 80.0, D(2025, 8, 1))
wti = [(d, v) for d, v in wti if d <= hoy][:-2] + [(D(2026, 10, 16), 101.41), (D(2026, 10, 19), 97.32)]        # salta de nov (101,41) a dic (97,32)
pw = P.metricas_precio(wti)
assert pw["cambio_1d_pct"] == round((97.32 / 101.41 - 1) * 100, 2) and pw["valor"] == 97.32
ctr = {"CLX26.NYM": [(D(2026, 10, 12 + i), 100 + i * 0.3) for i in range(4)] + [(D(2026, 10, 16), 101.41), (D(2026, 10, 19), 100.32)],
       "CLZ26.NYM": [(D(2026, 10, 12 + i), 98 + i * 0.2) for i in range(4)] + [(D(2026, 10, 16), 98.14), (D(2026, 10, 19), 97.30)]}
aj, tk, aviso = P.ajustar_roll(pw, wti, ctr)
assert tk == "CLZ26.NYM" and aj["cambio_1d_pct"] == round((97.30 / 98.14 - 1) * 100, 2) and aviso and "mezcla dos contratos" in aviso, (tk, aj, aviso)
aj2, tk2, av2 = P.ajustar_roll(pw, wti, {"CLX26.NYM": ctr["CLX26.NYM"]})
assert tk2 is None and aj2 == pw and av2 is None, "si ningún contrato real coincide, no se toca nada"
print("3) OK empalme: CL=F pasó de 101,41 (nov) a 97,32 (dic) = −4,0 % falso; medido sobre CLZ26 (dic) el cambio real es −0,86 %; sin contrato que coincida no se corrige")

# ---------------------------------------------------------------- 4) inventarios EIA: lectura del historial, media de 5 años, voto
html = ("<html><script>x</script><table><tr><td>2026-Oct</td><td>10/02</td><td>&nbsp;424,134&nbsp;</td><td>10/09</td><td>&nbsp;415,577&nbsp;</td></tr>"
        "<tr><td>&nbsp;&nbsp;2025-Oct</td><td>10/03</td><td>430,000</td><td>10/10</td><td>431,000</td></tr></table></html>")
h = P.parse_hist(html)
assert h == [(D(2025, 10, 3), 430000.0), (D(2025, 10, 10), 431000.0), (D(2026, 10, 2), 424134.0), (D(2026, 10, 9), 415577.0)], h
base = []
for y in range(2019, 2027):
    d0 = D(y, 1, 1)
    while d0.weekday() != 4:
        d0 += dt.timedelta(days=1)
    while d0 <= D(y, 12, 31):
        base.append((d0, 420000.0 if y < 2026 else 400000.0))
        d0 += dt.timedelta(days=7)
base = [x for x in base if x[0] <= D(2026, 10, 9)]
inv = P.inventario(base)
assert inv["semana"] == "2026-10-09" and inv["valor_mb"] == 400.0 and inv["media_5a_mb"] == 420.0 and inv["vs_media_5a_pct"] == round((400 / 420 - 1) * 100, 2) and inv["voto"] == 1 and inv["anios_media"] == 5
for v, voto in ((412000.0, 0), (428500.0, -1), (428400.0, 0), (411600.0, 0), (411500.0, 1)):
    s2 = base[:-1] + [(base[-1][0], v)]
    assert P.inventario(s2)["voto"] == voto, (v, P.inventario(s2))
assert P.inventario(base[:30]) is None, "con poca historia → SIN DATO"
m, n = P.media_5a(base[-3:], D(2026, 10, 9))
assert m is None, "sin 4 años de historia no hay media de 5 años"
api = json.dumps({"response": {"data": [{"period": "2026-10-09", "series": "WCESTUS1", "value": "415577"}, {"period": "2026-10-02", "series": "WCESTUS1", "value": "424134"}, {"period": "2026-10-09", "series": "OTRA", "value": "1"}]}})
assert P.parse_api(api, "WCESTUS1") == [(D(2026, 10, 2), 424134.0), (D(2026, 10, 9), 415577.0)]
sem, vals = P.parse_tabla1('"STUB_1","10/9/26","10/2/26"\n"Crude Oil","698.560","707.117"\n"Commercial (Excluding SPR)","415.577","424.134"\n"Total Motor Gasoline","208.262","204.744"\n"Distillate Fuel Oil","102.611","105.138"\n')
assert sem == D(2026, 10, 9) and vals == {"crudo": 415577.0, "gasolina": 208262.0, "destilados": 102611.0}
print("4) OK inventarios: historial EIA leído; media de 5 años = 420 Mb; 400 Mb = −4,76 % → voto +1; ±2 % exactos no votan (−2,0 % → 0); poca historia → SIN DATO; API v2 y table1.csv leídos")

# ---------------------------------------------------------------- 5) clave de la API de EIA: solo se usa en la consulta y no se filtra
clave = "CLAVE-SECRETA-123"
visto = []


def eia_roto(url):
    visto.append(url)
    if "api.eia.gov" in url:
        raise OSError("fallo con " + url)                       # un error que incluye la URL (con la clave) no debe salir de eia_serie
    return html


r, orig = P.eia_serie("WCESTUS1", eia_roto, clave)
assert "tablas públicas" in orig and any(clave in u for u in visto if "api.eia.gov" in u) and r, "con la API caída se recurre a las tablas públicas"
r2, orig2 = P.eia_serie("WCESTUS1", eia_roto, None)
assert not any("api.eia.gov" in u for u in visto[1:]) and "tablas públicas" in orig2, "sin clave no se llama a la API"
print("5) OK EIA_API_KEY: con clave se prueba la API v2 (y si falla se usan las tablas públicas sin propagar la URL con la clave); sin clave no se llama a la API")

# ---------------------------------------------------------------- 6) calendario oficial de la EIA
ESQ = ("<table><tr><td>Data for the week ending</td></tr><tr><td>October 9, 2026</td><td>October 15, 2026</td><td>Thursday</td><td>12:00 p.m.</td><td>Columbus Day</td></tr>"
       "<tr><td>December 19, 2025</td><td>December 29, 2025</td><td>Monday</td><td>5:00 p.m.</td><td>Christmas</td></tr></table>")
exc = P.parse_calendario_eia(ESQ)
assert exc == {D(2026, 10, 9): (D(2026, 10, 15), "12:00"), D(2025, 12, 19): (D(2025, 12, 29), "17:00")}, exc
assert P.publicacion_eia(D(2026, 10, 9), exc) == (D(2026, 10, 15), "12:00") and P.publicacion_eia(D(2026, 10, 16), exc) == (D(2026, 10, 21), "10:30")
assert P.proxima_publicacion(exc, D(2026, 10, 19)) == (D(2026, 10, 16), D(2026, 10, 21), "10:30")
assert P.proxima_publicacion(exc, D(2026, 10, 21)) == (D(2026, 10, 16), D(2026, 10, 21), "10:30"), "el día del informe aún cuenta"
print("6) OK calendario EIA: miércoles 10:30 ET salvo excepciones oficiales (semana al 9-oct → jueves 15-oct 12:00 ET por el Columbus Day); próximo informe 21-oct")

# ---------------------------------------------------------------- 7) tesis: todas las ramas y la intensidad
PR = {"valor": 100.0, "sma200": 90.0}
PRB = {"valor": 80.0, "sma200": 90.0}


def cv(estado):
    return {"estado": estado}


def iv(*v):
    return {k: {"voto": x} for k, x in zip(("crudo", "gasolina", "destilados"), v)}


def ct_(voto):
    return {"estado": "OK", "voto": voto}


t = P.tesis(PR, cv("ESCASEZ"), iv(1, 1, 1), ct_(1))
assert (t["resultado"], t["intensidad"], t["puntos"]) == ("ALCISTA", "FUERTE", 4)
t = P.tesis(PR, cv("ESCASEZ"), iv(1, 1, 0), ct_(-1))
assert t["votos"] == {"precio": 1, "curva": 1, "inventarios": 1, "cot": -1} and (t["resultado"], t["intensidad"], t["puntos"]) == ("ALCISTA", "DÉBIL", 2), "un factor en contra → débil aunque sume 2"
t = P.tesis(PR, cv("ESCASEZ"), iv(1, 1, 1), ct_(0))
assert (t["resultado"], t["intensidad"], t["puntos"]) == ("ALCISTA", "FUERTE", 3)
t = P.tesis(PR, cv("PLANA"), iv(0, 0, 0), ct_(0))
assert (t["resultado"], t["puntos"]) == ("SIN TESIS", 1)
t = P.tesis(PRB, cv("SOBRA"), iv(-1, -1, 0), ct_(1))
assert t["votos"]["inventarios"] == -1 and (t["resultado"], t["intensidad"], t["puntos"]) == ("BAJISTA", "DÉBIL", -2)
t = P.tesis(PRB, cv("SOBRA"), iv(-1, -1, -1), ct_(-1))
assert (t["resultado"], t["intensidad"], t["puntos"]) == ("BAJISTA", "FUERTE", -4)
t = P.tesis(PR, cv("SOBRA"), iv(1, 1, 1), ct_(-1))
assert (t["resultado"], t["puntos"]) == ("SIN TESIS", 0), "+1 −1 +1 −1 = 0"
assert P.tesis(PR, None, {}, {"estado": "SIN DATO"})["resultado"] == "SIN TESIS" and P.tesis(PR, None, {}, {"estado": "SIN DATO"})["puntos"] is None, "solo el precio → faltan datos"
assert P.tesis(None, cv("ESCASEZ"), iv(1, 1, 1), ct_(1))["resultado"] == "SIN TESIS", "sin precio no hay tesis"
t = P.tesis(PR, None, iv(1, 1, 1), {"estado": "SIN DATO"})
assert t["factores_con_dato"] == 2 and t["resultado"] == "SIN TESIS", "con 2 factores de 4 con dato, SIN TESIS por falta de dato"
t = P.tesis(PR, None, iv(1, 1, 1), ct_(1))
assert t["resultado"] == "ALCISTA" and t["factores_con_dato"] == 3 and t["puntos"] == 3, "3 factores con dato bastan"
t = P.tesis(PR, cv("ESCASEZ"), iv(1, 1, 1), ct_(1))
assert all(isinstance(x, list) and x for x in (t["confirmaria"], t["invalidaria"])) and "90,00 $" in t["confirmaria"][0]
assert P.tesis(PRB, cv("SOBRA"), iv(-1, -1, -1), ct_(-1))["confirmaria"][0].startswith("el WTI se mantiene por debajo")
cot_alto = P.cot_wti({"contratos": [{"clave": "wti", "gestores": {"percentil_3a": 66, "fecha": "2026-10-13", "neto": 1, "largos": 2, "cortos": 1, "cambio_semana": 0, "min_3a": 0, "max_3a": 5}}]})
cot_bajo = P.cot_wti({"contratos": [{"clave": "wti", "gestores": {"percentil_3a": 34, "fecha": "2026-10-13", "neto": 1, "largos": 2, "cortos": 1, "cambio_semana": 0, "min_3a": 0, "max_3a": 5}}]})
cot_med = P.cot_wti({"contratos": [{"clave": "wti", "gestores": {"percentil_3a": 50, "fecha": "2026-10-13", "neto": 1, "largos": 2, "cortos": 1, "cambio_semana": 0, "min_3a": 0, "max_3a": 5}}]})
assert (cot_alto["voto"], cot_bajo["voto"], cot_med["voto"]) == (1, -1, 0) and P.cot_wti(None)["estado"] == "SIN DATO" and P.cot_wti({"contratos": []})["estado"] == "SIN DATO"
print("7) OK tesis: 4 votos = ALCISTA FUERTE; +2 con un voto en contra = DÉBIL; −2 = BAJISTA DÉBIL; −4 = BAJISTA FUERTE; 0/±1 = SIN TESIS; sin precio o con < 3 factores = SIN TESIS; COT ≥ 66 → +1, ≤ 34 → −1")

# ---------------------------------------------------------------- 8) relaciones (no puntúan)
n = 90
wp = []
pv = 80.0
for i in range(n):
    pv *= 1 + 0.01 * (1 if i % 3 else -1.5) * (1 + 0.1 * (i % 5))                # variaciones diarias irregulares (no constantes)
    wp.append((D(2026, 1, 1) + dt.timedelta(days=i), pv))
dxy_inv = [(d, 100.0 / (v / 80.0)) for d, v in wp]
rel = P.relaciones(wp, [(d, 2.0 + 0.001 * i) for i, (d, _) in enumerate(wp)], dxy_inv, wp)
f = {x["clave"]: x for x in rel["filas"]}
assert f["xle"]["correlacion_60d"] == 1.0 and f["dxy"]["correlacion_60d"] is not None and f["dxy"]["correlacion_60d"] < -0.9 and f["t5yie"]["unidad_cambio"] == "pb"
rel2 = P.relaciones(wp, [], None, wp)
assert [x.get("sin_dato") for x in rel2["filas"]] == [True, True, None]
print("8) OK relaciones: XLE = +1,00, DXY inverso < −0,9, breakeven en pb; sin dato → SIN DATO (no puntúan)")

# ---------------------------------------------------------------- 9) construir(): fuentes simuladas, cada una falla por separado
def yahoo_sim(sym, rango="2y", minimo=5):
    if sym == "CL=F":
        return wti
    if sym == "BZ=F":
        return serie(300, 108.0, 85.0, D(2025, 8, 1))
    if sym.startswith("CL"):
        return ctr.get(sym) or [(d, 100.0) for d in fechas]
    return serie(300, 68.0, 55.0, D(2025, 8, 1))


def fred_sim(sid, desde):
    base = {"DCOILWTICO": 101.9, "DCOILBRENTEU": 126.5, "GASREGW": 4.33, "T5YIE": 2.37}[sid]
    return [(d, base) for d, _ in serie(560, 0, 0, D(2024, 9, 2)) if d <= D(2026, 10, 14)]


def eia_sim(url):
    return html_largo


# historial EIA largo: 8 años de semanas
filas = []
for y in range(2018, 2027):
    d0 = D(y, 1, 5)
    while d0.weekday() != 4:
        d0 += dt.timedelta(days=1)
    r = []
    while d0.year == y and d0 <= D(2026, 10, 9):
        r.append((d0, 420000.0 if y < 2026 else 400000.0 - 100 * len(r)))
        d0 += dt.timedelta(days=7)
    filas += r
html_largo = "<html>" + "".join(f"<tr><td>{d.year}-Jan</td><td>{d.month:02d}/{d.day:02d}</td><td>{int(v):,}</td></tr>" for d, v in filas) + "</html>"
cot_ok = {"contratos": [{"clave": "wti", "gestores": {"percentil_3a": 14, "fecha": "2026-10-13", "neto": 40574, "largos": 171973, "cortos": 131399, "cambio_semana": -13024, "min_3a": -38154, "max_3a": 254544, "estado": "CORTO ELEVADO", "informe": "Dinero gestionado (Disaggregated)", "serie": [["2026-10-13", 40574]]}}]}
T = nueva()
J = P.construir({"yahoo": yahoo_sim, "fred": fred_sim, "eia": eia_sim, "cot": lambda: cot_ok, "consumo": lambda: {"tesis": {"resultado": "DIVERGENCIA MERCADO DEFENSIVO", "intensidad": "FUERTE"}, "fecha_datos": "2026-10-16"}},
                en("2026-10-19", "15:00"), T)
assert J["tesis"]["resultado"] in ("ALCISTA", "BAJISTA", "SIN TESIS") and not J["errores"], J["errores"]
assert J["precios"]["wti"]["contrato_cl_f"] == "CLZ26.NYM" and J["precios"]["wti"]["aviso_empalme"], "el empalme se corrige en construir()"
assert J["curva"]["m1"] == "CLX26.NYM" and J["curva"]["historico_propio"]["dias"] == 1 and os.path.exists(os.path.join(T, "data", "historico_curva_wti.csv"))
assert J["plataformas"]["estado"] == "SIN DATO" and "bakerhughes" in J["plataformas"]["motivo"].lower() and J["inventarios"]["proximo_informe"]["fecha"] == "2026-10-21"
assert J["gasolina"]["consumo"]["tesis"] == "DIVERGENCIA MERCADO DEFENSIVO" and J["cot"]["voto"] == -1 and len(J["reglas"]) >= 6 and len(J["precios"]["wti_spot_serie"]) > 100
assert J["precios"]["segunda_fuente"]["wti"]["fred"] == 101.9
# cada fuente falla por separado
def sin(*nombres):
    def y(sym, rango="2y", minimo=5):
        if any(sym == n for n in nombres):
            raise OSError("caído")
        return yahoo_sim(sym, rango, minimo)
    return y


Ja = P.construir({"yahoo": sin("CL=F"), "fred": fred_sim, "eia": eia_sim, "cot": lambda: cot_ok, "consumo": lambda: None}, en("2026-10-19", "15:00"), nueva())
assert "yahoo_CL=F" in Ja["errores"] and "FRED DCOILWTICO" in Ja["precios"]["wti"]["fuente"] and Ja["precios"]["wti"]["fecha"] == "2026-10-14", "Yahoo caído → FRED de respaldo con su fecha"
Jb = P.construir({"yahoo": sin("CLX26.NYM"), "fred": fred_sim, "eia": eia_sim, "cot": lambda: cot_ok, "consumo": lambda: None}, en("2026-10-19", "15:00"), nueva())
assert Jb["curva"] is None and Jb["tesis"]["votos"]["curva"] is None and "curva" in Jb["errores"]
Jc = P.construir({"yahoo": yahoo_sim, "fred": fred_sim, "eia": lambda u: (_ for _ in ()).throw(OSError("EIA caída")), "cot": lambda: None, "consumo": lambda: None}, en("2026-10-19", "15:00"), nueva())
assert Jc["inventarios"]["crudo"] is None and Jc["cot"]["estado"] == "SIN DATO" and Jc["tesis"]["votos"]["inventarios"] is None and Jc["tesis"]["votos"]["cot"] is None
assert Jc["tesis"]["factores_con_dato"] == 2 and Jc["tesis"]["resultado"] == "SIN TESIS", "precio + curva = 2 factores: SIN TESIS por falta de dato"
Jd = P.construir({"yahoo": lambda s, r="2y", m=5: (_ for _ in ()).throw(OSError("todo caído")), "fred": lambda s, d: (_ for _ in ()).throw(OSError("FRED caído")), "eia": lambda u: (_ for _ in ()).throw(OSError("x")),
                  "cot": lambda: None, "consumo": lambda: None}, en("2026-10-19", "15:00"), nueva())
assert Jd["tesis"]["resultado"] == "SIN TESIS" and Jd["precios"]["wti"] is None and Jd["curva"] is None
print("9) OK construir(): con todo → tesis y curva con histórico propio, empalme corregido, Baker Hughes SIN DATO; Yahoo caído → FRED de respaldo; sin contrato 1.º → curva SIN DATO; sin EIA/COT → SIN TESIS por falta de dato; todo caído → SIN DATO")

# ---------------------------------------------------------------- 10) vigilante y refresco de la EIA
T = nueva()
tabla = '"STUB_1","10/9/26","10/2/26"\n"Commercial (Excluding SPR)","415.577","424.134"\n"Total Motor Gasoline","208.262","204.744"\n"Distillate Fuel Oil","102.611","105.138"\n'
tabla2 = tabla.replace('"10/9/26","10/2/26"', '"10/16/26","10/9/26"').replace("415.577", "410.000")


class RedEIA:
    def __init__(self, t):
        self.n = 0
        self.t = t

    def eia(self, url):
        self.n += 1
        return self.t if "table1" in url else ESQ


assert P.pendientes_eia(T, en("2026-10-21", "16:00")) == [], "sin ninguna semana registrada no hay referencia: no se avisa"
rf = RedEIA(tabla)
assert I.refrescar_eia(T, en("2026-10-19", "09:00"), rf) == {} and rf.n == 2
assert {r["semana"] for r in P.registro_eia(T)} == {"2026-10-09"} and len(P.registro_eia(T)) == 3
assert I.refrescar_eia(T, en("2026-10-19", "15:00"), rf) is None and rf.n == 2, "6 h después y nada pendiente: no se vuelve a pedir"
assert P.excepciones_eia(T)[D(2026, 10, 9)] == (D(2026, 10, 15), "12:00")
assert P.pendientes_eia(T, en("2026-10-21", "15:00")) == [], "14:30 UTC = 10:00 ET del 21-oct: aún no han pasado 2 h del informe de las 10:30 ET"
pend = P.pendientes_eia(T, en("2026-10-21", "17:00"))                   # 13:00 ET: pasadas 2 h 30 min del informe
assert [(s.isoformat()) for s, _ in pend] == ["2026-10-16"]
env = []
fake = lambda x: (env.append(x), (True, None))[1]                        # noqa: E731
r = I.vigilar(T, en("2026-10-21", "17:00"), enviar=fake)
assert [x[1] for x in r] == ["AVISADO"] and "DATO NO REGISTRADO" in env[0] and "Inventarios de petróleo EIA" in env[0] and "16-10-2026" in env[0] and "eia_inventarios.csv" in env[0]
assert I.vigilar(T, en("2026-10-21", "18:30"), enviar=fake) == [] and len(env) == 1, "un aviso por dato"
assert I.refrescar_eia(T, en("2026-10-21", "17:05"), RedEIA(tabla2)) == {}, "informe pendiente: se vuelve a pedir en cada pasada"
T2 = nueva()
I.refrescar_eia(T2, en("2026-10-19", "09:00"), RedEIA(tabla))
I.refrescar_eia(T2, en("2026-10-21", "15:20"), RedEIA(tabla2), True)
e2 = []
assert I.vigilar(T2, en("2026-10-21", "17:00"), enviar=lambda x: (e2.append(x), (True, None))[1]) == [] and not e2, "semana registrada → no hay aviso"
# informe con excepción: el jueves 15-oct a las 12:00 ET
assert [s.isoformat() for s, _ in P.pendientes_eia(T2, en("2026-10-15", "13:00"))] == [], "14:00 UTC... aún no han pasado 2 h"
B = I.bloque_eia(T2, en("2026-10-22", "12:00"))
assert B["estado"] == "OK" and B["semana"] == "2026-10-16" and B["publicado"] == "2026-10-21" and B["antiguedad_dias"] == 1 and B["ambar"] is False and B["proximo"]["fecha"] == "2026-10-28"
assert I.bloque_eia(T2, en("2026-11-05", "12:00"))["ambar"] is True, "más de 10 días sin informe nuevo → ámbar"
assert I.bloque_eia(nueva(), en("2026-10-22", "12:00"))["estado"] == "SIN DATO"
class RedSinEIA:
    pass
assert I.refrescar_eia(T2, en("2026-10-30", "09:00"), RedSinEIA()) is None
print("10) OK vigilante EIA: sin registro previo no avisa; informe de las 10:30 ET registrado → nada; a +2 h 30 min sin registrar → un aviso con fuente EIA; refresco con tope de 20 h; bloque EIA ámbar a los 10 días; Red simulada sin .eia no toca la red")

# ---------------------------------------------------------------- 11) agenda: informe de la EIA como MEDIA con hora oficial (y festivos)
ev = P.eventos_agenda(T2, D(2026, 10, 19))
assert [(e["fecha"], e["hora_ny"], e["importancia"]) for e in ev] == [("2026-10-21", "10:30", "MEDIA"), ("2026-10-28", "10:30", "MEDIA")] and ev[0]["hora_madrid"] == "16:30" and ev[1]["hora_madrid"] == "15:30"
ev2 = P.eventos_agenda(T2, D(2026, 10, 12))
assert [(e["fecha"], e["hora_ny"]) for e in ev2][0] == ("2026-10-15", "12:00"), "el Columbus Day mueve el informe al jueves a las 12:00 ET"
import agenda as AG  # noqa: E402
assert {t["tipo"]: t["importancia"] for t in AG.tabla_importancia() if t["tipo"] in ("EIA", "OPEP")} == {"EIA": "MEDIA", "OPEP": "ALTA"}
assert "no accesible" in P.OPEP_SIN_DATO and "403" in P.OPEP_SIN_DATO
print("11) OK agenda: informe EIA = MEDIA, miércoles 10:30 ET (16:30 Madrid; 15:30 tras el cambio de hora europeo), jueves 12:00 ET con festivo; OPEP+ = ALTA en la tabla de importancia pero SIN DATO (opec.org bloquea)")

# ---------------------------------------------------------------- 12) marcador: señal «petroleo» sobre el WTI al contado
assert "petroleo" in M.TIPOS_PUNTUABLES and M.SERIE_DE["WTI"] == "wti"
T = nueva()
dias_ = [d for d, _ in serie(760, 0, 0, D(2024, 6, 3))]
spot = [[d.isoformat(), round(80 * (1.003 ** i), 4)] for i, d in enumerate(dias_)]


def escribe(res):
    json.dump({"tesis": {"resultado": res}, "precios": {"wti_spot_serie": spot}}, open(os.path.join(T, "site/data/petroleo.json"), "w", encoding="utf-8"))


hoy_ = dt.datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
escribe("SIN TESIS")
assert M.registrar(T, hoy_, "run-1") == []
escribe("ALCISTA")
nuevas = M.registrar(T, hoy_ + dt.timedelta(hours=1), "run-2")
assert [(s["tipo"], s["activo"], s["direccion"], s["origen"]) for s in nuevas] == [("petroleo", "WTI", "ALCISTA", "vivo")] and "SIN TESIS → ALCISTA" in nuevas[0]["valor"]
escribe("BAJISTA")
n2 = M.registrar(T, hoy_ + dt.timedelta(hours=2), "run-3")
assert [(s["direccion"]) for s in n2] == ["BAJISTA"]
escribe("SIN TESIS")
n3 = M.registrar(T, hoy_ + dt.timedelta(hours=3), "run-4")
assert [s["direccion"] for s in n3] == ["NINGUNA"], "SIN TESIS se registra como no puntuable"
nr = M.evaluar(T, dt.datetime(2026, 10, 17, 22, 0, tzinfo=UTC))
por = {(r["id"], str(r["horizonte"])): r for r in nr}
ida, idb, idc = nuevas[0]["id"], n2[0]["id"], n3[0]["id"]
assert ida.startswith("petroleo-wti-") and por[(ida, "20")]["resultado"] == "ACIERTO" and por[(idb, "20")]["resultado"] == "FALLO" and por[(ida, "20")]["unidad"] == "%", por
assert all(por[k]["resultado"] not in ("ACIERTO", "FALLO") for k in por if k[0] == idc), "SIN TESIS (dirección NINGUNA) no puntúa"
print("12) OK marcador: SIN TESIS → ALCISTA registra «petroleo» sobre WTI (ALCISTA, T+20 = ACIERTO con el spot que sube), el giro a BAJISTA es FALLO, SIN TESIS no puntúa")

print("\nTODO OK · sin red, sin envíos reales")
