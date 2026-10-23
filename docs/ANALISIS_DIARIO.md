# Análisis diario (Fase 18) · cómo publicar el informe de Ruiz

Ruiz envía cada día su informe (texto con tablas, secciones A–K; G = oro). Se publica con un script; el terminal (`#/analisis`) lo muestra cotejado contra los datos de NEXORA. **Sin IA en ejecución:** el texto se guarda tal cual y el parser es por reglas.

## Cuando Ruiz escribe «PUBLICA ANALISIS · sesgo oro: X · visibilidad: Y» + el texto

1. Guarda el texto **tal cual** en un archivo temporal (fuera del repo, p. ej. el directorio de scratchpad o `%TEMP%`; nunca dentro de `data/` ni de `site/`).
2. Ejecuta (X = `alcista`, `bajista` o `neutral`; Y = `privado` o `resumen`; tipo `ORO_MACRO` salvo que Ruiz diga que es de índices → `INDICES`):
   ```bash
   PYTHONUTF8=1 python tools/publicar_analisis.py RUTA_TEMPORAL.txt --sesgo X --tipo ORO_MACRO --visibilidad Y
   ```
   (`--fecha AAAA-MM-DD` y `--corte HH:MM` solo si el informe no los trae en sus primeras líneas.)
3. `git add data/analisis_indice.csv data/analisis_cotejos.jsonl site/data/analisis.json data/analisis/` (esta última solo existe con visibilidad `resumen`), commit y push.
4. Responde **solo** con: la ruta del archivo, el resumen del cotejo (`n ✅ · n ⚠️ · n —`) y la lista de ⚠️ (es exactamente lo que imprime el script). **No reanalices ni resumas el informe** (ahorro de tokens). **El sesgo de oro es el que indica Ruiz; no se deduce del texto.**

## Qué guarda y dónde (solo añadir; nunca se sobrescribe)

| Qué | Dónde | Público |
|---|---|---|
| Informe completo (front-matter + texto) | repo **privado** `komonartisans-ops/nexora-diario` · `analisis/AAAA/AAAA-MM-DD_<tipo>[_vN].md` | no |
| El mismo informe ya extraído (secciones, escenarios…) | `analisis/AAAA/AAAA-MM-DD_<tipo>[_vN].json` (lo lee la vista con el token del Diario) | no |
| Índice (fecha, tipo, versión, visibilidad, sesgo, hash, estado) | `data/analisis_indice.csv` | sí |
| Cotejo numérico (panel A.2, calendario B.3, Fed) | `data/analisis_cotejos.jsonl` y `site/data/analisis.json` | sí (sin el texto del informe) |
| Resumen (tesis, veredicto, K.2, escenarios literales) | `data/analisis/AAAA/<id>.md` | **solo** con `--visibilidad resumen` |
| Resultado del sesgo a T+1 / T+5 | `data/analisis_resultados.csv` | sí |

Con `--visibilidad privado` ningún texto del informe llega al repo público (solo el índice, el cotejo numérico y el resultado). Para escribir en el repo privado hace falta `gh auth` con acceso a `nexora-diario`.

**Reedición:** si ya hay un informe de esa fecha y tipo con otro hash, el nuevo se guarda como `_v2` (`_v3`…) y el anterior queda `REVISADA` (una fila nueva en el índice; no se toca ningún archivo). Con el mismo hash no se hace nada.

## Cotejo (lo más importante)

Cada fila del panel A.2 que NEXORA tiene (2Y, 5Y, 10Y, 30Y, DFII10, breakeven 10Y, DXY, oro contado, Brent, WTI, VIX, reservas, TGA, ON RRP, SOFR, COT oro) se compara con el valor de NEXORA **en la misma fecha** (sus históricos; si no hay histórico de esa fecha, el dato actual solo si es de esa fecha). Tolerancias: tipos ±3 pb; DXY ±0,3; oro ±0,5 %; Brent/WTI ±1,5 %; VIX ±0,5; resto ±1 %. Estados: ✅ coincide · ⚠️ difiere (ambos valores y la fuente de NEXORA) · — NEXORA no lo tiene (nunca se rellena). El calendario B.3 se compara con la agenda de NEXORA (eventos que faltan u horas distintas, con la nota del cambio de hora: Europa 25-oct, EE. UU. 1-nov) y las probabilidades de la Fed se muestran lado a lado, cada una con su fuente.

## Resultado del sesgo

La etapa `analisis` (modos cierre y diario de `actualizar.yml`) añade a `data/analisis_resultados.csv` el resultado a T+1 y T+5 sesiones con la variación del oro, de DXY y de DFII10: CUMPLIDO / FALLIDO / MIXTO (reglas fijas en `engine/analisis.py`). Hasta 20 resultados evaluados la página muestra «n<20: sin conclusión».

## Vista `#/analisis`

Cabecera (fecha/corte, tesis central, chip de sesgo, veredicto, resumen del cotejo), «Tesis anterior → hoy», bloques A–K plegables (G abierto), cotejo, histórico por fecha con filtro por sesgo y pestañas ORO_MACRO / INDICES. El texto de un informe privado solo se ve con el Diario conectado en ese navegador.

Pruebas: `PYTHONUTF8=1 python tools/prueba_analisis.py` (sin red ni GitHub; el repo privado se simula con una carpeta).
