# Disparo externo de workflows (cron-job.org)

GitHub descarta la mayoría de los crones de `schedule`. Los crones del repositorio se mantienen como **respaldo**; el disparo fiable lo hace un servicio externo llamando a la API de GitHub (`workflow_dispatch`). Los tres workflows ya lo admiten:

| Workflow | Fichero | Entradas (`inputs`) |
|---|---|---|
| actualizar | `actualizar.yml` | `modo`: `horario` · `cierre` · `diario` · `todo` (defecto `diario`) |
| reacciones | `reacciones.yml` | `modo`: `vivo` (defecto) · `reconstruir` |
| agenda_diaria | `agenda_diaria.yml` | `forzar`: `false` (defecto) · `true` |

## 1. Token fine-grained (solo este repositorio, solo Actions)

1. GitHub → tu foto → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens** → **Generate new token**.
2. **Token name**: `cron-job.org nexora-terminal`. **Expiration**: 90 días (anota la fecha en tu calendario; al caducar los disparos dan 401 y el aviso de salud de la web lo detectará).
3. **Resource owner**: `komonartisans-ops`.
4. **Repository access** → **Only select repositories** → `nexora-terminal`.
5. **Permissions → Repository permissions** → **Actions: Read and write**. Deja todo lo demás en *No access* (*Metadata: Read-only* se añade solo y es obligatorio).
6. **Generate token** y copia el valor (empieza por `github_pat_`). No lo pegues en el chat, en el repositorio ni en capturas.

Prueba desde tu terminal (el token en una variable, nunca escrito en el comando):

```bash
read -rs GH_TOKEN; export GH_TOKEN
curl -i -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer $GH_TOKEN" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/komonartisans-ops/nexora-terminal/actions/workflows/agenda_diaria.yml/dispatches \
  -d '{"ref":"main"}'
```

Respuesta correcta: `HTTP/2 204` (sin cuerpo). `401` = token mal copiado o caducado · `403/404` = permisos o repositorio mal elegidos · `422` = una entrada inválida.

## 2. Tareas en cron-job.org (cuenta gratuita)

Crea cuenta en https://cron-job.org → **Cronjobs → Create cronjob**. En las tres tareas:

- **Request method**: `POST` (en *Advanced*).
- **Headers** (*Advanced → Headers*):

  | Clave | Valor |
  |---|---|
  | `Accept` | `application/vnd.github+json` |
  | `Authorization` | `Bearer <TU_TOKEN>` (pégalo solo en este campo) |
  | `X-GitHub-Api-Version` | `2022-11-28` |
  | `Content-Type` | `application/json` |

- **Request body**: el JSON de cada tarea (abajo).
- **Time zone**: la indicada en cada tarea. **Notify on failure**: activado. Éxito = HTTP `204`.

Base de las URL: `https://api.github.com/repos/komonartisans-ops/nexora-terminal/actions/workflows/<fichero>/dispatches`

### Tarea A · actualizar, cada hora en días laborables

| Campo | Valor |
|---|---|
| Title | `nexora actualizar horario` |
| URL | `https://api.github.com/repos/komonartisans-ops/nexora-terminal/actions/workflows/actualizar.yml/dispatches` |
| Time zone | `UTC` |
| Schedule (*User-defined*) | Minutos: `7` · Horas: `6,7,8,…,22` · Días del mes: todos · Meses: todos · Días de la semana: lunes a viernes |
| Body | `{"ref":"main","inputs":{"modo":"horario"}}` |

*(Opcionales, mismas cabeceras)*: `diario` a las 05:30 UTC lun-vie → `{"ref":"main","inputs":{"modo":"diario"}}`; `cierre` a las 21:30 UTC lun-vie → `{"ref":"main","inputs":{"modo":"cierre"}}`.

### Tarea B · reacciones, cada 5 minutos de 11:00 a 21:55 UTC en días laborables

Desde el 18-oct-2026 B1 cubre 11-21 UTC (antes 12-20) para que el aviso previo por Telegram llegue a los eventos de las 08:00 ET (aviso a las 11:30 UTC en verano) y a los resultados «después del cierre» de invierno (16:05 ET = 21:05 UTC, aviso a las 20:30 UTC). B2 (21:00) queda como respaldo redundante: la concurrencia de GitHub evita ejecuciones solapadas.

| Campo | B1 | B2 |
|---|---|---|
| Title | `NEXORA reacciones 11-21h` | `nexora reacciones 21h` |
| URL | `https://api.github.com/repos/komonartisans-ops/nexora-terminal/actions/workflows/reacciones.yml/dispatches` | igual |
| Time zone | `UTC` | `UTC` |
| Minutos | `0,5,10,…,55` | `0` |
| Horas | `11,12,…,21` | `21` |
| Días de la semana | lunes a viernes | lunes a viernes |
| Body | `{"ref":"main","inputs":{"modo":"vivo"}}` | `{"ref":"main","inputs":{"modo":"vivo"}}` |

Cada ejecución recoge todo lo vencido y sale en segundos si no hay nada pendiente (las fases tardías se registran con origen `vivo-tardío`). Solo despliega la web si hubo cambios.

### Tarea C · agenda, 8:00 Madrid

| Campo | Valor |
|---|---|
| Title | `nexora agenda 8h Madrid` |
| URL | `https://api.github.com/repos/komonartisans-ops/nexora-terminal/actions/workflows/agenda_diaria.yml/dispatches` |
| Time zone | `Europe/Madrid` (así el cambio de horario no importa) |
| Schedule | Minutos: `0` · Horas: `8` · Días de la semana: lunes a viernes |
| Body | `{"ref":"main"}` |

El script envía como mucho una vez por día (estado en `data/estado_agenda.json`), así que coincidir con el cron de GitHub no duplica el mensaje.

## 3. Respaldo y salud

- Los crones de `schedule` de GitHub siguen en los tres workflows como respaldo.
- La página **Agenda → Salud de los workflows** muestra la última ejecución de cada workflow y cuántas de las esperadas (el horario de arriba) se hicieron hoy. Solo cuentan ejecuciones lanzadas por `schedule` o `workflow_dispatch`.
- Si `actualizar` lleva más de 2 h sin ejecutarse en horario laborable (06-22 UTC, lun-vie), `engine/salud.py` envía un aviso por Telegram (uno por parada). `salud.py` corre dentro de `reacciones` y de `actualizar`; si ambos dejan de ejecutarse el aviso tampoco sale, y cron-job.org (*Notify on failure*) es la segunda red.
- Seguridad: el token solo puede lanzar workflows de este repositorio. Si sospechas que se ha filtrado, revócalo en GitHub y crea otro.

## 4. El modo horario recupera el diario y el cierre (auditoría 16-oct-2026)

cron-job.org solo dispara `modo=horario`; el build **diario** (05:30 UTC) y el **cierre** (21:30 UTC) dependen de los crones de GitHub, que no están garantizados
(15-oct: diario +4,6 h y cierre +2,3 h; 16-oct: el diario no salió). Por eso `engine/build.py` **escala** el modo horario: si ya son las 05:30 UTC y hoy no se ejecutó
`ciclo`, esa ejecución añade todas las etapas del diario; si son las 21:30 UTC y hoy no se ejecutó `gamma`, añade las del cierre. Se mide «ejecutada» (no «ok») para que
una fuente caída no relance el build completo cada hora. El modo efectivo queda en `meta.json` y en `data/ejecuciones.csv` (`horario+diario`, `horario+cierre`).

El modo horario incluye además `calendario` y `publicados` (y con ellos `agenda.json`), para que el día de una publicación el dato salga a la web en la hora siguiente.

*Opcional (no necesario ahora):* dos tareas más en cron-job.org con el mismo cuerpo que la tarea A (`{"ref":"main","inputs":{"modo":"diario"}}` a las 05:30 UTC lun-vie y
`{"ref":"main","inputs":{"modo":"cierre"}}` a las 21:30 UTC lun-vie) dejan al diario y al cierre a su hora exacta; sin ellas llegan con hasta una hora de retraso.
