"""NEXORA · GAMMA DE ÍNDICES — CRITERIO NEXORA (método propio, documentado; NO es un dato oficial de ningún proveedor).

Entrada: cadena de opciones con 15 min de retraso de Cboe (gratuita): SPX + SPY → futuro ES, NDX + QQQ → futuro NQ.

Método:
  1. Se descartan vencimientos pasados o a más de 45 días y strikes a más de ±15 % del precio. Interés abierto (OI) = el de la cadena
     (cifra de la OCC del cierre anterior; la OCC lo actualiza cada mañana, por eso el GEX del cierre usa el OI de la víspera).
  2. Volatilidad implícita por (vencimiento, strike): la de la opción fuera de dinero (put bajo el precio, call por encima); si no es válida
     (< 2 % o > 300 %) se usa la del otro lado; si tampoco, se descarta. La gamma se recalcula con Black-Scholes (r − q = 0, T = días naturales / 365)
     porque la gamma que publica Cboe viene redondeada a 4 decimales (en NDX casi todas son 0,000x); se usa el mismo convenio de tiempo que la IV de Cboe
     (días naturales / 365) y la comparación con la gamma de Cboe, donde es comparable (≥ 0,002), va en el JSON.
  3. GEX$ de cada opción = gamma × OI × 100 × S² × 1 %  (dólares de delta que hay que re-cubrir por cada 1 % de movimiento).
     Convención de signo: calls +, puts − (supuesto: los creadores de mercado están largos de calls y cortos de puts de los clientes).
     Es una HIPÓTESIS: el OI no dice quién está comprado o vendido. El signo real del posicionamiento no se observa.
  4. SPY y QQQ se pasan a la escala del índice multiplicando el strike por (índice / ETF) y se suman a SPX / NDX por tramos de 10 puntos (ES) y 50 (NQ).
  5. Call Wall = tramo por encima del precio con mayor GEX de calls. Put Wall = tramo por debajo con mayor GEX de puts.
     Gamma Flip = precio al que el GEX neto cambia de signo al recalcular todas las gammas con el precio hipotético (barrido ±12 %).
  6. Conversión a futuro: nivel del futuro = nivel del índice + base del día, con la base = cierre del futuro − cierre del índice en el mismo minuto
     (barras de 5 min de Yahoo). Sin barras de 5 min se usa la base de cierres diarios y se avisa; sin ninguna, el nivel queda solo en el índice.
Solo se guarda histórico cuando el snapshot es del cierre de Nueva York (último dato del índice ≥ 15:59 ET)."""
from __future__ import annotations

import datetime as dt
import math
import re
import statistics

import csvlog
import fuentes
import precios

URL_CBOE = "https://cdn-api.cboe.com/api/global/delayed_quotes/options/{}.json"
URL_FUENTE = "https://www.cboe.com/delayed_quotes/spx/quote_table"
RX = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")
DIAS_MAX = 45
BANDA = 0.15
BARRIDO = 0.12
PASO = 0.0025
MULT = 100
S2PI = 2.5066282746310002
INDICES = {
    "ES": {"nombre": "S&P 500 → futuro ES", "indice": "SPX", "yahoo_idx": "^GSPC", "yahoo_fut": "ES=F", "cadenas": ["_SPX", "SPY"], "tramo": 10, "etf": "SPY"},
    "NQ": {"nombre": "Nasdaq-100 → futuro NQ", "indice": "NDX", "yahoo_idx": "^NDX", "yahoo_fut": "NQ=F", "cadenas": ["_NDX", "QQQ"], "tramo": 50, "etf": "QQQ"},
}


def _bdays(d0, d1):
    n, d = 0, d0
    while d < d1:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def _gamma(S, K, T, sig):
    st = sig * math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * sig * sig * T) / st
    return math.exp(-0.5 * d1 * d1) / (S2PI * S * st)


def _cargar(simbolo):
    j = fuentes.json_(URL_CBOE.format(simbolo), tries=3, timeout=120)
    d = j["data"]
    if not d.get("options") or d.get("current_price") in (None, 0):
        raise RuntimeError(f"cadena {simbolo} vacía")
    return d, j.get("timestamp")


def _procesar(d, sesion):
    """Agrupa por (vencimiento, strike) y fija una IV por grupo. Devuelve (registros, estadísticas, muestra de validación)."""
    spot = float(d["current_price"])
    g, descartes = {}, 0
    muestra = []
    for o in d["options"]:
        m = RX.match(o.get("option") or "")
        if not m:
            continue
        _, ymd, cp, k = m.groups()
        exp = dt.date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:]))
        if exp <= sesion or (exp - sesion).days > DIAS_MAX:
            continue
        K = int(k) / 1000.0
        if abs(K / spot - 1) > BANDA:
            continue
        g.setdefault((exp, K), {})[cp] = (float(o.get("iv") or 0), float(o.get("open_interest") or 0), float(o.get("gamma") or 0))
    reg = []
    for (exp, K), x in g.items():
        otm = "C" if K >= spot else "P"
        otro = "P" if otm == "C" else "C"
        iv = None
        for lado in (otm, otro):
            if lado in x and 0.02 <= x[lado][0] <= 3.0:
                iv = x[lado][0]
                break
        oic, oip = x.get("C", (0, 0, 0))[1], x.get("P", (0, 0, 0))[1]
        if iv is None:
            descartes += (oic > 0) + (oip > 0)
            continue
        if oic <= 0 and oip <= 0:
            continue
        T = max((exp - sesion).days, 0.5) / 365.0
        reg.append((K, T, iv, oic, oip, exp))
        # muestra de validación frente a la gamma que publica Cboe (solo cerca del dinero y con plazo suficiente)
        if abs(K / spot - 1) < 0.03 and T * 365 >= 5:
            lado = otm if otm in x else otro
            if x[lado][2] >= 0.002:   # por debajo, el redondeo a 4 decimales de Cboe domina el error
                muestra.append(abs(_gamma(spot, K, T, iv) / x[lado][2] - 1))
    return reg, {"descartes_oi_sin_iv": descartes, "grupos": len(g)}, muestra


def _gex_neto(registros, S_idx):
    """GEX neto ($ por 1 %) a un precio hipotético del índice. `registros`: lista de (K_nativo, T, iv, oi_c, oi_p, ratio)."""
    tot = 0.0
    for K, T, iv, oic, oip, ratio in registros:
        S = S_idx / ratio
        gm = _gamma(S, K, T, iv) * MULT * S * S * 0.01
        tot += gm * (oic - oip)
    return tot


def _sesion_y_cierre(d):
    """(fecha de sesión, cierre confirmado) a partir de la última operación del subyacente (hora de Nueva York)."""
    lt = d.get("last_trade_time") or ""
    f = dt.datetime.strptime(lt[:19], "%Y-%m-%dT%H:%M:%S")
    return f.date(), (f.hour, f.minute) >= (15, 59) and f.weekday() < 5, f


def _base_futuro(sym_fut, sym_idx, sesion):
    """Base = futuro − índice en el mismo minuto de la sesión. Devuelve dict con la base, el método y la advertencia."""
    err = []
    try:
        idx = [(t, v) for t, v in precios.intradia(sym_idx) if t.date() == sesion]
        precios.pausa()
        fut = {t: v for t, v in precios.intradia(sym_fut)}
        if not idx:
            raise RuntimeError("sin barras del índice en la sesión")
        t_last, c_idx = idx[-1]
        f = fut.get(t_last - dt.timedelta(minutes=5))   # el cierre de la barra de 5 min anterior es el precio del futuro en t_last
        if f is None:
            raise RuntimeError("sin barra del futuro en ese minuto")
        return {"base": round(f - c_idx, 2), "fut": round(f, 2), "idx": round(c_idx, 2), "momento_et": t_last.strftime("%Y-%m-%d %H:%M"),
                "metodo": "intradía 5 min (futuro e índice en el mismo minuto)", "aproximada": False, "fuente": "Yahoo Finance", "errores": err}
    except Exception as e:  # noqa: BLE001
        err.append(f"intradía: {type(e).__name__}: {str(e)[:80]}")
    try:
        fd, _ = precios.diario(sym_fut, "1mo")
        precios.pausa()
        idd, _ = precios.diario(sym_idx, "1mo")
        cf = next(b["c"] for b in fd if b["fecha"] == sesion)
        ci = next(b["c"] for b in idd if b["fecha"] == sesion)
        return {"base": round(cf - ci, 2), "fut": round(cf, 2), "idx": round(ci, 2), "momento_et": None,
                "metodo": "APROXIMADA: cierres diarios (el futuro cierra a las 17:00 ET y el índice a las 16:00 ET)", "aproximada": True, "fuente": "Yahoo Finance", "errores": err}
    except Exception as e:  # noqa: BLE001
        err.append(f"diario: {type(e).__name__}: {str(e)[:80]}")
    return {"base": None, "fut": None, "idx": None, "momento_et": None, "metodo": "SIN DATO: no se pudo calcular la base; niveles solo en el índice", "aproximada": None, "fuente": "Yahoo Finance", "errores": err}


def _calcular(clave, cfg):
    cad, ts_arch = {}, {}
    for s in cfg["cadenas"]:
        cad[s], ts_arch[s] = _cargar(s)
    idx_d = cad[cfg["cadenas"][0]]
    etf_d = cad[cfg["cadenas"][1]]
    sesion, cierre, t_idx = _sesion_y_cierre(idx_d)
    S0 = float(idx_d["current_price"])
    ratio_etf = S0 / float(etf_d["current_price"])
    regs, stats, muestra = [], {}, []
    for s, ratio in ((cfg["cadenas"][0], 1.0), (cfg["cadenas"][1], ratio_etf)):
        r, st, m = _procesar(cad[s], sesion)
        regs += [(K, T, iv, oic, oip, ratio, exp, s) for K, T, iv, oic, oip, exp in r]
        stats[s] = {**st, "opciones": len(r), "spot": float(cad[s]["current_price"]), "ultima_operacion": cad[s].get("last_trade_time")}
        muestra += m
    if len(regs) < 200:
        raise RuntimeError(f"{clave}: solo {len(regs)} grupos válidos de opciones")

    # perfil por tramo (en puntos de índice)
    tr = cfg["tramo"]
    callg, putg = {}, {}
    for K, T, iv, oic, oip, ratio, exp, s in regs:
        S = float(cad[s]["current_price"])
        gm = _gamma(S, K, T, iv) * MULT * S * S * 0.01
        k_eq = K * ratio
        b = round(k_eq / tr) * tr
        callg[b] = callg.get(b, 0.0) + gm * oic
        putg[b] = putg.get(b, 0.0) + gm * oip
    net_spot = sum(callg.values()) - sum(putg.values())
    arriba = {b: v for b, v in callg.items() if b >= S0}
    abajo = {b: v for b, v in putg.items() if b <= S0}
    cw = max(arriba, key=arriba.get) if arriba else None
    pw = max(abajo, key=abajo.get) if abajo else None

    # barrido para el gamma flip
    nat = [(K, T, iv, oic, oip, ratio) for K, T, iv, oic, oip, ratio, _, _ in regs]
    grid = [S0 * (1 + BARRIDO) - i * (S0 * PASO) for i in range(int(2 * BARRIDO / PASO) + 1)]
    grid.sort()
    curva = [(S, _gex_neto(nat, S)) for S in grid]
    cruces = []
    for (s1, g1), (s2, g2) in zip(curva, curva[1:]):
        if g1 == 0:
            cruces.append(s1)
        elif g1 * g2 < 0:
            cruces.append(s1 + (s2 - s1) * (0 - g1) / (g2 - g1))
    flip = min(cruces, key=lambda x: abs(x - S0)) if cruces else None
    pos = net_spot > 0

    def tops(dic, n=5, reverse=True):
        return [{"idx": b, "musd": round(v / 1e6, 1)} for b, v in sorted(dic.items(), key=lambda kv: kv[1], reverse=reverse)[:n]]

    # perfil para el gráfico: ±8 % del precio
    lo, hi = S0 * 0.92, S0 * 1.08
    perfil = [{"k": b, "call": round(callg.get(b, 0) / 1e6, 1), "put": round(-putg.get(b, 0) / 1e6, 1), "net": round((callg.get(b, 0) - putg.get(b, 0)) / 1e6, 1)}
              for b in sorted(set(callg) | set(putg)) if lo <= b <= hi]
    venc = sorted({str(e) for *_, e, _s in regs})
    return {"clave": clave, "nombre": cfg["nombre"], "indice": cfg["indice"], "sesion": sesion.isoformat(), "cierre_confirmado": cierre,
            "ultima_operacion_et": t_idx.strftime("%Y-%m-%d %H:%M:%S"), "spot_idx": round(S0, 2), "ratio_etf": round(ratio_etf, 4),
            "gex_neto_musd": round(net_spot / 1e6, 1), "gex_calls_musd": round(sum(callg.values()) / 1e6, 1), "gex_puts_musd": round(-sum(putg.values()) / 1e6, 1),
            "regimen": "POSITIVA" if pos else "NEGATIVA",
            "call_wall": {"idx": cw, "musd": round(callg[cw] / 1e6, 1)} if cw is not None else None,
            "put_wall": {"idx": pw, "musd": round(putg[pw] / 1e6, 1)} if pw is not None else None,
            "flip": {"idx": round(flip, 1)} if flip is not None else None, "otros_cruces_idx": [round(c, 1) for c in cruces if c != flip],
            "top_calls": tops(callg), "top_puts": tops(putg), "perfil": perfil,
            "curva": [[round(s, 1), round(g / 1e6, 1)] for s, g in curva],
            "vencimientos": venc, "n_vencimientos": len(venc), "n_grupos": len(regs), "cadenas": stats,
            "validacion_gamma": {"n": len(muestra), "mediana_error_rel_pct": round(100 * statistics.median(muestra), 2) if muestra else None,
                                 "p90_error_rel_pct": round(100 * sorted(muestra)[int(0.9 * len(muestra))], 2) if len(muestra) > 10 else None},
            "sesion_dt": sesion}


def _a_futuro(M, base):
    b = base.get("base")
    for k in ("call_wall", "put_wall", "flip"):
        x = M.get(k)
        if x:
            x["fut"] = round(x["idx"] + b, 1) if b is not None else None
    M["spot_fut"] = round(M["spot_idx"] + b, 2) if b is not None else None
    M["base"] = base
    for k in ("top_calls", "top_puts"):
        for x in M[k]:
            x["fut"] = round(x["idx"] + b, 1) if b is not None else None
    for p in M["perfil"]:
        p["fut"] = round(p["k"] + b, 1) if b is not None else None
    return M


def _texto(M):
    nm, fut = M["clave"], M["spot_fut"]
    cw, pw, fl = M["call_wall"], M["put_wall"], M["flip"]
    f = lambda x: (f"{x['fut']:,.0f}".replace(",", ".") if x and x.get("fut") is not None else "—")  # noqa: E731
    i = lambda x: (f"{x['idx']:,.0f}".replace(",", ".") if x else "—")  # noqa: E731
    sig = "positiva" if M["regimen"] == "POSITIVA" else "negativa"
    niv = (f"Call Wall {f(cw)} {nm} ({i(cw)} {M['indice']}), Put Wall {f(pw)} ({i(pw)})"
           + (f", Gamma Flip {f(fl)} ({i(fl)})" if fl else ", sin Gamma Flip dentro de ±12 %"))
    return niv + f"; gamma {sig} ({M['gex_neto_musd'] / 1000:+.1f} mm$ por 1 %)".replace(".", ",")


def _roll(d):
    """¿Cae `d` en la ventana de vencimiento trimestral de ES/NQ (3.er viernes de mar/jun/sep/dic − 8 días … + 0)?"""
    if d.month not in (3, 6, 9, 12):
        return False
    primero = d.replace(day=1)
    viernes = [primero + dt.timedelta(days=i) for i in range(31) if (primero + dt.timedelta(days=i)).month == d.month and (primero + dt.timedelta(days=i)).weekday() == 4]
    t = viernes[2]
    return t - dt.timedelta(days=8) <= d <= t


def revisar(clave, historico, ohlc):
    """Compara cada sesión guardada con la barra del futuro de la SESIÓN SIGUIENTE. ohlc: [{fecha,o,h,l,c}] del futuro."""
    filas = sorted((r for r in historico if r.get("indice") == clave), key=lambda r: r["fecha_sesion"], reverse=True)
    by = sorted(ohlc, key=lambda b: b["fecha"])
    out = []
    for r in filas:
        d = dt.date.fromisoformat(r["fecha_sesion"])
        sig = next((b for b in by if b["fecha"] > d), None)
        e = {"fecha_sesion": r["fecha_sesion"], "spot_fut": _f(r.get("spot_fut")), "niveles": {}}
        if sig is None:
            e["estado"] = "PENDIENTE"
        elif _roll(d) or _roll(sig["fecha"]):
            e["estado"] = "ROLL"
            e["nota"] = "Ventana de vencimiento trimestral del futuro: la sesión siguiente cotiza otro contrato; no se evalúa."
        else:
            e["estado"] = "EVALUADA"
            e["sesion_siguiente"] = {"fecha": sig["fecha"].isoformat(), "o": sig["o"], "h": sig["h"], "l": sig["l"], "c": sig["c"]}
            for k, nombre in (("call_wall_fut", "Call Wall"), ("put_wall_fut", "Put Wall"), ("flip_fut", "Gamma Flip")):
                L = _f(r.get(k))
                if L is None:
                    continue
                tocado = sig["l"] <= L <= sig["h"]
                if k == "call_wall_fut":
                    res = ("RECHAZADO" if sig["c"] < L else "SUPERADO") if sig["h"] >= L else "NO TOCADO"
                elif k == "put_wall_fut":
                    res = ("DEFENDIDO" if sig["c"] > L else "ROTO") if sig["l"] <= L else "NO TOCADO"
                else:
                    res = "CERRÓ POR ENCIMA" if sig["c"] > L else "CERRÓ POR DEBAJO"
                e["niveles"][nombre] = {"nivel": L, "tocado": tocado or (res not in ("NO TOCADO",) and k != "flip_fut"), "resultado": res,
                                        "dist_cierre": round(sig["c"] - L, 1)}
        out.append(e)
    res = {}
    for nombre in ("Call Wall", "Put Wall", "Gamma Flip"):
        ev = [x["niveles"][nombre] for x in out if x["estado"] == "EVALUADA" and nombre in x["niveles"]]
        tocados = [v for v in ev if v["resultado"] not in ("NO TOCADO",)]
        if nombre == "Call Wall":
            ok = sum(1 for v in tocados if v["resultado"] == "RECHAZADO")
        elif nombre == "Put Wall":
            ok = sum(1 for v in tocados if v["resultado"] == "DEFENDIDO")
        else:
            ok = None
        res[nombre] = {"evaluadas": len(ev), "tocadas": len(tocados), "respetadas": ok}
    return {"sesiones": out, "resumen": res}


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def medir():
    from time import time as _t
    out, errores, base_err = {}, {}, {}
    for clave, cfg in INDICES.items():
        try:
            M = _calcular(clave, cfg)
            base = _base_futuro(cfg["yahoo_fut"], cfg["yahoo_idx"], M.pop("sesion_dt"))
            precios.pausa()
            _a_futuro(M, base)
            M["resumen_texto"] = _texto(M)
            out[clave] = M
        except Exception as e:  # noqa: BLE001
            errores[clave] = f"{type(e).__name__}: {e}"
    if not out:
        raise RuntimeError("Cboe no devolvió ninguna cadena válida: " + "; ".join(f"{k}: {v}" for k, v in errores.items())[:300])
    return {"indices": out, "errores": errores, "fuente": "Cboe · cadena de opciones con 15 min de retraso (cdn-api.cboe.com)", "url": URL_FUENTE,
            "etiqueta": "CRITERIO NEXORA", "metodo": re.sub(r"\n {4,}", " ", __doc__.split("Método:")[1].split("Solo se guarda")[0].strip()), "dias_max": DIAS_MAX, "banda_strikes": BANDA}


def guardar_historico(M):
    """Memoria permanente: solo se añade y solo si el snapshot es del cierre de Nueva York (una fila por sesión e índice)."""
    filas = []
    for clave, x in M["indices"].items():
        if not x["cierre_confirmado"]:
            continue
        g = lambda d: (d or {}).get("idx", "")  # noqa: E731
        h = lambda d: (d or {}).get("fut", "")  # noqa: E731
        filas.append({"fecha_sesion": x["sesion"], "indice": clave, "spot_idx": x["spot_idx"], "base": x["base"]["base"] if x["base"]["base"] is not None else "",
                      "base_metodo": "5m" if x["base"]["aproximada"] is False else "diaria" if x["base"]["aproximada"] else "sin dato",
                      "spot_fut": x["spot_fut"] if x["spot_fut"] is not None else "",
                      "call_wall_idx": g(x["call_wall"]), "put_wall_idx": g(x["put_wall"]), "flip_idx": g(x["flip"]),
                      "call_wall_fut": h(x["call_wall"]), "put_wall_fut": h(x["put_wall"]), "flip_fut": h(x["flip"]),
                      "gex_neto_musd": x["gex_neto_musd"], "regimen": x["regimen"], "n_vencimientos": x["n_vencimientos"], "n_grupos": x["n_grupos"],
                      "ultima_operacion_et": x["ultima_operacion_et"]})
    return csvlog.anadir("historico_gamma.csv", filas, ("fecha_sesion", "indice"))


if __name__ == "__main__":
    import json
    M = medir()
    for k, x in M["indices"].items():
        print(k, x["sesion"], "cierre" if x["cierre_confirmado"] else "INTRADÍA", "| spot", x["spot_idx"], "fut", x["spot_fut"], "| base", x["base"]["base"], x["base"]["metodo"])
        print("   ", x["resumen_texto"])
        print("   GEX neto", x["gex_neto_musd"], "calls", x["gex_calls_musd"], "puts", x["gex_puts_musd"], "| grupos", x["n_grupos"], "venc", x["n_vencimientos"], "| val", x["validacion_gamma"])
        print("   top calls", x["top_calls"][:3], "top puts", x["top_puts"][:3], "cruces", x["otros_cruces_idx"])
    print(M["errores"])
