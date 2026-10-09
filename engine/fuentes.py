"""NEXORA · descargas HTTP gratuitas (solo biblioteca estándar). Reintenta y lanza la última excepción: quien llama decide qué es SIN DATO."""
from __future__ import annotations

import json
import time
import urllib.request

UA_NAV = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def get(url, tries=3, timeout=45, ua=UA_NAV, accept=None):
    """Bytes de `url`. `ua` distinto por fuente: el FMI rechaza el UA de navegador y acepta uno de biblioteca."""
    last = None
    for k in range(tries):
        try:
            h = {"User-Agent": ua}
            if accept:
                h["Accept"] = accept
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (k + 1))
    raise last


def texto(url, **kw):
    return get(url, **kw).decode("utf-8", errors="replace")


def json_(url, **kw):
    return json.loads(get(url, **kw).decode("utf-8"))
