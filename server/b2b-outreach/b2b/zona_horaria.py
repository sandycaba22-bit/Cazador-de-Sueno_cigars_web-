"""Zona IANA y ventana local de cada negocio. Todo instante interno queda en UTC.

La zona del operador (B2B_ZONA_OPERADOR, por defecto America/Santo_Domingo) solo
sirve para mostrar horas, las tandas y el resumen de las 20:00. No cambia el reloj.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from b2b.paths import ROOT
from b2b.zonas import (
    NOMBRE_A_ABBR,
    RESPALDO,
    ZONA_ESTADO,
    ZONA_PROVINCIA,
    tz,
)

# Provincias. La abreviatura ya está en zonas.ZONA_PROVINCIA.
_NOMBRE_PROVINCIA = {
    "alberta": "AB",
    "british columbia": "BC",
    "manitoba": "MB",
    "new brunswick": "NB",
    "newfoundland and labrador": "NL",
    "newfoundland": "NL",
    "nova scotia": "NS",
    "northwest territories": "NT",
    "nunavut": "NU",
    "ontario": "ON",
    "prince edward island": "PE",
    "quebec": "QC",
    "québec": "QC",
    "saskatchewan": "SK",
    "yukon": "YT",
}

# Si no hay estado reconocible. config/ventanas_envio.json puede sumar países.
_ZONA_PAIS = {
    "jamaica": "America/Jamaica",
    "puerto rico": "America/Puerto_Rico",
    "dominican republic": "America/Santo_Domingo",
    "república dominicana": "America/Santo_Domingo",
    "republica dominicana": "America/Santo_Domingo",
    "bahamas": "America/Nassau",
    "haiti": "America/Port-au-Prince",
    "haïti": "America/Port-au-Prince",
    "cuba": "America/Havana",
    "mexico": "America/Mexico_City",
    "méxico": "America/Mexico_City",
    "canada": "America/Toronto",
    "united states": "America/New_York",
    "united states of america": "America/New_York",
    "usa": "America/New_York",
    "us": "America/New_York",
    "spain": "Europe/Madrid",
    "españa": "Europe/Madrid",
    "france": "Europe/Paris",
    "francia": "Europe/Paris",
    "germany": "Europe/Berlin",
    "alemania": "Europe/Berlin",
    "united kingdom": "Europe/London",
    "uk": "Europe/London",
    "reino unido": "Europe/London",
    "italy": "Europe/Rome",
    "italia": "Europe/Rome",
    "netherlands": "Europe/Amsterdam",
    "países bajos": "Europe/Amsterdam",
    "aruba": "America/Aruba",
    "curaçao": "America/Curacao",
    "curacao": "America/Curacao",
    "trinidad and tobago": "America/Port_of_Spain",
    "barbados": "America/Barbados",
}

_VENTANAS_DEFECTO = ((time(9, 0), time(11, 30)), (time(13, 30), time(16, 0)))
_DIAS_DEFECTO = frozenset({1, 2, 3, 4, 5})
_PRIORIDAD_DEFECTO = frozenset({2, 3, 4})

_BANDA = {
    "America/New_York": "este",
    "America/Detroit": "este",
    "America/Indiana/Indianapolis": "este",
    "America/Toronto": "este",
    "America/Iqaluit": "este",
    "America/Jamaica": "este",
    "America/Nassau": "este",
    "America/Port-au-Prince": "este",
    "America/Havana": "este",
    "America/Chicago": "centro",
    "America/Winnipeg": "centro",
    "America/Regina": "centro",
    "America/Mexico_City": "centro",
    "America/Denver": "montana",
    "America/Phoenix": "montana",
    "America/Edmonton": "montana",
    "America/Yellowknife": "montana",
    "America/Los_Angeles": "pacifico",
    "America/Vancouver": "pacifico",
    "America/Tijuana": "pacifico",
}
ORDEN_OLA = ("este", "centro", "montana", "pacifico", "otro")

_AVISO = {
    "estado": "Zona por estado, no por el mapa",
    "pais": "Zona por país, no por el mapa",
    "respaldo": "Zona de respaldo, no es la del negocio",
}

_finder = None
_finder_listo = False


def _utc(momento: datetime) -> datetime:
    if momento.tzinfo is None:
        return momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(timezone.utc)


def zona_operador_nombre() -> str:
    nombre = (os.getenv("B2B_ZONA_OPERADOR", "") or "").strip() or "America/Santo_Domingo"
    try:
        ZoneInfo(nombre)
    except Exception:
        return "America/Santo_Domingo"
    return nombre


def zona_operador():
    return tz(zona_operador_nombre())


def segundos_planificador() -> int:
    """Nunca más seguido que cada 60 s, aunque la variable venga baja o vacía."""
    try:
        n = int(os.getenv("B2B_PLANIFICADOR_SEG", "60") or "60")
    except ValueError:
        n = 60
    return max(60, n)


def _abbr(texto: str) -> tuple[str, str]:
    """(abreviatura, 'estado'|'provincia'|'')."""
    bruto = (texto or "").strip()
    if not bruto:
        return "", ""
    up = bruto.upper()
    if up in ZONA_ESTADO:
        return up, "estado"
    if up in ZONA_PROVINCIA:
        return up, "provincia"
    abbr = NOMBRE_A_ABBR.get(bruto.casefold())
    if abbr:
        return abbr, "estado"
    prov = _NOMBRE_PROVINCIA.get(bruto.casefold())
    if prov:
        return prov, "provincia"
    return "", ""


def _iana_valida(nombre: str) -> str:
    nombre = (nombre or "").strip()
    if not nombre:
        return ""
    try:
        ZoneInfo(nombre)
    except Exception:
        return ""
    return nombre


def _timezonefinder(lat: float, lon: float) -> str:
    """Biblioteca offline opcional. Sin ella, no hay red: se usan las cajas de abajo."""
    global _finder, _finder_listo
    if not _finder_listo:
        _finder_listo = True
        try:
            from timezonefinder import TimezoneFinder

            _finder = TimezoneFinder()
        except Exception:
            _finder = None
    if _finder is None:
        return ""
    try:
        return _iana_valida(_finder.timezone_at(lat=lat, lng=lon) or "")
    except Exception:
        return ""


def _cajas(lat: float, lon: float, estado: str) -> str:
    """Excepciones que un mapa estado→zona se come: panhandle y El Paso.

    Arizona se queda en America/Phoenix (sin cambio de hora). La Nación Navajo,
    que sí cambia, solo se distingue si timezonefinder está instalado.
    """
    abbr, tipo = _abbr(estado)
    if tipo != "estado":
        return ""
    if abbr == "FL" and 29.5 <= lat <= 31.1 and lon <= -85.0:
        return "America/Chicago"
    if abbr == "TX" and 29.0 <= lat <= 33.2 and lon <= -104.0:
        return "America/Denver"
    if abbr == "AZ":
        return "America/Phoenix"
    return ""


def _coords(lead: dict) -> tuple[float, float] | None:
    try:
        lat = float(lead.get("lat"))
        lon = float(lead.get("lon"))
    except (TypeError, ValueError):
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return lat, lon


def _estado_del_lead(lead: dict) -> str:
    for campo in ("estado", "pais"):
        abbr, tipo = _abbr(str(lead.get(campo) or ""))
        if abbr and tipo == "estado":
            return str(lead.get(campo) or "")
    return ""


def _provincia_del_lead(lead: dict) -> str:
    for campo in ("estado", "pais"):
        abbr, tipo = _abbr(str(lead.get(campo) or ""))
        if abbr and tipo == "provincia":
            return abbr
    return ""


def _ruta_ventanas() -> str:
    explicita = (os.getenv("B2B_VENTANAS_PATH", "") or "").strip()
    if explicita:
        return explicita
    return str(ROOT / "config" / "ventanas_envio.json")


def _tabla_paises() -> dict:
    path = _ruta_ventanas()
    try:
        data = json.loads(open(path, encoding="utf-8").read())
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    paises = data.get("paises") if isinstance(data, dict) else None
    if not isinstance(paises, dict):
        return {}
    return {str(k).casefold(): v for k, v in paises.items() if isinstance(v, dict)}


# El JSON guarda una sola lista. Estos nombres, y cualquier estado o provincia, la heredan.
_ALIAS_FERIADOS = {
    "united states": "united states",
    "united states of america": "united states",
    "usa": "united states",
    "us": "united states",
    "estados unidos": "united states",
    "ee.uu.": "united states",
    "eeuu": "united states",
    "ee. uu.": "united states",
    "canada": "canada",
    "canadá": "canada",
}


def _bloque_pais(lead: dict) -> dict:
    tabla = _tabla_paises()
    for campo in ("pais", "estado"):
        clave = str(lead.get(campo) or "").strip().casefold()
        if clave and clave in tabla:
            return tabla[clave]
    return {}


def _pais_de_feriados(lead: dict) -> str:
    """EE.UU. o Canadá aunque el lead diga Florida u Ontario, no el nombre del país."""
    for campo in ("pais", "estado"):
        clave = str(lead.get(campo) or "").strip().casefold()
        if clave in _ALIAS_FERIADOS:
            return _ALIAS_FERIADOS[clave]
    abbr, tipo = _abbr(str(lead.get("estado") or lead.get("pais") or ""))
    if tipo == "estado" and abbr != "JM":
        return "united states"
    if tipo == "provincia":
        return "canada"
    return ""


def _fechas(bloque: dict) -> set[str]:
    fechas: set[str] = set()
    for dia in (bloque or {}).get("feriados") or []:
        texto = str(dia).strip()
        if len(texto) == 10 and texto[4] == "-" and texto[7] == "-":
            fechas.add(texto)
    return fechas


def _parse_hora(texto: str) -> time | None:
    partes = (texto or "").strip().split(":")
    if len(partes) != 2:
        return None
    try:
        hora, minuto = int(partes[0]), int(partes[1])
    except ValueError:
        return None
    if not (0 <= hora <= 23 and 0 <= minuto <= 59):
        return None
    return time(hora, minuto)


def _parse_ventanas(texto: str) -> list[tuple[time, time]]:
    salida: list[tuple[time, time]] = []
    for trozo in (texto or "").split(","):
        if "-" not in trozo:
            continue
        ini_s, fin_s = trozo.split("-", 1)
        ini, fin = _parse_hora(ini_s), _parse_hora(fin_s)
        if ini and fin and ini < fin:
            salida.append((ini, fin))
    return salida


def _parse_dias(texto: str) -> set[int]:
    dias: set[int] = set()
    for trozo in (texto or "").split(","):
        trozo = trozo.strip()
        if not trozo:
            continue
        try:
            n = int(trozo)
        except ValueError:
            continue
        if 1 <= n <= 7:
            dias.add(n)
    return dias


def reglas_de(lead: dict) -> dict:
    """Ventanas, días hábiles, descanso y feriados. Si falta la variable, no se abre el día entero."""
    bloque = _bloque_pais(lead)
    ventanas = _parse_ventanas(os.getenv("B2B_ENVIO_VENTANAS_LOCALES", "") or "")
    if isinstance(bloque.get("ventanas"), list):
        unidas = _parse_ventanas(",".join(str(v) for v in bloque["ventanas"]))
        if unidas:
            ventanas = unidas
    if not ventanas:
        ventanas = list(_VENTANAS_DEFECTO)
    dias = _parse_dias(os.getenv("B2B_ENVIO_DIAS", "") or "")
    if isinstance(bloque.get("dias"), list):
        propios = _parse_dias(",".join(str(d) for d in bloque["dias"]))
        if propios:
            dias = propios
    if not dias:
        dias = set(_DIAS_DEFECTO)
    prioridad = _parse_dias(os.getenv("B2B_ENVIO_DIAS_PRIORIDAD", "") or "")
    if isinstance(bloque.get("prioridad"), list):
        propios = _parse_dias(",".join(str(d) for d in bloque["prioridad"]))
        if propios:
            prioridad = propios
    if not prioridad:
        prioridad = set(_PRIORIDAD_DEFECTO)
    descanso = _parse_dias(",".join(str(d) for d in (bloque.get("descanso") or [])))
    feriados = _fechas(bloque)
    canon = _pais_de_feriados(lead)
    if canon:
        feriados |= _fechas(_tabla_paises().get(canon) or {})
    return {
        "ventanas": ventanas,
        "dias": dias - descanso,
        "prioridad": prioridad,
        "feriados": feriados,
    }


def resolver_zona(lead: dict) -> dict:
    """Orden: lat/lon, estado o provincia, país, respaldo. Nunca un offset fijo."""
    estado = _estado_del_lead(lead)
    coords = _coords(lead)
    if coords is not None:
        lat, lon = coords
        precisa = _timezonefinder(lat, lon)
        if precisa:
            return {"iana": precisa, "fuente": "coordenadas", "exacta": True}
        caja = _cajas(lat, lon, estado or str(lead.get("estado") or lead.get("pais") or ""))
        if caja:
            return {"iana": caja, "fuente": "coordenadas", "exacta": True}
        # El punto descarta el panhandle / El Paso: el resto del estado es una sola zona.
        if estado:
            abbr, _tipo = _abbr(estado)
            if abbr in ("FL", "TX", "AZ"):
                return {"iana": ZONA_ESTADO[abbr], "fuente": "coordenadas", "exacta": True}
    if estado:
        abbr, _tipo = _abbr(estado)
        iana = ZONA_ESTADO.get(abbr) or RESPALDO
        return {"iana": iana, "fuente": "estado", "exacta": False}
    prov = _provincia_del_lead(lead)
    if prov:
        return {"iana": ZONA_PROVINCIA[prov], "fuente": "estado", "exacta": False}
    bloque = _bloque_pais(lead)
    de_json = _iana_valida(str(bloque.get("zona") or ""))
    if de_json:
        return {"iana": de_json, "fuente": "pais", "exacta": False}
    for campo in ("pais", "estado"):
        iana = _ZONA_PAIS.get(str(lead.get(campo) or "").strip().casefold())
        iana = _iana_valida(iana or "")
        if iana:
            return {"iana": iana, "fuente": "pais", "exacta": False}
    return {"iana": RESPALDO, "fuente": "respaldo", "exacta": False}


def aplicar_zona(lead: dict) -> dict:
    info = resolver_zona(lead)
    lead["zona_iana"] = info["iana"]
    lead["zona_fuente"] = info["fuente"]
    lead["zona_exacta"] = info["exacta"]
    return lead


def _local(momento: datetime, lead: dict) -> datetime:
    if not lead.get("zona_iana"):
        aplicar_zona(lead)
    return _utc(momento).astimezone(tz(str(lead.get("zona_iana") or RESPALDO)))


def _dia_habil(dia, lead: dict, reglas: dict) -> bool:
    if dia.isoweekday() not in reglas["dias"]:
        return False
    if dia.isoformat() in reglas["feriados"]:
        return False
    return True


def en_ventana(momento: datetime, lead: dict) -> bool:
    local = _local(momento, lead)
    reglas = reglas_de(lead)
    if not _dia_habil(local.date(), lead, reglas):
        return False
    actual = local.time().replace(tzinfo=None)
    return any(ini <= actual < fin for ini, fin in reglas["ventanas"])


def primer_hueco(momento: datetime, lead: dict) -> datetime:
    """Primer instante >= momento que cae en un día hábil y dentro de una ventana local."""
    if not lead.get("zona_iana"):
        aplicar_zona(lead)
    zona = tz(str(lead.get("zona_iana") or RESPALDO))
    local = _utc(momento).astimezone(zona)
    reglas = reglas_de(lead)
    for offset in range(0, 28):
        dia = local.date() + timedelta(days=offset)
        if not _dia_habil(dia, lead, reglas):
            continue
        for ini, fin in reglas["ventanas"]:
            inicio = datetime(dia.year, dia.month, dia.day, ini.hour, ini.minute, tzinfo=zona)
            final = datetime(dia.year, dia.month, dia.day, fin.hour, fin.minute, tzinfo=zona)
            if offset == 0 and local >= final:
                continue
            if offset == 0 and inicio <= local < final:
                return _utc(local)
            if inicio >= local:
                return _utc(inicio)
    # Sin hueco en 4 semanas: no adelantar a 'ahora' (eso enviaría fuera de horario).
    return _utc(local + timedelta(days=28))


def banda(iana: str) -> str:
    return _BANDA.get(iana or "", "otro")


def prioridad_dia(momento: datetime, lead: dict) -> int:
    """0 = martes a jueves (salen antes a igualdad de puntaje). 1 = lunes o viernes."""
    local = _local(momento, lead)
    reglas = reglas_de(lead)
    return 0 if local.isoweekday() in reglas["prioridad"] else 1


def ordenar_ola(items: list[dict]) -> list[dict]:
    """Puntaje primero, y dentro de cada banda se alterna Este → Centro → Montaña → Pacífico."""
    grupos: dict[str, list[dict]] = {nombre: [] for nombre in ORDEN_OLA}
    for item in items:
        lead = item.get("lead") or {}
        iana = item.get("zona_iana") or lead.get("zona_iana") or ""
        grupos[banda(str(iana))].append(item)

    def _clave(item: dict) -> tuple:
        lead = item.get("lead") or {}
        try:
            puntaje = int(item.get("puntaje") if item.get("puntaje") is not None else lead.get("puntaje") or 0)
        except (TypeError, ValueError):
            puntaje = 0
        cuando = item.get("_cuando_orden")
        prio = 1
        if isinstance(cuando, datetime):
            prio = prioridad_dia(cuando, {**lead, "zona_iana": item.get("zona_iana") or lead.get("zona_iana")})
        return (prio, -puntaje, str(item.get("nombre") or ""))

    for nombre in grupos:
        grupos[nombre].sort(key=_clave)
    salida: list[dict] = []
    while any(grupos.values()):
        for nombre in ORDEN_OLA:
            if grupos[nombre]:
                salida.append(grupos[nombre].pop(0))
    return salida


def _lugar_visible(lead: dict) -> str:
    return (
        (lead.get("ciudad") or "").strip()
        or (lead.get("estado") or "").strip()
        or (lead.get("pais") or "").strip()
        or "el negocio"
    )


def linea_horario(cuando: datetime, lead: dict, ahora: datetime | None = None) -> str:
    """'hoy 10:42 hora de Tampa (11:42 hora RD)' más el aviso si la zona no es el punto."""
    if not lead.get("zona_iana"):
        aplicar_zona(lead)
    cuando = _utc(cuando)
    ahora = _utc(ahora or datetime.now(timezone.utc))
    local = cuando.astimezone(tz(str(lead.get("zona_iana") or RESPALDO)))
    operador = cuando.astimezone(zona_operador())
    mismo_dia = local.date() == ahora.astimezone(local.tzinfo).date()
    if mismo_dia:
        izquierda = f"hoy {local.strftime('%H:%M')}"
    else:
        izquierda = f"el {local.strftime('%Y-%m-%d')} {local.strftime('%H:%M')}"
    etiqueta = "hora RD" if zona_operador_nombre() == "America/Santo_Domingo" else "hora operador"
    frase = f"{izquierda} hora de {_lugar_visible(lead)} ({operador.strftime('%H:%M')} {etiqueta})"
    if not lead.get("zona_exacta", True):
        frase += ". " + _AVISO.get(str(lead.get("zona_fuente") or ""), _AVISO["respaldo"])
    return frase


def frase_programado(cuando: datetime, lead: dict, ahora: datetime | None = None) -> str:
    return "Se enviará " + linea_horario(cuando, lead, ahora)
