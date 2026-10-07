from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from b2b.logging_ops import registrar_evento
from b2b.paths import state_file

TELEGRAM_MAX_DESCARTES = 10


def fecha_archivo_dia() -> str:
    return datetime.now().strftime("%Y%m%d")


def _iso_desde_mtime(path) -> str:
    try:
        ts = path.stat().st_mtime
        return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    except OSError:
        return ""


def entrada_descarte(nombre: str, motivo: str, *, etapa: str = "", fuente: str = "") -> dict[str, str]:
    row: dict[str, str] = {
        "nombre": (nombre or "—")[:120],
        "motivo": motivo,
    }
    if etapa:
        row["etapa"] = etapa
    if fuente:
        row["fuente"] = fuente
    return row


def entrada_repetido(nombre: str, contra: str, fecha: str) -> dict[str, str]:
    return {
        "nombre": (nombre or "—")[:120],
        "motivo": "repetido",
        "contra": contra,
        "fecha": fecha,
    }


def append_dudoso_diario(pais: str, lead: dict, motivo: str) -> None:
    path = state_file(f"dudosos_{fecha_archivo_dia()}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
    else:
        payload = {}
    payload.setdefault("fecha", fecha_archivo_dia())
    payload["actualizado"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    islas = payload.setdefault("islas", {})
    prev = islas.get(pais) or []
    prev.append(
        {
            "nombre": (lead.get("nombre") or "—")[:120],
            "motivo": motivo,
            "web": (lead.get("web") or "")[:200],
            "pais": pais,
        }
    )
    islas[pais] = prev
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def append_isla_en_archivo_diario(
    pais: str,
    descartes: list[dict[str, Any]],
    repetidos: list[dict[str, Any]],
) -> None:
    if not descartes and not repetidos:
        return
    path = state_file(f"descartados_{fecha_archivo_dia()}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
    else:
        payload = {}
    payload.setdefault("fecha", fecha_archivo_dia())
    payload["actualizado"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    islas = payload.setdefault("islas", {})
    prev = islas.get(pais) or {"descartes": [], "repetidos": []}
    prev["descartes"] = list(prev.get("descartes") or []) + list(descartes)
    prev["repetidos"] = list(prev.get("repetidos") or []) + list(repetidos)
    islas[pais] = prev
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def entrada_sin_contacto(lead: dict) -> dict[str, str]:
    return {
        "nombre": (lead.get("nombre") or "—")[:120],
        "fuente": (lead.get("fuente") or "")[:60],
        "direccion": (lead.get("direccion") or "")[:200],
        "place_id": (lead.get("place_id") or "")[:80],
        "web": (lead.get("web") or "")[:200],
    }


def append_sin_contacto_diario(pais: str, filas: list[dict[str, Any]]) -> None:
    if not filas:
        return
    path = state_file(f"sin_contacto_{fecha_archivo_dia()}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict = {}
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
    payload.setdefault("fecha", fecha_archivo_dia())
    payload["actualizado"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    islas = payload.setdefault("islas", {})
    prev = list(islas.get(pais) or [])
    vistos = {(r.get("nombre"), r.get("place_id")) for r in prev}
    for fila in filas:
        clave = (fila.get("nombre"), fila.get("place_id"))
        if clave not in vistos:
            prev.append(fila)
            vistos.add(clave)
    islas[pais] = prev
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def resumen_motivos(descartes: list[dict[str, Any]], max_motivos: int = 4) -> str:
    """'web muerta ×2, vape/smoke shop ×1' (los más frecuentes)."""
    cuenta: dict[str, int] = {}
    for row in descartes:
        mot = (row.get("motivo") or "descartado").strip()
        cuenta[mot] = cuenta.get(mot, 0) + 1
    orden = sorted(cuenta.items(), key=lambda kv: (-kv[1], kv[0]))
    partes = [f"{m} ×{n}" for m, n in orden[:max_motivos]]
    if len(orden) > max_motivos:
        partes.append(f"+{len(orden) - max_motivos} motivos")
    return ", ".join(partes)


def registrar_log_descartes_isla(
    pais: str,
    descartes: list[dict[str, Any]],
    repetidos: list[dict[str, Any]],
) -> None:
    if not descartes and not repetidos:
        return
    registrar_evento(
        {
            "evento": "buscar_descartes_isla",
            "pais": pais,
            "descartes": descartes,
            "repetidos": repetidos,
        }
    )


def lineas_resumen_descartes(
    descartes: list[dict[str, Any]],
    repetidos: list[dict[str, Any]],
    *,
    max_items: int = TELEGRAM_MAX_DESCARTES,
) -> list[str]:
    lineas: list[str] = []
    items: list[str] = []
    for row in descartes:
        nom = row.get("nombre") or "—"
        mot = row.get("motivo") or "descartado"
        items.append(f"· {nom}: {mot}")
    for row in repetidos:
        nom = row.get("nombre") or "—"
        contra = row.get("contra") or "cola/registro"
        fecha = (row.get("fecha") or "")[:16]
        items.append(f"· {nom}: repetido ({contra}{', ' + fecha if fecha else ''})")
    if not items:
        return lineas
    lineas.append("Descartes:")
    lineas.extend(items[:max_items])
    restantes = len(items) - max_items
    if restantes > 0:
        lineas.append(f"… y {restantes} más (log / descartados_{fecha_archivo_dia()}.json)")
    return lineas
