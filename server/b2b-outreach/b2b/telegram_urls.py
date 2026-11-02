"""URLs válidas para botones inline de Telegram (sin mailto, sin espacios)."""
from __future__ import annotations

import re
from urllib.parse import urlsplit

# Telegram suele rechazar URLs > ~2000 y cualquier esquema que no sea http(s).
_MAX = 2000
_ESPACIO = re.compile(r"\s")


def url_boton_valida(url: str) -> bool:
    bruto = (url or "").strip()
    if not bruto or len(bruto) > _MAX or _ESPACIO.search(bruto):
        return False
    if not bruto.startswith(("http://", "https://")):
        return False
    try:
        partes = urlsplit(bruto)
    except Exception:
        return False
    if not partes.netloc or " " in partes.netloc:
        return False
    return True


def filtrar_teclado(markup: dict | None) -> dict:
    """Quita botones URL inválidos. Conserva callback_data."""
    if not markup or not isinstance(markup, dict):
        return {"inline_keyboard": []}
    filas_out: list[list[dict]] = []
    for fila in markup.get("inline_keyboard") or []:
        nueva = []
        for boton in fila:
            if not isinstance(boton, dict):
                continue
            if "url" in boton:
                if url_boton_valida(boton.get("url") or ""):
                    nueva.append(boton)
                continue
            nueva.append(boton)
        if nueva:
            filas_out.append(nueva)
    if not filas_out:
        filas_out = [[]]
    return {"inline_keyboard": filas_out}


def es_error_url_boton(exc: BaseException | str) -> bool:
    texto = str(exc)
    return "BUTTON_URL_INVALID" in texto or "button_url_invalid" in texto.lower()


def teclado_solo_callbacks(markup: dict | None) -> dict:
    """Último recurso: solo Enviado / Descartar / callbacks, sin URL."""
    filas_out: list[list[dict]] = []
    for fila in (markup or {}).get("inline_keyboard") or []:
        nueva = [b for b in fila if isinstance(b, dict) and "callback_data" in b and "url" not in b]
        if nueva:
            filas_out.append(nueva)
    if not filas_out:
        filas_out = [[
            {"text": "✅ Enviado", "callback_data": "b2be:manual"},
            {"text": "🗑 Descartar", "callback_data": "b2bd:manual"},
        ]]
    return {"inline_keyboard": filas_out}
