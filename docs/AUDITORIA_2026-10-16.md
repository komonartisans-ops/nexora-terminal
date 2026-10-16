# Auditoría NEXORA Terminal · 16-oct-2026

Alcance: datos (todas las páginas y `site/data/*.json`), visual (23 páginas × 375/768/1440 px, carga directa por URL en el sitio publicado), funcionamiento (Actions, cron-job.org, salud, Telegram, diario, monitor de reacciones) y seguridad (repo público e historial).
Método: Fase 1 solo lectura → Fase 2 arreglos (un commit por tema) → Fase 3 re-verificación con la misma prueba que detectó cada fallo.
Reglas respetadas: no se tocaron reglas congeladas (reacciones v3), criterios CRITERIO NEXORA ni umbrales; no se modificó cron-job.org; no se borró ningún dato histórico; ningún secreto impreso; **ningún mensaje real de Telegram enviado por la auditoría** (alertas revisadas en código y con datos reales de `alertas.json`).

## 1. Resumen ejecutivo

| Severidad | Encontrados | Arreglados y verificados | Arreglados, verificación en Actions pendiente | Pendientes |
|---|---|---|---|---|
| CRÍTICO | 1 | 1 | 0 | 0 |
| ALTO | 6 | 6 | 0 | 0 |
| MEDIO | 10 | 6 | 0 | 4 (F-15, F-16, F-17, F-19) |
| BAJO | 5 | 1 | 0 | 4 (F-18 y F-22 sin acción posible; F-20, F-21 pendientes) |

Lo más grave: **el IPC interanual de la web era falso** (4,02 % en vez de 3,72 % para sep-26; subyacente 2,79 % en vez de 2,57 %) porque FRED no tiene el IPC de octubre de 2025 y el motor calculaba «hace 12 meses» por posición. Arreglado y verificado contra FRED.
Lo que está bien: precios (Yahoo), Tesoro 2Y/10Y/real, liquidez (WALCL, reservas, RRP, M2, BCE, BoJ), diferenciales de crédito, COT (CFTC), SKEW/VIX/VIX3M (Cboe), 37 de 38 tipos oficiales (BIS), FedWatch recalculado a mano desde los futuros ZQ, tesis por activo = reglas de `por_activo.py` (6/6), cambio de hora (25-oct / 1-nov) bien tratado, sin secretos en el repo ni en las 79 versiones del historial, cron-job.org correcto (4 tareas, cuerpo JSON válido, 204 en los disparos), `salud.json` refleja la realidad, reglas v3 de reacciones intactas.

## 2. Hallazgos

| ID | Sev. | Página / fichero | Evidencia | Causa | Arreglo (commit) | Verificado |
|---|---|---|---|---|---|---|
| F-01 | CRÍTICO | Calendario, Datos publicados, Régimen, Índices · `build.py`, `datos_macro.py`, `regimen.py`, `ciclo.py`, `indices.py` | IPC sep-26 web 4,02 % vs 3,72 % (324,245 → 336,298); ago 3,71 vs 3,35; jul 3,54 vs 3,30; subyacente 2,79 vs 2,57; Régimen «IPC subyacente … vs 2.8 % interanual». FRED `CPIAUCSL`: 32 observaciones en 33 meses (falta 2025-10) | Interanual por posición `s[i-12]`: con el hueco compara contra el mes de 13 meses antes | `engine/mensual.py`: referencia = mismo mes del año anterior; si falta, SIN DATO. Aplicado en 8 módulos; ceros inventados → SIN DATO (`5d1336c`) | **Sí**: recalculado con las funciones reales sobre FRED: 3,72 / 3,35 / subyacente 2,566; oct-2026 → None. Producción (ciclo de las 07:07 UTC): IPC 3,72 %, ago 3,35 %, subyacente 2,57 % en `calendario.json`, `publicados.json` y Régimen |
| F-02 | ALTO | Calendario, Datos publicados · `build.py`, `datos_macro.py` | Peticiones de paro periodo 3-oct «publicado 15-oct» (realmente 8-oct); ventas minoristas ago «publicado 15-oct» (realmente 16-sep) | `fecha_publicacion` = último evento con fecha ≤ hoy aunque aún no hubiera salido (build 10:08 UTC, dato 12:30 UTC) | `mensual.fecha_publicacion`: evento ya ocurrido, posterior al cierre del periodo y dentro de su retraso típico, si no «fuera del rango» (`5d1336c`) | **Sí**: 8-oct, 16-sep, 14-oct (IPC), 2-oct (NFP) con el calendario real |
| F-03 | ALTO | Todas · `build.py`, workflows | `actualizar` sin ejecutar 15-oct 11:13→19:49 UTC (8,6 h de mercado: YAML roto 15:28 + crones perdidos); diario del 15-oct a las 10:07 (+4,6 h), cierre a las 23:46 (+2,3 h); el diario del 16-oct no salió. cron-job.org solo dispara `horario` | Diario (05:30) y cierre (21:30) dependen de crones de GitHub no garantizados | `build.escalar()`: el horario añade diario/cierre si hoy no se ejecutaron; horario incluye calendario+publicados (`d4e55b8`) | **Sí en producción**: el ciclo de las 07:07 UTC se ejecutó como `horario+diario` (23 etapas, 844 s, todas OK) y `ejecuciones.csv` lo registra |
| F-04 | ALTO | Agenda · `agenda.py`, `agenda.json` | «mié 15 oct 2026», «jue 16 oct 2026» (16-oct-2026 = viernes); «HOY» mostraba el 15-oct estando a 16-oct (JSON de 11:24 UTC del día anterior) | `dia` de la fecha ET con `fecha` de Madrid; `agenda.json` solo se regenera en el build diario | Día de la semana de la fecha de Madrid (`3e708cc`); `calendario` en el horario (`d4e55b8`) | **Sí en producción**: `agenda.json` generado 16-oct 07:10 UTC, «vie 16-oct 05:30», próximos 7 días correctos |
| F-05 | ALTO | Agenda (375 px) | Columna Evento ≈ 60 px, una palabra por línea, 6224 px de alto | Tablas `nowrap` sin ancho mínimo | Filas apiladas en móvil: 4118 px (`ecdd6a3`) | Sí (captura `despues/agenda_375.png`) |
| F-11 | ALTO | Índices USA («beneficios SIN DATO»), Régimen · `indices.py` | `errores.factset = FileNotFoundError: 'pdftotext'` en todas las ejecuciones de Actions | `ubuntu-latest` no trae `pdftotext` | Lectura con `pypdf` (ya instalado) si falta; regex del P/E tolerante (`e674711`) | Probado con el PDF real del 9-oct con ambas rutas (29,6 % · P/E 19,1 · guías 44/72). **Sí en producción**: `indices.json` sin errores y bloque `beneficios` con el informe del 9-oct |
| F-14 | ALTO | Telegram «Qué vigilar» (Fed y giro) · `alertas.py` | Eventos de noche (Warsh 23:30 ET) se anunciaban con la fecha de Nueva York y la hora de Madrid («jue 15 oct · 05:30», real vie 16) y se daban por pasados | Usa `fecha` (ET) en vez de `fecha_madrid` | `fm(e)` en `vigilar`/`vigilar_fed` (`3e708cc`) | Sí (agenda de prueba: vie 16-oct 05:30) |
| F-06 | MEDIO | Bancos centrales del mundo (375/768) | Scroll horizontal del documento: 802 > 375 | Tablas dentro de `<details>` sin contenedor de scroll | CSS móvil (`ecdd6a3`) | Sí: `scrollWidth = clientWidth` a 375 y 768 |
| F-07 | MEDIO | Régimen, Índices, COT, Divisas, FedWatch (móvil) | Columnas cortadas / «NEUTR·AL» en vertical | Ancho mínimo ausente | `min-width` + scroll en tarjeta (`ecdd6a3`) | Sí (capturas `despues/`); la tarjeta se desplaza, sin indicador visual (BAJO pendiente) |
| F-08 | MEDIO | Resumen · `app.js` | «-6,3 % f…» | `cut()` a mitad de palabra | Corta en el último espacio (`ecdd6a3`) | Sí (prueba con node) |
| F-10 | MEDIO | Bancos centrales (FedWatch) | `fecha_precios` = hoy con la barra de la sesión en curso comparada con «ayer» (cierre), sin aviso | Dato intradía de Yahoo | Etiqueta «SESIÓN EN CURSO · NO ES CIERRE» (`ff3e5b1`) | Sí (render local) |
| F-12 | MEDIO | Calendario / Agenda | Producción industrial 18:15 Madrid (12:15 ET); Fed: 9:15 a.m. ET | Hora deducida de FRED | `HORA_OFICIAL_ET` (`3e708cc`) | Sí contra `federalreserve.gov/json/calendar.json`; H.4.1, H.6 y H.8 coinciden |
| F-13 | MEDIO | `data/reacciones_eventos.csv` | 7 fases del discurso del 15-oct duplicadas (dos disparos a 05:51:17 y :18) | `push_seguro` une por líneas y no ve la clave | `leer_log()` valida la primera fila por (evento, fase); CSV intacto (`e944323`) | Sí: 147 filas → 139 vigentes, 0 duplicadas |
| F-16 | MEDIO | Resumen / Régimen / Contexto / Cripto | Mismo documento con «30 % de subida» (resumen, 15-oct) y «14 %» (FedWatch, 16-oct); G3 17,41 (cripto, 1-sep) frente a 17,35 (liquidez, 7-oct); BTC 14-oct frente a 16-oct | Etapas con cadencias distintas; cada bloque lleva su fecha | Sin cambio de código: parte se reduce con el horario ampliado; el resto es diseño dated | No (pendiente de decisión) |
| F-15 | MEDIO | Noticias | `fuentes.tesoro: HTTP 404` en todas las ejecuciones | El RSS de press-releases del Tesoro ya no existe (probadas 6 variantes de URL) | — | Pendiente: no hay RSS gratuito alternativo |
| F-19 | MEDIO | Tono de bancos centrales | 25+ «discurso BCE … texto demasiado corto (0 palabras)» | Texto de discursos del BCE no extraíble | — | Pendiente (bloque marcado SECUNDARIO en la web) |
| F-17 | MEDIO | Calendario | Confianza U. Michigan 11:00 ET (suele ser 10:00 ET) | Misma deducción desde FRED que F-12 | — | No verificable (FRED inaccesible desde este equipo y la Fed no publica esa hora); importancia MEDIA |
| F-09 | BAJO | Encabezados `.sect` (móvil) | «CONTRADICCIONESlo que…» | Sin separación | `gap` + wrap (`ecdd6a3`) | Sí |
| F-18 | BAJO | Oro, Régimen | `lbma_*: HTTP 403` desde Actions | LBMA bloquea la IP | Ya rotulado como respaldo COMEX en la web | Nada que hacer |
| F-20 | BAJO | CSV | `reacciones_eventos.csv`: filas de 41/43/46 columnas (migraciones) y CRLF/LF mezclados → diffs ruidosos (79 «borradas» = normalización) | Evolución del esquema | — | Pendiente (los valores no se pierden) |
| F-21 | BAJO | Skew | «160,4» en el texto y «160,5» en la tarjeta (valor 160,45) | Redondeo Python vs JS | — | Pendiente |
| F-22 | BAJO | Capturas | `capturas/` está en `.gitignore` | Decisión previa | Las 71 capturas de esta auditoría quedan en local | — |

## 3. Contraste de datos (web vs fuente primaria en vivo)

Fuente consultada el 16-oct-2026 ~06:30–07:30 UTC. «OK» = coincide (diferencias de céntimos en cifras intradía de oro/BTC/DXY por la hora de consulta).

| Página | Cifra | Web | Fuente | Fecha dato | Publicación | Resultado |
|---|---|---|---|---|---|---|
| Resumen | S&P 500 | 7.744,06 | Yahoo `^GSPC` 7.744,06 | 15-oct | cierre | OK |
| Resumen | Nasdaq 100 / Dow / Russell | 29.935,60 / 52.177,69 / 2.767,27 | Yahoo idéntico | 15-oct | cierre | OK |
| Resumen | VIX | 16,46 (−2,43 %) | Yahoo/Cboe 16,46 | 15-oct | cierre | OK |
| Resumen | Oro / BTC / DXY | 4.194,4 / 82.076 / 101,93 | Yahoo 4.196,3 / 81.968 / 101,94 | 16-oct | en vivo | OK (minutos) |
| Bancos | 2Y / 10Y / 10Y real | 4,77 / 5,10 / 2,78 | Tesoro XML 4,77 / 5,10 / 2,78 | 15-oct | 15-oct | OK |
| Bancos | Cambio 1d 2Y / 10Y / real | −5 / −9 / −6 pb | 4,82→4,77 / 5,19→5,10 / 2,84→2,78 | 15-oct | | OK |
| Bancos | FedWatch 28-oct (ZQX26) | 3,915 % · subida 14 % | Yahoo ZQX26 → 3,915; (3,915−3,88)/0,25 = 14 % | 16-oct (sesión en curso) | | OK |
| Bancos | FedWatch 9-dic (ZQZ26) | 4,1405 % | (4,075·31 − 3,915·9)/22 = 4,1405 | 16-oct | | OK |
| Bancos | Tipos oficiales (38 bancos) | ver mapa | BIS WS_CBPOL: 37/38 idénticos; PH sin valor en el último día (la web usa el anterior) | 13-oct | | OK |
| Bancos | BCE / BoJ | 2,50 / 1,25 | BIS 2,5 / 1,25 | 13-oct | | OK |
| Liquidez | Activos Fed (WALCL) | 6,7476 bill. | FRED 6.747.560 M$ | 7-oct | H.4.1 8-oct | OK |
| Liquidez | Reservas (WRESBAL) | 3,0297 bill. | FRED 3.029.659 | 7-oct | | OK |
| Liquidez | RRP | 0,201 mm$ | FRED RRPONTSYD 0,201 | 14-oct | | OK |
| Liquidez | M2 / interanual | 23,3428 bill. / +5,659 % | FRED M2SL 23.342,8 / +5,659 % | ago-26 | 22-sep | OK |
| Liquidez | BCE en $ | 6,653 bill. | 5.943.911 M€ × 1,1193 | 9-oct | | OK |
| Liquidez | Liquidez neta | 5,865 | 6.747,56 − 880,25 − 0,2 = 5.867 | 7-oct | | OK |
| Liquidez | Global G3 | 17,35 | Fed + BCE(2-oct) + BoJ(1-sep) = 17,35 | 7-oct | | OK (suma al día de la Fed) |
| Liquidez | SOFR / IORB | 3,89 / 3,90 | FRED 3,89 / 3,90 | 13-oct | | OK |
| Liquidez | NFCI | −0,494 (2-oct) | FRED hoy −0,507 | 2-oct | revisado | OK (revisión de vintage posterior al build) |
| Ciclo | OAS IG / BBB / HY / CCC | 83 / 103 / 316 / 1.267 pb | FRED BAML idéntico (+ 5d y 1m) | 13-oct | | OK |
| Ciclo | Curva 10Y−3M mensual / Baa−10Y | 1,05 / 1,48 | GS10−TB3MS 4,99−3,94 / BAA10YM 1,48 | sep-26 | | OK |
| Ciclo | SLOOS / Sahm | 0,0 / 0,0 | FRED DRTSCILM 0,0 (jul) / SAHMREALTIME 0,0 | | | OK (ceros reales, no rellenados) |
| Calendario | IPC sep-26 interanual | **4,02 %** | FRED: 336,298/324,245 = **3,72 %** | sep-26 | 14-oct | **DIFERÍA → corregido** |
| Calendario | IPC ago-26 | **3,71 %** | **3,35 %** | ago-26 | | **DIFERÍA → corregido** |
| Datos publicados | IPC subyacente sep | **2,79 %** | **2,57 %** | sep-26 | 14-oct | **DIFERÍA → corregido** |
| Datos publicados | NFP sep | +29 mil | PAYEMS 159.044−159.015 | sep-26 | 2-oct | OK |
| Datos publicados | PCE ago (interanual) | 3,42 % | calculado sobre PCEPI completo: 3,42 % | ago-26 | 30-sep | OK |
| Datos publicados | Peticiones de paro | 197.000 (3-oct) | FRED hoy 198.000 (revisado) | 3-oct | **8-oct (web decía 15-oct)** | OK valor / **DIFERÍA fecha → corregido** |
| Posicionamiento | EUR no comerciales | 243.020 / 342.352 | CFTC 6dca-aqww idéntico | 6-oct | 9-oct | OK |
| Posicionamiento | JPY y USD (ICE) | 190.368/128.043 · 30.526/18.515 | CFTC idéntico | 6-oct | | OK |
| Posicionamiento | EUR gestores (TFF) | 499.449 / 309.568 | CFTC gpe5-46if idéntico | 6-oct | | OK |
| Riesgo de cola | SKEW / previo | 160,45 / 157,30 | Cboe SKEW_History idéntico | 15-oct | | OK |
| Riesgo de cola | VIX / VIX3M | 16,46 / 18,49 | Cboe idéntico | 15-oct | | OK |
| Cripto | BTC (Coinbase) | 81.566,29 | Coinbase 14-oct cierre 81.566,29 | 14-oct | | OK |
| Cripto | Stablecoins | 305,49 mm$ | DefiLlama 305,2 (día en curso) | 15-oct | | OK |
| Oro | Brent | 125,44 | FRED vintage 13-oct: 125,44 (6-oct) | 6-oct | | OK (y rotulado «con retraso de varios días») |
| Divisas | Suma de factores | 8/8 monedas | total = Σ puntos | | | OK |
| Resumen | Tesis por activo | 6 activos | `por_activo._tesis()` | | | OK 6/6 |

**No verificado de forma independiente** (se dice, no se da por bueno): GEX/gamma de índices (cadena de opciones Cboe retrasada; sin fuente alternativa gratuita), Semis vs Software (Yahoo devolvió 429 a esta máquina), z-scores del tono de bancos centrales, GLD en toneladas, amplitud del mercado, factores de la matriz de divisas más allá de su suma, noticias RSS, 38 bancos: inflación y PIB (FMI WEO).

**Frescura frente a frecuencia oficial**: precios y tipos al día; H.4.1 (jueves) con el dato del 7-oct hasta el siguiente build tras el jueves (ahora, ≤ 1 h con el horario ampliado); OAS (1 día de retraso oficial); COT semanal (6-oct, el 13-oct sale hoy 15:30 ET); mensuales (IPC, NFP…) al día; BoJ balance mensual (1-sep, rotulado); fondos monetarios 46 días (rotulado «CADUCADA, no suma»). La franja roja de la web solo salta a las 48 h por **etapa**, no por la fecha del dato: cada tarjeta lleva su fecha y los casos caducados se rotulan.
Valores sospechosos de relleno: ninguno (series constantes solo en tipos oficiales en escalón; ningún null convertido en 0 fuera de F-01, ya corregido).
Cambio de hora (25-oct EE. UU. sigue en EDT hasta el 1-nov): 08:30 ET → 14:30 Madrid el 23-oct, **13:30** del 26-oct al 30-oct, 14:30 desde el 2-nov; FOMC 28-oct 14:00 ET = 19:00 Madrid. Correcto.

## 4. Funcionamiento

- **GitHub Actions, últimas 48 h** (antes de la auditoría): `actualizar` 16 ejecuciones (11 `schedule`, 4 `workflow_dispatch`, 1 `push` fallida = YAML roto del 15-oct 15:28, corregido en el commit siguiente), duración mediana 200 s, máx. 741 s; `reacciones` 12 (4 `schedule`, 8 `workflow_dispatch`), 33–186 s, 0 fallos; `agenda_diaria` 3 (`workflow_dispatch`), 10–47 s, 0 fallos.
- **cron-job.org** (API, clave sin imprimir): 4 tareas activas — `actualizar` (UTC, minuto 7, 06–22 h, lun–vie), `reacciones` 12–20 h cada 5 min y 21:00 (UTC, lun–vie), `agenda 8h Madrid` (Europe/Madrid, así sobrevive al cambio de hora). Cuerpos JSON válidos, cabeceras correctas (token con formato `github_pat_…`), notificación por fallo activa. Últimos disparos: 204. **No se tocó nada.** Falta (opcional) disparar `diario` y `cierre`: ver F-03 y `docs/DISPARO_EXTERNO.md` §4.
- **salud.json** coincide con la API de Actions (última de `actualizar` 15-oct 23:46, `reacciones` y `agenda_diaria` 16-oct 05:51).
- **Telegram** (revisado en código y con mensajes reales ya enviados, `alertas.json`): formato de 4 líneas en Fed, SKEW, giro (reacciones), prueba; salud (aviso si `actualizar` > 2 h parado) y agenda (08:00 Madrid) usan HTML permitido (`<b>`); errores sin token; antiduplicado por día y clave (`estado_alertas.json`, UTC) y por episodio (SKEW) / evento-fase (giro); la referencia de Fed solo avanza si Telegram aceptó el mensaje. Hallazgo: F-14. Límite: 4000 caracteres con corte simple (no alcanzado nunca; riesgo teórico de HTML truncado).
- **Diario**: repo `nexora-diario` privado, último commit de sincronización 10-oct 07:19 UTC («Limpieza de datos de prueba»); el token vive solo en el `localStorage` del navegador; no verificable de extremo a extremo sin el token del usuario.
- **Monitor de reacciones**: el evento más reciente (discurso del presidente de la Fed, 15-oct 23:30 ET) tiene T-5, T+5, T+15, T+30, T+60 y T+120 (el cierre no existe para un acto posterior a las 16:00 ET; T+1 pendiente, hoy 10:00 ET). Reglas v3 «congeladas el 15-10-2026»: desde su commit solo cambió el alcance (más eventos, marca «contaminada», calendario de ejecución); las constantes y funciones de clasificación y giro no cambiaron.

## 5. Re-verificación en producción

Primer ciclo `actualizar` con el código nuevo: 16-oct 07:07 UTC (`workflow_dispatch` de cron-job.org), conclusión *success*, modo efectivo `horario+diario` (el diario de hoy no se había ejecutado), 23 etapas OK en 844 s, despliegue de Pages correcto.
Comprobado en los JSON publicados: IPC sep-26 3,72 % (ago 3,35 %), IPC subyacente 2,57 %, Régimen «IPC subyacente 3 meses anualizado 3,4 % vs 2,6 % interanual», peticiones de paro del 10-oct «publicadas 15-oct» (ya con el dato nuevo), `agenda.json` del día con «vie 16-oct», `indices.json` sin error de FactSet, `meta.json` con `modo: horario+diario`.
Fuera de alcance de esta prueba (no hay ejecución aún): la ejecución horaria normal con calendario y publicados (08:07 UTC) y el escalado de `horario+cierre` (22:07 UTC): su lógica está probada con relojes simulados y las etapas que añade ya corrieron bien en el diario.
Detalle menor visto en producción: el IPP (PPI) no recibe fecha de publicación porque el texto del evento («Precios de producción») no contiene «IPP»; queda como «fuera del rango» (antes mostraba una fecha falsa o ninguna).

## 6. Seguridad

Árbol actual y 79 commits revisados con patrones de token de Telegram, `github_pat_`, `ghp_/gho_`, claves de API (`FRED_API_KEY`, `BLS_API_KEY`, `CRONJOB…`), `chat_id`, correos y nombres de fichero tipo `*.env`/`config`: **sin coincidencias**. `config.env` está ignorado (`*.env`). `TELEGRAM_TOKEN` y `TELEGRAM_CHAT_ID` solo existen como GitHub Secrets. Lo único personal visible es el nombre de la cuenta de GitHub (`komonartisans-ops`), inevitable en un repo público. `nexora-diario` es privado.

## 7. Capturas (`capturas/auditoria/`, local)

71 ficheros: `{pagina}_{375|768|1440}.png` para las 23 páginas (`resumen, watchlists, regimen, ciclo, bancos, mapa, agenda, eventos, tono, liquidez, divisas, posicionamiento, skew, gamma, semis, oro, indices, cripto, noticias, calendario, publicados, diario, tesis`) + `informe.json` (métricas automáticas por página y ancho: scroll, elementos fuera, canvas vacíos, NaN/undefined, consola, 4xx/5xx, fuentes cargadas). Tras los arreglos: `capturas/auditoria/despues/` (agenda, mapa, regimen, indices, resumen, bancos a 375 y 768 px).
Resultado automático: 0 errores de consola, 0 peticiones 4xx/5xx, 0 `NaN/undefined/null/[object Object]`, 0 imágenes rotas, 0 gráficos vacíos, Inter / IBM Plex Mono / Source Serif 4 cargadas en las 69 combinaciones; único scroll horizontal: mapa (F-06, corregido). Revisión visual manual de las 23 capturas móviles: defectos F-05, F-07, F-08, F-09 y el desfase de fechas F-04; el diseño de escritorio es coherente (mismos tokens, tipografías y formato de cifras).

## 8. Pendiente y por qué

1. **F-16** (coherencia entre bloques con cadencias distintas): decisión de diseño; ahora los bloques se refrescan cada hora, pero `resumen`, `regimen`, `liquidez` y `monitores` siguen siendo diarios.
2. **F-15** (RSS del Tesoro, 404 permanente): no hay alternativa gratuita; la página lo rotula como SIN DATO.
3. **F-19, F-17, F-20, F-21**: baja prioridad o no verificables desde aquí.
4. Dos tareas opcionales en cron-job.org (diario y cierre) para quitar la dependencia de los crones de GitHub: no se crearon porque la instrucción era no tocar cron-job.org.
5. Sin verificar: gamma, semis, tono, GLD (§3).
