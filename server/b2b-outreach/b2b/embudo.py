"""Resumen del embudo B2B para Telegram (/embudo y aviso 20:00 RD)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from b2b.logging_ops import registrar_evento
from b2b.paths import log_dir, state_file
from b2b.zonas import tz


def _hoy_rd(ahora: datetime | None = None) -> str:
    from b2b.zona_horaria import zona_operador

    zona = zona_operador()
    momento = ahora or datetime.now(timezone.utc)
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(zona).strftime("%Y-%m-%d")


def _contar_eventos(dia: str) -> dict[str, int]:
    cont: dict[str, int] = {}
    path = log_dir() / f"busqueda-{dia.replace('-', '')}.jsonl"
    # También acepta YYYYMMDD en el nombre.
    if not path.is_file():
        path = log_dir() / f"busqueda-{dia}.jsonl"
    if not path.is_file():
        # Nombre típico busqueda-YYYYMMDD.jsonl
        compacto = dia.replace("-", "")
        path = log_dir() / f"busqueda-{compacto}.jsonl"
    if not path.is_file():
        return cont
    try:
        with path.open(encoding="utf-8") as handle:
            for linea in handle:
                try:
                    ev = json.loads(linea)
                except json.JSONDecodeError:
                    continue
                clave = (ev.get("evento") or "").strip()
                if clave:
                    cont[clave] = cont.get(clave, 0) + 1
                if clave == "busqueda_pais":
                    cont["prospectos_nuevos"] = cont.get("prospectos_nuevos", 0) + int(
                        ev.get("prospectos_nuevos") or 0
                    )
    except OSError:
        pass
    return cont


def _despacho_dia(dia: str) -> dict:
    path = state_file("despachador_tarjetas.json")
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    bloque = data.get("tarjetas_dia") or {}
    if bloque.get("dia") != dia:
        return {"enviadas": 0}
    return {
        "enviadas": int(bloque.get("manana") or 0) + int(bloque.get("tarde") or 0),
        "manana": int(bloque.get("manana") or 0),
        "tarde": int(bloque.get("tarde") or 0),
    }


def _estados_leads() -> dict[str, int]:
    path = state_file("leads_estado.json")
    out: dict[str, int] = {}
    if not path.is_file():
        return out
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return out
    for meta in (data.get("leads") or {}).values():
        if not isinstance(meta, dict):
            continue
        est = (meta.get("estado") or "").strip() or "desconocido"
        out[est] = out.get(est, 0) + 1
    return out


def texto_embudo(ahora: datetime | None = None) -> str:
    dia = _hoy_rd(ahora)
    ev = _contar_eventos(dia)
    desp = _despacho_dia(dia)
    estados = _estados_leads()
    lineas = [
        f"📊 Embudo B2B · {dia}",
        f"Encontrados/nuevos (log): {ev.get('prospectos_nuevos', 0)}",
        f"Tarjetas Telegram hoy: {desp.get('enviadas', 0)} (mañana {desp.get('manana', 0)} · tarde {desp.get('tarde', 0)})",
        f"Aprobadas: {estados.get('aprobado', 0) + estados.get('enviado', 0)} · "
        f"Enviadas correo: {estados.get('enviado', 0)} · "
        f"Descartadas: {estados.get('descartado', 0)}",
        f"Omitidas/vencidas (eventos): {ev.get('tarjeta_vencida', 0)}",
        f"Rebotes: {estados.get('reboto', 0)} · Respuestas: {estados.get('respondio', 0)} · "
        f"Bajas: {estados.get('baja', 0) + ev.get('exclusion_correo', 0)}",
        f"Fallos Telegram: {ev.get('telegram_prospecto_fallo', 0) + ev.get('telegram_alerta_fallo', 0)}",
    ]
    return "\n".join(lineas)


def _ruta_aviso() -> Path:
    return state_file("embudo_aviso.json")


def emitir_si_toca(ahora: datetime | None = None) -> str:
    """A las 20:00 hora del operador manda el resumen una vez al día. Devuelve el texto o ''."""
    from b2b.zona_horaria import zona_operador

    zona = zona_operador()
    momento = ahora or datetime.now(timezone.utc)
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    local = momento.astimezone(zona)
    if local.hour < 20:
        return ""
    dia = local.strftime("%Y-%m-%d")
    path = _ruta_aviso()
    previo = {}
    if path.is_file():
        try:
            previo = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previo = {}
    if previo.get("dia") == dia:
        return ""
    texto = texto_embudo(momento)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"dia": dia, "enviado": True}, indent=2) + "\n", encoding="utf-8")
    registrar_evento({"evento": "embudo_diario", "dia": dia})
    return texto
