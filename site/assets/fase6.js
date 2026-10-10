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
    h += `<div class="card kpi"><div class="lab">Zona relativa · últimas ${S.ventana_relativa} sesiones <span class="tag sin" style="margin-left:4px">ALERTA</span></div><div class="exp">Percentil del SKEW dentro de su propia ventana reciente (usa la alerta de Telegram)</div>
      <div class="big">p${nf(S.percentil_500, 0)}<small><span class="ck ${ZONA_CLS[zr] || 'sd'}">${esc(zr)}</span></small></div>
      <table><tr><td>Umbral alto (p90)</td><td><b>${nf(S.umbral_alto_500, 1)}</b></td></tr><tr><td>Umbral elevado (p75)</td><td>${nf(S.umbral_elevado_500, 1)}</td></tr><tr><td>Sesiones en la zona</td><td>${S.racha_relativa}</td></tr>
      <tr><td>Avisos en 3 años (relativa · fija)</td><td>${S.avisos_3_anos ? S.avisos_3_anos.relativa + ' · ' + S.avisos_3_anos.fija : '—'}</td></tr></table>
      ${foot('Cálculo NEXORA sobre Cboe · SKEW', S.fecha, S.url)}</div>`;
  }
  conf.forEach((c) => {
    const cls = c.encendida === true ? 'no' : c.encendida === false ? 'ok' : 'sd';
    h += `<div class="card kpi"><div class="lab">${esc(c.nombre)}</div><div class="exp">${c.encendida === true ? 'ENCENDIDA' : c.encendida === false ? 'APAGADA' : 'SIN DATO'}</div>
      <div style="margin:6px 0"><span class="ck ${cls}">${esc(c.estado)}</span></div><div class="note" style="margin:0 0 6px">${esc(c.valor)}</div><div class="note" style="margin:0;color:var(--dim)">${esc(c.regla)}</div>
      ${c.retraso_dias > 21 ? `<div class="note" style="margin:6px 0 0;color:var(--amber)">Dato con ${c.retraso_dias} días de retraso (publicación de la fuente).</div>` : ''}
      ${foot(c.fuente, c.fecha, c.url && c.url.startsWith('http') ? c.url : null)}</div>`;
  });
  h += '</div>';

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
  h += `<div class="note">${esc(S.metodo)} Memoria permanente: <a class="src" href="https://github.com/komonartisans-ops/nexora-terminal/blob/main/data/historico_skew.csv" target="_blank" rel="noopener">data/historico_skew.csv</a>. Alerta de Telegram: una por episodio de zona alta relativa (percentil ≥ 90 de las últimas 500 sesiones).</div>`;
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
function gammaBloque(k, x, fecha) {
  const b = x.base || {};
  const F = (o) => (o && o.fut != null ? nf(o.fut, 0) : '—');
  const Iv = (o) => (o ? nf(o.idx, 0) : '—');
  const pos = x.regimen === 'POSITIVA';
  const dist = (o) => (o && x.spot_fut != null && o.fut != null ? `${sg(o.fut - x.spot_fut, 0, ' pts')} (${sg((o.fut / x.spot_fut - 1) * 100, 2, ' %')})` : '');
  let h = `<div class="sect"><h2>${esc(x.nombre)}</h2><span class="more">sesión ${esc(dmy(x.sesion))} · ${x.cierre_confirmado ? 'cierre de Nueva York' : 'SNAPSHOT INTRADÍA (no es el cierre)'} · ${x.n_vencimientos} vencimientos · ${x.n_grupos} strikes</span></div>`;
  h += '<div class="grid g4">';
  h += `<div class="card kpi"><div class="lab">Precio del futuro ${k}</div><div class="exp">${esc(x.indice)} ${nf(x.spot_idx, 2)} + base</div><div class="big">${x.spot_fut != null ? nf(x.spot_fut, 2) : SD}</div>
    <table><tr><td>Base del día</td><td>${b.base != null ? sg(b.base, 2, ' pts') : 'SIN DATO'}</td></tr><tr><td>Método</td><td style="text-align:right;white-space:normal;font-size:10.5px">${esc(b.metodo || '')}</td></tr></table>${foot(b.fuente || 'Yahoo Finance', x.sesion)}</div>`;
  h += `<div class="card kpi"><div class="lab">Call Wall</div><div class="exp">Mayor gamma de calls por encima del precio</div><div class="big up">${F(x.call_wall)}<small> ${k}</small></div>
    <table><tr><td>En el índice</td><td>${Iv(x.call_wall)}</td></tr><tr><td>Distancia</td><td>${dist(x.call_wall)}</td></tr><tr><td>GEX del tramo</td><td>${x.call_wall ? nf(x.call_wall.musd / 1000, 1) + ' mm $' : '—'}</td></tr></table>${foot('CRITERIO NEXORA · Cboe', x.sesion)}</div>`;
  h += `<div class="card kpi"><div class="lab">Put Wall</div><div class="exp">Mayor gamma de puts por debajo del precio</div><div class="big down">${F(x.put_wall)}<small> ${k}</small></div>
    <table><tr><td>En el índice</td><td>${Iv(x.put_wall)}</td></tr><tr><td>Distancia</td><td>${dist(x.put_wall)}</td></tr><tr><td>GEX del tramo</td><td>${x.put_wall ? nf(x.put_wall.musd / 1000, 1) + ' mm $' : '—'}</td></tr></table>${foot('CRITERIO NEXORA · Cboe', x.sesion)}</div>`;
  h += `<div class="card kpi"><div class="lab">Gamma Flip · régimen</div><div class="exp">Precio donde el GEX neto cambia de signo</div><div class="big amber">${x.flip ? F(x.flip) : 'SIN CRUCE'}<small> ${k}</small></div>
    <table><tr><td>Régimen</td><td><span class="ck ${pos ? 'ok' : 'no'}">GAMMA ${esc(x.regimen)}</span></td></tr><tr><td>En el índice</td><td>${x.flip ? Iv(x.flip) : '—'}</td></tr><tr><td>GEX neto</td><td>${nf(x.gex_neto_musd / 1000, 1)} mm $ / 1 %</td></tr></table>${foot('CRITERIO NEXORA · Cboe', x.sesion)}</div></div>`;
  const eje = (p) => Math.round(p.fut != null ? p.fut : p.k);
  const niv = [{ v: x.spot_fut ?? x.spot_idx, c: '#E6E8EB', t: 'precio', dash: true, fila: 0 }, { v: x.call_wall && (x.call_wall.fut ?? x.call_wall.idx), c: '#2FA36B', t: 'Call Wall', fila: 1 },
    { v: x.put_wall && (x.put_wall.fut ?? x.put_wall.idx), c: '#C8463D', t: 'Put Wall', fila: 2 }, { v: x.flip && (x.flip.fut ?? x.flip.idx), c: '#C8A24A', t: 'Flip', fila: 3 }];
  MOUNT.push(() => {
    if (!window.Chart) return;
    const el = document.getElementById('gP_' + k);
    if (el) {
      const P = x.perfil.filter((p) => Math.abs(p.k / x.spot_idx - 1) <= 0.04);
      new Chart(el, { type: 'bar', plugins: [lineasNivel(niv)], data: { labels: P.map((p) => eje(p)), datasets: [
        { label: 'GEX calls', data: P.map((p) => p.call), backgroundColor: '#2FA36B', stack: 's', maxBarThickness: 12 },
        { label: 'GEX puts', data: P.map((p) => p.put), backgroundColor: '#C8463D', stack: 's', maxBarThickness: 12 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { labels: { color: '#8A93A0', boxWidth: 10, font: { family: 'IBM Plex Mono', size: 10 } } },
        tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${num(c.parsed.y / 1000, 2)} mm $` } } },
      scales: { x: { stacked: true, ticks: { color: '#8A93A0', font: { family: 'IBM Plex Mono', size: 10 }, maxRotation: 0, autoSkip: true, maxTicksLimit: 12 }, grid: { display: false } },
        y: { stacked: true, ticks: { color: '#8A93A0', font: { family: 'IBM Plex Mono', size: 10 }, callback: (v) => num(v / 1000, 0) }, grid: { color: '#14181e' }, title: { display: true, text: 'mm $ por 1 %', color: '#5C6470', font: { size: 10 } } } } } });
    }
    const e2 = document.getElementById('gC_' + k);
    if (e2) {
      const b0 = (x.base && x.base.base) || 0;
      const C = x.curva.map(([s, g]) => [s + b0, g]);
      new Chart(e2, { type: 'line', plugins: [lineasNivel([niv[0], niv[3]])], data: { labels: C.map((c) => Math.round(c[0])), datasets: [{ label: 'GEX neto', data: C.map((c) => c[1]), borderColor: '#C8A24A', backgroundColor: 'rgba(200,162,74,.12)', fill: { target: 'origin' }, pointRadius: 0, tension: 0.25, borderWidth: 2 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { title: (i) => `${k} ${i[0].label}`, label: (c) => `GEX neto: ${num(c.parsed.y / 1000, 1)} mm $` } } },
          scales: { x: { ticks: { color: '#8A93A0', font: { family: 'IBM Plex Mono', size: 10 }, maxTicksLimit: 9, maxRotation: 0 }, grid: { display: false } },
            y: { ticks: { color: '#8A93A0', font: { family: 'IBM Plex Mono', size: 10 }, callback: (v) => num(v / 1000, 0) }, grid: { color: '#14181e' } } } } });
    }
  });
  h += '<div class="grid g21" style="margin-top:12px">';
  h += `<div class="card"><h3>GEX por nivel de precio del futuro</h3><div class="sub">Verde = gamma de calls · rojo = gamma de puts · en mm $ por cada 1 % de movimiento (SPX+SPY / NDX+QQQ sumados)</div><div style="position:relative;height:320px"><canvas id="gP_${k}"></canvas></div>${foot('CRITERIO NEXORA · Cboe (retraso 15 min)', x.sesion)}</div>`;
  h += `<div class="card"><h3>GEX neto según el precio</h3><div class="sub">Recalculado a cada precio hipotético. Por encima del flip: gamma positiva</div><div style="position:relative;height:320px"><canvas id="gC_${k}"></canvas></div>${foot('CRITERIO NEXORA · Cboe', x.sesion)}</div></div>`;
  h += `<div class="grid g2" style="margin-top:12px"><div class="card pad0 scroll"><table class="t"><thead><tr><th>Mayores tramos de calls</th><th>${k}</th><th>Índice</th><th>mm $</th></tr></thead><tbody>${x.top_calls.map((t) => `<tr><td>Call</td><td><b class="up">${t.fut != null ? nf(t.fut, 0) : '—'}</b></td><td>${nf(t.idx, 0)}</td><td>${nf(t.musd / 1000, 2)}</td></tr>`).join('')}</tbody></table></div>
    <div class="card pad0 scroll"><table class="t"><thead><tr><th>Mayores tramos de puts</th><th>${k}</th><th>Índice</th><th>mm $</th></tr></thead><tbody>${x.top_puts.map((t) => `<tr><td>Put</td><td><b class="down">${t.fut != null ? nf(t.fut, 0) : '—'}</b></td><td>${nf(t.idx, 0)}</td><td>${nf(t.musd / 1000, 2)}</td></tr>`).join('')}</tbody></table></div></div>`;
  return h;
}
function revisionHtml(G) {
  const R = G.revision || {};
  let h = '<div class="sect"><h2>Cómo reaccionó el futuro en cada nivel</h2><span class="more">cada sesión guardada frente a la barra del futuro de la sesión siguiente</span></div>';
  h += `<div class="note" style="margin-top:0">Histórico propio: ${G.sesiones_guardadas || 0} ${G.sesiones_guardadas === 1 ? 'sesión guardada' : 'sesiones guardadas'} (el histórico empieza con este módulo: no hay cadenas de opciones gratuitas anteriores, no se reconstruye). Se evalúa sesión a sesión; se excluyen las ventanas de vencimiento trimestral del futuro.</div>`;
  const col = { RECHAZADO: 'ok', DEFENDIDO: 'ok', SUPERADO: 'no', ROTO: 'no', 'NO TOCADO': 'sd', 'CERRÓ POR ENCIMA': 'par', 'CERRÓ POR DEBAJO': 'par' };
  ['ES', 'NQ'].forEach((k) => {
    const r = R[k];
    h += `<div class="card pad0 scroll" style="margin-bottom:12px"><table class="t"><thead><tr><th>${k} · sesión</th><th>Estado</th><th>Call Wall</th><th>Put Wall</th><th>Gamma Flip</th><th>Sesión siguiente (máx · mín · cierre)</th></tr></thead><tbody>`;
    if (!r || r.sin_dato || !r.sesiones.length) h += '<tr><td colspan="6" style="text-align:left;color:var(--dim)">SIN DATO: todavía no hay sesiones guardadas o la fuente no respondió.</td></tr>';
    else h += r.sesiones.slice(0, 20).map((s) => {
      const c = (n) => { const v = s.niveles && s.niveles[n]; return v ? `<span class="ck ${col[v.resultado] || 'sd'}">${esc(v.resultado)}</span><small>${nf(v.nivel, 0)} · cierre ${sg(v.dist_cierre, 0)}</small>` : '—'; };
      const sig = s.sesion_siguiente;
      return `<tr><td>${esc(dmy(s.fecha_sesion))}</td><td><span class="ck ${s.estado === 'EVALUADA' ? 'ok' : s.estado === 'ROLL' ? 'par' : 'sd'}">${esc(s.estado)}</span></td><td>${c('Call Wall')}</td><td>${c('Put Wall')}</td><td>${c('Gamma Flip')}</td>
        <td>${sig ? `${esc(fd(sig.fecha))}: ${nf(sig.h, 0)} · ${nf(sig.l, 0)} · ${nf(sig.c, 0)}` : esc(s.nota || 'esperando la sesión siguiente')}</td></tr>`;
    }).join('');
    const rs = r && r.resumen;
    h += `</tbody></table>${footIn('Yahoo Finance (' + (k === 'ES' ? 'ES=F' : 'NQ=F') + ') · data/historico_gamma.csv', false, null, rs ? `Call Wall: ${rs['Call Wall'].respetadas ?? 0} rechazos en ${rs['Call Wall'].tocadas} toques · Put Wall: ${rs['Put Wall'].respetadas ?? 0} defensas en ${rs['Put Wall'].tocadas} toques` : '')}</div>`;
  });
  return h;
}
function pageGamma() {
  const G = D.gamma;
  let h = head('Análisis', 'Gamma de índices', 'Dónde están las coberturas de opciones que obligan a los creadores de mercado a comprar o vender: Call Wall, Put Wall y Gamma Flip de SPX+SPY (ES) y NDX+QQQ (NQ), convertidos a precio del futuro con la base del día.',
    `Calculado con la cadena de opciones de Cboe (retraso de 15 min) tras el cierre de Nueva York · descargado: ${G && G.generado_utc ? esc(horaAct(G.generado_utc)) : 'SIN DATO'} <span class="tag sin" style="margin-left:6px">CRITERIO NEXORA</span>`);
  h += fallo('gamma');
  if (!G || !G.indices) return h + noData('Gamma de índices');
  const I = G.indices, es = I.ES, nq = I.NQ;
  const un = (x) => (x ? x.resumen_texto : 'SIN DATO');
  h += essential(`${esc(un(es))}. ${nq ? 'NQ: ' + esc(un(nq)) + '.' : ''}`,
    `Hipótesis (no hecho): con gamma positiva, las coberturas de los creadores de mercado tienden a frenar los movimientos (venden en subidas, compran en bajadas); con gamma negativa los amplifican. Esto depende de suponer que los clientes están largos de puts y los creadores largos de calls: el interés abierto no revela quién está de cada lado. Sesión ${es ? esc(dmy(es.sesion)) : ''}.`,
    'Los muros son más fiables cerca de vencimientos y con el precio próximo; un cierre firme más allá del Call Wall o por debajo del Put Wall invalida el nivel. Se recalcula en cada cierre de Nueva York (21:30 UTC).');
  if (G.descartados_intradia && Object.keys(G.descartados_intradia).length) h += `<div class="banner amber" style="margin:0 0 12px;border-radius:6px">Se conserva el último cierre válido: la última descarga fue intradía y no se usa.</div>`;
  ['ES', 'NQ'].forEach((k) => { if (I[k]) h += gammaBloque(k, I[k], G.generado_utc); else h += `<div class="sect"><h2>${k}</h2></div>${noData('Gamma ' + k)}`; });
  h += revisionHtml(G);
  const v = (es && es.validacion_gamma) || {};
  const vn = (nq && nq.validacion_gamma) || {};
  h += `<div class="sect"><h2>Método · CRITERIO NEXORA</h2><span class="more">método propio, documentado; no es un dato oficial de ningún proveedor</span></div><div class="card"><div class="note" style="margin-top:0;white-space:pre-line">${esc(G.metodo)}</div>
    <div class="row2"><span>Validación: gamma propia frente a la de Cboe (mediana del error, donde Cboe ≥ 0,002)</span><span class="mono">ES ${v.mediana_error_rel_pct != null ? nf(v.mediana_error_rel_pct, 1) + ' %' : '—'} · NQ ${vn.mediana_error_rel_pct != null ? nf(vn.mediana_error_rel_pct, 1) + ' %' : '—'}</span></div>
    <div class="note">Límites: el interés abierto es el de la víspera (la OCC lo publica cada mañana); las opciones de 0DTE del día no están en el cierre; el signo de la posición de los creadores de mercado es un supuesto; la base cambia con el roll trimestral del futuro.
    Memoria permanente: <a class="src" href="https://github.com/komonartisans-ops/nexora-terminal/blob/main/data/historico_gamma.csv" target="_blank" rel="noopener">data/historico_gamma.csv</a>.</div>
    ${foot(G.fuente, es && es.sesion, G.url)}</div>`;
  return h + errores(Object.assign({}, G.errores, G.errores_revision));
}

Object.assign(window.EXTRA_PAGES, { skew: pageSkew, semis: pageSemis, gamma: pageGamma });
