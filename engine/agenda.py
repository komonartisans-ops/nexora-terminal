#!/usr/bin/env python3
"""NEXORA · AGENDA a partir de los calendarios OFICIALES (calendario.py) + Telegram diario de las 8:00 Madrid.

  · Importancia ALTA/MEDIA fija por tipo de evento (tabla publicada en site/data/agenda.json y en la web).
  · eventos_altos(): TODOS los eventos de importancia alta con hora conocida, para el monitor de reacciones (no hay lista fija).
  · bloque(): hoy y próximos 7 días con hora ET y hora Madrid (contexto.json).
  · diario(): mensaje de Telegram de cada día laborable a las 8:00 Madrid (una línea si no hay nada de importancia alta).

    python agenda.py --diario [--forzar]     (job agenda_diaria.yml; idempotente por día)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import zoneinfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

NY, MAD, UTC = zoneinfo.ZoneInfo("America/New_York"), zoneinfo.ZoneInfo("Europe/Madrid"), dt.timezone.utc
ROOT = os.path.dirname(HERE)
DATA, SITE_DATA = os.path.join(ROOT, "data"), os.path.join(ROOT, "site", "data")
ESTADO = os.path.join(DATA, "estado_agenda.json")
MIN_TXT_DIA = {0: "lun", 1: "mar", 2: "mié", 3: "jue", 4: "vie", 5: "sáb", 6: "dom"}


# ------------------------------------------------------------------ tabla publicada
def tabla_importancia():
    """Importancia fija por tipo de evento. La fuente de verdad es calendario.FRED_RELEASES (+ FOMC, ISM, actas, BCE, BoJ, subastas)."""
    import calendario as C
    T = []
    for rid, (nm, imp, af, qm) in C.FRED_RELEASES.items():
        org = {50: "BLS", 10: "BLS", 46: "BLS", 192: "BLS", 188: "BLS", 54: "BEA", 53: "BEA", 9: "Census", 27: "Census", 97: "Census", 95: "Census", 13: "Fed", 20: "Fed", 21: "Fed",
               22: "Fed", 180: "DOL", 351: "Fed de Filadelfia", 91: "U. Michigan"}.get(rid, "FRED")
        T.append({"tipo": C.TIPO_FRED.get(rid, str(rid)), "evento": nm, "organismo": org, "importancia": imp, "hora_ny_tipica": C.HORA_TIPICA_NY.get(C.TIPO_FRED.get(rid, ""), ""),
                  "fuente": f"FRED Release Calendar (rid {rid})"})
    T += [{"tipo": "FOMC", "evento": "Decisión FOMC (Fed)", "organismo": "Fed", "importancia": "ALTA", "hora_ny_tipica": "14:00", "fuente": "federalreserve.gov"},
          {"tipo": "ACTAS", "evento": "Actas del FOMC", "organismo": "Fed", "importancia": "ALTA", "hora_ny_tipica": "14:00", "fuente": "federalreserve.gov/json/calendar.json"},
          {"tipo": "DISCURSO", "evento": "Discursos y comparecencias del presidente de la Fed", "organismo": "Fed", "importancia": "ALTA", "hora_ny_tipica": "", "fuente": "federalreserve.gov/json/calendar.json"},
          {"tipo": "DISCURSOS", "evento": "Discursos y comparecencias de votantes del FOMC", "organismo": "Fed", "importancia": "MEDIA", "hora_ny_tipica": "", "fuente": "federalreserve.gov/json/calendar.json"},
          {"tipo": "ISM", "evento": "ISM manufacturero", "organismo": "ISM", "importancia": "ALTA", "hora_ny_tipica": "10:00", "fuente": "ismworld.org"},
          {"tipo": "ISM_SERV", "evento": "ISM servicios", "organismo": "ISM", "importancia": "MEDIA", "hora_ny_tipica": "10:00", "fuente": "ismworld.org"},
          {"tipo": "SUBASTA", "evento": "Subastas del Tesoro a 2, 10 y 30 años (resto de plazos: BAJA)", "organismo": "Tesoro", "importancia": "MEDIA", "hora_ny_tipica": "13:00", "fuente": "TreasuryDirect"},
          {"tipo": "BCE", "evento": "Decisión de política monetaria del BCE", "organismo": "BCE", "importancia": "MEDIA", "hora_ny_tipica": "", "fuente": "ecb.europa.eu"},
          {"tipo": "BOJ", "evento": "Decisión de política monetaria del Banco de Japón", "organismo": "BoJ", "importancia": "MEDIA", "hora_ny_tipica": "", "fuente": "boj.or.jp"},
          {"tipo": "EIA", "evento": "Inventarios de petróleo (EIA, Weekly Petroleum Status Report)", "organismo": "EIA", "importancia": "MEDIA", "hora_ny_tipica": "10:30", "fuente": "eia.gov (calendario oficial; festivos en la tabla de excepciones)"},
          {"tipo": "OPEP", "evento": "Reuniones de la OPEP+ (ALTA si hay calendario oficial accesible; hoy SIN DATO: opec.org bloquea el acceso automático)", "organismo": "OPEP", "importancia": "ALTA", "hora_ny_tipica": "", "fuente": "opec.org"}]
    orden = {"ALTA": 0, "MEDIA": 1, "BAJA": 2}
    return sorted(T, key=lambda x: (orden[x["importancia"]], x["tipo"]))


# ------------------------------------------------------------------ eventos de importancia alta (para el monitor de reacciones)
def eventos_altos(desde, hasta):
    """[{id, tipo, evento, fecha(date), hora_ny, fuente, url}] de TODOS los eventos ALTA con hora conocida entre desde y hasta (ambos incluidos).
    Cada fuente falla por separado (SIN DATO), nunca el conjunto."""
    import calendario as C
    out, years = {}, sorted({desde.year, hasta.year})

    def add(tipo, d, h, nombre, fuente, url):
        if desde <= d <= hasta and (h or C.HORA_TIPICA_NY.get(tipo)):
            out[f"{tipo}-{d}"] = {"id": f"{tipo}-{d}", "tipo": tipo, "evento": nombre, "fecha": d, "hora_ny": h or C.HORA_TIPICA_NY[tipo], "fuente": fuente, "url": url}
    for rid, (nm, imp, af, qm) in C.FRED_RELEASES.items():
        if imp != "ALTA":
            continue
        try:
            for d, h, nombre, url in C.fred_calendar(rid, years):
                add(C.TIPO_FRED[rid], d, h, nm, f"FRED Release Calendar · {nombre}", url)
        except Exception as e:  # noqa: BLE001
            print(f"agenda {C.TIPO_FRED.get(rid)}: {type(e).__name__}: {str(e)[:80]}")
    try:
        for d, sep, url in C.fomc():
            add("FOMC", d, "14:00", "Decisión FOMC (Fed)", "federalreserve.gov (calendario FOMC)", url)
    except Exception as e:  # noqa: BLE001
        print(f"agenda FOMC: {type(e).__name__}: {str(e)[:80]}")
    try:
        for d, tipo, url in C.ism():
            if tipo == "manufacturero":
                add("ISM", d, "10:00", "ISM manufacturero", "ISM (Institute for Supply Management)", url)
    except Exception as e:  # noqa: BLE001
        print(f"agenda ISM: {type(e).__name__}: {str(e)[:80]}")
    try:
        for x in C.fed_votantes(dias=max(1, (hasta - C.HOY).days)):
            if x.get("tipo") == "FOMC" and "Minutes" in x["evento"] and x["hora_ny"]:
                add("ACTAS", dt.date.fromisoformat(x["fecha"]), x["hora_ny"], "Actas del FOMC", "Federal Reserve (calendario oficial)", x["url"])
    except Exception as e:  # noqa: BLE001
        print(f"agenda ACTAS: {type(e).__name__}: {str(e)[:80]}")
    try:
        for x in C.fed_votantes(dias=max(1, (hasta - C.HOY).days)):
            if x.get("presidente") and x["hora_ny"]:
                add("DISCURSO", dt.date.fromisoformat(x["fecha"]), x["hora_ny"], "Discurso del presidente de la Fed: " + x["evento"], "Federal Reserve (calendario oficial)", x["url"])
    except Exception as e:  # noqa: BLE001
        print(f"agenda DISCURSO: {type(e).__name__}: {str(e)[:80]}")
    # varios ALTA a la misma hora → un único evento combinado («PPI + Ventas minoristas»)
    grupos = {}
    for x in sorted(out.values(), key=lambda x: (x["fecha"], x["hora_ny"], x["tipo"])):
        grupos.setdefault((x["fecha"], x["hora_ny"]), []).append(x)
    res = []
    for (d, h), g in grupos.items():
        if len(g) == 1:
            res.append(g[0])
            continue
        g.sort(key=lambda x: ETIQUETA_ORDEN.get(x["tipo"], 50))
        tipo = "+".join(x["tipo"] for x in g)
        res.append({"id": f"{tipo}-{d}", "tipo": tipo, "evento": " + ".join(ETIQUETA.get(x["tipo"], x["evento"]) for x in g), "fecha": d, "hora_ny": h,
                    "combinado": [x["tipo"] for x in g], "fuente": " | ".join(sorted({x["fuente"] for x in g})), "url": g[0]["url"]})
    return sorted(res, key=lambda x: (x["fecha"], x["hora_ny"]))


ETIQUETA = {"PPI": "PPI", "VENTAS": "Ventas minoristas", "IPC": "IPC", "NFP": "Empleo (NFP)", "PCE": "PCE", "PIB": "PIB", "ECI": "Costes laborales (ECI)", "FOMC": "FOMC",
            "ACTAS": "Actas del FOMC", "ISM": "ISM manufacturero", "DISCURSO": "Discurso del presidente de la Fed"}
ETIQUETA_ORDEN = {k: i for i, k in enumerate(ETIQUETA)}


# ------------------------------------------------------------------ agenda para contexto.json y Telegram
def _todos(cal):
    """Eventos del calendario + discursos/actas de votantes, normalizados."""
    E = list((cal or {}).get("eventos") or [])
    vistos = {(e["fecha"], e["evento"]) for e in E}
    for x in (cal or {}).get("fed_vigilar") or []:
        if (x["fecha"], x["evento"]) not in vistos:
            E.append(x)
    return E


def bloque(cal, hoy=None, dias=7):
    hoy = hoy or dt.datetime.now(MAD).date()
    lim = hoy + dt.timedelta(days=dias)
    fm = lambda e: e.get("fecha_madrid") or e["fecha"]   # el día que importa es el de Madrid (un acto de 23:30 ET es del día siguiente aquí)
    E = [e for e in _todos(cal) if hoy.isoformat() <= fm(e) <= lim.isoformat() and e.get("importancia") in ("ALTA", "MEDIA")]
    E.sort(key=lambda e: (fm(e), e.get("hora_madrid") or "99", 0 if e["importancia"] == "ALTA" else 1))
    dia = lambda e: ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"][dt.date.fromisoformat(fm(e)).weekday()]  # el día de la semana es el de Madrid, como la fecha mostrada
    f = lambda e: {"fecha": fm(e), "fecha_et": e["fecha"], "dia": dia(e), "hora_ny": e.get("hora_ny") or None, "hora_madrid": e.get("hora_madrid") or None,
                   "evento": e["evento"], "importancia": e["importancia"], "nota": e.get("nota") or None}
    return {"hoy": [f(e) for e in E if fm(e) == hoy.isoformat()], "proximos_7_dias": [f(e) for e in E if fm(e) > hoy.isoformat()],
            "regla_horas": "Fed: horas del calendario oficial en ET (también en actos en el extranjero); FRED: hora central → ET; todo se convierte a Madrid y el día es el de Madrid.",
            "hasta": lim.isoformat(), "fuente": "Calendarios oficiales: FRED Release Calendar (BLS, BEA, Census), Federal Reserve, ISM, BCE, BoJ, TreasuryDirect",
            "importancia": "Fija por tipo de evento (tabla en site/data/agenda.json)", "generado_utc": dt.datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")}


def escribir_json(cal):
    os.makedirs(SITE_DATA, exist_ok=True)
    J = {"generado_utc": dt.datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"), "tabla_importancia": tabla_importancia(), "agenda": bloque(cal),
         "contaminacion": "Una fase de un evento de importancia alta se marca «contaminada» si otro evento de importancia alta se publica entre el dato y esa fase."}
    json.dump(J, open(os.path.join(SITE_DATA, "agenda.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return J


def texto_diario(cal, hoy=None):
    import html
    hoy = hoy or dt.datetime.now(MAD).date()
    B = bloque(cal, hoy, 0)
    altos = [e for e in B["hoy"] if e["importancia"] == "ALTA"]
    cab = f"<b>NEXORA · Agenda {MIN_TXT_DIA[hoy.weekday()]} {hoy.strftime('%d-%m-%Y')}</b>"
    if not altos:
        return f"{cab}\nHoy sin datos de importancia alta"
    L = [cab, "Hoy, hora de Madrid:"]
    grupos = {}
    for e in altos:  # varios datos altos a la misma hora se muestran juntos (el monitor los registra como un único evento combinado)
        grupos.setdefault((e["hora_madrid"] or "", e["hora_ny"] or ""), []).append(e["evento"])
    for (hm, hn), nombres in grupos.items():
        L.append(f"• <b>{html.escape(hm or 'hora sin confirmar')}</b> · {html.escape(' + '.join(nombres))}" + (f" ({html.escape(hn)} ET)" if hn else "")
                 + (" · dato combinado" if len(nombres) > 1 else ""))
    med = [e for e in B["hoy"] if e["importancia"] == "MEDIA"]
    ahora = dt.datetime.now(MAD)
    if hoy == ahora.date():  # «Media» solo muestra lo que falta por salir (los que no tienen hora se conservan)
        med = [e for e in med if not e["hora_madrid"] or e["hora_madrid"] >= ahora.strftime("%H:%M")]
    if med:
        L.append("Media: " + "; ".join(f"{html.escape(e['hora_madrid'] or '—')} {html.escape(e['evento'])}" for e in med[:5]))
    return "\n".join(L)


def diario(forzar=False):
    import calendario as C
    import telegram
    ahora = dt.datetime.now(MAD)
    hoy = ahora.date()
    if hoy.weekday() >= 5 and not forzar:
        print("fin de semana: sin agenda diaria")
        return 0
    try:
        est = json.load(open(ESTADO, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        est = {"enviados": []}
    if hoy.isoformat() in est["enviados"] and not forzar:
        print("ya enviada hoy")
        return 0
    if ahora.hour < 8 and not forzar:
        print(f"{ahora:%H:%M} Madrid: aún no son las 8:00; lo enviará el otro cron")
        return 0
    try:
        cal = C.construir(dias=8, pasado=1, con_resultados=False)
    except Exception as e:  # noqa: BLE001
        print("calendario en vivo no disponible:", type(e).__name__)
        cal = None
    if not cal or not cal.get("eventos"):
        try:
            cal = json.load(open(os.path.join(SITE_DATA, "calendario.json"), encoding="utf-8"))
        except Exception:  # noqa: BLE001
            cal = None
    if not cal:
        txt = "<b>NEXORA · Agenda</b>\nSIN DATO: no se ha podido leer el calendario oficial hoy"
    else:
        txt = texto_diario(cal, hoy)
    print(txt)
    if not telegram.configurado():
        print("Telegram sin configurar")
        return 0
    ok, err = telegram.enviar(txt)
    if ok:
        est["enviados"] = (est["enviados"] + [hoy.isoformat()])[-30:]
        os.makedirs(DATA, exist_ok=True)
        json.dump(est, open(ESTADO, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    else:
        print("Telegram:", err)
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--diario", action="store_true")
    ap.add_argument("--forzar", action="store_true")
    a = ap.parse_args()
    if a.diario:
        return diario(a.forzar)
    import calendario as C
    cal = C.construir(8, 1, False)
    print(texto_diario(cal))
    return 0


if __name__ == "__main__":
    sys.exit(main())
