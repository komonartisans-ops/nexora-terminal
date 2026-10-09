/* NEXORA TERMINAL · front vanilla. Sin backend: lee site/data/*.json que escribe engine/build.py.
   Seguridad: todo texto dinámico se inserta con esc(); los datos son JSON propio del build (no entrada de usuarios). */
'use strict';

/* ------------------------------------------------------------------ utilidades */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const nfc = {};
const num = (v, d = 2) => {
  if (v == null || Number.isNaN(+v)) return null;
  nfc[d] = nfc[d] || new Intl.NumberFormat('es-ES', { minimumFractionDigits: d, maximumFractionDigits: d, useGrouping: 'always' });
  return nfc[d].format(v);
};
const SD = '<span class="sd-val">SIN DATO</span>';
const sg = (v, d = 2, suf = '') => (v == null || Number.isNaN(+v) ? '—' : `${v > 0 ? '+' : ''}${num(v, d)}${suf}`);
const pill = (v, d = 2, suf = '%', inv = false) => {
  if (v == null || Number.isNaN(+v)) return '<span class="pill flat">—</span>';
  const z = Math.abs(v) < 1e-9;
  const cls = z ? 'flat' : ((v > 0) !== inv ? 'up' : 'down');
  return `<span class="pill ${cls}">${z ? '▬' : v > 0 ? '▲' : '▼'} ${sg(v, d, suf)}</span>`;
};
const MES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
const DIA = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'];
const pd = (iso) => new Date(iso + 'T12:00:00Z');
const fd = (iso) => (iso ? `${+iso.slice(8, 10)} ${MES[+iso.slice(5, 7) - 1]}` : '—');
const fdy = (iso) => (iso ? `${fd(iso)} ${iso.slice(0, 4)}` : '—');
const fdm = (iso) => (iso ? `${MES[+iso.slice(5, 7) - 1]} ${iso.slice(0, 4)}` : '—');
const fdd = (iso) => (iso ? `${DIA[pd(iso).getUTCDay()]} ${fd(iso)}` : '—');
const stampDate = (s) => (s ? new Date(String(s).replace(' UTC', 'Z').replace(' ', 'T')) : null);
const horaAct = (s) => {
  const d = stampDate(s);
  if (!d || isNaN(d)) return 'sin fecha';
  return d.toLocaleString('es-ES', { timeZone: 'Europe/Madrid', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) + ' (Madrid)';
};
const hoyISO = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Europe/Madrid' });
const diasHasta = (iso) => Math.round((pd(iso) - pd(hoyISO())) / 864e5);
const lsGet = (k, d) => { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* sin almacenamiento */ } };

/* cambio de una serie [[iso,v]] a `dias` naturales; null si no hay punto de referencia razonable (no se interpola) */
function chg(s, dias) {
  if (!s || s.length < 2) return null;
  const last = s[s.length - 1];
  const lim = new Date(pd(last[0]) - dias * 864e5).toISOString().slice(0, 10);
  let ref = null;
  for (let i = s.length - 1; i >= 0; i--) if (s[i][0] <= lim) { ref = s[i]; break; }
  if (!ref) return null;
  const age = (pd(lim) - pd(ref[0])) / 864e5;
  if (age > dias + 10) return null;
  return last[1] - ref[1];
}
const lastOf = (s) => (s && s.length ? s[s.length - 1] : null);

/* ------------------------------------------------------------------ navegación */
const PAGES = [
  { id: 'resumen', g: 'Mercados', t: 'Resumen', d: 'Una tarjeta por activo con tesis y causa → efecto', f: 1 },
  { id: 'watchlists', g: 'Mercados', t: 'Watchlists', d: 'Listas editables de activos (se guardan en tu navegador)', f: 5 },
  { id: 'regimen', g: 'Análisis', t: 'Régimen macro', d: 'Crecimiento, inflación, empleo, liquidez, crédito y dólar', f: 2 },
  { id: 'ciclo', g: 'Análisis', t: 'Ciclo y crédito EE. UU.', d: 'Fase del ciclo, 9 señales, probit NY Fed, diferenciales', f: 2 },
  { id: 'bancos', g: 'Análisis', t: 'Bancos centrales', d: 'Fed, BCE y BoJ: tipos, reuniones y FedWatch propio', f: 1 },
  { id: 'liquidez', g: 'Análisis', t: 'Liquidez', d: 'Liquidez neta de la Fed, reservas, TGA, RRP y liquidez global', f: 1 },
  { id: 'divisas', g: 'Análisis', t: 'Sesgo de divisas', d: 'Matriz de ocho divisas por factores', f: 4 },
  { id: 'posicionamiento', g: 'Análisis', t: 'Posicionamiento (COT)', d: 'CFTC: neto no comercial y gestores de activos', f: 4 },
  { id: 'oro', g: 'Análisis', t: 'Oro, reservas y flujos', d: 'Tipo real, DXY, GLD, compras de bancos centrales', f: 3 },
  { id: 'indices', g: 'Análisis', t: 'Índices USA', d: 'Amplitud, beneficios, VIX, XLY/XLP', f: 3 },
  { id: 'cripto', g: 'Análisis', t: 'Cripto', d: 'BTC, ETH/BTC, funding, OI, stablecoins, ETF', f: 3 },
  { id: 'noticias', g: 'Noticias', t: 'Bancos centrales (RSS)', d: 'Comunicados y discursos oficiales, solo titular y enlace', f: 4 },
  { id: 'calendario', g: 'Noticias', t: 'Calendario económico', d: 'Semana actual y siguiente con hora de Madrid', f: 1 },
  { id: 'publicados', g: 'Noticias', t: 'Datos publicados', d: 'Últimas publicaciones y revisiones (original → revisado)', f: 2 },
  { id: 'diario', g: 'Personal', t: 'Diario de operaciones', d: 'Calendario mensual con P&L y notas', f: 5 },
  { id: 'tesis', g: 'Personal', t: 'Registro de tesis', d: 'Histórico de tesis y su resultado', f: 5 },
];
const PLAN = {
  3: 'Oro, Índices USA y Cripto.',
  4: 'COT (CFTC), Sesgo de divisas y Noticias RSS de bancos centrales.',
  5: 'Diario de operaciones, Watchlists y Registro de tesis (datos personales solo en tu navegador).',
};
const GROUPS = ['Mercados', 'Análisis', 'Noticias', 'Personal'];
const LIVE = new Set(['resumen', 'bancos', 'liquidez', 'calendario', 'ciclo', 'regimen', 'publicados', 'oro', 'indices', 'cripto']);
const D = {};
const MOUNT = [];

function buildNav() {
  const nav = $('#nav');
  nav.innerHTML = GROUPS.map((g) => `<div class="nav-item" data-g="${g}">
    <button class="nav-btn">${g} <span class="chev">▾</span></button>
    <div class="menu">${PAGES.filter((p) => p.g === g).map((p) => `<a href="#/${p.id}" data-id="${p.id}"><div class="t">${esc(p.t)}${!LIVE.has(p.id) ? `<span class="fase">F${p.f}</span>` : ''}</div><div class="d">${esc(p.d)}</div></a>`).join('')}</div>
  </div>`).join('');
  $$('.nav-item', nav).forEach((it) => {
    $('.nav-btn', it).addEventListener('click', (e) => { e.stopPropagation(); const o = it.classList.contains('open'); $$('.nav-item').forEach((x) => x.classList.remove('open')); if (!o) it.classList.add('open'); });
  });
  document.addEventListener('click', () => $$('.nav-item').forEach((x) => x.classList.remove('open')));
  $('#burger').addEventListener('click', () => nav.classList.toggle('show'));
  $$('.menu a', nav).forEach((a) => a.addEventListener('click', () => { nav.classList.remove('show'); $$('.nav-item').forEach((x) => x.classList.remove('open')); }));
  const q = $('#q'), res = $('#results');
  const draw = () => {
    const t = q.value.trim().toLowerCase();
    const m = PAGES.filter((p) => !t || (p.t + ' ' + p.d + ' ' + p.g).toLowerCase().includes(t)).slice(0, 8);
    res.innerHTML = m.map((p) => `<a href="#/${p.id}">${esc(p.t)} <span class="fase">${p.g}</span></a>`).join('') || '<a>Sin resultados</a>';
    res.classList.add('show');
  };
  q.addEventListener('input', draw);
  q.addEventListener('focus', draw);
  q.addEventListener('keydown', (e) => { if (e.key === 'Enter') { const a = $('a[href]', res); if (a) location.hash = a.getAttribute('href'); q.blur(); res.classList.remove('show'); q.value = ''; } if (e.key === 'Escape') { q.blur(); res.classList.remove('show'); } });
  res.addEventListener('click', () => { res.classList.remove('show'); q.value = ''; });
  document.addEventListener('click', (e) => { if (!e.target.closest('.search')) res.classList.remove('show'); });
  document.addEventListener('keydown', (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); q.focus(); } });
}
function tick() {
  const f = (tz) => new Date().toLocaleTimeString('es-ES', { timeZone: tz, hour: '2-digit', minute: '2-digit' });
  $('#clkNY').textContent = f('America/New_York');
  $('#clkMAD').textContent = f('Europe/Madrid');
}

/* ------------------------------------------------------------------ componentes */
function head(eyebrow, titulo, lede, stamp) {
  return `<div class="eyebrow">${esc(eyebrow)}</div><h1>${esc(titulo)}</h1><p class="lede">${lede}</p><div class="stamp">${stamp || ''}</div>`;
}
function essential(l1, l2, l3) {
  return `<section class="essential" aria-label="Lo esencial"><div class="h">Lo esencial</div>
    <p><b>Qué ha cambiado</b>${l1}</p><p><b>Qué significa</b>${l2}</p><p><b>Qué vigilar</b>${l3}</p></section>`;
}
function foot(src, fecha, url, extra) {
  const s = url ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(src)}</a>` : esc(src);
  return `<div class="foot"><span>Fuente: ${s}</span><span>${fecha ? 'dato ' + esc(fdy(fecha)) + (extra ? ' · ' + extra : '') : fecha === false ? (extra || '') : (extra || 'dato SIN DATO')}</span></div>`;
}
function spark(serie, n = 63) {
  const s = (serie || []).slice(-n);
  if (s.length < 3) return '';
  const vs = s.map((x) => x[1]); const mn = Math.min(...vs), mx = Math.max(...vs), r = mx - mn || 1;
  const pts = vs.map((v, i) => `${(i / (vs.length - 1) * 100).toFixed(1)},${(46 - (v - mn) / r * 42).toFixed(1)}`).join(' ');
  const c = vs[vs.length - 1] >= vs[0] ? '#2FA36B' : '#C8463D';
  const meses = Math.max(1, Math.round((pd(s[s.length - 1][0]) - pd(s[0][0])) / 864e5 / 30.4));
  return `<svg class="spark" viewBox="0 0 100 50" preserveAspectRatio="none"><polygon points="0,50 ${pts} 100,50" fill="${c}" opacity=".13"/><polyline points="${pts}" fill="none" stroke="${c}" stroke-width="1.5" vector-effect="non-scaling-stroke"/></svg><div class="sparkcap"><span>${esc(fd(s[0][0]))}</span><span>${meses === 1 ? '1 mes' : meses + ' meses'}</span><span>${esc(fd(s[s.length - 1][0]))}</span></div>`;
}
function ck(estado) {
  const e = String(estado || '').toUpperCase();
  const c = e === 'CUMPLE' || e === 'FAVORABLE' ? 'ok' : e === 'NO CUMPLE' || e === 'DESFAVORABLE' ? 'no' : e === 'PARCIAL' || e === 'NEUTRAL' ? 'par' : 'sd';
  return `<span class="ck ${c}">${esc(e || 'SIN DATO')}</span>`;
}
function tagTesis(et) {
  const e = String(et || '');
  const c = e.includes('DÉBIL') ? 'deb' : e.startsWith('ALCISTA') ? 'alc' : e.startsWith('BAJISTA') ? 'baj' : 'sin';
  return e ? `<span class="tag ${c}">${esc(e)}</span>` : '<span class="tag sd">NO CUBIERTO</span>';
}
function fallo(nombre) {
  const e = D.meta && D.meta.etapas && D.meta.etapas[nombre];
  return e && !e.ok ? `<div class="banner amber" style="margin:0 0 14px;border-radius:6px">Esta fuente falló en la última ejecución (${esc((e.error || '').slice(0, 140))}). Se muestra el último dato válido${e.ultimo_ok_utc ? ' del ' + esc(horaAct(e.ultimo_ok_utc)) : ''} o SIN DATO.</div>` : '';
}
function noData(nombre) {
  return `<div class="card"><div class="empty" style="height:140px">SIN DATO · ${esc(nombre)} · sin copia válida todavía</div></div>`;
}
function kpi(o) {
  /* o: {lab, exp, serie, unidad, suf, dec, k, inv, fuente, url, filas:[[etq,dias]]} */
  const l = lastOf(o.serie);
  const k = o.k || 1;
  const body = l ? `<div class="big">${num(l[1] * k, o.dec ?? 2)}<small>${esc(o.unidad || '')}</small></div>
      <table>${(o.filas || [['1 semana', 7], ['4 semanas', 28], ['12 semanas', 84]]).map(([e, d]) => { const c = chg(o.serie, d); return `<tr><td>${e}</td><td>${pill(c == null ? null : c * k, o.dec ?? 2, ' ' + (o.suf ?? ''), o.inv)}</td></tr>`; }).join('')}</table>`
    : `<div class="big">${SD}</div>`;
  return `<div class="card kpi"><div class="lab">${esc(o.lab)}</div><div class="exp">${esc(o.exp || '')}</div>${body}${foot(o.fuente, l && l[0], o.url)}</div>`;
}

/* ------------------------------------------------------------------ gráficos */
const COL = { amber: '#C8A24A', pos: '#2FA36B', neg: '#C8463D', blue: '#6C8EBF', violet: '#9B87C9', gray: '#8A93A0', white: '#E6E8EB' };
function lw(id, defs, opts = {}) {
  MOUNT.push(() => {
    const el = document.getElementById(id);
    if (!el) return;
    if (!defs.some((d) => d.data && d.data.length > 1) || !window.LightweightCharts) { el.innerHTML = '<div class="empty">SIN DATO</div>'; return; }
    const chart = LightweightCharts.createChart(el, {
      width: el.clientWidth, height: el.clientHeight,
      layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#8A93A0', fontFamily: 'IBM Plex Mono, monospace', fontSize: 11 },
      grid: { vertLines: { color: '#14181e' }, horzLines: { color: '#14181e' } },
      rightPriceScale: { borderColor: '#1E232B' }, leftPriceScale: { visible: !!opts.left, borderColor: '#1E232B' },
      timeScale: { borderColor: '#1E232B', fixLeftEdge: true, fixRightEdge: true },
      crosshair: { mode: 0, vertLine: { color: '#2A313B' }, horzLine: { color: '#2A313B' } },
    });
    const series = defs.map((d) => {
      const pf = { type: 'price', precision: d.prec ?? 2, minMove: Math.pow(10, -(d.prec ?? 2)) };
      const common = { priceScaleId: d.scale || 'right', priceFormat: pf, priceLineVisible: false, lastValueVisible: true, lineWidth: d.w || 2 };
      const s = d.area ? chart.addAreaSeries({ ...common, lineColor: d.color, topColor: d.color + '40', bottomColor: d.color + '00' })
        : d.step ? chart.addLineSeries({ ...common, color: d.color, lineType: 1 }) : chart.addLineSeries({ ...common, color: d.color });
      s.setData((d.data || []).map(([t, v]) => ({ time: t, value: v })));
      return s;
    });
    chart.timeScale().fitContent();
    if (opts.init) { const all0 = defs.flatMap((d) => d.data || []).map((x) => x[0]).sort(); const to0 = all0[all0.length - 1]; chart.timeScale().setVisibleRange({ from: new Date(pd(to0) - opts.init * 864e5).toISOString().slice(0, 10), to: to0 }); }
    const leg = document.getElementById(id + '-leg');
    if (leg) chart.subscribeCrosshairMove((p) => {
      defs.forEach((d, i) => { const v = p.seriesData && p.seriesData.get(series[i]); const b = leg.querySelector(`[data-i="${i}"]`); if (b) b.textContent = v ? num(v.value, d.prec ?? 2) : ''; });
    });
    new ResizeObserver(() => chart.applyOptions({ width: el.clientWidth, height: el.clientHeight })).observe(el);
    const rb = document.getElementById(id + '-rng');
    if (rb) rb.addEventListener('click', (e) => {
      const b = e.target.closest('button'); if (!b) return;
      $$('button', rb).forEach((x) => x.classList.remove('on')); b.classList.add('on');
      const n = +b.dataset.d; if (!n) { chart.timeScale().fitContent(); return; }
      const all = defs.flatMap((d) => d.data || []).map((x) => x[0]).sort(); const to = all[all.length - 1];
      chart.timeScale().setVisibleRange({ from: new Date(pd(to) - n * 864e5).toISOString().slice(0, 10), to });
    });
  });
  const leg = defs.map((d, i) => `<span><i style="background:${d.color}"></i>${esc(d.name)} <b class="mono" data-i="${i}" style="color:#E6E8EB"></b></span>`).join('');
  const rng = opts.range === false ? '' : `<span id="${id}-rng" style="margin-left:auto;display:flex;gap:4px">${[['3M', 92], ['6M', 183], ['1A', 365], ['Todo', 0]].map(([l, d], i, a) => `<button class="fbtn ${i === a.length - 1 ? 'on' : ''}" data-d="${d}" style="padding:2px 8px;font-size:10.5px">${l}</button>`).join('')}</span>`;
  return `<div class="legend" id="${id}-leg">${leg}${rng}</div><div class="chart ${opts.tall ? 'tall' : ''} ${opts.fill ? 'fill' : ''}" id="${id}"></div>`;
}
function rebase(s, desde) {
  const pts = s.filter((x) => x[0] >= desde);
  if (!pts.length) return [];
  return pts.map(([t, v]) => [t, +(v / pts[0][1] * 100).toFixed(3)]);
}

/* ------------------------------------------------------------------ páginas */
const LABEL = { t2y: 'Rendimiento 2Y EE. UU.', real: 'Tipo real 10Y', dxy: 'Dólar (réplica DXY)', vix: 'VIX', hy: 'Diferencial HY', fed: 'Fed · prob. de subida próxima reunión' };
const UMB = { fed: [10, 15], t2y: [5, 10], real: [4, 8], dxy: [0.3, 0.6], vix: [8, 12], hy: [8, 15] };
const UNID = { fed: ['%', ' pts'], t2y: ['%', ' pb'], real: ['%', ' pb'], dxy: ['', '%'], vix: ['', '%'], hy: [' pb', ' pb'] };

/* alerta de tensión de crédito (CCC, HY, BBB, IG) con las reglas y umbrales de ciclo.py: solo aparece si está activa */
function alertaCredito() {
  const C = D.ciclo;
  if (!C || !C.estado_credito || !/TENSI/i.test(C.estado_credito)) return '';
  const U = C.umb_cred || {}, S = (C.series && C.series.oas) || {}, cr = C.credito || {};
  const NOM = { ccc: 'CCC · las más frágiles', hy: 'High yield', bbb: 'BBB', ig: 'Grado de inversión' };
  const celdas = ['ccc', 'hy', 'bbb', 'ig'].map((k) => {
    const m = cr[k];
    if (!m) return `<div class="cm"><div class="k">${NOM[k]}</div><div class="v">${SD}</div></div>`;
    const u = U[k] || [];
    const d5 = m['5d_pb'] ?? m.d5_pb;
    const on = (d5 != null && u[0] != null && d5 >= u[0]) || (m['1m_pb'] != null && u[1] != null && m['1m_pb'] >= u[1]);
    return `<div class="cm ${on ? 'on' : ''}"><div class="k">${NOM[k]}${on ? ' · SUPERA UMBRAL' : ''}</div><div class="v mono">${num(m.pb, 0)}<small> pb</small></div>
      <div class="d">5 d ${pill(d5, 0, ' pb', true)} · 1 m ${pill(m['1m_pb'], 0, ' pb', true)}</div>${S[k] ? spark(S[k], 126) : ''}
      <div class="n">percentil ${m.percentil_1a} del último año · alerta a ${u[0] ?? '—'} pb (5 d) / ${u[1] ?? '—'} pb (1 m)</div><div class="n">${esc(fdy(m.fecha))}</div></div>`;
  }).join('');
  const ccc = cr.ccc;
  return `<a class="credit-alert" href="#/ciclo" aria-label="Alerta de tensión de crédito">
    <div class="ca-head"><span class="ca-tag">ALERTA ACTIVA</span><span class="ca-title">${esc(C.estado_credito)}</span><span class="ca-go">Ciclo y crédito →</span></div>
    <div class="ca-body"><div class="ca-text"><p><b>Hecho</b>${esc(C.estado_credito)}${ccc ? `. El diferencial CCC está en ${num(ccc.pb, 0)} pb, en el percentil ${ccc.percentil_1a} del último año (mínimo de 12 meses: ${num(ccc.min_1a_pb, 0)} pb).` : ''}</p>
      <p><b>Interpretación</b>Los bonos de las empresas más endeudadas exigen cada vez más para financiarlas. Suele adelantarse a la bolsa y pesa sobre todo en el Russell 2000.</p>
      <p><b>Escenario a vigilar</b>Si se amplía también el high yield (umbral ${(U.hy || [])[0] ?? '—'} pb en 5 días), el estrés deja de ser solo de los más frágiles y pasa a ser de todo el crédito de riesgo. Si el CCC se estrecha, la señal pierde fuerza.</p></div>
      <div class="ca-grid">${celdas}</div></div>
    <div class="foot"><span>Fuente: ICE BofA vía FRED (BAMLH0A3HYC, BAMLH0A0HYM2, BAMLC0A4CBBB, BAMLC0A0CM) · reglas de ciclo.py</span><span>dato ${esc(fdy((cr.ccc || {}).fecha))}</span></div></a>`;
}

function pageResumen() {
  const R = D.resumen, P = D.precios, C = D.calendario, T = D.tipos;
  const act = (P && P.activos) || {};
  const orden = [['oro', 'Oro', 'USD'], ['btc', 'Bitcoin', 'USD'], ['spx', 'S&P 500', 'pts'], ['ndx', 'Nasdaq 100', 'pts'], ['dji', 'US30 · Dow Jones', 'pts'], ['rut', 'Russell 2000', 'pts']];
  const TES = (R && R.tesis_activos) || {};
  const nombreTesis = { oro: 'Oro', btc: 'Bitcoin', spx: 'S&P 500', ndx: 'Nasdaq 100', dji: 'US30 · Dow Jones', rut: 'Russell 2000' };
  const corteFecha = R && R.corte ? (R.corte.match(/\d{4}-\d{2}-\d{2}/g) || []).pop() : null;
  const stamp = `Precios: ${P && P.generado_utc ? esc(horaAct(P.generado_utc)) : 'SIN DATO'} · Tesis: ${R && R.generado_utc ? esc(horaAct(R.generado_utc)) : 'SIN DATO'} · corte de datos: ${R ? esc(R.corte) : 'SIN DATO'}`;
  let h = head('Mercados', 'Resumen', 'Una tarjeta por activo: precio, tendencia y el viento macro que lo acompaña. La tesis solo describe si la macro empuja a favor o en contra; no es una recomendación de compra o venta.', stamp);
  h += fallo('precios') + fallo('resumen');
  const prox = ((C && C.eventos) || []).filter((e) => e.fecha >= hoyISO());
  const vig = R ? R.vigilar.slice(0, 2).map(esc).join(' · ') : SD;
  h += alertaCredito();
  h += essential(R ? esc(R.movido) : SD, R ? (R.sencillo_activos ? esc(R.sencillo_activos.split('. Cada activo')[0]) + '.' : esc(R.tesis)) : SD, vig);

  h += '<div class="sect"><h2>Activos</h2><span class="more">cambio 1d · 1 sem · 1 mes · 3 meses · gráfico de 3 meses</span></div><div class="grid g6">';
  h += orden.map(([k, nm, u]) => {
    const a = act[k];
    if (!a || a.valor == null) return `<div class="card kpi asset"><div class="top"><div><div class="nm">${nm}</div></div>${tagTesis(null)}</div><div class="big" style="margin-top:12px">${SD}</div>${foot((a && a.fuente) || 'Yahoo Finance', null)}</div>`;
    const t = TES[nombreTesis[k]];
    return `<div class="card kpi asset"><div class="top"><div><div class="nm">${nm}</div><div class="sym">${esc(a.simbolo)}</div></div>${nombreTesis[k] ? (t ? tagTesis(t.etiqueta) : tagTesis('SIN TESIS')) : tagTesis(null)}</div>
      <div class="big" style="margin-top:10px">${num(a.valor, a.valor > 1000 ? 0 : 2)}<small>${u}</small></div><div class="chg">${pill(a.cambio_1d_pct)}</div>${spark(a.serie, 63)}
      <table><tr><td>1 semana</td><td>${pill(a.cambio_5d_pct)}</td></tr><tr><td>1 mes</td><td>${pill(a.cambio_21d_pct)}</td></tr><tr><td>3 meses</td><td>${pill(a.cambio_63d_pct)}</td></tr></table>
      ${foot(a.fuente, a.fecha)}</div>`;
  }).join('') + '</div>';

  h += '<div class="sect"><h2>Panel de mercado</h2><span class="more">▲▼ frente al cierre anterior · vs media de 50 sesiones</span></div><div class="card pad0 scroll"><table class="t"><thead><tr><th>Activo</th><th>Último</th><th>1d</th><th>1 sem</th><th>1 mes</th><th>3 meses</th><th>vs SMA50</th><th>Dato</th><th style="text-align:left">Fuente</th></tr></thead><tbody>';
  const filas = [...orden.map((o) => o[0]), 'vix', 'dxy'];
  h += filas.map((k) => {
    const a = act[k];
    if (!a || a.valor == null) return `<tr><td>${esc((a && a.nombre) || k)}</td><td colspan="7" style="text-align:left;color:var(--dim)">SIN DATO</td><td style="text-align:left;color:var(--dim)">${esc((a && a.fuente) || '')}</td></tr>`;
    const v = ((a.valor / a.sma50 - 1) * 100);
    return `<tr><td>${esc(a.nombre)}<small>${esc(a.simbolo)}</small></td><td>${num(a.valor, a.valor > 1000 ? 0 : 2)}</td><td>${pill(a.cambio_1d_pct)}</td><td>${pill(a.cambio_5d_pct)}</td><td>${pill(a.cambio_21d_pct)}</td><td>${pill(a.cambio_63d_pct)}</td><td>${pill(v, 1)}</td><td>${esc(fd(a.fecha))}</td><td style="text-align:left;color:var(--dim)">${esc(a.fuente)}</td></tr>`;
  }).join('');
  h += '</tbody></table></div>';

  /* tesis por activo: MISMO motor que el informe diario (por_activo.py): viento macro de la semana + veredicto del monitor propio */
  const nombres = ['Oro', 'Nasdaq 100', 'S&P 500', 'Bitcoin', 'US30 · Dow Jones', 'Russell 2000'];
  const MP = (R && R.motores_propios) || {};
  const monDe = { 'Oro': 'oro_xau', 'Bitcoin': 'liquidez_cripto' };
  const cut = (x, n) => { x = String(x ?? ''); return x.length > n ? x.slice(0, n - 1) + '…' : x; };
  const lst = (arr) => (arr && arr.length ? arr.map((x) => esc(cut(x, 120))).join(' · ') : '');
  const cardTesis = (n) => {
    const t = TES[n];
    if (!t) return `<div class="card asset"><div class="top"><div class="nm">${esc(n)}</div>${tagTesis(null)}</div><div class="flow">SIN DATO: la tesis no se pudo calcular en esta ejecución.</div>${foot('Motor NEXORA (por_activo.py)', false)}</div>`;
    const pr = t.propio, est = MP[monDe[n] || 'indices'] || {};
    const prop = pr ? `<div><b style="color:var(--text)">${esc(pr.veredicto)}</b> · ${esc(cut(pr.detalle, 190))}</div>${pr.favor && pr.favor.length ? `<div class="up">A favor: ${lst(pr.favor)}</div>` : ''}${pr.contra && pr.contra.length ? `<div class="down">En contra: ${lst(pr.contra)}</div>` : ''}${pr.rotacion ? `<div>Rotación cíclico/defensivo (XLY/XLP): ${esc(cut(pr.rotacion, 130))}</div>` : ''}${pr.avisos && pr.avisos[0] ? `<div style="color:var(--amber)">${esc(cut(pr.avisos[0], 130))}</div>` : ''}` : '<div>SIN DATO: el monitor propio no respondió (nunca se estima).</div>';
    return `<div class="card asset"><div class="top"><div class="nm">${esc(n)}</div>${tagTesis(t.etiqueta)}</div>
      <div class="flow">${esc(t.tesis)}<em>Viento macro</em><div>Hoy · ${esc(t.hoy)}</div><div>Semana · ${esc(t.semana)}</div><em>Su motor propio · ${esc(t.motor_propio_nombre || '')}</em>${prop}</div>
      ${foot('Motor NEXORA por_activo.py (monitor ' + (est.calculado_utc ? horaAct(est.calculado_utc) : 'SIN DATO') + ')', corteFecha)}</div>`;
  };
  h += '<div class="grid g21 stretch" style="margin-top:12px"><div class="col"><div class="sect" style="margin-top:14px"><h2>Tesis por activo · viento macro + motor propio</h2><span class="more">mismo motor que el informe diario · seis activos</span></div>';
  h += '<div class="grid g2">' + nombres.map(cardTesis).join('') + '</div>';
  /* gráfico grande que llena el hueco bajo las tesis: 2Y vs tipo real a 10 años (Tesoro de EE. UU.) */
  const t2 = T && T.t2y, rl = T && T.real10;
  h += `<div class="card chartcard" style="margin-top:12px"><h3>Bono a 2 años frente al tipo real a 10 años</h3><div class="sub">Los dos motores que más pesan en oro e índices. Si el 2Y baja y el tipo real no, el mercado espera una Fed más blanda pero sigue exigiendo rentabilidad real.</div>
    ${lw('cTipos2', [{ name: 'Bono a 2 años', color: COL.amber, data: t2 && t2.serie, prec: 2 }, { name: 'Tipo real 10 años', color: COL.blue, data: rl && rl.serie, prec: 2 }], { fill: true, init: 365 })}
    ${foot(t2 ? t2.fuente : 'Tesoro de EE. UU.', t2 && t2.fecha, t2 && t2.url)}</div></div><div>`;
  h += '<div class="sect" style="margin-top:14px"><h2>Motores macro</h2><span class="more">umbral de sesión</span></div><div class="card pad0"><table class="t"><thead><tr><th>Motor</th><th>Valor</th><th>Hoy</th><th>Umbral</th></tr></thead><tbody>';
  const M = (R && R.motores) || {};
  h += Object.keys(LABEL).map((k) => {
    const m = M[k]; if (!m) return `<tr><td>${esc(LABEL[k])}</td><td colspan="3" style="color:var(--dim);text-align:left">SIN DATO</td></tr>`;
    const [u1, u2] = UNID[k]; const sig = m.delta != null && Math.abs(m.delta) >= UMB[k][0];
    return `<tr><td>${esc(LABEL[k])}<small>${esc(fd(m.fecha))}</small></td><td>${num(m.valor, k === 'fed' || k === 'hy' ? 0 : 2)}${u1}</td><td>${pill(m.delta, k === 'dxy' || k === 'vix' ? 2 : 1, u2)}</td><td>${sig ? '<span class="ck par">SUPERA</span>' : `<span class="mono" style="color:var(--dim)">${UMB[k][0]}${u2.trim()}</span>`}</td></tr>`;
  }).join('') + '</tbody></table>' + footIn('Tesoro de EE. UU., BCE, Cboe, ICE BofA vía FRED, FedWatch NEXORA', corteFecha) + '</div>';
  h += '<div class="sect"><h2>Próximos eventos</h2><a class="more" href="#/calendario">calendario →</a></div><div class="card">';
  const lista = prox.filter((e) => e.importancia !== 'BAJA').slice(0, 7);
  h += lista.length ? lista.map((e) => `<div class="evrow"><span class="when">${esc(fdh(e.fecha, e.hora_madrid))}</span><span class="what">${esc(e.evento)}<span class="aff">${esc(e.afecta)}</span></span></div>`).join('') : SD;
  h += foot('Calendario NEXORA (FRED, ISM, Fed, Nasdaq)', false, null, 'hora de Madrid') + '</div>';
  h += cardAlertas() + '</div></div>';

  h += `<div class="sect"><h2>En palabras sencillas</h2></div><div class="card"><div class="simple">${R ? esc(R.sencillo_activos || '') + ' ' + esc(R.sencillo) : SD}</div>
    <ul class="watch" style="margin-top:12px">${R ? R.vigilar.map((v) => `<li>${esc(v)}</li>`).join('') : ''}</ul>
    <div class="note">Cada cifra procede de su fuente oficial (Tesoro de EE. UU., FRED, Cboe, Nasdaq, Coinbase, futuros ZQ). Si una descarga falla se muestra SIN DATO: nunca se interpola ni se estima.</div>${foot('Plantillas deterministas NEXORA (sin IA)', corteFecha)}</div>`;
  return h;
}

function cuentaAtras(iso) {
  if (!iso) return SD;
  const d = diasHasta(iso);
  return `<span class="cd">${d > 0 ? `en ${d} día${d === 1 ? '' : 's'}` : d === 0 ? 'hoy' : `hace ${-d} día${d === -1 ? '' : 's'}`}</span>`;
}
function pageBancos() {
  const F = D.fedwatch, C = D.calendario, L = D.liquidez;
  const hist = (L && L.historico) || {};
  let h = head('Análisis', 'Bancos centrales', 'Tipos oficiales, próxima reunión y lo que descuenta el mercado de futuros de la Fed (FedWatch propio, mismo método que CME, calculado con futuros ZQ).', `FedWatch: ${F && F.generado_utc ? esc(horaAct(F.generado_utc)) : 'SIN DATO'} · precios de futuros del ${F ? esc(fdy(F.fecha_precios)) : 'SIN DATO'}`);
  h += fallo('fedwatch');
  if (!F || !F.reuniones) return h + noData('FedWatch');
  const R = F.reuniones, r0 = R[0], pr = r0.prob_reunion;
  const pc = (C && C.proximos_bancos_centrales) || {};
  const tendencia = F.lectura.startsWith('MÁS DURA') ? 'una Fed más dura que hace una semana' : F.lectura.startsWith('MÁS BLANDA') ? 'una Fed más blanda que hace una semana' : 'una Fed sin cambios relevantes frente a hace una semana';
  const mayor = pr.subida >= pr.bajada && pr.subida >= pr.mantiene ? 'subida' : pr.bajada >= pr.mantiene ? 'bajada' : 'mantener';
  h += essential(`${esc(F.resumen)}. Tipo esperado a 3 reuniones: ${sg(F.tipo_esperado_3_reuniones_5d_pb, 0, ' pb')} en 5 sesiones.`,
    `Hipótesis: el mercado descuenta ${esc(tendencia)}. Resultado más probable de la próxima reunión: <b style="color:var(--text)">${mayor}</b>. Una Fed más dura suele pesar sobre oro, índices y BTC; más blanda, al revés (interpretación, no hecho).`,
    `Reunión Fed ${esc(fdd(r0.reunion))} (${cuentaAtras(r0.reunion)}). Si la probabilidad de subida se mueve más de 15 puntos, cambia el viento para todo.`);
  const ta = F.tipos_actuales || {};
  const nextOf = (re) => { const k = Object.keys(pc).find((x) => re.test(x)); return k ? pc[k] : null; };
  const bal = (k) => lastOf(hist[k]);
  const bank = (nombre, rate, sub, next, balK, fuente) => {
    const b = bal(balK);
    const fechaTipo = nombre === 'Fed' ? F.fecha_precios : (ta[nombre] && ta[nombre].fecha);
    return `<div class="card bank"><div class="eyebrow" style="color:var(--muted)">${nombre}</div>
      <div class="rate">${rate || SD}</div><div class="note" style="margin:0 0 8px">${sub || ''}</div>
      <div class="row"><span>Próxima reunión</span><span>${next ? `${esc(fdd(next.fecha))} · ${cuentaAtras(next.fecha)}` : SD}</span></div>
      <div class="row"><span>Balance</span><span class="mono">${b ? `${num(b[1], 2)} bill. $ <small style="color:var(--dim)">${esc(fd(b[0]))}</small>` : 'SIN DATO'}</span></div>
      ${foot(fuente, fechaTipo)}</div>`;
  };
  const fed = ta.Fed || {};
  h += '<div class="sect"><h2>Tipos oficiales y calendario</h2></div><div class="grid g3">';
  h += bank('Fed', fed.rango && fed.rango[0] != null ? `${num(fed.rango[0], 2)}–${num(fed.rango[1], 2)}<small> %</small>` : null, `EFFR ${fed.effr != null ? num(fed.effr, 2) + ' %' : 'SIN DATO'} · rango objetivo`, nextOf(/Fed/i), 'balance_fed_T', 'FRED DFEDTARL/U · H.4.1');
  h += bank('BCE', ta.BCE && ta.BCE.valor != null ? `${num(ta.BCE.valor, 2)}<small> %</small>` : null, 'Facilidad de depósito', nextOf(/BCE|ECB/i), 'bce_T', 'FRED ECBDFR · ECBASSETSW');
  h += bank('BoJ', ta.BoJ && ta.BoJ.valor != null ? `${num(ta.BoJ.valor, 2)}<small> %</small>` : null, 'Tipo de política (OCDE, mensual). Sin dato reciente en FRED: no se estima', nextOf(/Jap|BoJ/i), 'boj_T', 'FRED IRSTCB01JPM156N · JPNASSETS');
  h += '</div>';

  h += '<div class="sect"><h2>FedWatch · probabilidades por reunión</h2><span class="more">futuros ZQ (CBOT) · EFFR · calendario FOMC</span></div><div class="grid g21">';
  h += `<div class="card"><h3>Qué espera el mercado en cada reunión</h3><div class="sub">Probabilidad de subida / mantener / bajada del tipo en esa reunión</div><div class="chart" style="height:290px"><canvas id="cFW"></canvas></div>${foot('FedWatch NEXORA', F.fecha_precios, null, 'puede diferir unos puntos de CME')}</div>`;
  h += `<div class="card"><h3>Tipo esperado tras cada reunión</h3><div class="sub">Hoy: EFFR ${num(F.effr, 2)} %</div><div class="chart" style="height:290px"><canvas id="cFW2"></canvas></div>${foot('FedWatch NEXORA', F.fecha_precios)}</div></div>`;
  MOUNT.push(() => {
    if (!window.Chart) return;
    Chart.defaults.color = '#8A93A0'; Chart.defaults.font.family = 'IBM Plex Mono, monospace'; Chart.defaults.font.size = 11;
    const lab = R.map((r) => fd(r.reunion));
    new Chart($('#cFW'), { type: 'bar', data: { labels: lab, datasets: [
      { label: 'Subida', data: R.map((r) => r.prob_reunion.subida), backgroundColor: COL.neg },
      { label: 'Mantener', data: R.map((r) => r.prob_reunion.mantiene), backgroundColor: '#4A5360' },
      { label: 'Bajada', data: R.map((r) => r.prob_reunion.bajada), backgroundColor: COL.pos }] },
      options: { maintainAspectRatio: false, scales: { x: { stacked: true, grid: { display: false }, border: { color: '#1E232B' } }, y: { stacked: true, max: 100, grid: { color: '#14181e' }, border: { display: false }, ticks: { callback: (v) => v + ' %' } } }, plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, boxHeight: 10 } }, tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${num(c.parsed.y, 1)} %` } } } } });
    new Chart($('#cFW2'), { type: 'line', data: { labels: ['Hoy', ...lab], datasets: [{ label: 'Tipo esperado', data: [F.effr, ...R.map((r) => r.tipo_esperado)], borderColor: COL.amber, backgroundColor: 'rgba(200,162,74,.12)', fill: true, tension: 0.2, pointRadius: 3, pointBackgroundColor: COL.amber }] },
      options: { maintainAspectRatio: false, scales: { x: { grid: { display: false }, border: { color: '#1E232B' } }, y: { grid: { color: '#14181e' }, border: { display: false }, ticks: { callback: (v) => num(v, 2) + ' %' } } }, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => num(c.parsed.y, 3) + ' %' } } } } });
  });
  h += '<div class="card pad0 scroll" style="margin-top:12px"><table class="t"><thead><tr><th>Reunión</th><th>Tipo esperado</th><th>Subida</th><th>Mantener</th><th>Bajada</th><th></th><th>Δ subida 1d</th><th>Δ subida 5d</th><th>Δ tipo 5d</th><th>Acum. &gt; hoy</th></tr></thead><tbody>';
  h += R.map((r) => `<tr><td>${esc(fdd(r.reunion))}<small>${cuentaAtras(r.reunion)}</small></td><td>${num(r.tipo_esperado, 3)} %</td><td class="down">${num(r.prob_reunion.subida, 1)} %</td><td>${num(r.prob_reunion.mantiene, 1)} %</td><td class="up">${num(r.prob_reunion.bajada, 1)} %</td>
    <td><div class="prob"><i class="s" style="width:${r.prob_reunion.subida}%"></i><i class="m" style="width:${r.prob_reunion.mantiene}%"></i><i class="b" style="width:${r.prob_reunion.bajada}%"></i></div></td>
    <td>${pill(r.subida_1d_pts, 1, ' pts', true)}</td><td>${pill(r.subida_5d_pts, 1, ' pts', true)}</td><td>${pill(r.tipo_5d_pb, 1, ' pb', true)}</td><td>${num(r.prob_acumulada.mas_alto_que_hoy, 1)} %</td></tr>`).join('');
  h += '</tbody></table>' + footIn('FedWatch NEXORA (futuros ZQ del CBOT, EFFR, calendario FOMC)', F.fecha_precios) + '</div>';
  h += `<div class="note">Rojo = más tipos (endurecimiento); verde = menos tipos. ${esc(F.fuente)}</div>`;

  const th = F.tipos_historico || {};
  h += '<div class="sect"><h2>Tipos oficiales · histórico</h2></div><div class="grid g21"><div class="card">'
    + lw('cTipos', [{ name: 'Fed (techo del rango)', color: COL.amber, data: th.fed_max, step: true }, { name: 'BCE (depósito)', color: COL.blue, data: th.bce_deposito, step: true }, { name: 'BoJ (OCDE, mensual)', color: COL.violet, data: th.boj_politica, step: true }], { tall: true })
    + foot('FRED DFEDTARU · ECBDFR · IRSTCB01JPM156N', lastOf(th.fed_max) && lastOf(th.fed_max)[0]) + '</div>';
  h += `<div class="card"><h3>Probabilidad de subida · próxima reunión</h3><div class="sub">Últimas sesiones (${esc(fd(r0.reunion))})</div><table class="t" style="margin-top:4px"><thead><tr><th>Sesión</th><th>Subida</th><th>Bajada</th></tr></thead><tbody>`
    + (F.historial || []).slice().reverse().map((x) => `<tr><td>${esc(fdd(x.fecha))}</td><td class="down">${num(x.prox_subida, 1)} %</td><td class="up">${num(x.prox_bajada, 1)} %</td></tr>`).join('')
    + `</tbody></table>${foot('FedWatch NEXORA', F.fecha_precios)}</div></div>`;
  if (F.errores && Object.keys(F.errores).length) h += `<div class="note">Fuentes sin dato: ${Object.entries(F.errores).map(([k, v]) => esc(k + ': ' + String(v).slice(0, 80))).join(' · ')}</div>`;
  return h;
}

function pageLiquidez() {
  const L = D.liquidez;
  let h = head('Análisis', 'Liquidez', 'Cuánto dinero circula (balance de la Fed, cuenta del Tesoro, repo inverso), cómo se mueven los grandes bancos centrales y si se cumple la secuencia de giro de liquidez.', `Actualizado: ${L && L.generado_utc ? esc(horaAct(L.generado_utc)) : 'SIN DATO'} · datos semanales de la Fed con fecha propia en cada tarjeta`);
  h += fallo('liquidez');
  if (!L || !L.evaluacion) return h + noData('Liquidez');
  const E = L.evaluacion, M = L.metricas, H = L.historico || {};
  const cr = E.checklist_resumen || {};
  const neta = lastOf(H.liquidez_neta_T);
  const d4 = chg(H.liquidez_neta_T, 28);
  h += essential(neta ? `Liquidez neta de la Fed ${num(neta[1], 2)} bill. $ (${esc(fdy(neta[0]))}), ${sg(d4, 2, ' bill. $')} en 4 semanas. TGA ${M.tga ? num(M.tga.valor_B, 0) : 'SIN DATO'} mm $ (${M.tga ? sg(M.tga.delta_1s_B, 0, ' mm $') : '—'} en 1 semana), RRP ${M.rrp ? num(M.rrp.valor_B, 1) : 'SIN DATO'} mm $.` : SD,
    `Lectura NEXORA: <b style="color:var(--text)">${esc(E.lectura)}</b>. Checklist ${cr.cumple ?? '—'}/${cr.total ?? 8} condiciones cumplidas; secuencia ${E.secuencia_cumplidos ?? '—'}/7. Interpretación: ${E.lectura.includes('SIN GIRO') ? 'la liquidez no está dando un empujón claro a los activos de riesgo' : 'hay señales de cambio de liquidez que conviene contrastar con los activos'}.`,
    `Reservas bancarias (semanal, H.4.1), TGA tras la liquidación de subastas y la próxima decisión de la Fed. ${E.avisos && E.avisos.length ? esc(E.avisos[0]) : ''}`);
  h += `<div class="state"><div class="card"><div class="eb">Liquidez</div><div class="v ${E.lectura.includes('SIN GIRO') ? 'amber' : ''}">${esc(E.lectura)}</div><p>Reservas, TGA y RRP: ${E.nucleo ? `${E.nucleo.fav} a favor · ${E.nucleo.des} en contra de ${E.nucleo.n}` : 'SIN DATO'} (núcleo). Contexto global: ${E.contexto_13 ? `${E.contexto_13.fav} favorables · ${E.contexto_13.des} desfavorables` : 'SIN DATO'}.</p>${foot('Monitor de liquidez NEXORA (FRED, Tesoro, Fed)', (lastOf(H.liquidez_neta_T) || [])[0])}</div>
    <div class="card"><div class="eb">Secuencia de giro</div><div class="v">${E.secuencia_cumplidos ?? '—'} <span style="color:var(--dim)">/ 7</span></div><p>Cumple hasta el paso ${E.secuencia_hasta ?? 0}. El giro exige TGA↓, RRP↓ y reservas↑ primero, y después tipos, Fed, dólar y BTC.</p>${foot('Secuencia NEXORA (FRED, Tesoro, Fed, Coinbase)', (lastOf(H.liquidez_neta_T) || [])[0])}</div></div>`;
  (E.avisos || []).forEach((a) => { h += `<div class="banner amber" style="margin-top:10px;border-radius:6px">${esc(a)}</div>`; });

  h += '<div class="sect"><h2>Balance y liquidez</h2><span class="more">bill. $ = billones de dólares (10¹²) · mm $ = miles de millones</span></div><div class="grid g4">';
  h += kpi({ lab: 'Liquidez neta de la Fed', exp: 'Balance − TGA − RRP: el dinero realmente disponible para el sistema', serie: H.liquidez_neta_T, unidad: 'bill. $', suf: 'bill.', fuente: 'FRED WALCL, WTREGEN, RRPONTSYD', url: 'https://fred.stlouisfed.org/series/WALCL' });
  h += kpi({ lab: 'Balance de la Reserva Federal', exp: 'Activos totales (QE sube, QT baja)', serie: H.balance_fed_T, unidad: 'bill. $', suf: 'bill.', fuente: 'FRED WALCL', url: 'https://fred.stlouisfed.org/series/WALCL' });
  h += kpi({ lab: 'TGA · cuenta del Tesoro', exp: 'Si sube, drena liquidez (rojo); si baja, la inyecta', serie: H.tga_T, unidad: 'bill. $', suf: 'bill.', inv: true, fuente: 'FRED WTREGEN', url: 'https://fred.stlouisfed.org/series/WTREGEN' });
  h += kpi({ lab: 'Repo inverso (RRP)', exp: 'Efectivo aparcado en la Fed; agotado = ya no aporta', serie: H.rrp_T, k: 1000, unidad: 'mm $', suf: 'mm $', dec: 1, inv: true, fuente: 'FRED RRPONTSYD', url: 'https://fred.stlouisfed.org/series/RRPONTSYD' });
  h += kpi({ lab: 'Reservas bancarias', exp: 'Colchón de los bancos en la Fed', serie: H.reservas_T, unidad: 'bill. $', suf: 'bill.', fuente: 'FRED WRESBAL', url: 'https://fred.stlouisfed.org/series/WRESBAL' });
  h += kpi({ lab: 'Liquidez global G3', exp: 'Fed + BCE + Banco de Japón en dólares (sin PBoC)', serie: H.liquidez_global_T, unidad: 'bill. $', suf: 'bill.', fuente: 'FRED WALCL, ECBASSETSW, JPNASSETS, DEX*', url: 'https://fred.stlouisfed.org/series/ECBASSETSW' });
  h += kpi({ lab: 'Balance del BCE', exp: 'Activos del Eurosistema en dólares', serie: H.bce_T, unidad: 'bill. $', suf: 'bill.', fuente: 'FRED ECBASSETSW', url: 'https://fred.stlouisfed.org/series/ECBASSETSW' });
  h += kpi({ lab: 'Balance del Banco de Japón', exp: 'Activos en dólares (dato mensual)', serie: H.boj_T, unidad: 'bill. $', suf: 'bill.', fuente: 'FRED JPNASSETS', url: 'https://fred.stlouisfed.org/series/JPNASSETS', filas: [['1 mes', 28], ['3 meses', 90], ['12 meses', 365]] });
  h += '</div>';

  const desde = (H.sp500 && H.sp500.length ? H.sp500[0][0] : '2025-01-01');
  const lnS = (H.liquidez_neta_T || []).filter((x) => x[0] >= desde);
  const d0 = lnS.length ? lnS[0][0] : desde;
  h += '<div class="sect"><h2>Gráficos</h2></div><div class="grid g2"><div class="card"><h3>Liquidez neta de la Fed frente al S&amp;P 500</h3><div class="sub">Base 100 al inicio. Cuando se separan, uno de los dos está descontando algo que el otro no.</div>'
    + lw('cNeta', [{ name: 'Liquidez neta (Balance − TGA − RRP)', color: COL.amber, data: rebase(H.liquidez_neta_T || [], d0), prec: 1 }, { name: 'S&P 500', color: COL.blue, data: rebase(H.sp500 || [], d0), prec: 1 }])
    + foot('FRED WALCL · WTREGEN · RRPONTSYD · SP500', (lastOf(H.sp500) || [])[0]) + '</div>';
  h += '<div class="card"><h3>Liquidez global</h3><div class="sub">Balances de la Fed, el BCE y el Banco de Japón (bill. $, convertidos con tipos de cambio de la Fed)</div>'
    + lw('cGlob', [{ name: 'Total G3 (eje izq.)', color: COL.amber, data: H.liquidez_global_T, scale: 'left', prec: 2 }, { name: 'Fed', color: COL.white, data: H.balance_fed_T, w: 1 }, { name: 'BCE', color: COL.blue, data: H.bce_T, w: 1 }, { name: 'BoJ', color: COL.violet, data: H.boj_T, w: 1 }], { left: true })
    + foot('FRED WALCL · ECBASSETSW · JPNASSETS · DEXUSEU · DEXJPUS', (lastOf(H.liquidez_global_T) || [])[0]) + '</div>';
  h += '<div class="card"><h3>TGA y reservas bancarias</h3><div class="sub">Si el Tesoro engorda su cuenta, las reservas bajan (bill. $)</div>'
    + lw('cTga', [{ name: 'TGA', color: COL.neg, data: H.tga_T }, { name: 'Reservas', color: COL.pos, data: H.reservas_T }])
    + foot('FRED WTREGEN · WRESBAL', (lastOf(H.reservas_T) || [])[0]) + '</div>';
  h += '<div class="card"><h3>Condiciones financieras (NFCI) y repo inverso</h3><div class="sub">NFCI &gt; 0 = condiciones más duras que la media; RRP en bill. $</div>'
    + lw('cNfci', [{ name: 'NFCI (eje izq.)', color: COL.amber, data: H.nfci, scale: 'left', prec: 3 }, { name: 'RRP', color: COL.gray, data: H.rrp_T, prec: 3 }], { left: true })
    + foot('FRED NFCI · RRPONTSYD', (lastOf(H.nfci) || [])[0]) + '</div></div>';

  h += '<div class="sect"><h2>Checklist de liquidez</h2><span class="more">' + (cr.cumple ?? '—') + ' de ' + (cr.total ?? 8) + ' cumplidas</span></div><div class="grid g2"><div class="card pad0"><table class="t"><thead><tr><th>Condición</th><th>Estado</th><th>Nota</th></tr></thead><tbody>'
    + (E.checklist || []).map((c) => `<tr><td>${c.n}. ${esc(c.condicion)}</td><td>${ck(c.estado)}</td><td style="text-align:left;color:var(--dim);white-space:normal">${esc(c.nota || '')}</td></tr>`).join('') + '</tbody></table>' + footIn('Checklist NEXORA (FRED, Tesoro, Fed)', (lastOf(H.liquidez_neta_T) || [])[0]) + '</div>';
  h += '<div class="card pad0"><table class="t"><thead><tr><th>Secuencia del giro</th><th>Estado</th><th>Detalle</th></tr></thead><tbody>'
    + (E.secuencia || []).map((c) => `<tr><td>${c.n}. ${esc(c.paso)}</td><td>${ck(c.estado)}</td><td style="text-align:left;color:var(--dim);white-space:normal">${esc(c.detalle || '')}</td></tr>`).join('') + '</tbody></table>' + footIn('Secuencia NEXORA (FRED, Tesoro, Fed, Coinbase)', (lastOf(H.liquidez_neta_T) || [])[0]) + '</div></div>';

  h += '<div class="sect"><h2>Indicadores</h2><span class="more">valor · dirección · fuente · frecuencia</span></div><div class="card pad0 scroll"><table class="t"><thead><tr><th>Indicador</th><th>Valor</th><th>Dir.</th><th>Estado</th><th style="text-align:left">Detalle</th><th style="text-align:left">Fuente</th></tr></thead><tbody>'
    + (E.indicadores || []).map((i) => `<tr><td>${esc(i.nombre)}<small>${esc(i.nivel)}</small></td><td>${esc(i.valor)}</td><td class="${i.dir.includes('↑') ? 'up' : i.dir.includes('↓') ? 'down' : 'flat'}">${esc(i.dir)}</td><td>${ck(i.estado)}</td><td style="text-align:left;color:var(--muted);white-space:normal">${esc(i.detalle)}</td><td style="text-align:left;color:var(--dim);white-space:normal">${esc(i.fuente)} · ${esc(i.frecuencia)}</td></tr>`).join('') + '</tbody></table></div>';

  const pan = (E.contexto && E.contexto.panel) || [];
  if (pan.length) h += '<div class="sect"><h2>Contexto global</h2></div><div class="card pad0 scroll"><table class="t"><thead><tr><th>Señal</th><th>Estado</th><th>Valor</th><th style="text-align:left">Lectura</th><th style="text-align:left">Fuente</th></tr></thead><tbody>'
    + pan.map((p) => `<tr><td>${esc(p.nombre)}</td><td>${ck(p.estado)}</td><td>${esc(p.valor)}</td><td style="text-align:left;color:var(--muted);white-space:normal">${esc(p.lectura)}</td><td style="text-align:left;color:var(--dim);white-space:normal">${esc(p.fuente)}</td></tr>`).join('') + '</tbody></table></div>';
  const er = { ...(M.errores || {}), ...(L.errores_historico || {}) };
  if (Object.keys(er).length) h += `<div class="note">Fuentes sin dato en esta ejecución (SIN DATO, no se estima): ${Object.entries(er).map(([k, v]) => esc(k + ': ' + String(v).slice(0, 90))).join(' · ')}</div>`;
  return h;
}

/* calendario */
const calState = { rango: 'semana', imp: 'TODAS' };
function semanaMadrid(offset) {
  const hoy = pd(hoyISO());
  const dow = (hoy.getUTCDay() + 6) % 7;
  const ini = new Date(hoy - (dow - offset * 7) * 864e5);
  return [ini.toISOString().slice(0, 10), new Date(+ini + 6 * 864e5).toISOString().slice(0, 10)];
}
function calEventos() {
  const C = D.calendario; if (!C || !C.eventos) return [];
  const hoy = hoyISO();
  let ev = C.eventos;
  if (calState.rango === 'semana') { const [a, b] = semanaMadrid(0); ev = ev.filter((e) => e.fecha >= a && e.fecha <= b); }
  else if (calState.rango === 'siguiente') { const [a, b] = semanaMadrid(1); ev = ev.filter((e) => e.fecha >= a && e.fecha <= b); }
  else if (calState.rango === 'pasados') ev = ev.filter((e) => e.fecha < hoy && diasHasta(e.fecha) >= -7);
  else ev = ev.filter((e) => e.fecha >= hoy);
  if (calState.imp !== 'TODAS') ev = ev.filter((e) => e.importancia === calState.imp);
  return ev;
}
function evHtml(e) {
  const pasado = e.fecha < hoyISO();
  const pub = e.publicado;
  let chips = (e.afecta || '').split('·').map((x) => x.trim()).filter(Boolean).map((x) => `<span class="chip">${esc(x)}</span>`).join('');
  if (pub && !pub.sin_dato) {
    const u = pub.descripcion && /%/.test(pub.descripcion) ? ' %' : '';
    chips = `<span class="chip">${pasado ? 'Publicado' : 'Último dato'} <b>${num(pub.valor, Math.abs(pub.valor) >= 1000 ? 0 : 2)}${u}</b> · periodo ${esc(fdm(pub.periodo))}</span><span class="chip">Anterior <b>${num(pub.anterior, Math.abs(pub.anterior) >= 1000 ? 0 : 2)}${u}</b></span>` + chips;
  }
  const key = 'nx.consenso.' + e.fecha + '.' + e.evento;
  chips += `<span class="chip">Consenso (manual) <input data-k="${esc(key)}" value="${esc(lsGet(key, ''))}" placeholder="—" style="width:54px;background:none;border:0;border-bottom:1px solid var(--border2);color:var(--amber);font:inherit;text-align:center"></span>`;
  return `<div class="ev ${pasado ? 'past' : ''}"><div class="tm">${esc(e.hora_madrid || '—')}<small>${e.hora_ny ? 'NY ' + esc(e.hora_ny) : 'sin hora'}</small></div>
    <div class="imp ${esc(e.importancia)}" title="Importancia ${esc(e.importancia)}"><i></i><i></i><i></i></div>
    <div><div class="nm">${esc(e.evento)}</div><div class="qm">${esc(e.que_mirar)}</div><div class="meta"><a class="src" href="${esc(e.url)}" target="_blank" rel="noopener">${esc(e.fuente)}</a>${e.nota ? ' · ' + esc(e.nota) : ''}</div></div>
    <div class="chips">${chips}</div></div>`;
}
function drawCalendario() {
  const ev = calEventos(); const el = $('#calList'); if (!el) return;
  const dias = [...new Set(ev.map((e) => e.fecha))].sort();
  el.innerHTML = dias.length ? dias.map((d) => `<div class="day"><h4>${esc(fdd(d).toUpperCase())} <span>${diasHasta(d) === 0 ? 'HOY' : diasHasta(d) > 0 ? 'en ' + diasHasta(d) + (diasHasta(d) === 1 ? ' día' : ' días') : 'hace ' + -diasHasta(d) + ' días'}</span></h4>${ev.filter((e) => e.fecha === d).sort((a, b) => (a.hora_madrid || '99').localeCompare(b.hora_madrid || '99')).map(evHtml).join('')}</div>`).join('')
    : '<div class="card"><div class="empty" style="height:120px">SIN EVENTOS EN ESTE RANGO</div></div>';
  $$('input[data-k]', el).forEach((i) => i.addEventListener('change', () => lsSet(i.dataset.k, i.value)));
}
function pageCalendario() {
  const C = D.calendario;
  let h = head('Noticias', 'Calendario económico', 'Fechas y horas oficiales convertidas a Madrid y Nueva York. No incluye consenso de analistas (es de pago): hay un campo manual para anotarlo, que se guarda solo en tu navegador.', `Actualizado: ${C && C.generado_utc ? esc(horaAct(C.generado_utc)) : 'SIN DATO'} · ${C ? esc(C.nota) : ''}`);
  h += fallo('calendario');
  if (!C || !C.eventos) return h + noData('Calendario');
  const hoy = hoyISO();
  const sem = semanaMadrid(0);
  const altas = C.eventos.filter((e) => e.fecha >= sem[0] && e.fecha <= sem[1] && e.fecha >= hoy && e.importancia === 'ALTA').slice(0, 3);
  const pc = C.proximos_bancos_centrales || {};
  h += essential(`${C.eventos.filter((e) => e.fecha >= hoy).length} eventos en los próximos ${diasHasta(C.hasta)} días. ${altas.length ? 'Esta semana, de importancia alta: ' + altas.map((e) => `${esc(e.evento)} (${esc(fdd(e.fecha))} ${esc(e.hora_madrid || '')})`).join('; ') + '.' : 'Sin eventos de importancia alta lo que queda de semana.'}`,
    'Los datos de inflación y empleo mueven las expectativas de tipos (2Y, tipo real y dólar); los resultados de grandes empresas mueven los índices. La hipótesis sobre cada uno está en «qué mirar».',
    Object.keys(pc).length ? Object.entries(pc).map(([k, v]) => `${esc(k)} ${esc(fd(v.fecha))} (${cuentaAtras(v.fecha)})`).join(' · ') : 'Sin fecha de banco central en el rango.');
  if (Object.keys(pc).length) h += '<div class="grid g3">' + Object.entries(pc).map(([k, v]) => `<div class="card"><div class="eyebrow" style="color:var(--muted)">Decisión de tipos</div><div style="font-family:var(--serif);font-size:20px;margin:6px 0 2px">${esc(k)}</div><div class="mono">${esc(fdd(v.fecha))} · ${cuentaAtras(v.fecha)}</div>${foot('Calendario oficial del banco central', v.fecha)}</div>`).join('') + '</div>';
  h += `<div class="filters" id="calF" style="margin-top:18px">${[['semana', 'Esta semana'], ['siguiente', 'Próxima semana'], ['todo', 'Todo lo que viene'], ['pasados', 'Últimos 7 días']].map(([k, l]) => `<button class="fbtn ${calState.rango === k ? 'on' : ''}" data-r="${k}">${l}</button>`).join('')}<span style="width:14px"></span>${['TODAS', 'ALTA', 'MEDIA'].map((k) => `<button class="fbtn ${calState.imp === k ? 'on' : ''}" data-i="${k}">${k === 'TODAS' ? 'Toda importancia' : k.charAt(0) + k.slice(1).toLowerCase()}</button>`).join('')}</div><div id="calList"></div>`;
  MOUNT.push(() => {
    drawCalendario();
    $('#calF').addEventListener('click', (e) => {
      const b = e.target.closest('button'); if (!b) return;
      if (b.dataset.r) calState.rango = b.dataset.r;
      if (b.dataset.i) calState.imp = b.dataset.i;
      $$('#calF button').forEach((x) => x.classList.toggle('on', (x.dataset.r && x.dataset.r === calState.rango) || (x.dataset.i && x.dataset.i === calState.imp)));
      drawCalendario();
    });
  });
  const U = C.ultimos_publicados || {};
  h += '<div class="sect"><h2>Últimos datos de referencia</h2><span class="more">periodo ≠ fecha de publicación · sin consenso</span></div><div class="card pad0 scroll"><table class="t"><thead><tr><th>Dato</th><th>Periodo</th><th>Valor</th><th>Anterior</th><th>Publicado</th><th style="text-align:left">Fuente</th></tr></thead><tbody>'
    + Object.entries(U).map(([n, v]) => v.sin_dato ? `<tr><td>${esc(n)}</td><td colspan="4" style="color:var(--dim);text-align:left">SIN DATO</td><td style="text-align:left;color:var(--dim)">${esc(v.fuente)}</td></tr>`
      : `<tr><td>${esc(n)}<small>${esc(v.descripcion)}</small></td><td>${esc(fdm(v.periodo))}</td><td>${num(v.valor, Math.abs(v.valor) >= 1000 ? 0 : 2)}</td><td>${num(v.anterior, Math.abs(v.anterior) >= 1000 ? 0 : 2)} <small>${esc(fdm(v.anterior_periodo))}</small></td><td>${v.fecha_publicacion ? esc(fdy(v.fecha_publicacion)) : '<span style="color:var(--dim)">fuera del rango</span>'}</td><td style="text-align:left"><a class="src" href="${esc(v.url)}" target="_blank" rel="noopener">${esc(v.fuente)}</a></td></tr>`).join('')
    + '</tbody></table></div>';
  if (C.errores && Object.keys(C.errores).length) h += `<div class="note">Fuentes sin dato (SIN DATO): ${Object.entries(C.errores).map(([k, v]) => esc(k + ': ' + String(v).slice(0, 90))).join(' · ')}</div>`;
  return h;
}

/* ------------------------------------------------------------------ fase 2: Ciclo y crédito, Régimen macro, Datos publicados, alertas */
const fdh = (iso, hora) => (iso ? `${fdd(iso)}${hora ? ' · ' + hora : ''}` : '—');
const TONO_CSS = { pos: 'var(--pos)', amb: 'var(--amber)', neg: 'var(--neg)' };
function footIn(src, fecha, url, extra) { return `<div style="padding:0 16px 12px">${foot(src, fecha, url, extra)}</div>`; }
function pillAbs(v, dec, suf, inv) { return pill(v == null ? null : v, dec, suf, inv); }

const FASE_TXT = {
  'EXPANSIÓN': 'Ninguna o casi ninguna señal adelantada avisa de recesión y la regla de Sahm no ha saltado: el riesgo de ciclo es bajo con estas reglas. Es lo que dicen los datos hoy, no una garantía.',
  'DESACELERACIÓN': 'Dos o tres señales adelantadas están encendidas: la economía pierde velocidad. Suele pesar sobre beneficios y favorecer a lo defensivo (interpretación, no hecho).',
  'RIESGO ALTO': 'Cuatro o más señales adelantadas encendidas: zona de riesgo alto de recesión en 12-18 meses según las reglas de NEXORA (hipótesis, no predicción).',
  'RECESIÓN PROBABLE': 'La regla de Sahm ya salta: el paro ha subido 0,5 puntos sobre su mínimo, lo que históricamente confirma que la recesión ha empezado (hecho medido; confirmación, no anticipo).',
};
const faseClave = (f) => Object.keys(FASE_TXT).find((k) => String(f).startsWith(k)) || '';
const RULE = { curva: '10Y − 3M < 0 pp', desinversion: 'curva ≥ 0 tras ≥ 3 meses invertida en los 12 previos', ebp: 'EBP > 0,5', baa: 'Baa − 10Y sube ≥ 0,5 pp en 6 meses', sloos: '> 20 % neto de bancos endureciendo',
  nfci: 'NFCI > 0', claims: 'media 4 sem. ≥ +20 % sobre su mínimo de 12 meses', permisos: '≤ −20 % interanual', temporal: '≤ −3 % interanual', sahm: '≥ 0,5 pp' };
const TIPO_SEN = { adelantada: 'adelantada', coincidente: 'coincidente', 'confirmación': 'confirmación' };
function fmtSen(h) {
  const v = h.valor; if (v == null) return null;
  if (h.id === 'claims') return num(v, 0);
  const d = ['curva', 'desinversion', 'ebp', 'baa', 'nfci', 'sahm'].includes(h.id) ? 2 : 1;
  const u = { curva: ' pp', desinversion: ' pp', baa: ' pp', sloos: ' % neto', sahm: ' pp', permisos: ' % a/a', temporal: ' % a/a' }[h.id] || '';
  return num(v, d) + u;
}
function pageCiclo() {
  const C = D.ciclo;
  let h = head('Análisis', 'Ciclo y crédito EE. UU.', 'Diez señales de economía real y crédito con las reglas de ciclo.py de NEXORA: la regla de Sahm confirma la recesión; cuatro o más señales adelantadas encendidas = riesgo alto; dos o tres = desaceleración. Más el estrés diario del crédito (IG, BBB, HY, CCC).',
    `Actualizado: ${C && C.generado_utc ? esc(horaAct(C.generado_utc)) : 'SIN DATO'} · cada señal lleva el mes de su dato`);
  h += fallo('ciclo');
  if (!C || !C.senales) return h + noData('Ciclo y crédito');
  const sh = C.senales.find((s) => s.id === 'sahm');
  const encendidas = C.senales.filter((s) => s.encendida);
  const clave = faseClave(C.fase);
  const S = C.series || {};
  h += essential(`Fase <b style="color:${TONO_CSS[C.tono]}">${esc(C.fase)}</b>: ${C.senales_adelantadas_encendidas} de ${C.senales_adelantadas_total} señales adelantadas encendidas${encendidas.length ? ' (' + encendidas.map((s) => esc(s.senal)).join('; ') + ')' : ''}; regla de Sahm ${sh && sh.encendida ? 'ENCENDIDA' : sh && sh.encendida === false ? 'apagada' : 'SIN DATO'}. Probabilidad de recesión a 12 meses: ${C.prob_recesion_curva_nyfed != null ? num(C.prob_recesion_curva_nyfed, 1) + ' % (curva, modelo de la Fed de NY)' : 'SIN DATO'}${C.prob_recesion_ebp_fed != null ? ' · ' + num(C.prob_recesion_ebp_fed, 1) + ' % (EBP, Fed)' : ''}.`,
    esc(FASE_TXT[clave] || ''),
    `${esc(C.estado_credito)}. Un cambio de fase, una señal que se enciende o un salto de crédito (IG +10 / BBB +12 / HY +25 / CCC +60 pb en 5 días) dispara alerta en Telegram.`);

  h += `<div class="state" style="grid-template-columns:repeat(3,1fr)"><div class="card"><div class="eb">Fase del ciclo</div><div class="v" style="color:${TONO_CSS[C.tono]};font-size:20px">${esc(C.fase)}</div>
    <div class="lamps">${C.senales.map((s) => `<i class="${s.encendida === true ? 'on' : s.encendida === false ? 'off' : 'nd'}" title="${esc(s.senal + ': ' + (s.encendida === true ? 'ENCENDIDA' : s.encendida === false ? 'APAGADA' : 'SIN DATO'))}"></i>`).join('')}</div>
    <p style="margin-top:8px">Reglas de ciclo.py: Sahm → RECESIÓN PROBABLE · ≥ 4 adelantadas → RIESGO ALTO · ≥ 2 → DESACELERACIÓN · resto EXPANSIÓN.</p>${foot('NEXORA ciclo.py sobre FRED, Fed y Fed de Chicago', false, null, 'cuenta de señales')}</div>
    <div class="card"><div class="eb">Probabilidad de recesión a 12 meses</div><div class="v">${C.prob_recesion_curva_nyfed != null ? num(C.prob_recesion_curva_nyfed, 1) + ' %' : SD}</div>
    <p>Según la curva 10Y−3M (${C.curva_10y3m != null ? num(C.curva_10y3m, 2) + ' pp' : 'SIN DATO'}), modelo probit de la Fed de Nueva York. Según la prima de riesgo de los bonos (EBP, Fed): <b style="color:var(--text)">${C.prob_recesion_ebp_fed != null ? num(C.prob_recesion_ebp_fed, 1) + ' %' : 'SIN DATO'}</b>${C.prob_ebp_mes ? ' (' + esc(fdm(C.prob_ebp_mes + '-01')) + ')' : ''}. Son probabilidades estadísticas, no predicciones.</p>${foot('Fed de Nueva York (probit) · Reserva Federal (EBP)', false, 'https://www.newyorkfed.org/research/capital_markets/ycfaq', 'dato mensual / diario')}</div>
    <div class="card"><div class="eb">Estado del crédito</div><div class="v" style="font-size:20px;color:${/TENSI/.test(C.estado_credito) ? 'var(--neg)' : 'var(--pos)'}">${esc(C.estado_credito.split(':')[0])}</div>
    <p>${esc(C.estado_credito.includes(':') ? C.estado_credito.split(':').slice(1).join(':').trim() : 'Ningún diferencial supera sus umbrales de 5 días ni de 1 mes.')}</p>${foot('ICE BofA vía FRED', (C.credito.hy || {}).fecha)}</div></div>`;

  h += '<div class="sect"><h2>Las señales</h2><span class="more">rojo = encendida (avisa) · verde = apagada · gris = SIN DATO · «avisó» = recesiones precedidas desde que existe la señal</span></div><div class="grid g3">';
  h += C.senales.map((s) => {
    const v = (C.validacion || {})[s.id];
    const val = v ? `Avisó ${v.avisadas}/${v.recesiones} recesiones · ${v.falsas_alarmas} falsas alarmas${v.antelacion_mediana_meses != null ? ' · ' + num(v.antelacion_mediana_meses, 0) + ' meses de antelación típica' : v.retraso_mediano_meses != null ? ' · salta ' + num(v.retraso_mediano_meses, 0) + ' meses tras el inicio' : ''} (desde ${esc(v.desde)})` : 'Sin historial de activaciones para validar';
    const mes = s.mes ? s.mes + '-01' : null;
    return `<div class="card sig ${s.encendida === true ? 'on' : s.encendida === false ? 'off' : 'nd'}"><div class="top"><div class="nm">${esc(s.senal)}</div><span class="ck ${s.encendida === true ? 'no' : s.encendida === false ? 'ok' : 'sd'}">${s.encendida === true ? 'ENCENDIDA' : s.encendida === false ? 'APAGADA' : 'SIN DATO'}</span></div>
      <div class="big mono">${fmtSen(s) || SD}</div><div class="note" style="margin:6px 0 0">Se enciende si ${esc(RULE[s.id] || '')} · ${esc(TIPO_SEN[s.tipo] || s.tipo)}</div>
      <div class="note" style="margin:4px 0 0">${esc(s.que_mide)}</div><div class="note" style="margin:4px 0 0;color:var(--dim)">${val}</div>
      ${foot(s.fuente, false, null, mes ? 'dato ' + (s.id === 'claims' ? esc(fdm(mes)) + ' (semanal)' : esc(fdm(mes))) : 'SIN DATO')}</div>`;
  }).join('') + '</div>';

  h += '<div class="sect"><h2>Diferenciales de crédito</h2><span class="more">pb · si suben, financiarse cuesta más (rojo) · umbrales de alerta UMB_CRED de ciclo.py</span></div><div class="grid g4">';
  const U = C.umb_cred || {};
  h += ['ig', 'bbb', 'hy', 'ccc'].map((k) => {
    const m = (C.credito || {})[k];
    if (!m) return `<div class="card kpi"><div class="lab">${k.toUpperCase()}</div><div class="big">${SD}</div>${foot('FRED (ICE BofA)', null)}</div>`;
    const serie = (S.oas || {})[k];
    return `<div class="card kpi"><div class="lab">${esc(m.nombre)}</div><div class="exp">Diferencial frente al Tesoro (OAS, ICE BofA) · percentil ${m.percentil_1a} del último año · mínimo 1 año ${num(m.min_1a_pb, 0)} pb</div><div class="big">${num(m.pb, 0)}<small>pb</small></div>${serie ? spark(serie, 126) : ''}
      <table><tr><td>5 días <span style="color:var(--dim)">(alerta ≥ ${(U[k] || [])[0] ?? '—'})</span></td><td>${pill(m.d5_pb ?? m['5d_pb'], 0, ' pb', true)}</td></tr><tr><td>1 mes <span style="color:var(--dim)">(≥ ${(U[k] || [])[1] ?? '—'})</span></td><td>${pill(m['1m_pb'], 0, ' pb', true)}</td></tr><tr><td>3 meses</td><td>${pill(m['3m_pb'], 0, ' pb', true)}</td></tr></table>
      ${foot('FRED ' + ({ ig: 'BAMLC0A0CM', bbb: 'BAMLC0A4CBBB', hy: 'BAMLH0A0HYM2', ccc: 'BAMLH0A3HYC' })[k] + ' (ICE BofA)', m.fecha, 'https://fred.stlouisfed.org/series/' + ({ ig: 'BAMLC0A0CM', bbb: 'BAMLC0A4CBBB', hy: 'BAMLH0A0HYM2', ccc: 'BAMLH0A3HYC' })[k])}</div>`;
  }).join('') + '</div>';

  const oas = S.oas || {};
  h += '<div class="sect"><h2>Gráficos</h2></div><div class="grid g2">';
  h += `<div class="card"><h3>Grado de inversión y BBB</h3><div class="sub">pb · más alto = más estrés en el crédito de calidad</div>${lw('cIgBbb', [{ name: 'IG', color: COL.blue, data: oas.ig, prec: 0 }, { name: 'BBB', color: COL.amber, data: oas.bbb, prec: 0 }])}${foot('FRED BAMLC0A0CM · BAMLC0A4CBBB (ICE BofA)', (lastOf(oas.ig) || [])[0], 'https://fred.stlouisfed.org/series/BAMLC0A4CBBB')}</div>`;
  h += `<div class="card"><h3>High yield y CCC</h3><div class="sub">pb · CCC en el eje izquierdo (escala mucho mayor)</div>${lw('cHyCcc', [{ name: 'CCC (eje izq.)', color: COL.neg, data: oas.ccc, scale: 'left', prec: 0 }, { name: 'High yield', color: COL.amber, data: oas.hy, prec: 0 }], { left: true })}${foot('FRED BAMLH0A0HYM2 · BAMLH0A3HYC (ICE BofA)', (lastOf(oas.hy) || [])[0], 'https://fred.stlouisfed.org/series/BAMLH0A3HYC')}</div>`;
  const umb = (a, v) => (a || []).map(([t]) => [t, v]);
  h += `<div class="card"><h3>Probabilidad de recesión según la curva (probit)</h3><div class="sub">% a 12 meses · probit de la Fed de Nueva York aplicado a la curva 10Y−3M mensual</div>${lw('cProbit', [{ name: 'Probabilidad (curva)', color: COL.amber, data: S.probit, area: true, prec: 1 }, { name: 'Según EBP (Fed)', color: COL.blue, data: S.ebp_prob, prec: 1 }])}${foot('Fed de Nueva York (probit) · FRED GS10, TB3MS · Fed (EBP)', false, 'https://www.newyorkfed.org/research/capital_markets/ycfaq', 'dato mensual')}</div>`;
  h += `<div class="card"><h3>Prima de bono en exceso (EBP)</h3><div class="sub">pp · parte del diferencial de crédito que no explica el riesgo de impago · la señal se enciende por encima de 0,5</div>${lw('cEbp', [{ name: 'EBP', color: COL.amber, data: S.ebp, prec: 2 }, { name: 'Umbral 0,5', color: COL.neg, data: umb(S.ebp, 0.5), w: 1, prec: 2 }])}${foot('Reserva Federal (Gilchrist-Zakrajšek)', false, 'https://www.federalreserve.gov/econres/notes/feds-notes/ebp_csv.csv', C.prob_ebp_mes ? 'dato mensual · ' + esc(fdm(C.prob_ebp_mes + '-01')) : '')}</div>`;
  h += `<div class="card"><h3>Curva de tipos 10Y − 3M</h3><div class="sub">pp · por debajo de 0 = curva invertida (señal encendida)</div>${lw('cCurva', [{ name: '10Y − 3M mensual', color: COL.amber, data: S.curva_mensual, prec: 2 }, { name: 'Diaria', color: COL.blue, data: S.curva_diaria, w: 1, prec: 2 }, { name: 'Cero', color: COL.gray, data: umb(S.curva_mensual, 0), w: 1, prec: 2 }])}${foot('FRED GS10 · TB3MS · T10Y3M', (lastOf(S.curva_diaria) || [])[0], 'https://fred.stlouisfed.org/series/T10Y3M')}</div>`;
  h += `<div class="card"><h3>Condiciones financieras (NFCI) y regla de Sahm</h3><div class="sub">NFCI &gt; 0 = más duras que la media · Sahm ≥ 0,5 = recesión en marcha</div>${lw('cNfci2', [{ name: 'NFCI (eje izq.)', color: COL.amber, data: S.nfci, scale: 'left', prec: 2 }, { name: 'Sahm', color: COL.neg, data: S.sahm, prec: 2 }], { left: true })}${foot('FRED NFCI · SAHMREALTIME', (lastOf(S.nfci) || [])[0], 'https://fred.stlouisfed.org/series/SAHMREALTIME')}</div></div>`;

  h += '<div class="sect"><h2>Reglas y fuentes de cada señal</h2><span class="more">ciclo.py · umbrales CRITERIO NEXORA salvo Sahm 0,5 y el probit de la Fed de NY</span></div><div class="card pad0 scroll"><table class="t"><thead><tr><th>Señal</th><th>Tipo</th><th>Valor</th><th style="text-align:left">Se enciende si</th><th>Estado</th><th>Mes</th><th style="text-align:left">Fuente</th></tr></thead><tbody>'
    + C.senales.map((s) => `<tr><td>${esc(s.senal)}</td><td>${esc(s.tipo)}</td><td>${fmtSen(s) || 'SIN DATO'}</td><td style="text-align:left;color:var(--muted)">${esc(RULE[s.id] || '')}</td><td>${s.encendida === true ? '<span class="ck no">ENCENDIDA</span>' : s.encendida === false ? '<span class="ck ok">APAGADA</span>' : '<span class="ck sd">SIN DATO</span>'}</td><td>${esc(s.mes || '—')}</td><td style="text-align:left;color:var(--dim)">${esc(s.fuente)}</td></tr>`).join('')
    + '</tbody></table></div><div class="note">' + esc(C.nota || '') + ' Si una fuente falla la señal queda SIN DATO y no cuenta.</div>';
  if (C.errores && Object.keys(C.errores).length) h += `<div class="note">Fuentes sin dato: ${Object.entries(C.errores).map(([k, v]) => esc(k + ': ' + String(v).slice(0, 90))).join(' · ')}</div>`;
  return h;
}

/* ---------------- régimen macro */
function tonoDim(d) {
  const e = (d.estado || '').toUpperCase(), n = d.dimension;
  if (/SIN DATO/.test(e)) return 'sd';
  const T = (re) => re.test(e);
  if (n === 'INFLACIÓN') return T(/DESACELER/) ? 'ok' : T(/ACELER/) ? 'no' : 'par';
  if (n === 'CRECIMIENTO' || n === 'EMPLEO') return T(/DETERIOR|DESACELER|SE ENFR|CAE|DÉBIL/) ? 'no' : T(/FIRME|ACELER|MEJOR/) ? 'ok' : 'par';
  if (n === 'LIQUIDEZ') return T(/RESTRICT|DESFAV|DREN/) ? 'no' : T(/EXPANSIV|FAVOR|INYECT/) ? 'ok' : 'par';
  if (n === 'CRÉDITO') return T(/ESTR[ÉE]S|SE ENDURECE/) ? 'no' : T(/RELAJ|LAXO|MEJOR/) ? 'ok' : 'par';
  if (n === 'POLÍTICA MONETARIA') return T(/ENDURECIENDO|RESTRICT/) ? 'no' : T(/RECORT|EXPANSIV|RELAJ/) ? 'ok' : 'par';
  if (n === 'FISCAL') return T(/RESTRICT/) ? 'no' : T(/EXPANSIV/) ? 'ok' : 'par';
  if (n === 'CONDICIONES FINANCIERAS') return T(/ENDURECI/) ? 'no' : T(/RELAJ|LAXAS/) ? 'ok' : 'par';
  if (n === 'CURVA DE TIPOS') return T(/INVERTID/) ? 'no' : 'par';
  if (n === 'DÓLAR') return T(/FORTALEC|FUERTE/) ? 'no' : T(/DEBILIT/) ? 'ok' : 'par';
  return 'par';
}
function pageRegimen() {
  const G = D.regimen;
  let h = head('Análisis', 'Régimen macro', 'Mapa de las condiciones macro de EE. UU.: crecimiento, inflación, empleo, liquidez, crédito, política monetaria, fiscal, condiciones financieras, curva y dólar, y si los tres monitores de NEXORA cuentan la misma historia.',
    `Actualizado: ${G && G.generado_utc ? esc(horaAct(G.generado_utc)) : 'SIN DATO'} · cada dimensión muestra su evidencia y su fuente`);
  h += fallo('regimen');
  if (!G || !G.evaluacion) return h + noData('Régimen macro');
  const E = G.evaluacion;
  const q = (t) => (E.preguntas.find((x) => x.pregunta.includes(t)) || {}).respuesta || 'SIN DATO';
  h += essential(`Régimen: <b style="color:var(--text)">${esc(E.cuadrante)}</b> (${esc(E.fuerza)}). Riesgo en índices: ${esc(E.riesgo)} · liquidez: ${esc(E.liquidez)}. ${esc(q('acelerando'))}`,
    `Monitores: ${esc(E.concordancia)}. ${esc(E.motor_lectura)}. ${E.contradicciones.length ? `Hay ${E.contradicciones.length} contradicción(es) entre mercados y macro (abajo): son hipótesis a vigilar, no hechos.` : 'Sin contradicciones entre mercados y macro según las reglas.'}`,
    esc(q('datos pueden cambiarlo')).slice(0, 320));
  h += `<div class="state" style="grid-template-columns:repeat(4,1fr)">${[['Régimen', E.cuadrante, E.fuerza], ['Riesgo (índices)', E.riesgo, 'monitor de índices'], ['Liquidez', E.liquidez, 'monitor de liquidez'], ['Monitores', E.concordancia.replace('LOS TRES COINCIDEN: ', 'Coinciden: '), E.motor_lectura]]
    .map(([a, b, c]) => `<div class="card"><div class="eb">${a}</div><div class="v" style="font-size:18px">${esc(b)}</div><p>${esc(c)}</p></div>`).join('')}</div>`;
  h += '<div class="sect"><h2>Mapa de régimen</h2><span class="more">color = presión sobre activos de riesgo: verde apoya · ámbar neutral · rojo presiona (criterio NEXORA sobre el texto del estado)</span></div><div class="grid g3">';
  h += E.mapa.map((d) => {
    const t = tonoDim(d);
    const ev = (d.evidencia || []).slice(0, 6);
    return `<div class="card dim ${t}"><div class="top"><div class="nm">${esc(d.dimension)}</div><span class="ck ${t}">${esc(d.dir || '')}</span></div>
      <div class="estado">${esc(d.estado)}</div><ul class="ev-list">${ev.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>${foot(d.fuente || 'NEXORA', false, null, esc(G.evaluacion && G.generado_utc ? 'corte ' + horaAct(G.generado_utc) : ''))}</div>`;
  }).join('') + '</div>';

  h += '<div class="sect"><h2>Los tres monitores</h2><span class="more">¿cuentan la misma historia?</span></div><div class="card pad0 scroll"><table class="t"><thead><tr><th>Monitor</th><th style="text-align:left">Lectura</th><th>Sentido</th><th>Precio</th><th style="text-align:left">Detalle</th></tr></thead><tbody>'
    + E.monitores.map((m) => `<tr><td>${esc(m.monitor)}</td><td style="text-align:left">${esc(m.lectura)}</td><td>${ck(m.sentido)}</td><td>${esc(m.precio)}</td><td style="text-align:left;color:var(--dim);white-space:normal">${esc(m.detalle)}</td></tr>`).join('') + '</tbody></table>'
    + footIn('Monitores NEXORA (liquidez, oro, índices) sobre FRED, Tesoro, Cboe, Coinbase', false, null, esc(G.generado_utc ? horaAct(G.generado_utc) : '')) + '</div>';

  h += '<div class="grid g2" style="margin-top:12px"><div><div class="sect" style="margin-top:14px"><h2>Motor común</h2><span class="more">¿hay una causa que mueva a todos?</span></div><div class="card pad0"><table class="t"><thead><tr><th>Motor</th><th>Valor</th><th style="text-align:left">Efecto</th></tr></thead><tbody>'
    + E.motor.map((m) => `<tr><td>${esc(m.motor)}</td><td>${esc(m.valor)}</td><td style="text-align:left;color:var(--muted);white-space:normal">${esc(m.efecto)}</td></tr>`).join('') + '</tbody></table>'
    + footIn('Tesoro de EE. UU., BCE, FRED NFCI, FedWatch NEXORA', false) + '</div></div>';
  h += '<div><div class="sect" style="margin-top:14px"><h2>Patrones cross-asset del último mes</h2><span class="more">reglas cumplidas / total</span></div><div class="card">'
    + E.patrones.map((p) => `<div class="patron"><div class="pn"><span>${esc(p.patron)}</span><span class="mono">${p.cumple}/${p.de}</span></div><div class="pbar"><i style="width:${p.pct}%"></i></div></div>`).join('')
    + `<div class="note">Patrón dominante: ${E.patron_dominante.length ? esc(E.patron_dominante.join(', ')) : 'ninguno (se necesita ≥ 75 % de las reglas)'}.</div>` + foot('Cboe, FRED, Coinbase, Tesoro, BCE', false) + '</div></div></div>';

  h += '<div class="sect"><h2>Contradicciones</h2><span class="more">lo que un activo hace y la macro no explica</span></div>';
  h += E.contradicciones.length ? '<div class="grid g2">' + E.contradicciones.map((c) => `<div class="card"><p style="margin:0;color:#c4c9d0">${esc(c)}</p>${foot('Reglas NEXORA sobre los tres monitores', false)}</div>`).join('') + '</div>' : '<div class="card"><div class="empty" style="height:80px">SIN CONTRADICCIONES SEGÚN LAS REGLAS</div></div>';

  h += '<div class="sect"><h2>Preguntas clave</h2><span class="more">respondidas con datos</span></div><div class="card pad0">'
    + E.preguntas.map((p) => `<details class="qa"><summary>${esc(p.pregunta)}</summary><p>${esc(p.respuesta)}</p></details>`).join('') + footIn('Mapa de régimen NEXORA', false) + '</div>';
  if (E.cuadrante_simple) h += `<div class="note">Cuadrante simplificado (comparable con el histórico): ${esc(E.cuadrante_simple.cuadrante)} · ${esc(E.cuadrante_simple.detalle)}.</div>`;
  const er = G.errores || {};
  if (Object.keys(er).length) h += `<div class="note">Fuentes sin dato: ${Object.entries(er).map(([k, v]) => esc(k + ': ' + String(v).slice(0, 90))).join(' · ')}</div>`;
  return h;
}

/* ---------------- datos publicados */
function pagePublicados() {
  const P = D.publicados, C = D.calendario;
  let h = head('Noticias', 'Datos publicados', 'Últimas publicaciones macro con su periodo, su fecha de publicación y sus revisiones (formato original → revisado). El periodo del dato no es la fecha en que se publica: se muestran las dos.',
    `Actualizado: ${P && P.generado_utc ? esc(horaAct(P.generado_utc)) : 'SIN DATO'} · registro de revisiones desde el ${P ? esc(fdy(P.registro_desde)) : 'SIN DATO'}`);
  h += fallo('publicados');
  if (!P || !P.series) return h + noData('Datos publicados');
  const S = Object.entries(P.series).filter(([, v]) => !v.sin_dato);
  const rev = P.revisiones || [];
  const per = (v, p) => (v.serie === 'ICSA' ? fdy(p) : fdm(p));
  const prox = ((C && C.eventos) || []).filter((e) => e.fecha >= hoyISO() && e.importancia === 'ALTA').slice(0, 2);
  h += essential(`${S.length} series oficiales mostradas (${P.filas_registro} filas en el registro); ${P.n_revisiones} revisión(es) detectada(s) desde el ${esc(fdy(P.registro_desde))}. ${rev.length ? 'Última: ' + esc(rev[0].serie) + ' (' + esc(fdm(rev[0].periodo)) + ') ' + num(rev[0].original, 2) + ' → ' + num(rev[0].revisado, 2) + '.' : 'Todavía ninguna: aparecen cuando un periodo ya guardado cambia de valor.'}`,
    'Hecho: cada cifra es la que publica la fuente oficial; «original» es el primer valor que NEXORA registró y «revisado» el último. Interpretación: si un dato se revisa, la lectura que se hizo del primer valor queda desfasada: compara siempre original → revisado.',
    prox.length ? `Próximas publicaciones de importancia alta: ${prox.map((e) => `${esc(fdh(e.fecha, e.hora_madrid))} ${esc(e.evento)}`).join(' · ')}.` : 'Sin publicaciones de importancia alta en el calendario próximo.');
  h += '<div class="sect"><h2>Revisiones detectadas</h2><span class="more">dato original → revisado (nivel de la serie oficial)</span></div>';
  h += rev.length ? '<div class="card pad0 scroll"><table class="t"><thead><tr><th>Dato</th><th>Periodo</th><th>Original</th><th>Revisado</th><th>Cambio</th><th>Detectado</th></tr></thead><tbody>'
    + rev.map((r) => `<tr><td>${esc(r.serie)}</td><td>${esc(r.id === 'ICSA' ? fdy(r.periodo) : fdm(r.periodo))}</td><td>${num(r.original, 2)}</td><td><b>${num(r.revisado, 2)}</b></td><td>${pill(r.revisado - r.original, 2, '', false)}</td><td>${esc(fdy(r.visto))}</td></tr>`).join('') + '</tbody></table>' + footIn('Registro NEXORA data/publicaciones_macro.csv sobre FRED', false, 'https://github.com/komonartisans-ops/nexora-terminal/blob/main/data/publicaciones_macro.csv', 'tipo REVISIÓN') + '</div>'
    : `<div class="card"><div class="empty" style="height:90px">SIN REVISIONES DESDE EL INICIO DEL REGISTRO</div><div class="note">${esc(P.nota)} El registro (${P.filas_registro} filas) solo se añade y no duplica nada.</div>${foot('Registro NEXORA data/publicaciones_macro.csv', false, 'https://github.com/komonartisans-ops/nexora-terminal/blob/main/data/publicaciones_macro.csv', 'registro desde ' + esc(fdy(P.registro_desde)))}</div>`;
  h += '<div class="sect"><h2>Series</h2><span class="more">último periodo · valor · variación frente al anterior · fecha de publicación</span></div><div class="grid g3">';
  h += Object.entries(P.series).map(([nombre, v]) => {
    if (v.sin_dato) return `<div class="card kpi"><div class="lab">${esc(nombre)}</div><div class="big">${SD}</div>${foot(v.fuente, null, v.url)}</div>`;
    const ps = v.periodos, a = ps[ps.length - 1], b = ps[ps.length - 2];
    const dec = v.decimales, u = v.unidad === '%' ? ' %' : v.unidad === 'mil' ? ' mil' : '';
    return `<div class="card kpi"><div class="lab">${esc(nombre)}</div><div class="exp">${esc(v.descripcion)}</div>
      <div class="big">${num(a.valor, dec)}<small>${esc(u.trim() || v.unidad)}</small></div>
      <div class="chg">${b ? pill(a.valor - b.valor, dec, v.unidad === '%' ? ' pp' : '', false) : ''} <span style="color:var(--dim);font-size:10.5px">frente a ${esc(per(v, b && b.periodo))}</span></div>
      <table class="mini"><tr><th>Periodo</th><th>Valor</th><th>Original → revisado</th></tr>${ps.slice().reverse().map((p) => `<tr><td>${esc(per(v, p.periodo))}</td><td>${num(p.valor, dec)}</td><td>${p.revisado ? `<span class="down">${num(p.nivel_original, 2)} → ${num(p.nivel_actual, 2)}</span>` : '<span style="color:var(--dim)">sin revisar</span>'}</td></tr>`).join('')}</table>
      <div class="note" style="margin:8px 0 0">Periodo: <b style="color:var(--text)">${esc(per(v, a.periodo))}</b> · Publicado: <b style="color:var(--text)">${v.fecha_publicacion_calendario ? esc(fdd(v.fecha_publicacion_calendario)) : 'sin fecha en el calendario'}</b> · Registrado por NEXORA: ${a.visto_primera_vez ? esc(fdy(a.visto_primera_vez)) : '—'}${a.tipo_primer_registro && a.tipo_primer_registro.startsWith('HIST') ? ' (carga inicial)' : ''}</div>
      ${foot(v.fuente, false, v.url, 'periodo ' + esc(per(v, a.periodo)))}</div>`;
  }).join('') + '</div>';
  h += `<div class="note">${esc(P.nota)} «Registrado por NEXORA» es la fecha de nuestra captura, no la oficial de publicación; esa sale del calendario económico. En la tabla de cada serie, «original → revisado» está en el nivel de la serie oficial (p. ej. miles de empleos, índice de precios). Memoria permanente: <a class="src" href="https://github.com/komonartisans-ops/nexora-terminal/blob/main/data/publicaciones_macro.csv" target="_blank" rel="noopener">data/publicaciones_macro.csv</a> (${P.filas_registro} filas).</div>`;
  if (P.errores && Object.keys(P.errores).length) h += `<div class="note">Fuentes sin dato (SIN DATO): ${Object.entries(P.errores).map(([k, v]) => esc(k + ': ' + String(v).slice(0, 90))).join(' · ')}</div>`;
  return h;
}

/* ---------------- alertas (tarjeta para el Resumen) */
function cardAlertas() {
  const A = D.alertas;
  if (!A) return `<div class="sect"><h2>Alertas Telegram</h2></div><div class="card"><div class="empty" style="height:70px">SIN DATO · alertas todavía no evaluadas</div></div>`;
  const r = (A.recientes || []).slice(-5).reverse();
  const U = A.umbrales || {};
  return `<div class="sect"><h2>Alertas Telegram</h2><span class="more">${A.telegram_configurado ? 'canal activo' : 'canal sin configurar en esta ejecución'}</span></div><div class="card">
    ${r.length ? r.map((x) => `<div class="alrt"><span class="mono" style="color:var(--dim);font-size:10.5px">${esc(horaAct(x.fecha_utc))}</span><span>${esc(x.titulo)}</span><span class="ck ${x.enviada ? 'ok' : 'no'}">${x.enviada ? 'ENVIADA' : 'NO ENVIADA'}</span></div>`).join('') : '<div class="note" style="margin:0">Ninguna alerta disparada todavía: ningún umbral se ha cruzado.</div>'}
    <div class="note">Umbrales: Fed ±${U.fed_pts ?? 15} pts · 2Y ±${U.t2y_pb ?? 12} pb · 10Y real ±${U.real_pb ?? 8} pb · DXY ±${U.dxy_pct ?? 0.7} % · VIX &gt;${U.vix_nivel ?? 25} · IG +${U.ig_pb ?? 10} / BBB +${U.bbb_pb ?? 12} / HY +${U.hy_pb ?? 25} / CCC +${U.ccc_pb ?? 60} pb (5 d) · oro ±${U.oro_pct ?? 2} % · BTC −7 / +8 % · ETF BTC &lt;−500 M$. Una vez al día cada una.</div>
    ${foot('Motor de alertas NEXORA (data/estado_alertas.json)', false, null, esc('evaluado ' + horaAct(A.ultima_evaluacion_utc)))}</div>`;
}

function pagePlaceholder(p) {
  return head(p.g, p.t, esc(p.d), '') + `<div class="placeholder"><span class="fase">FASE ${p.f}</span><h2>${esc(p.t)}</h2><p>${esc(p.d)}.</p><p style="color:var(--dim)">Este módulo se construye en la fase ${p.f} (${esc(PLAN[p.f] || '')}). No hay datos de relleno: hasta entonces la página queda vacía a propósito.</p></div>`;
}

/* ------------------------------------------------------------------ banners y router */
function banners() {
  const m = D.meta; let h = '';
  if (!m) h = '<div class="banner red">SIN DATO: no se pudo leer meta.json. La web no tiene datos todavía.</div>';
  else {
    const ahora = Date.now();
    const viejas = Object.entries(m.etapas || {}).filter(([, v]) => { const d = stampDate(v.ultimo_ok_utc); return !d || isNaN(d) || (ahora - d) / 36e5 > 48; });
    if (viejas.length) h += `<div class="banner red">Dato con más de 48 h o sin copia válida: ${viejas.map(([k, v]) => `${esc(k)} (${v.ultimo_ok_utc ? esc(horaAct(v.ultimo_ok_utc)) : 'nunca'})`).join(' · ')}</div>`;
    const fallos = Object.entries(m.etapas || {}).filter(([k, v]) => !v.ok && !viejas.find((x) => x[0] === k));
    if (fallos.length) h += `<div class="banner amber">Fuente con fallo en la última ejecución: ${fallos.map(([k]) => esc(k)).join(', ')} · se muestra el último dato válido</div>`;
  }
  $('#banners').innerHTML = h;
}
function route() {
  const id = (location.hash.replace(/^#\//, '') || 'resumen').split('?')[0];
  const p = PAGES.find((x) => x.id === id) || PAGES[0];
  $$('.nav-btn').forEach((b) => b.classList.remove('active'));
  $$('.menu a').forEach((a) => a.classList.toggle('cur', a.dataset.id === p.id));
  const it = $(`.nav-item[data-g="${p.g}"] .nav-btn`); if (it) it.classList.add('active');
  MOUNT.length = 0;
  const fn = { resumen: pageResumen, bancos: pageBancos, liquidez: pageLiquidez, calendario: pageCalendario, ciclo: pageCiclo, regimen: pageRegimen, publicados: pagePublicados }[p.id] || (window.EXTRA_PAGES || {})[p.id];
  let html;
  try { html = fn ? fn() : pagePlaceholder(p); } catch (e) { console.error(e); html = head(p.g, p.t, '', '') + `<div class="banner red" style="border-radius:6px">Error al dibujar esta página: ${esc(e.message)}. El resto de la web sigue funcionando.</div>`; }
  $('#app').innerHTML = html;
  document.title = `${p.t} · NEXORA Terminal`;
  window.scrollTo(0, 0);
  MOUNT.forEach((f) => { try { f(); } catch (e) { console.error(e); } });
}

async function cargar() {
  await Promise.all(['meta', 'precios', 'fedwatch', 'tipos', 'calendario', 'liquidez', 'ciclo', 'publicados', 'resumen', 'regimen', 'alertas', 'oro', 'indices', 'series'].map(async (n) => {
    try { const r = await fetch(`data/${n}.json?v=${Date.now()}`, { cache: 'no-store' }); if (r.ok) D[n] = await r.json(); } catch (e) { /* SIN DATO */ }
  }));
}
(async function init() {
  buildNav(); tick(); setInterval(tick, 30000);
  await cargar(); banners();
  window.addEventListener('hashchange', route);
  route();
  setInterval(async () => { await cargar(); banners(); }, 15 * 60 * 1000);
})();
