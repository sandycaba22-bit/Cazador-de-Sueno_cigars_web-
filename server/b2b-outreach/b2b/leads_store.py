from __future__ import annotations

import json
from pathlib import Path

from b2b.paths import data_file, state_file
from b2b.website import dominio_negocio

NO_CONTACT_PATH = data_file("no_contactar.json")

# Parcheable en tests; None = calcular con state_file() en cada llamada.
SEEN_PATH: Path | None = None
NO_CONTACT_STATE_PATH: Path | None = None

_DOMINIOS_PRUEBA = ("example.com", "example.org", "example.net")


def seen_path() -> Path:
    return SEEN_PATH or state_file("registro_leads.json")


def no_contact_state_path() -> Path:
    return NO_CONTACT_STATE_PATH or state_file("no_contactar_telegram.json")


def _dominio(web: str) -> str:
    return dominio_negocio(web)


def _place_id_valido(pid: str) -> bool:
    return bool(pid) and not pid.startswith("fixture-")


def _dominio_valido(dom: str) -> bool:
    if not dom or dom.endswith(".test") or dom in _DOMINIOS_PRUEBA:
        return False
    return bool(dominio_negocio(f"https://{dom}/"))


def _load_seen() -> dict:
    path = seen_path()
    if not path.is_file():
        return {"place_ids": [], "dominios": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"place_ids": [], "dominios": []}
    return {
        "place_ids": [p for p in data.get("place_ids", []) if _place_id_valido(p)],
        "dominios": [d for d in data.get("dominios", []) if _dominio_valido(d)],
    }


def _save_seen(data: dict) -> None:
    path = seen_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def en_lista_no_contactar(nombre: str, web: str = "") -> bool:
    nombre_l = nombre.strip().lower()
    dom = _dominio(web)
    for path in (NO_CONTACT_PATH, no_contact_state_path()):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
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
    if _place_id_valido(place_id):
        ids.add(place_id)
    dom = _dominio(web)
    if _dominio_valido(dom):
        doms.add(dom)
    _save_seen({"place_ids": sorted(ids), "dominios": sorted(doms)})
