# NEXORA Terminal

Terminal macro web, visual y gratuito. Se actualiza solo con GitHub Actions y se publica en GitHub Pages.

- `engine/` scripts Python (solo biblioteca estándar, sin claves ni LLM) · `build.py` ejecuta todo y escribe `site/data/*.json`
- `data/` memoria permanente (CSV, solo se añade)
- `site/` web estática (HTML + CSS + JS vanilla; `lightweight-charts` y `Chart.js` desde CDN con versión fija)
- `.github/workflows/` `actualizar.yml` (cron) y `pages.yml` (despliegue)

Reglas: coste cero · nunca se inventan datos (`SIN DATO` con fuente y hora del último dato válido) · periodo ≠ publicación · sin recomendaciones de compra o venta · secretos solo en GitHub Secrets.

Local: `python engine/build.py --modo diario` y `python -m http.server 8765 -d site`.

## Fase 6 · riesgo de cola, semis/software y gamma

| Página | Motor | Fuentes (gratis) | Cuándo |
|---|---|---|---|
| Riesgo de cola (SKEW) | `engine/skew.py` | Cboe (SKEW, VIX, VIX3M, SPX), FRED WRMFNS, OFR, `ciclo.json` | cada hora (la alerta) y al cierre |
| Semis vs Software | `engine/semis.py` | Yahoo Finance (respaldo Nasdaq.com), Invesco (pesos QQQ) | al cierre |
| Gamma de índices | `engine/gamma.py` | Cboe: cadena de opciones con 15 min de retraso (SPX+SPY, NDX+QQQ), Yahoo (base del futuro) | solo al cierre (cron 21:30 UTC) |

- `site/data/contexto.json` (`engine/contexto.py`): resumen compacto de todo el terminal, con fuente y fecha en cada bloque, para redactar informes.
- Gamma y zonas del SKEW son **CRITERIO NEXORA** (método propio documentado en la página y en la cabecera de cada módulo).
- Memoria permanente nueva: `data/historico_skew.csv`, `data/historico_gamma.csv` (niveles de cada cierre; la página los compara con la sesión siguiente).
- Cboe sirve una cadena TLS con un cruce caducado que algunos OpenSSL rechazan: `fuentes.py` reintenta con `curl`, que sigue verificando el certificado.
- Modo nuevo `--modo cierre`.

## Fase 8 · reacción a eventos (`#/eventos`)

| Pieza | Detalle |
|---|---|
| Motor | `engine/reaccion.py` · eventos IPC, NFP, PCE (FRED Release Calendar: BLS/BEA) y FOMC (federalreserve.gov) |
| Job | `.github/workflows/reacciones.yml`: arranca ~60 min antes del evento y espera dentro del job; registra T-5, T+5, T+15, T+30, T+60 y T+120; los crones de 16:05 ET (cierre) y 10:05 ET (T+1, día siguiente) completan el resto |
| Series | Yahoo (5 min): ZT=F calibrado contra el 2 Yr del Tesoro (2YY=F no tiene barras), ^TNX (ZN=F×beta tras las 15:00 ET), DX-Y.NYB, GC=F, NQ=F, ES=F, BTC-USD; 10Y real FRED DFII10 al día siguiente |
| Memoria | `data/reacciones_eventos.csv` (solo se añade) y `data/estado_reacciones.json` (avisos de giro enviados) |
| Alerta | Telegram si la regla de giro v2 da REFUGIO / RIESGO o SORPRESA DESHECHA en T+60, T+120, cierre o T+1; una por evento y fase |

**Regla de giro v2** (medida contra T+5, no contra T-5; pendiente de validar con eventos nuevos): en T+60, T+120, cierre y T+1 se calcula la *devolución* de 2Y y 10Y (% de su movimiento de T+5 ya deshecho). ≥ 60 % de ambos con NQ cayendo más que en T+5 → REFUGIO / RIESGO; ≥ 60 % con NQ recuperando → SORPRESA DESHECHA; < 30 % → SE CONFIRMA. Alerta Telegram, una por evento y fase, en REFUGIO / RIESGO y SORPRESA DESHECHA. El resultado se calcula al construir el JSON desde el CSV (el log sigue siendo solo-añadir).

Las clases (FED MÁS DURA / MÁS SUAVE / REFUGIO / EMPINAMIENTO POR PLAZO LARGO / SIN REACCIÓN) son **CRITERIO NEXORA** y sus reglas están en la página. `engine/push_seguro.py` fusiona los CSV si `actualizar` y `reacciones` escriben a la vez.

## Agenda (fase 9)

`engine/agenda.py` · agenda desde los calendarios oficiales (FRED Release Calendar: BLS, BEA, Census, Fed, DOL; Federal Reserve; ISM; BCE; BoJ; TreasuryDirect). Importancia ALTA/MEDIA **fija por tipo** (tabla en `site/data/agenda.json` y en la página «Agenda»). Bloque `agenda` en `contexto.json` (hoy y próximos 7 días, hora ET y Madrid). `agenda_diaria.yml`: Telegram cada día laborable a las 8:00 Madrid («Hoy sin datos de importancia alta» si no hay nada). El monitor de reacciones vigila **todos** los eventos ALTA de la agenda (IPC, PPI, NFP, PCE, PIB, FOMC, actas, ISM manufacturero) y marca como *contaminada* la fase en la que otro dato alto cae entre el dato y la fase.
- Disparo externo (cron-job.org) y salud de los workflows: `docs/DISPARO_EXTERNO.md`, `engine/salud.py`, página Agenda → Salud.
