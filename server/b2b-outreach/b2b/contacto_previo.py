"""¿Ya contactamos este negocio por correo/dominio? (envios_correo + seguimiento + no_contactar)."""
from __future__ import annotations

import json
from pathlib import Path

from b2b.buscar_filtros import dominio_web
from b2b.leads_store import en_lista_no_contactar
from b2b.paths import state_file


def _dominio_correo(correo: str) -> str:
    c = (correo or "").strip().lower()
    if "@" not in c:
        return ""
    return c.split("@", 1)[-1].strip()


def _correos_y_dominios_envios() -> tuple[set[str], set[str]]:
    path = state_file("envios_correo.json")
    correos: set[str] = set()
    dominios: set[str] = set()
    if not path.is_file():
        return correos, dominios
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return correos, dominios
    for clave in ("envios", "simulados"):
        for item in data.get(clave) or []:
            if not isinstance(item, dict):
                continue
            if item.get("ok") is False:
                continue
            c = (item.get("correo") or "").strip().lower()
            if c:
                correos.add(c)
            d = (item.get("dominio") or _dominio_correo(c) or "").strip().lower()
            if d:
                dominios.add(d)
    return correos, dominios


def _correos_y_dominios_seguimiento() -> tuple[set[str], set[str]]:
    path = state_file("seguimiento.json")
    correos: set[str] = set()
    dominios: set[str] = set()
    if not path.is_file():
        return correos, dominios
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return correos, dominios
    for item in (data.get("items") or {}).values():
        if not isinstance(item, dict):
            continue
        c = (item.get("correo") or "").strip().lower()
        if c:
            correos.add(c)
            d = _dominio_correo(c)
            if d:
                dominios.add(d)
        web_dom = dominio_web(item.get("web") or "")
        if web_dom:
            dominios.add(web_dom)
    return correos, dominios


def motivo_ya_contactado(lead: dict) -> str:
    """'' si se puede mostrar; si no, el motivo para omitir la tarjeta."""
    if en_lista_no_contactar(lead.get("nombre") or "", lead.get("web") or ""):
        return "no_contactar"
    correo = (lead.get("correo") or "").strip().lower()
    dom_web = dominio_web(lead.get("web") or "")
    dom_mail = _dominio_correo(correo)
    env_c, env_d = _correos_y_dominios_envios()
    seg_c, seg_d = _correos_y_dominios_seguimiento()
    if correo and (correo in env_c or correo in seg_c):
        return "ya_correo"
    # Dominio del correo o de la web ya contactado (mismo negocio / sede).
    for d in (dom_mail, dom_web):
        if d and (d in env_d or d in seg_d):
            return "ya_dominio"
    return ""


def ya_contactado(lead: dict) -> bool:
    return bool(motivo_ya_contactado(lead))
