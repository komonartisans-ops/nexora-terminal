/* NEXORA TERMINAL · fase 5: Diario de operaciones, Watchlists, Registro de tesis y bloque «Contradicciones» del Resumen.
   Se carga después de app.js, mercados.js y fase4.js y reutiliza sus helpers.
   PRIVACIDAD: el diario y las watchlists viven en el localStorage del navegador (el repo es público, nada se sube a él).
   El diario puede, además, sincronizarse con el repo PRIVADO nexora-diario si pegas un token (ver diario_sync.js).
   Todo texto dinámico (incluido lo que escribe el usuario) pasa por esc() antes de entrar en el HTML. */
'use strict';

/* ------------------------------------------------------------------ utilidades de la fase */
const MESES_L = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
const f5 = {
  uid: () => Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
  mean: (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : null),
  usd: (v, d = 2) => (v == null ? '—' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${num(Math.abs(v), d)} $`),
  cls: (v) => (v > 0 ? 'up' : v < 0 ? 'down' : 'flat'),
  /* repinta un contenedor con HTML (ya escapado) que usa lw()/barras(): ejecuta los montajes pendientes */
  paint(el, build) { MOUNT.length = 0; const html = build(); el.innerHTML = html; MOUNT.splice(0).forEach((f) => { try { f(); } catch (e) { console.error(e); } }); },
  descarga(nombre, texto, tipo) {
    try {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([texto], { type: tipo }));
      a.download = nombre; document.body.appendChild(a); a.click(); a.remove();
    } catch (e) { alert('No se pudo generar el archivo: ' + e.message); }
  },
  csvCelda: (v) => `"${String(v ?? '').replace(/"/g, '""')}"`,
};

/* ================================================================== CONTRADICCIONES (Resumen) */
/* Tres lecturas de «dirección de riesgo» con reglas fijas y documentadas. +1 = apetito de riesgo, −1 = aversión, 0 = sin lectura.
   Crédito: CCC o HY por encima de los umbrales de ciclo.py (5 d o 1 m) = TENSIÓN (−1); si no, SIN TENSIÓN (+1).
   Divisas: media del sesgo total de AUD, NZD, CAD (cíclicas) menos la de JPY, CHF (refugio): ≥ +2 apetito, ≤ −2 aversión.
   COT: percentil a 3 años del neto no comercial: media de AUD, NZD, CAD, S&P, Nasdaq, Russell menos media de JPY, CHF: ≥ +15 apetito, ≤ −15 aversión. */
const CICLICAS = ['AUD', 'NZD', 'CAD'], REFUGIO = ['JPY', 'CHF'];
const COT_RIESGO = ['aud', 'nzd', 'cad', 'spx', 'ndx', 'rut'], COT_REFUGIO = ['jpy', 'chf'];
const DIRTXT = { 1: 'APETITO DE RIESGO', '-1': 'AVERSIÓN AL RIESGO', 0: 'SIN LECTURA' };

function senalCredito() {
  const C = D.ciclo;
  if (!C || !C.credito) return null;
  const U = C.umb_cred || {}, cr = C.credito;
  const t = (k) => {
    const m = cr[k], u = U[k] || [];
    if (!m) return null;
    const d5 = m['5d_pb'] ?? m.d5_pb;
    return { m, d5, d1m: m['1m_pb'], on5: d5 != null && u[0] != null && d5 >= u[0], on1m: m['1m_pb'] != null && u[1] != null && m['1m_pb'] >= u[1], u };
  };
  const ccc = t('ccc'), hy = t('hy');
  if (!ccc && !hy) return null;
  const tension = [ccc, hy].some((x) => x && (x.on5 || x.on1m));
  const fecha = (ccc || hy).m.fecha;
  return { dir: tension ? -1 : 1, etiqueta: tension ? 'TENSIÓN' : 'SIN TENSIÓN', ccc, hy, fecha, serie: C.series && C.series.oas && C.series.oas.ccc,
    texto: tension ? 'CCC o high yield superan su umbral de alerta (5 días o 1 mes).' : 'Ni CCC ni high yield superan su umbral de alerta.' };
}
function senalDivisas() {
  const V = D.divisas;
  if (!V || !V.monedas) return null;
  const tot = (k) => { const m = V.monedas.find((x) => x.clave === k); return m && m.total != null ? m.total : null; };
  const c = CICLICAS.map(tot).filter((x) => x != null), r = REFUGIO.map(tot).filter((x) => x != null);
  if (!c.length || !r.length) return null;
  const mc = f5.mean(c), mr = f5.mean(r), spread = mc - mr;
  const dir = spread >= 2 ? 1 : spread <= -2 ? -1 : 0;
  return { dir, etiqueta: dir > 0 ? 'APETITO' : dir < 0 ? 'AVERSIÓN' : 'NEUTRAL', mc, mr, spread, vix: V.riesgo && V.riesgo.vix, regimen: V.riesgo && V.riesgo.regimen,
    fecha: V.generado_utc, texto: 'Sesgo macro de las divisas cíclicas frente a las refugio.' };
}
function senalCot() {
  const C = D.cot;
  if (!C || !C.contratos) return null;
  const p = (k) => { const c = C.contratos.find((x) => x.clave === k); return c && c.no_comerciales && c.no_comerciales.percentil_3a != null ? c.no_comerciales.percentil_3a : null; };
  const a = COT_RIESGO.map(p).filter((x) => x != null), b = COT_REFUGIO.map(p).filter((x) => x != null);
  if (!a.length || !b.length) return null;
  const pr = f5.mean(a), ph = f5.mean(b), diff = pr - ph;
  const dir = diff >= 15 ? 1 : diff <= -15 ? -1 : 0;
  return { dir, etiqueta: dir > 0 ? 'APETITO' : dir < 0 ? 'AVERSIÓN' : 'NEUTRAL', pr, ph, diff, n: a.length + b.length, fecha: C.fecha_informe,
    texto: 'Percentil del neto no comercial en activos de riesgo frente a refugio.' };
}
function veredictoPar(a, b, nom) {
  if (!a || !b) return { k: 'sd', et: 'SIN DATO', nom, txt: 'Falta una de las dos lecturas: no se compara ni se estima.' };
  if (a.dir === 0 || b.dir === 0) return { k: 'par', et: 'SIN LECTURA CLARA', nom, txt: 'Una de las dos lecturas es neutral, así que no hay contradicción que señalar.' };
  if (a.dir === b.dir) return { k: 'ok', et: 'COINCIDEN', nom, txt: `Las dos apuntan al mismo lado: ${DIRTXT[a.dir].toLowerCase()}.` };
  return { k: 'no', et: 'CONTRADICCIÓN', nom, txt: `El crédito apunta a ${DIRTXT[a.dir].toLowerCase()} y la otra lectura a ${DIRTXT[b.dir].toLowerCase()}.` };
}
function bloqueContradicciones() {
  const cr = senalCredito(), fx = senalDivisas(), cot = senalCot();
  const v1 = veredictoPar(cr, fx, 'Crédito frente a divisas'), v2 = veredictoPar(cr, cot, 'Crédito frente a COT');
  const flecha = (s) => (!s ? '<span class="sd-val">SIN DATO</span>' : `<span class="${s.dir > 0 ? 'up' : s.dir < 0 ? 'down' : 'flat'}">${s.dir > 0 ? '▲' : s.dir < 0 ? '▼' : '▬'} ${esc(s.etiqueta)}</span>`);
  const hay = v1.k === 'no' || v2.k === 'no';
  const cCr = !cr ? `<div class="card sig nd"><div class="top"><div class="nm">Crédito · CCC y HY</div></div><div class="big">${SD}</div>${foot('ICE BofA vía FRED', null)}</div>`
    : `<div class="card sig ${cr.dir < 0 ? 'on' : 'off'}"><div class="top"><div class="nm">Crédito · CCC y HY</div><span class="ck ${cr.dir < 0 ? 'no' : 'ok'}">${esc(cr.etiqueta)}</span></div>
      <div class="big">${flecha(cr)}</div><div class="note" style="margin:2px 0 6px">${esc(cr.texto)}</div>
      <table class="mini"><tr><th>Tramo</th><th>Nivel</th><th>5 d · 1 m</th></tr>
      ${cr.ccc ? `<tr><td>CCC</td><td>${num(cr.ccc.m.pb, 0)} pb</td><td>${sg(cr.ccc.d5, 0)} · ${sg(cr.ccc.d1m, 0)}</td></tr>` : ''}
      ${cr.hy ? `<tr><td>HY</td><td>${num(cr.hy.m.pb, 0)} pb</td><td>${sg(cr.hy.d5, 0)} · ${sg(cr.hy.d1m, 0)}</td></tr>` : ''}</table>
      ${cr.serie ? spark(cr.serie, 126) : ''}${foot('ICE BofA vía FRED · umbrales de ciclo.py', cr.fecha)}</div>`;
  const cFx = !fx ? `<div class="card sig nd"><div class="top"><div class="nm">Sesgo de divisas</div></div><div class="big">${SD}</div>${foot('Matriz NEXORA de divisas', null)}</div>`
    : `<div class="card sig ${fx.dir < 0 ? 'on' : fx.dir > 0 ? 'off' : 'nd'}"><div class="top"><div class="nm">Sesgo de divisas</div><span class="ck ${fx.dir < 0 ? 'no' : fx.dir > 0 ? 'ok' : 'par'}">${esc(fx.etiqueta)}</span></div>
      <div class="big">${flecha(fx)}</div><div class="note" style="margin:2px 0 6px">${esc(fx.texto)}</div>
      <table class="mini"><tr><th>Grupo</th><th>Sesgo medio</th><th>Regla</th></tr>
      <tr><td>Cíclicas (${CICLICAS.join(', ')})</td><td>${sg(fx.mc, 1)}</td><td></td></tr>
      <tr><td>Refugio (${REFUGIO.join(', ')})</td><td>${sg(fx.mr, 1)}</td><td></td></tr>
      <tr><td>Diferencia</td><td><b>${sg(fx.spread, 1)}</b></td><td>≥ +2 / ≤ −2</td></tr></table>
      <div class="note">Régimen de riesgo del propio cálculo: ${fx.regimen ? esc(fx.regimen) + ' · VIX ' + num(fx.vix, 1) : 'SIN DATO'}.</div>
      <div class="foot"><span>Fuente: <a href="#/divisas">Matriz NEXORA de divisas</a></span><span>calculado ${esc(horaAct(fx.fecha))}</span></div></div>`;
  const cCot = !cot ? `<div class="card sig nd"><div class="top"><div class="nm">Posicionamiento COT</div></div><div class="big">${SD}</div>${foot('CFTC · COT', null)}</div>`
    : `<div class="card sig ${cot.dir < 0 ? 'on' : cot.dir > 0 ? 'off' : 'nd'}"><div class="top"><div class="nm">Posicionamiento COT</div><span class="ck ${cot.dir < 0 ? 'no' : cot.dir > 0 ? 'ok' : 'par'}">${esc(cot.etiqueta)}</span></div>
      <div class="big">${flecha(cot)}</div><div class="note" style="margin:2px 0 6px">${esc(cot.texto)}</div>
      <table class="mini"><tr><th>Grupo</th><th>Percentil medio 3a</th><th>Regla</th></tr>
      <tr><td>Riesgo (AUD, NZD, CAD, S&amp;P, Nasdaq, Russell)</td><td>p${num(cot.pr, 0)}</td><td></td></tr>
      <tr><td>Refugio (JPY, CHF)</td><td>p${num(cot.ph, 0)}</td><td></td></tr>
      <tr><td>Diferencia</td><td><b>${sg(cot.diff, 0)}</b></td><td>≥ +15 / ≤ −15</td></tr></table>
      ${foot('CFTC · COT (Legacy, no comerciales)', cot.fecha, 'https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm', 'informe del martes')}</div>`;
  const vcard = (v) => `<div class="card verdict ${v.k}"><div class="eb">${esc(v.nom)}</div><div class="top"><span class="ck ${v.k}">${esc(v.et)}</span></div><p>${esc(v.txt)}</p></div>`;
  let lectura;
  if (hay) {
    const con = v1.k === 'no' && v2.k === 'no' ? 'las divisas y el posicionamiento COT' : v1.k === 'no' ? 'el sesgo de divisas' : 'el posicionamiento COT';
    lectura = `<p><b>Hecho</b>El crédito de riesgo y ${con} apuntan en direcciones opuestas (reglas y umbrales en cada tarjeta).</p>
      <p><b>Interpretación</b>Cuando dos termómetros de riesgo discrepan, uno de los dos va por delante del otro. El crédito suele reaccionar antes cuando hay estrés en las empresas más frágiles; divisas y COT se mueven con más lentitud (COT es semanal y con retraso).</p>
      <p><b>Escenario a vigilar</b>Convergencia a la baja: divisas y COT acaban reflejando la tensión del crédito. Convergencia al alza: el CCC se estrecha y la señal de crédito pierde fuerza. Es contexto, no una señal de compra o venta.</p>`;
  } else if ([v1, v2].some((v) => v.k === 'sd')) {
    lectura = '<p><b>Hecho</b>Falta alguna de las lecturas, así que la comparación queda incompleta. No se estima el dato que falta.</p>';
  } else {
    lectura = '<p><b>Hecho</b>Crédito, divisas y posicionamiento no apuntan en direcciones opuestas con las reglas actuales.</p><p><b>Interpretación</b>Sin discrepancia entre termómetros no hay señal de que uno vaya por delante del otro. Un cambio de signo en cualquiera de los tres reabriría la comparación.</p>';
  }
  return `<div class="sect"><h2>Contradicciones</h2><span class="more">crédito (CCC/HY) frente a sesgo de divisas y posicionamiento COT · ▲ apetito de riesgo · ▼ aversión</span></div>
    <div class="contra ${hay ? 'hay' : ''}"><div class="grid g3 stretch">${cCr}${cFx}${cCot}</div>
    <div class="grid g3 stretch" style="margin-top:12px">${vcard(v1)}${vcard(v2)}<div class="card contra-txt">${lectura}</div></div></div>`;
}

/* ================================================================== DIARIO DE OPERACIONES */
const DK = 'nexora.diario.v1';
const diario = { mes: null, dia: null, st: null };
const dLoad = () => { const s = lsGet(DK, null); return DSYNC.norm(s && Array.isArray(s.trades) ? s : null); };
/* guarda en local y avisa a la sincronización con GitHub (pend = 'replace' tras importar) */
const dSave = (pend) => { lsSet(DK, diario.st); DSYNC.cambio(pend); };
const diarioFuente = () => (DSYNC.conectado() ? 'Tu diario (navegador + repo privado nexora-diario)' : 'Tu diario (localStorage del navegador)');
const ymd = (y, m, d) => `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
const ACT_BASE = ['Oro', 'Bitcoin', 'S&P 500', 'Nasdaq 100', 'US30', 'Russell 2000', 'EUR/USD', 'USD/JPY', 'Otro'];

function diarioStats(trs) {
  const n = trs.length, g = trs.filter((t) => t.pnl > 0), p = trs.filter((t) => t.pnl < 0);
  const tot = trs.reduce((a, t) => a + t.pnl, 0);
  const bruto = g.reduce((a, t) => a + t.pnl, 0), perd = -p.reduce((a, t) => a + t.pnl, 0);
  return { n, g: g.length, p: p.length, tot, win: n ? g.length / n * 100 : null, pf: perd > 0 ? bruto / perd : null, medG: g.length ? bruto / g.length : null, medP: p.length ? -perd / p.length : null };
}
function diarioHtml() {
  const S = diario.st, [Y, M] = diario.mes;
  const pref = `${Y}-${String(M + 1).padStart(2, '0')}`;
  const mesTr = S.trades.filter((t) => t.fecha.startsWith(pref));
  const st = diarioStats(mesTr), all = diarioStats(S.trades);
  const porDia = {};
  mesTr.forEach((t) => { (porDia[t.fecha] = porDia[t.fecha] || []).push(t); });
  const hoy = hoyISO();
  const primero = new Date(Date.UTC(Y, M, 1)), nd = new Date(Date.UTC(Y, M + 1, 0)).getUTCDate();
  const off = (primero.getUTCDay() + 6) % 7;
  const celdas = [];
  for (let i = 0; i < off; i++) celdas.push(null);
  for (let d = 1; d <= nd; d++) celdas.push(d);
  while (celdas.length % 7) celdas.push(null);
  let cal = '<div class="jcal"><div class="jh">Lun</div><div class="jh">Mar</div><div class="jh">Mié</div><div class="jh">Jue</div><div class="jh">Vie</div><div class="jh we">Sáb</div><div class="jh we">Dom</div><div class="jh sem">Semana</div>';
  for (let w = 0; w < celdas.length / 7; w++) {
    let semPnl = 0, semN = 0;
    for (let c = 0; c < 7; c++) {
      const d = celdas[w * 7 + c];
      if (d == null) { cal += '<div class="jd vacio"></div>'; continue; }
      const f = ymd(Y, M, d), ts = porDia[f] || [], pnl = ts.reduce((a, t) => a + t.pnl, 0);
      semPnl += pnl; semN += ts.length;
      const cls = ts.length ? (pnl > 0 ? 'win' : pnl < 0 ? 'loss' : 'be') : '';
      cal += `<button class="jd ${cls} ${f === hoy ? 'hoy' : ''} ${f === diario.dia ? 'sel' : ''} ${c > 4 ? 'we' : ''}" data-dia="${f}"><span class="n">${d}</span>${S.notas[f] ? '<i class="nota" title="Tiene nota"></i>' : ''}${ts.length ? `<span class="p mono">${f5.usd(pnl, 0)}</span><span class="o">${ts.length} op.</span>` : ''}</button>`;
    }
    cal += `<div class="jd sem ${semN ? (semPnl > 0 ? 'win' : semPnl < 0 ? 'loss' : 'be') : ''}"><span class="o">Sem. ${w + 1}</span>${semN ? `<span class="p mono">${f5.usd(semPnl, 0)}</span><span class="o">${semN} op.</span>` : '<span class="o">—</span>'}</div>`;
  }
  cal += '</div>';
  /* serie acumulada y diaria */
  const fechas = [...new Set(S.trades.map((t) => t.fecha))].sort();
  let acc = 0;
  const cum = fechas.map((f) => { acc += S.trades.filter((t) => t.fecha === f).reduce((a, t) => a + t.pnl, 0); return [f, +acc.toFixed(2)]; });
  const diasMes = fechas.filter((f) => f.startsWith(pref));
  const act = diario.dia || hoy;
  const delDia = S.trades.filter((t) => t.fecha === act);
  const mejor = diasMes.map((f) => [f, porDia[f].reduce((a, t) => a + t.pnl, 0)]).sort((a, b) => b[1] - a[1]);
  const kp = (lab, val, sub, c) => `<div class="card kpi"><div class="lab">${lab}</div><div class="big ${c || ''}">${val}</div><div class="chg" style="color:var(--dim)">${sub}</div></div>`;
  let h = `<div class="jtop"><div class="filters" style="margin:0"><button class="fbtn" data-a="prev" aria-label="Mes anterior">‹</button><span class="jmes">${MESES_L[M]} ${Y}</span><button class="fbtn" data-a="next" aria-label="Mes siguiente">›</button><button class="fbtn" data-a="hoy">Hoy</button></div>
    <div class="filters" style="margin:0"><button class="fbtn" data-a="exp-json">Exportar JSON</button><button class="fbtn" data-a="exp-csv">Exportar CSV</button><button class="fbtn" data-a="imp">Importar JSON</button><input type="file" id="jimp" accept="application/json,.json" hidden></div></div><div id="jsync">${DSYNC.html()}</div>`;
  h += `<div class="grid g4" style="margin-top:12px">
    ${kp('P&amp;L del mes', st.n ? f5.usd(st.tot) : '0,00 $', st.n ? `${st.n} operaciones · ${st.g} ganadoras · ${st.p} perdedoras` : 'sin operaciones este mes', st.tot > 0 ? 'up' : st.tot < 0 ? 'down' : '')}
    ${kp('Win rate del mes', st.win == null ? '—' : num(st.win, 0) + ' %', st.n ? `media ganadora ${st.medG == null ? '—' : f5.usd(st.medG, 0)} · perdedora ${st.medP == null ? '—' : f5.usd(st.medP, 0)}` : 'sin resultado')}
    ${kp('Factor de beneficio', st.pf == null ? '—' : num(st.pf, 2), 'ganancias brutas / pérdidas brutas del mes')}
    ${kp('Acumulado total', all.n ? f5.usd(all.tot) : '0,00 $', all.n ? `${all.n} operaciones · win rate ${all.win == null ? '—' : num(all.win, 0) + ' %'}` : 'registro vacío', all.tot > 0 ? 'up' : all.tot < 0 ? 'down' : '')}</div>`;
  h += `<div class="grid g21 stretch" style="margin-top:12px"><div class="card pad0"><div style="padding:12px 16px 4px" class="chead"><span>Calendario · ${MESES_L[M]} ${Y}</span><span class="more">clic en un día para añadir operaciones y notas</span></div><div style="padding:0 12px 12px">${cal}</div></div>
    <div class="col"><div class="card"><div class="chead"><span>${esc(fdd(act))}</span><span class="more">${delDia.length} ${delDia.length === 1 ? 'operación' : 'operaciones'}</span></div>
      <form id="jform" class="jform"><input type="hidden" name="fecha" value="${esc(act)}">
        <label>Activo<select name="activo">${ACT_BASE.map((a) => `<option>${esc(a)}</option>`).join('')}</select></label>
        <label>Lado<select name="lado"><option>Largo</option><option>Corto</option></select></label>
        <label class="full">Resultado (P&amp;L en $)<input name="pnl" inputmode="decimal" placeholder="p. ej. 125,50 o -80" required></label>
        <label class="full">Motivo / nota<input name="nota" maxlength="240" placeholder="Qué tesis había y qué pasó"></label>
        <button class="fbtn on full" type="submit">Añadir operación</button></form>
      ${delDia.length ? '<div class="jlist">' + delDia.map((t) => `<div class="jop"><span class="tag ${t.pnl > 0 ? 'alc' : t.pnl < 0 ? 'baj' : 'sin'}">${esc(t.lado)}</span><span class="nm">${esc(t.activo)}</span><span class="mono ${f5.cls(t.pnl)}">${f5.usd(t.pnl)}</span><button class="x" data-del="${esc(t.id)}" aria-label="Borrar operación">×</button>${t.nota ? `<span class="nt">${esc(t.nota)}</span>` : ''}</div>`).join('') + '</div>' : '<div class="note">Sin operaciones este día.</div>'}
      <label class="full" style="display:block;margin-top:10px"><span class="note">Nota del día</span><textarea id="jnota" rows="3" maxlength="600" placeholder="Estado de ánimo, errores, lo que repetirías…">${esc(S.notas[act] || '')}</textarea></label>
      <button class="fbtn" data-a="nota" style="margin-top:6px">Guardar nota</button></div></div></div>`;
  h += '<div class="grid g2" style="margin-top:12px"><div class="card chartcard"><h3>Curva de P&amp;L acumulado</h3><div class="sub">Suma de todos los resultados registrados, por fecha</div>';
  h += (cum.length > 1 ? lw('jCum', [{ name: 'P&L acumulado ($)', color: COL.amber, data: cum, prec: 2, area: true }], { range: false, fill: true }) : `<div class="chart fill"><div class="empty">${cum.length ? 'UN SOLO DÍA REGISTRADO · la curva aparece con el segundo' : 'SIN OPERACIONES · añade la primera para ver la curva'}</div></div>`);
  h += `${foot(diarioFuente(), false, null, DSYNC.conectado() ? 'copia privada en GitHub' : 'no se sube a ningún servidor')}</div>`;
  h += '<div class="card chartcard"><h3>P&amp;L diario del mes</h3><div class="sub">Verde = día ganador · rojo = día perdedor</div>';
  h += diasMes.length ? barras('jBar', diasMes.map((f) => String(+f.slice(8))), [{ name: 'P&L ($)', data: diasMes.map((f) => +porDia[f].reduce((a, t) => a + t.pnl, 0).toFixed(2)) }], { dec: 2, alto: 300, fino: 26 })
    : '<div class="chart fill"><div class="empty">SIN OPERACIONES ESTE MES</div></div>';
  h += `${foot(diarioFuente(), false, null, mejor.length ? 'mejor día ' + esc(fd(mejor[0][0])) + ' ' + f5.usd(mejor[0][1], 0) : 'sin días registrados')}</div></div>`;
  h += '<div class="sect"><h2>Operaciones del mes</h2><span class="more">más recientes primero</span></div><div class="card pad0 scroll">';
  h += mesTr.length ? `<table class="t"><thead><tr><th>Fecha</th><th>Activo</th><th>Lado</th><th>P&amp;L</th><th style="text-align:left">Nota</th><th></th></tr></thead><tbody>${mesTr.slice().sort((a, b) => b.fecha.localeCompare(a.fecha)).map((t) => `<tr><td>${esc(fdd(t.fecha))}</td><td>${esc(t.activo)}</td><td>${esc(t.lado)}</td><td class="${f5.cls(t.pnl)}">${f5.usd(t.pnl)}</td><td style="text-align:left;color:var(--muted);white-space:normal">${esc(t.nota || '')}</td><td><button class="x" data-del="${esc(t.id)}" aria-label="Borrar">×</button></td></tr>`).join('')}</tbody></table>`
    : '<div class="empty" style="height:110px;border:0">SIN OPERACIONES ESTE MES · usa el formulario de arriba</div>';
  h += '</div>';
  h += '<div class="note">Todo lo que escribes aquí se guarda en este navegador (localStorage). Con «Conectar GitHub» además se copia, en cada cambio, a tu repo privado nexora-diario (el token se queda solo en este navegador). Sin conexión se usa la copia local y se sincroniza después. Exportar JSON sigue siendo una copia extra. Importar sustituye el diario actual (y la copia de GitHub). El diario es tuyo y no forma parte de las tesis ni de las alertas de NEXORA.</div>';
  return h;
}
function pageDiario() {
  diario.st = dLoad();
  const hoy = hoyISO();
  if (!diario.mes) diario.mes = [+hoy.slice(0, 4), +hoy.slice(5, 7) - 1];
  if (!diario.dia) diario.dia = hoy;
  const S = diario.st, pref = `${diario.mes[0]}-${String(diario.mes[1] + 1).padStart(2, '0')}`;
  const mt = diarioStats(S.trades.filter((t) => t.fecha.startsWith(pref)));
  let h = head('Personal', 'Diario de operaciones', 'Tu diario de trades: qué pasó, por qué y cómo te sentiste. Calendario mensual con P&amp;L por día y semana, curva acumulada y estadísticas. Vive en tu navegador y, si quieres, en un repo privado tuyo.',
    `Registro personal · ${S.trades.length} operaciones guardadas${DSYNC.conectado() ? ' (navegador + GitHub privado)' : ' en este navegador'}`);
  h += essential(S.trades.length ? `${MESES_L[diario.mes[1]]}: ${mt.n} operaciones, P&amp;L ${f5.usd(mt.tot)}${mt.win != null ? ', win rate ' + num(mt.win, 0) + ' %' : ''}.` : 'El diario está vacío: todavía no has registrado ninguna operación en este navegador.',
    'Hecho: son tus propias cifras, sin comisiones ni deslizamiento salvo que las incluyas en el P&amp;L. Interpretación: el win rate solo sirve junto al tamaño medio de ganadoras y perdedoras (factor de beneficio).',
    'Anota el motivo de cada trade junto a la tesis NEXORA del día (Registro de tesis) para ver después si seguías tu plan o la contradecías.');
  h += '<div id="dia-root"></div>';
  MOUNT.push(() => {
    const root = document.getElementById('dia-root');
    if (!root) return;
    const repaint = () => f5.paint(root, diarioHtml);
    repaint();
    /* sincronización: lo remoto/fusionado se adopta y se repinta solo si el Diario sigue en pantalla */
    DSYNC.bind({ get: () => diario.st, set: (st) => { diario.st = DSYNC.norm(st); lsSet(DK, diario.st); if (document.getElementById('dia-root') === root) repaint(); } });
    DSYNC.abrir();
    root.addEventListener('click', (e) => {
      const dia = e.target.closest('[data-dia]'), del = e.target.closest('[data-del]'), a = e.target.closest('[data-a]');
      if (dia) { diario.dia = dia.dataset.dia; repaint(); return; }
      if (del) { diario.st.trades = diario.st.trades.filter((t) => t.id !== del.dataset.del); diario.st.borrados[del.dataset.del] = new Date().toISOString(); dSave(); repaint(); return; }
      if (!a) return;
      const k = a.dataset.a;
      if (DSYNC.accion(k)) return;
      if (k === 'prev' || k === 'next') { const [y, m] = diario.mes; const n = m + (k === 'next' ? 1 : -1); diario.mes = [y + Math.floor(n / 12), ((n % 12) + 12) % 12]; repaint(); }
      else if (k === 'hoy') { const t = hoyISO(); diario.mes = [+t.slice(0, 4), +t.slice(5, 7) - 1]; diario.dia = t; repaint(); }
      else if (k === 'nota') { const v = $('#jnota', root).value.trim(); diario.st.notas[diario.dia] = v; diario.st.notasMod[diario.dia] = new Date().toISOString(); dSave(); repaint(); }
      else if (k === 'exp-json') f5.descarga(`nexora-diario-${hoyISO()}.json`, JSON.stringify(diario.st, null, 1), 'application/json');
      else if (k === 'exp-csv') {
        const cab = ['fecha', 'activo', 'lado', 'pnl', 'nota'];
        f5.descarga(`nexora-diario-${hoyISO()}.csv`, [cab.join(','), ...diario.st.trades.slice().sort((a, b) => a.fecha.localeCompare(b.fecha)).map((t) => cab.map((c) => f5.csvCelda(t[c])).join(','))].join('\n'), 'text/csv');
      } else if (k === 'imp') $('#jimp', root).click();
    });
    root.addEventListener('submit', (e) => {
      if (e.target.id === 'jghform') { e.preventDefault(); DSYNC.enviar(e.target); return; }
      if (e.target.id !== 'jform') return;
      e.preventDefault();
      const f = new FormData(e.target);
      const pnl = parseFloat(String(f.get('pnl')).replace(/\s/g, '').replace(',', '.'));
      if (!Number.isFinite(pnl)) { alert('El resultado debe ser un número (p. ej. 125,50 o -80).'); return; }
      diario.st.trades.push({ id: f5.uid(), fecha: String(f.get('fecha')), activo: String(f.get('activo')), lado: String(f.get('lado')), pnl: Math.round(pnl * 100) / 100, nota: String(f.get('nota') || '').trim() });
      dSave(); repaint();
    });
    root.addEventListener('change', (e) => {
      if (e.target.id !== 'jimp' || !e.target.files[0]) return;
      const rd = new FileReader();
      rd.onload = () => {
        try {
          const o = JSON.parse(rd.result);
          if (!o || !Array.isArray(o.trades)) throw new Error('el archivo no tiene la lista «trades»');
          const ok = o.trades.filter((t) => t && /^\d{4}-\d{2}-\d{2}$/.test(t.fecha) && Number.isFinite(+t.pnl)).map((t) => ({ id: String(t.id || f5.uid()), fecha: t.fecha, activo: String(t.activo || 'Otro').slice(0, 40), lado: t.lado === 'Corto' ? 'Corto' : 'Largo', pnl: +t.pnl, nota: String(t.nota || '').slice(0, 240) }));
          if (!confirm(`Importar ${ok.length} operaciones sustituirá el diario actual (${diario.st.trades.length}). ¿Continuar?`)) return;
          const notas = {}, notasMod = {}, ahora = new Date().toISOString();
          Object.entries(o.notas && typeof o.notas === 'object' ? o.notas : {}).forEach(([d, v]) => { if (/^\d{4}-\d{2}-\d{2}$/.test(d) && v) { notas[d] = String(v).slice(0, 600); notasMod[d] = ahora; } });
          diario.st = DSYNC.norm({ trades: ok, notas, notasMod, borrados: {} });
          dSave('replace'); repaint();
        } catch (err) { alert('No se pudo importar: ' + err.message); }
      };
      rd.readAsText(e.target.files[0]);
    });
  });
  return h;
}

/* ================================================================== WATCHLISTS */
const WK = 'nexora.watchlists.v1';
/* catálogo: solo lo que NEXORA ya descarga en el build (Yahoo/FRED) + pares de Coinbase en directo desde el navegador */
const WCAT = [
  { id: 'spx', sym: 'SPX', nom: 'S&P 500', f: 'precios' }, { id: 'ndx', sym: 'NDX', nom: 'Nasdaq 100', f: 'precios' },
  { id: 'dji', sym: 'DJI', nom: 'Dow Jones (US30)', f: 'precios' }, { id: 'rut', sym: 'RUT', nom: 'Russell 2000', f: 'precios' },
  { id: 'oro', sym: 'XAU', nom: 'Oro (futuros)', f: 'precios' }, { id: 'btc', sym: 'BTC', nom: 'Bitcoin', f: 'precios' },
  { id: 'vix', sym: 'VIX', nom: 'Volatilidad S&P', f: 'precios' }, { id: 'dxy', sym: 'DXY', nom: 'Índice dólar', f: 'precios' },
  { id: 'qqq', sym: 'QQQ', nom: 'Invesco QQQ', f: 'yahoo' }, { id: 'spy', sym: 'SPY', nom: 'SPDR S&P 500', f: 'yahoo' },
  { id: 'iwm', sym: 'IWM', nom: 'iShares Russell 2000', f: 'yahoo' }, { id: 'rsp', sym: 'RSP', nom: 'S&P 500 equiponderado', f: 'yahoo' },
  { id: 'xly', sym: 'XLY', nom: 'Consumo discrecional', f: 'yahoo' }, { id: 'xlp', sym: 'XLP', nom: 'Consumo básico', f: 'yahoo' },
  { id: 'gld', sym: 'GLD', nom: 'SPDR Gold', f: 'yahoo' }, { id: 'gdx', sym: 'GDX', nom: 'Mineras de oro', f: 'yahoo' },
  { id: 'vix3m', sym: 'VIX3M', nom: 'VIX a 3 meses', f: 'yahoo' },
  { id: 't2y', sym: 'US2Y', nom: 'Bono EE. UU. 2 años', f: 'tipo' }, { id: 'n10', sym: 'US10Y', nom: 'Bono EE. UU. 10 años', f: 'tipo' }, { id: 'real10', sym: 'REAL10', nom: 'Tipo real 10 años', f: 'tipo' },
  { id: 'cb:ETH-USD', sym: 'ETH', nom: 'Ethereum (Coinbase)', f: 'cb' }, { id: 'cb:SOL-USD', sym: 'SOL', nom: 'Solana (Coinbase)', f: 'cb' },
  { id: 'cb:XRP-USD', sym: 'XRP', nom: 'XRP (Coinbase)', f: 'cb' }, { id: 'cb:ADA-USD', sym: 'ADA', nom: 'Cardano (Coinbase)', f: 'cb' },
  { id: 'cb:LINK-USD', sym: 'LINK', nom: 'Chainlink (Coinbase)', f: 'cb' }, { id: 'cb:DOGE-USD', sym: 'DOGE', nom: 'Dogecoin (Coinbase)', f: 'cb' },
];
const WDEF = () => [
  { id: 'w1', nombre: 'Principal', ids: ['spx', 'ndx', 'dji', 'rut', 'oro', 'btc', 'cb:ETH-USD', 'dxy', 'vix'] },
  { id: 'w2', nombre: 'Macro y tipos', ids: ['t2y', 'n10', 'real10', 'dxy', 'vix', 'vix3m', 'gld', 'xly', 'xlp'] },
];
const wst = { listas: null, sel: null, picker: null, cb: {} };
const wLoad = () => { const l = lsGet(WK, null); return Array.isArray(l) && l.length ? l : WDEF(); };
const wSave = () => lsSet(WK, wst.listas);
const wCat = (id) => WCAT.find((c) => c.id === id) || (/^cb:[A-Z0-9]{2,10}-USD$/.test(id) ? { id, sym: id.slice(3).split('-')[0], nom: id.slice(3) + ' (Coinbase)', f: 'cb' } : { id, sym: String(id).slice(0, 12), nom: 'Sin fuente gratuita', f: 'ninguna' });

/* variación en sesiones sobre una serie [[fecha, valor]]; null si no hay puntos suficientes (no se interpola) */
function wCambios(s, yield_) {
  if (!s || s.length < 2) return null;
  const l = s[s.length - 1][1];
  const c = (n) => { if (s.length <= n) return null; const r = s[s.length - 1 - n][1]; return yield_ ? (l - r) * 100 : (l / r - 1) * 100; };
  return { d1: c(1), d5: c(5), d21: c(21), d63: c(63) };
}
function wFila(it) {
  const c = wCat(it);
  if (c.f === 'precios') { const a = act(c.id); return a && a.valor != null ? { c, v: a.valor, fecha: a.fecha, serie: a.serie, ch: { d1: a.cambio_1d_pct, d5: a.cambio_5d_pct, d21: a.cambio_21d_pct, d63: a.cambio_63d_pct }, fuente: a.fuente } : { c }; }
  if (c.f === 'yahoo') { const a = D.series && D.series.yahoo && D.series.yahoo[c.id]; return a && a.valor != null ? { c, v: a.valor, fecha: a.fecha, serie: a.serie, ch: wCambios(a.serie), fuente: a.fuente } : { c }; }
  if (c.f === 'tipo') { const a = D.tipos && D.tipos[c.id]; return a && a.valor != null ? { c, v: a.valor, fecha: a.fecha, serie: a.serie, ch: wCambios(a.serie, true), yld: true, fuente: a.fuente } : { c }; }
  if (c.f === 'cb') { const a = wst.cb[c.id]; return a && a.v != null ? { c, v: a.v, fecha: a.fecha, serie: a.serie, ch: wCambios(a.serie), fuente: 'Coinbase Exchange (directo, sin clave)' } : { c, pend: a === undefined, err: a && a.err }; }
  return { c };
}
async function wCargaCb(ids) {
  await Promise.all(ids.map(async (id) => {
    const par = id.slice(3);
    try {
      const r = await fetch(`https://api.exchange.coinbase.com/products/${par}/candles?granularity=86400`);
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const j = await r.json();
      const s = j.map((k) => [new Date(k[0] * 1000).toISOString().slice(0, 10), k[4]]).sort((a, b) => a[0].localeCompare(b[0]));
      if (s.length < 2) throw new Error('sin velas');
      wst.cb[id] = { v: s[s.length - 1][1], fecha: s[s.length - 1][0], serie: s };
    } catch (e) { wst.cb[id] = { v: null, err: e.message }; }
  }));
}
function wTabla(l) {
  const rows = l.ids.map(wFila);
  const f = (v, d, yld) => (v == null ? '<td style="color:var(--dim)">—</td>' : `<td>${pill(v, d, yld ? ' pb' : '%')}</td>`);
  const sp = (s) => (s && s.length > 2 ? spark(s, 63).replace(/<div class="sparkcap">.*$/, '') : '');
  return `<div class="card pad0 scroll"><table class="t"><thead><tr><th>Activo</th><th>Último</th><th>1 d</th><th>1 sem</th><th>1 mes</th><th>3 meses</th><th>Tendencia</th><th>Dato</th><th style="text-align:left">Fuente</th></tr></thead><tbody>`
    + (rows.map((r) => r.v == null ? `<tr><td><b>${esc(r.c.sym)}</b><small>${esc(r.c.nom)}</small></td><td colspan="6" style="text-align:left;color:var(--dim)">SIN DATO${r.pend ? ' · cargando…' : r.c.f === 'ninguna' ? ' · sin fuente gratuita accesible desde el navegador' : r.err ? ' · ' + esc(r.err) : ''}</td><td></td><td></td></tr>`
      : `<tr><td><b>${esc(r.c.sym)}</b><small>${esc(r.c.nom)}</small></td><td>${num(r.v, r.yld ? 2 : r.v > 1000 ? 0 : 2)}${r.yld ? ' %' : ''}</td>${f(r.ch && r.ch.d1, r.yld ? 0 : 2, r.yld)}${f(r.ch && r.ch.d5, r.yld ? 0 : 2, r.yld)}${f(r.ch && r.ch.d21, r.yld ? 0 : 2, r.yld)}${f(r.ch && r.ch.d63, r.yld ? 0 : 2, r.yld)}<td style="min-width:120px">${sp(r.serie)}</td><td>${esc(fd(r.fecha))}</td><td style="text-align:left;color:var(--dim)">${esc(r.fuente)}</td></tr>`).join('') || '<tr><td colspan="9" style="text-align:left;color:var(--dim)">Lista vacía: usa «Elegir activos».</td></tr>')
    + '</tbody></table></div>';
}
function wHtml() {
  const L = wst.listas;
  const sel = L.find((x) => x.id === wst.sel) || L[0];
  let h = '<form id="wnueva" class="wnueva"><input name="n" maxlength="40" placeholder="Nueva watchlist" required aria-label="Nombre de la nueva watchlist"><button class="fbtn on" type="submit">Crear</button></form>';
  h += '<div class="wgrid">' + L.map((l) => `<div class="card wl ${l.id === sel.id ? 'cur' : ''}"><div class="wh"><div><h3>${esc(l.nombre)}</h3><span class="sub" style="margin:0">${l.ids.length} activos</span></div>
      <div class="wb"><button class="fbtn ${l.id === sel.id ? 'on' : ''}" data-w="ver" data-id="${esc(l.id)}">Ver en la terminal</button><button class="fbtn" data-w="ren" data-id="${esc(l.id)}">Renombrar</button><button class="fbtn" data-w="del" data-id="${esc(l.id)}">Borrar</button></div></div>
      <div class="chips2">${l.ids.map((i) => { const c = wCat(i); return `<span class="chip2" title="${esc(c.nom)}"><b>${esc(c.sym)}</b><em>${esc(c.nom)}</em><button class="x" data-w="quitar" data-id="${esc(l.id)}" data-i="${esc(i)}" aria-label="Quitar ${esc(c.sym)}">×</button></span>`; }).join('') || '<span class="note">Lista vacía</span>'}</div>
      <button class="fbtn" data-w="pick" data-id="${esc(l.id)}" style="margin-top:10px">${wst.picker === l.id ? 'Cerrar selector' : 'Elegir activos'}</button>
      ${wst.picker === l.id ? `<div class="picker">${WCAT.map((c) => `<button class="fbtn ${l.ids.includes(c.id) ? 'on' : ''}" data-w="tog" data-id="${esc(l.id)}" data-i="${esc(c.id)}">${esc(c.sym)} <span style="color:var(--dim)">${esc(c.nom)}</span></button>`).join('')}
        <form class="wcb" data-id="${esc(l.id)}"><input name="par" maxlength="14" placeholder="Par Coinbase, p. ej. AVAX-USD" aria-label="Par de Coinbase"><button class="fbtn" type="submit">Añadir par</button></form></div>` : ''}</div>`).join('') + '</div>';
  h += `<div class="sect"><h2>${esc(sel.nombre)} · en la terminal</h2><span class="more">precios del último build y pares de Coinbase en directo · ▲▼ frente al cierre anterior</span></div>${wTabla(sel)}`;
  h += '<div class="note">Fuentes: el build de NEXORA (Yahoo Finance, Tesoro de EE. UU.) y, para criptomonedas, la API pública de Coinbase Exchange consultada desde tu navegador. Yahoo no permite consultas directas desde el navegador, así que un símbolo fuera del catálogo se muestra como SIN DATO en vez de estimarse. Tus listas se guardan solo en este navegador.</div>';
  return h;
}
function pageWatchlists() {
  wst.listas = wLoad();
  if (!wst.sel || !wst.listas.some((l) => l.id === wst.sel)) wst.sel = wst.listas[0].id;
  const P = D.precios;
  let h = head('Mercados', 'Watchlists', 'Crea listas con los activos que quieres seguir y elige cuál ver en la terminal. Precio, variación y tendencia de cada uno, con su fuente y su fecha. Las listas se guardan en tu navegador.',
    `Precios: ${P && P.generado_utc ? esc(horaAct(P.generado_utc)) : 'SIN DATO'} · pares de Coinbase en directo al abrir la página`);
  h += fallo('precios');
  h += '<div id="wl-root"></div>';
  MOUNT.push(() => {
    const root = document.getElementById('wl-root');
    if (!root) return;
    const repaint = () => { root.innerHTML = wHtml(); };
    const pedir = async () => {
      const ids = [...new Set(wst.listas.flatMap((l) => l.ids).filter((i) => i.startsWith('cb:') && wst.cb[i] === undefined))];
      if (ids.length) { await wCargaCb(ids); repaint(); }
    };
    repaint(); pedir();
    root.addEventListener('click', (e) => {
      const b = e.target.closest('[data-w]'); if (!b) return;
      const l = wst.listas.find((x) => x.id === b.dataset.id), k = b.dataset.w;
      if (!l) return;
      if (k === 'ver') wst.sel = l.id;
      else if (k === 'ren') { const n = prompt('Nuevo nombre de la watchlist', l.nombre); if (n && n.trim()) l.nombre = n.trim().slice(0, 40); }
      else if (k === 'del') { if (wst.listas.length < 2) { alert('Debe quedar al menos una watchlist.'); return; } if (!confirm(`¿Borrar «${l.nombre}»?`)) return; wst.listas = wst.listas.filter((x) => x.id !== l.id); if (wst.sel === l.id) wst.sel = wst.listas[0].id; }
      else if (k === 'quitar') l.ids = l.ids.filter((x) => x !== b.dataset.i);
      else if (k === 'pick') wst.picker = wst.picker === l.id ? null : l.id;
      else if (k === 'tog') { const i = b.dataset.i; l.ids = l.ids.includes(i) ? l.ids.filter((x) => x !== i) : [...l.ids, i].slice(0, 100); }
      wSave(); repaint(); pedir();
    });
    root.addEventListener('submit', (e) => {
      e.preventDefault();
      if (e.target.id === 'wnueva') {
        const n = String(new FormData(e.target).get('n')).trim();
        if (!n) return;
        const l = { id: 'w' + f5.uid(), nombre: n.slice(0, 40), ids: [] };
        wst.listas.push(l); wst.sel = l.id; wst.picker = l.id;
      } else if (e.target.classList.contains('wcb')) {
        const par = String(new FormData(e.target).get('par')).trim().toUpperCase().replace(/\s/g, '');
        const l = wst.listas.find((x) => x.id === e.target.dataset.id);
        if (!/^[A-Z0-9]{2,10}-USD$/.test(par)) { alert('Formato de par de Coinbase contra dólar: BASE-USD (p. ej. AVAX-USD).'); return; }
        const id = 'cb:' + par;
        if (l && !l.ids.includes(id)) l.ids.push(id);
      }
      wSave(); repaint(); pedir();
    });
  });
  return h;
}

/* ================================================================== REGISTRO DE TESIS */
const HZ_CLS = { ACIERTO: 'ok', FALLO: 'no', PENDIENTE: 'sd', 'NO EVALUADA': 'sd' };
const TESIS_ORDEN = ['Oro', 'Bitcoin', 'S&P 500', 'Nasdaq 100', 'US30 · Dow Jones', 'Russell 2000'];
function tesisColor(et) {
  const e = String(et || '');
  return e.includes('DÉBIL') ? 'deb' : e.startsWith('ALCISTA') ? 'alc' : e.startsWith('BAJISTA') ? 'baj' : 'sin';
}
const tesisSt = { activo: 'Todos' };
function pageTesis() {
  const T = D.tesis;
  let h = head('Personal', 'Registro de tesis', 'Histórico de las tesis de NEXORA por activo y día, con su verificación posterior a 1, 5 y 20 sesiones. Sirve para medir cuánto ha acertado el motor, no para operar.',
    `Verificación: ${T && T.generado_utc ? esc(horaAct(T.generado_utc)) : 'SIN DATO'} · memoria: data/registro_tesis.csv (solo se añade)`);
  h += fallo('tesis');
  if (!T || !T.filas) return h + noData('Registro de tesis');
  const F = T.filas;
  const dir = F.filter((r) => /^(ALCISTA|BAJISTA)/.test(r.tesis));
  const ev = []; F.forEach((r) => Object.entries(r.horizontes).forEach(([n, x]) => { if (x.estado === 'ACIERTO' || x.estado === 'FALLO') ev.push({ r, n, x }); }));
  const ac = ev.filter((e) => e.x.estado === 'ACIERTO').length;
  const fechas = [...new Set(F.map((r) => r.fecha))].sort();
  const pend = dir.reduce((a, r) => a + Object.values(r.horizontes).filter((x) => x.estado === 'PENDIENTE').length, 0);
  h += essential(`${F.length} tesis registradas en ${fechas.length} día${fechas.length === 1 ? '' : 's'} (${dir.length} con dirección, ${F.length - dir.length} «SIN TESIS»). ${ev.length ? `${ac} aciertos de ${ev.length} comprobaciones (${num(ac / ev.length * 100, 0)} %).` : 'Todavía ninguna se ha podido comprobar: faltan sesiones.'}`,
    'Hecho: una tesis ALCISTA acierta si el precio a 1, 5 o 20 sesiones está por encima del de referencia; BAJISTA, por debajo. Interpretación: con pocas observaciones el porcentaje no significa nada; hacen falta muchas semanas para que sea informativo.',
    `${pend} comprobaciones pendientes. La siguiente se cierra cuando haya una sesión nueva tras la fecha de cada tesis.`);

  const R = T.resumen || {};
  h += '<div class="sect"><h2>Acierto por activo y horizonte</h2><span class="more">aciertos / comprobaciones · solo tesis con dirección</span></div><div class="grid g6">';
  h += TESIS_ORDEN.map((a) => {
    const b = R[a] || {};
    const fila = (n) => { const x = b[n]; return `<tr><td>T+${n}</td><td>${x && x.evaluadas ? `<b class="${x.aciertos / x.evaluadas >= 0.5 ? 'up' : 'down'}">${x.aciertos}/${x.evaluadas}</b>` : '<span style="color:var(--dim)">pendiente</span>'}</td></tr>`; };
    const ult = F.find((r) => r.activo === a);
    return `<div class="card kpi"><div class="lab">${esc(a)}</div><div class="exp">${ult ? 'Última: ' + esc(fd(ult.fecha)) : ''}</div><div style="margin:2px 0 8px">${ult ? tagTesis(ult.tesis) : SD}</div><table>${(T.horizontes || [1, 5, 20]).map((n) => fila(String(n))).join('')}</table></div>`;
  }).join('') + '</div>';

  /* matriz fecha × activo con el color de la tesis de ese día */
  /* últimas 8 sesiones (lun-vie) hasta la última fecha registrada; un día sin fila se muestra vacío, no se rellena */
  const cols = []; { let d = pd(fechas[fechas.length - 1]); while (cols.length < 8) { const w = d.getUTCDay(); if (w !== 0 && w !== 6) cols.unshift(d.toISOString().slice(0, 10)); d = new Date(d - 864e5); } }
  h += '<div class="sect"><h2>Matriz de tesis</h2><span class="more">verde = alcista · rojo = bajista · ámbar = débil · gris = sin tesis</span></div><div class="card pad0 scroll"><table class="t hm tm"><thead><tr><th>Activo</th>' + cols.map((f) => `<th>${esc(fd(f))}</th>`).join('') + '</tr></thead><tbody>';
  h += TESIS_ORDEN.map((a) => `<tr><td>${esc(a)}</td>${cols.map((f) => { const r = F.find((x) => x.fecha === f && x.activo === a); return r ? `<td class="hc tc-${tesisColor(r.tesis)}" title="${esc(r.tesis)} · ${esc(r.motores || '')}"><div class="hv">${r.tesis.startsWith('ALCISTA') ? '▲' : r.tesis.startsWith('BAJISTA') ? '▼' : '▬'}</div><div class="hs">${esc(r.puntuacion || '0')}</div></td>` : '<td class="hc z"></td>'; }).join('')}</tr>`).join('');
  h += '</tbody></table>' + footIn('Registro NEXORA data/registro_tesis.csv', fechas[fechas.length - 1], 'https://github.com/komonartisans-ops/nexora-terminal/blob/main/data/registro_tesis.csv', 'una fila por activo y día') + '</div>';

  const vis = F.filter((r) => tesisSt.activo === 'Todos' || r.activo === tesisSt.activo);
  h += `<div class="sect"><h2>Histórico</h2><span class="more">${vis.length} filas</span></div><div class="filtros" id="tfil">${['Todos', ...TESIS_ORDEN].map((a) => `<button class="fbtn ${tesisSt.activo === a ? 'on' : ''}" data-a="${esc(a)}">${esc(a)}</button>`).join('')}</div>`;
  h += '<div class="card pad0 scroll"><table class="t"><thead><tr><th>Fecha</th><th style="text-align:left">Activo</th><th>Tesis</th><th>Puntuación</th><th style="text-align:left">Motores</th><th>Referencia</th><th>T+1</th><th>T+5</th><th>T+20</th></tr></thead><tbody>';
  const hz = (x) => (x.estado === 'ACIERTO' || x.estado === 'FALLO' ? `<span class="ck ${HZ_CLS[x.estado]}">${x.estado}</span> <small class="mono ${f5.cls(x.ret_pct)}">${sg(x.ret_pct, 2, '%')}</small>` : `<span class="ck sd">${x.estado}</span>`);
  h += vis.map((r) => `<tr><td>${esc(fdd(r.fecha))}</td><td style="text-align:left">${esc(r.activo)}</td><td>${tagTesis(r.tesis)}</td><td>${esc(r.puntuacion || '0')}</td><td style="text-align:left;color:var(--muted);white-space:normal">${esc(r.motores || '')}</td><td>${r.precio_referencia == null ? '—' : num(r.precio_referencia, r.precio_referencia > 1000 ? 0 : 2)}</td>${['1', '5', '20'].map((n) => `<td>${hz(r.horizontes[n] || { estado: 'PENDIENTE' })}</td>`).join('')}</tr>`).join('');
  h += '</tbody></table>' + footIn('Registro NEXORA + cierres de Yahoo Finance', fechas[fechas.length - 1], 'https://github.com/komonartisans-ops/nexora-terminal/blob/main/data/registro_tesis.csv') + '</div>';
  h += `<div class="note">${esc(T.regla)} Fuente: ${esc(T.fuente)}. Cada ejecución diaria añade filas nuevas y nunca reescribe las anteriores; el histórico de Git conserva qué se sabía en cada fecha.</div>`;
  MOUNT.push(() => {
    const bar = document.getElementById('tfil');
    if (bar) bar.addEventListener('click', (e) => { const b = e.target.closest('button'); if (!b) return; tesisSt.activo = b.dataset.a; route(); });
  });
  return h;
}

Object.assign(window.EXTRA_PAGES, { diario: pageDiario, watchlists: pageWatchlists, tesis: pageTesis });
