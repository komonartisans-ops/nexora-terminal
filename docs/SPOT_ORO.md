# Contraste del spot del oro (Fase 19)

Ningún dato derivado del spot XAU/USD (ratio XAU/GLD, base GC−XAU, niveles de la pestaña ORO de `#/gamma`, línea ORO) depende de una sola fuente. Código: `engine/spot_oro.py`; etapa de build `spot_oro` (en el modo **cierre**, justo antes de `gamma_oro`; el vigilante del cierre la exige porque lee `MODOS["cierre"]`). Pruebas: `PYTHONUTF8=1 python tools/prueba_spot_oro.py` (sin red ni Telegram).

## Fuentes (comparadas a la misma hora ±5 min; si no, `NO_SINCRONIZADO`)

| Fuente | Qué es | Notas |
|---|---|---|
| Principal | gold-api.com XAU/USD al contado | la de siempre |
| Contraste A | GC=F (Yahoo, barra de 5 min) − base GC−XAU de la sesión anterior (`data/xau_gc_base.csv`) = spot implícito | **Informativo** y respaldo si cae la principal. Yahoo da COMEX con ≈ 10 min de retraso y el futuro para de 21:00 a 22:00 UTC: casi nunca está a ±5 min de la principal (la tolerancia NO se relaja). La web lo etiqueta «informativo (retraso ~10 min)» |
| Contraste B | Swissquote, feed público de cotizaciones de bróker (punto medio bid/ask, marca de tiempo propia) | sí es de la misma hora que la principal; es el contraste que verifica en el cierre |

Stooq (XAUUSD) se probó y se descartó: su CSV está tras un desafío JavaScript anti-bot y no responde a un script.

## Regla (umbral fijo 0,3 %)

- ≤ 0,3 % con alguna fuente sincronizada → `OK`, se usa la principal (chip «spot verificado»).
- \> 0,3 % con alguna → `DUDOSO` ⚠️: el ratio y la base de ese día **no se actualizan** (se usa el último ratio OK, `ratio_fuente=ANTERIOR`) y la línea ORO acaba en `;spot=dudoso`.
- Principal caída → `GC_IMPLICITO` (`spot_fuente=GC_IMPLICITO`); la base de ese día no se anota (sería circular).
- Principal y GC implícito caídos → **último recurso** `SWISSQUOTE` (`spot_fuente=SWISSQUOTE`): hay niveles ORO, pero el ratio y la base **no se actualizan** (se usan los últimos OK, `ratio_fuente=ANTERIOR`). Sin ninguna de las tres fuentes la etapa falla (el vigilante lo avisa); no se inventa.
- Ninguna fuente de contraste sincronizada → `NO_SINCRONIZADO` (o `SIN_CONTRASTE` si no hay ninguna): se usa la principal, sin ⚠️, y la web dice que no se pudo verificar.
- 2 sesiones seguidas en `DUDOSO` → un aviso por Telegram por racha (clave `spot_oro|<inicio>` en `data/vigilante_estado.json`, lo envía `integridad.vigilar`).
- Swissquote sin responder **3 sesiones seguidas** → aviso en `#/integridad` y un Telegram por racha (clave `swiss_caido|<inicio>`): sin él, el spot volvería a depender de una sola fuente sin enterarnos. Una respuesta de Swissquote corta la racha.

## Registro y visibilidad

`data/xau_spot_contraste.csv` (solo añadir; una fila por sesión, la primera decisión del día manda): fecha, hora, cada fuente con su hora, diferencias, estado, fuente usada, `ratio_fuente`. Se ve en `#/gamma` → ORO (chip con las fuentes en su ⓘ) y en `#/integridad` (tarjeta con historial y racha).

## La hora del spot: el cierre del GLD (Fase 20)

El ratio XAU/GLD = spot del oro / cierre de GLD, así que el spot tiene que ser el **de la hora del cierre de GLD: 16:00 en Nueva York** (zona `America/New_York`, no horas fijas: **20:00 UTC hasta el 31-oct-2026, 21:00 UTC desde el 2-nov**, tras el cambio de hora de EE. UU. del 1-nov; el 27-nov y el 24-dic la NYSE cierra a las 13:00 ET). En esa hora el futuro del oro sigue abierto (para de 21:00 a 22:00 UTC en verano y de 22:00 a 23:00 UTC en invierno), de modo que GC=F, gold-api y Swissquote se pueden comparar en la misma ventana (±5 min).

- **Captura:** el workflow `reacciones` (cron-job.org cada 5 min, 11-21 UTC) ejecuta primero `python engine/spot_oro.py --capturar`: solo actúa de lunes a viernes dentro de ±5 min de ese cierre y solo si el día aún no tiene fila; la hora del spot de gold-api también debe estar en la ventana. La primera captura válida manda y su nota empieza por `VENTANA_GLD`.
- **Si no hay captura** (por ejemplo una cola de ejecuciones): el cierre de las 21:30 UTC no usa el spot de esa hora. Reconstruye el de la hora del cierre del GLD con el GC=F de entonces (barra de 5 min) menos la base GC−XAU de la sesión anterior → estado `GC_IMPLICITO`, nota `FUERA_DE_VENTANA`, sin verificar. Sin GC=F o sin base: el ratio **no se actualiza** (`ratio_fuente=ANTERIOR`). Nunca se usa el spot de otra hora.
- **Corrección hacia atrás** (`python tools/revisar_ratio_cierre_gld.py --aplicar`): para los días con spot de gold-api de las ~21:30 UTC se estima el spot de la hora del cierre del GLD (GC=F de entonces − la base de ese día) y, si el ratio cambia, se **añade** una fila `REVISADA` a `data/xau_gld_ratio.csv` (la cabecera gana la columna `estado` al final; ninguna fila se borra ni se edita; las lecturas usan la última fila de cada fecha). Revisados el 24-oct-2026: 20-oct −0,046 %, 21-oct −0,176 %, 22-oct +0,107 %, 23-oct +0,048 %. El 19-oct (proxy provisional) no se toca. Los niveles XAU ya guardados en `historico_gamma_oro.csv` son medidas históricas y no se reescriben.
