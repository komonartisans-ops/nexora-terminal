"""NEXORA · variaciones de series MENSUALES por FECHA, nunca por posición.

Una serie mensual puede tener meses que la fuente no publicó (el BLS no publicó el IPC de octubre de 2025). Si se calcula «hace 12 meses» como
s[i-12], con un hueco en medio se compara contra el mes equivocado (el IPC de sep-2026 saldría contra ago-2025: 4,02 % en vez de 3,72 %).
Aquí se busca el mes exacto; si falta, el resultado es None (SIN DATO) y nunca se estima ni se interpola."""
from __future__ import annotations


def _ym(d):
    """(año, mes) de una fecha (date/datetime) o de un texto AAAA-MM[-DD]."""
    if isinstance(d, str):
        return int(d[:4]), int(d[5:7])
    return d.year, d.month


def _resta_meses(ym, n):
    y, m = ym
    t = y * 12 + (m - 1) - n
    return t // 12, t % 12 + 1


def valor_hace(s, i, n):
    """Valor de la observación n meses ANTES de s[i] (mismo calendario), o None si ese mes no está en la serie.
    s = [(fecha, valor)] ordenada; i = índice de la observación de referencia (admite negativos)."""
    if not s or not (-len(s) <= i < len(s)):
        return None
    objetivo = _resta_meses(_ym(s[i][0]), n)
    for d, v in s:
        if _ym(d) == objetivo:
            return v
    return None


def var_pct(s, i=-1, meses=12):
    """Variación % de s[i] frente al mismo mes de hace `meses` meses; None si falta ese mes o el valor base es 0."""
    ref = valor_hace(s, i, meses)
    if ref in (None, 0):
        return None
    return (s[i][1] / ref - 1) * 100


def var_pct_dict(m, clave, meses=12):
    """Igual que var_pct para un diccionario {'AAAA-MM': valor}."""
    ref = m.get(f"{_resta_meses(_ym(clave), meses)[0]:04d}-{_resta_meses(_ym(clave), meses)[1]:02d}")
    if ref in (None, 0) or clave not in m:
        return None
    return (m[clave] / ref - 1) * 100


# ---------------------------------------------------------------- fecha de publicación del ÚLTIMO periodo mostrado
def fin_periodo(periodo_iso, tipo):
    """Último día del periodo: 'semana' (la fecha es el sábado de cierre), 'trimestre' (la fecha es el primer día del trimestre) o 'mes'."""
    import datetime as dt
    d = dt.date.fromisoformat(periodo_iso)
    if tipo == "semana":
        return d
    n = 3 if tipo == "trimestre" else 1
    t = d.year * 12 + (d.month - 1) + n
    y, m = t // 12, t % 12 + 1
    return dt.date(y, m, 1) - dt.timedelta(days=1)


LAG_MAX = {"semana": 10, "mes": 45, "trimestre": 100}  # días máximos entre el cierre del periodo y su primera publicación


def fecha_publicacion(eventos, claves, periodo_iso, tipo="mes", lag_max=None, ahora=None):
    """Fecha (ISO) en que se publicó por primera vez el periodo `periodo_iso`, según el calendario oficial, o None si no se puede asegurar.
    Solo cuenta un evento que (1) YA HA OCURRIDO (fecha y hora de Nueva York ≤ ahora; el calendario del día aún no ha salido a las 10:00 UTC),
    (2) cae DESPUÉS del cierre del periodo y (3) dentro del retraso típico de ese tipo de dato. Se toma el primero que cumple: las publicaciones
    posteriores del mismo dato son revisiones o el dato del periodo siguiente. Si ninguno cumple: None («fuera del rango»), nunca una estimación."""
    import datetime as dt
    from zoneinfo import ZoneInfo
    ny = ZoneInfo("America/New_York")
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    fin = fin_periodo(periodo_iso, tipo)
    lag = lag_max if lag_max is not None else LAG_MAX[tipo]
    mejores = []
    for e in eventos or []:
        if not any(c in e.get("evento", "").lower() for c in claves):
            continue
        d = dt.date.fromisoformat(e["fecha"])
        hm = e.get("hora_ny") or "23:59"
        h, m = map(int, hm.split(":"))
        if dt.datetime.combine(d, dt.time(h, m), ny).astimezone(dt.timezone.utc) > ahora:
            continue
        if d > fin and (d - fin).days <= lag:
            mejores.append(d)
    return min(mejores).isoformat() if mejores else None
