from __future__ import annotations

import os

FUENTES_VALIDAS = ("simulado", "osm", "google", "ambas", "auto")


def resolver_fuente_leads(*, forzar_simulado: bool = False) -> str:
    """
    Devuelve: simulado | osm | google | ambas
    - --simulado / forzar_simulado → fixtures (solo pruebas)
    - FUENTE_LEADS=google  → solo Google Places; nunca OpenStreetMap
    - FUENTE_LEADS=ambas   → Google primero + OSM de respaldo (fusionando duplicados)
    - FUENTE_LEADS=osm     → solo OpenStreetMap
    - FUENTE_LEADS=auto    → ambas si hay GOOGLE_PLACES_API_KEY, si no osm (default)
    Sin clave, ambas/auto caen a osm. google se queda en google y no llama a OSM.
    """
    if forzar_simulado:
        return "simulado"
    raw = (os.getenv("FUENTE_LEADS", "auto") or "auto").strip().lower()
    if raw not in FUENTES_VALIDAS:
        raw = "auto"
    if raw in ("simulado", "osm", "google"):
        return raw
    if not os.getenv("GOOGLE_PLACES_API_KEY", "").strip():
        return "osm"
    return "ambas" if raw == "auto" else raw
