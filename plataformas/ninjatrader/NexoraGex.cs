// NEXORA · NexoraGex (NinjaTrader 8). Indicador de CONTEXTO, no de entradas.
// Lee https://komonartisans-ops.github.io/nexora-terminal/data/gamma.json cada 15 minutos y dibuja, en gráficos de ES/MES y NQ/MNQ:
//   Gamma Flip, Call Wall, Put Wall, Max Gamma y la banda del movimiento esperado (EM), con una etiqueta de régimen.
// Los niveles son precios de FUTURO calculados por NEXORA (CRITERIO NEXORA, método propio) con la cadena de opciones de Cboe (15 min de retraso) del cierre anterior.
// No depende de librerías externas: incluye su propio lector de JSON. Compatible con C# 5 (el compilador de NinjaTrader 8).
#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.Net;
using System.Text;
using System.Threading;
using System.Windows.Media;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    public class NexoraGex : Indicator
    {
        // ------------------------------------------------------------------ datos de un índice (ES o NQ)
        private class Niveles
        {
            public string Indice;
            public string Sesion;
            public string RegimenCierre;
            public double Flip = double.NaN;
            public double CallWall = double.NaN;
            public double PutWall = double.NaN;
            public double MaxGamma = double.NaN;
            public double Em = double.NaN;
            public double SpotFut = double.NaN;
        }

        private class Descarga
        {
            public Dictionary<string, Niveles> Indices = new Dictionary<string, Niveles>();
            public string GeneradoUtc;
            public string Error;
            public DateTime Hora;
        }

        private readonly object candado = new object();
        private Descarga pendiente;
        private Descarga actual;
        private bool descargando;
        private DateTime ultimoIntento = DateTime.MinValue;
        private int ultimaBarraDibujada = -1;
        private bool hayCambio;
        private string raizIndice;

        // ------------------------------------------------------------------ parámetros
        [NinjaScriptProperty]
        [Display(Name = "URL de gamma.json", Description = "Archivo que publica NEXORA", GroupName = "NEXORA", Order = 1)]
        public string UrlGamma { get; set; }

        [NinjaScriptProperty]
        [Range(1, 240)]
        [Display(Name = "Minutos entre lecturas", Description = "Cada cuántos minutos se vuelve a leer el archivo", GroupName = "NEXORA", Order = 2)]
        public int MinutosRefresco { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Mostrar Max Gamma", GroupName = "Niveles", Order = 1)]
        public bool MostrarMaxGamma { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Mostrar banda EM", Description = "Banda del movimiento esperado de un día alrededor del precio de referencia", GroupName = "Niveles", Order = 2)]
        public bool MostrarBandaEm { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Mostrar etiqueta de régimen", GroupName = "Niveles", Order = 3)]
        public bool MostrarEtiqueta { get; set; }

        [NinjaScriptProperty]
        [Range(1, 6)]
        [Display(Name = "Grosor de las líneas", GroupName = "Niveles", Order = 4)]
        public int Grosor { get; set; }

        [NinjaScriptProperty]
        [Range(6, 240)]
        [Display(Name = "Horas hasta marcar «datos antiguos»", GroupName = "NEXORA", Order = 3)]
        public int HorasAntiguo { get; set; }

        // ------------------------------------------------------------------ ciclo de vida
        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "NEXORA: Gamma Flip, Call Wall, Put Wall, Max Gamma y banda EM de ES/NQ (contexto, no entradas).";
                Name = "NexoraGex";
                Calculate = Calculate.OnEachTick;
                IsOverlay = true;
                DisplayInDataBox = false;
                PaintPriceMarkers = false;
                IsSuspendedWhileInactive = true;
                UrlGamma = "https://komonartisans-ops.github.io/nexora-terminal/data/gamma.json";
                MinutosRefresco = 15;
                MostrarMaxGamma = true;
                MostrarBandaEm = true;
                MostrarEtiqueta = true;
                Grosor = 2;
                HorasAntiguo = 72;
            }
            else if (State == State.Configure)
            {
                try
                {
                    // Los servidores de GitHub Pages exigen TLS 1.2 (valor 3072); .NET 4.x de NinjaTrader 8 puede no activarlo por defecto.
                    ServicePointManager.SecurityProtocol = ServicePointManager.SecurityProtocol | (SecurityProtocolType)3072;
                }
                catch (Exception)
                {
                }
            }
            else if (State == State.DataLoaded)
            {
                raizIndice = RaizDelInstrumento();
            }
        }

        // «ES», «MES» → ES; «NQ», «MNQ» → NQ; cualquier otro → null
        private string RaizDelInstrumento()
        {
            string n = Instrument.MasterInstrument.Name.ToUpperInvariant();
            if (n == "ES" || n == "MES")
                return "ES";
            if (n == "NQ" || n == "MNQ")
                return "NQ";
            return null;
        }

        protected override void OnBarUpdate()
        {
            // solo se actúa en la última barra (histórico y tiempo real): los niveles son del día, no de cada barra
            if (CurrentBar != Count - 1)
                return;

            if (raizIndice == null)
            {
                if (ultimaBarraDibujada != CurrentBar)
                {
                    Draw.TextFixed(this, "nexoraRegimen", "NEXORA GEX: instrumento no admitido (solo ES, MES, NQ y MNQ)", TextPosition.TopLeft);
                    ultimaBarraDibujada = CurrentBar;
                }
                return;
            }

            // 1) ¿toca leer de nuevo?
            if (!descargando && (DateTime.UtcNow - ultimoIntento).TotalMinutes >= MinutosRefresco)
            {
                ultimoIntento = DateTime.UtcNow;
                descargando = true;
                ThreadPool.QueueUserWorkItem(new WaitCallback(Descargar));
            }

            // 2) ¿ha llegado una lectura nueva?
            lock (candado)
            {
                if (pendiente != null)
                {
                    // si la nueva lectura falla pero había una buena, se conserva la buena y se anota el error
                    if (pendiente.Error != null && actual != null && actual.Error == null)
                        actual.Error = pendiente.Error;
                    else
                        actual = pendiente;
                    pendiente = null;
                    hayCambio = true;
                }
            }

            if (actual == null)
            {
                if (ultimaBarraDibujada != -2)
                {
                    Draw.TextFixed(this, "nexoraRegimen", "NEXORA GEX: leyendo gamma.json…", TextPosition.TopLeft);
                    ultimaBarraDibujada = -2;
                }
                return;
            }

            // 3) dibujar (solo si hay datos nuevos o una barra nueva: así no se redibuja en cada tick)
            if (hayCambio || ultimaBarraDibujada != CurrentBar)
            {
                Dibujar();
                hayCambio = false;
                ultimaBarraDibujada = CurrentBar;
            }
        }

        // ------------------------------------------------------------------ descarga en un hilo aparte (nunca bloquea el gráfico)
        private void Descargar(object estado)
        {
            Descarga d = new Descarga();
            d.Hora = DateTime.Now;
            try
            {
                string url = UrlGamma + (UrlGamma.Contains("?") ? "&" : "?") + "t=" + DateTime.UtcNow.Ticks.ToString(CultureInfo.InvariantCulture);
                string texto;
                using (WebClient wc = new WebClient())
                {
                    wc.Encoding = Encoding.UTF8;
                    wc.Headers.Add("User-Agent", "NexoraGex/1.0");
                    texto = wc.DownloadString(url);
                }
                object raiz = new MiniJson(texto).Leer();
                Dictionary<string, object> r = raiz as Dictionary<string, object>;
                if (r == null)
                    throw new Exception("el archivo no es un objeto JSON");
                d.GeneradoUtc = Texto(r, "generado_utc");
                Dictionary<string, object> idx = Obj(r, "indices");
                if (idx == null)
                    throw new Exception("el archivo no trae «indices»");
                foreach (KeyValuePair<string, object> kv in idx)
                {
                    Dictionary<string, object> x = kv.Value as Dictionary<string, object>;
                    if (x == null)
                        continue;
                    Niveles n = new Niveles();
                    n.Indice = kv.Key;
                    n.Sesion = Texto(x, "sesion");
                    n.RegimenCierre = Texto(x, "regimen");
                    n.Flip = Fut(x, "flip");
                    n.CallWall = Fut(x, "call_wall");
                    n.PutWall = Fut(x, "put_wall");
                    n.MaxGamma = Fut(x, "max_gamma");
                    n.SpotFut = Num(x, "spot_fut");
                    Dictionary<string, object> em = Obj(x, "em");
                    n.Em = em == null ? double.NaN : Num(em, "puntos");
                    d.Indices[kv.Key] = n;
                }
            }
            catch (Exception e)
            {
                d.Error = e.GetType().Name + ": " + e.Message;
                Print("NexoraGex: no se pudo leer gamma.json (" + d.Error + "). Se conserva la última lectura buena.");
            }
            lock (candado)
            {
                pendiente = d;
                descargando = false;
            }
        }

        // ------------------------------------------------------------------ utilidades de lectura
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

        // nivel en precio de futuro: «{ "idx": …, "fut": … }»
        private static double Fut(Dictionary<string, object> d, string k)
        {
            Dictionary<string, object> n = Obj(d, k);
            return n == null ? double.NaN : Num(n, "fut");
        }

        // ------------------------------------------------------------------ dibujo
        private void Dibujar()
        {
            Niveles n;
            if (!actual.Indices.TryGetValue(raizIndice, out n))
            {
                Draw.TextFixed(this, "nexoraRegimen", "NEXORA GEX: gamma.json no trae niveles de " + raizIndice + " (SIN DATO)", TextPosition.TopLeft);
                return;
            }

            if (!double.IsNaN(n.Flip))
                Linea("nexoraFlip", "Gamma Flip", n.Flip, Brushes.Gold, DashStyleHelper.Solid);
            else
                RemoveDrawObject("nexoraFlip");
            if (!double.IsNaN(n.CallWall))
                Linea("nexoraCW", "Call Wall", n.CallWall, Brushes.Tomato, DashStyleHelper.Solid);
            else
                RemoveDrawObject("nexoraCW");
            if (!double.IsNaN(n.PutWall))
                Linea("nexoraPW", "Put Wall", n.PutWall, Brushes.LimeGreen, DashStyleHelper.Solid);
            else
                RemoveDrawObject("nexoraPW");
            if (MostrarMaxGamma && !double.IsNaN(n.MaxGamma))
                Linea("nexoraMaxG", "Max Gamma", n.MaxGamma, Brushes.DodgerBlue, DashStyleHelper.Dash);
            else
                RemoveDrawObject("nexoraMaxG");

            // banda EM: precio de referencia ± movimiento esperado de un día
            if (MostrarBandaEm && !double.IsNaN(n.Em) && !double.IsNaN(n.SpotFut))
            {
                double arriba = n.SpotFut + n.Em;
                double abajo = n.SpotFut - n.Em;
                int desde = Math.Min(CurrentBar, 600);
                Draw.Rectangle(this, "nexoraEM", false, desde, arriba, 0, abajo, Brushes.Transparent, Brushes.SteelBlue, 12);
                Draw.Text(this, "nexoraEMup", "EM + " + Fmt(n.Em), 0, arriba, Brushes.SteelBlue);
                Draw.Text(this, "nexoraEMdn", "EM − " + Fmt(n.Em), 0, abajo, Brushes.SteelBlue);
            }
            else
            {
                RemoveDrawObject("nexoraEM");
                RemoveDrawObject("nexoraEMup");
                RemoveDrawObject("nexoraEMdn");
            }

            if (MostrarEtiqueta)
                Draw.TextFixed(this, "nexoraRegimen", Etiqueta(n), TextPosition.TopLeft);
            else
                RemoveDrawObject("nexoraRegimen");
        }

        private void Linea(string tag, string nombre, double precio, Brush color, DashStyleHelper estilo)
        {
            Draw.HorizontalLine(this, tag, precio, color, estilo, Grosor);
            Draw.Text(this, tag + "t", nombre + " " + Fmt(precio), 0, precio, color);
        }

        // texto del régimen: depende del precio actual frente al Gamma Flip (por encima = gamma positiva)
        private string Etiqueta(Niveles n)
        {
            StringBuilder sb = new StringBuilder();
            sb.Append("NEXORA GEX · ").Append(raizIndice);
            if (!double.IsNaN(n.Flip))
            {
                double c = Close[0];
                sb.Append(c > n.Flip ? " · gamma POSITIVA (precio sobre el flip)" : c < n.Flip ? " · gamma NEGATIVA (precio bajo el flip)" : " · precio en el flip");
            }
            else
            {
                sb.Append(" · sin Gamma Flip (SIN DATO)");
            }
            if (!string.IsNullOrEmpty(n.Sesion))
                sb.Append("\nNiveles de la sesión ").Append(n.Sesion);
            if (!string.IsNullOrEmpty(actual.GeneradoUtc))
                sb.Append(" · archivo ").Append(actual.GeneradoUtc);
            DateTime g;
            if (!string.IsNullOrEmpty(actual.GeneradoUtc)
                && DateTime.TryParseExact(actual.GeneradoUtc.Replace(" UTC", ""), "yyyy-MM-dd HH:mm", CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out g)
                && (DateTime.UtcNow - g).TotalHours > HorasAntiguo)
                sb.Append("\nATENCIÓN: datos antiguos (más de ").Append(HorasAntiguo.ToString(CultureInfo.InvariantCulture)).Append(" h)");
            if (actual.Error != null)
                sb.Append("\nÚltima lectura fallida: ").Append(actual.Error);
            sb.Append("\nContexto de mercado, no una entrada");
            return sb.ToString();
        }

        private static string Fmt(double v)
        {
            return v.ToString("0.00", CultureInfo.InvariantCulture);
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
}
