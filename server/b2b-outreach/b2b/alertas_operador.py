"""Avisos al chat del operador. Nunca al chat de las tarjetas (TELEGRAM_CHAT_ID)."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

from b2b.io_atomico import escribir_json
from b2b.paths import state_file


def chat_alertas() -> str:
    return os.getenv("TELEGRAM_ALERTAS_CHAT_ID", "").strip()


def _estado_path():
    return state_file("alertas_operador.json")


def _load() -> dict:
    path = _estado_path()
    if not path.is_file():
        return {"ultimas": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ultimas": {}}
    data.setdefault("ultimas", {})
    return data


def _flag(nombre: str) -> bool:
    return os.getenv(nombre, "0").strip() == "1"


def _correo_destino() -> str:
    return os.getenv("B2B_ALERTAS_CORREO", "").strip()


def alertar(clave: str, texto: str, *, cooldown_seg: int = 3600, enviar=None) -> bool:
    """Chat de alertas si existe. Si está vacío: chat de tarjetas y/o correo, o solo el log.

    Los dos canales nuevos quedan apagados si falta la variable. Una causa, una vez por hora.
    """
    data = _load()
    ahora = time.time()
    previo = float((data.get("ultimas") or {}).get(clave) or 0)
    if cooldown_seg and ahora - previo < cooldown_seg:
        return False
    data.setdefault("ultimas", {})[clave] = ahora
    escribir_json(_estado_path(), data)
    cuerpo = (texto or "")[:3500]
    chat = chat_alertas()
    if chat:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            return False
        if enviar is None:
            enviar = _enviar
        enviar(token, chat, cuerpo)
        return True
    envio_alguno = False
    if _flag("B2B_ALERTAS_EN_CHAT_TARJETAS"):
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        tarjetas = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if token and tarjetas:
            if enviar is None:
                enviar = _enviar
            enviar(token, tarjetas, "ALERTA\n" + cuerpo)
            envio_alguno = True
    destino = _correo_destino()
    if destino:
        try:
            if _correo_alerta(destino, cuerpo):
                envio_alguno = True
        except Exception:
            from b2b.logging_ops import registrar_evento

            registrar_evento({"evento": "alerta_correo_fallo", "clave": clave})
    if envio_alguno:
        return True
    from b2b.logging_ops import registrar_evento

    registrar_evento({"evento": "alerta_sin_chat", "clave": clave, "texto": cuerpo[:240]})
    return False


def _correo_alerta(destino: str, texto: str) -> bool:
    """Correo con la cuenta 1. Sin clave, o con el envío real apagado, no sale."""
    from email.message import EmailMessage

    from b2b.envio_correo import _enviar_smtp, cuentas_activas

    if os.getenv("B2B_ENVIO_REAL", "0").strip() != "1":
        return False
    cuenta = next((c for c in cuentas_activas() if c.get("n") == 1 and c.get("clave")), None)
    if cuenta is None:
        return False
    msg = EmailMessage()
    msg["From"] = cuenta["correo"]
    msg["To"] = destino
    msg["Subject"] = "ALERTA B2B"
    msg.set_content("ALERTA\n\n" + (texto or ""))
    _enviar_smtp(cuenta, msg)
    return True


def _enviar(token: str, chat: str, texto: str) -> None:
    if os.getenv("B2B_UNDER_TEST") == "1":
        from b2b.cortafuegos_tests import simular_envio

        simular_envio(texto)
        return
    import json as _json
    import urllib.request

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = _json.dumps({
        "chat_id": chat,
        "text": texto,
        "disable_web_page_preview": True,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        resp.read()


def marca() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
