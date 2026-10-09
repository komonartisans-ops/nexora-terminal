/* NEXORA TERMINAL · páginas de la fase 4: Sesgo de divisas, Posicionamiento (COT) y Noticias de bancos centrales.
   Se carga después de app.js y mercados.js y reutiliza sus helpers. Todo texto dinámico pasa por esc(). */
'use strict';

/* ------------------------------------------------------------------ SESGO DE DIVISAS */
const SESGO_CLS = { 'FUERTE': 'alc', 'MODERADO': 'alc', 'NEUTRAL': 'sin', 'DÉBIL': 'baj', 'MUY DÉBIL': 'baj' };
function celdaFactor(k, f, m) {
  if (!f || f.puntos == null || f.valor == null || Number.isNaN(f.valor)) return '<td class="hc z"><span class="sd-val" style="font-size:11px">SIN DATO</span></td>';
  const cls = f.puntos > 0 ? 'p1' : f.puntos < 0 ? 'm1' : 'z';
  const v = f.valor;
  const txt = k === 'tipo' ? `${num(v, 2)} %` : k === 'real' ? `${sg(v, 2)} %` : k === 'bono' ? (m.clave === 'USD' ? 'base' : `${sg(v * 100, 0)} pb`) : k === 'crec' ? `${num(v, 1)} %` : k === 'giro' ? `${sg(v, 2)} pp` : `VIX ${num(v, 1)}`;
  const sub = k === 'riesgo' ? (f.puntos > 0 ? 'se beneficia' : f.puntos < 0 ? 'se resiente' : 'sin efecto') : (f.fecha ? String(f.fecha).length === 10 ? fd(f.fecha) : f.fecha : '');
  return `<td class="hc ${cls}" title="${esc(f.fuente || '')}"><div class="hv">${esc(txt)}</div><div class="hs">${f.puntos > 0 ? '▲ +1' : f.puntos < 0 ? '▼ −1' : '▬ 0'} · ${esc(sub)}</div></td>`;
}
function pageDivisas() {
  const V = D.divisas;
  let h = head('Análisis', 'Sesgo de divisas', 'Matriz de ocho divisas por seis factores objetivos. Cada celda vale +1, 0 o −1 con una regla fija y documentada abajo; la suma es el sesgo macro relativo. Es una lectura de fortaleza macro, no una recomendación de compra o venta.',
    `Actualizado: ${V && V.generado_utc ? esc(horaAct(V.generado_utc)) : 'SIN DATO'} · tipos de política BIS/BoJ · inflación y PIB: FMI WEO ${V ? esc(V.anio_weo) : ''}`);
  h += fallo('divisas');
  if (!V || !V.monedas) return h + noData('Sesgo de divisas');
  const E = V.esencial || {};
  h += essential(esc(E.cambio || 'SIN DATO'), esc(E.significa || ''), esc(E.vigilar || ''));

  h += '<div class="sect"><h2>Matriz de factores</h2><span class="more">verde = favorable · rojo = desfavorable · ordenada por sesgo total</span></div>';
  h += '<div class="card pad0 scroll"><table class="t hm"><thead><tr><th>Divisa</th>' + V.factores.map((f) => `<th>${esc(f.nombre)}</th>`).join('') + '<th>Total</th><th>Sesgo</th><th>3 m vs USD</th></tr></thead><tbody>';
  h += V.monedas.map((m) => `<tr><td><b>${esc(m.clave)}</b><small>${esc(m.nombre)}</small><div class="hs" style="margin-top:2px">${esc(m.banco)}</div></td>${V.factores.map((f) => celdaFactor(f.clave, m.factores[f.clave], m)).join('')}
    <td><b class="mono ${m.total > 0 ? 'up' : m.total < 0 ? 'down' : ''}" style="font-size:16px">${m.total == null ? '—' : (m.total > 0 ? '+' : '') + m.total}</b><div class="hs">${m.n_factores}/6 factores</div></td>
    <td>${m.sesgo === 'SIN DATO' ? '<span class="tag sd">SIN DATO</span>' : `<span class="tag ${SESGO_CLS[m.sesgo] || 'sin'}">${esc(m.sesgo)}</span>`}</td><td>${pill(m.fx_3m_pct)}</td></tr>`).join('');
  h += '</tbody></table>' + footIn('BIS (tipos de política), Banco de Japón, FMI WEO, Tesoro/BCE/OCDE vía FRED', false, 'https://data.bis.org/topics/CBPOL', 'pasa el ratón por una celda para ver su fuente') + '</div>';

  const con = V.monedas.filter((m) => m.total != null);
  h += '<div class="grid g21" style="margin-top:12px"><div class="card"><h3>Sesgo macro total por divisa</h3><div class="sub">Suma de los seis factores (−6 a +6). No es una previsión de precio.</div>'
    + barras('bDiv', con.map((m) => m.clave), [{ name: 'Sesgo', data: con.map((m) => m.total) }], { dec: 0, alto: 250, fino: 28 })
    + foot('Reglas NEXORA sobre fuentes oficiales', false, null, 'determinista, sin IA') + '</div>';
  const R = V.riesgo || {};
  const b = V.boj;
  h += `<div class="card"><h3>Contexto del cálculo</h3><div class="sub">Lo que entra en la matriz y de dónde sale</div>
    <div class="row2"><span>Régimen de riesgo</span><span>${R.regimen ? `<span class="ck ${R.regimen === 'AVERSIÓN' ? 'no' : R.regimen === 'APETITO' ? 'ok' : 'par'}">${esc(R.regimen)}</span> <span class="mono">VIX ${num(R.vix, 1)}</span>` : SD}</span></div>
    <div class="row2"><span>Yen · tipo oficial</span><span class="mono">${b ? `${num(b.valor, 2)} % <small style="color:var(--dim)">decisión ${b.fecha ? esc(fdy(b.fecha)) : 'no localizada'}</small>` : 'SIN DATO'}</span></div>
    <div class="note" style="margin:6px 0 0">${b ? `El tipo del yen se lee de la web del propio Banco de Japón (${esc(b.texto)}); FRED/OCDE lleva años de retraso en esta serie.` : 'La web del Banco de Japón no respondió: el yen puntúa sin el factor de tipo oficial (nunca se estima).'}</div>
    <div class="note">Bono 10Y: diferencial frente al 10Y de EE. UU.; solo EE. UU. y la zona euro tienen curva diaria gratuita, el resto es mensual (OCDE) y se compara con la media del mes del Tesoro. No hay 2Y gratuito y fiable fuera de esos dos mercados.</div>
    ${foot('FMI · WEO, BIS, BCE', false, 'https://www.imf.org/external/datamapper/NGDP_RPCH@WEO')}</div></div>`;

  h += '<div class="sect"><h2>Reglas de cada factor</h2><span class="more">se aplican igual a las ocho divisas</span></div><div class="card"><ol class="reglas">' + (V.reglas || []).map((r) => `<li>${esc(r.replace(/^\d\s+·?\s*/, ''))}</li>`).join('') + '</ol>'
    + '<div class="note">Hecho: los valores de cada celda. Interpretación: el signo (+1/−1) según la regla. Hipótesis: que la macro relativa pese sobre el tipo de cambio. Escenario: un cambio de régimen de riesgo o una decisión inesperada de un banco central reordenaría la matriz de un día para otro.</div>'
    + `<div class="foot"><span>Fuentes: ${(V.fuentes || []).map((f) => `<a href="${esc(f.url)}" target="_blank" rel="noopener">${esc(f.nombre)}</a>`).join(' · ')}</span><span>memoria: data/historico_divisas.csv</span></div></div>`;
  return h + errores(V.errores);
}

/* ------------------------------------------------------------------ POSICIONAMIENTO (COT) */
function gauge(p) {
  if (p == null) return '<span class="sd-val" style="font-size:11px">SIN DATO</span>';
  const col = p >= 90 ? 'var(--neg)' : p <= 10 ? 'var(--pos)' : 'var(--amber)';
  return `<div class="gauge" title="percentil ${p} a 3 años"><i style="left:${Math.min(98, Math.max(2, p))}%;background:${col}"></i></div><div class="hs" style="text-align:center">p${p}</div>`;
}
const EST_CLS = { 'EXTREMO LARGO': 'no', 'EXTREMO CORTO': 'ok', 'LARGO ELEVADO': 'par', 'CORTO ELEVADO': 'par', 'INTERMEDIO': 'sd', 'SIN DATO': 'sd' };
function bloqueCot(b) {
  if (!b) return '<td colspan="3" style="color:var(--dim);text-align:center">SIN DATO</td>';
  return `<td><b>${sg(b.neto, 0)}</b></td><td>${pill(b.cambio_semana, 0, '')}</td><td style="min-width:96px">${gauge(b.percentil_3a)}</td>`;
}
function pagePosicionamiento() {
  const C = D.cot;
  let h = head('Análisis', 'Posicionamiento (COT)', 'Qué hacen los fondos en los futuros de divisas, oro, índices, bonos y bitcoin según la CFTC. Neto = largos − cortos; el percentil sitúa el neto actual entre las últimas ~156 semanas.',
    `Informe del ${C ? esc(fdy(C.fecha_informe)) : 'SIN DATO'} (datos del martes; la CFTC lo publica el viernes) · descargado: ${C && C.generado_utc ? esc(horaAct(C.generado_utc)) : 'SIN DATO'}`);
  h += fallo('cot');
  if (!C || !C.contratos) return h + noData('Posicionamiento COT');
  const ok = C.contratos.filter((c) => !c.sin_dato);
  const ext = [];
  ok.forEach((c) => {
    [['no_comerciales', 'no comerciales'], ['gestores', 'gestores']].forEach(([k, n]) => {
      const b = c[k]; if (b && (b.percentil_3a >= 90 || b.percentil_3a <= 10)) ext.push(`${c.nombre} (${n}: ${b.percentil_3a >= 90 ? 'largo' : 'corto'} extremo, p${b.percentil_3a})`);
    });
  });
  const mov = ok.filter((c) => c.no_comerciales).sort((a, b) => Math.abs(b.no_comerciales.cambio_semana) / (b.no_comerciales.max_3a - b.no_comerciales.min_3a || 1) - Math.abs(a.no_comerciales.cambio_semana) / (a.no_comerciales.max_3a - a.no_comerciales.min_3a || 1))[0];
  h += essential(`${ok.length} de ${C.contratos.length} contratos con dato. ${ext.length ? 'Posiciones extremas (percentil ≥90 o ≤10): ' + esc(ext.slice(0, 5).join('; ')) + (ext.length > 5 ? ` y ${ext.length - 5} más.` : '.') : 'Ninguna posición en zona extrema.'}`,
    `Hecho: los percentiles de arriba. Interpretación: un extremo largo indica posicionamiento ya cargado, de modo que queda menos combustible comprador y el activo es más sensible a una noticia adversa; un extremo corto, lo contrario. Es una lectura de contexto, no una señal de compra o venta.${mov ? ` Mayor cambio semanal relativo: ${esc(mov.nombre)} (${sg(mov.no_comerciales.cambio_semana, 0)} contratos).` : ''}`,
    'Próximo informe: viernes 15:30 ET (21:30 en Madrid). Compara si los extremos se corrigen o se amplían y si coinciden con el giro de la Fed (Bancos centrales).');

  const grupos = [...new Set(C.contratos.map((c) => c.grupo))];
  h += '<div class="sect"><h2>Posicionamiento por mercado</h2><span class="more">▲▼ cambio semanal del neto · p = percentil a 3 años · verde = corto extremo, rojo = largo extremo</span></div>';
  h += '<div class="card pad0 scroll"><table class="t cot"><thead><tr><th rowspan="2">Contrato</th><th colspan="3" class="gh">No comerciales (Legacy)</th><th colspan="3" class="gh">Gestores de activos (TFF) · oro: dinero gestionado</th><th rowspan="2">Estado</th></tr><tr><th>Neto</th><th>Δ sem.</th><th>Percentil 3a</th><th>Neto</th><th>Δ sem.</th><th>Percentil 3a</th></tr></thead><tbody>';
  grupos.forEach((g) => {
    h += `<tr class="grp"><td colspan="8">${esc(g)}</td></tr>`;
    C.contratos.filter((c) => c.grupo === g).forEach((c) => {
      const e = (c.no_comerciales && c.no_comerciales.estado) || 'SIN DATO';
      h += `<tr><td>${esc(c.nombre)}<small>${esc(c.codigo)}</small></td>${bloqueCot(c.no_comerciales)}${bloqueCot(c.gestores)}<td>${c.sin_dato ? '<span class="tag sd">SIN DATO</span>' : `<span class="ck ${EST_CLS[e]}">${esc(e)}</span>`}</td></tr>`;
    });
  });
  h += '</tbody></table>' + footIn('CFTC · Commitments of Traders (Legacy, TFF, Disaggregated)', C.fecha_informe, C.url, 'publicado el viernes siguiente') + '</div>';

  h += '<div class="sect"><h2>Neto histórico</h2><span class="more">3 años · no comerciales (eje der.) y gestores (eje izq.)</span></div><div class="grid g2">';
  [['eur', 'Euro'], ['jpy', 'Yen japonés'], ['oro', 'Oro'], ['spx', 'S&P 500'], ['ndx', 'Nasdaq-100'], ['btc', 'Bitcoin']].forEach(([k, nm]) => {
    const c = C.contratos.find((x) => x.clave === k);
    const a = c && c.no_comerciales, b = c && c.gestores;
    h += `<div class="card"><h3>${esc(nm)}</h3><div class="sub">Neto en contratos (largos − cortos)</div>${a || b ? lw('cc_' + k, [{ name: 'No comerciales', color: COL.amber, data: a && a.serie, prec: 0 }, { name: (b && b.informe.startsWith('Dinero') ? 'Dinero gestionado' : 'Gestores de activos') + ' (izq.)', color: COL.blue, data: b && b.serie, prec: 0, scale: 'left' }], { left: true, init: 730 }) : '<div class="empty" style="height:200px">SIN DATO</div>'}${foot('CFTC · COT', (a || b) && (a || b).fecha, C.url)}</div>`;
  });
  h += '</div>';
  h += `<div class="note">${esc(C.metodo)} Memoria permanente: <a class="src" href="https://github.com/komonartisans-ops/nexora-terminal/blob/main/data/historico_cot.csv" target="_blank" rel="noopener">data/historico_cot.csv</a>. Los gestores de activos no existen en el informe TFF para el oro: se usa «dinero gestionado» del informe Disaggregated.</div>`;
  return h + errores(C.errores);
}

/* ------------------------------------------------------------------ NOTICIAS DE BANCOS CENTRALES */
const horaMad = (s) => { const d = stampDate(s); return d && !isNaN(d) ? d.toLocaleTimeString('es-ES', { timeZone: 'Europe/Madrid', hour: '2-digit', minute: '2-digit' }) : '--:--'; };
const diaMad = (s) => { const d = stampDate(s); return d && !isNaN(d) ? d.toLocaleDateString('en-CA', { timeZone: 'Europe/Madrid' }) : null; };
function pageNoticias() {
  const N = D.noticias;
  let h = head('Noticias', 'Bancos centrales (RSS)', 'Comunicados, discursos y novedades de la Fed, el BCE, el Banco de Japón y el Banco de Inglaterra, tal cual los publican. Solo titular, hora, orador y enlace: NEXORA no resume ni interpreta el contenido.',
    `RSS descargados: ${N && N.generado_utc ? esc(horaAct(N.generado_utc)) : 'SIN DATO'} · horas en Madrid`);
  h += fallo('noticias');
  if (!N || !N.items) return h + noData('Noticias de bancos centrales');
  const hoy = hoyISO();
  const it = N.items.filter((i) => i.fecha_utc);
  const de24 = it.filter((i) => (Date.now() - stampDate(i.fecha_utc)) / 36e5 <= 24);
  const cuenta = {}; de24.forEach((i) => { cuenta[i.banco] = (cuenta[i.banco] || 0) + 1; });
  const disc = it.filter((i) => i.tipo === 'Discurso' || i.tipo === 'Entrevista').slice(0, 2);
  const prox = ((D.calendario && D.calendario.eventos) || []).filter((e) => e.fecha >= hoy && e.importancia === 'ALTA').slice(0, 2);
  h += essential(de24.length ? `${de24.length} publicaciones en las últimas 24 h: ${Object.entries(cuenta).map(([b, n]) => `${esc(b)} ${n}`).join(' · ')}.` : 'Sin publicaciones nuevas en las últimas 24 h.',
    `Hecho: son los titulares oficiales, sin filtrar por importancia. ${disc.length ? 'Últimos discursos o entrevistas: ' + disc.map((d) => `${esc(d.orador || d.banco)} (${esc(d.banco)}, ${esc(fd(diaMad(d.fecha_utc)))})`).join('; ') + '. ' : ''}Para saber qué dijo hay que abrir el enlace: la interpretación es tuya.`,
    prox.length ? `Eventos de importancia alta en el calendario: ${prox.map((e) => `${esc(fdh(e.fecha, e.hora_madrid))} ${esc(e.evento)}`).join(' · ')}.` : 'Sin eventos de importancia alta próximos en el calendario.');

  const bancos = ['Todos', ...new Set(it.map((i) => i.banco))];
  h += `<div class="sect"><h2>Titulares</h2><span class="more">filtra por banco</span></div><div class="filtros" id="nfil">${bancos.map((b, i) => `<button class="fbtn ${i === 0 ? 'on' : ''}" data-b="${esc(b)}">${esc(b)}</button>`).join('')}</div>`;
  h += '<div class="grid g21"><div class="card pad0" id="nlista">';
  let dia = null;
  it.slice(0, 90).forEach((i) => {
    const d = diaMad(i.fecha_utc);
    if (d !== dia) { dia = d; h += `<div class="ndia" data-dia="1">${esc(fdd(d))}</div>`; }
    h += `<a class="nrow" data-b="${esc(i.banco)}" href="${esc(i.enlace)}" target="_blank" rel="noopener"><span class="nh mono">${esc(horaMad(i.fecha_utc))}</span><span class="nb">${esc(i.banco)}</span><span class="nt"><span class="ntipo">${esc(i.tipo)}${i.orador ? ' · ' + esc(i.orador) : ''}</span>${esc(i.titulo)}</span></a>`;
  });
  h += foot('RSS oficiales de cada banco central', false, null, 'enlaces a la fuente original') + '</div>';
  h += '<div><div class="card"><h3>Estado de las fuentes</h3><div class="sub">Cada RSS falla por separado; si uno cae, el resto sigue</div>';
  h += Object.values(N.fuentes || {}).map((f) => `<div class="row2"><span><a class="src" href="${esc(f.pagina)}" target="_blank" rel="noopener">${esc(f.banco)}</a></span><span>${f.ok ? `<span class="ck ok">OK</span> <span class="mono" style="color:var(--dim);font-size:10.5px">${f.n} · ${esc(f.ultimo ? horaAct(f.ultimo + ' UTC') : '')}</span>` : `<span class="ck no">SIN DATO</span>`}</span></div>${f.ok ? '' : `<div class="note" style="margin:0 0 6px">${esc(f.error || '')}. El Tesoro de EE. UU. no publica un RSS de comunicados accesible: se enlaza su página.</div>`}`).join('');
  h += `<div class="note">${esc(N.nota)} Memoria: <a class="src" href="https://github.com/komonartisans-ops/nexora-terminal/blob/main/data/historico_noticias.csv" target="_blank" rel="noopener">data/historico_noticias.csv</a>.</div></div></div></div>`;
  MOUNT.push(() => {
    const bar = document.getElementById('nfil'), lista = document.getElementById('nlista');
    if (!bar || !lista) return;
    bar.addEventListener('click', (e) => {
      const b = e.target.closest('button'); if (!b) return;
      $$('button', bar).forEach((x) => x.classList.remove('on')); b.classList.add('on');
      const sel = b.dataset.b;
      $$('.nrow', lista).forEach((r) => { r.style.display = sel === 'Todos' || r.dataset.b === sel ? '' : 'none'; });
      $$('.ndia', lista).forEach((d) => { let n = d.nextElementSibling, vis = false; while (n && n.classList.contains('nrow')) { if (n.style.display !== 'none') vis = true; n = n.nextElementSibling; } d.style.display = vis ? '' : 'none'; });
    });
  });
  return h;
}

Object.assign(window.EXTRA_PAGES, { divisas: pageDivisas, posicionamiento: pagePosicionamiento, noticias: pageNoticias });
