"""Prueba del almacén por meses con un GitHub simulado (API de Contents): migración, carga perezosa, mes de 1.500 operaciones (>1 MB), fusión y edición."""
import base64, hashlib, json, os, re, sys, time
from playwright.sync_api import sync_playwright

REPO = r'C:\Users\ruizt\nexora-terminal'
OUT = r'C:\Users\ruizt\nexora-terminal\capturas\diario_meses'
BASE = 'http://localhost:8765'
CHROME = os.path.expandvars(r"%LOCALAPPDATA%\ms-playwright\chromium-1223\chrome-win64\chrome.exe")
RAW = 'https://raw.githubusercontent.com/komonartisans-ops/nexora-terminal/main/'
API = 'https://api.github.com/repos/komonartisans-ops/nexora-diario'
os.makedirs(OUT, exist_ok=True)

# ---------------------------------------------------------------- GitHub simulado
FILES = {}          # ruta -> bytes
LOG = []            # (metodo, ruta, tipo)
PUTS = {}


def sha(b):
    return hashlib.sha1(b'blob %d\0' % len(b) + b).hexdigest()


def api(route):
    rq = route.request
    path = rq.url.split('/repos/komonartisans-ops/nexora-diario', 1)[1].split('?')[0]
    ok = lambda body, st=200, ct='application/json': route.fulfill(status=st, body=body if isinstance(body, (bytes, str)) else json.dumps(body), headers={'content-type': ct, 'access-control-allow-origin': '*'})
    if path == '':
        return ok({'permissions': {'push': True}})
    m = re.match(r'/contents/(.*)$', path)
    ruta = m.group(1)
    accept = rq.headers.get('accept', '')
    if rq.method == 'GET':
        if ruta == 'diario':
            fs = [{'name': k.split('/', 1)[1], 'sha': sha(v), 'type': 'file', 'size': len(v)} for k, v in FILES.items() if k.startswith('diario/')]
            LOG.append(('LIST', ruta, ''))
            return ok(fs) if fs else ok({'message': 'Not Found'}, 404)
        if ruta not in FILES:
            return ok({'message': 'Not Found'}, 404)
        b = FILES[ruta]
        if 'raw' in accept:
            LOG.append(('RAW', ruta, len(b)))
            return ok(b, 200, 'text/plain')
        LOG.append(('JSON', ruta, len(b)))
        if len(b) > 1048576:   # como la API real: sin contenido inline por encima de 1 MB
            return ok({'sha': sha(b), 'encoding': 'none', 'content': '', 'size': len(b)})
        return ok({'sha': sha(b), 'encoding': 'base64', 'content': base64.b64encode(b).decode(), 'size': len(b)})
    if rq.method == 'PUT':
        d = json.loads(rq.post_data)
        b = base64.b64decode(d['content'])
        if ruta in FILES and d.get('sha') != sha(FILES[ruta]):
            return ok({'message': 'conflict'}, 409)
        if ruta not in FILES and d.get('sha'):
            return ok({'message': 'conflict'}, 422)
        FILES[ruta] = b
        PUTS[ruta] = PUTS.get(ruta, 0) + 1
        LOG.append(('PUT', ruta, len(b)))
        return ok({'content': {'sha': sha(b)}}, 201)
    return ok('x', 405)


def raw_repo(route):
    f = os.path.join(REPO, route.request.url.replace(RAW, '').split('?')[0].replace('/', os.sep))
    route.fulfill(status=200, body=open(f, 'rb').read(), headers={'access-control-allow-origin': '*'}) if os.path.exists(f) else route.fulfill(status=404, body='no')


def nuevo_ctx(b, token=True):
    ctx = b.new_context(viewport={'width': 1440, 'height': 900})
    ctx.route(RAW + '**', raw_repo)
    ctx.route(API + '**', api)
    pg = ctx.new_page()
    pg.on('pageerror', lambda e: ERR.append(str(e)))
    pg.on('console', lambda m: ERR.append(m.text) if m.type == 'error' and 'net::' not in m.text else None)
    return ctx, pg


ERR = []


def trade(i, fecha, foto=None, **kw):
    t = {'id': f't{i:05d}', 'fecha': fecha, 'hora': f'{7 + i % 12:02d}:{(i * 7) % 60:02d}', 'activo': ['Nasdaq 100', 'Oro', 'Bitcoin', 'S&P 500'][i % 4], 'lado': 'Largo' if i % 3 else 'Corto',
         'pnl': round(((i * 37) % 300) - 120 + 0.5, 2), 'nota': 'op %d' % i, 'mod': '2026-09-01T10:00:00.000Z'}
    if foto:
        t['foto'] = foto
    t.update(kw)
    return t


def put_leg(obj):
    FILES['diario.json'] = (json.dumps(obj, ensure_ascii=False, indent=1) + '\n').encode()


def ids_remotos():
    out = {}
    for k, v in FILES.items():
        if re.match(r'diario/\d{4}-\d{2}\.json$', k):
            for t in json.loads(v)['trades']:
                out[t['id']] = (k, t)
    return out


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME)

    # foto real (para dar tamaño realista a cada operación)
    ctx0, pg0 = nuevo_ctx(b)
    pg0.goto(BASE + '/#/diario'); pg0.reload(); pg0.wait_for_timeout(1500)
    FOTO_REAL = pg0.evaluate("FOTO.tomar({fecha:'2026-10-14',hora:'13:45',activo:'Nasdaq 100',lado:'Largo'})")
    assert FOTO_REAL['estado'] == 'OK'
    print('tamaño de una foto:', len(json.dumps(FOTO_REAL, ensure_ascii=False)), 'bytes')
    ctx0.close()

    # ================= A) MIGRACIÓN desde diario.json (con notas, lápidas y una operación solo local)
    leg = {'version': 1, 'actualizado': '2026-10-16T10:00:00Z',
           'trades': [trade(i, f'2026-08-{1 + i % 28:02d}') for i in range(40)] + [trade(100 + i, f'2026-09-{1 + i % 28:02d}', FOTO_REAL) for i in range(60)] + [trade(200 + i, f'2026-10-{1 + i % 16:02d}', FOTO_REAL) for i in range(25)],
           'notas': {'2026-08-05': 'nota agosto', '2026-10-03': 'nota octubre'}, 'notasMod': {'2026-08-05': '2026-08-05T20:00:00Z', '2026-10-03': '2026-10-03T20:00:00Z'},
           'borrados': {'t99999': '2026-09-20T00:00:00Z'}}
    put_leg(leg)
    leg_bytes = FILES['diario.json']; leg_sha = sha(leg_bytes)
    ctx, pg = nuevo_ctx(b)
    local = {'trades': [trade(900, '2026-10-12', FOTO_REAL, nota='solo local')], 'notas': {}, 'notasMod': {}, 'borrados': {}}
    ctx.add_init_script("if (!localStorage.getItem('nexora.diario.v1')) { localStorage.setItem('nexora.diario.v1', %s); localStorage.setItem('nexora.diario.gh.v1', JSON.stringify({token:'test-no-real'})); }" % json.dumps(json.dumps(local)))
    LOG.clear()
    pg.goto(BASE + '/#/diario')
    pg.wait_for_timeout(5000)
    assert sha(FILES['diario.json']) == leg_sha, 'diario.json antiguo fue modificado'
    meses = sorted(k for k in FILES if re.match(r'diario/\d{4}-\d{2}\.json$', k))
    print('A) archivos:', sorted(k for k in FILES if k.startswith('diario/')))
    assert meses == ['diario/2026-08.json', 'diario/2026-09.json', 'diario/2026-10.json'], meses
    assert 'diario/_migracion.json' in FILES and 'diario/borrados.json' in FILES
    rem = ids_remotos()
    esperado = {t['id'] for t in leg['trades']} | {'t00900'}
    assert set(rem) == esperado, (len(set(rem)), len(esperado), esperado ^ set(rem))
    n8 = len(json.loads(FILES['diario/2026-08.json'])['notas']); assert json.loads(FILES['diario/2026-08.json'])['notas'] == {'2026-08-05': 'nota agosto'}
    assert json.loads(FILES['diario/borrados.json'])['borrados'] == leg['borrados']
    print('   OK: diario.json intacto (sha igual), %d operaciones repartidas en 3 meses + 1 solo local, notas y lápidas conservadas' % len(rem))
    print('   marca:', json.loads(FILES['diario/_migracion.json'])['operaciones_en_meses'], 'operaciones')
    # 2ª recarga: no vuelve a migrar ni reescribe nada
    LOG.clear(); pg.reload(); pg.wait_for_timeout(3500)
    assert not [x for x in LOG if x[0] == 'PUT'], 'recarga reescribe archivos: %s' % [x for x in LOG if x[0] == 'PUT']
    assert not [x for x in LOG if x[1] == 'diario.json' and x[0] != 'JSON'], 'vuelve a leer diario.json crudo'
    print('   OK: recarga sin escrituras')

    # ================= B) CARGA PEREZOSA
    LOG.clear()
    pg.goto(BASE + '/#/diario'); pg.reload(); pg.wait_for_timeout(3500)
    raws = [x[1] for x in LOG if x[0] == 'RAW']
    print('B) Diario (mes actual) descargó:', raws)
    assert raws in ([], ['diario/2026-10.json']) and not any('2026-08' in r or '2026-09' in r for r in raws), raws
    LOG.clear(); pg.click('[data-a=prev]'); pg.wait_for_timeout(2500)
    raws = [x[1] for x in LOG if x[0] == 'RAW']
    print('   al ir al mes anterior descargó:', raws)
    assert raws == ['diario/2026-09.json'], raws
    LOG.clear()
    pg2 = ctx.new_page(); pg2.on('pageerror', lambda e: ERR.append(str(e)))
    pg2.goto(BASE + '/#/operativa'); pg2.reload(); pg2.wait_for_timeout(4000)
    txt = pg2.inner_text('#app')
    m = re.search(r'(\d+) operaciones registradas', txt)
    print('   Mi operativa:', m.group(0) if m else txt[:300])
    assert m and int(m.group(1)) == len(esperado), (m and m.group(1), len(esperado))
    print('   OK: Mi operativa lee los 3 meses (%d operaciones)' % len(esperado))
    pg2.close()

    # ================= C) MES DE 1.500 OPERACIONES (> 1 MB)
    grande = [trade(5000 + i, f'2026-07-{1 + i % 28:02d}', FOTO_REAL) for i in range(1500)]
    texto = json.dumps({'version': 2, 'mes': '2026-07', 'trades': grande, 'notas': {}, 'notasMod': {}, 'borrados': {}}, ensure_ascii=False).encode()
    FILES['diario/2026-07.json'] = texto
    print('C) mes de 1.500 operaciones:', len(texto), 'bytes =', round(len(texto) / 1048576, 2), 'MB')
    assert len(texto) > 1048576
    LOG.clear()
    t0 = time.time()
    pg.goto(BASE + '/#/operativa'); pg.reload(); pg.wait_for_timeout(1000)
    pg.wait_for_function("document.querySelector('#op-root') && /operaciones registradas/.test(document.querySelector('#app').innerText)", timeout=30000)
    dt = time.time() - t0
    txt = pg.inner_text('#app'); m = re.search(r'(\d+) operaciones registradas', txt)
    print('   Mi operativa con 1.500 + resto: %s en %.1f s' % (m.group(0), dt))
    assert int(m.group(1)) == len(esperado) + 1500
    print('   lecturas:', [(x[1], x[2]) for x in LOG if x[0] == 'RAW'])
    pg.screenshot(path=f'{OUT}/operativa_1500_pc.png', full_page=True)
    # escritura de un archivo > 1 MB: se añade una operación en julio por la interfaz
    pg.goto(BASE + '/#/diario'); pg.reload(); pg.wait_for_timeout(2500)
    pg.evaluate("diario.mes = [2026, 6]; diario.dia = '2026-07-15'")
    pg.goto(BASE + '/#/diario'); pg.wait_for_timeout(500)
    LOG.clear()
    pg.evaluate("""async () => { await DSYNC.asegurar(['2026-07']); DSYNC.guardarTrade({id:'nueva1', fecha:'2026-07-20', hora:'10:00', activo:'Oro', lado:'Largo', pnl: 55.5, nota:'añadida sobre mes grande', mod: new Date().toISOString()}); await DSYNC.sincronizar(); }""")
    pg.wait_for_timeout(1500)
    puts = [(x[1], x[2]) for x in LOG if x[0] == 'PUT']
    print('   PUT tras añadir una operación:', puts)
    assert puts and puts[0][0] == 'diario/2026-07.json' and puts[0][1] > 1048576, puts
    assert len(json.loads(FILES['diario/2026-07.json'])['trades']) == 1501
    print('   OK: archivo de %.2f MB escrito y leído sin límite de 1 MB' % (puts[0][1] / 1048576))
    pg.screenshot(path=f'{OUT}/diario_mes_grande_pc.png', full_page=True)

    # ================= D) FUSIÓN: gana la edición más reciente; unión de lo demás
    ctxB, pgB = nuevo_ctx(b)
    pgB.goto(BASE + '/#/diario'); pgB.wait_for_timeout(300)
    pgB.evaluate("localStorage.setItem('nexora.diario.gh.v1', JSON.stringify({token:'test-no-real'}))")
    pgB.reload(); pgB.wait_for_timeout(3000)
    # A (pg) y B (pgB) editan la misma operación t00100 y B además añade otra; B edita más tarde
    pg.evaluate("""async () => { await DSYNC.asegurar(['2026-09']); const t = DSYNC.estado().trades.find(x => x.id==='t00100'); DSYNC.guardarTrade(Object.assign({}, t, {nota:'edición de A', pnl: 111, mod:'2026-10-18T10:00:00.000Z'})); }""")
    pgB.evaluate("""async () => { await DSYNC.asegurar(['2026-09']); const t = DSYNC.estado().trades.find(x => x.id==='t00100'); DSYNC.guardarTrade(Object.assign({}, t, {nota:'edición de B (más reciente)', pnl: 222, mod:'2026-10-18T11:00:00.000Z'})); DSYNC.guardarTrade({id:'soloB', fecha:'2026-09-10', hora:'09:00', activo:'Oro', lado:'Largo', pnl: 5, nota:'solo B', mod:'2026-10-18T11:00:01.000Z'}); await DSYNC.sincronizar(); }""")
    pgB.wait_for_timeout(1500)
    pg.evaluate("DSYNC.sincronizar()"); pg.wait_for_timeout(2500)   # A sube su edición, más antigua: debe perder
    rem = ids_remotos()
    assert rem['t00100'][1]['nota'] == 'edición de B (más reciente)' and rem['t00100'][1]['pnl'] == 222, rem['t00100'][1]
    assert 'soloB' in rem
    a = pg.evaluate("DSYNC.estado().trades.find(x => x.id==='t00100').pnl")
    assert a == 222, a
    print('D) OK: gana la edición más reciente (B, pnl 222), A la adopta y se conserva la operación nueva de B')
    # orden inverso: la edición MÁS ANTIGUA llega la última y no pisa
    pg.evaluate("""async () => { const t = DSYNC.estado().trades.find(x => x.id==='t00101'); DSYNC.guardarTrade(Object.assign({}, t, {nota:'A tarde', mod:'2026-10-18T12:00:00.000Z'})); await DSYNC.sincronizar(); }""")
    pgB.evaluate("""async () => { const t = DSYNC.estado().trades.find(x => x.id==='t00101'); DSYNC.guardarTrade(Object.assign({}, t, {nota:'B temprano', mod:'2026-10-18T09:00:00.000Z'})); await DSYNC.sincronizar(); }""")
    pgB.wait_for_timeout(1500)
    assert ids_remotos()['t00101'][1]['nota'] == 'A tarde', ids_remotos()['t00101'][1]
    print('   OK: una edición antigua que llega después no pisa a la reciente')

    # ================= E) EDICIÓN con cambio de mes + borrado
    pg.evaluate("""async () => { await DSYNC.asegurar(['2026-09','2026-08']); const t = DSYNC.estado().trades.find(x => x.id==='t00102'); DSYNC.guardarTrade(Object.assign({}, t, {fecha:'2026-08-30', mod: new Date().toISOString()})); DSYNC.borrarTrade('t00103'); await DSYNC.sincronizar(); }""")
    pg.wait_for_timeout(1500)
    rem = ids_remotos()
    assert rem['t00102'][0] == 'diario/2026-08.json' and 't00103' not in rem and '2026-09' not in rem['t00102'][0]
    assert 't00103' in json.loads(FILES['diario/2026-09.json'])['borrados']
    print('E) OK: la operación cambia de mes (sale de septiembre, entra en agosto, una sola copia) y el borrado deja lápida')

    pg.screenshot(path=f'{OUT}/diario_pc.png', full_page=True)
    b.close()
print('PUTs por archivo:', PUTS)
print('ERRORES DE CONSOLA:', ERR if ERR else 'ninguno')
