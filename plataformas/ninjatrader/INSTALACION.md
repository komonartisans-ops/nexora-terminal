# NexoraGex · instalación en NinjaTrader 8 (paso a paso)

**Qué hace:** en gráficos de **ES, MES, NQ y MNQ** dibuja Gamma Flip, Call Wall, Put Wall, Max Gamma y la banda EM, con una etiqueta de régimen arriba a la izquierda. Lee los niveles de `https://komonartisans-ops.github.io/nexora-terminal/data/gamma.json` cada 15 minutos (configurable). Es contexto, **no** da entradas.

**Requisitos:** NinjaTrader 8 (8.0.x o 8.1.x), conexión a internet desde el equipo y acceso a `komonartisans-ops.github.io` (HTTPS).

## 1. Copia el archivo

1. Descarga [`NexoraGex.cs`](NexoraGex.cs) (botón «Raw» de GitHub → clic derecho → «Guardar como…»).
2. Abre el Explorador de archivos de Windows y pega `NexoraGex.cs` en esta carpeta:  
   `Documentos\NinjaTrader 8\bin\Custom\Indicators\`

## 2. Compila

1. En el **Centro de control** de NinjaTrader: **Nuevo → Editor de NinjaScript**.
2. En el árbol de la izquierda abre **Indicators** y comprueba que aparece **NexoraGex**.
3. Con `NexoraGex` abierto, pulsa **Compilar** (F5) o el icono de la llave inglesa.
4. Abajo debe aparecer «Compilación correcta». Si sale algún error, copia el texto completo del mensaje (lo habitual es una versión muy antigua de NinjaTrader).

## 3. Añádelo al gráfico

1. Abre un gráfico de **ES** (o MES) o de **NQ** (o MNQ) con el contrato vigente, por ejemplo `ES 12-26`.
2. Clic derecho en el gráfico → **Indicadores…** → busca **NexoraGex** → **Añadir** → **Aceptar**.
3. A los pocos segundos verás las líneas: **dorada** = Gamma Flip, **roja** = Call Wall, **verde** = Put Wall, **azul discontinua** = Max Gamma, **banda azul** = EM.
4. Arriba a la izquierda, la etiqueta muestra el régimen (gamma positiva si el precio está sobre el flip, negativa si está debajo), la sesión de los niveles y la hora del archivo.

## 4. Parámetros (en la ventana de indicadores)

| Parámetro | Por defecto | Para qué sirve |
|---|---|---|
| URL de gamma.json | la de NEXORA | No la cambies salvo que alojes tu propia copia. |
| Minutos entre lecturas | 15 | Cada cuánto vuelve a leer el archivo (los niveles cambian una vez al día). |
| Mostrar Max Gamma / banda EM / etiqueta | sí | Activa o desactiva cada elemento. |
| Grosor de las líneas | 2 | |
| Horas hasta marcar «datos antiguos» | 72 | Si el archivo es más viejo, la etiqueta lo avisa. |

## Si algo no sale

- **«NEXORA GEX: leyendo gamma.json…» durante mucho rato:** mira la pestaña **Salida (Output)** del Centro de control: el indicador escribe allí el motivo (por ejemplo, un cortafuegos que bloquea `github.io`). Mientras haya un fallo, conserva la última lectura buena y la etiqueta muestra «Última lectura fallida».
- **«instrumento no admitido»:** solo ES, MES, NQ y MNQ.
- **Los niveles no coinciden con tu contrato:** los niveles son de futuro continuo con la base del día; en la semana del vencimiento trimestral (marzo, junio, septiembre, diciembre) comprueba la fecha de la sesión en la etiqueta.
- **Es contexto:** un nivel no es una señal. Las reglas de los avisos de Telegram y su medición están en la web (`#/gamma` y `#/marcador`).

## Qué lee el indicador (por si quieres revisarlo)

Solo estos campos de `gamma.json` → `indices` → `ES` / `NQ`: `sesion`, `regimen`, `spot_fut`, `flip.fut`, `call_wall.fut`, `put_wall.fut`, `max_gamma.fut` y `em.puntos`. No envía nada a ningún sitio: solo descarga el JSON público. Incluye su propio lector de JSON (sin librerías externas) y está escrito en C# 5 para compilar en NinjaTrader 8.

## Sobre la validación

El archivo se ha comprobado con un compilador de C# 5 contra una declaración mínima de la API de NinjaTrader y su lectura de `gamma.json` se ha probado con el archivo real (`python tools/validar_csharp.py`). **La prueba definitiva es el botón «Compilar» de tu NinjaTrader 8**: si aparece un error de compilación, envía el texto del mensaje.
