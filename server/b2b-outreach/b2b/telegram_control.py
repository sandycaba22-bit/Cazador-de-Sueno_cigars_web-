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
        return max(1, int(os.getenv("B2B_TELEGRAM_MAX_POR_HORA", "30") or "30"))
    except ValueError:
        return 30


def pausa_entre_mensajes() -> None:
    try:
        sec = float(os.getenv("B2B_TELEGRAM_PAUSE_SEC", "4") or "4")
    except ValueError:
        sec = 4.0
    if sec > 0:
        time.sleep(sec)


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


def _telegram_post(token: str, method: str, payload: dict) -> dict | None:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None


def _manejar_callback(token: str, chat_id: str, cb: dict) -> str | None:
    from b2b.telegram_gestion import (
        agregar_no_contactar,
        marcar_gestionado_telegram,
        quitar_pendiente,
        resolver_pendiente,
    )

    data = (cb.get("data") or "").strip()
    if not data.startswith("b2b"):
        return None
    cid = str((cb.get("message") or {}).get("chat", {}).get("id", ""))
    if cid != str(chat_id):
        return None
    accion = "enviado" if data.startswith("b2be:") else "descartado" if data.startswith("b2bd:") else ""
    tok = data.split(":", 1)[-1] if ":" in data else ""
    if not accion or not tok:
        return None
    pend = resolver_pendiente(tok) or {}
    lead = {
        "nombre": pend.get("nombre") or "",
        "web": pend.get("web") or "",
        "pais": pend.get("pais") or "",
    }
    marcar_gestionado_telegram(lead, accion)
    if accion == "descartado":
        agregar_no_contactar(lead["nombre"], lead["web"], motivo="telegram_descartar")
    quitar_pendiente(tok)
    cb_id = cb.get("id")
    if cb_id:
        _telegram_post(token, "answerCallbackQuery", {"callback_query_id": cb_id})
    etiqueta = "✅ Enviado" if accion == "enviado" else "🗑 Descartado"
    msg_id = (cb.get("message") or {}).get("message_id")
    if msg_id:
        _telegram_post(
            token,
            "editMessageReplyMarkup",
            {"chat_id": chat_id, "message_id": msg_id, "reply_markup": {"inline_keyboard": []}},
        )
    nombre = lead.get("nombre") or "—"
    return f"{etiqueta}: {nombre}"


def procesar_comandos_chat(token: str, chat_id: str) -> list[str]:
    """Lee updates: /pausa, /seguir y botones Enviado/Descartar."""
    data = _load()
    offset = int(data.get("update_offset") or 0)
    url = f"https://api.telegram.org/bot{token}/getUpdates?timeout=1&limit=10&offset={offset}"
    acks: list[str] = []
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return acks
    for upd in body.get("result") or []:
        uid = int(upd.get("update_id") or 0)
        if uid >= offset:
            data["update_offset"] = uid + 1
        cb = upd.get("callback_query")
        if cb:
            ack = _manejar_callback(token, chat_id, cb)
            if ack:
                acks.append(ack)
            continue
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
    _save(data)
    return acks
