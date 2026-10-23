/* NEXORA TERMINAL · integridad de datos (#/integridad), tabla «Cuándo salió cada dato» de #/publicados y resumen en la cabecera.
   Lee site/data/integridad.json (engine/integridad.py). Solo muestra: no calcula ni cambia nada. Todo texto dinámico pasa por esc(). */
'use strict';

const INTEG_ESTADO = { verde: ['ok', 'AL DÍA'], ambar: ['par', 'RETRASADO'], gris: ['sd', 'SIN DATO'] };
const integF = (iso) => (iso ? fdy(iso) : null);
const integH = (utc) => (utc ? horaAct(utc) : 'SIN DATO');

/* resumen en la cabecera: «Integridad: X/Y al día» */
function integHeader() {
  const el = document.getElementById('integ'), I = D.integridad;
  if (!el) return;
  if (!I || !I.resumen) { el.className = 'integ sd'; el.textContent = 'Integridad: SIN DATO'; el.title = 'integridad.json no disponible'; return; }
  const r = I.resumen, n = (I.discrepancias_abiertas || []).length;
  el.className = 'integ ' + (n ? 'no' : r.retrasados ? 'par' : r.sin_dato ? 'sd' : 'ok');
  el.dataset.c = `${r.al_dia}/${r.total}${n ? ' !' : ''}`;   // versión corta para móvil
  el.textContent = `${r.texto}${n ? ` · ${n} discrepancia${n > 1 ? 's' : ''}` : ''}`;
  el.title = `${r.retrasados} retrasado(s) · ${r.sin_dato} sin dato · actualizado ${horaAct(I.generado_utc)}. Pulsa para ver el detalle.`;
}

/* tabla «Cuándo salió cada dato» (se usa en #/publicados y en #/integridad) */
function integTablaPublicados(corto) {
  const I = D.integridad;
  let h = '<div class="sect"><h2>Cuándo salió cada dato</h2><span class="more">dato de · publicado el · registrado por NEXORA · próximo dato</span></div>';
  h += '<div class="note" style="margin:0 0 8px">Cada dato se publica semanas después del mes al que se refiere: el IPC de octubre sale en noviembre.</div>';
  if (!I || !I.publicaciones) return h + noData('Integridad de datos (integridad.json)');
  const ultimo = (x, i, a) => a.findIndex((y) => y.serie === x.serie) === i;      // la primera fila de cada serie es su último periodo
  const filas = I.publicaciones.filter((x, i, a) => !corto || ultimo(x, i, a));
  h += '<div class="card pad0 scroll"><table class="t stack"><thead><tr><th style="text-align:left">Dato</th><th>Dato de</th><th>Publicado el</th><th>Registrado por NEXORA</th><th style="text-align:left">Próximo dato</th><th>Segunda fuente</th></tr></thead><tbody>';
  h += filas.map((x) => {
    const d = x.discrepancia;
    return `<tr><td data-label="Dato" style="text-align:left"><b>${esc(x.dato)}</b></td><td data-label="Dato de">${esc(x.dato_de)}</td>
      <td data-label="Publicado el">${x.publicado ? `${esc(fdy(x.publicado))}<small>${esc(x.publicado_fuente)}</small>` : '<span class="sd-val">SIN DATO</span>'}</td>
      <td data-label="Registrado">${x.registrado ? `${esc(x.registrado_utc ? horaAct(x.registrado_utc) : fdy(x.registrado) + ' (solo fecha)')}<small>${esc(x.registro_origen || '')}${x.retraso_horas != null ? ` · ${num(x.retraso_horas, 1)} h tras la publicación` : x.retraso_dias != null ? ` · ${x.retraso_dias} d tras la publicación` : ''}</small>` : '<span class="sd-val">SIN DATO</span>'}</td>
      <td data-label="Próximo dato" style="text-align:left">${x.proximo ? `${esc(x.proximo.texto)}<small>${x.proximo.hora_madrid ? esc(x.proximo.hora_madrid) + ' Madrid · ' : ''}${esc(x.proximo.fuente || '')}</small>${x.proximo.otra_fuente ? `<span class="ck par" title="${esc(x.proximo.discrepancia_calendario || '')}">DISCREPANCIA DE CALENDARIO</span><small style="color:var(--amber)">Calendario oficial: ${esc(x.proximo.otra_fuente.texto)} (${esc(x.proximo.otra_fuente.fuente)})</small><small>${esc(x.proximo.discrepancia_calendario || '')}</small>` : ''}` : (ultimo(x, I.publicaciones.indexOf(x), I.publicaciones) ? '<span class="sd-val">SIN DATO</span><small>fuera del calendario conocido</small>' : '—')}</td>
      <td data-label="Segunda fuente">${d ? `<span class="ck no">DISCREPANCIA</span><small>${esc(d.primaria)}: ${esc(d.primaria_valor)} · FRED: ${esc(d.fred_valor)} · manda la primaria</small>` : x.segunda_fuente === 'BLS' ? '<span class="ck ok">coincide con BLS</span>' : x.segunda_fuente === 'BEA' ? '<span class="ck sd">SIN DATO</span><small>BEA exige clave</small>' : '—'}</td></tr>`;
  }).join('');
  return h + `</tbody></table>${footIn('FRED/ALFRED (fecha de publicación), data/publicaciones_macro.csv (registro NEXORA), calendario FRED', I.generado_utc && I.generado_utc.slice(0, 10), null, 'último periodo de cada serie')}</div>`;
}

function pageIntegridad() {
  const I = D.integridad;
  let h = head('Análisis', 'Integridad de datos', 'Si cada bloque de la web está al día, si algún dato oficial se publicó y NEXORA no lo registró, y si FRED y la fuente primaria (BLS) dicen lo mismo. Nada se inventa: sin dato aparece SIN DATO.',
    `Actualizado: ${I && I.generado_utc ? esc(horaAct(I.generado_utc)) : 'SIN DATO'}`);
  if (!I || !I.bloques) return h + noData('Integridad de datos (integridad.json)');
  const r = I.resumen, disc = I.discrepancias_abiertas || [];
  h += essential(`${esc(r.texto)}: ${r.retrasados} retrasado(s) y ${r.sin_dato} sin dato. ${disc.length ? disc.length + ' discrepancia(s) abierta(s) entre FRED y la fuente primaria.' : 'Sin discrepancias abiertas con la fuente primaria.'}`,
    'Hecho: «al día» = la última ejecución válida es posterior a la última programada para ese bloque (con la tolerancia de sus crones); «retrasado» = no lo es o la última ejecución falló; «sin dato» = no hay ninguna. Interpretación: un bloque retrasado no significa que el dato sea malo, sino que puede estar viejo.',
    'Mira primero las discrepancias abiertas y los retrasos de registro: son lo que más afecta a la fiabilidad de lo que lees.', 'Cómo leerlo');
  const vc = I.vigilante_cierre;
  if (vc && vc.alerta) h += `<div class="banner red" style="margin:0 0 14px;border-radius:6px"><b>Vigilante del cierre parado:</b> ${esc(vc.texto)} Revisa el disparo externo (cron-job.org, 22:15 UTC).</div>`;
  const dcal = I.discrepancias_calendario || [];
  if (dcal.length) h += `<div class="banner amber" style="margin:0 0 14px;border-radius:6px"><b>Discrepancia de calendario:</b> ${dcal.map((d) => `${esc(d.dato)}: FRED «${esc(d.fred)}» frente a «${esc(d.oficial)}» (${esc(d.motivo)})`).join(' · ')}. Se muestran las dos fechas; no se elige una.</div>`;
  if (disc.length) h += `<div class="banner red" style="margin:0 0 14px;border-radius:6px"><b>DISCREPANCIA abierta:</b> ${disc.map((d) => `${esc(d.serie)} ${esc(d.periodo.slice(0, 7))} (${esc(d.tipo.toLowerCase())}): FRED ${esc(d.fred_valor)} frente a ${esc(d.primaria)} ${esc(d.primaria_valor)}${d.dif_pct ? ' (' + esc(num(+d.dif_pct, 3)) + ' %)' : ''}`).join(' · ')}. Manda la fuente primaria.</div>`;
  const rv = I.discrepancias_revisadas || [];
  if (rv.length) h += `<div class="sect"><h2>Discrepancias revisadas</h2><span class="more">en gris · fuera del contador · siguen visibles</span></div><div class="card pad0 scroll"><table class="t stack"><thead><tr><th style="text-align:left">Discrepancia</th><th style="text-align:left">Detalle</th><th style="text-align:left">Motivo</th><th>Revisada</th><th style="text-align:left">Cuándo se reabre o se cierra</th></tr></thead><tbody>${rv.map((d) => `<tr style="color:var(--dim)"><td data-label="Discrepancia" style="text-align:left"><b>${esc(d.titulo)}</b> <span class="ck sd">REVISADA</span></td><td data-label="Detalle" style="text-align:left">${esc(d.detalle)}</td><td data-label="Motivo" style="text-align:left">${esc(d.motivo)}</td><td data-label="Revisada">${esc(horaAct(d.registrada_utc))}<small>${esc(d.revisor)}</small></td><td data-label="Regla" style="text-align:left">${esc(d.regla)}</td></tr>`).join('')}</tbody></table>${footIn('data/discrepancias_revisadas.csv (solo añadir)', I.generado_utc && I.generado_utc.slice(0, 10), null, 'una revisada vuelve a contar si cambia de forma relevante')}</div>`;
  h += '<div class="sect"><h2>Estado de cada bloque</h2><span class="more">verde = al día · ámbar = retrasado · gris = SIN DATO</span></div><div class="card pad0 scroll"><table class="t stack"><thead><tr><th style="text-align:left">Bloque</th><th>Estado</th><th>Frecuencia</th><th>Último dato</th><th>Registrado</th><th>Próximo</th><th>Discrepancias</th></tr></thead><tbody>';
  h += I.bloques.map((b) => {
    const [cls, txt] = INTEG_ESTADO[b.color] || ['sd', 'SIN DATO'];
    return `<tr><td data-label="Bloque" style="text-align:left"><a href="#/${esc(b.pagina)}"><b>${esc(b.bloque)}</b></a></td><td data-label="Estado"><span class="ck ${cls}" title="${esc(b.motivo)}">${txt}</span>${b.color === 'verde' ? '' : `<small>${esc(b.motivo)}</small>`}</td>
      <td data-label="Frecuencia">${esc(b.frecuencia)}</td><td data-label="Último dato">${b.ultimo_dato ? esc(fdy(b.ultimo_dato)) : b.color === 'gris' ? '<span class="sd-val">SIN DATO</span>' : '—'}</td><td data-label="Registrado">${esc(integH(b.registrado_utc))}</td>
      <td data-label="Próximo">${esc(horaAct(b.proximo_utc))}</td><td data-label="Discrepancias">${b.discrepancias_abiertas ? `<span class="ck no">${b.discrepancias_abiertas}</span>` : '0'}</td></tr>`;
  }).join('') + `</tbody></table>${footIn('Ejecuciones de build.py (site/data/meta.json) y crones', I.generado_utc && I.generado_utc.slice(0, 10), null, 'los fines de semana no cuentan como retraso')}</div>`;
  h += integTablaPublicados(true);
  const rr = I.retrasos_registro || [];
  h += '<div class="sect"><h2>Retrasos de registro</h2><span class="more">fecha oficial de publicación frente a la fecha en que NEXORA lo registró</span></div><div class="card pad0 scroll">';
  h += rr.length ? `<table class="t"><thead><tr><th style="text-align:left">Dato</th><th>Dato de</th><th>Publicado</th><th>Registrado</th><th>Retraso</th></tr></thead><tbody>${rr.map((x) => `<tr><td style="text-align:left"><b>${esc(x.dato)}</b></td><td>${esc(x.dato_de)}</td><td>${esc(fdy(x.publicado))}</td><td>${esc(x.registrado_utc ? horaAct(x.registrado_utc) : fdy(x.registrado) + ' (solo fecha)')}</td><td class="${x.retraso_dias > 1 ? 'down' : ''}">${x.retraso_horas != null ? num(x.retraso_horas, 1) + ' h' : x.retraso_dias + (x.retraso_dias === 1 ? ' día' : ' días') + ' (solo fecha)'}</td></tr>`).join('')}</tbody></table>`
    : '<div class="empty" style="height:90px;border:0">SIN DATOS REGISTRADOS EN VIVO TODAVÍA</div>';
  h += `<div class="note" style="padding:0 16px 12px">Histórico anterior al arreglo del disparo externo (cron-job.org): el registro se hacía a la primera ejecución del día siguiente, por eso sale ≈ 1 día. Las filas anteriores a esta versión solo guardan la fecha de registro (retraso en días); las nuevas guardan también la hora (retraso en horas). Los datos de «carga inicial» no cuentan: se bajaron de golpe al empezar y no miden el retraso. Desde la ampliación de la franja de reacciones y el vigilante, este número debe bajar.</div></div>`;
  h += integMichigan(I.michigan);
  h += integEia(I.eia);
  h += integSpotOro(I.spot_oro);
  h += integObsidian(I.obsidian);
  const V = I.vigilante || {}, S = I.segunda_fuente || {};
  h += '<div class="sect"><h2>Vigilante y segunda fuente</h2><span class="more">cómo se comprueba cada dato</span></div><div class="grid g3"><div class="card"><div class="chead"><span>Vigilante de publicaciones</span></div>'
    + `<p class="note" style="margin:6px 0">Regla: ${esc(V.regla || '')}. Un aviso por dato.</p><p class="note" style="margin:0">${V.avisos ? V.avisos + ' aviso(s) enviado(s) hasta ahora.' : 'Ningún aviso enviado todavía: no ha faltado ningún dato.'}</p></div>`
    + `<div class="card"><div class="chead"><span>Vigilante del cierre</span></div><p class="note" style="margin:6px 0">${esc(vc ? vc.texto : 'SIN DATO')}</p><p class="note" style="margin:0">Comprueba cada día a las 22:15 UTC, en data/ejecuciones.csv, que las etapas del cierre de las 21:30 UTC corrieron OK; avisa por Telegram si no. Si él mismo no corre en 2 días hábiles, avisa esta página.</p></div>
    <div class="card"><div class="chead"><span>Segunda fuente</span></div><p class="note" style="margin:6px 0"><b>BLS</b> (IPC, IPC subyacente, IPP): ${esc(S.BLS || '')}.</p><p class="note" style="margin:0"><b>BEA</b> (PIB, PCE): ${esc(S.BEA || '')}</p>${S.bls_ultimo_error ? `<p class="note" style="margin:4px 0 0">Último error de BLS: ${esc(S.bls_ultimo_error)}</p>` : ''}${S.bea_ultimo_error ? `<p class="note" style="margin:4px 0 0">Último error de BEA: ${esc(S.bea_ultimo_error)}</p>` : ''}</div></div>`;
  return h;
}

/* Fase 19: contraste del spot del oro (gold-api frente a GC=F − base y Swissquote) */
function integSpotOro(B) {
  let h = '<div class="sect"><h2>Spot del oro · contraste de fuentes</h2><span class="more">gold-api · GC=F − base · Swissquote · umbral 0,3 %</span></div>';
  const u = B && B.ultimo;
  if (!u) return h + '<div class="card"><p class="note" style="margin:0">SIN DATO: el primer contraste se registra en el cierre de las 21:30 UTC (data/xau_spot_contraste.csv).</p></div>';
  const cls = (e) => (e === 'OK' ? 'ok' : e === 'DUDOSO' ? 'no' : e === 'GC_IMPLICITO' || e === 'SWISSQUOTE' || e === 'NO_SINCRONIZADO' ? 'par' : 'sd');
  const dp = (x) => (x === '' || x == null ? '—' : `${+x > 0 ? '+' : ''}${esc(num(+x, 3))} %`);
  if (B.racha_swiss_caido >= B.sesiones_swiss_aviso) h += `<div class="banner red" style="margin:0 0 14px;border-radius:6px"><b>Swissquote sin responder ${B.racha_swiss_caido} sesiones seguidas</b> (desde ${esc(fdy(B.racha_swiss_desde))}): el spot del oro depende solo de gold-api. El GC=F es informativo (retraso ~10 min).</div>`;
  else if (u.swiss_precio === '') h += `<div class="banner amber" style="margin:0 0 14px;border-radius:6px"><b>Swissquote no respondió en el último contraste</b> (${B.racha_swiss_caido} de ${B.sesiones_swiss_aviso} sesiones seguidas antes del aviso por Telegram).</div>`;
  if (B.racha_dudoso >= 2) h += `<div class="banner red" style="margin:0 0 14px;border-radius:6px"><b>Spot del oro dudoso ${B.racha_dudoso} sesiones seguidas</b> (desde ${esc(fdy(B.racha_desde))}). El ratio XAU/GLD y la base GC−XAU no se actualizan mientras dure.</div>`;
  else if (u.estado === 'DUDOSO') h += `<div class="banner amber" style="margin:0 0 14px;border-radius:6px"><b>Spot del oro dudoso el ${esc(fdy(u.fecha))}:</b> el ratio XAU/GLD no se actualizó (se usa el último OK). Si se repite mañana, aviso por Telegram.</div>`;
  h += `<div class="card"><div class="chead"><span>Último contraste · ${esc(fdy(u.fecha))}</span><span class="ck ${cls(u.estado)}">${esc(u.estado)}</span></div>`
    + `<p class="note" style="margin:6px 0">${esc(u.texto_fuentes)}</p><p class="note" style="margin:0">Spot usado: <b>${esc(u.spot_usado)}</b> (${esc(u.spot_fuente)}) · ratio XAU/GLD: ${u.ratio_fuente === 'ANTERIOR' ? '<b>NO actualizado</b> (se usa el último OK)' : 'de la sesión'}${u.nota ? ' · ' + esc(u.nota) : ''}</p>`
    + `<p class="note" style="margin:6px 0 0">${esc(B.regla)}</p></div>`;
  h += '<div class="card pad0 scroll" style="margin-top:12px"><table class="t stack"><thead><tr><th style="text-align:left">Sesión</th><th>gold-api</th><th>GC implícito <small>informativo (retraso ~10 min)</small></th><th>Dif. GC</th><th>Swissquote</th><th>Dif. Swiss</th><th>Estado</th><th>Ratio</th></tr></thead><tbody>'
    + (B.historial || []).map((r) => `<tr><td data-label="Sesión" style="text-align:left">${esc(fdy(r.fecha))}</td><td data-label="gold-api">${esc(r.spot_principal || 'CAÍDA')}</td><td data-label="GC implícito">${esc(r.spot_gc_implicito || '—')}</td><td data-label="Dif. GC">${r.spot_gc_implicito && (r.dif_gc_pct === '' || r.dif_gc_pct == null) ? 'informativo' : dp(r.dif_gc_pct)}</td><td data-label="Swissquote">${esc(r.swiss_precio || '—')}</td><td data-label="Dif. Swiss">${dp(r.dif_swiss_pct)}</td><td data-label="Estado"><span class="ck ${cls(r.estado)}">${esc(r.estado)}</span></td><td data-label="Ratio">${esc(r.ratio_fuente)}</td></tr>`).join('')
    + `</tbody></table>${footIn(B.fuente, u.fecha, null, '2 sesiones seguidas en DUDOSO → un aviso por Telegram')}</div>`;
  return h;
}

/* exportador a Obsidian (Fase 20): corre en el PC de Ruiz y sube un latido (data/obsidian_latido.csv); aviso si falla 2 días seguidos */
function integObsidian(B) {
  let h = '<div class="sect"><h2>Exportador a Obsidian · latido</h2><span class="more">PC de Ruiz · 08:30, 23:45 y al iniciar sesión · aviso si falla 2 días seguidos</span></div>';
  if (!B || !B.ultimo) return h + `<div class="card"><p class="note" style="margin:0">${esc(B ? B.texto : 'SIN DATO')}</p></div>`;
  const cls = (e) => (e === 'OK' ? 'ok' : e === 'AVISO' || e.startsWith('PENDIENTE') ? 'par' : 'no');
  const pp = B.pendiente_aprobar;
  if (pp) h += `<div class="banner amber" style="margin:0 0 14px;border-radius:6px"><b>Exportador actualizado, pendiente de aprobar:</b> el commit ${esc(pp.commit)} cambió tools/exportar_obsidian.py (+${esc(pp.resumen && pp.resumen.anade)} −${esc(pp.resumen && pp.resumen.quita)} líneas) y el PC sigue ejecutando la versión aprobada (${esc(pp.aprobado || 'ninguna')}). Los datos se siguen descargando. Revisa el cambio y aprueba con la copia anclada: <code>python %LOCALAPPDATA%\NexoraExportador\aprobado\exportar_obsidian.py --aprobar</code> (sin argumentos: muestra el diff completo real y su hash; lee ese hash en tu terminal, no aquí, y repítelo; pide escribir APROBAR). El resumen de abajo es orientativo y no sustituye al diff completo.<pre style="white-space:pre-wrap;margin:8px 0 0;font-size:12px">${esc(((pp.resumen && pp.resumen.lineas) || []).join('\n'))}${pp.resumen && pp.resumen.truncado ? '\n…' : ''}</pre></div>`;
  if (B.alerta) h +=`<div class="banner red" style="margin:0 0 14px;border-radius:6px"><b>Exportador a Obsidian parado:</b> ${esc(B.texto)} Último latido correcto: ${esc(B.ultimo_ok || 'ninguno')}. Revisa la tarea «NEXORA exportar a Obsidian» y el log del PC.</div>`;
  h += `<div class="card"><div class="chead"><span>Último latido · ${esc(fdy(B.ultimo.fecha))} ${esc(B.ultimo.hora_utc)} UTC</span><span class="ck ${cls(B.ultimo.estado)}">${esc(B.ultimo.estado)}</span></div>`
    + `<p class="note" style="margin:6px 0">${esc(B.texto)}</p><p class="note" style="margin:0">OK = exportó sin novedades · AVISO = exportó, con algún aviso (por ejemplo una nota editada a mano, guardada como «NEXORA v2») · ERROR = no pudo exportar. Solo se registran fecha, hora y estado.</p></div>`;
  h += '<div class="card pad0 scroll" style="margin-top:12px"><table class="t stack"><thead><tr><th style="text-align:left">Fecha</th><th>Hora (UTC)</th><th>Estado</th></tr></thead><tbody>'
    + (B.historial || []).map((r) => `<tr><td data-label="Fecha" style="text-align:left">${esc(fdy(r.fecha))}</td><td data-label="Hora (UTC)">${esc(r.hora_utc)}</td><td data-label="Estado"><span class="ck ${cls(r.estado)}">${esc(r.estado)}</span></td></tr>`).join('')
    + `</tbody></table>${footIn(B.fuente, B.ultimo.fecha, null, '2 días seguidos sin una pasada OK/AVISO → un aviso por Telegram')}</div>`;
  return h;
}

/* ánimo del consumidor (U. Michigan): último dato, preliminar/final, antigüedad (ámbar > 45 días), contraste con FRED y próximo lanzamiento */
function integMichigan(B) {
  let h = '<div class="sect"><h2>Ánimo del consumidor (U. Michigan)</h2><span class="more">fuente primaria: la Universidad · FRED de respaldo</span></div>';
  if (!B || B.estado !== 'OK' || !B.ultimo) return h + `<div class="card"><p class="note" style="margin:0">SIN DATO: no hay ninguna lectura de la Universidad de Michigan ni de FRED registrada.</p></div>`;
  const u = B.ultimo, uf = B.ultimo_final, fr = B.fred, tipo = u.tipo === 'preliminar' ? 'PRELIMINAR' : 'FINAL';
  const pub = (x) => (x && x.publicado ? esc(fdy(x.publicado)) : 'SIN DATO');
  const edad = `${B.antiguedad_dias} día${B.antiguedad_dias === 1 ? '' : 's'}`;
  h += `<div class="card pad0 scroll"><table class="t stack"><thead><tr><th style="text-align:left">Dato</th><th>Valor</th><th>Tipo</th><th>Publicado el</th><th>Visto por NEXORA</th><th>Antigüedad</th></tr></thead><tbody>`
    + `<tr><td data-label="Dato" style="text-align:left"><b>${esc(u.texto)}</b> <small>Universidad de Michigan</small></td><td data-label="Valor">${esc(num(u.valor, 1))}</td><td data-label="Tipo"><span class="ck ${u.tipo === 'preliminar' ? 'sd' : 'ok'}">${tipo}</span></td><td data-label="Publicado el">${pub(u)}</td><td data-label="Visto por NEXORA">${u.visto_utc ? esc(horaAct(u.visto_utc)) : 'SIN DATO'}</td><td data-label="Antigüedad"><span class="ck ${B.ambar ? 'par' : 'ok'}">${edad}${B.ambar ? ' · ámbar' : ''}</span></td></tr>`
    + (uf && uf.periodo !== u.periodo ? `<tr><td data-label="Dato" style="text-align:left"><b>${esc(uf.texto)}</b> <small>último final</small></td><td data-label="Valor">${esc(num(uf.valor, 1))}</td><td data-label="Tipo"><span class="ck ok">FINAL</span></td><td data-label="Publicado el">${pub(uf)}</td><td data-label="Visto por NEXORA">${uf.visto_utc ? esc(horaAct(uf.visto_utc)) : 'SIN DATO'}</td><td data-label="Antigüedad">—</td></tr>` : '')
    + (fr ? `<tr><td data-label="Dato" style="text-align:left"><b>${esc(fr.texto)}</b> <small>FRED UMCSENT (respaldo)</small></td><td data-label="Valor">${esc(num(fr.valor, 1))}</td><td data-label="Tipo"><span class="ck ok">FINAL</span></td><td data-label="Publicado el">SIN DATO</td><td data-label="Visto por NEXORA">—</td><td data-label="Antigüedad"><span class="ck ${fr.antiguedad_dias > B.umbral_antiguedad_dias ? 'par' : 'ok'}">${esc(String(fr.antiguedad_dias))} días${fr.antiguedad_dias > B.umbral_antiguedad_dias ? ' · ámbar' : ''}</span></td></tr>` : '')
    + '</tbody></table>'
    + `<div class="note" style="padding:8px 16px 12px">Antigüedad = días desde el cierre del mes al que se refiere el dato (0 mientras el mes no ha terminado); ámbar si pasa de ${esc(String(B.umbral_antiguedad_dias))} días. `
    + `${fr && fr.meses_de_retraso > 0 ? `FRED va ${esc(String(fr.meses_de_retraso))} mes${fr.meses_de_retraso > 1 ? 'es' : ''} por detrás (publica este índice con retraso por licencia). ` : ''}`
    + `${fr && fr.coincide === true ? 'FRED coincide con la Universidad en el último mes que tienen en común. ' : fr && fr.coincide === false ? '<b>FRED no coincide con la Universidad: manda la Universidad.</b> ' : ''}`
    + `${B.proximo ? `Próximo lanzamiento anunciado: ${esc(B.proximo.texto)} el ${esc(fdy(B.proximo.fecha))}${B.proximo.hora_et ? ' a las ' + esc(B.proximo.hora_et) + ' ET' : ''} (${esc(B.proximo.fuente || '')}). ` : 'Próximo lanzamiento: SIN DATO (la Universidad lo anuncia en su portada tras cada publicación). '}`
    + `El vigilante avisa si un lanzamiento (preliminar o final) no está registrado 2 h después. La web de la Universidad no indica la fecha de un dato ya publicado: solo se muestra si NEXORA la anotó antes. ${B.ultima_descarga_utc ? 'Última descarga: ' + esc(horaAct(B.ultima_descarga_utc + ' UTC')) + '.' : ''}</div>`
    + footIn('Universidad de Michigan (sca.isr.umich.edu) · FRED UMCSENT', false, 'https://www.sca.isr.umich.edu/tables.html', 'antigüedad en ámbar si > 45 días') + '</div>';
  return h;
}

/* inventarios de petróleo de la EIA: última semana registrada, cuándo salió, antigüedad (ámbar > 10 días) y próximo informe */
function integEia(B) {
  if (!B) return '';
  let h = '<div class="sect"><h2>Inventarios de petróleo (EIA)</h2><span class="more">informe semanal · miércoles 10:30 ET salvo festivos</span></div>';
  if (B.estado !== 'OK') return h + `<div class="card"><p class="note" style="margin:0">SIN DATO: NEXORA aún no ha registrado ningún informe de la EIA.${B.error ? ' Último error: ' + esc(B.error) : ''}</p></div>`;
  const P = B.productos || {}, mb = (k) => (P[k] == null ? 'SIN DATO' : num(P[k] / 1000, 1) + ' Mb');
  h += `<div class="card pad0 scroll"><table class="t stack"><thead><tr><th style="text-align:left">Semana al</th><th>Publicado el</th><th>Visto por NEXORA</th><th>Antigüedad</th><th>Crudo</th><th>Gasolina</th><th>Destilados</th></tr></thead><tbody>`
    + `<tr><td data-label="Semana al" style="text-align:left"><b>${esc(fdy(B.semana))}</b></td><td data-label="Publicado el">${esc(fdy(B.publicado))} ${esc(B.hora_et || '')} ET</td><td data-label="Visto por NEXORA">${B.visto_utc ? esc(horaAct(B.visto_utc)) : 'SIN DATO'}</td>`
    + `<td data-label="Antigüedad"><span class="ck ${B.ambar ? 'par' : 'ok'}">${esc(String(B.antiguedad_dias))} día${B.antiguedad_dias === 1 ? '' : 's'}${B.ambar ? ' · ámbar' : ''}</span></td><td data-label="Crudo">${mb('crudo')}</td><td data-label="Gasolina">${mb('gasolina')}</td><td data-label="Destilados">${mb('destilados')}</td></tr></tbody></table>`
    + `<div class="note" style="padding:8px 16px 12px">Antigüedad = días desde que la EIA publicó el informe de esa semana; ámbar si pasan más de ${esc(String(B.umbral_dias))} días sin un informe nuevo. ${B.proximo ? `Próximo informe: ${esc(fdy(B.proximo.fecha))} a las ${esc(B.proximo.hora_et)} ET (semana al ${esc(fdy(B.proximo.semana))}), calendario oficial de la EIA. ` : ''}El vigilante avisa si el informe no está registrado 2 h después. ${B.ultima_descarga_utc ? 'Última descarga: ' + esc(horaAct(B.ultima_descarga_utc + ' UTC')) + '.' : ''}</div>`
    + footIn('EIA · Weekly Petroleum Status Report (ir.eia.gov/wpsr/table1.csv)', false, 'https://www.eia.gov/petroleum/supply/weekly/schedule.php', 'antigüedad en ámbar si > 10 días') + '</div>';
  return h;
}

Object.assign(window.EXTRA_PAGES, { integridad: pageIntegridad });
