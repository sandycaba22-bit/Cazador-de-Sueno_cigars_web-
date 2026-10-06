from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from b2b.nombres_busqueda import overpass_regex_alternativas
from b2b.osm_places import (
    _dedupe_elementos,
    _elemento_a_lead,
    _fetch_overpass,
    _iso_para_pais,
    _pausa_entre_consultas,
)
from b2b.paths import data_file, state_file

BBOX_PATH = data_file("osm_bbox_fallback.json")
CACHE_DIR = state_file("cache_osm_cuadricula")
ESTADO_PATH = state_file("buscar_global_estado.json")
PASO_GRADOS = 0.45


def _bbox_pais(iso: str) -> dict:
    if BBOX_PATH.is_file():
        data = json.loads(BBOX_PATH.read_text(encoding="utf-8"))
        if iso in data:
            return data[iso]
    raise ValueError(f"Sin bbox en osm_bbox_fallback.json para ISO {iso}")


def celdas_desde_bbox(box: dict, paso: float = PASO_GRADOS) -> list[dict]:
    out: list[dict] = []
    lat = float(box["south"])
    north = float(box["north"])
    west = float(box["west"])
    east = float(box["east"])
    while lat < north:
        lat2 = min(lat + paso, north)
        lon = west
        while lon < east:
            lon2 = min(lon + paso, east)
            out.append({"south": lat, "west": lon, "north": lat2, "east": lon2})
            lon = lon2
        lat = lat2
    return out


def _celda_id(iso: str, celda: dict) -> str:
    raw = f"{iso}|{celda['south']:.4f}|{celda['west']:.4f}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _cache_path(celda_id: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{celda_id}.json"


def _query_celda(celda: dict) -> str:
    s, w, n, e = celda["south"], celda["west"], celda["north"], celda["east"]
    re_f = overpass_regex_alternativas("fuertes")
    return f"""
[out:json][timeout:35];
(
  nwr["shop"~"tobacco|cigar"]({s},{w},{n},{e});
  nwr["shop"="duty_free"]({s},{w},{n},{e});
  nwr["amenity"~"bar|pub|cafe|restaurant"]["cigar"="yes"]({s},{w},{n},{e});
  nwr["tourism"~"hotel|resort"]["name"~"{re_f}",i]({s},{w},{n},{e});
  nwr["name"~"{re_f}",i]({s},{w},{n},{e});
);
out center tags;
""".strip()


def _leer_cache(celda_id: str) -> list[dict] | None:
    path = _cache_path(celda_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return list(data.get("elements") or [])
    except (OSError, json.JSONDecodeError):
        return None


def _guardar_cache(celda_id: str, elementos: list[dict]) -> None:
    path = _cache_path(celda_id)
    path.write_text(
        json.dumps({"elements": elementos}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def cargar_estado_global() -> dict:
    if not ESTADO_PATH.is_file():
        return {"pais_idx": 0, "celda_idx": 0}
    try:
        return json.loads(ESTADO_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"pais_idx": 0, "celda_idx": 0}


def guardar_estado_global(estado: dict) -> None:
    ESTADO_PATH.parent.mkdir(parents=True, exist_ok=True)
    prev = cargar_estado_global()
    prev.update(estado)
    ESTADO_PATH.write_text(json.dumps(prev, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def buscar_celda(
    pais: str,
    iso: str,
    celda: dict,
    celda_idx: int,
    *,
    usar_cache: bool = True,
    rotar_espejo: int = 0,
) -> tuple[list[dict], int]:
    cid = _celda_id(iso, celda)
    llamadas = 0
    if usar_cache:
        cached = _leer_cache(cid)
        if cached is not None:
            elementos = cached
        else:
            _pausa_entre_consultas()
            elementos = _fetch_overpass(_query_celda(celda), rotar_desde=rotar_espejo)
            llamadas = 1
            _guardar_cache(cid, elementos)
    else:
        _pausa_entre_consultas()
        elementos = _fetch_overpass(_query_celda(celda), rotar_desde=rotar_espejo)
        llamadas = 1
    leads: list[dict] = []
    for el in elementos:
        lead = _elemento_a_lead(el, pais)
        if not lead:
            continue
        lat = el.get("lat")
        lon = el.get("lon")
        if lat is None or lon is None:
            center = el.get("center") or {}
            lat = center.get("lat")
            lon = center.get("lon")
        if lat is not None and lon is not None:
            lead["lat"] = lat
            lead["lon"] = lon
        tags = el.get("tags") or {}
        wa = tags.get("contact:whatsapp") or tags.get("whatsapp") or ""
        if wa:
            lead["whatsapp"] = str(wa).strip()
        leads.append(lead)
    return leads, llamadas


def preparar_celdas_pais(iso: str) -> list[dict]:
    return celdas_desde_bbox(_bbox_pais(iso))


def obtener_elementos_cuadricula(
    iso: str,
    *,
    max_celdas: int = 6,
    celda_inicio: int = 0,
) -> tuple[list[dict], int]:
    """Elementos OSM por celdas (consultas pequeñas). Para dry-run en territorios grandes."""
    celdas = preparar_celdas_pais(iso)
    fin = min(len(celdas), celda_inicio + max(1, max_celdas))
    todos: list[dict] = []
    llamadas = 0
    for idx in range(celda_inicio, fin):
        celda = celdas[idx]
        cid = _celda_id(iso, celda)
        cached = _leer_cache(cid)
        if cached is not None:
            todos.extend(cached)
            continue
        _pausa_entre_consultas()
        elementos = _fetch_overpass(_query_celda(celda), rotar_desde=idx % 3)
        llamadas += 1
        _guardar_cache(cid, elementos)
        todos.extend(elementos)
    return _dedupe_elementos(todos), llamadas
