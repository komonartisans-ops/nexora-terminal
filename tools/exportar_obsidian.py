#!/usr/bin/env python3
"""NEXORA · exportador a Obsidian (Fase 20: «el cerebro lo sabe todo»). Corre en el PC de Ruiz (Programador de tareas), NO en GitHub.

Qué hace en cada pasada (idempotente: sin novedades no toca ni un archivo de la bóveda):
  1. git pull del repo público (nexora-terminal) y del privado (nexora-diario) en clones propios del exportador (nunca imprime credenciales).
  2. Escribe SOLO dentro de 60_Market_Intelligence/ y 10_Diario/Premercado/ de la bóveda. Nunca borra.
       · 02_Daily_Snapshots/AAAA-MM-DD.md   inmutables: si existen, no se tocan. Un día sin datos en el repo sale como «SIN DATO».
       · 04_Theses/T-AAAAMMDD-ACTIVO.md     una nota por tesis y activo solo cuando cambia, con enlace a la anterior (inmutables).
       · 05_Analisis/AAAA/<id>.md           informes de Ruiz (texto completo) + cotejo + resultado (se actualiza cuando llega el resultado).
       · 07_Sistema_NEXORA/{Docs,Registros}  copia de docs/ y últimas 30 filas de los registros clave (los CSV no se tocan).
       · Bitácora NEXORA AAAA-MM            una línea por commit del repo, fallo y revisión de datos; solo se añade al final.
       · Notas escritas a mano (Bitácora, Estado y pendientes, MOC, Global Market State…): solo se AMPLÍAN con un bloque propio delimitado
         por <!-- NEXORA:auto:… --> o con líneas añadidas al final. Lo que ya había nunca se reescribe.
  3. Si una nota gestionada fue editada por Ruiz (su hash no es el de la última exportación) NO se pisa: se crea «… (NEXORA v2).md» y se avisa.
  4. Latido: añade una fila a data/obsidian_latido.csv (fecha, hora, estado) y la sube al repo público. Si falla 2 días seguidos,
     integridad.py avisa en #/integridad y por Telegram (una vez por racha).

Uso:
  python tools/exportar_obsidian.py                    pasada completa (clones propios, latido)
  python tools/exportar_obsidian.py --programado       lo que lanza el Programador de tareas (solo corre si toca o se perdió la última)
  python tools/exportar_obsidian.py --registrar-tarea  crea la tarea de Windows (08:30, 23:45 y al iniciar sesión)
  python tools/exportar_obsidian.py --vista-previa AAAA-MM-DD   imprime el snapshot de ese día sin escribir nada
Opciones de prueba: --boveda RUTA --publico RUTA --privado RUTA --estado RUTA --sin-git --sin-latido --hoy AAAA-MM-DD
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
RAIZ_SCRIPT = os.path.dirname(HERE)
UTC = dt.timezone.utc

URL_PUBLICO = "https://github.com/komonartisans-ops/nexora-terminal.git"
URL_PRIVADO = "https://github.com/komonartisans-ops/nexora-diario.git"
WEB_CSV = "https://github.com/komonartisans-ops/nexora-terminal/blob/main/data/"
BOVEDA_DEF = r"C:\Users\ruizt\OneDrive\Documentos\Mi Cerebro Digital"
# Fuera de %LOCALAPPDATA%: las apps empaquetadas (MSIX, como Claude) virtualizan AppData y el Programador de tareas no vería los archivos.
BASE = os.environ.get("NEXORA_BASE") or os.path.join(os.path.expanduser("~"), "NexoraExportador")
MI = "60_Market_Intelligence"
SIS = MI + "/07_Sistema_NEXORA"
ZONAS = (MI + "/", "10_Diario/Premercado/", "10_Diario/Operaciones/")      # lo único donde el exportador puede escribir
DESDE = "2026-10-02"
SLOTS_LOCALES = ("08:30", "23:45")
FILAS_REGISTRO = 30
TAREA = "NEXORA exportar a Obsidian"
SECRETO = re.compile(r"(gh[pousr]_[A-Za-z0-9]{10,}|github_pat_[A-Za-z0-9_]{10,}|https://[^/\s:@]+:[^@\s]+@|x-access-token:[^@\s]+|Bearer\s+\S+)")
BOT = re.compile(r"(\[skip ci\]|^(datos (horario|diario|cierre|todo)|reacciones|vigilante del cierre|agenda diaria|niveles gamma|latido obsidian)\b)", re.I)
SLUGS = {"Oro": "ORO", "Nasdaq 100": "NDX", "S&P 500": "SPX", "Bitcoin": "BTC", "US30 · Dow Jones": "US30", "Russell 2000": "RUT"}


def limpiar(t):
    return SECRETO.sub("«secreto»", str(t))


# ============================================================================ utilidades de texto
def n(x, d=1, signo=False):
    """Número a texto español (miles con punto, decimales con coma). None → SIN DATO."""
    if x is None or x == "":
        return "SIN DATO"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x)
    s = f"{v:,.{d}f}".replace(",", "§").replace(".", ",").replace("§", ".")
    return ("+" + s if v > 0 and signo else s)


def celda(x):
    return str(x if x is not None else "").replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


def yaml(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if v is None:
        return "null"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(json.dumps(x, ensure_ascii=False) for x in v) + "]"
    return json.dumps(str(v), ensure_ascii=False)


def frontmatter(d):
    return "---\n" + "\n".join(f"{k}: {yaml(v)}" for k, v in d.items()) + "\n---\n"


def tabla(cabeceras, filas):
    if not filas:
        return "_(sin filas)_\n"
    out = ["| " + " | ".join(cabeceras) + " |", "|" + "|".join("---" for _ in cabeceras) + "|"]
    out += ["| " + " | ".join(celda(c) for c in f) + " |" for f in filas]
    return "\n".join(out) + "\n"


def sha(t):
    return hashlib.sha256(t.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def fecha_es(d):
    return f"{d[8:10]}-{d[5:7]}-{d[:4]}"


# ============================================================================ git
def git(repo, *a, timeout=240):
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never", "LC_ALL": "C.UTF-8"}
    r = subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, env=env)
    return r.returncode, limpiar(r.stdout), limpiar(r.stderr)


def preparar_clon(ruta, url, log):
    """Clona si falta; si existe, trae lo nuevo. Devuelve (ok, vacio, mensaje)."""
    try:
        if not os.path.isdir(os.path.join(ruta, ".git")):
            os.makedirs(os.path.dirname(ruta), exist_ok=True)
            env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
            r = subprocess.run(["git", "clone", url, ruta], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900, env=env)
            if r.returncode != 0:
                return False, False, "clone: " + limpiar(r.stderr)[-200:]
        rc, _, _ = git(ruta, "rev-parse", "--verify", "HEAD")
        if rc != 0:
            rc2, _, _ = git(ruta, "fetch", "origin")
            rc3, _, _ = git(ruta, "rev-parse", "--verify", "origin/HEAD")
            if rc3 != 0:
                return True, True, "repositorio vacío"
        rc, _, err = git(ruta, "pull", "--rebase", "--autostash")
        if rc != 0:
            return False, False, "pull: " + err.strip()[-200:]
        return True, False, "al día"
    except Exception as e:  # noqa: BLE001
        return False, False, f"{type(e).__name__}: {limpiar(e)[:150]}"


# ============================================================================ estado local y registro
class Estado:
    """Hashes de lo exportado (para detectar ediciones de Ruiz), líneas de bitácora ya escritas y última pasada. Vive FUERA de la bóveda."""
    def __init__(self, ruta):
        self.ruta = ruta
        self.d = {"hashes": {}, "lineas": [], "ultima_pasada_local": None, "ultima_ok_utc": None}
        try:
            self.d.update(json.load(open(ruta, encoding="utf-8")))
        except (OSError, ValueError):
            pass
        self.sucio = False

    def guardar(self):
        if not self.sucio:
            return
        os.makedirs(os.path.dirname(self.ruta), exist_ok=True)
        tmp = self.ruta + ".tmp"
        json.dump(self.d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        os.replace(tmp, self.ruta)
        self.sucio = False

    def hash(self, rel):
        return self.d["hashes"].get(rel)

    def poner_hash(self, rel, h):
        if self.d["hashes"].get(rel) != h:
            self.d["hashes"][rel] = h
            self.sucio = True


class Boveda:
    """Escribe en la bóveda con las reglas de la Fase 20: nunca borra, no pisa ediciones, no toca lo que no cambia."""
    def __init__(self, raiz, estado, simular=False):
        self.raiz, self.estado, self.simular = raiz, estado, simular
        self.res = {"creadas": [], "actualizadas": [], "v2": [], "iguales": 0, "ampliadas": [], "avisos": []}

    def ruta(self, rel):
        rel = rel.replace("\\", "/")
        if ".." in rel.split("/") or not any(rel.startswith(z) for z in ZONAS):
            raise ValueError(f"fuera de la zona permitida: {rel}")
        return os.path.join(self.raiz, *rel.split("/"))

    def leer(self, rel):
        try:
            return open(self.ruta(rel), "r", encoding="utf-8", newline="").read().replace("\r\n", "\n")
        except OSError:
            return None

    def _escribir(self, rel, texto):
        p = self.ruta(rel)
        if not self.simular:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            tmp = p + ".nexora.tmp"
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(texto)
            os.replace(tmp, p)
        self.estado.poner_hash(rel, sha(texto))

    def inmutable(self, rel, texto):
        if self.leer(rel) is not None:
            self.res["iguales"] += 1
            return "existe"
        self._escribir(rel, texto)
        self.res["creadas"].append(rel)
        return "creada"

    def gestionada(self, rel, texto):
        """Crea o actualiza una nota nuestra. Si Ruiz la editó (hash distinto al de la última exportación) crea «(NEXORA v2)» y avisa."""
        if not texto.endswith("\n"):
            texto += "\n"
        base = rel[:-3] if rel.endswith(".md") else rel
        for k in range(1, 20):
            r = rel if k == 1 else f"{base} (NEXORA v{k}).md"
            cur = self.leer(r)
            if cur is None:
                self._escribir(r, texto)
                (self.res["creadas"] if k == 1 else self.res["v2"]).append(r)
                if k > 1:
                    self.res["avisos"].append(f"«{rel}» fue editada: la versión nueva está en «{r}»")
                return "creada" if k == 1 else "v2"
            if sha(cur) == sha(texto):
                self.estado.poner_hash(r, sha(texto))
                self.res["iguales"] += 1
                return "igual"
            if self.estado.hash(r) == sha(cur):          # no editada desde la última exportación: se actualiza
                self._escribir(r, texto)
                self.res["actualizadas"].append(r)
                return "actualizada"
            # editada por Ruiz (o sin registro de origen): no se pisa; se prueba la siguiente versión
        raise RuntimeError(f"demasiadas versiones de {rel}")

    def bloque(self, rel, clave, contenido, crear=None):
        """Amplía una nota con un bloque propio <!-- NEXORA:auto:clave -->…<!-- /NEXORA:auto:clave -->. Solo se reescribe lo que hay entre las marcas."""
        ini, fin = f"<!-- NEXORA:auto:{clave} -->", f"<!-- /NEXORA:auto:{clave} -->"
        nuevo = f"{ini}\n{contenido.rstrip()}\n{fin}"
        cur = self.leer(rel)
        if cur is None:
            if crear is None:
                self.res["avisos"].append(f"no existe «{rel}»: no se puede ampliar")
                return "falta"
            texto = crear.rstrip("\n") + "\n\n" + nuevo + "\n"
            self._escribir(rel, texto)
            self.res["creadas"].append(rel)
            return "creada"
        i, j = cur.find(ini), cur.find(fin)
        if i >= 0 and j > i:
            actual = cur[i:j + len(fin)]
            if actual == nuevo:
                self.res["iguales"] += 1
                return "igual"
            texto = cur[:i] + nuevo + cur[j + len(fin):]
        else:
            texto = cur + ("" if cur.endswith("\n") else "\n") + "\n" + nuevo + "\n"
        self._escribir(rel, texto)
        self.res["ampliadas"].append(rel)
        return "ampliada"

    def anexar(self, rel, lineas, cabecera="", crear=None):
        """Solo añade al final (bitácora). Nunca toca lo anterior."""
        if not lineas:
            return 0
        cur = self.leer(rel)
        if cur is None:
            if crear is None:
                self.res["avisos"].append(f"no existe «{rel}»: no se puede ampliar")
                return 0
            cur = crear.rstrip("\n") + "\n"
            creada = True
        else:
            creada = False
        add = ("" if cur.endswith("\n") else "\n")
        if cabecera and cabecera not in cur:
            add += "\n" + cabecera + "\n"
        add += "\n".join(lineas) + "\n"
        self._escribir(rel, cur + add)
        (self.res["creadas"] if creada else self.res["ampliadas"]).append(rel)
        return len(lineas)

    def cambios(self):
        r = self.res
        return len(r["creadas"]) + len(r["actualizadas"]) + len(r["v2"]) + len(r["ampliadas"])


# ============================================================================ lectura de datos del repo
class Datos:
    def __init__(self, raiz, hoy=None):
        self.raiz = raiz
        self.hoy = hoy or dt.datetime.now(UTC).strftime("%Y-%m-%d")
        self._csv, self._ctx, self._commit = {}, {}, {}

    def p(self, *a):
        return os.path.join(self.raiz, *a)

    def csv(self, rel):
        if rel not in self._csv:
            try:
                self._csv[rel] = list(csv.DictReader(open(self.p(*rel.split("/")), encoding="utf-8", newline="")))
            except OSError:
                self._csv[rel] = None
        return self._csv[rel]

    def json(self, rel):
        try:
            return json.load(open(self.p(*rel.split("/")), encoding="utf-8"))
        except (OSError, ValueError):
            return None

    # ---- histórico de contexto.json (una foto por hora)
    def ctx_archivos(self, d):
        try:
            return sorted(f for f in os.listdir(self.p("data", "historico_contexto", d)) if f.endswith(".json.gz"))
        except OSError:
            return []

    def ctx(self, d, cual="ultimo"):
        a = self.ctx_archivos(d)
        if not a:
            return None
        f = a[-1] if cual == "ultimo" else a[0]
        k = (d, f)
        if k not in self._ctx:
            try:
                self._ctx[k] = json.load(gzip.open(self.p("data", "historico_contexto", d, f), "rt", encoding="utf-8"))
            except (OSError, ValueError):
                self._ctx[k] = None
        return self._ctx[k]

    # ---- máquina del tiempo: un JSON del sitio tal como estaba al final del día d (último commit anterior a las 00:00 UTC del día siguiente)
    def _commit_antes(self, d, horas):
        k = (d, horas)
        if k not in self._commit:
            sig = (dt.datetime.combine(dt.date.fromisoformat(d) + dt.timedelta(days=1), dt.time(0, 0), UTC) + dt.timedelta(hours=horas)).isoformat()
            rc, out, _ = git(self.raiz, "rev-list", "-n", "1", f"--before={sig}", "HEAD")
            self._commit[k] = out.strip() if rc == 0 and out.strip() else None
        return self._commit[k]

    def git_en(self, d, rel):
        """JSON del sitio tal como estaba al final del día d. El cierre (21:30 UTC) a veces corre pasada la medianoche: si la versión de las 00:00 UTC
        no es de la sesión d pero una posterior (hasta las 12:00 UTC del día siguiente) sí lo es, se usa esa. Nada se inventa: son versiones publicadas."""
        def leer(c):
            if not c:
                return None
            rc, out, _ = git(self.raiz, "show", f"{c}:{rel}")
            try:
                return json.loads(out) if rc == 0 else None
            except ValueError:
                return None
        J = leer(self._commit_antes(d, 0))
        if isinstance(J, dict) and "sesion" in J and J.get("sesion") != d and dt.date.fromisoformat(d).weekday() < 5:
            J2 = leer(self._commit_antes(d, 12))
            if isinstance(J2, dict) and J2.get("sesion") == d:
                return J2
        return J

    def cerrado(self, d):
        """Un día está cerrado cuando ya pasó (UTC) o cuando el cierre de hoy ya corrió y dejó su foto de contexto."""
        if d < self.hoy:
            return True
        if d > self.hoy:
            return False
        filas = [r for r in (self.csv("data/ejecuciones.csv") or []) if r["capturado_utc"][:10] == d and "cierre" in r["modo"] and r["capturado_utc"][11:16] >= "21:30"]
        if not filas:
            return False
        t = max(r["capturado_utc"][:16] for r in filas)
        c = self.ctx(d, "ultimo")
        return bool(c) and str(c.get("generado_utc", ""))[:16] >= t

    def dias(self):
        d0, d1 = dt.date.fromisoformat(DESDE), dt.date.fromisoformat(self.hoy)
        return [(d0 + dt.timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


# ============================================================================ snapshot diario
def nivel(x, clave=None):
    if not isinstance(x, dict):
        return None
    return x.get(clave) if clave else x


def gamma_dia(D, d):
    """Gamma por activo al final del día D: {ES, NQ, US30, ORO} → dict normalizado (None = SIN DATO). Fuente: JSON del sitio en git; si no, contexto; si no, CSV histórico."""
    out = {}
    G = d.git_en(D, "site/data/gamma.json") or {}
    ind = G.get("indices") or {}
    ctx = (d.ctx(D) or {}).get("gamma_indices", {}).get("indices", {})
    csvg = {(r["fecha_sesion"], r["indice"]): r for r in (d.csv("data/historico_gamma.csv") or [])}
    for clave, nombre in (("ES", "ES · S&P 500"), ("NQ", "NQ · Nasdaq 100")):
        e, c = ind.get(clave), ctx.get(clave)
        if e:
            out[clave] = {"nombre": nombre, "sesion": e.get("sesion"), "regimen": e.get("regimen"), "flip": nivel(e.get("flip"), "fut"), "call": nivel(e.get("call_wall"), "fut"),
                          "put": nivel(e.get("put_wall"), "fut"), "maxg": nivel(e.get("max_gamma"), "fut"), "maxg_tipo": nivel(e.get("max_gamma"), "tipo"),
                          "em": e.get("em"), "unidad": "futuro", "fuente": "gamma.json"}
        elif c:
            out[clave] = {"nombre": nombre, "sesion": c.get("sesion"), "regimen": c.get("regimen_gamma"), "flip": nivel(c.get("gamma_flip"), "fut"), "call": nivel(c.get("call_wall"), "fut"),
                          "put": nivel(c.get("put_wall"), "fut"), "maxg": None, "maxg_tipo": None, "em": None, "unidad": "futuro", "fuente": "contexto"}
        else:
            fila = next((r for (f, i), r in sorted(csvg.items(), reverse=True) if i == clave and f <= D), None)
            out[clave] = ({"nombre": nombre, "sesion": fila["fecha_sesion"], "regimen": fila["regimen"], "flip": float(fila["flip_fut"] or 0) or None, "call": float(fila["call_wall_fut"] or 0) or None,
                           "put": float(fila["put_wall_fut"] or 0) or None, "maxg": None, "maxg_tipo": None, "em": None, "unidad": "futuro", "fuente": "historico_gamma.csv"} if fila else None)
    U = d.git_en(D, "site/data/gamma_us30.json")
    if U:
        out["US30"] = {"nombre": "US30 · Dow (DIA)", "sesion": U.get("sesion"), "regimen": U.get("regimen"), "flip": nivel(U.get("flip"), "fut"), "call": nivel(U.get("call_wall"), "fut"),
                       "put": nivel(U.get("put_wall"), "fut"), "maxg": nivel(U.get("max_gamma"), "fut"), "maxg_tipo": nivel(U.get("max_gamma"), "tipo"), "em": U.get("em"), "unidad": "futuro", "fuente": "gamma_us30.json"}
    else:
        fila = next((r for r in sorted(d.csv("data/historico_gamma.csv") or [], key=lambda r: r["fecha_sesion"], reverse=True) if r["indice"] == "YM" and r["fecha_sesion"] <= D), None)
        out["US30"] = ({"nombre": "US30 · Dow (DIA)", "sesion": fila["fecha_sesion"], "regimen": fila["regimen"], "flip": float(fila["flip_fut"] or 0) or None, "call": float(fila["call_wall_fut"] or 0) or None,
                        "put": float(fila["put_wall_fut"] or 0) or None, "maxg": None, "maxg_tipo": None, "em": None, "unidad": "futuro", "fuente": "historico_gamma.csv"} if fila else None)
    O = d.git_en(D, "site/data/gamma_oro.json")
    if O:
        nv = {x.get("clave"): x for x in O.get("niveles") or []}
        mg = O.get("max_gamma") or {}
        out["ORO"] = {"nombre": "ORO · GLD ref. → XAU", "sesion": O.get("sesion"), "regimen": O.get("regimen"), "flip": (nv.get("flip") or {}).get("xau"), "call": (nv.get("call_wall") or {}).get("xau"),
                      "put": (nv.get("put_wall") or {}).get("xau"), "maxg": mg.get("idx"), "maxg_tipo": mg.get("tipo"), "em": {"puntos": O.get("em_xau"), "pct": (O.get("em") or {}).get("pct")},
                      "unidad": "XAU/USD", "fuente": "gamma_oro.json", "linea": O.get("linea"), "spot_contraste": O.get("spot_contraste")}
    else:
        fila = next((r for r in sorted(d.csv("data/historico_gamma_oro.csv") or [], key=lambda r: r["fecha_sesion"], reverse=True) if r["fecha_sesion"] <= D), None)
        out["ORO"] = ({"nombre": "ORO · GLD ref. → XAU", "sesion": fila["fecha_sesion"], "regimen": fila["regimen"], "flip": float(fila["flip_xau"] or 0) or None, "call": float(fila["call_wall_xau"] or 0) or None,
                       "put": float(fila["put_wall_xau"] or 0) or None, "maxg": float(fila["max_gamma_xau"] or 0) or None, "maxg_tipo": None, "em": {"puntos": float(fila["em_xau"] or 0) or None, "pct": None},
                       "unidad": "XAU/USD", "fuente": "historico_gamma_oro.csv", "linea": None} if fila else None)
    return out


def spot_oro_dia(D, d):
    for r in d.csv("data/xau_spot_contraste.csv") or []:
        if r["fecha"] == D:
            # solo se leen datos del repo; nunca se importa código descargado (el exportador se ejecuta anclado, ver --aprobar)
            fuentes = (f"gold-api {r.get('spot_principal') or 'CAÍDA'} · GC implícito {r.get('spot_gc_implicito') or '—'} (dif. {r.get('dif_gc_pct') or '—'} %) · "
                       f"Swissquote {r.get('swiss_precio') or '—'} (dif. {r.get('dif_swiss_pct') or '—'} %)")
            return {**r, "texto_fuentes": fuentes}
    return None


def eventos_alta(D, d):
    c = d.ctx(D, "primero") or {}
    evs = [e for e in ((c.get("agenda") or {}).get("hoy") or []) if e.get("importancia") == "ALTA" and (e.get("fecha") == D)]
    if not evs:
        evs = [e for e in ((c.get("calendario") or {}).get("proximos_14_dias") or []) if e.get("importancia") == "ALTA" and e.get("fecha") == D]
    reac = [r for r in (d.csv("data/reacciones_eventos.csv") or []) if r["fecha"] == D and r.get("clasificacion")]
    return evs, reac


def tesis_dia(D, d):
    c = d.ctx(D)
    if c and (c.get("tesis") or {}).get("tesis_por_activo"):
        return [{"activo": a["activo"], "etiqueta": a["etiqueta"], "viento": a.get("viento_semana"), "motor": a.get("motor_propio"), "veredicto": a.get("veredicto_motor_propio"),
                 "a_favor": a.get("a_favor") or [], "en_contra": a.get("en_contra") or [], "texto": a.get("tesis")} for a in c["tesis"]["tesis_por_activo"]], "contexto"
    filas = {}
    for r in d.csv("data/registro_tesis.csv") or []:
        if r["fecha"] == D:
            filas[r["activo"]] = r
    if filas:
        return [{"activo": a, "etiqueta": r["tesis"], "viento": None, "motor": r.get("motores"), "veredicto": None, "a_favor": [], "en_contra": [], "texto": None, "puntuacion": r.get("puntuacion"),
                 "precio": r.get("precio_referencia")} for a, r in filas.items()], "registro_tesis.csv"
    return [], None


def snapshot(D, d):
    """(texto, hay_datos). Todo lo que falta es «SIN DATO»; nada se reconstruye ni se inventa."""
    ctx = d.ctx(D)
    prev = (dt.date.fromisoformat(D) - dt.timedelta(days=1)).isoformat()
    tes, ftes = tesis_dia(D, d)
    G = gamma_dia(D, d)
    sp = spot_oro_dia(D, d)
    evs, reac = eventos_alta(D, d)
    hr = [r for r in (d.csv("data/historico_regimen.csv") or []) if r["fecha_captura"] == D]
    hc = [r for r in (d.csv("data/historico_ciclo.csv") or []) if r["fecha_captura"] == D]
    hay = bool(ctx or tes or hr or hc or any(G.values()))
    fm = {"tipo": "snapshot", "as_of": D, "origen": "nexora-terminal"}
    if not hay:
        fm.update({"estado_dato": "SIN DATO", "tags": ["snapshot", "nexora"]})
        return (frontmatter(fm) + f"\n# Snapshot de mercado · {D}\n\n> Foto inmutable del día.\n\n**SIN DATO.** El repositorio no tiene datos de este día (el sistema empieza a registrar el 2026-10-08). No se reconstruye nada.\n\n"
                f"Anterior: [[02_Daily_Snapshots/{prev}|{prev}]]\n"), False
    R = (ctx or {}).get("regimen_macro")
    reg_txt = None
    if R:
        reg_txt = f"{R.get('cuadrante')} · {R.get('fuerza')} · riesgo: {R.get('riesgo')} · liquidez: {R.get('liquidez')}"
    elif hr:
        r = hr[-1]
        reg_txt = f"{r['cuadrante']} · {r['fuerza']} · riesgo: {r['riesgo']} · liquidez: {r['liquidez']}"
    F = (ctx or {}).get("fedwatch_y_tipos") or {}
    reu = (F.get("reuniones") or [None])[0]
    M = ((ctx or {}).get("mercado") or {}).get("activos") or {}
    tt = F.get("tipos_tesoro") or {}
    hy = (((ctx or {}).get("credito") or {}).get("diferenciales") or {}).get("hy", {}).get("pb") or (hc[-1]["hy_pb"] if hc else None)
    if reu:
        fm["fed_reunion"], fm["fed_subida_pct"] = reu.get("reunion"), reu.get("prob_subida_pct")
    for k, v in (("us2y", (tt.get("t2y") or {}).get("valor")), ("us10y", (tt.get("n10") or {}).get("valor")), ("real10y", (tt.get("real10") or {}).get("valor")),
                 ("dxy", (M.get("dxy") or {}).get("valor")), ("vix", (M.get("vix") or {}).get("valor")), ("hy_pb", float(hy) if hy not in (None, "") else None)):
        if v is not None:
            fm[k] = v
    if reg_txt:
        fm["regimen"] = reg_txt
    for t in tes:
        s = SLUGS.get(t["activo"])
        if s:
            fm["tesis_" + s.lower()] = t["etiqueta"]
            if t.get("viento"):
                fm["viento_" + s.lower()] = t["viento"]
    fm["fuente_contexto"] = (ctx or {}).get("generado_utc") or "SIN DATO (solo CSV históricos)"
    fm["tags"] = ["snapshot", "nexora"]
    L = [frontmatter(fm), f"# Snapshot de mercado · {D}", "", "> Foto inmutable del día: no se edita. Se escribe cuando el día está cerrado y refleja el último estado del sistema de ese día.",
         f"> Fuente: {'foto de contexto de ' + fm['fuente_contexto'] if ctx else 'CSV históricos del repo (ese día no hay foto de contexto): fuente parcial'}.", ""]
    L += ["## Régimen", "", reg_txt or "SIN DATO", ""]
    if R:
        cs = R.get("cuadrante_simple") or {}
        if cs:
            L += [f"- Lectura simple: {cs.get('cuadrante')} (crecimiento {cs.get('crecimiento')}, inflación {cs.get('inflacion')}) · {cs.get('detalle')}"]
        L += [f"- Concordancia de los monitores: {R.get('concordancia_monitores')} · motor: {R.get('motor')}"]
        for c in R.get("contradicciones") or []:
            L += [f"- Contradicción: {c}"]
        L += [""]
    if reu:
        L += [f"**Fed:** reunión {reu.get('reunion')}: subida {n(reu.get('prob_subida_pct'), 0)} %, mantener {n(reu.get('prob_mantiene_pct'), 0)} %, bajada {n(reu.get('prob_bajada_pct'), 0)} %. "
              f"2Y {n(fm.get('us2y'), 2)} % · 10Y {n(fm.get('us10y'), 2)} % · 10Y real {n(fm.get('real10y'), 2)} % · DXY {n(fm.get('dxy'), 2)} · VIX {n(fm.get('vix'), 2)}", ""]
    L += ["## Tesis por activo", ""]
    if tes:
        L += [tabla(["Activo", "Tesis (intensidad)", "Viento semana", "Motor propio", "Nota de tesis"],
                    [[t["activo"], t["etiqueta"], t.get("viento") or "SIN DATO", t.get("veredicto") or "SIN DATO", nota_tesis_vigente(t["activo"], D, d)] for t in tes])]
    else:
        L += ["SIN DATO.", ""]
    L += ["## Gamma por activo", "", "Niveles en precio del futuro (ORO: XAU/USD). Max Gamma: «pin» = gamma neta positiva (imán), «acelera» = negativa. Criterio NEXORA, no dato oficial.", ""]
    filas = []
    for k in ("ES", "NQ", "US30", "ORO"):
        g = G.get(k)
        if not g:
            filas.append([k, "SIN DATO", "", "", "", "", "", ""])
            continue
        em = g.get("em") or {}
        emt = "SIN DATO" if not em or em.get("puntos") is None else f"±{n(em.get('puntos'), 1)}" + (f" ({n(em.get('pct'), 2)} %)" if em.get("pct") is not None else "")
        mg = "SIN DATO" if g.get("maxg") is None else f"{n(g['maxg'], 0)}" + (f" · {g['maxg_tipo']}" if g.get("maxg_tipo") else " · (tipo SIN DATO)")
        ses = g.get("sesion") or "SIN DATO"
        filas.append([g["nombre"], ses + ("" if ses == D else " ⚠ no es de este día"), g.get("regimen") or "SIN DATO", n(g.get("flip"), 0), n(g.get("call"), 0), n(g.get("put"), 0), mg, emt])
    L += [tabla(["Activo", "Sesión", "Régimen gamma", "Flip", "Call Wall", "Put Wall", "Max Gamma", "EM"], filas)]
    O = G.get("ORO") or {}
    L += ["## ORO · línea y spot", ""]
    linea = O.get("linea")
    L += [f"- Línea ORO: `{linea}`" + ("" if (O.get("sesion") == D) else f" (de la sesión {O.get('sesion')})") if linea else "- Línea ORO: SIN DATO (no guardada en el repo para este día)"]
    if sp:
        L += [f"- Spot del oro: **{sp['estado']}**" + (" (verificado)" if sp["estado"] == "OK" else " (dudoso: ratio y base no se actualizaron)" if sp["estado"] == "DUDOSO" else "")
              + f" · usado {sp.get('spot_usado')} ({sp.get('spot_fuente')}) · ratio {sp.get('ratio_fuente')}", f"- Fuentes: {sp.get('texto_fuentes')}"]
    else:
        L += ["- Spot del oro: SIN DATO (el contraste de fuentes del spot se registra desde el cierre del 2026-10-23, Fase 19)"]
    L += [""]
    L += ["## Petróleo", ""]
    P = (ctx or {}).get("petroleo")
    if P:
        t = P.get("tesis") or {}
        L += [f"- WTI {n(P.get('wti'), 2)} · Brent {n(P.get('brent'), 2)} ({P.get('fecha')}) · tesis {t.get('resultado')} {t.get('intensidad')} (puntos {t.get('puntos')}) · curva {(P.get('curva') or {}).get('estado')} "
              f"({n((P.get('curva') or {}).get('diferencial_pct'), 2)} %) · inventarios {n((P.get('inventarios_crudo') or {}).get('cambio_semana_mb'), 1)} mb en la semana", ""]
    else:
        wti = M.get("wti")
        L += [(f"- WTI {n(wti.get('valor'), 2)} ({wti.get('fecha')}); la tesis de petróleo no estaba en el contexto de ese día." if wti else "SIN DATO."), ""]
    L += ["## Consumo (XLY/XLP)", ""]
    C, CR = (ctx or {}).get("consumo"), (ctx or {}).get("consumo_ratio")
    if C:
        xl = (C.get("mercado") or {}).get("XLY_XLP") or {}
        t = C.get("tesis") or {}
        L += [f"- Tesis de consumo: **{t.get('resultado')}** ({t.get('intensidad')}) · XLY/XLP {n(xl.get('ratio'), 4)} · {n(xl.get('dist_sma200_pct'), 2, True)} % frente a su SMA200 · pendiente 3m {n(xl.get('pendiente_3m_pct'), 2, True)} %"]
        if CR:
            f1 = ((CR.get("filtro_sma200") or {}).get("XLY/XLP") or {})
            L += [f"- Filtro SMA200: diario {(f1.get('diario') or {}).get('estado')} · semanal {(f1.get('semanal') or {}).get('estado')}"]
        L += [""]
    else:
        L += ["SIN DATO (el módulo de consumo no estaba en el contexto de ese día).", ""]
    L += ["## Crédito", ""]
    K = (ctx or {}).get("credito")
    if K:
        df = K.get("diferenciales") or {}
        L += [f"- {K.get('estado')}", "- " + " · ".join(f"{k.upper()} {n((df.get(k) or {}).get('pb'), 0)} pb (5d {n((df.get(k) or {}).get('d5_pb'), 0, True)})" for k in ("ig", "bbb", "hy", "ccc") if df.get(k)), ""]
    elif hc:
        r = hc[-1]
        L += [f"- {r['estado_credito']}", f"- IG {r['ig_pb']} pb · BBB {r['bbb_pb']} pb · HY {r['hy_pb']} pb · CCC {r['ccc_pb']} pb (fase del ciclo: {r['fase']})", ""]
    else:
        L += ["SIN DATO.", ""]
    L += ["## Eventos ALTA del día", ""]
    if evs:
        L += [f"- {e.get('hora_madrid') or 'hora SIN DATO'} (Madrid) · {e.get('evento')}" + (f" — {e.get('nota')}" if e.get("nota") else "") for e in evs]
    else:
        L += [("- Ninguno de importancia ALTA en la agenda de ese día." if (ctx and (ctx.get("agenda") or ctx.get("calendario"))) else "- SIN DATO: ese día no hay agenda en el repo.")]
    for r in reac:
        L += [f"- Reacción registrada · {r['evento']} ({r['fase']}): {r['clasificacion']}"]
    L += [""]
    vig = ((ctx or {}).get("tesis") or {}).get("vigilar") or []
    if vig:
        L += ["## Qué vigilar", ""] + [f"- {v}" for v in vig] + [""]
    L += ["## Enlaces", "", f"Anterior: [[02_Daily_Snapshots/{prev}|{prev}]] · [[01_State/Global Market State|Estado global]] · [[00_MOC/Market Intelligence|Índice]]", ""]
    return "\n".join(L), True


def nota_tesis_vigente(activo, D, d):
    """Enlace a la nota de la tesis vigente ese día (la más reciente con fecha ≤ D)."""
    s = SLUGS.get(activo)
    if not s:
        return ""
    cand = [x[0] for x in getattr(d, "tesis_notas", {}).get(s, []) if x[0] <= D]
    return f"[[04_Theses/T-{cand[-1].replace('-', '')}-{s}|T-{cand[-1].replace('-', '')}-{s}]]" if cand else ""


# ============================================================================ tesis (una nota por cambio)
def parse_etiqueta(e):
    e = (e or "").upper()
    sesgo = "SIN TESIS" if "SIN" in e else "ALCISTA" if "ALCISTA" in e else "BAJISTA" if "BAJISTA" in e else "NEUTRAL" if "NEUTRAL" in e else e
    inten = "DÉBIL" if ("DÉBIL" in e or "DEBIL" in e) else "FUERTE" if "FUERTE" in e else "MODERADA" if "MODERAD" in e else "—"
    return sesgo, inten


def serie_tesis(d, dias_cerrados):
    """{slug: [(fecha, activo, etiqueta)]} con la última etiqueta de cada día cerrado (registro_tesis.csv; si no hay, el contexto)."""
    por = {}
    for D in dias_cerrados:
        tes, _ = tesis_dia(D, d)
        for t in tes:
            s = SLUGS.get(t["activo"]) or re.sub(r"[^A-Z0-9]", "", t["activo"].upper())[:6]
            por.setdefault(s, []).append((D, t["activo"], t["etiqueta"], t))
    return por


def notas_tesis(bov, d, dias_cerrados):
    por = serie_tesis(d, dias_cerrados)
    d.tesis_notas = {}
    for s, serie in por.items():
        previa = None
        antigua = f"{MI}/04_Theses/T-20261001-{s}.md"
        enlace_antigua = f"[[04_Theses/T-20261001-{s}|T-20261001-{s}]]" if os.path.exists(bov.ruta(antigua)) else None
        for D, activo, etiq, t in serie:
            if previa is not None and previa[2] == etiq:
                continue
            tid = f"T-{D.replace('-', '')}-{s}"
            sesgo, inten = parse_etiqueta(etiq)
            ant = previa
            ant_link = (f"[[04_Theses/T-{ant[0].replace('-', '')}-{s}|T-{ant[0].replace('-', '')}-{s}]] ({ant[2]}, desde {ant[0]})" if ant
                        else (enlace_antigua + " (tesis del sistema anterior, 2026-10-01)" if enlace_antigua else "ninguna: primera tesis registrada por el terminal"))
            fm = {"tipo": "tesis", "thesis_id": tid, "activo": activo, "estado": "REGISTRADA", "sesgo": sesgo, "intensidad": inten, "etiqueta": etiq, "creada": D, "origen": "nexora-terminal",
                  "anterior": (f"T-{ant[0].replace('-', '')}-{s}" if ant else (f"T-20261001-{s}" if enlace_antigua else None)), "tags": ["tesis", "nexora"]}
            L = [frontmatter(fm), f"# {tid} · {activo} · {etiq}", "",
                 "> Nota inmutable: se crea solo cuando la tesis del activo cambia. La tesis vigente en cada fecha es la nota más reciente de ese activo (ver el [[01_State/Global Market State|estado global]]).", "",
                 f"- **Cambio:** {ant[2] + ' → ' if ant else ''}{etiq} el {D}", f"- **Tesis anterior:** {ant_link}", f"- **Viento macro de la semana:** {t.get('viento') or 'SIN DATO'}",
                 f"- **Motor propio:** {t.get('motor') or 'SIN DATO'} → {t.get('veredicto') or 'SIN DATO'}"]
            if t.get("puntuacion") not in (None, ""):
                L += [f"- **Puntuación del registro:** {t['puntuacion']}"]
            if t.get("precio") not in (None, ""):
                L += [f"- **Precio de referencia (registro_tesis.csv):** {n(t['precio'], 2)}"]
            L += ["", "## Texto de la tesis", "", t.get("texto") or "SIN DATO (ese día no hay foto de contexto con el texto; solo la etiqueta del registro).", ""]
            if t.get("a_favor"):
                L += ["## A favor", ""] + [f"- {x}" for x in t["a_favor"]] + [""]
            if t.get("en_contra"):
                L += ["## En contra", ""] + [f"- {x}" for x in t["en_contra"]] + [""]
            L += [f"Relacionado: [[02_Daily_Snapshots/{D}|Snapshot del {D}]] · [[00_MOC/Market Intelligence|Índice]]", ""]
            bov.inmutable(f"{MI}/04_Theses/{tid}.md", "\n".join(L))
            d.tesis_notas.setdefault(s, []).append((D, etiq, activo))
            previa = (D, activo, etiq)
    return por


# ============================================================================ análisis (informes de Ruiz)
def parse_fm(texto):
    m = re.match(r"---\n(.*?)\n---\n?(.*)", texto, re.S)
    if not m:
        return {}, texto
    fm = {}
    for ln in m.group(1).splitlines():
        if ":" in ln:
            k, v = ln.split(":", 1)
            v = v.strip()
            try:
                fm[k.strip()] = json.loads(v) if v[:1] in "[{\"" else v
            except ValueError:
                fm[k.strip()] = v
    return fm, m.group(2).lstrip("\n")


def notas_analisis(bov, d, privado, log):
    idx = {}
    for r in d.csv("data/analisis_indice.csv") or []:
        idx[r["id"]] = r
    res = {}
    for r in d.csv("data/analisis_resultados.csv") or []:
        res.setdefault(r["id"], []).append(r)
    cot_pub = {}
    try:
        for ln in open(d.p("data", "analisis_cotejos.jsonl"), encoding="utf-8"):
            if ln.strip():
                x = json.loads(ln)
                cot_pub[x["id"]] = x
    except OSError:
        pass
    carpeta = os.path.join(privado, "analisis") if privado else None
    filas_idx = []
    ids = sorted(set(idx) | set(cot_pub))
    if carpeta and os.path.isdir(carpeta):
        for a in sorted(os.listdir(carpeta)):
            for f in sorted(os.listdir(os.path.join(carpeta, a))):
                if f.endswith(".md"):
                    ids.append(f[:-3])
    for id_ in sorted(set(ids)):
        ruta_md = os.path.join(carpeta, id_[:4], id_ + ".md") if carpeta else None
        ruta_js = os.path.join(carpeta, id_[:4], id_ + ".json") if carpeta else None
        texto, fm = None, {}
        if ruta_md and os.path.exists(ruta_md):
            fm, texto = parse_fm(open(ruta_md, encoding="utf-8").read().replace("\r\n", "\n"))
        else:
            pub = d.p("data", "analisis", id_[:4], id_ + ".md")
            if os.path.exists(pub):
                fm, texto = parse_fm(open(pub, encoding="utf-8").read().replace("\r\n", "\n"))
                texto = "> Solo el RESUMEN público: el informe completo es privado y no está accesible en este equipo.\n\n" + texto
        ix = idx.get(id_) or {}
        if texto is None:
            bov.res["avisos"].append(f"informe {id_}: sin texto accesible (repo privado no disponible); se omite su nota")
            continue
        est = ix.get("estado") or "VIGENTE"
        js = None
        if ruta_js and os.path.exists(ruta_js):
            try:
                js = json.load(open(ruta_js, encoding="utf-8"))
            except ValueError:
                js = None
        cot = (js or {}).get("cotejo") or cot_pub.get(id_) or {}
        fecha = fm.get("fecha") or ix.get("fecha") or id_[:10]
        tipo = fm.get("tipo") or ix.get("tipo") or "ORO_MACRO"
        rs = sorted(res.get(id_, []), key=lambda r: r["horizonte"])
        meta = {"tipo": "analisis", "id": id_, "fecha": fecha, "tipo_informe": tipo, "version": fm.get("version") or ix.get("version") or 1, "estado": est, "sesgo_oro": fm.get("sesgo_oro") or ix.get("sesgo_oro"),
                "corte_madrid": fm.get("corte_madrid") or ix.get("corte_madrid"), "corte_origen": fm.get("corte_origen") or ix.get("corte_origen"), "publicado_utc": fm.get("publicado_utc") or ix.get("publicado_utc"),
                "precio_base": fm.get("precio_base") or ix.get("precio_base"), "visibilidad": fm.get("visibilidad") or ix.get("visibilidad"),
                "resultado": " / ".join(f"{r['horizonte']} {r['veredicto']}" for r in rs) or "PENDIENTE", "origen": "nexora-diario", "tags": ["analisis", "nexora"]}
        L = [frontmatter(meta), f"# Informe {tipo} · {fecha}" + (f" (v{meta['version']})" if str(meta["version"]) != "1" else ""), "",
             f"Sesgo del oro (lo indicó Ruiz): **{meta['sesgo_oro']}** · corte {meta['corte_madrid']} Madrid ({meta['corte_origen']}) · precio base {meta['precio_base']} · estado {est}", "", "## Resultado del sesgo", ""]
        if rs:
            L += [tabla(["Horizonte", "Fecha", "Δ oro %", "Δ DXY", "Δ DFII10 pb", "Umbral", "Umbral %", "Veredicto"],
                        [[r["horizonte"], r["fecha_t"], r["oro_pct"], r["dxy_var"], r["dfii10_pb"], r["umbral"], r["umbral_pct"], r["veredicto"]] for r in rs]),
                  "Umbral EM = la expectativa de movimiento del oro de ese día; FIJO = porcentaje fijo cuando no hay EM válido. Sin conclusiones con n<20.", ""]
        else:
            L += ["PENDIENTE: todavía no hay sesión de cierre para evaluar (T+1 / T+5).", ""]
        L += ["## Cotejo con NEXORA", ""]
        if cot:
            for secc, titulo in (("panel", "Panel A.2"), ("calendario", "Calendario B.3")):
                fs = cot.get(secc) or []
                if fs:
                    L += [f"**{titulo}**", ""]
                    for f in fs:
                        if secc == "panel":
                            L += [f"- {f.get('estado')} {f.get('nombre')}: informe {n(f.get('valor'), 3)} · NEXORA {n(f.get('nexora'), 3)} ({f.get('fuente')}, {f.get('fecha_nexora')}) · tolerancia {f.get('tolerancia')}"]
                        else:
                            L += [f"- {f.get('estado')} {f.get('fecha')} {f.get('hora') or ''} {f.get('texto') or (f.get('nexora') or {}).get('evento', '')}: {f.get('nota') or ''}".rstrip()]
                    L += [""]
            L += [f"Resumen: {json.dumps(cot.get('resumen'), ensure_ascii=False)} · calendario {json.dumps(cot.get('resumen_calendario'), ensure_ascii=False)}", ""]
        else:
            L += ["SIN DATO.", ""]
        L += ["## Informe (texto completo)", "", "> Bóveda privada: el texto íntegro de Ruiz.", "", texto.rstrip(), ""]
        rel = f"{MI}/05_Analisis/{fecha[:4]}/{id_}.md"
        bov.gestionada(rel, "\n".join(L))
        filas_idx.append([f"[[05_Analisis/{fecha[:4]}/{id_}|{id_}]]", tipo, meta["version"], est, meta["sesgo_oro"], meta["resultado"]])
    idx_txt = (frontmatter({"tipo": "indice", "tags": ["analisis", "nexora"]}) + "# Análisis de Ruiz · índice\n\nInformes diarios y semanales con su cotejo y resultado (CUMPLIDO / FALLIDO / MIXTO). Generado por el exportador; no editar.\n\n"
               + tabla(["Informe", "Tipo", "Versión", "Estado", "Sesgo oro", "Resultado"], filas_idx[::-1]))
    bov.gestionada(f"{MI}/05_Analisis/00 Índice de análisis.md", idx_txt)
    return len(filas_idx)


# ============================================================================ sistema: docs, registros, bitácora
# ============================================================================ Diario de operaciones (repo privado nexora-diario/diario/AAAA-MM.json)
SETUP_CORTO = {"Barrido+vuelta": "A", "Ruptura+continuación": "B", "Otro": "Otro"}
CONF_NOMBRES = {"absorcion": "Absorción", "iceberg": "Iceberg", "div_delta": "Divergencia delta", "stacked": "Stacked imbalances", "barrido_lit": "Barrido LIT", "fvg": "FVG", "vah_val_poc": "VAH/VAL/POC"}
COLS_OP = ["Estado", "Fecha", "Hora", "Activo", "Setup", "Dirección", "R", "Resultado $", "Res.", "Confirmaciones", "Foto NEXORA", "id", "h"]


def foto_texto(f):
    if not isinstance(f, dict) or not f:
        return "SIN FOTO"
    p = [str(f.get("estado") or "SIN DATO")]
    if isinstance(f.get("tesis"), dict):
        p.append("tesis " + str(f["tesis"].get("etiqueta")))
    if isinstance(f.get("gamma"), dict) and f["gamma"].get("signo"):
        p.append("gamma " + str(f["gamma"]["signo"]))
    if isinstance(f.get("regimen"), dict) and f["regimen"].get("cuadrante"):
        p.append("régimen " + str(f["regimen"]["cuadrante"])[:40])
    ev = f.get("evento_alta_2h")
    if isinstance(ev, dict):
        p.append("ALTA 2h: " + (", ".join(str(e.get("evento")) for e in ev.get("eventos") or [])[:60] if ev.get("si") else "no"))
    if f.get("contexto_utc"):
        p.append("ctx " + str(f["contexto_utc"]))
    return " · ".join(p)


def hash_op(t):
    base = {k: t.get(k) for k in ("fecha", "hora", "hora_salida", "activo", "lado", "instrumento", "tamano", "valor_punto", "precio_entrada", "precio_stop", "precio_objetivo", "precio_salida", "pnl", "r", "r_plan",
                                  "nota", "setup", "conf", "foto")}
    return hashlib.sha1(json.dumps(base, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:8]


def r_de(t):
    """R de la operación o None. Solo el que calcula el Diario (resultado $ / riesgo $ con stop); sin stop es None y no se inventa."""
    try:
        return float(t["r"]) if t.get("r") not in (None, "") else None
    except (TypeError, ValueError):
        return None


def fila_op(estado, t):
    pnl = float(t.get("pnl") or 0)
    r = r_de(t)
    return "| " + " | ".join(celda(x) for x in [
        estado, t.get("fecha"), t.get("hora") or "SIN DATO", t.get("activo"), SETUP_CORTO.get(t.get("setup"), "sin setup"), t.get("lado"),
        (n(r, 2, True) if r is not None else "SIN DATO"), n(pnl, 2, True), "GANADA" if pnl > 0 else "PERDIDA" if pnl < 0 else "BE",
        ", ".join(CONF_NOMBRES.get(k, k) for k in t.get("conf") or []) or "—", foto_texto(t.get("foto")), t.get("id"), hash_op(t)]) + " |"


def pf(valores):
    """Profit factor de una lista de resultados (en $ o en R): ganancias brutas / pérdidas brutas."""
    g = sum(v for v in valores if v > 0)
    p = -sum(v for v in valores if v < 0)
    return "SIN DATO" if not valores else ("∞ (sin pérdidas)" if p == 0 and g > 0 else "—" if p == 0 else n(g / p, 2))


def resumen_mes(mes, ts):
    L = [f"## Resumen del mes {mes}", "", "Se recalcula en cada pasada con el estado actual de cada operación (las filas de abajo son el historial y no se tocan).", ""]
    if not ts:
        return "\n".join(L + ["Sin operaciones.", ""])
    gan = [t for t in ts if float(t["pnl"]) > 0]
    con_r = [r_de(t) for t in ts if r_de(t) is not None]
    L += [f"- Operaciones: **{len(ts)}** · acierto: **{n(100 * len(gan) / len(ts), 0)} %** ({len(gan)} ganadas)" + (" · n<20: sin conclusión" if len(ts) < 20 else ""),
          f"- Resultado total: {n(sum(float(t['pnl']) for t in ts), 2, True)} $ · esperanza por operación: {n(sum(float(t['pnl']) for t in ts) / len(ts), 2, True)} $",
          "- Esperanza en R: " + (f"**{n(sum(con_r) / len(con_r), 2, True)} R** ({len(con_r)} de {len(ts)} operaciones con R) · profit factor en R: {pf(con_r)}" if con_r else
                                 "SIN DATO: ninguna operación del mes tiene stop (R = resultado $ / riesgo $); no se inventa."), ""]
    filas = []
    for nombre in ("Barrido+vuelta", "Ruptura+continuación", "Otro", None):
        sub = [t for t in ts if t.get("setup") == nombre] if nombre else [t for t in ts if t.get("setup") not in SETUP_CORTO]
        if sub:
            rs = [r_de(t) for t in sub if r_de(t) is not None]
            filas.append([(f"{SETUP_CORTO[nombre]} · {nombre}" if nombre else "sin setup"), len(sub), n(100 * sum(float(t["pnl"]) > 0 for t in sub) / len(sub), 0) + " %",
                          n(sum(float(t["pnl"]) for t in sub) / len(sub), 2, True) + " $", pf([float(t["pnl"]) for t in sub]),
                          (n(sum(rs) / len(rs), 2, True) + f" R ({len(rs)}/{len(sub)})") if rs else "SIN DATO", pf(rs) if rs else "SIN DATO"])
    return "\n".join(L + [tabla(["Setup", "n", "Acierto", "Esperanza ($/op.)", "Profit factor ($)", "Esperanza (R/op.)", "Profit factor (R)"], filas)])


def notas_diario(bov, d, privado):
    carpeta = os.path.join(privado, "diario") if privado else None
    if not carpeta or not os.path.isdir(carpeta):
        return 0
    nuevas = 0
    for f in sorted(os.listdir(carpeta)):
        m = re.match(r"^(\d{4}-\d{2})\.json$", f)
        if not m:
            continue
        mes = m.group(1)
        try:
            J = json.load(open(os.path.join(carpeta, f), encoding="utf-8"))
        except (OSError, ValueError):
            bov.res["avisos"].append(f"diario/{f}: no se pudo leer; se omite")
            continue
        borrados = J.get("borrados") or {}
        trades = {t["id"]: t for t in J.get("trades") or [] if isinstance(t, dict) and t.get("id") and t["id"] not in borrados}
        rel = f"10_Diario/Operaciones/{mes}.md"
        if not trades and not borrados:
            continue
        inicial = (frontmatter({"tipo": "diario-operaciones", "mes": mes, "origen": "nexora-diario", "tags": ["diario", "operaciones", "nexora"]}) + f"# Operaciones {mes}\n\n"
                   "Diario de operaciones exportado desde el repo privado. **Solo se añade**: una fila por operación; si corriges una operación se añade una fila REVISADA (y ANULADA si la borras), nunca se reescribe una fila. "
                   "`R` = SIN DATO mientras la operación no traiga R.\n\n<!-- NEXORA:auto:resumen -->\n<!-- /NEXORA:auto:resumen -->\n\n## Operaciones\n\n"
                   "| " + " | ".join(COLS_OP) + " |\n|" + "|".join("---" for _ in COLS_OP) + "|\n")
        bov.inmutable(rel, inicial)
        cur = bov.leer(rel) or ""
        ultimo = {}
        for ln in cur.splitlines():
            c = [x.strip() for x in re.split(r"(?<!\\)\|", ln.strip().strip("|"))]
            if len(c) == len(COLS_OP) and c[0] in ("ALTA", "REVISADA", "ANULADA"):
                ultimo[c[-2]] = (c[0], c[-1])
        nuevas_filas = []
        for t in sorted(trades.values(), key=lambda t: (t.get("fecha", ""), t.get("hora") or "", t["id"])):
            ant = ultimo.get(t["id"])
            if ant is None:
                nuevas_filas.append(fila_op("ALTA", t))
            elif ant[1] != hash_op(t) or ant[0] == "ANULADA":
                nuevas_filas.append(fila_op("REVISADA", t))
        for id_ in sorted(borrados):
            if id_ in ultimo and ultimo[id_][0] != "ANULADA":
                nuevas_filas.append(fila_op("ANULADA", {"id": id_, "fecha": "", "activo": "(operación borrada)", "pnl": 0, "conf": []}))
        if nuevas_filas:
            bov.anexar(rel, nuevas_filas)
            nuevas += len(nuevas_filas)
        bov.bloque(rel, "resumen", resumen_mes(mes, list(trades.values())))
    return nuevas


def notas_docs(bov, d):
    carpeta = d.p("docs")
    out = []
    for f in sorted(os.listdir(carpeta)) if os.path.isdir(carpeta) else []:
        if not f.endswith(".md"):
            continue
        t = open(os.path.join(carpeta, f), encoding="utf-8").read().replace("\r\n", "\n")
        fm = {"tags": ["nexora", "docs"], "origen": f"docs/{f} (repo nexora-terminal)", "fuente_sha": hashlib.sha1(t.encode("utf-8")).hexdigest()[:12],
              "aviso": "Copia automática del repo: no editar aquí (si la editas, la próxima versión se guarda como «NEXORA v2»)."}
        bov.gestionada(f"{SIS}/Docs/{f}", frontmatter(fm) + "\n" + t)
        out.append(f[:-3])
    return out


REGISTROS = [
    ("Marcador de señales", ["data/marcador_senales.csv", "data/marcador_resultados_v2.csv"],
     {"data/marcador_senales.csv": ["fecha_utc", "tipo", "activo", "direccion", "valor", "origen", "estado"],
      "data/marcador_resultados_v2.csv": ["id", "horizonte", "resultado", "ret", "unidad", "fecha_ref", "fecha_fin"]}),
    ("Resultados del análisis", ["data/analisis_resultados.csv"], {"data/analisis_resultados.csv": ["id", "fecha", "tipo", "sesgo_oro", "horizonte", "oro_pct", "umbral", "umbral_pct", "veredicto"]}),
    ("Reacciones a eventos", ["data/reacciones_eventos.csv"], {"data/reacciones_eventos.csv": ["evento_id", "fase", "fecha", "hora_ny", "clasificacion", "d_y2_pb", "d_dxy_pct", "d_oro_pct", "d_nq_pct", "estado"]}),
    ("Discrepancias revisadas", ["data/discrepancias_revisadas.csv"], {"data/discrepancias_revisadas.csv": ["registrada_utc", "clave", "estado", "motivo", "revisor"]}),
    ("Contraste del spot del oro", ["data/xau_spot_contraste.csv"], {"data/xau_spot_contraste.csv": ["fecha", "spot_principal", "spot_gc_implicito", "dif_gc_pct", "swiss_precio", "dif_swiss_pct", "estado", "spot_fuente", "ratio_fuente"]}),
    ("Vigilar cierre", ["data/vigilar_cierre.csv"], {"data/vigilar_cierre.csv": ["fecha", "ejecutado_utc", "resultado", "run_id_cierre", "detalle"]}),
]


def notas_registros(bov, d):
    nombres = []
    for titulo, csvs, cols in REGISTROS:
        L = [frontmatter({"tags": ["nexora", "registro"], "tipo": "registro", "origen": "nexora-terminal/data", "aviso": "Generada automáticamente; los CSV originales nunca se editan."}), f"# {titulo}", "",
             f"Últimas {FILAS_REGISTRO} filas (las más recientes arriba). Los CSV son de solo añadir; la fuente de verdad es el CSV del repo."]
        for c in csvs:
            filas = d.csv(c)
            L += ["", f"## {os.path.basename(c)}", "", f"CSV: [{c}]({WEB_CSV}{os.path.basename(c)})", ""]
            if filas is None:
                L += ["SIN DATO: el CSV todavía no existe en el repo.", ""]
                continue
            cs = [x for x in cols[c] if filas and x in filas[0]] or (list(filas[0].keys())[:8] if filas else cols[c])
            L += [f"Total de filas: {len(filas)}", "", tabla(cs, [[f.get(x, "") for x in cs] for f in filas[-FILAS_REGISTRO:][::-1]])]
        bov.gestionada(f"{SIS}/Registros/{titulo}.md", "\n".join(L))
        nombres.append(titulo)
    return nombres


def lineas_bitacora(d):
    """[(mes AAAA-MM, fecha, clave, línea)] de los commits no automáticos, los fallos de etapas, las vigilancias fallidas y las revisiones de datos."""
    out = []
    rc, txt, _ = git(d.raiz, "log", "--reverse", "--format=%h%x1f%cs%x1f%s%x1f%b%x1e")
    for reg in txt.split("\x1e"):
        p = reg.strip("\n").split("\x1f")
        if len(p) < 4 or not p[0].strip():
            continue
        h, f, s, b = p[0].strip(), p[1], p[2], p[3]
        if BOT.search(s):
            continue
        tipo = "fix" if re.search(r"\b(fix|corrige|corregid|arregl|error|fallo|bug)", s, re.I) else "feat" if re.match(r"(feat|fase|a[ñn]ad|nuevo)", s, re.I) else "cambio"
        pq = " ".join(x.strip() for x in b.split("\n\n")[0].splitlines() if x.strip() and not x.lower().startswith("co-authored")).strip()
        if pq == s:
            pq = ""
        out.append((f[:7], f, f"commit|{h}", f"- {f} · [{tipo}] {s[:400] + ('…' if len(s) > 400 else '')}" + (f" — por qué: {pq[:400] + ('…' if len(pq) > 400 else '')}" if pq else "") + f" (`{h}`)"))
    fall = {}
    for r in d.csv("data/ejecuciones.csv") or []:
        if r.get("etapas_fallo") and "SIMULACRO" not in r.get("modo", ""):
            for e in r["etapas_fallo"].split(","):
                fall.setdefault((r["capturado_utc"][:10], e), 0)
                fall[(r["capturado_utc"][:10], e)] += 1
    for (f, e), c in sorted(fall.items()):
        out.append((f[:7], f, f"fallo|{f}|{e}", f"- {f} · [fallo de datos] la etapa «{e}» falló {c} {'vez' if c == 1 else 'veces'} ese día (data/ejecuciones.csv)."))
    for r in d.csv("data/vigilar_cierre.csv") or []:
        if r.get("resultado") not in ("OK", "NO_TOCA", "SIMULACRO", None, ""):
            out.append((r["fecha"][:7], r["fecha"], f"vigcierre|{r['fecha']}|{r['ejecutado_utc']}", f"- {r['fecha']} · [fallo] el vigilante del cierre dio {r['resultado']}: {celda(r.get('detalle'))[:200]}"))
    for r in d.csv("data/discrepancias_revisadas.csv") or []:
        f = r["registrada_utc"][:10]
        out.append((f[:7], f, f"rev|{r['id']}", f"- {f} · [revisión de datos] {r['clave']} marcada {r['estado']} por {r.get('revisor') or '—'}: {celda(r.get('motivo'))[:240]}"))
    for r in d.csv("data/discrepancias.csv") or []:
        f = r["detectada_utc"][:10]
        out.append((f[:7], f, f"disc|{r['id']}", f"- {f} · [discrepancia] {r['serie']} {r['periodo']} ({r['tipo']}): FRED {r['fred_valor']} frente a {r['primaria']} {r['primaria_valor']} — estado {r['estado']}"))
    return sorted(out, key=lambda x: (x[1], x[2]))


def bitacora(bov, d):
    por_mes = {}
    todas = lineas_bitacora(d)
    todo_texto = "\n".join(bov.leer(f"{SIS}/Bitácora NEXORA {mes}.md") or "" for mes in sorted({x[0] for x in todas}))
    escritos = set(re.findall(r"\b[0-9a-f]{7}\b", todo_texto))
    hechos = set(bov.estado.d["lineas"])
    for mes, f, clave, ln in todas:
        if clave in hechos or (clave.startswith("commit|") and clave[7:] in escritos):
            continue
        por_mes.setdefault(mes, []).append((clave, ln))
    total = 0
    for mes, items in sorted(por_mes.items()):
        crear = frontmatter({"tags": ["nexora", "bitacora"], "periodo": mes}) + f"# Bitácora NEXORA · {mes}\n\nRegistro automático de lo construido, de los fallos y de las revisiones de datos (el cerebro guarda los errores, no solo los aciertos)."
        rel = f"{SIS}/Bitácora NEXORA {mes}.md"
        n_ = bov.anexar(rel, [x[1] for x in items], cabecera="## Registro automático (NEXORA)", crear=crear)
        if n_:
            bov.estado.d["lineas"] = sorted(set(bov.estado.d["lineas"]) | {x[0] for x in items})
            bov.estado.sucio = True
            total += n_
    return total


# ============================================================================ notas de estado, MOC
def bloque_estado_pendientes(d, bov):
    I = d.json("site/data/integridad.json") or {}
    vc = (d.csv("data/vigilar_cierre.csv") or [])
    vc = [r for r in vc if r.get("resultado") != "SIMULACRO"]
    sp = (d.csv("data/xau_spot_contraste.csv") or [])
    an = d.csv("data/analisis_indice.csv") or []
    L = ["## Estado automático (NEXORA)", "",
         f"- Integridad: {((I.get('resumen') or {}).get('texto')) or 'SIN DATO'} · discrepancias abiertas: {len(I.get('discrepancias_abiertas') or [])}",
         f"- Último vigilante del cierre: {vc[-1]['fecha'] + ' · ' + vc[-1]['resultado'] if vc else 'SIN DATO'}",
         f"- Spot del oro, último contraste: {sp[-1]['fecha'] + ' · ' + sp[-1]['estado'] if sp else 'SIN DATO (aún no hay filas)'}",
         f"- Último informe de Ruiz publicado: {an[-1]['id'] + ' (' + an[-1]['estado'] + ')' if an else 'ninguno todavía'}", ""]
    return "\n".join(L)


def bloque_moc_sistema(bov, docs, regs):
    meses = sorted(f[len("Bitácora NEXORA "):-3] for f in os.listdir(os.path.dirname(bov.ruta(f"{SIS}/x.md"))) if f.startswith("Bitácora NEXORA ") and f.endswith(".md") and "NEXORA v" not in f[16:]) if os.path.isdir(os.path.dirname(bov.ruta(f"{SIS}/x.md"))) else []
    L = ["## Exportación automática (Fase 20)", "", "**Bitácoras**", ""] + [f"- [[Bitácora NEXORA {m}]]" for m in meses]
    L += ["", "**Registros** (últimas 30 filas; el CSV vive en el repo)", ""] + [f"- [[Registros/{r}|{r}]]" for r in regs]
    L += ["", "**Docs** (copia de `docs/` del repo)", ""] + [f"- [[Docs/{x}|{x}]]" for x in docs]
    L += ["", "**Análisis de Ruiz:** [[05_Analisis/00 Índice de análisis|Índice de informes]]", "", "**Memoria de mercado:** [[00_MOC/Market Intelligence|Market Intelligence]] · [[01_State/Global Market State|Estado global]]"]
    return "\n".join(L)


def bloque_estado_global(d, ultimo, tes_vig):
    L = ["## Estado actual (NEXORA, terminal en línea)", "", f"Último snapshot: [[02_Daily_Snapshots/{ultimo}|{ultimo}]]", ""]
    if tes_vig:
        L += [tabla(["Activo", "Tesis vigente", "Desde", "Nota"], tes_vig)]
    L += ["Cada snapshot y cada cambio de tesis los escribe el exportador (`tools/exportar_obsidian.py`); las tesis `T-20261001-*` son del sistema anterior.", ""]
    return "\n".join(L)


def bloque_moc_mi(d):
    return "\n".join(["## Terminal NEXORA (nexora-terminal)", "",
                      "- Tesis registradas por el terminal (una nota por cambio):", "",
                      "```dataview", "TABLE activo, sesgo, intensidad, creada, anterior", f'FROM "{MI}/04_Theses"', 'WHERE origen = "nexora-terminal"', "SORT creada DESC", "LIMIT 30", "```", "",
                      "- [[05_Analisis/00 Índice de análisis|Análisis de Ruiz (informes, cotejo y resultado)]]",
                      "- [[00 Sistema NEXORA (MOC)|Sistema NEXORA: docs, registros y bitácora]]", ""])


# ============================================================================ pasada completa
def exportar(cfg, log):
    d = Datos(cfg["publico"], cfg.get("hoy"))
    estado = Estado(cfg["estado"])
    bov = Boveda(cfg["boveda"], estado, simular=cfg.get("simular", False))
    dias = d.dias()
    cerrados = [D for D in dias if d.cerrado(D)]
    notas_tesis(bov, d, cerrados)
    nsnap = 0
    for D in cerrados:
        rel = f"{MI}/02_Daily_Snapshots/{D}.md"
        if bov.leer(rel) is not None:          # inmutable: si existe no se vuelve ni a calcular
            bov.res["iguales"] += 1
            continue
        nsnap += (bov.inmutable(rel, snapshot(D, d)[0]) == "creada")
    nan = notas_analisis(bov, d, cfg.get("privado"), log)
    nop = notas_diario(bov, d, cfg.get("privado"))
    docs = notas_docs(bov, d)
    regs = notas_registros(bov, d)
    nbit = bitacora(bov, d)
    ultimo = cerrados[-1] if cerrados else None
    tes_vig = []
    for s, lst in sorted(d.tesis_notas.items()):
        D, etiq, act = lst[-1]
        tes_vig.append([act, etiq, D, f"[[04_Theses/T-{D.replace('-', '')}-{s}|T-{D.replace('-', '')}-{s}]]"])
    if ultimo:
        bov.bloque(f"{MI}/01_State/Global Market State.md", "estado", bloque_estado_global(d, ultimo, tes_vig),
                   crear=frontmatter({"tipo": "estado", "tags": ["estado", "nexora"]}) + "# Estado global del mercado")
    bov.bloque(f"{MI}/00_MOC/Market Intelligence.md", "terminal", bloque_moc_mi(d),
               crear=frontmatter({"tipo": "moc", "tags": ["moc", "nexora"]}) + "# Market Intelligence · índice")
    bov.bloque(f"{SIS}/00 Sistema NEXORA (MOC).md", "exportador", bloque_moc_sistema(bov, docs, regs), crear=frontmatter({"tags": ["nexora", "moc"]}) + "# Sistema NEXORA · mapa")
    bov.bloque(f"{SIS}/Estado y pendientes.md", "estado", bloque_estado_pendientes(d, bov), crear=frontmatter({"tags": ["nexora", "pendientes"]}) + "# NEXORA · Estado y pendientes")
    # el MOC del sistema lista las bitácoras que existen: se recalcula tras haber escrito la bitácora (ya incluido arriba porque bitacora() corrió antes)
    estado.guardar()
    return {"res": bov.res, "snapshots_nuevos": nsnap, "dias_cerrados": len(cerrados), "informes": nan, "operaciones": nop, "bitacora_lineas": nbit}


# ============================================================================ latido y push
def latido(publico, estado_txt, ahora, log, extra=()):
    archivos = ["data/obsidian_latido.csv", *extra]
    ruta = os.path.join(publico, "data", "obsidian_latido.csv")
    nuevo = not os.path.exists(ruta)
    with open(ruta, "a", encoding="utf-8", newline="") as f:
        if nuevo:
            f.write("fecha,hora_utc,estado\n")
        f.write(f"{ahora.strftime('%Y-%m-%d')},{ahora.strftime('%H:%M')},{estado_txt}\n")
    msg = f"latido obsidian {ahora.strftime('%Y-%m-%d %H:%M')} UTC [skip ci]"
    for intento in range(4):
        git(publico, "config", "user.name", "nexora-exportador")
        git(publico, "config", "user.email", "nexora-exportador@users.noreply.github.com")
        git(publico, "add", *archivos)
        if intento == 0:
            rc, _, err = git(publico, "commit", "-m", msg, "--", *archivos)
            if rc != 0:
                log(f"latido: no se pudo hacer commit: {err.strip()[-150:]}")
                return False
        rc, _, err = git(publico, "pull", "--rebase", "--autostash")
        if rc != 0:
            git(publico, "rebase", "--abort")
            log(f"latido: pull --rebase falló: {err.strip()[-150:]}")
            continue
        rc, _, err = git(publico, "push", "origin", "HEAD")
        if rc == 0:
            return True
        log(f"latido: push falló (intento {intento + 1}): {err.strip()[-150:]}")
    return False


# ============================================================================ ejecución anclada (seguridad)
# La tarea de Windows NO ejecuta el código que acaba de descargar: ejecuta una copia fija (aprobada por Ruiz) en ANCLADO_DIR. Los DATOS se descargan siempre;
# el CÓDIGO del exportador solo cambia cuando Ruiz lo aprueba con `python tools/exportar_obsidian.py --aprobar`.
REL_SCRIPT = "tools/exportar_obsidian.py"
ANCLADO_DIR = os.path.join(BASE, "aprobado")
ANCLADO = os.path.join(ANCLADO_DIR, "exportar_obsidian.py")
ANCLADO_META = os.path.join(ANCLADO_DIR, "aprobado.json")
REL_PENDIENTE = "data/obsidian_pendiente.json"


def blob_git(ruta):
    r = subprocess.run(["git", "hash-object", ruta], capture_output=True, text=True, encoding="utf-8")
    return r.stdout.strip() if r.returncode == 0 else None


def meta_anclada():
    try:
        return json.load(open(ANCLADO_META, encoding="utf-8"))
    except (OSError, ValueError):
        return None


def visible(s):
    """Hace visibles los caracteres de control y los de dirección/invisibles de Unicode (para que lo mostrado sea lo que hay)."""
    import unicodedata
    return "".join(c if (c == "\t" or (c.isprintable() and unicodedata.category(c) not in ("Cf", "Zl", "Zp"))) else f"\\u{{{ord(c):x}}}" for c in s)


def diff_completo(viejo, nuevo):
    """El diff real y completo entre la versión anclada y la nueva, sin recortar ni enmascarar nada; lo no imprimible se muestra como \\u{..}. Se usa solo en la terminal de Ruiz."""
    import difflib
    a = open(viejo, encoding="utf-8").read().split("\n") if viejo and os.path.exists(viejo) else []
    b = open(nuevo, encoding="utf-8").read().split("\n")
    return [visible(x) for x in difflib.unified_diff(a, b, "anclado", "nuevo", lineterm="", n=2)]


def resumen_diff(viejo, nuevo, maximo=30):
    """Resumen del cambio entre dos versiones del exportador: líneas añadidas/quitadas y las primeras líneas cambiadas (sin secretos)."""
    import difflib
    a = open(viejo, encoding="utf-8").read().splitlines() if viejo and os.path.exists(viejo) else []
    b = open(nuevo, encoding="utf-8").read().splitlines()
    cambios = [x for x in difflib.unified_diff(a, b, lineterm="", n=0) if x[:1] in "+-" and not x.startswith(("+++", "---"))]
    mas, menos = sum(x[0] == "+" for x in cambios), sum(x[0] == "-" for x in cambios)
    return {"anade": mas, "quita": menos, "lineas": [visible(limpiar(x if len(x) <= 160 else x[:160] + f" […LÍNEA LARGA: {len(x)} caracteres, ver el diff completo]")) for x in cambios[:maximo]], "truncado": len(cambios) > maximo}


def comprobar_actualizacion(publico, maximo=30):
    """None si el exportador del repo es el aprobado; si no, dict con el resumen del cambio pendiente de aprobar."""
    nuevo = os.path.join(publico, *REL_SCRIPT.split("/"))
    if not os.path.exists(nuevo):
        return None
    b = blob_git(nuevo)
    m = meta_anclada()
    if m and m.get("blob") == b:
        return None
    rc, out, _ = git(publico, "log", "-1", "--format=%h", "--", REL_SCRIPT)
    return {"pendiente": True, "blob": (b or "")[:12], "commit": out.strip(), "aprobado": (m or {}).get("commit"), "resumen": resumen_diff(ANCLADO, nuevo, maximo)}


def escribir_pendiente(publico, info):
    """data/obsidian_pendiente.json: lo lee integridad.py (aviso + Telegram). Solo se reescribe si cambia."""
    ruta = os.path.join(publico, *REL_PENDIENTE.split("/"))
    txt = json.dumps(info or {"pendiente": False}, ensure_ascii=False, indent=1) + "\n"
    try:
        if open(ruta, encoding="utf-8").read() == txt:
            return False
    except OSError:
        if not info:
            return False
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    open(ruta, "w", encoding="utf-8", newline="\n").write(txt)
    return True


def aprobar(publico, log, blob_esperado=None, confirmar=None):
    r"""Ruiz aprueba el exportador del repo y se ancla esa versión. Medidas contra aprobar código no revisado:
    · NO hace pull: usa lo que la última pasada ya trajo al clon (el diff que viste en #/integridad o en Telegram).
    · Hay que repetir el hash que se vio: `--aprobar <blob>`; si el del clon es otro, se rechaza.
    · El contenido se copia del objeto git (git cat-file), no del árbol de trabajo (sin carrera), y debe coincidir con HEAD del clon.
    · Muestra el diff COMPLETO y pide escribir APROBAR (solo con terminal interactiva).
    Recomendado: ejecutarlo con la copia ya anclada (`python %USERPROFILE%\NexoraExportador\aprobado\exportar_obsidian.py --aprobar <blob>`), nunca con el archivo recién descargado."""
    nuevo = os.path.join(publico, *REL_SCRIPT.split("/"))
    info = comprobar_actualizacion(publico, maximo=100000)
    if info is None:
        log("el exportador anclado ya es el del repo; nada que aprobar")
        return 0
    b = blob_git(nuevo)
    rc, head, _ = git(publico, "rev-parse", f"HEAD:{REL_SCRIPT}")
    if rc != 0 or head.strip() != b:
        log("el archivo del clon no coincide con HEAD (¿modificado a mano?): no se aprueba")
        return 1
    r = info["resumen"]
    log(f"exportador pendiente {info['commit']} (aprobado hasta ahora: {info['aprobado'] or 'ninguno'}): +{r['anade']} −{r['quita']} líneas · hash {b[:12]}")
    if sys.stdout:
        print("\n".join(diff_completo(ANCLADO, nuevo)))      # el diff real y completo, sin recortes ni enmascarado; lo no imprimible, visible
    if not blob_esperado:
        log(f"Revisa el diff y repite con el hash: --aprobar {b[:12]}")
        return 2
    if not b.startswith(blob_esperado.strip().lower()) or len(blob_esperado.strip()) < 8:
        log(f"el hash indicado no es el del clon ({b[:12]}): lo que ibas a aprobar no es lo que hay ahora; no se aprueba")
        return 1
    if confirmar is None:
        if not (sys.stdin and sys.stdin.isatty()):
            log("sin terminal interactiva: la aprobación exige escribir APROBAR a mano")
            return 1
        confirmar = input("Escribe APROBAR para anclar esta versión: ").strip()
    if confirmar != "APROBAR":
        log("no confirmado")
        return 1
    r2 = subprocess.run(["git", "-C", publico, "cat-file", "blob", b], capture_output=True)
    if r2.returncode != 0:
        log("no se pudo leer el objeto git")
        return 1
    os.makedirs(ANCLADO_DIR, exist_ok=True)
    if os.path.exists(ANCLADO):
        os.chmod(ANCLADO, 0o666)
    with open(ANCLADO, "wb") as f:
        f.write(r2.stdout)
    if blob_git(ANCLADO) != b:
        os.remove(ANCLADO)
        log("la copia no coincide con el objeto git; abortado")
        return 1
    os.chmod(ANCLADO, 0o444)
    json.dump({"commit": info["commit"], "blob": b, "aprobado_local": dt.datetime.now().isoformat(timespec="seconds")}, open(ANCLADO_META, "w", encoding="utf-8"), indent=1)
    log(f"exportador {info['commit']} ({b[:12]}) aprobado y anclado en {ANCLADO}")
    return 0


def debida(ahora_local):
    """Última hora programada (08:30 / 23:45) que ya pasó."""
    cands = []
    for dd in (ahora_local.date() - dt.timedelta(days=1), ahora_local.date()):
        for s in SLOTS_LOCALES:
            t = dt.datetime.combine(dd, dt.time.fromisoformat(s))
            if t <= ahora_local:
                cands.append(t)
    return max(cands)


def registrar_tarea(script, log):
    py = sys.executable
    pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
    exe = pyw if os.path.exists(pyw) else py
    ps = f"""
$ErrorActionPreference = 'Stop'
$a = New-ScheduledTaskAction -Execute '{exe}' -Argument '"{script}" --programado'
$t1 = New-ScheduledTaskTrigger -Daily -At 08:30
$t2 = New-ScheduledTaskTrigger -Daily -At 23:45
$t3 = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName '{TAREA}' -Action $a -Trigger @($t1,$t2,$t3) -Settings $s -Description 'NEXORA Fase 20: exporta el terminal a la bóveda de Obsidian (08:30, 23:45 y al iniciar sesión si se perdió la última). Sin secretos en el log.' -Force | Out-Null
Get-ScheduledTask -TaskName '{TAREA}' | Select-Object TaskName,State | Format-Table -AutoSize | Out-String
"""
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True, text=True, encoding="utf-8", errors="replace")
    log(f"tarea: rc={r.returncode} {limpiar(r.stdout).strip()} {limpiar(r.stderr).strip()[:300]}")
    return r.returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boveda", default=os.environ.get("NEXORA_BOVEDA") or BOVEDA_DEF)
    ap.add_argument("--publico", default=None, help="clon del repo público (defecto: clon propio del exportador)")
    ap.add_argument("--privado", default=None, help="clon del repo privado nexora-diario")
    ap.add_argument("--estado", default=os.path.join(BASE, "estado.json"))
    ap.add_argument("--log", default=os.path.join(BASE, "exportador.log"))
    ap.add_argument("--sin-git", action="store_true")
    ap.add_argument("--sin-latido", action="store_true")
    ap.add_argument("--programado", action="store_true")
    ap.add_argument("--forzar", action="store_true")
    ap.add_argument("--registrar-tarea", action="store_true")
    ap.add_argument("--aprobar", nargs="?", const="", default=None, metavar="BLOB", help="aprueba y ancla la versión del exportador que hay en el repo (la tarea solo ejecuta la aprobada)")
    ap.add_argument("--vista-previa", default=None)
    ap.add_argument("--hoy", default=None)
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.log), exist_ok=True)

    def log(m):
        linea = f"{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {limpiar(m)}"
        try:
            with open(a.log, "a", encoding="utf-8") as f:
                f.write(linea + "\n")
            if sys.stdout:
                print(linea, flush=True)
        except Exception:  # noqa: BLE001
            pass

    ahora = dt.datetime.now(UTC)
    if a.aprobar is not None:
        return aprobar(a.publico or os.path.join(BASE, "repos", "nexora-terminal"), log, a.aprobar or None)
    if a.registrar_tarea:
        if not os.path.exists(ANCLADO):
            log("primero aprueba una versión: python tools/exportar_obsidian.py --aprobar")
            return 1
        return 0 if registrar_tarea(ANCLADO, log) else 1
    anclado = os.path.abspath(__file__) == os.path.abspath(ANCLADO)
    pendiente = None
    publico = a.publico or os.path.join(BASE, "repos", "nexora-terminal")
    privado = a.privado or os.path.join(BASE, "repos", "nexora-diario")
    est = Estado(a.estado)
    if a.programado and not a.forzar:
        due = debida(dt.datetime.now())
        ult = est.d.get("ultima_pasada_local")
        if ult and dt.datetime.fromisoformat(ult) >= due:
            log(f"programado: ya hay una pasada posterior a la hora debida ({due:%Y-%m-%d %H:%M}); nada que hacer")
            return 0
    estado_final, avisos = "OK", []
    try:
        if not a.sin_git:
            ok, _, m = preparar_clon(publico, URL_PUBLICO, log)
            if not ok:
                avisos.append(f"repo público: {m}")
            ok2, vacio, m2 = preparar_clon(privado, URL_PRIVADO, log)
            if not ok2:
                avisos.append(f"repo privado: {m2} (se exporta sin los informes nuevos)")
            elif vacio:
                log("repo privado vacío: todavía no hay informes")
        if anclado and not a.sin_git:
            pendiente = comprobar_actualizacion(publico)
            if pendiente:
                log(f"EXPORTADOR ACTUALIZADO en el repo ({pendiente['commit']}), pendiente de aprobar: +{pendiente['resumen']['anade']} −{pendiente['resumen']['quita']} líneas. "
                    "Se sigue ejecutando la versión aprobada. Aprobar tras revisar el diff: python tools/exportar_obsidian.py --aprobar <hash>")
        if a.vista_previa:
            d = Datos(publico, a.hoy)
            print(snapshot(a.vista_previa, d)[0])
            return 0
        if not os.path.isdir(os.path.join(a.boveda, MI)):
            raise RuntimeError(f"no encuentro la bóveda en «{a.boveda}»")
        r = exportar({"boveda": a.boveda, "publico": publico, "privado": privado if os.path.isdir(os.path.join(privado, ".git")) else None, "estado": a.estado, "hoy": a.hoy}, log)
        res = r["res"]
        log(f"exportación: {len(res['creadas'])} creadas · {len(res['actualizadas'])} actualizadas · {len(res['ampliadas'])} ampliadas · {len(res['v2'])} v2 · {res['iguales']} sin cambios "
            f"(snapshots nuevos {r['snapshots_nuevos']}, días cerrados {r['dias_cerrados']}, informes {r['informes']}, líneas de bitácora {r['bitacora_lineas']})")
        for x in res["creadas"]:
            log("  + " + x)
        for x in res["actualizadas"] + res["ampliadas"]:
            log("  ~ " + x)
        for x in res["avisos"]:
            log("  AVISO " + x)
            avisos.append(x)
        if avisos:
            estado_final = "AVISO"
        est2 = Estado(a.estado)
        est2.d["ultima_pasada_local"] = dt.datetime.now().isoformat(timespec="seconds")
        est2.d["ultima_ok_utc"] = ahora.strftime("%Y-%m-%d %H:%M")
        est2.sucio = True
        est2.guardar()
        print_resumen(r)
    except Exception as e:  # noqa: BLE001
        estado_final = "ERROR"
        log("ERROR " + limpiar(f"{type(e).__name__}: {e}") + " | " + limpiar(traceback.format_exc().splitlines()[-3:]))
    if pendiente and estado_final != "ERROR":
        estado_final = "PENDIENTE@" + str(pendiente.get("aprobado") or "ninguno")[:7]
    if not a.sin_latido and not a.sin_git:
        try:
            extra = [REL_PENDIENTE] if anclado and escribir_pendiente(publico, pendiente) else []
            ok = latido(publico, estado_final, ahora, log, extra)
            log(f"latido {estado_final}: {'subido' if ok else 'NO subido'}")
        except Exception as e:  # noqa: BLE001
            log("latido: " + limpiar(f"{type(e).__name__}: {e}"))
    return 0 if estado_final != "ERROR" else 1


def print_resumen(r):
    if sys.stdout is None:
        return
    res = r["res"]
    print(f"Creadas {len(res['creadas'])} · actualizadas {len(res['actualizadas'])} · ampliadas {len(res['ampliadas'])} · v2 {len(res['v2'])} · sin cambios {res['iguales']}")


if __name__ == "__main__":
    sys.exit(main())
