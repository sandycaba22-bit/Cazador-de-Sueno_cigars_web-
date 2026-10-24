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

from b2b.buscar_filtros import descartar_lead_osm, motivo_descarte_osm
from b2b.nombres_busqueda import clasificar_aceptacion, overpass_regex_alternativas
from b2b.country_rules import buscar_pais
from b2b.logging_ops import registrar_evento, registrar_osm_fallo
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

OVERPASS_TIMEOUT_SEC = 15
_REINTENTOS_ISLA = 2
_TOPE_SEGUNDOS_ISLA = 120
_ESPERA_ENTRE_REINTENTOS_ISLA = (5,)
_deadline_isla: float | None = None

USER_AGENT = os.getenv(
    "OSM_USER_AGENT",
    "CazadorDeSuenosB2B/1.0 (B2B wholesale outreach; contact: cazadordesueno1@gmail.com)",
)
ISO_PATH = data_file("osm_iso3166.json")

BBOX_PATH = data_file("osm_bbox_fallback.json")


def _regex_nombre_fuertes() -> str:
    return overpass_regex_alternativas("fuertes")


def _regex_nombre_debiles() -> str:
    return overpass_regex_alternativas("debiles")


class OsmIslaFallida(RuntimeError):
    """Overpass no respondió tras reintentos para un país/isla."""


class OsmTopeIsla(Exception):
    """Se agotaron los 2 minutos de esta isla. No es RuntimeError: no se traga en los reintentos internos."""


def _pausa_entre_consultas() -> None:
    try:
        sec = float(os.getenv("OSM_OVERPASS_PAUSE_SEC", "2") or "2")
    except ValueError:
        sec = 2.0
    if _deadline_isla is not None:
        restante = _deadline_isla - time.monotonic()
        if restante <= 0:
            raise OsmTopeIsla("OSM: tope de 2 minutos por isla")
        sec = min(sec, restante)
    if sec > 0:
        time.sleep(sec)


def _timeout_peticion() -> float:
    if _deadline_isla is None:
        return float(OVERPASS_TIMEOUT_SEC)
    restante = _deadline_isla - time.monotonic()
    if restante <= 0:
        raise OsmTopeIsla("OSM: tope de 2 minutos por isla")
    return min(float(OVERPASS_TIMEOUT_SEC), restante)


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


def _nombre_log_osm(el: dict, tags: dict) -> str:
    nombre = _tag(tags, "name", "brand", "operator")
    if nombre:
        return nombre
    osm_type = el.get("type") or "node"
    osm_id = el.get("id")
    if osm_id is not None:
        return f"{osm_type}/{osm_id}"
    return "—"


def _motivo_si_sin_lead(el: dict, pais: str) -> str:
    tags = el.get("tags") or {}
    nombre = _tag(tags, "name", "brand", "operator")
    if not nombre and tags.get("shop") in ("tobacco", "cigar"):
        calle = _tag(tags, "addr:street", "addr:place", "addr:city")
        nombre = f"Tobacco shop {calle}".strip() if calle else "Tobacco shop"
    if not nombre:
        return "sin nombre"
    etiqueta = motivo_descarte_osm(nombre, tags)
    if etiqueta:
        return etiqueta
    shop = tags.get("shop") or ""
    if shop == "e-cigarette":
        return "vape/smoke shop"
    preview = {
        "nombre": nombre,
        "web": _tag(tags, "website", "contact:website", "url"),
        "_osm_tags": dict(tags),
        "osm_shop_tobacco": shop in ("tobacco", "cigar"),
    }
    bucket, motivo = clasificar_aceptacion(preview)
    if bucket == "excluido":
        return motivo
    if bucket == "dudoso":
        return motivo
    return "filtro OSM"


def _elemento_a_lead(el: dict, pais: str) -> dict | None:
    tags = el.get("tags") or {}
    nombre = _tag(tags, "name", "brand", "operator")
    if not nombre and tags.get("shop") in ("tobacco", "cigar"):
        calle = _tag(tags, "addr:street", "addr:place", "addr:city")
        nombre = f"Tobacco shop {calle}".strip() if calle else "Tobacco shop"
    if not nombre:
        return None
    if descartar_lead_osm(nombre, tags):
        return None
    shop = tags.get("shop") or ""
    if shop == "e-cigarette":
        return None
    preview = {
        "nombre": nombre,
        "web": _tag(tags, "website", "contact:website", "url"),
        "_osm_tags": dict(tags),
        "osm_shop_tobacco": shop in ("tobacco", "cigar"),
        "fuente": "openstreetmap",
    }
    bucket, _motivo = clasificar_aceptacion(preview)
    if bucket == "excluido":
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
        "osm_shop_tobacco": tags.get("shop") in ("tobacco", "cigar"),
        "_osm_tags": dict(tags),
        "nombre_clasificacion": bucket,
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


def _bbox_para_iso(iso: str) -> dict | None:
    if not BBOX_PATH.is_file():
        return None
    data = json.loads(BBOX_PATH.read_text(encoding="utf-8"))
    box = data.get(iso)
    return box if isinstance(box, dict) else None


def _query_profunda_en_area(area_selector: str) -> str:
    re_f = _regex_nombre_fuertes()
    return f"""
[out:json][timeout:15];
{area_selector}
(
  nwr["shop"="tobacco"](area.search);
  nwr["shop"="cigar"](area.search);
  nwr["shop"="e-cigarette"](area.search);
  nwr["shop"="duty_free"](area.search);
  nwr["shop"="alcohol"](area.search);
  nwr["amenity"~"cafe|bar|pub|restaurant"]["cigar"="yes"](area.search);
  nwr["tourism"~"hotel|resort"]["name"~"{re_f}",i](area.search);
  nwr["shop"="convenience"]["name"~"{re_f}",i](area.search);
  nwr["name"~"{re_f}",i](area.search);
);
out center tags;
""".strip()


def _query_debiles_en_area(area_selector: str) -> str:
    re_d = _regex_nombre_debiles()
    return f"""
[out:json][timeout:15];
{area_selector}
(
  nwr["shop"~"tobacco|cigar"]["name"~"{re_d}",i](area.search);
  nwr["shop"="alcohol"]["name"~"{re_d}",i](area.search);
  nwr["amenity"~"bar|pub|cafe|restaurant"]["name"~"{re_d}",i](area.search);
);
out center tags;
""".strip()


def _query_iso(iso: str) -> str:
    selector = (
        f'area["ISO3166-1"="{iso}"][admin_level=2]->.search;'
    )
    return _query_profunda_en_area(selector)


def _query_iso_debiles(iso: str) -> str:
    selector = f'area["ISO3166-1"="{iso}"][admin_level=2]->.search;'
    return _query_debiles_en_area(selector)


def _query_bbox(box: dict) -> str:
    s, w, n, e = box["south"], box["west"], box["north"], box["east"]
    re_f = _regex_nombre_fuertes()
    return f"""
[out:json][timeout:15];
(
  nwr["shop"="tobacco"]({s},{w},{n},{e});
  nwr["shop"="cigar"]({s},{w},{n},{e});
  nwr["shop"="duty_free"]({s},{w},{n},{e});
  nwr["shop"="alcohol"]({s},{w},{n},{e});
  nwr["amenity"~"cafe|bar|pub|restaurant"]["cigar"="yes"]({s},{w},{n},{e});
  nwr["shop"="convenience"]["name"~"{re_f}",i]({s},{w},{n},{e});
  nwr["name"~"{re_f}",i]({s},{w},{n},{e});
);
out center tags;
""".strip()


def _query_bbox_debiles(box: dict) -> str:
    s, w, n, e = box["south"], box["west"], box["north"], box["east"]
    re_d = _regex_nombre_debiles()
    return f"""
[out:json][timeout:15];
(
  nwr["shop"~"tobacco|cigar"]["name"~"{re_d}",i]({s},{w},{n},{e});
  nwr["shop"="alcohol"]["name"~"{re_d}",i]({s},{w},{n},{e});
  nwr["amenity"~"bar|pub|cafe|restaurant"]["name"~"{re_d}",i]({s},{w},{n},{e});
);
out center tags;
""".strip()


def _query_tobacco_around(lat: float, lon: float, radio_m: int) -> str:
    return f"""
[out:json][timeout:15];
(
  nwr["shop"~"tobacco|cigar"](around:{radio_m},{lat},{lon});
);
out center tags;
""".strip()


def _contar_tipos(elementos: list[dict]) -> dict[str, int]:
    out = {"node": 0, "way": 0, "relation": 0, "other": 0}
    for el in elementos:
        t = (el.get("type") or "other").lower()
        if t in out:
            out[t] += 1
        else:
            out["other"] += 1
    return out


def _fetch_elementos_territorio(iso: str, rotar_desde: int) -> tuple[list[dict], str, int]:
    """Dos pasadas: etiquetas + nombres fuertes, luego nombres débiles acotados."""
    llamadas = 0
    elems: list[dict] = []
    modo = "iso"
    iso_ok = False
    try:
        elems = _fetch_overpass(_query_iso(iso), rotar_desde=rotar_desde)
        llamadas += 1
        iso_ok = True
    except RuntimeError:
        elems = []

    try:
        _pausa_entre_consultas()
        extra = _fetch_overpass(_query_iso_debiles(iso), rotar_desde=rotar_desde)
        llamadas += 1
        elems = _dedupe_elementos(elems + extra)
    except RuntimeError:
        pass

    if elems:
        return elems, modo, llamadas

    box = _bbox_para_iso(iso)
    if box:
        elems_bbox = _fetch_overpass(_query_bbox(box), rotar_desde=rotar_desde)
        llamadas += 1
        try:
            _pausa_entre_consultas()
            extra_b = _fetch_overpass(_query_bbox_debiles(box), rotar_desde=rotar_desde)
            llamadas += 1
            elems_bbox = _dedupe_elementos(elems_bbox + extra_b)
        except RuntimeError:
            pass
        return elems_bbox, "bbox", llamadas
    if iso_ok:
        return elems, modo, llamadas
    raise RuntimeError(f"Sin resultados Overpass para ISO {iso} (área y bbox)")


def _fetch_overpass(query: str, rotar_desde: int = 0) -> list[dict]:
    """Un intento lógico: rota mirrors; como máximo 15 s por petición."""
    body = urllib.parse.urlencode({"data": query}).encode("utf-8")
    headers = {"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"}
    urls = OVERPASS_URLS[rotar_desde:] + OVERPASS_URLS[:rotar_desde]
    errors: list[str] = []
    for base_url in urls:
        timeout = _timeout_peticion()
        request = urllib.request.Request(base_url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
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
) -> tuple[list[dict], int, dict]:
    llamadas = 0
    elementos: list[dict] = []
    _pausa_entre_consultas()
    elementos, modo, llamadas = _fetch_elementos_territorio(iso, rotar_espejo)
    elementos = _dedupe_elementos(elementos)

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
    descartes_osm: list[dict] = []
    vistos: set[str] = set()
    for el in elementos:
        tags = el.get("tags") or {}
        lead = _elemento_a_lead(el, pais)
        if not lead:
            descartes_osm.append(
                {
                    "nombre": _nombre_log_osm(el, tags),
                    "motivo": _motivo_si_sin_lead(el, pais),
                    "etapa": "osm",
                    "fuente": "openstreetmap",
                }
            )
            continue
        clave = lead.get("place_id") or lead["nombre"].lower()
        if clave in vistos:
            descartes_osm.append(
                {
                    "nombre": lead["nombre"],
                    "motivo": "duplicado OSM (misma pasada)",
                    "etapa": "osm",
                    "fuente": "openstreetmap",
                }
            )
            continue
        vistos.add(clave)
        if tipo_filtro and lead.get("tipo_negocio") != tipo_filtro:
            descartes_osm.append(
                {
                    "nombre": lead["nombre"],
                    "motivo": f"tipo filtrado ({tipo_filtro})",
                    "etapa": "osm",
                    "fuente": "openstreetmap",
                }
            )
            continue
        candidatos.append(lead)
    candidatos.sort(key=lambda p: orden_tipo.get(p.get("tipo_negocio", "tienda"), 99))
    conteo = _contar_tipos(elementos)
    meta = {
        "modo": modo,
        "raw": len(elementos),
        "nodes": conteo["node"],
        "ways": conteo["way"],
        "relations": conteo["relation"],
        "filtrados_ok": len(candidatos),
        "descartes": descartes_osm,
    }
    import sys

    print(
        f"OSM {pais}: {meta['raw']} elementos (n/w/r={conteo['node']}/{conteo['way']}/"
        f"{conteo['relation']}, vía {modo}) → {meta['filtrados_ok']} leads, "
        f"{len(descartes_osm)} descartes",
        file=sys.stderr,
    )
    registrar_evento({"evento": "osm_conteo_isla", "pais": pais, **meta})
    return candidatos, llamadas, meta


def _abrir_tope_isla() -> None:
    global _deadline_isla
    _deadline_isla = time.monotonic() + _TOPE_SEGUNDOS_ISLA


def _cerrar_tope_isla() -> None:
    global _deadline_isla
    _deadline_isla = None


def buscar_en_pais_osm(
    pais: str,
    tipos: list[str],
    limite: int,
    tipo_filtro: str = "",
) -> tuple[list[dict], int, dict]:
    if tipo_filtro:
        tipos = [tipo_filtro]
    iso = _iso_para_pais(pais)
    ultimo_error: BaseException | None = None
    _abrir_tope_isla()
    try:
        for intento in range(_REINTENTOS_ISLA):
            if _deadline_isla is not None and time.monotonic() >= _deadline_isla:
                ultimo_error = OsmTopeIsla("OSM: tope de 2 minutos por isla")
                break
            if intento > 0:
                espera = _ESPERA_ENTRE_REINTENTOS_ISLA[min(intento - 1, len(_ESPERA_ENTRE_REINTENTOS_ISLA) - 1)]
                registrar_osm_fallo(pais, f"reintento isla {intento + 1}/{_REINTENTOS_ISLA} tras {espera}s")
                time.sleep(espera)
            try:
                return _buscar_en_pais_osm_cuerpo(
                    pais, tipos, limite, tipo_filtro, iso, rotar_espejo=intento
                )
            except OsmTopeIsla as error:
                ultimo_error = error
                registrar_osm_fallo(pais, str(error))
                break
            except RuntimeError as error:
                ultimo_error = error
                registrar_osm_fallo(pais, f"intento {intento + 1}/{_REINTENTOS_ISLA}: {error}")
    finally:
        _cerrar_tope_isla()
    raise OsmIslaFallida(pais, str(ultimo_error or "Overpass sin respuesta"))


def obtener_elementos_osm_pais(pais: str) -> tuple[list[dict], int]:
    """Elementos OSM crudos (fuertes + débiles) para dry-run u auditoría."""
    iso = _iso_para_pais(pais)
    ultimo: BaseException | None = None
    llamadas = 0
    _abrir_tope_isla()
    try:
        for intento in range(_REINTENTOS_ISLA):
            if _deadline_isla is not None and time.monotonic() >= _deadline_isla:
                ultimo = OsmTopeIsla("OSM: tope de 2 minutos por isla")
                break
            if intento > 0:
                time.sleep(_ESPERA_ENTRE_REINTENTOS_ISLA[min(intento - 1, len(_ESPERA_ENTRE_REINTENTOS_ISLA) - 1)])
            try:
                _pausa_entre_consultas()
                elementos, _modo, llamadas = _fetch_elementos_territorio(iso, intento)
                return _dedupe_elementos(elementos), llamadas
            except OsmTopeIsla as error:
                ultimo = error
                break
            except RuntimeError as error:
                ultimo = error
    finally:
        _cerrar_tope_isla()
    raise ultimo or RuntimeError(f"Overpass sin respuesta para {pais}")
