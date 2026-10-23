#!/usr/bin/env python3
"""NEXORA · publica el informe diario de Ruiz (Fase 18). Guardado SOLO AÑADIR: nunca sobrescribe.

  python tools/publicar_analisis.py INFORME.txt --sesgo neutral --tipo DIARIO|SEMANAL --visibilidad privado [--fecha AAAA-MM-DD] [--corte HH:MM]
  (tipo DIARIO = ORO_MACRO, el defecto; INDICES = diario de índices; SEMANAL = el del domingo, archivo AAAA-MM-DD_semanal.md)

Qué hace (sin IA; el texto se guarda tal cual):
  1. Calcula el hash, extrae las secciones (engine/analisis.py) y COTEJA el panel A.2, el calendario B.3 y las probabilidades de la Fed contra los datos de NEXORA de la MISMA fecha.
  2. Guarda el informe COMPLETO (front-matter + texto) en el repo PRIVADO komonartisans-ops/nexora-diario: analisis/AAAA/AAAA-MM-DD_<tipo>[_vN].md (vía `gh api`; necesita `gh auth` con acceso a ese repo).
  3. Repo PÚBLICO: data/analisis_indice.csv (fecha, tipo, versión, visibilidad, sesgo, hash), data/analisis_cotejos.jsonl (cotejo numérico) y site/data/analisis.json.
     Con --visibilidad resumen, además data/analisis/AAAA/<id>.md con SOLO el resumen (tesis, veredicto, K.2, escenarios literales). Con privado, ningún texto del informe llega al repo público.
  4. Si ya hay un informe de esa fecha y tipo con otro hash → archivo _v2 (_v3…) y el anterior queda REVISADA (una fila nueva en el índice; no se toca ningún archivo). Mismo hash → no hace nada.
  --solo-local DIR  escribe el informe completo en DIR en vez de en GitHub (pruebas). --raiz RUTA  raíz del repo público (pruebas).
Salida: SOLO la ruta del archivo, el resumen del cotejo (n ✅ · n ⚠️ · n —) y la lista de ⚠️. No hace commit ni push (lo hace quien lo lanza)."""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import subprocess
import sys
import zoneinfo

HERE = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(RAIZ, "engine"))
import analisis as A  # noqa: E402

REPO_PRIVADO = "komonartisans-ops/nexora-diario"
MAD = zoneinfo.ZoneInfo("Europe/Madrid")
UTC = dt.timezone.utc


def _gh(*args, entrada=None):
    return subprocess.run(["gh", *args], input=entrada, capture_output=True, text=True, encoding="utf-8", timeout=120)


def escribir_privado(ruta, contenido, solo_local=None):
    """Crea `ruta` en el repo privado. Si ya existe con OTRO contenido, lanza error (nunca se sobrescribe). Devuelve la ruta (o la local)."""
    if solo_local:
        p = os.path.join(solo_local, ruta)
        if os.path.exists(p) and open(p, encoding="utf-8").read() != contenido:
            raise RuntimeError(f"{ruta} ya existe con otro contenido: no se sobrescribe")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w", encoding="utf-8", newline="\n").write(contenido)
        return p
    r = _gh("api", f"repos/{REPO_PRIVADO}/contents/{ruta}", "-H", "Accept: application/vnd.github.raw+json")
    if r.returncode == 0:
        if r.stdout != contenido:
            raise RuntimeError(f"{ruta} ya existe en {REPO_PRIVADO} con otro contenido: no se sobrescribe")
        return f"{REPO_PRIVADO}:{ruta}"
    cuerpo = json.dumps({"message": f"análisis {os.path.basename(ruta)}", "content": base64.b64encode(contenido.encode("utf-8")).decode()})
    w = _gh("api", "-X", "PUT", f"repos/{REPO_PRIVADO}/contents/{ruta}", "--input", "-", entrada=cuerpo)
    if w.returncode != 0:
        raise RuntimeError("no se pudo escribir en el repo privado: " + (w.stderr or w.stdout)[:200])
    return f"{REPO_PRIVADO}:{ruta}"


def precio_base(raiz, t0, precio_fn=None):
    """(precio, hora UTC, fuente) del oro en el CORTE: la barra de 5 min de GC=F más cercana anterior a t0 (Yahoo); si no, la última captura horaria de NEXORA anterior a t0. None si no hay; nunca un dato posterior."""
    try:
        v, hora, fuente = (precio_fn or A.precio_base_yahoo)(t0)
    except Exception:  # noqa: BLE001
        u = A._ultimo_antes(raiz, "oro", t0)
        return (u[0], u[1], "historico_precios.csv (captura horaria de NEXORA, GC=F)") if u else None
    if A._utc(hora) is None or A._utc(hora) > t0:
        raise ValueError("el precio base no puede ser posterior al corte")
    return v, hora, fuente


def publicar(texto, sesgo, tipo, visibilidad, fecha=None, corte=None, raiz=RAIZ, solo_local=None, ahora=None, precio_fn=None):
    tipo = A.tipo_normal(tipo)
    if sesgo not in A.SESGOS or tipo not in A.TIPOS or visibilidad not in A.VISIBILIDADES:
        raise ValueError("sesgo, tipo o visibilidad no válidos")
    ahora = ahora or dt.datetime.now(UTC)
    texto = texto.replace("\r\n", "\n").strip("\n") + "\n"
    h = A.hash_texto(texto)
    parsed = A.parse(texto)
    fecha = fecha or parsed["fecha_detectada"] or ahora.astimezone(MAD).strftime("%Y-%m-%d")
    # CORTE ≠ PUBLICACIÓN: el corte es el de la cabecera del informe; la hora de publicación se guarda aparte (publicado_utc) y no se usa para evaluar. Sin corte en el informe: ESTIMADO = hora de publicación.
    if corte:
        corte_origen = "MANUAL"
    elif parsed["corte_detectado"]:
        corte, corte_origen = parsed["corte_detectado"], "INFORME"
    else:
        corte, corte_origen = ahora.astimezone(MAD).strftime("%H:%M"), "ESTIMADO"
    t0 = A.t0_utc(fecha, corte)
    pb = precio_base(raiz, t0, precio_fn)
    ruta_ind = A.P(raiz, "data", "analisis_indice.csv")
    previos = [r for r in A.indice_vigente(raiz) if r["fecha"] == fecha and r["tipo"] == tipo]
    if any(r["hash"] == h for r in previos):
        return {"estado": "YA_PUBLICADO", "id": next(r["id"] for r in previos if r["hash"] == h)}
    version = len(previos) + 1
    id_ = f"{fecha}_{A.sufijo_tipo(tipo)}" + (f"_v{version}" if version > 1 else "")
    sello = ahora.strftime("%Y-%m-%d %H:%M UTC")
    # 1) cotejo (solo lectura de los datos de NEXORA)
    cot = A.cotejar(parsed, fecha, raiz)
    # 2) informe completo, al repo privado
    fm = A._frontmatter({"fecha": fecha, "corte_madrid": corte, "tipo": tipo, "visibilidad": visibilidad, "sesgo_oro": sesgo, "escenarios": [e["nombre"] for e in parsed["escenarios"]], "hash": h, "version": version,
                         "corte_origen": corte_origen, "publicado_utc": ahora.strftime("%Y-%m-%d %H:%M UTC"), "precio_base": pb[0] if pb else "SIN DATO", "precio_base_hora": pb[1] if pb else ""})
    ruta_priv = f"analisis/{fecha[:4]}/{id_}.md"
    destino = escribir_privado(ruta_priv, fm + "\n\n" + texto, solo_local)
    # el informe ya extraído (secciones, escenarios…) también va al repo PRIVADO: la vista del terminal lo lee con el token del Diario; no se reanaliza en el navegador
    estructura = {k: parsed[k] for k in ("secciones", "bloques", "orden", "tesis_central", "veredicto", "tesis_final", "escenarios", "red_team", "data_gaps", "reconocido")}
    estructura["cotejo"] = cot            # el cotejo con los textos literales del informe (filas, eventos y líneas de la Fed) solo en el repo privado
    estructura.update({"id": id_, "fecha": fecha, "corte_madrid": corte, "tipo": tipo, "sesgo_oro": sesgo, "hash": h, "texto": texto})
    escribir_privado(ruta_priv[:-3] + ".json", json.dumps(estructura, ensure_ascii=False, indent=1), solo_local)
    # 3) repo público: índice, cotejo y (solo si visibilidad=resumen) el resumen
    resumen = A.resumen_publico(parsed) if visibilidad == "resumen" else None
    ruta_pub = None
    if resumen is not None:
        ruta_pub = A.P(raiz, "data", "analisis", fecha[:4], f"{id_}.md")
        os.makedirs(os.path.dirname(ruta_pub), exist_ok=True)
        cuerpo = [fm, "", "# RESUMEN (el informe completo es privado)", "", "## Tesis central", resumen["tesis_central"] or "SIN DATO (no se reconoció)", "",
                  "## Veredicto", resumen["veredicto"] or "SIN DATO (no se reconoció)", "", "## Tesis final (K.2)", resumen["tesis_final"] or "SIN DATO (no se reconoció)", "", "## Escenarios"]
        for e in resumen["escenarios"]:
            cuerpo += [f"### {e['nombre']}", f"- Condiciones: {e['condiciones'] or 'SIN DATO'}", f"- Confirmación: {e['confirmacion'] or 'SIN DATO'}", f"- Invalidación: {e['invalidacion'] or 'SIN DATO'}", ""]
        open(ruta_pub, "x", encoding="utf-8", newline="\n").write("\n".join(cuerpo) + "\n")       # «x»: si existe, falla (nunca sobrescribe)
    filas = []
    for p in previos:
        if p["estado"] == "VIGENTE":
            filas.append({**p, "estado": "REVISADA", "registrada_utc": sello, "nota": f"sustituida por {id_}"})
    filas.append({"id": id_, "fecha": fecha, "tipo": tipo, "version": version, "visibilidad": visibilidad, "sesgo_oro": sesgo, "corte_madrid": corte, "corte_origen": corte_origen, "publicado_utc": sello,
                  "precio_base": pb[0] if pb else "", "precio_base_hora": pb[1] if pb else "", "precio_base_fuente": pb[2] if pb else "SIN DATO", "hash": h, "estado": "VIGENTE", "registrada_utc": sello, "nota": ""})
    # el índice es solo-añadir con clave (id, estado): una fila REVISADA nueva no pisa la VIGENTE antigua, la sustituye como último estado
    n0 = len(A.leer_csv(ruta_ind))
    os.makedirs(os.path.dirname(ruta_ind), exist_ok=True)
    A.anadir_csv(ruta_ind, filas, A.CAMPOS_INDICE, lambda r: (r["id"], r["estado"]))
    assert len(A.leer_csv(ruta_ind)) == n0 + len(filas)
    reg = {"id": id_, "fecha": fecha, "tipo": tipo, "registrada_utc": sello, "panel": [{k: v for k, v in x.items() if k != "texto"} for x in cot["panel"]],
           "calendario": [{k: v for k, v in x.items() if k != "texto"} for x in cot["calendario"]],       # sin el texto del evento del informe (solo fecha, hora, estado, evento de NEXORA y nota)
           "fed": {"informe": [], "informe_n": len(cot["fed"]["informe"]), "informe_fuente": cot["fed"]["informe_fuente"], "nexora": cot["fed"]["nexora"]},      # las líneas literales de la Fed van al repo privado
           "resumen": cot["resumen"], "resumen_calendario": cot["resumen_calendario"],
           "tolerancias": cot["tolerancias"], "resumen_publico": resumen}
    with open(A.P(raiz, "data", "analisis_cotejos.jsonl"), "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(reg, ensure_ascii=False) + "\n")
    J = A.construir(raiz, ahora)
    os.makedirs(A.P(raiz, "site", "data"), exist_ok=True)
    json.dump(J, open(A.P(raiz, "site", "data", "analisis.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return {"estado": "PUBLICADO", "id": id_, "version": version, "corte": corte, "corte_origen": corte_origen, "precio_base": pb, "ruta_privada": destino, "ruta_publica": ruta_pub, "cotejo": cot, "reconocido": parsed["reconocido"]}


def salida(r):
    """Lo ÚNICO que se responde: ruta, resumen del cotejo y lista de ⚠️."""
    if r["estado"] == "YA_PUBLICADO":
        return f"Ya publicado (mismo hash): {r['id']}. No se escribió nada."
    c = r["cotejo"]
    s, sc = c["resumen"], c["resumen_calendario"]
    out = [f"Archivo: {r['ruta_privada']}" + (f" · público (resumen): {os.path.relpath(r['ruta_publica'], RAIZ).replace(os.sep, '/')}" if r["ruta_publica"] else " · público: solo índice y cotejo (sin texto)"),
           f"Cotejo del panel A.2: {s['ok']} ✅ · {s['dif']} ⚠️ · {s['sin']} —   |   calendario B.3: {sc['ok']} ✅ · {sc['dif']} ⚠️ · {sc['sin']} —"]
    if not r["reconocido"]:
        out.append("AVISO: no se reconoció ninguna cabecera de sección; la vista mostrará el texto tal cual.")
    if r["corte_origen"] == "ESTIMADO":
        out.append(f"⚠️ corte=ESTIMADO ({r['corte']} Madrid = hora de publicación): el informe no trae «Corte: HH:MM»")
    if not r["precio_base"]:
        out.append("⚠️ sin precio base del oro en el corte: este informe no se evaluará hasta que haya datos anteriores al corte")
    ws = [f"⚠️ {f['nombre']}: informe {f['valor']:g} · NEXORA {f['nexora']:g} ({f['fuente']}, {f['fecha_nexora']}) · dif {f['dif']:+g} (tolerancia {f['tolerancia']})" for f in c["panel"] if f["estado"] == "⚠️"]
    ws += [f"⚠️ {f['fecha']} {f['hora'] or ''} {f['texto'][:50] or f['nexora']['evento']}: {f['nota']}" for f in c["calendario"] if f["estado"] == "⚠️"]
    return "\n".join(out + ws)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("archivo")
    ap.add_argument("--sesgo", required=True, choices=A.SESGOS)
    ap.add_argument("--tipo", default="DIARIO", choices=("DIARIO",) + A.TIPOS)
    ap.add_argument("--visibilidad", required=True, choices=A.VISIBILIDADES)
    ap.add_argument("--fecha")
    ap.add_argument("--corte")
    ap.add_argument("--solo-local")
    ap.add_argument("--raiz", default=RAIZ)
    a = ap.parse_args()
    r = publicar(open(a.archivo, encoding="utf-8").read(), a.sesgo, a.tipo, a.visibilidad, a.fecha, a.corte, a.raiz, a.solo_local)
    print(salida(r))


if __name__ == "__main__":
    main()
