from __future__ import annotations

import os

PESO_TIPO = {
    "distribuidor": 5,
    "duty_free": 4,
    "lounge": 3,
    "hotel": 3,
    "casino": 3,
    "tienda": 2,
}


def puntaje_minimo() -> int:
    try:
        return max(0, int(os.getenv("MIN_LEAD_SCORE", "4") or "4"))
    except ValueError:
        return 4


def puntuar_lead(lead: dict) -> tuple[int, dict]:
    """Puntúa un lead enriquecido; mayor = mejor fit B2B."""
    detalle: dict[str, int] = {}
    tipo = (lead.get("tipo") or lead.get("tipo_negocio") or "tienda").lower()
    detalle["tipo"] = PESO_TIPO.get(tipo, 1)

    from b2b.website import dominio_negocio

    if dominio_negocio((lead.get("web") or "").strip()):
        detalle["web"] = 2
    if lead.get("vende_cigarros") is True:
        detalle["web_cigarros"] = 2

    if (lead.get("telefono") or "").strip():
        detalle["telefono"] = 1
    if any((lead.get(k) or "").strip() for k in ("instagram", "facebook", "whatsapp")):
        detalle["redes"] = 1

    if (lead.get("correo") or "").strip():
        detalle["correo"] = 2
    elif not lead.get("sin_correo_publico"):
        detalle["correo"] = 0

    rating = lead.get("rating")
    reviews = lead.get("user_rating_count") or lead.get("userRatingCount") or 0
    try:
        rating_f = float(rating) if rating is not None else 0.0
    except (TypeError, ValueError):
        rating_f = 0.0
    try:
        reviews_i = int(reviews)
    except (TypeError, ValueError):
        reviews_i = 0
    if reviews_i >= 10:
        detalle["reseñas"] = 2
    elif reviews_i >= 3:
        detalle["reseñas"] = 1
    if rating_f >= 4.0:
        detalle["valoracion"] = 1

    fuente = (lead.get("fuente") or "").lower()
    if fuente in ("openstreetmap", "osm"):
        if (lead.get("telefono") or "").strip():
            detalle["contacto_osm"] = 2
        elif lead.get("osm_shop_tobacco"):
            detalle["tabaco_osm"] = 2
    if fuente.startswith("google_places") and lead.get("business_status") == "OPERATIONAL":
        detalle["google_operativo"] = 1

    total = sum(detalle.values())
    return total, detalle


def califica_lead(lead: dict) -> bool:
    score, _ = puntuar_lead(lead)
    return score >= puntaje_minimo()


def tiene_telefono_o_correo(lead: dict) -> bool:
    return bool((lead.get("telefono") or "").strip() or (lead.get("correo") or "").strip()
                or (lead.get("whatsapp") or "").strip())


def priorizar_leads_contacto(leads: list[dict]) -> list[dict]:
    """Primero negocios con correo o teléfono confirmado (mejor conversión)."""

    def clave(lead: dict) -> tuple:
        mail = 1 if (lead.get("correo") or "").strip() else 0
        tel = 1 if (lead.get("telefono") or lead.get("whatsapp") or "").strip() else 0
        return (0 if (mail or tel) else 1, 0 if mail else 1, 0 if tel else 1, lead.get("nombre") or "")

    return sorted(leads, key=clave)
