"""NEXORA · posicionamiento de la CFTC (Commitments of Traders). API Socrata pública, sin clave ni coste.

Tres informes: Legacy (no comerciales), TFF (gestores de activos y fondos apalancados en financieros) y Disaggregated
(dinero gestionado, solo para el oro). Se publica el viernes con datos del martes anterior.
Para cada contrato: neto (largos − cortos), percentil a 3 años de ese neto y cambio semanal.
Si un informe o un contrato no responde se marca SIN DATO: nunca se interpola."""
from __future__ import annotations

import datetime as dt
import urllib.parse

import csvlog
import fuentes

BASE = "https://publicreporting.cftc.gov/resource/{}.json"
LEGACY, TFF, DISAG = "6dca-aqww", "gpe5-46if", "72hh-3qpy"
# (clave, nombre, grupo, código CFTC)
CONTRATOS = [
    ("usd", "Índice dólar (ICE)", "Divisas", "098662"), ("eur", "Euro", "Divisas", "099741"), ("jpy", "Yen japonés", "Divisas", "097741"),
    ("gbp", "Libra esterlina", "Divisas", "096742"), ("chf", "Franco suizo", "Divisas", "092741"), ("cad", "Dólar canadiense", "Divisas", "090741"),
    ("aud", "Dólar australiano", "Divisas", "232741"), ("nzd", "Dólar neozelandés", "Divisas", "112741"),
    ("oro", "Oro (COMEX)", "Materias primas", "088691"),
    ("spx", "S&P 500 (consolidado)", "Índices", "13874+"), ("ndx", "Nasdaq-100 (consolidado)", "Índices", "20974+"),
    ("dji", "Dow Jones (consolidado)", "Índices", "12460+"), ("rut", "Russell 2000 (E-mini)", "Índices", "239742"),
    ("ust2", "Bono EE. UU. 2 años", "Bonos", "042601"), ("ust10", "Bono EE. UU. 10 años", "Bonos", "043602"), ("ust30", "Bono EE. UU. 30 años", "Bonos", "020601"),
    ("btc", "Bitcoin (CME)", "Cripto", "133741"),
]
URL_INFORME = "https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm"
ANIOS = 3


def _consulta(ds, campos, codigos, desde):
    cods = ",".join(f"'{c}'" for c in codigos)
    q = {"$select": "report_date_as_yyyy_mm_dd,cftc_contract_market_code," + campos,
         "$where": f"cftc_contract_market_code in({cods}) AND report_date_as_yyyy_mm_dd >= '{desde}T00:00:00.000'",
         "$order": "report_date_as_yyyy_mm_dd ASC", "$limit": "50000"}
    return fuentes.json_(BASE.format(ds) + "?" + urllib.parse.urlencode(q), timeout=90)


def _netos(filas, largo, corto):
    """{código: [(fecha, neto, largos, cortos)]} ordenado por fecha."""
    out = {}
    for r in filas:
        try:
            l, c = int(float(r[largo])), int(float(r[corto]))
        except (KeyError, ValueError, TypeError):
            continue
        out.setdefault(r["cftc_contract_market_code"], []).append((r["report_date_as_yyyy_mm_dd"][:10], l - c, l, c))
    return out


def _resumen(serie):
    """Neto actual, cambio semanal, percentil a 3 años (posición del neto actual entre los netos del periodo) y serie."""
    if not serie or len(serie) < 8:
        return None
    netos = [s[1] for s in serie]
    ult = serie[-1]
    prev = serie[-2]
    pct = round(sum(1 for v in netos if v <= ult[1]) / len(netos) * 100)
    return {"fecha": ult[0], "neto": ult[1], "largos": ult[2], "cortos": ult[3], "cambio_semana": ult[1] - prev[1], "fecha_previa": prev[0],
            "percentil_3a": pct, "min_3a": min(netos), "max_3a": max(netos), "semanas": len(netos),
            "serie": [[s[0], s[1]] for s in serie]}


def _estado(pct):
    if pct is None:
        return "SIN DATO"
    return "EXTREMO LARGO" if pct >= 90 else "EXTREMO CORTO" if pct <= 10 else "LARGO ELEVADO" if pct >= 70 else "CORTO ELEVADO" if pct <= 30 else "INTERMEDIO"


def medir():
    desde = (dt.date.today() - dt.timedelta(days=365 * ANIOS + 10)).isoformat()
    codigos = [c[3] for c in CONTRATOS]
    err, leg, tff, dis = {}, {}, {}, {}
    try:
        leg = _netos(_consulta(LEGACY, "open_interest_all,noncomm_positions_long_all,noncomm_positions_short_all", codigos, desde), "noncomm_positions_long_all", "noncomm_positions_short_all")
    except Exception as e:  # noqa: BLE001
        err["legacy"] = f"{type(e).__name__}: {e}"
    try:
        filas = _consulta(TFF, "open_interest_all,asset_mgr_positions_long,asset_mgr_positions_short,lev_money_positions_long,lev_money_positions_short", codigos, desde)
        tff = _netos(filas, "asset_mgr_positions_long", "asset_mgr_positions_short")
        lev = _netos(filas, "lev_money_positions_long", "lev_money_positions_short")
    except Exception as e:  # noqa: BLE001
        err["tff"] = f"{type(e).__name__}: {e}"
        lev = {}
    try:
        dis = _netos(_consulta(DISAG, "m_money_positions_long_all,m_money_positions_short_all", ["088691"], desde), "m_money_positions_long_all", "m_money_positions_short_all")
    except Exception as e:  # noqa: BLE001
        err["disaggregated"] = f"{type(e).__name__}: {e}"
    if not leg and not tff:
        raise RuntimeError("CFTC no responde: " + "; ".join(f"{k}: {v}" for k, v in err.items())[:300])

    out = []
    for k, nombre, grupo, cod in CONTRATOS:
        nc = _resumen(leg.get(cod))
        if k == "oro":  # el oro no está en TFF: los gestores son «dinero gestionado» del informe Disaggregated
            gs, gnom = _resumen(dis.get(cod)), "Dinero gestionado (Disaggregated)"
        else:
            gs, gnom = _resumen(tff.get(cod)), "Gestores de activos (TFF)"
        fa = _resumen(lev.get(cod)) if k != "oro" else None
        out.append({"clave": k, "nombre": nombre, "grupo": grupo, "codigo": cod, "sin_dato": not (nc or gs),
                    "no_comerciales": nc and {**nc, "estado": _estado(nc["percentil_3a"])},
                    "gestores": gs and {**gs, "estado": _estado(gs["percentil_3a"]), "informe": gnom},
                    "apalancados": fa and {**fa, "estado": _estado(fa["percentil_3a"])}})
    fechas = [c["no_comerciales"]["fecha"] for c in out if c["no_comerciales"]] + [c["gestores"]["fecha"] for c in out if c["gestores"]]
    fecha = max(fechas)
    # memoria permanente (solo se añade): una fila por contrato y semana de informe
    filas_csv = []
    for c in out:
        for tipo, bloque in (("no_comerciales", c["no_comerciales"]), ("gestores", c["gestores"])):
            if bloque:
                filas_csv.append({"fecha_informe": bloque["fecha"], "contrato": c["codigo"], "clave": c["clave"], "tipo": tipo, "neto": bloque["neto"],
                                  "largos": bloque["largos"], "cortos": bloque["cortos"], "percentil_3a": bloque["percentil_3a"]})
    csvlog.anadir("historico_cot.csv", filas_csv, ("fecha_informe", "contrato", "tipo"))
    return {"fecha_informe": fecha, "publicado": "viernes siguiente, 15:30 ET (datos del martes)", "contratos": out, "errores": err,
            "fuente": "CFTC · Commitments of Traders (API Socrata publicreporting.cftc.gov)", "url": URL_INFORME,
            "metodo": f"Neto = largos − cortos. Percentil = posición del neto actual entre las ~{ANIOS * 52} semanas anteriores (≥90 extremo largo, ≤10 extremo corto)."}


if __name__ == "__main__":
    import json
    r = medir()
    for c in r["contratos"]:
        nc, g = c["no_comerciales"], c["gestores"]
        print(c["nombre"], "| NC", nc and (nc["fecha"], nc["neto"], nc["cambio_semana"], nc["percentil_3a"]), "| G", g and (g["neto"], g["cambio_semana"], g["percentil_3a"]))
    print(r["errores"])
