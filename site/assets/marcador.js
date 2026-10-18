/* NEXORA TERMINAL · Marcador de aciertos de señales (#/marcador).
   Lee site/data/marcador.json, que escribe engine/marcador.py (sin IA; registro solo-añadir en data/marcador_senales.csv y
   data/marcador_resultados.csv). La página solo muestra: no calcula ni concluye nada. Todo texto dinámico pasa por esc(). */
'use strict';

const MC = { h: '5', datos: null };
const MC_TIPOS = [['tesis', 'Tesis por activo (cambios)'], ['fed', 'Alertas Fed'], ['skew', 'SKEW alto con ≥ 2 confirmaciones'], ['regimen', 'Régimen (cambios)'],
  ['liquidez', 'Liquidez (cambios de etiqueta)'], ['reaccion', 'Reacción a eventos (solo registro)']];
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
    const punt = d.n_senales - d.no_puntuables;
    if (t === 'reaccion' || !punt) {
      return `<tr><td data-label="Tipo" style="text-align:left"><b>${esc(nom)}</b></td><td data-label="Señales" class="mono">${d.n_senales}</td><td colspan="8" data-label="Medición" style="text-align:left;color:var(--dim)">${t === 'reaccion' ? 'solo registro: reglas v3 congeladas, no se puntúa' : 'ninguna con dirección esperada (no puntuables: ' + d.no_puntuables + ')'}</td></tr>`;
    }
    const u = t === 'fed' ? 'pb' : '%';
    const corto = b.n < 20;
    return `<tr class="${corto ? 'poca' : ''}"><td data-label="Tipo" style="text-align:left"><b>${esc(nom)}</b><small>${d.no_puntuables ? d.no_puntuables + ' sin dirección (no puntuables)' : ''}</small></td><td data-label="Señales" class="mono">${d.n_senales}</td>
      <td data-label="Medidas" class="mono">${b.n}${b.pendientes ? `<small>${b.pendientes} pendientes</small>` : ''}</td>
      <td data-label="% acierto">${b.n ? `${mcPct(b.acierto_pct)}<small>${b.aciertos} acierto · ${b.fallos} fallo · ${b.neutrales} neutral</small>` : '—'}</td>
      <td data-label="Azar">${mcPct(b.base_media_pct)}</td><td data-label="Dif. (pp)" class="${mcCls(b.diferencia_pp)}">${b.diferencia_pp == null ? '—' : (b.diferencia_pp > 0 ? '+' : '') + num(b.diferencia_pp, 1)}</td>
      <td data-label="Retorno medio" class="${mcCls(b.ret_medio)}">${mcRet(b.ret_medio, u)}</td><td data-label="Peor caso" class="${mcCls(b.peor_ret)}">${mcRet(b.peor_ret, u)}</td><td data-label="Peor adverso" class="${mcCls(b.peor_mae)}">${mcRet(b.peor_mae, u)}</td>
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
    'Hecho: cada señal se midió con cierres oficiales a 1, 5 y 20 sesiones frente al cierre anterior a su emisión. Interpretación: nada se concluye aquí; si el % de acierto no supera claramente la tasa base (lo que se acierta por azar en ese activo y horizonte), la señal no aporta información medible.',
    `Con menos de ${M.min_n || 20} señales medidas el grupo se marca «muestra insuficiente». Las vivas y las reconstruidas no se mezclan.`, 'Cómo leerlo');
  h += `<div class="filters" style="margin:0 0 6px">${['1', '5', '20'].map(btn).join('')}</div>`;
  h += mcTabla(viv, 'Señales vivas', 'emitidas por el sistema en su momento · el marcador que cuenta');
  h += mcTabla(bf, 'Señales reconstruidas (backfill)', 'pasado reconstruido desde el histórico de contexto y los CSV de memoria · no es lo mismo que acertar en vivo');
  h += '<div class="sect"><h2>Últimas señales</h2><span class="more">más recientes primero · hasta 60</span></div><div class="card pad0 scroll"><table class="t stack"><thead><tr><th>Fecha (UTC)</th><th style="text-align:left">Tipo</th><th>Activo</th><th>Dirección</th><th style="text-align:left">Qué la disparó</th><th>Origen</th><th>T+1</th><th>T+5</th><th>T+20</th></tr></thead><tbody>';
  h += (M.senales || []).slice(0, 60).map((s) => {
    const hz = s.horizontes;
    const cel = (k) => (typeof hz === 'string' ? `<span class="ck sd">${esc(hz.toLowerCase())}</span>` : mcChip(hz[k]));
    return `<tr><td data-label="Fecha" class="mono">${esc(s.fecha_utc)}</td><td data-label="Tipo" style="text-align:left">${esc(s.tipo)}</td><td data-label="Activo">${esc(s.activo)}</td><td data-label="Dirección"><span class="tag ${s.direccion === 'ALCISTA' ? 'alc' : s.direccion === 'BAJISTA' ? 'baj' : 'sin'}">${esc(s.direccion.toLowerCase())}</span></td>
      <td data-label="Disparo" style="text-align:left;white-space:normal;max-width:380px">${esc(s.valor)}${s.nota ? `<small>${esc(s.nota)}</small>` : ''}</td><td data-label="Origen"><span class="ck ${s.origen === 'vivo' ? 'ok' : 'sd'}">${esc(s.origen)}</span></td>
      <td data-label="T+1">${cel('1')}</td><td data-label="T+5">${cel('5')}</td><td data-label="T+20">${cel('20')}</td></tr>`;
  }).join('') || '<tr><td colspan="9" style="text-align:left;color:var(--dim)">Sin señales registradas.</td></tr>';
  h += `</tbody></table>${footIn('engine/marcador.py (data/marcador_senales.csv y data/marcador_resultados.csv, solo añadir)', M.generado_utc && M.generado_utc.slice(0, 10), null, 'cierres de Yahoo Finance (precios) y FRED (2Y)')}</div>`;
  h += `<div class="sect"><h2>Reglas del marcador</h2><span class="more">fijas; no cambian según el resultado</span></div><div class="card"><details class="qa" open><summary>Qué cuenta como señal, qué dirección se espera y cómo se mide</summary><p style="white-space:pre-line">${esc(M.reglas || '')}</p></details></div>`;
  h += `<div class="note">${esc(M.nota || '')} Una señal sin cierres suficientes queda PENDIENTE y no se estima. Las correcciones no editan filas: se añade una fila ANULADA. Banda de «neutral»: ±${esc(M.banda_neutral ? M.banda_neutral.pct : 0.1)} % (±${esc(M.banda_neutral ? M.banda_neutral.pb : 1)} pb en el 2Y).</div>`;
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
    const pintar = () => { if (document.getElementById('mc-root') === root) root.innerHTML = mcHtml(MC.datos); };
    pintar();
    root.addEventListener('click', (e) => { const b = e.target.closest('[data-h]'); if (b) { MC.h = b.dataset.h; pintar(); } });
  });
  return h;
}

Object.assign(window.EXTRA_PAGES, { marcador: pageMarcador });
