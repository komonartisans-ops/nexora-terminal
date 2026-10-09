"""NEXORA · titulares de bancos centrales desde sus RSS oficiales. Solo titular, fecha, orador y enlace: sin resúmenes ni IA.

Cada fuente falla por separado y queda marcada. Memoria permanente en data/historico_noticias.csv (se añade, no duplica)."""
from __future__ import annotations

import datetime as dt
import email.utils
import re
import xml.etree.ElementTree as ET

import csvlog
import fuentes

FUENTES = [
    # clave, banco, tipo por defecto, url RSS, página humana
    ("fed_press", "Fed", "Comunicado", "https://www.federalreserve.gov/feeds/press_all.xml", "https://www.federalreserve.gov/newsevents/pressreleases.htm"),
    ("fed_speech", "Fed", "Discurso", "https://www.federalreserve.gov/feeds/speeches.xml", "https://www.federalreserve.gov/newsevents/speeches-testimony.htm"),
    ("bce", "BCE", "Comunicado", "https://www.ecb.europa.eu/rss/press.html", "https://www.ecb.europa.eu/press/html/index.en.html"),
    ("boj", "BoJ", "Novedad", "https://www.boj.or.jp/en/rss/whatsnew.xml", "https://www.boj.or.jp/en/whatsnew.htm"),
    ("boe", "BoE", "Noticia", "https://www.bankofengland.co.uk/rss/news", "https://www.bankofengland.co.uk/news"),
    ("tesoro", "Tesoro EE. UU.", "Comunicado", "https://home.treasury.gov/news/press-releases/feed", "https://home.treasury.gov/news/press-releases"),
]
BCE_TIPO = {"/pr/": "Comunicado", "/key/": "Discurso", "/inter/": "Entrevista", "/accounts/": "Actas", "/pressconf": "Rueda de prensa", "/sp": "Discurso", "/blog": "Blog"}
MAX_POR_FUENTE = 40


def _fecha(txt):
    if not txt:
        return None
    try:
        d = email.utils.parsedate_to_datetime(txt.strip())
        return d.astimezone(dt.timezone.utc) if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:  # noqa: BLE001
        pass
    try:
        d = dt.datetime.fromisoformat(txt.strip().replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def _t(el, tag):
    x = el.find(tag)
    return (x.text or "").strip() if x is not None and x.text else ""


def _limpia(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    return re.sub(r"\s+", " ", s).strip()


def _orador(clave, titulo, autor):
    if clave == "fed_speech" and "," in titulo:
        o, resto = titulo.split(",", 1)
        if len(o) <= 40:
            return o.strip(), resto.strip()
    if clave == "bce" and ":" in titulo:
        o, resto = titulo.split(":", 1)
        if len(o) <= 40 and len(o.split()) <= 4:
            return o.strip(), resto.strip()
    return (autor or None), titulo


def _parsea(clave, banco, tipo0, xml):
    raiz = ET.fromstring(xml)
    items = raiz.findall(".//item")
    out = []
    for it in items[:MAX_POR_FUENTE]:
        titulo = _limpia(_t(it, "title"))
        enlace = _t(it, "link") or _t(it, "guid")
        f = _fecha(_t(it, "pubDate")) or _fecha(_t(it, "{http://purl.org/dc/elements/1.1/}date"))
        if not titulo or not enlace:
            continue
        autor = _t(it, "{http://purl.org/dc/elements/1.1/}creator") or _t(it, "author")
        orador, tit = _orador(clave, titulo, autor)
        tipo = tipo0
        if clave == "bce":
            tipo = next((v for k, v in BCE_TIPO.items() if k in enlace), tipo0)
        out.append({"banco": banco, "tipo": tipo, "titulo": tit, "orador": orador, "fecha_utc": f.strftime("%Y-%m-%d %H:%M") if f else None,
                    "fecha": f.date().isoformat() if f else None, "enlace": enlace.replace("europa.eu//", "europa.eu/"), "fuente": clave})
    if not out:
        raise RuntimeError("RSS sin elementos legibles")
    return out


def medir():
    todo, estado = [], {}
    for clave, banco, tipo0, url, pagina in FUENTES:
        try:
            items = _parsea(clave, banco, tipo0, fuentes.get(url, tries=2, timeout=30))
            todo += items
            estado[clave] = {"banco": banco, "ok": True, "n": len(items), "url": url, "pagina": pagina, "ultimo": max((i["fecha_utc"] or "" for i in items), default=None)}
        except Exception as e:  # noqa: BLE001
            estado[clave] = {"banco": banco, "ok": False, "n": 0, "url": url, "pagina": pagina, "error": f"{type(e).__name__}: {str(e)[:160]}"}
    if not todo:
        raise RuntimeError("ningún RSS responde")
    # sin fecha → al final; nunca se inventa una fecha
    todo.sort(key=lambda i: i["fecha_utc"] or "", reverse=True)
    ahora = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
    csvlog.anadir("historico_noticias.csv", [{"enlace": i["enlace"], "fecha_utc": i["fecha_utc"] or "", "banco": i["banco"], "tipo": i["tipo"],
                                              "orador": i["orador"] or "", "titulo": i["titulo"], "visto_utc": ahora} for i in todo], ("enlace",))
    return {"items": todo[:150], "fuentes": estado, "n_total": len(todo),
            "nota": "Solo titular, fecha, orador y enlace procedentes de los RSS oficiales. NEXORA no resume ni interpreta el contenido."}


if __name__ == "__main__":
    r = medir()
    for k, v in r["fuentes"].items():
        print(k, v["ok"], v.get("n"), v.get("ultimo") or v.get("error"))
    for i in r["items"][:12]:
        print(i["fecha_utc"], i["banco"], i["tipo"], "|", i["orador"], "|", i["titulo"][:70])
