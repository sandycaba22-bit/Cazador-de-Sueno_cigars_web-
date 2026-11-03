"""Comprueba credenciales antes de arrancar. No llama a la red."""
from __future__ import annotations

import os
import re

_TOKEN_RE = re.compile(r"^\d+:[A-Za-z0-9_-]{20,}$")
_CHAT_RE = re.compile(r"^-?\d{5,}$")
_PLACEHOLDER = {
    "",
    "pega_aqui",
    "tu_token",
    "changeme",
    "xxx",
}


def _valor(*nombres: str) -> str:
    for nombre in nombres:
        raw = os.getenv(nombre, "").strip()
        if raw:
            return raw
    return ""


def errores_arranque() -> list[str]:
    """Solo lo que impide vigilar: token o chat de las tarjetas."""
    errores: list[str] = []
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or token.lower() in _PLACEHOLDER or not _TOKEN_RE.match(token):
        errores.append("TELEGRAM_BOT_TOKEN falta o no tiene el formato de BotFather (123:ABC…).")
    if not chat or not _CHAT_RE.match(chat):
        errores.append("TELEGRAM_CHAT_ID falta o no es el número del chat de las tarjetas.")
    return errores


def advertencias_arranque() -> list[str]:
    """No detienen el servicio. Quedan en el log."""
    avisos: list[str] = []
    chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    alertas = os.getenv("TELEGRAM_ALERTAS_CHAT_ID", "").strip()
    if not alertas or not _CHAT_RE.match(alertas):
        avisos.append(
            "TELEGRAM_ALERTAS_CHAT_ID falta o no es numérico. "
            "El servicio arranca, pero las alertas no salen a tu chat."
        )
    elif alertas == chat:
        avisos.append(
            "TELEGRAM_ALERTAS_CHAT_ID es el mismo que TELEGRAM_CHAT_ID. "
            "El servicio arranca, pero no mando alertas al chat de las tarjetas."
        )
    if os.getenv("B2B_ENVIO_REAL", "0").strip() == "1":
        tiene = False
        for n in (1,):
            correo = _valor(f"CORREO_REMITENTE_{n}", f"EMAIL_REMITENTE_{n}")
            clave = _valor(f"CORREO_CLAVE_{n}", f"EMAIL_CLAVE_{n}")
            if correo and "@" in correo and clave and len(clave) >= 8:
                tiene = True
        if not tiene:
            avisos.append(
                "B2B_ENVIO_REAL=1 pero falta un correo de Gmail con clave de aplicación "
                "(CORREO_REMITENTE_n y CORREO_CLAVE_n)."
            )
    fuente = (os.getenv("FUENTE_LEADS", "google") or "google").strip().lower()
    if fuente in ("google", "ambas"):
        clave_g = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
        if not clave_g or clave_g.lower() in _PLACEHOLDER or len(clave_g) < 10:
            avisos.append("GOOGLE_PLACES_API_KEY falta o es un marcador.")
    return avisos
