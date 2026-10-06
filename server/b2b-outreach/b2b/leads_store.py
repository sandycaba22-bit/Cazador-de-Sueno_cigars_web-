from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from b2b.paths import data_file, state_file

SEEN_PATH = state_file("registro_leads.json")
NO_CONTACT_PATH = data_file("no_contactar.json")


def _load_seen() -> dict:
    if not SEEN_PATH.is_file():
        return {"place_ids": [], "dominios": []}
    return json.loads(SEEN_PATH.read_text(encoding="utf-8"))


def _save_seen(data: dict) -> None:
    SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    SEEN_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _dominio(web: str) -> str:
    try:
        host = urlparse(web).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def en_lista_no_contactar(nombre: str, web: str = "") -> bool:
    if not NO_CONTACT_PATH.is_file():
        return False
    data = json.loads(NO_CONTACT_PATH.read_text(encoding="utf-8"))
    nombre_l = nombre.strip().lower()
    dom = _dominio(web)
    for item in data.get("negocios", []):
        if item.get("nombre", "").strip().lower() == nombre_l:
            return True
        if dom and _dominio(item.get("web", "")) == dom:
            return True
    return False


def ya_visto(place_id: str = "", web: str = "") -> bool:
    data = _load_seen()
    if place_id and place_id in data.get("place_ids", []):
        return True
    dom = _dominio(web)
    return bool(dom and dom in data.get("dominios", []))


def marcar_visto(place_id: str = "", web: str = "") -> None:
    data = _load_seen()
    ids = set(data.get("place_ids", []))
    doms = set(data.get("dominios", []))
    if place_id:
        ids.add(place_id)
    dom = _dominio(web)
    if dom:
        doms.add(dom)
    _save_seen({"place_ids": sorted(ids), "dominios": sorted(doms)})
