/* NEXORA TERMINAL · fase 6: Riesgo de cola (SKEW), Semis vs Software y Gamma de índices.
   Se carga después de app.js, mercados.js, fase4.js y fase5.js y reutiliza sus helpers. Todo texto dinámico pasa por esc(). */
'use strict';

const ZONA_CLS = { NORMAL: 'ok', ELEVADO: 'par', ALTO: 'no' };
const CLASE_CLS = { 'FALSA ALARMA': 'par', 'CAÍDA ≥ 5 %': 'no', 'EN CURSO': 'sd' };
const nf = (v, d = 1) => (v == null || Number.isNaN(+v) ? '—' : num(v, d));
const dmy = (iso) => (iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : '—');
const linea = (serie, y) => (serie && serie.length > 1 ? [[serie[0][0], y], [serie[serie.length - 1][0], y]] : null);

/* ================================================================== RIESGO DE COLA (SKEW) */
function pageSkew() {
  const S = D.skew;
  let h = head('Análisis', 'Riesgo de cola (SKEW)', 'El SKEW de Cboe mide cuánto más caras están las puts muy fuera de dinero del S&P 500. Subido = el mercado paga por cubrirse de una caída fuerte e improbable. No predice fecha ni tamaño.',
    `Cierre del ${S && S.fecha ? esc(fdy(S.fecha)) : 'SIN DATO'} · descargado: ${S && S.generado_utc ? esc(horaAct(S.generado_utc)) : 'SIN DATO'} · zonas fijas: normal &lt; 135 · elevado ≥ 135 · alto ≥ 140 · zonas relativas (500 sesiones): elevado ≥ p75 · alto ≥ p90 <span class="tag sin" style="margin-left:6px">CRITERIO NEXORA</span>`);
  h += fallo('skew');
  if (!S || S.valor == null) return h + noData('SKEW de Cboe');
  const E = S.esencial || {};
  h += essential(esc(E.cambio), esc(E.significa), esc(E.vigilar));
  const conf = S.confirmaciones || [];
  const sk = (S.series && S.series.skew) || [];
  const est = S.estudio || null;

  h += '<div class="sect"><h2>Lectura actual</h2><span class="more">SKEW · zona relativa · VIX · crédito · fondos monetarios</span></div><div class="grid g3">';
  h += `<div class="card kpi"><div class="lab">SKEW de Cboe</div><div class="exp">Zona: ${esc(S.zona)}</div><div class="big">${nf(S.valor, 1)}<small> ${S.zona === 'ALTO' ? '≥ 140' : S.zona === 'ELEVADO' ? '≥ 135' : '&lt; 135'}</small></div>
    <table><tr><td>Sesión previa</td><td>${S.previo != null ? nf(S.previo, 1) : '—'}</td></tr><tr><td>Percentil desde 1990</td><td><b>p${S.percentil_hist}</b></td></tr><tr><td>Percentil último año</td><td>p${S.percentil_1a}</td></tr>
    <tr><td>Sesiones en la zona</td><td>${S.racha_sesiones}</td></tr></table>
    <div style="margin:8px 0 2px"><span class="ck ${ZONA_CLS[S.zona] || 'sd'}">${esc(S.zona)}</span></div>${foot(S.fuente.split('(')[0], S.fecha, S.url)}</div>`;
  if (S.zona_relativa) {
    const zr = S.zona_relativa;
    h += `<div class="card kpi"><div class="lab">Zona relativa · últimas ${S.ventana_relativa} sesiones <span class="tag sin" style="margin-left:4px">ALERTA</span></div><div class="exp">Percentil del SKEW dentro de su propia ventana reciente (primera condición de la alerta de Telegram)</div>
      <div class="big">p${nf(S.percentil_500, 0)}<small><span class="ck ${ZONA_CLS[zr] || 'sd'}">${esc(zr)}</span></small></div>
      <table><tr><td>Umbral alto (p90)</td><td><b>${nf(S.umbral_alto_500, 1)}</b></td></tr><tr><td>Umbral elevado (p75)</td><td>${nf(S.umbral_elevado_500, 1)}</td></tr><tr><td>Sesiones en la zona</td><td>${S.racha_relativa}</td></tr>
      <tr><td>Avisos en 3 años (relativa · fija)</td><td>${S.avisos_3_anos ? S.avisos_3_anos.relativa + ' · ' + S.avisos_3_anos.fija : '—'}</td></tr></table>
      ${foot('Cálculo NEXORA sobre Cboe · SKEW', S.fecha, S.url)}</div>`;
  }
  conf.forEach((c) => {
    const cls = c.caducada ? 'sd' : c.encendida === true ? 'no' : c.encendida === false ? 'ok' : 'sd';
    h += `<div class="card kpi"><div class="lab">${esc(c.nombre)}</div><div class="exp">${c.caducada ? 'CADUCADA · NO SUMA' : c.encendida === true ? 'ENCENDIDA' : c.encendida === false ? 'APAGADA' : 'SIN DATO'}</div>
      <div style="margin:6px 0"><span class="ck ${cls}">${esc(c.estado)}</span></div><div class="note" style="margin:0 0 6px">${esc(c.valor)}</div><div class="note" style="margin:0;color:var(--dim)">${esc(c.regla)}</div>
      ${c.retraso_dias > 21 ? `<div class="note" style="margin:6px 0 0;color:var(--amber)">Dato con ${c.retraso_dias} días de retraso (publicación de la fuente).</div>` : ''}
      ${foot(c.fuente, c.fecha, c.url && c.url.startsWith('http') ? c.url : null)}</div>`;
  });
  h += '</div>';
  if (S.alerta) {
    const A = S.alerta;
    const ck = (ok, t) => `<span class="ck ${ok ? 'ok' : 'no'}">${ok ? 'SÍ' : 'NO'}</span> ${t}`;
    h += `<div class="card" style="margin-top:12px"><div class="lab">Regla de la alerta de Telegram <span class="tag sin" style="margin-left:4px">CRITERIO NEXORA</span></div>
      <p class="note" style="margin:6px 0 8px">${esc(A.regla)}</p>
      <div class="row2"><span>1 · Zona relativa alta (percentil ≥ p90 de ${S.ventana_relativa} sesiones)</span><span>${ck(A.cumple_zona, 'p' + nf(S.percentil_500, 0) + ' · ' + esc(S.zona_relativa || '—'))}</span></div>
      <div class="row2"><span>2 · Al menos ${A.minimo} confirmaciones encendidas (VIX, crédito, fondos monetarios)</span><span>${ck(A.cumple_confirmaciones, A.confirmaciones_encendidas + ' de ' + A.confirmaciones_validas)}</span></div>
      <div class="row2"><span><b>Estado hoy</b></span><span><b>${esc(A.estado)}</b></span></div></div>`;
  }

  /* gráficos: SKEW con umbrales, y S&P 500 */
  h += '<div class="sect"><h2>SKEW y S&amp;P 500</h2><span class="more">ámbar = SKEW · rojo/gris = umbrales fijos 140/135 · violeta/azul = percentiles 90/75 de las últimas 500 sesiones</span></div><div class="grid g2">';
  h += `<div class="card chartcard"><h3>SKEW de Cboe</h3><div class="sub">Últimos ~5 años</div>${lw('cSkew', [{ name: 'SKEW', color: COL.amber, data: sk, prec: 1, area: true },
    { name: 'Alto fijo (140)', color: COL.neg, data: linea(sk, 140), prec: 0, w: 1 }, { name: 'Elevado fijo (135)', color: COL.gray, data: linea(sk, 135), prec: 0, w: 1 },
    { name: 'p90 de 500 sesiones', color: COL.violet, data: (S.series && S.series.p90_500) || [], prec: 1, w: 1 }, { name: 'p75 de 500 sesiones', color: COL.blue, data: (S.series && S.series.p75_500) || [], prec: 1, w: 1 }], { tall: true, init: 730 })}${foot('Cboe · SKEW', S.fecha, S.url)}</div>`;
  h += `<div class="card chartcard"><h3>S&amp;P 500 y VIX</h3><div class="sub">S&amp;P 500 (eje izq.) y VIX (eje der.)</div>${lw('cSkSpx', [{ name: 'VIX', color: COL.violet, data: S.series.vix, prec: 2, scale: 'right', w: 1 },
    { name: 'S&P 500', color: COL.blue, data: S.series.spx, prec: 0, scale: 'left' }], { left: true, tall: true, init: 730 })}${foot('Cboe · SPX y VIX', S.fecha, S.url)}</div></div>`;

  /* estudio histórico */
  if (est && est.resumen) {
    const r = est.resumen, b = est.tasa_base || {};
    h += '<div class="sect"><h2>Estudio histórico propio</h2><span class="more">qué hizo el S&amp;P 500 tras entrar el SKEW en zona alta · incluye las falsas alarmas</span></div>';
    h += `<div class="note" style="margin-top:0">Entrada = primer cierre ≥ 140 tras ${est.enfriamiento} sesiones sin estarlo (desde ${esc(dmy(r.desde))}). Falsa alarma = el S&amp;P 500 no cae un 5 % o más desde ese cierre en las 60 sesiones siguientes. ${esc(est.sesgo_del_estudio)}</div>`;
    h += '<div class="grid g21"><div class="card pad0 scroll"><table class="t"><thead><tr><th>Horizonte</th><th>Entradas</th><th>Media</th><th>Mediana</th><th>% positivos</th><th>Peor</th><th>Mejor</th><th>Tasa base (mediana · % pos.)</th></tr></thead><tbody>';
    (est.horizontes || []).forEach((hz) => {
      const x = r[String(hz)] || {}, y = b[String(hz)] || {};
      h += `<tr><td>${hz} sesiones <small>≈ ${hz === 5 ? '1' : hz === 20 ? '4' : '12'} semanas</small></td><td>${x.n ?? '—'}</td><td>${pill(x.media)}</td><td>${pill(x.mediana)}</td><td>${nf(x.pct_positivos, 0)} %</td><td>${pill(x.peor)}</td><td>${pill(x.mejor)}</td><td>${pill(y.mediana)} <small style="display:inline;color:var(--dim)">· ${nf(y.pct_positivos, 0)} %</small></td></tr>`;
    });
    h += `</tbody></table>${footIn('Cboe (SKEW y SPX, precio sin dividendos) · cálculo NEXORA', S.fecha, S.url, 'tasa base = cualquier sesión desde 1990')}</div>`;
    h += `<div class="card"><h3>¿Cuántas fueron falsas alarmas?</h3><div class="sub">${r.completos} entradas con 60 sesiones cumplidas</div>
      <div class="row2"><span>Caída ≥ 5 % posterior</span><span class="mono down">${r.caidas} · ${nf(100 - r.pct_falsas, 0)} %</span></div>
      <div class="row2"><span>Falsa alarma</span><span class="mono amber">${r.falsas_alarmas} · ${nf(r.pct_falsas, 0)} %</span></div>
      <div class="row2"><span>Tasa base: caída ≥ 5 % en cualquier sesión</span><span class="mono">${nf(b.caida_5_60s_pct, 0)} %</span></div>
      <div class="note">Hecho: el SKEW alto no multiplicó la frecuencia de caídas fuertes posteriores. Interpretación: el SKEW mide el precio de la cobertura, no la probabilidad del evento. Úsalo como contexto de posicionamiento, no como señal de timing.</div></div></div>`;
    const er = S.estudio_relativo, ef = S.estudio_fijo_misma_muestra;
    if (er && er.resumen && ef && ef.resumen) {
      const fila = (nom, e) => {
        const r = e.resumen, b = e.tasa_base || {};
        return `<tr><td><b>${nom}</b><small>${esc(e.criterio)}</small></td><td>${r.episodios}</td><td>${r.completos}</td><td>${r.caidas} · ${nf(100 - r.pct_falsas, 0)} %</td><td><b>${r.falsas_alarmas} · ${nf(r.pct_falsas, 0)} %</b></td>
          <td>${pill((r['5'] || {}).mediana)}</td><td>${pill((r['20'] || {}).mediana)}</td><td>${pill((r['60'] || {}).mediana)}</td><td>${nf(b.caida_5_60s_pct, 0)} %</td></tr>`;
      };
      h += `<div class="sect"><h2>Zona relativa frente a zona fija · misma muestra</h2><span class="more">desde ${esc(dmy(er.muestra_desde))} (primera sesión con 500 de historia) · se revalida con el mismo estudio</span></div>
        <div class="card pad0 scroll"><table class="t"><thead><tr><th>Criterio</th><th>Entradas</th><th>Con 60 s</th><th>Caída ≥ 5 %</th><th>Falsas alarmas</th><th>Mediana 5 s</th><th>Mediana 20 s</th><th>Mediana 60 s</th><th>Tasa base caída ≥ 5 %</th></tr></thead><tbody>
        ${fila('Zona relativa (≥ p90)', er)}${fila('Zona fija (≥ 140)', ef)}</tbody></table>${footIn('Cboe · SKEW y SPX · cálculo NEXORA (mismas reglas: 5/20/60 sesiones, caída ≥ 5 %, enfriamiento de 10 sesiones)', S.fecha, S.url)}</div>
        <div class="note">Hecho: con la zona relativa la alerta salta ${er.resumen.episodios} veces desde ${esc(dmy(er.muestra_desde))}; en ${nf(er.resumen.pct_falsas, 0)} % de ellas el S&amp;P 500 no cayó un 5 % en las 60 sesiones siguientes, frente a una tasa base de caída del ${nf((er.tasa_base || {}).caida_5_60s_pct, 0)} % en cualquier sesión. Interpretación: ninguno de los dos criterios mejora la frecuencia de caídas fuertes respecto a una sesión cualquiera; la zona relativa sirve para que la alerta no quede encendida permanentemente cuando el SKEW sube de nivel de forma estructural, no para predecir caídas.</div>`;
    }
    if (est.episodio_actual) {
      const a = est.episodio_actual;
      h += `<div class="note">Episodio actual: entrada el ${esc(dmy(a.entrada))} con el S&amp;P 500 en ${nf(a.spx_entrada, 0)}; hoy ${nf(a.spx_ultimo, 0)} (${sg(a.ret_desde_entrada_pct, 2, ' %')} desde la entrada, ${a.sesiones} sesiones en zona alta).</div>`;
    }
    h += '<div class="sect"><h2>Episodios</h2><span class="more">más recientes primero</span></div><div class="card pad0 scroll" style="max-height:440px;overflow:auto"><table class="t"><thead><tr><th>Entrada</th><th>SKEW</th><th>S&amp;P 500</th><th>5 sesiones</th><th>20 sesiones</th><th>60 sesiones</th><th>Peor caída en 60 s</th><th>Resultado</th></tr></thead><tbody>';
    h += est.episodios.map((e) => `<tr><td>${esc(dmy(e.fecha))}</td><td>${nf(e.skew, 1)}</td><td>${nf(e.spx, 0)}</td><td>${pill(e.ret['5'])}</td><td>${pill(e.ret['20'])}</td><td>${pill(e.ret['60'])}</td><td>${pill(e.peor_caida_60s)}</td><td><span class="ck ${CLASE_CLS[e.clase] || 'sd'}">${esc(e.clase)}</span></td></tr>`).join('');
    h += `</tbody></table>${footIn('Cboe · SKEW y SPX', S.fecha, S.url)}</div>`;
  }

  /* deriva estructural */
  const dist = (S.distribucion_anual || []).filter((d) => d.anio >= 2005);
  h += '<div class="sect"><h2>El umbral de 140 y su deriva</h2><span class="more">% de sesiones de cada año con SKEW ≥ 140</span></div><div class="grid g21"><div class="card"><h3>Sesiones en zona alta por año</h3><div class="sub">Si el SKEW vive estructuralmente más alto, un umbral fijo selecciona menos</div>'
    + barras('bSkDist', dist.map((d) => String(d.anio)), [{ name: '% sesiones ≥ 140', data: dist.map((d) => d.pct_alto) }], { dec: 0, suf: ' %', alto: 240, fino: 22 }) + foot('Cboe · SKEW (cálculo NEXORA)', S.fecha, S.url) + '</div>';
  const f = S.fondos_monetarios || {}, m = f.minoristas, t = f.total;
  h += `<div class="card"><h3>Dinero en fondos monetarios</h3><div class="sub">Refugio de liquidez: entradas fuertes suelen acompañar a la aversión al riesgo</div>
    <div class="row2"><span>Minoristas (FRED WRMFNS, semanal)</span><span class="mono">${m ? `${nf(m.valor_mm / 1000, 2)} bill. $ <small style="color:var(--dim)">${esc(fd(m.fecha))}</small>` : 'SIN DATO'}</span></div>
    ${m ? `<div class="row2"><span>Variación 4 · 13 · 52 semanas</span><span>${pill(m.var_4s_pct)} ${pill(m.var_13s_pct)} ${pill(m.var_52s_pct)}</span></div><div class="row2"><span>Percentil de la variación a 13 s</span><span class="mono">p${m.percentil_var_13s}</span></div>` : ''}
    <div class="row2"><span>Total (OFR, N-MFP, mensual)</span><span class="mono">${t ? `${nf(t.valor_bill, 2)} bill. $ <small style="color:var(--dim)">${esc(fd(t.fecha))}</small>` : 'SIN DATO'}</span></div>
    ${t ? `<div class="row2"><span>Variación 1 · 3 · 12 meses</span><span>${pill(t.var_1m_pct)} ${pill(t.var_3m_pct)} ${pill(t.var_12m_pct)}</span></div>` : ''}
    ${m && m.serie ? spark(m.serie, 156) : ''}${foot('FRED WRMFNS · OFR Money Market Fund Monitor', m && m.fecha, m && m.url)}</div></div>`;
  h += `<div class="note">${esc(S.metodo)} Memoria permanente: <a class="src" href="https://github.com/komonartisans-ops/nexora-terminal/blob/main/data/historico_skew.csv" target="_blank" rel="noopener">data/historico_skew.csv</a>. Alerta de Telegram: una por episodio, solo con zona alta relativa (percentil ≥ 90 de las últimas 500 sesiones) Y al menos 2 de las 3 confirmaciones encendidas (VIX, crédito, fondos monetarios).</div>`;
  return h + errores(S.errores);
}

/* ================================================================== SEMIS vs SOFTWARE */
const ESC_CLS = { neg: 'no', pos: 'ok', amb: 'par', sin: 'sd' };
function pageSemis() {
  const S = D.semis;
  let h = head('Análisis', 'Semis vs Software', 'Ratio SMH/IGV con sus medias de 50 y 200 sesiones, escenario del día con reglas fijas, sensibilidad de NQ, ES y YM y los grandes del Nasdaq. Semis = hardware y ciclo de inversión; software = tecnología con poco capital.',
    `Cierre del ${S && S.fecha ? esc(fdy(S.fecha)) : 'SIN DATO'} · descargado: ${S && S.generado_utc ? esc(horaAct(S.generado_utc)) : 'SIN DATO'} <span class="tag sin" style="margin-left:6px">CRITERIO NEXORA</span>`);
  h += fallo('semis');
  if (!S || !S.ratio) return h + noData('Semis vs Software');
  const R = S.ratio, E = S.escenario, EE = S.esencial || {};
  h += essential(esc(EE.cambio), esc(EE.significa), esc(EE.vigilar));

  h += '<div class="sect"><h2>Estado</h2><span class="more">ratio · tendencia · escenario de hoy · escenario de la semana</span></div><div class="grid g4">';
  h += `<div class="card kpi"><div class="lab">Ratio SMH / IGV</div><div class="exp">Semis relativos a software</div><div class="big">${nf(R.valor, 3)}</div>
    <table><tr><td>vs media 50</td><td>${pill(R.vs_sma50_pct)}</td></tr><tr><td>vs media 200</td><td>${pill(R.vs_sma200_pct)}</td></tr><tr><td>1 mes</td><td>${pill(R.cambios_pct['1m'], 1)}</td></tr><tr><td>3 meses</td><td>${pill(R.cambios_pct['3m'], 1)}</td></tr><tr><td>12 meses</td><td>${pill(R.cambios_pct['12m'], 1)}</td></tr><tr><td>Percentil 1 año</td><td>p${R.percentil_1a}</td></tr></table>
    ${foot('Yahoo Finance · SMH / IGV', R.fecha)}</div>`;
  h += `<div class="card kpi"><div class="lab">Tendencia del ratio</div><div class="exp">Posición frente a sus medias</div><div style="margin:12px 0 8px"><span class="tag ${R.tendencia.includes('SEMIS') ? 'alc' : R.tendencia.includes('SOFTWARE') ? 'deb' : 'sin'}" style="font-size:12px">${esc(R.tendencia)}</span></div>
    <div class="note" style="margin:0">${R.cruce_medias ? `Último cruce 50/200: ${esc(R.cruce_medias.tipo)} el ${esc(dmy(R.cruce_medias.fecha))}.` : 'Sin cruce 50/200 en la serie.'}</div>${foot('Cálculo NEXORA', R.fecha)}</div>`;
  h += `<div class="card kpi"><div class="lab">Escenario de hoy</div><div class="exp">SMH ${sg(S.hoy.smh_pct, 2, ' %')} · IGV ${sg(S.hoy.igv_pct, 2, ' %')}</div><div style="margin:12px 0 8px"><span class="ck ${ESC_CLS[E.tono] || 'sd'}" style="font-size:12px">${esc(E.etiqueta)}</span></div>
    <div class="note" style="margin:0">${esc(E.texto)}</div>${foot('Reglas NEXORA (abajo)', S.hoy.fecha)}</div>`;
  const W = S.semana.escenario;
  h += `<div class="card kpi"><div class="lab">Escenario de 5 sesiones</div><div class="exp">SMH ${sg(S.semana.smh_pct, 2, ' %')} · IGV ${sg(S.semana.igv_pct, 2, ' %')}</div><div style="margin:12px 0 8px"><span class="ck ${ESC_CLS[W.tono] || 'sd'}" style="font-size:12px">${esc(W.etiqueta)}</span></div>
    <div class="note" style="margin:0">Mismas reglas aplicadas a la variación de la semana.</div>${foot('Reglas NEXORA (abajo)', S.hoy.fecha)}</div></div>`;

  h += `<div class="sect"><h2>Ratio SMH/IGV</h2><span class="more">si sube, lideran los semis; si baja, el software</span></div><div class="card chartcard">${lw('cSemis', [{ name: 'SMH/IGV', color: COL.amber, data: R.serie, prec: 3 },
    { name: 'Media 50', color: COL.blue, data: R.sma50_serie, prec: 3, w: 1 }, { name: 'Media 200', color: COL.violet, data: R.sma200_serie, prec: 3, w: 1 }], { tall: true, init: 365 })}${foot('Yahoo Finance · SMH, IGV', R.fecha)}</div>`;

  /* impacto relativo */
  const I = S.impacto || {};
  h += '<div class="sect"><h2>Impacto relativo en NQ, ES y YM</h2><span class="more">regresión de 250 sesiones del índice sobre SMH e IGV · sensibilidad histórica, no causalidad</span></div><div class="grid g21"><div class="card pad0 scroll"><table class="t"><thead><tr><th>Futuro</th><th>β semis</th><th>β software</th><th>R²</th><th>Hoy · índice</th><th>Aporta semis</th><th>Aporta software</th><th>Explicado</th></tr></thead><tbody>';
  ['NQ', 'ES', 'YM'].forEach((k) => {
    const x = I[k];
    h += x ? `<tr><td><b>${k}</b><small>${esc(x.nombre)} (${esc(x.indice)})</small></td><td>${nf(x.beta_semis, 2)}</td><td>${nf(x.beta_software, 2)}</td><td>${nf(x.r2, 2)}</td><td>${pill(x.real_pct)}</td><td>${pill(x.contrib_semis_pp, 2, ' pp')}</td><td>${pill(x.contrib_software_pp, 2, ' pp')}</td><td>${pill(x.explicado_pp, 2, ' pp')}</td></tr>`
      : `<tr><td><b>${k}</b></td><td colspan="7" style="text-align:left;color:var(--dim)">SIN DATO</td></tr>`;
  });
  h += `</tbody></table>${footIn('Yahoo Finance · cálculo NEXORA (mínimos cuadrados)', S.fecha)}</div>`;
  const P = S.pesos_ndx;
  h += `<div class="card"><h3>Peso en el Nasdaq-100</h3><div class="sub">${P ? `Componentes de QQQ al ${esc(dmy(P.fecha))}` : 'SIN DATO'}</div>${P ? dona('dSemis', [['Semis', P.semis_pct], ['Software', P.software_pct], ['Resto', P.otros_pct]], ['#C8A24A', '#6C8EBF', '#2A313B'], 180) : ''}
    ${P ? `<div class="note">Semis: ${esc(P.semis.slice(0, 8).join(', '))}…<br>Software: ${esc(P.software.slice(0, 8).join(', '))}…</div>` : ''}${foot('Invesco · holdings de QQQ', P && P.fecha, P && P.url)}</div></div>`;
  h += `<div class="note">Lectura: con β semis mayor que β software, un día de semis fuertes y software plano mueve más al NQ que al revés. En YM (30 valores, casi sin semis ni software puros) el R² es bajo: la sensibilidad es débil y no debe sobreinterpretarse.</div>`;

  /* grandes */
  h += '<div class="sect"><h2>Grandes del Nasdaq</h2><span class="more">lista fija NEXORA · peso real de QQQ (Invesco) · RS = rentabilidad 1 mes menos la de QQQ</span></div><div class="card pad0 scroll"><table class="t"><thead><tr><th>Valor</th><th>Sector</th><th>Peso</th><th>Precio</th><th>1d</th><th>1 sem</th><th>1 mes</th><th>vs SMA50</th><th>vs SMA200</th><th>RS 1m</th><th>Aporta hoy</th><th>3 meses</th></tr></thead><tbody>';
  const ord = S.grandes.slice().sort((a, b) => (b.peso_pct || 0) - (a.peso_pct || 0));
  h += ord.map((g) => g.sin_dato ? `<tr><td>${esc(g.nombre)}<small>${esc(g.simbolo)}</small></td><td colspan="11" style="text-align:left;color:var(--dim)">SIN DATO</td></tr>`
    : `<tr><td>${esc(g.nombre)}<small>${esc(g.simbolo)}</small></td><td style="text-align:left;color:var(--muted)">${esc(g.sector)}</td><td>${g.peso_pct != null ? nf(g.peso_pct, 1) + ' %' : '—'}</td><td>${nf(g.precio, 2)}</td><td>${pill(g.d1_pct)}</td><td>${pill(g.d5_pct)}</td><td>${pill(g.d21_pct)}</td><td>${pill(g.vs_sma50_pct, 1)}</td><td>${pill(g.vs_sma200_pct, 1)}</td><td>${pill(g.rs21_vs_qqq_pp, 1, ' pp')}</td><td>${pill(g.contrib_hoy_pp, 2, ' pp')}</td><td>${pill(g.d63_pct)}</td></tr>`).join('');
  h += `</tbody></table>${footIn('Yahoo Finance (respaldo Nasdaq.com) · Invesco (pesos)', S.fecha, null, 'peso del cierre anterior')}</div>`;

  h += '<div class="sect"><h2>Reglas</h2><span class="more">fijas, documentadas y sin optimizar</span></div><div class="card"><ol class="reglas">' + (S.reglas || []).map((r) => `<li>${esc(r)}</li>`).join('') + '</ol>'
    + '<div class="note">Hecho: cierres de SMH, IGV y de los índices. Interpretación: la etiqueta del escenario según estas reglas. Hipótesis: que el diferencial refleje rotación de capital y no ruido de un día. Escenario: si el diferencial se mantiene varias sesiones, la rotación se consolida; si revierte, era ruido.</div>'
    + `<div class="foot"><span>Fuentes: Yahoo Finance · Nasdaq.com (respaldo) · Invesco</span><span>memoria: site/data/semis.json</span></div></div>`;
  return h + errores(S.errores);
}

/* ================================================================== GAMMA DE ÍNDICES */
/* complemento de Chart.js: líneas verticales con rótulo en un eje de categorías (nivel más próximo) */
function lineasNivel(niveles) {
  return {
    id: 'niveles',
    afterDatasetsDraw(ch) {
      const { ctx, chartArea: a, scales: { x } } = ch;
      const labs = ch.data.labels.map(Number);
      ctx.save();
      niveles.forEach((n) => {
        if (n.v == null || !labs.length) return;
        let j = 0, best = Infinity;
        labs.forEach((l, i) => { const d = Math.abs(l - n.v); if (d < best) { best = d; j = i; } });
        const px = x.getPixelForValue(j);
        if (px < a.left || px > a.right) return;
        ctx.strokeStyle = n.c; ctx.lineWidth = 1.2; ctx.setLineDash(n.dash ? [4, 3] : []);
        ctx.beginPath(); ctx.moveTo(px, a.top); ctx.lineTo(px, a.bottom); ctx.stroke();
        ctx.setLineDash([]); ctx.fillStyle = n.c; ctx.font = '10px IBM Plex Mono'; ctx.textAlign = 'center';
        ctx.fillText(n.t, Math.min(Math.max(px, a.left + 28), a.right - 28), a.top + 10 + (n.fila || 0) * 11);
      });
      ctx.restore();
    },
  };
}
/* ---- gamma por activo (pestañas US500 · US100 · US30 · ORO): misma estructura completa para los cuatro ---- */
const GM_ACT = [{ id: 'US500', es: 'ES', fuente: 'Yahoo Finance (ES=F) · data/historico_gamma.csv' }, { id: 'US100', es: 'NQ', fuente: 'Yahoo Finance (NQ=F) · data/historico_gamma.csv' },
  { id: 'US30', fuente: 'Yahoo Finance (YM=F) · data/historico_gamma.csv (indice YM)' }, { id: 'ORO', fuente: 'GLD (Yahoo Finance) · data/historico_gamma_oro.csv' }];
let GM_GRAF = [];
function gmEntrada(a) {
  const G = D.gamma || {};
  if (a.id === 'US500' || a.id === 'US100') return { x: (G.indices || {})[a.es], rev: (G.revision || {})[a.es], err: (G.errores || {})[a.es] };
  const x = a.id === 'US30' ? D.gamma_us30 : D.gamma_oro;
  return { x, rev: x && x.revision, err: x && x.error_ultimo };
}
const gmN = (v, d) => (v == null ? '—' : nf(v, d));
const gmG = (m, d = 1) => (m == null ? '—' : Math.abs(m) >= 1000 ? `${nf(m / 1000, d)} mm $` : `${nf(m, 0)} M $`);      // GEX en M$ si es pequeño (GLD, DIA), en mm $ si no
/* Lo esencial: qué ha cambiado frente a la sesión guardada anterior, qué significa el régimen y qué vigilar (hechos del JSON; la lectura es hipótesis) */
function gmEsencial(x, C, F, dec, ref) {
  const u = C === 'XAU' ? C : (F || C);      // el oro compara sus niveles en XAU; los demás, en el futuro
  let l1;
  if (!x.anterior) l1 = `Primera sesión guardada de este activo (${esc(dmy(x.sesion))}): todavía no hay una sesión anterior con la que comparar. Hoy la gamma es ${esc(String(x.regimen).toLowerCase())} (${gmG(x.gex_neto_musd)} por 1 %).`;
  else {
    const n = x.anterior.niveles, f = (k, t) => (n[k] && n[k].dif != null ? `${t} ${nf(n[k].antes, dec)} → ${nf(n[k].ahora, dec)} (${sg(n[k].dif, dec)})` : `${t} SIN DATO`);
    l1 = `Frente a la sesión del ${esc(dmy(x.anterior.sesion_anterior))}: ${f('call_wall', 'Call Wall')}, ${f('put_wall', 'Put Wall')}, ${f('flip', 'Gamma Flip')} (${esc(u)}). ${x.anterior.regimen.cambio ? `<b>Cambio de régimen: de gamma ${esc(String(x.anterior.regimen.antes).toLowerCase())} a ${esc(String(x.regimen).toLowerCase())}.</b>` : `Régimen sin cambios: gamma ${esc(String(x.regimen).toLowerCase())}.`}`;
  }
  const pos = x.regimen === 'POSITIVA';
  const l2 = `Hipótesis (no hecho): con gamma ${pos ? 'positiva' : 'negativa'}, las coberturas de los creadores de mercado tienden a ${pos ? 'frenar los movimientos (venden en subidas, compran en bajadas)' : 'amplificarlos (compran en subidas, venden en bajadas)'}. Depende de suponer que los clientes están largos de puts y los creadores largos de calls: el interés abierto no revela quién está de cada lado.${ref ? ` Los niveles son los de ${esc(ref)} pasados a ${esc(C)}: una referencia, no las opciones del propio ${esc(C)}.` : ''}`;
  const sp = x.spot_idx, niv = [['Call Wall', x.call_wall], ['Put Wall', x.put_wall], ['Gamma Flip', x.flip]].filter(([, o]) => o && sp != null).map(([t, o]) => [t, o.idx - sp]).sort((a, b) => Math.abs(a[1]) - Math.abs(b[1]));
  const em = x.em && x.em.puntos != null ? ` El EM (movimiento esperado de un día) es ${nf(x.em.puntos, dec)} pts.` : '';
  const l3 = `${niv.length ? `El nivel más cercano es el ${esc(niv[0][0])}, a ${sg(niv[0][1], dec)} pts del precio.` : ''}${em} Un cierre firme más allá del Call Wall o por debajo del Put Wall invalida el nivel. Se recalcula en cada cierre de Nueva York (21:30 UTC).`;
  return essential(l1, l2, l3);
}
function gmHistorial(a, x, rev, C, F, dec) {
  const k = F || C, etf = x.etiqueta ? ` (${esc(a.id === 'ORO' ? 'GLD $' : 'DIA')})` : '';
  let h = '<div class="sect"><h2>Cómo reaccionó el precio en cada nivel</h2><span class="more">cada sesión guardada frente a la barra de la sesión siguiente</span></div>';
  h += `<div class="note" style="margin-top:0">Histórico propio: ${x.sesiones_guardadas || 0} ${x.sesiones_guardadas === 1 ? 'sesión guardada' : 'sesiones guardadas'} (el histórico empieza con este módulo: no hay cadenas de opciones gratuitas anteriores, no se reconstruye). Se evalúa sesión a sesión${a.id === 'ORO' ? '; se mide sobre GLD, donde están los niveles (niveles en $ de GLD)' : '; se excluyen las ventanas de vencimiento trimestral del futuro'}.</div>`;
  const col = { RECHAZADO: 'ok', DEFENDIDO: 'ok', SUPERADO: 'no', ROTO: 'no', 'NO TOCADO': 'sd', 'CERRÓ POR ENCIMA': 'par', 'CERRÓ POR DEBAJO': 'par' };
  const d = a.id === 'ORO' ? 1 : 0;
  h += `<div class="card pad0 scroll" style="margin-bottom:12px"><table class="t"><thead><tr><th>${esc(k)} · sesión${etf}</th><th>Estado</th><th>Call Wall</th><th>Put Wall</th><th>Gamma Flip</th><th>Sesión siguiente (máx · mín · cierre)</th></tr></thead><tbody>`;
  if (!rev || rev.sin_dato || !rev.sesiones.length) h += '<tr><td colspan="6" style="text-align:left;color:var(--dim)">SIN DATO: todavía no hay sesiones guardadas o la fuente no respondió.</td></tr>';
  else h += rev.sesiones.slice(0, 20).map((s) => {
    const c = (n) => { const v = s.niveles && s.niveles[n]; return v ? `<span class="ck ${col[v.resultado] || 'sd'}">${esc(v.resultado)}</span><small>${nf(v.nivel, d)} · cierre ${sg(v.dist_cierre, d)}</small>` : '—'; };
    const sig = s.sesion_siguiente;
    return `<tr><td>${esc(dmy(s.fecha_sesion))}</td><td><span class="ck ${s.estado === 'EVALUADA' ? 'ok' : s.estado === 'ROLL' ? 'par' : 'sd'}">${esc(s.estado)}</span></td><td>${c('Call Wall')}</td><td>${c('Put Wall')}</td><td>${c('Gamma Flip')}</td>
      <td>${sig ? `${esc(fd(sig.fecha))}: ${nf(sig.h, d)} · ${nf(sig.l, d)} · ${nf(sig.c, d)}` : esc(s.nota || 'esperando la sesión siguiente')}</td></tr>`;
  }).join('');
  const rs = rev && rev.resumen && rev.resumen['Call Wall'];
  h += `</tbody></table>${footIn(a.fuente, false, null, rs ? `Call Wall: ${rs.respetadas ?? 0} rechazos en ${rs.tocadas} toques · Put Wall: ${rev.resumen['Put Wall'].respetadas ?? 0} defensas en ${rev.resumen['Put Wall'].tocadas} toques` : '')}</div>`;
  return h;
}
/* devuelve {html, montar}: montar() dibuja los gráficos cuando el HTML ya está en la página */
/* Fase 19: chip del contraste del spot del oro (solo ORO) con las fuentes en su ⓘ */
function gmSpotFila(x) {
  if (!x.etiqueta || x.clave !== 'GC') return '';
  const c = x.spot_contraste;
  if (!c) return `<tr><td>Spot</td><td><span class="ck sd">SIN CONTRASTE</span></td></tr>`;
  const e = c.estado, cls = e === 'OK' ? 'ok' : e === 'DUDOSO' ? 'no' : 'par';
  const txt = e === 'OK' ? 'spot verificado' : e === 'DUDOSO' ? 'spot dudoso' : e === 'GC_IMPLICITO' ? 'spot = GC implícito' : e === 'SWISSQUOTE' ? 'spot = Swissquote (último recurso)' : e === 'NO_SINCRONIZADO' ? 'spot no sincronizado' : 'spot sin contrastar';
  const ayh = [`Estado: ${e} · umbral ${nf(c.umbral_pct, 1)} % entre fuentes de la misma hora (±5 min).`, c.texto_fuentes || '',
    `Spot usado: ${c.spot_usado} (${c.spot_fuente}) · ratio XAU/GLD: ${c.ratio_fuente === 'ANTERIOR' ? 'NO actualizado hoy, se usa el último OK' : 'de la sesión'}.`, c.nota || ''].filter(Boolean).join('\n');
  return `<tr><td>Spot <button type="button" class="info" data-t="Spot del oro: fuentes" data-ayh="${esc(ayh)}" aria-label="Fuentes del spot del oro" aria-expanded="false">ⓘ</button></td><td><span class="ck ${cls}" title="${esc(c.texto_fuentes || '')}">${esc(txt)}</span></td></tr>`;
}
function gmActivo(a) {
  const { x, rev, err } = gmEntrada(a);
  if (!x) return { html: `<div class="sect"><h2>${esc(a.id)}</h2></div>${noData('Gamma ' + a.id)}${err ? errores({ [a.id]: err }) : ''}`, montar() {} };
  if (x.sin_dato) return { html: `<div class="sect"><h2>${esc(a.id)} · ${esc(x.nombre || '')}</h2><span class="more">${esc(x.etiqueta || '')}</span></div><div class="card"><div class="empty" style="height:auto;padding:24px;white-space:normal">${esc(x.motivo)}</div>${foot(x.fuente || 'Cboe', false, null, 'SIN DATO')}</div>`, montar() {} };
  const C = x.contado || x.indice, F = x.futuro !== undefined ? x.futuro : x.clave, dec = (C === 'XAU' || C === 'GLD') ? 1 : 0, b = x.base || {}, ref = x.etiqueta ? x.etiqueta.replace(', referencia', '') : '';
  const pos = x.regimen === 'POSITIVA', tieneF = F != null && x.spot_fut != null;
  const Ci = (o) => (o ? gmN(o.idx, dec) : '—'), Fu = (o) => (F && o && o.fut != null ? gmN(o.fut, dec) : 'SIN DATO');
  const dist = (o) => (o && x.spot_idx != null ? `${sg(o.idx - x.spot_idx, dec, ' pts')} (${sg((o.idx / x.spot_idx - 1) * 100, 2, ' %')})` : '—');
  const mg = x.max_gamma;
  let h = `<div class="sect"><h2>${esc(a.id)} · ${esc(x.nombre)}</h2><span class="more">${x.etiqueta ? `<span class="tag sin">${esc(x.etiqueta)}</span> ` : ''}sesión ${esc(dmy(x.sesion))} · ${x.cierre_confirmado ? 'cierre de Nueva York' : 'SNAPSHOT INTRADÍA (no es el cierre)'} · ${x.n_vencimientos} vencimientos · ${x.n_grupos} strikes</span></div>`;
  h += gmEsencial(x, C, F, dec, ref);
  h += '<div class="grid g3" style="margin-top:12px">';
  h += `<div class="card kpi"><div class="lab">Precio ${esc(C)}</div><div class="exp">${F ? `Contado en grande · futuro ${esc(F)} debajo` : 'Contado'}</div><div class="big">${gmN(x.spot_idx, 2)}<small> ${esc(C)}</small></div>
    <table><tr><td>Futuro ${esc(F || '')}</td><td>${tieneF ? nf(x.spot_fut, 2) : 'SIN DATO'}</td></tr><tr><td>Base del día</td><td>${b.base != null ? sg(b.base, 2, ' pts') : 'SIN DATO'}</td></tr>${gmSpotFila(x)}<tr><td>Método</td><td style="text-align:right;white-space:normal;font-size:10.5px">${esc(b.metodo || '')}</td></tr></table>${foot(b.fuente || 'Yahoo Finance', x.sesion)}</div>`;
  [['Call Wall', x.call_wall, 'up', 'Mayor gamma de calls por encima del precio'], ['Put Wall', x.put_wall, 'down', 'Mayor gamma de puts por debajo del precio']].forEach(([t, o, cl, ex]) => {
    h += `<div class="card kpi"><div class="lab">${t}</div><div class="exp">${ex}</div><div class="big ${cl}">${Ci(o)}<small> ${esc(C)}</small></div>
      <table><tr><td>Futuro ${esc(F || '')}</td><td>${Fu(o)}</td></tr><tr><td>Distancia</td><td>${dist(o)}</td></tr><tr><td>GEX del tramo</td><td>${o ? gmG(o.musd) : '—'}</td></tr></table>${foot('CRITERIO NEXORA · Cboe', x.sesion)}</div>`;
  });
  h += `<div class="card kpi"><div class="lab">Gamma Flip · régimen</div><div class="exp">Precio donde el GEX neto cambia de signo</div><div class="big amber">${x.flip ? Ci(x.flip) : 'SIN CRUCE'}<small> ${esc(C)}</small></div>
    <table><tr><td>Futuro ${esc(F || '')}</td><td>${x.flip ? Fu(x.flip) : '—'}</td></tr><tr><td>Régimen</td><td><span class="ck ${pos ? 'ok' : 'no'}">GAMMA ${esc(x.regimen)}</span></td></tr><tr><td>GEX neto</td><td>${gmG(x.gex_neto_musd)} / 1 %</td></tr></table>${foot('CRITERIO NEXORA · Cboe', x.sesion)}</div>`;
  h += `<div class="card kpi"><div class="lab">Max Gamma · ${mg ? (mg.tipo === 'pin' ? 'pin' : 'acelera') : 'SIN DATO'}</div><div class="exp">Tramo con más gamma absoluta (calls + |puts|)</div><div class="big" style="color:var(--blue,#6C8EBF)">${Ci(mg)}<small> ${esc(C)}</small></div>
    <table><tr><td>Futuro ${esc(F || '')}</td><td>${Fu(mg)}</td></tr><tr><td>Tipo</td><td>${mg && mg.tipo ? `<span class="ck ${mg.tipo === 'pin' ? 'ok' : 'no'}">${mg.tipo === 'pin' ? 'PIN' : 'ACELERA'}</span>` : '—'}</td></tr><tr><td>GEX neto del tramo</td><td>${mg && mg.neto_musd != null ? (mg.neto_musd > 0 ? '+' : '') + gmG(mg.neto_musd, 2) : '—'}</td></tr></table>
    <div class="note" style="margin:6px 0 0">«Pin» solo si la gamma neta del tramo es positiva (las coberturas frenan el precio contra el nivel); si es negativa, «acelera».</div>${foot('CRITERIO NEXORA · Cboe', x.sesion)}</div>`;
  const em = x.em || {};
  h += `<div class="card kpi"><div class="lab">EM · movimiento esperado de 1 día</div><div class="exp">${esc(em.formula || '')}</div><div class="big">${em.puntos != null ? nf(em.puntos, dec) : 'SIN DATO'}<small> pts</small></div>
    <table><tr><td>Volatilidad</td><td>${em.vol != null ? esc(em.vol_simbolo) + ' ' + nf(em.vol, 1) : 'SIN DATO'}</td></tr><tr><td>En porcentaje</td><td>${em.pct != null ? nf(em.pct, 2) + ' %' : '—'}</td></tr><tr><td>Banda del día</td><td>${em.puntos != null && x.spot_idx != null ? nf(x.spot_idx - em.puntos, dec) + ' – ' + nf(x.spot_idx + em.puntos, dec) : '—'}</td></tr></table>${foot(em.fuente || 'Yahoo Finance', em.vol_fecha || x.sesion)}</div></div>`;
  h += '<div class="grid g21" style="margin-top:12px">';
  h += `<div class="card"><h3>GEX por nivel de precio</h3><div class="sub">Verde = gamma de calls · rojo = gamma de puts · en dólares por cada 1 % de movimiento${x.etiqueta ? ' · calculado con ' + esc(ref) : ''}. Eje en ${esc(F || C)}</div><div style="position:relative;height:320px"><canvas id="gP_${a.id}"></canvas></div>${foot('CRITERIO NEXORA · Cboe (retraso 15 min)', x.sesion)}</div>`;
  h += `<div class="card"><h3>GEX neto según el precio</h3><div class="sub">Recalculado a cada precio hipotético. Por encima del flip: gamma positiva</div><div style="position:relative;height:320px"><canvas id="gC_${a.id}"></canvas></div>${foot('CRITERIO NEXORA · Cboe', x.sesion)}</div></div>`;
  const tb = (t, lst, cl) => `<div class="card pad0 scroll"><table class="t"><thead><tr><th>${t}</th><th>${esc(F || C)}</th><th>${esc(C)}</th><th>GEX / 1 %</th></tr></thead><tbody>${lst.map((r) => `<tr><td>${t === 'Mayores tramos de calls' ? 'Call' : 'Put'}</td><td><b class="${cl}">${F && r.fut != null ? nf(r.fut, dec) : '—'}</b></td><td>${nf(r.idx, dec)}</td><td>${gmG(r.musd, 2)}</td></tr>`).join('')}</tbody></table></div>`;
  h += `<div class="grid g2" style="margin-top:12px">${tb('Mayores tramos de calls', x.top_calls, 'up')}${tb('Mayores tramos de puts', x.top_puts, 'down')}</div>`;
  h += gmHistorial(a, x, rev, C, F, dec);
  if (x.etiqueta) h += `<div class="note">${esc(x.etiqueta)}: no existe una cadena de opciones gratuita del ${esc(C)}; los niveles son los del ETF ${esc(ref)} multiplicados por ${esc(C)}/${esc(ref)} (${x.ratio_contado != null ? nf(x.ratio_contado, 4) : x.ratio && x.ratio.valor != null ? nf(x.ratio.valor, 4) : 'SIN DATO'}${x.ratio && x.ratio.fecha ? ' del ' + esc(dmy(x.ratio.fecha)) : ''}). Es una aproximación.</div>`;
  const niv = [{ v: x.spot_fut ?? x.spot_idx, c: '#E6E8EB', t: 'precio', dash: true, fila: 0 }, { v: x.call_wall && (x.call_wall.fut ?? x.call_wall.idx), c: '#2FA36B', t: 'Call Wall', fila: 1 },
    { v: x.put_wall && (x.put_wall.fut ?? x.put_wall.idx), c: '#C8463D', t: 'Put Wall', fila: 2 }, { v: x.flip && (x.flip.fut ?? x.flip.idx), c: '#C8A24A', t: 'Flip', fila: 3 }];
  const montar = () => {
    if (!window.Chart) return;
    const el = document.getElementById('gP_' + a.id), usaF = F != null && x.spot_fut != null;
    const eje = (p) => Math.round(usaF && p.fut != null ? p.fut : p.k);
    if (el) {
      const P = x.perfil.filter((p) => Math.abs(p.k / x.spot_idx - 1) <= 0.04), pq = Math.max(...P.map((p) => Math.max(p.call, -p.put))) < 1000, dv = pq ? 1 : 1000, un = pq ? 'M $' : 'mm $';
      GM_GRAF.push(new Chart(el, { type: 'bar', plugins: [lineasNivel(niv)], data: { labels: P.map((p) => eje(p)), datasets: [
        { label: 'GEX calls', data: P.map((p) => p.call), backgroundColor: '#2FA36B', stack: 's', maxBarThickness: 12 },
        { label: 'GEX puts', data: P.map((p) => p.put), backgroundColor: '#C8463D', stack: 's', maxBarThickness: 12 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { labels: { color: '#8A93A0', boxWidth: 10, font: { family: 'IBM Plex Mono', size: 10 } } },
        tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${num(c.parsed.y / dv, 2)} ${un}` } } },
      scales: { x: { stacked: true, ticks: { color: '#8A93A0', font: { family: 'IBM Plex Mono', size: 10 }, maxRotation: 0, autoSkip: true, maxTicksLimit: 12 }, grid: { display: false } },
        y: { stacked: true, ticks: { color: '#8A93A0', font: { family: 'IBM Plex Mono', size: 10 }, callback: (v) => num(v / dv, 0) }, grid: { color: '#14181e' }, title: { display: true, text: un + ' por 1 %', color: '#5C6470', font: { size: 10 } } } } } }));
    }
    const e2 = document.getElementById('gC_' + a.id);
    if (e2) {
      const b0 = usaF ? (b.base || 0) : 0;
      const Cv = x.curva.map(([s, g]) => [s + b0, g]), cq = Math.max(...Cv.map((c) => Math.abs(c[1]))) < 1000, dc = cq ? 1 : 1000;
      GM_GRAF.push(new Chart(e2, { type: 'line', plugins: [lineasNivel([niv[0], niv[3]])], data: { labels: Cv.map((c) => Math.round(c[0])), datasets: [{ label: 'GEX neto', data: Cv.map((c) => c[1]), borderColor: '#C8A24A', backgroundColor: 'rgba(200,162,74,.12)', fill: { target: 'origin' }, pointRadius: 0, tension: 0.25, borderWidth: 2 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { title: (i) => `${F || C} ${i[0].label}`, label: (c) => `GEX neto: ${num(c.parsed.y / dc, 1)} ${cq ? 'M $' : 'mm $'}` } } },
          scales: { x: { ticks: { color: '#8A93A0', font: { family: 'IBM Plex Mono', size: 10 }, maxTicksLimit: 9, maxRotation: 0 }, grid: { display: false } },
            y: { ticks: { color: '#8A93A0', font: { family: 'IBM Plex Mono', size: 10 }, callback: (v) => num(v / dc, 0) }, grid: { color: '#14181e' } } } } }));
    }
  };
  return { html: h, montar };
}
/* línea de niveles para TradingView: el MISMO formato que el Telegram de las 15:00 (engine/gamma_intradia.py · linea_niveles) */
function lineaNivelesGamma(G) {
  return ['ES', 'NQ'].map((k) => {
    const x = ((G || {}).indices || {})[k];
    if (!x || !x.flip || x.flip.fut == null) return `${k} flip=na;cw=na;pw=na;em=na;maxg=na;rf=na`;
    const v = (o) => (o && o.fut != null ? Number(o.fut).toFixed(1) : 'na');
    return `${k} flip=${v(x.flip)};cw=${v(x.call_wall)};pw=${v(x.put_wall)};em=${x.em && x.em.puntos != null ? Number(x.em.puntos).toFixed(1) : 'na'};maxg=${v(x.max_gamma)};rf=${x.sesion || 'na'}`;
  }).join(' | ');
}
function plataformasHtml(G) {
  const I = (G && G.indices) || {}, v = (o) => (o && o.fut != null ? nf(o.fut, 1) : 'SIN DATO');
  let h = '<div class="sect"><h2>Niveles para plataformas</h2><span class="more">precios de futuro · NinjaTrader 8 y TradingView</span></div><div class="card pad0 scroll"><table class="t stack"><thead><tr><th style="text-align:left">Índice</th><th>Gamma Flip</th><th>Call Wall</th><th>Put Wall</th><th>Max Gamma</th><th>EM (1 día)</th><th>Sesión de los niveles</th></tr></thead><tbody>';
  h += ['ES', 'NQ'].map((k) => { const x = I[k]; if (!x) return `<tr><td data-label="Índice" style="text-align:left"><b>${k}</b></td><td colspan="6"><span class="sd-val">SIN DATO</span></td></tr>`; const em = x.em || {};
    return `<tr><td data-label="Índice" style="text-align:left"><b>${k}</b></td><td data-label="Gamma Flip">${v(x.flip)}</td><td data-label="Call Wall">${v(x.call_wall)}</td><td data-label="Put Wall">${v(x.put_wall)}</td><td data-label="Max Gamma">${v(x.max_gamma)}</td><td data-label="EM (1 día)">${em.puntos != null ? nf(em.puntos, 1) + ' pts <small>(' + esc(em.vol_simbolo) + ' ' + nf(em.vol, 1) + ')</small>' : 'SIN DATO'}</td><td data-label="Sesión de los niveles">${esc(dmy(x.sesion))}</td></tr>`; }).join('');
  h += `</tbody></table><div class="note" style="padding:8px 16px 4px">Línea para el indicador de TradingView (la misma que llega por Telegram a las 15:00, hora de Madrid):</div><div style="padding:0 16px 8px"><code id="gLinea" style="display:block;white-space:normal;word-break:break-all;padding:8px;border:1px solid var(--line);border-radius:6px">${esc(lineaNivelesGamma(G))}</code>
    <button class="fbtn" id="gCopiar" style="margin-top:6px" type="button">Copiar línea</button> <span class="note" id="gCopiado"></span></div>
    <div class="note" style="padding:0 16px 12px"><b>Avisos intradía de ES y NQ</b> (Telegram, sesión regular, velas de 5 min): cambio de régimen (2 cierres al otro lado del flip), techo en gamma positiva (≤ 0,25 × EM del Call Wall), pérdida del Put Wall en gamma negativa (2 cierres por debajo) y EM agotado (rango del día ≥ 100 % del EM). Máx. 6 al día, sin repetir el mismo en 60 min. Son hechos de precio frente a niveles, <b>contexto y no entradas</b>; su medición (MFE/MAE a 15, 30 y 60 min) está en <a href="#/marcador">Marcador</a>. Los indicadores y su instalación paso a paso: <a class="src" href="https://github.com/komonartisans-ops/nexora-terminal/tree/main/plataformas" target="_blank" rel="noopener">carpeta /plataformas</a>. EM = precio × VIX (ES) o VXN (NQ) / 100 / √252 con la volatilidad del cierre de la sesión de los niveles.</div></div>`;
  MOUNT.push(() => {
    const b = document.getElementById('gCopiar');
    if (b) b.addEventListener('click', async () => {
      const t = document.getElementById('gLinea').textContent, o = document.getElementById('gCopiado');
      try { await navigator.clipboard.writeText(t); o.textContent = 'Copiada.'; } catch (e) { const r = document.createRange(); r.selectNodeContents(document.getElementById('gLinea')); const s = window.getSelection(); s.removeAllRanges(); s.addRange(r); o.textContent = 'Seleccionada: pulsa Ctrl+C.'; }
    });
  });
  return h;
}
/* línea ORO para el indicador «NEXORA Oro» de TradingView (parte del bloque final «Niveles para plataformas») */
function oroLineaHtml(GO) {
  let h = '<div class="card" style="margin-top:12px"><div class="chead"><span>Oro · línea para el indicador «NEXORA Oro» de TradingView</span></div>';
  if (!GO || GO.sin_dato || !GO.linea) return h + '<div class="note">SIN DATO · data/gamma_oro.json</div></div>';
  const r = GO.ratio;
  h += `<div class="note" style="padding:0 0 4px">La misma línea que llega por Telegram a las 15:00 (hora de Madrid), aquí con el evento de la última actualización. Niveles de GLD (referencia) en precio XAU/USD${r ? `, ratio XAU/GLD ${nf(r.valor, 4)} del ${esc(dmy(r.fecha))}${r.exacto ? '' : ' (APROXIMADO)'}` : ', SIN ratio XAU/GLD'}.</div><div><code id="gLineaOro" style="display:block;white-space:normal;word-break:break-all;padding:8px;border:1px solid var(--line);border-radius:6px">${esc(GO.linea)}</code>
    <button class="fbtn" id="gCopiarOro" style="margin-top:6px" type="button">Copiar línea</button> <span class="note" id="gCopiadoOro"></span></div>
    <div class="note">Su medición (¿tocó el oro la zona nivel ± 0,25×EM en la sesión siguiente?) está en <a href="#/marcador">Marcador</a>. ${esc(GO.fuente || '')}.</div></div>`;
  MOUNT.push(() => {
    const b = document.getElementById('gCopiarOro');
    if (b) b.addEventListener('click', async () => {
      const t = document.getElementById('gLineaOro').textContent, o = document.getElementById('gCopiadoOro');
      try { await navigator.clipboard.writeText(t); o.textContent = 'Copiada.'; } catch (e) { const rg = document.createRange(); rg.selectNodeContents(document.getElementById('gLineaOro')); const s = window.getSelection(); s.removeAllRanges(); s.addRange(rg); o.textContent = 'Seleccionada: pulsa Ctrl+C.'; }
    });
  });
  return h;
}
function pageGamma() {
  const G = D.gamma;
  let h = head('Análisis', 'Gamma por activo', 'Dónde están las coberturas de opciones que obligan a los creadores de mercado a comprar o vender: Call Wall, Put Wall, Gamma Flip y Max Gamma de US500 (SPX+SPY → ES), US100 (NDX+QQQ → NQ), US30 (DIA, referencia → DJI y YM) y ORO (GLD, referencia → XAU y GC).',
    `Calculado con las cadenas de opciones de Cboe (retraso de 15 min) tras el cierre de Nueva York · descargado: ${G && G.generado_utc ? esc(horaAct(G.generado_utc)) : 'SIN DATO'} <span class="tag sin" style="margin-left:6px">CRITERIO NEXORA</span>`);
  h += fallo('gamma');
  if (!G || !G.indices) return h + noData('Gamma de índices');
  const I = G.indices, es = I.ES, nq = I.NQ;
  const guardada = lsGet('nexora_gamma_tab', 'US500'), tab0 = GM_ACT.some((a) => a.id === guardada) ? guardada : 'US500';
  h += `<div class="picker" id="gm-tabs" role="tablist" style="margin:0 0 12px;display:flex;gap:6px;flex-wrap:wrap">${GM_ACT.map((a) => `<button class="fbtn ${a.id === tab0 ? 'on' : ''}" role="tab" aria-selected="${a.id === tab0}" data-t="${a.id}">${a.id}</button>`).join('')}</div><div id="gm-root"></div>`;
  if (G.descartados_intradia && Object.keys(G.descartados_intradia).length) h += `<div class="banner amber" style="margin:12px 0;border-radius:6px">Se conserva el último cierre válido: la última descarga fue intradía y no se usa.</div>`;
  const v = (es && es.validacion_gamma) || {};
  const vn = (nq && nq.validacion_gamma) || {};
  h += `<div class="sect"><h2>Método · CRITERIO NEXORA</h2><span class="more">método propio, documentado; no es un dato oficial de ningún proveedor</span></div><div class="card"><div class="note" style="margin-top:0;white-space:pre-line">${esc(G.metodo)}</div>
    <div class="note">US30 y ORO: no hay cadenas de opciones gratuitas del Dow ni del oro al contado, así que se usan las de los ETF DIA y GLD («DIA, referencia», «GLD, referencia») con el mismo método y se convierten con el ratio contado/ETF de la sesión (DJI/DIA y XAU/GLD); el futuro es el nivel de contado más la base del día (YM − DJI, GC − XAU). Con datos insuficientes: SIN DATO.</div>
    <div class="row2"><span>Validación: gamma propia frente a la de Cboe (mediana del error, donde Cboe ≥ 0,002)</span><span class="mono">ES ${v.mediana_error_rel_pct != null ? nf(v.mediana_error_rel_pct, 1) + ' %' : '—'} · NQ ${vn.mediana_error_rel_pct != null ? nf(vn.mediana_error_rel_pct, 1) + ' %' : '—'}</span></div>
    <div class="note">Límites: el interés abierto es el de la víspera (la OCC lo publica cada mañana); las opciones de 0DTE del día no están en el cierre; el signo de la posición de los creadores de mercado es un supuesto; la base cambia con el roll trimestral del futuro.
    Memoria permanente: <a class="src" href="https://github.com/komonartisans-ops/nexora-terminal/blob/main/data/historico_gamma.csv" target="_blank" rel="noopener">data/historico_gamma.csv</a>.</div>
    ${foot(G.fuente, es && es.sesion, G.url)}</div>`;
  h += plataformasHtml(G);
  h += oroLineaHtml(D.gamma_oro);
  MOUNT.push(() => {
    const root = document.getElementById('gm-root'), bar = document.getElementById('gm-tabs');
    if (!root || !bar) return;
    const pintar = (id) => {
      GM_GRAF.forEach((c) => { try { c.destroy(); } catch (e) { /* ya destruido */ } });
      GM_GRAF = [];
      const r = gmActivo(GM_ACT.find((a) => a.id === id) || GM_ACT[0]);
      root.innerHTML = r.html;
      r.montar();
      $$('button', bar).forEach((b) => { const on = b.dataset.t === id; b.classList.toggle('on', on); b.setAttribute('aria-selected', on); });
    };
    bar.addEventListener('click', (e) => { const b = e.target.closest('[data-t]'); if (!b) return; lsSet('nexora_gamma_tab', b.dataset.t); pintar(b.dataset.t); });
    pintar(tab0);
  });
  return h + errores(Object.assign({}, G.errores, G.errores_revision));
}

Object.assign(window.EXTRA_PAGES, { skew: pageSkew, semis: pageSemis, gamma: pageGamma });
