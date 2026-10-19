/* NEXORA TERMINAL · Petróleo (#/petroleo) y tarjeta del resumen. Lee site/data/petroleo.json (engine/petroleo.py, sin IA). Solo muestra: no calcula ni cambia reglas.
   Todo texto dinámico pasa por esc(). */
'use strict';

const PT_VOTO = { 1: ['ok', 'A FAVOR (+1)'], 0: ['par', 'NEUTRO (0)'], '-1': ['no', 'EN CONTRA (−1)'] };
const ptChip = (v) => { if (v == null) return '<span class="ck sd">SIN DATO</span>'; const [c, t] = PT_VOTO[String(v)] || ['sd', 'SIN DATO']; return `<span class="ck ${c}">${t}</span>`; };
const ptPct = (v, d = 2) => (v == null ? '—' : `${v > 0 ? '+' : ''}${num(v, d)} %`);
const ptEstadoCurva = { ESCASEZ: ['ok', 'ESCASEZ (backwardation)'], SOBRA: ['no', 'SOBRA (contango)'], PLANA: ['par', 'PLANA'] };

function ptKpi(nm, p) {
  if (!p || p.valor == null) return `<div class="card kpi asset"><div class="top"><div><div class="nm">${esc(nm)}</div></div></div><div class="big" style="margin-top:12px">${SD}</div></div>`;
  return `<div class="card kpi asset"><div class="top"><div><div class="nm">${esc(nm)}</div></div></div><div class="big" style="margin-top:10px">${num(p.valor, 2)}<small>USD/barril</small></div><div class="chg">${pill(p.cambio_1d_pct)}</div>
    <table><tr><td>1 semana</td><td>${pill(p.cambio_5d_pct)}</td></tr><tr><td>1 mes</td><td>${pill(p.cambio_21d_pct)}</td></tr><tr><td>3 meses</td><td>${pill(p.cambio_63d_pct)}</td></tr>
    <tr><td>Media de 200</td><td>${num(p.sma200, 2)} <small>(${ptPct(p.dist_sma200_pct, 1)})</small></td></tr></table>${foot(p.fuente, p.fecha)}</div>`;
}

function ptGrafico(id, G, titulo, sub) {
  if (!G || !G.precio || !G.precio.length) return `<div class="card"><h3>${esc(titulo)}</h3><div class="sub">${esc(sub)}</div><div class="empty" style="height:240px">SIN DATO · serie de precios</div></div>`;
  return `<div class="card chartcard"><h3>${esc(titulo)}</h3><div class="sub">${esc(sub)}</div>${lw(id, [
    { name: 'Precio', color: COL.amber, data: G.precio, prec: 2, area: true }, { name: 'Media 50', color: COL.blue, data: G.sma50, w: 1, prec: 2 }, { name: 'Media 200', color: COL.violet, data: G.sma200, w: 1, prec: 2 }], { init: 365 })}</div>`;
}

function ptTesisCard(T) {
  const tag = T.resultado === 'ALCISTA' ? 'alc' : T.resultado === 'BAJISTA' ? 'baj' : 'sin';
  const V = T.votos || {};
  const filas = [['precio', 'Precio', 'WTI frente a su media de 200 sesiones'], ['curva', 'Curva', 'diferencial 1.er–2.º vencimiento'], ['inventarios', 'Inventarios', `crudo, gasolina y destilados frente a su media de 5 años (suma ${T.suma_inventarios == null ? 'SIN DATO' : (T.suma_inventarios > 0 ? '+' : '') + T.suma_inventarios})`], ['cot', 'Posicionamiento (COT)', 'percentil a 3 años del dinero gestionado']];
  return `<div class="grid g2"><div class="card"><div class="chead"><span>Resultado de petróleo hoy</span></div>
    <div style="margin:10px 0 6px"><span class="tag ${tag} ${T.intensidad === 'DÉBIL' ? 'int-deb' : ''}" style="font-size:13px;padding:5px 12px">${esc(T.resultado || 'SIN DATO')}</span>${T.intensidad ? `<span class="ck ${T.intensidad === 'FUERTE' ? 'ok' : 'par'}" style="margin-left:8px">intensidad ${esc(T.intensidad)}</span>` : ''}${T.puntos != null ? `<span class="ck sd" style="margin-left:8px">suma ${T.puntos > 0 ? '+' : ''}${esc(String(T.puntos))} de ±4</span>` : ''}</div>
    ${T.motivo ? `<p class="note">${esc(T.motivo)}</p>` : ''}
    <p class="note" style="margin:8px 0 2px"><b style="color:var(--text)">Qué lo confirmaría</b></p><ul class="note" style="margin:0;padding-left:18px">${(T.confirmaria || []).map((x) => `<li>${esc(x)}</li>`).join('') || '<li>—</li>'}</ul>
    <p class="note" style="margin:8px 0 2px"><b style="color:var(--text)">Qué lo invalidaría</b></p><ul class="note" style="margin:0;padding-left:18px">${(T.invalidaria || []).map((x) => `<li>${esc(x)}</li>`).join('') || '<li>—</li>'}</ul>
    ${foot('petroleo.py (reglas fijas)', false, null, 'dirección en el marcador: ' + esc(T.resultado === 'ALCISTA' ? 'alcista' : T.resultado === 'BAJISTA' ? 'bajista' : 'ninguna') + ' (WTI a T+20)')}</div>
    <div class="card"><div class="chead"><span>Los cuatro factores</span></div><table class="t stack"><thead><tr><th style="text-align:left">Factor</th><th>Voto</th><th style="text-align:left">Con qué dato</th></tr></thead><tbody>${filas.map(([k, n, d]) => `<tr><td data-label="Factor" style="text-align:left"><b>${esc(n)}</b></td><td data-label="Voto">${ptChip(V[k])}</td><td data-label="Con qué dato" style="text-align:left;white-space:normal;min-width:180px">${esc(d)}</td></tr>`).join('')}</tbody></table>
    ${(T.causa_efecto || []).length ? `<p class="note" style="margin:10px 0 2px"><b style="color:var(--text)">Causa → efecto (hechos de hoy)</b></p><ul class="note" style="margin:0;padding-left:18px">${T.causa_efecto.map(([a, b]) => `<li><b>${esc(a)}</b>: ${esc(b)}.</li>`).join('')}</ul>` : ''}</div></div>`;
}

function ptCurva(C) {
  let h = '<div class="sect"><h2>Curva de futuros del WTI</h2><span class="more">1.er frente a 2.º vencimiento · contratos reales del mes</span></div>';
  if (!C) return h + `<div class="card"><div class="empty" style="height:100px">SIN DATO · contratos mensuales de WTI</div></div>`;
  const [c, t] = ptEstadoCurva[C.estado] || ['sd', 'SIN DATO'], hp = C.historico_propio || {};
  h += `<div class="grid g2"><div class="card"><div class="chead"><span>Hoy</span></div><div style="display:flex;gap:24px;flex-wrap:wrap;align-items:baseline;margin-top:8px"><div><div class="lab">1.er vencimiento (${esc(C.m1)})</div><div class="big">${num(C.precio_m1, 2)}<small>$</small></div></div>
    <div><div class="lab">2.º vencimiento (${esc(C.m2)})</div><div class="big">${num(C.precio_m2, 2)}<small>$</small></div></div><div><div class="lab">Diferencial</div><div class="big ${C.diferencial > 0 ? 'up' : C.diferencial < 0 ? 'down' : ''}">${C.diferencial > 0 ? '+' : ''}${num(C.diferencial, 2)}<small>$ · ${ptPct(C.diferencial_pct)}</small></div></div></div>
    <p style="margin:10px 0 4px"><span class="ck ${c}">${esc(t)}</span></p>
    <p class="note" style="margin:4px 0">Backwardation (1.º por encima del 2.º, ≥ +0,5 %) = el mercado paga por tener petróleo ya: ESCASEZ. Contango (1.º por debajo, ≤ −0,5 %) = SOBRA. En medio, PLANA. El 1.er contrato vence el ${esc(fdy(C.vence_m1))} (${esc(String(C.dias_a_vencimiento_m1))} día${C.dias_a_vencimiento_m1 === 1 ? '' : 's'}).</p>
    ${C.aviso ? `<div class="banner amber" style="margin:6px 0;border-radius:6px"><b>Ojo:</b> ${esc(C.aviso)}.</div>` : ''}
    <p class="note" style="margin:4px 0">Este mismo par de contratos, en los ${esc(String(C.dias_par))} días en que cotizaron los dos: hoy está en el percentil ${esc(String(C.percentil_par))} (rango ${ptPct(C.min_pct)} a ${ptPct(C.max_pct)}). No es el 1.º–2.º de cada día pasado: los contratos vencidos ya no están en Yahoo y la EIA dejó de publicar sus series de futuros en abril de 2024.</p>
    <p class="note" style="margin:4px 0">Histórico propio del 1.º–2.º de cada día: ${hp.dias ? `${esc(String(hp.dias))} día${hp.dias === 1 ? '' : 's'} acumulados desde ${esc(fdy(hp.desde))}${hp.percentil == null ? ' (percentil disponible a partir de 30 días)' : ' · percentil ' + esc(String(hp.percentil))}` : 'SIN DATO'}.</p>
    ${foot('Yahoo Finance (contratos CL<mes><año>.NYM)', C.fecha, null, 'tickers verificados: ' + esc(C.m1) + ', ' + esc(C.m2))}</div>`;
  h += (C.historico_par && C.historico_par.length) ? `<div class="card chartcard"><h3>Diferencial del par ${esc(C.m1)} − ${esc(C.m2)} (% del 2.º)</h3><div class="sub">Positivo = backwardation (escasez); negativo = contango (sobra)</div>${lw('cPtCurva', [{ name: 'Diferencial %', color: COL.amber, data: C.historico_par, prec: 2, area: true }], { init: 365 })}</div></div>`
    : '<div class="card"><div class="empty" style="height:200px">SIN DATO · histórico del par</div></div></div>';
  return h;
}

function ptInventarios(I) {
  let h = '<div class="sect"><h2>Inventarios semanales de la EIA</h2><span class="more">crudo (sin SPR), gasolina y destilados · millones de barriles</span></div>';
  const filas = ['crudo', 'gasolina', 'destilados'].map((k) => I[k]).filter(Boolean);
  if (!filas.length) return h + `<div class="card"><div class="empty" style="height:100px">SIN DATO · Weekly Petroleum Status Report de la EIA</div></div>`;
  const pr = I.proximo_informe;
  h += `<div class="card pad0 scroll"><table class="t stack"><thead><tr><th style="text-align:left">Producto</th><th>Semana al</th><th>Nivel</th><th>Cambio semanal</th><th>Media 5 años</th><th>Frente a la media</th><th>Voto</th></tr></thead><tbody>`
    + filas.map((x) => `<tr><td data-label="Producto" style="text-align:left"><b>${esc(x.nombre)}</b><small>${esc(x.serie_id)}</small></td><td data-label="Semana al">${esc(fdy(x.semana))}</td><td data-label="Nivel">${num(x.valor_mb, 1)}</td><td data-label="Cambio semanal">${pill(x.cambio_semana_mb, 1, ' Mb')}</td>`
      + `<td data-label="Media 5 años">${x.media_5a_mb == null ? 'SIN DATO' : num(x.media_5a_mb, 1)}</td><td data-label="Frente a la media">${x.vs_media_5a_pct == null ? 'SIN DATO' : `${ptPct(x.vs_media_5a_pct, 1)} <small>(${num(x.vs_media_5a_mb, 1)} Mb)</small>`}</td><td data-label="Voto">${ptChip(x.voto)}</td></tr>`).join('')
    + `</tbody></table><div class="note" style="padding:8px 16px 12px">Por debajo de su media de 5 años en más de un 2 % = menos colchón de oferta (a favor del precio); por encima en más de un 2 % = más colchón (en contra). La media es la de la misma semana de los 5 años anteriores. Fuente de los datos: ${esc(I.origen || 'EIA')}${I.con_clave_api ? '' : ' (sin clave de API: tablas públicas del Weekly Petroleum Status Report)'}. ${pr ? `Próximo informe: ${esc(fdy(pr.fecha))} a las ${esc(pr.hora_et)} ET (semana al ${esc(fdy(pr.semana))}); calendario oficial de la EIA.` : ''}</div></div>`;
  const cr = I.crudo;
  h += cr && cr.serie ? `<div class="card chartcard" style="margin-top:12px"><h3>Inventarios comerciales de crudo (Mb)</h3><div class="sub">Dos años de lecturas semanales</div>${lw('cPtInv', [{ name: 'Crudo (Mb)', color: COL.amber, data: cr.serie, prec: 1, area: true }], { init: 730 })}${foot('EIA · Weekly Petroleum Status Report', cr.semana)}</div>` : '';
  return h;
}

function ptCot(C) {
  let h = '<div class="sect"><h2>Posicionamiento (COT) del WTI</h2><span class="more">CFTC · dinero gestionado · publica el viernes con datos del martes</span></div>';
  if (!C || C.estado !== 'OK') return h + `<div class="card"><div class="empty" style="height:100px">SIN DATO · ${esc((C && C.motivo) || 'CFTC')}</div></div>`;
  return h + `<div class="grid g2"><div class="card"><div style="display:flex;gap:24px;flex-wrap:wrap;align-items:baseline"><div><div class="lab">Neto (largos − cortos)</div><div class="big">${num(C.neto, 0)}<small>contratos</small></div></div><div><div class="lab">Cambio semanal</div><div class="big ${C.cambio_semana >= 0 ? 'up' : 'down'}">${C.cambio_semana > 0 ? '+' : ''}${num(C.cambio_semana, 0)}</div></div>
    <div><div class="lab">Percentil a 3 años</div><div class="big">${esc(String(C.percentil_3a))}<small>de 100 · ${esc(C.zona || '')}</small></div></div></div>
    <p style="margin:8px 0 2px">${ptChip(C.voto)}</p><p class="note" style="margin:4px 0">Largos ${num(C.largos, 0)} · cortos ${num(C.cortos, 0)} · rango a 3 años ${num(C.min_3a, 0)} a ${num(C.max_3a, 0)}. Regla: percentil ≥ 66 vota +1; ≤ 34 vota −1.</p>${foot(C.fuente, C.fecha, 'https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm')}</div>
    <div class="card chartcard"><h3>Neto del dinero gestionado</h3><div class="sub">Últimas 104 semanas</div>${lw('cPtCot', [{ name: 'Neto', color: COL.blue, data: C.serie, prec: 0, area: true }], { init: 730 })}</div></div>`;
}

function ptGasolina(G) {
  let h = '<div class="sect"><h2>Gasolina en EE. UU. y consumo</h2><span class="more">precio medio semanal de la gasolina regular · FRED GASREGW</span></div>';
  if (!G || G.estado !== 'OK') return h + `<div class="card"><div class="empty" style="height:100px">SIN DATO · FRED GASREGW</div></div>`;
  const K = G.consumo;
  return h + `<div class="grid g2"><div class="card"><div style="display:flex;gap:24px;flex-wrap:wrap;align-items:baseline"><div><div class="lab">Gasolina regular</div><div class="big">${num(G.valor, 3)}<small>$/galón · ${esc(fdy(G.fecha))}</small></div></div>
    <div><div class="lab">4 semanas</div><div class="big">${pill(G.cambio_4s_pct)}</div></div><div><div class="lab">Interanual</div><div class="big">${G.interanual_pct == null ? 'SIN DATO' : pill(G.interanual_pct)}</div></div></div>
    <p class="note" style="margin:10px 0 4px">Efecto en el consumo (hecho, sin elasticidades inventadas): la gasolina es un gasto que el hogar no puede aplazar; cuando sube, queda menos renta para el resto del gasto. ${K && K.tesis ? `La tesis de consumo de hoy es <b>${esc(K.tesis)}</b>${K.intensidad ? ' (intensidad ' + esc(K.intensidad) + ')' : ''}: ` : ''}<a href="#/consumo">ver #/consumo →</a>. Para ver su efecto real, mira las ventas minoristas y el consumo real, y la tasa de ahorro, en esa página.</p>
    ${foot(G.fuente, G.fecha)}</div><div class="card chartcard"><h3>Gasolina regular ($/galón)</h3><div class="sub">Dos años de lecturas semanales</div>${lw('cPtGas', [{ name: '$/galón', color: COL.amber, data: G.serie, prec: 3, area: true }], { init: 730 })}</div></div>`;
}

function ptRelaciones(R) {
  let h = '<div class="sect"><h2>Relaciones del petróleo</h2><span class="more">se muestran, NO puntúan en la tesis</span></div>';
  if (!R || !(R.filas || []).length) return h + `<div class="card"><div class="empty" style="height:80px">SIN DATO</div></div>`;
  return h + `<div class="card pad0 scroll"><table class="t stack"><thead><tr><th style="text-align:left">Frente a</th><th>Valor</th><th>Cambio 3 meses</th><th>Correlación 60 sesiones</th><th style="text-align:left">Lectura</th></tr></thead><tbody>`
    + R.filas.map((x) => (x.sin_dato ? `<tr><td data-label="Frente a" style="text-align:left"><b>${esc(x.nombre)}</b></td><td colspan="4"><span class="sd-val">SIN DATO</span></td></tr>`
      : `<tr><td data-label="Frente a" style="text-align:left"><b>${esc(x.nombre)}</b><small>${esc(fdy(x.fecha))}</small></td><td data-label="Valor">${num(x.valor, 2)}</td><td data-label="Cambio 3 meses">${x.unidad_cambio === 'pb' ? `${x.cambio_3m > 0 ? '+' : ''}${num(x.cambio_3m, 0)} pb` : ptPct(x.cambio_3m, 1)}</td><td data-label="Correlación 60 sesiones">${x.correlacion_60d == null ? 'SIN DATO' : num(x.correlacion_60d, 2)}</td><td data-label="Lectura" style="text-align:left">${esc(x.lectura || 'SIN DATO')}</td></tr>`)).join('')
    + `</tbody></table><div class="note" style="padding:8px 16px 12px">Correlación de las variaciones diarias de los últimos 60 días comunes (WTI frente a la variación diaria del breakeven en puntos, o a la variación % de DXY y XLE). Con el WTI ${ptPct(R.wti_cambio_3m_pct, 1)} en 3 meses. Una correlación no implica causa y no entra en ninguna regla.</div></div>`;
}

function petroleoHtml(M) {
  const T = M.tesis || {}, P = M.precios || {}, I = M.inventarios || {};
  let h = essential(
    `${esc(T.resultado || 'SIN DATO')}${T.intensidad ? ' · intensidad ' + esc(T.intensidad) : ''}${T.puntos != null ? ' · suma ' + (T.puntos > 0 ? '+' : '') + esc(String(T.puntos)) : ''}: ${(T.causa_efecto || []).slice(0, 2).map(([a, b]) => esc(a + ': ' + b)).join('; ') || esc(T.motivo || '')}.`,
    `Hecho: WTI ${P.wti ? num(P.wti.valor, 2) + ' $' : 'SIN DATO'}, Brent ${P.brent ? num(P.brent.valor, 2) + ' $' : 'SIN DATO'}. Interpretación: cuatro factores con reglas fijas (precio, curva, inventarios, COT); no es una recomendación de compra o venta.`,
    `Qué lo confirmaría: ${esc((T.confirmaria || ['—'])[0])}. Qué lo invalidaría: ${esc((T.invalidaria || ['—'])[0])}.`, 'Qué vigilar');
  h += '<div class="sect"><h2>Precio del petróleo</h2><span class="more">WTI y Brent · futuros del primer vencimiento · fecha del dato</span></div><div class="grid g2">' + ptKpi('WTI (CL=F)', P.wti) + ptKpi('Brent (BZ=F)', P.brent) + '</div>';
  if (P.wti && P.wti.aviso_empalme) h += `<div class="banner amber" style="margin:12px 0 0;border-radius:6px"><b>Cambio de contrato:</b> ${esc(P.wti.aviso_empalme)}.</div>`;
  const seg = P.segunda_fuente || {};
  h += `<div class="note" style="margin:10px 0 0">Segunda fuente (FRED, precios al contado de la EIA con retraso): ${['wti', 'brent'].filter((k) => seg[k]).map((k) => `${k === 'wti' ? 'WTI' : 'Brent'} el ${esc(fdy(seg[k].fecha))}: Yahoo ${num(seg[k].yahoo, 2)} $ frente a FRED ${num(seg[k].fred, 2)} $ (${ptPct(seg[k].dif_pct, 1)})`).join(' · ') || 'SIN DATO'}. ${esc((P.segunda_fuente_nota && P.segunda_fuente_nota.brent) || '')} ${esc((P.segunda_fuente_nota && P.segunda_fuente_nota.wti) || '')}${P.spread_brent_wti != null ? ` Diferencial Brent − WTI (futuros): ${num(P.spread_brent_wti, 2)} $.` : ''}</div>`;
  h += '<div class="sect"><h2>Tesis de petróleo</h2><span class="more">reglas fijas · sin IA</span></div>' + ptTesisCard(T);
  h += '<div class="sect"><h2>Petróleo a 2 años</h2><span class="more">con medias de 50 y 200 sesiones</span></div><div class="grid g2">' + ptGrafico('cPtWti', (M.graficos || {}).wti, 'WTI', 'Futuro del primer vencimiento (serie empalmada: hay saltos al cambiar de contrato)') + ptGrafico('cPtBrent', (M.graficos || {}).brent, 'Brent', 'Futuro del primer vencimiento (serie empalmada)') + '</div>';
  h += ptCurva(M.curva) + ptInventarios(I);
  const B = M.plataformas || {};
  h += `<div class="sect"><h2>Plataformas de petróleo (Baker Hughes)</h2><span class="more">recuento semanal de la industria</span></div><div class="card"><span class="ck sd">SIN DATO</span><p class="note" style="margin:8px 0 0">${esc(B.motivo || 'SIN DATO')}</p>${foot(B.fuente || 'Baker Hughes', false, B.url, 'no se estima')}</div>`;
  h += ptCot(M.cot) + ptGasolina(M.gasolina) + ptRelaciones(M.relaciones);
  h += `<div class="sect"><h2>Reglas fijas de petróleo</h2><span class="more">impresas tal cual las aplica el motor</span></div><div class="card"><details class="qa" open><summary>Reglas fijas de petróleo</summary>${(M.reglas || []).map((r) => `<p style="margin:6px 0">${esc(r)}</p>`).join('')}</details></div>`;
  h += `<div class="note" style="margin:12px 0 0">Fuentes: ${esc(M.fuentes || '')}. Hecho, interpretación y escenario van separados: los precios, inventarios y posiciones son hechos; la tesis es una lectura con reglas fijas, no una recomendación de compra o venta.</div>`;
  const er = Object.keys(M.errores || {});
  if (er.length) h += `<div class="banner amber" style="margin:12px 0 0;border-radius:6px"><b>Fuentes con error (SIN DATO en su parte):</b> ${er.map((k) => esc(k)).join(', ')}.</div>`;
  return h;
}

function pagePetroleo() {
  const h = head('Análisis', 'Petróleo', 'WTI y Brent como un activo completo: precio, curva de futuros (escasez o sobra), inventarios semanales de la EIA, posicionamiento de la CFTC, gasolina y una tesis con reglas fijas.',
    'Datos públicos y gratuitos · sin IA en ejecución') + '<div id="pt-root"><div class="empty" style="height:180px">CARGANDO PETRÓLEO…</div></div>';
  MOUNT.push(async () => {
    const root = document.getElementById('pt-root');
    if (!root) return;
    let M = null;
    try { const r = await fetch('data/petroleo.json?v=' + Date.now(), { cache: 'no-store' }); if (r.ok) M = await r.json(); } catch (e) { /* SIN DATO */ }
    if (document.getElementById('pt-root') !== root) return;
    if (!M || !M.tesis) { root.innerHTML = noData('Petróleo (petroleo.json)'); return; }
    f5.paint(root, () => petroleoHtml(M));
  });
  return h;
}

/* tarjeta del resumen: precio WTI/Brent (de precios.json), tesis y causa → efecto (de petroleo.json) */
function cardPetroleoResumen() {
  const M = D.petroleo, A = (D.precios && D.precios.activos) || {}, MP = (M && M.precios) || {}, w = MP.wti || A.wti, b = MP.brent || A.brent, T = M && M.tesis;   /* petroleo.json trae el cambio diario ya corregido del salto de contrato */
  const px = (a, nm) => (a && a.valor != null ? `<div><div class="lab">${esc(nm)}</div><div class="big">${num(a.valor, 2)}<small>USD</small></div><div class="chg">${pill(a.cambio_1d_pct)}</div></div>` : `<div><div class="lab">${esc(nm)}</div><div class="big">${SD}</div></div>`);
  let h = '<div class="sect"><h2>Petróleo</h2><a class="more" href="#/petroleo">página completa →</a></div><div class="card asset"><div class="top"><div class="nm">WTI y Brent</div>' + (T ? tagTesis(T.resultado === 'SIN TESIS' ? 'SIN TESIS' : `${T.resultado}${T.intensidad === 'DÉBIL' ? ' · DÉBIL' : ''}`) : '<span class="tag sd">SIN DATO</span>') + '</div>';
  h += `<div style="display:flex;gap:28px;flex-wrap:wrap;margin:8px 0">${px(w, 'WTI')}${px(b, 'Brent')}${M && M.curva ? `<div><div class="lab">Curva WTI</div><div class="big" style="font-size:18px">${esc((ptEstadoCurva[M.curva.estado] || [0, 'SIN DATO'])[1])}</div><div class="chg">${ptPct(M.curva.diferencial_pct)}</div></div>` : ''}</div>`;
  if (T) {
    h += `<div class="flow">${esc(T.resultado)}${T.intensidad ? ' · intensidad ' + esc(T.intensidad) : ''}: suma de cuatro factores (precio, curva, inventarios, COT)${T.puntos != null ? ' = ' + (T.puntos > 0 ? '+' : '') + esc(String(T.puntos)) : ''}.<em>Causa → efecto</em>${(T.causa_efecto || []).map(([a, c]) => `<div><b>${esc(a)}</b> → ${esc(c)}</div>`).join('') || '<div>SIN DATO</div>'}</div>`;
  } else h += `<div class="flow">SIN DATO: la tesis de petróleo no se pudo calcular en esta ejecución.</div>`;
  return h + foot('petroleo.py (reglas fijas) · precios Yahoo Finance', M && M.fecha_datos) + '</div>';
}

Object.assign(window.EXTRA_PAGES, { petroleo: pagePetroleo });
