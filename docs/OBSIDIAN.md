# Exportador a Obsidian (Fase 20) · «el cerebro lo sabe todo»

Un script que corre **en el PC de Ruiz** (no en GitHub) copia lo que sabe NEXORA a la bóveda `Mi Cerebro Digital`: fotos diarias, tesis, informes de Ruiz con su resultado, docs, registros y bitácora. Código: `tools/exportar_obsidian.py`. Pruebas: `PYTHONUTF8=1 python tools/prueba_exportar_obsidian.py` (sin red, sin Telegram, sin tocar la bóveda real).

## Reglas (no se negocian)

- **Solo escribe dentro de `60_Market_Intelligence/`, `10_Diario/Premercado/` y `10_Diario/Operaciones/`** de la bóveda. Cualquier otra ruta (o con `..`) se rechaza por código.
- **Nunca borra.** Nunca edita un CSV del repo.
- **Los snapshots diarios son inmutables:** si `02_Daily_Snapshots/AAAA-MM-DD.md` existe, ni se vuelve a calcular.
- **Una nota gestionada que Ruiz ha editado no se pisa.** Cada nota escrita por el exportador guarda su hash (en `%LOCALAPPDATA%\NexoraExportador\estado.json`, fuera de la bóveda). Si el hash del archivo ya no es el de la última exportación, la versión nueva va a `… (NEXORA v2).md` (luego `v3`…), se anota un AVISO en el log y el latido sale como `AVISO`. La v2 sí se mantiene al día mientras nadie la edite.
- **Las notas escritas a mano solo se amplían:** `Bitácora NEXORA AAAA-MM`, `Estado y pendientes`, `00 Sistema NEXORA (MOC)`, `Global Market State` y `Market Intelligence` conservan todo lo que ya tenían; el exportador añade al final un bloque propio entre `<!-- NEXORA:auto:… -->` y `<!-- /NEXORA:auto:… -->` (solo se reescribe lo que hay entre esas marcas) o, en la bitácora, líneas nuevas al final.
- **Idempotente:** una pasada sin novedades no cambia ni un byte de la bóveda.
- **Sin secretos:** usa los clones y las credenciales de git que ya existen en el PC (`gh`/Git Credential Manager). El log y los mensajes pasan por un filtro que enmascara tokens (`ghp_…`, `github_pat_…`, `https://usuario:clave@…`, `Bearer …`).

## Qué exporta

| Dónde (en `60_Market_Intelligence/`) | Qué | Tipo |
|---|---|---|
| `02_Daily_Snapshots/AAAA-MM-DD.md` | régimen, Fed, tesis por activo con intensidad, gamma de ES/NQ/US30/ORO (flip, call/put wall, Max Gamma «pin/acelera», EM), línea ORO, estado del spot del oro (verificado/dudoso y fuentes), petróleo, consumo XLY/XLP, crédito, eventos ALTA del día (con la reacción registrada), qué vigilar. Un día sin datos en el repo sale como **SIN DATO**; nada se reconstruye. | inmutable |
| `04_Theses/T-AAAAMMDD-ACTIVO.md` | una nota por tesis y activo **solo cuando cambia**, con enlace a la anterior (la primera enlaza a la del sistema anterior `T-20261001-…`). | inmutable |
| `05_Analisis/AAAA/<id>.md` y `00 Índice de análisis.md` | informes de Ruiz (diarios y semanales), **texto completo** (la bóveda es privada) + cotejo ✅/⚠️/— con NEXORA + resultado CUMPLIDO/FALLIDO/MIXTO a T+1/T+5 con su umbral (EM o FIJO). Leen el repo privado `nexora-diario` y los CSV públicos. | gestionada (se actualiza al llegar el resultado) |
| `07_Sistema_NEXORA/Docs/*.md` | copia de **todo** `docs/` del repo, actualizada si cambia. | gestionada |
| `07_Sistema_NEXORA/Registros/*.md` | una nota por registro clave (marcador de señales, resultados del análisis, reacciones a eventos, discrepancias revisadas, contraste del spot del oro, vigilar_cierre) con las últimas 30 filas y enlace al CSV. | gestionada |
| `07_Sistema_NEXORA/Bitácora NEXORA AAAA-MM.md` | una línea por commit del repo (excepto los automáticos de datos): fecha, tipo (`feat`/`fix`/`cambio`), qué y por qué; además fallos de etapas, vigilantes fallidos, discrepancias y revisiones de datos («el cerebro guarda los errores, no solo los aciertos»). No duplica. | solo añadir |
| `01_State/Global Market State.md`, `00_MOC/Market Intelligence.md`, `07_Sistema_NEXORA/00 Sistema NEXORA (MOC).md`, `Estado y pendientes.md` | bloques propios con enlaces a todo lo anterior y tesis vigentes. | bloque delimitado |

### Diario de operaciones → `10_Diario/Operaciones/AAAA-MM.md`

Lee `nexora-diario/diario/AAAA-MM.json` (el repo privado) y escribe una nota por mes, **solo añadiendo**: una fila `ALTA` por operación (fecha, hora, activo, setup A = Barrido+vuelta / B = Ruptura+continuación / Otro, dirección, R, resultado en $ y GANADA/PERDIDA/BE, confirmaciones y la foto NEXORA: estado, tesis, gamma, régimen, evento ALTA a 2 h y hora del contexto). Si corriges una operación se añade una fila `REVISADA` (la antigua queda); si la borras, una fila `ANULADA`. Cada fila lleva el `id` y un hash corto para detectar cambios sin tocar lo ya escrito. Arriba, un bloque delimitado «Resumen del mes» (único trozo que se reescribe) con n, acierto, esperanza y profit factor por setup (con «n<20: sin conclusión»).

**R:** el Diario guarda el resultado en $ y las operaciones no traen R, así que la columna R y la esperanza en R salen como **SIN DATO** (no se inventa); si una operación trae un campo `r`, se usa. La esperanza se da además en $ por operación.

`10_Diario/Premercado/` está permitido pero **no se escribe** en esta fase (no estaba en la lista de lo que se exporta).

### Cuándo está «cerrado» un día

Un día se escribe cuando **ya pasó** (UTC) o, si es el de hoy, cuando existe una pasada de cierre de **≥ 21:30 UTC** de ese día **y** una foto de `contexto` generada después. El cierre de las 00:18 UTC pertenece a la sesión anterior. Para la gamma y el spot se usa la última versión publicada de la sesión de ese día, aunque el cierre haya corrido pasada la medianoche UTC (hasta las 12:00 UTC del día siguiente), leída del historial de git del propio repo; si la sesión de la gamma no es la del día, la fila lo dice (⚠ no es de este día).

## Cómo se ejecuta

El exportador trabaja con **clones propios** en `%LOCALAPPDATA%\NexoraExportador\repos\` (`nexora-terminal` y `nexora-diario`), para no interferir con la carpeta donde se desarrolla. En cada pasada: `git pull --rebase --autostash` de ambos (si uno falla, se exporta con lo que haya y la pasada sale como `AVISO`), exportación y latido.

```bash
python tools/exportar_obsidian.py                  # pasada completa
python tools/exportar_obsidian.py --programado     # lo que lanza el Programador de tareas
python tools/exportar_obsidian.py --registrar-tarea
python tools/exportar_obsidian.py --vista-previa 2026-10-22   # imprime el snapshot de ese día sin escribir nada
```

### Tarea de Windows «NEXORA exportar a Obsidian»

Una sola tarea con tres disparadores: diaria a las **08:30** y **23:45** (hora local) y **al iniciar sesión**; con «ejecutar lo antes posible si se perdió una ejecución». `--programado` solo trabaja si la última pasada es anterior a la última hora programada (08:30 / 23:45) ya pasada: un inicio de sesión con todo al día no hace nada. Log local: `%LOCALAPPDATA%\NexoraExportador\exportador.log` (sin secretos). Estado: `…\estado.json`.

## Ejecución anclada (seguridad)

La tarea de Windows **no ejecuta el código que acaba de descargar**: ejecuta una copia fija, `%LOCALAPPDATA%\NexoraExportador\aprobado\exportar_obsidian.py` (solo lectura, con su commit y hash en `aprobado.json`). Los **datos** (repos público y privado) se siguen descargando con normalidad en cada pasada; el **código del exportador** solo cambia cuando lo apruebas.

- Si `tools/exportar_obsidian.py` cambia en `main`, la pasada sigue con la versión aprobada, registra el latido como `PENDIENTE@<commit aprobado>` y sube `data/obsidian_pendiente.json` (commit nuevo, hash y resumen del diff, con tokens enmascarados).
- `#/integridad` muestra el banner ámbar «Exportador actualizado, pendiente de aprobar» con el diff resumido, y se envía **un** Telegram por versión nueva (clave `obsidian_pendiente|<hash>`).
- Para aprobar (a prueba de aprobar código no revisado): revisa el diff completo (`git diff` en el clon `%LOCALAPPDATA%\NexoraExportador\repos\nexora-terminal`, o el que muestra `--aprobar` sin argumento) y ejecuta, **con la copia ya anclada**, no con el archivo recién descargado: `python %LOCALAPPDATA%\NexoraExportador\aprobado\exportar_obsidian.py --aprobar <hash>`. Sin hash solo muestra el diff y el hash. Con el hash: no hace `pull` (usa lo que la última pasada trajo), rechaza si el hash no es el del clon o si el archivo del clon difiere de `HEAD`, copia el contenido del objeto git (no del árbol de trabajo), exige terminal interactiva y que escribas `APROBAR`. El siguiente latido limpia el aviso.
- Regla: no aprobar sin haber leído el diff. El exportador anclado no importa ni ejecuta ningún otro código del repo (solo lee datos).
- `--registrar-tarea` apunta a la copia anclada y exige haber aprobado una versión antes.

## Latido y aviso

Cada pasada añade una fila a **`data/obsidian_latido.csv`** (`fecha,hora_utc,estado`: solo eso) y la sube al repo público (`latido obsidian … [skip ci]`, con reintentos si un bot escribió a la vez). `estado` = `OK`, `AVISO` (exportó, pero con algún aviso: nota editada guardada como v2, repo sin poder actualizarse…) o `ERROR` (no pudo exportar).

`engine/integridad.py` lo vigila: **si los 2 últimos días completos no tienen ninguna pasada OK/AVISO** → tarjeta roja en `#/integridad` («Exportador a Obsidian · latido») y **un** Telegram por racha (clave `obsidian|<primer día sin exportar>` en `data/vigilante_estado.json`). Los días anteriores al primer latido no cuentan; sin ningún latido, SIN DATO y sin alerta. Se cuentan días naturales (si el PC está apagado dos días seguidos, avisa).

## Qué hacer si algo falla

- *El aviso de Telegram llegó:* abre el log, mira la última línea `ERROR`/`AVISO`. Causas típicas: PC apagado, sin internet, credencial de git caducada (`gh auth login`), la bóveda movida de sitio (`--boveda RUTA` o variable `NEXORA_BOVEDA`).
- *Una nota «(NEXORA v2)»:* editaste la original. Si quieres volver a la automática, mueve tu versión a otro nombre; el exportador dejará la v2 como está y no volverá a tocar la editada.
