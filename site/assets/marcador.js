/* NEXORA TERMINAL · Marcador de aciertos de señales (#/marcador).
   Lee site/data/marcador.json, que escribe engine/marcador.py (sin IA; registro solo-añadir en data/marcador_senales.csv y
   data/marcador_resultados.csv). La página solo muestra: no calcula ni concluye nada. Todo texto dinámico pasa por esc(). */
'use strict';

const MC = { h: '5', datos: null, gi: null };

/* marcador «gamma intradía»: MFE/MAE a 15, 30 y 60 min de los avisos enviados (solo descriptivo; reglas congeladas hasta n ≥ 20 por regla) */
function mcGammaIntradia(G) {
  let h = '<div class="sect"><h2>Gamma intradía</h2><span class="more">avisos de ES y NQ con velas de 5 min · MFE y MAE a 15, 30 y 60 min</span></div>';
  if (!G || !G.por_regla) return h + `<div class="card"><div class="empty" style="height:90px">SIN DATO · data/gamma_intradia.json</div></div>`;
  const rs = Object.values(G.por_regla), hz = G.horizontes_min || [15, 30, 60], em = (v) => (v == null ? '—' : num(v, 2) + '×');
  h += `<div class="card pad0 scroll"><table class="t stack"><thead><tr><th style="text-align:left">Regla</th><th>Avisos</th>${hz.map((x) => `<th>${x} min · n</th><th>${x} min · MFE / MAE (mediana)</th>`).join('')}<th>Estado</th></tr></thead><tbody>`
    + rs.map((r) => `<tr class="${r.fiable ? '' : 'poca'}"><td data-label="Regla" style="text-align:left"><b>${esc(r.nombre)}</b></td><td data-label="Avisos" class="mono">${esc(String(r.n_senales))}</td>`
      + hz.map((x) => { const d = r.horizontes[String(x)] || {}; return `<td data-label="${x} min · n" class="mono">${esc(String(d.n || 0))}</td><td data-label="${x} min · MFE / MAE">${d.mfe_mediana_pts == null ? '—' : `${num(d.mfe_mediana_pts, 1)} / ${num(d.mae_mediana_pts, 1)} pts <small>(${em(d.mfe_mediana_em)} / ${em(d.mae_mediana_em)} EM)</small>`}</td>`; }).join('')
      + `<td data-label="Estado"><span class="ck ${r.fiable ? 'ok' : 'par'}">${r.fiable ? 'EVALUABLE' : 'CONGELADA · n < ' + esc(String(G.min_n))}</span></td></tr>`).join('')
    + `</tbody></table><div class="note" style="padding:8px 16px 12px">${esc(G.metodo || '')} ${G.n_senales ? '' : 'Todavía no hay ningún aviso enviado: el registro empieza con el primero.'}</div>`
    + (G.ultimas && G.ultimas.length ? `<div class="note" style="padding:0 16px 12px"><b>Últimos avisos:</b> ${G.ultimas.slice(0, 5).map((u) => `${esc(fdy(u.fecha_et))} ${esc(u.indice)} · ${esc((G.por_regla[u.regla] || {}).nombre || u.regla)} (${esc(String(u.precio_ref))}, gamma ${esc(u.regimen)})`).join(' · ')}</div>` : '')
    + footIn('engine/gamma_intradia.py (data/gamma_intradia_senales.csv y data/gamma_intradia_resultados.csv, solo añadir)', G.generado_utc && G.generado_utc.slice(0, 10), null, 'velas de 5 min de Yahoo Finance') + '</div>';
  return h;
}
const MC_TIPOS = [['tesis', 'Tesis por activo (cambios)'], ['fed', 'Alertas Fed'], ['skew', 'SKEW alto con ≥ 2 confirmaciones'], ['regimen', 'Régimen (cambios)'],
  ['liquidez', 'Liquidez (cambios de etiqueta)'], ['consumo', 'Tesis de consumo (cambios)'], ['petroleo', 'Tesis de petróleo (cambios)'], ['cruce_sma200_ratio', 'Cruce SMA200 del ratio de consumo (válido tras 5 cierres)'], ['divergencia_ratio', 'Divergencia SPY / consumo amplio'], ['reaccion', 'Reacción a eventos (solo registro)']];
const mcPct = (v) => (v == null ? '—' : num(v, 1) + ' %');
const mcRet = (v, u) => (v == null ? '—' : `${v > 0 ? '+' : ''}${num(v, u === 'pb' ? 1 : 2)} ${u === 'pb' ? 'pb' : '%'}`);
const mcCls = (v) => (v == null ? '' : v > 0 ? 'up' : v < 0 ? 'down' : 'flat');
const mcChip = (h) => {
  if (!h) return '<span class="ck sd">—</span>';
  if (h.estado === 'PENDIENTE') return '<span class="ck sd" title="Aún no hay cierre a ese horizonte; nunca se estima">pendiente</span>';
  const c = h.estado === 'ACIERTO' ? 'ok' : h.estado === 'FALLO' ? 'no' : 'par';
  return `<span class="ck ${c}" title="${esc(h.estado)}">${esc(h.estado.toLowerCase())}</span> <span class="mono ${mcCls(h.ret)}" style="font-size:11px">${mcRet(h.ret, h.unidad)}</span>`;
};

function mcTabla(res, titulo, sub) {
  const filas = MC_TIPOS.filter(([t]) => res && res[t]);
  let h = `<div class="sect"><h2>${esc(titulo)}</h2><span class="more">${esc(sub)}</span></div>`;
  if (!filas.length) return h + '<div class="card"><div class="empty" style="height:100px">SIN SEÑALES EN ESTE GRUPO TODAVÍA</div></div>';
  h += `<div class="card pad0 scroll"><table class="t stack"><thead><tr><th style="text-align:left">Tipo de señal</th><th>Señales</th><th>Medidas a T+${esc(MC.h)}</th><th>% acierto</th><th>Azar (tasa base)</th><th>Dif. (pp)</th><th>Retorno medio</th><th>Peor caso</th><th>Peor adverso</th><th style="text-align:left">Fiabilidad</th></tr></thead><tbody>`;
  h += filas.map(([t, nom]) => {
    const d = res[t], b = d.horizontes[MC.h];
    if (!b) return `<tr><td data-label="Tipo de señal" style="text-align:left"><b>${esc(nom)}</b></td><td data-label="Señales">${d.n_senales}</td><td colspan="8" style="text-align:left;color:var(--dim)">este tipo se mide a T+${Object.keys(d.horizontes).join(' y T+')} sesiones: cambia el horizonte arriba</td></tr>`;
    const punt = d.n_senales - d.no_puntuables;
    if (t === 'reaccion' || !punt) {
      return `<tr><td data-label="Tipo" style="text-align:left"><b>${esc(nom)}</b></td><td data-label="Señales" class="mono">${d.n_senales}</td><td colspan="8" data-label="Medición" style="text-align:left;color:var(--dim)">${t === 'reaccion' ? 'solo registro: reglas v3 congeladas, no se puntúa' : 'ninguna con dirección esperada (no puntuables: ' + d.no_puntuables + ')'}</td></tr>`;
    }
    const u = t === 'fed' ? 'pb' : '%';
    const corto = b.n < 20;
    return `<tr class="${corto ? 'poca' : ''}"><td data-label="Tipo" style="text-align:left"><b>${esc(nom)}</b><small>${d.no_puntuables ? d.no_puntuables + ' sin dirección (no puntuables)' : ''}</small></td><td data-label="Señales" class="mono">${d.n_senales}</td>
      <td data-label="Medidas" class="mono">${b.n}${b.pendientes ? `<small>${b.pendientes} pendientes</small>` : ''}</td>
      <td data-label="% acierto">${b.n ? `${mcPct(b.acierto_pct)}<small>${b.aciertos} acierto · ${b.fallos} fallo${t === 'skew' ? '' : ' · ' + b.neutrales + ' neutral'}</small>${t === 'skew' ? `<small>caída ≥ 1σ: ${b.comp_caida} · VIX ≥ +20 %: ${b.comp_vix}</small>` : ''}` : '—'}</td>
      <td data-label="Azar">${mcPct(b.base_media_pct)}</td><td data-label="Dif. (pp)" class="${mcCls(b.diferencia_pp)}">${b.diferencia_pp == null ? '—' : (b.diferencia_pp > 0 ? '+' : '') + num(b.diferencia_pp, 1)}</td>
      <td data-label="Retorno medio" title="${t === 'skew' ? 'Retorno del S&P 500 a ese horizonte (no direccional)' : 'Retorno en la dirección esperada'}" class="${mcCls(b.ret_medio)}">${mcRet(b.ret_medio, u)}</td><td data-label="Peor caso" class="${mcCls(b.peor_ret)}">${mcRet(b.peor_ret, u)}</td><td data-label="Peor adverso" title="${t === 'skew' ? 'Mayor caída máxima intrahorizonte del S&P 500' : 'Peor retorno entre la referencia y el horizonte, en la dirección esperada'}" class="${mcCls(b.peor_mae)}">${mcRet(b.peor_mae, u)}</td>
      <td data-label="Fiabilidad" style="text-align:left;white-space:normal;min-width:150px">${b.n === 0 ? '<span class="ck sd">sin medidas</span>' : corto ? '<span class="ck par" title="Con menos de 20 señales medidas la diferencia con el azar no se distingue del ruido">muestra insuficiente (n &lt; 20)</span>' : '<span class="ck ok">n ≥ 20</span>'}</td></tr>`;
  }).join('');
  return h + '</tbody></table></div>';
}

function mcHtml(M) {
  const R = M.resumen || {}, viv = R.vivo, bf = R.backfill;
  const cuenta = (r) => (r ? Object.values(r).reduce((a, d) => a + d.n_senales, 0) : 0);
  const nv = cuenta(viv), nb = cuenta(bf);
  const btn = (h) => `<button class="fbtn ${MC.h === h ? 'on' : ''}" data-h="${h}">T+${h} sesiones</button>`;
  let h = essential(`${nv} señales vivas y ${nb} reconstruidas del pasado; ${M.n_anuladas || 0} anuladas.`,
    'Hecho: cada señal se midió (criterio v2) con cierres oficiales a 1, 5 y 20 sesiones frente al cierre anterior a su emisión; «neutral» = movimiento menor que 0,25 σ del activo a ese horizonte. Interpretación: nada se concluye aquí; si el % de acierto no supera claramente la tasa base (lo que se acierta por azar en ese activo y horizonte), la señal no aporta información medible.',
    `Con menos de ${M.min_n || 20} señales medidas el grupo se marca «muestra insuficiente». Las vivas y las reconstruidas no se mezclan.`, 'Cómo leerlo');
  h += `<div class="banner amber" style="margin:0 0 14px;border-radius:6px"><b>Criterio v2 (${esc((M.criterio && M.criterio.desde) || '')}).</b> ${esc(M.cambio_criterio || '')}</div>`;
  h += `<div class="filters" style="margin:0 0 6px">${['1', '5', '20', '60'].map(btn).join('')}</div>`;
  h += mcTabla(viv, 'Señales vivas', 'emitidas por el sistema en su momento · el marcador que cuenta');
  h += mcTabla(bf, 'Señales reconstruidas (backfill)', 'pasado reconstruido desde el histórico de contexto y los CSV de memoria · no es lo mismo que acertar en vivo');
  h += '<div class="sect"><h2>Últimas señales</h2><span class="more">más recientes primero · hasta 60</span></div><div class="card pad0 scroll"><table class="t stack"><thead><tr><th>Fecha (UTC)</th><th style="text-align:left">Tipo</th><th>Activo</th><th>Dirección</th><th style="text-align:left">Qué la disparó</th><th>Origen</th><th>T+1</th><th>T+5</th><th>T+20</th><th>T+60</th></tr></thead><tbody>';
  h += (M.senales || []).slice(0, 60).map((s) => {
    const hz = s.horizontes;
    const cel = (k) => (typeof hz === 'string' ? `<span class="ck sd">${esc(hz.toLowerCase())}</span>` : mcChip(hz[k]));
    return `<tr><td data-label="Fecha" class="mono">${esc(s.fecha_utc)}</td><td data-label="Tipo" style="text-align:left">${esc(s.tipo)}</td><td data-label="Activo">${esc(s.activo)}</td><td data-label="Dirección"><span class="tag ${s.direccion === 'ALCISTA' ? 'alc' : s.direccion === 'BAJISTA' ? 'baj' : 'sin'}">${esc(s.direccion.toLowerCase())}</span></td>
      <td data-label="Disparo" style="text-align:left;white-space:normal;max-width:380px">${esc(s.valor)}${s.criterio ? `<small>${esc(s.criterio)}</small>` : ''}${s.nota ? `<small>${esc(s.nota)}</small>` : ''}</td><td data-label="Origen"><span class="ck ${s.origen === 'vivo' ? 'ok' : 'sd'}">${esc(s.origen)}</span></td>
      <td data-label="T+1">${cel('1')}</td><td data-label="T+5">${cel('5')}</td><td data-label="T+20">${cel('20')}</td><td data-label="T+60">${cel('60')}</td></tr>`;
  }).join('') || '<tr><td colspan="10" style="text-align:left;color:var(--dim)">Sin señales registradas.</td></tr>';
  h += `</tbody></table>${footIn('engine/marcador.py (data/marcador_senales.csv y data/marcador_resultados.csv, solo añadir)', M.generado_utc && M.generado_utc.slice(0, 10), null, 'cierres de Yahoo Finance (precios) y FRED (2Y)')}</div>`;
  h += mcGammaIntradia(MC.gi);
  h += `<div class="sect"><h2>Reglas del marcador</h2><span class="more">fijas; no cambian según el resultado</span></div><div class="card"><details class="qa" open><summary>Criterios v2: qué cuenta como señal, qué se espera y cómo se mide</summary><p style="white-space:pre-line">${esc(M.reglas || '')}</p></details></div>`;
  h += `<div class="note">${esc(M.nota || '')} Una señal sin cierres suficientes queda PENDIENTE y no se estima. Las correcciones no editan filas: se añade una fila ANULADA.</div>`;
  return h;
}

function pageMarcador() {
  const h = head('Análisis', 'Marcador de señales', 'Cuántas veces acertó cada tipo de señal del sistema (tesis, Fed, SKEW, régimen, liquidez) a 1, 5 y 20 sesiones, comparado con lo que se acierta por azar en ese activo y horizonte. Sin conclusiones automáticas.',
    '<span class="tag sin">REGISTRO SOLO-AÑADIR</span> sin IA en ejecución') + '<div id="mc-root"><div class="empty" style="height:160px">CARGANDO EL MARCADOR…</div></div>';
  MOUNT.push(async () => {
    const root = document.getElementById('mc-root');
    if (!root) return;
    try {
      const r = await fetch('data/marcador.json?v=' + Date.now(), { cache: 'no-store' });
      if (!r.ok) throw new Error(r.status);
      MC.datos = await r.json();
    } catch (e) { root.innerHTML = noData('Marcador de señales (data/marcador.json)'); return; }
    try { const g = await fetch('data/gamma_intradia.json?v=' + Date.now(), { cache: 'no-store' }); MC.gi = g.ok ? await g.json() : null; } catch (e) { MC.gi = null; }
    const pintar = () => { if (document.getElementById('mc-root') === root) root.innerHTML = mcHtml(MC.datos); };
    pintar();
    root.addEventListener('click', (e) => { const b = e.target.closest('[data-h]'); if (b) { MC.h = b.dataset.h; pintar(); } });
  });
  return h;
}

Object.assign(window.EXTRA_PAGES, { marcador: pageMarcador });
