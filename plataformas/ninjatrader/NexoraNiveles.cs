// NEXORA · NexoraNiveles (NinjaTrader 8). Indicador de CONTEXTO, no de entradas.
// Descarga https://komonartisans-ops.github.io/nexora-terminal/data/niveles_nt8.json (sin claves; lo genera el cierre de NEXORA) cada 15 minutos y dibuja, en gráficos de
// GC, ES, NQ, YM y sus micros (MGC, MES, MNQ, MYM), el Gamma Flip, el Call Wall, el Put Wall y el Max Gamma (pin / acelera) en PRECIO DE FUTURO.
// Líneas finas discontinuas en gris claro y ámbar, con una etiqueta pequeña a la derecha («CW 4144 · pin»). Si los niveles no son de la última sesión de mercado
// (o el spot del oro es dudoso) las líneas pasan a gris oscuro y aparece «CADUCADO dd-mm» (rojo) o «SPOT DUDOSO» (ámbar).
// Compatible con NinjaTrader 8.0.28 y con MZpack 3.18.8: no usa colores del Volume Profile de MZpack (magenta, naranja y azul), no calcula nada pesado en OnBarUpdate
// (la descarga va en un hilo aparte y el dibujo solo se rehace cuando algo cambia) y no depende de librerías externas (lector de JSON propio, C# 5).
// La lógica (calendario de sesiones, caducidad, selección de niveles) está en la clase NexoraNivelesLogica, sin dependencias de NinjaTrader, para poder probarla fuera de él.
#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.Net;
using System.Text;
using System.Threading;
using System.Windows;
using System.Windows.Media;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    // ------------------------------------------------------------------ opciones visibles en la ventana de parámetros
    public enum NexoraModoDibujo
    {
        Cercanos,        // niveles dentro de ±N × EM del precio, los más cercanos, máximo M (por defecto N = 1, M = 3)
        Todos,           // los cuatro niveles
        SoloMasCercano   // solo el más cercano por encima y el más cercano por debajo del precio (para el gráfico de 1 min)
    }

    public enum NexoraPosicionAviso { ArribaIzquierda, ArribaDerecha, AbajoIzquierda, AbajoDerecha }

    // ------------------------------------------------------------------ datos
    public class NexoraNivelesInstrumento
    {
        public string Clave;
        public string Sesion;           // «AAAA-MM-DD» de la cadena de opciones de la que salen los niveles
        public string Regimen;
        public double Flip = double.NaN;
        public double CallWall = double.NaN;
        public double PutWall = double.NaN;
        public double MaxGamma = double.NaN;
        public string MaxGammaTipo;     // «pin» | «acelera» | null
        public double Em = double.NaN;
        public string SpotEstado;       // «verificado» | «dudoso» | «no_verificado»
        public string GeneradoUtc;
    }

    public class NexoraNivelesLectura
    {
        public Dictionary<string, NexoraNivelesInstrumento> Instrumentos = new Dictionary<string, NexoraNivelesInstrumento>();
        public string GeneradoUtc;
    }

    public class NexoraNivelesLinea
    {
        public string Etiqueta;         // «CW 4144 · pin»
        public double Precio;
        public bool Ambar;              // true = ámbar (Gamma Flip / Max Gamma); false = gris claro (muros)
    }

    public class NexoraNivelesEstado
    {
        public bool Caducado;
        public string FechaTexto;       // «dd-mm» de la sesión de los niveles, o «sin fecha»
        public bool SpotDudoso;
    }

    // ------------------------------------------------------------------ lógica pura (sin NinjaTrader)
    public static class NexoraNivelesLogica
    {
        public const double GraciaPorDefecto = 5.0;     // horas tras el cierre de las 16:00 ET en que el cierre de NEXORA aún puede estar publicando la sesión nueva

        // «GC», «MGC», «ES», … → clave del JSON (mayúsculas); null si no es un instrumento admitido
        public static string ClaveDeInstrumento(string nombre)
        {
            if (string.IsNullOrEmpty(nombre))
                return null;
            string n = nombre.Trim().ToUpperInvariant();
            int esp = n.IndexOf(' ');
            if (esp > 0)
                n = n.Substring(0, esp);                // «GC 12-26» → «GC»
            switch (n)
            {
                case "GC": case "MGC": case "ES": case "MES": case "NQ": case "MNQ": case "YM": case "MYM":
                    return n;
            }
            return null;
        }

        private static string RaizDeMicro(string clave)
        {
            switch (clave)
            {
                case "MGC": return "GC";
                case "MES": return "ES";
                case "MNQ": return "NQ";
                case "MYM": return "YM";
            }
            return null;
        }

        // el instrumento del JSON; si el JSON no trae el micro, usa el contrato grande (mismos niveles)
        public static NexoraNivelesInstrumento Buscar(NexoraNivelesLectura l, string clave)
        {
            NexoraNivelesInstrumento n;
            if (l == null || clave == null)
                return null;
            if (l.Instrumentos.TryGetValue(clave, out n))
                return n;
            string raiz = RaizDeMicro(clave);
            if (raiz != null && l.Instrumentos.TryGetValue(raiz, out n))
                return n;
            return null;
        }

        // ------------------------------------------------------------------ calendario de sesiones de la NYSE
        private static DateTime NesimoDomingo(int anio, int mes, int n)
        {
            DateTime d = new DateTime(anio, mes, 1);
            while (d.DayOfWeek != DayOfWeek.Sunday)
                d = d.AddDays(1);
            return d.AddDays(7 * (n - 1));
        }

        private static DateTime NesimoDia(int anio, int mes, DayOfWeek dia, int n)
        {
            DateTime d = new DateTime(anio, mes, 1);
            while (d.DayOfWeek != dia)
                d = d.AddDays(1);
            return d.AddDays(7 * (n - 1));
        }

        private static DateTime UltimoLunes(int anio, int mes)
        {
            DateTime d = new DateTime(anio, mes, DateTime.DaysInMonth(anio, mes));
            while (d.DayOfWeek != DayOfWeek.Monday)
                d = d.AddDays(-1);
            return d;
        }

        private static DateTime Pascua(int y)
        {
            int a = y % 19, b = y / 100, c = y % 100, d = b / 4, e = b % 4, f = (b + 8) / 25, g = (b - f + 1) / 3;
            int h = (19 * a + b - d - g + 15) % 30, i = c / 4, k = c % 4, l = (32 + 2 * e + 2 * i - h - k) % 7, m = (a + 11 * h + 22 * l) / 451;
            int mes = (h + l - 7 * m + 114) / 31, dia = ((h + l - 7 * m + 114) % 31) + 1;
            return new DateTime(y, mes, dia);
        }

        // festivo de fecha fija: si cae en sábado se observa el viernes (salvo el Año Nuevo, que no se traslada) y si cae en domingo, el lunes
        private static bool FijoObservado(DateTime d, int mes, int dia, bool trasladaSabado)
        {
            DateTime f = new DateTime(d.Year, mes, dia);
            if (f.DayOfWeek == DayOfWeek.Saturday)
                return trasladaSabado && d == f.AddDays(-1);
            if (f.DayOfWeek == DayOfWeek.Sunday)
                return d == f.AddDays(1);
            return d == f;
        }

        // festivos de la NYSE (los cierres extraordinarios por duelo nacional no se modelan)
        public static bool EsFestivoNYSE(DateTime fecha)
        {
            DateTime d = fecha.Date;
            int y = d.Year;
            if (FijoObservado(d, 1, 1, false) || FijoObservado(d, 7, 4, true) || FijoObservado(d, 12, 25, true))
                return true;
            if (y >= 2022 && FijoObservado(d, 6, 19, true))
                return true;
            return d == NesimoDia(y, 1, DayOfWeek.Monday, 3)          // Martin Luther King
                || d == NesimoDia(y, 2, DayOfWeek.Monday, 3)          // Presidents' Day
                || d == Pascua(y).AddDays(-2)                         // Viernes Santo
                || d == UltimoLunes(y, 5)                             // Memorial Day
                || d == NesimoDia(y, 9, DayOfWeek.Monday, 1)          // Labor Day
                || d == NesimoDia(y, 11, DayOfWeek.Thursday, 4);      // Thanksgiving
        }

        public static bool EsDiaDeSesion(DateTime d)
        {
            return d.DayOfWeek != DayOfWeek.Saturday && d.DayOfWeek != DayOfWeek.Sunday && !EsFestivoNYSE(d);
        }

        // hora de Nueva York (horario de verano de EE. UU.: 2.º domingo de marzo 02:00 hasta 1.er domingo de noviembre 02:00)
        public static DateTime ANuevaYork(DateTime utc)
        {
            DateTime ini = NesimoDomingo(utc.Year, 3, 2).AddHours(7);     // 02:00 EST = 07:00 UTC
            DateTime fin = NesimoDomingo(utc.Year, 11, 1).AddHours(6);    // 02:00 EDT = 06:00 UTC
            return utc.AddHours(utc >= ini && utc < fin ? -4 : -5);
        }

        // la última sesión de mercado: el último día de sesión cuyo cierre (16:00 ET) + gracia ya pasó
        public static DateTime UltimaSesion(DateTime utc, double graciaHoras)
        {
            DateTime ny = ANuevaYork(utc);
            DateTime d = ny.Date;
            if (ny < d.AddHours(16.0 + graciaHoras))
                d = d.AddDays(-1);
            while (!EsDiaDeSesion(d))
                d = d.AddDays(-1);
            return d;
        }

        // ------------------------------------------------------------------ caducidad
        public static NexoraNivelesEstado Evaluar(NexoraNivelesInstrumento n, DateTime utc, double graciaHoras)
        {
            NexoraNivelesEstado e = new NexoraNivelesEstado();
            e.SpotDudoso = n != null && n.SpotEstado == "dudoso";
            DateTime ses;
            if (n == null || string.IsNullOrEmpty(n.Sesion) || !DateTime.TryParseExact(n.Sesion, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out ses))
            {
                e.Caducado = true;
                e.FechaTexto = "sin fecha";
                return e;
            }
            e.FechaTexto = ses.ToString("dd-MM", CultureInfo.InvariantCulture);
            e.Caducado = ses.Date < UltimaSesion(utc, graciaHoras);
            return e;
        }

        // ------------------------------------------------------------------ qué niveles se dibujan
        private class Candidato
        {
            public string Nombre;
            public double Precio;
            public bool Ambar;
            public string Tipo;
        }

        private static string Fmt(double v)
        {
            return v.ToString("0", CultureInfo.InvariantCulture);
        }

        public static List<NexoraNivelesLinea> Seleccionar(NexoraNivelesInstrumento n, double precio, NexoraModoDibujo modo, int maximo, double anchoEm)
        {
            List<Candidato> todos = new List<Candidato>();
            if (n != null)
            {
                if (!double.IsNaN(n.Flip)) todos.Add(new Candidato { Nombre = "FLIP", Precio = n.Flip, Ambar = true });
                if (!double.IsNaN(n.CallWall)) todos.Add(new Candidato { Nombre = "CW", Precio = n.CallWall, Ambar = false });
                if (!double.IsNaN(n.PutWall)) todos.Add(new Candidato { Nombre = "PW", Precio = n.PutWall, Ambar = false });
                if (!double.IsNaN(n.MaxGamma)) todos.Add(new Candidato { Nombre = "MG", Precio = n.MaxGamma, Ambar = true, Tipo = n.MaxGammaTipo });
            }

            // niveles en el mismo precio (p. ej. Put Wall = Max Gamma) → una sola línea con las dos etiquetas, «PW/MG 3774 · acelera»
            List<Candidato> unicos = new List<Candidato>();
            foreach (Candidato c in todos)
            {
                Candidato igual = null;
                foreach (Candidato u in unicos)
                    if (Math.Abs(u.Precio - c.Precio) < 0.05)
                        igual = u;
                if (igual == null)
                {
                    unicos.Add(new Candidato { Nombre = c.Nombre, Precio = c.Precio, Ambar = c.Ambar, Tipo = c.Tipo });
                }
                else
                {
                    igual.Nombre = igual.Nombre + "/" + c.Nombre;
                    igual.Ambar = igual.Ambar || c.Ambar;
                    if (c.Tipo != null)
                        igual.Tipo = c.Tipo;
                }
            }

            List<Candidato> elegidos = new List<Candidato>();
            bool hayPrecio = !double.IsNaN(precio);
            if (modo == NexoraModoDibujo.Todos || !hayPrecio)
            {
                elegidos = unicos;
            }
            else if (modo == NexoraModoDibujo.SoloMasCercano)
            {
                Candidato arriba = null, abajo = null;
                foreach (Candidato c in unicos)
                {
                    if (c.Precio >= precio)
                    {
                        if (arriba == null || c.Precio < arriba.Precio) arriba = c;
                    }
                    else if (abajo == null || c.Precio > abajo.Precio)
                    {
                        abajo = c;
                    }
                }
                if (arriba != null) elegidos.Add(arriba);
                if (abajo != null) elegidos.Add(abajo);
            }
            else
            {
                double lim = (n == null || double.IsNaN(n.Em)) ? double.PositiveInfinity : anchoEm * n.Em;
                foreach (Candidato c in unicos)
                    if (Math.Abs(c.Precio - precio) <= lim)
                        elegidos.Add(c);
                elegidos.Sort(delegate(Candidato a, Candidato b) { return Math.Abs(a.Precio - precio).CompareTo(Math.Abs(b.Precio - precio)); });
                if (elegidos.Count > maximo)
                    elegidos.RemoveRange(maximo, elegidos.Count - maximo);
            }

            List<NexoraNivelesLinea> r = new List<NexoraNivelesLinea>();
            foreach (Candidato c in elegidos)
            {
                NexoraNivelesLinea l = new NexoraNivelesLinea();
                l.Etiqueta = c.Nombre + " " + Fmt(c.Precio) + (string.IsNullOrEmpty(c.Tipo) ? "" : " · " + c.Tipo);
                l.Precio = c.Precio;
                l.Ambar = c.Ambar;
                r.Add(l);
            }
            return r;
        }

        // ------------------------------------------------------------------ lectura del JSON
        public static NexoraNivelesLectura Leer(string texto)
        {
            Dictionary<string, object> raiz = new MiniJson(texto).Leer() as Dictionary<string, object>;
            if (raiz == null)
                throw new FormatException("el archivo no es un objeto JSON");
            Dictionary<string, object> inst = Obj(raiz, "instrumentos");
            if (inst == null)
                throw new FormatException("el archivo no trae «instrumentos»");
            NexoraNivelesLectura l = new NexoraNivelesLectura();
            l.GeneradoUtc = Texto(raiz, "generado_utc");
            foreach (KeyValuePair<string, object> kv in inst)
            {
                Dictionary<string, object> x = kv.Value as Dictionary<string, object>;
                if (x == null)
                    continue;
                NexoraNivelesInstrumento n = new NexoraNivelesInstrumento();
                n.Clave = kv.Key;
                n.Sesion = Texto(x, "sesion");
                n.Regimen = Texto(x, "regimen");
                n.Flip = Num(x, "flip");
                n.CallWall = Num(x, "call_wall");
                n.PutWall = Num(x, "put_wall");
                n.MaxGamma = Num(x, "max_gamma");
                n.MaxGammaTipo = Texto(x, "max_gamma_tipo");
                n.Em = Num(x, "em");
                n.SpotEstado = Texto(x, "spot_estado");
                n.GeneradoUtc = Texto(x, "generado_utc");
                l.Instrumentos[kv.Key] = n;
            }
            return l;
        }

        private static Dictionary<string, object> Obj(Dictionary<string, object> d, string k)
        {
            object o;
            return d.TryGetValue(k, out o) ? o as Dictionary<string, object> : null;
        }

        private static string Texto(Dictionary<string, object> d, string k)
        {
            object o;
            return d.TryGetValue(k, out o) && o is string ? (string)o : null;
        }

        private static double Num(Dictionary<string, object> d, string k)
        {
            object o;
            if (d.TryGetValue(k, out o) && o is double)
                return (double)o;
            return double.NaN;
        }

        // ------------------------------------------------------------------ lector de JSON mínimo (objetos, listas, textos, números, true/false/null)
        private class MiniJson
        {
            private readonly string s;
            private int i;

            public MiniJson(string texto)
            {
                s = texto;
                i = 0;
            }

            public object Leer()
            {
                object v = Valor();
                Espacios();
                return v;
            }

            private void Espacios()
            {
                while (i < s.Length && char.IsWhiteSpace(s[i]))
                    i++;
            }

            private object Valor()
            {
                Espacios();
                if (i >= s.Length)
                    throw new FormatException("JSON incompleto");
                char c = s[i];
                if (c == '{')
                    return Objeto();
                if (c == '[')
                    return Lista();
                if (c == '"')
                    return Cadena();
                if (c == 't' && Coincide("true"))
                    return true;
                if (c == 'f' && Coincide("false"))
                    return false;
                if (c == 'n' && Coincide("null"))
                    return null;
                if (c == 'N' && Coincide("NaN"))
                    return double.NaN;
                return Numero();
            }

            private bool Coincide(string palabra)
            {
                if (string.CompareOrdinal(s, i, palabra, 0, palabra.Length) == 0)
                {
                    i += palabra.Length;
                    return true;
                }
                return false;
            }

            private Dictionary<string, object> Objeto()
            {
                Dictionary<string, object> d = new Dictionary<string, object>();
                i++;
                Espacios();
                if (i < s.Length && s[i] == '}')
                {
                    i++;
                    return d;
                }
                while (true)
                {
                    Espacios();
                    string k = Cadena();
                    Espacios();
                    if (i >= s.Length || s[i] != ':')
                        throw new FormatException("se esperaba ':' en la posición " + i);
                    i++;
                    d[k] = Valor();
                    Espacios();
                    if (i < s.Length && s[i] == ',')
                    {
                        i++;
                        continue;
                    }
                    if (i < s.Length && s[i] == '}')
                    {
                        i++;
                        return d;
                    }
                    throw new FormatException("objeto mal formado en la posición " + i);
                }
            }

            private List<object> Lista()
            {
                List<object> l = new List<object>();
                i++;
                Espacios();
                if (i < s.Length && s[i] == ']')
                {
                    i++;
                    return l;
                }
                while (true)
                {
                    l.Add(Valor());
                    Espacios();
                    if (i < s.Length && s[i] == ',')
                    {
                        i++;
                        continue;
                    }
                    if (i < s.Length && s[i] == ']')
                    {
                        i++;
                        return l;
                    }
                    throw new FormatException("lista mal formada en la posición " + i);
                }
            }

            private string Cadena()
            {
                if (i >= s.Length || s[i] != '"')
                    throw new FormatException("se esperaba un texto en la posición " + i);
                i++;
                StringBuilder sb = new StringBuilder();
                while (i < s.Length)
                {
                    char c = s[i++];
                    if (c == '"')
                        return sb.ToString();
                    if (c == '\\' && i < s.Length)
                    {
                        char e = s[i++];
                        switch (e)
                        {
                            case 'n': sb.Append('\n'); break;
                            case 't': sb.Append('\t'); break;
                            case 'r': sb.Append('\r'); break;
                            case 'b': sb.Append('\b'); break;
                            case 'f': sb.Append('\f'); break;
                            case 'u':
                                if (i + 4 > s.Length)
                                    throw new FormatException("escape \\u incompleto");
                                sb.Append((char)int.Parse(s.Substring(i, 4), NumberStyles.HexNumber, CultureInfo.InvariantCulture));
                                i += 4;
                                break;
                            default: sb.Append(e); break;
                        }
                    }
                    else
                    {
                        sb.Append(c);
                    }
                }
                throw new FormatException("texto sin cerrar");
            }

            private double Numero()
            {
                int ini = i;
                while (i < s.Length && ("+-0123456789.eE".IndexOf(s[i]) >= 0))
                    i++;
                double v;
                if (i == ini || !double.TryParse(s.Substring(ini, i - ini), NumberStyles.Float, CultureInfo.InvariantCulture, out v))
                    throw new FormatException("número inválido en la posición " + ini);
                return v;
            }
        }
    }

    // ------------------------------------------------------------------ el indicador
    public class NexoraNiveles : Indicator
    {
        private class Resultado
        {
            public NexoraNivelesLectura Lectura;
            public string Error;
            public DateTime Hora;
        }

        // descarga con límite de tiempo (WebClient no lo trae)
        private class WebClientConLimite : WebClient
        {
            protected override WebRequest GetWebRequest(Uri direccion)
            {
                WebRequest r = base.GetWebRequest(direccion);
                if (r != null)
                    r.Timeout = 12000;
                return r;
            }
        }

        private readonly object candado = new object();
        private Timer temporizador;
        private bool descargando;
        private bool terminado;
        private NexoraNivelesLectura actual;
        private DateTime horaLecturaOk = DateTime.MinValue;
        private string ultimoError;
        private DateTime horaError = DateTime.MinValue;
        private string clave;
        private double ultimoPrecio = double.NaN;
        private string ultimaFirma = "";
        private int lineasPintadas;
        private Brush brAmbar, brGrisClaro, brGrisOscuro, brRojo, brInfo;
        private SimpleFont fuenteEtiqueta, fuenteAviso, fuenteInfo;
        private const int MaxLineas = 4;

        // ------------------------------------------------------------------ parámetros
        [NinjaScriptProperty]
        [Display(Name = "URL de niveles_nt8.json", Description = "Archivo público que publica NEXORA (sin claves)", GroupName = "NEXORA", Order = 1)]
        public string UrlNiveles { get; set; }

        [NinjaScriptProperty]
        [Range(1, 240)]
        [Display(Name = "Minutos entre lecturas", Description = "Cada cuántos minutos se vuelve a descargar el archivo (los niveles cambian una vez al día)", GroupName = "NEXORA", Order = 2)]
        public int MinutosRefresco { get; set; }

        [NinjaScriptProperty]
        [Range(0, 7)]
        [Display(Name = "Horas de gracia tras el cierre", Description = "Horas después de las 16:00 (Nueva York) antes de exigir los niveles de la sesión nueva (el cierre de NEXORA tarda en publicar)", GroupName = "NEXORA", Order = 3)]
        public int HorasGracia { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Modo de dibujo", Description = "Cercanos = niveles dentro de ±1 EM del precio (máx. 3) · Todos = los 4 niveles · SoloMasCercano = el más cercano por encima y por debajo (para 1 min)", GroupName = "Dibujo", Order = 1)]
        public NexoraModoDibujo Modo { get; set; }

        [NinjaScriptProperty]
        [Range(1, 4)]
        [Display(Name = "Máximo de niveles (modo Cercanos)", GroupName = "Dibujo", Order = 2)]
        public int MaximoCercanos { get; set; }

        [NinjaScriptProperty]
        [Range(0.25, 5.0)]
        [Display(Name = "Distancia máxima en EM (modo Cercanos)", Description = "1 = niveles a menos de 1 movimiento esperado del precio", GroupName = "Dibujo", Order = 3)]
        public double AnchoEm { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Mostrar texto de estado", GroupName = "Dibujo", Order = 4)]
        public bool MostrarEstado { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Posición del aviso", GroupName = "Dibujo", Order = 5)]
        public NexoraPosicionAviso PosicionAviso { get; set; }

        // ------------------------------------------------------------------ ciclo de vida
        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "NEXORA: Gamma Flip, Call Wall, Put Wall y Max Gamma de GC, ES, NQ, YM y micros, en precio de futuro, con aviso de caducidad (contexto, no entradas).";
                Name = "NexoraNiveles";
                Calculate = Calculate.OnBarClose;
                IsOverlay = true;
                DisplayInDataBox = false;
                PaintPriceMarkers = false;
                IsSuspendedWhileInactive = true;
                UrlNiveles = "https://komonartisans-ops.github.io/nexora-terminal/data/niveles_nt8.json";
                MinutosRefresco = 15;
                HorasGracia = 5;
                Modo = NexoraModoDibujo.Cercanos;
                MaximoCercanos = 3;
                AnchoEm = 1.0;
                MostrarEstado = true;
                PosicionAviso = NexoraPosicionAviso.ArribaIzquierda;
            }
            else if (State == State.Configure)
            {
                try
                {
                    // GitHub Pages exige TLS 1.2 (valor 3072); el .NET 4.x de NinjaTrader 8 puede no activarlo por defecto.
                    ServicePointManager.SecurityProtocol = ServicePointManager.SecurityProtocol | (SecurityProtocolType)3072;
                }
                catch (Exception)
                {
                }
            }
            else if (State == State.DataLoaded)
            {
                clave = NexoraNivelesLogica.ClaveDeInstrumento(Instrument.MasterInstrument.Name);
                brAmbar = Congelado(255, 176, 0);              // ámbar
                brGrisClaro = Congelado(200, 200, 200);        // gris claro
                brGrisOscuro = Congelado(110, 110, 110);       // caducado
                brRojo = Congelado(235, 60, 50);
                brInfo = Congelado(150, 150, 150);
                fuenteEtiqueta = new SimpleFont("Arial", 9);
                fuenteAviso = new SimpleFont("Arial", 14);
                fuenteInfo = new SimpleFont("Arial", 10);
                if (clave != null)
                    temporizador = new Timer(new TimerCallback(Tick), null, 0, MinutosRefresco * 60000);
            }
            else if (State == State.Terminated)
            {
                terminado = true;
                if (temporizador != null)
                {
                    temporizador.Dispose();
                    temporizador = null;
                }
            }
        }

        private static Brush Congelado(byte r, byte g, byte b)
        {
            SolidColorBrush br = new SolidColorBrush(Color.FromRgb(r, g, b));
            br.Freeze();
            return br;
        }

        // ------------------------------------------------------------------ barras: casi no hace nada (la descarga va en otro hilo; el dibujo solo se rehace si cambia algo)
        protected override void OnBarUpdate()
        {
            if (State == State.Historical && CurrentBar < Count - 1)
                return;                                         // en el histórico solo importa la última barra
            if (clave == null)
            {
                Aviso("NexoraNiveles: instrumento no admitido (solo GC, ES, NQ, YM y sus micros)");
                return;
            }
            ultimoPrecio = Close[0];
            Actualizar(false);
        }

        // ------------------------------------------------------------------ descarga (hilo del temporizador, nunca bloquea el gráfico)
        private void Tick(object estado)
        {
            lock (candado)
            {
                if (descargando || terminado)
                    return;
                descargando = true;
            }
            Resultado r = new Resultado();
            r.Hora = DateTime.Now;
            try
            {
                string url = UrlNiveles + (UrlNiveles.Contains("?") ? "&" : "?") + "t=" + DateTime.UtcNow.Ticks.ToString(CultureInfo.InvariantCulture);
                string texto;
                using (WebClient wc = new WebClientConLimite())
                {
                    wc.Encoding = Encoding.UTF8;
                    wc.Headers.Add("User-Agent", "NexoraNiveles/1.0");
                    texto = wc.DownloadString(url);
                }
                r.Lectura = NexoraNivelesLogica.Leer(texto);
            }
            catch (Exception e)
            {
                r.Error = e.GetType().Name + ": " + e.Message;
                Print("NexoraNiveles: no se pudo leer niveles_nt8.json (" + r.Error + "). Se conserva la última lectura buena.");
            }
            lock (candado)
            {
                descargando = false;
            }
            if (terminado)
                return;
            try
            {
                TriggerCustomEvent(new Action<object>(Aplicar), r);     // vuelve al hilo de NinjaScript para tocar el gráfico
            }
            catch (Exception)
            {
            }
        }

        private void Aplicar(object estado)
        {
            if (terminado || State == State.Terminated)
                return;
            Resultado r = (Resultado)estado;
            if (r.Error == null)
            {
                actual = r.Lectura;
                horaLecturaOk = r.Hora;
                ultimoError = null;
            }
            else
            {
                ultimoError = r.Error;                          // la lectura buena anterior (si la hay) se conserva
                horaError = r.Hora;
            }
            Actualizar(true);
        }

        // ------------------------------------------------------------------ dibujo (solo si algo ha cambiado)
        private void Actualizar(bool forzar)
        {
            if (clave == null || State < State.Historical)
                return;
            if (actual == null)
            {
                Aviso(ultimoError == null ? "NexoraNiveles: leyendo niveles_nt8.json…" : "NexoraNiveles: sin lectura todavía (" + ultimoError + ")");
                return;
            }
            NexoraNivelesInstrumento n = NexoraNivelesLogica.Buscar(actual, clave);
            if (n == null)
            {
                Aviso("NexoraNiveles: el archivo no trae niveles de " + clave + " (SIN DATO)");
                return;
            }
            if (double.IsNaN(ultimoPrecio))
                return;                                         // aún no ha pasado ninguna barra por OnBarUpdate

            NexoraNivelesEstado est = NexoraNivelesLogica.Evaluar(n, DateTime.UtcNow, HorasGracia);
            List<NexoraNivelesLinea> lineas = NexoraNivelesLogica.Seleccionar(n, ultimoPrecio, Modo, MaximoCercanos, AnchoEm);

            StringBuilder f = new StringBuilder();
            f.Append(CurrentBar).Append('|').Append(est.Caducado).Append(est.SpotDudoso).Append(est.FechaTexto).Append(ultimoError != null).Append(n.Regimen);
            foreach (NexoraNivelesLinea l in lineas)
                f.Append('|').Append(l.Etiqueta);
            string firma = f.ToString();
            if (!forzar && firma == ultimaFirma)
                return;
            ultimaFirma = firma;

            // líneas y etiquetas: finas, discontinuas; gris oscuro si están caducadas o el spot es dudoso
            bool apagado = est.Caducado || est.SpotDudoso;
            for (int k = 0; k < lineas.Count && k < MaxLineas; k++)
            {
                NexoraNivelesLinea l = lineas[k];
                Brush color = apagado ? brGrisOscuro : (l.Ambar ? brAmbar : brGrisClaro);
                Draw.HorizontalLine(this, "NexNivL" + k, l.Precio, color, DashStyleHelper.Dash, 1);
                string txt = new string(' ', 2 * l.Etiqueta.Length + 4) + l.Etiqueta;       // el texto se centra en la última barra: el relleno lo empuja hacia el margen derecho
                Draw.Text(this, "NexNivT" + k, false, txt, 0, l.Precio, -9, color, fuenteEtiqueta, TextAlignment.Left, Brushes.Transparent, Brushes.Transparent, 0);
            }
            for (int k = lineas.Count; k < lineasPintadas; k++)
            {
                RemoveDrawObject("NexNivL" + k);
                RemoveDrawObject("NexNivT" + k);
            }
            lineasPintadas = Math.Min(lineas.Count, MaxLineas);

            // textos de estado: rojo = caducado, ámbar = spot dudoso (en la esquina contraria), gris = todo en orden
            if (est.Caducado)
            {
                Texto("NexNivAviso", "CADUCADO " + est.FechaTexto, brRojo, fuenteAviso, PosicionAviso);
            }
            else if (est.SpotDudoso)
            {
                Texto("NexNivAviso", "SPOT DUDOSO", brAmbar, fuenteAviso, PosicionAviso);
            }
            else if (MostrarEstado)
            {
                Texto("NexNivAviso", "NEXORA " + clave + " · niveles de la sesión " + est.FechaTexto + " · " + lineas.Count + " en pantalla" + (string.IsNullOrEmpty(n.Regimen) ? "" : " · gamma " + n.Regimen.ToLowerInvariant()), brInfo, fuenteInfo, PosicionAviso);
            }
            else
            {
                RemoveDrawObject("NexNivAviso");
            }
            if (est.Caducado && est.SpotDudoso)
                Texto("NexNivAviso2", "SPOT DUDOSO", brAmbar, fuenteAviso, VerticalContraria(PosicionAviso));
            else
                RemoveDrawObject("NexNivAviso2");
            if (ultimoError != null)
                Texto("NexNivFallo", "lectura fallida" + (horaLecturaOk == DateTime.MinValue ? "" : ": se usa la de las " + horaLecturaOk.ToString("HH:mm", CultureInfo.InvariantCulture)), brAmbar, fuenteInfo, HorizontalContraria(PosicionAviso));
            else
                RemoveDrawObject("NexNivFallo");
        }

        private void Aviso(string texto)
        {
            Texto("NexNivAviso", texto, brInfo, fuenteInfo, PosicionAviso);
        }

        private void Texto(string tag, string texto, Brush color, SimpleFont fuente, NexoraPosicionAviso donde)
        {
            if (color == null)
                color = Brushes.Gray;                           // todavía no se han creado los pinceles (antes de DataLoaded)
            Draw.TextFixed(this, tag, texto, Posicion(donde), color, fuente ?? new SimpleFont("Arial", 10), Brushes.Transparent, Brushes.Transparent, 0);
        }

        private static TextPosition Posicion(NexoraPosicionAviso p)
        {
            switch (p)
            {
                case NexoraPosicionAviso.ArribaDerecha: return TextPosition.TopRight;
                case NexoraPosicionAviso.AbajoIzquierda: return TextPosition.BottomLeft;
                case NexoraPosicionAviso.AbajoDerecha: return TextPosition.BottomRight;
            }
            return TextPosition.TopLeft;
        }

        private static NexoraPosicionAviso VerticalContraria(NexoraPosicionAviso p)
        {
            switch (p)
            {
                case NexoraPosicionAviso.ArribaIzquierda: return NexoraPosicionAviso.AbajoIzquierda;
                case NexoraPosicionAviso.ArribaDerecha: return NexoraPosicionAviso.AbajoDerecha;
                case NexoraPosicionAviso.AbajoIzquierda: return NexoraPosicionAviso.ArribaIzquierda;
            }
            return NexoraPosicionAviso.ArribaDerecha;
        }

        private static NexoraPosicionAviso HorizontalContraria(NexoraPosicionAviso p)
        {
            switch (p)
            {
                case NexoraPosicionAviso.ArribaIzquierda: return NexoraPosicionAviso.ArribaDerecha;
                case NexoraPosicionAviso.ArribaDerecha: return NexoraPosicionAviso.ArribaIzquierda;
                case NexoraPosicionAviso.AbajoIzquierda: return NexoraPosicionAviso.AbajoDerecha;
            }
            return NexoraPosicionAviso.AbajoIzquierda;
        }
    }
}
