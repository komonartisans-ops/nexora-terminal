#!/usr/bin/env python3
"""Diagnóstico MANUAL (solo lectura): ¿responden desde GitHub Actions las fuentes de petróleo que se bloquean en local? Imprime estado HTTP, tamaño y enlaces de descarga.
No escribe datos ni envía nada."""
import re
import sys
import urllib.request

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "text/html,application/xhtml+xml,*/*", "Accept-Language": "en-US,en;q=0.9"}
URLS = ["https://rigcount.bakerhughes.com/na-rig-count", "https://rigcount.bakerhughes.com/", "https://www.opec.org/opec_web/en/press_room/calendar.htm",
        "https://www.opec.org/", "https://www.eia.gov/petroleum/supply/weekly/schedule.php", "https://ir.eia.gov/wpsr/table1.csv",
        "https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=PET&s=WCESTUS1&f=W", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=WCESTUS1&cosd=2026-09-01"]
for u in URLS:
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=40)
        b = r.read().decode("utf-8", "replace")
        print(f"OK  {r.status} {len(b):>7} {u}")
        for m in re.findall(r'href="([^"]*(?:xlsx|xlsb|xls|csv|static-files)[^"]*)"', b)[:8]:
            print("      enlace:", m)
        txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", b))
        if "rigcount" in u:
            i = txt.lower().find("oil")
            print("      texto:", txt[max(0, i - 100):i + 500])
        if "opec.org/opec_web" in u:
            print("      texto:", txt[:500])
    except Exception as e:  # noqa: BLE001
        print(f"ERR {type(e).__name__} {str(e)[:90]} {u}")
sys.exit(0)
