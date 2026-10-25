"""Registro de control. No envía correo ni WhatsApp: solo anota la aprobación manual."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta

from b2b.correo_corporativo import clasificar_correo
from b2b.logging_ops import registrar_evento
from b2b.mercados_exportacion import es_canada, idioma_exportacion
from b2b.paths import state_file

REGISTRO_PATH = None
ESTADOS = ("borrador", "pendiente_aprobacion", "aprobado", "enviado", "descartado")


def ruta_registro():
    return REGISTRO_PATH or state_file("registro_control.json")


def _ahora() -> datetime:
    return datetime.now().astimezone()


def _ts(momento: datetime | None = None) -> str:
    return (momento or _ahora()).isoformat(timespec="seconds")


def _limite_diario() -> int:
    try:
        return max(1, int(os.getenv("B2B_ENVIOS_MAX_DIA", "15") or "15"))
    except ValueError:
        return 15


def _pausa_segundos() -> float:
    try:
        return max(0.0, float(os.getenv("B2B_PAUSA_ENTRE_ENVIOS_SEC", "120") or "120"))
    except ValueError:
        return 120.0


def _cargar() -> list[dict]:
    path = ruta_registro()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return list(data.get("registros") or []) if isinstance(data, dict) else []


def _guardar(filas: list[dict]) -> None:
    path = ruta_registro()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"registros": filas}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _linea(row: dict) -> str:
    return (
        f"CONTROL empresa={row.get('empresa') or ''} pais={row.get('pais') or ''} "
        f"tipo={row.get('tipo') or ''} idioma={row.get('idioma') or ''} "
        f"estado={row.get('estado') or ''} ts={row.get('ts') or ''}"
    )


def _anotar(row: dict) -> dict:
    print(_linea(row))
    registrar_evento({"evento": "control_envio", **{k: row.get(k) or "" for k in (
        "id", "empresa", "pais", "tipo", "idioma", "estado", "ts", "correo_clase",
    )}})
    return row


def _buscar(filas: list[dict], registro_id: str) -> dict | None:
    for row in filas:
        if row.get("id") == registro_id:
            return row
    return None


def preparar(
    empresa: str,
    pais: str,
    tipo: str,
    idioma: str = "",
    correo: str = "",
    web: str = "",
) -> dict:
    if es_canada(pais):
        raise ValueError("Canadá está excluido de la cola de exportación.")
    idioma_final = (idioma or idioma_exportacion(pais) or "en").strip().lower()
    clase = clasificar_correo(correo, web) if (correo or "").strip() else ""
    row = {
        "id": uuid.uuid4().hex[:12],
        "empresa": (empresa or "").strip(),
        "pais": (pais or "").strip(),
        "tipo": (tipo or "").strip() or "tienda",
        "idioma": idioma_final,
        "estado": "borrador",
        "ts": _ts(),
        "correo": (correo or "").strip(),
        "correo_clase": clase,
    }
    filas = _cargar()
    filas.append(row)
    _guardar(filas)
    return _anotar(row)


def aprobar(registro_id: str) -> dict:
    """Marca el borrador como aprobado. No envía el mensaje."""
    filas = _cargar()
    row = _buscar(filas, registro_id)
    if row is None:
        raise KeyError(registro_id)
    if row.get("estado") == "enviado":
        return row
    row["estado"] = "aprobado"
    row["ts"] = _ts()
    _guardar(filas)
    return _anotar(row)


def confirmar_envio(registro_id: str, ahora: datetime | None = None) -> dict:
    """Registra que la persona confirmó el envío. No abre correo ni WhatsApp."""
    filas = _cargar()
    row = _buscar(filas, registro_id)
    if row is None:
        raise KeyError(registro_id)
    def rechazo(motivo: str) -> dict:
        print(f"{_linea(row)} motivo={motivo}")
        return {**row, "ok": False, "motivo": motivo}

    if row.get("estado") != "aprobado":
        return rechazo("requiere_aprobacion")
    clase = row.get("correo_clase") or ""
    if row.get("correo") and clase not in {"corporativo", "corporativo_personal"}:
        return rechazo("correo_no_corporativo")
    momento = ahora or _ahora()
    hoy = momento.date().isoformat()
    enviados = [r for r in filas if r.get("estado") == "enviado" and str(r.get("ts") or "").startswith(hoy)]
    if len(enviados) >= _limite_diario():
        return rechazo("limite_diario")
    pausa = _pausa_segundos()
    if pausa > 0 and enviados:
        ultimo = max(datetime.fromisoformat(r["ts"]) for r in enviados)
        if momento - ultimo < timedelta(seconds=pausa):
            return rechazo("pausa")
    row["estado"] = "enviado"
    row["ts"] = _ts(momento)
    row["ok"] = True
    _guardar(filas)
    return _anotar(row)
