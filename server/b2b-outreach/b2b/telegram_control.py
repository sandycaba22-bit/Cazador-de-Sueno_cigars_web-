from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from b2b.paths import state_file

CONTROL_PATH = state_file("telegram_control.json")


def _load() -> dict:
    if not CONTROL_PATH.is_file():
        return {"pausado": False, "envios_hora": []}
    try:
        return json.loads(CONTROL_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"pausado": False, "envios_hora": []}


def _save(data: dict) -> None:
    CONTROL_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONTROL_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def esta_pausado() -> bool:
    return bool(_load().get("pausado"))


def set_pausado(valor: bool) -> None:
    data = _load()
    data["pausado"] = valor
    _save(data)


def _limite_por_hora() -> int:
    try:
        return max(1, int(os.getenv("B2B_TELEGRAM_MAX_POR_HORA", "6") or "6"))
    except ValueError:
        return 6


def _podar_envios(data: dict) -> dict:
    ahora = time.time()
    ventana = [t for t in data.get("envios_hora") or [] if ahora - float(t) < 3600]
    data["envios_hora"] = ventana
    return data


def puede_enviar_telegram() -> bool:
    if esta_pausado():
        return False
    data = _podar_envios(_load())
    _save(data)
    return len(data.get("envios_hora") or []) < _limite_por_hora()


def registrar_envio_telegram() -> None:
    data = _podar_envios(_load())
    data.setdefault("envios_hora", []).append(time.time())
    _save(data)


def procesar_comandos_chat(token: str, chat_id: str) -> list[str]:
    """Lee updates y aplica /pausa /seguir. Devuelve acks enviados."""
    url = f"https://api.telegram.org/bot{token}/getUpdates?timeout=1&limit=5"
    acks: list[str] = []
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return acks
    for upd in body.get("result") or []:
        msg = upd.get("message") or {}
        text = (msg.get("text") or "").strip().lower()
        cid = str(msg.get("chat", {}).get("id", ""))
        if cid != str(chat_id):
            continue
        if text in ("/pausa", "pausa"):
            set_pausado(True)
            acks.append("⏸ Búsqueda Telegram pausada (/seguir para reanudar).")
        elif text in ("/seguir", "seguir", "/resume"):
            set_pausado(False)
            acks.append("▶️ Envíos Telegram reanudados.")
    return acks
