"""Comprueba que toda cifra de probabilidad de la Fed que aparece en site/data/*.json coincide con fedwatch.json (misma cifra, misma hora).
Uso: python tools/coherencia_fed.py [site/data]   → código de salida 1 si algún bloque cita otra cifra."""
import glob, json, os, re, sys
D = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site", "data")
F = json.load(open(os.path.join(D, "fedwatch.json"), encoding="utf-8"))
r0 = F["reuniones"][0]
esperado = str(round(r0["prob_reunion"]["subida"]))
mal = []
for f in sorted(glob.glob(os.path.join(D, "*.json"))):
    if os.path.basename(f) in ("fedwatch.json", "alertas.json", "tesis.json", "reacciones.json"):
        continue
    t = open(f, encoding="utf-8").read()
    for m in re.finditer(rf"{r0['reunion']}[^\"]{{0,45}}?subida (\d+) ?%|Fed [^\"]{{3,12}}: hoy (\d+) % de subida", t):
        v = m.group(1) or m.group(2)
        if v != esperado:
            mal.append((os.path.basename(f), v))
print(f"fedwatch.json ({F['generado_utc']}): subida {esperado} % en {r0['reunion']}")
print("incoherencias:", mal or "ninguna")
sys.exit(1 if mal else 0)
