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
  2: 'Alertas Telegram, Ciclo y crédito, Régimen macro y Datos publicados con revisiones.',
  3: 'Oro, Índices USA y Cripto.',
  4: 'COT (CFTC), Sesgo de divisas y Noticias RSS de bancos centrales.',
  5: 'Diario de operaciones, Watchlists y Registro de tesis (datos personales solo en tu navegador).',
};
const GROUPS = ['Mercados', 'Análisis', 'Noticias', 'Personal'];
const D = {};
const MOUNT = [];

function buildNav() {
  const nav = $('#nav');
  nav.innerHTML = GROUPS.map((g) => `<div class="nav-item" data-g="${g}">
    <button class="nav-btn">${g} <span class="chev">▾</span></button>
    <div class="menu">${PAGES.filter((p) => p.g === g).map((p) => `<a href="#/${p.id}" data-id="${p.id}"><div class="t">${esc(p.t)}${p.f > 1 ? `<span class="fase">F${p.f}</span>` : ''}</div><div class="d">${esc(p.d)}</div></a>`).join('')}</div>
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
  return `<div class="foot"><span>Fuente: ${s}</span><span>${fecha ? 'dato ' + esc(fdy(fecha)) + (extra ? ' · ' + extra : '') : (extra || 'dato SIN DATO')}</span></div>`;
}
function spark(serie, n = 60) {
  const s = (serie || []).slice(-n);
  if (s.length < 3) return '';
  const vs = s.map((x) => x[1]); const mn = Math.min(...vs), mx = Math.max(...vs), r = mx - mn || 1;
  const pts = vs.map((v, i) => `${(i / (vs.length - 1) * 100).toFixed(1)},${(30 - (v - mn) / r * 28).toFixed(1)}`).join(' ');
  const c = vs[vs.length - 1] >= vs[0] ? '#2FA36B' : '#C8463D';
  return `<svg class="spark" viewBox="0 0 100 32" preserveAspectRatio="none"><polygon points="0,32 ${pts} 100,32" fill="${c}" opacity=".12"/><polyline points="${pts}" fill="none" stroke="${c}" stroke-width="1.4" vector-effect="non-scaling-stroke"/></svg>`;
}
function ck(estado) {
  const e = String(estado || '').toUpperCase();
  const c = e === 'CUMPLE' || e === 'FAVORABLE' ? 'ok' : e === 'NO CUMPLE' || e === 'DESFAVORABLE' ? 'no' : e === 'PARCIAL' || e === 'NEUTRAL' ? 'par' : 'sd';
  return `<span class="ck ${c}">${esc(e || 'SIN DATO')}</span>`;
}
function tagTesis(et) {
  const m = { 'ALCISTA': 'alc', 'BAJISTA': 'baj', 'DÉBIL': 'deb', 'SIN TESIS': 'sin' };
  return et ? `<span class="tag ${m[et] || 'sin'}">${esc(et)}</span>` : '<span class="tag sd">NO CUBIERTO</span>';
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
    const leg = document.getElementById(id + '-leg');
    if (leg) chart.subscribeCrosshairMove((p) => {
      defs.forEach((d, i) => { const v = p.seriesData && p.seriesData.get(series[i]); const b = leg.querySelector(`[data-i="${i}"]`); if (b) b.textContent = v ? num(v.value, d.prec ?? 2) : ''; });
    });
    new ResizeObserver(() => chart.applyOptions({ width: el.clientWidth })).observe(el);
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
  return `<div class="legend" id="${id}-leg">${leg}${rng}</div><div class="chart ${opts.tall ? 'tall' : ''}" id="${id}"></div>`;
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

function pageResumen() {
  const R = D.resumen, P = D.precios, C = D.calendario;
  const act = (P && P.activos) || {};
  const orden = [['oro', 'Oro', 'USD'], ['btc', 'Bitcoin', 'USD'], ['spx', 'S&P 500', 'pts'], ['ndx', 'Nasdaq 100', 'pts'], ['dji', 'US30 · Dow Jones', 'pts'], ['rut', 'Russell 2000', 'pts']];
  const TES = (R && R.tesis_activos) || {};
  const nombreTesis = { oro: 'Oro', btc: 'Bitcoin', spx: 'S&P 500', ndx: 'Nasdaq 100' };
  const corteFecha = R && R.corte ? (R.corte.match(/\d{4}-\d{2}-\d{2}/g) || []).pop() : null;
  const stamp = `Precios: ${P && P.generado_utc ? esc(horaAct(P.generado_utc)) : 'SIN DATO'} · Tesis: ${R && R.generado_utc ? esc(horaAct(R.generado_utc)) : 'SIN DATO'} · corte de datos: ${R ? esc(R.corte) : 'SIN DATO'}`;
  let h = head('Mercados', 'Resumen', 'Una tarjeta por activo: precio, tendencia y el viento macro que lo acompaña. La tesis solo describe si la macro empuja a favor o en contra; no es una recomendación de compra o venta.', stamp);
  h += fallo('precios') + fallo('resumen');
  const prox = ((C && C.eventos) || []).filter((e) => e.fecha >= hoyISO());
  const vig = R ? R.vigilar.slice(0, 2).map(esc).join(' · ') : SD;
  h += essential(R ? esc(R.movido) : SD, R ? esc(R.tesis) : SD, vig);

  h += '<div class="sect"><h2>Activos</h2><span class="more">1d · 1 sem · 1 mes · 3 meses</span></div><div class="grid g6">';
  h += orden.map(([k, nm, u]) => {
    const a = act[k];
    if (!a || a.valor == null) return `<div class="card kpi asset"><div class="top"><div><div class="nm">${nm}</div></div>${tagTesis(null)}</div><div class="big" style="margin-top:12px">${SD}</div>${foot('Yahoo Finance', null)}</div>`;
    const t = TES[nombreTesis[k]];
    return `<div class="card kpi asset"><div class="top"><div><div class="nm">${nm}</div><div class="sym">${esc(a.simbolo)}</div></div>${nombreTesis[k] ? (t ? tagTesis(t.etiqueta) : tagTesis('SIN TESIS')) : tagTesis(null)}</div>
      <div class="big" style="margin-top:10px">${num(a.valor, a.valor > 1000 ? 0 : 2)}<small>${u}</small></div><div class="chg">${pill(a.cambio_1d_pct)}</div>${spark(a.serie)}
      <table><tr><td>1 semana</td><td>${pill(a.cambio_5d_pct)}</td></tr><tr><td>1 mes</td><td>${pill(a.cambio_21d_pct)}</td></tr><tr><td>3 meses</td><td>${pill(a.cambio_63d_pct)}</td></tr></table>
      ${foot(a.fuente.replace(/ \(.*\)/, ''), a.fecha)}</div>`;
  }).join('') + '</div>';

  h += '<div class="sect"><h2>Panel de mercado</h2><span class="more">▲▼ frente al cierre anterior · vs media de 50 sesiones</span></div><div class="card pad0 scroll"><table class="t"><thead><tr><th>Activo</th><th>Último</th><th>1d</th><th>1 sem</th><th>1 mes</th><th>3 meses</th><th>vs SMA50</th><th>Dato</th></tr></thead><tbody>';
  const filas = [...orden.map((o) => o[0]), 'vix', 'dxy'];
  h += filas.map((k) => {
    const a = act[k];
    if (!a || a.valor == null) return `<tr><td>${esc((a && a.nombre) || k)}</td><td colspan="7" style="text-align:left;color:var(--dim)">SIN DATO</td></tr>`;
    const v = ((a.valor / a.sma50 - 1) * 100);
    return `<tr><td>${esc(a.nombre)}<small>${esc(a.simbolo)}</small></td><td>${num(a.valor, a.valor > 1000 ? 0 : 2)}</td><td>${pill(a.cambio_1d_pct)}</td><td>${pill(a.cambio_5d_pct)}</td><td>${pill(a.cambio_21d_pct)}</td><td>${pill(a.cambio_63d_pct)}</td><td>${pill(v, 1)}</td><td>${esc(fd(a.fecha))}</td></tr>`;
  }).join('');
  h += '</tbody></table></div>';

  h += '<div class="grid g21" style="margin-top:12px"><div><div class="sect" style="margin-top:14px"><h2>Tesis por activo · causa → efecto</h2><span class="more">viento macro de hoy</span></div><div class="grid g2">';
  h += ['Oro', 'Nasdaq 100', 'S&P 500', 'Bitcoin'].map((n) => {
    const t = TES[n]; const s = R && R.significa.find((x) => x.activo === n);
    const mot = t && t.motores.length ? t.motores.map((m) => `<div>${esc(LABEL[m.motor] || m.motor)} ${m.sube ? '↑' : '↓'} → ${esc(m.razon)}</div>`).join('') : '<div>Ningún motor macro supera su umbral de hoy.</div>';
    return `<div class="card asset"><div class="top"><div class="nm">${n}</div>${t ? tagTesis(t.etiqueta) : tagTesis('SIN TESIS')}</div>
      <div class="flow">${s ? esc(s.texto) : SD}<em>Motores que lo mueven</em>${mot}</div>
      ${foot('Reglas NEXORA (sensibilidades fijas)', corteFecha)}</div>`;
  }).join('');
  h += '</div></div><div>';
  h += '<div class="sect" style="margin-top:14px"><h2>Motores macro</h2><span class="more">umbral de sesión</span></div><div class="card pad0"><table class="t"><thead><tr><th>Motor</th><th>Valor</th><th>Hoy</th><th>Umbral</th></tr></thead><tbody>';
  const M = (R && R.motores) || {};
  h += Object.keys(LABEL).map((k) => {
    const m = M[k]; if (!m) return `<tr><td>${esc(LABEL[k])}</td><td colspan="3" style="color:var(--dim);text-align:left">SIN DATO</td></tr>`;
    const [u1, u2] = UNID[k]; const sig = m.delta != null && Math.abs(m.delta) >= UMB[k][0];
    return `<tr><td>${esc(LABEL[k])}<small>${esc(fd(m.fecha))}</small></td><td>${num(m.valor, k === 'fed' || k === 'hy' ? 0 : 2)}${u1}</td><td>${pill(m.delta, k === 'dxy' || k === 'vix' ? 2 : 1, u2)}</td><td>${sig ? '<span class="ck par">SUPERA</span>' : `<span class="mono" style="color:var(--dim)">${UMB[k][0]}${u2.trim()}</span>`}</td></tr>`;
  }).join('') + '</tbody></table></div>';
  h += '<div class="sect"><h2>Próximos eventos</h2><a class="more" href="#/calendario">calendario →</a></div><div class="card">';
  const lista = prox.filter((e) => e.importancia !== 'BAJA').slice(0, 7);
  h += lista.length ? lista.map((e) => `<div style="display:grid;grid-template-columns:62px 1fr;gap:8px;padding:6px 0;border-bottom:1px solid var(--border)"><span class="mono" style="color:var(--amber);font-size:11.5px">${esc(fdd(e.fecha))}<br><span style="color:var(--dim)">${esc(e.hora_madrid || '—')}</span></span><span style="font-size:12px">${esc(e.evento)}<br><span style="color:var(--dim);font-size:10.5px">${esc(e.afecta)}</span></span></div>`).join('') : SD;
  h += foot('Calendario NEXORA (FRED, ISM, Fed, Nasdaq)', null, null, 'hora de Madrid') + '</div></div></div>';

  h += `<div class="sect"><h2>En palabras sencillas</h2></div><div class="card"><div class="simple">${R ? esc(R.sencillo) : SD}</div>
    <ul class="watch" style="margin-top:12px">${R ? R.vigilar.map((v) => `<li>${esc(v)}</li>`).join('') : ''}</ul>
    <div class="note">Cada cifra procede de su fuente oficial (Tesoro de EE. UU., FRED, Cboe, Nasdaq, Coinbase, futuros ZQ). Si una descarga falla se muestra SIN DATO: nunca se interpola ni se estima.</div></div>`;
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
  h += '</tbody></table></div>';
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
  h += `<div class="state"><div class="card"><div class="eb">Liquidez</div><div class="v ${E.lectura.includes('SIN GIRO') ? 'amber' : ''}">${esc(E.lectura)}</div><p>Reservas, TGA y RRP: ${E.nucleo ? `${E.nucleo.fav} a favor · ${E.nucleo.des} en contra de ${E.nucleo.n}` : 'SIN DATO'} (núcleo). Contexto global: ${E.contexto_13 ? `${E.contexto_13.fav} favorables · ${E.contexto_13.des} desfavorables` : 'SIN DATO'}.</p></div>
    <div class="card"><div class="eb">Secuencia de giro</div><div class="v">${E.secuencia_cumplidos ?? '—'} <span style="color:var(--dim)">/ 7</span></div><p>Cumple hasta el paso ${E.secuencia_hasta ?? 0}. El giro exige TGA↓, RRP↓ y reservas↑ primero, y después tipos, Fed, dólar y BTC.</p></div></div>`;
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
    + (E.checklist || []).map((c) => `<tr><td>${c.n}. ${esc(c.condicion)}</td><td>${ck(c.estado)}</td><td style="text-align:left;color:var(--dim);white-space:normal">${esc(c.nota || '')}</td></tr>`).join('') + '</tbody></table></div>';
  h += '<div class="card pad0"><table class="t"><thead><tr><th>Secuencia del giro</th><th>Estado</th><th>Detalle</th></tr></thead><tbody>'
    + (E.secuencia || []).map((c) => `<tr><td>${c.n}. ${esc(c.paso)}</td><td>${ck(c.estado)}</td><td style="text-align:left;color:var(--dim);white-space:normal">${esc(c.detalle || '')}</td></tr>`).join('') + '</tbody></table></div></div>';

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
  if (Object.keys(pc).length) h += '<div class="grid g3">' + Object.entries(pc).map(([k, v]) => `<div class="card"><div class="eyebrow" style="color:var(--muted)">Decisión de tipos</div><div style="font-family:var(--serif);font-size:20px;margin:6px 0 2px">${esc(k)}</div><div class="mono">${esc(fdd(v.fecha))} · ${cuentaAtras(v.fecha)}</div></div>`).join('') + '</div>';
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
  const fn = { resumen: pageResumen, bancos: pageBancos, liquidez: pageLiquidez, calendario: pageCalendario }[p.id];
  let html;
  try { html = fn ? fn() : pagePlaceholder(p); } catch (e) { console.error(e); html = head(p.g, p.t, '', '') + `<div class="banner red" style="border-radius:6px">Error al dibujar esta página: ${esc(e.message)}. El resto de la web sigue funcionando.</div>`; }
  $('#app').innerHTML = html;
  document.title = `${p.t} · NEXORA Terminal`;
  window.scrollTo(0, 0);
  MOUNT.forEach((f) => { try { f(); } catch (e) { console.error(e); } });
}

async function cargar() {
  await Promise.all(['meta', 'precios', 'fedwatch', 'calendario', 'liquidez', 'resumen'].map(async (n) => {
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
