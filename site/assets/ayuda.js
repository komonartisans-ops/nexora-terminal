/* NEXORA TERMINAL · capa de comprensión: guía «Cómo leer NEXORA» (#/guia), iconos ⓘ en cada bloque y semáforo coherente con leyenda fija.
   Solo texto y presentación: no calcula ni cambia ningún dato, umbral ni regla. Todos los textos viven en site/data/ayuda.json.
   Todo texto dinámico pasa por esc(). */
'use strict';

const AY = { d: null, p: null, keys: [], pop: null, ctx: null };
const ayNz = (s) => String(s || '').toLowerCase().replace(/\s+/g, ' ').trim();
const ayRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

function ayCargar() {
  if (!AY.p) {
    AY.p = fetch('data/ayuda.json?v=' + Date.now(), { cache: 'no-store' }).then((r) => (r.ok ? r.json() : null)).then((j) => {
      AY.d = j;
      if (j) AY.keys = Object.keys(j.bloques || {}).sort((a, b) => b.length - a.length);
      return j;
    }).catch(() => null);
  }
  return AY.p;
}

/* texto de ayuda de un bloque: 1) clave del título, 2) glosario por palabra clave, 3) texto genérico de la página */
function ayBuscar(titulo, pagina) {
  const d = AY.d;
  if (!d) return null;
  const t = ayNz(titulo);
  for (const k of AY.keys) if (t.startsWith(k)) return { v: d.bloques[k], g: false, tipo: 'bloque' };
  for (const g of d.glosario || []) {
    for (const c of g.claves || []) {
      const re = new RegExp('(^|[^a-záéíóúñ0-9+])' + ayRe(c.toLowerCase()) + '($|[^a-záéíóúñ0-9])');
      if (re.test(t)) return { v: [g.def, g.analogia, 'Está en el glosario de la guía.'], g: true, termino: g.termino, tipo: 'glosario' };
    }
  }
  const p = (d.paginas || []).find((x) => x.id === pagina);
  return p ? { v: [p.generico || p.titulo, 'Léela de arriba abajo: primero «Lo esencial», luego el detalle.', 'Cada cifra lleva su fuente y su fecha; si falta un dato aparece SIN DATO.'], g: false, tipo: 'pagina' } : null;
}
const AY_ET = ['Qué es', 'Cómo se lee', 'Por qué importa'];
function ayHtml(r) {
  return r.v.map((x, i) => `<p><b>${r.g ? ['Definición', 'Analogía', 'Ver más'][i] : AY_ET[i]}</b> ${esc(x)}</p>`).join('') + '<p class="ay-mas"><a href="#/guia">Abrir la guía «Cómo leer NEXORA»</a></p>';
}

/* ---------------------------------------------------------------- iconos ⓘ y ventana de ayuda */
const AY_SEL = '#app .sect h2, #app .card h3, #app .card .chead > span:first-child, #app .card .lab, #app .card .nm';
const ayPagina = () => (location.hash.replace(/^#\//, '') || 'resumen').split('?')[0];
function ayCerrar() { if (AY.pop) { AY.pop.hidden = true; const b = document.querySelector('.info[aria-expanded="true"]'); if (b) b.setAttribute('aria-expanded', 'false'); } }
function ayAbrir(btn) {
  if (!AY.pop) {
    AY.pop = document.createElement('div');
    AY.pop.id = 'ay-pop'; AY.pop.setAttribute('role', 'dialog'); AY.pop.hidden = true;
    document.body.appendChild(AY.pop);
  }
  const ya = btn.getAttribute('aria-expanded') === 'true';
  ayCerrar();
  if (ya) return;
  const r = ayBuscar(btn.dataset.t, ayPagina());
  AY.pop.innerHTML = `<button class="ay-x" aria-label="Cerrar">×</button><div class="ay-t">${esc(btn.dataset.t)}</div>${r ? ayHtml(r) : '<p>Sin texto de ayuda para este bloque.</p>'}`;
  AY.pop.hidden = false; btn.setAttribute('aria-expanded', 'true');
  if (window.innerWidth <= 600) { AY.pop.style.cssText = ''; AY.pop.classList.add('sheet'); return; }
  AY.pop.classList.remove('sheet');
  const b = btn.getBoundingClientRect(), w = Math.min(340, window.innerWidth - 24);
  AY.pop.style.width = w + 'px';
  AY.pop.style.left = Math.max(12, Math.min(window.scrollX + b.left - 8, window.scrollX + window.innerWidth - w - 12)) + 'px';
  AY.pop.style.top = (window.scrollY + b.bottom + 8) + 'px';
}
document.addEventListener('click', (e) => {
  const b = e.target.closest('.info');
  if (b) { e.preventDefault(); e.stopPropagation(); ayAbrir(b); return; }
  if (e.target.closest('.ay-x') || (AY.pop && !AY.pop.hidden && !e.target.closest('#ay-pop'))) ayCerrar();
});
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') ayCerrar(); });
window.addEventListener('hashchange', ayCerrar);

function ayInyectar() {
  if (!AY.d || ayPagina() === 'guia') return;
  document.querySelectorAll(AY_SEL).forEach((el) => {
    if (el.querySelector(':scope > .info')) return;
    const t = (el.textContent || '').trim().replace(/\s+/g, ' ');
    if (!t || t.length > 90) return;
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'info'; b.textContent = 'ⓘ'; b.dataset.t = t; b.setAttribute('aria-label', 'Ayuda: ' + t); b.setAttribute('aria-expanded', 'false');
    el.appendChild(b);
  });
}

/* ---------------------------------------------------------------- semáforo: solo cambia la CLASE de etiquetas que ya existen (no su cálculo) */
const AY_SEM = [                      // el orden importa: lo más específico primero
  ['sd', /^(SIN DATO|SIN TESIS|MUESTRA INSUFICIENTE|PENDIENTE\b(?! DE VALIDAR)|NO PUNTUABLE|SOLO REGISTRO|SIN MEDIDAS|SIN FOTO|SIN HORA|SIN HISTÓRICO|BACKFILL|SIN EVENTO)/],
  ['par', /^(MIXTO|VIGILAR|PARCIAL|NEUTRAL|ELEVADO|CONTRADICCIÓN|PENDIENTE DE VALIDAR|SECUNDARIO)/],
  ['no', /^(DESFAVORABLE|ALERTA|FALLO|EN CONTRA|BAJISTA|TENSIÓN|ESTRÉS|RECESIÓN|RIESGO ALTO|INVERSIÓN|MUY DÉBIL|DÉBIL$)/],
  ['ok', /^(FAVORABLE|CONFIRMADO|SE CONFIRMA|ACIERTO|A FAVOR|ALCISTA|FUERTE|SIN TENSIÓN)/],
];
const AY_TAG = { ok: 'alc', par: 'deb', no: 'baj', sd: 'sin' };
function ayColorear() {
  document.querySelectorAll('#app .ck:not([data-sem]), #app .tag:not([data-sem])').forEach((el) => {
    el.dataset.sem = '1';
    const t = (el.textContent || '').trim().toUpperCase();
    const r = AY_SEM.find(([, re]) => re.test(t));
    if (/^(ALCISTA|BAJISTA)/.test(t)) el.classList.add(/DÉBIL/.test(t) ? 'int-deb' : 'int-fue');   // intensidad: el color sigue siendo la dirección
    if (!r) return;
    if (el.classList.contains('ck')) { el.classList.remove('ok', 'no', 'par', 'sd'); el.classList.add(r[0]); }
    else if (!(r[0] === 'sd' && el.classList.contains('sd'))) { el.classList.remove('alc', 'baj', 'deb', 'sin', 'sd'); el.classList.add(AY_TAG[r[0]]); }
  });
}
function ayLeyenda() {
  const el = document.getElementById('leyenda');
  if (!el || !AY.d) return;
  el.innerHTML = '<span class="ley-t">Colores</span>' + AY.d.semaforo.map((s) => `<span class="ley"><i class="${esc(s.clase)}"></i><b>${esc(s.nombre)}</b> ${esc(s.texto)}</span>`).join('') + (AY.d.semaforo_nota ? `<span class="ley-n">${esc(AY.d.semaforo_nota)} ${esc(AY.d.semaforo_intensidad || '')}</span>` : '') + '<a class="ley-g" href="#/guia">Cómo leer NEXORA</a>';
}

let ayTimer = null;
function ayPasada() { ayInyectar(); ayColorear(); }
let ayHecho = false;
function ayIniciar() {
  if (ayHecho) return;
  ayHecho = true;
  ayCargar().then(() => {
    ayLeyenda(); ayPasada();
    const app = document.getElementById('app');
    if (app) new MutationObserver(() => { clearTimeout(ayTimer); ayTimer = setTimeout(ayPasada, 60); }).observe(app, { childList: true, subtree: true });
  });
}

/* ================================================================== GUÍA #/guia */
function ayEjemplo(id, C) {
  if (!C) return null;
  try {
    const tes = Object.fromEntries(((C.tesis || {}).tesis_por_activo || []).map((t) => [t.activo, t.etiqueta]));
    const m = (C.mercado || {}).activos || {};
    const ej = {
      resumen: () => `Hoy: Oro ${tes.Oro}, Nasdaq 100 ${tes['Nasdaq 100']}, S&P 500 ${tes['S&P 500']}, Bitcoin ${tes.Bitcoin}.`,
      regimen: () => `Régimen actual: ${C.regimen_macro.cuadrante}; riesgo ${C.regimen_macro.riesgo}.`,
      ciclo: () => `Fase actual: ${C.ciclo.fase}; señales encendidas: ${C.ciclo.senales_adelantadas_encendidas} de ${C.ciclo.senales_adelantadas_total}.`,
      bancos: () => C.fedwatch_y_tipos.resumen,
      mapa: () => `En 12 meses: ${C.bancos_centrales_mundo.contador_12m.sube} bancos suben tipos, ${C.bancos_centrales_mundo.contador_12m.baja} los bajan y ${C.bancos_centrales_mundo.contador_12m.sin_cambios} no los cambian.`,
      agenda: () => { const a = ((C.agenda || {}).hoy || []).filter((e) => e.importancia === 'ALTA'); return a.length ? `Hoy, importancia alta: ${a.map((e) => `${e.evento} (${e.hora_madrid || 'sin hora'} Madrid)`).join('; ')}.` : 'Hoy no hay datos de importancia alta en la agenda.'; },
      eventos: () => `Último evento: ${C.reaccion_a_eventos.ultimo_evento.evento}; clasificación en T+5: ${C.reaccion_a_eventos.ultimo_evento.clase_t5}.`,
      tono: () => `Estado del bloque de tono: ${C.tono_bancos_centrales.estado_bloque} (no distingue del azar si dice «secundario»).`,
      liquidez: () => `Lectura actual: ${C.liquidez.lectura}; checklist ${C.liquidez.checklist.cumple} de ${C.liquidez.checklist.total} condiciones cumplidas.`,
      divisas: () => C.sesgo_divisas.resumen,
      posicionamiento: () => { const k = C.posicionamiento_cot.contratos[1]; return `${k.contrato}: los gestores de activos están en «${k.gestores.estado}» (percentil ${k.gestores.percentil_3a} a 3 años), informe del ${C.posicionamiento_cot.fecha_informe}.`; },
      skew: () => `SKEW ${String(C.riesgo_de_cola_skew.valor).replace('.', ',')} en zona ${C.riesgo_de_cola_skew.zona} (relativa: ${C.riesgo_de_cola_skew.zona_relativa.zona_relativa}).`,
      gamma: () => `Gamma de NQ: ${C.gamma_indices.indices.NQ.regimen_gamma.toLowerCase()}; de ES: ${C.gamma_indices.indices.ES.regimen_gamma.toLowerCase()}.`,
      semis: () => `Escenario de hoy: ${C.semis_vs_software.escenario_hoy}.`,
      oro: () => `Tesis del oro: ${tes.Oro}. El oro cotiza a ${num(m.oro.valor, 0)} $ (${m.oro.fecha}).`,
      indices: () => `VIX en ${num(m.vix.valor, 1)} y MOVE en ${num(m.move.valor, 0)} (${m.vix.fecha}).`,
      cripto: () => `ETF de bitcoin el ${C.etf_flujos_btc_eth.btc.ultimo_dia}: ${num(C.etf_flujos_btc_eth.btc.total_musd, 1)} M$ netos (positivo = entra dinero).`,
      marcador: () => `El marcador tiene ${C.marcador.n_senales} señales registradas; mira siempre n y la tasa base antes de fiarte.`,
      noticias: () => `Última actualización correcta de las noticias: ${C.frescura.noticias.ultimo_ok_utc}.`,
      calendario: () => { const e = C.calendario.proximos_14_dias[0]; return `Próximo dato: ${e.evento} el ${fdy(e.fecha)} (${e.hora_madrid || 'hora sin confirmar'} Madrid), importancia ${e.importancia}.`; },
      publicados: () => { const x = C.calendario.ultimos_publicados[0]; return `${x.serie}: ${num(x.valor, 2)} (periodo ${x.periodo}), anterior ${num(x.anterior, 2)}; publicado el ${fdy(x.fecha_publicacion)}.`; },
      tesis: () => `Hoy la tesis del Nasdaq 100 es «${tes['Nasdaq 100']}»: el registro la guarda y la comprueba después a 1, 5 y 20 sesiones.`,
    };
    return ej[id] ? ej[id]() : null;
  } catch (e) { return null; }
}
const AY_EJ_PERSONAL = {
  watchlists: 'Ejemplo: creas la lista «Mi vigilancia» con oro y S&P 500; la web guarda la lista solo en tu navegador.',
  diario: 'Ejemplo: apuntas «Largo, Nasdaq 100, +125 $» a las 15:35 y la web guarda qué decían tesis, régimen y agenda en ese momento.',
  operativa: 'Ejemplo: tras 40 operaciones ves si ganaste más a favor de la tesis que en contra. Con menos de 20 por grupo, no concluyas.',
};

function ayGuiaHtml(d, C) {
  const G = d.guia;
  const pg = (id) => (PAGES.find((p) => p.id === id) || {}).t || id;
  let h = '<div class="grid g2">';
  h += `<div class="card"><div class="chead"><span>Qué es NEXORA</span></div><ol class="gl-l">${G.que_es.map((x) => `<li>${esc(x)}</li>`).join('')}</ol></div>`;
  h += `<div class="card gl-no"><div class="chead"><span>Para qué NO sirve</span></div><ul class="gl-l">${G.no_sirve.map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div></div>`;
  h += `<div class="note" style="margin-top:10px">Colores de toda la web: ${d.semaforo.map((s) => `<span class="ley"><i class="${esc(s.clase)}"></i><b>${esc(s.nombre)}</b> = ${esc(s.texto)}</span>`).join(' ')}. ${esc(d.semaforo_nota || '')} ${esc(d.semaforo_intensidad || '')}</div>`;
  h += '<div class="sect"><h2>El flujo en un vistazo</h2><span class="more">pulsa cada paso para ir a esa página</span></div><div class="flujo">';
  h += G.flujo.map((f, i) => `<a class="paso" href="#/${esc(f.pagina)}"><span class="n">${f.paso}</span><b>${esc(f.titulo)}</b><small>${esc(f.texto)}</small></a>${i < G.flujo.length - 1 ? '<span class="flecha" aria-hidden="true">→</span>' : ''}`).join('');
  h += '</div>';
  h += '<div class="sect"><h2>Un día con NEXORA</h2><span class="more">qué mirar y cuándo</span></div><div class="card"><div class="dia">';
  h += G.dia.map((x) => `<div class="mom"><div class="hh">${esc(x.hora)}</div><div><b>${esc(x.titulo)}</b><p>${esc(x.texto)}</p></div></div>`).join('') + '</div></div>';
  h += '<div class="sect"><h2>Una tarjeta por página</h2><span class="more">qué responde, cómo leerla y un ejemplo de hoy</span></div><div class="grid g3 gl-pag">';
  h += d.paginas.map((p) => {
    const ej = AY_EJ_PERSONAL[p.id] || ayEjemplo(p.id, C) || 'SIN DATO en este momento (se rellena cuando el contexto está disponible).';
    return `<div class="card gl-card"><div class="chead"><span><a href="#/${esc(p.id)}">${esc(p.titulo)}</a></span></div><p class="q">${esc(p.pregunta)}</p>
      <p><b>En 10 segundos</b> ${esc(p.diez)}</p><p><b>Ejemplo de hoy</b> ${esc(ej)}</p><p class="fr"><b>Se actualiza</b> ${esc(p.frecuencia)}</p></div>`;
  }).join('') + '</div>';
  h += '<div class="sect"><h2>Glosario</h2><span class="more">' + d.glosario.length + ' términos en palabras sencillas</span></div>';
  h += '<div class="card"><input id="gl-q" class="gl-q" placeholder="Buscar un término…" autocomplete="off" aria-label="Buscar en el glosario"><dl class="gl" id="gl">';
  h += d.glosario.map((g) => `<div class="gt" data-b="${esc(ayNz(g.termino + ' ' + (g.claves || []).join(' ') + ' ' + g.def))}"><dt>${esc(g.termino)}</dt><dd>${esc(g.def)}<small>Como si… ${esc(g.analogia)}</small></dd></div>`).join('');
  h += '</dl></div>';
  h += '<div class="sect"><h2>Errores típicos de lectura</h2><span class="more">los que más cuestan</span></div><div class="grid g2">';
  h += G.errores.map((e) => `<div class="card gl-err"><b>${esc(e.titulo)}</b><p>${esc(e.texto)}</p></div>`).join('') + '</div>';
  h += '<div class="note">Hecho, interpretación, hipótesis y escenario van siempre separados en NEXORA. Nada de esto es una recomendación de compra o venta.</div>';
  return h;
}

function pageGuia() {
  const h = head('Guía', 'Cómo leer NEXORA', 'Para quien empieza de cero: qué es, para qué sirve, cómo se lee cada página y qué significan las palabras raras.',
    'Texto fijo en <a class="src" href="data/ayuda.json">ayuda.json</a>; los ejemplos usan los datos de hoy.') + '<div id="gl-root"><div class="empty" style="height:160px">CARGANDO LA GUÍA…</div></div>';
  MOUNT.push(async () => {
    const root = document.getElementById('gl-root');
    if (!root) return;
    const d = await ayCargar();
    if (!d) { root.innerHTML = noData('Guía (ayuda.json)'); return; }
    try { const r = await fetch('data/contexto.json?v=' + Date.now(), { cache: 'no-store' }); AY.ctx = r.ok ? await r.json() : null; } catch (e) { AY.ctx = null; }
    if (document.getElementById('gl-root') !== root) return;
    root.innerHTML = ayGuiaHtml(d, AY.ctx);
    const q = document.getElementById('gl-q');
    if (q) q.addEventListener('input', () => { const t = ayNz(q.value); document.querySelectorAll('#gl .gt').forEach((e) => { e.hidden = !!t && !e.dataset.b.includes(t); }); });
    ayColorear();
  });
  return h;
}
Object.assign(window.EXTRA_PAGES, { guia: pageGuia });
window.addEventListener('DOMContentLoaded', ayIniciar);
if (document.readyState !== 'loading') ayIniciar();
