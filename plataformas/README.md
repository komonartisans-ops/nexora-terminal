# NEXORA · Niveles de gamma en tus plataformas

Dos indicadores **de contexto** (no de entradas): dibujan en tu gráfico los niveles que NEXORA calcula cada día con la cadena de opciones de Cboe (15 min de retraso) del cierre anterior, ya convertidos a **precio de futuro** (ES y NQ).

| Nivel | Qué es |
|---|---|
| **Gamma Flip** | Precio al que el GEX neto cambia de signo. Por encima = gamma positiva; por debajo = gamma negativa (hipótesis del método). |
| **Call Wall** | Tramo por encima del precio con mayor gamma de calls. |
| **Put Wall** | Tramo por debajo del precio con mayor gamma de puts. |
| **Max Gamma** | Tramo con mayor gamma absoluta (calls + \|puts\|). |
| **EM** | Movimiento esperado de un día: `precio × VIX (ES) o VXN (NQ) / 100 / √252`, con la volatilidad del cierre de la sesión de los niveles. Se dibuja como banda alrededor del cierre anterior. |

> Son **niveles de referencia, no señales**. El método es propio (CRITERIO NEXORA, documentado en la página «Gamma de índices» de la web) y se apoya en una hipótesis no observable: que los creadores de mercado están largos de calls y cortos de puts de los clientes. Nada de esto es una recomendación de compra o venta.

## Elige tu plataforma

| Plataforma | Cómo recibe los niveles | Carpeta | Instalación |
|---|---|---|---|
| **NinjaTrader 8** | Lee solo `https://komonartisans-ops.github.io/nexora-terminal/data/gamma.json` cada 15 minutos | [`ninjatrader/`](ninjatrader/) | [`INSTALACION.md`](ninjatrader/INSTALACION.md) |
| **NinjaTrader 8 · NexoraNiveles** (Fase 21, recomendado) | Descarga solo `…/data/niveles_nt8.json` cada 15 minutos: GC, ES, NQ, YM y micros, en precio de futuro, con aviso rojo de «CADUCADO dd-mm» y ámbar de «SPOT DUDOSO» | [`ninjatrader/NexoraNiveles.cs`](ninjatrader/NexoraNiveles.cs) | [`docs/INSTALACION_NT8.md`](../docs/INSTALACION_NT8.md) |
| **TradingView** | Tú pegas la línea que NEXORA te envía por Telegram a las 15:00 (Madrid) | [`tradingview/`](tradingview/) | [`INSTALACION.md`](tradingview/INSTALACION.md) |
| **TradingView · Oro** | Tú pegas la línea `XAU …` que llega en el mismo Telegram de las 15:00 (niveles de GLD, referencia, en precio XAU/USD) | [`tradingview/`](tradingview/) | [`INSTALACION_ORO.md`](tradingview/INSTALACION_ORO.md) |

## La línea de Telegram (TradingView)

Cada día laborable a las **15:00 de Madrid** llega un mensaje con una línea como esta (precios de futuro, punto decimal, `na` si falta un nivel):

```
ES flip=7804.0;cw=7843.6;pw=7693.6;em=97.0;maxg=7743.6 | NQ flip=29920.4;cw=29892.0;pw=28592.0;em=502.1;maxg=29392.0
```

El mensaje indica también la sesión de la cadena de Cboe de la que salen los niveles, la fuente y, si los niveles tienen más de 4 días, un aviso de antigüedad.

## Oro (XAU/USD): línea `XAU` y el indicador «NEXORA Oro»

El mismo mensaje de las 15:00 trae una segunda línea para el oro:

```
XAU tesis=alcista;int=debil;flip=4167.1;cw=4144.2;pw=3762.5;em=57.8;maxg=4253.2;ratio=10.9057;rf=2026-10-19;cot=largo-bajo_p27;etf=+3.1;evento=no
```

- Los niveles (`flip`, `cw`, `pw`, `maxg`, `em`) son los de la cadena de opciones del ETF **GLD** (Cboe), pasados a precio XAU/USD con el ratio XAU/GLD (`ratio`, de la fecha `rf`). Se etiquetan siempre **«GLD, referencia»**: no hay cadena gratuita del oro al contado.
- `tesis` e `int` salen de la tesis de oro de NEXORA; `cot` = lado, nivel y percentil a 3 años del dinero gestionado en COMEX; `etf` = toneladas del trust GLD en 5 sesiones; `evento` = eventos ALTA del día con hora de Madrid (`@na` si no hay hora publicada, `no` si no hay).
- El indicador [`NexoraOro.pine`](tradingview/NexoraOro.pine) añade la parte en vivo (DXY y tipo real a 10 años `FRED:DFII10` frente a su media de 50, y el aviso «oro sube con tipo real al alza» en 5 sesiones), PDH/PDL y los máximos/mínimos de Asia y Londres. Instalación: [`INSTALACION_ORO.md`](tradingview/INSTALACION_ORO.md).
- En la web: `#/gamma` (pestañas US500, US100, US30 y ORO) y `#/marcador` («Gamma oro»: ¿tocó el oro la zona nivel ± 0,25×EM en la sesión siguiente?, medido sobre GLD, congelado hasta 20 sesiones).

## De dónde salen los datos y con qué retraso

- **Opciones:** Cboe (`cdn-api.cboe.com`), cadena con 15 minutos de retraso, tomada al cierre de Nueva York. El interés abierto es el de la víspera (la OCC lo actualiza cada mañana).
- **Conversión a futuro:** nivel del futuro = nivel del índice + base (futuro − índice en el mismo minuto, velas de 5 min de Yahoo Finance).
- **Cuándo se actualizan:** una vez por día, en la ejecución de cierre (21:30 UTC). Hasta entonces, los niveles son los del cierre anterior. Si el futuro cambia de contrato (vencimiento trimestral), la base del día ya lo recoge; en la ventana de roll conviene mirar la fecha de la sesión.
- **Comprobación:** en la web, `#/gamma` muestra los mismos niveles con su fecha y el método completo.

## Avisos de Telegram durante la sesión (no hace falta instalar nada)

Además, NEXORA avisa por Telegram durante la sesión regular (09:30–16:00 ET) de cuatro hechos de precio sobre estos niveles, con velas de 5 min: cambio de régimen (2 cierres al otro lado del flip), techo en gamma positiva (≤ 0,25 × EM del Call Wall), pérdida del Put Wall en gamma negativa (2 cierres por debajo) y EM agotado (rango del día ≥ 100 % del EM). Máximo 6 al día, sin repetir el mismo en 60 min. Cada aviso trae el hecho, el régimen, la invalidación, el retraso de los datos y si hay un dato de importancia alta a ±15 min. Su historial y su medición (MFE/MAE a 15, 30 y 60 min) están en `#/marcador` → «Gamma intradía».
