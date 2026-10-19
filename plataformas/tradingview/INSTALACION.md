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
   `ES flip=7804.0;cw=7843.6;pw=7693.6;em=97.0;maxg=7743.6 | NQ flip=29920.4;cw=29892.0;pw=28592.0;em=502.1;maxg=29392.0`
2. En el gráfico, haz clic en el engranaje del indicador (**Ajustes**) → pestaña **Datos de entrada**.
3. Pega la línea en **«Línea de niveles»**. Puedes pegar la línea completa con ES y NQ: el indicador elige el tramo que corresponde al instrumento del gráfico.
4. **Aceptar**. Verás las líneas: **dorada** = Gamma Flip, **roja** = Call Wall, **verde** = Put Wall, **azul discontinua** = Max Gamma, y una **banda azul tenue** = cierre anterior ± EM.
5. Arriba a la derecha, un pequeño cuadro indica el régimen: gamma **positiva** si el precio está sobre el flip y **negativa** si está bajo.

> Si el cuadro dice «pega la línea de niveles de Telegram», el campo está vacío; si dice «la línea no trae niveles de ES/NQ», revisa que has pegado la línea completa.

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
