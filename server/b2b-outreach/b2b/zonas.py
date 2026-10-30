"""Zona horaria del local. Canadá está en el mapa y todavía no se busca."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# (desfase estándar en minutos, desfase de verano en minutos). El verano sigue la regla de EE.UU.
_MINUTOS = {
    "America/New_York": (-300, -240),
    "America/Detroit": (-300, -240),
    "America/Chicago": (-360, -300),
    "America/Denver": (-420, -360),
    "America/Phoenix": (-420, -420),
    "America/Los_Angeles": (-480, -420),
    "America/Anchorage": (-540, -480),
    "Pacific/Honolulu": (-600, -600),
    "America/Puerto_Rico": (-240, -240),
    "America/Jamaica": (-300, -300),
    "America/Santo_Domingo": (-240, -240),
    # Provincias: listas para cuando se agregue Canadá. Hoy no se buscan.
    "America/Toronto": (-300, -240),
    "America/Winnipeg": (-360, -300),
    "America/Edmonton": (-420, -360),
    "America/Vancouver": (-480, -420),
    "America/Halifax": (-240, -180),
    "America/Moncton": (-240, -180),
    "America/St_Johns": (-210, -150),
    "America/Regina": (-360, -360),
    "America/Whitehorse": (-420, -420),
    "America/Yellowknife": (-420, -360),
    "America/Iqaluit": (-300, -240),
}

ZONA_ESTADO = {
    "AL": "America/Chicago", "AK": "America/Anchorage", "AZ": "America/Phoenix",
    "AR": "America/Chicago", "CA": "America/Los_Angeles", "CO": "America/Denver",
    "CT": "America/New_York", "DE": "America/New_York", "DC": "America/New_York",
    "FL": "America/New_York", "GA": "America/New_York", "HI": "Pacific/Honolulu",
    "ID": "America/Denver", "IL": "America/Chicago", "IN": "America/Indiana/Indianapolis",
    "IA": "America/Chicago", "KS": "America/Chicago", "KY": "America/New_York",
    "LA": "America/Chicago", "ME": "America/New_York", "MD": "America/New_York",
    "MA": "America/New_York", "MI": "America/Detroit", "MN": "America/Chicago",
    "MS": "America/Chicago", "MO": "America/Chicago", "MT": "America/Denver",
    "NE": "America/Chicago", "NV": "America/Los_Angeles", "NH": "America/New_York",
    "NJ": "America/New_York", "NM": "America/Denver", "NY": "America/New_York",
    "NC": "America/New_York", "ND": "America/Chicago", "OH": "America/New_York",
    "OK": "America/Chicago", "OR": "America/Los_Angeles", "PA": "America/New_York",
    "RI": "America/New_York", "SC": "America/New_York", "SD": "America/Chicago",
    "TN": "America/Chicago", "TX": "America/Chicago", "UT": "America/Denver",
    "VT": "America/New_York", "VA": "America/New_York", "WA": "America/Los_Angeles",
    "WV": "America/New_York", "WI": "America/Chicago", "WY": "America/Denver",
    "PR": "America/Puerto_Rico", "JM": "America/Jamaica",
}

# Indiana no está en el respaldo: cae a Nueva York, que es la misma franja.
_MINUTOS["America/Indiana/Indianapolis"] = (-300, -240)

ZONA_PROVINCIA = {
    "AB": "America/Edmonton", "BC": "America/Vancouver", "MB": "America/Winnipeg",
    "NB": "America/Moncton", "NL": "America/St_Johns", "NS": "America/Halifax",
    "NT": "America/Yellowknife", "NU": "America/Iqaluit", "ON": "America/Toronto",
    "PE": "America/Halifax", "QC": "America/Toronto", "SK": "America/Regina",
    "YT": "America/Whitehorse",
}

NOMBRE_A_ABBR = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "district of columbia": "DC", "florida": "FL", "georgia": "GA", "hawaii": "HI",
    "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "puerto rico": "PR", "jamaica": "JM",
}

RESPALDO = "America/New_York"


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> datetime:
    primero = datetime(year, month, 1)
    salto = (weekday - primero.weekday()) % 7
    return primero + timedelta(days=salto + (n - 1) * 7)


def _verano_eeuu(momento_utc: datetime) -> bool:
    year = momento_utc.year
    inicio = _nth_weekday(year, 3, 6, 2).replace(hour=7)
    fin = _nth_weekday(year, 11, 6, 1).replace(hour=6)
    marca = momento_utc.replace(tzinfo=None)
    return inicio <= marca < fin


class _Desfase(tzinfo):
    """Respaldo si el sistema no trae la base IANA (Windows sin tzdata)."""

    def __init__(self, nombre: str):
        self._nombre = nombre
        self._std, self._dst = _MINUTOS.get(nombre, _MINUTOS[RESPALDO])

    def _minutos(self, momento_utc: datetime) -> int:
        if self._std == self._dst:
            return self._std
        return self._dst if _verano_eeuu(momento_utc) else self._std

    def utcoffset(self, dt: datetime | None) -> timedelta:
        if dt is None:
            return timedelta(minutes=self._std)
        utc = dt.replace(tzinfo=None) - timedelta(minutes=self._std)
        return timedelta(minutes=self._minutos(utc))

    def dst(self, dt: datetime | None) -> timedelta:
        if dt is None or self._std == self._dst:
            return timedelta(0)
        off = self.utcoffset(dt)
        return off - timedelta(minutes=self._std)

    def tzname(self, dt: datetime | None) -> str:
        return self._nombre

    def fromutc(self, dt: datetime) -> datetime:
        off = timedelta(minutes=self._minutos(dt.replace(tzinfo=None)))
        return (dt.replace(tzinfo=None) + off).replace(tzinfo=self)


def tz(nombre: str) -> tzinfo:
    clave = nombre or RESPALDO
    try:
        return ZoneInfo(clave)
    except ZoneInfoNotFoundError:
        return _Desfase(clave if clave in _MINUTOS else RESPALDO)


def iana_de_lugar(lugar: str) -> str:
    """Estado de EE.UU., Puerto Rico, Jamaica, o una provincia canadiense ya mapeada."""
    bruto = (lugar or "").strip()
    if not bruto:
        return RESPALDO
    if bruto.upper() in ZONA_ESTADO:
        return ZONA_ESTADO[bruto.upper()]
    if bruto.upper() in ZONA_PROVINCIA:
        return ZONA_PROVINCIA[bruto.upper()]
    abbr = NOMBRE_A_ABBR.get(bruto.casefold())
    if abbr:
        return ZONA_ESTADO[abbr]
    return RESPALDO


def ahora_local(momento: datetime, lugar: str) -> datetime:
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(tz(iana_de_lugar(lugar)))


def en_horario_laboral(momento: datetime, lugar: str, inicio: int = 9, fin: int = 17) -> bool:
    local = ahora_local(momento, lugar)
    if local.weekday() >= 5:
        return False
    return inicio <= local.hour < fin


def siguiente_habil(momento: datetime, lugar: str, inicio: int = 9, fin: int = 17) -> datetime:
    """Si ya está en horario, lo deja. Si no, el próximo día hábil a la hora de inicio."""
    local = ahora_local(momento, lugar)
    if en_horario_laboral(momento, lugar, inicio, fin):
        return local
    dia = local.date()
    if local.weekday() >= 5 or local.hour >= fin:
        dia = dia + timedelta(days=1)
        while dia.weekday() >= 5:
            dia += timedelta(days=1)
    return datetime(dia.year, dia.month, dia.day, inicio, 0, tzinfo=local.tzinfo)
