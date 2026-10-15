/* NEXORA TERMINAL · fase 9: agenda oficial (hoy y próximos 7 días) y tabla de importancia por tipo de evento. Todo texto pasa por esc(). */
'use strict';

function pageAgenda() {
  const A = D.agenda;
  const stamp = `Actualizado: ${A && A.generado_utc ? esc(A.generado_utc) : 'SIN DATO'} <span class="tag sin" style="margin-left:6px">CALENDARIOS OFICIALES</span>`;
  let h = head('Análisis', 'Agenda', 'Qué se publica hoy y en los próximos 7 días, con la hora de Nueva York y de Madrid, y la importancia fija que NEXORA asigna a cada tipo de dato. El monitor de reacciones vigila todos los de importancia alta.', stamp);
  h += fallo('agenda');
  if (!A || !A.agenda) return h + noData('Calendarios oficiales (FRED, Fed, ISM, BCE, BoJ, TreasuryDirect)');
  const B = A.agenda;
  const fila = (e) => `<tr><td>${esc(e.dia || '')} ${esc(fdy(e.fecha))}</td><td>${esc(e.hora_madrid || '—')}</td><td>${esc(e.hora_ny || '—')}</td><td style="text-align:left;white-space:normal">${esc(e.evento)}${e.nota ? ` <small>${esc(e.nota)}</small>` : ''}</td><td><span class="ck ${e.importancia === 'ALTA' ? 'no' : 'par'}">${esc(e.importancia)}</span></td></tr>`;
  const alt = B.hoy.filter((e) => e.importancia === 'ALTA');
  h += essential(alt.length ? `Hoy, de importancia alta: ${alt.map((e) => `${esc(e.evento)} (${esc(e.hora_madrid || 'hora sin confirmar')} Madrid)`).join('; ')}.` : 'Hoy sin datos de importancia alta.',
    'Los de importancia alta se registran minuto a minuto en <a href="#/eventos">Reacción a eventos</a>; una fase queda «contaminada» si otro dato alto cae entre el dato y esa fase.',
    `${B.proximos_7_dias.filter((e) => e.importancia === 'ALTA').length} de importancia alta en los próximos 7 días.`, 'Próximos 7 días');
  h += '<div class="sect"><h2>Hoy</h2></div><div class="card pad0 scroll"><table class="t"><thead><tr><th>Día</th><th>Madrid</th><th>NY (ET)</th><th>Evento</th><th>Imp.</th></tr></thead><tbody>';
  h += B.hoy.length ? B.hoy.map(fila).join('') : '<tr><td colspan="5" style="text-align:left;color:var(--dim)">Sin eventos de importancia alta o media.</td></tr>';
  h += '</tbody></table></div><div class="sect"><h2>Próximos 7 días</h2></div><div class="card pad0 scroll"><table class="t"><thead><tr><th>Día</th><th>Madrid</th><th>NY (ET)</th><th>Evento</th><th>Imp.</th></tr></thead><tbody>';
  h += B.proximos_7_dias.length ? B.proximos_7_dias.map(fila).join('') : '<tr><td colspan="5" style="text-align:left;color:var(--dim)">SIN DATO</td></tr>';
  h += `</tbody></table>${footIn(B.fuente, B.generado_utc && B.generado_utc.slice(0, 10), null, 'horas oficiales convertidas con cambio de horario')}</div>`;
  h += '<div class="sect"><h2>Importancia por tipo de evento</h2><span class="more">fija; no cambia según el dato</span></div><div class="card pad0 scroll"><table class="t"><thead><tr><th>Tipo</th><th>Evento</th><th>Organismo</th><th>Hora ET típica</th><th>Imp.</th><th>Fuente</th></tr></thead><tbody>';
  h += (A.tabla_importancia || []).map((t) => `<tr><td style="text-align:left"><b>${esc(t.tipo)}</b></td><td style="text-align:left;white-space:normal">${esc(t.evento)}</td><td>${esc(t.organismo)}</td><td>${esc(t.hora_ny_tipica || '—')}</td><td><span class="ck ${t.importancia === 'ALTA' ? 'no' : t.importancia === 'MEDIA' ? 'par' : 'sd'}">${esc(t.importancia)}</span></td><td><small>${esc(t.fuente)}</small></td></tr>`).join('');
  h += '</tbody></table></div>';
  h += `<div class="note">${esc(A.contaminacion || '')} Sin consenso de analistas (es de pago): solo fechas y horas oficiales.</div>`;
  return h + errores(A.errores);
}

Object.assign(window.EXTRA_PAGES, { agenda: pageAgenda });
