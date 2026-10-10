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
