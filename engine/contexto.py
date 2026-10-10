"""NEXORA · contexto.json — resumen compacto de TODO el terminal, con fuente y fecha en cada bloque.

Pensado para que un asistente (Claude) lo lea cuando el usuario pida un informe, sin tener que abrir quince JSON.
Solo LEE los JSON ya calculados de site/data/: no descarga nada, no llama a ninguna IA y no estima datos que falten
(un bloque sin datos queda como {"estado": "SIN DATO"} con la fuente esperada y la última copia válida si existe)."""
from __future__ import annotations

import datetime as dt
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SITE_DATA = os.path.join(os.path.dirname(HERE), "site", "data")
URL = "https://komonartisans-ops.github.io/nexora-terminal/"

LECTURA = [
    "Cita siempre la fuente y la fecha del dato que uses (campos 'fuente' y 'fecha' de cada bloque). El periodo del dato no es la fecha de publicación.",
    "Separa hecho, interpretación, hipótesis y escenario. No hagas recomendaciones de compra o venta.",
    "Un bloque con estado 'SIN DATO' o con 'ok': false significa que la fuente falló: dilo, no lo estimes ni lo sustituyas por memoria.",
    "Los bloques 'CRITERIO NEXORA' (gamma, semis/software, zonas del SKEW) son métodos propios, no datos oficiales: menciona el método.",
    "Revisa 'frescura' y 'datos_con_mas_de_48h' antes de afirmar nada sobre el estado actual.",
]


def _leer(n):
    try:
        with open(os.path.join(SITE_DATA, n + ".json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def _sd(fuente, ultimo=None):
    return {"estado": "SIN DATO", "fuente": fuente, "ultima_copia_valida_utc": ultimo}


def _ok(j):
    return bool(j) and j.get("ok") is not False


def _r(x, d=2):
    try:
        return round(float(x), d)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- bloques
def _mercado(P):
    if not P or not P.get("activos"):
        return _sd("Yahoo Finance (precios.json)")
    out = {}
    for k, a in P["activos"].items():
        if a.get("valor") is None:
            out[k] = {"estado": "SIN DATO", "fuente": a.get("fuente")}
        else:
            out[k] = {"nombre": a["nombre"], "valor": a["valor"], "fecha": a.get("fecha"), "cambio_1d_pct": a.get("cambio_1d_pct"), "cambio_5d_pct": a.get("cambio_5d_pct"),
                      "cambio_21d_pct": a.get("cambio_21d_pct"), "cambio_63d_pct": a.get("cambio_63d_pct"), "vs_sma50_pct": _r((a["valor"] / a["sma50"] - 1) * 100, 1) if a.get("sma50") else None,
                      "fuente": a.get("fuente")}
    return {"actualizado_utc": P.get("generado_utc"), "activos": out}


def _tesis(R):
    if not R or not R.get("tesis_activos"):
        return _sd("por_activo.py (resumen.json)")
    out = []
    for a, t in R["tesis_activos"].items():
        p = t.get("propio") or {}
        out.append({"activo": a, "etiqueta": t.get("etiqueta"), "viento_semana": t.get("viento_semana"), "motor_propio": t.get("motor_propio_nombre"),
                    "veredicto_motor_propio": p.get("veredicto"), "a_favor": (p.get("favor") or [])[:3], "en_contra": (p.get("contra") or [])[:3], "tesis": t.get("tesis")})
    return {"corte_datos": R.get("corte"), "actualizado_utc": R.get("generado_utc"), "que_lo_ha_movido": R.get("movido"), "vigilar": R.get("vigilar"), "tesis_por_activo": out,
            "fuente": "Motor NEXORA por_activo.py (plantillas deterministas) sobre monitores propios"}


def _ciclo(C):
    if not C or not C.get("fase"):
        return _sd("ciclo.py (FRED, NY Fed, Fed EBP)")
    sen = [{"nombre": s.get("nombre") or s.get("clave"), "encendida": s.get("encendida")} for s in (C.get("senales") or [])]
    return {"fase": C["fase"], "fecha": C.get("fecha"), "senales_adelantadas_encendidas": C.get("senales_adelantadas_encendidas"), "senales_adelantadas_total": C.get("senales_adelantadas_total"),
            "prob_recesion_curva_nyfed_pct": C.get("prob_recesion_curva_nyfed"), "prob_recesion_ebp_fed_pct": C.get("prob_recesion_ebp_fed"), "curva_10y3m_pp": C.get("curva_10y3m"),
            "senales": sen, "actualizado_utc": C.get("generado_utc"), "fuente": "FRED, NY Fed (probit), Fed (EBP) · reglas de ciclo.py"}


def _credito(C):
    if not C or not C.get("credito"):
        return _sd("ICE BofA vía FRED (ciclo.json)")
    cr = {k: {"pb": v.get("pb"), "d5_pb": v.get("5d_pb"), "d1m_pb": v.get("1m_pb"), "percentil_1a": v.get("percentil_1a"), "fecha": v.get("fecha")} for k, v in C["credito"].items() if v}
    return {"estado": C.get("estado_credito"), "diferenciales": cr, "umbrales_alerta_pb": C.get("umb_cred"), "fuente": "ICE BofA vía FRED (BAMLC0A0CM, BAMLC0A4CBBB, BAMLH0A0HYM2, BAMLH0A3HYC)"}


def _liquidez(L):
    if not L or not L.get("evaluacion"):
        return _sd("FRED / Tesoro (liquidez.json)")
    E, H = L["evaluacion"], L.get("historico") or {}
    ult = lambda k: (H.get(k) or [[None, None]])[-1]  # noqa: E731
    return {"lectura": E.get("lectura"), "checklist": E.get("checklist_resumen"), "secuencia_cumplidos": E.get("secuencia_cumplidos"),
            "liquidez_neta_bill_usd": {"valor": ult("liquidez_neta_T")[1], "fecha": ult("liquidez_neta_T")[0]},
            "tga_bill_usd": {"valor": ult("tga_T")[1], "fecha": ult("tga_T")[0]}, "reservas_bill_usd": {"valor": ult("reservas_T")[1], "fecha": ult("reservas_T")[0]},
            "avisos": (E.get("avisos") or [])[:3], "actualizado_utc": L.get("generado_utc"), "fuente": "FRED (WALCL, WTREGEN, RRPONTSYD, WRESBAL), Tesoro, Fed"}


def _fed(F, T):
    if not F or not F.get("reuniones"):
        return _sd("FedWatch NEXORA (futuros ZQ del CBOT)")
    reun = [{"reunion": r["reunion"], "tipo_esperado": r["tipo_esperado"], "prob_subida_pct": r["prob_reunion"]["subida"], "prob_mantiene_pct": r["prob_reunion"]["mantiene"],
             "prob_bajada_pct": r["prob_reunion"]["bajada"], "subida_5d_pts": r.get("subida_5d_pts")} for r in F["reuniones"][:4]]
    tipos = {k: {"valor": v.get("valor"), "fecha": v.get("fecha")} for k, v in (T or {}).items() if isinstance(v, dict) and "valor" in v}
    return {"fecha_precios": F.get("fecha_precios"), "rango_objetivo": F.get("rango_objetivo"), "effr": F.get("effr"), "lectura": F.get("lectura"), "resumen": F.get("resumen"),
            "reuniones": reun, "tipos_tesoro": tipos, "tipos_oficiales": F.get("tipos_actuales"), "actualizado_utc": F.get("generado_utc"),
            "fuente": "FedWatch NEXORA (futuros ZQ, EFFR, calendario FOMC) · Tesoro de EE. UU."}


def _cot(C):
    if not C or not C.get("contratos"):
        return _sd("CFTC · Commitments of Traders")
    out = []
    for c in C["contratos"]:
        if c.get("sin_dato"):
            out.append({"contrato": c["nombre"], "estado": "SIN DATO"})
            continue
        nc, g = c.get("no_comerciales"), c.get("gestores")
        out.append({"contrato": c["nombre"], "grupo": c["grupo"],
                    "no_comerciales": nc and {"neto": nc["neto"], "cambio_semana": nc["cambio_semana"], "percentil_3a": nc["percentil_3a"], "estado": nc["estado"]},
                    "gestores": g and {"neto": g["neto"], "cambio_semana": g["cambio_semana"], "percentil_3a": g["percentil_3a"], "estado": g["estado"]}})
    return {"fecha_informe": C.get("fecha_informe"), "publicado": C.get("publicado"), "contratos": out, "fuente": C.get("fuente"), "metodo": C.get("metodo")}


def _divisas(D):
    if not D or not D.get("monedas"):
        return _sd("Matriz NEXORA de divisas")
    return {"actualizado_utc": D.get("generado_utc"), "riesgo": D.get("riesgo"), "resumen": (D.get("esencial") or {}).get("cambio"),
            "monedas": [{"divisa": m["clave"], "total": m["total"], "sesgo": m["sesgo"], "fx_3m_pct": m.get("fx_3m_pct")} for m in D["monedas"]],
            "fuente": "BIS (tipos), BoJ, FMI WEO, Tesoro/BCE/OCDE vía FRED · reglas NEXORA"}


def _regimen(R):
    if not R or not R.get("evaluacion"):
        return _sd("regimen.py (regimen.json)")
    E = R["evaluacion"]
    return {"cuadrante": E.get("cuadrante"), "fuerza": E.get("fuerza"), "cuadrante_simple": E.get("cuadrante_simple"), "riesgo": E.get("riesgo"), "liquidez": E.get("liquidez"),
            "concordancia_monitores": E.get("concordancia"), "motor": E.get("motor_lectura"),
            "mapa": [{"dimension": d["dimension"], "estado": d["estado"], "puntos": d.get("puntos")} for d in E.get("mapa", [])],
            "contradicciones": E.get("contradicciones") or [], "actualizado_utc": R.get("generado_utc"), "fuente": "Mapa de régimen NEXORA (FRED, BLS, BEA, Fed regionales, monitores propios)"}


def _calendario(C):
    if not C or not C.get("eventos"):
        return _sd("Calendario NEXORA (FRED, ISM, Fed, Nasdaq)")
    hoy = dt.date.today().isoformat()
    lim = (dt.date.today() + dt.timedelta(days=14)).isoformat()
    prox = [{"fecha": e["fecha"], "hora_madrid": e.get("hora_madrid"), "evento": e["evento"], "importancia": e.get("importancia"), "afecta": e.get("afecta")}
            for e in C["eventos"] if hoy <= e["fecha"] <= lim and e.get("importancia") in ("ALTA", "MEDIA")][:18]
    pub = [{"serie": k, "periodo": v.get("periodo"), "valor": v.get("valor"), "anterior": v.get("anterior"), "fecha_publicacion": v.get("fecha_publicacion"), "fuente": v.get("fuente")}
           for k, v in (C.get("ultimos_publicados") or {}).items() if not v.get("sin_dato")]
    return {"proximos_14_dias": prox, "bancos_centrales": C.get("proximos_bancos_centrales"), "ultimos_publicados": pub, "actualizado_utc": C.get("generado_utc"),
            "fuente": "Calendario NEXORA · sin consenso de analistas (es de pago)"}


def _skew(S):
    if not S or S.get("valor") is None:
        return _sd("Cboe · SKEW")
    est = S.get("estudio") or {}
    r = est.get("resumen") or {}
    return {"fecha": S["fecha"], "valor": S["valor"], "zona": S["zona"], "umbrales": S.get("umbrales"), "percentil_historico": S.get("percentil_hist"), "percentil_1a": S.get("percentil_1a"),
            "racha_sesiones": S.get("racha_sesiones"), "entrada_zona_alta": S.get("entrada_zona_alta"),
            "confirmaciones": [{"nombre": c["nombre"], "estado": c["estado"], "encendida": c["encendida"], "valor": c["valor"], "fecha": c.get("fecha"), "fuente": c.get("fuente")}
                               for c in S.get("confirmaciones", [])],
            "confirmaciones_encendidas": f"{S.get('confirmaciones_encendidas')} de {S.get('confirmaciones_validas')}",
            "estudio_historico": {"episodios": r.get("episodios"), "completos": r.get("completos"), "caidas_5pct_60s": r.get("caidas"), "falsas_alarmas": r.get("falsas_alarmas"),
                                  "tasa_base_caida_5pct_60s": (est.get("tasa_base") or {}).get("caida_5_60s_pct"),
                                  "mediana_ret_pct": {h: (r.get(h) or {}).get("mediana") for h in ("5", "20", "60")}, "desde": r.get("desde"), "aviso": est.get("sesgo_del_estudio")},
            "esencial": S.get("esencial"), "actualizado_utc": S.get("generado_utc"), "fuente": S.get("fuente"), "etiqueta": "CRITERIO NEXORA (zonas y episodios)"}


def _gamma(G):
    if not G or not G.get("indices"):
        return _sd("Cboe · cadena de opciones con retraso")
    out = {}
    for k, x in G["indices"].items():
        out[k] = {"sesion": x["sesion"], "cierre_confirmado": x["cierre_confirmado"], "spot_indice": x["spot_idx"], "spot_futuro": x.get("spot_fut"),
                  "base_futuro": (x.get("base") or {}).get("base"), "metodo_base": (x.get("base") or {}).get("metodo"), "regimen_gamma": x["regimen"],
                  "gex_neto_musd_por_1pct": x["gex_neto_musd"],
                  "call_wall": x.get("call_wall"), "put_wall": x.get("put_wall"), "gamma_flip": x.get("flip"), "resumen": x.get("resumen_texto")}
    return {"indices": out, "actualizado_utc": G.get("generado_utc"), "fuente": G.get("fuente"), "etiqueta": "CRITERIO NEXORA (método propio, no dato oficial)",
            "supuesto": "GEX con signo +calls / −puts: hipótesis sobre el posicionamiento de los creadores de mercado, no observable."}


def _semis(S):
    if not S or not S.get("ratio"):
        return _sd("Yahoo Finance (SMH, IGV)")
    r = S["ratio"]
    return {"fecha": S["fecha"], "ratio_smh_igv": r["valor"], "vs_sma50_pct": r["vs_sma50_pct"], "vs_sma200_pct": r["vs_sma200_pct"], "tendencia": r["tendencia"],
            "cambios_pct": r["cambios_pct"], "hoy": S.get("hoy"), "escenario_hoy": (S.get("escenario") or {}).get("etiqueta"), "explicacion": (S.get("escenario") or {}).get("texto"),
            "impacto": {k: {"beta_semis": v["beta_semis"], "beta_software": v["beta_software"], "r2": v["r2"], "real_pct": v["real_pct"], "explicado_pp": v["explicado_pp"]}
                        for k, v in (S.get("impacto") or {}).items()},
            "peso_ndx": S.get("pesos_ndx") and {k: S["pesos_ndx"][k] for k in ("fecha", "semis_pct", "software_pct")},
            "actualizado_utc": S.get("generado_utc"), "fuente": S.get("fuente"), "etiqueta": "CRITERIO NEXORA"}


# ---------------------------------------------------------------- contradicciones (mismas reglas que el bloque del Resumen)
def _senal_credito(C):
    if not C or not C.get("credito"):
        return None
    U, cr = C.get("umb_cred") or {}, C["credito"]
    def t(k):
        m, u = cr.get(k), U.get(k) or []
        if not m:
            return None
        d5, d1m = m.get("5d_pb"), m.get("1m_pb")
        return {"pb": m.get("pb"), "d5": d5, "d1m": d1m, "on": (d5 is not None and len(u) > 0 and d5 >= u[0]) or (d1m is not None and len(u) > 1 and d1m >= u[1]), "fecha": m.get("fecha")}
    ccc, hy = t("ccc"), t("hy")
    if not ccc and not hy:
        return None
    ten = any(x and x["on"] for x in (ccc, hy))
    return {"dir": -1 if ten else 1, "etiqueta": "TENSIÓN" if ten else "SIN TENSIÓN", "ccc": ccc, "hy": hy}


def _senal_divisas(D):
    if not D or not D.get("monedas"):
        return None
    tot = {m["clave"]: m["total"] for m in D["monedas"] if m.get("total") is not None}
    c = [tot[k] for k in ("AUD", "NZD", "CAD") if k in tot]
    r = [tot[k] for k in ("JPY", "CHF") if k in tot]
    if not c or not r:
        return None
    sp = sum(c) / len(c) - sum(r) / len(r)
    d = 1 if sp >= 2 else -1 if sp <= -2 else 0
    return {"dir": d, "etiqueta": "APETITO" if d > 0 else "AVERSIÓN" if d < 0 else "NEUTRAL", "diferencial": round(sp, 2)}


def _senal_cot(C):
    if not C or not C.get("contratos"):
        return None
    def p(k):
        c = next((x for x in C["contratos"] if x["clave"] == k), None)
        return c["no_comerciales"]["percentil_3a"] if c and c.get("no_comerciales") and c["no_comerciales"].get("percentil_3a") is not None else None
    a = [x for x in (p(k) for k in ("aud", "nzd", "cad", "spx", "ndx", "rut")) if x is not None]
    b = [x for x in (p(k) for k in ("jpy", "chf")) if x is not None]
    if not a or not b:
        return None
    df = sum(a) / len(a) - sum(b) / len(b)
    d = 1 if df >= 15 else -1 if df <= -15 else 0
    return {"dir": d, "etiqueta": "APETITO" if d > 0 else "AVERSIÓN" if d < 0 else "NEUTRAL", "diferencial_percentil": round(df, 1)}


def _par(a, b, nom):
    DT = {1: "apetito de riesgo", -1: "aversión al riesgo", 0: "sin lectura"}
    if not a or not b:
        return {"par": nom, "resultado": "SIN DATO", "texto": "Falta una de las dos lecturas: no se compara ni se estima."}
    if a["dir"] == 0 or b["dir"] == 0:
        return {"par": nom, "resultado": "SIN LECTURA CLARA", "texto": "Una de las dos lecturas es neutral."}
    if a["dir"] == b["dir"]:
        return {"par": nom, "resultado": "COINCIDEN", "texto": f"Las dos apuntan a {DT[a['dir']]}."}
    return {"par": nom, "resultado": "CONTRADICCIÓN", "texto": f"El crédito apunta a {DT[a['dir']]} y la otra lectura a {DT[b['dir']]}."}


def _contradicciones(C, D, T, R, S):
    cr, fx, cot = _senal_credito(C), _senal_divisas(D), _senal_cot(T)
    pares = [_par(cr, fx, "Crédito frente a divisas"), _par(cr, cot, "Crédito frente a COT")]
    extra = []
    if S and S.get("zona") == "ALTO" and (S.get("confirmaciones") or [{}])[0].get("encendida") is False:
        extra.append({"par": "SKEW frente a VIX", "resultado": "CONTRADICCIÓN", "texto": "El SKEW está en zona alta (cobertura de cola cara) mientras el VIX y su curva no muestran estrés: "
                                                                                      "cobertura sin miedo generalizado (hipótesis, no hecho)."})
    return {"senales": {"credito": cr and {k: cr[k] for k in ("etiqueta", "dir")}, "divisas": fx, "cot": cot}, "pares": pares + extra,
            "del_regimen": ((R or {}).get("evaluacion") or {}).get("contradicciones") or [],
            "reglas": "Crédito: CCC o HY por encima de sus umbrales de ciclo.py = tensión. Divisas: sesgo medio AUD/NZD/CAD − JPY/CHF (±2). COT: percentil medio riesgo − refugio (±15).",
            "fuente": "Reglas NEXORA sobre ciclo.py, matriz de divisas y COT de la CFTC"}


# ---------------------------------------------------------------- principal
def construir():
    J = {n: _leer(n) for n in ("meta", "precios", "resumen", "ciclo", "liquidez", "fedwatch", "tipos", "cot", "divisas", "regimen", "calendario", "skew", "gamma", "semis", "alertas")}
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    meta = J["meta"] or {}
    fres, viejos, fallos = {}, [], []
    ahora = dt.datetime.now(dt.timezone.utc)
    for k, e in (meta.get("etapas") or {}).items():
        fres[k] = {"ok": e.get("ok"), "ultimo_ok_utc": e.get("ultimo_ok_utc")}
        try:
            t = dt.datetime.strptime(e.get("ultimo_ok_utc") or "", "%Y-%m-%d %H:%M UTC").replace(tzinfo=dt.timezone.utc)
            if (ahora - t).total_seconds() > 48 * 3600:
                viejos.append(k)
        except ValueError:
            viejos.append(k)
        if e.get("ok") is False:
            fallos.append({"etapa": k, "error": (e.get("error") or "")[:160]})
    skew = J["skew"] if _ok(J["skew"]) or (J["skew"] and J["skew"].get("valor") is not None) else None
    out = {
        "version": 1, "generado_utc": stamp, "terminal": URL,
        "proposito": "Resumen compacto de todo el terminal NEXORA para redactar informes. Fuente y fecha en cada bloque. Sin IA en su generación.",
        "lectura_para_informes": LECTURA,
        "frescura": fres, "datos_con_mas_de_48h": viejos, "fallos_ultima_ejecucion": fallos,
        "mercado": _mercado(J["precios"]),
        "tesis": _tesis(J["resumen"]),
        "regimen_macro": _regimen(J["regimen"]),
        "ciclo": _ciclo(J["ciclo"]),
        "credito": _credito(J["ciclo"]),
        "liquidez": _liquidez(J["liquidez"]),
        "fedwatch_y_tipos": _fed(J["fedwatch"], J["tipos"]),
        "riesgo_de_cola_skew": _skew(skew),
        "gamma_indices": _gamma(J["gamma"] if J["gamma"] and J["gamma"].get("indices") else None),
        "semis_vs_software": _semis(J["semis"] if J["semis"] and J["semis"].get("ratio") else None),
        "posicionamiento_cot": _cot(J["cot"]),
        "sesgo_divisas": _divisas(J["divisas"]),
        "contradicciones": _contradicciones(J["ciclo"], J["divisas"], J["cot"], J["regimen"], skew),
        "calendario": _calendario(J["calendario"]),
        "alertas_recientes": [{"fecha_utc": a.get("fecha_utc"), "titulo": a.get("titulo"), "enviada": a.get("enviada"), "l1": a.get("l1")}
                              for a in ((J["alertas"] or {}).get("recientes") or [])[-5:]],
    }
    return out


if __name__ == "__main__":
    c = construir()
    s = json.dumps(c, ensure_ascii=False, indent=1)
    print(len(s), "bytes")
    print(s[:3000])
