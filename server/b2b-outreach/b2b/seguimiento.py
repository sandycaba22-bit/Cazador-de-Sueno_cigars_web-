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
    from b2b.io_atomico import escribir_json

    escribir_json(_ruta(), data)


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


def dias_correo() -> list[int]:
    """Días 4 y 10 por defecto. Un valor inválido no abre seguimientos extra."""
    raw = os.getenv("B2B_SEGUIMIENTO_DIAS", "4,10")
    nums: list[int] = []
    for trozo in (raw or "").split(","):
        try:
            n = int(trozo.strip())
        except ValueError:
            continue
        if 1 <= n <= 60:
            nums.append(n)
    return nums or [4, 10]


def anotar_planes_correo(lead: dict, cuando: datetime) -> None:
    """Programa los seguimientos en el primer hueco hábil de la zona del negocio."""
    from b2b.zona_horaria import aplicar_zona, primer_hueco

    if cuando.tzinfo is None:
        cuando = cuando.replace(tzinfo=timezone.utc)
    aplicar_zona(lead)
    data = _load()
    clave = clave_prospecto(lead)
    item = dict((data.get("items") or {}).get(clave) or {})
    if item.get("correos_programados"):
        return
    planes = []
    for dia in dias_correo():
        hueco = primer_hueco(cuando + timedelta(days=dia), lead)
        planes.append({
            "dia": dia,
            "enviar_despues_de": hueco.isoformat(timespec="seconds"),
            "estado": "programado",
            "materializado": False,
        })
    item["correos_programados"] = planes
    item.setdefault("nombre", lead.get("nombre") or "")
    item.setdefault("correo", (lead.get("correo") or "").strip().lower())
    item.setdefault("canal", "correo")
    item.setdefault("cuando", cuando.isoformat(timespec="seconds"))
    item["lead"] = {
        "nombre": lead.get("nombre") or "",
        "correo": lead.get("correo") or "",
        "pais": lead.get("pais") or "",
        "estado": lead.get("estado") or "",
        "ciudad": lead.get("ciudad") or "",
        "idioma": lead.get("idioma") or "en",
        "tipo": lead.get("tipo") or "tienda",
        "web": lead.get("web") or "",
        "lat": lead.get("lat"),
        "lon": lead.get("lon"),
        "puntaje": lead.get("puntaje"),
        "zona_iana": lead.get("zona_iana") or "",
        "zona_fuente": lead.get("zona_fuente") or "",
        "zona_exacta": bool(lead.get("zona_exacta")),
    }
    data["items"][clave] = item
    _save(data)


def planes_listos(ahora: datetime) -> list[tuple[str, dict, dict]]:
    if ahora.tzinfo is None:
        ahora = ahora.replace(tzinfo=timezone.utc)
    data = _load()
    listos = []
    for clave, item in (data.get("items") or {}).items():
        if not isinstance(item, dict):
            continue
        for plan in item.get("correos_programados") or []:
            if not isinstance(plan, dict) or plan.get("materializado") or plan.get("estado") == "cancelado":
                continue
            try:
                cuando = datetime.fromisoformat(plan.get("enviar_despues_de") or "")
            except ValueError:
                continue
            if cuando.tzinfo is None:
                cuando = cuando.replace(tzinfo=timezone.utc)
            if cuando <= ahora:
                listos.append((clave, item, plan))
    return listos


def marcar_plan(clave: str, dia: int, estado: str, motivo: str = "", *, materializado: bool = False) -> None:
    data = _load()
    item = dict((data.get("items") or {}).get(clave) or {})
    planes = []
    for plan in item.get("correos_programados") or []:
        if isinstance(plan, dict) and int(plan.get("dia") or 0) == int(dia):
            plan = dict(plan)
            plan["estado"] = estado
            plan["materializado"] = materializado or estado == "cancelado"
            if motivo:
                plan["motivo"] = motivo
        planes.append(plan)
    item["correos_programados"] = planes
    data["items"][clave] = item
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
