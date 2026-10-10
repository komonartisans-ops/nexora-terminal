"""NEXORA · BANCOS CENTRALES DEL MUNDO. Todo gratuito y oficial, sin IA.

Qué hace
  1. Tipos de política de los 38 bancos centrales del dataset WS_CBPOL del BIS (tipo actual, último movimiento, cambio a 12 meses).
  2. Próxima reunión SOLO si el propio banco publica calendario y se ha podido leer de su web (si no, SIN DATO con el motivo).
  3. Histórico de los 8 grandes desde 2010 (BIS).
  4. Capas del mapa: inflación y PIB (FMI DataMapper, WEO: año y si es dato o previsión) y divisa frente al USD a 1 mes (BIS WS_XRU).
  5. Contador global (cuántos suben/bajan a 12 meses) y lectura de liquidez global: CRITERIO NEXORA, regla fija documentada abajo.

CRITERIO NEXORA (fijo, no optimizado)
  · Movimiento a 12 meses = tipo hoy − tipo hace 365 días. SUBE ≥ +0,10 pp · BAJA ≤ −0,10 pp · si no, SIN CAMBIOS.
  · Amplitud = (bancos que suben − bancos que bajan) / bancos con dato.  ≥ +0,20 → ENDURECIMIENTO · ≤ −0,20 → RELAJACIÓN · si no, MIXTA.
  · Balance Fed + BCE + BoJ (liquidez.json): variación a 12 meses ≥ +2 % → EXPANDE · ≤ −2 % → SE CONTRAE · si no, PLANO.
  · La lectura global combina ambas patas; si falta una se dice y se lee solo la otra.
Los tipos del BIS son un único valor por banco (para la Fed, el punto medio del rango objetivo); la fecha es la de la observación del BIS.

Memoria permanente: data/historico_tipos_bancos.csv (puntos de cambio del tipo; solo se añade)."""
from __future__ import annotations

import csv
import datetime as dt
import html
import io
import json
import os
import re

import csvlog
import fuentes

HERE = os.path.dirname(os.path.abspath(__file__))
BIS_CBPOL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/D.{}?{}&format=csv"
BIS_XRU = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_XRU/1.0/D..?startPeriod={}&format=csv"
URL_BIS = "https://data.bis.org/topics/CBPOL"
URL_IMF = "https://www.imf.org/external/datamapper/"
IMF_UA = "python-requests/2.31"
DESDE = "2010-01-01"
UMBRAL_MOV = 0.10       # pp
UMBRAL_AMPLITUD = 0.20
UMBRAL_BALANCE = 2.0    # %

# código BIS → (banco, país o área, ISO-3 para la ficha, moneda)
BANCOS = {
    "US": ("Reserva Federal (Fed)", "Estados Unidos", "USA", "USD"),
    "XM": ("Banco Central Europeo (BCE)", "Zona euro", "EURO", "EUR"),
    "JP": ("Banco de Japón (BoJ)", "Japón", "JPN", "JPY"),
    "GB": ("Banco de Inglaterra (BoE)", "Reino Unido", "GBR", "GBP"),
    "CH": ("Banco Nacional Suizo (SNB)", "Suiza", "CHE", "CHF"),
    "CA": ("Banco de Canadá (BoC)", "Canadá", "CAN", "CAD"),
    "AU": ("Banco de la Reserva de Australia (RBA)", "Australia", "AUS", "AUD"),
    "NZ": ("Banco de la Reserva de Nueva Zelanda (RBNZ)", "Nueva Zelanda", "NZL", "NZD"),
    "SE": ("Riksbank", "Suecia", "SWE", "SEK"),
    "NO": ("Norges Bank", "Noruega", "NOR", "NOK"),
    "DK": ("Danmarks Nationalbank", "Dinamarca", "DNK", "DKK"),
    "IS": ("Banco Central de Islandia", "Islandia", "ISL", "ISK"),
    "PL": ("Narodowy Bank Polski", "Polonia", "POL", "PLN"),
    "CZ": ("Česká národní banka", "Chequia", "CZE", "CZK"),
    "HU": ("Magyar Nemzeti Bank", "Hungría", "HUN", "HUF"),
    "RO": ("Banca Națională a României", "Rumanía", "ROU", "RON"),
    "RS": ("Banco Nacional de Serbia", "Serbia", "SRB", "RSD"),
    "MK": ("Banco Nacional de Macedonia del Norte", "Macedonia del Norte", "MKD", "MKD"),
    "TR": ("Banco Central de la República de Turquía (CBRT)", "Turquía", "TUR", "TRY"),
    "RU": ("Banco de Rusia", "Rusia", "RUS", "RUB"),
    "IL": ("Banco de Israel", "Israel", "ISR", "ILS"),
    "SA": ("Banco Central de Arabia Saudí (SAMA)", "Arabia Saudí", "SAU", "SAR"),
    "KW": ("Banco Central de Kuwait", "Kuwait", "KWT", "KWD"),
    "ZA": ("Banco de la Reserva de Sudáfrica (SARB)", "Sudáfrica", "ZAF", "ZAR"),
    "MA": ("Bank Al-Maghrib", "Marruecos", "MAR", "MAD"),
    "CN": ("Banco Popular de China (PBoC)", "China", "CHN", "CNY"),
    "HK": ("Autoridad Monetaria de Hong Kong (HKMA)", "Hong Kong", "HKG", "HKD"),
    "IN": ("Banco de la Reserva de la India (RBI)", "India", "IND", "INR"),
    "KR": ("Banco de Corea (BoK)", "Corea del Sur", "KOR", "KRW"),
    "ID": ("Bank Indonesia", "Indonesia", "IDN", "IDR"),
    "MY": ("Bank Negara Malaysia", "Malasia", "MYS", "MYR"),
    "TH": ("Banco de Tailandia (BoT)", "Tailandia", "THA", "THB"),
    "PH": ("Bangko Sentral ng Pilipinas", "Filipinas", "PHL", "PHP"),
    "BR": ("Banco Central de Brasil (BCB)", "Brasil", "BRA", "BRL"),
    "MX": ("Banco de México (Banxico)", "México", "MEX", "MXN"),
    "CL": ("Banco Central de Chile", "Chile", "CHL", "CLP"),
    "CO": ("Banco de la República (Colombia)", "Colombia", "COL", "COP"),
    "PE": ("Banco Central de Reserva del Perú", "Perú", "PER", "PEN"),
}
GRANDES = ["US", "XM", "JP", "GB", "CH", "CA", "AU", "NZ"]


# ---------------------------------------------------------------- utilidades
def _fecha_es(d):
    return d.strftime("%Y-%m-%d")


def _paso(serie, d):
    """Valor del tipo vigente en la fecha d (serie en escalón [(fecha, valor)] ordenada). None si d es anterior al primer punto."""
    v = None
    for f, x in serie:
        if f <= d:
            v = x
        else:
            break
    return v


def _csv_bis(url, timeout=120):
    return list(csv.DictReader(io.StringIO(fuentes.texto(url, timeout=timeout, tries=3))))


# ---------------------------------------------------------------- tipos de política (BIS) con memoria permanente
def _cargar_pasos():
    out = {}
    for r in csvlog.leer("historico_tipos_bancos.csv"):
        try:
            out.setdefault(r["area"], []).append((dt.date.fromisoformat(r["fecha"]), float(r["valor"])))
        except (KeyError, ValueError):
            continue
    return {k: sorted(v) for k, v in out.items()}


def _pasos_de_diaria(filas, previo=None):
    """Puntos de cambio (fecha, valor) de una serie diaria [(fecha, valor)] ordenada; `previo` = último valor ya conocido."""
    out = []
    ult = previo
    for d, v in filas:
        if ult is None or abs(v - ult) > 1e-9:
            out.append((d, v))
            ult = v
    return out


def tipos_bis(hoy):
    """{area: [(fecha, valor)]} puntos de cambio desde 2010 + {area: fecha del último dato válido}. Descarga solo la ventana reciente
    si la memoria permanente ya existe; la historia completa (~90 MB) solo en la primera ejecución."""
    areas = "+".join(BANCOS)
    pasos = _cargar_pasos()
    completo = any(a not in pasos or len(pasos[a]) == 0 for a in BANCOS)
    desde = DESDE if completo else (hoy - dt.timedelta(days=150)).isoformat()
    filas = _csv_bis(BIS_CBPOL.format(areas, f"startPeriod={desde}"), timeout=600 if completo else 120)
    diaria, ultimo = {}, {}
    for r in filas:
        try:
            v = float(r["OBS_VALUE"])
        except ValueError:
            continue
        if v != v:  # NaN: fines de semana y festivos; no es dato
            continue
        diaria.setdefault(r["REF_AREA"], []).append((dt.date.fromisoformat(r["TIME_PERIOD"]), v))
    nuevas = []
    for a in BANCOS:
        s = sorted(diaria.get(a, []))
        if not s:
            continue
        ultimo[a] = s[-1][0]
        if completo or not pasos.get(a):
            ps = _pasos_de_diaria(s)
            pasos[a] = ps
        else:
            corte = s[0][0]
            viejo = [p for p in pasos[a] if p[0] < corte]
            ref = viejo[-1][1] if viejo else None
            ps = _pasos_de_diaria(s, ref)
            pasos[a] = viejo + ps
        nuevas += [{"area": a, "fecha": d.isoformat(), "valor": v, "capturado": hoy.isoformat()} for d, v in pasos[a]]
    csvlog.anadir("historico_tipos_bancos.csv", nuevas, ("area", "fecha"))
    # fecha del último dato de TODAS las áreas del BIS (detecta series muertas como Argentina sin tocar nuestra lista)
    fin = {}
    for r in _csv_bis(f"https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/D.?lastNObservations=1&format=csv"):
        try:
            if float(r["OBS_VALUE"]) == float(r["OBS_VALUE"]):
                fin[r["REF_AREA"]] = r["TIME_PERIOD"]
        except ValueError:
            fin.setdefault(r["REF_AREA"], r["TIME_PERIOD"] + " (último valor sin dato)")
    return pasos, ultimo, fin


# ---------------------------------------------------------------- calendarios OFICIALES de reuniones
MESES_EN = {m: i + 1 for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"])}
MESES_ABR = {k[:3]: v for k, v in MESES_EN.items()}


def _txt(url, **kw):
    t = fuentes.texto(url, tries=2, timeout=40, **kw)
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", t, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t)))


def _cal_fed():
    u = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
    t = _txt(u)
    out = []
    MES = "January|February|March|April|May|June|July|August|September|October|November|December"
    for m in re.finditer(r"(\d{4}) FOMC Meetings (.*?)(?=\d{4} FOMC Meetings|$)", t):
        y = int(m.group(1))
        sec = re.split(r"Note:|Back to Top", m.group(2))[0]
        sec = re.sub(r"\(Released [^)]*\)", " ", sec)           # fechas de publicación de las actas: no son reuniones
        sec = re.sub(rf"(?:{MES}) \d{{1,2}} \(notation vote\)", " ", sec)  # votos por escrito: no son reuniones
        for mm in re.finditer(rf"({MES}) (\d{{1,2}})(?:-(?:({MES}) )?(\d{{1,2}}))?(?!\d)", sec):
            mes = MESES_EN[mm.group(3)] if mm.group(3) else MESES_EN[mm.group(1)]
            dia = int(mm.group(4) or mm.group(2))
            try:
                out.append(dt.date(y, mes, dia))
            except ValueError:
                pass
    return sorted(set(out)), u


def _cal_bce():
    u = "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"
    t = fuentes.texto(u, tries=2, timeout=40)
    out = []
    for d, x in re.findall(r"<dt>\s*(\d\d/\d\d/\d{4})\s*</dt>\s*<dd>(.*?)</dd>", t, flags=re.S):
        x = re.sub(r"<[^>]+>", "", x)
        if "monetary policy meeting" in x and "Day 2" in x:
            out.append(dt.datetime.strptime(d, "%d/%m/%Y").date())
    return sorted(set(out)), u


def _cal_boe():
    u = "https://www.bankofengland.co.uk/monetary-policy/upcoming-mpc-dates"
    t = _txt(u)
    out = []
    for m in re.finditer(r"(\d{4}) confirmed dates (.*?)(?=Current Bank Rate|Monetary Policy Committee voting history|Monetary Policy Committee Reports|$)", t):
        y = int(m.group(1))
        for mm in re.finditer(r"(?:Monday|Tuesday|Wednesday|Thursday|Friday) (\d{1,2}) (January|February|March|April|May|June|July|August|September|October|November|December)", m.group(2)):
            out.append(dt.date(y, MESES_EN[mm.group(2)], int(mm.group(1))))
    return sorted(set(out)), u


def _cal_snb():
    u = "https://www.snb.ch/en/services-events/digital-services/event-schedule"
    t = _txt(u)
    out = []
    for mm in re.finditer(r"Monetary policy assessment of (\d{1,2}) (January|February|March|April|May|June|July|August|September|October|November|December) (\d{4}) \(press release\)", t):
        out.append(dt.date(int(mm.group(3)), MESES_EN[mm.group(2)], int(mm.group(1))))
    return sorted(set(out)), u


def _cal_boc():
    u = "https://www.bankofcanada.ca/2025/08/bank-canada-publishes-2026-schedule-policy-interest-rate-announcements-other-major-publications/"
    t = _txt(u)
    m = re.search(r"interest rate announcements for 2026 are as follows: (.*?) The scheduled dates for", t)
    if not m:
        raise RuntimeError("BoC: formato de la nota de calendario cambiado")
    out = [dt.date(2026, MESES_EN[a], int(b)) for a, b in re.findall(r"Wednesday, (\w+) (\d{1,2})", m.group(1)) if a in MESES_EN]
    return sorted(set(out)), u


def _cal_boj():
    u = "https://www.boj.or.jp/en/about/calendar/"
    t = _txt(u)
    a = re.search(r"last update: (\w+) (\d{1,2}), (\d{4})", t)
    m = next((x for x in re.finditer(r"Upcoming Monetary Policy Meeting Dates (.*?) Monetary Policy Meetings", t) if re.search(r"\d", x.group(1))), None)
    if not a or not m:
        raise RuntimeError("BoJ: formato del calendario cambiado")
    y = int(a.group(3))
    out = []
    # «Oct. 29 (Thurs.), 30 (Fri.)»: cada mes nuevo abre una reunión y la decisión se anuncia el último día del grupo
    grupos = []
    for mes, dia in re.findall(r"(?:([A-Z][a-z]{2})\.? )?(\d{1,2}) \(", m.group(1)):
        if mes in MESES_ABR:
            grupos.append([mes, []])
        if grupos:
            grupos[-1][1].append(int(dia))
    for mes, dias in grupos:
        out.append(dt.date(y, MESES_ABR[mes], dias[-1]))
    if not out:
        raise RuntimeError("BoJ: sin fechas legibles")
    return sorted(set(out)), u


def _cal_riksbank():
    u = "https://www.riksbank.se/en-gb/press-and-published/calendar/calendar-2026"
    t = _txt(u)
    out = []
    for d, mes, y in re.findall(r"(\d{1,2}) ([A-Z][a-z]{2}) (\d{4}) Publication of monetary policy decision", t):
        if mes in MESES_ABR:
            out.append(dt.date(int(y), MESES_ABR[mes], int(d)))
    return sorted(set(out)), u


# RBA: calendario oficial publicado en nota de prensa (la web del RBA rechaza descargas automáticas: se verificó a mano). La decisión es el segundo día.
RBA = ([dt.date(2026, 2, 3), dt.date(2026, 3, 17), dt.date(2026, 5, 5), dt.date(2026, 6, 16), dt.date(2026, 8, 11),
        dt.date(2026, 9, 29), dt.date(2026, 11, 3), dt.date(2026, 12, 8)], "https://www.rba.gov.au/media-releases/2025/mr-25-02.html", "2026-10-10")

CALENDARIOS = {"US": _cal_fed, "XM": _cal_bce, "GB": _cal_boe, "CH": _cal_snb, "CA": _cal_boc, "JP": _cal_boj, "SE": _cal_riksbank}


def calendarios(hoy):
    out, err = {}, {}
    for a, fn in CALENDARIOS.items():
        try:
            fechas, url = fn()
            fut = [d for d in fechas if d >= hoy]
            out[a] = {"fechas": [d.isoformat() for d in fechas], "proxima": fut[0].isoformat() if fut else None, "fuente": "Calendario oficial del banco central", "url": url,
                      "lectura": "automática en esta ejecución"}
        except Exception as e:  # noqa: BLE001
            err[a] = f"{type(e).__name__}: {str(e)[:140]}"
    fut = [d for d in RBA[0] if d >= hoy]
    out["AU"] = {"fechas": [d.isoformat() for d in RBA[0]], "proxima": fut[0].isoformat() if fut else None, "fuente": "Nota oficial del RBA", "url": RBA[1],
                 "lectura": f"verificada a mano el {RBA[2]} (la web del RBA bloquea la descarga automática)"}
    return out, err


# ---------------------------------------------------------------- FMI DataMapper: inflación y PIB (anual)
def _imf(ind):
    return fuentes.json_(f"https://www.imf.org/external/datamapper/api/v1/{ind}", ua=IMF_UA, timeout=90)["values"][ind]


def fmi(hoy):
    """{iso3: {'inflacion': {...}, 'pib': {...}}}. Año del dato = último año completo (hoy.year − 1): el FMI no separa dato de estimación en su API,
    así que se rotula «dato o estimación». El año en curso se ofrece aparte como PREVISIÓN."""
    ano, ano_p = hoy.year - 1, hoy.year
    out, err = {}, {}
    for clave, ind in (("inflacion", "PCPIPCH"), ("pib", "NGDP_RPCH")):
        try:
            v = _imf(ind)
            for iso, serie in v.items():
                x, p = serie.get(str(ano)), serie.get(str(ano_p))
                if x is None and p is None:
                    continue
                out.setdefault(iso, {})[clave] = {"valor": x, "ano": ano, "prevision": p, "ano_prevision": ano_p}
        except Exception as e:  # noqa: BLE001
            err[ind] = f"{type(e).__name__}: {str(e)[:120]}"
    return out, err


# ---------------------------------------------------------------- divisas frente al USD (BIS WS_XRU), cambio a 1 mes
def divisas(hoy):
    """{area BIS: {'valor', 'fecha', 'cambio_1m_pct', 'ref_fecha', 'moneda'}}. Cambio > 0 = la divisa local se APRECIA frente al dólar."""
    filas = _csv_bis(BIS_XRU.format((hoy - dt.timedelta(days=75)).isoformat()), timeout=90)
    s, mon = {}, {}
    for r in filas:
        try:
            v = float(r["OBS_VALUE"])
        except ValueError:
            continue
        if v != v or v <= 0:
            continue
        s.setdefault(r["REF_AREA"], []).append((dt.date.fromisoformat(r["TIME_PERIOD"]), v))
        mon[r["REF_AREA"]] = r["CURRENCY"]
    out = {}
    for a, pts in s.items():
        pts.sort()
        f, v = pts[-1]
        lim = f - dt.timedelta(days=30)
        ref = [p for p in pts if p[0] <= lim]
        if not ref or (lim - ref[-1][0]).days > 7:
            cambio, rf = None, None
        else:
            rf = ref[-1]
            cambio = round((rf[1] / v - 1) * 100, 2)  # unidades locales por USD: si baja, la divisa se aprecia
        out[a] = {"valor": round(v, 6), "fecha": f.isoformat(), "cambio_1m_pct": cambio, "ref_fecha": rf[0].isoformat() if rf else None, "moneda": mon[a]}
    miembros_euro = sorted(a for a, m in mon.items() if m == "EUR" and a != "XM")
    return out, miembros_euro


# ---------------------------------------------------------------- medición
def _dir(d):
    return "SUBE" if d >= UMBRAL_MOV else "BAJA" if d <= -UMBRAL_MOV else "SIN CAMBIOS"


def medir(liquidez=None):
    hoy = dt.date.today()
    err = {}
    pasos, ultimo, fin_bis = tipos_bis(hoy)
    cal, e_cal = calendarios(hoy)
    err.update({f"calendario {k}": v for k, v in e_cal.items()})
    try:
        imf, e_imf = fmi(hoy)
        err.update(e_imf)
    except Exception as e:  # noqa: BLE001
        imf = {}
        err["FMI"] = f"{type(e).__name__}: {e}"
    try:
        fx, euro = divisas(hoy)
    except Exception as e:  # noqa: BLE001
        fx, euro = {}, []
        err["BIS WS_XRU"] = f"{type(e).__name__}: {e}"
    iso = json.load(open(os.path.join(HERE, "paises_iso.json"), encoding="utf-8"))
    a2_a_ccn = {v["a2"]: k for k, v in iso.items()}

    bancos = []
    for a, (banco, pais, iso3, moneda) in BANCOS.items():
        s = pasos.get(a) or []
        if not s or a not in ultimo:
            bancos.append({"codigo": a, "banco": banco, "pais": pais, "iso3": iso3, "moneda": moneda, "sin_dato": True, "motivo": "BIS sin dato en esta ejecución"})
            continue
        f, v = ultimo[a], s[-1][1]
        v = _paso(s, f)
        antes = _paso(s, f - dt.timedelta(days=365))
        cambios = [(s[i][0], round(s[i][1] - s[i - 1][1], 4)) for i in range(1, len(s))]
        um = cambios[-1] if cambios else None
        c12 = round(v - antes, 4) if antes is not None else None
        c = cal.get(a)
        if c and c["proxima"]:
            prox = {"fecha": c["proxima"], "dias": (dt.date.fromisoformat(c["proxima"]) - hoy).days, "fuente": c["fuente"], "url": c["url"], "lectura": c["lectura"]}
            motivo = None
        else:
            prox = None
            motivo = ("Calendario oficial leído pero sin reuniones futuras publicadas" if c else
                      f"Calendario no legible en esta ejecución ({err.get('calendario ' + a, 'error')})" if ("calendario " + a) in err else
                      "No se ha localizado un calendario oficial legible por máquina: no se estima")
        x = fx.get(a) if moneda != "USD" else None
        bancos.append({
            "codigo": a, "banco": banco, "pais": pais, "iso3": iso3, "moneda": moneda, "tipo": round(v, 4), "fecha_dato": f.isoformat(),
            "ultimo_movimiento": ({"fecha": um[0].isoformat(), "delta": um[1], "direccion": "SUBE" if um[1] > 0 else "BAJA", "dias": (hoy - um[0]).days} if um else None),
            "cambio_12m": c12, "dir_12m": _dir(c12) if c12 is not None else None,
            "proxima": prox, "motivo_sin_proxima": motivo,
            "fx": ({**x, "por_usd": x["valor"]} if x else None),
            "inflacion": (imf.get(iso3) or {}).get("inflacion"), "pib": (imf.get(iso3) or {}).get("pib"),
            "pasos": [[d.isoformat(), val] for d, val in s if d >= dt.date(2015, 1, 1)] if a not in GRANDES else None,
        })
    ok = [b for b in bancos if not b.get("sin_dato")]

    # contador
    sube = [b for b in ok if b["dir_12m"] == "SUBE"]
    baja = [b for b in ok if b["dir_12m"] == "BAJA"]
    igual = [b for b in ok if b["dir_12m"] == "SIN CAMBIOS"]
    n = len([b for b in ok if b["dir_12m"]])
    amplitud = round((len(sube) - len(baja)) / n, 3) if n else None
    tipos_txt = None if amplitud is None else ("ENDURECIMIENTO" if amplitud >= UMBRAL_AMPLITUD else "RELAJACIÓN" if amplitud <= -UMBRAL_AMPLITUD else "MIXTA")
    # balance Fed + BCE + BoJ (liquidez.json)
    bal = None
    try:
        g = (liquidez or {}).get("historico", {}).get("liquidez_global_T") or []
        if len(g) > 10:
            ult = g[-1]
            lim = (dt.date.fromisoformat(ult[0]) - dt.timedelta(days=365)).isoformat()
            ref = next((p for p in reversed(g) if p[0] <= lim), None)
            if ref and (dt.date.fromisoformat(lim) - dt.date.fromisoformat(ref[0])).days <= 20:
                var = round((ult[1] / ref[1] - 1) * 100, 2)
                bal = {"valor_T": ult[1], "fecha": ult[0], "ref_fecha": ref[0], "var_12m_pct": var,
                       "estado": "EXPANDE" if var >= UMBRAL_BALANCE else "SE CONTRAE" if var <= -UMBRAL_BALANCE else "PLANO",
                       "fuente": "FRED (WALCL, ECBASSETSW, JPNASSETS) · liquidez.json de este terminal"}
    except Exception as e:  # noqa: BLE001
        err["balance"] = f"{type(e).__name__}: {e}"
    partes = []
    if tipos_txt:
        partes.append(f"tipos: {len(sube)} suben y {len(baja)} bajan de {n} bancos ({tipos_txt.lower()})")
    if bal:
        partes.append(f"balance Fed+BCE+BoJ {bal['estado'].lower()} ({sg(bal['var_12m_pct'])} % a 12 meses)")
    if tipos_txt and bal:
        mix = {("ENDURECIMIENTO", "SE CONTRAE"): "LIQUIDEZ GLOBAL RESTRICTIVA", ("ENDURECIMIENTO", "PLANO"): "LIQUIDEZ GLOBAL ALGO RESTRICTIVA",
               ("ENDURECIMIENTO", "EXPANDE"): "SEÑALES CONTRADICTORIAS (tipos al alza, balances en expansión)",
               ("MIXTA", "SE CONTRAE"): "LIQUIDEZ GLOBAL ALGO RESTRICTIVA", ("MIXTA", "PLANO"): "LIQUIDEZ GLOBAL NEUTRA", ("MIXTA", "EXPANDE"): "LIQUIDEZ GLOBAL ALGO EXPANSIVA",
               ("RELAJACIÓN", "SE CONTRAE"): "SEÑALES CONTRADICTORIAS (tipos a la baja, balances en contracción)", ("RELAJACIÓN", "PLANO"): "LIQUIDEZ GLOBAL ALGO EXPANSIVA",
               ("RELAJACIÓN", "EXPANDE"): "LIQUIDEZ GLOBAL EXPANSIVA"}
        lectura = mix[(tipos_txt, bal["estado"])]
    elif tipos_txt:
        lectura = {"ENDURECIMIENTO": "TIPOS ENDURECIÉNDOSE (balance sin dato)", "RELAJACIÓN": "TIPOS RELAJÁNDOSE (balance sin dato)", "MIXTA": "TIPOS SIN DIRECCIÓN CLARA (balance sin dato)"}[tipos_txt]
    else:
        lectura = "SIN DATO"
    # próximas reuniones ordenadas
    futuras = sorted([b for b in ok if b.get("proxima")], key=lambda b: b["proxima"]["fecha"])

    # países para el mapa (clave: código numérico ISO 3166-1)
    paises = {}
    por_iso3 = {v["a3"]: k for k, v in iso.items()}
    banco_de_iso3 = {b["iso3"]: b["codigo"] for b in bancos if b["iso3"] != "EURO"}
    for ccn, v in iso.items():
        a3 = v["a3"]
        cod = banco_de_iso3.get(a3)
        if a3 in [] or v["a2"] in euro:
            cod = "XM"
        f = imf.get(a3, {})
        paises[ccn] = {"a2": v["a2"], "a3": a3, "banco": cod, "inflacion": f.get("inflacion"), "pib": f.get("pib"),
                       "zona_euro": v["a2"] in euro}
    hist = {}
    for a in GRANDES:
        s = pasos.get(a) or []
        if s:
            hist[a] = [[d.isoformat(), val] for d, val in s] + [[hoy.isoformat(), s[-1][1]]]
    sin_banco = {k: v for k, v in fin_bis.items() if k not in BANCOS and k not in ("AT", "BE", "DE", "ES", "FR", "GR", "IT", "NL", "PT", "HR")}
    return {"fecha": hoy.isoformat(), "bancos": bancos, "n_bancos": len(ok), "n_catalogo": len(BANCOS),
            "contador": {"sube": len(sube), "baja": len(baja), "sin_cambios": len(igual), "total": n, "amplitud": amplitud, "tipos": tipos_txt,
                         "bancos_sube": [b["codigo"] for b in sube], "bancos_baja": [b["codigo"] for b in baja]},
            "balance": bal, "lectura": {"etiqueta": lectura, "texto": "; ".join(partes) + "." if partes else "SIN DATO",
                                        "regla": (f"Movimiento a 12 meses: SUBE ≥ +{_c(UMBRAL_MOV)} pp, BAJA ≤ −{_c(UMBRAL_MOV)} pp. Amplitud = (suben − bajan) / bancos con dato: "
                                                  f"≥ +{_c(UMBRAL_AMPLITUD)} endurecimiento, ≤ −{_c(UMBRAL_AMPLITUD)} relajación, entre medias mixta. Balance Fed+BCE+BoJ a 12 meses: "
                                                  f"≥ +{UMBRAL_BALANCE:.0f} % expande, ≤ −{UMBRAL_BALANCE:.0f} % se contrae, entre medias plano. Es una convención fija de NEXORA, no un modelo ajustado.")},
            "proximas_reuniones": [{"codigo": b["codigo"], "banco": b["banco"], "fecha": b["proxima"]["fecha"], "dias": b["proxima"]["dias"]} for b in futuras],
            "con_calendario": len([b for b in ok if b.get("proxima")]),
            "historico8": hist, "grandes": GRANDES, "eurozona": {"codigo": "XM", "miembros_a2": euro, "n": len(euro),
                                                                 "nota": "Países cuya divisa es el euro en el BIS (WS_XRU); todos comparten el tipo del BCE."},
            "paises": paises, "ano_fmi": hoy.year - 1, "ano_prevision_fmi": hoy.year,
            "series_sin_actualizar_bis": sin_banco,
            "fuentes": {"tipos": {"nombre": "BIS · Central bank policy rates (WS_CBPOL)", "url": URL_BIS}, "fmi": {"nombre": "FMI · DataMapper (WEO): PCPIPCH y NGDP_RPCH", "url": URL_IMF},
                        "divisas": {"nombre": "BIS · tipos de cambio frente al USD (WS_XRU)", "url": "https://data.bis.org/topics/XRU"}},
            "errores": err}


def _c(x):
    return f"{x:.2f}".replace(".", ",")


def sg(v, d=1):
    return f"{v:+.{d}f}".replace(".", ",")


if __name__ == "__main__":
    M = medir()
    M.pop("paises")
    for b in M["bancos"]:
        b.pop("pasos", None)
    print(json.dumps({k: v for k, v in M.items() if k not in ("historico8", "bancos")}, ensure_ascii=False, indent=1)[:3000])
    for b in M["bancos"]:
        print(b["codigo"], b.get("tipo"), b.get("fecha_dato"), b.get("ultimo_movimiento"), b.get("cambio_12m"), (b.get("proxima") or {}).get("fecha"))
