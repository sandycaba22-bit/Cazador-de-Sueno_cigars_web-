from __future__ import annotations

import os

FUENTES_VALIDAS = ("simulado", "osm", "google", "ambas", "auto")


def resolver_fuente_leads(*, forzar_simulado: bool = False) -> str:
    """
    Devuelve: simulado | osm | google | ambas
    - --simulado / forzar_simulado → fixtures (solo pruebas)
    - FUENTE_LEADS=google  → Google Places; OSM solo si Google no da resultados
    - FUENTE_LEADS=ambas   → Google primero + OSM de respaldo (fusionando duplicados)
    - FUENTE_LEADS=osm     → solo OpenStreetMap
    - FUENTE_LEADS=auto    → ambas si hay GOOGLE_PLACES_API_KEY, si no osm (default)
    Sin clave, google/ambas caen a osm sin fallar.
    """
    if forzar_simulado:
        return "simulado"
    raw = (os.getenv("FUENTE_LEADS", "auto") or "auto").strip().lower()
    if raw not in FUENTES_VALIDAS:
        raw = "auto"
    if raw in ("simulado", "osm"):
        return raw
    if not os.getenv("GOOGLE_PLACES_API_KEY", "").strip():
        return "osm"
    return "ambas" if raw == "auto" else raw
