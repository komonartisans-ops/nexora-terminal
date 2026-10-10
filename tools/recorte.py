"""Recorte de una página en móvil/escritorio: python tools/recorte.py pagina ancho y0 alto salida.png [selector_clic] ..."""
import os, sys
from playwright.sync_api import sync_playwright
page, w, y0, h, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
clicks = sys.argv[6:]
CHROME = os.path.expandvars(r"%LOCALAPPDATA%\ms-playwright\chromium-1223\chrome-win64\chrome.exe")
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME)
    pg = b.new_page(viewport={"width": w, "height": 900})
    pg.goto(f"http://localhost:8765/#/{page}"); pg.reload(); pg.wait_for_timeout(4500)
    for c in clicks:
        pg.click(c, force=True); pg.wait_for_timeout(600)
    pg.screenshot(path=out, full_page=True, clip={"x": 0, "y": y0, "width": w, "height": h})
    b.close()
