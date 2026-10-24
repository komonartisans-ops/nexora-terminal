# NEXORA · Niveles gamma + sesiones en TradingView (paso a paso)

**Qué hace:** dibuja en gráficos de **ES/MES** y **NQ/MNQ** el Gamma Flip, el Call Wall, el Put Wall, el Max Gamma y la banda EM, además de **PDH/PDL** (máximo y mínimo del día anterior) y los **máximos/mínimos de Asia y de Londres**. Los niveles gamma salen de la **línea que NEXORA te envía por Telegram a las 15:00 (Madrid)**; tú la pegas en el indicador. Es contexto, **no** da entradas.

Versión de Pine Script: **v6**. Funciona con una cuenta gratuita de TradingView.

## 1. Crea el indicador

1. Abre un gráfico de **ES1!** o **NQ1!** (o MES1! / MNQ1!) en TradingView.
2. Abajo, abre el **Editor de Pine** (pestaña «Pine Editor»).
3. Menú **Abrir → Nuevo script en blanco** y **borra todo el texto** que trae.
4. Abre [`NexoraNiveles.pine`](NexoraNiveles.pine), copia **todo** su contenido y pégalo en el editor.
5. Pulsa **Guardar** (Ctrl+S) y ponle un nombre, por ejemplo «NEXORA GEX».
6. Pulsa **Añadir al gráfico**. No debe aparecer ningún error en rojo.

## 2. Pega la línea de niveles (cada día)

1. En Telegram, copia la línea del mensaje de las 15:00, por ejemplo:  
   `ES flip=7804.0;cw=7843.6;pw=7693.6;em=97.0;maxg=7743.6;rf=2026-10-19 | NQ flip=29920.4;cw=29892.0;pw=28592.0;em=502.1;maxg=29392.0;rf=2026-10-19`
2. En el gráfico, haz clic en el engranaje del indicador (**Ajustes**) → pestaña **Datos de entrada**.
3. Pega la línea en **«Línea de niveles»**. Puedes pegar la línea completa con ES y NQ: el indicador elige el tramo que corresponde al instrumento del gráfico.
4. **Aceptar**. Verás las líneas: **dorada** = Gamma Flip, **roja** = Call Wall, **verde** = Put Wall, **azul discontinua** = Max Gamma, y una **banda azul tenue** = cierre anterior ± EM.
5. Arriba a la derecha, un pequeño cuadro indica el régimen: gamma **positiva** si el precio está sobre el flip y **negativa** si está bajo.

> Si el cuadro dice «pega la línea de niveles de Telegram», el campo está vacío; si dice «la línea no trae niveles de ES/NQ», revisa que has pegado la línea completa.

## Cuándo caduca la línea (Fase 21)

Desde la Fase 21 cada tramo de la línea acaba en `rf=AAAA-MM-DD`: la sesión de la cadena de opciones de la que salen sus niveles. Si el `rf=` de tu línea es anterior al de la línea que **toca hoy**, el indicador pone una fila **roja y grande** «NIVELES DEL dd-mm · CADUCADOS, pega la línea de hoy» y dibuja las líneas en **gris discontinuo** (con «· CADUCADO» en sus etiquetas). Pega la línea nueva y desaparece.

La regla es la misma que la del indicador de oro: la línea que toca es la de la última sesión de la bolsa cerrada antes del último «relevo» (lunes a viernes, **15:30 de Madrid**, media hora después del Telegram). En fin de semana y en festivos de la bolsa **no** salta la alarma (no hay línea nueva que pegar). Los días de sesión salen de las barras diarias de `AMEX:SPY` (ajuste «Símbolo del calendario de la bolsa»); sin datos de SPY se usan lunes a viernes. Una línea antigua sin `rf=` no se evalúa. Detalle y tabla de ejemplos: [`INSTALACION_ORO.md`](INSTALACION_ORO.md).

> **Actualización de la Fase 21: hay que volver a pegar el indicador (una sola vez).** Abre el Editor de Pine con tu script, borra todo el texto, pega de nuevo el contenido de [`NexoraNiveles.pine`](NexoraNiveles.pine) y pulsa **Guardar**. Las líneas que ya tenías pegadas (sin `rf=`) siguen funcionando, pero sin aviso de caducidad hasta que pegues la de hoy. Si usas NinjaTrader 8, [`NexoraNiveles.cs`](../ninjatrader/NexoraNiveles.cs) lo hace todo solo ([`docs/INSTALACION_NT8.md`](../../docs/INSTALACION_NT8.md)).

## 3. Ajustes útiles

| Ajuste | Por defecto | Para qué sirve |
|---|---|---|
| Mostrar Max Gamma / banda EM / etiquetas de precio | sí | Quita lo que no uses. |
| PDH / PDL | sí | Máximo y mínimo del día anterior (línea gris). |
| Máx./mín. de Asia y de Londres | sí | Naranja = Asia, turquesa = Londres. Se mantienen visibles hasta que empieza la siguiente sesión. |
| Zona horaria de las sesiones | America/New_York | Las horas de abajo se leen en esta zona. |
| Sesión de Asia | 20:00–02:00 (ET) | Cámbiala si usas otra definición. |
| Sesión de Londres | 02:00–05:00 (ET) | Cámbiala si usas otra definición. |

## Notas importantes

- **Precios de futuro:** los niveles ya vienen en precio de futuro (ES/NQ). Úsalos en gráficos de futuros, no en el índice SPX ni en SPY/QQQ.
- **Cada día hay que pegar la línea nueva.** Los niveles de ayer no se actualizan solos; el mensaje de Telegram dice de qué sesión de Cboe son (y avisa si tienen más de 4 días).
- **Cambio de contrato:** en la semana del vencimiento trimestral (marzo, junio, septiembre, diciembre) comprueba la fecha de la sesión del mensaje.
- **Valores `na`:** si falta un nivel, la línea lleva `na` y ese nivel simplemente no se dibuja.
- **Es contexto:** un nivel no es una señal. Las reglas de los avisos de Telegram y su medición están en la web (`#/gamma` y `#/marcador`).

## Sobre la validación

El script se ha compilado con el propio compilador de TradingView, sin errores ni advertencias (`python tools/validar_pine_tradingview.py plataformas/tradingview/NexoraNiveles.pine`), y un script con un error deliberado sí falla en esa comprobación. Aun así, TradingView actualiza Pine con frecuencia: si al pegarlo aparece un error en tu editor, envía el texto del mensaje.
