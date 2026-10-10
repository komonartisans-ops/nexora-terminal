"""Capturas de la fase 7 (mapa, tono, SKEW) en escritorio y móvil. Uso: python tools/capturas7.py [URL_BASE] [DIR_SALIDA]"""
import os
import sys
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765"
OUT = sys.argv[2] if len(sys.argv) > 2 else "capturas"
CHROME = os.path.expandvars(r"%LOCALAPPDATA%\ms-playwright\chromium-1223\chrome-win64\chrome.exe")
os.makedirs(OUT, exist_ok=True)
with sync_playwright() as p:
    kw = {"executable_path": CHROME} if os.path.exists(CHROME) else {}
    b = p.chromium.launch(**kw)
    for w, h, tag in ((1440, 900, "pc"), (390, 844, "movil")):
        pg = b.new_page(viewport={"width": w, "height": h})
        errs = []
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errs.append(str(e)))
        for name in ("mapa", "tono", "skew"):
            pg.goto(f"{BASE}/#/{name}")
            pg.reload()
            pg.wait_for_timeout(4500)
            pg.screenshot(path=f"{OUT}/{name}_{tag}.png", full_page=True)
            print("ok", name, tag)
        if tag == "pc":  # capa de inflación con un país seleccionado
            pg.goto(f"{BASE}/#/mapa"); pg.reload(); pg.wait_for_timeout(4000)
            pg.click("button[data-capa=infl]")
            pg.click("path[data-ccn='724']", force=True)
            pg.wait_for_timeout(500)
            pg.screenshot(path=f"{OUT}/mapa_inflacion_pc.png", full_page=True)
        print(tag, "errores consola:", errs[:8])
    b.close()
