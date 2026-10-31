"""Revisión de dudosos: los 10 mejores, uno a uno, con Aprobar o Descartar."""
from __future__ import annotations

import json
from pathlib import Path

from b2b.lead_score import puntuar_lead
from b2b.paths import queue_dir, state_file
from b2b.telegram_gestion import registrar_pendiente, token_callback


def _ruta_estado() -> Path:
    return state_file("dudosos_revision.json")


def _cola() -> Path:
    cola = queue_dir()
    return cola if cola else state_file("x").parent


def _leer(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def cargar_mejores(limite: int = 10) -> list[dict]:
    carpeta = _cola() / "dudoso"
    leads = []
    if carpeta.is_dir():
        for path in carpeta.glob("*.json"):
            data = _leer(path)
            if not data or data.get("dudoso_resuelto"):
                continue
            data["_path"] = str(path)
            score, _ = puntuar_lead(data)
            data["puntaje"] = data.get("puntaje") or score
            leads.append(data)
    leads.sort(key=lambda lead: (-int(lead.get("puntaje") or 0), (lead.get("nombre") or "").lower()))
    return leads[:limite]


def _load() -> dict:
    path = _ruta_estado()
    if not path.is_file():
        return {"pendientes": [], "indice": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"pendientes": [], "indice": 0}
    data.setdefault("pendientes", [])
    data.setdefault("indice", 0)
    return data


def _save(data: dict) -> None:
    path = _ruta_estado()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def preparar_tanda() -> dict:
    mejores = cargar_mejores(10)
    tokens = []
    for lead in mejores:
        token = token_callback(lead)
        lead["token"] = token
        registrar_pendiente(token, lead, lead.get("_path") or "")
        tokens.append(token)
    data = {"pendientes": tokens, "indice": 0}
    _save(data)
    return data


def actual(data: dict | None = None) -> tuple[str, dict] | tuple[None, None]:
    data = data if data is not None else _load()
    tokens = data.get("pendientes") or []
    indice = int(data.get("indice") or 0)
    if indice >= len(tokens):
        return None, None
    from b2b.telegram_gestion import resolver_pendiente

    token = tokens[indice]
    pend = resolver_pendiente(token) or {}
    return token, pend


def avanzar() -> tuple[str, dict] | tuple[None, None]:
    data = _load()
    data["indice"] = int(data.get("indice") or 0) + 1
    _save(data)
    return actual(data)


def aprobar(lead: dict) -> str:
    """Pasa el dudoso a la cola normal (inbox)."""
    origen = Path(lead.get("_path") or lead.get("inbox_path") or "")
    inbox = _cola() / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    payload = dict(lead)
    payload.pop("_path", None)
    payload["calidad_bucket"] = "aceptado"
    payload["telegram_notificado"] = False
    payload["dudoso_resuelto"] = "aprobado"
    nombre = (payload.get("nombre") or "dudoso").strip() or "dudoso"
    dest = inbox / (origen.name if origen.name.endswith(".json") else f"{token_callback(payload)}.json")
    if dest.exists():
        dest = inbox / f"aprobado-{dest.name}"
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if origen.is_file() and origen.parent.name == "dudoso":
        try:
            origen.unlink()
        except OSError:
            pass
    return nombre


MOTIVOS = {
    "n": "No vende cigarros",
    "c": "Cerrado",
    "y": "Ya contactado",
    "o": "Otro",
}


def guardar_motivo(lead: dict, codigo: str) -> str:
    motivo = MOTIVOS.get(codigo, codigo or "Otro")
    path = state_file("motivos_descarte.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    else:
        data = {}
    filas = list(data.get("motivos") or [])
    filas.append({
        "nombre": lead.get("nombre") or "",
        "web": lead.get("web") or "",
        "correo": lead.get("correo") or "",
        "telefono": lead.get("telefono") or "",
        "motivo": motivo,
        "pais": lead.get("pais") or "",
    })
    data["motivos"] = filas
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    origen = Path(lead.get("inbox_path") or lead.get("_path") or "")
    if origen.is_file():
        try:
            guardado = json.loads(origen.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            guardado = {}
        if isinstance(guardado, dict):
            guardado["motivo_descarte"] = motivo
            origen.write_text(json.dumps(guardado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return motivo
