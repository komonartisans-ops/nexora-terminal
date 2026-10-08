# NEXORA Terminal

Terminal macro web, visual y gratuito. Se actualiza solo con GitHub Actions y se publica en GitHub Pages.

- `engine/` scripts Python (solo biblioteca estándar, sin claves ni LLM) · `build.py` ejecuta todo y escribe `site/data/*.json`
- `data/` memoria permanente (CSV, solo se añade)
- `site/` web estática (HTML + CSS + JS vanilla; `lightweight-charts` y `Chart.js` desde CDN con versión fija)
- `.github/workflows/` `actualizar.yml` (cron) y `pages.yml` (despliegue)

Reglas: coste cero · nunca se inventan datos (`SIN DATO` con fuente y hora del último dato válido) · periodo ≠ publicación · sin recomendaciones de compra o venta · secretos solo en GitHub Secrets.

Local: `python engine/build.py --modo diario` y `python -m http.server 8765 -d site`.
