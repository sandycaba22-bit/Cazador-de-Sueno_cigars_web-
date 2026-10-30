"""Local 100 % seguro: solo pasa a tarjeta si cumple todas las condiciones."""
from __future__ import annotations

import os
import re

from b2b.contacto_web import tipo_url
from b2b.leads_store import en_lista_no_contactar
from b2b.nombres_busqueda import contiene_fuerte
from b2b.telegram_control import USPS_ESTADOS, mercado_canonico
from b2b.telegram_gestion import ya_gestionado_telegram
from b2b.zonas import NOMBRE_A_ABBR

_CIGARRO = re.compile(r"cigar|humidor|tobacco|tobacconist", re.I)
_TIPOS_OK = {"tienda", "lounge", "distribuidor", "duty_free"}


def _min_rating() -> float:
    try:
        return float(os.getenv("GOOGLE_PLACES_MIN_RATING", "4") or "4")
    except ValueError:
        return 4.0


def _min_resenas() -> int:
    try:
        return int(os.getenv("GOOGLE_PLACES_MIN_RESENAS", "5") or "5")
    except ValueError:
        return 5


def _abbr_estado(estado: str) -> str:
    bruto = (estado or "").strip()
    if bruto.upper() in USPS_ESTADOS:
        return bruto.upper()
    return NOMBRE_A_ABBR.get(bruto.casefold(), "")


def direccion_en_lugar(direccion: str, lugar: str) -> bool:
    """La dirección cae en el estado buscado. PR y Jamaica, por su nombre."""
    texto = direccion or ""
    if not texto.strip() or not (lugar or "").strip():
        return False
    canon = mercado_canonico(lugar) or (lugar or "").strip()
    abbr = _abbr_estado(canon)
    if canon.casefold() == "virginia":
        resto = re.sub(r"\bWest Virginia\b", " ", texto, flags=re.I)
        if re.search(r"\bVirginia\b", resto, re.I) or _tiene_abbr(resto, "VA"):
            return True
        return False
    if re.search(rf"\b{re.escape(canon)}\b", texto, re.I):
        return True
    if abbr and _tiene_abbr(texto, abbr):
        return True
    return False


def _tiene_abbr(texto: str, abbr: str) -> bool:
    return bool(re.search(rf"(?:^|[,\s])\s*{abbr}(?:\s+\d{{5}}(?:-\d{{4}})?|\s*$|,)", texto))


def _senal_cigarro(lead: dict) -> bool:
    if lead.get("vende_cigarros") is True:
        return True
    nombre = lead.get("nombre") or ""
    types = " ".join(str(t) for t in (lead.get("types") or []))
    tipo = (lead.get("tipo") or lead.get("tipo_negocio") or "").lower()
    texto = f"{nombre} {types}"
    if _CIGARRO.search(texto) or contiene_fuerte(nombre):
        return True
    return tipo in _TIPOS_OK and _CIGARRO.search(texto)


def _telefono(lead: dict) -> str:
    return (lead.get("telefono") or lead.get("telefono_internacional") or "").strip()


def verificar_local(lead: dict, estado_buscado: str) -> tuple[bool, list[str], str]:
    """(ok, motivos, resumen). Si ok es falso, no se encola tarjeta."""
    motivos: list[str] = []
    estado = (lead.get("business_status") or "").strip().upper()
    if estado != "OPERATIONAL":
        motivos.append("no está operativo en Google")
    if not _telefono(lead):
        motivos.append("sin teléfono")
    if tipo_url(lead.get("web") or "") != "web":
        motivos.append("sin web propia")
    rating = lead.get("rating")
    resenas = lead.get("user_rating_count")
    try:
        rating_n = float(rating)
    except (TypeError, ValueError):
        rating_n = -1.0
    try:
        resenas_n = int(resenas or 0)
    except (TypeError, ValueError):
        resenas_n = 0
    if rating_n < _min_rating():
        motivos.append(f"rating {rating_n:g} bajo")
    if resenas_n < _min_resenas():
        motivos.append(f"reseñas {resenas_n} bajo")
    if not direccion_en_lugar(lead.get("direccion") or "", estado_buscado):
        motivos.append("dirección fuera del estado buscado")
    if not _senal_cigarro(lead):
        motivos.append("sin señal de cigarros")
    if en_lista_no_contactar(lead.get("nombre") or "", lead.get("web") or ""):
        motivos.append("en no contactar")
    if ya_gestionado_telegram(lead):
        motivos.append("ya gestionado")

    abbr = _abbr_estado(mercado_canonico(estado_buscado) or estado_buscado) or (estado_buscado or "").strip()
    partes = ["Local verificado", "Operativo"]
    if rating_n >= 0:
        partes.append(f"⭐ {rating_n:g} ({resenas_n})")
    if _telefono(lead):
        partes.append("Tel")
    if lead.get("vende_cigarros") is True:
        partes.append("Web con cigarros")
    elif _senal_cigarro(lead):
        partes.append("Señal de cigarros")
    partes.append(f"Dirección en {abbr}")
    resumen = " · ".join(partes)
    return (not motivos), motivos, resumen
