/* NEXORA TERMINAL · Análisis diario (#/analisis): el informe diario de Ruiz cotejado contra los datos de NEXORA.
   Lee site/data/analisis.json (público: índice, cotejo numérico, resumen si la visibilidad es «resumen», resultados). El texto completo del informe está en el repo PRIVADO nexora-diario y solo se
   muestra con el token del Diario conectado en este navegador (el mismo de «Diario de operaciones»; nunca se envía a ningún otro sitio). Sin IA: el navegador no analiza nada, solo muestra lo que
   guardó tools/publicar_analisis.py. Todo texto dinámico pasa por esc(). */
'use strict';

const AN = { tipo: lsGet('nexora_analisis_tipo', 'ORO_MACRO'), sesgo: 'todos', sel: null, privado: {}, repo: 'komonartisans-ops/nexora-diario' };
const AN_BLOQUES = [['A', 'A · Panel y contexto'], ['B', 'B · Calendario'], ['C', 'C'], ['D', 'D'], ['E', 'E'], ['F', 'F'], ['G', 'G · Oro'], ['H', 'H'], ['I', 'I'], ['J', 'J · Escenarios, red team y data gaps'], ['K', 'K · Conclusión']];
const anSesgoCls = (s) => (s === 'alcista' ? 'ok' : s === 'bajista' ? 'no' : 'par');
const anEstCls = (e) => (e === '✅' ? 'ok' : e === '⚠️' ? 'par' : 'sd');
const anV = (v) => (v == null || Number.isNaN(+v) ? '—' : num(+v, Math.abs(+v) >= 1000 ? 1 : 2));
const anN = (v, d = 2) => (v == null || v === '' || Number.isNaN(+v) ? '—' : num(+v, d));

/* informe completo del repo privado (JSON ya extraído por el script); null si no hay token o no se puede leer */
async function anPrivado(e) {
  if (AN.privado[e.id] !== undefined) return AN.privado[e.id];
  const c = lsGet('nexora.diario.gh.v1', null);
  if (!c || !c.token) return (AN.privado[e.id] = null);
  try {
    const r = await fetch(`https://api.github.com/repos/${AN.repo}/contents/${e.ruta_privada.replace(/\.md$/, '.json')}`, { headers: { Accept: 'application/vnd.github.raw+json', Authorization: 'Bearer ' + c.token, 'X-GitHub-Api-Version': '2022-11-28' }, cache: 'no-store' });
    return (AN.privado[e.id] = r.ok ? await r.json() : null);
  } catch (err) { return (AN.privado[e.id] = null); }
}

function anCabecera(e, P) {
  const R = e.resultados || [], rp = e.resumen_publico, c = e.cotejo && e.cotejo.resumen;
  const tesis = (P && P.tesis_central) || (rp && rp.tesis_central) || '';
  const ver = (P && P.veredicto) || (rp && rp.veredicto) || '';
  let h = `<div class="card"><div class="chead"><span>${esc(fdy(e.fecha))} · corte ${esc(e.corte_madrid || '—')} (Madrid) · ${esc(e.tipo)}${e.version > 1 ? ' · v' + esc(String(e.version)) : ''}</span>`
    + `<span><span class="ck ${anSesgoCls(e.sesgo_oro)}">SESGO ORO · ${esc(String(e.sesgo_oro).toUpperCase())}</span> <span class="ck sd">${e.visibilidad === 'privado' ? 'PRIVADO' : 'RESUMEN PÚBLICO'}</span>${e.estado === 'REVISADA' ? ' <span class="ck par">REVISADA</span>' : ''}</span></div>`;
  h += `<p style="margin:8px 0 4px"><b>Tesis central.</b> ${tesis ? esc(tesis) : `<span class="sd-val">${P === undefined ? 'cargando…' : 'SIN DATO'}</span> <small>${e.visibilidad === 'privado' ? '(informe privado: conecta el Diario para verlo)' : ''}</small>`}</p>`;
  h += `<p style="margin:4px 0"><b>Veredicto.</b> ${ver ? esc(ver) : '<span class="sd-val">SIN DATO</span>'}</p>`;
  h += `<p style="margin:4px 0"><b>Cotejo con NEXORA.</b> ${c ? `<span class="ck ok">${c.ok} ✅</span> <span class="ck par">${c.dif} ⚠️</span> <span class="ck sd">${c.sin} —</span>` : '<span class="sd-val">SIN DATO</span>'}`
    + `${e.cotejo && e.cotejo.resumen_calendario ? ` · calendario: ${e.cotejo.resumen_calendario.ok} ✅ · ${e.cotejo.resumen_calendario.dif} ⚠️ · ${e.cotejo.resumen_calendario.sin} —` : ''}</p>`;
  h += `<p style="margin:4px 0"><b>Resultado del sesgo.</b> ${R.length ? R.map((r) => `T+${esc(String(r.horizonte))} (${esc(fdy(r.fecha_t))}): <span class="ck ${r.veredicto === 'CUMPLIDO' ? 'ok' : r.veredicto === 'FALLIDO' ? 'no' : 'par'}">${esc(r.veredicto)}</span> <small>oro ${anN(r.oro_pct)} % · DXY ${anN(r.dxy_var, 2)} · DFII10 ${anN(r.dfii10_pb, 1)} pb</small>`).join(' · ') : '<span class="sd-val">pendiente</span> <small>(T+1 y T+5 cuando haya esas sesiones)</small>'}</p></div>`;
  return h;
}

function anAnterior(e, todas) {
  const a = e.anterior && todas.find((x) => x.id === e.anterior);
  if (!a) return `<div class="card"><div class="note" style="margin:0"><b>Tesis anterior → hoy.</b> No hay un informe anterior de este tipo.</div></div>`;
  return `<div class="card"><div class="note" style="margin:0"><b>Tesis anterior → hoy.</b> <a href="#/analisis" data-an="${esc(a.id)}">${esc(fdy(a.fecha))}</a>: <span class="ck ${anSesgoCls(a.sesgo_oro)}">${esc(a.sesgo_oro)}</span> → <span class="ck ${anSesgoCls(e.sesgo_oro)}">${esc(e.sesgo_oro)}</span> ${a.sesgo_oro === e.sesgo_oro ? '(sin cambio de sesgo)' : '<b>(cambio de sesgo)</b>'}. El sesgo lo indica Ruiz al publicar; NEXORA no lo deduce del texto.</div></div>`;
}

function anCotejo(e) {
  const c = e.cotejo;
  if (!c) return `<div class="card"><div class="empty" style="height:80px">SIN DATO · cotejo</div></div>`;
  let h = `<div class="sect"><h2>Cotejo del panel A.2 con NEXORA</h2><span class="more">tolerancias: ${esc(c.tolerancias || '')}</span></div><div class="card pad0 scroll"><table class="t stack"><thead><tr><th></th><th style="text-align:left">Dato</th><th>Informe</th><th>NEXORA</th><th>Diferencia</th><th style="text-align:left">Fuente y fecha de NEXORA</th></tr></thead><tbody>`;
  h += (c.panel || []).map((f) => `<tr><td data-label="Estado"><span class="ck ${anEstCls(f.estado)}">${esc(f.estado)}</span></td><td data-label="Dato" style="text-align:left"><b>${esc(f.nombre)}</b></td><td data-label="Informe" class="mono">${anV(f.valor)}</td>`
    + `<td data-label="NEXORA" class="mono">${f.nexora == null ? '<span class="sd-val">SIN DATO</span>' : anV(f.nexora)}</td><td data-label="Diferencia" class="mono">${f.dif == null ? '—' : esc(String(f.dif)) + (f.tolerancia && f.tolerancia.includes('pb') ? ' pb' : f.tolerancia && f.tolerancia.includes('%') ? ' %' : '')} <small>${esc(f.tolerancia || '')}</small></td>`
    + `<td data-label="Fuente" style="text-align:left"><small>${f.fuente ? esc(f.fuente) + ' · ' + esc(f.fecha_nexora || '') : 'NEXORA no lo tiene para esa fecha'}</small></td></tr>`).join('') || '<tr><td colspan="6" style="text-align:left;color:var(--dim)">El panel A.2 no se reconoció en el informe.</td></tr>';
  h += `</tbody></table>${footIn('engine/analisis.py · históricos propios de NEXORA (misma fecha)', e.fecha, null, '✅ coincide · ⚠️ difiere · — NEXORA no lo tiene (nunca se rellena)')}</div>`;
  const cal = c.calendario || [];
  h += `<div class="sect"><h2>Calendario B.3 frente a la agenda de NEXORA</h2><span class="more">tiene en cuenta el cambio de hora (Europa 25-oct, EE. UU. 1-nov)</span></div><div class="card pad0 scroll"><table class="t stack"><thead><tr><th></th><th>Día</th><th>Hora informe</th><th style="text-align:left">Evento del informe</th><th>NEXORA (Madrid)</th><th style="text-align:left">Nota</th></tr></thead><tbody>`
    + (cal.length ? cal.map((f) => `<tr><td data-label="Estado"><span class="ck ${anEstCls(f.estado)}">${esc(f.estado)}</span></td><td data-label="Día">${esc(fdy(f.fecha))}</td><td data-label="Hora informe" class="mono">${esc(f.hora || '—')}</td><td data-label="Evento" style="text-align:left">${esc(f.texto || '—')}</td>`
      + `<td data-label="NEXORA" class="mono">${f.nexora ? esc((f.nexora.hora_madrid || '—') + ' · ' + (f.nexora.evento || '')) : '—'}</td><td data-label="Nota" style="text-align:left"><small>${esc(f.nota || '')}</small></td></tr>`).join('')
      : '<tr><td colspan="6" style="text-align:left;color:var(--dim)">El calendario B.3 no se reconoció en el informe o no tiene eventos con hora.</td></tr>');
  h += `</tbody></table></div>`;
  const F = c.fed || {};
  h += `<div class="sect"><h2>Probabilidades de la Fed · lado a lado</h2><span class="more">cada una con su fuente; son métodos distintos y no se juzgan</span></div><div class="grid g2"><div class="card"><div class="chead"><span>Informe</span></div>`
    + `${(F.informe || []).length ? F.informe.map((l) => `<p class="note" style="margin:4px 0">${esc(l)}</p>`).join('') : '<p class="note" style="margin:4px 0"><span class="sd-val">SIN DATO</span> · el informe no trae probabilidades de la Fed reconocibles</p>'}<div class="foot"><span>Fuente: ${esc(F.informe_fuente || '')}</span></div></div>`
    + `<div class="card"><div class="chead"><span>NEXORA (fedwatch.py)</span></div>${F.nexora ? `<p class="note" style="margin:4px 0">Reunión del ${esc(fdy(F.nexora.reunion))}: subida ${anN(F.nexora.subida, 1)} % · mantiene ${anN(F.nexora.mantiene, 1)} % · bajada ${anN(F.nexora.bajada, 1)} %</p>` : '<p class="note"><span class="sd-val">SIN DATO</span></p>'}<div class="foot"><span>Fuente: ${esc(F.nexora ? F.nexora.fuente : '')}</span><span>${F.nexora ? 'precios del ' + esc(fdy(F.nexora.fecha_precios)) : ''}</span></div></div></div>`;
  return h;
}

function anBloques(e, P) {
  if (!P) {
    const rp = e.resumen_publico;
    if (rp) return `<div class="sect"><h2>Resumen público</h2><span class="more">el informe completo es privado</span></div><div class="card">${anEscenarios(rp.escenarios)}<p class="note"><b>Tesis final (K.2).</b> ${esc(rp.tesis_final || 'SIN DATO')}</p></div>`;
    return `<div class="sect"><h2>Informe</h2></div><div class="card"><div class="note" style="margin:0">El texto de este informe es <b>privado</b> (repo nexora-diario). Conecta el Diario de operaciones en este navegador para verlo aquí. En el repo público solo hay el índice, el cotejo numérico y el resultado del sesgo.</div></div>`;
  }
  if (!P.reconocido) return `<div class="sect"><h2>Informe (texto tal cual)</h2><span class="more">no se reconoció ninguna cabecera: no se inventa nada</span></div><div class="card"><pre style="white-space:pre-wrap;margin:0;font:12px/1.5 var(--mono,monospace)">${esc(P.texto || '')}</pre></div>`;
  let h = `<div class="sect"><h2>Informe por bloques</h2><span class="more">G (oro) abierto · el texto es el tuyo, tal cual</span></div>`;
  const pre = (t) => `<pre style="white-space:pre-wrap;word-break:break-word;margin:0;font:12px/1.5 var(--mono,monospace);overflow-x:auto">${esc(t)}</pre>`;
  if (P.secciones && P.secciones.TESIS) h += `<details class="qa card"><summary>Tesis central</summary>${pre(P.secciones.TESIS)}</details>`;
  AN_BLOQUES.forEach(([L, t]) => { if (P.bloques && P.bloques[L]) h += `<details class="qa card" ${L === 'G' ? 'open' : ''}><summary>${esc(t)}</summary>${pre(P.bloques[L])}${L === 'G' ? anEscenarios(P.escenarios) : ''}${L === 'J' ? anJ(P) : ''}</details>`; });
  if (P.secciones && P.secciones.VEREDICTO) h += `<details class="qa card"><summary>Veredicto</summary>${pre(P.secciones.VEREDICTO)}</details>`;
  if (P.previo) h += `<details class="qa card"><summary>Cabecera del informe</summary>${pre(P.previo)}</details>`;
  return h;
}
function anEscenarios(es) {
  if (!es || !es.length) return '';
  return `<div style="margin-top:10px">${es.map((x) => `<div class="note" style="margin:6px 0"><b>${esc(x.nombre)}</b><br>Condiciones: ${esc(x.condiciones || 'SIN DATO')}<br>Confirmación: ${esc(x.confirmacion || 'SIN DATO')}<br>Invalidación: ${esc(x.invalidacion || 'SIN DATO')}</div>`).join('')}</div>`;
}
function anJ(P) {
  return `${P.red_team && P.red_team.length ? `<div class="note"><b>Red team.</b> ${esc(P.red_team.join(' '))}</div>` : ''}${P.data_gaps && P.data_gaps.length ? `<div class="note"><b>Data gaps.</b> ${esc(P.data_gaps.join(' '))}</div>` : ''}`;
}

function anHistorico(todas, e) {
  const lista = todas.filter((x) => x.tipo === AN.tipo && x.estado === 'VIGENTE' && (AN.sesgo === 'todos' || x.sesgo_oro === AN.sesgo)).slice().reverse();
  return `<div class="sect"><h2>Histórico</h2><span class="more">por fecha · filtro por sesgo de oro</span></div><div class="card pad0 scroll"><table class="t stack"><thead><tr><th>Fecha</th><th>Sesgo oro</th><th>Visibilidad</th><th>Cotejo</th><th>T+1</th><th>T+5</th></tr></thead><tbody>`
    + (lista.length ? lista.map((x) => { const r = (h) => (x.resultados || []).find((y) => String(y.horizonte) === String(h));
      const v = (y) => (y ? `<span class="ck ${y.veredicto === 'CUMPLIDO' ? 'ok' : y.veredicto === 'FALLIDO' ? 'no' : 'par'}">${esc(y.veredicto)}</span>` : '<span class="sd-val">pendiente</span>');
      return `<tr class="${e && x.id === e.id ? 'cur' : ''}"><td data-label="Fecha"><a href="#/analisis" data-an="${esc(x.id)}">${esc(fdy(x.fecha))}</a></td><td data-label="Sesgo"><span class="ck ${anSesgoCls(x.sesgo_oro)}">${esc(x.sesgo_oro)}</span></td><td data-label="Visibilidad">${esc(x.visibilidad)}</td>`
        + `<td data-label="Cotejo" class="mono">${x.cotejo ? `${x.cotejo.resumen.ok} ✅ · ${x.cotejo.resumen.dif} ⚠️ · ${x.cotejo.resumen.sin} —` : '—'}</td><td data-label="T+1">${v(r(1))}</td><td data-label="T+5">${v(r(5))}</td></tr>`; }).join('')
      : '<tr><td colspan="6" style="text-align:left;color:var(--dim)">Todavía no hay informes publicados de este tipo (con este filtro).</td></tr>')
    + '</tbody></table></div>';
}

function anAcumulado(A) {
  const a = A.acumulado || {};
  return `<div class="sect"><h2>Acierto acumulado del sesgo de oro</h2><span class="more">a T+1 y T+5 sesiones · CUMPLIDO / FALLIDO / MIXTO</span></div><div class="grid g2">`
    + ['T+1', 'T+5'].map((k) => { const x = a[k] || {}; return `<div class="card"><div class="chead"><span>${k}</span></div><div class="big">${x.acierto_pct == null ? 'SIN DATO' : num(x.acierto_pct, 1) + ' %'}</div><div class="note" style="margin:4px 0">${esc(String(x.cumplidos || 0))} cumplidos · ${esc(String(x.mixtos || 0))} mixtos · ${esc(String(x.fallidos || 0))} fallidos de ${esc(String(x.n || 0))} · <b>${esc(x.conclusion || 'n<20: sin conclusión')}</b></div></div>`; }).join('')
    + `</div><details class="qa card"><summary>Reglas del resultado (fijas)</summary><p class="note" style="white-space:pre-line">${esc(A.reglas || '')}</p></details>`;
}

function pageAnalisis() {
  const A = D.analisis;
  let h = head('Personal', 'Análisis diario', 'Tu informe diario cotejado con los datos de NEXORA: tesis, sesgo de oro, escenarios y, sobre todo, qué cifras del panel coinciden con NEXORA y cuáles difieren. Sin IA: el texto es el tuyo.',
    `Informes publicados con tools/publicar_analisis.py · ${A && A.generado_utc ? 'actualizado: ' + esc(horaAct(A.generado_utc)) : 'SIN DATO'}`);
  if (!A || !A.entradas) return h + noData('Análisis diario (analisis.json)');
  if (!A.entradas.length) return h + `<div class="card"><div class="empty" style="height:auto;padding:26px;white-space:normal">Todavía no hay ningún informe publicado. Se publica con <code>python tools/publicar_analisis.py INFORME.txt --sesgo neutral --tipo ORO_MACRO --visibilidad privado</code> (docs/ANALISIS_DIARIO.md).</div></div>` + anAcumulado(A);
  h += '<div class="picker" id="an-tabs" style="margin:0 0 10px;display:flex;gap:6px;flex-wrap:wrap"></div><div class="picker" id="an-filtro" style="margin:0 0 12px;display:flex;gap:6px;flex-wrap:wrap"></div><div id="an-root"></div>';
  h += `<div class="note" style="margin-top:14px">${esc(A.fuente || '')}. El sesgo de oro lo indica Ruiz al publicar. No es una recomendación de compra o venta.</div>`;
  MOUNT.push(() => {
    const root = document.getElementById('an-root'), tabs = document.getElementById('an-tabs'), fil = document.getElementById('an-filtro');
    if (!root) return;
    const todas = A.entradas;
    const pintar = async () => {
      if (document.getElementById('an-root') !== root) return;
      tabs.innerHTML = A.entradas.length ? ['ORO_MACRO', 'INDICES'].map((t) => `<button class="fbtn ${AN.tipo === t ? 'on' : ''}" data-tipo="${t}">${t}</button>`).join('') : '';
      fil.innerHTML = ['todos', 'alcista', 'bajista', 'neutral'].map((s) => `<button class="fbtn ${AN.sesgo === s ? 'on' : ''}" data-sesgo="${s}">${s === 'todos' ? 'Todos los sesgos' : s}</button>`).join('');
      const vig = todas.filter((x) => x.tipo === AN.tipo && x.estado === 'VIGENTE');
      const e = (AN.sel && todas.find((x) => x.id === AN.sel && x.tipo === AN.tipo)) || vig[vig.length - 1] || null;
      if (!e) { root.innerHTML = `<div class="card"><div class="empty" style="height:80px">Todavía no hay informes ${esc(AN.tipo)}.</div></div>` + anHistorico(todas, null); return; }
      root.innerHTML = anCabecera(e, undefined) + anAnterior(e, todas) + anBloques(e, null) + anCotejo(e) + anHistorico(todas, e) + anAcumulado(A);
      const P = await anPrivado(e);
      if (document.getElementById('an-root') === root && P) root.innerHTML = anCabecera(e, P) + anAnterior(e, todas) + anBloques(e, P) + anCotejo(e) + anHistorico(todas, e) + anAcumulado(A);
      else if (document.getElementById('an-root') === root) root.innerHTML = anCabecera(e, null) + anAnterior(e, todas) + anBloques(e, null) + anCotejo(e) + anHistorico(todas, e) + anAcumulado(A);
    };
    const clic = (ev) => {
      const t = ev.target.closest('[data-tipo]'), s = ev.target.closest('[data-sesgo]'), a = ev.target.closest('[data-an]');
      if (t) { AN.tipo = t.dataset.tipo; AN.sel = null; lsSet('nexora_analisis_tipo', AN.tipo); pintar(); } else if (s) { AN.sesgo = s.dataset.sesgo; pintar(); } else if (a) { ev.preventDefault(); AN.sel = a.dataset.an; pintar(); }
    };
    [tabs, fil, root].forEach((x) => x.addEventListener('click', clic));
    pintar();
  });
  return h;
}
Object.assign(window.EXTRA_PAGES, { analisis: pageAnalisis });
