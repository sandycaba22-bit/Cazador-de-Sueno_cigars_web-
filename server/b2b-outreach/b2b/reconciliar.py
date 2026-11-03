"""Cruce nocturno: cierra ya contactados y repara estados que se contradicen."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from b2b.contacto_previo import motivo_ya_contactado
from b2b.paths import queue_dir, state_file


def _leer(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _guardar(path: Path, data: dict) -> None:
    from b2b.io_atomico import escribir_json

    escribir_json(path, data)


def modo_reconciliar() -> str:
    """reporte (defecto) solo lista. aplicar escribe."""
    raw = (os.getenv("B2B_RECONCILIAR_MODO") or "reporte").strip().lower()
    return "aplicar" if raw == "aplicar" else "reporte"


def reconciliar(
    cola: Path | None = None,
    ahora: datetime | None = None,
    *,
    aplicar: bool | None = None,
) -> list[str]:
    """En reporte no toca archivos. En aplicar cierra y repara."""
    if aplicar is None:
        aplicar = modo_reconciliar() == "aplicar"
    cola = cola or queue_dir()
    if cola is None:
        return []
    inbox = cola / "inbox"
    if not inbox.is_dir():
        if not aplicar:
            return []
        inbox.mkdir(parents=True, exist_ok=True)
    cambios: list[str] = []
    pref = "" if aplicar else "Revisaría: "
    from b2b.despachador_tarjetas import _load, cerrar_tarjeta

    estado = _load()
    abiertas = dict(estado.get("abiertas") or {})
    for token, info in list(abiertas.items()):
        path = Path((info or {}).get("inbox") or "")
        lead = _leer(path) if path.is_file() else None
        if not lead:
            continue
        motivo = motivo_ya_contactado(lead)
        if not motivo and (lead.get("estado_tarjeta") or "") in ("correo_enviado", "correo_en_curso"):
            motivo = lead.get("estado_tarjeta") or ""
        if not motivo:
            continue
        if aplicar:
            lead["telegram_notificado"] = True
            lead["estado_tarjeta"] = "ya_contactado" if motivo in ("ya_correo", "ya_dominio", "no_contactar") else lead.get("estado_tarjeta")
            lead["omitido_motivo"] = motivo
            _guardar(path, lead)
            cerrar_tarjeta(token, ahora=ahora, espera_seg=0)
        cambios.append(f"{pref}Cerré tarjeta abierta de {lead.get('nombre') or token} ({motivo}).")

    for path in list(inbox.glob("*.json")):
        lead = _leer(path)
        if not lead or lead.get("telegram_notificado"):
            continue
        motivo = motivo_ya_contactado(lead)
        if not motivo:
            continue
        if aplicar:
            lead["telegram_notificado"] = True
            lead["estado_tarjeta"] = "ya_contactado"
            lead["omitido_motivo"] = motivo
            _guardar(path, lead)
        cambios.append(f"{pref}Saqué de la cola a {lead.get('nombre') or path.name} ({motivo}).")

    cambios.extend(_reparar_estados(aplicar=aplicar, pref=pref))
    if cambios:
        from b2b.logging_ops import registrar_evento

        registrar_evento({"evento": "reconciliacion", "n": len(cambios)})
    return cambios


def _reparar_estados(*, aplicar: bool, pref: str) -> list[str]:
    path = state_file("leads_estado.json")
    data = _leer(path) or {}
    leads = dict(data.get("leads") or {})
    if not leads:
        return []
    envios = _correos_ok()
    cambios: list[str] = []
    tocado = False
    for clave, item in list(leads.items()):
        if not isinstance(item, dict):
            continue
        estado = (item.get("estado") or "").strip()
        correo = (item.get("correo") or "").strip().lower()
        if estado == "enviado" and correo and correo not in envios:
            if aplicar:
                item["estado"] = "aprobado"
                item["reparado"] = "enviado_sin_envios_correo"
                leads[clave] = item
                tocado = True
            cambios.append(f"{pref}Reparé {item.get('nombre') or correo}: figuraba enviado y no está en envios_correo.")
        if estado in ("en_cola", "programado") and correo and not _en_outbox(correo):
            if aplicar:
                item["estado"] = "aprobado"
                item["reparado"] = "en_cola_sin_outbox"
                leads[clave] = item
                tocado = True
            cambios.append(f"{pref}Reparé {item.get('nombre') or correo}: en_cola sin archivo en outbox.")
    if aplicar and tocado:
        data["leads"] = leads
        _guardar(path, data)
    return cambios


def _correos_ok() -> set[str]:
    path = state_file("envios_correo.json")
    data = _leer(path) or {}
    out: set[str] = set()
    for item in data.get("envios") or []:
        if isinstance(item, dict) and item.get("ok") is not False:
            c = (item.get("correo") or "").strip().lower()
            if c:
                out.add(c)
    return out


def _en_outbox(correo: str) -> bool:
    cola = queue_dir()
    if cola is None:
        return False
    carpeta = cola / "outbox"
    if not carpeta.is_dir():
        return False
    for path in carpeta.glob("*.json"):
        item = _leer(path) or {}
        if (item.get("correo") or "").strip().lower() == correo and item.get("estado") in ("en_cola", "programado"):
            return True
    return False


def toca_noche(ahora_local: datetime, ya_hecho_dia: str) -> bool:
    """Una vez, a las 02:00 hora local."""
    if ahora_local.hour != 2:
        return False
    return ya_hecho_dia != ahora_local.strftime("%Y-%m-%d")
