"""Barrera de red para tests. No deja salir un mensaje real a Telegram ni a Google."""
from __future__ import annotations

import os
import sys

MENSAJES: list[str] = []
_INSTALADO = False

TOKEN_FALSO = "000000000:TEST_TOKEN_NO_REAL_DO_NOT_SEND"
CHAT_FALSO = "1"
CHAT_ALERTAS_FALSO = "2"


class LlamadaRealProhibida(BaseException):
    """No hereda de Exception: los except Exception del bot no pueden tragársela."""


def bajo_test() -> bool:
    if os.getenv("B2B_UNDER_TEST") == "1":
        return True
    argv = " ".join(sys.argv)
    if "unittest" in argv or "pytest" in argv:
        return True
    return any("test_" in parte for parte in sys.argv)


def _url_de(objeto) -> str:
    if hasattr(objeto, "full_url"):
        return str(objeto.full_url)
    return str(getattr(objeto, "url", objeto))


def _prohibido(url: str) -> None:
    bajo = url.lower()
    if "api.telegram.org" in bajo or "places.googleapis.com" in bajo:
        limpio = url.split("/bot", 1)[0]
        raise LlamadaRealProhibida(
            "Un test intentó una llamada real a "
            f"{limpio}. Los tests no pueden usar Telegram ni Google Places."
        )


def instalar() -> None:
    global _INSTALADO
    if _INSTALADO:
        return
    _INSTALADO = True
    os.environ["B2B_UNDER_TEST"] = "1"
    os.environ["B2B_ENVIO_REAL"] = "0"
    os.environ["TELEGRAM_BOT_TOKEN"] = TOKEN_FALSO
    os.environ["TELEGRAM_CHAT_ID"] = CHAT_FALSO
    os.environ["TELEGRAM_ALERTAS_CHAT_ID"] = CHAT_ALERTAS_FALSO
    os.environ["GOOGLE_PLACES_API_KEY"] = ""
    os.environ.setdefault("FUENTE_LEADS", "simulado")

    import urllib.request

    original = urllib.request.urlopen

    def urlopen(url, *args, **kwargs):
        _prohibido(_url_de(url))
        return original(url, *args, **kwargs)

    urllib.request.urlopen = urlopen

    try:
        import requests

        original_post = requests.post
        original_request = requests.sessions.Session.request

        def post(url, *args, **kwargs):
            _prohibido(str(url))
            return original_post(url, *args, **kwargs)

        def request(self, method, url, *args, **kwargs):
            _prohibido(str(url))
            return original_request(self, method, url, *args, **kwargs)

        requests.post = post
        requests.sessions.Session.request = request
    except ImportError:
        pass


def simular_envio(texto: str) -> None:
    MENSAJES.append(texto or "")
