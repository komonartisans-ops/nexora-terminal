# Análisis diario (Fase 18) · cómo publicar el informe de Ruiz

Ruiz envía cada día su informe (texto con tablas, secciones A–K; G = oro). Se publica con un script; el terminal (`#/analisis`) lo muestra cotejado contra los datos de NEXORA. **Sin IA en ejecución:** el texto se guarda tal cual y el parser es por reglas.

## Cuando Ruiz escribe «PUBLICA ANALISIS · tipo: DIARIO|SEMANAL · sesgo oro: X · visibilidad: Y» + el texto

Si no indica el tipo: **DIARIO**.

1. Guarda el texto **tal cual** en un archivo temporal (fuera del repo, p. ej. el directorio de scratchpad o `%TEMP%`; nunca dentro de `data/` ni de `site/`).
2. Ejecuta (X = `alcista`, `bajista` o `neutral`; Y = `privado` o `resumen`; T = `DIARIO` (el defecto; se guarda como `ORO_MACRO`), `SEMANAL` o, si Ruiz lo pide, `INDICES`):
   ```bash
   PYTHONUTF8=1 python tools/publicar_analisis.py RUTA_TEMPORAL.txt --sesgo X --tipo T --visibilidad Y
   ```
   (`--fecha AAAA-MM-DD` y `--corte HH:MM` solo si el informe no los trae en sus primeras líneas. El corte sale de la cabecera: «Corte: 07:00, hora de Madrid».)
3. `git add data/analisis_indice.csv data/analisis_cotejos.jsonl site/data/analisis.json data/analisis/` (esta última solo existe con visibilidad `resumen`), commit y push.
4. Responde **solo** con: la ruta del archivo, el resumen del cotejo (`n ✅ · n ⚠️ · n —`) y la lista de ⚠️ (es exactamente lo que imprime el script). **No reanalices ni resumas el informe** (ahorro de tokens). **El sesgo de oro es el que indica Ruiz; no se deduce del texto.**

## Qué guarda y dónde (solo añadir; nunca se sobrescribe)

| Qué | Dónde | Público |
|---|---|---|
| Informe completo (front-matter + texto) | repo **privado** `komonartisans-ops/nexora-diario` · `analisis/AAAA/AAAA-MM-DD_ORO_MACRO[_vN].md` (diario), `…_INDICES…`, `…_semanal[_vN].md` (semanal) | no |
| El mismo informe ya extraído (secciones, escenarios…) | `analisis/AAAA/AAAA-MM-DD_<tipo>[_vN].json` (lo lee la vista con el token del Diario) | no |
| Índice (fecha, tipo, versión, visibilidad, sesgo, corte y su origen, publicado_utc, precio base y su hora, hash, estado) | `data/analisis_indice.csv` | sí |
| Cotejo numérico (panel A.2, calendario B.3, Fed) | `data/analisis_cotejos.jsonl` y `site/data/analisis.json` | sí (sin el texto del informe) |
| Resumen (tesis, veredicto, K.2, escenarios literales) | `data/analisis/AAAA/<id>.md` | **solo** con `--visibilidad resumen` |
| Resultado del sesgo a T+1 / T+5 | `data/analisis_resultados.csv` | sí |

Con `--visibilidad privado` ningún texto del informe llega al repo público (solo el índice, el cotejo numérico y el resultado). Para escribir en el repo privado hace falta `gh auth` con acceso a `nexora-diario`.

**Reedición:** si ya hay un informe de esa fecha y tipo con otro hash, el nuevo se guarda como `_v2` (`_v3`…) y el anterior queda `REVISADA` (una fila nueva en el índice; no se toca ningún archivo). Con el mismo hash no se hace nada.

## Cotejo (lo más importante)

Cada fila del panel A.2 que NEXORA tiene (2Y, 5Y, 10Y, 30Y, DFII10, breakeven 10Y, DXY, oro contado, Brent, WTI, VIX, reservas, TGA, ON RRP, SOFR, COT oro) se compara con el valor de NEXORA **en la misma fecha** (sus históricos; si no hay histórico de esa fecha, el dato actual solo si es de esa fecha). Tolerancias: tipos ±3 pb; DXY ±0,3; oro ±0,5 %; Brent/WTI ±1,5 %; VIX ±0,5; resto ±1 %. Estados: ✅ coincide · ⚠️ difiere (ambos valores y la fuente de NEXORA) · — NEXORA no lo tiene (nunca se rellena). El calendario B.3 se compara con la agenda de NEXORA (eventos que faltan u horas distintas, con la nota del cambio de hora: Europa 25-oct, EE. UU. 1-nov) y las probabilidades de la Fed se muestran lado a lado, cada una con su fuente.

## Corte ≠ publicación

- El **corte** es el de la cabecera del informe («Corte: 07:00, hora de Madrid»). La hora a la que se publica se guarda aparte (`publicado_utc`) y **no se usa para evaluar nada**. Si el informe no trae corte: se usa la hora de publicación y el índice marca `corte_origen = ESTIMADO` (el script lo avisa como ⚠️).
- Todo lo que fija la evaluación sale de datos **anteriores a fecha + corte**: el **precio base** (la barra de 5 min de GC=F más cercana anterior al corte, con su hora; el spot del oro no tiene histórico intradía gratuito, y GC=F es la misma serie con la que se mide el resultado; si Yahoo falla, la última captura horaria de NEXORA anterior al corte; si no hay ninguna, no se evalúa y el script lo avisa) y el **EM** (el último EM de oro guardado antes del corte, normalmente el del cierre de la sesión anterior; `em_sesion` en el CSV; si tiene más de 3 días hábiles de antigüedad, umbral FIJO).
- Ejemplo: un informe del día D con corte 07:00 publicado a las 14:00 usa el EM del cierre de D−1 y el precio de las 07:00, nunca datos posteriores.

## Resultado del sesgo

La etapa `analisis` (modos cierre y diario de `actualizar.yml`) añade a `data/analisis_resultados.csv` el resultado con la variación del oro (precio base en el corte → cierre de la sesión), de DXY y de DFII10 (columnas `umbral` = EM o FIJO, `umbral_pct`, `em_sesion`, `precio_base`, `precio_base_hora`, `precio_fin`).

- **DIARIO:** T+1 = cierre de la primera sesión que termina después del corte (la del propio día si el corte es anterior a su cierre); T+5 = cierre de la quinta sesión. **SEMANAL:** solo la semana siguiente, de la apertura del domingo al cierre del viernes (la quinta sesión tras el corte), con el umbral = EM del cierre del viernes × √5.
- **Umbral = EM del oro** (gamma de GLD, referencia, en %; a T+5 y en el semanal, EM × √5).
- **Alcista:** CUMPLIDO si Δoro ≥ +0,3 × EM; FALLIDO si Δoro ≤ −0,3 × EM; si no, MIXTO. **Bajista:** simétrico. **Neutral:** CUMPLIDO si |Δoro| ≤ 0,5 × EM; FALLIDO si |Δoro| > 1 × EM; si no, MIXTO.
- Un CUMPLIDO direccional pasa a MIXTO si DXY y DFII10 van los dos en contra.
- Sin EM válido: los % fijos (alcista/bajista ±0,25 %; neutral 0,5 % a T+1 y 1,5 % a T+5) y `umbral = FIJO`.
- El acierto acumulado del SEMANAL va **aparte** del diario. Hasta 20 resultados evaluados: «n<20: sin conclusión».

## Vista `#/analisis`

Cabecera (fecha, corte y su origen, publicado, precio base, tesis central, chip de sesgo, veredicto, resumen del cotejo, «Semanal vigente» con su sesgo al lado del diario), «Tesis anterior → hoy», bloques A–K plegables (G abierto), cotejo, histórico por fecha con filtro por sesgo y pestañas ORO_MACRO / INDICES / SEMANAL. El texto de un informe privado solo se ve con el Diario conectado en ese navegador.

Pruebas: `PYTHONUTF8=1 python tools/prueba_analisis.py` (sin red ni GitHub; el repo privado se simula con una carpeta).
