from __future__ import annotations

import os


def resolver_fuente_leads(*, forzar_simulado: bool = False) -> str:
    """
    Devuelve: simulado | osm | google
    - --simulado / forzar_simulado → fixtures (solo pruebas)
    - FUENTE_LEADS=google|osm|simulado|auto (default auto)
    - auto: Google solo si hay clave; si no, OpenStreetMap (gratis)
    """
    if forzar_simulado:
        return "simulado"
    raw = (os.getenv("FUENTE_LEADS", "auto") or "auto").strip().lower()
    if raw == "simulado":
        return "simulado"
    if raw == "google":
        if not os.getenv("GOOGLE_PLACES_API_KEY", "").strip():
            raise RuntimeError(
                "FUENTE_LEADS=google pero falta GOOGLE_PLACES_API_KEY. "
                "Usa FUENTE_LEADS=osm o deja auto."
            )
        return "google"
    if raw == "osm":
        return "osm"
    if os.getenv("GOOGLE_PLACES_API_KEY", "").strip():
        return "google"
    return "osm"
