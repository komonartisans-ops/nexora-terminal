"""NEXORA · memoria permanente: CSV de SOLO AÑADIR, sin filas duplicadas.

Cada fila se identifica por una clave (columnas `claves`); si esa clave ya existe en el archivo no se vuelve a escribir.
El histórico de Git de data/*.csv funciona además como «datos vintage» (qué se sabía en cada fecha)."""
from __future__ import annotations

import csv
import os

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def leer(nombre):
    p = os.path.join(DATA, nombre)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def anadir(nombre, filas, claves):
    """Añade las filas cuya clave (tupla de `claves`) no existe todavía. Devuelve cuántas se añadieron."""
    if not filas:
        return 0
    os.makedirs(DATA, exist_ok=True)
    p = os.path.join(DATA, nombre)
    vistas = {tuple(r.get(c, "") for c in claves) for r in leer(nombre)}
    nuevas = []
    for fila in filas:
        k = tuple(str(fila.get(c, "")) for c in claves)
        if k in vistas:
            continue
        vistas.add(k)
        nuevas.append(fila)
    if not nuevas:
        return 0
    campos = list(filas[0].keys())
    existe = os.path.exists(p)
    if existe:  # si ya hay cabecera se respeta su orden de columnas
        with open(p, encoding="utf-8", newline="") as f:
            cab = next(csv.reader(f), None)
        if cab:
            campos = cab
    with open(p, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        if not existe or os.path.getsize(p) == 0:
            w.writeheader()
        w.writerows(nuevas)
    return len(nuevas)
