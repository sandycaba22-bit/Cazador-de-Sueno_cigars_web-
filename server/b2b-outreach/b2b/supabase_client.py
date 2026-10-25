"""Cliente REST de Supabase para el bot B2B.

Usa la API oficial PostgREST (`/rest/v1`). La clave de servicio se lee del
entorno y no se registra. Si no hay URL ni clave, las funciones no hacen nada:
los tests y un arranque sin nube siguen con el JSON local.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

_ID_SOLICITUD = __import__("re").compile(r"^[a-f0-9]{12}$")


def _url() -> str:
    return os.getenv("SUPABASE_URL", "").strip().rstrip("/")


def _clave() -> str:
    servicio = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if servicio:
        return servicio
    return os.getenv("SUPABASE_ANON_KEY", "").strip()


def configurado() -> bool:
    return bool(_url() and _clave())


def _pedir(method: str, path: str, body: dict | list | None = None, prefer: str = "") -> bool:
    if not configurado():
        return False
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {
        "apikey": _clave(),
        "Authorization": "Bearer " + _clave(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    req = urllib.request.Request(_url() + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            resp.read()
            status = getattr(resp, "status", 200)
            return 200 <= int(status) < 300
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        return False


def guardar_lead_b2b(lead: dict) -> bool:
    """Inserta un negocio cazado. Un place_id repetido no duplica la fila."""
    if not configurado() or not isinstance(lead, dict):
        return False
    nombre = str(lead.get("nombre") or "").strip()
    if len(nombre) < 2:
        return False
    place_id = str(lead.get("place_id") or "").strip()
    fila = {
        "nombre": nombre[:180],
        "direccion": str(lead.get("direccion") or "")[:300],
        "ciudad": str(lead.get("ciudad") or "")[:120],
        "pais": str(lead.get("pais") or "")[:80],
        "tipo_establecimiento": str(lead.get("tipo_negocio") or lead.get("tipo") or "")[:80],
        "telefono": str(lead.get("telefono_internacional") or lead.get("telefono") or "")[:40],
        "web": str(lead.get("web") or "")[:300],
        "contacto": str(lead.get("correo") or lead.get("email") or "")[:180],
        "fuente": str(lead.get("fuente") or "google_places")[:40],
    }
    if place_id and not place_id.startswith("fixture-"):
        fila["place_id"] = place_id[:180]
        path = "/rest/v1/leads_b2b?on_conflict=place_id"
        prefer = "resolution=ignore-duplicates,return=minimal"
    else:
        path = "/rest/v1/leads_b2b"
        prefer = "return=minimal"
    return _pedir("POST", path, fila, prefer)


def actualizar_solicitud(solicitud_id: str, estado: str) -> bool:
    if estado not in ("aprobado", "rechazado"):
        return False
    if not _ID_SOLICITUD.match(solicitud_id or ""):
        return False
    if not configurado():
        return False
    from datetime import datetime, timezone

    path = "/rest/v1/solicitudes_precios?id=eq." + solicitud_id
    cuerpo = {
        "estado": estado,
        "actualizado_en": datetime.now(timezone.utc).isoformat(),
    }
    return _pedir("PATCH", path, cuerpo, "return=minimal")
