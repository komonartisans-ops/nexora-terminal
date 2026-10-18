#!/usr/bin/env python3
"""NEXORA · calendario oficial anual de BLS (IPC, IPP, Empleo, JOLTS) y BEA (PIB, PCE). Sin IA, gratis, sin claves.

Se descarga de las páginas oficiales (bls.gov/schedule/news_release/*.htm y bea.gov/news/schedule), se guarda en data/calendario_oficial_anual.json con su fuente y su
fecha de descarga y se usa como RESPALDO del «próximo dato» cuando el calendario de FRED no lo trae. Si tampoco está aquí: SIN DATO. No se infiere ninguna fecha.
Se refresca como máximo una vez a la semana; si la descarga falla se conserva la copia anterior (con el error anotado)."""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(HERE)
CABECERAS = {"User-Agent": "Mozilla/5.0 (nexora-terminal; datos publicos)", "Accept": "text/html,*/*"}   # bls.gov rechaza las peticiones sin Accept
CADUCA_DIAS = 7
MESES = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}

# página oficial → (serie(s) FRED que publica, nombre del evento, organismo)
BLS_PAGINAS = {
    "cpi": (["CPIAUCSL", "CPILFESL"], "IPC EE. UU. (CPI)"), "ppi": (["PPIFIS"], "Precios de producción (PPI)"),
    "empsit": (["PAYEMS", "UNRATE"], "Empleo EE. UU. (NFP, paro, salarios)"), "jolts": (["JTSJOL"], "Vacantes JOLTS"),
}
BEA_URL = "https://www.bea.gov/news/schedule"


def _get(url, t=40):
    return urllib.request.urlopen(urllib.request.Request(url, headers=CABECERAS), timeout=t).read().decode("utf-8", "replace")


def _txt(s):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s))).strip()


def _fecha_bls(s):
    """'Nov. 10, 2026' / 'Sept. 3, 2026' → date."""
    m = re.match(r"([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),\s*(\d{4})", s.strip())
    return dt.date(int(m.group(3)), MESES[m.group(1).lower()], int(m.group(2))) if m else None


def _hora(s):
    m = re.search(r"(\d{1,2}):(\d{2})\s*([AP])M", s, re.I)
    if not m:
        return None
    h = int(m.group(1)) % 12 + (12 if m.group(3).upper() == "P" else 0)
    return f"{h:02d}:{m.group(2)}"


def parsear_bls(htm, pagina):
    """Filas «Reference Month · Release Date · Release Time» de una página de calendario de BLS."""
    series, nombre = BLS_PAGINAS[pagina]
    out = []
    for fila in re.findall(r"<tr[^>]*>(.*?)</tr>", htm, re.S):
        c = [_txt(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", fila, re.S)]
        if len(c) < 3:
            continue
        f = _fecha_bls(c[1])
        mp = re.match(r"([A-Za-z]+)\s+(\d{4})", c[0])
        if not f or not mp or mp.group(1)[:3].lower() not in MESES:
            continue
        per = dt.date(int(mp.group(2)), MESES[mp.group(1)[:3].lower()], 1)
        out.append({"organismo": "BLS", "series": series, "evento": nombre, "periodo": per.isoformat(), "fecha": f.isoformat(), "hora_et": _hora(c[2]),
                    "url": f"https://www.bls.gov/schedule/news_release/{pagina}.htm"})
    return out


def parsear_bea(htm):
    """Filas de bea.gov/news/schedule: PIB (GDP, estimaciones) y Renta y gasto personal (PCE). Año de la cabecera «Year 2026»."""
    ym = re.search(r"Year\s+(\d{4})", htm)
    if not ym:
        return []
    anio = int(ym.group(1))
    out = []
    for fila in re.findall(r"<tr[^>]*>(.*?)</tr>", htm, re.S):
        d = re.search(r'class="release-date">\s*([A-Za-z]+)\s+(\d{1,2})', fila)
        t = re.search(r'class="release-title[^"]*"[^>]*>(.*?)</td>', fila, re.S)
        if not d or not t or d.group(1)[:3].lower() not in MESES:
            continue
        titulo = _txt(t.group(1))
        f = dt.date(anio, MESES[d.group(1)[:3].lower()], int(d.group(2)))
        hora = _hora(_txt(fila))
        mq = re.search(r"(\d)(?:st|nd|rd|th) Quarter (\d{4})", titulo)
        mm = re.search(r"Personal Income and Outlays,\s*([A-Za-z]+)\s+(\d{4})", titulo)
        if titulo.startswith("GDP (") and "State" not in titulo and mq:
            q = int(mq.group(1))
            out.append({"organismo": "BEA", "series": ["GDPC1"], "evento": "PIB EE. UU. · " + re.sub(r",.*", "", titulo), "periodo": dt.date(int(mq.group(2)), 3 * q - 2, 1).isoformat(),
                        "fecha": f.isoformat(), "hora_et": hora, "url": BEA_URL})
        elif mm and mm.group(1)[:3].lower() in MESES:
            out.append({"organismo": "BEA", "series": ["PCEPI", "PCEPILFE"], "evento": "Renta y gasto personal (PCE)", "periodo": dt.date(int(mm.group(2)), MESES[mm.group(1)[:3].lower()], 1).isoformat(),
                        "fecha": f.isoformat(), "hora_et": hora, "url": BEA_URL})
    return out


def descargar(raiz=RAIZ, ahora=None, get=_get, forzar=False):
    """Descarga y guarda data/calendario_oficial_anual.json (como mucho una vez por semana). Devuelve el JSON guardado."""
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    ruta = os.path.join(raiz, "data", "calendario_oficial_anual.json")
    previo = leer(raiz)
    if previo and not forzar:
        try:
            antes = dt.datetime.strptime(previo["descargado_utc"], "%Y-%m-%d %H:%M UTC").replace(tzinfo=dt.timezone.utc)
            if (ahora - antes).days < CADUCA_DIAS and not previo.get("errores"):
                return previo
        except (KeyError, ValueError):
            pass
    eventos, errores, fuentes = [], {}, {}
    stamp = ahora.strftime("%Y-%m-%d %H:%M UTC")
    for pagina in BLS_PAGINAS:
        url = f"https://www.bls.gov/schedule/news_release/{pagina}.htm"
        try:
            ev = parsear_bls(get(url), pagina)
            if not ev:
                raise ValueError("la página no trae filas de calendario")
            eventos += ev
            fuentes[f"BLS {pagina}"] = {"url": url, "descargado_utc": stamp, "filas": len(ev)}
        except Exception as e:  # noqa: BLE001
            errores[f"BLS {pagina}"] = f"{type(e).__name__}: {str(e)[:80]}"
    try:
        ev = parsear_bea(get(BEA_URL))
        if not ev:
            raise ValueError("la página no trae filas de calendario")
        eventos += ev
        fuentes["BEA schedule"] = {"url": BEA_URL, "descargado_utc": stamp, "filas": len(ev)}
    except Exception as e:  # noqa: BLE001
        errores["BEA schedule"] = f"{type(e).__name__}: {str(e)[:80]}"
    bajo = bool(eventos)           # ¿se descargó algo nuevo en esta pasada?
    if previo and errores:          # lo que falló conserva la copia anterior (con su propia fecha de descarga); lo que bajó se actualiza
        malos = {k.split()[0] if k.startswith("BEA") else k for k in errores}
        for e in previo.get("eventos", []):
            clave = "BEA" if e["organismo"] == "BEA" else "BLS " + e["url"].rsplit("/", 1)[1].replace(".htm", "")
            if any(clave.startswith(m) or m.startswith(clave) for m in malos) and e not in eventos:
                eventos.append(e)
        for k, v in (previo.get("fuentes") or {}).items():
            fuentes.setdefault(k, v)
    out = {"descargado_utc": stamp if bajo else (previo or {}).get("descargado_utc"), "fuentes": fuentes, "errores": errores,
           "nota": "Calendarios oficiales de BLS y BEA. Respaldo del «próximo dato» cuando FRED no lo trae; sin fecha aquí = SIN DATO (nunca se infiere).", "eventos": sorted(eventos, key=lambda e: (e["fecha"], e["evento"]))}
    if eventos:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
    return out


def leer(raiz=RAIZ):
    try:
        with open(os.path.join(raiz, "data", "calendario_oficial_anual.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def proximo(raiz, sid, desde):
    """Primer evento oficial con fecha ≥ desde que publica la serie `sid`: {organismo, evento, periodo, fecha, hora_et, url, descargado_utc} o None."""
    C = leer(raiz)
    if not C:
        return None
    cand = [e for e in C.get("eventos", []) if sid in e["series"] and e["fecha"] >= desde.isoformat()]
    if not cand:
        return None
    e = min(cand, key=lambda x: x["fecha"])
    fu = (C.get("fuentes") or {}).get("BEA schedule" if e["organismo"] == "BEA" else "BLS " + e["url"].rsplit("/", 1)[1].replace(".htm", "")) or {}
    return {**e, "descargado_utc": fu.get("descargado_utc") or C.get("descargado_utc")}


if __name__ == "__main__":
    r = descargar(forzar="--forzar" in sys.argv)
    print(len(r["eventos"]), "eventos ·", r["descargado_utc"], "· errores:", r["errores"] or "ninguno")
