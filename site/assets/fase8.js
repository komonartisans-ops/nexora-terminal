/* NEXORA TERMINAL · fase 8: reacción a eventos (IPC, NFP, PCE, FOMC). Se carga después de fase7.js y reutiliza sus helpers.
   Todo texto dinámico pasa por esc(). Sin dato = SIN DATO. */
'use strict';

const CLASE_COL = { 'FED MÁS DURA': '#C8463D', 'FED MÁS SUAVE': '#2FA36B', REFUGIO: '#9B87C9', 'EMPINAMIENTO POR PLAZO LARGO': '#C8A24A', 'SIN REACCIÓN': '#8A93A0', 'MIXTA (sin regla)': '#6C8EBF',
  'REFUGIO / RIESGO': '#9B87C9', 'ALIVIO DESHECHO': '#D9843B', 'INVERSIÓN · NQ cae': '#E0607E', 'INVERSIÓN · NQ sube': '#3FB5A8', 'SORPRESA DESHECHA': '#4FA3C7', 'SE CONFIRMA': '#8A93A0', PARCIAL: '#C8A24A', 'SIN BASE': '#5b6470', 'SIN DATO': '#5b6470' };
const chipClase = (c) => (c ? `<span class="chip" style="border:1px solid ${CLASE_COL[c] || '#3a4250'};color:${CLASE_COL[c] || 'var(--muted)'};white-space:nowrap">${esc(c)}</span>` : '<span class="pill flat">—</span>');
const dv = (v, d, u) => (v == null ? '<span class="sd-val" style="font-size:10px">SIN DATO</span>' : `<span class="${v > 0 ? '' : ''}">${sg(v, d)}${u}</span>`);
const FASES_ORD = ['T-5', 'T+5', 'T+15', 'T+30', 'T+60', 'T+120', 'CIERRE', 'T+1'];
const FASE_ROT = { CIERRE: 'Cierre', 'T+1': 'T+1 (10:00 ET)' };
const pctDev = (v) => (v == null ? '<span class="sd-val" style="font-size:10px">—</span>' : `${num(v, 0)} %`);
/* celda de «Qué fue al cierre» y similares: etiqueta propia para que en móvil (tabla apilada) siga viéndose */
const lab = (t) => `data-label="${esc(t)}"`;

function pageEventos() {
  const R = D.reacciones;
  const stamp = `Actualizado: ${R && R.generado_utc ? esc(R.generado_utc) : 'SIN DATO'} · reglas v${R ? esc(R.version_reglas) : ''} <span class="tag sin" style="margin-left:6px">CRITERIO NEXORA</span>`;
  let h = head('Análisis', 'Reacción a eventos', 'Qué hacen el 2Y, el 10Y, el dólar, el oro, el Nasdaq y el BTC tras cada dato de importancia alta de la agenda oficial (IPC, PPI, empleo, PCE, PIB, FOMC, actas, ISM), y cómo lo clasifica una regla fija y publicada. Datos de Yahoo Finance con barras de 5 minutos; fechas y horas del calendario oficial.', stamp);
  h += fallo('reacciones');
  if (!R || !R.eventos || !R.eventos.length) return h + noData('Yahoo Finance (5 min) + calendario oficial');
  const E = R.eventos;
  const u = E.find((e) => e.id === R.ultimo) || E[0];
  const f = (n) => u.fases.find((x) => x.fase === n);
  const f5 = f('T+5'), fc = f('CIERRE');
  const cad = (x) => (x ? `2Y ${sg(x.d_y2_pb, 1)} pb · 10Y ${sg(x.d_y10_pb, 1)} pb · DXY ${sg(x.d_dxy_pct, 2)} % · oro ${sg(x.d_oro_pct, 2)} % · NQ ${sg(x.d_nq_pct, 2)} % · BTC ${sg(x.d_btc_pct, 2)} %` : 'SIN DATO');
  const so = u.sorpresa;
  const GIRO_FASES = ['T+60', 'T+120', 'CIERRE', 'T+1'];
  h += essential(
    `${esc(u.evento)} · ${esc(fdy(u.fecha))} ${esc(u.hora_ny)} ET${u.reconstruido ? ' (reconstruido con barras de 5 min)' : ''}: en T+5 la lectura es <b style="color:var(--text)">${esc(u.clase_t5 || 'SIN DATO')}</b>. ${esc(cad(f5))} (frente a T-5).`,
    `${GIRO_FASES.map((n) => { const x = f(n); const g = x && x.giro; return `${n === 'CIERRE' ? 'Cierre' : n}: <b style="color:var(--text)">${g && g.clase ? esc(g.clase) : 'sin registro'}</b>${g && g.dev_y2_pct != null ? ` (2Y ${num(g.dev_y2_pct, 0)} % · 10Y ${num(g.dev_y10_pct, 0)} %)` : ''}`; }).join(' · ')}. ${u.giro_en && u.giro_en.length ? `Alerta de giro en ${esc(u.giro_en.join(' y '))}.` : 'Sin giro: ninguna fase deshace ≥ 60 % del movimiento de T+5.'} ${fc ? `Al cierre la lectura de la regla v1 es <b style="color:var(--text)">${esc(fc.clasificacion)}</b>.` : 'El cierre aún no está registrado.'} <i>Devolución = % del movimiento de T+5 ya deshecho.</i>`,
    so ? (so.modo === 'z' ? `Salto del 2Y en T+5 de ${sg(so.pb, 1)} pb = ${sg(so.z, 2)} σ frente a ${so.n} eventos ${esc(u.tipo)} previos.` : `Salto del 2Y en T+5 de ${sg(so.pb, 1)} pb. <i>${esc(so.nota)}</i>`) : 'Salto del 2Y en T+5: SIN DATO.',
    'Sorpresa');

  /* secuencia de fases del último evento */
  h += `<div class="sect"><h2>Último evento · secuencia de fases</h2><span class="more">todos los movimientos frente al precio de T-5 (5 min antes de la publicación)</span></div>`;
  h += `<div class="card"><div class="note" style="margin:0 0 10px">${esc(u.evento)} · ${esc(fdy(u.fecha))} · ${esc(u.hora_ny)} hora de Nueva York ${u.reconstruido ? '<span class="tag sd">RECONSTRUIDO</span>' : '<span class="tag sin">EN VIVO</span>'}${String(u.tipo).includes('+') ? ' <span class="tag sd" title="varios datos de importancia alta a la misma hora: se registra un único evento">COMBINADO: ' + esc(u.tipo.replace(/\+/g, ' + ')) + '</span>' : ''}</div>
    <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px">${FASES_ORD.filter((n) => n !== 'T-5').map((n) => { const x = f(n); return `<div style="flex:1 1 110px;min-width:105px"><div class="note" style="margin:0 0 3px">${esc(FASE_ROT[n] || n)}</div>${chipClase(x ? x.clasificacion : null)}${x && x.giro && x.giro.clase ? `<div style="margin-top:4px">${chipClase(x.giro.clase)}</div>` : ''}</div>`; }).join('')}</div></div>`;
  h += '<div class="card pad0 scroll" style="margin-top:10px"><table class="t"><thead><tr><th>Fase</th><th>Clase</th><th>2Y pb</th><th>10Y pb</th><th>Dev. 2Y</th><th>Dev. 10Y</th><th>Giro (v3)</th><th>DXY %</th><th>Oro %</th><th>NQ %</th><th>ES %</th><th>BTC %</th><th>Origen</th></tr></thead><tbody>';
  h += FASES_ORD.map((n) => {
    const x = f(n);
    if (!x) return `<tr><td><b>${n}</b></td><td colspan="12" style="text-align:left;color:var(--dim)">SIN REGISTRO todavía</td></tr>`;
    if (n === 'T-5') return `<tr><td><b>${n}</b></td><td colspan="11" style="text-align:left;color:var(--dim)">precio base (cierre de la barra de 5 min previa a la publicación)</td><td>${esc(x.origen)}</td></tr>`;
    const g = x.giro || {};
    return `<tr><td><b>${esc(FASE_ROT[n] || n)}</b></td><td style="text-align:left">${chipClase(x.clasificacion)}</td><td>${dv(x.d_y2_pb, 1, '')}</td><td>${dv(x.d_y10_pb, 1, '')}${x.y10_fuente && x.y10_fuente !== '^TNX' ? ` <small title="${esc(x.y10_fuente)}" style="color:var(--amber)">ZN</small>` : ''}</td>
      <td>${n === 'T+5' ? '—' : pctDev(g.dev_y2_pct)}</td><td>${n === 'T+5' ? '—' : (g.y10_base === false ? '<small title="el 10Y no supera su umbral en T+5: no cuenta en la devolución">10Y sin base</small>' : pctDev(g.dev_y10_pct))}</td><td style="text-align:left" ${g.nota ? `title="${esc(g.nota)}"` : ''}>${g.clase ? chipClase(g.clase) : '<span class="pill flat">—</span>'}${g.debil ? ' <small>base débil</small>' : ''}${x.contaminada ? ` <small style="color:var(--amber)" title="${esc((x.contaminada_por || []).join(', '))} se publica entre el dato y esta fase">contaminada</small>` : ''}</td>
      <td>${dv(x.d_dxy_pct, 2, '')}</td><td>${dv(x.d_oro_pct, 2, '')}</td><td>${dv(x.d_nq_pct, 2, '')}</td><td>${dv(x.d_es_pct, 2, '')}</td><td>${dv(x.d_btc_pct, 2, '')}</td><td><small>${esc(x.origen)}</small></td></tr>`;
  }).join('');
  h += `</tbody></table>${footIn('Yahoo Finance (ZT=F calibrado, ^TNX, DX-Y.NYB, GC=F, NQ=F, ES=F, BTC-USD)', u.fecha, null, 'barras de 5 min; ZN = 10Y inferido de ZN=F porque ^TNX no cotiza tras las 15:00 ET')}</div>`;
  const umb = f5 && f5.umbrales ? f5.umbrales : null;
  if (umb) h += `<div class="note">Umbrales usados en T+5 (${esc(f5.umbral_origen)}): 2Y ±${num(umb.y2, 1)} pb · 10Y ±${num(umb.y10, 1)} pb · DXY ±${num(umb.dxy, 2)} % · NQ ±${num(umb.nq, 2)} %. Pico del DXY en la ventana: ${f5.dxy_pico_pct != null ? sg(f5.dxy_pico_pct, 2) + ' %' : 'SIN DATO'}.</div>`;
  h += `<div class="note"><b>10Y real (FRED DFII10):</b> ${u.real10 ? `${num(u.real10.valor, 2)} % · cambio de todo el día ${sg(u.real10.d_pb, 1)} pb. Añadido al día siguiente (${esc(u.real10.origen)}); no es el cambio de la ventana del evento.` : 'se añade el día siguiente al evento (FRED publica el dato con un día de retraso): SIN DATO todavía.'}</div>`;

  /* tabla histórica */
  h += `<div class="sect"><h2>Histórico · qué clasificación de T+5 terminó imponiéndose</h2><span class="more">n = ${R.n_con_cierre} eventos con T+5 y cierre registrados (últimos 60 días): muestra pequeña, lectura orientativa</span></div>`;
  const T = R.tabla_t5_vs_cierre || {};
  h += '<div class="card pad0 scroll"><table class="t stack"><thead><tr><th>Clase en T+5</th><th>n</th><th>Igual al cierre</th><th>%</th><th>Qué fue al cierre</th></tr></thead><tbody>';
  h += Object.keys(T).length ? Object.entries(T).map(([c, t]) => `<tr><td style="text-align:left">${chipClase(c)}</td><td ${lab('n')}>${t.n}</td><td ${lab('Igual al cierre')}>${t.igual_cierre}/${t.n}</td><td ${lab('%')}><b>${num(100 * t.igual_cierre / t.n, 0)} %</b></td><td ${lab('Qué fue al cierre')} style="text-align:left;white-space:normal">${Object.entries(t.cierre).map(([k, v]) => `${esc(k)} ×${v}`).join(' · ')}</td></tr>`).join('') : '<tr><td colspan="5" style="text-align:left;color:var(--dim)">SIN DATO</td></tr>';
  h += `</tbody></table>${footIn('data/reacciones_eventos.csv · cálculo NEXORA', R.generado_utc && R.generado_utc.slice(0, 10), null, 'frecuencias con n visible; no es una probabilidad')}</div>`;
  h += '<div class="card pad0 scroll" style="margin-top:10px"><table class="t"><thead><tr><th>Evento</th><th>Fecha</th><th>T+5</th><th>T+60</th><th>T+120</th><th>Cierre</th><th>T+1</th><th>Giro v3 (T+60 / T+120 / cierre / T+1)</th><th>2Y T+5 (pb)</th><th>Origen</th></tr></thead><tbody>';
  h += E.map((e) => {
    const c = (n) => { const x = e.fases.find((y) => y.fase === n); return x ? chipClase(x.clasificacion) : '<span class="pill flat">—</span>'; };
    return `<tr><td style="text-align:left;font-family:var(--sans)">${esc(e.tipo)}</td><td>${esc(fdy(e.fecha))}</td><td style="text-align:left">${c('T+5')}</td><td style="text-align:left">${c('T+60')}</td><td style="text-align:left">${c('T+120')}</td><td style="text-align:left">${c('CIERRE')}</td><td style="text-align:left">${c('T+1')}</td>
      <td style="text-align:left;white-space:normal">${['T+60', 'T+120', 'CIERRE', 'T+1'].map((n) => { const k = (e.giro_fases || {})[n]; const fx = e.fases.find((y) => y.fase === n); return `<div><small style="margin:0">${esc(n)}</small> ${k ? chipClase(k) : '<span class="pill flat">—</span>'}${fx && fx.giro && fx.giro.debil ? ' <small>base débil</small>' : ''}${fx && fx.contaminada ? ' <small style="color:var(--amber)">contaminada</small>' : ''}</div>`; }).join('')}${e.diseno ? ' <span class="tag sd">DISEÑO</span>' : ''}</td><td>${e.sorpresa ? sg(e.sorpresa.pb, 1) + (e.sorpresa.modo === 'z' ? ` <small>(${sg(e.sorpresa.z, 1)} σ)</small>` : '') : '—'}</td><td><small>${e.reconstruido ? 'reconstruido' : 'en vivo'}</small></td></tr>`;
  }).join('');
  h += `</tbody></table>${footIn('Yahoo Finance + calendario oficial · registro solo-añadir', R.generado_utc && R.generado_utc.slice(0, 10), null, 'los reconstruidos usan barras de 5 min de Yahoo (últimos 60 días)')}</div>`;

  /* regla de giro v2: validación */
  const VG = R.validacion_giro;
  if (VG) {
    const orden = ['REFUGIO / RIESGO', 'ALIVIO DESHECHO', 'SORPRESA DESHECHA', 'INVERSIÓN · NQ cae', 'INVERSIÓN · NQ sube', 'SE CONFIRMA', 'PARCIAL', 'SIN BASE', 'SIN DATO'];
    h += `<div class="sect"><h2>Regla de giro v3 · resultado en los otros ${VG.n_otros} eventos</h2><span class="more"><span class="tag sd">${esc(VG.estado)}</span></span></div>
      <div class="card pad0 scroll"><table class="t"><thead><tr><th>Fase</th>${orden.map((c) => `<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${['T+60', 'T+120', 'CIERRE', 'T+1'].map((n) => { const d = (VG.por_fase || {})[n] || {}; return `<tr><td><b>${esc(FASE_ROT[n] || n)}</b></td>${orden.map((c) => `<td>${d[c] ? `<span title="${esc(d[c].eventos.join(', '))}">${d[c].n}</span>` : '·'}</td>`).join('')}</tr>`; }).join('')}</tbody></table>
      ${footIn('data/reacciones_eventos.csv · cálculo NEXORA', R.generado_utc && R.generado_utc.slice(0, 10), null, 'n = eventos; pase el cursor sobre la cifra para ver cuáles')}</div>
      <div class="note">${esc(VG.nota)} El evento de diseño (${esc(VG.evento_diseno)}) está en la tabla de arriba, marcado «DISEÑO», y no entra en este recuento.</div>`;
  }

  /* reglas */
  const RG = R.reglas || {};
  h += `<div class="sect"><h2>Reglas de clasificación</h2><span class="more">CRITERIO NEXORA · publicadas antes de ver los resultados</span></div>
    <details class="qa card" open><summary>Clases y umbrales</summary>
      <table class="t" style="margin-top:8px"><thead><tr><th>Clase</th><th>Regla</th></tr></thead><tbody>${(RG.clases || []).map((c) => `<tr><td style="text-align:left">${chipClase(c.clase)}</td><td style="text-align:left;white-space:normal">${esc(c.regla)}</td></tr>`).join('')}</tbody></table>
      <p class="note">${esc(RG.precedencia || '')} ${esc(RG.movimiento || '')}</p>
      <p class="note">${esc(RG.umbral || '')} Suelos: ${Object.entries(RG.suelos || {}).map(([k, v]) => `${esc(k)} ${v}`).join(' · ')}.</p>
      <p class="note">${esc(RG.giro || '')} ${esc(RG.criterio || '')}</p></details>
    <details class="qa card" open><summary>Regla de giro v3 (medida contra T+5) · CONGELADAS · v3</summary>
      <p class="note"><b>${esc(RG.congelacion || '')}</b> Resultado todavía pendiente de validar con eventos nuevos.</p>
      <table class="t" style="margin-top:8px"><thead><tr><th>Clase</th><th>Regla</th></tr></thead><tbody>${(RG.giro_clases || []).map((c) => `<tr><td style="text-align:left">${chipClase(c.clase)}</td><td style="text-align:left;white-space:normal">${esc(c.regla)}</td></tr>`).join('')}</tbody></table>
      <p class="note">Base: el 2Y supera su umbral en T+5, al alza o a la baja; el 10Y solo cuenta en la devolución si su movimiento en T+5 supera su umbral. Devolución = (movimiento en T+5 − movimiento en la fase) / movimiento en T+5, sobre 2Y y 10Y, ambos frente a T-5; se mide contra el signo del movimiento inicial. Se evalúa en T+60, T+120, cierre y T+1 (día siguiente 10:00 ET).</p></details>
    <details class="qa card"><summary>De dónde sale cada serie</summary><table class="t" style="margin-top:8px"><tbody>${Object.entries(R.series || {}).map(([k, v]) => `<tr><td style="text-align:left"><b>${esc(k)}</b></td><td style="text-align:left;white-space:normal">${esc(v)}</td></tr>`).join('')}</tbody></table>
      ${R.calibracion ? `<p class="note">Calibración de hoy: 2Y = ${num(R.calibracion.beta_2y, 1)} pb por punto de ZT=F (R² ${num(R.calibracion.r2_2y, 2)}, n = ${R.calibracion.n_2y} días frente al 2 Yr del Tesoro) · 10Y de reserva = ${num(R.calibracion.beta_10y, 1)} pb por punto de ZN=F (R² ${num(R.calibracion.r2_10y, 2)}, n = ${R.calibracion.n_10y} barras de 5 min frente a ^TNX).</p>` : ''}</details>`;
  h += `<div class="note">${esc(R.fuente || '')} Memoria permanente: <a class="src" href="https://github.com/komonartisans-ops/nexora-terminal/blob/main/data/reacciones_eventos.csv" target="_blank" rel="noopener">data/reacciones_eventos.csv</a>. Alertas de giro enviadas: ${(R.avisos_enviados || []).length ? esc((R.avisos_enviados || []).join(', ')) : 'ninguna'}.</div>`;
  return h + errores(R.errores);
}

Object.assign(window.EXTRA_PAGES, { eventos: pageEventos });
