"""NEXORA · tipo oficial del Banco de Japón leído de la web del propio BoJ (FRED/OCDE va con años de retraso).

El BoJ publica la «guideline» de operaciones de mercado en su portada: «The Bank will encourage the uncollateralized
overnight call rate to remain at around X percent». La fecha de la decisión sale del último comunicado
«Change in the Guideline for Money Market Operations» (kAAMMDDa.pdf) del índice de comunicados del año.
Si la web cambia de formato y no se reconoce el valor, se lanza un error: nunca se estima."""
from __future__ import annotations

import re
from urllib.parse import urljoin

import fuentes

PORTADA = "https://www.boj.or.jp/en/"


def tipo_oficial():
    h = fuentes.texto(PORTADA)
    m = re.search(r"remain\s+at\s+around\s+([0-9]+(?:\.[0-9]+)?)\s+percent", h, flags=re.I)
    if not m:
        raise RuntimeError("BoJ: la portada ya no trae la frase de la guideline (formato cambiado)")
    valor = float(m.group(1))
    if not 0 <= valor <= 10:
        raise RuntimeError(f"BoJ: valor fuera de rango ({valor})")
    enlace = re.search(r'<a href="([^"]*state_\d{4}/index\.htm)"[^>]*>\s*The Bank will encourage', h)
    url_com = urljoin(PORTADA, enlace.group(1)) if enlace else "https://www.boj.or.jp/en/mopo/mpmdeci/index.htm"
    fecha = None
    try:
        idx = fuentes.texto(url_com)
        for a in re.finditer(r'<a [^>]*href="([^"]*/k(\d{2})(\d{2})(\d{2})a\.pdf)"[^>]*>\s*([^<]*)', idx):
            if re.match(r"\s*Change in the Guideline", a.group(5)):
                fecha = f"20{a.group(2)}-{a.group(3)}-{a.group(4)}"
                break
    except Exception:  # noqa: BLE001  la fecha es accesoria: sin ella se dice «fecha de decisión no localizada»
        pass
    return {"valor": valor, "fecha": fecha, "texto": m.group(0), "fuente": "Banco de Japón (boj.or.jp, portada: guideline vigente)",
            "url": url_com, "nota": None if fecha else "fecha de la decisión no localizada en la web del BoJ"}


if __name__ == "__main__":
    print(tipo_oficial())
