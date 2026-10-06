from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from b2b.budget import puede_llamar, registrar_llamada
from b2b.country_rules import buscar_pais
from b2b.logging_ops import registrar_presupuesto_agotado
from b2b.paths import FIXTURES

PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,places.websiteUri,"
    "places.nationalPhoneNumber,places.types,places.googleMapsUri,"
    "places.rating,places.userRatingCount"
)

QUERIES_BASE = {
    "distribuidor": [
        "tobacco wholesale distributor {pais}",
        "cigar distributor {pais}",
        "importador tabaco {pais}",
    ],
    "tienda": [
        "cigar shop {pais}",
        "tobacco shop {pais}",
        "tabaquería {pais}",
        "tabac cigares {pais}",
        "sigarenwinkel {pais}",
    ],
    "lounge": ["cigar lounge {pais}", "cigar bar {pais}"],
    "hotel": ["humidor hotel resort {pais}", "luxury hotel cigar {pais}"],
    "casino": ["casino cigar lounge {pais}", "casino tobacco shop {pais}"],
    "duty_free": ["duty free tobacco {pais}", "duty free cigars {pais}"],
}

SOCIAL_PERSONAL = ("instagram.com", "facebook.com/profile", "linkedin.com/in/")


class PresupuestoPlacesAgotado(RuntimeError):
    """Tope diario de llamadas a Google Places alcanzado."""


def _slug(pais: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", pais.lower()).strip("_")


def _api_key() -> str:
    key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "Falta GOOGLE_PLACES_API_KEY en .env (local). Usa --simulado / --dry-run."
        )
    return key


def _es_negocio_b2b(nombre: str, web: str) -> bool:
    nombre_l = nombre.lower()
    if any(x in nombre_l for x in ("private", "personal", "particulier")):
        return False
    if web and any(x in web.lower() for x in SOCIAL_PERSONAL):
        return False
    return True


def _clasificar_tipos(types: list[str], nombre: str) -> str:
    nombre_l = nombre.lower()
    joined = " ".join(types or []).lower()
    if "duty" in nombre_l or "airport" in joined:
        return "duty_free"
    if "distributor" in nombre_l or "wholesale" in nombre_l or "import" in nombre_l:
        return "distribuidor"
    if "casino" in nombre_l or "casino" in joined:
        return "casino"
    if "lounge" in nombre_l or "bar" in joined or "night_club" in joined:
        return "lounge"
    if "hotel" in joined or "lodging" in joined or "resort" in nombre_l:
        return "hotel"
    return "tienda"


def _normalizar_place(raw: dict, pais: str) -> dict[str, Any]:
    nombre = (raw.get("displayName") or {}).get("text") or raw.get("nombre") or "Negocio sin nombre"
    types = raw.get("types") or []
    web = raw.get("websiteUri") or raw.get("web") or ""
    if not web and raw.get("googleMapsUri"):
        web = raw["googleMapsUri"]
    return {
        "nombre": nombre,
        "pais": pais,
        "web": web,
        "telefono": raw.get("nationalPhoneNumber") or raw.get("telefono") or "",
        "direccion": raw.get("formattedAddress") or raw.get("direccion") or "",
        "place_id": raw.get("id") or raw.get("place_id") or "",
        "tipo_negocio": raw.get("tipo_negocio") or _clasificar_tipos(types, nombre),
        "fuente": raw.get("fuente") or "google_places",
        "rating": raw.get("rating"),
        "user_rating_count": raw.get("userRatingCount") or raw.get("user_rating_count"),
    }


def _post_search(text_query: str) -> list[dict]:
    if not puede_llamar():
        registrar_presupuesto_agotado()
        raise PresupuestoPlacesAgotado(
            "Tope diario MAX_PLACES_CALLS_DIA alcanzado. Detén el buscador hasta mañana."
        )
    payload = json.dumps({"textQuery": text_query, "pageSize": 10}).encode("utf-8")
    request = urllib.request.Request(
        PLACES_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": _api_key(),
            "X-Goog-FieldMask": FIELD_MASK,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Google Places respondió {error.code}: {detail}") from error
    registrar_llamada(1)
    return body.get("places") or []


def _fixture_path(pais: str) -> Path:
    slug = _slug(pais)
    candidatos = [
        FIXTURES / f"places_{slug}.json",
        FIXTURES / "places_martinique_sample.json",
    ]
    for path in candidatos:
        if path.is_file():
            return path
    return FIXTURES / "places_martinique_sample.json"


def _consultas_para_pais(pais: str, tipo: str) -> list[str]:
    entry = buscar_pais(pais) or {}
    idiomas = entry.get("idiomas") or ["en"]
    plantillas = list(QUERIES_BASE.get(tipo, QUERIES_BASE["tienda"]))
    if "fr" in idiomas:
        plantillas.extend(
            [
                f"tabac cigares {pais}",
                f"boutique cigare {pais}",
            ]
        )
    if "nl" in idiomas:
        plantillas.extend([f"sigarenwinkel {pais}", f"sigaar lounge {pais}"])
    if "es" in idiomas:
        plantillas.extend([f"tabaquería {pais}", f"importador puros {pais}"])
    if "pt" in idiomas:
        plantillas.extend([f"loja charutos {pais}", f"importador tabaco {pais}"])
    return plantillas


def buscar_en_pais(
    pais: str,
    tipos: list[str],
    limite: int,
    simulado: bool = False,
    tipo_filtro: str = "",
) -> tuple[list[dict], int]:
    if tipo_filtro:
        tipos = [tipo_filtro]
    if simulado:
        path = _fixture_path(pais)
        if not path.is_file():
            return [], 0
        data = json.loads(path.read_text(encoding="utf-8"))
        lugares = [_normalizar_place(p, pais) for p in data.get("places", [])]
        filtrados = [p for p in lugares if _es_negocio_b2b(p["nombre"], p.get("web", ""))]
        return filtrados[:limite], 0

    resultados: list[dict] = []
    vistos: set[str] = set()
    llamadas = 0
    for tipo in tipos:
        for plantilla in _consultas_para_pais(pais, tipo):
            if len(resultados) >= limite:
                break
            if not puede_llamar():
                registrar_presupuesto_agotado()
                return resultados[:limite], llamadas
            consulta = plantilla.format(pais=pais)
            try:
                raw_list = _post_search(consulta)
            except PresupuestoPlacesAgotado:
                return resultados[:limite], llamadas
            llamadas += 1
            for raw in raw_list:
                place = _normalizar_place(raw, pais)
                if not _es_negocio_b2b(place["nombre"], place.get("web", "")):
                    continue
                clave = place.get("place_id") or place.get("nombre", "")
                if clave in vistos:
                    continue
                vistos.add(clave)
                resultados.append(place)
                if len(resultados) >= limite:
                    break
    orden_tipo = {t: i for i, t in enumerate(tipos)}
    resultados.sort(key=lambda p: orden_tipo.get(p.get("tipo_negocio", "tienda"), 99))
    return resultados[:limite], llamadas
