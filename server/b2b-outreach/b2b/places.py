from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from b2b import budget
from b2b.contacto_web import normalizar_canales
from b2b.country_rules import buscar_pais
from b2b.logging_ops import registrar_evento, registrar_presupuesto_agotado
from b2b.paths import FIXTURES, state_file

PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,places.location,"
    "places.nationalPhoneNumber,places.internationalPhoneNumber,places.websiteUri,"
    "places.googleMapsUri,places.businessStatus,places.rating,places.userRatingCount,places.types"
)
PAGE_SIZE = 20

# (tipo de negocio, idioma, término). "*" = se busca en toda isla.
TERMINOS_GOOGLE: tuple[tuple[str, str, str], ...] = (
    ("tienda", "*", "cigar shop"),
    ("tienda", "en", "tobacconist"),
    ("tienda", "es", "tabaquería"),
    ("tienda", "nl", "sigarenwinkel"),
    ("tienda", "fr", "cave à cigares"),
    ("lounge", "*", "cigar lounge"),
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

SOCIAL_PERSONAL = ("facebook.com/profile", "linkedin.com/in/")

# Tras un 400/401/403 (clave inválida o API no habilitada) no se insiste en este proceso.
_GOOGLE_DESACTIVADO: dict[str, str] = {}


class PresupuestoPlacesAgotado(RuntimeError):
    """Tope diario o mensual de llamadas a Google Places alcanzado."""


def _slug(pais: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", pais.lower()).strip("_")


def _api_key() -> str:
    key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Falta GOOGLE_PLACES_API_KEY; se usa OpenStreetMap.")
    return key


def google_disponible() -> bool:
    return bool(os.getenv("GOOGLE_PLACES_API_KEY", "").strip()) and not _GOOGLE_DESACTIVADO


def _sin_clave(texto: str) -> str:
    key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
    texto = texto or ""
    if key:
        texto = texto.replace(key, "***")
    return re.sub(r"AIza[0-9A-Za-z_\-]{20,}", "***", texto)


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


def _normalizar_place(raw: dict, pais: str, tipo_consulta: str = "") -> dict[str, Any]:
    nombre = (raw.get("displayName") or {}).get("text") or raw.get("nombre") or "Negocio sin nombre"
    types = raw.get("types") or []
    tipo = raw.get("tipo_negocio") or _clasificar_tipos(types, nombre)
    if tipo == "tienda" and tipo_consulta == "lounge":
        tipo = "lounge"
    loc = raw.get("location") or {}
    intl = raw.get("internationalPhoneNumber") or ""
    lead = {
        "nombre": nombre,
        "pais": pais,
        "web": raw.get("websiteUri") or raw.get("web") or "",
        "maps_url": raw.get("googleMapsUri") or raw.get("maps_url") or "",
        "telefono": raw.get("nationalPhoneNumber") or intl or raw.get("telefono") or "",
        "telefono_internacional": intl,
        "direccion": raw.get("formattedAddress") or raw.get("direccion") or "",
        "place_id": raw.get("id") or raw.get("place_id") or "",
        "tipo_negocio": tipo,
        "fuente": raw.get("fuente") or "google_places",
        "rating": raw.get("rating"),
        "user_rating_count": raw.get("userRatingCount") or raw.get("user_rating_count"),
        "business_status": raw.get("businessStatus") or raw.get("business_status") or "",
        "types": list(types),
    }
    if loc.get("latitude") is not None:
        lead["lat"] = loc.get("latitude")
        lead["lon"] = loc.get("longitude")
    return normalizar_canales(lead)


# --- Caché mensual (búsquedas por isla+término) y lugares por place_id ----------------


def cache_path() -> Path:
    return state_file("google_places_cache.json")


def _mes() -> str:
    return datetime.now().strftime("%Y-%m")


def _load_cache() -> dict:
    path = cache_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("busquedas", {})
                data.setdefault("places", {})
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {"busquedas": {}, "places": {}}


def _save_cache(data: dict) -> None:
    mes = _mes()
    data["busquedas"] = {k: v for k, v in data["busquedas"].items() if k.startswith(mes + "|")}
    vivos = {pid for v in data["busquedas"].values() for pid in v.get("ids", [])}
    data["places"] = {pid: raw for pid, raw in data["places"].items() if pid in vivos}
    path = cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def _clave_busqueda(pais: str, consulta: str) -> str:
    return f"{_mes()}|{pais}|{consulta}"


def isla_buscada_este_mes(pais: str, consultas: list[str] | None = None) -> bool:
    data = _load_cache()
    consultas = consultas if consultas is not None else [c for _t, _i, c in consultas_google(pais, [])]
    return bool(consultas) and all(_clave_busqueda(pais, c) in data["busquedas"] for c in consultas)


# --- Llamada a la API -------------------------------------------------------------------


def _post_search(text_query: str, idioma: str = "") -> list[dict]:
    """Una sola llamada places:searchText (sin Place Details)."""
    motivo = budget.motivo_bloqueo()
    if motivo:
        raise PresupuestoPlacesAgotado(motivo)
    cuerpo: dict[str, Any] = {"textQuery": text_query, "pageSize": PAGE_SIZE}
    if idioma:
        cuerpo["languageCode"] = idioma
    request = urllib.request.Request(
        PLACES_URL,
        data=json.dumps(cuerpo).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": _api_key(),
            "X-Goog-FieldMask": FIELD_MASK,
        },
        method="POST",
    )
    budget.registrar_llamada(1)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detalle = _sin_clave(error.read().decode("utf-8", errors="replace"))[:300]
        if error.code in (400, 401, 403):
            _GOOGLE_DESACTIVADO["motivo"] = f"HTTP {error.code}"
        raise RuntimeError(f"Google Places respondió {error.code}: {detalle}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise RuntimeError(f"Google Places sin respuesta: {_sin_clave(str(error))[:200]}") from None
    return body.get("places") or []


def consultas_google(pais: str, tipos: list[str]) -> list[tuple[str, str, str]]:
    """(tipo, idioma, texto) por isla, en los idiomas locales de country_rules."""
    entry = buscar_pais(pais) or {}
    idiomas = list(entry.get("idiomas") or ["en"])
    tipos_ok = set(tipos) if tipos else {"tienda", "lounge"}
    out: list[tuple[str, str, str]] = []
    for tipo, idioma, termino in TERMINOS_GOOGLE:
        if tipo not in tipos_ok:
            continue
        if idioma != "*" and idioma not in idiomas:
            continue
        lang = idioma if idioma != "*" else ("en" if "en" in idiomas else idiomas[0])
        out.append((tipo, lang, f"{termino} {pais}"))
    return out


def _avisar_tope(motivo: str) -> None:
    if not budget.marcar_aviso(motivo):
        return
    registrar_presupuesto_agotado()
    est = budget.estado()
    if motivo == "mensual":
        texto = (
            f"⛔ Google Places: tope mensual alcanzado ({est['mes']}/{est['max_mes']} búsquedas). "
            "Sigo solo con OpenStreetMap hasta el mes que viene."
        )
    else:
        texto = (
            f"⛔ Google Places: tope diario alcanzado ({est['dia']}/{est['max_dia']} búsquedas). "
            "Sigo solo con OpenStreetMap y retomo Google mañana."
        )
    from b2b.telegram_buscar import notificar_buscar

    notificar_buscar(texto, simulado=False)


def _orden_calidad(lead: dict) -> tuple:
    try:
        rating = float(lead.get("rating") or 0)
    except (TypeError, ValueError):
        rating = 0.0
    try:
        reviews = int(lead.get("user_rating_count") or 0)
    except (TypeError, ValueError):
        reviews = 0
    return (-rating, -reviews, lead.get("nombre") or "")


def buscar_google_pais(pais: str, tipos: list[str]) -> tuple[list[dict], int, dict]:
    """Google Places (New) por isla y tipo. Devuelve leads OPERATIONAL ordenados, llamadas, stats."""
    cache = _load_cache()
    stats: dict = {"google": 0, "google_llamadas": 0, "google_cache": 0, "descartes": []}
    vistos: dict[str, tuple[dict, str]] = {}
    llamadas = 0
    for tipo, idioma, consulta in consultas_google(pais, tipos):
        clave = _clave_busqueda(pais, consulta)
        hit = cache["busquedas"].get(clave)
        if hit is not None:
            raws = [cache["places"][pid] for pid in hit.get("ids", []) if pid in cache["places"]]
            stats["google_cache"] += 1
        else:
            motivo = budget.motivo_bloqueo()
            if motivo:
                stats["presupuesto_agotado"] = motivo
                _avisar_tope(motivo)
                break
            try:
                raws = _post_search(consulta, idioma)
            except PresupuestoPlacesAgotado as error:
                stats["presupuesto_agotado"] = str(error)
                _avisar_tope(str(error))
                break
            llamadas += 1
            ids = []
            for raw in raws:
                pid = raw.get("id")
                if pid:
                    cache["places"][pid] = raw
                    ids.append(pid)
            cache["busquedas"][clave] = {
                "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "ids": ids,
            }
            _save_cache(cache)
        for raw in raws:
            pid = raw.get("id") or raw.get("place_id") or ""
            if pid and pid not in vistos:
                vistos[pid] = (raw, tipo)

    leads: list[dict] = []
    for raw, tipo in vistos.values():
        lead = _normalizar_place(raw, pais, tipo)
        estado = lead.get("business_status") or "sin estado"
        if estado != "OPERATIONAL":
            stats["descartes"].append(
                {"nombre": lead["nombre"], "motivo": f"Google: {estado}", "etapa": "google_estado",
                 "fuente": "google_places"}
            )
            continue
        if not _es_negocio_b2b(lead["nombre"], raw.get("websiteUri") or ""):
            stats["descartes"].append(
                {"nombre": lead["nombre"], "motivo": "perfil personal", "etapa": "google_estado",
                 "fuente": "google_places"}
            )
            continue
        leads.append(lead)
    leads.sort(key=_orden_calidad)
    stats["google"] = len(leads)
    stats["google_llamadas"] = llamadas
    return leads, llamadas, stats


# --- Fixtures (--simulado) -----------------------------------------------------------


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
        plantillas.extend([f"tabac cigares {pais}", f"boutique cigare {pais}"])
    if "nl" in idiomas:
        plantillas.extend([f"sigarenwinkel {pais}", f"sigaar lounge {pais}"])
    if "es" in idiomas:
        plantillas.extend([f"tabaquería {pais}", f"importador puros {pais}"])
    if "pt" in idiomas:
        plantillas.extend([f"loja charutos {pais}", f"importador tabaco {pais}"])
    return plantillas


# --- Despacho por fuente ---------------------------------------------------------------


def _buscar_osm(pais, tipos, limite, tipo_filtro, modo_global) -> tuple[list[dict], int, dict]:
    if modo_global:
        from b2b.buscar_global import recolectar_leads_global

        return recolectar_leads_global(pais, tipos, limite, tipo_filtro=tipo_filtro, simulado=False)
    from b2b.buscar_pais import recolectar_leads_pais

    return recolectar_leads_pais(pais, tipos, limite, tipo_filtro=tipo_filtro, simulado=False)


def _buscar_google_seguro(pais: str, tipos: list[str]) -> tuple[list[dict], int, dict]:
    if not google_disponible():
        motivo = _GOOGLE_DESACTIVADO.get("motivo") or "sin GOOGLE_PLACES_API_KEY"
        return [], 0, {"google_omitido": motivo, "descartes": []}
    try:
        return buscar_google_pais(pais, tipos)
    except RuntimeError as error:
        msg = _sin_clave(str(error))[:300]
        registrar_evento({"evento": "google_places_error", "pais": pais, "error": msg})
        return [], 0, {"google_error": msg, "descartes": []}


def buscar_en_pais(
    pais: str,
    tipos: list[str],
    limite: int,
    simulado: bool = False,
    tipo_filtro: str = "",
    fuente: str = "",
    modo_global: bool = False,
) -> tuple[list[dict], int, dict]:
    """
    fuente: osm | google (Google y OSM solo si Google no da nada) | ambas (Google primero + OSM).
    Sin clave o con el tope agotado, Google se omite y sigue OSM.
    """
    if tipo_filtro:
        tipos = [tipo_filtro]
    if simulado:
        path = _fixture_path(pais)
        if not path.is_file():
            return [], 0, {}
        data = json.loads(path.read_text(encoding="utf-8"))
        lugares = [_normalizar_place(p, pais) for p in data.get("places", [])]
        filtrados = [p for p in lugares if _es_negocio_b2b(p["nombre"], p.get("web", ""))]
        return filtrados[:limite], 0, {}
    if fuente not in ("google", "ambas"):
        return _buscar_osm(pais, tipos, limite, tipo_filtro, modo_global)

    g_leads, g_llamadas, g_stats = _buscar_google_seguro(pais, tipos)
    g_descartes = list(g_stats.pop("descartes", []) or [])
    if fuente == "google" and g_leads:
        return g_leads, g_llamadas, {**g_stats, "descartes": g_descartes}

    from b2b.buscar_filtros import combinar_fuentes
    from b2b.osm_places import OsmIslaFallida

    try:
        o_leads, o_llamadas, o_stats = _buscar_osm(pais, tipos, limite, tipo_filtro, modo_global)
    except (OsmIslaFallida, RuntimeError, ValueError):
        if not g_leads:
            raise
        o_leads, o_llamadas, o_stats = [], 0, {"osm_error": "OSM sin respuesta; solo Google"}
    fusiones: list[dict] = []
    todos = combinar_fuentes(g_leads, o_leads, fusiones)
    stats = dict(o_stats or {})
    stats.update(g_stats)
    stats["descartes"] = g_descartes + list(stats.get("descartes") or []) + fusiones
    return todos, g_llamadas + o_llamadas, stats
