"""NEXORA · flujos diarios de los ETF spot de bitcoin y de ether de EE. UU. (millones de $).

FUENTE: Farside Investors (farside.co.uk/btc/ y /eth/). Es la única fuente gratuita que agrega todos los emisores; no hay API ni fichero oficial
(IBIT, FBTC… publican por separado) y es una TABLA HTML, así que el módulo se protege de que cambie:
  · la cabecera debe traer los tickers y la columna «Total»; cada fila debe tener tantas celdas como tickers + 2;
  · el Total de cada día debe ser igual a la suma de los ETF (±0,3 M$ por redondeos); la fila que no cuadra se descarta y se cuenta;
  · si no queda ninguna fila válida de los últimos 7 días → SIN DATO (excepción), nunca una cifra dudosa.
HORA DE CORTE: la cifra es del DÍA DE NEGOCIACIÓN D (hasta el cierre de EE. UU., 16:00 ET). Farside no publica hora fija: la web lo muestra cuando lo recibe
(con el día D ya visible a primera hora de la mañana siguiente en UTC). Una cifra puede corregirse después: el histórico (data/historico_etf_flujos.csv,
solo-añadir) guarda cada valor distinto como una fila nueva con su hora de captura, así que las revisiones se ven.
Paréntesis = salidas (negativo). Sin IA, sin claves."""
from __future__ import annotations

import datetime as dt
import html
import re

import fuentes

PARES = {"btc": ("Bitcoin", "https://farside.co.uk/btc/"), "eth": ("Ether", "https://farside.co.uk/eth/")}
FILA_FECHA = re.compile(r"\d{2} \w{3} \d{4}$")


def _celdas(fila):
    return [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", x))).strip() for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", fila, flags=re.S)]


def _num(s):
    s = s.strip()
    if s in ("", "-"):
        return 0.0
    return float(s.replace(",", "").replace("(", "-").replace(")", "").replace("*", ""))


def parsear(texto_html):
    """(tickers, filas válidas [(fecha, total, {ticker: valor})], n_descartadas). Lanza ValueError si la estructura no es la esperada."""
    filas = [_celdas(r) for r in re.findall(r"<tr[^>]*>(.*?)</tr>", texto_html, flags=re.S)]
    cab = next((c for c in filas if len(c) >= 4 and c[0] == "" and all(re.fullmatch(r"[A-Z]{3,5}", x) for x in c[1:-1] if x) and c[-1] == ""), None)
    if not cab or not any(c and c[-1] == "Total" for c in filas):
        raise ValueError("estructura de Farside distinta de la esperada (sin tickers o sin columna Total)")
    tickers = [x for x in cab[1:-1]]
    ok, mal = [], 0
    for c in filas:
        if not c or not FILA_FECHA.match(c[0]):
            continue
        try:
            if len(c) != len(tickers) + 2:
                raise ValueError("celdas")
            f = dt.datetime.strptime(c[0], "%d %b %Y").date()
            v = [_num(x) for x in c[1:]]
            if abs(sum(v[:-1]) - v[-1]) > 0.3:
                raise ValueError("el total no cuadra")
            ok.append((f, v[-1], {t: x for t, x in zip(tickers, v[:-1])}))
        except ValueError:
            mal += 1
    return tickers, ok, mal


def medir(hoy=None):
    hoy = hoy or dt.date.today()
    out, err = {}, {}
    for k, (nombre, url) in PARES.items():
        try:
            tickers, filas, mal = parsear(fuentes.texto(url, tries=3, timeout=45))
            if not filas or (hoy - filas[-1][0]).days > 7:
                raise ValueError("sin ninguna fila válida de los últimos 7 días")
            filas.sort(key=lambda x: x[0])
            f, tot, por = filas[-1]
            out[k] = {"nombre": nombre, "serie": [[d.isoformat(), t] for d, t, _ in filas],
                      "ultimo": {"fecha": f.isoformat(), "total_musd": tot, "por_etf": {t: v for t, v in por.items() if v}},
                      "acum_5d_musd": round(sum(t for _, t, _ in filas[-5:]), 1), "acum_dias": len(filas), "filas_descartadas": mal, "tickers": tickers,
                      "fuente": url, "url": url}
        except Exception as e:  # noqa: BLE001
            err[k] = f"{type(e).__name__}: {str(e)[:120]}"
            out[k] = {"nombre": nombre, "sin_dato": True, "fuente": url, "url": url}
    if len(err) == len(PARES):
        raise RuntimeError("Farside no respondió o cambió su estructura: " + "; ".join(f"{k}: {v}" for k, v in err.items()))
    return {"etf": out, "errores": err, "fuente": "Farside Investors (tabla HTML, validada fila a fila)",
            "corte": "Día de negociación D hasta el cierre de EE. UU. (16:00 ET); Farside no fija hora de publicación; las correcciones se guardan como filas nuevas en data/historico_etf_flujos.csv"}
