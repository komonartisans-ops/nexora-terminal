# NexoraNiveles en NinjaTrader 8 (Fase 21) · guía paso a paso

**Qué hace:** dibuja en tu gráfico de **GC, ES, NQ, YM** (y sus micros **MGC, MES, MNQ, MYM**) los niveles de gamma del día en **precio de futuro**: Gamma Flip, Call Wall, Put Wall y Max Gamma. Los descarga **solo**, cada 15 minutos, de un archivo público de NEXORA: ya no hay que pegar nada a mano. Si los niveles no son los de la última sesión, **te lo dice en rojo** y apaga las líneas. Es contexto, **no** da entradas.

**Qué necesitas:** NinjaTrader 8 (escrito para la 8.0.28; su lógica está probada fuera de NinjaTrader y lo que falta por confirmar es solo el botón «Compilar» de tu equipo, paso 2), conexión a internet y acceso a `komonartisans-ops.github.io`. No hace falta ninguna clave ni cuenta. No toca MZpack: no usa ninguno de los colores de su Volume Profile (magenta, naranja y azul).

## 1. Copia el archivo (una sola vez)

1. Abre [`NexoraNiveles.cs`](../plataformas/ninjatrader/NexoraNiveles.cs) en GitHub y pulsa el botón **«Raw»**; con clic derecho elige **«Guardar como…»** y guárdalo con el nombre `NexoraNiveles.cs` (que no se llame `NexoraNiveles.cs.txt`).
2. Abre el **Explorador de archivos** de Windows y pega ese archivo en esta carpeta:
   `Documentos\NinjaTrader 8\bin\Custom\Indicators\`

## 2. Compila (una sola vez)

1. En el **Centro de control** de NinjaTrader: menú **Nuevo → Editor de NinjaScript** (NinjaScript Editor).
2. En el árbol de la izquierda abre la carpeta **Indicators** y comprueba que aparece **NexoraNiveles**. Haz doble clic para abrirlo.
3. Con él abierto pulsa **F5** (o el icono de la llave inglesa «Compile»).
4. Abajo debe poner **«Compilación correcta»** (sin errores en rojo). Si sale un error, copia el texto completo del mensaje y envíalo: es lo único que hace falta para corregirlo.

> NinjaTrader añade solo al final del archivo un bloque «NinjaScript generated code». Es normal; no lo toques.

## 3. Añádelo al gráfico de 5 minutos

1. Abre un gráfico de **5 minutos** del contrato vigente (por ejemplo `GC 12-26` o `ES 12-26`).
2. Clic derecho sobre el gráfico → **Indicadores…** (Indicators).
3. En la lista de la izquierda busca **NexoraNiveles** y pulsa **Añadir** (Add).
4. A la derecha deja los valores por defecto (explicados abajo) y pulsa **Aceptar**.
5. A los pocos segundos verás las líneas: **ámbar** = Gamma Flip y Max Gamma; **gris claro** = Call Wall y Put Wall. Todas finas y discontinuas, con una etiqueta pequeña a la derecha, por ejemplo `CW 4156` o `MG 3774 · acelera`.
6. **Importante para ver las etiquetas:** clic derecho sobre el gráfico → **Propiedades…** → **Margen derecho** (Right side margin) → pon **120** y **Aceptar**. Sin margen, las etiquetas se salen de la pantalla.

## 4. Añádelo al gráfico de 1 minuto

Repite exactamente los pasos 3.1 a 3.4 en el gráfico de 1 minuto, y en la ventana de parámetros cambia **Modo de dibujo** a **SoloMasCercano**: así solo verás el nivel más cercano por encima y el más cercano por debajo del precio, sin llenar el gráfico. Pon también el margen derecho (3.6).

## 5. Qué significan los modos de dibujo

| Modo | Qué dibuja | Para qué |
|---|---|---|
| **Cercanos** (por defecto) | Los niveles a menos de **1 EM** del precio (el movimiento esperado de un día), como máximo **3**, los más cercanos | Gráfico de 5 min |
| **Todos** | Los 4 niveles, estén cerca o lejos | Ver el mapa completo |
| **SoloMasCercano** | Solo el más cercano por encima y el más cercano por debajo del precio (máximo 2 líneas) | Gráfico de 1 min |

Si dos niveles caen en el mismo precio (por ejemplo Put Wall y Max Gamma) se dibuja **una sola línea** con las dos etiquetas: `PW/MG 3774 · acelera`. **pin** = el nivel tiende a atraer el precio; **acelera** = tiende a empujarlo (hipótesis del método, no certeza).

## 6. Qué te avisa y cómo leerlo

| Lo que ves | Qué significa |
|---|---|
| Texto gris pequeño arriba a la izquierda: `NEXORA GC · niveles de la sesión 23-10 · 2 en pantalla · gamma negativa` | Todo en orden: los niveles son los de la última sesión de mercado |
| Texto **rojo** `CADUCADO 23-10` y las líneas en **gris oscuro** | El archivo no es de la última sesión de mercado (el cierre de NEXORA no se ha publicado o ha fallado). **No uses esos niveles** hasta que desaparezca |
| Texto **ámbar** `SPOT DUDOSO` y las líneas en gris oscuro | (Solo oro.) El spot del oro no coincidió entre fuentes y NEXORA mantuvo el ratio anterior: los niveles del oro son menos fiables hoy |
| Texto ámbar `lectura fallida: se usa la de las 09:45` | No se pudo descargar el archivo ahora; el indicador **conserva la última lectura buena** y lo indica |
| `instrumento no admitido` | El gráfico no es GC, ES, NQ, YM ni un micro |

**Cuándo se considera «caducado»:** el indicador calcula la última sesión de la bolsa de Nueva York (con sus festivos) y exige que el archivo sea de esa sesión, dándole **5 horas de margen** tras el cierre de las 16:00 ET para que el cierre de NEXORA publique. Por eso en sábado, domingo y festivos **no** aparece el aviso (vale la sesión del viernes o la anterior al festivo), y el lunes por la tarde sí aparecería si el cierre del lunes no llegó a publicarse.

## 7. Parámetros (ventana de indicadores)

| Parámetro | Por defecto | Para qué sirve |
|---|---|---|
| URL de niveles_nt8.json | la de NEXORA | No la cambies salvo que alojes tu propia copia |
| Minutos entre lecturas | 15 | Cada cuánto se vuelve a descargar (los niveles cambian una vez al día) |
| Horas de gracia tras el cierre | 5 | Margen antes de exigir la sesión nueva |
| Modo de dibujo | Cercanos | Cercanos / Todos / SoloMasCercano |
| Máximo de niveles (modo Cercanos) | 3 | |
| Distancia máxima en EM (modo Cercanos) | 1,0 | |
| Mostrar texto de estado | sí | El texto gris pequeño (los avisos rojo y ámbar salen siempre) |
| Posición del aviso | Arriba izquierda | Mueve los textos si chocan con otro panel (por ejemplo el de MZpack) |

## Si algo no sale

- **«leyendo niveles_nt8.json…» durante mucho rato o «sin lectura todavía»:** abre en el Centro de control la pestaña **Salida** (Output): el indicador escribe allí el motivo (un cortafuegos o antivirus que bloquea `github.io`, o no hay internet).
- **No veo etiquetas:** falta el margen derecho (paso 3.6).
- **Sale `CADUCADO` y es lunes por la tarde o más tarde:** mira en la web `#/integridad` si el cierre de NEXORA corrió; mientras no publique, el aviso es correcto.
- **Dos indicadores con líneas repetidas:** si ya tenías **NexoraGex** (solo ES/NQ) en el gráfico, quítalo: NexoraNiveles hace lo mismo y además cubre GC y YM y avisa de la caducidad.
- **Error al compilar:** copia el mensaje entero (paso 2.4).

## Para curiosos: qué se descarga y qué hace el indicador

- **Archivo:** `https://komonartisans-ops.github.io/nexora-terminal/data/niveles_nt8.json`. Lo genera la etapa `niveles_nt8` del cierre de NEXORA (21:30 UTC) y del build diario, justo después de la gamma de US30; reempaqueta lo que ya publican `gamma.json` (ES, NQ), `gamma_us30.json` (YM) y `gamma_oro.json` (GC). Sin datos personales ni claves.
- **Por instrumento** (en puntos de precio del contrato de futuro; los micros llevan los mismos niveles y un campo `alias_de`): `sesion` (la de la cadena de opciones de la que salen los niveles; en el oro, la del ratio XAU/GLD «rf»), `regimen`, `flip`, `call_wall`, `put_wall`, `max_gamma`, `max_gamma_tipo` (`pin` | `acelera`), `em`, `spot_estado` y `generado_utc`.
- **`spot_estado`:** en el oro, el contraste de la Fase 19/20 (`verificado`, `dudoso` si la diferencia entre fuentes supera el 0,3 %, o `no_verificado`). En ES, NQ y YM, `verificado` si la base futuro − índice se midió en el mismo minuto y `no_verificado` si es aproximada; ahí no hay contraste, así que nunca sale `dudoso`.
- **Descarga:** en un hilo aparte (un temporizador), con la clase de red estándar de .NET (`WebClient`) y un límite de 12 s. Se eligió `WebClient` y no `HttpClient` porque NinjaTrader 8 no enlaza `System.Net.Http` por defecto y obligaría a añadir una referencia a mano. Si falla, se conserva la última lectura buena.
- **Rendimiento:** `OnBarUpdate` solo guarda el último cierre y compara una «firma» de lo que habría que dibujar; solo si cambia algo (otra barra, otro nivel cercano, otro estado) se vuelven a crear como mucho 4 líneas y 4 etiquetas. No hay bucles sobre barras ni cálculos pesados.
- **La lógica está probada fuera de NinjaTrader:** `PYTHONUTF8=1 python tools/prueba_niveles_nt8.py` compila `NexoraNiveles.cs` con un compilador de C# 5 y ejecuta de verdad su calendario de sesiones (idéntico a un cálculo independiente en Python en más de 21 000 instantes), la caducidad (sesión de hoy, fin de semana, festivo, caducada, spot dudoso) y la selección de niveles. **La prueba definitiva de que compila en tu versión es el botón «Compilar» (F5) del paso 2.**
- **Limitaciones conocidas:** los cierres extraordinarios de la bolsa por duelo nacional no están modelados; los niveles son de futuro continuo con la base del día de la sesión de los niveles, así que en la semana del vencimiento trimestral (marzo, junio, septiembre, diciembre) conviene comprobar la fecha en el texto de estado.
