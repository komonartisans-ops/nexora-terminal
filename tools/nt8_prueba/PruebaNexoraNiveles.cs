// Arnés de prueba de la LÓGICA de NexoraNiveles.cs (NexoraNivelesLogica): se compila con csc junto a NexoraNiveles.cs y tools/stubs_ninjatrader.cs y lo maneja
// tools/prueba_niveles_nt8.py por la entrada estándar. No es NinjaTrader: prueba el mismo código C# que luego compila NinjaTrader 8.
// Órdenes (una por línea, campos separados por «;»; la respuesta es una línea por orden):
//   ULTIMA;<AAAA-MM-DDTHH:MM utc>;<gracia h>                      → AAAA-MM-DD
//   EVALUAR;<archivo json>;<clave>;<AAAA-MM-DDTHH:MM utc>;<gracia> → CAD=0|1;FECHA=dd-MM;SPOT=0|1
//   SELECCIONAR;<archivo json>;<clave>;<precio>;<modo>;<max>;<ancho em> → etiqueta@precio@ambar|gris … (vacío si ninguna)
//   FESTIVO;<AAAA-MM-DD>                                           → 0|1
//   NY;<AAAA-MM-DDTHH:MM utc>                                      → hora de Nueva York AAAA-MM-DDTHH:MM
//   CLAVE;<nombre del instrumento>                                 → clave o «-»
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using NinjaTrader.NinjaScript.Indicators;

public static class PruebaNexoraNiveles
{
    private static DateTime Utc(string s)
    {
        return DateTime.ParseExact(s, "yyyy-MM-ddTHH:mm", CultureInfo.InvariantCulture, DateTimeStyles.None);
    }

    private static double D(string s)
    {
        return double.Parse(s, CultureInfo.InvariantCulture);
    }

    private static string Responder(string linea)
    {
        string[] p = linea.Split(';');
        switch (p[0])
        {
            case "ULTIMA":
                return NexoraNivelesLogica.UltimaSesion(Utc(p[1]), D(p[2])).ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
            case "FESTIVO":
                return NexoraNivelesLogica.EsFestivoNYSE(DateTime.ParseExact(p[1], "yyyy-MM-dd", CultureInfo.InvariantCulture)) ? "1" : "0";
            case "NY":
                return NexoraNivelesLogica.ANuevaYork(Utc(p[1])).ToString("yyyy-MM-ddTHH:mm", CultureInfo.InvariantCulture);
            case "CLAVE":
                return NexoraNivelesLogica.ClaveDeInstrumento(p[1]) ?? "-";
            case "EVALUAR":
            {
                NexoraNivelesLectura l = NexoraNivelesLogica.Leer(File.ReadAllText(p[1], Encoding.UTF8));
                NexoraNivelesInstrumento n = NexoraNivelesLogica.Buscar(l, p[2]);
                if (n == null)
                    return "SIN_INSTRUMENTO";
                NexoraNivelesEstado e = NexoraNivelesLogica.Evaluar(n, Utc(p[3]), D(p[4]));
                return "CAD=" + (e.Caducado ? "1" : "0") + ";FECHA=" + e.FechaTexto + ";SPOT=" + (e.SpotDudoso ? "1" : "0");
            }
            case "SELECCIONAR":
            {
                NexoraNivelesLectura l = NexoraNivelesLogica.Leer(File.ReadAllText(p[1], Encoding.UTF8));
                NexoraNivelesInstrumento n = NexoraNivelesLogica.Buscar(l, p[2]);
                NexoraModoDibujo modo = (NexoraModoDibujo)Enum.Parse(typeof(NexoraModoDibujo), p[4]);
                double precio = p[3] == "NaN" ? double.NaN : D(p[3]);
                List<NexoraNivelesLinea> r = NexoraNivelesLogica.Seleccionar(n, precio, modo, int.Parse(p[5]), D(p[6]));
                List<string> o = new List<string>();
                foreach (NexoraNivelesLinea x in r)
                    o.Add(x.Etiqueta + "@" + x.Precio.ToString("0.0", CultureInfo.InvariantCulture) + "@" + (x.Ambar ? "ambar" : "gris"));
                return string.Join("|", o.ToArray());
            }
        }
        return "ORDEN_DESCONOCIDA";
    }

    public static int Main()
    {
        Console.OutputEncoding = new UTF8Encoding(false);
        Console.InputEncoding = new UTF8Encoding(false);
        string linea;
        while ((linea = Console.In.ReadLine()) != null)
        {
            if (linea.Length == 0)
                continue;
            try
            {
                Console.Out.WriteLine(Responder(linea));
            }
            catch (Exception e)
            {
                Console.Out.WriteLine("ERROR " + e.GetType().Name + ": " + e.Message);
            }
        }
        return 0;
    }
}
