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

    web = (lead.get("web") or "").strip()
    if web.startswith(("http://", "https://")) and "google.com/maps" not in web.lower():
        detalle["web"] = 2
    elif web.startswith(("http://", "https://")):
        detalle["web"] = 1

    if (lead.get("telefono") or "").strip():
        detalle["telefono"] = 1

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

    total = sum(detalle.values())
    return total, detalle


def califica_lead(lead: dict) -> bool:
    score, _ = puntuar_lead(lead)
    return score >= puntaje_minimo()
