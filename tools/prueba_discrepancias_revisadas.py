#!/usr/bin/env python3
"""Pruebas de «discrepancias revisadas» de Integridad. Sin red. Uso: PYTHONUTF8=1 python tools/prueba_discrepancias_revisadas.py"""
import csv
import datetime as dt
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine"))
import integridad as I  # noqa: E402

UTC = dt.timezone.utc
T = tempfile.mkdtemp(prefix="rev_")
os.makedirs(os.path.join(T, "data"))
t = lambda d, h="10:00": dt.datetime.fromisoformat(f"{d} {h}").replace(tzinfo=UTC)  # noqa: E731


def brent(fred=126.55, fut=106.06, per="2026-10-14"):
    dif = abs((fut / fred - 1) * 100)
    return {"id": "x", "detectada_utc": "", "serie": "BRENT", "periodo": per, "tipo": "VALOR", "fred_valor": str(fred), "primaria": "Yahoo BZ=F (futuro)", "primaria_valor": str(fut), "dif_pct": f"{dif:.4f}", "estado": "ABIERTA", "nota": ""}


cal = [{"dato": "Ofertas de empleo (JOLTS)", "serie": "JTSJOL", "fred": "JOLTS de septiembre · 3-nov", "oficial": "JOLTS de octubre · 1-dic", "oficial_fuente": "BLS", "motivo": "m", "proximo": {"fecha": "2026-11-03"}}]


def filas():
    with open(os.path.join(T, "data", "discrepancias_revisadas.csv"), encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# 1) sin revisar: todo cuenta
ab, c, rv = I.aplicar_revisadas(T, t("2026-10-20"), [brent()], cal)
assert len(ab) == 1 and len(c) == 1 and rv == [] and not os.path.exists(os.path.join(T, "data", "discrepancias_revisadas.csv"))
# 2) revisar con motivo y fecha; clave inexistente falla
try:
    I.revisar(T, "NOEXISTE", "x", "Ruiz", t("2026-10-20"), abiertas=[brent()], calendario=cal)
    raise SystemExit("debía fallar")
except ValueError:
    pass
f = I.revisar(T, "BRENT", "Físico vs futuro en backwardation. Revisado por Ruiz 20-10-2026", "Ruiz", t("2026-10-20", "07:18"), abiertas=[brent()], calendario=cal)
I.revisar(T, "CALENDARIO|JTSJOL|2026-11-03", "Pendiente de resolver el 3-nov con el dato real", "Ruiz", t("2026-10-20", "07:18"), abiertas=[brent()], calendario=cal)
assert f["signo_ref"] == -1 and f["registrada_utc"] == "2026-10-20 07:18 UTC" and len(filas()) == 2
ab, c, rv = I.aplicar_revisadas(T, t("2026-10-20", "08:00"), [brent()], cal)
assert ab == [] and c == [] and {r["clave"] for r in rv} == {"BRENT", "CALENDARIO|JTSJOL|2026-11-03"} and all(r["motivo"] and r["revisor"] == "Ruiz" for r in rv), "revisadas: fuera del contador, visibles, con motivo"
assert len(filas()) == 2, "no escribe nada si no cambia nada"
print("1-2) OK revisar con motivo y fecha; las revisadas salen del contador y siguen visibles; clave inexistente → error")

# 3) Brent: sigue revisada con cambios pequeños (también 24,9 %)
ab, c, rv = I.aplicar_revisadas(T, t("2026-10-21"), [brent(fut=126.55 * (1 - 0.249), per="2026-10-20")], cal)
assert ab == [] and len(rv) == 2
# 4) Brent: > 25 % se reabre (fila REABIERTA, vuelve a contar) y sigue reabierta aunque luego baje
ab, c, rv = I.aplicar_revisadas(T, t("2026-10-22"), [brent(fut=126.55 * (1 - 0.26), per="2026-10-21")], cal)
assert len(ab) == 1 and [r["clave"] for r in rv] == ["CALENDARIO|JTSJOL|2026-11-03"] and filas()[-1]["estado"] == "REABIERTA" and "25" in filas()[-1]["nota"]
ab, c, rv = I.aplicar_revisadas(T, t("2026-10-23"), [brent(per="2026-10-22")], cal)
assert len(ab) == 1, "reabierta: vuelve a contar hasta que se revise otra vez"
I.revisar(T, "BRENT", "revisada de nuevo", "Ruiz", t("2026-10-23", "11:00"), abiertas=[brent(per="2026-10-22")], calendario=cal)
assert I.aplicar_revisadas(T, t("2026-10-23", "12:00"), [brent(per="2026-10-22")], cal)[0] == []
# 5) Brent: el signo se invierte → se reabre
ab, c, rv = I.aplicar_revisadas(T, t("2026-10-24"), [brent(fred=100.0, fut=115.0, per="2026-10-23")], cal)
assert len(ab) == 1 and filas()[-1]["estado"] == "REABIERTA" and "signo" in filas()[-1]["nota"]
# 6) se cierra sola: Brent por debajo del umbral (la discrepancia ya no existe) y JOLTS cuando sale el dato (desaparece del calendario)
I.revisar(T, "BRENT", "otra vez", "Ruiz", t("2026-10-24", "12:00"), abiertas=[brent(fred=100.0, fut=115.0)], calendario=cal)
ab, c, rv = I.aplicar_revisadas(T, t("2026-11-03", "16:30"), [], [])
assert ab == [] and c == [] and rv == []
ult = I.revisiones(T)
assert ult["BRENT"]["estado"] == "CERRADA" and ult["CALENDARIO|JTSJOL|2026-11-03"]["estado"] == "CERRADA" and "se cierra sola" in ult["BRENT"]["nota"]
n = len(filas())
I.aplicar_revisadas(T, t("2026-11-04"), [], [])
assert len(filas()) == n, "idempotente"
# 7) una CERRADA no oculta una discrepancia nueva con la misma clave
ab, c, rv = I.aplicar_revisadas(T, t("2026-11-10"), [brent(per="2026-11-09")], cal)
assert len(ab) == 1 and len(c) == 1, "tras cerrarse, una discrepancia nueva cuenta de nuevo hasta que se revise"
# 8) solo añadir
ids = [r["id"] for r in filas()]
assert len(ids) == len(set(ids))
print("3-8) OK Brent se reabre solo con > 25 % o signo invertido (24,9 % no); se cierra sola al desaparecer (Brent < 10 %, JOLTS publicado); idempotente; solo añadir")
shutil.rmtree(T, ignore_errors=True)
print("\nTODO OK")
