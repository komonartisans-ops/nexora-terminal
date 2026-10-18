/* NEXORA TERMINAL · almacén del Diario de operaciones y sincronización con un repo PRIVADO de GitHub.
   Se carga antes de fase5.js.

   FORMATO: un archivo por mes en komonartisans-ops/nexora-diario/diario/AAAA-MM.json (trades, notas y lápidas de ese mes).
   Sin límite práctico de tamaño: la lectura usa el tipo raw de la API de Contents (hasta 100 MB; el límite de 1 MB solo afecta a la lectura
   en base64) y la escritura PUT admite hasta 100 MB. El diario.json antiguo NO se toca ni se borra: se lee una vez, se reparte por meses y
   queda como copia (diario/_migracion.json deja constancia). Las lápidas del formato antiguo van a diario/borrados.json.
   COPIA LOCAL: IndexedDB (sin el tope de ~5 MB de localStorage), un registro por mes. El localStorage antiguo se migra y se deja intacto.
   CARGA PEREZOSA: la página Diario pide solo el mes que muestra; «Mi operativa» pide todos. Un mes se descarga solo si su sha en el listado
   del directorio difiere del que ya tenemos.
   FUSIÓN (por mes): unión por id; si la misma operación está en las dos copias gana la de mayor `mod` (edición más reciente), a igualdad la
   local; lo borrado (lápida) no revive; notas por fecha de modificación. Importar JSON sustituye (pend='replace').

   PRIVACIDAD: el token (fine-grained, solo Contents de nexora-diario) vive SOLO en el localStorage de este navegador. Nunca se escribe en el
   repo público, ni en una URL, ni en la consola. Sin token no se envía nada a ningún servidor.
   Todo texto dinámico pasa por esc() antes de entrar en el HTML. */
'use strict';
const DSYNC = (() => {
  const REPO = 'komonartisans-ops/nexora-diario', DIR = 'diario', LEGACY = 'diario.json';
  const KC = 'nexora.diario.gh.v1', KLOC = 'nexora.diario.v1';
  const API = `https://api.github.com/repos/${REPO}`;
  const S = { fase: 'off', msg: '', hora: null, sinLocal: false };      // fase: off | sync | ok | offline | error
  const R = new Map();           // mes 'AAAA-MM' -> registro {mes, trades:{id:t}, notas, notasMod, borrados, sha, dirty, pend, ver}
  let legB = {}, legBsha = null; // lápidas del formato antiguo (id -> iso), compartidas por todos los meses
  let vista = null, aviso = null, iniciado = null, busy = false, again = false, timer = null, abierto = false;
  const conocidos = new Set();

  const cfg = () => { const c = lsGet(KC, null); return c && typeof c.token === 'string' && c.token ? c : null; };
  const obj = (o) => (o && typeof o === 'object' && !Array.isArray(o) ? o : {});
  const ahoraISO = () => new Date().toISOString();
  const RE_FECHA = /^\d{4}-\d{2}-\d{2}/;
  const mesDe = (f) => (RE_FECHA.test(String(f)) ? String(f).slice(0, 7) : '0000-00');
  const mesOk = (m) => /^\d{4}-\d{2}$/.test(m);

  /* estado normalizado {trades:[], notas, notasMod, borrados} (también para JSON importados o del formato antiguo) */
  const norm = (s) => { const o = obj(s); return { trades: Array.isArray(o.trades) ? o.trades : [], notas: obj(o.notas), notasMod: obj(o.notasMod), borrados: obj(o.borrados) }; };
  const nuevo = (mes) => ({ mes, trades: {}, notas: {}, notasMod: {}, borrados: {}, sha: null, dirty: false, pend: 'merge', ver: 0 });

  /* ------------------------------------------------------------ almacén local (IndexedDB; sin él, solo memoria de la sesión) */
  const KV = (() => {
    let dbp = null; const mem = new Map();
    const abrir = () => dbp || (dbp = new Promise((res) => {
      try {
        const r = indexedDB.open('nexora-diario', 1);
        r.onupgradeneeded = () => r.result.createObjectStore('kv');
        r.onsuccess = () => res(r.result);
        r.onerror = () => { S.sinLocal = true; res(null); };
        r.onblocked = () => { S.sinLocal = true; res(null); };
      } catch (e) { S.sinLocal = true; res(null); }
    }));
    const tx = async (modo, fn) => {
      const db = await abrir();
      if (!db) return fn(null).result;
      return new Promise((res, rej) => { const t = db.transaction('kv', modo); const rq = fn(t.objectStore('kv')); t.oncomplete = () => res(rq && rq.result); t.onerror = () => rej(t.error); t.onabort = () => rej(t.error); });
    };
    return {
      abrir,
      get: (k) => tx('readonly', (s) => (s ? s.get(k) : { result: mem.get(k) })),
      set: (k, v) => tx('readwrite', (s) => (s ? s.put(v, k) : (mem.set(k, v), { result: 1 }))),
      keys: () => tx('readonly', (s) => (s ? s.getAllKeys() : { result: [...mem.keys()] })),
    };
  })();
  const serial = (r) => ({ mes: r.mes, trades: r.trades, notas: r.notas, notasMod: r.notasMod, borrados: r.borrados, sha: r.sha, dirty: r.dirty, pend: r.pend });
  const enVuelo = new Map();
  function persistir(mes) {          // coalescido: si ya hay una escritura en curso se repite al terminar
    if (enVuelo.has(mes)) { enVuelo.set(mes, true); return; }
    enVuelo.set(mes, false);
    const r = R.get(mes);
    if (!r) { enVuelo.delete(mes); return; }
    KV.set('mes:' + mes, serial(r)).catch(() => { S.sinLocal = true; }).finally(() => { const otra = enVuelo.get(mes); enVuelo.delete(mes); if (otra) persistir(mes); });
  }
  const aRegistro = (mes, d) => Object.assign(nuevo(mes), { trades: Object.fromEntries((Array.isArray(d.trades) ? d.trades : []).filter((t) => t && t.id).map((t) => [t.id, t])), notas: obj(d.notas), notasMod: obj(d.notasMod), borrados: obj(d.borrados) });

  /* ------------------------------------------------------------ vista del estado cargado y mutaciones */
  function estado() {
    if (vista) return vista;
    const trades = [], notas = {}, notasMod = {}, borrados = Object.assign({}, legB);
    for (const r of R.values()) {
      for (const id in r.trades) trades.push(r.trades[id]);
      Object.assign(notas, r.notas); Object.assign(notasMod, r.notasMod); Object.assign(borrados, r.borrados);
    }
    return (vista = { trades, notas, notasMod, borrados });
  }
  const invalidar = () => { vista = null; };
  const registro = (mes) => { let r = R.get(mes); if (!r) { r = nuevo(mes); R.set(mes, r); } return r; };
  function tocar(r) { r.dirty = true; r.ver++; invalidar(); persistir(r.mes); agenda(); }

  /* alta o edición; si cambia de mes, sale del mes antiguo (sin lápida: no es un borrado) */
  function guardarTrade(t) {
    const mes = mesDe(t.fecha);
    for (const r of R.values()) if (r.mes !== mes && r.trades[t.id]) { delete r.trades[t.id]; tocar(r); }
    const r = registro(mes); r.trades[t.id] = t; tocar(r);
  }
  function borrarTrade(id) {
    for (const r of R.values()) if (r.trades[id]) { delete r.trades[id]; r.borrados[id] = ahoraISO(); tocar(r); return; }
  }
  function guardarNota(fecha, txt) { const r = registro(mesDe(fecha)); r.notas[fecha] = txt; r.notasMod[fecha] = ahoraISO(); tocar(r); }
  /* importar: todos los meses (cargados antes con asegurar('todos')) pasan a contener solo lo importado; la copia local manda sobre la remota */
  function reemplazar(st) {
    const n = norm(st), meses = new Set([...R.keys(), ...n.trades.map((t) => mesDe(t.fecha)), ...Object.keys(n.notas).map(mesDe)]);
    meses.forEach((m) => { const r = registro(m); r.trades = {}; r.notas = {}; r.notasMod = {}; r.borrados = {}; r.pend = 'replace'; });
    n.trades.forEach((t) => { if (t && t.id) registro(mesDe(t.fecha)).trades[t.id] = t; });
    Object.entries(n.notas).forEach(([d, v]) => { const r = registro(mesDe(d)); r.notas[d] = v; r.notasMod[d] = n.notasMod[d] || ahoraISO(); });
    meses.forEach((m) => tocar(R.get(m)));
  }

  /* ------------------------------------------------------------ fusión por mes */
  function mezclar(r, l) {           // r = remoto, l = local; a igualdad de `mod` gana la local
    const borrados = Object.assign({}, r.borrados, l.borrados), trades = {};
    [...Object.values(r.trades), ...Object.values(l.trades)].forEach((t) => {
      if (!t || !t.id || borrados[t.id] || legB[t.id]) return;
      const p = trades[t.id];
      if (!p || String(t.mod || '') >= String(p.mod || '')) trades[t.id] = t;
    });
    const notas = {}, notasMod = {};
    new Set([...Object.keys(r.notas), ...Object.keys(l.notas)]).forEach((d) => {
      const tr = r.notasMod[d] || '', tl = l.notasMod[d] || '';
      const loc = d in l.notas && (!(d in r.notas) || tl >= tr);
      notas[d] = loc ? l.notas[d] : r.notas[d];
      if (loc ? tl : tr) notasMod[d] = loc ? tl : tr;
    });
    return { trades, notas, notasMod, borrados };
  }
  /* una misma operación en dos meses (edición con cambio de fecha en otro dispositivo): se queda la de mayor `mod`; y se aplican las lápidas antiguas */
  function depurar() {
    const donde = new Map();
    for (const r of R.values()) for (const id in r.trades) {
      if (legB[id]) { delete r.trades[id]; tocar(r); continue; }
      const o = donde.get(id);
      if (!o) { donde.set(id, r); continue; }
      const [a, b] = String(r.trades[id].mod || '') > String(o.trades[id].mod || '') ? [o, r] : [r, o];  // a = la que pierde
      delete a.trades[id]; tocar(a); donde.set(id, b);
    }
  }

  /* ------------------------------------------------------------ API de GitHub */
  const b64e = (s) => { const u = new TextEncoder().encode(s); let b = ''; for (let i = 0; i < u.length; i += 0x8000) b += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000)); return btoa(b); };
  const falla = (tipo, msg) => Object.assign(new Error(msg), { tipo });
  const llamar = (url, metodo, cuerpo, accept) => fetch(url, {
    method: metodo, cache: 'no-store',
    headers: Object.assign({ Accept: accept || 'application/vnd.github+json', Authorization: 'Bearer ' + cfg().token, 'X-GitHub-Api-Version': '2022-11-28' }, cuerpo ? { 'Content-Type': 'application/json' } : {}),
    body: cuerpo ? JSON.stringify(cuerpo) : undefined,
  });
  const msgAuth = 'El token no es válido, ha caducado o no tiene permiso de Contents (lectura y escritura) sobre nexora-diario.';
  const revisar = (r, que) => {
    if (r.status === 401 || r.status === 403) throw falla('auth', msgAuth);
    if (r.status === 409 || r.status === 422) throw falla('conflicto', 'conflicto');
    if (!r.ok) throw falla('http', `GitHub respondió ${r.status} ${que}.`);
  };
  async function leerRaw(ruta) {     // contenido completo, sin el tope de 1 MB de la lectura en base64
    const r = await llamar(`${API}/contents/${ruta}`, 'GET', null, 'application/vnd.github.raw+json');
    revisar(r, 'al leer ' + ruta);
    return r.text();
  }
  async function poner(ruta, texto, sha, msg) {
    const w = await llamar(`${API}/contents/${ruta}`, 'PUT', Object.assign({ message: msg, content: b64e(texto) }, sha ? { sha } : {}));
    revisar(w, 'al guardar ' + ruta);
    return (await w.json()).content.sha;
  }
  /* listado del directorio diario/ (nombre + sha, sin descargar nada) y existencia del diario.json antiguo */
  async function listar() {
    const r = await llamar(`${API}/contents/${DIR}`, 'GET');
    const meses = new Map(); let borr = null, migrado = false;
    if (r.status === 404) {
      const rr = await llamar(API, 'GET');     // 404 = aún no existe el directorio, o el token no ve el repo: se distingue mirando el repo
      if (rr.status === 401 || rr.status === 403 || rr.status === 404) throw falla('auth', msgAuth);
    } else {
      revisar(r, 'al listar diario/');
      (await r.json()).forEach((x) => {
        const m = /^(\d{4}-\d{2})\.json$/.exec(x.name);
        if (m) meses.set(m[1], x.sha); else if (x.name === 'borrados.json') borr = x.sha; else if (x.name === '_migracion.json') migrado = true;
      });
    }
    let legacy = null;
    if (!migrado) { const l = await llamar(`${API}/contents/${LEGACY}`, 'GET'); if (l.ok) legacy = { sha: (await l.json()).sha }; else if (l.status !== 404) revisar(l, 'al comprobar diario.json'); }
    meses.forEach((_, m) => conocidos.add(m));
    return { meses, borr, migrado, legacy };
  }
  const textoMes = (r) => {
    const t = Object.values(r.trades).sort((a, b) => (a.fecha + (a.hora || '') + a.id).localeCompare(b.fecha + (b.hora || '') + b.id));
    return `{"version":2,"mes":${JSON.stringify(r.mes)},"actualizado":${JSON.stringify(ahoraISO())},"trades":[\n${t.map((x) => JSON.stringify(x)).join(',\n')}\n],"notas":${JSON.stringify(r.notas)},"notasMod":${JSON.stringify(r.notasMod)},"borrados":${JSON.stringify(r.borrados)}}\n`;
  };
  async function leerMes(mes) {
    let d; try { d = JSON.parse(await leerRaw(`${DIR}/${mes}.json`)); } catch (e) { if (e.tipo) throw e; throw falla('http', `diario/${mes}.json del repo no es un JSON válido; no se sobrescribe.`); }
    return aRegistro(mes, d);
  }
  /* sustituye el contenido de un mes NO modificado por lo que hay en GitHub */
  async function traer(mes, sha) {
    const rem = await leerMes(mes), r = registro(mes);
    r.trades = rem.trades; r.notas = rem.notas; r.notasMod = rem.notasMod; r.borrados = rem.borrados; r.sha = sha; r.dirty = false; r.pend = 'merge';
    invalidar(); persistir(mes);
  }
  async function traerBorrados(lista) {
    if (!lista.borr || lista.borr === legBsha) return;
    try { const d = JSON.parse(await leerRaw(`${DIR}/borrados.json`)); legB = Object.assign({}, legB, obj(d.borrados)); legBsha = lista.borr; await KV.set('legacy-borrados', { b: legB, sha: legBsha }); invalidar(); } catch (e) { if (e.tipo) throw e; }
  }

  /* ------------------------------------------------------------ migración remota diario.json → diario/AAAA-MM.json (idempotente) */
  async function migrarRemoto(lista) {
    let leg;
    try { leg = norm(JSON.parse(await leerRaw(LEGACY))); } catch (e) { if (e.tipo) throw e; throw falla('http', 'El diario.json antiguo no es un JSON válido: no se migra ni se toca.'); }
    const por = {}, g = (m) => (por[m] = por[m] || { trades: {}, notas: {}, notasMod: {}, borrados: {} });
    leg.trades.forEach((t) => { if (t && t.id) g(mesDe(t.fecha)).trades[t.id] = t; });
    Object.keys(leg.notas).forEach((d) => { const x = g(mesDe(d)); x.notas[d] = leg.notas[d]; if (leg.notasMod[d]) x.notasMod[d] = leg.notasMod[d]; });
    /* lápidas antiguas: a diario/borrados.json (unión con las que ya hubiera) */
    let b = Object.assign({}, legB, leg.borrados);
    if (lista.borr) { try { b = Object.assign({}, obj(JSON.parse(await leerRaw(`${DIR}/borrados.json`)).borrados), b); } catch (e) { if (e.tipo) throw e; } }
    let sb = lista.borr;
    if (Object.keys(b).length) sb = await poner(`${DIR}/borrados.json`, JSON.stringify({ version: 2, nota: 'Lápidas (operaciones borradas) del formato antiguo diario.json', borrados: b }, null, 1) + '\n', lista.borr, 'Diario: lápidas del formato antiguo');
    legB = b; legBsha = sb; await KV.set('legacy-borrados', { b: legB, sha: legBsha });
    let nT = 0, nN = 0;
    const escritos = new Set();
    for (const mes of Object.keys(por).sort()) {
      let fusion = por[mes];
      const sha = lista.meses.get(mes) || null;
      if (sha) fusion = mezclar(aRegistro(mes, por[mes]), await leerMes(mes));   // lo que ya hubiera en el mes (formato nuevo) gana a igualdad
      const r = Object.assign(nuevo(mes), fusion);
      await poner(`${DIR}/${mes}.json`, textoMes(r), sha, `Diario ${mes}: migrado desde diario.json (${Object.keys(r.trades).length} operaciones)`);
      Object.keys(r.trades).forEach((id) => escritos.add(id));
      nT += Object.keys(r.trades).length; nN += Object.values(r.notas).filter(Boolean).length;
    }
    /* comprobación antes de dejar la marca: toda operación del diario.json antiguo (no borrada) está en algún mes */
    const falta = leg.trades.filter((t) => t && t.id && !leg.borrados[t.id] && !b[t.id] && !escritos.has(t.id));
    if (falta.length) throw falla('http', `La migración no copió ${falta.length} operaciones; se reintentará y diario.json no se toca.`);
    await poner(`${DIR}/_migracion.json`, JSON.stringify({ version: 2, migrado: ahoraISO(), desde: LEGACY, sha_diario_json: lista.legacy && lista.legacy.sha, operaciones_en_meses: nT, notas_en_meses: nN, meses: Object.keys(por).sort(), nota: 'diario.json se conserva como copia y ya no se lee ni se escribe.' }, null, 1) + '\n', null, 'Diario: migración a un archivo por mes completada');
  }

  /* ------------------------------------------------------------ carga (local + remoto) */
  async function iniciar() {
    if (!iniciado) iniciado = (async () => {
      await KV.abrir();
      const lb = await KV.get('legacy-borrados'); if (lb) { legB = obj(lb.b); legBsha = lb.sha || null; }
      /* una vez: el diario del localStorage antiguo pasa a registros por mes (el original se deja intacto como copia) */
      if (!(await KV.get('migrado-ls'))) {
        const s = lsGet(KLOC, null);
        if (s && Array.isArray(s.trades)) {
          const n = norm(s), por = {};
          n.trades.forEach((t) => { if (t && t.id) (por[mesDe(t.fecha)] = por[mesDe(t.fecha)] || []).push(t); });
          Object.keys(n.notas).forEach((d) => { por[mesDe(d)] = por[mesDe(d)] || []; });
          for (const m of Object.keys(por)) {
            const prev = await KV.get('mes:' + m), r = prev ? Object.assign(nuevo(m), prev) : nuevo(m);
            por[m].forEach((t) => { r.trades[t.id] = t; });
            Object.keys(n.notas).filter((d) => mesDe(d) === m).forEach((d) => { r.notas[d] = n.notas[d]; r.notasMod[d] = n.notasMod[d] || ''; });
            r.dirty = true; R.set(m, r); await KV.set('mes:' + m, serial(r));
          }
          Object.entries(n.borrados).forEach(([id, ts]) => { if (!(id in legB)) legB[id] = ts; });
          await KV.set('legacy-borrados', { b: legB, sha: legBsha });
        }
        await KV.set('migrado-ls', ahoraISO());
      }
      for (const k of await KV.keys()) {                 // meses locales: se anotan todos; se cargan en memoria los que tienen cambios sin subir
        if (!String(k).startsWith('mes:')) continue;
        conocidos.add(String(k).slice(4));
        const rec = await KV.get(k);
        if (rec && rec.dirty && !R.has(rec.mes)) R.set(rec.mes, Object.assign(nuevo(rec.mes), rec));
      }
      invalidar();
    })();
    return iniciado;
  }
  /* carga en memoria los meses pedidos (o 'todos'); si hay conexión, descarga solo los que han cambiado en GitHub */
  async function asegurar(que) {
    await iniciar();
    let lista = null;
    if (cfg()) { try { lista = await listar(); } catch (e) { /* sin red o sin permiso: se usa lo local */ } }
    const meses = que === 'todos' ? [...new Set([...conocidos, ...R.keys(), ...(lista ? lista.meses.keys() : [])])] : [].concat(que);
    let cambio = false;
    for (const m of meses) {
      if (!mesOk(m)) continue;
      if (!R.has(m)) { const rec = await KV.get('mes:' + m); if (rec) { R.set(m, Object.assign(nuevo(m), rec)); cambio = true; } }
      const r = R.get(m), sha = lista && lista.meses.get(m);
      if (sha && (!r || (!r.dirty && r.sha !== sha))) { try { await traer(m, sha); cambio = true; } catch (e) { if (e.tipo === 'auth') throw e; } }
    }
    if (lista) { try { await traerBorrados(lista); } catch (e) { /* se reintenta en la sincronización */ } }
    if (cambio) { depurar(); invalidar(); }
    return estado();
  }

  /* ------------------------------------------------------------ una pasada de sincronización: sube los meses con cambios y refresca los cargados */
  async function pasada() {
    if (!cfg()) { fase('off'); return false; }
    fase('sync');
    await iniciar();
    let lista = await listar();
    if (lista.legacy && !lista.migrado) {
      try { await migrarRemoto(lista); } catch (e) { if (e.tipo === 'conflicto') return true; throw e; }
      lista = await listar();
    }
    await traerBorrados(lista);
    let repetir = false;
    for (const r of [...R.values()]) {
      const sha = lista.meses.get(r.mes) || null;
      if (!r.dirty) { if (sha && sha !== r.sha) { await traer(r.mes, sha); if (aviso) aviso(); } continue; }
      const v0 = r.ver;
      let propio = r;
      if (sha && r.pend !== 'replace' && sha !== r.sha) {      // otro dispositivo escribió este mes: se fusiona
        const m = mezclar(await leerMes(r.mes), r);
        if (r.ver === v0) { Object.assign(r, m); invalidar(); if (aviso) aviso(); }
        propio = Object.assign(nuevo(r.mes), m);
      }
      const sinContenido = !Object.keys(propio.trades).length && !Object.values(propio.notas).some(Boolean) && !Object.keys(propio.borrados).length;
      if (!sha && sinContenido) { r.dirty = false; r.pend = 'merge'; persistir(r.mes); continue; }
      let nuevoSha;
      try {
        nuevoSha = await poner(`${DIR}/${r.mes}.json`, textoMes(propio), sha, `Diario ${r.mes} · ${Object.keys(propio.trades).length} operaciones`);
      } catch (e) { if (e.tipo === 'conflicto') { repetir = true; continue; } throw e; }
      r.sha = nuevoSha;
      if (r.ver === v0) { r.dirty = false; r.pend = 'merge'; } else repetir = true;
      persistir(r.mes);
    }
    depurar();
    return repetir;
  }
  async function ejecutar() {
    if (!cfg()) return;
    if (busy) { again = true; return; }
    busy = true;
    try {
      let n = 0, repetir;
      do { again = false; repetir = await pasada(); n++; } while ((repetir || again) && n < 4);
      S.hora = new Date();
      const sucio = [...R.values()].some((r) => r.dirty);
      fase(sucio ? 'offline' : 'ok', sucio ? 'Quedan cambios por subir; se reintentará.' : '');
      if (aviso) aviso();
    } catch (e) {
      if (e instanceof TypeError) fase('offline', 'Sin conexión con GitHub: usas la copia de este navegador y se sincronizará al volver.');
      else fase('error', e && e.message ? e.message : 'Error de sincronización.');
    } finally { busy = false; }
  }
  function agenda() { if (!cfg()) return; clearTimeout(timer); timer = setTimeout(ejecutar, 700); }

  /* ------------------------------------------------------------ interfaz */
  function fase(f, msg) { S.fase = f; S.msg = msg || ''; pintar(); }
  function panelHtml() {
    const c = cfg(), hh = S.hora ? S.hora.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' }) : '';
    const dot = { off: 'flat', sync: 'amber', ok: 'up', offline: 'amber', error: 'down' }[S.fase];
    const txt = {
      off: 'GitHub no conectado · el diario solo está en este navegador.',
      sync: 'Sincronizando con GitHub…',
      ok: `Sincronizado con el repo privado nexora-diario (un archivo por mes)${hh ? ' · ' + hh : ''}.`,
      offline: S.msg || 'Sin conexión: copia local en uso.',
      error: S.msg || 'Error de sincronización.',
    }[S.fase];
    const b = (a, t, on) => `<button class="fbtn ${on ? 'on' : ''}" data-a="${a}">${t}</button>`;
    let h = `<div class="jsync"><span class="${dot}">●</span><span class="jsync-t">${esc(txt)}${S.sinLocal ? ' Este navegador no permite guardar una copia local persistente (IndexedDB): lo que no esté sincronizado con GitHub se perderá al cerrar.' : ''}</span><span class="jsync-b">`;
    h += c ? b('gh-sync', 'Sincronizar') + b('gh-off', 'Desconectar') : b('gh-conectar', 'Conectar GitHub', true);
    h += '</span></div>';
    if (!c && abierto) {
      h += `<form id="jghform" class="jghform"><label>Token fine-grained de GitHub (solo Contents de nexora-diario)
        <input type="password" name="token" autocomplete="off" spellcheck="false" placeholder="github_pat_…" required></label>
        <button class="fbtn on" type="submit">Guardar y sincronizar</button>
        <div class="note">El token se guarda únicamente en el localStorage de este navegador. No se sube al repo público ni se muestra en pantalla.</div></form>`;
    }
    return h;
  }
  function pintar() {
    const el = document.getElementById('jsync');
    if (!el) return;
    const t = el.querySelector('input[name=token]');
    if (t && t.value) return; // no pisar un token a medio pegar
    const doc = new DOMParser().parseFromString(panelHtml(), 'text/html'); // HTML ya escapado con esc()
    el.replaceChildren(...doc.body.childNodes);
  }

  async function conectar(token) {
    const t = String(token || '').trim();
    if (!t) return;
    fase('sync');
    try {
      lsSet(KC, { token: t });
      const r = await llamar(API, 'GET');
      if (!r.ok) throw falla('auth', msgAuth);
      const j = await r.json();
      if (j.permissions && j.permissions.push === false) throw falla('auth', 'El token solo tiene lectura: necesita Contents en modo lectura y escritura.');
      await iniciar();
      /* todo lo que ya había en este navegador se marca para subir (se fusiona con lo remoto, no lo sustituye) */
      for (const k of await KV.keys()) {
        if (!String(k).startsWith('mes:')) continue;
        const m = String(k).slice(4);
        if (!R.has(m)) { const rec = await KV.get(k); if (rec) R.set(m, Object.assign(nuevo(m), rec)); }
      }
      R.forEach((r) => { if (Object.keys(r.trades).length || Object.values(r.notas).some(Boolean)) { r.dirty = true; persistir(r.mes); } });
      abierto = false;
      window.dispatchEvent(new Event('nexora:diario-conexion'));
    } catch (e) {
      try { localStorage.removeItem(KC); } catch (x) { /* sin almacenamiento */ }
      fase(e instanceof TypeError ? 'offline' : 'error', e instanceof TypeError ? 'Sin conexión: no se pudo comprobar el token.' : e.message);
      return;
    }
    await ejecutar();
  }
  function desconectar() {
    try { localStorage.removeItem(KC); } catch (e) { /* sin almacenamiento */ }
    abierto = false; S.hora = null; fase('off');
    window.dispatchEvent(new Event('nexora:diario-conexion'));
    if ((location.hash || '').startsWith('#/operativa')) route();
  }

  window.addEventListener('online', () => { if (cfg()) ejecutar(); });

  return {
    norm, mezclar, REPO,
    conectado: () => !!cfg(),
    iniciar, asegurar, estado,
    guardarTrade, borrarTrade, guardarNota, reemplazar,
    /* fn() se llama cuando una sincronización cambia lo que hay en memoria (para repintar) */
    onCambio(fn) { aviso = fn; },
    mesesCargados: () => [...R.keys()].filter(mesOk).sort(),
    mesesConocidos: () => [...new Set([...conocidos, ...R.keys()])].filter(mesOk).sort(),
    abrir() { pintar(); if (cfg()) ejecutar(); },
    sincronizar: ejecutar,
    html: panelHtml,
    accion(a) {
      if (a === 'gh-conectar') { abierto = !abierto; pintar(); return true; }
      if (a === 'gh-sync') { ejecutar(); return true; }
      if (a === 'gh-off') { if (confirm('¿Desconectar GitHub? Se borra el token de este navegador; la copia local y la del repo se conservan.')) desconectar(); return true; }
      return false;
    },
    enviar(form) { const t = new FormData(form).get('token'); form.reset(); conectar(String(t || '')); },
  };
})();
