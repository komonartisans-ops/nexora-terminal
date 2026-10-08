#!/usr/bin/env python3
"""
NEXORA · Calendario macro oficial automático (común a los monitores de cripto, oro e índices).

Fuentes oficiales, sin clave (nada se estima; lo que no se descarga queda como SIN DATO):
  · FRED Release Calendar (St. Louis Fed): fechas y horas que publican los propios organismos (BLS, BEA, Census,
    Fed, DOL, U. Michigan, Fed de Filadelfia). FRED da la hora en hora central de EE. UU. → se convierte a Nueva York y Madrid.
  · Federal Reserve: calendario de reuniones del FOMC (comunicado 14:00 Nueva York, día 2).
  · ISM: calendario oficial de publicación de los PMI (10:00 Nueva York).
  · BCE: calendario de reuniones del Consejo de Gobierno (solo reuniones de política monetaria).
  · Banco de Japón: calendario de reuniones de política monetaria (MPM).
  · TreasuryDirect: subastas del Tesoro anunciadas (solo notas y bonos; afectan a la curva).
  · Resultados empresariales (opcional): resultados.py (Nasdaq/Zacks; fecha confirmada o estimada).

    python calendario.py [--dias 21] [--pasado 7] [--out DIR]  → calendario_YYYYMMDD.json / .md
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import zoneinfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from liquidez_cripto import get, get_json, safe  # noqa: E402

CT, NY, MAD = zoneinfo.ZoneInfo("America/Chicago"), zoneinfo.ZoneInfo("America/New_York"), zoneinfo.ZoneInfo("Europe/Madrid")
HOY = dt.datetime.now(MAD).date()
UA = "curl/8.0"

# FRED release id → (nombre NEXORA, importancia, monitores afectados, qué mirar)
FRED_RELEASES = {
    50: ("Empleo EE. UU. (NFP, paro, salarios)", "ALTA", "cripto · oro · índices", "Empleo fuerte → 2Y ↑ (menos recortes); débil → 2Y ↓. Mirar salarios y revisiones."),
    10: ("IPC EE. UU. (CPI)", "ALTA", "cripto · oro · índices", "Subyacente m/m y servicios: inflación ↑ retrasa recortes (2Y ↑, real ↑)."),
    54: ("Renta y gasto personal (PCE)", "ALTA", "cripto · oro · índices", "PCE subyacente: la medida de inflación que sigue la Fed."),
    53: ("PIB EE. UU.", "MEDIA", "índices · oro", "Crecimiento y deflactor; revisiones."),
    192: ("Vacantes JOLTS", "MEDIA", "índices · oro", "Demanda de trabajo: vacantes ↓ = mercado laboral se enfría."),
    9: ("Ventas minoristas", "MEDIA", "índices", "Consumo: motor del crecimiento."),
    46: ("Precios de producción (PPI)", "MEDIA", "oro · índices", "Presión de costes que puede llegar al IPC."),
    180: ("Peticiones de paro semanales", "MEDIA", "índices · oro", "Media de 4 semanas ↑ = empleo se enfría."),
    351: ("Encuesta manufacturera Fed Filadelfia", "MEDIA", "índices", "Actividad industrial adelantada (proxy del ISM)."),
    91: ("Confianza U. Michigan (expectativas de inflación)", "MEDIA", "oro · índices", "Expectativas de inflación a 1 y 5 años."),
    20: ("Balance de la Fed H.4.1 (reservas, TGA, RRP)", "MEDIA", "cripto · oro · índices", "Liquidez: reservas ↑ / TGA ↓ = acompaña."),
    21: ("Oferta monetaria M2 (H.6)", "BAJA", "cripto · oro", "Liquidez a medio plazo."),
    13: ("Producción industrial", "BAJA", "índices", "Ciclo industrial (US30)."),
    22: ("Crédito bancario H.8", "BAJA", "índices", "Crédito de bancos comerciales."),
}
MES = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], 1)}


def txt(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", html))


def ev(fecha, hora_ny, evento, importancia, afecta, que_mirar, fuente, url, nota=""):
    """hora_ny = 'HH:MM' (Nueva York) o None si la fuente no la publica."""
    hm = None
    if hora_ny:
        h, m = map(int, hora_ny.split(":"))
        t = dt.datetime.combine(fecha, dt.time(h, m), NY)
        hm = t.astimezone(MAD).strftime("%H:%M")
    return {"fecha": fecha.isoformat(), "dia": ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"][fecha.weekday()], "hora_ny": hora_ny or "",
            "hora_madrid": hm or "", "evento": evento, "importancia": importancia, "afecta": afecta, "que_mirar": que_mirar,
            "fuente": fuente, "url": url, "nota": nota}


def fred_calendar(rid, years):
    out = []
    for y in years:
        url = f"https://fred.stlouisfed.org/releases/calendar?rid={rid}&y={y}"
        t = txt(get(url, timeout=40).decode("utf-8", "ignore"))
        for m in re.finditer(r"(\w+) (\d\d), (\d{4})((?: \|)+ (?:\w+ (?:\| )+)?)([\d:]+) ([ap]m)((?: \|)+) ([^|]+)", t):
            if m.group(1) not in MES:
                continue
            d = dt.date(int(m.group(3)), MES[m.group(1)], int(m.group(2)))
            h, mi = map(int, m.group(5).split(":"))
            h = h % 12 + (12 if m.group(6) == "pm" else 0)
            ny = dt.datetime.combine(d, dt.time(h, mi), CT).astimezone(NY)
            out.append((ny.date(), ny.strftime("%H:%M"), m.group(8).strip(), url))
    return out


def fomc():
    url = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
    h = get(url, timeout=40).decode("utf-8", "ignore")
    out = []
    for y in (HOY.year, HOY.year + 1):
        i = h.find(f"{y} FOMC Meetings")
        if i < 0:
            continue
        j = h.find("FOMC Meetings</a>", i + 30)
        blk = h[i:j if j > 0 else i + 60000]
        for m in re.finditer(r'fomc-meeting__month[^>]*><strong>([A-Za-z/]+)</strong></div>\s*<div class="fomc-meeting__date[^>]*>([^<]+)</div>', blk):
            mes, dias = m.group(1).split("/")[-1], m.group(2)
            nums = re.findall(r"\d+", dias)
            if not nums or mes not in MES:
                continue
            mes2 = MES[mes]
            if "/" in m.group(1) and int(nums[-1]) < int(nums[0]):
                pass  # reunión a caballo entre dos meses: el último día pertenece al segundo mes
            d = dt.date(y, mes2, int(nums[-1]))
            sep = "*" in dias
            out.append((d, "SEP" if sep else "", url))
    return out


def ism():
    url = "https://www.ismworld.org/supply-management-news-and-reports/reports/rob-report-calendar/"
    t = txt(get(url, timeout=40).decode("utf-8", "ignore"))
    out = []
    for m in re.finditer(r"(January|February|March|April|May|June|July|August|September|October|November|December) (\d{4})(?: \|)+ (\d{1,2})(?: \|)+ (\d{1,2})", t):
        y, mo = int(m.group(2)), MES[m.group(1)]
        out.append((dt.date(y, mo, int(m.group(3))), "manufacturero", url))
        out.append((dt.date(y, mo, int(m.group(4))), "servicios", url))
    return out


def bce():
    url = "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"
    t = txt(get(url, timeout=40).decode("utf-8", "ignore"))
    out = []
    for m in re.finditer(r"(\d\d)/(\d\d)/(\d{4})(?: \|)+ ([^|]+)", t):
        s = m.group(4)
        if "monetary policy meeting" in s and "non-monetary" not in s and ("Day 2" in s or "press conference" in s):
            out.append((dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))), s.strip(), url))
    return out


def boj():
    url = "https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm"
    h = get(url, timeout=40).decode("utf-8", "ignore")
    out = []
    ab = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "June": 6, "July": 7, "Aug": 8, "Sept": 9, "Oct": 10, "Nov": 11, "Dec": 12}
    for y in (HOY.year, HOY.year + 1):
        i = h.find(f"Table : {y}")
        if i < 0:
            continue
        j = h.find("</table>", i)
        for tr in re.findall(r"<tr.*?</tr>", h[i:j], re.S):
            tds = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)
            if not tds:
                continue
            c = re.sub(r"\s+", " ", re.sub("<[^>]+>", "", tds[0]))
            m = re.match(r"(Jan|Feb|Mar|Apr|May|June|July|Aug|Sept|Oct|Nov|Dec)\.? (\d+) \([^)]*\)(?:, (?:(Jan|Feb|Mar|Apr|May|June|July|Aug|Sept|Oct|Nov|Dec)\.? )?(\d+))?", c)
            if m:
                mes = ab[m.group(3) or m.group(1)]
                dia = int(m.group(4) or m.group(2))
                out.append((dt.date(y, mes, dia), url))
    return out


def subastas():
    url = "https://www.treasurydirect.gov/TA_WS/securities/upcoming?format=json"
    d = get_json(url)
    out = []
    for x in d:
        if x.get("securityType") in ("Note", "Bond", "TIPS") or "TIPS" in (x.get("securityTerm") or ""):
            f = dt.date.fromisoformat(x["auctionDate"][:10])
            hc = x.get("closingTimeCompetitive") or ""
            hora = None
            m = re.match(r"(\d+):(\d+) (AM|PM)", hc)
            if m:
                hora = f"{int(m.group(1)) % 12 + (12 if m.group(3) == 'PM' else 0):02d}:{m.group(2)}"
            imp = x.get("offeringAmount")
            out.append((f, hora, f"Subasta del Tesoro {x['securityType']} {x['securityTerm']}" + (f" ({float(imp) / 1e9:,.0f} MM$)" if imp else ""), url))
    return out


def construir(dias=21, pasado=7, con_resultados=True):
    desde, hasta = HOY - dt.timedelta(days=pasado), HOY + dt.timedelta(days=dias)
    years = sorted({desde.year, hasta.year})
    E, err = [], {}
    for rid, (nm, imp, af, qm) in FRED_RELEASES.items():
        r, e = safe(fred_calendar, rid, years)
        if e:
            err[f"fred_{rid}"] = e
            continue
        for d, h, nombre_fred, url in r:
            if desde <= d <= hasta:
                E.append(ev(d, h, nm, imp, af, qm, f"FRED Release Calendar · {nombre_fred}", url))
    r, e = safe(fomc)
    if r:
        for d, sep, url in r:
            if desde <= d <= hasta:
                E.append(ev(d, "14:00", "Decisión FOMC (Fed)" + (" + proyecciones (SEP)" if sep else ""), "ALTA", "cripto · oro · índices",
                            "Tipo oficial, comunicado y rueda de prensa (14:30 NY). Mirar 2Y y FedWatch.", "Federal Reserve", url))
    else:
        err["fomc"] = e
    r, e = safe(ism)
    if r:
        for d, tipo, url in r:
            if desde <= d <= hasta:
                E.append(ev(d, "10:00", f"ISM {tipo}", "ALTA" if tipo == "manufacturero" else "MEDIA", "índices · oro",
                            "≥ 50 expansión, < 50 contracción; precios pagados = presión inflacionista.", "ISM (Institute for Supply Management)", url))
    else:
        err["ism"] = e
    r, e = safe(bce)
    if r:
        for d, s, url in r:
            if desde <= d <= hasta:
                E.append(ev(d, None, "Decisión de política monetaria del BCE", "MEDIA", "oro · índices (vía EUR/DXY)",
                            "Tipos del BCE → EUR → DXY (el euro pesa el 57,6 % del DXY).", "Banco Central Europeo", url, "hora de publicación: ver BCE"))
    else:
        err["bce"] = e
    r, e = safe(boj)
    if r:
        for d, url in r:
            if desde <= d <= hasta:
                E.append(ev(d, None, "Decisión de política monetaria del Banco de Japón (día 2)", "MEDIA", "cripto · oro · índices (vía yen/carry)",
                            "Subidas del BoJ → yen ↑ → posible deshacer carry trade (volatilidad global).", "Bank of Japan", url, "hora de publicación variable (sin hora fija oficial)"))
    else:
        err["boj"] = e
    r, e = safe(subastas)
    if r:
        for d, h, s, url in r:
            if desde <= d <= hasta:
                E.append(ev(d, h, s, "MEDIA", "índices · oro", "Demanda débil (cola) → yields ↑.", "TreasuryDirect (U.S. Treasury)", url,
                            "" if h else "hora de cierre aún no anunciada"))
    else:
        err["subastas"] = e
    if con_resultados:
        try:
            import resultados
            R = resultados.proximos(hasta)
            for x in R:
                d = dt.date.fromisoformat(x["fecha"])
                if desde <= d <= hasta:
                    E.append(ev(d, None, f"Resultados {x['empresa']} ({x['simbolo']})", "ALTA" if x["simbolo"] in resultados.CLAVE else "MEDIA",
                                "índices", f"BPA estimado {x['bpa_estimado']} · {x['momento']}", "Nasdaq / Zacks", x["url"],
                                "fecha CONFIRMADA" if x["confirmada"] else "fecha ESTIMADA por algoritmo (Zacks); puede cambiar"))
        except Exception as ex:  # noqa: BLE001
            err["resultados"] = f"{type(ex).__name__}: {ex}"
    prox = {}
    for nm, fn, idx in (("Fed (FOMC)", fomc, 0), ("BCE", bce, 0), ("Banco de Japón", boj, 0)):
        r, e = safe(fn)
        if r:
            fut = sorted(x[idx] for x in r if x[idx] >= HOY)
            if fut:
                prox[nm] = {"fecha": fut[0].isoformat(), "dias": (fut[0] - HOY).days}
    orden = {"ALTA": 0, "MEDIA": 1, "BAJA": 2}
    E.sort(key=lambda x: (x["fecha"], x["hora_ny"] or "99", orden[x["importancia"]]))
    return {"generado": dt.datetime.now(MAD).strftime("%Y-%m-%d %H:%M Madrid"), "desde": desde.isoformat(), "hasta": hasta.isoformat(),
            "eventos": E, "proximos_bancos_centrales": prox, "errores": err,
            "nota": "Horas oficiales convertidas a Nueva York y Madrid con cambio de horario incluido. Las fechas de FRED las publican los organismos y pueden cambiar (p. ej., cierre del Gobierno)."}


def to_md(C):
    L = [f"# Calendario macro oficial · {C['desde']} → {C['hasta']} · generado {C['generado']}", "", C["nota"], "",
         "| Fecha | Hora Madrid | Hora NY | Evento | Imp. | Afecta | Qué mirar | Fuente |", "|---|---|---|---|---|---|---|---|"]
    for e in C["eventos"]:
        pas = " (publicado)" if e["fecha"] < HOY.isoformat() else ""
        L.append(f"| {e['dia']} {e['fecha']}{pas} | {e['hora_madrid'] or '—'} | {e['hora_ny'] or '—'} | {e['evento']}{(' · ' + e['nota']) if e['nota'] else ''} | {e['importancia']} | {e['afecta']} | {e['que_mirar']} | [{e['fuente']}]({e['url']}) |")
    if C.get("proximos_bancos_centrales"):
        L += ["", "Próximas decisiones de bancos centrales: " + " · ".join(f"{k} {v['fecha']} (en {v['dias']} días)" for k, v in C["proximos_bancos_centrales"].items())]
    if C["errores"]:
        L += ["", "Fuentes no disponibles (SIN DATO): " + "; ".join(f"{k}: {v}" for k, v in C["errores"].items())]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=21)
    ap.add_argument("--pasado", type=int, default=7)
    ap.add_argument("--out", default="out")
    ap.add_argument("--sin-resultados", action="store_true")
    a = ap.parse_args()
    C = construir(a.dias, a.pasado, not a.sin_resultados)
    os.makedirs(a.out, exist_ok=True)
    p = os.path.join(a.out, f"calendario_{HOY.strftime('%Y%m%d')}.json")
    json.dump(C, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(p.replace(".json", ".md"), "w", encoding="utf-8").write(to_md(C))
    print(p)
    print(f"{len(C['eventos'])} eventos · errores: {C['errores']}")


if __name__ == "__main__":
    main()


def html_tabla(C, desde, afecta=None, num=""):
    """Sección HTML autocontenida (estilos en línea) para insertar en los informes PDF de los monitores.
    afecta: 'cripto' | 'oro' | 'índices' filtra por el campo «afecta»; solo importancia ALTA y MEDIA desde la fecha `desde`."""
    import html as _h
    e_ = _h.escape
    ev_ = [e for e in (C or {}).get("eventos", []) if e["fecha"] >= desde and e["importancia"] in ("ALTA", "MEDIA") and (not afecta or afecta in e["afecta"])]
    if not ev_:
        return ""
    ROJO, AMBAR = "#a83240", "#9a7b2f"
    th = "text-align:left;font-size:6.5pt;letter-spacing:.08em;text-transform:uppercase;color:#fff;background:#0d1b2e;padding:1.4mm"
    td = "border-bottom:.5px solid #d0d0d0;padding:1.4mm;vertical-align:top;font-size:7.6pt"
    rows = ""
    for e in ev_:
        nota = f"<div style='font-size:6.5pt;color:#8b95a8'>{e_(e['nota'])}</div>" if e["nota"] else ""
        col = ROJO if e["importancia"] == "ALTA" else AMBAR
        rows += (f"<tr style='page-break-inside:avoid'><td style='{td}'>{e_(e['dia'])} {e_(e['fecha'][5:])}</td><td style='{td}'>{e_(e['hora_madrid'] or '—')}</td>"
                 f"<td style='{td}'><b>{e_(e['evento'])}</b>{nota}</td><td style='{td};color:{col};font-weight:bold'>{e_(e['importancia'])}</td>"
                 f"<td style='{td}'>{e_(e['que_mirar'])}</td></tr>")
    cb = " · ".join(f"{k} {v['fecha']} (en {v['dias']} días)" for k, v in (C.get("proximos_bancos_centrales") or {}).items())
    return (f"<h2><span class='n'>{e_(str(num))}</span>Calendario oficial de las próximas semanas</h2>"
            "<table style='width:100%;border-collapse:collapse;table-layout:fixed;margin:1.5mm 0 3mm 0'><colgroup><col style='width:10%'><col style='width:8%'><col style='width:32%'><col style='width:9%'><col style='width:41%'></colgroup>"
            f"<tr><th style='{th}'>Fecha</th><th style='{th}'>Madrid</th><th style='{th}'>Evento</th><th style='{th}'>Imp.</th><th style='{th}'>Qué mirar</th></tr>{rows}</table>"
            f"<div style='font-size:6.5pt;color:#8b95a8'>Próximos bancos centrales: {e_(cb)}. Fuentes oficiales: FRED Release Calendar (BLS, BEA, Census, Fed, DOL), Federal Reserve, ISM, BCE, Banco de Japón, TreasuryDirect; resultados: Nasdaq/Zacks. Horas convertidas a Madrid.</div>")
