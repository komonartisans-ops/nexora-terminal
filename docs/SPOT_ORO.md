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
