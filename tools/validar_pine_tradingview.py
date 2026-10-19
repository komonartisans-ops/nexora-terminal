#!/usr/bin/env python3
"""Compila un script Pine con el compilador de TradingView (endpoint público pine-facade, usuario Guest; solo compila, no publica ni guarda nada).
Uso:  python tools/validar_pine_tradingview.py plataformas/tradingview/NexoraNiveles.pine
Salida: «COMPILA SIN ERRORES» o la lista de errores con línea y columna. Un script con un error deliberado debe fallar (control negativo)."""
import json
import sys
import urllib.request
import uuid

URL = "https://pine-facade.tradingview.com/pine-facade/translate_light?user_name=Guest&pine_id=TEMP"


def compilar(fuente):
    b = uuid.uuid4().hex
    cuerpo = (f"--{b}\r\nContent-Disposition: form-data; name=\"source\"\r\n\r\n{fuente}\r\n--{b}--\r\n").encode("utf-8")
    req = urllib.request.Request(URL, data=cuerpo, headers={"Content-Type": "multipart/form-data; boundary=" + b, "Origin": "https://www.tradingview.com", "User-Agent": "Mozilla/5.0"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8"))


def errores(j):
    r = j.get("result") or {}
    out = []
    for k in ("errors2", "errors"):
        for e in r.get(k) or []:
            s = e.get("start") or {}
            out.append(f"línea {s.get('line')}, col {s.get('column')}: {e.get('message')}")
    if not j.get("success") and not out:
        out.append(str(j.get("reason") or j)[:300])
    return out


if __name__ == "__main__":
    src = open(sys.argv[1], encoding="utf-8").read()
    j = compilar(src)
    e = errores(j)
    ver = (j.get("result") or {}).get("scriptTitle") or ""
    adv = [w.get("message") for w in ((j.get("result") or {}).get("warnings2") or [])]
    if e:
        print("ERRORES:", *e, sep="\n  ")
        sys.exit(1)
    print("COMPILA SIN ERRORES", f"· título: {ver}" if ver else "", f"· advertencias: {adv}" if adv else "")
