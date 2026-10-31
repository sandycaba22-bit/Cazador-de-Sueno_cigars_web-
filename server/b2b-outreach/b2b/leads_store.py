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
    out = {
        "place_ids": [p for p in data.get("place_ids", []) if _place_id_valido(p)],
        "dominios": [d for d in data.get("dominios", []) if _dominio_valido(d)],
    }
    telefonos = [t for t in data.get("telefonos") or [] if t]
    correos = [c for c in data.get("correos") or [] if c]
    if telefonos:
        out["telefonos"] = telefonos
    if correos:
        out["correos"] = correos
    return out


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


ESTADOS_LEAD = (
    "nuevo",
    "aprobado",
    "aprobado_simulado",
    "en_cola",
    "enviado",
    "respondio",
    "reboto",
    "baja",
    "descartado",
)


def clave_lead(lead: dict) -> str:
    nom = (lead.get("nombre") or "").strip().lower()
    dom = _dominio(lead.get("web") or "")
    correo = (lead.get("correo") or "").strip().lower()
    return f"{nom}|{dom}|{correo}"


def _estado_path() -> Path:
    return state_file("leads_estado.json")


def _load_estados() -> dict:
    path = _estado_path()
    if not path.is_file():
        return {"leads": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"leads": {}}
    data.setdefault("leads", {})
    return data


def _save_estados(data: dict) -> None:
    path = _estado_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def guardar_estado_lead(lead: dict, estado: str, **extra) -> None:
    if estado not in ESTADOS_LEAD:
        return
    data = _load_estados()
    leads = dict(data.get("leads") or {})
    prev = dict(leads.get(clave_lead(lead)) or {})
    prev.update({
        "estado": estado,
        "nombre": lead.get("nombre") or prev.get("nombre") or "",
        "correo": (lead.get("correo") or prev.get("correo") or "").strip().lower(),
        "web": lead.get("web") or prev.get("web") or "",
    })
    prev.update(extra)
    leads[clave_lead(lead)] = prev
    data["leads"] = leads
    _save_estados(data)


def estado_de_lead(lead: dict) -> str:
    item = (_load_estados().get("leads") or {}).get(clave_lead(lead)) or {}
    return item.get("estado") or "nuevo"


def _guardar_seen(ids: set[str], doms: set[str], telefonos: set[str] | None = None, correos: set[str] | None = None) -> None:
    payload = {"place_ids": sorted(ids), "dominios": sorted(doms)}
    if telefonos:
        payload["telefonos"] = sorted(telefonos)
    if correos:
        payload["correos"] = sorted(correos)
    _save_seen(payload)


def _tel_clave(lead: dict) -> str:
    import re

    digitos = re.sub(r"\D", "", (lead.get("telefono_internacional") or lead.get("telefono") or lead.get("whatsapp") or ""))
    return digitos[-10:] if len(digitos) >= 8 else ""


def marcar_visto(place_id: str = "", web: str = "") -> None:
    data = _load_seen()
    ids = set(data.get("place_ids", []))
    doms = set(data.get("dominios", []))
    if _place_id_valido(place_id):
        ids.add(place_id)
    dom = _dominio(web)
    if _dominio_valido(dom):
        doms.add(dom)
    _guardar_seen(ids, doms, set(data.get("telefonos") or []), set(data.get("correos") or []))


def registrar_contacto(lead: dict) -> None:
    """Guarda teléfono y correo para no volver a contactar el mismo negocio."""
    data = _load_seen()
    telefonos = set(data.get("telefonos") or [])
    correos = set(data.get("correos") or [])
    tel = _tel_clave(lead)
    correo = (lead.get("correo") or "").strip().lower()
    if tel:
        telefonos.add(tel)
    if "@" in correo and not correo.endswith(("@example.com", "@example.org", "@example.net")) and not correo.endswith(".test"):
        correos.add(correo)
    _guardar_seen(
        set(data.get("place_ids") or []),
        set(data.get("dominios") or []),
        telefonos,
        correos,
    )


def contacto_visto(lead: dict) -> bool:
    data = _load_seen()
    tel = _tel_clave(lead)
    correo = (lead.get("correo") or "").strip().lower()
    if tel and tel in set(data.get("telefonos") or []):
        return True
    if correo and correo in set(data.get("correos") or []):
        return True
    return False
