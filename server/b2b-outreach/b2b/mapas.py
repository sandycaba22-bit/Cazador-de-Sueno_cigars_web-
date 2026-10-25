"""Links de mapa para cada prospecto: Google Maps, Apple Maps y Waze.

Se arman solo con datos que ya trae el lead (place_id, coordenadas, dirección, nombre);
no hacen llamadas de red ni gastan cuota de Google.
"""
from __future__ import annotations

import urllib.parse

from b2b.website import es_url_mapa


def _coordenadas(lead: dict) -> str:
    lat, lon = lead.get("lat"), lead.get("lon")
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return ""
    if not (-90 <= lat_f <= 90 and -180 <= lon_f <= 180) or (lat_f == 0 and lon_f == 0):
        return ""
    return f"{lat_f:.6f},{lon_f:.6f}"


def _consulta(lead: dict) -> str:
    """Nombre + dirección: la búsqueda que mejor ubica el negocio si no hay coordenadas."""
    partes = [(lead.get("nombre") or "").strip(), (lead.get("direccion") or "").strip()]
    return ", ".join(p for p in partes if p)


def google_maps_url(lead: dict) -> str:
    url = (lead.get("maps_url") or "").strip()
    if url:
        return url
    web = (lead.get("web") or "").strip()
    if web and es_url_mapa(web):
        return web
    consulta = _consulta(lead)
    if not consulta:
        return ""
    base = "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(consulta)
    pid = (lead.get("place_id") or "").strip()
    return f"{base}&query_place_id={urllib.parse.quote(pid)}" if pid else base


def apple_maps_url(lead: dict) -> str:
    coords = _coordenadas(lead)
    nombre = (lead.get("nombre") or "").strip()
    if coords:
        q = f"&q={urllib.parse.quote(nombre)}" if nombre else ""
        return f"https://maps.apple.com/?ll={coords}{q}"
    consulta = _consulta(lead)
    return f"https://maps.apple.com/?q={urllib.parse.quote(consulta)}" if consulta else ""


def waze_url(lead: dict) -> str:
    coords = _coordenadas(lead)
    if coords:
        return f"https://waze.com/ul?ll={coords}&navigate=yes"
    direccion = (lead.get("direccion") or "").strip() or _consulta(lead)
    return f"https://waze.com/ul?q={urllib.parse.quote(direccion)}&navigate=yes" if direccion else ""


def botones_mapa(lead: dict) -> list[dict]:
    """Botones inline de Telegram (solo los que se pueden armar con certeza)."""
    botones = []
    for texto, url in (
        ("📍 Google Maps", google_maps_url(lead)),
        ("🍎 Apple Maps", apple_maps_url(lead)),
        ("🚗 Waze", waze_url(lead)),
    ):
        if url:
            botones.append({"text": texto, "url": url})
    return botones
