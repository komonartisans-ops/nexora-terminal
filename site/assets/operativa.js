/* NEXORA TERMINAL · Diario conectado con el sistema: «foto» del estado de NEXORA a la hora de entrada de cada operación y página «Mi operativa».
   Se carga después de fase5.js. Todo texto dinámico pasa por esc().
   PRIVACIDAD: la foto se guarda dentro de la operación (localStorage + diario.json del repo PRIVADO nexora-diario), nunca en el repo público.
   Del repo público solo se LEEN los contextos históricos (data/historico_contexto/…json.gz, sin datos personales).
   Nunca se inventa nada: si no hay contexto anterior a la hora de entrada, o un bloque no tiene dato, la foto lo dice (SIN HISTÓRICO / SIN DATO). */
'use strict';

const FOTO = (() => {
  const VENTANA_EVENTO_MIN = 2 * 60;            // evento de importancia ALTA a ±2 h de la entrada
  const TZ = 'Europe/Madrid';
  let indicePromesa = null;
  const cacheCtx = new Map();                    // 'AAAA-MM-DD/HHMM' -> contexto

  /* 'AAAA-MM-DD' + 'HH:MM' en hora de Madrid -> milisegundos UTC (con cambio de horario). null si no es válido */
  function madridMs(fecha, hhmm) {
    const f = /^(\d{4})-(\d{2})-(\d{2})$/.exec(fecha || ''), h = /^(\d{1,2}):(\d{2})$/.exec(hhmm || '');
    if (!f || !h || +h[1] > 23 || +h[2] > 59) return null;
    const nominal = Date.UTC(+f[1], +f[2] - 1, +f[3], +h[1], +h[2]);
    const fmt = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
    const offset = (ms) => { // minutos que Madrid va por delante de UTC en ese instante
      const p = Object.fromEntries(fmt.formatToParts(new Date(ms)).map((x) => [x.type, x.value]));
      return (Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute) - ms) / 6e4;
    };
    let ms = nominal - offset(nominal) * 6e4;
    ms = nominal - offset(ms) * 6e4;             // segunda pasada: la primera puede caer al otro lado del cambio de hora
    return ms;
  }
  const stampMs = (s) => { const d = stampDate(s); return d && !isNaN(d) ? d.getTime() : null; };
  const utcTxt = (ms) => new Date(ms).toISOString().slice(0, 16).replace('T', ' ') + ' UTC';

  /* ---------------------------------------------------------------- índice y contextos históricos */
  function indice() {
    if (!indicePromesa) {
      indicePromesa = fetch('data/historico_contexto_indice.json?v=' + Date.now(), { cache: 'no-store' })
        .then((r) => { if (!r.ok) throw new Error('índice ' + r.status); return r.json(); })
        .then((j) => {
          const fotos = [];
          Object.entries(j.dias || {}).forEach(([d, hs]) => hs.forEach((hh) => {
            const ms = Date.UTC(+d.slice(0, 4), +d.slice(5, 7) - 1, +d.slice(8, 10), +hh.slice(0, 2), +hh.slice(2));
            fotos.push({ ms, clave: `${d}/${hh}` });
          }));
          fotos.sort((a, b) => a.ms - b.ms);
          return { base: j.base, fotos };
        })
        .catch((e) => { indicePromesa = null; throw e; });  // un fallo puntual no se queda cacheado
    }
    return indicePromesa;
  }
  async function leerGz(url) {
    if (typeof DecompressionStream === 'undefined') throw new Error('este navegador no puede descomprimir gzip');
    const r = await fetch(url, { cache: 'force-cache' });
    if (!r.ok) throw new Error('histórico ' + r.status);
    return new Response(r.body.pipeThrough(new DecompressionStream('gzip'))).json();
  }
  async function contextoDe(base, clave) {
    if (!cacheCtx.has(clave)) cacheCtx.set(clave, await leerGz(`${base}${clave}.json.gz`));
    return cacheCtx.get(clave);
  }

  /* contexto más cercano ANTERIOR (o igual) a la hora de entrada. Devuelve {ctx, origen} o {sin: motivo}. Lanza si la red falla. */
  async function contextoAntes(ms) {
    const vivo = D.contexto && stampMs(D.contexto.generado_utc) != null && stampMs(D.contexto.generado_utc) <= ms ? D.contexto : null;
    let ix = null;
    try { ix = await indice(); } catch (e) { if (!vivo) throw e; }
    let mejor = null;
    if (ix) for (let i = ix.fotos.length - 1; i >= 0; i--) if (ix.fotos[i].ms <= ms) { mejor = ix.fotos[i]; break; }
    if (vivo && (!mejor || stampMs(vivo.generado_utc) >= mejor.ms)) return { ctx: vivo, ms: stampMs(vivo.generado_utc), origen: 'publicado' };
    if (!mejor) return { sin: 'No hay contexto guardado anterior a esa hora (el histórico empieza el ' + (ix && ix.fotos[0] ? utcTxt(ix.fotos[0].ms) : 'SIN DATO') + ').' };
    return { ctx: await contextoDe(ix.base, mejor.clave), ms: mejor.ms, origen: 'histórico' };
  }
  /* contexto vivo cargado bajo demanda (el resto de páginas no lo necesitan) */
  async function cargarVivo() {
    if (D.contexto) return;
    try { const r = await fetch('data/contexto.json?v=' + Date.now(), { cache: 'no-store' }); if (r.ok) D.contexto = await r.json(); } catch (e) { /* sin red: solo histórico */ }
  }

  /* ---------------------------------------------------------------- extracción de la foto (solo lee; lo que falte queda null) */
  const ACT_TESIS = { 'Oro': 'Oro', 'Bitcoin': 'Bitcoin', 'S&P 500': 'S&P 500', 'Nasdaq 100': 'Nasdaq 100', 'US30': 'US30', 'Russell 2000': 'Russell 2000' };
  const ACT_GAMMA = { 'Nasdaq 100': 'NQ', 'S&P 500': 'ES' };
  const val = (v) => (v === undefined ? null : v);

  function eventosAlta(listas, ms) {
    const dentro = [], sinHora = [], vistos = new Set();
    listas.forEach((e) => {
      if (!e || e.importancia !== 'ALTA') return;
      const k = `${e.fecha}|${e.hora_madrid}|${e.evento}`;
      if (vistos.has(k)) return;
      vistos.add(k);
      const t = e.hora_madrid ? madridMs(e.fecha, e.hora_madrid) : null;
      if (t == null) { sinHora.push(e); return; }
      const min = Math.round((t - ms) / 6e4);
      if (Math.abs(min) <= VENTANA_EVENTO_MIN) dentro.push({ evento: e.evento, fecha: e.fecha, hora_madrid: e.hora_madrid, min_respecto_entrada: min });
    });
    dentro.sort((a, b) => Math.abs(a.min_respecto_entrada) - Math.abs(b.min_respecto_entrada));
    return { dentro, sinHora };
  }

  function extraer(ctx, trade, ms, ctxMs, origen, agendaExtra) {
    const faltan = [];
    const nombreTesis = ACT_TESIS[trade.activo];
    const tp = (ctx.tesis && ctx.tesis.tesis_por_activo) || [];
    const t = nombreTesis ? tp.find((x) => String(x.activo).startsWith(nombreTesis)) : null;
    if (nombreTesis && !t) faltan.push('tesis');
    const R = ctx.regimen_macro, L = ctx.liquidez, C = ctx.ciclo, F = ctx.fedwatch_y_tipos, S = ctx.riesgo_de_cola_skew, G = ctx.gamma_indices;
    const reu = F && F.reuniones && F.reuniones[0];
    if (!R || !R.cuadrante_simple) faltan.push('regimen'); if (!L || !L.lectura) faltan.push('liquidez'); if (!C || !C.fase) faltan.push('ciclo');
    if (!reu) faltan.push('fedwatch'); if (!S || !S.zona) faltan.push('skew');
    const gk = ACT_GAMMA[trade.activo], g = gk && G && G.indices && G.indices[gk];
    if (gk && !g) faltan.push('gamma');
    /* eventos: la Agenda oficial si el contexto la trae; los contextos anteriores al 15-oct-2026 solo traen el calendario de 14 días */
    const ag = ctx.agenda, cal = ctx.calendario && ctx.calendario.proximos_14_dias;
    const fuenteEv = ag ? 'agenda' : cal ? 'calendario' : null;
    const lista = [...(ag ? [...(ag.hoy || []), ...(ag.proximos_7_dias || [])] : cal || []), ...(agendaExtra || [])];
    if (!fuenteEv) faltan.push('agenda');
    const ev = eventosAlta(lista, ms);
    return {
      version: 1, estado: 'OK',
      entrada_utc: utcTxt(ms), contexto_utc: utcTxt(ctxMs), contexto_generado: ctx.generado_utc || null, origen,
      desfase_min: Math.round((ms - ctxMs) / 6e4),
      tesis: t ? { activo: t.activo, etiqueta: t.etiqueta, viento_semana: val(t.viento_semana), motor_propio: val(t.veredicto_motor_propio) } : null,
      regimen: R && R.cuadrante_simple ? { cuadrante: R.cuadrante_simple.cuadrante, nexora: val(R.cuadrante), riesgo: val(R.riesgo), liquidez: val(R.liquidez) } : null,
      liquidez: L && L.lectura ? { lectura: L.lectura, checklist: L.checklist ? `${L.checklist.cumple}/${L.checklist.total}` : null } : null,
      ciclo: C && C.fase ? { fase: C.fase, prob_recesion_curva_pct: val(C.prob_recesion_curva_nyfed_pct) } : null,
      fedwatch: reu ? { reunion: reu.reunion, subida_pct: val(reu.prob_subida_pct), mantiene_pct: val(reu.prob_mantiene_pct), bajada_pct: val(reu.prob_bajada_pct) } : null,
      gamma: g ? { indice: gk, signo: val(g.regimen_gamma), flip_indice: g.gamma_flip ? val(g.gamma_flip.idx) : null, flip_futuro: g.gamma_flip ? val(g.gamma_flip.fut) : null, sesion: val(g.sesion) } : null,
      skew: S && S.zona ? { zona: S.zona, relativa: S.zona_relativa ? val(S.zona_relativa.zona_relativa) : null, valor: val(S.valor), fecha: val(S.fecha) } : null,
      evento_alta_2h: fuenteEv ? { fuente: fuenteEv, si: ev.dentro.length > 0, eventos: ev.dentro, alta_sin_hora_confirmada: ev.sinHora.filter((e) => e.fecha === trade.fecha).slice(0, 4).map((e) => ({ evento: e.evento, fecha: e.fecha })) } : null,
      faltan,
    };
  }

  /* Foto de una operación. Nunca lanza: devuelve {estado:'OK'|'SIN HORA'|'SIN HISTÓRICO'|'PENDIENTE', …} */
  async function tomar(trade) {
    const ms = madridMs(trade.fecha, trade.hora);
    if (ms == null) return { version: 1, estado: 'SIN HORA', motivo: 'La operación no tiene hora de entrada válida: no se puede elegir el contexto.' };
    try {
      await cargarVivo();
      const r = await contextoAntes(ms);
      if (r.sin) return { version: 1, estado: 'SIN HISTÓRICO', entrada_utc: utcTxt(ms), motivo: r.sin };
      /* entrada de madrugada en Madrid: los eventos de la víspera viven en el último contexto anterior a las 00:00 de ese día */
      let extra = [];
      if (+trade.hora.slice(0, 2) < 2) {
        try {
          const ix = await indice(), medianoche = madridMs(trade.fecha, '00:00');
          const ant = ix.fotos.filter((f) => f.ms < medianoche).pop();
          if (ant && medianoche - ant.ms < 36e5 * 30) { const c2 = await contextoDe(ix.base, ant.clave); extra = c2.agenda ? c2.agenda.hoy || [] : (c2.calendario && c2.calendario.proximos_14_dias) || []; }
        } catch (e) { /* sin el día anterior se queda con lo del contexto elegido */ }
      }
      return extraer(r.ctx, trade, ms, r.ms, r.origen, extra);
    } catch (e) {
      return { version: 1, estado: 'PENDIENTE', entrada_utc: utcTxt(ms), motivo: 'No se pudo leer el histórico (' + (e && e.message ? e.message : 'sin red') + '). Se reintentará al abrir el Diario.' };
    }
  }
  /* reintenta las fotos pendientes; devuelve cuántas cambió */
  async function completarPendientes(trades) {
    let n = 0;
    for (const t of trades) {
      if (t.foto && t.foto.estado === 'PENDIENTE') {
        const f = await tomar(t);
        if (f.estado !== 'PENDIENTE') { t.foto = f; n++; }
      }
    }
    return n;
  }

  /* ---------------------------------------------------------------- lectura de la foto para estadísticas */
  const dirTesis = (et) => (/^ALCISTA/.test(et || '') ? 1 : /^BAJISTA/.test(et || '') ? -1 : 0);
  /* A FAVOR / EN CONTRA / SIN TESIS según la etiqueta de tesis del activo en la foto y el lado de la operación (débil cuenta igual que fuerte) */
  function alineacion(t) {
    const f = t.foto;
    if (!f || f.estado !== 'OK') return null;
    const d = f.tesis ? dirTesis(f.tesis.etiqueta) : 0;
    if (!d) return 'SIN TESIS';
    return d === (t.lado === 'Corto' ? -1 : 1) ? 'A FAVOR' : 'EN CONTRA';
  }
  return { tomar, completarPendientes, alineacion, madridMs, utcTxt, VENTANA_EVENTO_MIN };
})();

/* ================================================================== «Mi operativa» */
const MIN_N = 20;
function statsGrupo(trs) {
  const s = diarioStats(trs);
  return Object.assign(s, { medio: s.n ? s.tot / s.n : null });
}
function tablaGrupos(titulo, sub, filas, idGraf) {
  /* filas: [[nombre, trades]] en el orden deseado */
  const calc = filas.map(([nom, trs]) => [nom, statsGrupo(trs)]);
  let h = `<div class="sect"><h2>${esc(titulo)}</h2><span class="more">${esc(sub)}</span></div><div class="grid g21" style="align-items:start"><div class="card pad0 scroll"><table class="t stack"><thead><tr><th>Grupo</th><th>n</th><th>Ganadoras</th><th>Win rate</th><th>P&amp;L total</th><th>P&amp;L medio</th><th>Factor benef.</th><th style="text-align:left">Fiabilidad</th></tr></thead><tbody>`;
  h += calc.map(([nom, s]) => {
    const corto = s.n < MIN_N;
    return `<tr class="${corto ? 'poca' : ''}"><td data-label="Grupo" style="text-align:left"><b>${esc(nom)}</b></td><td data-label="n" class="mono">${s.n}</td><td data-label="Ganadoras">${s.n ? `${s.g} / ${s.n}` : '—'}</td><td data-label="Win rate">${s.win == null ? '—' : num(s.win, 0) + ' %'}</td>
      <td data-label="P&L total" class="${f5.cls(s.tot)}">${s.n ? f5.usd(s.tot) : '—'}</td><td data-label="P&L medio" class="${f5.cls(s.medio)}">${s.n ? f5.usd(s.medio) : '—'}</td><td data-label="Factor benef.">${s.pf == null ? '—' : num(s.pf, 2)}</td>
      <td data-label="Fiabilidad" style="text-align:left;white-space:normal;min-width:150px">${s.n === 0 ? '<span class="ck sd">sin operaciones</span>' : corto ? `<span class="ck par" title="Con menos de ${MIN_N} operaciones la diferencia entre grupos no se distingue del azar">muestra insuficiente (n &lt; ${MIN_N})</span>` : '<span class="ck ok">n ≥ ' + MIN_N + '</span>'}</td></tr>`;
  }).join('');
  h += '</tbody></table></div><div class="card chartcard"><h3>P&amp;L medio por operación</h3><div class="sub">Barras apagadas = muestra insuficiente</div>';
  const con = calc.filter(([, s]) => s.n > 0);
  h += con.length ? barras(idGraf, con.map(([nom, s]) => `${nom} (n=${s.n})`), [{ name: 'P&L medio ($)', data: con.map(([, s]) => +s.medio.toFixed(2)) }], { dec: 2, alto: Math.max(150, con.length * 44 + 40), fino: 26, horizontal: true, tenue: con.map(([, s]) => s.n < MIN_N) })
    : '<div class="chart fill"><div class="empty">SIN OPERACIONES</div></div>';
  return h + '</div></div>';
}

function pageOperativa() {
  const conectado = typeof DSYNC !== 'undefined' && DSYNC.conectado();
  let h = head('Personal', 'Mi operativa', 'Cómo te ha ido según lo que decía el sistema NEXORA en el momento de entrar: a favor o en contra de su tesis, en cada régimen, con y sin un dato de importancia alta cerca. Son tus propias operaciones, leídas de tu repo privado.',
    'Registro personal · solo visible con el token del Diario conectado');
  if (!conectado) {
    return h + `<div class="card"><div class="empty" style="height:150px;flex-direction:column;gap:8px;text-align:center;padding:0 16px">PÁGINA PRIVADA · conecta tu repo nexora-diario en <a href="#/diario">Diario de operaciones</a> («Conectar GitHub») para verla.<span style="color:var(--dim);text-transform:none;letter-spacing:0">Sin el token no se muestra nada de tu operativa.</span></div></div>`;
  }
  h += '<div id="op-root"><div class="empty" style="height:160px">LEYENDO TU DIARIO…</div></div>';
  MOUNT.push(() => {
    const root = document.getElementById('op-root');
    if (!root) return;
    let st = dLoad();
    const repaint = () => { if (document.getElementById('op-root') === root) f5.paint(root, () => operativaHtml(st)); };
    /* fotos que quedaron pendientes por falta de red: se reintentan y, si cambian, se guardan y sincronizan */
    const completar = async () => {
      if (await FOTO.completarPendientes(st.trades)) { diario.st = st; lsSet(DK, st); DSYNC.cambio(); repaint(); }
    };
    repaint();
    /* la copia del repo privado se adopta al sincronizar (misma lógica que el Diario) */
    DSYNC.bind({ get: () => st, set: (s2) => { st = DSYNC.norm(s2); diario.st = st; lsSet(DK, st); repaint(); completar(); } });
    DSYNC.abrir();
    completar();
  });
  return h;
}

function operativaHtml(S) {
  const T = S.trades;
  if (!T.length) return '<div class="card"><div class="empty" style="height:140px">DIARIO VACÍO · registra operaciones con su hora de entrada para ver esta página</div></div>';
  const conFoto = T.filter((t) => t.foto && t.foto.estado === 'OK');
  const estados = {};
  T.filter((t) => !(t.foto && t.foto.estado === 'OK')).forEach((t) => { const k = t.foto ? t.foto.estado : 'SIN HORA'; estados[k] = (estados[k] || 0) + 1; });
  const g = statsGrupo(T);
  let h = essential(`${T.length} operaciones registradas, ${conFoto.length} con foto del sistema; win rate ${g.win == null ? '—' : num(g.win, 0) + ' %'}, P&amp;L ${f5.usd(g.tot)}.`,
    `Hecho: cada grupo muestra tus resultados reales según el estado de NEXORA a la hora de entrada (el contexto publicado más cercano anterior). Interpretación: ningún grupo con n &lt; ${MIN_N} permite concluir nada; con pocas operaciones una diferencia entre «a favor» y «en contra» es ruido.`,
    'Los grupos no son señales: esta página mide tu operativa, no recomienda comprar ni vender.', 'Cómo leerlo');
  if (Object.keys(estados).length) h += `<div class="note" style="margin-bottom:10px">Sin foto: ${Object.entries(estados).map(([k, n]) => `${n} (${esc(k.toLowerCase())})`).join(' · ')}. Entran en la tabla «por activo» pero no en las que dependen del estado del sistema. Añade o corrige la hora de entrada con ✎ en el Diario para completarlas.</div>`;
  const orden = (arr, f) => arr.map((k) => [k, conFoto.filter((t) => f(t) === k)]);
  h += tablaGrupos('Frente a la tesis NEXORA del activo', 'tesis alcista/bajista (débil incluida) frente a tu lado; sin tesis = sin dirección o activo sin tesis', orden(['A FAVOR', 'EN CONTRA', 'SIN TESIS'], FOTO.alineacion), 'opAlin');
  const regs = [...new Set(conFoto.map((t) => (t.foto.regimen && t.foto.regimen.cuadrante) || 'SIN DATO'))].sort();
  h += tablaGrupos('Por régimen macro', 'cuadrante crecimiento/inflación de la foto (régimen NEXORA)', orden(regs, (t) => (t.foto.regimen && t.foto.regimen.cuadrante) || 'SIN DATO'), 'opReg');
  const evt = (t) => (t.foto.evento_alta_2h ? (t.foto.evento_alta_2h.si ? 'CON EVENTO ALTA ±2 h' : 'SIN EVENTO ALTA ±2 h') : 'SIN DATO DE AGENDA');
  h += tablaGrupos('Con y sin evento cercano', 'dato de importancia alta a ±2 h de tu entrada (Agenda NEXORA)', orden(['CON EVENTO ALTA ±2 h', 'SIN EVENTO ALTA ±2 h', 'SIN DATO DE AGENDA'].filter((k) => k !== 'SIN DATO DE AGENDA' || conFoto.some((t) => evt(t) === k)), evt), 'opEvt');
  const acts = [...new Set(T.map((t) => t.activo))].sort();
  h += tablaGrupos('Por activo', 'todas las operaciones, con o sin foto', acts.map((a) => [a, T.filter((t) => t.activo === a)]), 'opAct');
  h += `<div class="note">Regla de «a favor / en contra»: se toma la etiqueta de tesis del activo en la foto (ALCISTA o BAJISTA, débil o no) y se compara con tu lado (Largo = alcista). Los activos sin tesis NEXORA (EUR/USD, USD/JPY, Otro) y las etiquetas SIN TESIS cuentan como «sin tesis». La foto es la del último contexto publicado antes de tu hora de entrada (hora de Madrid); el desfase aparece en cada operación del Diario. Win rate y P&amp;L son los que anotaste, sin ajustar por tamaño de posición.</div>`;
  return h;
}

Object.assign(window.EXTRA_PAGES, { operativa: pageOperativa });
window.FOTO = FOTO;
