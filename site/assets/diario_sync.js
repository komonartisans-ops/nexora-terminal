/* NEXORA TERMINAL · sincronización del Diario de operaciones con un repo PRIVADO de GitHub.
   Se carga antes de fase5.js. Guarda el diario en komonartisans-ops/nexora-diario/diario.json con la API de Contents.
   PRIVACIDAD: el token (fine-grained, solo Contents de nexora-diario) vive SOLO en el localStorage de este navegador.
   Nunca se escribe en el repo público, ni en una URL, ni en la consola. Sin token no se envía nada a ningún servidor.
   Estrategia: la copia local manda mientras haya cambios pendientes («dirty»); al volver la red se fusiona con la remota
   (unión por id, borrados con lápida, notas por fecha de modificación). Importar JSON sustituye la copia remota.
   Todo texto dinámico pasa por esc() antes de entrar en el HTML. */
'use strict';
const DSYNC = (() => {
  const REPO = 'komonartisans-ops/nexora-diario', RUTA = 'diario.json';
  const KC = 'nexora.diario.gh.v1', KM = 'nexora.diario.sync.v1';
  const URL_ARCHIVO = `https://api.github.com/repos/${REPO}/contents/${RUTA}`, URL_REPO = `https://api.github.com/repos/${REPO}`;
  const S = { fase: 'off', msg: '', hora: null }; // fase: off | sync | ok | offline | error
  let io = null, ver = 0, timer = null, busy = false, again = false, abierto = false;

  const cfg = () => { const c = lsGet(KC, null); return c && typeof c.token === 'string' && c.token ? c : null; };
  const meta = () => Object.assign({ sha: null, dirty: false, pend: 'merge' }, lsGet(KM, {}));
  const setMeta = (p) => lsSet(KM, Object.assign(meta(), p));
  const obj = (o) => (o && typeof o === 'object' && !Array.isArray(o) ? o : {});

  /* estado del diario normalizado: {trades, notas, notasMod, borrados} */
  const norm = (s) => { const o = obj(s); return { trades: Array.isArray(o.trades) ? o.trades : [], notas: obj(o.notas), notasMod: obj(o.notasMod), borrados: obj(o.borrados) }; };
  const vacio = (s) => !s.trades.length && !Object.values(s.notas).some(Boolean);
  const canon = (s) => {
    const n = norm(s), ord = (o) => Object.keys(o).sort().reduce((a, k) => { a[k] = o[k]; return a; }, {});
    return JSON.stringify({ t: n.trades.slice().sort((a, b) => String(a.id).localeCompare(String(b.id))), n: ord(n.notas), m: ord(n.notasMod), b: ord(n.borrados) });
  };
  function merge(r, l) {
    const borrados = Object.assign({}, r.borrados, l.borrados), mp = new Map();
    [...r.trades, ...l.trades].forEach((t) => { if (t && t.id && !borrados[t.id]) mp.set(t.id, t); });
    const notas = {}, notasMod = {};
    new Set([...Object.keys(r.notas), ...Object.keys(l.notas)]).forEach((d) => {
      const tr = r.notasMod[d] || '', tl = l.notasMod[d] || '';
      const loc = d in l.notas && (!(d in r.notas) || tl >= tr);
      notas[d] = loc ? l.notas[d] : r.notas[d];
      if (loc ? tl : tr) notasMod[d] = loc ? tl : tr;
    });
    return { trades: [...mp.values()], notas, notasMod, borrados };
  }

  const b64e = (s) => { let b = ''; new TextEncoder().encode(s).forEach((x) => { b += String.fromCharCode(x); }); return btoa(b); };
  const b64d = (s) => new TextDecoder().decode(Uint8Array.from(atob(s.replace(/\s/g, '')), (c) => c.charCodeAt(0)));
  const falla = (tipo, msg) => Object.assign(new Error(msg), { tipo });
  const llamar = (url, metodo, cuerpo) => fetch(url, {
    method: metodo, cache: 'no-store',
    headers: Object.assign({ Accept: 'application/vnd.github+json', Authorization: 'Bearer ' + cfg().token, 'X-GitHub-Api-Version': '2022-11-28' }, cuerpo ? { 'Content-Type': 'application/json' } : {}),
    body: cuerpo ? JSON.stringify(cuerpo) : undefined,
  });
  const msgAuth = 'El token no es válido, ha caducado o no tiene permiso de Contents (lectura y escritura) sobre nexora-diario.';

  /* ---------------------------------------------------------------- una pasada de sincronización */
  async function pasada() {
    if (!cfg()) { fase('off'); return false; }
    fase('sync');
    const r = await llamar(URL_ARCHIVO, 'GET');
    let remoto = null, sha = null;
    if (r.status === 404) {
      /* 404 = el archivo aún no existe (repo vacío) o el token no ve el repo: se distingue mirando el repo */
      const rr = await llamar(URL_REPO, 'GET');
      if (rr.status === 401 || rr.status === 403 || rr.status === 404) throw falla('auth', msgAuth);
    } else if (r.status === 401 || r.status === 403) throw falla('auth', msgAuth);
    else if (!r.ok) throw falla('http', `GitHub respondió ${r.status}.`);
    else {
      const j = await r.json();
      if (j.encoding !== 'base64') throw falla('http', 'diario.json es demasiado grande para la API de Contents (más de 1 MB).');
      try { remoto = norm(JSON.parse(b64d(j.content))); } catch (e) { throw falla('http', 'diario.json del repo no es un JSON válido; no se sobrescribe.'); }
      sha = j.sha;
    }
    const m = meta(), local = norm(io.get()), v0 = ver;
    if (remoto && !m.dirty) {
      if (canon(remoto) !== canon(local)) io.set(remoto);
      setMeta({ sha }); return false;
    }
    const next = remoto && m.pend !== 'replace' ? merge(remoto, local) : local;
    if (remoto && canon(next) === canon(remoto)) {
      setMeta({ sha, dirty: false, pend: 'merge' });
      if (canon(next) !== canon(local) && v0 === ver) io.set(next);
      return false;
    }
    if (!remoto && !m.dirty && vacio(next)) return false;
    const n = next.trades.length, k = Object.values(next.notas).filter(Boolean).length;
    const doc = Object.assign({ version: 1, actualizado: new Date().toISOString() }, next);
    const w = await llamar(URL_ARCHIVO, 'PUT', Object.assign(
      { message: `Diario ${new Date().toISOString()} · ${n} operaciones, ${k} notas`, content: b64e(JSON.stringify(doc, null, 1) + '\n') },
      sha ? { sha } : {}));
    if (w.status === 409 || w.status === 422) return true; // alguien escribió antes: se vuelve a leer y fusionar
    if (w.status === 401 || w.status === 403) throw falla('auth', msgAuth);
    if (!w.ok) throw falla('http', `GitHub respondió ${w.status} al guardar.`);
    const nuevo = (await w.json()).content.sha, cambio = v0 !== ver;
    setMeta({ sha: nuevo, dirty: cambio, pend: cambio ? m.pend : 'merge' });
    if (!cambio && canon(next) !== canon(local)) io.set(next);
    return cambio;
  }

  async function ejecutar() {
    if (!io || !cfg()) return;
    if (busy) { again = true; return; }
    busy = true;
    try {
      let n = 0, repetir;
      do { again = false; repetir = await pasada(); n++; } while ((repetir || again) && n < 4);
      S.hora = new Date(); fase(meta().dirty ? 'offline' : 'ok', meta().dirty ? 'Quedan cambios por subir; se reintentará.' : '');
    } catch (e) {
      if (e instanceof TypeError) fase('offline', 'Sin conexión con GitHub: usas la copia de este navegador y se sincronizará al volver.');
      else fase('error', e && e.message ? e.message : 'Error de sincronización.');
    } finally { busy = false; }
  }
  const agenda = () => { clearTimeout(timer); timer = setTimeout(ejecutar, 700); };

  /* ---------------------------------------------------------------- interfaz */
  function fase(f, msg) { S.fase = f; S.msg = msg || ''; pintar(); }
  function panelHtml() {
    const c = cfg(), hh = S.hora ? S.hora.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' }) : '';
    const dot = { off: 'flat', sync: 'amber', ok: 'up', offline: 'amber', error: 'down' }[S.fase];
    const txt = {
      off: 'GitHub no conectado · el diario solo está en este navegador.',
      sync: 'Sincronizando con GitHub…',
      ok: `Sincronizado con el repo privado nexora-diario${hh ? ' · ' + hh : ''}.`,
      offline: S.msg || 'Sin conexión: copia local en uso.',
      error: S.msg || 'Error de sincronización.',
    }[S.fase];
    const b = (a, t, on) => `<button class="fbtn ${on ? 'on' : ''}" data-a="${a}">${t}</button>`;
    let h = `<div class="jsync"><span class="${dot}">●</span><span class="jsync-t">${esc(txt)}</span><span class="jsync-b">`;
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

  /* ---------------------------------------------------------------- API pública */
  async function conectar(token) {
    const t = String(token || '').trim();
    if (!t) return;
    fase('sync');
    try {
      lsSet(KC, { token: t });
      const r = await llamar(URL_REPO, 'GET');
      if (!r.ok) throw falla('auth', msgAuth);
      const j = await r.json();
      if (j.permissions && j.permissions.push === false) throw falla('auth', 'El token solo tiene lectura: necesita Contents en modo lectura y escritura.');
      const loc = norm(io.get());
      lsSet(KM, { sha: null, dirty: !vacio(loc), pend: 'merge' });
      abierto = false;
    } catch (e) {
      try { localStorage.removeItem(KC); } catch (x) { /* sin almacenamiento */ }
      fase(e instanceof TypeError ? 'offline' : 'error', e instanceof TypeError ? 'Sin conexión: no se pudo comprobar el token.' : e.message);
      return;
    }
    await ejecutar();
  }
  function desconectar() {
    try { localStorage.removeItem(KC); localStorage.removeItem(KM); } catch (e) { /* sin almacenamiento */ }
    abierto = false; S.hora = null; fase('off');
  }

  window.addEventListener('online', () => { if (io && cfg()) ejecutar(); });

  return {
    norm, merge, canon, REPO,
    conectado: () => !!cfg(),
    /* io: {get(): estado actual, set(estado): adopta uno remoto/fusionado} */
    bind(o) { io = o; },
    abrir() { pintar(); if (cfg()) ejecutar(); },
    /* llamar tras cada alta, edición o borrado: pend='replace' fuerza que la copia local sustituya a la remota (importar) */
    cambio(pend) {
      ver++;
      if (!cfg()) return;
      setMeta({ dirty: true, pend: pend === 'replace' ? 'replace' : meta().pend });
      agenda();
    },
    html: panelHtml,
    /* acciones de botón; devuelve true si las gestiona */
    accion(a) {
      if (a === 'gh-conectar') { abierto = !abierto; pintar(); return true; }
      if (a === 'gh-sync') { ejecutar(); return true; }
      if (a === 'gh-off') { if (confirm('¿Desconectar GitHub? Se borra el token de este navegador; la copia local y la del repo se conservan.')) desconectar(); return true; }
      return false;
    },
    enviar(form) { const t = new FormData(form).get('token'); form.reset(); conectar(String(t || '')); },
  };
})();
