# NEXORA Oro en TradingView (paso a paso)

**Qué hace:** en un gráfico de **oro (XAU/USD)** muestra, en vivo, cómo van el **dólar (DXY)** y el **tipo real a 10 años** frente a su media de 50 sesiones, avisa si **el oro sube con el tipo real al alza**, y dibuja los **niveles de gamma de GLD (referencia)** pasados a precio XAU/USD con la línea que NEXORA te envía por Telegram a las 15:00 (Madrid). Añade **PDH/PDL** y los **máximos/mínimos de Asia y de Londres** (útil para ICT/LIT). Es contexto, **no** da entradas.

Versión de Pine Script: **v6**. Funciona con una cuenta gratuita de TradingView (hace falta iniciar sesión para añadir scripts propios a un gráfico). El script compila sin errores ni advertencias con el compilador de TradingView (`python tools/validar_pine_tradingview.py plataformas/tradingview/NexoraOro.pine`).

## 1. Crea el indicador

1. Abre un gráfico de **XAUUSD** (OANDA, FOREXCOM…), **GOLD** (TVC) o **GC1!** / **MGC1!**, en el marco temporal que uses (los datos en vivo usan cierres diarios).
2. Abajo, abre el **Editor de Pine** (pestaña «Pine Editor»).
3. Menú **Abrir → Nuevo script en blanco** y **borra todo el texto** que trae.
4. Abre [`NexoraOro.pine`](NexoraOro.pine), copia **todo** su contenido y pégalo en el editor.
5. Pulsa **Guardar** (Ctrl+S) y ponle un nombre, por ejemplo «NEXORA Oro».
6. Pulsa **Añadir al gráfico**. No debe aparecer ningún error en rojo.

## 2. Pega la línea ORO (cada día)

1. En Telegram, copia la línea ORO del mensaje de las 15:00 (la que empieza por `XAU`), por ejemplo:  
   `XAU tesis=alcista;int=debil;flip=4167.1;cw=4144.2;pw=3762.5;em=57.8;maxg=4253.2;ratio=10.9057;rf=2026-10-19;cot=largo-bajo_p27;etf=+3.1;evento=no`
2. En el gráfico, haz clic en el engranaje del indicador (**Ajustes**) → pestaña **Datos de entrada**.
3. Pega la línea en **«Línea ORO»** y pulsa **Aceptar**.
4. Verás líneas finas con la etiqueta **«GLD ref.»**: **dorada** = Gamma Flip, **roja** = Call Wall, **verde** = Put Wall, **azul discontinua** = Max Gamma, y una banda azul tenue = cierre anterior ± EM.

## 3. Qué ves en el panel (arriba a la derecha)

| Fila | Significado |
|---|---|
| **Dólar (DXY)** | Valor de `TVC:DXY` y si está por encima (↑, en rojo: suele pesar sobre el oro) o por debajo (↓, en verde) de su media de 50 sesiones. |
| **Tipo real 10A** | Valor de `FRED:DFII10` (rendimiento de los bonos del Tesoro ligados a la inflación a 10 años; dato diario) y su posición frente a la media de 50. |
| **Aviso** | «Oro sube con tipo real al alza» cuando, en las últimas 5 sesiones, el oro sube **y** el tipo real también. Se puede crear una **alerta** de TradingView con la condición «Oro sube con tipo real al alza». |
| **Tesis** | Tesis de NEXORA para el oro (alcista / bajista / sin tesis) y su intensidad. |
| **COT** | Dinero gestionado en COMEX: lado (largo/corto), nivel frente a sus 3 últimos años y percentil. |
| **ETF GLD (5 sesiones)** | Variación de toneladas del trust GLD en 5 sesiones. |
| **Evento ALTA (Madrid)** | Eventos de importancia ALTA del día con hora de Madrid; `na` si la hora no está publicada. |
| **GLD ref.** | Ratio XAU/GLD usado y su fecha. Si la línea tiene más de 4 días, aparece «ANTIGUA». |
| **SPOT DUDOSO** (fila ámbar, la última) | Solo aparece si la línea ORO acaba en `;spot=dudoso` (Fase 19: el spot del oro difirió más de un 0,3 % entre fuentes de la misma hora). Significa «niveles con ratio anterior»: el ratio XAU/GLD de ese día no se actualizó y los niveles usan el último ratio verificado. Si la línea no trae la clave `spot`, no se muestra nada. |

> **Actualización de la Fase 20 (clave `spot`): hay que volver a pegar el indicador.** Abre el Editor de Pine con tu script «NEXORA Oro», borra todo el texto, pega de nuevo el contenido de [`NexoraOro.pine`](NexoraOro.pine) y pulsa **Guardar** (el gráfico se actualiza solo; la línea ORO que tienes en «Datos de entrada» se conserva). Si no lo repegas, el indicador funciona igual pero no mostrará la fila ámbar de spot dudoso.
> Ejemplo de línea con la clave: `XAU tesis=alcista;int=debil;flip=4167.1;cw=4144.2;pw=3762.5;em=57.8;maxg=4253.2;ratio=10.9057;rf=2026-10-19;cot=largo-bajo_p27;etf=+3.1;evento=no;spot=dudoso`

## 4. Ajustes útiles

| Ajuste | Por defecto | Para qué sirve |
|---|---|---|
| Mostrar Max Gamma / banda EM / etiquetas | sí | Quita lo que no uses. |
| Dibujar aunque el gráfico no sea oro | no | Por defecto los niveles solo se dibujan en XAUUSD, GOLD, GC y MGC. |
| Índice del dólar / Tipo real a 10 años | `TVC:DXY` / `FRED:DFII10` | Símbolos de la parte en vivo (verificados en TradingView). |
| Media / Ventana del aviso | 50 / 5 sesiones | Sesiones de la media y del aviso. |
| PDH / PDL, Asia, Londres | sí | Gris = día anterior, naranja = Asia, turquesa = Londres. |
| Zona horaria y sesiones | America/New_York, Asia 20:00–02:00, Londres 02:00–05:00 | Cámbialas si usas otra definición. |

## Notas importantes

- **«GLD, referencia»:** no existe una cadena de opciones gratuita del oro al contado. Los niveles son los del **ETF GLD** (cadena de Cboe con 15 min de retraso del cierre anterior) multiplicados por el **ratio XAU/GLD** de la fecha `rf`. Es una **referencia**: el ratio deriva despacio y varía unas décimas según la hora, así que cada nivel es una aproximación de unos pocos dólares. El método es el mismo que el de SPX/NDX (Gamma Flip, Call/Put Wall, Max Gamma, EM = GLD × GVZ / 100 / √252).
- **Datos en vivo:** DXY y el tipo real usan cierres diarios (`request.security`); el tipo real de FRED se publica con un día de retraso.
- **Hipótesis:** el signo de la posición de los creadores de mercado (calls +, puts −) no es observable. Nada de esto es una recomendación de compra o venta.
- **Medición:** en la web, `#/marcador` mide si el oro reaccionó a ±0,25×EM del nivel en la sesión siguiente (descriptivo; congelado hasta 20 sesiones).
