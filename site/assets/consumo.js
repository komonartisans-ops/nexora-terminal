/* NEXORA TERMINAL · «¿Está consumiendo la gente?» (#/consumo). Lee site/data/consumo.json (engine/consumo.py, sin IA). Solo muestra: no calcula ni cambia reglas.
   Todo texto dinámico pasa por esc(). */
'use strict';

const CS_TAG = { 'CONSUMO FUERTE': 'alc', 'SE ENFRÍA': 'baj', 'CONSUMO DÉBIL': 'baj', 'DIVERGENCIA MERCADO ADELANTADO': 'deb', 'DIVERGENCIA MERCADO DEFENSIVO': 'deb' };
const CS_ESTADO = { ALZA: ['ok', 'AL ALZA'], BAJA: ['no', 'A LA BAJA'], MIXTO: ['par', 'MIXTO'], RESPALDA: ['ok', 'RESPALDA'], 'NO RESPALDA': ['no', 'NO RESPALDA'], MIXTA: ['par', 'MIXTA'], 'SIN DATO': ['sd', 'SIN DATO'] };
const csChip = (e) => { const [c, t] = CS_ESTADO[e] || ['sd', 'SIN DATO']; return `<span class="ck ${c}">${t}</span>`; };
const csPct = (v, d = 2) => (v == null ? '—' : `${v > 0 ? '+' : ''}${num(v, d)} %`);

function csGrafico(id, G, titulo, sub, pie) {
  if (!G || !G.ratio || !G.ratio.length) return `<div class="card"><h3>${esc(titulo)}</h3><div class="sub">${esc(sub)}</div><div class="empty" style="height:240px">SIN DATO · ${esc(pie)}</div></div>`;
  return `<div class="card chartcard"><h3>${esc(titulo)}</h3><div class="sub">${esc(sub)}</div>${lw(id, [
    { name: 'Ratio', color: COL.amber, data: G.ratio, prec: 3, area: true }, { name: 'Media 50', color: COL.blue, data: G.sma50, w: 1, prec: 3 }, { name: 'Media 200', color: COL.violet, data: G.sma200, w: 1, prec: 3 }], { init: 730 })}${foot(pie, G.ratio[G.ratio.length - 1][0])}</div>`;
}

const CS_SECTOR = { XLY: 'Consumo discrecional', XLP: 'Consumo básico', XLK: 'Tecnología', XLE: 'Energía', XLU: 'Servicios públicos', XLV: 'Salud', XLF: 'Financieras', XLI: 'Industriales' };
const csPp = (v, d = 2) => (v == null ? '—' : `${v > 0 ? '+' : ''}${num(v, d)} pp`);

/* los tres usos del ratio: filtro SMA 200, rotación frente a SPY y divergencia (consumo_ratio.json; solo describe, sin recomendaciones) */
function cnsRatio(RR) {
  let h = '';
  if (!RR || !RR.filtro_sma200) return `<div class="sect"><h2>Filtro SMA 200 del ratio</h2></div><div class="card"><div class="empty" style="height:80px">SIN DATO · consumo_ratio.json</div></div>`;
  const F = RR.filtro_sma200;
  h += `<div class="sect"><h2>Filtro SMA 200 del ratio</h2><span class="more">cruce válido solo tras ${esc(String(F.cierres_para_cruce))} cierres seguidos al otro lado</span></div><div class="card pad0 scroll"><table class="t stack"><thead><tr><th style="text-align:left">Ratio</th><th>Marco</th><th>Estado</th><th>Lado vigente</th><th>Cruce en curso</th><th>Último cruce válido</th><th>Cruces válidos en 12 meses</th></tr></thead><tbody>`;
  h += Object.values(F.ratios).map((r) => ['diario', 'semanal'].map((tf) => {
    const x = r[tf];
    if (!x || x.estado === 'SIN DATO') return `<tr><td data-label="Ratio" style="text-align:left"><b>${esc(r.nombre)}</b></td><td data-label="Marco">${tf}</td><td colspan="5"><span class="sd-val">SIN DATO</span> <small>${esc((x && x.motivo) || '')}</small></td></tr>`;
    const sobre = x.lado_actual > 0, vig = x.vigente > 0;
    return `<tr><td data-label="Ratio" style="text-align:left"><b>${esc(r.nombre)}</b></td><td data-label="Marco">${tf}</td><td data-label="Estado"><span class="ck ${sobre ? 'ok' : 'no'}">${esc(x.estado)}</span> <small>${csPct(x.dist_pct, 2)} · ${esc(fdy(x.fecha))}</small></td>`
      + `<td data-label="Lado vigente"><span class="ck ${vig ? 'ok' : 'no'}">${esc(x.vigente_texto)}</span></td><td data-label="Cruce en curso">${x.pendiente ? `<span class="ck par">${esc(String(x.pendiente))} de ${esc(String(F.cierres_para_cruce))} cierres</span>` : '—'}</td>`
      + `<td data-label="Último cruce válido">${x.ultimo_cruce ? `${esc(fdy(x.ultimo_cruce.fecha))} <small>${esc(x.ultimo_cruce.sentido.toLowerCase())}</small>` : 'ninguno en la historia'}</td>`
      + `<td data-label="Cruces válidos en 12 meses"><span class="ck ${x.poco_fiable ? 'par' : 'sd'}">${esc(String(x.cruces_12m))}</span>${x.nota ? ` <small style="color:var(--amber)"><b>${esc(x.nota)}</b></small>` : ''}</td></tr>`;
  }).join('')).join('');
  h += `</tbody></table><div class="note" style="padding:8px 16px 12px">Estado = cierre del ratio frente a su media de 200 (sesiones en diario; cierres semanales en semanal, con la semana en curso solo si ya cerró el viernes). El lado vigente solo cambia tras ${esc(String(F.cierres_para_cruce))} cierres consecutivos al otro lado; un cierre de vuelta reinicia la cuenta. Con ${esc(String(F.umbral_cruces_12m))} o más cruces válidos en 12 meses el filtro se marca poco fiable (mercado lateral). No puntúa en la tesis de consumo.</div>${footIn('Yahoo Finance (XLY, XLP, RSPD, RSPS)', RR.fecha_datos, null, 'SMA 200 propia')}</div>`;

  const Ro = RR.rotacion || {};
  h += '<div class="sect"><h2>Rotación frente a SPY</h2><span class="more">rendimiento relativo a 1 y 3 meses · ordenada por 3 meses · solo describe</span></div>';
  if (Ro.estado !== 'OK') h += '<div class="card"><div class="empty" style="height:80px">SIN DATO · series de los sectores</div></div>';
  else {
    h += `<div class="card pad0 scroll"><table class="t stack"><thead><tr><th>Puesto 3 m</th><th style="text-align:left">Sector (ETF)</th><th>Rend. 3 m</th><th>Relativo a SPY 3 m</th><th>Rend. 1 m</th><th>Relativo a SPY 1 m</th><th>Puesto 1 m</th></tr></thead><tbody>`
      + `<tr><td data-label="Puesto 3 m">—</td><td data-label="Sector (ETF)" style="text-align:left"><b>SPY</b><small>referencia</small></td><td data-label="Rend. 3 m">${csPct(Ro.spy.ret_3m)}</td><td data-label="Relativo a SPY 3 m">—</td><td data-label="Rend. 1 m">${csPct(Ro.spy.ret_1m)}</td><td data-label="Relativo a SPY 1 m">—</td><td data-label="Puesto 1 m">—</td></tr>`
      + (Ro.filas || []).map((f) => `<tr><td data-label="Puesto 3 m" class="mono">${f.puesto_3m == null ? '—' : esc(String(f.puesto_3m))}</td><td data-label="Sector (ETF)" style="text-align:left"><b>${esc(f.etf)}</b><small>${esc(CS_SECTOR[f.etf] || '')}</small></td><td data-label="Rend. 3 m">${csPct(f.ret_3m)}</td>`
        + `<td data-label="Relativo a SPY 3 m" class="${f.rel_3m > 0 ? 'up' : f.rel_3m < 0 ? 'down' : ''}">${csPp(f.rel_3m)}</td><td data-label="Rend. 1 m">${csPct(f.ret_1m)}</td><td data-label="Relativo a SPY 1 m" class="${f.rel_1m > 0 ? 'up' : f.rel_1m < 0 ? 'down' : ''}">${csPp(f.rel_1m)}</td><td data-label="Puesto 1 m" class="mono">${f.puesto_1m == null ? '—' : esc(String(f.puesto_1m))}</td></tr>`).join('')
      + `</tbody></table><div class="note" style="padding:8px 16px 12px">${esc(Ro.nota)}</div>${footIn('Yahoo Finance (ETF sectoriales SPDR y SPY)', Ro.spy.fecha, null, '21 y 63 sesiones')}</div>`;
  }

  const Dv = RR.divergencia || {}, e = Dv.hoy;
  h += '<div class="sect"><h2>Divergencia: SPY frente al consumo amplio</h2><span class="more">SPY en máximo de 63 sesiones y RSPD/RSPS más de un 3 % por debajo del suyo</span></div>';
  if (!e) h += '<div class="card"><div class="empty" style="height:80px">SIN DATO · SPY, RSPD o RSPS</div></div>';
  else {
    const si = (b) => (b == null ? '<span class="ck sd">SIN DATO</span>' : b ? '<span class="ck ok">SÍ</span>' : '<span class="ck sd">no</span>');
    const col = e.fuerza === 'FUERTE' ? 'no' : e.fuerza === 'MEDIA' ? 'par' : 'sd';
    h += `<div class="grid g2"><div class="card"><div class="chead"><span>Hoy · ${esc(fdy(e.fecha))}</span></div><div style="margin:10px 0 6px">${e.activa ? `<span class="ck ${col}" style="font-size:13px;padding:5px 12px">DIVERGENCIA ${esc(e.fuerza)}${e.parcial ? ' (parcial)' : ''}</span>` : '<span class="ck sd" style="font-size:13px;padding:5px 12px">SIN DIVERGENCIA</span>'}</div>`
      + `<table class="t stack"><thead><tr><th style="text-align:left">Condición</th><th>Valor</th><th>¿Se cumple?</th></tr></thead><tbody>`
      + `<tr><td data-label="Condición" style="text-align:left">SPY marca máximo de cierre de 63 sesiones</td><td data-label="Valor">—</td><td data-label="¿Se cumple?">${si(e.spy_max_63)}</td></tr>`
      + `<tr><td data-label="Condición" style="text-align:left">RSPD/RSPS más de un ${esc(num(Dv.umbral_pct, 0))} % por debajo de su máximo de 63 sesiones</td><td data-label="Valor">${csPct(e.ratio_vs_max63_pct)}</td><td data-label="¿Se cumple?">${si(e.ratio_vs_max63_pct < -Dv.umbral_pct)}</td></tr>`
      + `<tr><td data-label="Condición" style="text-align:left"><b>Confirmación 1:</b> amplitud a la baja en 1 mes (RSP frente a SPY, 20 sesiones, ≤ ${esc(num(-Dv.amplitud.umbral_pp, 0))} pp)</td><td data-label="Valor">${csPp(e.amplitud_pp)}</td><td data-label="¿Se cumple?">${si(e.amplitud_a_la_baja)}</td></tr>`
      + `<tr><td data-label="Condición" style="text-align:left"><b>Confirmación 2:</b> diferenciales de crédito ampliándose (umbrales de ciclo.py)</td><td data-label="Valor">${e.credito_detalle && e.credito_detalle.length ? esc(e.credito_detalle.join(', ')) : '—'}</td><td data-label="¿Se cumple?">${si(e.credito_ampliandose)}</td></tr></tbody></table>`
      + `<p class="note" style="margin:8px 0 0">Las dos confirmaciones = FUERTE; una = MEDIA; ninguna = DÉBIL. Telegram solo cuando aparece una FUERTE (máx. 1 por semana). ${Dv.telegram ? 'Hoy: ' + esc(Dv.telegram.motivo) + '.' : ''}</p>${footIn('Yahoo Finance (SPY, RSP, RSPD, RSPS) · FRED (ICE BofA)', e.fecha, null, 'divergencia con reglas fijas')}</div>`
      + `<div class="card"><div class="chead"><span>Últimas divergencias</span></div><table class="t stack"><thead><tr><th>Inicio</th><th>Fuerza</th></tr></thead><tbody>${(Dv.inicios_recientes || []).slice().reverse().map((x) => `<tr><td data-label="Inicio">${esc(fdy(x.fecha))}</td><td data-label="Fuerza"><span class="ck ${x.fuerza === 'FUERTE' ? 'no' : x.fuerza === 'MEDIA' ? 'par' : 'sd'}">${esc(x.fuerza)}</span>${x.parcial ? ' <small>parcial</small>' : ''}</td></tr>`).join('') || '<tr><td colspan="2">ninguna</td></tr>'}</tbody></table>`
      + `<p class="note" style="margin:8px 0 0">Una divergencia nueva solo cuenta si hace 10 o más sesiones que no había ninguna. «Parcial» = falta el dato de una confirmación (el crédito de FRED solo cubre 3 años). La amplitud usada es la que ya mide NEXORA (RSP frente a SPY); el porcentaje de valores del S&amp;P sobre su SMA 200 no se calcula. Cada cruce válido y cada divergencia quedan en el <a href="#/marcador">Marcador</a> y se miden sobre SPY a T+20 y T+60 frente a la tasa base.</p></div></div>`;
  }
  return h;
}

function consumoHtml(M, RR) {
  const T = M.tesis || {}, C = M.capas || {}, mk = M.mercado || {}, cap = mk.cap, ig = mk.igual, pw = mk.pesos;
  const tag = CS_TAG[T.resultado] || 'sin';
  let h = essential(
    `${esc(T.resultado || 'SIN DATO')}${T.intensidad ? ' · intensidad ' + esc(T.intensidad) : ''}: ${esc(T.porque || '')}.`,
    `Hecho: mercado (peso igual RSPD/RSPS) ${esc((CS_ESTADO[C.mercado.estado] || [0, 'SIN DATO'])[1].toLowerCase())}, datos reales ${esc((CS_ESTADO[C.real.estado] || [0, 'SIN DATO'])[1].toLowerCase())}, capacidad ${esc((CS_ESTADO[C.capacidad.estado] || [0, 'SIN DATO'])[1].toLowerCase())}. Interpretación: las reglas son fijas y están impresas más abajo; la tesis es contexto, no una orden.`,
    `Qué lo confirmaría: ${esc(T.confirmaria || '—')}. Qué lo invalidaría: ${esc(T.invalidaria || '—')}.`, 'Qué vigilar');
  if (mk.aviso) h += `<div class="banner amber" style="margin:0 0 14px;border-radius:6px"><b>Concentración: ${esc(mk.aviso)}.</b> En 3 meses XLY/XLP ${csPct(cap && cap.pendiente_3m_pct)} y RSPD/RSPS ${csPct(ig && ig.pendiente_3m_pct)}${pw ? `; Amazon + Tesla pesan el ${esc(num(pw.suma, 1))} % de XLY (${esc(pw.fecha)})` : ''}.</div>`;
  h += `<div class="sect"><h2>Tesis de consumo</h2><span class="more">reglas fijas · sin IA</span></div><div class="grid g2"><div class="card"><div class="chead"><span>Resultado de hoy</span></div>
    <div style="margin:10px 0 6px"><span class="tag ${tag} ${T.intensidad === 'DÉBIL' ? 'int-deb' : ''}" style="font-size:13px;padding:5px 12px">${esc(T.resultado || 'SIN DATO')}</span>${T.intensidad ? ` <span class="ck ${T.intensidad === 'FUERTE' ? 'ok' : 'par'}">intensidad ${esc(T.intensidad)}</span>` : ''}</div>
    <p class="note" style="margin:4px 0">${esc(T.porque || '')}. ${T.motivo_intensidad ? 'Intensidad: ' + esc(T.motivo_intensidad) + '.' : ''}</p>
    <p class="note" style="margin:8px 0 2px"><b style="color:var(--text)">Qué lo confirmaría</b> · ${esc(T.confirmaria || '—')}</p><p class="note" style="margin:2px 0"><b style="color:var(--text)">Qué lo invalidaría</b> · ${esc(T.invalidaria || '—')}</p>
    ${foot('consumo.py (reglas fijas)', false, null, `dirección en el marcador: ${esc((T.direccion_marcador || 'NINGUNA').toLowerCase())} (RSPD/RSPS a T+20)`)}</div>
    <div class="card"><div class="chead"><span>Las tres capas</span></div><table class="t stack"><thead><tr><th style="text-align:left">Capa</th><th>Estado</th><th style="text-align:left">Con qué datos</th></tr></thead><tbody>
      <tr><td data-label="Capa" style="text-align:left"><b>Mercado</b><small>peso igual RSPD/RSPS</small></td><td data-label="Estado">${csChip(C.mercado.estado)}</td><td data-label="Con qué datos" style="text-align:left;white-space:normal">${esc(C.mercado.detalle)}</td></tr>
      <tr><td data-label="Capa" style="text-align:left"><b>Real</b><small>ventas y consumo reales</small></td><td data-label="Estado">${csChip(C.real.estado)}</td><td data-label="Con qué datos" style="text-align:left;white-space:normal">${esc(C.real.detalle)}</td></tr>
      <tr><td data-label="Capa" style="text-align:left"><b>Capacidad</b><small>renta, ahorro, crédito, morosidad</small></td><td data-label="Estado">${csChip(C.capacidad.estado)}</td><td data-label="Con qué datos" style="text-align:left;white-space:normal">${esc(C.capacidad.detalle || '')}${C.capacidad.suma != null ? ` → suma ${C.capacidad.suma > 0 ? '+' : ''}${C.capacidad.suma}` : ''}</td></tr>
    </tbody></table></div></div>`;
  h += '<div class="sect"><h2>Gráficos: ¿consumo amplio o dos empresas?</h2><span class="more">2 años · medias de 50 y 200 sesiones</span></div>';
  h += `<div class="grid g2">${csGrafico('csCap', (M.graficos || {}).cap, 'Consumo discrecional / básico (XLY/XLP, ponderado por capitalización)', 'Sube cuando el mercado apuesta por el consumo cíclico; Amazon y Tesla pesan mucho en XLY.', 'XLY y XLP (Yahoo Finance)')}
    ${csGrafico('csIgual', (M.graficos || {}).igual, 'Consumo discrecional / básico en peso igual (RSPD/RSPS)', 'Cada empresa pesa lo mismo: refleja el consumo amplio, no a las más grandes.', 'RSPD y RSPS (Yahoo Finance)')}</div>`;
  h += `<div class="note" style="margin-top:8px"><b style="color:var(--text)">Concentración.</b> ${pw ? `Amazon + Tesla pesan el <b>${esc(num(pw.suma, 1))} %</b> de XLY (Amazon ${esc(num(pw.amzn, 2))} % + Tesla ${esc(num(pw.tsla, 2))} %; posiciones oficiales de State Street SSGA, ${esc(pw.fecha)}).` : 'Peso de Amazon + Tesla en XLY: <span class="sd-val">SIN DATO</span> (posiciones de SSGA no disponibles).'}
    Diferencia entre ambos ratios en 3 meses: ${mk.diferencia_3m_pp == null ? '<span class="sd-val">SIN DATO</span>' : `${csPct(mk.diferencia_3m_pp)} (XLY/XLP ${csPct(cap && cap.pendiente_3m_pct)} · RSPD/RSPS ${csPct(ig && ig.pendiente_3m_pct)})`}.
    Si los dos ratios se separan más de ${esc(num(mk.umbral_pp == null ? 2 : mk.umbral_pp, 0))} pp en 3 meses, en cualquier sentido, el ratio lo mueven AMZN+TSLA, no el consumo amplio.</div>`;
  const A = M.animo;
  h += `<div class="sect"><h2>Contexto de ánimo</h2><span class="more">no puntúa en la tesis</span></div><div class="card">${cnsAnimo(M.animo)}</div>`;
  const I = D.integridad || {}, pubs = I.publicaciones || [];
  h += '<div class="sect"><h2>Datos reales de consumo y renta</h2><span class="more">FRED · % interanual y tendencia a 3 meses · fecha del dato y de publicación</span></div><div class="card pad0 scroll"><table class="t stack"><thead><tr><th style="text-align:left">Dato</th><th>Dato de</th><th>Valor</th><th>Tendencia 3 meses</th><th>Publicado el</th><th>Registrado por NEXORA</th></tr></thead><tbody>';
  h += (M.real || []).map((x) => {
    if (x.sin_dato) return `<tr><td data-label="Dato" style="text-align:left"><b>${esc(x.nombre)}</b></td><td colspan="5"><span class="sd-val">SIN DATO</span></td></tr>`;
    const p = pubs.find((y) => y.serie === x.serie && y.periodo === x.periodo);
    const per = x.frecuencia === 'Q' ? `T${Math.floor((+x.periodo.slice(5, 7) - 1) / 3) + 1} ${x.periodo.slice(0, 4)}` : fdm(x.periodo);
    const val = x.modo === 'yoy' ? `${csPct(x.valor)} <small>interanual</small>` : `${num(x.valor, x.unidad === 'índice' ? 1 : 2)}${x.unidad === '%' ? ' %' : ''}`;
    const tr = x.tendencia_3m == null ? '—' : `<span class="${x.tendencia_3m > 0 ? 'up' : x.tendencia_3m < 0 ? 'down' : 'flat'}">${x.tendencia_3m > 0 ? '+' : ''}${num(x.tendencia_3m, 2)} ${x.tendencia_unidad}</span>`;
    return `<tr><td data-label="Dato" style="text-align:left"><b>${esc(x.nombre)}</b><small>${esc(x.serie)} · capa ${esc(x.capa)}</small></td><td data-label="Dato de">${esc(per)}</td><td data-label="Valor">${val}</td><td data-label="Tendencia 3 meses">${tr}</td>
      <td data-label="Publicado el">${p && p.publicado ? `${esc(fdy(p.publicado))}<small>${esc(p.publicado_fuente || '')}</small>` : '<span class="sd-val">SIN DATO</span>'}</td>
      <td data-label="Registrado">${p && p.registrado ? esc(p.registrado_utc ? horaAct(p.registrado_utc) : fdy(p.registrado) + ' (solo fecha)') : '<span class="sd-val">SIN DATO</span>'}</td></tr>`;
  }).join('') + `</tbody></table>${footIn('FRED (RRSFS, PCEC96, DSPIC96, PSAVERT, TOTALSL, UMCSENT, DRCCLACBS); fechas de publicación de FRED/ALFRED (tabla de #/publicados)', M.fecha_datos, null, 'cada dato sale semanas después del mes al que se refiere')}</div>`;
  h += `<div class="sect"><h2>Reglas de la tesis (fijas)</h2><span class="more">impresas tal como las aplica el motor</span></div><div class="card"><details class="qa" open><summary>Cómo se calcula cada capa y el resultado</summary>${(M.reglas || []).map((r) => `<p style="margin:6px 0">${esc(r)}</p>`).join('')}</details><details class="qa"><summary>Avisos de contexto (no puntúan en la tesis)</summary>${(M.reglas_contexto || []).map((r) => `<p style="margin:6px 0">${esc(r)}</p>`).join('')}</details></div>`;
  if (M.errores && Object.keys(M.errores).length) h += `<div class="note">Fuentes sin dato en la última ejecución (SIN DATO, no se estima): ${Object.entries(M.errores).map(([k, v]) => esc(k + ': ' + String(v).slice(0, 90))).join(' · ')}</div>`;
  h += cnsRatio(RR);
  return h + '<div class="note">Hecho, interpretación, hipótesis y escenario van separados: los datos y los ratios son hechos; la tesis es una lectura con reglas fijas, no una recomendación de compra o venta.</div>';
}

function pageConsumo() {
  const h = head('Análisis', 'Consumo', '¿Está consumiendo la gente? Mercado (ratios de consumo discrecional frente a básico), datos reales (ventas, consumo, renta, ahorro, crédito, morosidad) y una tesis con reglas fijas que los compara.',
    'Datos públicos y gratuitos · sin IA en ejecución') + '<div id="cs-root"><div class="empty" style="height:180px">CARGANDO CONSUMO…</div></div>';
  MOUNT.push(async () => {
    const root = document.getElementById('cs-root');
    if (!root) return;
    let M = null;
    try { const r = await fetch('data/consumo.json?v=' + Date.now(), { cache: 'no-store' }); if (r.ok) M = await r.json(); } catch (e) { /* SIN DATO */ }
    if (document.getElementById('cs-root') !== root) return;
    if (!M || !M.tesis) { root.innerHTML = noData('Consumo (consumo.json)'); return; }
    let RR = null;
    try { const r2 = await fetch('data/consumo_ratio.json?v=' + Date.now(), { cache: 'no-store' }); if (r2.ok) RR = await r2.json(); } catch (e) { /* SIN DATO */ }
    f5.paint(root, () => consumoHtml(M, RR));
  });
  return h;
}

/* tarjeta «Contexto de ánimo»: fuente primaria = Universidad de Michigan (preliminar o final, con su fecha); FRED = respaldo y segunda fuente. Solo muestra lo que trae consumo.json. */
function cnsAnimo(A) {
  const d = A && A.dato, u = d && d.ultimo;
  if (!A || A.estado !== 'OK' || !u) return `<div class="empty" style="height:80px">SIN DATO · confianza del consumidor (U. Michigan) desde 1978</div>${foot('Universidad de Michigan (sca.isr.umich.edu) · FRED UMCSENT de respaldo', false, 'https://www.sca.isr.umich.edu/tables.html', 'solo contexto: no entra en la tesis')}`;
  const tipo = u.tipo === 'preliminar' ? 'PRELIMINAR' : 'FINAL', uf = d.ultimo_final, fr = d.fred;
  const pub = (x) => (x && x.publicado ? `publicado el ${esc(fdy(x.publicado))}` : `fecha de publicación SIN DATO (la web de Michigan no la indica${x && x.visto_utc ? '; NEXORA lo vio el ' + esc(fdy(x.visto_utc.slice(0, 10))) : ''})`);
  const edad = d.antiguedad_dias == null ? 'SIN DATO' : `${d.antiguedad_dias} día${d.antiguedad_dias === 1 ? '' : 's'}`;
  let h = `<div style="display:flex;gap:28px;flex-wrap:wrap;align-items:baseline"><div><div class="lab">Confianza U. Michigan</div><div class="big">${esc(num(A.valor, 1))}<small>${esc(fdm(A.periodo))} · ${tipo}</small></div></div>
    <div><div class="lab">Percentil desde ${esc(A.desde.slice(0, 4))}</div><div class="big ${A.zona_baja ? 'down' : ''}">${esc(num(A.percentil, 1))}<small>de 100 · ${esc(String(A.n))} meses</small></div></div>
    <div style="flex:1;min-width:220px"><p class="note" style="margin:0">Rango histórico: ${esc(num(A.minimo, 1))} (mínimo) a ${esc(num(A.maximo, 1))} (máximo). ${A.zona_baja ? 'Está en el ' + esc(num(A.umbral_percentil, 0)) + ' % más bajo de su historia.' : 'No está en el ' + esc(num(A.umbral_percentil, 0)) + ' % más bajo.'} El percentil usa el dato más reciente (${tipo.toLowerCase()}).</p>
    ${A.nota ? `<p class="note" style="margin:6px 0 0;color:var(--amber)"><b>${esc(A.nota.charAt(0).toUpperCase() + A.nota.slice(1))}:</b> la confianza está en mínimos pero la capa real de consumo sube.</p>` : ''}</div></div>`;
  h += `<div class="note" style="margin:10px 0 0"><span class="ck ${d.ambar ? 'par' : 'ok'}">Antigüedad ${edad}${d.ambar ? ' · más de ' + esc(String(d.umbral_antiguedad_dias)) + ' días' : ''}</span> desde el cierre del mes de referencia (ámbar si pasa de ${esc(String(d.umbral_antiguedad_dias))} días).</div>`;
  h += `<ul class="note" style="margin:8px 0 0;padding-left:18px"><li><b>${esc(u.texto)} · ${tipo}</b>: ${esc(num(u.valor, 1))} · ${pub(u)}.</li>`
    + (uf && uf.periodo !== u.periodo ? `<li><b>Último final</b>: ${esc(uf.texto)} · ${esc(num(uf.valor, 1))} · ${pub(uf)}.</li>` : '')
    + (fr ? `<li><b>FRED (respaldo y segunda fuente)</b>: ${esc(fr.texto)} · ${esc(num(fr.valor, 1))}${fr.meses_de_retraso > 0 ? ` — va ${esc(String(fr.meses_de_retraso))} mes${fr.meses_de_retraso > 1 ? 'es' : ''} por detrás de la Universidad (FRED publica este índice con retraso por licencia)` : ''}${fr.coincide === true ? '; coincide con la Universidad en ese mes' : fr.coincide === false ? '; <b>NO coincide</b> con la Universidad (manda la Universidad)' : ''}.</li>` : '<li><b>FRED</b>: SIN DATO.</li>')
    + '</ul>';
  if (d.origen === 'fred') h += `<div class="banner amber" style="margin:10px 0 0;border-radius:6px"><b>La Universidad de Michigan no respondió:</b> se muestra el dato de FRED (respaldo), que va con retraso.${(d.errores && Object.keys(d.errores).length) ? ' ' + esc(Object.values(d.errores).join(' · ')) : ''}</div>`;
  return h + foot('Universidad de Michigan (sca.isr.umich.edu) · FRED UMCSENT de respaldo', false, 'https://www.sca.isr.umich.edu/tables.html', `dato de ${esc(u.texto)} (${tipo.toLowerCase()}) · solo contexto: no entra en la tesis`);
}

Object.assign(window.EXTRA_PAGES, { consumo: pageConsumo });
