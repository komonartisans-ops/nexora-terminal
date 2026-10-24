// Declaraciones MÍNIMAS de la API de NinjaTrader 8 que usan NexoraGex.cs y NexoraNiveles.cs, solo para comprobar que el indicador compila (sintaxis y uso de tipos). NO es NinjaTrader:
// la prueba definitiva es compilarlo dentro de NinjaTrader 8 (Nuevo > Editor de NinjaScript > Compilar). Las firmas siguen la documentación pública de NT8.
using System;
using System.Windows.Media;

namespace NinjaTrader.Gui
{
}

namespace NinjaTrader.Gui.Chart
{
}

namespace NinjaTrader.Gui.Tools
{
    // NT8: NinjaTrader.Gui.Tools.SimpleFont(string family, int size)
    public class SimpleFont
    {
        public SimpleFont(string family, int size) { }
    }
}

namespace NinjaTrader.NinjaScript
{
    public enum State { SetDefaults, Configure, Active, DataLoaded, Historical, Transition, Realtime, Terminated }
    public enum Calculate { OnBarClose, OnEachTick, OnPriceChange }
    public enum DashStyleHelper { Dash, DashDot, DashDotDot, Dot, Solid }
    public enum TextPosition { BottomLeft, BottomRight, Center, TopLeft, TopRight }

    public interface ISeries<T>
    {
        T this[int barsAgo] { get; }
    }

    public class MasterInstrument { public string Name; }
    public class Instrument { public MasterInstrument MasterInstrument = new MasterInstrument(); }

    [AttributeUsage(AttributeTargets.Property)]
    public class NinjaScriptPropertyAttribute : Attribute { }

    public class NinjaScriptBase
    {
        public string Name;
        public string Description;
        public Calculate Calculate;
        public State State;
        public int CurrentBar;
        public int Count;
        public bool IsOverlay;
        public bool DisplayInDataBox;
        public bool PaintPriceMarkers;
        public bool IsSuspendedWhileInactive;
        public Instrument Instrument = new Instrument();
        public ISeries<double> Close;
        protected virtual void OnStateChange() { }
        protected virtual void OnBarUpdate() { }
        public void Print(string s) { }
        public void RemoveDrawObject(string tag) { }
        // NT8: TriggerCustomEvent(Action<object> customEvent, object state): ejecuta el delegado en el hilo de NinjaScript
        protected void TriggerCustomEvent(Action<object> customEvent, object state) { }
    }
}

namespace NinjaTrader.NinjaScript.Indicators
{
    public class Indicator : NinjaScript.NinjaScriptBase { }
}

namespace NinjaTrader.NinjaScript.DrawingTools
{
    public static class Draw
    {
        public static object HorizontalLine(NinjaScript.NinjaScriptBase owner, string tag, double y, Brush brush, NinjaScript.DashStyleHelper dashStyle, int width) { return null; }
        public static object Text(NinjaScript.NinjaScriptBase owner, string tag, string text, int barsAgo, double y, Brush textBrush) { return null; }
        public static object TextFixed(NinjaScript.NinjaScriptBase owner, string tag, string text, NinjaScript.TextPosition textPosition) { return null; }
        public static object TextFixed(NinjaScript.NinjaScriptBase owner, string tag, string text, NinjaScript.TextPosition textPosition, Brush textBrush, NinjaTrader.Gui.Tools.SimpleFont font, Brush outlineBrush, Brush areaBrush, int areaOpacity) { return null; }
        public static object Text(NinjaScript.NinjaScriptBase owner, string tag, bool isAutoScale, string text, int barsAgo, double y, int yPixelOffset, Brush textBrush, NinjaTrader.Gui.Tools.SimpleFont font, System.Windows.TextAlignment alignment, Brush outlineBrush, Brush areaBrush, int areaOpacity) { return null; }
        public static object Rectangle(NinjaScript.NinjaScriptBase owner, string tag, bool isAutoScale, int startBarsAgo, double startY, int endBarsAgo, double endY, Brush outlineBrush, Brush areaBrush, int areaOpacity) { return null; }
    }
}
