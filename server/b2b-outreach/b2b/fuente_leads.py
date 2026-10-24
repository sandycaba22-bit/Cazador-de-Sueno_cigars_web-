from __future__ import annotations

import os

FUENTES_VALIDAS = ("simulado", "osm", "google", "ambas", "auto")


def resolver_fuente_leads(*, forzar_simulado: bool = False) -> str:
    """
    Devuelve: simulado | osm | google | ambas
    - --simulado / forzar_simulado → fixtures (solo pruebas)
    - FUENTE_LEADS=google  → solo Google Places; nunca OpenStreetMap (default)
    - FUENTE_LEADS=ambas   → Google primero + OSM de respaldo (fusionando duplicados)
    - FUENTE_LEADS=osm     → solo OpenStreetMap
    - FUENTE_LEADS=auto    → google si hay GOOGLE_PLACES_API_KEY; sin clave no cae a OSM
    Sin clave, google/auto se quedan en google y no llaman a OSM.
    """
    if forzar_simulado:
        return "simulado"
    raw = (os.getenv("FUENTE_LEADS", "google") or "google").strip().lower()
    if raw not in FUENTES_VALIDAS:
        raw = "google"
    if raw in ("simulado", "osm", "google"):
        return raw
    if raw == "auto":
        return "google"
    if not os.getenv("GOOGLE_PLACES_API_KEY", "").strip():
        return "google"
    return raw
