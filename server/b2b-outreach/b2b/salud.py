"""Chequeos periódicos y texto de /salud. No abre red."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from b2b.paths import state_file


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _parse(marca: str) -> datetime | None:
    if not marca:
        return None
    try:
        momento = datetime.fromisoformat(marca)
    except ValueError:
        return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento


def latido(ahora: datetime | None = None) -> None:
    ahora = ahora or _ahora()
    path = state_file("salud_latido.txt")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ahora.isoformat(timespec="seconds"), encoding="utf-8")


def servicio_estuvo_caido(ahora: datetime | None = None, umbral_min: int = 15) -> bool:
    """Lo usa scripts/comprobar_latido.py (timer systemd), no el proceso de --vigilar."""
    ahora = ahora or _ahora()
    path = state_file("salud_latido.txt")
    if not path.is_file():
        return False
    try:
        previo = _parse(path.read_text(encoding="utf-8").strip())
    except OSError:
        return False
    if not previo:
        return False
    return ahora - previo > timedelta(minutes=umbral_min)


def texto_salud(cola: Path | None = None, ahora: datetime | None = None) -> str:
    ahora = ahora or _ahora()
    from b2b.budget import estado
    from b2b.despachador_tarjetas import abiertas_ahora
    from b2b.paths import queue_dir

    cola = cola or queue_dir()
    inbox = (cola / "inbox") if cola else None
    pendientes = 0
    if inbox and inbox.is_dir():
        pendientes = sum(1 for p in inbox.glob("*.json") if p.is_file())
    abiertas = len(abiertas_ahora(ahora))
    envios = _ultimo_envio()
    imap = _ultimo_imap()
    est = estado()
    pausa = "sí" if _pausado() else "no"
    return "\n".join([
        "Salud del bot",
        f"- Servicio: en marcha (pausa={pausa})",
        f"- Cola inbox: {pendientes}",
        f"- Tarjetas abiertas: {abiertas}",
        f"- Último envío: {envios or 'ninguno'}",
        f"- Google: hoy {est['dia']}/{est['max_dia']}, mes {est['mes']}/{est['max_mes']}, "
        f"tanda {est['tanda']} {est['tanda_llamadas']}/{est['max_tanda']}",
        f"- Última lectura IMAP: {imap or 'nunca'}",
    ])


def _pausado() -> bool:
    try:
        from b2b.telegram_control import esta_pausado

        return esta_pausado()
    except Exception:
        return False


def _ultimo_envio() -> str:
    path = state_file("envios_correo.json")
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return (data.get("ultimo_envio") or "").strip()


def _ultimo_imap() -> str:
    path = state_file("imap_bajas_estado.json")
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return (data.get("ultimo_check") or "").strip()


def avisos_periodicos(cola: Path, ahora: datetime | None = None) -> list[tuple[str, str]]:
    """(clave, texto) de condiciones que hay que avisar. No envía."""
    ahora = ahora or _ahora()
    avisos: list[tuple[str, str]] = []
    inbox = cola / "inbox"
    pendientes = 0
    if inbox.is_dir():
        for path in inbox.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict) and not data.get("telegram_notificado"):
                pendientes += 1
    ultimo = _parse(_ultimo_envio()) or _parse(_ultima_tarjeta(ahora))
    if pendientes > 0 and (ultimo is None or ahora - ultimo >= timedelta(hours=3)):
        avisos.append((
            "sin_tarjetas_3h",
            f"⚠️ 0 tarjetas enviadas en 3 h y la cola tiene {pendientes} pendiente(s).",
        ))
    if os.getenv("B2B_ENVIO_REAL", "0").strip() == "1":
        imap = _parse(_ultimo_imap())
        if imap is None or ahora - imap >= timedelta(hours=1):
            avisos.append((
                "imap_sin_lectura_1h",
                "⚠️ El lector de Gmail no ha leído en 1 h. Las bajas (unsubscribe) dependen de eso.",
            ))
    return avisos


def _ultima_tarjeta(ahora: datetime) -> str:
    path = state_file("despachador_tarjetas.json")
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    marcas = []
    for info in (data.get("abiertas") or {}).values():
        if isinstance(info, dict) and info.get("enviada_en"):
            marcas.append(info["enviada_en"])
    return max(marcas) if marcas else ""
