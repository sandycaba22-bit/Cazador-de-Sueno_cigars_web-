from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from b2b.country_rules import buscar_pais
from b2b.paths import data_file

OVERPASS_URLS = [
    u.strip()
    for u in (
        os.getenv("OSM_OVERPASS_URL", "")
        or "https://overpass-api.de/api/interpreter|https://overpass.kumi.systems/api/interpreter"
    ).split("|")
    if u.strip()
]
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
        "direccion": _tag(
            tags,
            "addr:full",
            "contact:street",
            "addr:street",
        ),
        "place_id": place_id,
        "tipo_negocio": _clasificar(nombre, tags),
        "fuente": "openstreetmap",
        "osm_shop_tobacco": tags.get("shop") == "tobacco",
    }


def _query_tobacco(iso: str) -> str:
    return f"""
[out:json][timeout:55];
area["ISO3166-1"="{iso}"][admin_level=2]->.country;
(
  node["shop"="tobacco"](area.country);
  way["shop"="tobacco"](area.country);
);
out center tags 80;
""".strip()


def _query_nombre_comercial(iso: str) -> str:
    name_re = (
        "cigar|Cigar|tabac|Tabac|tobacco|Tobacco|charuto|Charuto|puro|Puro|"
        "humidor|Humidor|tabaquer|Tabaquer|sigar|Sigar|Cigare"
    )
    return f"""
[out:json][timeout:55];
area["ISO3166-1"="{iso}"][admin_level=2]->.country;
(
  node["shop"~"kiosk|convenience"]["name"~"{name_re}"](area.country);
  way["shop"~"kiosk|convenience"]["name"~"{name_re}"](area.country);
  node["amenity"="bar"]["name"~"{name_re}"](area.country);
  way["amenity"="bar"]["name"~"{name_re}"](area.country);
);
out center tags 40;
""".strip()


def _fetch_overpass(query: str) -> list[dict]:
    body = urllib.parse.urlencode({"data": query}).encode("utf-8")
    headers = {"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"}
    errors: list[str] = []
    for base_url in OVERPASS_URLS:
        request = urllib.request.Request(base_url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return payload.get("elements") or []
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:200]
            errors.append(f"{base_url} → HTTP {error.code}: {detail}")
        except urllib.error.URLError as error:
            errors.append(f"{base_url} → {error}")
        except TimeoutError as error:
            errors.append(f"{base_url} → timeout: {error}")
    raise RuntimeError("Overpass no respondió: " + " | ".join(errors))


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


def buscar_en_pais_osm(
    pais: str,
    tipos: list[str],
    limite: int,
    tipo_filtro: str = "",
) -> tuple[list[dict], int]:
    if tipo_filtro:
        tipos = [tipo_filtro]
    iso = _iso_para_pais(pais)
    elementos = _dedupe_elementos(_fetch_overpass(_query_tobacco(iso)))
    llamadas = 1
    if len(elementos) < limite:
        try:
            extra = _fetch_overpass(_query_nombre_comercial(iso))
            llamadas += 1
            elementos = _dedupe_elementos(elementos + extra)
        except RuntimeError:
            pass
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
