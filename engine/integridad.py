#!/usr/bin/env python3
"""NEXORA · integridad de datos. Sin IA, gratis, solo-añadir. No toca umbrales, criterios ni reglas v3: solo MIRA y avisa.

  1. VIGILANTE de publicaciones: para cada evento de agenda con serie asociada (IPC, IPP, NFP, paro, ventas, PCE, PIB, JOLTS, peticiones, producción industrial),
     si a hora de publicación + 2 h el periodo nuevo NO está en publicados.json → Telegram «DATO NO REGISTRADO: <dato> de <mes>, publicado a las <hora>».
     Un aviso por dato (data/vigilante_estado.json, solo-añadir). Se comprueba en los runs horarios (build) y en «reacciones» (modo vivo).
  2. SEGUNDA FUENTE: IPC, IPC subyacente e IPP frente a la API pública de BLS (sin clave). Si el índice difiere > 0,05 % o el periodo no coincide → DISCREPANCIA
     (data/discrepancias.csv, solo-añadir; se cierra con una fila CERRADA). Manda la fuente primaria (BLS). PIB y PCE: la API de BEA exige clave → SIN DATO.
  3. PUBLICACIÓN OFICIAL de cada dato (ALFRED, el archivo de versiones de FRED, sin clave): fecha en que FRED/ALFRED recogió por primera vez cada periodo
     (data/publicacion_oficial.csv, solo-añadir). Con ella se mide el retraso de registro de NEXORA.
  4. site/data/integridad.json: semáforo por bloque de la web (al día / retrasado / SIN DATO), próximo dato esperado, discrepancias abiertas y retrasos de registro.
Nada se inventa: sin dato = SIN DATO."""
from __future__ import annotations

import csv
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.request
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(HERE)
sys.path.insert(0, HERE)

UTC, NY, MAD = dt.timezone.utc, ZoneInfo("America/New_York"), ZoneInfo("Europe/Madrid")
ESPERA_VIGILANTE_H = 2          # el dato debe estar registrado 2 h después de su publicación
VENTANA_VIGILANTE_H = 48        # solo se avisa dentro de las 48 h siguientes (más allá ya no es un aviso útil)
UMBRAL_DISCREPANCIA_PCT = 0.05
BLS_MAX_DIA = 8
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
MES_CORTO = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

# serie FRED → serie primaria de BLS (índices en el mismo nivel que FRED)
BLS = {"CPIAUCSL": "CUSR0000SA0", "CPILFESL": "CUSR0000SA0L1E", "PPIFIS": "WPSFD4"}
BEA_SIN_DATO = "BEA exige clave de API (UserID): sin el secreto BEA_API_KEY no hay acceso, SIN DATO (no se inventa)."
# NIPA: índice de precios PCE (mensual, T20804) y PIB real (trimestral, T10106). Línea = descripción EXACTA (verificada con la API real: T20804 línea 1, línea 25 y T10106 línea 1).
# Divisor: BEA da el nivel en dólares × 10^UNIT_MULT (T10106: millones); FRED GDPC1 está en miles de millones de dólares → se divide por 1e9. Los índices (UNIT_MULT=0) no cambian.
BEA_TABLAS = {"PCEPI": ("T20804", "M", "personal consumption expenditures (pce)", 1.0), "PCEPILFE": ("T20804", "M", "pce excluding food and energy", 1.0),
              "GDPC1": ("T10106", "Q", "gross domestic product", 1e9)}
SEGUNDA_FUENTE = {"CPIAUCSL": "BLS", "CPILFESL": "BLS", "PPIFIS": "BLS", "PCEPI": "BEA", "PCEPILFE": "BEA", "GDPC1": "BEA"}


def P(raiz, *a):
    return os.path.join(raiz, *a)


def leer_json(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def leer_csv(ruta):
    if not os.path.exists(ruta):
        return []
    with open(ruta, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def anadir_csv(ruta, filas, campos, clave):
    """Solo-añadir: añade las filas con clave nueva; nunca modifica ni borra las anteriores."""
    vistas = {clave(r) for r in leer_csv(ruta)}
    nuevas = []
    for r in filas:
        k = clave(r)
        if k not in vistas:
            vistas.add(k)
            nuevas.append(r)
    if nuevas:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        existe = os.path.exists(ruta)
        with open(ruta, "a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
            if not existe:
                w.writeheader()
            for r in nuevas:
                w.writerow({c: r.get(c, "") for c in campos})
    return nuevas


def series_vigiladas():
    """Series de datos_macro.VISTA con su tipo de periodo y el retraso (en meses) del periodo que publica cada evento."""
    import datos_macro as DM
    out = []
    for nombre, sid, modo, dec, unidad, desc, claves, n in DM.VISTA:
        tipo = "semana" if sid == "ICSA" else "trimestre" if (modo == "qoq_anual" or sid in DM.TRIMESTRALES) else "mes"
        out.append({"nombre": nombre, "sid": sid, "modo": modo, "claves": claves, "tipo": tipo, "lag_m": 2 if sid == "JTSJOL" else 1, "unidad": unidad})
    return out


# ---------------------------------------------------------------- periodos
def periodo_esperado(tipo, lag_m, d):
    """Periodo (primer día) que publica un evento de fecha d (ET)."""
    if tipo == "semana":
        return d - dt.timedelta(days=((d.weekday() - 5) % 7) or 7)      # el sábado que cierra la semana de referencia
    if tipo == "trimestre":
        q0 = ((d.month - 1) // 3) * 3 + 1 - 3
        y = d.year - (1 if q0 < 1 else 0)
        return dt.date(y, q0 + 12 if q0 < 1 else q0, 1)
    m = d.month - lag_m
    y = d.year
    while m < 1:
        m += 12
        y -= 1
    return dt.date(y, m, 1)


def fin_periodo(p, tipo):
    if tipo == "semana":
        return p
    n = 3 if tipo == "trimestre" else 1
    m = p.month - 1 + n
    return dt.date(p.year + m // 12, m % 12 + 1, 1) - dt.timedelta(days=1)


def texto_periodo(p, tipo):
    if tipo == "semana":
        return f"semana del {p.day} {MES_CORTO[p.month - 1]} {p.year}"
    if tipo == "trimestre":
        return f"T{(p.month - 1) // 3 + 1} {p.year}"
    return f"{MESES[p.month - 1]} {p.year}"


CORTO = {"CPIAUCSL": "IPC", "CPILFESL": "IPC subyacente", "PAYEMS": "Nóminas (NFP)", "UNRATE": "Tasa de paro", "ICSA": "Peticiones de paro", "RSAFS": "Ventas minoristas",
         "PPIFIS": "IPP", "GDPC1": "PIB", "PCEPI": "PCE", "PCEPILFE": "PCE subyacente", "INDPRO": "Producción industrial", "JTSJOL": "JOLTS"}


def etiqueta_proximo(nombre, p, tipo, sid=None):
    base = CORTO.get(sid) or nombre.split(" (")[0].replace("EE. UU.", "").replace("Empleo · ", "").strip()
    if tipo == "semana":
        return f"{base} de la {texto_periodo(p, tipo)}"
    if tipo == "trimestre":
        return f"{base} de {texto_periodo(p, tipo)}"
    return f"{base} de {MESES[p.month - 1]}"


# ---------------------------------------------------------------- eventos (agenda + calendario)
def eventos(raiz):
    """[{fecha (ET), hora_ny, evento, t (UTC)}] con hora confirmada, de agenda.json y calendario.json (sin duplicados)."""
    out, vistos = [], set()
    A = (leer_json(P(raiz, "site", "data", "agenda.json")) or {}).get("agenda") or {}
    C = (leer_json(P(raiz, "site", "data", "calendario.json")) or {}).get("eventos") or []
    for e in (A.get("hoy") or []) + (A.get("proximos_7_dias") or []):
        out.append({"fecha": e.get("fecha_et") or e.get("fecha"), "hora_ny": e.get("hora_ny"), "evento": e.get("evento", ""), "importancia": e.get("importancia")})
    for e in C:
        out.append({"fecha": e.get("fecha"), "hora_ny": e.get("hora_ny"), "evento": e.get("evento", ""), "importancia": e.get("importancia")})
    res = []
    for e in out:
        if not e["fecha"] or not e["hora_ny"]:
            continue
        k = (e["fecha"], e["hora_ny"], e["evento"])
        if k in vistos:
            continue
        vistos.add(k)
        h, m = map(int, e["hora_ny"].split(":"))
        e["t"] = dt.datetime.combine(dt.date.fromisoformat(e["fecha"]), dt.time(h, m), NY).astimezone(UTC)
        res.append(e)
    return sorted(res, key=lambda x: x["t"])


def coincide(ev, claves):
    n = ev["evento"].lower()
    return any(c in n for c in claves)


# ---------------------------------------------------------------- 1) vigilante
def _estado_v(raiz):
    return leer_json(P(raiz, "data", "vigilante_estado.json")) or {"creado_utc": None, "avisos": {}}


def _guardar_v(raiz, est, nuevos):
    """Solo-añadir: relee y añade las claves nuevas; una clave existente nunca se modifica."""
    actual = _estado_v(raiz)
    actual["creado_utc"] = actual.get("creado_utc") or est.get("creado_utc")
    for k, v in nuevos.items():
        actual["avisos"].setdefault(k, v)
    os.makedirs(P(raiz, "data"), exist_ok=True)
    with open(P(raiz, "data", "vigilante_estado.json"), "w", encoding="utf-8") as f:
        json.dump(actual, f, ensure_ascii=False, indent=1)


def pendientes_vigilante(raiz, ahora):
    """[(serie, evento, periodo, t_evento)] cuyo periodo esperado no está en publicados.json a evento + 2 h (dentro de las 48 h siguientes)."""
    pub = (leer_json(P(raiz, "site", "data", "publicados.json")) or {}).get("series") or {}
    out = []
    for ev in eventos(raiz):
        dt_h = (ahora - ev["t"]).total_seconds() / 3600
        if not (ESPERA_VIGILANTE_H <= dt_h <= VENTANA_VIGILANTE_H):
            continue
        d = dt.date.fromisoformat(ev["fecha"])
        for s in series_vigiladas():
            if not coincide(ev, s["claves"]):
                continue
            p = periodo_esperado(s["tipo"], s["lag_m"], d)
            reg = {x["periodo"] for x in ((pub.get(s["nombre"]) or {}).get("periodos") or [])}
            if p.isoformat() not in reg:
                out.append((s, ev, p))
    import petroleo                                    # petróleo: informe semanal de la EIA (su fuente es el propio informe, no publicados.json)
    for semana, t in petroleo.pendientes_eia(raiz, ahora):
        out.append(({"nombre": "Inventarios de petróleo EIA", "sid": "WPSR", "tipo": "semana", "eia": True, "claves": []},
                    {"t": t, "fecha": t.date().isoformat(), "evento": "Inventarios semanales de petróleo (EIA)"}, semana))
    import michigan                                    # U. Michigan (preliminar y final): su fuente es la propia Universidad, no publicados.json
    for tipo, per, t, fecha, fuente in michigan.pendientes(raiz, ahora):
        out.append(({"nombre": f"Confianza U. Michigan ({tipo})", "sid": "UMCSENT", "tipo": "mes", "michigan": tipo, "claves": []},
                    {"t": t, "fecha": fecha, "evento": f"Confianza del consumidor U. Michigan, {tipo}", "fuente": fuente}, per))
    return out


def mensaje_vigilante(s, ev, p):
    from telegram import esc
    hm = ev["t"].astimezone(MAD).strftime("%H:%M")
    if s.get("eia"):
        return (f"<b>DATO NO REGISTRADO:</b> {esc(s['nombre'])} de la semana al {p.day:02d}-{p.month:02d}-{p.year}, publicado a las {hm} (Madrid)\n"
                f"Han pasado más de {ESPERA_VIGILANTE_H} h y NEXORA no lo tiene en data/eia_inventarios.csv (fuente: ir.eia.gov/wpsr/table1.csv). Hecho de integridad, no una señal de mercado.")
    if s.get("michigan"):
        return (f"<b>DATO NO REGISTRADO:</b> {esc(s['nombre'])} de {esc(texto_periodo(p, 'mes'))}, publicado a las {hm} (Madrid)\n"
                f"Han pasado más de {ESPERA_VIGILANTE_H} h y NEXORA no lo tiene en data/michigan.csv (fuente: sca.isr.umich.edu; FRED UMCSENT es solo respaldo y llega con 1-2 meses de retraso). "
                "Hecho de integridad, no una señal de mercado.")
    return (f"<b>DATO NO REGISTRADO:</b> {esc(s['nombre'])} de {esc(texto_periodo(p, s['tipo']))}, publicado a las {hm} (Madrid)\n"
            f"Han pasado más de {ESPERA_VIGILANTE_H} h y NEXORA no lo tiene en publicados.json (FRED {esc(s['sid'])}). Hecho de integridad, no una señal de mercado.")


def vigilar(raiz=RAIZ, ahora=None, seco=False, enviar=None, push=False):
    """Una pasada del vigilante. Devuelve [(clave, estado, texto)]. seco=True: imprime y no envía ni escribe."""
    ahora = ahora or dt.datetime.now(UTC)
    est = _estado_v(raiz)
    if not est.get("creado_utc"):
        est["creado_utc"] = ahora.strftime("%Y-%m-%d %H:%M UTC")
        if not seco:
            _guardar_v(raiz, est, {})
    out, nuevos = [], {}
    for s, ev, p in pendientes_vigilante(raiz, ahora):
        clave = f"{s['nombre']}|{p.isoformat()}"
        if clave in est["avisos"]:
            continue
        txt = mensaje_vigilante(s, ev, p)
        if seco:
            print("[seco · no se envía]\n" + txt + "\n")
            out.append((clave, "SECO", txt))
            continue
        import telegram
        ok, err = (enviar or telegram.enviar)(txt)
        if ok:
            nuevos[clave] = {"estado": "AVISADO", "avisado_utc": ahora.strftime("%Y-%m-%d %H:%M UTC"), "dato": s["nombre"], "periodo": p.isoformat(),
                             "evento": ev["evento"], "publicado_utc": ev["t"].strftime("%Y-%m-%d %H:%M UTC")}
            out.append((clave, "AVISADO", txt))
        else:
            print("vigilante: Telegram no aceptó el aviso (se reintenta):", err)
            out.append((clave, "ERROR", err or ""))
    vc = estado_vigilante_cierre(raiz, ahora)
    if vc["alerta"]:
        clave = f"vigilar_cierre|{vc['ultima_fecha'] or DESDE_VIGILAR_CIERRE}"
        if clave not in est["avisos"]:
            txt = (f"<b>NEXORA · Integridad</b>\nEl vigilante del cierre no ha corrido en {vc['dias_habiles_sin_correr']} días hábiles (último: {vc['ultima_fecha'] or 'ninguno'}). "
                   "Revisa el disparo externo de cron-job.org (tarea C, 22:15 UTC) y el workflow vigilar_cierre.")
            if seco:
                print("[seco · no se envía]\n" + txt + "\n")
                out.append((clave, "SECO", txt))
            else:
                import telegram
                ok, err = (enviar or telegram.enviar)(txt)
                if ok:
                    nuevos[clave] = {"estado": "AVISADO", "avisado_utc": ahora.strftime("%Y-%m-%d %H:%M UTC"), "dato": "vigilar_cierre", "periodo": vc["ultima_fecha"] or DESDE_VIGILAR_CIERRE,
                                     "evento": "el vigilante del cierre no corre", "publicado_utc": ""}
                    out.append((clave, "AVISADO", txt))
                else:
                    print("vigilante: Telegram no aceptó el aviso (se reintenta):", err)
                    out.append((clave, "ERROR", err or ""))
    # Fase 19: un solo aviso por racha (clave = inicio de la racha): spot del oro en ⚠️ 2 sesiones seguidas, o Swissquote sin responder 3 sesiones seguidas
    try:
        import spot_oro
        n1, i1 = spot_oro.racha_dudoso(raiz)
        n2, i2 = spot_oro.racha_swiss_caido(raiz)
        pendientes = []
        if n1 >= 2:
            pendientes.append((f"spot_oro|{i1}", "spot_oro", i1, "spot del oro dudoso 2 sesiones seguidas", spot_oro.mensaje_racha(n1, i1, spot_oro.filas(raiz)[-1])))
        if n2 >= spot_oro.SESIONES_SWISS_CAIDO:
            pendientes.append((f"swiss_caido|{i2}", "swiss_caido", i2, "Swissquote sin responder 3 sesiones seguidas", spot_oro.mensaje_swiss_caido(n2, i2)))
        for clave, dato, periodo, evento, txt in pendientes:
            if clave in est["avisos"]:
                continue
            if seco:
                print("[seco · no se envía]\n" + txt + "\n")
                out.append((clave, "SECO", txt))
                continue
            import telegram
            ok, err = (enviar or telegram.enviar)(txt)
            if ok:
                nuevos[clave] = {"estado": "AVISADO", "avisado_utc": ahora.strftime("%Y-%m-%d %H:%M UTC"), "dato": dato, "periodo": periodo, "evento": evento, "publicado_utc": ""}
                out.append((clave, "AVISADO", txt))
            else:
                print("vigilante: Telegram no aceptó el aviso (se reintenta):", err)
                out.append((clave, "ERROR", err or ""))
    except Exception as e:  # noqa: BLE001
        print("vigilante spot_oro:", type(e).__name__, str(e)[:100])
    # Fase 20: el exportador a Obsidian corre en el PC de Ruiz; si no da señales 2 días seguidos, un aviso por racha
    try:
        ob = estado_latido_obsidian(raiz, ahora)
        if ob.get("pendiente_aprobar"):      # el código del exportador cambió en main: el PC sigue con la versión aprobada hasta que Ruiz la apruebe
            p = ob["pendiente_aprobar"]
            hexa = lambda s: s if re.fullmatch(r"[0-9a-f]{7,40}", str(s or "")) else "?"      # lo que viene del repo no se interpola sin validar
            clave = f"obsidian_pendiente|{hexa(p.get('blob'))}"
            if clave not in est["avisos"]:
                r = p.get("resumen") or {}
                cuerpo = "\n".join(str(x) for x in (r.get("lineas") or []))[:1500]
                num_ = lambda v: v if isinstance(v, int) else "?"
                txt = (f"<b>NEXORA · Exportador actualizado, pendiente de aprobar</b>\nCommit {hexa(p.get('commit'))} (aprobado: {hexa(p.get('aprobado')) if p.get('aprobado') else 'ninguno'}): +{num_(r.get('anade'))} −{num_(r.get('quita'))} líneas en tools/exportar_obsidian.py. "
                       "El PC sigue ejecutando la versión aprobada; los datos se siguen descargando. Resumen orientativo (NO sustituye al diff completo):\n<pre>" + html.escape(cuerpo) + ("\n…" if r.get("truncado") else "") + "</pre>\n"
                       "Para aprobar no uses ningún hash de este mensaje: en tu PC ejecuta la copia anclada sin argumentos, lee el diff completo y el hash que imprime ahí, y repite con ese hash: "
                       "python %LOCALAPPDATA%\\NexoraExportador\\aprobado\\exportar_obsidian.py --aprobar (pedirá escribir APROBAR).")
                if seco:
                    print("[seco · no se envía]\n" + txt + "\n")
                    out.append((clave, "SECO", txt))
                else:
                    import telegram
                    ok, err = (enviar or telegram.enviar)(txt)
                    if ok:
                        nuevos[clave] = {"estado": "AVISADO", "avisado_utc": ahora.strftime("%Y-%m-%d %H:%M UTC"), "dato": "obsidian_pendiente", "periodo": str(p.get("commit")),
                                         "evento": "exportador actualizado, pendiente de aprobar", "publicado_utc": ""}
                        out.append((clave, "AVISADO", txt))
                    else:
                        print("vigilante: Telegram no aceptó el aviso (se reintenta):", err)
                        out.append((clave, "ERROR", err or ""))
        if ob["alerta"]:
            clave = f"obsidian|{ob['racha_desde']}"
            if clave not in est["avisos"]:
                txt = (f"<b>NEXORA · Integridad</b>\nEl exportador a Obsidian lleva {ob['racha_dias']} días seguidos sin exportar (desde {ob['racha_desde']}; último latido correcto: {ob['ultimo_ok'] or 'ninguno'}). "
                       "Revisa el PC de Ruiz: tarea «NEXORA exportar a Obsidian» del Programador de tareas y el log en %LOCALAPPDATA%\\NexoraExportador\\exportador.log.")
                if seco:
                    print("[seco · no se envía]\n" + txt + "\n")
                    out.append((clave, "SECO", txt))
                else:
                    import telegram
                    ok, err = (enviar or telegram.enviar)(txt)
                    if ok:
                        nuevos[clave] = {"estado": "AVISADO", "avisado_utc": ahora.strftime("%Y-%m-%d %H:%M UTC"), "dato": "obsidian", "periodo": ob["racha_desde"],
                                         "evento": "el exportador a Obsidian no da señales", "publicado_utc": ""}
                        out.append((clave, "AVISADO", txt))
                    else:
                        print("vigilante: Telegram no aceptó el aviso (se reintenta):", err)
                        out.append((clave, "ERROR", err or ""))
    except Exception as e:  # noqa: BLE001
        print("vigilante obsidian:", type(e).__name__, str(e)[:100])
    if nuevos and not seco:
        _guardar_v(raiz, est, nuevos)
        if push and os.environ.get("GITHUB_ACTIONS"):
            import subprocess
            subprocess.run([sys.executable, os.path.join(HERE, "push_seguro.py"), "vigilante " + ahora.strftime("%Y-%m-%d %H:%M") + " UTC [skip ci]"], check=False, timeout=180)
    return out


def refrescar_michigan(raiz=RAIZ, ahora=None, red=None, forzar=False):
    """Descarga las tablas de Michigan (anota lecturas nuevas y fechas anunciadas). Máx. 1 vez cada 20 h, salvo que haya un lanzamiento anunciado y sin registrar (entonces cada pasada).
    red=None: red real. red con atributo .michigan(url) → texto: lo usa (pruebas). Una Red simulada sin .michigan no toca la red."""
    import michigan
    ahora = ahora or dt.datetime.now(UTC)
    fetch = None
    if red is not None:
        fetch = getattr(red, "michigan", None)
        if fetch is None:
            return None
    est = _est_i(raiz)
    prev = (est.get("michigan") or {}).get("ultimo_utc")
    try:
        hace_h = (ahora - dt.datetime.fromisoformat(prev).replace(tzinfo=UTC)).total_seconds() / 3600 if prev else None
    except ValueError:
        hace_h = None
    if not (forzar or hace_h is None or hace_h >= 20 or michigan.hay_pendiente(raiz, ahora)):
        return None
    L = michigan.actualizar(raiz, ahora, fetch)
    est = _est_i(raiz)
    est["michigan"] = {"ultimo_utc": ahora.strftime("%Y-%m-%dT%H:%M:%S"), "ultimo_error": "; ".join(f"{k}: {v}" for k, v in L["errores"].items()) or None}
    _guardar_i(raiz, est)
    return L


def refrescar_eia(raiz=RAIZ, ahora=None, red=None, forzar=False):
    """Lee la tabla semanal de la EIA y el calendario oficial (máx. 1 vez cada 20 h salvo informe pendiente). red=None: red real; una Red simulada sin .eia no toca la red."""
    import petroleo
    fetch = None
    if red is not None:
        fetch = getattr(red, "eia", None)
        if fetch is None:
            return None
    return petroleo.refrescar_eia(raiz, ahora or dt.datetime.now(UTC), fetch, forzar)


# ---------------------------------------------------------------- red (inyectable en pruebas)
def _get(url, datos=None, t=40):
    req = urllib.request.Request(url, data=datos, headers={"User-Agent": "nexora-terminal/1.0 (datos publicos)", **({"Content-Type": "application/json"} if datos else {})})
    return urllib.request.urlopen(req, timeout=t).read().decode("utf-8", "replace")


class Red:
    def bls(self, ids, anio):
        """{serie BLS: {(año, mes): valor}} de la API pública v1 (sin clave, 25 consultas/día)."""
        body = json.dumps({"seriesid": ids, "startyear": str(anio - 1), "endyear": str(anio)}).encode()
        j = json.loads(_get("https://api.bls.gov/publicAPI/v1/timeseries/data/", body))
        if j.get("status") != "REQUEST_SUCCEEDED":
            raise RuntimeError("BLS: " + "; ".join(j.get("message") or [])[:120])
        out = {}
        for s in j["Results"]["series"]:
            out[s["seriesID"]] = {(int(x["year"]), int(x["period"][1:])): float(x["value"]) for x in s["data"]
                                if x["period"].startswith("M") and x["period"] != "M13" and re.fullmatch(r"-?\d+(\.\d+)?", x["value"].strip())}   # BLS marca «-» los meses sin dato
        return out

    def bea(self, clave, tabla, freq, anio):
        """[(descripción de línea, (año, mes|trimestre), valor)] de una tabla NIPA de la API de BEA. La clave nunca se imprime ni viaja en los mensajes de error."""
        url = f"https://apps.bea.gov/api/data?UserID={clave}&method=GetData&datasetname=NIPA&TableName={tabla}&Frequency={freq}&Year={anio},{anio - 1}&ResultFormat=JSON"
        try:
            j = json.loads(_get(url))
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"BEA no respondió ({type(e).__name__})") from None
        datos = (((j.get("BEAAPI") or {}).get("Results") or {}).get("Data")) or []
        if not datos:
            raise RuntimeError("BEA devolvió una respuesta sin datos (¿clave inválida o límite de uso?)")
        out = []
        for r in datos:
            m = re.fullmatch(r"(\d{4})([MQ])(\d{1,2})", r.get("TimePeriod", ""))
            v = (r.get("DataValue") or "").replace(",", "").strip()
            if m and re.fullmatch(r"-?\d+(\.\d+)?", v) and m.group(2) == freq:
                mult = int(r.get("UNIT_MULT") or 0)
                out.append((r.get("LineDescription", ""), (int(m.group(1)), int(m.group(3))), float(v) * 10 ** mult))     # nivel en unidades (dólares) o índice
        return out

    def alfred_tiene(self, sid, periodo, vintage):
        """¿Existe la observación `periodo` de la serie en ALFRED con vintage_date = `vintage`?"""
        raw = _get(f"https://alfred.stlouisfed.org/graph/alfredgraph.csv?id={sid}&cosd={periodo.isoformat()}&coed={periodo.isoformat()}&vintage_date={vintage.isoformat()}")
        for row in list(csv.reader(raw.splitlines()))[1:]:
            if row and row[0] == periodo.isoformat() and len(row) > 1 and row[1] not in ("", "."):
                return True
        return False


# ---------------------------------------------------------------- 2) segunda fuente
def _est_i(raiz):
    return leer_json(P(raiz, "data", "integridad_estado.json")) or {"bls": {"dia": None, "n": 0}, "ultimo_cotejo": {}}


def _guardar_i(raiz, est):
    with open(P(raiz, "data", "integridad_estado.json"), "w", encoding="utf-8") as f:
        json.dump(est, f, ensure_ascii=False, indent=1)


def _ultimo_fred(raiz, sid):
    """(periodo, valor) del último periodo registrado de la serie FRED en data/publicaciones_macro.csv (último valor conocido)."""
    filas = [r for r in leer_csv(P(raiz, "data", "publicaciones_macro.csv")) if r["serie"] == sid]
    if not filas:
        return None
    per = max(r["periodo"] for r in filas)
    return per, float([r for r in filas if r["periodo"] == per][-1]["valor"])


CAMPOS_DISC = ["id", "detectada_utc", "serie", "periodo", "tipo", "fred_valor", "primaria", "primaria_valor", "dif_pct", "estado", "nota"]


def discrepancias(raiz):
    """Estado actual por (serie, periodo, tipo): la última fila manda (ABIERTA o CERRADA)."""
    ult = {}
    for r in leer_csv(P(raiz, "data", "discrepancias.csv")):
        ult[(r["serie"], r["periodo"], r["tipo"])] = r
    return ult


# ---------------------------------------------------------------- discrepancias REVISADAS (data/discrepancias_revisadas.csv, solo añadir)
CAMPOS_REV = ["id", "registrada_utc", "clave", "estado", "motivo", "revisor", "dif_pct_ref", "signo_ref", "nota"]
BRENT_REABRIR_PCT = 25.0         # una discrepancia de Brent revisada se reabre si la diferencia supera este % o cambia de signo; se cierra sola al bajar del umbral de 10 % (lo hace petroleo.py)


def clave_disc(r):
    """Clave estable de una discrepancia: BRENT cambia de día cada comparación, así que se revisa por serie; el resto por (serie, periodo, tipo)."""
    return "BRENT" if r["serie"] == "BRENT" else f"{r['serie']}|{r['periodo']}|{r['tipo']}"


def clave_cal(x):
    return f"CALENDARIO|{x['serie']}|{x['proximo']['fecha']}"


def _signo(r):
    try:
        return 1 if float(r["primaria_valor"]) > float(r["fred_valor"]) else -1 if float(r["primaria_valor"]) < float(r["fred_valor"]) else 0
    except (TypeError, ValueError, KeyError):
        return 0


def revisiones(raiz):
    """Último estado por clave: REVISADA, REABIERTA o CERRADA (la última fila manda)."""
    ult = {}
    for r in leer_csv(P(raiz, "data", "discrepancias_revisadas.csv")):
        ult[r["clave"]] = r
    return ult


def _fila_rev(clave, estado, motivo, revisor, ahora, dif="", signo="", nota=""):
    sello = ahora.strftime("%Y-%m-%d %H:%M UTC")
    return {"id": f"{clave}|{sello}|{estado}", "registrada_utc": sello, "clave": clave, "estado": estado, "motivo": motivo, "revisor": revisor, "dif_pct_ref": dif, "signo_ref": signo, "nota": nota}


def revisar(raiz, clave, motivo, revisor, ahora=None, abiertas=None, calendario=None):
    """Marca como REVISADA una discrepancia abierta (con motivo y fecha). Solo añade una fila; no toca lo anterior. Devuelve la fila o lanza ValueError si esa clave no está abierta."""
    ahora = ahora or dt.datetime.now(UTC)
    abiertas = [r for r in discrepancias(raiz).values() if r["estado"] == "ABIERTA"] if abiertas is None else abiertas
    dif, signo = "", ""
    for r in abiertas:
        if clave_disc(r) == clave:
            dif, signo = r.get("dif_pct", ""), _signo(r)
            break
    else:
        if clave not in {clave_cal(x) for x in (calendario or [])}:
            raise ValueError(f"no hay ninguna discrepancia abierta con la clave «{clave}»")
    fila = _fila_rev(clave, "REVISADA", motivo, revisor, ahora, dif, signo)
    anadir_csv(P(raiz, "data", "discrepancias_revisadas.csv"), [fila], CAMPOS_REV, lambda r: r["id"])
    return fila


def aplicar_revisadas(raiz, ahora, abiertas, calendario):
    """Separa lo que cuenta (abiertas y de calendario sin revisar) de lo REVISADO (gris, visible, fuera del contador). Reglas, todas con una fila nueva en el CSV:
    · BRENT revisada se reabre si |diferencia| > 25 % o el signo se invierte (REABIERTA: vuelve a contar hasta que se revise otra vez).
    · Una revisada cuya discrepancia ya no existe (Brent por debajo del 10 %, o el calendario ya coincide / salió el dato) se cierra sola (CERRADA).
    Devuelve (abiertas, calendario, revisadas)."""
    rev = revisiones(raiz)
    nuevas, revisadas, ab, cal = [], [], [], []
    vivas = set()
    for r in abiertas:
        k = clave_disc(r)
        vivas.add(k)
        e = rev.get(k)
        if not e or e["estado"] != "REVISADA":
            ab.append(r)
            continue
        try:
            dif = abs(float(r.get("dif_pct") or 0))
        except ValueError:
            dif = 0.0
        if k == "BRENT" and (dif > BRENT_REABRIR_PCT or (str(_signo(r)) != str(e.get("signo_ref")) and e.get("signo_ref") not in ("", None))):
            motivo = (f"diferencia {dif:.1f} % > {BRENT_REABRIR_PCT:g} %" if dif > BRENT_REABRIR_PCT else "el signo de la diferencia se ha invertido")
            nuevas.append(_fila_rev(k, "REABIERTA", e["motivo"], e["revisor"], ahora, e.get("dif_pct_ref", ""), e.get("signo_ref", ""), "se reabre sola: " + motivo))
            ab.append(r)
        else:
            revisadas.append({"clave": k, "tipo": "VALOR", "titulo": f"{r['serie']} {r['periodo'][:10]} ({r['tipo'].lower()})",
                              "detalle": f"{r['primaria']} {r['primaria_valor']} frente a FRED {r['fred_valor']}" + (f" ({float(r['dif_pct']):.1f} %)" if r.get("dif_pct") else ""),
                              "motivo": e["motivo"], "revisor": e["revisor"], "registrada_utc": e["registrada_utc"],
                              "regla": f"Se reabre si la diferencia pasa del {BRENT_REABRIR_PCT:g} % o cambia de signo; se cierra sola al bajar del 10 %." if k == "BRENT" else "Se cierra sola cuando la discrepancia desaparece."})
    for x in calendario:
        k = clave_cal(x)
        vivas.add(k)
        e = rev.get(k)
        if e and e["estado"] == "REVISADA":
            revisadas.append({"clave": k, "tipo": "CALENDARIO", "titulo": f"{x['dato']} · calendario", "detalle": f"FRED «{x['fred']}» frente a «{x['oficial']}» ({x['motivo']})",
                              "motivo": e["motivo"], "revisor": e["revisor"], "registrada_utc": e["registrada_utc"], "regla": "Se cierra sola cuando sale el dato esperado o los calendarios coinciden."})
        else:
            cal.append(x)
    for k, e in rev.items():
        if e["estado"] == "REVISADA" and k not in vivas:
            nuevas.append(_fila_rev(k, "CERRADA", e["motivo"], e["revisor"], ahora, nota="se cierra sola: la discrepancia ya no existe (dato publicado, calendarios coinciden o diferencia por debajo del umbral)"))
    if nuevas:
        anadir_csv(P(raiz, "data", "discrepancias_revisadas.csv"), nuevas, CAMPOS_REV, lambda r: r["id"])
    return ab, cal, revisadas


# ---------------------------------------------------------------- el vigilante del vigilante: ¿corre tools/vigilar_cierre.py?
DESDE_VIGILAR_CIERRE = "2026-10-22"      # primer día en que debe correr (alta del workflow vigilar_cierre)
UMBRAL_VIGILAR_DIAS_HABILES = 2


def dias_habiles_entre(d0, d1):
    """Días laborables (lun-vie) en (d0, d1]."""
    n, d = 0, d0
    while d < d1:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def estado_vigilante_cierre(raiz, ahora):
    """Lee data/vigilar_cierre.csv (una fila por ejecución del vigilante). Alerta si lleva ≥ 2 días hábiles sin correr (se cuentan hasta AYER: la de hoy es a las 22:15 UTC)."""
    filas = [r for r in leer_csv(P(raiz, "data", "vigilar_cierre.csv")) if r.get("resultado") != "SIMULACRO"]      # un SIMULACRO no cuenta como ejecución real
    ult = max(filas, key=lambda r: (r["fecha"], r["ejecutado_utc"])) if filas else None
    ref = dt.date.fromisoformat(ult["fecha"]) if ult else dt.date.fromisoformat(DESDE_VIGILAR_CIERRE) - dt.timedelta(days=1)
    ayer = ahora.date() - dt.timedelta(days=1)
    sin = dias_habiles_entre(ref, ayer) if ayer > ref else 0
    alerta = sin >= UMBRAL_VIGILAR_DIAS_HABILES
    return {"ultima_fecha": ult["fecha"] if ult else None, "ultima_ejecucion_utc": ult["ejecutado_utc"] if ult else None, "ultimo_resultado": ult["resultado"] if ult else None,
            "dias_habiles_sin_correr": sin, "umbral_dias_habiles": UMBRAL_VIGILAR_DIAS_HABILES, "alerta": alerta, "ejecuciones_registradas": len(filas),
            "texto": (f"El vigilante del cierre lleva {sin} días hábiles sin correr (último: {ult['fecha'] if ult else 'ninguno todavía'})." if alerta else
                      (f"El vigilante del cierre corrió el {ult['fecha']}: {ult['resultado']}." if ult else "El vigilante del cierre todavía no ha corrido (primera ejecución: 22-oct a las 22:15 UTC).")),
            "fuente": "data/vigilar_cierre.csv · workflow vigilar_cierre (cron-job.org 22:15 UTC)"}


# ---------------------------------------------------------------- Fase 20: ¿el exportador a Obsidian (en el PC de Ruiz) da señales?
UMBRAL_OBSIDIAN_DIAS = 2


def estado_latido_obsidian(raiz, ahora):
    """Lee data/obsidian_latido.csv (fecha, hora_utc, estado: OK | AVISO | ERROR; una fila por pasada, la sube el propio exportador).
    Un día cuenta si tiene alguna pasada OK o AVISO. Alerta si los 2 últimos días COMPLETOS (hasta ayer) no tienen ninguna; el aviso es único por racha.
    Los días anteriores al primer latido no cuentan. Sin ningún latido todavía: SIN DATO, sin alerta."""
    filas = leer_csv(P(raiz, "data", "obsidian_latido.csv"))
    base = {"umbral_dias": UMBRAL_OBSIDIAN_DIAS, "fuente": "data/obsidian_latido.csv · tools/exportar_obsidian.py (Programador de tareas de Windows: 08:30, 23:45 y al iniciar sesión)"}
    if not filas:
        return {**base, "alerta": False, "ultimo": None, "ultimo_ok": None, "racha_dias": 0, "racha_desde": None, "historial": [],
                "texto": "SIN DATO: el exportador a Obsidian todavía no ha enviado ningún latido."}
    bueno = lambda e: e in ("OK", "AVISO") or e.startswith("PENDIENTE")      # PENDIENTE@<commit> = exportó con la versión aprobada y hay una versión nueva por aprobar
    buenos = {r["fecha"] for r in filas if bueno(r["estado"])}
    ult = max(filas, key=lambda r: (r["fecha"], r["hora_utc"]))
    ult_ok = max((r for r in filas if bueno(r["estado"])), key=lambda r: (r["fecha"], r["hora_utc"]), default=None)
    pend = leer_json(P(raiz, "data", "obsidian_pendiente.json")) or {}
    pend = pend if pend.get("pendiente") and ult["estado"].startswith("PENDIENTE") else None
    primero = min(r["fecha"] for r in filas)
    dia, racha = ahora.date() - dt.timedelta(days=1), 0
    while dia.isoformat() >= primero and dia.isoformat() not in buenos:
        racha += 1
        dia -= dt.timedelta(days=1)
    desde = (ahora.date() - dt.timedelta(days=racha)).isoformat() if racha else None
    alerta = racha >= UMBRAL_OBSIDIAN_DIAS
    return {**base, "alerta": alerta, "pendiente_aprobar": pend, "ultimo": {"fecha": ult["fecha"], "hora_utc": ult["hora_utc"], "estado": ult["estado"]},
            "ultimo_ok": f"{ult_ok['fecha']} {ult_ok['hora_utc']} UTC" if ult_ok else None, "racha_dias": racha, "racha_desde": desde, "n_latidos": len(filas),
            "historial": [{"fecha": r["fecha"], "hora_utc": r["hora_utc"], "estado": r["estado"]} for r in filas[-12:]][::-1],
            "texto": (f"El exportador a Obsidian lleva {racha} días seguidos sin exportar (desde {desde})." if alerta else
                      f"Último latido: {ult['fecha']} {ult['hora_utc']} UTC · {ult['estado']}" + (f" · {racha} día(s) sin exportar (aviso a partir de {UMBRAL_OBSIDIAN_DIAS})." if racha else "."))}


def cotejar_bls(raiz=RAIZ, ahora=None, red=None, forzar=False):
    """Compara FRED con BLS para IPC, IPC subyacente e IPP. Devuelve las filas de discrepancia nuevas (ABIERTA / CERRADA)."""
    ahora = ahora or dt.datetime.now(UTC)
    red = red or Red()
    est = _est_i(raiz)
    hoy = ahora.strftime("%Y-%m-%d")
    if est["bls"].get("dia") != hoy:
        est["bls"] = {"dia": hoy, "n": 0}
    abiertas = [k for k, r in discrepancias(raiz).items() if r["estado"] == "ABIERTA"]
    toca = forzar or bool(abiertas)
    for sid in BLS:
        u = _ultimo_fred(raiz, sid)
        prev = est["ultimo_cotejo"].get(sid)
        if u and (not prev or prev.get("periodo") != u[0] or (ahora - dt.datetime.fromisoformat(prev["utc"]).replace(tzinfo=UTC)).total_seconds() > 24 * 3600):
            toca = True
    if not toca or est["bls"]["n"] >= BLS_MAX_DIA:
        _guardar_i(raiz, est)
        return []
    est["bls"]["n"] += 1
    try:
        datos = red.bls(list(BLS.values()), ahora.year)
    except Exception as e:  # noqa: BLE001
        est["bls"]["ultimo_error"] = f"{type(e).__name__}: {str(e)[:100]}"
        _guardar_i(raiz, est)
        return []
    est["bls"].pop("ultimo_error", None)
    stamp = ahora.strftime("%Y-%m-%d %H:%M UTC")
    filas = []
    for sid, bid in BLS.items():
        u = _ultimo_fred(raiz, sid)
        serie_b = datos.get(bid) or {}
        if not u or not serie_b:
            continue
        p = dt.date.fromisoformat(u[0])
        ult_b = max(serie_b)                                   # (año, mes) más reciente en BLS
        for tipo, hay, fval, bval, nota in (
            ("PERIODO", (p.year, p.month) != ult_b, f"{p.year}-{p.month:02d}", f"{ult_b[0]}-{ult_b[1]:02d}", "el último periodo de FRED no coincide con el último de BLS"),
            ("VALOR", None, u[1], serie_b.get((p.year, p.month)), "diferencia de índice entre FRED y BLS para el mismo periodo"),
        ):
            if tipo == "VALOR":
                if bval is None:
                    continue                                    # BLS aún no tiene ese periodo: ya lo cubre la discrepancia de PERIODO
                dif = abs(fval - bval) / bval * 100
                hay = dif > UMBRAL_DISCREPANCIA_PCT
                dif_txt = f"{dif:.4f}"
            else:
                dif_txt = ""
            clave = (sid, p.isoformat(), tipo)
            ya = discrepancias(raiz).get(clave)
            if hay and (not ya or ya["estado"] != "ABIERTA"):
                filas.append({"id": f"{sid}|{p.isoformat()}|{tipo}|{stamp}|ABIERTA", "detectada_utc": stamp, "serie": sid, "periodo": p.isoformat(), "tipo": tipo,
                              "fred_valor": fval, "primaria": "BLS " + bid, "primaria_valor": bval, "dif_pct": dif_txt, "estado": "ABIERTA", "nota": nota + ". Manda BLS."})
            elif not hay and ya and ya["estado"] == "ABIERTA":
                filas.append({"id": f"{sid}|{p.isoformat()}|{tipo}|{stamp}|CERRADA", "detectada_utc": stamp, "serie": sid, "periodo": p.isoformat(), "tipo": tipo,
                              "fred_valor": fval, "primaria": "BLS " + bid, "primaria_valor": bval, "dif_pct": dif_txt, "estado": "CERRADA", "nota": "ya coinciden"})
        est["ultimo_cotejo"][sid] = {"periodo": u[0], "utc": ahora.strftime("%Y-%m-%dT%H:%M:%S")}
    nuevas = anadir_csv(P(raiz, "data", "discrepancias.csv"), filas, CAMPOS_DISC, lambda r: r["id"])
    _guardar_i(raiz, est)
    return nuevas


def cotejar_bea(raiz=RAIZ, ahora=None, red=None, clave=None, forzar=False):
    """Segunda fuente OPCIONAL para PCE (precios) y PIB real con la API de BEA. Solo si existe el secreto BEA_API_KEY; sin él no hace nada (SIN DATO)."""
    clave = clave if clave is not None else os.environ.get("BEA_API_KEY", "")
    if not clave:
        return []
    ahora = ahora or dt.datetime.now(UTC)
    red = red or Red()
    est = _est_i(raiz)
    hoy = ahora.strftime("%Y-%m-%d")
    if est.get("bea", {}).get("dia") != hoy:
        est["bea"] = {"dia": hoy, "n": 0}
    abiertas = [k for k, r in discrepancias(raiz).items() if r["estado"] == "ABIERTA" and k[0] in BEA_TABLAS]
    toca = forzar or bool(abiertas)
    for sid in BEA_TABLAS:
        u = _ultimo_fred(raiz, sid)
        prev = est.get("ultimo_cotejo", {}).get(sid)
        if u and (not prev or prev.get("periodo") != u[0] or (ahora - dt.datetime.fromisoformat(prev["utc"]).replace(tzinfo=UTC)).total_seconds() > 24 * 3600):
            toca = True
    if not toca or est["bea"]["n"] >= BLS_MAX_DIA:
        _guardar_i(raiz, est)
        return []
    stamp = ahora.strftime("%Y-%m-%d %H:%M UTC")
    filas, tablas = [], {}
    est["bea"].pop("ultimo_error", None)
    for sid, (tabla, freq, linea, div) in BEA_TABLAS.items():
        u = _ultimo_fred(raiz, sid)
        if not u:
            continue
        p = dt.date.fromisoformat(u[0])
        try:
            if (tabla, freq) not in tablas:
                est["bea"]["n"] += 1
                tablas[(tabla, freq)] = red.bea(clave, tabla, freq, p.year)
        except Exception as e:  # noqa: BLE001
            est["bea"]["ultimo_error"] = f"{type(e).__name__}: {str(e)[:100]}"        # el mensaje no contiene la clave
            continue
        serie_b = {}
        for d, k, v in tablas[(tabla, freq)]:
            if d.strip().lower() == linea:                             # descripción exacta de la línea
                serie_b.setdefault(k, v / div)
        if not serie_b:
            continue
        kp = (p.year, p.month) if freq == "M" else (p.year, (p.month - 1) // 3 + 1)
        ult_b = max(serie_b)
        for tipo, hay, fval, bval, nota in (
            ("PERIODO", kp != ult_b, f"{kp[0]}-{kp[1]:02d}", f"{ult_b[0]}-{ult_b[1]:02d}", "el último periodo de FRED no coincide con el último de BEA"),
            ("VALOR", None, u[1], serie_b.get(kp), "diferencia entre FRED y BEA para el mismo periodo"),
        ):
            if tipo == "VALOR":
                if bval is None:
                    continue
                dif = abs(fval - bval) / bval * 100
                hay, dif_txt = dif > UMBRAL_DISCREPANCIA_PCT, f"{dif:.4f}"
            else:
                dif_txt = ""
            k_ = (sid, p.isoformat(), tipo)
            ya = discrepancias(raiz).get(k_)
            if hay and (not ya or ya["estado"] != "ABIERTA"):
                filas.append({"id": f"{sid}|{p.isoformat()}|{tipo}|{stamp}|ABIERTA", "detectada_utc": stamp, "serie": sid, "periodo": p.isoformat(), "tipo": tipo, "fred_valor": fval,
                              "primaria": f"BEA {tabla}", "primaria_valor": bval, "dif_pct": dif_txt, "estado": "ABIERTA", "nota": nota + ". Manda BEA."})
            elif not hay and ya and ya["estado"] == "ABIERTA":
                filas.append({"id": f"{sid}|{p.isoformat()}|{tipo}|{stamp}|CERRADA", "detectada_utc": stamp, "serie": sid, "periodo": p.isoformat(), "tipo": tipo, "fred_valor": fval,
                              "primaria": f"BEA {tabla}", "primaria_valor": bval, "dif_pct": dif_txt, "estado": "CERRADA", "nota": "ya coinciden"})
        est.setdefault("ultimo_cotejo", {})[sid] = {"periodo": u[0], "utc": ahora.strftime("%Y-%m-%dT%H:%M:%S")}
    nuevas = anadir_csv(P(raiz, "data", "discrepancias.csv"), filas, CAMPOS_DISC, lambda r: r["id"])
    _guardar_i(raiz, est)
    return nuevas


# ---------------------------------------------------------------- 3) publicación oficial (ALFRED)
CAMPOS_PUB = ["serie", "periodo", "publicado", "fuente", "capturado_utc"]


def fecha_publicacion_alfred(sid, periodo, tipo, hoy, red):
    """Primer día en que ALFRED tiene la observación (búsqueda binaria: la presencia solo puede pasar de ausente a presente). None si aún no está o falla."""
    lo = fin_periodo(periodo, tipo) + dt.timedelta(days=1)
    hi = min(hoy, lo + dt.timedelta(days=100))
    try:
        if lo > hi or not red.alfred_tiene(sid, periodo, hi):
            return None
        while lo < hi:
            mid = lo + (hi - lo) // 2
            if red.alfred_tiene(sid, periodo, mid):
                hi = mid
            else:
                lo = mid + dt.timedelta(days=1)
        return hi
    except Exception:  # noqa: BLE001
        return None


def actualizar_publicaciones(raiz=RAIZ, ahora=None, red=None, max_nuevas=12):
    """Completa data/publicacion_oficial.csv para los últimos 3 periodos de cada serie (como mucho `max_nuevas` consultas por pasada)."""
    ahora = ahora or dt.datetime.now(UTC)
    red = red or Red()
    pub = (leer_json(P(raiz, "site", "data", "publicados.json")) or {}).get("series") or {}
    hechas = {(r["serie"], r["periodo"]) for r in leer_csv(P(raiz, "data", "publicacion_oficial.csv"))}
    filas = []
    for s in series_vigiladas():
        for per in ((pub.get(s["nombre"]) or {}).get("periodos") or [])[-3:][::-1]:
            if len(filas) >= max_nuevas:
                break
            if (s["sid"], per["periodo"]) in hechas:
                continue
            f = fecha_publicacion_alfred(s["sid"], dt.date.fromisoformat(per["periodo"]), s["tipo"], ahora.date(), red)
            if f:
                filas.append({"serie": s["sid"], "periodo": per["periodo"], "publicado": f.isoformat(), "fuente": "ALFRED (vintage_date)", "capturado_utc": ahora.strftime("%Y-%m-%d %H:%M UTC")})
    return anadir_csv(P(raiz, "data", "publicacion_oficial.csv"), filas, CAMPOS_PUB, lambda r: (r["serie"], r["periodo"]))


# ---------------------------------------------------------------- 4) semáforo por bloque
# (etapa, nombre en la web, página, frecuencia, extractor del último dato)
BLOQUES = [
    ("precios", "Precios de mercado", "resumen", "horario"), ("fedwatch", "FedWatch propio", "bancos", "horario"), ("tipos", "Tipos del Tesoro (2Y, 10Y, real)", "bancos", "horario"),
    ("calendario", "Calendario y agenda", "agenda", "horario"), ("publicados", "Datos publicados", "publicados", "horario"), ("resumen", "Resumen y tesis por activo", "resumen", "horario"),
    ("tesis", "Registro de tesis", "tesis", "horario"), ("regimen", "Régimen macro", "regimen", "horario"), ("etf", "Flujos de ETF de BTC y ETH", "cripto", "horario"),
    ("noticias", "Noticias de bancos centrales", "noticias", "horario"), ("skew", "Riesgo de cola (SKEW)", "skew", "horario"), ("alertas", "Alertas", "resumen", "horario"),
    ("reevaluar", "Reevaluación de tesis", "tesis", "horario"), ("marcador", "Marcador de señales", "marcador", "horario"), ("integridad", "Integridad de datos", "integridad", "horario"),
    ("reacciones", "Reacción a eventos", "eventos", "horario"),
    ("consumo", "Consumo (¿está consumiendo la gente?)", "consumo", "diario"), ("petroleo", "Petróleo (WTI, curva, inventarios EIA, COT)", "petroleo", "diario"), ("ciclo", "Ciclo y crédito", "ciclo", "diario"), ("liquidez", "Liquidez", "liquidez", "diario"), ("monitores", "Monitores de oro, índices y cripto", "oro", "diario"),
    ("series", "Series de los gráficos", "oro", "diario"), ("divisas", "Sesgo de divisas", "divisas", "diario"), ("cot", "Posicionamiento (COT)", "posicionamiento", "diario"),
    ("semis", "Semis vs software", "semis", "diario"), ("bancos", "Bancos centrales del mundo", "mapa", "diario"), ("tono", "Tono de bancos centrales", "tono", "diario"),
    ("gamma", "Gamma de índices", "gamma", "diario"),
]
TOLERANCIA_H = {"horario": 3.0, "diario": 30.0}


def ultima_programada(freq, ahora):
    """Último disparo programado (UTC) según los crones: horario = laborables a las xx:07 de 06 a 22 UTC; diario = 05:30 UTC todos los días."""
    if freq == "diario":
        d = ahora.replace(hour=5, minute=30, second=0, microsecond=0)
        return d if d <= ahora else d - dt.timedelta(days=1)
    t = ahora.replace(minute=7, second=0, microsecond=0)
    if t > ahora:
        t -= dt.timedelta(hours=1)
    for _ in range(24 * 8):
        if t.weekday() < 5 and 6 <= t.hour <= 22:
            return t
        t -= dt.timedelta(hours=1)
    return t


def proxima_programada(freq, ahora):
    if freq == "diario":
        d = ahora.replace(hour=5, minute=30, second=0, microsecond=0)
        return d if d > ahora else d + dt.timedelta(days=1)
    t = ahora.replace(minute=7, second=0, microsecond=0)
    if t <= ahora:
        t += dt.timedelta(hours=1)
    for _ in range(24 * 8):
        if t.weekday() < 5 and 6 <= t.hour <= 22:
            return t
        t += dt.timedelta(hours=1)
    return t


def _fecha_dato(raiz, etapa):
    """Fecha del último dato de un bloque (de su propio JSON); None si no se puede leer."""
    sd = P(raiz, "site", "data")
    try:
        c = leer_json(P(sd, "contexto.json")) or {}
        g = lambda *k: __import__("functools").reduce(lambda a, x: (a or {}).get(x) if isinstance(a, dict) else None, k, c)  # noqa: E731
        m = {"precios": g("mercado", "actualizado_utc"), "fedwatch": g("fedwatch_y_tipos", "fecha_precios"), "tipos": g("tipos_a_un_dia_y_repos", "sofr_effr", "fecha"),
             "calendario": g("agenda", "generado_utc"), "regimen": g("regimen_macro", "actualizado_utc"), "ciclo": g("ciclo", "fecha"), "liquidez": g("liquidez", "liquidez_neta_bill_usd", "fecha"),
             "etf": g("etf_flujos_btc_eth", "btc", "ultimo_dia"), "skew": g("riesgo_de_cola_skew", "fecha"), "gamma": g("gamma_indices", "indices", "NQ", "sesion"),
             "semis": g("semis_vs_software", "fecha"), "bancos": g("bancos_centrales_mundo", "fecha"), "tono": g("tono_bancos_centrales", "fecha"), "cot": g("posicionamiento_cot", "fecha_informe"),
             "divisas": g("sesgo_divisas", "riesgo", "fecha"), "resumen": g("tesis", "actualizado_utc"), "alertas": (g("alertas_recientes") or [{}])[-1].get("fecha_utc") if g("alertas_recientes") else None,
             "reacciones": g("reaccion_a_eventos", "ultimo_evento", "fecha"), "monitores": g("mercado", "actualizado_utc"), "series": g("mercado", "actualizado_utc"),
             "marcador": g("marcador", "actualizado_utc"), "tesis": g("tesis", "actualizado_utc"), "reevaluar": g("tesis", "actualizado_utc"), "integridad": None, "consumo": g("consumo", "fecha"), "petroleo": g("petroleo", "fecha")}
        v = m.get(etapa)
        if etapa == "publicados":
            fs = [r["fecha_captura"] for r in leer_csv(P(raiz, "data", "publicaciones_macro.csv"))]
            v = max(fs) if fs else None
        return str(v)[:10] if v else None
    except Exception:  # noqa: BLE001
        return None


def estado_bloques(raiz, ahora, abiertas):
    meta = (leer_json(P(raiz, "site", "data", "meta.json")) or {}).get("etapas") or {}
    out = []
    for etapa, nombre, pagina, freq in BLOQUES:
        e = meta.get(etapa) or {}
        ult = e.get("ultimo_ok_utc")
        try:
            t_ult = dt.datetime.strptime(ult, "%Y-%m-%d %H:%M UTC").replace(tzinfo=UTC) if ult else None
        except ValueError:
            t_ult = None
        esperada = ultima_programada(freq, ahora)
        tol = TOLERANCIA_H[freq]
        if t_ult is None:
            color, motivo = "gris", "SIN DATO: este bloque no tiene ninguna ejecución válida registrada"
        elif t_ult < esperada - dt.timedelta(hours=tol) or e.get("ok") is False:
            retraso = (esperada - t_ult).total_seconds() / 3600
            color = "ambar"
            motivo = ("la última ejecución falló; se muestra el último dato válido" if e.get("ok") is False and retraso <= tol
                      else f"retrasado {retraso:.0f} h frente a su frecuencia ({'cada hora en laborables' if freq == 'horario' else 'una vez al día'})")
        else:
            color, motivo = "verde", "al día"
        out.append({"etapa": etapa, "bloque": nombre, "pagina": pagina, "frecuencia": "cada hora (laborables)" if freq == "horario" else "una vez al día",
                    "color": color, "motivo": motivo, "ultimo_dato": _fecha_dato(raiz, etapa), "registrado_utc": ult,
                    "proximo_utc": proxima_programada(freq, ahora).strftime("%Y-%m-%d %H:%M UTC"),
                    "discrepancias_abiertas": abiertas if etapa == "publicados" else 0})
    return out


# ---------------------------------------------------------------- 5) publicaciones, retrasos y próximo dato
def hora_publicacion(raiz, s, publicado):
    """Instante (UTC) en que salió el dato el día `publicado`: del calendario conocido (agenda/FRED), del calendario oficial anual o de eventos_macro.csv. None si no se sabe."""
    for e in eventos(raiz):
        if e["fecha"] == publicado and coincide(e, s["claves"]):
            return e["t"]
    import calendario_oficial as CO
    for e in (CO.leer(raiz) or {}).get("eventos", []):
        if s["sid"] in e["series"] and e["fecha"] == publicado and e.get("hora_et"):
            h, m = map(int, e["hora_et"].split(":"))
            return dt.datetime.combine(dt.date.fromisoformat(publicado), dt.time(h, m), NY).astimezone(UTC)
    for r in leer_csv(P(raiz, "data", "eventos_macro.csv")):
        if r.get("fecha") == publicado and r.get("hora_madrid") and any(c in r.get("evento", "").lower() for c in s["claves"]):
            h, m = map(int, r["hora_madrid"].split(":"))
            return dt.datetime.combine(dt.date.fromisoformat(publicado), dt.time(h, m), MAD).astimezone(UTC)
    return None


def proximo_dato(raiz, s, evs, ahora):
    """Próximo dato de una serie: calendario FRED/agenda y, si no lo trae, el calendario oficial anual de BLS/BEA; si tampoco, None (SIN DATO)."""
    import calendario_oficial as CO
    prox = next((e for e in evs if coincide(e, s["claves"])), None)
    of = CO.proximo(raiz, s["sid"], ahora.date())

    def de_oficial(o):
        f = dt.date.fromisoformat(o["fecha"])
        hm = None
        if o.get("hora_et"):
            h, m = map(int, o["hora_et"].split(":"))
            hm = dt.datetime.combine(f, dt.time(h, m), NY).astimezone(MAD).strftime("%H:%M")
        return {"texto": f"{etiqueta_proximo(s['nombre'], dt.date.fromisoformat(o['periodo']), s['tipo'], s['sid'])} · {f.day}-{MES_CORTO[f.month - 1]}", "fecha": o["fecha"], "hora_madrid": hm,
                "fuente": f"{o['organismo']} · calendario oficial anual (descargado {str(o.get('descargado_utc') or 'SIN DATO')[:10]})", "url": o["url"]}
    if prox:
        pp = periodo_esperado(s["tipo"], s["lag_m"], dt.date.fromisoformat(prox["fecha"]))
        f = dt.date.fromisoformat(prox["fecha"])
        out = {"texto": f"{etiqueta_proximo(s['nombre'], pp, s['tipo'], s['sid'])} · {f.day}-{MES_CORTO[f.month - 1]}", "fecha": prox["fecha"], "hora_madrid": prox["t"].astimezone(MAD).strftime("%H:%M"),
               "fuente": "calendario de FRED / agenda NEXORA"}
        if of and (of["fecha"] != prox["fecha"] or of["periodo"] != pp.isoformat()):
            out["otra_fuente"] = de_oficial(of)          # los dos calendarios no coinciden: se dejan los dos y se marca
            out["discrepancia_calendario"] = (f"el calendario oficial no lista el periodo «{texto_periodo(pp, s['tipo'])}»: su siguiente fila es «{texto_periodo(dt.date.fromisoformat(of['periodo']), s['tipo'])}» ({of['fecha']})"
                                              if of["periodo"] != pp.isoformat() else f"fechas distintas para el mismo periodo: FRED {prox['fecha']} frente a {of['organismo']} {of['fecha']}")
        return out
    return de_oficial(of) if of else None


def tabla_publicaciones(raiz, ahora):
    pub = (leer_json(P(raiz, "site", "data", "publicados.json")) or {}).get("series") or {}
    oficial = {(r["serie"], r["periodo"]): r["publicado"] for r in leer_csv(P(raiz, "data", "publicacion_oficial.csv"))}
    cap = {}
    for r in leer_csv(P(raiz, "data", "publicaciones_macro.csv")):
        k = (r["serie"], r["periodo"])
        if k not in cap:
            cap[k] = (r["fecha_captura"], r["tipo"], (r.get("registrado_utc") or "").strip())      # las filas antiguas no tienen hora: solo fecha
    evs = [e for e in eventos(raiz) if e["t"] > ahora]
    disc = {(k[0], k[1]): r for k, r in discrepancias(raiz).items() if r["estado"] == "ABIERTA"}
    filas = []
    for s in series_vigiladas():
        v = pub.get(s["nombre"]) or {}
        pers = (v.get("periodos") or [])[-3:][::-1]
        proximo = proximo_dato(raiz, s, evs, ahora)
        for i, per in enumerate(pers):
            p = dt.date.fromisoformat(per["periodo"])
            pu = oficial.get((s["sid"], per["periodo"]))
            c = cap.get((s["sid"], per["periodo"]))
            origen = None if not c else "carga inicial" if c[1].startswith("HIST") else "NEXORA en vivo"
            retraso = horas = None
            reg_utc = c[2] if c and c[2] else None
            if pu and c and origen == "NEXORA en vivo":
                retraso = (dt.date.fromisoformat(c[0]) - dt.date.fromisoformat(pu)).days
                tp = hora_publicacion(raiz, s, pu) if reg_utc else None
                if tp:
                    try:
                        horas = round((dt.datetime.strptime(reg_utc, "%Y-%m-%d %H:%M UTC").replace(tzinfo=UTC) - tp).total_seconds() / 3600, 1)
                    except ValueError:
                        horas = None
            d = disc.get((s["sid"], per["periodo"]))
            filas.append({"dato": s["nombre"], "serie": s["sid"], "periodo": per["periodo"], "dato_de": texto_periodo(p, s["tipo"]), "publicado": pu or None,
                          "publicado_fuente": "FRED/ALFRED" if pu else None, "registrado": c[0] if c else None, "registrado_utc": reg_utc,
                          "registro_origen": origen, "retraso_dias": retraso, "retraso_horas": horas,
                          "valor": per.get("valor"), "proximo": proximo if i == 0 else None,
                          "discrepancia": ({"primaria": d["primaria"], "primaria_valor": d["primaria_valor"], "fred_valor": d["fred_valor"], "dif_pct": d["dif_pct"], "tipo": d["tipo"]} if d else None),
                          "segunda_fuente": SEGUNDA_FUENTE.get(s["sid"]) if i == 0 else None})
    return filas


def bloque_michigan(raiz, ahora):
    """Ánimo del consumidor: último dato de la Universidad de Michigan (preliminar/final), su antigüedad (ámbar si > 45 días), contraste con FRED y próximo lanzamiento anunciado."""
    import michigan
    por = {}
    for r in michigan.registro(raiz):
        k = r["periodo"]
        if k not in por or r["tipo"] == "final":
            por[k] = (dt.date.fromisoformat(k), float(r["valor"]), r["tipo"])
    serie = [por[k] for k in sorted(por)]
    u = _ultimo_fred(raiz, "UMCSENT")
    fred = [(dt.date.fromisoformat(u[0]), u[1])] if u else []
    est = (_est_i(raiz).get("michigan") or {})
    B = michigan.estado(raiz, serie, fred, ahora, {"descarga": est["ultimo_error"]} if est.get("ultimo_error") else {})
    B["ultima_descarga_utc"] = (est.get("ultimo_utc") or "").replace("T", " ")[:16] or None
    prox = next((e for e in michigan.calendario(raiz) if e["fecha"] >= ahora.date().isoformat()), None)
    B["proximo"] = None if not prox else {"fecha": prox["fecha"], "tipo": prox["tipo"], "texto": f"{prox['tipo']} de {michigan.texto_periodo(dt.date.fromisoformat(prox['periodo']))}",
                                          "hora_et": prox.get("hora_et"), "fuente": prox.get("fuente")}
    return B


UMBRAL_EIA_DIAS = 10


def bloque_eia(raiz, ahora):
    """Informe semanal de inventarios de la EIA: última semana registrada, cuándo salió, antigüedad (ámbar si pasan más de 10 días desde su publicación) y próximo informe."""
    import petroleo
    exc = petroleo.excepciones_eia(raiz)
    reg = petroleo.registro_eia(raiz)
    hoy = ahora.date()
    prox = petroleo.proxima_publicacion(exc, hoy)
    est = (_est_i(raiz).get("eia") or {})
    B = {"fuente": "EIA · Weekly Petroleum Status Report (ir.eia.gov/wpsr/table1.csv)", "umbral_dias": UMBRAL_EIA_DIAS, "estado": "SIN DATO", "ultima_descarga_utc": (est.get("ultimo_utc") or "").replace("T", " ")[:16] or None,
         "error": est.get("ultimo_error"), "proximo": None if not prox else {"semana": prox[0].isoformat(), "fecha": prox[1].isoformat(), "hora_et": prox[2]}}
    if reg:
        sem = max(r["semana"] for r in reg)
        pub, hm = petroleo.publicacion_eia(dt.date.fromisoformat(sem), exc)
        capt = min(r["capturado_utc"] for r in reg if r["semana"] == sem)
        edad = (hoy - pub).days
        B.update({"estado": "OK", "semana": sem, "publicado": pub.isoformat(), "hora_et": hm, "visto_utc": capt, "antiguedad_dias": edad, "ambar": edad > UMBRAL_EIA_DIAS,
                  "productos": {r["producto"]: float(r["valor_kb"]) for r in reg if r["semana"] == sem}})
    return B


def _resumen_spot(raiz):
    import spot_oro
    return spot_oro.resumen(raiz)


def construir(raiz=RAIZ, ahora=None):
    ahora = ahora or dt.datetime.now(UTC)
    disc = discrepancias(raiz)
    abiertas = [r for r in disc.values() if r["estado"] == "ABIERTA"]
    pubs = tabla_publicaciones(raiz, ahora)
    cal_todas = [{"dato": x["dato"], "serie": x["serie"], "fred": x["proximo"]["texto"], "oficial": x["proximo"]["otra_fuente"]["texto"], "oficial_fuente": x["proximo"]["otra_fuente"]["fuente"],
                  "motivo": x["proximo"]["discrepancia_calendario"], "proximo": {"fecha": x["proximo"]["fecha"]}} for x in pubs if x.get("proximo") and x["proximo"].get("discrepancia_calendario")]
    abiertas, cal_abiertas, revisadas = aplicar_revisadas(raiz, ahora, abiertas, cal_todas)      # las REVISADAS salen del contador pero siguen visibles
    bloques = estado_bloques(raiz, ahora, len(abiertas))
    al_dia = sum(b["color"] == "verde" for b in bloques)
    vig = _estado_v(raiz).get("avisos", {})
    est = _est_i(raiz)
    return {"version": 1, "ok": True, "generado_utc": ahora.strftime("%Y-%m-%d %H:%M UTC"),
            "resumen": {"al_dia": al_dia, "total": len(bloques), "retrasados": sum(b["color"] == "ambar" for b in bloques), "sin_dato": sum(b["color"] == "gris" for b in bloques),
                        "texto": f"Integridad: {al_dia}/{len(bloques)} al día"},
            "bloques": bloques, "publicaciones": pubs, "michigan": bloque_michigan(raiz, ahora), "eia": bloque_eia(raiz, ahora),
            "retrasos_registro": [x for x in pubs if x["retraso_dias"] is not None],
            "discrepancias_abiertas": [{k: r[k] for k in ("serie", "periodo", "tipo", "fred_valor", "primaria", "primaria_valor", "dif_pct", "detectada_utc", "nota")} for r in abiertas],
            "n_discrepancias_historial": len(leer_csv(P(raiz, "data", "discrepancias.csv"))),
            "discrepancias_calendario": [{k: x[k] for k in ("dato", "fred", "oficial", "oficial_fuente", "motivo")} for x in cal_abiertas],
            "discrepancias_revisadas": revisadas,
            "vigilante_cierre": estado_vigilante_cierre(raiz, ahora),
            "spot_oro": _resumen_spot(raiz),
            "obsidian": estado_latido_obsidian(raiz, ahora),
            "segunda_fuente": {"BLS": "API pública v1, sin clave (IPC, IPC subyacente, IPP): umbral 0,05 % en el índice o periodo distinto; manda BLS",
                               "BEA": ("API de BEA activa (secreto BEA_API_KEY): PCE y PIB real con el mismo umbral; manda BEA" if os.environ.get("BEA_API_KEY") else BEA_SIN_DATO),
                               "bea_activa": bool(os.environ.get("BEA_API_KEY")), "bls_consultas_hoy": est["bls"].get("n", 0), "bls_ultimo_error": est["bls"].get("ultimo_error"),
                               "bea_ultimo_error": (est.get("bea") or {}).get("ultimo_error")},
            "vigilante": {"avisos": len(vig), "ultimos": sorted(vig.values(), key=lambda x: x.get("avisado_utc", ""), reverse=True)[:5], "regla": f"aviso si a la hora de publicación + {ESPERA_VIGILANTE_H} h el periodo nuevo no está en publicados.json"}}


def etapa(raiz=RAIZ, ahora=None, red=None, enviar=None, seco=False):
    """Para build.py: vigilante + segunda fuente + publicaciones oficiales + integridad.json. Cada parte falla por separado."""
    ahora = ahora or dt.datetime.now(UTC)
    errores = {}
    import calendario_oficial
    for nombre, fn in (("calendario_oficial", lambda: calendario_oficial.descargar(raiz, ahora)), ("michigan", lambda: refrescar_michigan(raiz, ahora, red)), ("eia", lambda: refrescar_eia(raiz, ahora, red)),
                       ("vigilante", lambda: vigilar(raiz, ahora, seco, enviar)),
                       ("bls", lambda: cotejar_bls(raiz, ahora, red)), ("bea", lambda: cotejar_bea(raiz, ahora, red)), ("alfred", lambda: actualizar_publicaciones(raiz, ahora, red))):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            errores[nombre] = f"{type(e).__name__}: {str(e)[:100]}"
    out = construir(raiz, ahora)
    out["errores"] = errores
    return out


def bloque_contexto(raiz=RAIZ):
    """Resumen compacto para contexto.json."""
    J = leer_json(P(raiz, "site", "data", "integridad.json"))
    if not J:
        return {"estado": "SIN DATO", "fuente": "integridad.py"}
    return {"actualizado_utc": J.get("generado_utc"), "resumen": J["resumen"]["texto"], "retrasados": [b["bloque"] + " · " + b["motivo"] for b in J["bloques"] if b["color"] == "ambar"],
            "sin_dato": [b["bloque"] for b in J["bloques"] if b["color"] == "gris"],
            "DISCREPANCIAS_ABIERTAS": J["discrepancias_abiertas"] or "ninguna",
            "discrepancias_de_calendario": J.get("discrepancias_calendario") or "ninguna",
            "nota_discrepancias": "Si hay una DISCREPANCIA abierta, manda la fuente primaria (BLS); cita ambas cifras y no uses la de FRED sin avisar.",
            "segunda_fuente": J["segunda_fuente"], "fuente": "integridad.py (data/discrepancias.csv, data/publicacion_oficial.csv, data/vigilante_estado.json)"}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "evaluar"
    if cmd == "revisar":                                   # python integridad.py revisar CLAVE "motivo" [revisor]
        J = construir()
        cal = [{"serie": x["serie"], "proximo": {"fecha": x["proximo"]["fecha"]}} for x in J["publicaciones"] if x.get("proximo") and x["proximo"].get("discrepancia_calendario")]
        fila = revisar(RAIZ, sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "Ruiz", calendario=cal)
        print("REVISADA:", fila["clave"], "·", fila["registrada_utc"])
        cmd = "construir"
    if cmd == "vigilar":
        try:
            refrescar_michigan()                           # pasada de «reacciones»: mira antes la web de Michigan si hay un lanzamiento por registrar
        except Exception as e:  # noqa: BLE001
            print("michigan:", type(e).__name__, str(e)[:100])
        try:
            refrescar_eia()                                # y la tabla semanal de la EIA
        except Exception as e:  # noqa: BLE001
            print("eia:", type(e).__name__, str(e)[:100])
        print("pasada:", [(k, e) for k, e, _ in vigilar(seco="--seco" in sys.argv, push="--push" in sys.argv)] or "nada que avisar")
        sys.exit(0)
    if cmd == "backfill-publicacion":
        n = actualizar_publicaciones(max_nuevas=500)
        print("publicaciones oficiales nuevas:", len(n))
    elif cmd == "cotejar":
        print("discrepancias nuevas:", [(r["serie"], r["tipo"], r["estado"]) for r in cotejar_bls(forzar=True)])
    out = etapa(seco=True) if cmd == "evaluar" else construir()
    with open(P(RAIZ, "site", "data", "integridad.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(out["resumen"]["texto"], "· discrepancias abiertas:", len(out["discrepancias_abiertas"]))
