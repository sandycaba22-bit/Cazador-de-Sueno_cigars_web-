from __future__ import annotations

import hashlib
import json

from b2b.leads_store import _dominio
from b2b.paths import state_file

GESTION_PATH = state_file("telegram_prospectos_gestionados.json")
PENDIENTES_PATH = state_file("telegram_prospecto_pendientes.json")

EMAIL_VP = "cazadordesueno1@gmail.com"


def clave_prospecto(lead: dict) -> str:
    nom = (lead.get("nombre") or "").strip().lower()
    dom = _dominio(lead.get("web") or "")
    return f"{nom}|{dom}"


def _load_gestionados() -> dict:
    if not GESTION_PATH.is_file():
        return {"claves": {}}
    try:
        return json.loads(GESTION_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"claves": {}}


def _save_gestionados(data: dict) -> None:
    GESTION_PATH.parent.mkdir(parents=True, exist_ok=True)
    GESTION_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def ya_gestionado_telegram(lead: dict) -> bool:
    clave = clave_prospecto(lead)
    estado = (_load_gestionados().get("claves") or {}).get(clave)
    return estado in ("enviado", "descartado")


def marcar_gestionado_telegram(lead: dict, accion: str) -> None:
    if accion not in ("enviado", "descartado"):
        return
    data = _load_gestionados()
    claves = dict(data.get("claves") or {})
    claves[clave_prospecto(lead)] = accion
    data["claves"] = claves
    _save_gestionados(data)


def token_callback(lead: dict) -> str:
    raw = clave_prospecto(lead) + "|" + (lead.get("pais") or "")
    return hashlib.sha1(raw.encode()).hexdigest()[:10]


def _load_pendientes() -> dict:
    if not PENDIENTES_PATH.is_file():
        return {}
    try:
        return json.loads(PENDIENTES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_pendientes(data: dict) -> None:
    PENDIENTES_PATH.parent.mkdir(parents=True, exist_ok=True)
    PENDIENTES_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def registrar_pendiente(token: str, lead: dict, inbox_path: str = "") -> None:
    pend = _load_pendientes()
    pend[token] = {
        "nombre": lead.get("nombre") or "",
        "web": lead.get("web") or "",
        "pais": lead.get("pais") or "",
        "inbox_path": inbox_path,
    }
    _save_pendientes(pend)


def resolver_pendiente(token: str) -> dict | None:
    return _load_pendientes().get(token)


def quitar_pendiente(token: str) -> None:
    pend = _load_pendientes()
    pend.pop(token, None)
    _save_pendientes(pend)


def agregar_no_contactar(nombre: str, web: str = "", motivo: str = "") -> None:
    from b2b.leads_store import NO_CONTACT_STATE_PATH as NO_CONTACT_PATH

    NO_CONTACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not NO_CONTACT_PATH.is_file():
        data = {"negocios": []}
    else:
        data = json.loads(NO_CONTACT_PATH.read_text(encoding="utf-8"))
    negocios = list(data.get("negocios") or [])
    entry = {"nombre": nombre.strip(), "web": (web or "").strip(), "motivo": motivo.strip()}
    nom_l = entry["nombre"].lower()
    dom = _dominio(entry["web"])
    for item in negocios:
        if item.get("nombre", "").strip().lower() == nom_l:
            return
        if dom and _dominio(item.get("web", "")) == dom:
            return
    negocios.append(entry)
    data["negocios"] = negocios
    NO_CONTACT_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def tiene_medio_contacto(payload: dict) -> bool:
    tel = (payload.get("telefono") or "").strip()
    correo = (payload.get("correo") or "").strip()
    web = (payload.get("web") or "").strip()
    if tel or correo:
        return True
    return bool(web and web != "—" and web.startswith(("http://", "https://")))


def urls_formulario_contacto(web: str) -> list[str]:
    if not web or web == "—" or not web.startswith(("http://", "https://")):
        return []
    from b2b.website import CONTACT_PATHS
    import urllib.parse

    parsed = urllib.parse.urlparse(web)
    base = f"{parsed.scheme}://{parsed.netloc}"
    out: list[str] = []
    for path in CONTACT_PATHS:
        url = base + path
        if url not in out:
            out.append(url)
        if len(out) >= 3:
            break
    return out
