#!/usr/bin/env python3
"""Valida NexoraGex.cs: (1) sintaxis con tree-sitter (modo C#), (2) compilación con el compilador C# 5 de .NET Framework 4 (el mismo nivel de lenguaje que NinjaTrader 8) contra una
declaración mínima de la API de NinjaTrader (tools/stubs_ninjatrader.cs). NO sustituye a compilar dentro de NinjaTrader 8.
Uso:  python tools/validar_csharp.py [ruta.cs]"""
import glob
import os
import subprocess
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FUENTE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(RAIZ, "plataformas", "ninjatrader", "NexoraGex.cs")


def sintaxis(ruta):
    import tree_sitter_c_sharp as ts_cs
    from tree_sitter import Language, Parser
    parser = Parser(Language(ts_cs.language()))
    datos = open(ruta, "rb").read()
    arbol = parser.parse(datos)
    malos = []

    def rec(n):
        if n.type == "ERROR" or n.is_missing:
            malos.append((n.start_point[0] + 1, n.start_point[1] + 1, "faltante" if n.is_missing else "error", datos[n.start_byte:n.end_byte][:40]))
        for h in n.children:
            rec(h)
    rec(arbol.root_node)
    return malos


def csc():
    for p in glob.glob(r"C:\Windows\Microsoft.NET\Framework64\v4.*\csc.exe") + glob.glob(r"C:\Windows\Microsoft.NET\Framework\v4.*\csc.exe"):
        return p
    return None


def compilar(ruta):
    exe = csc()
    if not exe:
        return None, "no hay compilador csc.exe de .NET Framework 4 en este equipo"
    fw = os.path.dirname(exe)
    wpf = os.path.join(fw, "WPF")
    refs = ["System.dll", "System.Core.dll", "System.ComponentModel.DataAnnotations.dll"] + [os.path.join(wpf, d) for d in ("PresentationCore.dll", "WindowsBase.dll")]
    salida = os.path.join(tempfile.mkdtemp(prefix="csc_"), "NexoraGex.dll")
    cmd = [exe, "/nologo", "/target:library", "/warn:4", f"/out:{salida}"] + [f"/r:{r}" for r in refs] + [ruta, os.path.join(RAIZ, "tools", "stubs_ninjatrader.cs")]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="cp850", errors="replace")
    return r.returncode, (r.stdout + r.stderr).strip()


if __name__ == "__main__":
    malos = sintaxis(FUENTE)
    print("tree-sitter C#:", "SIN ERRORES DE SINTAXIS" if not malos else f"{len(malos)} problema(s): {malos[:5]}")
    rc, txt = compilar(FUENTE)
    if rc is None:
        print("csc:", txt)
    else:
        print("csc (C# 5, .NET Framework 4):", "COMPILA SIN ERRORES" if rc == 0 else "ERRORES")
        if txt:
            print(txt)
    sys.exit(0 if not malos and rc == 0 else 1)
