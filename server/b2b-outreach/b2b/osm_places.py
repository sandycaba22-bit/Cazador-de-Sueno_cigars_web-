from __future__ import annotations

import json
import os
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from b2b.country_rules import buscar_pais
from b2b.logging_ops import registrar_osm_fallo
from b2b.paths import data_file

_DEFAULT_MIRRORS = "|".join(
    (
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass.private.coffee/api/interpreter",
        "https://overpass.nchc.org.tw/api/interpreter",
    )
)
OVERPASS_URLS = [
    u.strip() for u in (os.getenv("OSM_OVERPASS_URL", "") or _DEFAULT_MIRRORS).split("|") if u.strip()
]

OVERPASS_TIMEOUT_SEC = 30
_REINTENTOS_ISLA = 3
_ESPERA_ENTRE_REINTENTOS_ISLA = (5, 10, 20)

USER_AGENT = os.getenv(
    "OSM_USER_AGENT",
    "CazadorDeSuenosB2B/1.0 (B2B wholesale outreach; contact: ventas@cazadordesuenocigars.com)",
)
ISO_PATH = data_file("osm_iso3166.json")

NAME_HINT = re.compile(
    r"cigar|humidor|tabac|tobacco|puro|charuto|sigar|smoke\s*shop|"
    r"wholesale|import|distribut|duty\s*free|casino|lounge",
    re.I,
)


class OsmIslaFallida(RuntimeError):
    """Overpass no respondió tras reintentos para un país/isla."""


def _pausa_entre_consultas() -> None:
    try:
        sec = float(os.getenv("OSM_OVERPASS_PAUSE_SEC", "2") or "2")
    except ValueError:
        sec = 2.0
    if sec > 0:
        time.sleep(sec)


def _error_reintentable(error: BaseException) -> bool:
    if isinstance(error, (TimeoutError, socket.timeout)):
        return True
    if isinstance(error, ssl.SSLError):
        return True
    if isinstance(error, urllib.error.URLError):
        return True
    if isinstance(error, urllib.error.HTTPError):
        return error.code in (429, 500, 502, 503, 504)
    if isinstance(error, OSError):
        return True
    return False


def _iso_para_pais(pais: str) -> str:
    entry = buscar_pais(pais) or {}
    iso = (entry.get("iso3166") or entry.get("iso3166_1") or "").strip().upper()
    if iso:
        return iso
    if ISO_PATH.is_file():
        mapping = json.loads(ISO_PATH.read_text(encoding="utf-8"))
        iso = (mapping.get(pais) or mapping.get(entry.get("pais", pais)) or "").strip().upper()
        if iso:
            return iso
    raise ValueError(
        f"Sin código ISO3166-1 para «{pais}». Añade iso3166 en country_rules o en data/osm_iso3166.json"
    )


def _clasificar(nombre: str, tags: dict) -> str:
    shop = (tags.get("shop") or "").lower()
    nombre_l = nombre.lower()
    joined = " ".join(f"{k}={v}" for k, v in tags.items()).lower()
    if "duty" in nombre_l or tags.get("shop") == "duty_free":
        return "duty_free"
    if any(x in nombre_l for x in ("distributor", "wholesale", "import", "importador")):
        return "distribuidor"
    if "casino" in nombre_l or "casino" in joined:
        return "casino"
    if "lounge" in nombre_l or "cigar bar" in nombre_l:
        return "lounge"
    if any(x in joined for x in ("tourism=hotel", "building=hotel")) or "hotel" in nombre_l:
        return "hotel"
    if shop == "tobacco":
        return "tienda"
    return "tienda"


def _direccion_lead(tags: dict) -> str:
    base = _tag(tags, "addr:full", "contact:street", "addr:street", "addr:city")
    zona = (tags.get("_zona_rd") or "").strip()
    if zona and zona.lower() not in base.lower():
        return f"{base}, {zona}, RD".strip(", ") if base else f"{zona}, RD"
    return base


def _tag(tags: dict, *keys: str) -> str:
    for key in keys:
        val = tags.get(key)
        if val:
            return str(val).strip()
    return ""


def _elemento_a_lead(el: dict, pais: str) -> dict | None:
    tags = el.get("tags") or {}
    nombre = _tag(tags, "name", "brand", "operator")
    if not nombre and tags.get("shop") == "tobacco":
        calle = _tag(tags, "addr:street", "addr:place", "addr:city")
        nombre = f"Tobacco shop {calle}".strip() if calle else "Tobacco shop"
    if not nombre:
        return None
    if not NAME_HINT.search(nombre) and tags.get("shop") != "tobacco":
        return None
    lat = el.get("lat")
    lon = el.get("lon")
    if lat is None or lon is None:
        center = el.get("center") or {}
        lat = center.get("lat")
        lon = center.get("lon")
    osm_type = el.get("type") or "node"
    osm_id = el.get("id")
    place_id = f"osm/{osm_type}/{osm_id}" if osm_id is not None else ""
    web = _tag(tags, "website", "contact:website", "url")
    if not web and lat is not None and lon is not None:
        web = f"https://www.openstreetmap.org/{osm_type}/{osm_id}"
    return {
        "nombre": nombre,
        "pais": pais,
        "web": web,
        "telefono": _tag(tags, "phone", "contact:phone", "contact:mobile"),
        "direccion": _direccion_lead(tags),
        "place_id": place_id,
        "tipo_negocio": _clasificar(nombre, tags),
        "fuente": "openstreetmap",
        "osm_shop_tobacco": tags.get("shop") == "tobacco",
    }


def _max_ciudades_rd() -> int:
    try:
        return max(0, int(os.getenv("B2B_RD_CIUDADES_MAX", "8") or "8"))
    except ValueError:
        return 8


def _ciudades_rd() -> list[dict]:
    path = data_file("osm_ciudades_rd.json")
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("ciudades") or [])


def _query_tobacco_around(lat: float, lon: float, radio_m: int) -> str:
    return f"""
[out:json][timeout:25];
(
  node["shop"="tobacco"](around:{radio_m},{lat},{lon});
  way["shop"="tobacco"](around:{radio_m},{lat},{lon});
);
out center 30 tags;
""".strip()


def _query_tobacco(iso: str) -> str:
    return f"""
[out:json][timeout:25];
area["ISO3166-1"="{iso}"][admin_level=2]->.country;
(
  node["shop"="tobacco"](area.country);
  way["shop"="tobacco"](area.country);
);
out center 50 tags;
""".strip()


def _query_nombre_comercial(iso: str) -> str:
    name_re = "cigar|Cigar|tabac|Tabac|tobacco|Tobacco|charuto|puro|humidor|Humidor"
    return f"""
[out:json][timeout:25];
area["ISO3166-1"="{iso}"][admin_level=2]->.country;
(
  node["amenity"="bar"]["name"~"{name_re}"](area.country);
  way["amenity"="bar"]["name"~"{name_re}"](area.country);
);
out center 25 tags;
""".strip()


def _fetch_overpass(query: str, rotar_desde: int = 0) -> list[dict]:
    """Un intento lógico: rota mirrors; timeout fijo 30 s por petición."""
    body = urllib.parse.urlencode({"data": query}).encode("utf-8")
    headers = {"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"}
    urls = OVERPASS_URLS[rotar_desde:] + OVERPASS_URLS[:rotar_desde]
    errors: list[str] = []
    for base_url in urls:
        request = urllib.request.Request(base_url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=OVERPASS_TIMEOUT_SEC) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return payload.get("elements") or []
        except urllib.error.HTTPError as error:
            errors.append(f"{base_url} HTTP {error.code}")
            if not _error_reintentable(error):
                raise RuntimeError("Overpass no respondió: " + errors[-1]) from error
        except BaseException as error:
            if not _error_reintentable(error):
                raise
            errors.append(f"{base_url} {type(error).__name__}: {error}")
    raise RuntimeError("Overpass no respondió: " + " | ".join(errors[-4:]))


def _dedupe_elementos(elementos: list[dict]) -> list[dict]:
    vistos: set[tuple[str, int]] = set()
    out: list[dict] = []
    for el in elementos:
        key = (str(el.get("type") or ""), int(el.get("id") or 0))
        if key in vistos:
            continue
        vistos.add(key)
        out.append(el)
    return out


def _buscar_en_pais_osm_cuerpo(
    pais: str,
    tipos: list[str],
    limite: int,
    tipo_filtro: str,
    iso: str,
    rotar_espejo: int = 0,
) -> tuple[list[dict], int]:
    llamadas = 0
    elementos: list[dict] = []
    _pausa_entre_consultas()
    elementos = _dedupe_elementos(
        _fetch_overpass(_query_tobacco(iso), rotar_desde=rotar_espejo)
    )
    llamadas = 1

    segunda = (os.getenv("OSM_SEGUNDA_PASADA", "0") or "0").strip().lower() not in (
        "0",
        "false",
        "no",
    )
    if segunda and len(elementos) < limite:
        try:
            _pausa_entre_consultas()
            extra = _fetch_overpass(_query_nombre_comercial(iso), rotar_desde=rotar_espejo)
            llamadas += 1
            elementos = _dedupe_elementos(elementos + extra)
        except RuntimeError as error:
            registrar_osm_fallo(pais, f"pasada2: {error}")

    if pais == "Dominican Republic":
        for ciudad in _ciudades_rd()[: _max_ciudades_rd()]:
            try:
                radio_km = float(ciudad.get("radio_km") or 12)
            except (TypeError, ValueError):
                radio_km = 12.0
            radio_m = int(radio_km * 1000)
            try:
                lat = float(ciudad["lat"])
                lon = float(ciudad["lon"])
            except (KeyError, TypeError, ValueError):
                continue
            try:
                _pausa_entre_consultas()
                extra = _fetch_overpass(_query_tobacco_around(lat, lon, radio_m), rotar_desde=rotar_espejo)
                llamadas += 1
                for el in extra:
                    tags = el.get("tags") or {}
                    if not tags.get("_zona_rd"):
                        tags = dict(tags)
                        tags["_zona_rd"] = str(ciudad.get("nombre") or "")
                        el = {**el, "tags": tags}
                elementos = _dedupe_elementos(elementos + extra)
            except RuntimeError as error:
                registrar_osm_fallo(f"RD:{ciudad.get('nombre', '?')}", str(error))

    orden_tipo = {t: i for i, t in enumerate(tipos)}
    candidatos: list[dict] = []
    vistos: set[str] = set()
    for el in elementos:
        lead = _elemento_a_lead(el, pais)
        if not lead:
            continue
        clave = lead.get("place_id") or lead["nombre"].lower()
        if clave in vistos:
            continue
        vistos.add(clave)
        if tipo_filtro and lead.get("tipo_negocio") != tipo_filtro:
            continue
        candidatos.append(lead)
    candidatos.sort(key=lambda p: orden_tipo.get(p.get("tipo_negocio", "tienda"), 99))
    return candidatos[:limite], llamadas


def buscar_en_pais_osm(
    pais: str,
    tipos: list[str],
    limite: int,
    tipo_filtro: str = "",
) -> tuple[list[dict], int]:
    if tipo_filtro:
        tipos = [tipo_filtro]
    iso = _iso_para_pais(pais)
    ultimo_error: RuntimeError | None = None
    for intento in range(_REINTENTOS_ISLA):
        if intento > 0:
            espera = _ESPERA_ENTRE_REINTENTOS_ISLA[intento - 1]
            registrar_osm_fallo(pais, f"reintento isla {intento + 1}/{_REINTENTOS_ISLA} tras {espera}s")
            time.sleep(espera)
        try:
            return _buscar_en_pais_osm_cuerpo(
                pais, tipos, limite, tipo_filtro, iso, rotar_espejo=intento
            )
        except RuntimeError as error:
            ultimo_error = error
            registrar_osm_fallo(pais, f"intento {intento + 1}/{_REINTENTOS_ISLA}: {error}")
    raise OsmIslaFallida(pais, str(ultimo_error or "Overpass sin respuesta"))
