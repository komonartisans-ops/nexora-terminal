"""Capturas de cada página con Playwright (revisión visual, no se despliega).
Uso: python tools/capturas.py [URL_BASE] [DIR_SALIDA]"""
import sys
import os
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765"
OUT = sys.argv[2] if len(sys.argv) > 2 else "capturas"
PAGES = ["resumen", "bancos", "liquidez", "calendario", "ciclo", "regimen", "publicados", "oro", "indices", "cripto", "divisas", "posicionamiento", "noticias"]
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
        for name in PAGES:
            pg.goto(f"{BASE}/#/{name}")
            pg.reload()
            pg.wait_for_timeout(2500)
            pg.screenshot(path=f"{OUT}/{name}_{tag}.png", full_page=True)
            print("ok", name, tag)
        # menú desplegado
        if tag == "pc":
            pg.goto(f"{BASE}/#/liquidez")
            pg.wait_for_timeout(1200)
            pg.click("text=Análisis")
            pg.wait_for_timeout(300)
            pg.screenshot(path=f"{OUT}/menu_pc.png")
        print(tag, "errores consola:", errs[:8])
    b.close()
