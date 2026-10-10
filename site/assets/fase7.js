/* NEXORA TERMINAL · fase 7: mapa mundial de bancos centrales y tono hawkish/dovish.
   Se carga después de app.js, mercados.js, fase4.js, fase5.js y fase6.js y reutiliza sus helpers. Todo texto dinámico pasa por esc(). */
'use strict';

/* ================================================================== MAPA MUNDIAL DE BANCOS CENTRALES */
const MAPA_CDN = {
  topo: 'https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-110m.json',
};
const SIN_COLOR = '#1a1f26';
const CAPAS = [
  { id: 'tipo', t: 'Tipo oficial', d: 'Tipo de política vigente (BIS)' },
  { id: 'mov', t: 'Último movimiento', d: 'Dirección y antigüedad del último cambio' },
  { id: 'c12', t: 'Cambio 12 m', d: 'Variación del tipo en 12 meses' },
  { id: 'infl', t: 'Inflación', d: 'IPC anual, FMI (año completo más reciente)' },
  { id: 'pib', t: 'PIB', d: 'Crecimiento real anual, FMI (año completo más reciente)' },
  { id: 'fx', t: 'Divisa vs USD 1 m', d: 'Cambio a 30 días frente al dólar (BIS)' },
];
const BINS = {
  tipo: { lim: [1, 2, 3, 5, 8, 15], col: ['#1f3347', '#2a4a68', '#3a6a92', '#6a8fa8', '#a58f55', '#c8a24a', '#e2bd5c'], et: ['< 1 %', '1 – 2 %', '2 – 3 %', '3 – 5 %', '5 – 8 %', '8 – 15 %', '≥ 15 %'] },
  c12: { lim: [-1.5, -0.5, -0.1, 0.1, 0.5, 1.5], col: ['#2a6aa8', '#3f86c4', '#6fa6d6', '#3a424d', '#dcc07a', '#c8a24a', '#a8812f'], et: ['≤ −1,5 pp', '−1,5 a −0,5', '−0,5 a −0,1', 'sin cambios (±0,1)', '+0,1 a +0,5', '+0,5 a +1,5', '≥ +1,5 pp'] },
  infl: { lim: [2, 3, 5, 10], col: ['#2b5a46', '#3f8a63', '#c8a24a', '#c8744a', '#c8463d'], et: ['< 2 %', '2 – 3 %', '3 – 5 %', '5 – 10 %', '≥ 10 %'] },
  pib: { lim: [0, 1, 2.5, 4], col: ['#c8463d', '#c8744a', '#8f8a5a', '#3f8a63', '#2f6f55'], et: ['< 0 %', '0 – 1 %', '1 – 2,5 %', '2,5 – 4 %', '≥ 4 %'] },
  fx: { lim: [-3, -1, -0.2, 0.2, 1, 3], col: ['#c8463d', '#c8744a', '#8a5a4a', '#3a424d', '#4a7a5a', '#3f8a63', '#2FA36B'], et: ['≤ −3 % (cae vs USD)', '−3 a −1 %', '−1 a −0,2 %', 'estable (±0,2 %)', '+0,2 a +1 %', '+1 a +3 %', '≥ +3 % (sube vs USD)'] },
};
const MOV_CAT = {
  'SUBE_RECIENTE': ['#e2bd5c', 'Subida en los últimos 90 días'], 'SUBE_ANTIGUA': ['#8a7332', 'Subida hace más de 90 días'],
  'BAJA_RECIENTE': ['#4a90d6', 'Bajada en los últimos 90 días'], 'BAJA_ANTIGUA': ['#2a4a6c', 'Bajada hace más de 90 días'],
};
const REGIONES = {
  mundo: { t: 'Mundo', ll: null }, europa: { t: 'Europa', ll: [[-14, 33], [42, 71]] }, asia: { t: 'Asia-Pacífico', ll: [[58, -12], [155, 56]] },
  america: { t: 'América', ll: [[-130, -56], [-30, 62]] }, africa: { t: 'África y Oriente Medio', ll: [[-20, -36], [62, 40]] },
};
let MAPA = { capa: 'tipo', sel: null, vb: null, geo: null, W: 960, H: 500, orden: 'tipo' };

function bin(capa, v) {
  const b = BINS[capa];
  let i = 0;
  while (i < b.lim.length && v >= b.lim[i]) i++;
  return i;
}
function porCodigo(B) { const m = {}; (B.bancos || []).forEach((x) => { m[x.codigo] = x; }); return m; }
function infoPais(B, bc, ccn) {
  const p = B.paises[ccn];
  if (!p) return null;
  return { p, banco: p.banco ? bc[p.banco] : null };
}
/* valor de un país en una capa → {v, color, txt}; v == null = SIN DATO */
function valorCapa(B, bc, ccn, capa) {
  const o = infoPais(B, bc, ccn);
  if (!o) return { v: null, color: SIN_COLOR, txt: 'SIN DATO' };
  const { p, banco: b } = o;
  const ok = b && !b.sin_dato;
  if (capa === 'tipo') return ok ? { v: b.tipo, color: BINS.tipo.col[bin('tipo', b.tipo)], txt: `${num(b.tipo, 2)} %` } : { v: null, color: SIN_COLOR, txt: 'SIN DATO' };
  if (capa === 'c12') return ok && b.cambio_12m != null ? { v: b.cambio_12m, color: BINS.c12.col[bin('c12', b.cambio_12m)], txt: `${sg(b.cambio_12m, 2)} pp` } : { v: null, color: SIN_COLOR, txt: 'SIN DATO' };
  if (capa === 'mov') {
    const m = ok && b.ultimo_movimiento;
    if (!m) return { v: null, color: SIN_COLOR, txt: 'SIN DATO' };
    const k = `${m.direccion}_${m.dias <= 90 ? 'RECIENTE' : 'ANTIGUA'}`;
    return { v: m.delta, color: MOV_CAT[k][0], txt: `${m.direccion === 'SUBE' ? '▲' : '▼'} ${sg(m.delta, 2)} pp · ${fdy(m.fecha)}` };
  }
  if (capa === 'infl') return p.inflacion && p.inflacion.valor != null ? { v: p.inflacion.valor, color: BINS.infl.col[bin('infl', p.inflacion.valor)], txt: `${num(p.inflacion.valor, 1)} % (${p.inflacion.ano})` } : { v: null, color: SIN_COLOR, txt: 'SIN DATO' };
  if (capa === 'pib') return p.pib && p.pib.valor != null ? { v: p.pib.valor, color: BINS.pib.col[bin('pib', p.pib.valor)], txt: `${sg(p.pib.valor, 1)} % (${p.pib.ano})` } : { v: null, color: SIN_COLOR, txt: 'SIN DATO' };
  if (capa === 'fx') return ok && b.fx && b.fx.cambio_1m_pct != null ? { v: b.fx.cambio_1m_pct, color: BINS.fx.col[bin('fx', b.fx.cambio_1m_pct)], txt: `${sg(b.fx.cambio_1m_pct, 2)} % (${b.moneda})` } : { v: null, color: SIN_COLOR, txt: b && b.moneda === 'USD' ? 'divisa base' : 'SIN DATO' };
  return { v: null, color: SIN_COLOR, txt: 'SIN DATO' };
}
function leyendaMapa(capa) {
  if (capa === 'mov') return Object.values(MOV_CAT).map(([c, e]) => [c, e]).concat([[SIN_COLOR, 'SIN DATO / sin banco en la muestra BIS']]);
  const b = BINS[capa];
  return b.col.map((c, i) => [c, b.et[i]]).concat([[SIN_COLOR, 'SIN DATO']]);
}
const nombrePais = (a2) => { try { return new Intl.DisplayNames(['es'], { type: 'region' }).of(a2); } catch (e) { return a2; } };
const eur2 = (v) => (v == null ? 'SIN DATO' : `${num(v, 2)} %`);

function fichaPais(B, bc, ccn) {
  const o = infoPais(B, bc, ccn);
  if (!o) return '<div class="note" style="margin:0">Territorio sin ficha en las fuentes (sin código ISO en la tabla de países). SIN DATO.</div>';
  const { p, banco: b } = o;
  const nom = nombrePais(p.a2);
  const zonaEuro = p.zona_euro;
  let h = `<div class="eyebrow" style="margin-bottom:2px">${zonaEuro ? 'Zona euro · tipo del BCE' : 'País'}</div><h3 style="font-family:var(--serif);font-weight:400;font-size:22px;margin:0 0 8px">${esc(nom)}</h3>`;
  if (b && !b.sin_dato) {
    const um = b.ultimo_movimiento, pr = b.proxima;
    h += `<div class="row2"><span>Banco central</span><span style="text-align:right">${esc(b.banco)}</span></div>
      <div class="row2"><span>Tipo oficial</span><span class="mono" style="font-size:16px">${num(b.tipo, 2)} %</span></div>
      <div class="row2"><span>Dato del BIS</span><span class="mono">${esc(fdy(b.fecha_dato))}</span></div>
      <div class="row2"><span>Último movimiento</span><span class="mono">${um ? `${um.direccion === 'SUBE' ? '▲' : '▼'} ${sg(um.delta, 2)} pp · ${esc(fdy(um.fecha))}` : 'SIN DATO'}</span></div>
      <div class="row2"><span>Cambio en 12 meses</span><span>${b.cambio_12m != null ? pill(b.cambio_12m, 2, ' pp', false) : SD}</span></div>
      <div class="row2"><span>Próxima reunión</span><span class="mono">${pr ? `${esc(fdy(pr.fecha))} · ${pr.dias} d` : 'SIN DATO'}</span></div>
      <div class="note" style="margin:2px 0 6px">${pr ? `Calendario oficial: <a class="src" href="${esc(pr.url)}" target="_blank" rel="noopener">fuente</a> (${esc(pr.lectura)}).` : esc(b.motivo_sin_proxima || '')}</div>
      <div class="row2"><span>Divisa vs USD (1 m)</span><span>${b.fx && b.fx.cambio_1m_pct != null ? `${pill(b.fx.cambio_1m_pct, 2, ' %', false)} <small style="color:var(--dim)">${esc(b.moneda)} · ${esc(fd(b.fx.fecha))}</small>` : (b.moneda === 'USD' ? 'divisa base' : SD)}</span></div>`;
  } else {
    h += `<div class="note" style="margin:0 0 6px">Sin banco central en la muestra de 38 del BIS: no hay tipo, movimiento ni calendario (SIN DATO).</div>`;
  }
  const i = p.inflacion, g = p.pib;
  h += `<div class="row2"><span>Inflación (FMI, ${i ? i.ano : B.ano_fmi})</span><span class="mono">${i && i.valor != null ? `${num(i.valor, 1)} %` : 'SIN DATO'}${i && i.prevision != null ? ` <small style="color:var(--dim)">previsión ${i.ano_prevision}: ${num(i.prevision, 1)} %</small>` : ''}</span></div>
    <div class="row2"><span>PIB real (FMI, ${g ? g.ano : B.ano_fmi})</span><span class="mono">${g && g.valor != null ? `${sg(g.valor, 1)} %` : 'SIN DATO'}${g && g.prevision != null ? ` <small style="color:var(--dim)">previsión ${g.ano_prevision}: ${sg(g.prevision, 1)} %</small>` : ''}</span></div>
    <div class="note" style="margin:8px 0 0">FMI DataMapper (WEO): el año ${B.ano_fmi} puede ser dato definitivo o estimación; la previsión de ${B.ano_prevision_fmi} es una PROYECCIÓN, no un dato. Fuentes: BIS, FMI, banco central.</div>`;
  return h;
}

function tablaBancos(B, orden) {
  const filas = (B.bancos || []).slice();
  const f = {
    tipo: (x) => -(x.tipo ?? -1e9), c12: (x) => -(x.cambio_12m ?? -1e9), prox: (x) => (x.proxima ? x.proxima.fecha : '9999'), pais: (x) => x.pais,
    infl: (x) => -((x.inflacion && x.inflacion.valor) ?? -1e9), fx: (x) => -(x.fx && x.fx.cambio_1m_pct != null ? x.fx.cambio_1m_pct : -1e9),
  }[orden] || ((x) => -(x.tipo ?? -1e9));
  filas.sort((a, b) => { const A = f(a), Bv = f(b); return A < Bv ? -1 : A > Bv ? 1 : 0; });
  const th = (k, t) => `<th data-ord="${k}" style="cursor:pointer;${orden === k ? 'color:var(--amber)' : ''}">${t}${orden === k ? ' ▾' : ''}</th>`;
  let h = `<table class="t"><thead><tr><th>Banco central</th>${th('pais', 'País')}${th('tipo', 'Tipo')}<th>Dato BIS</th><th>Último mov.</th>${th('c12', '12 m')}${th('prox', 'Próxima reunión')}${th('fx', 'Divisa 1 m')}${th('infl', 'Inflación')}<th>PIB</th></tr></thead><tbody>`;
  h += filas.map((b) => {
    if (b.sin_dato) return `<tr data-cod="${b.codigo}"><td>${esc(b.banco)}</td><td style="text-align:left">${esc(b.pais)}</td><td colspan="8" style="text-align:left;color:var(--dim)">SIN DATO · ${esc(b.motivo || '')}</td></tr>`;
    const um = b.ultimo_movimiento, pr = b.proxima;
    return `<tr data-cod="${b.codigo}" style="cursor:pointer"><td>${esc(b.banco)}</td><td style="text-align:left;font-family:var(--sans)">${esc(b.pais)}</td><td><b>${num(b.tipo, 2)} %</b></td><td>${esc(fd(b.fecha_dato))}</td>
      <td>${um ? `<span class="${um.delta > 0 ? 'amber' : 'up'}" style="${um.delta < 0 ? 'color:#6fa6d6' : ''}">${um.delta > 0 ? '▲' : '▼'} ${sg(um.delta, 2)}</span> <small>${esc(fd(um.fecha))} ${esc(um.fecha.slice(0, 4))}</small>` : 'SIN DATO'}</td>
      <td>${b.cambio_12m != null ? pill(b.cambio_12m, 2, '', false) : SD}</td>
      <td>${pr ? `<span class="cd">${esc(fdy(pr.fecha))}</span> <small>${pr.dias} d</small>` : '<span class="sd-val" style="font-size:11px" title="' + esc(b.motivo_sin_proxima || '') + '">SIN DATO</span>'}</td>
      <td>${b.fx && b.fx.cambio_1m_pct != null ? pill(b.fx.cambio_1m_pct, 2, ' %', false) : (b.moneda === 'USD' ? '<span class="pill flat">base</span>' : '<span class="pill flat">—</span>')}</td>
      <td>${b.inflacion && b.inflacion.valor != null ? `${num(b.inflacion.valor, 1)} %` : '—'}</td><td>${b.pib && b.pib.valor != null ? `${sg(b.pib.valor, 1)} %` : '—'}</td></tr>`;
  }).join('');
  return h + '</tbody></table>';
}

function pageMapa() {
  const B = D.bancos;
  const stamp = `Tipos BIS hasta ${B && B.bancos ? esc(fdy((B.bancos.filter((b) => b.fecha_dato).map((b) => b.fecha_dato).sort().pop()) || '')) : 'SIN DATO'} · descargado ${B && B.generado_utc ? esc(horaAct(B.generado_utc)) : 'SIN DATO'}`;
  let h = head('Análisis', 'Bancos centrales del mundo', 'Tipo oficial, último movimiento y cambio a 12 meses de 38 bancos centrales (BIS), con inflación y PIB del FMI y la divisa frente al dólar. Clic en un país para ver su ficha. Zona euro: sus países comparten el tipo del BCE.', stamp);
  h += fallo('bancos');
  if (!B || !B.bancos) return h + noData('BIS · tipos de política (WS_CBPOL)');
  const bc = porCodigo(B);
  const C = B.contador || {}, L = B.lectura || {};
  const g8 = (B.grandes || []).map((k) => bc[k]).filter((x) => x && !x.sin_dato);
  const g8txt = g8.map((x) => `${x.banco.replace(/ \(.*\)/, '').replace('Banco Central Europeo', 'BCE').replace('Reserva Federal', 'Fed').replace('Banco de Japón', 'BoJ')} ${num(x.tipo, 2)} %`).slice(0, 4).join(' · ');
  const prox = (B.proximas_reuniones || []).slice(0, 4).map((x) => `${x.banco.replace(/ \(.*\)/, '')} ${fd(x.fecha)} (${x.dias} d)`).join(' · ');
  h += essential(`${C.sube} de ${C.total} bancos centrales han subido tipos en los últimos 12 meses y ${C.baja} los han bajado; ${C.sin_cambios} no se han movido (BIS, ${esc(fdy(B.fecha))}). ${esc(g8txt)}.`,
    `Lectura de liquidez global: <b style="color:var(--text)">${esc(L.etiqueta || 'SIN DATO')}</b>. ${esc(L.texto || '')} <span class="tag sin">CRITERIO NEXORA</span> (regla abajo).`,
    prox ? `Próximas reuniones con calendario oficial: ${esc(prox)}.` : 'Ningún calendario oficial legible en esta ejecución (SIN DATO).');

  /* contador */
  const tonoAmp = C.tipos === 'ENDURECIMIENTO' ? 'amber' : C.tipos === 'RELAJACIÓN' ? 'up' : 'flat';
  h += '<div class="sect"><h2>Contador global · 12 meses</h2><span class="more">cuántos bancos suben, bajan o no se mueven</span></div><div class="grid g4">';
  h += `<div class="card kpi"><div class="lab">Suben tipos</div><div class="exp">Tipo hoy ≥ tipo hace 12 meses + 0,10 pp</div><div class="big amber">${C.sube}<small>de ${C.total}</small></div><div class="note" style="margin:6px 0 0">${(C.bancos_sube || []).map((k) => esc(k)).join(' · ')}</div></div>`;
  h += `<div class="card kpi"><div class="lab">Bajan tipos</div><div class="exp">Tipo hoy ≤ tipo hace 12 meses − 0,10 pp</div><div class="big" style="color:#6fa6d6">${C.baja}<small>de ${C.total}</small></div><div class="note" style="margin:6px 0 0">${(C.bancos_baja || []).map((k) => esc(k)).join(' · ')}</div></div>`;
  h += `<div class="card kpi"><div class="lab">Sin cambios</div><div class="exp">Dentro de ±0,10 pp</div><div class="big">${C.sin_cambios}<small>de ${C.total}</small></div>${foot('BIS · WS_CBPOL', B.fecha, B.fuentes.tipos.url)}</div>`;
  const bal = B.balance;
  h += `<div class="card kpi"><div class="lab">Liquidez global <span class="tag sin" style="margin-left:4px">CRITERIO NEXORA</span></div><div class="exp">Tipos de 38 bancos + balance Fed, BCE y BoJ</div><div class="big ${tonoAmp}" style="font-size:15px;line-height:1.25;font-family:var(--serif)">${esc(L.etiqueta || 'SIN DATO')}</div>
    <div class="note" style="margin:6px 0 0">Amplitud de tipos ${C.amplitud != null ? sg(C.amplitud, 2) : '—'} (${esc(C.tipos || '—')}) · balance ${bal ? `${esc(bal.estado)} ${sg(bal.var_12m_pct, 1)} % (${esc(fd(bal.fecha))})` : 'SIN DATO'}</div></div>`;
  h += '</div>';
  h += `<details class="qa card" style="margin-top:10px"><summary>Regla de la lectura de liquidez global (CRITERIO NEXORA)</summary><p>${esc(L.regla || '')}</p></details>`;

  /* mapa */
  h += '<div class="sect"><h2>Mapa</h2><span class="more">cambia la capa, pulsa un país</span></div>';
  h += `<div class="filters" id="capas">${CAPAS.map((c) => `<button class="fbtn ${MAPA.capa === c.id ? 'on' : ''}" data-capa="${c.id}" title="${esc(c.d)}">${esc(c.t)}</button>`).join('')}</div>`;
  h += `<div class="grid g21 stretch"><div class="card" style="padding:10px 12px"><div class="map-bar"><div class="filters" id="regiones" style="margin:0">${Object.entries(REGIONES).map(([k, r]) => `<button class="fbtn" data-reg="${k}">${esc(r.t)}</button>`).join('')}</div>
      <div class="map-zoom"><button class="fbtn" id="mz-mas" aria-label="Acercar">+</button><button class="fbtn" id="mz-menos" aria-label="Alejar">−</button></div></div>
    <div class="mapwrap" id="mapwrap"><div class="empty" style="height:100%">CARGANDO MAPA…</div></div>
    <div class="maplegend" id="maplegend"></div><div class="map-tip" id="maptip" hidden></div>
    <div class="note" id="mapcap" style="margin:6px 0 0"></div>
    ${foot('BIS (tipos y divisas), FMI DataMapper (WEO), Natural Earth vía world-atlas@2.0.2', B.fecha, B.fuentes.tipos.url)}</div>
    <div class="card" id="ficha"><div class="note" style="margin:0">Pulsa un país del mapa o una fila de la tabla para ver su ficha.</div></div></div>`;

  /* próximas reuniones */
  h += '<div class="sect"><h2>Próximas reuniones</h2><span class="more">solo bancos con calendario oficial legible; el resto, SIN DATO</span></div><div class="card">';
  const pm = B.proximas_reuniones || [];
  h += pm.length ? pm.map((x) => `<div class="evrow"><span class="when">${esc(fdd(x.fecha))}</span><span class="what">${esc(x.banco)}<span class="aff">dentro de ${x.dias} días · tipo actual ${num(bc[x.codigo].tipo, 2)} %</span></span></div>`).join('') : SD;
  h += `<div class="note">Calendarios leídos de las webs oficiales de Fed, BCE, BoE, SNB, BoC, BoJ y Riksbank en cada ejecución; el del RBA está verificado a mano en su nota oficial. Los ${B.n_bancos - (B.con_calendario || 0)} bancos restantes figuran como SIN DATO: no se estima ninguna fecha.</div>
    ${foot('Calendarios oficiales de cada banco central', B.fecha, null)}</div>`;

  /* tabla */
  h += '<div class="sect"><h2>Los 38 bancos centrales</h2><span class="more">pulsa una cabecera para ordenar · pulsa una fila para ver la ficha</span></div><div class="card pad0 scroll" id="tablabancos">' + tablaBancos(B, MAPA.orden) + footIn('BIS WS_CBPOL (tipos), BIS WS_XRU (divisas), FMI WEO', B.fecha, B.fuentes.tipos.url, 'inflación y PIB: año ' + B.ano_fmi) + '</div>';

  /* histórico de los 8 grandes */
  const H8 = B.historico8 || {};
  const COLS = ['#C8A24A', '#6C8EBF', '#E6E8EB', '#9B87C9', '#2FA36B', '#C8463D', '#8A93A0', '#d9885a'];
  const nombresCortos = { US: 'Fed', XM: 'BCE', JP: 'BoJ', GB: 'BoE', CH: 'SNB', CA: 'BoC', AU: 'RBA', NZ: 'RBNZ' };
  h += '<div class="sect"><h2>Histórico de los 8 grandes desde 2010</h2><span class="more">tipo de política (escalones en cada cambio)</span></div><div class="card chartcard">';
  h += lw('cBanc8', (B.grandes || []).map((k, i) => ({ name: nombresCortos[k] || k, color: COLS[i % 8], data: H8[k], prec: 2, step: true, w: 2 })), { tall: true });
  h += `${foot('BIS · WS_CBPOL (puntos de cambio guardados en data/historico_tipos_bancos.csv)', B.fecha, B.fuentes.tipos.url)}</div>`;

  /* notas */
  const ar = B.series_sin_actualizar_bis || {};
  h += `<div class="note">La muestra son los 38 bancos centrales con serie viva en el dataset WS_CBPOL del BIS. ${Object.keys(ar).length ? `Se excluye ${Object.entries(ar).map(([k, v]) => `${esc(k === 'AR' ? 'Argentina' : k)} (sin actualizar en el BIS desde ${esc(fdy(v))})`).join(', ')}.` : ''}
    Zona euro: ${B.eurozona ? B.eurozona.n : '—'} países con el euro como divisa según el BIS (el recuento oficial a 2026 incluye a Bulgaria). El BIS publica un único valor por banco (para la Fed, el punto medio del rango objetivo).
    El último movimiento y el cambio a 12 meses se calculan sobre la serie diaria del BIS (fecha de entrada en vigor). Inflación y PIB son anuales (FMI WEO); la divisa es la media diaria del BIS con unos días de retraso.
    Memoria permanente: <a class="src" href="https://github.com/komonartisans-ops/nexora-terminal/blob/main/data/historico_tipos_bancos.csv" target="_blank" rel="noopener">data/historico_tipos_bancos.csv</a>.</div>`;
  MOUNT.push(() => montarMapa(B, bc));
  return h + errores(B.errores);
}

function dibujaCapa(B, bc) {
  const w = $('#mapwrap');
  if (!w || !MAPA.geo) return;
  $$('path[data-ccn]', w).forEach((el) => {
    const v = valorCapa(B, bc, el.dataset.ccn, MAPA.capa);
    el.setAttribute('fill', v.color);
    el.classList.toggle('sel', el.dataset.ccn === MAPA.sel);
  });
  const lg = $('#maplegend');
  if (lg) lg.innerHTML = leyendaMapa(MAPA.capa).map(([c, e]) => `<span><i style="background:${c}"></i>${esc(e)}</span>`).join('');
  const cap = $('#mapcap');
  const c = CAPAS.find((x) => x.id === MAPA.capa);
  if (cap) cap.innerHTML = `<b style="color:var(--text)">${esc(c.t)}</b> · ${esc(c.d)}. ${MAPA.capa === 'infl' || MAPA.capa === 'pib' ? `Año ${B.ano_fmi} (FMI WEO; dato o estimación).` : MAPA.capa === 'fx' ? 'Verde = la divisa local se aprecia frente al dólar; rojo = se deprecia.' : MAPA.capa === 'tipo' ? 'Zona euro: tipo del BCE para los países que usan el euro.' : ''}`;
}
function seleccion(B, bc, ccn) {
  MAPA.sel = ccn;
  const f = $('#ficha');
  if (f) f.innerHTML = fichaPais(B, bc, ccn);
  $$('#mapwrap path[data-ccn]').forEach((el) => el.classList.toggle('sel', el.dataset.ccn === ccn));
}
function setVB(vb) {
  MAPA.vb = vb;
  const s = $('#mapwrap svg');
  if (s) s.setAttribute('viewBox', `${vb.x} ${vb.y} ${vb.w} ${vb.h}`);
}
async function montarMapa(B, bc) {
  const w = $('#mapwrap');
  if (!w) return;
  const tablaEl = $('#tablabancos');
  const enlazarTabla = () => {
    tablaEl.addEventListener('click', (e) => {
      const th = e.target.closest('th[data-ord]');
      if (th) { MAPA.orden = th.dataset.ord; tablaEl.firstElementChild.outerHTML = tablaBancos(B, MAPA.orden); return; }
      const tr = e.target.closest('tr[data-cod]');
      if (!tr) return;
      const ccn = Object.keys(B.paises).find((k) => B.paises[k].banco === tr.dataset.cod && (B.bancos.find((b) => b.codigo === tr.dataset.cod).iso3 === B.paises[k].a3 || tr.dataset.cod === 'XM' && B.paises[k].a3 === 'DEU'));
      if (ccn) { seleccion(B, bc, ccn); $('#ficha').scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
    });
  };
  enlazarTabla();
  $('#capas').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-capa]'); if (!b) return;
    MAPA.capa = b.dataset.capa;
    $$('#capas .fbtn').forEach((x) => x.classList.toggle('on', x === b));
    dibujaCapa(B, bc);
  });
  if (!window.d3 || !window.topojson) { w.innerHTML = '<div class="empty" style="height:100%">SIN DATO · no se pudieron cargar las librerías del mapa (d3-geo / topojson)</div>'; return; }
  let topo;
  try { topo = await (await fetch(MAPA_CDN.topo)).json(); } catch (e) { w.innerHTML = '<div class="empty" style="height:100%">SIN DATO · no se pudo cargar world-atlas@2.0.2</div>'; return; }
  const feats = topojson.feature(topo, topo.objects.countries).features.filter((f) => String(f.id).padStart(3, '0') !== '010'); // sin Antártida
  const proj = d3.geoNaturalEarth1().fitSize([MAPA.W, MAPA.H], { type: 'FeatureCollection', features: feats });
  const path = d3.geoPath(proj);
  MAPA.proj = proj;
  const paths = feats.map((f) => {
    const ccn = String(f.id).padStart(3, '0');
    return `<path data-ccn="${ccn}" data-n="${esc(f.properties.name)}" d="${path(f) || ''}" fill="${SIN_COLOR}"></path>`;
  }).join('');
  w.innerHTML = `<svg viewBox="0 0 ${MAPA.W} ${MAPA.H}" role="img" aria-label="Mapa mundial de bancos centrales" preserveAspectRatio="xMidYMid meet">${paths}</svg>`;
  MAPA.geo = true;
  setVB({ x: 0, y: 0, w: MAPA.W, h: MAPA.H });
  dibujaCapa(B, bc);
  if (MAPA.sel) seleccion(B, bc, MAPA.sel);

  const svg = $('svg', w), tip = $('#maptip');
  svg.addEventListener('pointermove', (e) => {
    const p = e.target.closest('path[data-ccn]');
    if (!p || e.pointerType === 'touch' || MAPA.drag) { tip.hidden = true; return; }
    const ccn = p.dataset.ccn, o = infoPais(B, bc, ccn);
    const v = valorCapa(B, bc, ccn, MAPA.capa);
    const nom = o ? nombrePais(o.p.a2) : p.dataset.n;
    const r = w.getBoundingClientRect();
    tip.innerHTML = `<b>${esc(nom)}</b><span>${esc(CAPAS.find((c) => c.id === MAPA.capa).t)}: ${esc(v.txt)}</span>`;
    tip.hidden = false;
    tip.style.left = Math.min(r.width - 190, Math.max(4, e.clientX - r.left + 12)) + 'px';
    tip.style.top = Math.max(4, e.clientY - r.top + 12) + 'px';
  });
  svg.addEventListener('pointerleave', () => { tip.hidden = true; });
  /* clic = ficha; arrastrar = mover el mapa */
  let ini = null;
  svg.addEventListener('pointerdown', (e) => { ini = { x: e.clientX, y: e.clientY, vb: { ...MAPA.vb }, mov: false }; MAPA.drag = false; });
  svg.addEventListener('pointermove', (e) => {
    if (!ini) return;
    const dx = e.clientX - ini.x, dy = e.clientY - ini.y;
    if (!ini.mov && Math.hypot(dx, dy) < 6) return;
    ini.mov = true; MAPA.drag = true; tip.hidden = true;
    const k = ini.vb.w / svg.getBoundingClientRect().width;
    setVB({ ...ini.vb, x: ini.vb.x - dx * k, y: ini.vb.y - dy * k });
  });
  const fin = (e) => {
    if (ini && !ini.mov) {
      const p = document.elementFromPoint(e.clientX, e.clientY);
      const t = p && p.closest && p.closest('path[data-ccn]');
      if (t) seleccion(B, bc, t.dataset.ccn);
    }
    ini = null; setTimeout(() => { MAPA.drag = false; }, 0);
  };
  svg.addEventListener('pointerup', fin);
  svg.addEventListener('pointercancel', () => { ini = null; MAPA.drag = false; });
  const zoom = (k) => {
    const v = MAPA.vb, cx = v.x + v.w / 2, cy = v.y + v.h / 2, nw = Math.min(MAPA.W, Math.max(60, v.w * k)), nh = nw * MAPA.H / MAPA.W;
    setVB({ x: cx - nw / 2, y: cy - nh / 2, w: nw, h: nh });
  };
  $('#mz-mas').addEventListener('click', () => zoom(1 / 1.6));
  $('#mz-menos').addEventListener('click', () => zoom(1.6));
  $('#regiones').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-reg]'); if (!b) return;
    const r = REGIONES[b.dataset.reg];
    if (!r.ll) { setVB({ x: 0, y: 0, w: MAPA.W, h: MAPA.H }); return; }
    const a = proj(r.ll[0]), c = proj(r.ll[1]);
    const x0 = Math.min(a[0], c[0]), x1 = Math.max(a[0], c[0]), y0 = Math.min(a[1], c[1]), y1 = Math.max(a[1], c[1]);
    let ww = (x1 - x0) * 1.08, hh = ww * MAPA.H / MAPA.W;
    if (hh < (y1 - y0) * 1.08) { hh = (y1 - y0) * 1.08; ww = hh * MAPA.W / MAPA.H; }
    setVB({ x: (x0 + x1) / 2 - ww / 2, y: (y0 + y1) / 2 - hh / 2, w: ww, h: hh });
  });
}

/* ================================================================== TONO HAWKISH / DOVISH */
const NIVEL_CLS = { HAWKISH: 'baj', DOVISH: 'alc', NEUTRAL: 'sin', 'NO PUNTÚA': 'sd', 'SIN PUNTUACIÓN': 'sd' };
const TONO_BCOS = ['Fed', 'BCE', 'BoJ'];
const AREA_TONO = { Fed: 'US', BCE: 'XM', BoJ: 'JP' };
function tonoBar(i) {
  if (i == null) return '<div class="tonebar sd"></div>';
  const p = Math.max(0, Math.min(100, (i + 1) * 50));
  return `<div class="tonebar" title="${num(i, 2)}"><i style="left:${p}%"></i></div><div class="tonebar-l"><span>dovish −1</span><span>0</span><span>+1 hawkish</span></div>`;
}
const nivelTag = (n) => `<span class="tag ${NIVEL_CLS[n] || 'sin'}">${esc(n || 'SIN DATO')}</span>`;
const cambioFlecha = (c) => (c == null ? '<span class="pill flat">—</span>' : `<span class="pill ${c >= 0.1 ? 'down' : c <= -0.1 ? 'up' : 'flat'}">${c > 0 ? '▲' : c < 0 ? '▼' : '▬'} ${sg(c, 2)}</span>`);
const topTerminos = (t, n = 6) => Object.entries(t || {}).sort((a, b) => b[1] - a[1]).slice(0, n).map(([k, v]) => `${esc(k)}${v > 1 ? ' ×' + v : ''}`).join(' · ');

function pageTono() {
  const T = D.tono;
  let h = head('Análisis', 'Tono de bancos centrales', 'Cuánto del lenguaje de los comunicados y discursos de la Fed, el BCE y el BoJ pertenece a un diccionario «hawkish» (endurecimiento) frente a otro «dovish» (relajación). Lectura léxica con diccionario publicado y sin IA; abajo, cuánto acierta frente a la siguiente decisión de tipos.',
    `Actualizado: ${T && T.generado_utc ? esc(horaAct(T.generado_utc)) : 'SIN DATO'} · diccionario ${T ? esc(T.diccionario.version) : ''} · solo webs oficiales <span class="tag sin" style="margin-left:6px">CRITERIO NEXORA</span>`);
  h += fallo('tono');
  if (!T || !T.comunicados) return h + noData('Tono de bancos centrales');
  const U = T.ultimo || {}, V = T.validacion || {}, R = T.reglas || {};
  const l = TONO_BCOS.map((b) => (U[b] ? `${b} ${num(U[b].indice, 2)} (${U[b].nivel.toLowerCase()}${U[b].cambio_txt && U[b].cambio_txt !== 'SIN CAMBIO' ? ', ' + U[b].cambio_txt.toLowerCase() : ''})` : `${b} SIN DATO`)).join(' · ');
  const supera = TONO_BCOS.filter((b) => V[b] && V[b].n && V[b].nivel.pct > Math.max(V[b].base_mantiene.pct, V[b].base_repite.pct));
  const mejor = (b) => Math.max(V[b].base_mantiene.pct, V[b].base_repite.pct);
  h += essential(`Último comunicado: ${esc(l)}. Escala −1 (todo dovish) a +1 (todo hawkish).`,
    supera.length ? `En ${supera.map(esc).join(', ')} el tono acierta más que las líneas base.` : `Hecho: en ninguno de los tres bancos el tono, por sí solo, acierta más veces la siguiente decisión que la regla «siempre mantiene» o «repetir la decisión anterior» (${TONO_BCOS.filter((b) => V[b] && V[b].n).map((b) => `${b} ${num(V[b].nivel.pct, 0)} % frente a ${num(mejor(b), 0)} %`).join(' · ')}). Hipótesis: el léxico recoge sobre todo la fase del ciclo de tipos, no un giro anticipado.`,
    'El próximo comunicado de cada banco (calendario en «Bancos centrales del mundo») y el cambio de tono frente al anterior; los discursos de cada orador se comparan con su intervención previa.');

  /* tarjetas por banco */
  h += '<div class="sect"><h2>Último comunicado de política monetaria</h2><span class="more">índice (H − D)/(H + D) · cambio frente al comunicado anterior</span></div><div class="grid g3">';
  h += TONO_BCOS.map((b) => {
    const u = U[b];
    if (!u) return `<div class="card kpi"><div class="lab">${b}</div><div class="big">${SD}</div>${foot(T.fuentes[b], false)}</div>`;
    const ser = (T.comunicados[b] || []).filter((x) => x.indice != null);
    return `<div class="card kpi"><div class="lab">${b} · ${esc(u.tipo)}</div><div class="exp">${esc(fdy(u.fecha))}${u.anterior ? ` · anterior ${esc(fdy(u.anterior.fecha))} (${num(u.anterior.indice, 2)})` : ''}</div>
      <div class="big">${sg(u.indice, 2)}<small>${nivelTag(u.nivel)}</small></div><div class="chg">${cambioFlecha(u.cambio)} <span style="color:var(--dim);font-size:10.5px">${esc(u.cambio_txt || '')}</span></div>
      ${tonoBar(u.indice)}
      <div class="note" style="margin:6px 0 2px"><b style="color:var(--text)">Términos:</b> ${u.h} hawkish · ${u.d} dovish · ${u.palabras} palabras</div>
      <div class="note" style="margin:0;color:var(--muted)">${topTerminos(u.terminos, 7)}</div>
      ${foot(T.fuentes[b], u.fecha, u.url, `${ser.length} comunicados desde 2015`)}</div>`;
  }).join('') + '</div>';

  /* gráficos tono + tipo */
  h += '<div class="sect"><h2>Tono y tipo oficial desde 2015</h2><span class="more">ámbar = índice de tono (eje der.) · azul = tipo de política (eje izq.)</span></div><div class="grid g3">';
  const B = D.bancos;
  TONO_BCOS.forEach((b, i) => {
    const ser = (T.comunicados[b] || []).filter((x) => x.indice != null).map((x) => [x.fecha, x.indice]);
    const tipo = B && B.historico8 ? (B.historico8[AREA_TONO[b]] || []).filter((x) => x[0] >= '2015-01-01') : [];
    h += `<div class="card chartcard" style="min-height:300px"><h3>${b}</h3><div class="sub">${ser.length} comunicados</div>${lw('cTono' + i, [{ name: 'Tipo', color: COL.blue, data: tipo, prec: 2, step: true, scale: 'left', w: 1 }, { name: 'Tono', color: COL.amber, data: ser, prec: 2 }], { left: true, range: false })}${foot(T.fuentes[b], false, null, 'tono: NEXORA · tipo: BIS')}</div>`;
  });
  h += '</div>';

  /* validación */
  h += `<div class="sect"><h2>Validación: ¿el tono anticipa la siguiente decisión?</h2><span class="more">desde 2015 · tono de cada comunicado frente al tipo de la reunión siguiente</span></div>`;
  h += `<div class="card"><div class="note" style="margin-top:0">Regla fija (definida antes de ver el resultado): el comunicado es HAWKISH si el índice es ≥ +${num(R.umbral_nivel, 2)}, DOVISH si es ≤ −${num(R.umbral_nivel, 2)} y NEUTRAL entre medias. Se predice SUBE, BAJA o MANTIENE y se compara con la variación del tipo de política (BIS) en la reunión siguiente (SUBE ≥ +${num(R.umbral_decision_pp, 2)} pp, BAJA ≤ −${num(R.umbral_decision_pp, 2)} pp, medida de ${R.ventana_decision_dias} días tras la reunión). La segunda regla usa el cambio de tono frente al comunicado anterior (± ${num(R.umbral_cambio, 2)}). Las líneas base son «siempre mantiene» y «repetir la decisión de la reunión anterior».</div></div>`;
  h += '<div class="card pad0 scroll" style="margin-top:10px"><table class="t"><thead><tr><th>Banco</th><th>Muestra</th><th>Periodo</th><th>Acierto · nivel</th><th>Acierto · cambio</th><th>Base «siempre mantiene»</th><th>Base «repite decisión»</th><th>Movimientos acertados (nivel)</th><th>Correlación tono ↔ Δ tipo</th><th>Tono ≥ mejor base</th></tr></thead><tbody>';
  h += TONO_BCOS.map((b) => {
    const x = V[b];
    if (!x || !x.n) return `<tr><td>${b}</td><td colspan="9" style="text-align:left;color:var(--dim)">SIN DATO · ${esc((x && x.motivo) || '')}</td></tr>`;
    const gana = x.nivel.pct > mejor(b);
    return `<tr><td><b>${b}</b></td><td>n = ${x.n}</td><td>${esc(fdy(x.desde))} → ${esc(fdy(x.hasta))}</td><td><b>${num(x.nivel.pct, 1)} %</b> <small>${x.nivel.aciertos}/${x.nivel.n}</small></td>
      <td>${num(x.cambio.pct, 1)} % <small>${x.cambio.aciertos}/${x.cambio.n}</small></td><td>${num(x.base_mantiene.pct, 1)} % <small>${x.base_mantiene.aciertos}/${x.base_mantiene.n}</small></td>
      <td>${num(x.base_repite.pct, 1)} % <small>${x.base_repite.aciertos}/${x.base_repite.n}</small></td><td>${x.nivel.mov_aciertos}/${x.nivel.mov_n} <small>${x.nivel.mov_opuestos} opuestos</small></td>
      <td>${x.correlacion != null ? sg(x.correlacion, 2) : '—'}</td><td><span class="ck ${gana ? 'ok' : 'no'}">${gana ? 'SÍ' : 'NO'}</span></td></tr>`;
  }).join('');
  const t = V._total;
  if (t && t.nivel.n) h += `<tr class="grp"><td><b>Total</b></td><td>n = ${t.nivel.n}</td><td>2015 →</td><td><b>${num(t.nivel.pct, 1)} %</b> <small>${t.nivel.aciertos}/${t.nivel.n}</small></td><td>${num(t.cambio.pct, 1)} % <small>${t.cambio.aciertos}/${t.cambio.n}</small></td><td>${num(t.base_mantiene.pct, 1)} %</td><td colspan="4"></td></tr>`;
  h += `</tbody></table>${footIn('Comunicados oficiales + tipos del BIS · cálculo NEXORA', T.fecha, null, 'muestra = reuniones con comunicado y decisión siguiente conocida')}</div>`;
  h += `<div class="note">Cómo leerlo: la regla de tres categorías pierde frente a «siempre mantiene» porque casi todas las reuniones no mueven el tipo y el diccionario rara vez da NEUTRAL (el BoJ casi siempre sale dovish por su vocabulario de «acomodación»). La correlación mide otra cosa: si un tono más hawkish se asocia a un cambio de tipo mayor en la reunión siguiente (positiva = sí). Es correlación, no causalidad, y parte de ella es inercia del ciclo. Con muestras de 90–100 reuniones y pocos movimientos, las cifras son orientativas.
    La columna «misma reunión» del archivo tono.json mide cuánto del tono es simple eco de la decisión que acompaña al comunicado.</div>`;

  /* oradores */
  const OR = T.oradores || [];
  h += `<div class="sect"><h2>Discursos por orador</h2><span class="more">${T.n_discursos_puntuados} puntúan de ${T.n_discursos} desde 2025 · solo si hay ≥ ${R.min_terminos_discurso} términos y ≥ ${R.min_menciones_tema} menciones de política monetaria o inflación</span></div>`;
  h += '<div class="card pad0 scroll"><table class="t"><thead><tr><th>Orador</th><th>Banco</th><th>Último discurso</th><th>Índice</th><th>Nivel</th><th>Anterior</th><th>Cambio</th><th>Media</th><th>n</th></tr></thead><tbody>';
  h += OR.length ? OR.slice(0, 40).map((o) => `<tr><td>${esc(o.orador)}</td><td style="text-align:left;font-family:var(--sans)">${esc(o.banco)}</td><td style="text-align:left;font-family:var(--sans);white-space:normal;max-width:300px"><a class="src" href="${esc(o.ultimo.url)}" target="_blank" rel="noopener">${esc(o.ultimo.titulo.slice(0, 70))}</a> <small>${esc(fdy(o.ultimo.fecha))}</small></td>
      <td><b>${sg(o.ultimo.indice, 2)}</b></td><td>${nivelTag(o.ultimo.nivel)}</td><td>${o.anterior ? `${sg(o.anterior.indice, 2)} <small>${esc(fd(o.anterior.fecha))}</small>` : '—'}</td><td>${cambioFlecha(o.cambio)}</td><td>${sg(o.media, 2)}</td><td>${o.n}</td></tr>`).join('')
    : '<tr><td colspan="9" style="text-align:left;color:var(--dim)">SIN DATO</td></tr>';
  h += `</tbody></table>${footIn('Webs oficiales de Fed, BCE y BoJ · diccionario NEXORA', T.fecha)}</div>`;

  const DS = (T.discursos || []).slice(0, 40);
  h += '<div class="sect"><h2>Discursos recientes</h2><span class="more">fecha · orador · título · índice</span></div><div class="card pad0">';
  h += DS.length ? DS.map((d) => `<div class="nrow"><span class="nh">${esc(fd(d.fecha))}</span><span class="nb">${esc(d.banco)}</span><span class="nt"><span class="ntipo">${esc(d.orador)}</span><a href="${esc(d.url)}" target="_blank" rel="noopener">${esc(d.titulo)}</a>
      <span style="display:block;margin-top:3px">${d.indice != null ? `${nivelTag(d.nivel)} <span class="mono">${sg(d.indice, 2)}</span> ${d.cambio != null ? cambioFlecha(d.cambio) + ' <small style="color:var(--dim)">frente al ' + esc(fd(d.anterior_fecha)) + '</small>' : ''}` : `<span class="tag sd">NO PUNTÚA</span> <small style="color:var(--dim)">${d.n_terminos} términos · ${d.menciones_tema} menciones del tema</small>`}</span></span></div>`).join('') : `<div class="note" style="padding:12px 16px">SIN DATO</div>`;
  h += `${footIn('Webs oficiales de Fed, BCE y BoJ', false)}</div>`;

  /* diccionario */
  const dic = T.diccionario || {};
  const lista = (arr) => arr.slice().sort((a, b) => b.peso - a.peso || a.termino.localeCompare(b.termino)).map((x) => `<span class="chip">${esc(x.termino)} <b>${x.peso}</b></span>`).join(' ');
  h += `<div class="sect"><h2>Diccionario publicado</h2><span class="more">versión ${esc(dic.version)} · ${dic.n_terminos} términos · peso 2 = señal fuerte, 1 = débil</span></div>
    <details class="qa card" open><summary>Términos hawkish (${dic.hawkish.length})</summary><div class="chips" style="justify-content:flex-start;max-width:none;margin-top:10px">${lista(dic.hawkish)}</div></details>
    <details class="qa card"><summary>Términos dovish (${dic.dovish.length})</summary><div class="chips" style="justify-content:flex-start;max-width:none;margin-top:10px">${lista(dic.dovish)}</div></details>
    <div class="note">Método: se buscan en minúsculas las frases más largas primero y cada trozo de texto puntúa una sola vez; el índice es (H − D)/(H + D) con los pesos de arriba. No hay análisis de contexto ni negaciones: «inflation has eased» puntúa dovish por frase, pero «not appropriate to cut» puntuaría dovish por «cut». Es un criterio de lectura, no un modelo ajustado: los pesos y umbrales se fijaron antes de ver la validación y no se han retocado después. Memoria permanente (puntuación y términos, no el texto):
    <a class="src" href="https://github.com/komonartisans-ops/nexora-terminal/blob/main/data/tono_comunicados.csv" target="_blank" rel="noopener">data/tono_comunicados.csv</a> · <a class="src" href="https://github.com/komonartisans-ops/nexora-terminal/blob/main/data/tono_discursos.csv" target="_blank" rel="noopener">data/tono_discursos.csv</a>.</div>`;
  return h + errores(T.errores);
}

Object.assign(window.EXTRA_PAGES, { mapa: pageMapa, tono: pageTono });
