"""Recordatorio en Telegram a los 5 días de marcar Enviado."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from b2b.paths import state_file
from b2b.telegram_gestion import clave_prospecto


def _ruta():
    return state_file("seguimiento.json")


def _load() -> dict:
    path = _ruta()
    if not path.is_file():
        return {"items": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"items": {}}
    data.setdefault("items", {})
    return data


def _save(data: dict) -> None:
    path = _ruta()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _dias() -> int:
    try:
        return max(1, int(os.getenv("B2B_SEGUIMIENTO_DIAS_RECORDATORIO", "5") or "5"))
    except ValueError:
        return 5


def registrar_enviado(lead: dict, canal: str, cuando: datetime | None = None) -> None:
    cuando = cuando or datetime.now(timezone.utc)
    if cuando.tzinfo is None:
        cuando = cuando.replace(tzinfo=timezone.utc)
    data = _load()
    clave = clave_prospecto(lead)
    data["items"][clave] = {
        "nombre": lead.get("nombre") or "",
        "canal": canal or "manual",
        "correo": (lead.get("correo") or "").strip().lower(),
        "telefono": (lead.get("telefono_internacional") or lead.get("telefono") or "").strip(),
        "cuando": cuando.isoformat(timespec="seconds"),
        "recordar_en": (cuando + timedelta(days=_dias())).isoformat(timespec="seconds"),
        "recordado": False,
    }
    _save(data)


def textos_recordatorio(ahora: datetime | None = None) -> list[str]:
    ahora = ahora or datetime.now(timezone.utc)
    if ahora.tzinfo is None:
        ahora = ahora.replace(tzinfo=timezone.utc)
    data = _load()
    textos = []
    cambio = False
    for clave, item in (data.get("items") or {}).items():
        if item.get("recordado"):
            continue
        try:
            vence = datetime.fromisoformat(item.get("recordar_en") or "")
        except ValueError:
            continue
        if vence.tzinfo is None:
            vence = vence.replace(tzinfo=timezone.utc)
        if ahora < vence:
            continue
        nombre = item.get("nombre") or "el negocio"
        canal = item.get("canal") or "manual"
        cuando = (item.get("cuando") or "")[:16].replace("T", " ")
        textos.append(
            f"📌 Seguimiento: hace {_dias()} días contactaste a {nombre} por {canal} ({cuando}). ¿Respondieron?"
        )
        item["recordado"] = True
        data["items"][clave] = item
        cambio = True
    if cambio:
        _save(data)
    return textos
