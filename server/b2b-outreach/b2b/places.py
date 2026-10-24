from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from b2b import budget
from b2b.contacto_web import normalizar_canales
from b2b.country_rules import buscar_pais
from b2b.logging_ops import registrar_evento, registrar_presupuesto_agotado
from b2b.mercados import (
    guardar_cursor,
    mercado_por_nombre,
    siguiente_mercado,
)
from b2b.paths import FIXTURES, state_file
from b2b.telefono import internacional

PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,"
    "places.nationalPhoneNumber,places.internationalPhoneNumber,"
    "places.websiteUri,places.googleMapsUri,"
    "places.rating,places.userRatingCount,places.businessStatus,places.types,nextPageToken"
)
PAGE_SIZE = 20
MAPS_PLACE_URL = "https://www.google.com/maps/search/?api=1&query={nombre}&query_place_id={pid}"
_CAMPOS_CRUDOS = (
    "websiteUri",
    "nationalPhoneNumber",
    "internationalPhoneNumber",
    "rating",
    "userRatingCount",
    "businessStatus",
    "googleMapsUri",
)
_TIPOS_BAR = {"bar", "night_club", "cafe", "restaurant"}
_TIPOS_LICOR = {"liquor_store"}

# (tipo de negocio, idioma, término). Todos los términos en EN.
TERMINOS_GOOGLE: tuple[tuple[str, str, str], ...] = (
    ("tienda", "en", "cigar shop"),
    ("lounge", "en", "cigar lounge"),
    ("lounge", "en", "cigar bar"),
    ("tienda", "en", "tobacconist"),
    ("tienda", "en", "cigar distributor"),
    ("tienda", "en", "tobacco wholesaler"),
    ("tienda", "en", "humidor"),
    ("lounge", "en", "hotel resort cigar lounge"),
    ("lounge", "en", "steakhouse humidor"),
    ("lounge", "en", "casino cigar room"),
    ("lounge", "en", "golf club cigar lounge"),
    ("tienda", "en", "liquor store humidor"),
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

# Tras cualquier error de Google (4xx, 5xx o sin respuesta) no se insiste en este proceso.
_GOOGLE_DESACTIVADO: dict[str, str] = {}

EXPLICACION_HTTP = {
    0: "sin respuesta",
    400: "petición inválida",
    401: "clave inválida",
    403: "clave inválida o Places API (New) no habilitada",
    429: "cuota de Google agotada",
}


class PresupuestoPlacesAgotado(RuntimeError):
    """Tope de la tanda, diario o mensual de llamadas a Google Places alcanzado."""


class GooglePlacesError(RuntimeError):
    """Error HTTP o de red de Google Places; ``codigo`` 0 = sin respuesta."""

    def __init__(self, codigo: int, mensaje: str):
        super().__init__(mensaje)
        self.codigo = codigo


def _slug(pais: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", pais.lower()).strip("_")


def _api_key() -> str:
    key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Falta GOOGLE_PLACES_API_KEY; no se busca sin Google Places.")
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
    nacional = raw.get("nationalPhoneNumber") or ""
    intl = raw.get("internationalPhoneNumber") or internacional(pais, nacional)
    google_id = raw.get("id") or ""
    maps = raw.get("googleMapsUri") or raw.get("maps_url") or ""
    if not maps and google_id:
        maps = MAPS_PLACE_URL.format(nombre=urllib.parse.quote(nombre), pid=urllib.parse.quote(google_id))
    lead = {
        "nombre": nombre,
        "pais": pais,
        "web": raw.get("websiteUri") or raw.get("web") or "",
        "maps_url": maps,
        "telefono": nacional or intl or raw.get("telefono") or "",
        "telefono_internacional": intl,
        "direccion": raw.get("formattedAddress") or raw.get("direccion") or "",
        "place_id": google_id or raw.get("place_id") or "",
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


def islas_agotadas_google(paises: list[str]) -> bool:
    """True si todas las islas de la lista ya se buscaron en Google este mes."""
    return bool(paises) and all(isla_buscada_este_mes(p) for p in paises)


# --- Llamada a la API -------------------------------------------------------------------


def _post_search(text_query: str, idioma: str = "") -> list[dict]:
    """Text Search con paginación completa (sin Place Details)."""
    motivo = budget.motivo_bloqueo()
    if motivo:
        raise PresupuestoPlacesAgotado(motivo)
    resultados: list[dict] = []
    token = ""
    while True:
        motivo = budget.motivo_bloqueo()
        if motivo:
            raise PresupuestoPlacesAgotado(motivo)
        cuerpo: dict[str, Any] = {"textQuery": text_query, "pageSize": PAGE_SIZE}
        if idioma:
            cuerpo["languageCode"] = idioma
        if token:
            cuerpo["pageToken"] = token
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
            _GOOGLE_DESACTIVADO["motivo"] = f"HTTP {error.code}"
            raise GooglePlacesError(error.code, f"Google Places respondió {error.code}: {detalle}") from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
            _GOOGLE_DESACTIVADO["motivo"] = "sin respuesta"
            raise GooglePlacesError(0, f"Google Places sin respuesta: {_sin_clave(str(error))[:200]}") from None
        resultados.extend(body.get("places") or [])
        token = body.get("nextPageToken") or ""
        if not token:
            break
    return resultados


def _log_place_crudo(raw: dict) -> None:
    """Un local por búsqueda: qué campos devolvió Google (presentes vs vacíos)."""
    nombre = (raw.get("displayName") or {}).get("text") or raw.get("nombre") or ""
    presentes = {campo: campo in raw for campo in _CAMPOS_CRUDOS}
    valores = {}
    for campo in _CAMPOS_CRUDOS:
        valor = raw.get(campo)
        if isinstance(valor, (dict, list)):
            valores[campo] = "obj"
        else:
            valores[campo] = valor
    ausentes = [campo for campo, ok in presentes.items() if not ok]
    registrar_evento(
        {
            "evento": "google_place_crudo",
            "nombre": nombre,
            "place_id": raw.get("id") or "",
            "campos_presentes": presentes,
            "ausentes": ausentes,
            "valores": valores,
        }
    )
    print(
        "Google crudo: "
        f"{nombre or 'sin nombre'} "
        f"status={valores.get('businessStatus') or 'ausente'} "
        f"tel_nacional={'sí' if valores.get('nationalPhoneNumber') else 'no'} "
        f"tel_internacional={'sí' if valores.get('internationalPhoneNumber') else 'no'} "
        f"web={'sí' if valores.get('websiteUri') else 'no'} "
        f"maps={'sí' if valores.get('googleMapsUri') else 'no'} "
        f"rating={valores.get('rating') if valores.get('rating') is not None else 'ausente'} "
        f"reseñas={valores.get('userRatingCount') if valores.get('userRatingCount') is not None else 'ausente'} "
        f"ausentes={','.join(ausentes) or 'ninguno'}",
        file=sys.stderr,
    )


def motivo_descarte_google(raw: dict, lead: dict) -> str:
    """'' si el local está OPERATIONAL y no cae en las exclusiones ya existentes.

    Teléfono, web, rating y reseñas no descartan: solo ordenan y se muestran en el aviso.
    """
    estado = (raw.get("businessStatus") or lead.get("business_status") or "").strip() or "sin estado"
    if estado != "OPERATIONAL":
        return f"Google: {estado}"
    nombre = lead.get("nombre") or ""
    web = lead.get("web") or ""
    telefono = (lead.get("telefono") or lead.get("telefono_internacional") or "").strip()
    if not telefono and not (web or "").strip():
        return "sin teléfono ni web"
    if not _es_negocio_b2b(nombre, web):
        return "perfil personal"
    from b2b.nombres_busqueda import clasificar_aceptacion, contiene_fuerte, texto_nombre_web

    bucket, motivo = clasificar_aceptacion(lead)
    if bucket == "excluido":
        return motivo
    types = {str(tipo).lower() for tipo in (raw.get("types") or lead.get("types") or [])}
    texto = texto_nombre_web(lead)
    senal_cigarro = "humidor" in texto.lower() or contiene_fuerte(texto)
    if not senal_cigarro and types & _TIPOS_LICOR:
        return "licorería sin humidor"
    if not senal_cigarro and types & _TIPOS_BAR:
        return "bar/café sin humidor"
    return ""


def consultas_google(pais: str, tipos: list[str]) -> list[tuple[str, str, str]]:
    """(tipo, idioma, texto) por estado/ciudad. Mercado inactivo o desconocido: lista vacía."""
    mercado = mercado_por_nombre(pais, solo_activos=True)
    if mercado is None:
        return []
    ciudades = list(mercado.get("ciudades") or [])
    tipos_ok = set(tipos) if tipos else {"tienda", "lounge"}
    out: list[tuple[str, str, str]] = []
    nombre = mercado.get("nombre") or pais
    if not ciudades:
        ciudades = [nombre]
    for tipo, _idioma, termino in TERMINOS_GOOGLE:
        if tipo not in tipos_ok:
            continue
        for ciudad in ciudades:
            consulta = f"{termino} in {ciudad}, {nombre}"
            out.append((tipo, "en", consulta))
    return out


def _continua_con_osm() -> bool:
    from b2b.fuente_leads import resolver_fuente_leads

    return resolver_fuente_leads() != "google"


def _avisar_tope(motivo: str) -> None:
    if not budget.marcar_aviso(motivo):
        return
    registrar_presupuesto_agotado()
    est = budget.estado()
    if _continua_con_osm():
        respaldo_mes = "Sigo solo con OpenStreetMap hasta el mes que viene."
        respaldo_tanda = "Sigo con OpenStreetMap y retomo Google"
        respaldo_dia = "Sigo solo con OpenStreetMap y retomo Google mañana."
    else:
        respaldo_mes = "En este modo no consulto OpenStreetMap."
        respaldo_tanda = "No consulto OpenStreetMap. Retomo Google"
        respaldo_dia = "En este modo no consulto OpenStreetMap. Retomo Google mañana."
    if motivo == "mensual":
        texto = (
            f"⛔ Google Places: tope mensual alcanzado ({est['mes']}/{est['max_mes']} búsquedas). "
            f"{respaldo_mes}"
        )
    elif motivo == "tanda":
        nombre = "de la mañana" if est["tanda"] == "manana" else "de la tarde"
        retomo = "en la tanda de la tarde (15:00)" if est["tanda"] == "manana" else "mañana a las 09:00"
        texto = (
            f"⏸️ Google Places: tanda {nombre} completa ({est['tanda_llamadas']}/{est['max_tanda']} "
            f"búsquedas). {respaldo_tanda} {retomo}."
        )
    else:
        texto = (
            f"⛔ Google Places: tope diario alcanzado ({est['dia']}/{est['max_dia']} búsquedas). "
            f"{respaldo_dia}"
        )
    _notificar(texto)


def _notificar(texto: str) -> None:
    from b2b.telegram_buscar import notificar_buscar

    notificar_buscar(texto, simulado=False)


def _avisar_error(error: GooglePlacesError) -> None:
    codigo = error.codigo
    registrar_evento({"evento": "google_places_error", "codigo": codigo, "error": _sin_clave(str(error))[:300]})
    if not budget.marcar_aviso(f"error_{codigo}"):
        return
    explicacion = EXPLICACION_HTTP.get(codigo) or ("error de Google" if codigo >= 500 else "error")
    etiqueta = f"respondió {codigo}" if codigo else "no respondió"
    if _continua_con_osm():
        sigue = "En esta corrida sigo solo con OpenStreetMap."
    else:
        sigue = "En esta corrida no consulto OpenStreetMap."
    _notificar(f"⚠️ Google Places {etiqueta} ({explicacion}). {sigue}")


def _orden_calidad(lead: dict) -> tuple:
    try:
        rating = float(lead.get("rating") or 0)
    except (TypeError, ValueError):
        rating = 0.0
    try:
        reviews = int(lead.get("user_rating_count") or 0)
    except (TypeError, ValueError):
        reviews = 0
    mail = 1 if (lead.get("correo") or "").strip() else 0
    tel = 1 if (lead.get("telefono") or "").strip() else 0
    return (0 if (mail or tel) else 1, -mail, -tel, -rating, -reviews, lead.get("nombre") or "")


def _avanzar_cursor(pais: str, idx: int, total: int) -> None:
    siguiente_idx = idx + 1
    if siguiente_idx >= total:
        nxt = siguiente_mercado(pais)
        guardar_cursor((nxt or {}).get("nombre") or pais, 0)
    else:
        guardar_cursor(pais, siguiente_idx)


def buscar_google_pais(
    pais: str,
    tipos: list[str],
    *,
    desde_consulta: int = 0,
    persistir_cursor: bool = False,
) -> tuple[list[dict], int, dict]:
    """Google Places (New) por estado/ciudad. Devuelve leads OPERATIONAL, llamadas, stats."""
    cache = _load_cache()
    stats: dict = {"google": 0, "google_llamadas": 0, "google_cache": 0, "descartes": [], "pais": pais}
    vistos: dict[str, tuple[dict, str]] = {}
    telefonos_vistos: set[str] = set()
    llamadas = 0
    crudo_logueado = False
    consultas = consultas_google(pais, tipos)
    stats["consultas_total"] = len(consultas)
    stats["consulta_inicio"] = max(0, desde_consulta)
    if persistir_cursor and not consultas:
        nxt = siguiente_mercado(pais)
        guardar_cursor((nxt or {}).get("nombre") or pais, 0)
        stats["mercado_omitido"] = "inactivo"
        return [], 0, stats
    for idx, (tipo, idioma, consulta) in enumerate(consultas):
        if idx < desde_consulta:
            continue
        clave = _clave_busqueda(pais, consulta)
        hit = cache["busquedas"].get(clave)
        if hit is not None:
            raws = [cache["places"][pid] for pid in hit.get("ids", []) if pid in cache["places"]]
            stats["google_cache"] += 1
        else:
            if _GOOGLE_DESACTIVADO:
                stats["google_omitido"] = _GOOGLE_DESACTIVADO.get("motivo", "")
                if persistir_cursor:
                    guardar_cursor(pais, idx)
                break
            motivo = budget.motivo_bloqueo()
            if motivo:
                stats["presupuesto_agotado"] = motivo
                if persistir_cursor:
                    guardar_cursor(pais, idx)
                _avisar_tope(motivo)
                break
            try:
                raws = _post_search(consulta, idioma)
            except PresupuestoPlacesAgotado as error:
                stats["presupuesto_agotado"] = str(error)
                if persistir_cursor:
                    guardar_cursor(pais, idx)
                _avisar_tope(str(error))
                break
            except GooglePlacesError as error:
                stats["google_error"] = _sin_clave(str(error))[:300]
                if persistir_cursor:
                    guardar_cursor(pais, idx)
                _avisar_error(error)
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
            if not crudo_logueado and isinstance(raw, dict):
                _log_place_crudo(raw)
                crudo_logueado = True
            pid = raw.get("id") or raw.get("place_id") or ""
            if pid and pid not in vistos:
                vistos[pid] = (raw, tipo)
        if persistir_cursor:
            _avanzar_cursor(pais, idx, len(consultas))

    leads: list[dict] = []
    for raw, tipo in vistos.values():
        lead = _normalizar_place(raw, pais, tipo)
        motivo = motivo_descarte_google(raw, lead)
        if motivo:
            etapa = "google_exclusion" if not motivo.startswith("Google:") and motivo != "perfil personal" else "google_estado"
            stats["descartes"].append(
                {"nombre": lead["nombre"], "motivo": motivo, "etapa": etapa,
                 "fuente": "google_places", "maps_url": lead.get("maps_url", "")}
            )
            continue
        tel = re.sub(r"\D", "", lead.get("telefono_internacional") or lead.get("telefono") or "")
        if tel and tel in telefonos_vistos:
            stats["descartes"].append(
                {"nombre": lead["nombre"], "motivo": "duplicado teléfono", "etapa": "google_dedupe",
                 "fuente": "google_places", "maps_url": lead.get("maps_url", "")}
            )
            continue
        if tel:
            telefonos_vistos.add(tel)
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
        FIXTURES / "places_usa_sample.json",
    ]
    for path in candidatos:
        if path.is_file():
            return path
    return FIXTURES / "places_usa_sample.json"


def _consultas_para_pais(pais: str, tipo: str) -> list[str]:
    entry = buscar_pais(pais) or {}
    idiomas = entry.get("idiomas") or ["en"]
    plantillas = list(QUERIES_BASE.get(tipo, QUERIES_BASE["tienda"]))
    if "es" in idiomas:
        plantillas.extend([f"tabaquería {pais}", f"importador puros {pais}"])
    return plantillas


# --- Despacho por fuente ---------------------------------------------------------------


def _buscar_osm(pais, tipos, limite, tipo_filtro, modo_global) -> tuple[list[dict], int, dict]:
    if modo_global:
        from b2b.buscar_global import recolectar_leads_global

        return recolectar_leads_global(pais, tipos, limite, tipo_filtro=tipo_filtro, simulado=False)
    from b2b.buscar_pais import recolectar_leads_pais

    return recolectar_leads_pais(pais, tipos, limite, tipo_filtro=tipo_filtro, simulado=False)


def _buscar_google_seguro(
    pais: str,
    tipos: list[str],
    *,
    desde_consulta: int = 0,
    persistir_cursor: bool = False,
) -> tuple[list[dict], int, dict]:
    if not google_disponible():
        motivo = _GOOGLE_DESACTIVADO.get("motivo") or "sin GOOGLE_PLACES_API_KEY"
        return [], 0, {"google_omitido": motivo, "descartes": []}
    try:
        return buscar_google_pais(
            pais, tipos, desde_consulta=desde_consulta, persistir_cursor=persistir_cursor
        )
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
    desde_consulta: int = 0,
    persistir_cursor: bool = False,
) -> tuple[list[dict], int, dict]:
    """
    fuente: osm | google (solo Google, nunca OSM) | ambas (Google primero + OSM).
    Sin clave o con el tope agotado, google no llama a OSM; ambas/osm sí pueden usar OSM.
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

    g_leads, g_llamadas, g_stats = _buscar_google_seguro(
        pais, tipos, desde_consulta=desde_consulta, persistir_cursor=persistir_cursor
    )
    g_descartes = list(g_stats.pop("descartes", []) or [])
    if fuente == "google":
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
