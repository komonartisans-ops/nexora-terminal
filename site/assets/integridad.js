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
      <td data-label="Próximo dato" style="text-align:left">${x.proximo ? `${esc(x.proximo.texto)}<small>${x.proximo.hora_madrid ? esc(x.proximo.hora_madrid) + ' Madrid · ' : ''}${esc(x.proximo.fuente || '')}</small>${x.proximo.otra_fuente ? `<small style="color:var(--amber)">Calendario oficial: ${esc(x.proximo.otra_fuente.texto)} (${esc(x.proximo.otra_fuente.fuente)})</small>` : ''}` : (ultimo(x, I.publicaciones.indexOf(x), I.publicaciones) ? '<span class="sd-val">SIN DATO</span><small>fuera del calendario conocido</small>' : '—')}</td>
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
  if (disc.length) h += `<div class="banner red" style="margin:0 0 14px;border-radius:6px"><b>DISCREPANCIA abierta:</b> ${disc.map((d) => `${esc(d.serie)} ${esc(d.periodo.slice(0, 7))} (${esc(d.tipo.toLowerCase())}): FRED ${esc(d.fred_valor)} frente a ${esc(d.primaria)} ${esc(d.primaria_valor)}${d.dif_pct ? ' (' + esc(num(+d.dif_pct, 3)) + ' %)' : ''}`).join(' · ')}. Manda la fuente primaria.</div>`;
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
  const V = I.vigilante || {}, S = I.segunda_fuente || {};
  h += '<div class="sect"><h2>Vigilante y segunda fuente</h2><span class="more">cómo se comprueba cada dato</span></div><div class="grid g2"><div class="card"><div class="chead"><span>Vigilante de publicaciones</span></div>'
    + `<p class="note" style="margin:6px 0">Regla: ${esc(V.regla || '')}. Un aviso por dato.</p><p class="note" style="margin:0">${V.avisos ? V.avisos + ' aviso(s) enviado(s) hasta ahora.' : 'Ningún aviso enviado todavía: no ha faltado ningún dato.'}</p></div>`
    + `<div class="card"><div class="chead"><span>Segunda fuente</span></div><p class="note" style="margin:6px 0"><b>BLS</b> (IPC, IPC subyacente, IPP): ${esc(S.BLS || '')}.</p><p class="note" style="margin:0"><b>BEA</b> (PIB, PCE): ${esc(S.BEA || '')}</p>${S.bls_ultimo_error ? `<p class="note" style="margin:4px 0 0">Último error de BLS: ${esc(S.bls_ultimo_error)}</p>` : ''}${S.bea_ultimo_error ? `<p class="note" style="margin:4px 0 0">Último error de BEA: ${esc(S.bea_ultimo_error)}</p>` : ''}</div></div>`;
  return h;
}

Object.assign(window.EXTRA_PAGES, { integridad: pageIntegridad });
