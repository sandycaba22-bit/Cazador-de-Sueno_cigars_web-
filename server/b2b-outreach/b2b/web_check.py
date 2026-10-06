from __future__ import annotations

import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from b2b.fuentes.http_polite import MIN_INTERVAL, USER_AGENT, _dominio, permitido_robots
from b2b.fuentes.http_polite import DOMAIN_LAST_FETCH

WEB_CHECK_TIMEOUT = 15
MAX_REDIRECTS = 3
RETRY_ESPERAS = (10, 30)

PARKING_RE = re.compile(
    r"domain\s+for\s+sale|buy\s+this\s+domain|parked\s+domain|"
    r"this\s+domain\s+is\s+for\s+sale|sedoparking|dan\.com",
    re.I,
)


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _respetar_pausa_dominio(url: str) -> None:
    dom = _dominio(url)
    ahora = time.time()
    ultimo = DOMAIN_LAST_FETCH.get(dom, 0.0)
    if ahora - ultimo < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - (ahora - ultimo))


def _marcar_dominio(url: str) -> None:
    DOMAIN_LAST_FETCH[_dominio(url)] = time.time()


def _clasificar_fallo(error: BaseException, http_code: int | None = None) -> str:
    if http_code in (404, 410):
        return "MUERTA"
    if http_code == 429 or (http_code is not None and 500 <= http_code <= 599):
        return "ERROR_TEMPORAL"
    if isinstance(error, ssl.SSLError):
        return "MUERTA"
    if isinstance(error, urllib.error.HTTPError):
        if error.code in (404, 410):
            return "MUERTA"
        if error.code == 429 or 500 <= error.code <= 599:
            return "ERROR_TEMPORAL"
    if isinstance(error, urllib.error.URLError):
        reason = getattr(error, "reason", None)
        if isinstance(reason, socket.gaierror):
            return "MUERTA"
        if isinstance(reason, TimeoutError) or isinstance(error.reason, TimeoutError):
            return "ERROR_TEMPORAL"
    if isinstance(error, TimeoutError):
        return "ERROR_TEMPORAL"
    return "ERROR_TEMPORAL"


def _parece_parking(body: bytes) -> bool:
    if not body:
        return False
    texto = body[:12000].decode("utf-8", errors="replace")
    return bool(PARKING_RE.search(texto))


def _get_una_vez(url: str) -> tuple[str, int | None, bytes, BaseException | None]:
    """GET manual con redirects limitados. Devuelve (clase, http, body, error)."""
    actual = url
    ultimo_error: BaseException | None = None
    ultimo_code: int | None = None
    body = b""
    for _ in range(MAX_REDIRECTS + 1):
        req = urllib.request.Request(
            actual,
            headers={"User-Agent": USER_AGENT},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=WEB_CHECK_TIMEOUT) as resp:
                ultimo_code = resp.status
                body = resp.read(16000)
                if 200 <= ultimo_code < 300:
                    if _parece_parking(body):
                        return "MUERTA", ultimo_code, body, None
                    return "OK", ultimo_code, body, None
                if ultimo_code in (404, 410):
                    return "MUERTA", ultimo_code, body, None
                if ultimo_code == 429 or 500 <= ultimo_code <= 599:
                    return "ERROR_TEMPORAL", ultimo_code, body, None
                return "ERROR_TEMPORAL", ultimo_code, body, None
        except urllib.error.HTTPError as error:
            ultimo_error = error
            ultimo_code = error.code
            if error.code in (301, 302, 303, 307, 308):
                destino = error.headers.get("Location")
                if destino:
                    actual = urllib.parse.urljoin(actual, destino)
                    continue
            clase = _clasificar_fallo(error, error.code)
            return clase, error.code, b"", error
        except BaseException as error:
            ultimo_error = error
            return _clasificar_fallo(error, ultimo_code), ultimo_code, b"", error
    return "ERROR_TEMPORAL", ultimo_code, body, ultimo_error


def chequear_web(url: str, *, simulado: bool = False) -> dict:
    """
    Clasifica la web del negocio. Campos: web_clase, web_estado, web_http, fecha_chequeo.
    """
    vacio = {
        "web_clase": "OMITIDO",
        "web_estado": "omitido",
        "web_http": None,
        "fecha_chequeo": _ahora_iso(),
    }
    if simulado or not (url or "").startswith(("http://", "https://")):
        return vacio
    if not permitido_robots(url):
        out = dict(vacio)
        out["web_clase"] = "ROBOTS"
        out["web_estado"] = "web_no_verificada"
        return out

    _respetar_pausa_dominio(url)
    clase, http, _body, _err = _get_una_vez(url)
    _marcar_dominio(url)

    if clase == "OK":
        return {
            "web_clase": "OK",
            "web_estado": "OK",
            "web_http": http,
            "fecha_chequeo": _ahora_iso(),
        }

    if clase == "MUERTA":
        return {
            "web_clase": "MUERTA",
            "web_estado": "MUERTA",
            "web_http": http,
            "fecha_chequeo": _ahora_iso(),
        }

    # ERROR_TEMPORAL — reintentos 10s y 30s
    for espera in RETRY_ESPERAS:
        time.sleep(espera)
        _respetar_pausa_dominio(url)
        clase, http, _, _ = _get_una_vez(url)
        _marcar_dominio(url)
        if clase == "OK":
            return {
                "web_clase": "OK",
                "web_estado": "OK",
                "web_http": http,
                "fecha_chequeo": _ahora_iso(),
            }
        if clase == "MUERTA":
            return {
                "web_clase": "MUERTA",
                "web_estado": "MUERTA",
                "web_http": http,
                "fecha_chequeo": _ahora_iso(),
            }

    return {
        "web_clase": "ERROR_TEMPORAL",
        "web_estado": "web_no_verificada",
        "web_http": http,
        "fecha_chequeo": _ahora_iso(),
    }
