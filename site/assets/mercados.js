/* NEXORA TERMINAL · páginas de mercado: Oro, Índices USA y Cripto (fase 3).
   Se carga después de app.js y reutiliza sus helpers (head, essential, foot, kpi, lw, pill, ck…). Todo texto dinámico pasa por esc(). */
'use strict';

/* ------------------------------------------------------------------ helpers propios */
const grp = (e) => {
  const s = String(e || '').toUpperCase();
  if (!s || /SIN DATO/.test(s)) return 'sd';
  if (/^NO |DESFAV|RISK-OFF|ROTA|CONTRARI|DRENAJE|NO CONFIRMA/.test(s)) return 'no';
  if (/FAVOR|^SE CUMPLE|^CUMPLE|RISK-ON|CONFIRMA|LIDERA/.test(s)) return 'ok';
  if (/NEUTRAL|PARCIAL|MIXTO|D[ÉE]BIL|SIN L[ÍI]DER/.test(s)) return 'par';
  return 'sd';
};
const ck2 = (e) => `<span class="ck ${grp(e)}">${esc(e || 'SIN DATO')}</span>`;
function sinDatoEl() { const d = document.createElement('div'); d.className = 'empty'; d.textContent = 'SIN DATO'; return d; }
/* flecha de dirección: forma = sentido del dato (↑ ↓ →), color = efecto según el estado del monitor */
function dirCell(dir, estado) {
  const d = String(dir || '');
  const g = grp(estado);
  const col = g === 'ok' ? 'up' : g === 'no' ? 'down' : 'flat';
  const f = d.includes('↑') ? '▲' : d.includes('↓') ? '▼' : d.includes('→') ? '▬' : '·';
  return `<span class="${col}" style="font-family:var(--mono)">${f}</span>`;
}
function tagSesgo(et) {
  const e = String(et || '');
  const c = e.includes('DÉBIL') ? 'deb' : e.startsWith('ALCISTA') ? 'alc' : e.startsWith('BAJISTA') ? 'baj' : e ? 'sin' : 'sd';
  return e ? `<span class="tag ${c}">${esc(e)}</span>` : '<span class="tag sd">NO CUBIERTO</span>';
}
function sma(serie, n) {
  const out = []; let acc = 0;
  for (let i = 0; i < serie.length; i++) {
    acc += serie[i][1];
    if (i >= n) acc -= serie[i - n][1];
    if (i >= n - 1) out.push([serie[i][0], +(acc / n).toFixed(4)]);
  }
  return out;
}
function ratio(a, b) {
  const mb = new Map((b || []).map((x) => [x[0], x[1]]));
  return (a || []).filter((x) => mb.has(x[0]) && mb.get(x[0])).map((x) => [x[0], +(x[1] / mb.get(x[0])).toFixed(5)]);
}
const ser = (k) => ((D.series && D.series.yahoo && D.series.yahoo[k]) || {}).serie || null;
const serC = (k) => (D.series && D.series.cripto && D.series.cripto[k]) || null;
const act = (k) => ((D.precios && D.precios.activos) || {})[k] || null;
const fix = (v, d = 2) => (v == null ? SD : num(v, d));

/* tarjeta de precio de un activo con su gráfico de 3 meses */
function priceCard(o) {
  const a = o.a;
  if (!a || a.valor == null) return `<div class="card kpi asset"><div class="top"><div><div class="nm">${esc(o.nm)}</div></div>${o.tag || ''}</div><div class="big" style="margin-top:12px">${SD}</div>${foot((a && a.fuente) || 'Yahoo Finance', null)}</div>`;
  return `<div class="card kpi asset"><div class="top"><div><div class="nm">${esc(o.nm)}</div><div class="sym">${esc(a.simbolo || '')}</div></div>${o.tag || ''}</div>
    <div class="big" style="margin-top:10px">${num(a.valor, a.valor > 1000 ? 0 : 2)}<small>${esc(o.u || '')}</small></div><div class="chg">${pill(a.cambio_1d_pct)}</div>${spark(a.serie, 63)}
    <table><tr><td>1 semana</td><td>${pill(a.cambio_5d_pct)}</td></tr><tr><td>1 mes</td><td>${pill(a.cambio_21d_pct)}</td></tr><tr><td>3 meses</td><td>${pill(a.cambio_63d_pct)}</td></tr></table>
    ${o.extra || ''}${foot(a.fuente, a.fecha)}</div>`;
}

/* gráfico de barras (Chart.js) con barras verdes/rojas según signo; con varias series, tres tonos */
function barras(id, etiquetas, series, opts = {}) {
  MOUNT.push(() => {
    const el = document.getElementById(id);
    if (!el) return;
    if (!window.Chart) { el.parentNode.replaceChildren(sinDatoEl()); return; }
    const V = ['#2FA36B', '#238256', '#1b6342'], R = ['#C8463D', '#9d352e', '#78271f'];
    const eje = opts.horizontal ? 'x' : 'y';
    new Chart(el, {
      type: 'bar',
      data: { labels: etiquetas, datasets: series.map((s, i) => ({ label: s.name, data: s.data, backgroundColor: s.data.map((v) => (v == null ? '#2A313B' : v >= 0 ? V[i % 3] : R[i % 3])), borderRadius: 2, maxBarThickness: opts.fino || 18 })) },
      options: {
        responsive: true, maintainAspectRatio: false, indexAxis: opts.horizontal ? 'y' : 'x',
        plugins: { legend: { display: series.length > 1, labels: { color: '#8A93A0', boxWidth: 10, font: { family: 'IBM Plex Mono', size: 10 } } },
          tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${c.parsed[eje] > 0 ? '+' : ''}${num(c.parsed[eje], opts.dec ?? 2)}${opts.suf || ''}` } } },
        scales: { x: { ticks: { color: '#8A93A0', font: { family: 'IBM Plex Mono', size: 10 }, maxRotation: 0, autoSkip: true }, grid: { color: '#14181e' } },
          y: { ticks: { color: '#8A93A0', font: { family: 'IBM Plex Mono', size: 10 } }, grid: { color: '#14181e' } } },
      },
    });
  });
  return `<div style="position:relative;height:${opts.alto || 260}px"><canvas id="${id}"></canvas></div>`;
}

function dona(id, partes, colores, alto = 200) {
  MOUNT.push(() => {
    const el = document.getElementById(id);
    if (!el || !window.Chart) return;
    new Chart(el, { type: 'doughnut', data: { labels: partes.map((p) => p[0]), datasets: [{ data: partes.map((p) => p[1]), backgroundColor: colores, borderColor: '#12151A', borderWidth: 2 }] },
      options: { responsive: true, maintainAspectRatio: false, cutout: '64%', plugins: { legend: { position: 'right', labels: { color: '#8A93A0', boxWidth: 10, font: { family: 'IBM Plex Mono', size: 10 } } } } } });
  });
  return `<div style="position:relative;height:${alto}px"><canvas id="${id}"></canvas></div>`;
}

/* tabla de señales de un monitor: dato · valor · ▲▼ · estado · lectura · fuente */
function tablaSenales(panel, titulo, fecha) {
  return `<div class="card pad0 scroll"><table class="t"><thead><tr><th>${esc(titulo)}</th><th>Valor</th><th>Dir.</th><th>Estado</th><th style="text-align:left">Lectura</th><th style="text-align:left">Fuente</th></tr></thead><tbody>`
    + (panel || []).map((p) => `<tr><td>${esc(p.dato || p.nombre)}${p.que_mirar ? `<small>${esc(p.que_mirar)}</small>` : ''}</td><td style="white-space:normal;min-width:170px">${esc(p.valor)}</td><td>${dirCell(p.dir, p.estado)}</td><td>${ck2(p.estado)}</td><td style="text-align:left;color:var(--muted);white-space:normal">${esc(p.lectura || p.detalle || '')}</td><td style="text-align:left;color:var(--dim);white-space:normal">${esc(p.fuente || '')}</td></tr>`).join('')
    + `</tbody></table>${footIn('Monitor NEXORA', fecha || false)}</div>`;
}
function tablaComparaciones(cmp, fecha) {
  return `<div class="card pad0 scroll"><table class="t"><thead><tr><th>Relación</th><th>Qué se busca</th><th>Estado</th><th style="text-align:left">Detalle</th><th style="text-align:left">Lectura</th></tr></thead><tbody>`
    + (cmp || []).map((c) => `<tr><td>${esc(c.par)}</td><td style="text-align:left;color:var(--muted);white-space:normal">${esc(c.busca)}</td><td>${ck2(c.estado)}</td><td style="text-align:left;white-space:normal">${esc(c.detalle)}</td><td style="text-align:left;color:var(--muted);white-space:normal">${esc(c.lectura)}</td></tr>`).join('')
    + `</tbody></table>${footIn('Monitor NEXORA', fecha || false)}</div>`;
}
const durl = (id) => `https://fred.stlouisfed.org/series/${id}`;
const preguntas = (E, fuente) => '<div class="card">' + (E.preguntas || []).map((p) => `<details class="qa"><summary>${esc(p.pregunta)}</summary><p>${esc(p.respuesta)}</p></details>`).join('') + foot(fuente, false, null, 'hecho · interpretación · hipótesis separados') + '</div>';
const errores = (er) => (er && Object.keys(er).length ? `<div class="note">Fuentes sin dato en esta ejecución (SIN DATO, no se estima): ${Object.entries(er).map(([k, v]) => esc(k + ': ' + String(v).slice(0, 80))).join(' · ')}</div>` : '');

/* ================================================================== ORO */
function pageOro() {
  const O = D.oro, T = D.tipos, G = act('oro'), DX = act('dxy');
  let h = head('Análisis', 'Oro, reservas y flujos', 'El oro no paga intereses: lo mueven el dólar, el tipo real a 10 años, los flujos de los ETF y el posicionamiento de los fondos. Cada dato lleva su fecha y su fuente; si una descarga falla se muestra SIN DATO.',
    `Monitor: ${O && O.generado_utc ? esc(horaAct(O.generado_utc)) : 'SIN DATO'} · precio: ${D.precios && D.precios.generado_utc ? esc(horaAct(D.precios.generado_utc)) : 'SIN DATO'}`);
  h += fallo('monitores') + fallo('precios');
  if (!O || !O.evaluacion) return h + noData('Oro');
  const M = O.metricas || {}, E = O.evaluacion, c = E.confluencia || {}, o = M.oro || {}, cot = M.cot, nv = M.niveles || {};
  const etf = M.etf; const gld = (O.series && O.series.gld_t) || null;
  const real = T && T.real10, t2 = T && T.t2y;
  const pr = (E.preguntas || []).find((q) => /liquidez en el gr/.test(q.pregunta));
  h += essential(
    `Oro ${G && G.valor != null ? num(G.valor, 0) + ' USD (' + sg(G.cambio_1d_pct, 2, ' %') + ' en el día, ' + esc(fd(G.fecha)) + ')' : 'SIN DATO'}; ${o['20d_pct'] != null ? sg(o['20d_pct'], 1, ' %') + ' en 20 sesiones' : ''}${o.sma200 && G && G.valor != null ? ', ' + sg((G.valor / o.sma200 - 1) * 100, 1, ' %') + ' frente a su media de 200 sesiones' : ''}. Tipo real 10Y ${real ? num(real.valor, 2) + ' % (' + sg(real.d5_pb, 0, ' pb') + ' en 5 días)' : 'SIN DATO'}.`,
    `Confluencia macro <b style="color:var(--text)">${esc(c.lectura || 'SIN DATO')}</b>: ${c.favorables ?? '—'} a favor y ${c.contrarias ?? '—'} en contra de ${c.disponibles ?? '—'} datos núcleo; el precio ${esc(c.precio || 'SIN DATO')}. Es una lectura de contexto, no una recomendación.`,
    pr ? esc(pr.respuesta).slice(0, 260) + '…' : 'Dólar, tipo real y FedWatch.');
  (E.avisos || []).forEach((a) => { h += `<div class="banner amber" style="margin:0 0 12px;border-radius:6px">${esc(a)}</div>`; });

  h += `<div class="state" style="grid-template-columns:repeat(3,1fr)"><div class="card"><div class="eb">Confluencia macro (núcleo)</div><div class="v ${grp(c.lectura) === 'par' ? 'amber' : ''}">${esc(c.lectura || 'SIN DATO')}</div>
    <div class="chips" style="margin:8px 0">${(c.nucleo || []).map((n) => `<span class="chip">${dirCell(n.dir, n.estado)} ${esc(n.dato)} ${ck2(n.estado)}</span>`).join('')}</div>${foot('Monitor de oro NEXORA (Tesoro, FRED, Fed)', (T && T.real10 && T.real10.fecha) || false)}</div>
    <div class="card"><div class="eb">Estructura del precio</div><div class="v" style="font-size:18px">${esc(c.precio || 'SIN DATO')}</div><p>${esc(nv.estructura_semanal || 'SIN DATO')}</p>${foot(nv.fuente ? nv.fuente.split(',')[0] : 'XAUT-USDT (OKX)', nv.fecha)}</div>
    <div class="card"><div class="eb">Posicionamiento y flujos</div><div class="v" style="font-size:18px">${cot ? 'Fondos ' + sg(cot.mm_neto, 0) + ' contratos' : 'SIN DATO'}</div><p>${cot ? `Percentil ${cot.mm_percentil_52s} % a 52 semanas · ${sg(cot.mm_neto_1s, 0)} en la semana. ` : ''}${etf ? `GLD ${num(etf.gld_t, 1)} t (${sg(etf['5d_t'], 1, ' t')} en 5 días).` : 'GLD: SIN DATO.'}</p>${foot('CFTC (COT) · SPDR Gold Shares', cot && cot.fecha)}</div></div>`;

  h += '<div class="sect"><h2>Oro y sus motores</h2><span class="more">1 semana · 4 semanas · 12 semanas · gráfico de 3 meses</span></div><div class="grid g4">';
  h += priceCard({ nm: 'Oro (futuros COMEX)', a: G, u: 'USD/oz', extra: o.max_52s ? `<div class="note" style="margin:6px 0 0">Máx. 52 s ${num(o.max_52s, 0)} · mín. ${num(o.min_52s, 0)} · desde máx. ${sg(o.vs_max_52s_pct, 1, ' %')} · año ${sg(o.ytd_pct, 1, ' %')}</div>` : '' });
  h += kpi({ lab: 'Tipo real a 10 años', exp: 'Lo que paga un bono tras la inflación: el rival más duro del oro (rojo si sube)', serie: real && real.serie, unidad: '%', suf: 'pp', inv: true, fuente: real ? real.fuente : 'Tesoro de EE. UU.', url: real && real.url });
  h += kpi({ lab: 'Bono a 2 años', exp: 'Apuesta del mercado sobre la Fed (rojo si sube)', serie: t2 && t2.serie, unidad: '%', suf: 'pp', inv: true, fuente: t2 ? t2.fuente : 'Tesoro de EE. UU.', url: t2 && t2.url });
  h += priceCard({ nm: 'Dólar (DXY)', a: DX, u: '', extra: '<div class="note" style="margin:6px 0 0">Un dólar fuerte suele pesar sobre el oro.</div>' });
  h += kpi({ lab: 'ETF GLD · toneladas', exp: 'Oro físico en el mayor ETF: entradas = demanda de inversión', serie: gld, unidad: 't', suf: 't', dec: 1, fuente: 'SPDR Gold Shares (World Gold Trust)', url: 'https://www.spdrgoldshares.com/usa/historical-data/', filas: [['1 semana', 7], ['1 mes', 28], ['3 meses', 90]] });
  h += `<div class="card kpi"><div class="lab">COT oro · fondos (managed money)</div><div class="exp">Posición neta de los fondos en futuros COMEX (CFTC, martes → publica el viernes)</div>${cot ? `<div class="big">${sg(cot.mm_neto, 0)}<small>contratos</small></div><table><tr><td>Cambio 1 semana</td><td>${pill(cot.mm_neto_1s, 0, '')}</td></tr><tr><td>Percentil 52 s</td><td><span class="mono">${cot.mm_percentil_52s} %</span></td></tr><tr><td>Comerciales (neto)</td><td><span class="mono">${sg(cot.comerciales_neto, 0)}</span></td></tr><tr><td>Interés abierto</td><td>${pill(cot.oi_1s_pct, 2)}</td></tr></table>` : `<div class="big">${SD}</div>`}${foot('CFTC Disaggregated, COMEX Gold', cot && cot.fecha, 'https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm', 'posiciones del martes')}</div>`;
  const br = M.brent;
  h += `<div class="card kpi"><div class="lab">Petróleo Brent</div><div class="exp">Energía cara = inflación esperada y tensión geopolítica</div>${br ? `<div class="big">${num(br.valor, 2)}<small>USD</small></div><table><tr><td>5 días</td><td>${pill(br['5d_pct'], 1)}</td></tr><tr><td>20 días</td><td>${pill(br['20d_pct'], 1)}</td></tr></table>` : `<div class="big">${SD}</div>`}${foot('EIA vía FRED (DCOILBRENTEU)', br && br.fecha, durl('DCOILBRENTEU'), 'con retraso de varios días')}</div>`;
  const be = M.be10Y;
  h += `<div class="card kpi"><div class="lab">Inflación esperada 10 años</div><div class="exp">Nominal − real (breakeven). El oro cubre la inflación inesperada</div>${be ? `<div class="big">${num(be.valor, 2)}<small>%</small></div><table><tr><td>5 días</td><td>${pill(be['5d_pb'], 0, ' pb')}</td></tr><tr><td>20 días</td><td>${pill(be['20d_pb'], 0, ' pb')}</td></tr></table>` : `<div class="big">${SD}</div>`}${foot('Tesoro de EE. UU. (nominal − real)', be && be.fecha)}</div></div>`;

  const gs = G && G.serie;
  const real_s = real && real.serie;
  h += '<div class="sect"><h2>Gráficos</h2><span class="more">pasa el ratón para ver cada valor · rangos 3M / 6M / 1A</span></div>';
  h += `<div class="card"><h3>Oro y sus medias de 50 y 200 sesiones</h3><div class="sub">USD por onza (futuros COMEX GC=F). Por debajo de la media de 200 sesiones la tendencia de fondo es bajista; por encima, alcista.</div>${gs ? lw('cOro', [{ name: 'Oro', color: COL.amber, data: gs, prec: 0, area: true }, { name: 'Media 50', color: COL.blue, data: sma(gs, 50), w: 1, prec: 0 }, { name: 'Media 200', color: COL.violet, data: sma(gs, 200), w: 1, prec: 0 }], { tall: true, init: 365 }) : '<div class="empty" style="height:200px">SIN DATO</div>'}${foot(G ? G.fuente : 'Yahoo Finance', G && G.fecha)}</div>`;
  h += '<div class="grid g2" style="margin-top:12px">';
  h += `<div class="card"><h3>Oro frente al tipo real a 10 años</h3><div class="sub">Eje izquierdo: oro (USD). Eje derecho: tipo real (%). Cuando el tipo real sube, el oro suele ceder.</div>${lw('cOroReal', [{ name: 'Oro (eje izq.)', color: COL.amber, data: gs, scale: 'left', prec: 0 }, { name: 'Tipo real 10Y', color: COL.blue, data: real_s, prec: 2 }], { left: true, init: 365 })}${foot(real ? real.fuente : 'Tesoro de EE. UU.', real && real.fecha, real && real.url)}</div>`;
  h += `<div class="card"><h3>Oro frente al dólar (DXY)</h3><div class="sub">Eje izquierdo: oro. Eje derecho: índice del dólar ICE (DX-Y.NYB).</div>${lw('cOroDxy', [{ name: 'Oro (eje izq.)', color: COL.amber, data: gs, scale: 'left', prec: 0 }, { name: 'DXY', color: COL.white, data: DX && DX.serie, prec: 2 }], { left: true, init: 365 })}${foot(DX ? DX.fuente : 'Yahoo Finance', DX && DX.fecha)}</div>`;
  h += `<div class="card"><h3>ETF GLD: toneladas en el trust</h3><div class="sub">Si el oro sube con toneladas al alza, hay demanda de inversión; si sube con toneladas a la baja, lo sostienen otros compradores.</div>${gld ? lw('cGld', [{ name: 'GLD (t)', color: COL.amber, data: gld, prec: 1, area: true }], { init: 365 }) : '<div class="empty" style="height:200px">SIN DATO · SPDR no respondió</div>'}${foot('SPDR Gold Shares (World Gold Trust)', gld && gld[gld.length - 1][0], 'https://www.spdrgoldshares.com/usa/historical-data/')}</div>`;
  h += `<div class="card"><h3>Rendimientos del Tesoro: 2 y 10 años y tipo real</h3><div class="sub">Si el 2Y baja y el real no, el mercado espera una Fed más blanda pero sigue exigiendo rentabilidad real.</div>${lw('cOroTipos', [{ name: '2 años', color: COL.amber, data: t2 && t2.serie, prec: 2 }, { name: '10 años', color: COL.white, data: T && T.n10 && T.n10.serie, prec: 2, w: 1 }, { name: 'Real 10 años', color: COL.blue, data: real_s, prec: 2 }], { init: 365 })}${foot(t2 ? t2.fuente : 'Tesoro de EE. UU.', t2 && t2.fecha, t2 && t2.url)}</div></div>`;

  const perf = [['1 día', o['1d_pct']], ['5 días', o['5d_pct']], ['20 días', o['20d_pct']], ['60 días', o['60d_pct']], ['Año', o.ytd_pct]];
  h += `<div class="grid g21" style="margin-top:12px"><div class="card"><h3>Rendimiento del oro por plazo</h3><div class="sub">% de variación · verde = sube, rojo = baja</div>${barras('bOro', perf.map((x) => x[0]), [{ name: 'Oro %', data: perf.map((x) => x[1]) }], { suf: ' %', alto: 230 })}${foot(o.fuente || 'Futuros COMEX GC=F (Yahoo Finance)', o.fecha)}</div>`;
  h += `<div class="card pad0"><div style="padding:14px 16px 0"><h3>Curva del Tesoro</h3><div class="sub">Rendimiento y cambio en puntos básicos (rojo = sube el tipo)</div></div><table class="t"><thead><tr><th>Plazo</th><th>Nivel</th><th>1 d</th><th>5 d</th><th>20 d</th></tr></thead><tbody>`
    + [['2 años', M.t2Y], ['5 años', M.t5Y], ['10 años', M.t10Y], ['30 años', M.t30Y], ['Real 5 años', M.real5Y], ['Real 10 años', M.real10Y]].map(([n, m]) => m ? `<tr><td>${n}<small>${esc(fd(m.fecha))}</small></td><td>${num(m.valor, 2)} %</td><td>${pill(m['1d_pb'], 0, ' pb', true)}</td><td>${pill(m['5d_pb'], 0, ' pb', true)}</td><td>${pill(m['20d_pb'], 0, ' pb', true)}</td></tr>` : `<tr><td>${n}</td><td colspan="4" style="color:var(--dim)">SIN DATO</td></tr>`).join('')
    + `</tbody></table>${footIn('Tesoro de EE. UU. (curva par diaria)', (M.t10Y || {}).fecha)}</div></div>`;

  h += '<div class="sect"><h2>Panel de señales</h2><span class="more">▲▼ sentido del dato · verde = favorable al oro, rojo = desfavorable</span></div>' + tablaSenales(E.panel, 'Dato', (M.t10Y || {}).fecha);
  h += '<div class="sect"><h2>Relaciones entre datos y niveles</h2><span class="more">¿se cumple lo que la teoría espera? · dónde está la liquidez</span></div><div class="grid g2">' + tablaComparaciones(E.comparaciones, (M.t10Y || {}).fecha);
  const fila = (n) => `<tr><td>${esc(n.nombre)}</td><td>${num(n.nivel, 1)}</td><td>${pill(n.dist_pct, 2)}</td><td><span class="mono">${sg(n.dist_atr, 1, ' ATR')}</span></td></tr>`;
  const pools = E.pools || {};
  h += `<div class="card pad0 scroll"><table class="t"><thead><tr><th>Niveles · referencia ${pools.referencia ? num(pools.referencia, 1) : 'SIN DATO'}</th><th>Nivel</th><th>Distancia</th><th>En ATR</th></tr></thead><tbody>`
    + ((pools.encima || []).map(fila).join('') + (pools.debajo || []).map(fila).join('') || '<tr><td colspan="4" style="color:var(--dim)">SIN DATO</td></tr>') + `</tbody></table><div class="note" style="padding:0 16px">ATR14 ${pools.atr14 ? num(pools.atr14, 1) : 'SIN DATO'} · proxy XAUT (token respaldado por oro, cotiza 24/7): verifica siempre en tu gráfico de XAU/USD.</div>${footIn(nv.fuente ? nv.fuente.split(',')[0] : 'OKX', nv.fecha)}</div></div>`;
  h += '<div class="sect"><h2>Pasos de la guía</h2><span class="more">del macro al posicionamiento</span></div><div class="card pad0"><table class="t"><thead><tr><th>Paso</th><th>Estado</th><th style="text-align:left">Detalle</th></tr></thead><tbody>'
    + (E.pasos || []).map((p) => `<tr><td>${p.n}. ${esc(p.paso)}<small>${esc(p.que)}</small></td><td>${ck2(p.estado)}</td><td style="text-align:left;color:var(--muted);white-space:normal">${esc(p.detalle)}</td></tr>`).join('') + `</tbody></table>${footIn('Guía NEXORA (oro)', (M.t10Y || {}).fecha)}</div>`;
  h += '<div class="sect"><h2>Las diez preguntas</h2></div>' + preguntas(E, 'Guía NEXORA (oro)');
  h += errores(M.errores);
  h += '<div class="note">Pendiente de integrar: compras de bancos centrales (FMI IFS / Consejo Mundial del Oro), que no tienen API gratuita estable; no se muestra ningún dato sustituto.</div>';
  return h;
}

/* ================================================================== ÍNDICES */
function pageIndices() {
  const I = D.indices, R = D.resumen;
  let h = head('Análisis', 'Índices USA', 'S&P 500, Nasdaq 100, US30 (Dow Jones) y Russell 2000: lo que mueve a cada uno (tipos, beneficios, amplitud, crédito), quién lidera y si el mercado se está volviendo defensivo.',
    `Monitor: ${I && I.generado_utc ? esc(horaAct(I.generado_utc)) : 'SIN DATO'} · precios: ${D.precios && D.precios.generado_utc ? esc(horaAct(D.precios.generado_utc)) : 'SIN DATO'}`);
  h += fallo('monitores') + fallo('precios');
  if (!I || !I.evaluacion) return h + noData('Índices USA');
  const M = I.metricas || {}, E = I.evaluacion, en = E.entorno || {}, FR = M.fuerza_relativa || {}, AM = M.amplitud || {};
  const T = D.tipos, real = T && T.real10;
  const idx = [['spx', 'S&P 500', 'S&P 500'], ['ndx', 'Nasdaq 100', 'Nasdaq 100'], ['dji', 'US30 · Dow Jones', 'Dow Jones (US30)'], ['rut', 'Russell 2000', 'Russell 2000']];
  const PI = Object.fromEntries((E.por_indice || []).map((x) => [x.indice, x]));
  const TES = (R && R.tesis_activos) || {};
  const lider = (E.preguntas || []).find((q) => /relative strength/.test(q.pregunta));
  const cons = E.consumo;
  const vix = act('vix');
  h += essential(
    `${idx.map(([k, n]) => { const a = act(k); return a && a.valor != null ? `${n} ${sg(a.cambio_1d_pct, 2, ' %')}` : `${n} SIN DATO`; }).join(' · ')} en el día. VIX ${vix && vix.valor != null ? num(vix.valor, 1) + ' (' + sg(vix.cambio_1d_pct, 1, ' %') + ')' : 'SIN DATO'}.`,
    `Entorno de riesgo <b style="color:var(--text)">${esc(en.lectura || 'SIN DATO')}</b>: ${en.risk_on ?? '—'} señales risk-on y ${en.risk_off ?? '—'} risk-off de ${en.disponibles ?? '—'}; liquidez ${esc(en.liquidez || 'SIN DATO')}, amplitud ${esc(en.breadth || 'SIN DATO')}. ${cons && cons.lectura ? esc(cons.lectura.split('.')[0]) + '.' : ''}`,
    lider ? esc(lider.respuesta) : 'Tipo real a 10 años, amplitud y beneficios.');
  (E.avisos || []).forEach((a) => { h += `<div class="banner amber" style="margin:0 0 12px;border-radius:6px">${esc(a)}</div>`; });

  h += '<div class="sect"><h2>Los cuatro índices</h2><span class="more">entorno de cada índice según el monitor · tesis NEXORA</span></div><div class="grid g4">';
  h += idx.map(([k, n, pn]) => {
    const p = PI[pn] || {};
    const t = TES[n];
    const fac = (p.factores || []).map((f) => `<span class="chip">${esc(f.factor)} ${ck2(f.estado)}</span>`).join('');
    const ex = `<div style="margin:8px 0 4px">${ck2(p.entorno || 'SIN DATO')} <span class="mono" style="color:var(--dim);font-size:10.5px">${p.puntos != null ? sg(p.puntos, 0, ' pts') : ''}</span></div><div class="chips" style="margin-bottom:6px">${fac}</div><div class="note" style="margin:0">Lo mueve: ${esc(p.que_lo_mueve || 'SIN DATO')}</div>`;
    return priceCard({ nm: n, a: act(k), u: 'pts', tag: t ? tagSesgo(t.etiqueta) : '', extra: ex });
  }).join('') + '</div>';

  const sp = act('spx') && act('spx').serie;
  const base = sp && sp.length ? sp[Math.max(0, sp.length - 252)][0] : '2025-10-01';
  const rb = (k) => rebase((act(k) && act(k).serie) || [], base);
  h += '<div class="sect"><h2>Gráficos</h2><span class="more">pasa el ratón para ver cada valor · rangos 3M / 6M / 1A</span></div>';
  h += `<div class="card"><h3>Los cuatro índices, base 100</h3><div class="sub">Rendimiento relativo desde el inicio del gráfico: quién lidera y quién se queda atrás (cierres diarios).</div>${lw('cIdx', [{ name: 'S&P 500', color: COL.white, data: rb('spx'), prec: 1 }, { name: 'Nasdaq 100', color: COL.amber, data: rb('ndx'), prec: 1 }, { name: 'US30', color: COL.blue, data: rb('dji'), prec: 1 }, { name: 'Russell 2000', color: COL.violet, data: rb('rut'), prec: 1 }], { tall: true })}${foot('Yahoo Finance (^GSPC, ^NDX, ^DJI, ^RUT)', (lastOf(sp) || [])[0])}</div>`;
  h += '<div class="grid g2" style="margin-top:12px">';
  const nd = (act('ndx') || {}).serie;
  const rel = M.relaciones && M.relaciones.nasdaq_real10;
  h += `<div class="card"><h3>Nasdaq 100 frente al tipo real a 10 años</h3><div class="sub">Eje izquierdo: Nasdaq. Eje derecho: tipo real (%). Un tipo real al alza resta valor a las tecnológicas de crecimiento.</div>${lw('cNdxReal', [{ name: 'Nasdaq 100 (eje izq.)', color: COL.amber, data: nd, scale: 'left', prec: 0 }, { name: 'Tipo real 10Y', color: COL.blue, data: real && real.serie, prec: 2 }], { left: true, init: 365 })}${foot(real ? real.fuente : 'Tesoro de EE. UU.', real && real.fecha, real && real.url, rel ? 'relación ' + esc(rel.estado) + ' · corr. 60 d ' + num(rel.corr_60, 2) : '')}</div>`;
  const v3 = ser('vix3m');
  h += `<div class="card"><h3>VIX y VIX a 3 meses</h3><div class="sub">Si el VIX supera al VIX3M (estructura invertida) hay miedo inmediato; lo normal es VIX por debajo.</div>${lw('cVix', [{ name: 'VIX', color: COL.neg, data: vix && vix.serie, prec: 2 }, { name: 'VIX3M', color: COL.gray, data: v3, prec: 2, w: 1 }], { init: 365 })}${foot('Cboe vía Yahoo Finance (^VIX, ^VIX3M)', vix && vix.fecha)}</div>`;
  const xr = ratio(ser('xly'), ser('xlp'));
  h += `<div class="card"><h3>Consumo discrecional / básico (XLY/XLP)</h3><div class="sub">Sube cuando el mercado apuesta por el consumo cíclico (risk-on); baja cuando se refugia en defensivos. Media de 200 sesiones en violeta.</div>${xr.length ? lw('cXly', [{ name: 'XLY/XLP', color: COL.amber, data: xr, prec: 3, area: true }, { name: 'Media 200', color: COL.violet, data: sma(xr, 200), w: 1, prec: 3 }], { init: 365 }) : '<div class="empty" style="height:200px">SIN DATO</div>'}${foot('ETF XLY y XLP (Yahoo Finance)', (xr[xr.length - 1] || [])[0], null, cons && cons.valor ? esc(String(cons.valor).split('·')[0]) : '')}</div>`;
  const rr = ratio(ser('iwm'), ser('qqq')), rs = ratio(ser('rsp'), ser('spy'));
  h += `<div class="card"><h3>Quién lidera: Russell frente a Nasdaq e igual peso frente a S&amp;P</h3><div class="sub">IWM/QQQ al alza = rotación hacia pequeñas empresas. RSP/SPY al alza = el mercado sube con más valores, no solo con las megacaps.</div>${rr.length || rs.length ? lw('cRot', [{ name: 'IWM/QQQ (eje izq.)', color: COL.violet, data: rr, scale: 'left', prec: 3 }, { name: 'RSP/SPY', color: COL.pos, data: rs, prec: 3 }], { left: true, init: 365 }) : '<div class="empty" style="height:200px">SIN DATO</div>'}${foot('ETF IWM, QQQ, RSP, SPY (Yahoo Finance)', (rr[rr.length - 1] || [])[0])}</div></div>`;

  const pares = [['Nasdaq vs S&P', FR.nasdaq_vs_sp], ['Russell vs Nasdaq', FR.russell_vs_nasdaq], ['US30 vs Nasdaq', FR.us30_vs_nasdaq], ['Russell vs S&P', FR.russell_vs_sp], ['Semis vs Nasdaq', FR.semis_vs_nasdaq], ['Industriales vs S&P', FR.industriales_vs_sp], ['Financieras vs S&P', FR.financieras_vs_sp]];
  h += '<div class="grid g21" style="margin-top:12px"><div class="card"><h3>Fuerza relativa (puntos porcentuales)</h3><div class="sub">Diferencia de rendimiento entre cada par · tres tonos = 5, 20 y 60 sesiones · verde = el primero supera al segundo</div>'
    + barras('bFr', pares.map((p) => p[0]), [{ name: '5 sesiones', data: pares.map((p) => (p[1] || {})['5d_pp'] ?? null) }, { name: '20 sesiones', data: pares.map((p) => (p[1] || {})['20d_pp'] ?? null) }, { name: '60 sesiones', data: pares.map((p) => (p[1] || {})['60d_pp'] ?? null) }], { horizontal: true, suf: ' pp', alto: 380, fino: 10 })
    + foot('ETF (Nasdaq Data)', false, null, 'ventanas de 5, 20 y 60 sesiones') + '</div>';
  const ses = AM.sesion || {};
  const gr = ses.grandes_10B, td = ses.todas;
  h += '<div class="card"><h3>Amplitud de la sesión anterior</h3><div class="sub">Cuántas acciones suben y bajan: una subida con pocas acciones es frágil.</div>';
  h += td ? dona('dAmp', [['Suben', td.suben], ['Bajan', td.bajan], ['Sin cambio', Math.max(0, td.n - td.suben - td.bajan)]], ['#2FA36B', '#C8463D', '#2A313B'], 170) : '<div class="empty" style="height:150px">SIN DATO</div>';
  h += `<table class="t mini" style="margin-top:6px"><thead><tr><th>Grupo</th><th>Suben</th><th>Bajan</th><th>% al alza</th><th>Vol. alcista</th></tr></thead><tbody>${[['Todas (EE. UU.)', td], ['Grandes (>10 mm $)', gr]].map(([n, x]) => x ? `<tr><td>${n}</td><td>${num(x.suben, 0)}</td><td>${num(x.bajan, 0)}</td><td>${pill(x.pct_suben - 50, 1, ' pp')}</td><td>${num(x.volumen_alcista_pct, 1)} %</td></tr>` : `<tr><td>${n}</td><td colspan="4" style="color:var(--dim)">SIN DATO</td></tr>`).join('')}</tbody></table>`;
  h += `<div class="note" style="margin:8px 0 0">Igual peso frente a S&amp;P (RSP−SPY): ${AM.rsp_vs_spy_20d_pp != null ? sg(AM.rsp_vs_spy_20d_pp, 2, ' pp') + ' en 20 sesiones' : 'SIN DATO'}.</div>${foot('Nasdaq Data (screener de acciones USA)', false, null, 'sesión anterior')}</div></div>`;

  h += '<div class="sect"><h2>Panel de señales</h2><span class="more">▲▼ sentido del dato · verde = favorable a la bolsa, rojo = desfavorable</span></div>' + tablaSenales(E.panel, 'Dato', (M.t10Y || {}).fecha);
  h += '<div class="sect"><h2>Relaciones entre datos</h2></div>' + tablaComparaciones(E.comparaciones, (M.t10Y || {}).fecha);
  h += '<div class="sect"><h2>Contexto adicional</h2><span class="more">crédito, posicionamiento CFTC, consumo y empleo</span></div>' + tablaSenales(E.adicionales, 'Dato', (M.t10Y || {}).fecha);
  const ni = M.indices || {};
  h += '<div class="sect"><h2>Niveles de referencia</h2><span class="more">día, semana y mes anteriores · ATR de 14 sesiones</span></div><div class="card pad0 scroll"><table class="t"><thead><tr><th>Índice</th><th>Cierre</th><th>1 d</th><th>5 d</th><th>20 d</th><th>Año</th><th>vs máx. 52 s</th><th>Máx. día</th><th>Mín. día</th><th>Máx. sem.</th><th>Mín. sem.</th><th>ATR14</th></tr></thead><tbody>'
    + (Object.entries(ni).map(([n, x]) => { const v = x.niveles || {}; return `<tr><td>${esc(n)}<small>${esc(x.etf || '')} · ${esc(fd(x.fecha))}</small></td><td>${num(x.cierre, 0)}</td><td>${pill(x['1d_pct'])}</td><td>${pill(x['5d_pct'])}</td><td>${pill(x['20d_pct'])}</td><td>${pill(x.ytd_pct, 1)}</td><td>${pill(x.vs_max_52s_pct, 1)}</td><td>${fix(v.PDH, 0)}</td><td>${fix(v.PDL, 0)}</td><td>${fix(v.PWH, 0)}</td><td>${fix(v.PWL, 0)}</td><td>${fix(v.atr14, 0)}</td></tr>`; }).join('') || '<tr><td colspan="12" style="color:var(--dim)">SIN DATO</td></tr>')
    + `</tbody></table>${footIn('Monitor de índices NEXORA (Nasdaq, FRED)', false)}</div>`;
  h += '<div class="sect"><h2>Las diez preguntas</h2></div>' + preguntas(E, 'Guía NEXORA (índices)');
  h += errores(M.errores);
  return h;
}

/* ================================================================== CRIPTO */
function pageCripto() {
  const L = D.liquidez, R = D.resumen;
  let h = head('Análisis', 'Cripto', 'Bitcoin sigue a la liquidez en dólares: balance de la Fed, cuenta del Tesoro, stablecoins y apetito de riesgo. Además, derivados (funding, interés abierto), flujos de los ETF y el resto del mercado.',
    `Monitor: ${L && L.generado_utc ? esc(horaAct(L.generado_utc)) : 'SIN DATO'} · series: ${D.series && D.series.generado_utc ? esc(horaAct(D.series.generado_utc)) : 'SIN DATO'}`);
  h += fallo('liquidez') + fallo('series');
  if (!L || !L.evaluacion) return h + noData('Cripto');
  const M = L.metricas || {}, E = L.evaluacion, C = M.cripto || {}, AD = M.adicionales || {}, cr = E.checklist_resumen || {};
  const btc = C.BTC, eth = C.ETH, eb = C['ETH/BTC'];
  const sb = serC('btc') || (act('btc') || {}).serie, seb = serC('ethbtc');
  const etf = serC('etf_btc_musd');
  const TES = (R && R.tesis_activos) || {};
  const tb = TES.Bitcoin;
  const ult = etf && etf[etf.length - 1];
  h += essential(
    `Bitcoin ${btc ? num(btc.precio, 0) + ' USD (' + sg(btc['1d'], 2, ' %') + ' en el día, ' + sg(btc['7d'], 1, ' %') + ' en 7 días, ' + esc(fd(btc.fecha)) + ')' : 'SIN DATO'}; ETH/BTC ${eb ? sg(eb['7d'], 1, ' %') + ' en 7 días' : 'SIN DATO'}. ${AD.stablecoins ? 'Stablecoins ' + num(AD.stablecoins.valor_B, 0) + ' mm $ (' + sg(AD.stablecoins.delta_30d_B, 1, ' mm $') + ' en 30 días)' : ''}${ult ? '. ETF de BTC: ' + sg(ult[1], 0, ' M$') + ' el ' + esc(fd(ult[0])) : ''}.`,
    `Lectura de liquidez NEXORA: <b style="color:var(--text)">${esc(E.lectura)}</b>; checklist ${cr.cumple ?? '—'}/${cr.total ?? 8} cumplido y secuencia ${E.secuencia_cumplidos ?? '—'}/7. ${tb ? 'Tesis macro del bitcoin: ' + esc(tb.etiqueta) + '.' : ''} Es contexto, no una señal de compra o venta.`,
    `Funding ${AD.funding_btc ? num(AD.funding_btc.anualizado_7d_pct, 1) + ' % anual' : 'SIN DATO'}, interés abierto ${AD.oi_btc ? sg(AD.oi_btc.pct_7d, 1, ' %') + ' en 7 días' : 'SIN DATO'} y flujos de ETF de EE. UU.`);
  (E.avisos || []).forEach((a) => { h += `<div class="banner amber" style="margin:0 0 12px;border-radius:6px">${esc(a)}</div>`; });

  h += '<div class="sect"><h2>Mercado cripto</h2><span class="more">1 día · 7 días · 30 días · 90 días</span></div><div class="grid g4">';
  const tarjeta = (n, sym, x, u, dec) => x ? `<div class="card kpi asset"><div class="top"><div><div class="nm">${n}</div><div class="sym">${sym}</div></div>${x.sobre_sma50 ? '<span class="tag alc">sobre SMA50</span>' : '<span class="tag baj">bajo SMA50</span>'}</div>
      <div class="big" style="margin-top:10px">${num(x.precio, dec)}<small>${u}</small></div><div class="chg">${pill(x['1d'])}</div>
      <table><tr><td>7 días</td><td>${pill(x['7d'])}</td></tr><tr><td>30 días</td><td>${pill(x['30d'])}</td></tr><tr><td>90 días</td><td>${pill(x['90d'])}</td></tr></table>
      ${foot('Coinbase Exchange (velas diarias)', x.fecha)}</div>` : `<div class="card kpi asset"><div class="top"><div class="nm">${n}</div></div><div class="big">${SD}</div>${foot('Coinbase Exchange', null)}</div>`;
  h += tarjeta('Bitcoin', 'BTC-USD', btc, 'USD', 0) + tarjeta('Ethereum', 'ETH-USD', eth, 'USD', 0) + tarjeta('ETH / BTC', 'ratio', eb, '', 5) + tarjeta('Solana', 'SOL-USD', C.SOL, 'USD', 2);
  h += kpi({ lab: 'Stablecoins en circulación', exp: 'Dólares digitales listos para comprar cripto (sube = entra liquidez)', serie: serC('stablecoins_B'), unidad: 'mm $', suf: 'mm $', dec: 1, fuente: 'DefiLlama (stablecoins)', url: 'https://defillama.com/stablecoins', filas: [['1 semana', 7], ['1 mes', 30], ['3 meses', 90]] });
  h += kpi({ lab: 'Funding BTC (anualizado)', exp: 'Coste de estar largo en perpetuos: alto = exceso de apalancamiento alcista', serie: serC('funding_btc_anual_pct'), unidad: '%', suf: 'pp', dec: 1, fuente: 'OKX (BTC-USDT-SWAP)', url: 'https://www.okx.com/trade-market/funding/swap', filas: [['1 día', 1], ['1 semana', 7], ['1 mes', 28]] });
  h += kpi({ lab: 'Interés abierto BTC', exp: 'Contratos vivos en derivados: sube con el precio = tendencia con convicción', serie: serC('oi_btc'), k: 1e-9, unidad: 'mm $', suf: 'mm $', dec: 2, fuente: 'OKX (rubik, BTC)', url: 'https://www.okx.com/', filas: [['1 semana', 7], ['1 mes', 28]] });
  h += kpi({ lab: 'Volatilidad implícita BTC (DVOL)', exp: 'El «VIX del bitcoin»: sube cuando el mercado teme movimientos fuertes', serie: serC('dvol'), unidad: '', suf: 'pts', dec: 1, inv: true, fuente: 'Deribit (DVOL)', url: 'https://www.deribit.com/statistics/BTC/volatility-index', filas: [['1 semana', 7], ['1 mes', 28], ['3 meses', 90]] });
  h += '</div>';

  h += '<div class="sect"><h2>Gráficos</h2><span class="more">pasa el ratón para ver cada valor · rangos 3M / 6M / 1A</span></div>';
  h += `<div class="card"><h3>Bitcoin y su media de 50 sesiones</h3><div class="sub">USD · cierres diarios. Por encima de la media de 50 sesiones el impulso es alcista; por debajo, débil.</div>${sb ? lw('cBtc', [{ name: 'BTC', color: COL.amber, data: sb, prec: 0, area: true }, { name: 'Media 50', color: COL.blue, data: sma(sb, 50), w: 1, prec: 0 }], { tall: true, init: 270 }) : '<div class="empty" style="height:200px">SIN DATO</div>'}${foot('Coinbase Exchange (BTC-USD)', sb && sb[sb.length - 1][0], 'https://www.coinbase.com/price/bitcoin')}</div>`;
  h += '<div class="grid g2" style="margin-top:12px">';
  h += `<div class="card"><h3>ETH/BTC: el apetito por riesgo dentro de cripto</h3><div class="sub">Si sube, el dinero se arriesga hacia ETH y altcoins; si baja, se refugia en bitcoin.</div>${seb ? lw('cEthBtc', [{ name: 'ETH/BTC', color: COL.violet, data: seb, prec: 5, area: true }, { name: 'Media 50', color: COL.gray, data: sma(seb, 50), w: 1, prec: 5 }]) : '<div class="empty" style="height:200px">SIN DATO</div>'}${foot('Coinbase Exchange (ETH-USD / BTC-USD)', seb && seb[seb.length - 1][0])}</div>`;
  const stc = serC('stablecoins_B');
  h += `<div class="card"><h3>Stablecoins en circulación</h3><div class="sub">Oferta total en miles de millones de dólares. Es la «pólvora seca» del mercado.</div>${stc ? lw('cStable', [{ name: 'Stablecoins (mm $)', color: COL.pos, data: stc, prec: 1, area: true }], { init: 180 }) : '<div class="empty" style="height:200px">SIN DATO</div>'}${foot('DefiLlama', stc && stc[stc.length - 1][0], 'https://defillama.com/stablecoins')}</div>`;
  h += `<div class="card"><h3>Flujos diarios de los ETF de bitcoin de EE. UU.</h3><div class="sub">Millones de dólares netos por día (Farside Investors). Verde = entradas, rojo = salidas; las salidas fuertes restan demanda al bitcoin.</div>${etf ? barras('bEtf', etf.slice(-45).map((x) => fd(x[0])), [{ name: 'Flujo neto (M$)', data: etf.slice(-45).map((x) => x[1]) }], { suf: ' M$', dec: 0, alto: 250, fino: 12 }) : '<div class="empty" style="height:200px">SIN DATO · Farside no respondió</div>'}${foot('Farside Investors', etf && etf[etf.length - 1][0], 'https://farside.co.uk/btc/')}</div>`;
  const fu = serC('funding_btc_anual_pct');
  h += `<div class="card"><h3>Funding y volatilidad implícita</h3><div class="sub">Funding anualizado (%, eje izq.) y DVOL del bitcoin.</div>${fu || serC('dvol') ? lw('cFund', [{ name: 'Funding anual % (eje izq.)', color: COL.amber, data: fu, scale: 'left', prec: 1 }, { name: 'DVOL', color: COL.neg, data: serC('dvol') && serC('dvol').slice(-120), prec: 1 }], { left: true }) : '<div class="empty" style="height:200px">SIN DATO</div>'}${foot('OKX · Deribit', fu && fu[fu.length - 1][0])}</div></div>`;

  h += '<div class="sect"><h2>Criptomonedas principales</h2><span class="more">▲▼ cambio en el plazo · SMA50 = por encima o por debajo de su media de 50 días</span></div><div class="card pad0 scroll"><table class="t"><thead><tr><th>Activo</th><th>Precio</th><th>1 d</th><th>7 d</th><th>30 d</th><th>90 d</th><th>SMA50</th><th>Vol. 7d / 30d</th><th>Dato</th></tr></thead><tbody>'
    + Object.entries(C).map(([n, x]) => `<tr><td>${esc(n)}</td><td>${num(x.precio, x.precio >= 100 ? 0 : x.precio >= 1 ? 2 : 4)}</td><td>${pill(x['1d'])}</td><td>${pill(x['7d'])}</td><td>${pill(x['30d'])}</td><td>${pill(x['90d'])}</td><td>${x.sobre_sma50 ? '<span class="up">▲ sobre</span>' : '<span class="down">▼ bajo</span>'}</td><td><span class="mono">${x.vol7d_vs_30d != null ? num(x.vol7d_vs_30d, 2) + '×' : '—'}</span></td><td>${esc(fd(x.fecha))}</td></tr>`).join('')
    + `</tbody></table>${footIn('Coinbase Exchange (velas diarias)', (btc || {}).fecha)}</div>`;
  const mk = AD.mercado;
  h += '<div class="grid g3" style="margin-top:12px">';
  h += `<div class="card kpi"><div class="lab">Mercado total</div><div class="exp">Capitalización de todas las criptomonedas</div>${mk ? `<div class="big">${num(mk.mcap_total_usd / 1e12, 2)}<small>bill. $</small></div><table><tr><td>24 h</td><td>${pill(mk.mcap_cambio_24h_pct)}</td></tr><tr><td>Volumen 24 h</td><td><span class="mono">${num(mk.volumen_24h_usd / 1e9, 0)} mm $</span></td></tr><tr><td>Dominancia BTC</td><td><span class="mono">${num(mk.dominancia_btc_pct, 1)} %</span></td></tr><tr><td>Dominancia ETH</td><td><span class="mono">${num(mk.dominancia_eth_pct, 1)} %</span></td></tr></table>` : `<div class="big">${SD}</div>`}${foot('CoinGecko (global)', false, 'https://www.coingecko.com/', 'al ejecutar el monitor')}</div>`;
  h += `<div class="card kpi"><div class="lab">Derivados de bitcoin</div><div class="exp">Apalancamiento y prima en EE. UU.</div>${AD.funding_btc ? `<div class="big">${num(AD.funding_btc.anualizado_7d_pct, 1)}<small>% funding 7 d</small></div><table><tr><td>Funding 30 d</td><td><span class="mono">${num(AD.funding_btc.anualizado_30d_pct, 1)} %</span></td></tr><tr><td>Funding ETH 7 d</td><td><span class="mono">${AD.funding_eth ? num(AD.funding_eth.anualizado_7d_pct, 1) + ' %' : 'SIN DATO'}</span></td></tr><tr><td>Interés abierto 30 d</td><td>${AD.oi_btc ? pill(AD.oi_btc.pct_30d, 1) : '—'}</td></tr><tr><td>Prima Coinbase</td><td>${AD.prima_coinbase ? pill(AD.prima_coinbase.ultimo_pct, 3) : '—'}</td></tr></table>` : `<div class="big">${SD}</div>`}${foot('OKX · Coinbase', AD.funding_btc && AD.funding_btc.hasta ? AD.funding_btc.hasta.slice(0, 10) : false)}</div>`;
  const g3 = (M.contexto || {}).g3;
  h += `<div class="card kpi"><div class="lab">Liquidez global G3</div><div class="exp">Fed + BCE + Banco de Japón (dólares)</div>${g3 ? `<div class="big">${num(g3.valor_T, 2)}<small>bill. $</small></div><table><tr><td>3 meses (USD)</td><td>${pill(g3.pct_3m_usd)}</td></tr><tr><td>3 meses (moneda local)</td><td>${pill(g3.pct_3m_local)}</td></tr></table><div class="note" style="margin:6px 0 0">Detalle en <a href="#/liquidez" style="color:var(--amber)">Liquidez</a>.</div>` : `<div class="big">${SD}</div>`}${foot('FRED (WALCL, ECBASSETSW, JPNASSETS)', g3 && g3.mes ? g3.mes + '-01' : false)}</div></div>`;

  h += '<div class="sect"><h2>Indicadores de liquidez que mueven al bitcoin</h2><span class="more">▲▼ sentido del dato · verde = favorable a los activos de riesgo</span></div>';
  h += '<div class="card pad0 scroll"><table class="t"><thead><tr><th>Indicador</th><th>Valor</th><th>Dir.</th><th>Estado</th><th style="text-align:left">Detalle</th><th style="text-align:left">Fuente</th></tr></thead><tbody>'
    + (E.indicadores || []).map((i) => `<tr><td>${esc(i.nombre)}<small>${esc(i.nivel)}</small></td><td style="white-space:normal">${esc(i.valor)}</td><td>${dirCell(i.dir, i.estado)}</td><td>${ck2(i.estado)}</td><td style="text-align:left;color:var(--muted);white-space:normal">${esc(i.detalle)}</td><td style="text-align:left;color:var(--dim);white-space:normal">${esc(i.fuente)} · ${esc(i.frecuencia)}</td></tr>`).join('') + `</tbody></table>${footIn('Monitor de liquidez NEXORA', false)}</div>`;
  const pan = (E.contexto && E.contexto.panel) || [];
  if (pan.length) h += '<div class="sect"><h2>Contexto global y cripto</h2></div><div class="card pad0 scroll"><table class="t"><thead><tr><th>Señal</th><th>Estado</th><th>Valor</th><th style="text-align:left">Lectura</th><th style="text-align:left">Fuente</th></tr></thead><tbody>'
    + pan.map((p) => `<tr><td>${esc(p.nombre)}</td><td>${ck2(p.estado)}</td><td style="white-space:normal">${esc(p.valor)}</td><td style="text-align:left;color:var(--muted);white-space:normal">${esc(p.lectura)}</td><td style="text-align:left;color:var(--dim);white-space:normal">${esc(p.fuente)}</td></tr>`).join('') + '</tbody></table></div>';
  h += errores({ ...(M.errores || {}), ...((D.series && D.series.errores) || {}) });
  return h;
}

window.EXTRA_PAGES = { oro: pageOro, indices: pageIndices, cripto: pageCripto };
