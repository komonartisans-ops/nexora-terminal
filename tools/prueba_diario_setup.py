#!/usr/bin/env python3
"""Prueba (Playwright, servidor local de site/) del Diario con «setup» y casillas de confirmación, el CSV exportado, «Mi operativa» por setup × régimen gamma y la línea de niveles de #/gamma
(debe ser idéntica a la que envía Telegram). Sin red externa ni envíos.
Uso:  python tools/prueba_diario_setup.py   (necesita Chromium de Playwright)"""
import datetime as dt
import json
import os
import subprocess
import sys
import threading
import http.server
import socketserver
import functools

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import gamma_intradia as G  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

CH = os.path.expandvars(r"%LOCALAPPDATA%\ms-playwright\chromium-1223\chrome-win64\chrome.exe")


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


class S(socketserver.ThreadingTCPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):      # el navegador cierra conexiones a medias: no es un error de la prueba
        pass


def servidor():
    h = functools.partial(Q, directory=os.path.join(ROOT, "site"))
    srv = S(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


srv = servidor()
URL = f"http://127.0.0.1:{srv.server_address[1]}/"
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CH if os.path.exists(CH) else None)
    pg = b.new_page(viewport={"width": 1440, "height": 1000})
    pg.on("pageerror", lambda e: errs.append(str(e)))
    # ---------------------------------------------------------------- 1) formulario del Diario
    pg.goto(URL + "#/diario")
    pg.reload()
    pg.wait_for_selector("#jform", timeout=20000)
    assert pg.locator("#jform select[name=setup] option").all_inner_texts() == ["Sin setup", "Barrido+vuelta", "Ruptura+continuación", "Otro"]
    assert pg.locator("#jform input[name=conf]").count() == 7
    nombres = [t.strip() for t in pg.locator("#jform .conf label").all_text_contents()]
    assert nombres == ["Absorción", "Iceberg", "Divergencia delta", "Stacked imbalances", "Barrido LIT", "FVG", "VAH/VAL/POC"], nombres
    hoy = dt.date.today().isoformat()
    pg.fill("#jform input[name=fecha]", hoy)
    pg.fill("#jform input[name=hora]", "00:05")
    pg.select_option("#jform select[name=activo]", "Nasdaq 100")
    pg.select_option("#jform select[name=instrumento]", "NQ")  # NQ = 20 $ por punto: riesgo 10 pts x 20 = 200 $; resultado 6,275 pts x 20 = 125,5 $ (se calcula solo)
    pg.fill("#jform input[name=tamano]", "1")
    pg.fill("#jform input[name=precio_entrada]", "20000")
    pg.fill("#jform input[name=precio_stop]", "19990")
    pg.fill("#jform input[name=precio_salida]", "20006,275")
    pg.select_option("#jform select[name=setup]", "Barrido+vuelta")
    pg.check("#jform input[name=conf][value=absorcion]")
    pg.check("#jform input[name=conf][value=fvg]")
    pg.click("#jform button[type=submit]")
    pg.wait_for_function("() => DSYNC.estado().trades.length >= 1", timeout=30000)
    t = pg.evaluate("() => DSYNC.estado().trades[0]")
    assert t["setup"] == "Barrido+vuelta" and t["conf"] == ["absorcion", "fvg"] and t["pnl"] == 125.5, t
    chip = pg.locator(".jop .ck").last.inner_text()
    assert "Barrido+vuelta" in chip and "2 conf." in chip, chip
    print("1) OK Diario: el formulario trae Setup (Barrido+vuelta / Ruptura+continuación / Otro) y las 7 casillas; la operación guarda setup y confirmaciones y la lista muestra «%s»" % chip)
    # editar: se conservan y se pueden cambiar
    pg.locator(".jop .x[data-edit]").first.click()
    pg.wait_for_selector("#jform[data-editando]")
    assert pg.locator("#jform select[name=setup]").input_value() == "Barrido+vuelta"
    assert pg.locator("#jform input[name=conf][value=absorcion]").is_checked() and pg.locator("#jform input[name=conf][value=fvg]").is_checked() and not pg.locator("#jform input[name=conf][value=iceberg]").is_checked()
    pg.select_option("#jform select[name=setup]", "")
    pg.uncheck("#jform input[name=conf][value=absorcion]")
    pg.click("#jform button[type=submit]")
    pg.wait_for_function("() => { const t = DSYNC.estado().trades[0]; return t && !t.setup; }", timeout=30000)
    t = pg.evaluate("() => DSYNC.estado().trades[0]")
    assert "setup" not in t and t["conf"] == ["fvg"], t
    print("2) OK edición: al editar se precargan setup y casillas; quitar el setup y una casilla se guarda (queda solo FVG)")
    # importación: el saneado conserva solo valores válidos
    sane = pg.evaluate("() => tradeNorm({ id: 'x', fecha: '2026-10-19', activo: 'Oro', lado: 'Largo', pnl: 10, setup: 'Inventado', conf: ['fvg', 'fvg', 'nada', 'iceberg'] })")
    assert "setup" not in sane and sane["conf"] == ["fvg", "iceberg"], sane
    sane = pg.evaluate("() => tradeNorm({ id: 'x', fecha: '2026-10-19', activo: 'Oro', lado: 'Largo', pnl: 10, setup: 'Otro', conf: [] })")
    assert sane["setup"] == "Otro" and "conf" not in sane
    print("3) OK importación: un setup desconocido se descarta; las confirmaciones se filtran y sin duplicados")
    # ---------------------------------------------------------------- 2) «Mi operativa»: setup × régimen gamma
    trades = []

    def tr(i, setup, signo, pnl, activo="Nasdaq 100", conf=None):
        x = {"id": f"t{i}", "fecha": "2026-10-1%d" % (i % 9), "hora": "10:00", "activo": activo, "lado": "Largo", "pnl": pnl}
        if setup:
            x["setup"] = setup
        if conf:
            x["conf"] = conf
        if signo:
            x["foto"] = {"estado": "OK", "gamma": {"indice": "NQ", "signo": signo}, "tesis": None, "regimen": {"cuadrante": "X"}}
        else:
            x["foto"] = {"estado": "OK", "gamma": None, "regimen": {"cuadrante": "X"}}
        trades.append(x)
    for i, (s, g, p_, a, c) in enumerate([("Barrido+vuelta", "NEGATIVA", 100, "Nasdaq 100", ["absorcion", "fvg"]), ("Barrido+vuelta", "NEGATIVA", -40, "Nasdaq 100", ["fvg"]), ("Barrido+vuelta", "POSITIVA", 60, "S&P 500", None),
                                          ("Ruptura+continuación", "NEGATIVA", 30, "Nasdaq 100", ["iceberg"]), ("Ruptura+continuación", None, -20, "Oro", None), (None, "POSITIVA", 15, "Nasdaq 100", None), ("Otro", "NEGATIVA", 5, "S&P 500", ["fvg", "vah_val_poc"])], start=1):
        tr(i, s, g, p_, a, c)
    html = pg.evaluate("(T) => operativaHtml({ trades: T, notas: {} })", trades)
    for frag in ("Por setup × régimen gamma", "Barrido+vuelta · gamma negativa", "Barrido+vuelta · gamma positiva", "Ruptura+continuación · gamma negativa", "Ruptura+continuación · sin régimen gamma", "Sin setup · gamma positiva", "Otro · gamma negativa", "Por confirmación"):
        assert frag in html, frag
    assert "Otro · gamma positiva" not in html and "Barrido+vuelta · sin régimen gamma" not in html, "los grupos vacíos no aparecen"
    celda = pg.evaluate("""(T) => { const d = document.createElement('div'); d.innerHTML = operativaHtml({ trades: T, notas: {} }); const f = [...d.querySelectorAll('tr')].find((r) => r.textContent.includes('Barrido+vuelta · gamma negativa')); return f.textContent; }""", trades)
    assert "2" in celda and "+60,00" in celda.replace(" ", "") or "60" in celda, celda
    conf_fila = pg.evaluate("""(T) => { const d = document.createElement('div'); d.innerHTML = operativaHtml({ trades: T, notas: {} }); return [...d.querySelectorAll('tr')].filter((r) => /^(Absorción|Iceberg|FVG|VAH\\/VAL\\/POC)/.test(r.textContent.trim())).map((r) => r.textContent.trim().slice(0, 14)); }""", trades)
    assert len(conf_fila) == 4 and conf_fila[0].startswith("Absorción"), conf_fila
    sin_muestra = pg.evaluate("""(T) => { const d = document.createElement('div'); d.innerHTML = operativaHtml({ trades: T, notas: {} }); return [...d.querySelectorAll('tr.poca')].length; }""", trades)
    assert sin_muestra >= 6, "con 1-2 operaciones por grupo todo queda marcado como muestra insuficiente (n < 20)"
    print("4) OK Mi operativa: 6 grupos «setup · régimen gamma» (solo los que tienen operaciones; sin foto de gamma o en el Oro = «sin régimen gamma») y la tabla por confirmación; todos marcados n < 20")
    # ---------------------------------------------------------------- 3) CSV exportado con setup, confirmaciones y régimen gamma
    pg.goto(URL + "#/diario")
    pg.reload()
    pg.wait_for_selector("[data-a=exp-csv]", timeout=20000)
    with pg.expect_download(timeout=30000) as dl:
        pg.click("[data-a=exp-csv]")
    csv_txt = open(dl.value.path(), encoding="utf-8").read()
    cab = csv_txt.splitlines()[0].split(",")
    assert cab[cab.index("setup"):cab.index("setup") + 3] == ["setup", "confirmaciones", "regimen_gamma"], cab
    assert "FVG" in csv_txt and "Nasdaq 100" in csv_txt, csv_txt[:400]
    print("3b) OK CSV exportado: columnas setup, confirmaciones y regimen_gamma tras la nota; la operación editada sale con «FVG»")
    # ---------------------------------------------------------------- 4) línea de niveles de #/gamma = la del Telegram
    pg.goto(URL + "#/gamma")
    pg.reload()
    pg.wait_for_selector("#gLinea", timeout=30000)
    js = pg.locator("#gLinea").inner_text().strip()
    J = json.load(open(os.path.join(ROOT, "site", "data", "gamma.json"), encoding="utf-8"))
    py = G.linea_niveles(J)
    assert js == py, (js, py)
    assert pg.locator("#gCopiar").count() == 1 and "Niveles para plataformas" in pg.text_content("#app")
    print("5) OK #/gamma: la línea de niveles de la web es idéntica a la del Telegram de las 15:00 → «%s»" % js)
    b.close()
srv.shutdown()
assert not errs, errs
print("\nTODO OK · sin red externa, sin envíos reales")
