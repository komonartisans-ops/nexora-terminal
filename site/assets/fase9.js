/* NEXORA TERMINAL · fase 9: agenda oficial (hoy y próximos 7 días) y tabla de importancia por tipo de evento. Todo texto pasa por esc(). */
'use strict';

function pageAgenda() {
  const A = D.agenda;
  const stamp = `Actualizado: ${A && A.generado_utc ? esc(A.generado_utc) : 'SIN DATO'} <span class="tag sin" style="margin-left:6px">CALENDARIOS OFICIALES</span>`;
  let h = head('Análisis', 'Agenda', 'Qué se publica hoy y en los próximos 7 días, con la hora de Nueva York y de Madrid, y la importancia fija que NEXORA asigna a cada tipo de dato. El monitor de reacciones vigila todos los de importancia alta.', stamp);
  h += fallo('agenda');
  if (A && A.generado_utc && A.generado_utc.slice(0, 10) !== hoyISO() && stampDate(A.generado_utc) && (Date.now() - stampDate(A.generado_utc)) > 36e5 * 3) h += `<div class="banner amber" style="margin:0 0 14px;border-radius:6px">Esta agenda se generó el ${esc(horaAct(A.generado_utc))}: «Hoy» puede no ser el día de hoy. Se regenera cada hora; si ves este aviso, revisa la salud de los workflows.</div>`;
  if (!A || !A.agenda) return h + noData('Calendarios oficiales (FRED, Fed, ISM, BCE, BoJ, TreasuryDirect)');
  const B = A.agenda;
  const fila = (e) => `<tr><td data-label="Día">${esc(e.dia || '')} ${esc(fdy(e.fecha))}</td><td data-label="Madrid">${esc(e.hora_madrid || '—')}</td><td data-label="NY (ET)">${esc(e.hora_ny || '—')}</td><td data-label="Evento" style="text-align:left;white-space:normal">${esc(e.evento)}${e.nota ? ` <small>${esc(e.nota)}</small>` : ''}</td><td data-label="Importancia"><span class="ck ${e.importancia === 'ALTA' ? 'no' : 'par'}">${esc(e.importancia)}</span></td></tr>`;
  const alt = B.hoy.filter((e) => e.importancia === 'ALTA');
  h += essential(alt.length ? `Hoy, de importancia alta: ${alt.map((e) => `${esc(e.evento)} (${esc(e.hora_madrid || 'hora sin confirmar')} Madrid)`).join('; ')}.` : 'Hoy sin datos de importancia alta.',
    'Los de importancia alta se registran minuto a minuto en <a href="#/eventos">Reacción a eventos</a>; una fase queda «contaminada» si otro dato alto cae entre el dato y esa fase.',
    `${B.proximos_7_dias.filter((e) => e.importancia === 'ALTA').length} de importancia alta en los próximos 7 días.`, 'Próximos 7 días');
  h += '<div class="sect"><h2>Hoy</h2></div><div class="card pad0 scroll"><table class="t stack"><thead><tr><th>Día</th><th>Madrid</th><th>NY (ET)</th><th>Evento</th><th>Imp.</th></tr></thead><tbody>';
  h += B.hoy.length ? B.hoy.map(fila).join('') : '<tr><td colspan="5" style="text-align:left;color:var(--dim)">Sin eventos de importancia alta o media.</td></tr>';
  h += '</tbody></table></div><div class="sect"><h2>Próximos 7 días</h2></div><div class="card pad0 scroll"><table class="t stack"><thead><tr><th>Día</th><th>Madrid</th><th>NY (ET)</th><th>Evento</th><th>Imp.</th></tr></thead><tbody>';
  h += B.proximos_7_dias.length ? B.proximos_7_dias.map(fila).join('') : '<tr><td colspan="5" style="text-align:left;color:var(--dim)">SIN DATO</td></tr>';
  h += `</tbody></table>${footIn(B.fuente, B.generado_utc && B.generado_utc.slice(0, 10), null, 'horas oficiales convertidas con cambio de horario')}</div>`;
  h += '<div class="sect"><h2>Importancia por tipo de evento</h2><span class="more">fija; no cambia según el dato</span></div><div class="card pad0 scroll"><table class="t"><thead><tr><th>Tipo</th><th>Evento</th><th>Organismo</th><th>Hora ET típica</th><th>Imp.</th><th>Fuente</th></tr></thead><tbody>';
  h += (A.tabla_importancia || []).map((t) => `<tr><td data-label="Tipo" style="text-align:left"><b>${esc(t.tipo)}</b></td><td data-label="Evento" style="text-align:left;white-space:normal">${esc(t.evento)}</td><td data-label="Organismo">${esc(t.organismo)}</td><td data-label="Hora ET típica">${esc(t.hora_ny_tipica || '—')}</td><td data-label="Importancia"><span class="ck ${t.importancia === 'ALTA' ? 'no' : t.importancia === 'MEDIA' ? 'par' : 'sd'}">${esc(t.importancia)}</span></td><td data-label="Fuente"><small>${esc(t.fuente)}</small></td></tr>`).join('');
  h += '</tbody></table></div>';
  h += `<div class="note">${esc(A.contaminacion || '')} Sin consenso de analistas (es de pago): solo fechas y horas oficiales.</div>`;
  /* salud de los workflows */
  const S = D.salud;
  h += '<div class="sect"><h2>Salud de los workflows</h2>' + (S ? `<span class="more">${esc(S.generado_utc)}</span>` : '') + '</div>';
  if (!S || !S.workflows) h += noData('API de GitHub Actions');
  else {
    h += S.actualizar_parada ? `<div class="note" style="border-left:3px solid var(--neg);padding-left:10px"><b>actualizar lleva más de ${esc(S.umbral_actualizar_h)} h sin ejecutarse</b> (aviso por Telegram enviado).</div>` : '';
    h += '<div class="card pad0 scroll"><table class="t"><thead><tr><th>Workflow</th><th>Última ejecución (UTC)</th><th>Hace</th><th>Resultado</th><th>Hoy: hechas / esperadas</th><th>Fallidas hoy</th><th>Horario esperado</th></tr></thead><tbody>';
    h += S.workflows.map((w) => {
      const ok = w.esperadas_hasta_ahora === 0 || (w.hoy_ejecutadas || 0) >= w.esperadas_hasta_ahora * 0.8;
      return `<tr><td style="text-align:left"><b>${esc(w.workflow)}</b></td><td>${esc(w.ultima_utc || 'SIN DATO')}</td><td>${w.horas_desde_ultima != null ? num(w.horas_desde_ultima, 1) + ' h' : '—'}</td><td>${esc(w.ultima_estado || '—')}</td>
        <td><span class="ck ${ok ? 'ok' : 'no'}">${w.hoy_ejecutadas != null ? esc(w.hoy_ejecutadas) : '—'} / ${esc(w.esperadas_hasta_ahora)}</span></td><td>${w.hoy_fallidas != null ? esc(w.hoy_fallidas) : '—'}</td><td style="text-align:left;white-space:normal"><small>${esc(w.horario_esperado)}</small>${w.error ? ` <small style="color:var(--neg)">${esc(w.error)}</small>` : ''}</td></tr>`;
    }).join('');
    h += `</tbody></table>${footIn('API de GitHub Actions', S.generado_utc && S.generado_utc.slice(0, 10), null, 'verde si hechas ≥ 80 % de las esperadas hasta ahora')}</div><div class="note">${esc(S.nota || '')}</div>`;
  }
  return h + errores(A.errores);
}

Object.assign(window.EXTRA_PAGES, { agenda: pageAgenda });
