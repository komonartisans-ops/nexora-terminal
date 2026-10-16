"""Auditoría visual automática: cada ruta #/ por URL directa, a 375, 768 y 1440 px.
Guarda capturas en capturas/auditoria/ y escribe un informe JSON con los hallazgos automáticos.
Uso: python tools/auditoria_visual.py [URL_BASE] [DIR_SALIDA] [paginas separadas por coma] [anchos separados por coma]"""
import json
import os
import re
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765"
OUT = sys.argv[2] if len(sys.argv) > 2 else "capturas/auditoria"
PAGES = ["resumen", "watchlists", "regimen", "ciclo", "bancos", "mapa", "agenda", "eventos", "tono", "liquidez", "divisas", "posicionamiento",
         "skew", "gamma", "semis", "oro", "indices", "cripto", "noticias", "calendario", "publicados", "diario", "tesis"]
ANCHOS = [(375, 812), (768, 1024), (1440, 900)]
if len(sys.argv) > 3 and sys.argv[3]:
    PAGES = sys.argv[3].split(",")
if len(sys.argv) > 4 and sys.argv[4]:
    ANCHOS = [a for a in ANCHOS if str(a[0]) in sys.argv[4].split(",")]
CHROME = os.path.expandvars(r"%LOCALAPPDATA%\ms-playwright\chromium-1223\chrome-win64\chrome.exe")
os.makedirs(OUT, exist_ok=True)

JS = r"""
() => {
  const vw = document.documentElement.clientWidth;
  const res = {};
  res.scrollW = document.documentElement.scrollWidth; res.clientW = vw; res.bodyScrollW = document.body.scrollWidth;
  // elementos que se salen del viewport (ignorando los dentro de un contenedor con scroll propio)
  const dentroDeScroll = (el) => { for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) { const o = getComputedStyle(p).overflowX; if ((o === 'auto' || o === 'scroll' || o === 'hidden') && p.scrollWidth > p.clientWidth + 1) return true; } return false; };
  const sale = [];
  document.querySelectorAll('#app *, header *, footer *').forEach((el) => {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return;
    if (r.right > vw + 1 && !dentroDeScroll(el)) sale.push((el.tagName.toLowerCase() + '.' + String(el.className).split(' ')[0] + ' «' + (el.innerText || '').slice(0, 40).replace(/\n/g, ' ') + '» right=' + Math.round(r.right)));
  });
  res.sale = sale.slice(0, 8); res.n_sale = sale.length;
  // textos cortados: overflow hidden y contenido más ancho que la caja (sin ser contenedor de scroll)
  const cortados = [];
  document.querySelectorAll('#app *').forEach((el) => {
    const cs = getComputedStyle(el);
    if ((cs.overflowX === 'hidden' || cs.textOverflow === 'ellipsis') && el.scrollWidth > el.clientWidth + 2 && el.clientWidth > 0 && (el.innerText || '').trim()) cortados.push(el.tagName.toLowerCase() + '.' + String(el.className).split(' ')[0] + ' «' + el.innerText.trim().slice(0, 50).replace(/\n/g, ' ') + '» ' + el.scrollWidth + '>' + el.clientWidth);
  });
  res.cortados = cortados.slice(0, 8); res.n_cortados = cortados.length;
  // tablas más anchas que su contenedor sin scroll propio
  const tablas = [];
  document.querySelectorAll('#app table').forEach((t) => { const p = t.parentElement; const o = getComputedStyle(p).overflowX; if (t.scrollWidth > p.clientWidth + 2 && !(o === 'auto' || o === 'scroll')) tablas.push('table en .' + String(p.className).split(' ')[0] + ' ' + t.scrollWidth + '>' + p.clientWidth); });
  res.tablas = tablas.slice(0, 5);
  const txt = document.querySelector('#app').innerText;
  const bad = [...txt.matchAll(/(^|[^\wÀ-ÿ])(NaN|undefined|null|\[object Object\]|Infinity|-Infinity)(?![\wÀ-ÿ])/g)].map((m) => m[2]);
  res.mal_texto = [...new Set(bad)];
  const ctx = []; for (const m of txt.matchAll(/.{0,30}(NaN|undefined|\[object Object\]|Infinity).{0,30}/g)) ctx.push(m[0].replace(/\n/g, ' ')); res.mal_ctx = ctx.slice(0, 5);
  // gráficos
  const vacios = [];
  document.querySelectorAll('#app canvas').forEach((c) => { const r = c.getBoundingClientRect(); if (r.width < 20 || r.height < 20) vacios.push('canvas ' + Math.round(r.width) + 'x' + Math.round(r.height)); });
  document.querySelectorAll('#app [class*="chart"], #app [id*="chart"], #app [id^="ch"]').forEach((c) => { if (c.tagName === 'CANVAS') return; const r = c.getBoundingClientRect(); if (r.height > 0 && r.height < 20 && !c.querySelector('canvas,svg')) vacios.push('contenedor ' + (c.id || c.className) + ' h=' + Math.round(r.height)); });
  res.graf_vacios = vacios.slice(0, 6);
  res.n_canvas = document.querySelectorAll('#app canvas').length; res.n_svg = document.querySelectorAll('#app svg').length;
  res.n_empty = document.querySelectorAll('#app .empty').length;
  res.empty_txt = [...document.querySelectorAll('#app .empty')].map((e) => e.innerText.trim().slice(0, 60)).slice(0, 6);
  res.imgs_rotas = [...document.querySelectorAll('img')].filter((i) => i.complete && i.naturalWidth === 0).map((i) => i.src.slice(0, 80));
  res.fuentes = { inter: document.fonts.check('12px Inter'), plex: document.fonts.check('12px "IBM Plex Mono"'), serif: document.fonts.check('12px "Source Serif 4"') };
  res.fuentes_cargadas = [...document.fonts].filter((f) => f.status === 'loaded').map((f) => f.family.replace(/"/g, '')).filter((v, i, a) => a.indexOf(v) === i);
  res.sd = (txt.match(/SIN DATO/g) || []).length;
  res.h1 = (document.querySelector('#app h1') || {}).innerText || '';
  res.altura = document.documentElement.scrollHeight;
  res.banners = [...document.querySelectorAll('#banners .banner')].map((b) => b.innerText.slice(0, 160));
  return res;
}
"""

informe = {}
with sync_playwright() as p:
    kw = {"executable_path": CHROME} if os.path.exists(CHROME) else {}
    b = p.chromium.launch(**kw)
    for w, h in ANCHOS:
        for name in PAGES:
            ctx = b.new_context(viewport={"width": w, "height": h})
            pg = ctx.new_page()
            errs, reqs = [], []
            pg.on("console", lambda m, errs=errs: errs.append(m.text[:200]) if m.type == "error" else None)
            pg.on("pageerror", lambda e, errs=errs: errs.append("PAGEERROR " + str(e)[:200]))
            pg.on("response", lambda r, reqs=reqs: reqs.append(f"{r.status} {r.url[:110]}") if r.status >= 400 else None)
            pg.on("requestfailed", lambda r, reqs=reqs: reqs.append(f"FAILED {r.url[:110]} {r.failure}"))
            try:
                pg.goto(f"{BASE}/#/{name}", wait_until="load", timeout=60000)
                pg.wait_for_timeout(4500)
                r = pg.evaluate(JS)
                pg.screenshot(path=f"{OUT}/{name}_{w}.png", full_page=True)
            except Exception as e:  # noqa: BLE001
                r = {"error_carga": str(e)[:200]}
            r["consola"] = errs[:6]
            r["peticiones_malas"] = reqs[:8]
            informe[f"{name}@{w}"] = r
            flags = []
            if r.get("scrollW", 0) > r.get("clientW", 0) + 1:
                flags.append(f"SCROLL-H {r['scrollW']}>{r['clientW']}")
            for k in ("n_sale", "n_cortados"):
                if r.get(k):
                    flags.append(f"{k}={r[k]}")
            for k in ("tablas", "mal_texto", "graf_vacios", "imgs_rotas", "consola", "peticiones_malas"):
                if r.get(k):
                    flags.append(f"{k}={len(r[k])}")
            print(f"{name}@{w}: {'; '.join(flags) or 'ok'}", flush=True)
            ctx.close()
    b.close()
with open(f"{OUT}/informe.json", "w", encoding="utf-8") as f:
    json.dump(informe, f, ensure_ascii=False, indent=1)
print("hecho")
