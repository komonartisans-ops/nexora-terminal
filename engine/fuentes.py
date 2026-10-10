"""NEXORA · descargas HTTP gratuitas (solo biblioteca estándar). Reintenta y lanza la última excepción: quien llama decide qué es SIN DATO."""
from __future__ import annotations

import json
import shutil
import ssl
import subprocess
import time
import urllib.request

UA_NAV = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def _es_error_tls(e):
    """True si el fallo es de VERIFICACIÓN de certificado (cadena incompleta o cruce caducado), no de red."""
    r = getattr(e, "reason", e)
    return isinstance(r, ssl.SSLCertVerificationError) or isinstance(e, ssl.SSLCertVerificationError)


def _curl(url, timeout, ua, accept):
    """Misma descarga con curl. Sigue VERIFICANDO el certificado (usa su propia pila TLS y su propio almacén de raíces):
    Cboe sirve una cadena de Let's Encrypt con un cruce ISRG X2→X1 caducado que el OpenSSL de algunos equipos rechaza y curl acepta."""
    exe = shutil.which("curl")
    if not exe:
        raise RuntimeError("curl no disponible")
    cmd = [exe, "-sS", "-L", "--fail", "--max-time", str(int(timeout)), "-A", ua]
    if accept:
        cmd += ["-H", f"Accept: {accept}"]
    r = subprocess.run(cmd + [url], capture_output=True, timeout=timeout + 20)
    if r.returncode != 0:
        raise RuntimeError(f"curl código {r.returncode}: {r.stderr.decode('utf-8', 'replace').strip()[:140]}")
    return r.stdout


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
            if _es_error_tls(e):  # no se desactiva la verificación: se prueba otra pila TLS que sí la supera
                try:
                    return _curl(url, timeout, ua, accept)
                except Exception as e2:  # noqa: BLE001
                    last = e2
            time.sleep(1.5 * (k + 1))
    raise last


def texto(url, **kw):
    return get(url, **kw).decode("utf-8", errors="replace")


def json_(url, **kw):
    return json.loads(get(url, **kw).decode("utf-8"))
