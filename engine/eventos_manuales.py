#!/usr/bin/env python3
"""NEXORA · eventos MANUALES de la agenda (data/eventos_manuales.csv). Para un dato o acto que el calendario oficial no trae (una reunión de la OPEP+, un discurso, una decisión
de un banco central…): se añade una fila desde GitHub y la agenda, el aviso previo (si es ALTA con hora) y la contaminación de las fases lo tratan IGUAL que un evento oficial,
marcado «manual». Sin IA, sin red.

Columnas (cabecera exacta): fecha, hora_et, evento, importancia, url, añadido_por
  fecha        AAAA-MM-DD
  hora_et      HH:MM en hora de Nueva York (ET). Vacía = sin hora (aparece en la agenda pero no puede avisar ni contaminar: sin hora no se inventa)
  evento       texto corto (máx. 120 caracteres)
  importancia  ALTA, MEDIA o BAJA (la agenda muestra ALTA y MEDIA)
  url          https:// de la FUENTE que confirma el evento (obligatoria: sin fuente no se añade)
  añadido_por  quién lo añade (obligatorio)
Una fila inválida NO se usa y el motivo aparece como error en el calendario (no rompe el resto)."""
from __future__ import annotations

import csv
import datetime as dt
import os
import re
import sys
import zoneinfo

HERE = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(HERE)
NY = zoneinfo.ZoneInfo("America/New_York")
CAMPOS = ["fecha", "hora_et", "evento", "importancia", "url", "añadido_por"]
IMPORTANCIAS = ("ALTA", "MEDIA", "BAJA")


def ruta(raiz=RAIZ):
    return os.path.join(raiz, "data", "eventos_manuales.csv")


def leer(raiz=RAIZ):
    """(eventos válidos, errores). Cada evento: {fecha (date), hora_et ('HH:MM' o ''), evento, importancia, url, anadido_por}."""
    p = ruta(raiz)
    if not os.path.exists(p):
        return [], []
    eventos, errores, vistos = [], [], set()
    with open(p, encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f)
        faltan = [c for c in CAMPOS if c not in (lector.fieldnames or [])]
        if faltan:
            return [], [f"data/eventos_manuales.csv: falta(n) la(s) columna(s) {', '.join(faltan)} (cabecera esperada: {','.join(CAMPOS)})"]
        for n, r in enumerate(lector, start=2):
            if not any((v or "").strip() for v in r.values()):
                continue
            fila = f"data/eventos_manuales.csv, línea {n}"
            try:
                fecha = dt.date.fromisoformat((r["fecha"] or "").strip())
            except ValueError:
                errores.append(f"{fila}: fecha «{r['fecha']}» inválida (usa AAAA-MM-DD)")
                continue
            hora = (r["hora_et"] or "").strip()
            if hora and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", hora):
                errores.append(f"{fila}: hora_et «{hora}» inválida (usa HH:MM, hora de Nueva York)")
                continue
            nombre = " ".join((r["evento"] or "").split())
            if not nombre or len(nombre) > 120:
                errores.append(f"{fila}: «evento» vacío o de más de 120 caracteres")
                continue
            imp = (r["importancia"] or "").strip().upper()
            if imp not in IMPORTANCIAS:
                errores.append(f"{fila}: importancia «{r['importancia']}» inválida (ALTA, MEDIA o BAJA)")
                continue
            url = (r["url"] or "").strip()
            if not re.fullmatch(r"https://[^\s<>\"']+", url):
                errores.append(f"{fila}: «url» debe ser una fuente https:// (sin fuente no se añade el evento)")
                continue
            quien = " ".join((r["añadido_por"] or "").split())
            if not quien:
                errores.append(f"{fila}: falta «añadido_por»")
                continue
            clave = (fecha, hora, nombre)
            if clave in vistos:
                continue
            vistos.add(clave)
            eventos.append({"fecha": fecha, "hora_et": hora, "evento": nombre, "importancia": imp, "url": url, "anadido_por": quien[:60]})
    return sorted(eventos, key=lambda e: (e["fecha"], e["hora_et"] or "99")), errores


def para_calendario(raiz, desde, hasta, ev):
    """Eventos del calendario (misma forma que los oficiales, vía calendario.ev) entre desde y hasta, con origen «manual». Devuelve (lista, errores)."""
    E, err = leer(raiz)
    out = []
    for m in E:
        if not (desde <= m["fecha"] <= hasta):
            continue
        x = ev(m["fecha"], m["hora_et"] or None, m["evento"], m["importancia"], "manual", "Evento añadido a mano (no viene del calendario oficial): comprueba la fuente.",
               f"Manual · añadido por {m['anadido_por']}", m["url"], f"manual · añadido por {m['anadido_por']}" + ("" if m["hora_et"] else " · hora sin confirmar"))
        x["origen"] = "manual"
        out.append(x)
    return out, err


def altos_para_reaccion(raiz, desde, hasta):
    """Eventos ALTA con hora, en el formato de agenda.eventos_altos, para que cuenten como contaminantes de las fases de un evento oficial (NO se miden como evento propio)."""
    E, _ = leer(raiz)
    return [{"id": f"MANUAL-{m['fecha']}-{m['hora_et'].replace(':', '')}", "tipo": "MANUAL", "evento": m["evento"] + " (manual)", "fecha": m["fecha"], "hora_ny": m["hora_et"],
             "fuente": f"Manual · añadido por {m['anadido_por']}", "url": m["url"], "manual": True}
            for m in E if m["importancia"] == "ALTA" and m["hora_et"] and desde <= m["fecha"] <= hasta]


if __name__ == "__main__":
    E, err = leer(sys.argv[1] if len(sys.argv) > 1 else RAIZ)
    print(f"{len(E)} evento(s) manual(es) válido(s)")
    for e in E:
        print(" ", e["fecha"], e["hora_et"] or "sin hora", e["importancia"], e["evento"], "·", e["anadido_por"])
    for x in err:
        print("  ERROR:", x)
    sys.exit(1 if err else 0)
