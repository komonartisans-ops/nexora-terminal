#!/usr/bin/env python3
"""Prueba (Playwright, servidor local de site/) del R en el Diario (Fase 20): campos obligatorios, riesgo en $ = |entrada − stop| × valor del punto × tamaño, R = resultado / riesgo,
R planeado = |objetivo − entrada| / |entrada − stop| con aviso ámbar < 2 R, valor del punto por instrumento (futuros fijos; CFD pedido una vez y recordado) y operaciones antiguas sin stop
(R = SIN DATO). Sin red externa ni envíos.   Uso: PYTHONUTF8=1 python tools/prueba_diario_r.py"""
import datetime as dt
import functools
import http.server
import os
import socketserver
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CH = os.path.expandvars(r"%LOCALAPPDATA%\ms-playwright\chromium-1223\chrome-win64\chrome.exe")


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


class S(socketserver.ThreadingTCPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        pass


srv = S(("127.0.0.1", 0), functools.partial(Q, directory=os.path.join(ROOT, "site")))
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{srv.server_address[1]}/"
errs, dialogos = [], []

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CH if os.path.exists(CH) else None)
    pg = b.new_page(viewport={"width": 1440, "height": 1100})
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("dialog", lambda d: (dialogos.append(d.message), d.dismiss()))
    pg.goto(URL + "#/diario")
    pg.reload()
    pg.wait_for_selector("#jform", timeout=20000)

    # ---- 1) cálculo puro
    c = pg.evaluate("() => calcR({lado:'Largo', entrada:20000, stop:19990, salida:20030, objetivo:20020, vp:20, tam:2})")
    assert c["riesgo_usd"] == 400 and c["pnl_calc"] == 1200 and c["r"] == 3 and c["r_plan"] == 2 and c["aviso"] is False, c
    c = pg.evaluate("() => calcR({lado:'Corto', entrada:5000, stop:5004, salida:5008, objetivo:4994, vp:50, tam:1})")      # corto que sale 4 puntos por encima del stop: -2 R
    assert c["riesgo_usd"] == 200 and c["pnl_calc"] == -400 and c["r"] == -2 and c["r_plan"] == 1.5 and c["aviso"] is True, c
    c = pg.evaluate("() => calcR({lado:'Largo', entrada:4000, stop:3990, salida:4010, vp:100, tam:1, pnl:900})")      # el neto con comisiones manda sobre el calculado
    assert c["pnl_calc"] == 1000 and c["pnl"] == 900 and c["r"] == 0.9 and c["r_plan"] is None, c
    for malo in ("{lado:'Largo', entrada:100, stop:101, salida:102, vp:1, tam:1}", "{lado:'Corto', entrada:100, stop:99, salida:98, vp:1, tam:1}", "{lado:'Largo', entrada:100, stop:100, salida:102, vp:1, tam:1}",
                 "{lado:'Largo', entrada:100, stop:99, salida:102, vp:1, tam:0}", "{lado:'Largo', entrada:100, stop:99, salida:102, objetivo:99, vp:1, tam:1}", "{lado:'Largo', entrada:100, salida:102, vp:1, tam:1}"):
        assert "error" in pg.evaluate(f"() => calcR({malo})"), malo
    vps = pg.evaluate("() => Object.fromEntries(['GC','MGC','ES','MES','NQ','MNQ','YM','MYM','CFD XAU','CFD US500','CFD US100','CFD US30'].map((k) => [k, valorPuntoFijo(k)]))")
    assert vps == {"GC": 100, "MGC": 10, "ES": 50, "MES": 5, "NQ": 20, "MNQ": 2, "YM": 5, "MYM": 0.5, "CFD XAU": None, "CFD US500": None, "CFD US100": None, "CFD US30": None}, vps
    print("1) OK cálculo: riesgo = |entrada−stop|×punto×tamaño; R = resultado/riesgo con signo; R planeado y aviso < 2 R; el neto indicado manda; stop/objetivo en el lado equivocado → error; valores del punto GC 100, MGC 10, ES 50, MES 5, NQ 20, MNQ 2, YM 5, MYM 0,5")

    # ---- 2) formulario: futuro (valor del punto fijo) con vista previa y aviso ámbar
    hoy = dt.date.today().isoformat()
    pg.fill("#jform input[name=fecha]", hoy)
    pg.fill("#jform input[name=hora]", "00:05")
    pg.select_option("#jform select[name=instrumento]", "ES")
    assert pg.input_value("#jform input[name=valor_punto]") == "50" and pg.locator("#jform input[name=valor_punto]").get_attribute("readonly") is not None
    for k, v in (("tamano", "2"), ("precio_entrada", "5000"), ("precio_stop", "4996"), ("precio_salida", "5012"), ("precio_objetivo", "5006")):
        pg.fill(f"#jform input[name={k}]", v)
    txt = pg.inner_text("#jr")
    assert "Riesgo 400 $" in txt and "1200 $" in txt and "R = +3" in txt and "R planeado 1,5" in txt and "por debajo de 2 R" in txt, txt
    pg.select_option("#jform select[name=setup]", "Ruptura+continuación")
    pg.click("#jform button[type=submit]")
    pg.wait_for_function("() => DSYNC.estado().trades.length >= 1", timeout=30000)
    t = pg.evaluate("() => DSYNC.estado().trades[0]")
    assert (t["instrumento"], t["valor_punto"], t["tamano"], t["precio_stop"], t["precio_objetivo"], t["riesgo_usd"], t["pnl"], t["r"], t["r_plan"]) == ("ES", 50, 2, 4996, 5006, 400, 1200, 3, 1.5), t
    fila = pg.inner_text(".jop")
    assert "+3,00 R" in fila and "plan 1,5 R < 2" in fila, fila
    print("2) OK futuro ES: valor del punto fijo (50, solo lectura), vista previa en vivo (riesgo 400 $, resultado 1200 $, R +3, R plan 1,5 con aviso ámbar) y la operación guarda riesgo, R y R planeado; la lista muestra «+3,00 R» y el aviso")

    # ---- 3) campos obligatorios y lados incoherentes: no se guarda
    n0 = pg.evaluate("() => DSYNC.estado().trades.length")
    pg.fill("#jform input[name=fecha]", hoy)
    pg.fill("#jform input[name=hora]", "00:06")
    pg.select_option("#jform select[name=instrumento]", "MES")
    for k, v in (("tamano", "1"), ("precio_entrada", "5000"), ("precio_salida", "5010")):      # sin stop
        pg.fill(f"#jform input[name={k}]", v)
    pg.fill("#jform input[name=precio_stop]", "")
    assert pg.evaluate("() => document.getElementById('jform').checkValidity()") is False, "sin stop el formulario no es válido (campo obligatorio)"
    pg.fill("#jform input[name=precio_stop]", "5004")      # stop por ENCIMA de la entrada en una operación larga
    pg.click("#jform button[type=submit]")
    pg.wait_for_timeout(600)
    assert dialogos and "por debajo de la entrada" in dialogos[-1], dialogos
    assert pg.evaluate("() => DSYNC.estado().trades.length") == n0
    print("3) OK sin stop el formulario no se envía (obligatorio); un stop del lado equivocado se rechaza con aviso y no se guarda")

    # ---- 4) CFD: pide el valor del punto una vez y lo recuerda
    pg.fill("#jform input[name=precio_stop]", "4990")
    pg.select_option("#jform select[name=instrumento]", "CFD US500")
    assert pg.locator("#jform input[name=valor_punto]").get_attribute("readonly") is None and pg.input_value("#jform input[name=valor_punto]") == ""
    pg.fill("#jform input[name=valor_punto]", "1,5")
    pg.click("#jform button[type=submit]")
    pg.wait_for_function("(n) => DSYNC.estado().trades.length > n", arg=n0, timeout=30000)
    t = [x for x in pg.evaluate("() => DSYNC.estado().trades") if x.get("instrumento") == "CFD US500"][0]
    assert t["valor_punto"] == 1.5 and t["riesgo_usd"] == 15 and t["pnl"] == 15 and t["r"] == 1, t
    pg.wait_for_selector("#jform")
    pg.select_option("#jform select[name=instrumento]", "CFD US100")
    assert pg.input_value("#jform input[name=valor_punto]") == "", "cada CFD recuerda el suyo"
    pg.select_option("#jform select[name=instrumento]", "CFD US500")
    assert pg.input_value("#jform input[name=valor_punto]") == "1,5", "el CFD US500 recuerda el valor del punto"
    print("4) OK CFD: el valor del punto se pide una vez (1,5 $), se guarda con la operación y se rellena solo la próxima vez (cada CFD el suyo)")

    # ---- 5) operaciones antiguas sin stop: R = SIN DATO y se pueden editar sin inventar nada
    pg.evaluate("() => { DSYNC.guardarTrade({ id: 'viejo1', fecha: '%s', hora: '00:01', activo: 'Oro', lado: 'Largo', pnl: 50, nota: 'antigua', mod: new Date().toISOString() }); dVista(); }" % hoy)
    pg.reload()
    pg.wait_for_selector(".jop")
    assert "SIN DATO" in pg.locator(".jop", has_text="antigua").inner_text()
    pg.locator(".jop", has_text="antigua").locator(".x[data-edit]").click()
    pg.wait_for_selector("#jform[data-editando]")
    assert pg.evaluate("() => document.querySelector('#jform [name=precio_stop]').required") is False and pg.inner_text("#jr").startswith("Operación anterior sin stop")
    pg.fill("#jform input[name=nota]", "antigua corregida")
    pg.click("#jform button[type=submit]")
    pg.wait_for_function("() => DSYNC.estado().trades.some((t) => t.nota === 'antigua corregida')", timeout=30000)
    v = [x for x in pg.evaluate("() => DSYNC.estado().trades") if x["id"] == "viejo1"][0]
    assert "r" not in v and "precio_stop" not in v and v["pnl"] == 50, v
    kpi = pg.inner_text(".grid.g4")
    assert "esperanza" in kpi and "R (2 de 3 con R)" in kpi.replace("\n", " "), kpi
    print("5) OK operación antigua sin stop: R = SIN DATO, se edita sin pedir stop y no se inventa nada; la esperanza del mes cuenta solo las operaciones con R (2 de 3)")

    # ---- 6) «Mi operativa»: esperanza en R y factor de beneficio en R por setup × régimen (los $ se mantienen); las operaciones sin R no entran
    fila = pg.evaluate("""(hoy) => { const mk = (id, pnl, extra) => Object.assign({ id, fecha: hoy, hora: '00:02', activo: 'Nasdaq 100', lado: 'Largo', pnl, setup: 'Barrido+vuelta' }, extra || {});
      const T = [mk('r1', 400, { r: 2 }), mk('r2', -200, { r: -1 }), mk('r3', 300, { r: 1.5 }), mk('r4', 50)];
      const d = document.createElement('div'); d.innerHTML = operativaHtml({ trades: T, notas: {} });
      const f = [...d.querySelectorAll('tr')].find((r) => r.textContent.includes('Barrido+vuelta · sin régimen gamma'));
      return { fila: f.textContent.replace(/\s+/g, ' '), cab: d.querySelector('thead').textContent.replace(/\s+/g, ' ') }; }""", hoy)
    f_, cab = fila["fila"], fila["cab"]
    assert "3 / 4" in f_ and "+0,83 R" in f_ and "3,50" in f_ and "550" in f_, f_
    assert "Esperanza (R)" in cab and "Factor benef. (R)" in cab and "Factor benef." in cab and "P&L total" in cab, cab
    print("6) OK Mi operativa: columnas «con R», «Esperanza (R)» y «Factor benef. (R)» junto a las de $; Barrido+vuelta con 3 de 4 operaciones con R → esperanza +0,83 R y factor 3,5 (la operación sin R no entra)")
    b.close()
assert not errs, errs
print("\nTODO OK · sin red externa, sin envíos reales")
