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


def alertar(clave: str, texto: str, *, cooldown_seg: int = 3600, enviar=None) -> bool:
    """Manda el aviso solo a TELEGRAM_ALERTAS_CHAT_ID. Sin ese chat, no envía a nadie."""
    chat = chat_alertas()
    data = _load()
    ahora = time.time()
    previo = float((data.get("ultimas") or {}).get(clave) or 0)
    if cooldown_seg and ahora - previo < cooldown_seg:
        return False
    data.setdefault("ultimas", {})[clave] = ahora
    escribir_json(_estado_path(), data)
    if not chat:
        from b2b.logging_ops import registrar_evento

        registrar_evento({"evento": "alerta_sin_chat", "clave": clave, "texto": (texto or "")[:240]})
        return False
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return False
    cuerpo = (texto or "")[:3500]
    if enviar is None:
        enviar = _enviar
    enviar(token, chat, cuerpo)
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
