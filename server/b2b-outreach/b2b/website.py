from __future__ import annotations

import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html import unescape

USER_AGENT = (
    "CazadorDeSuenos-B2B-Research/1.0 "
    "(+https://www.cazadordesuenocigars.com/wholesale.html; contacto mayorista)"
)
FETCH_DELAY = float(__import__("os").getenv("B2B_WEB_DELAY_SECONDS", "2") or "2")
TIMEOUT = 15

GENERIC_LOCAL = (
    "info",
    "contact",
    "contacto",
    "ventas",
    "sales",
    "hello",
    "shop",
    "commercial",
    "b2b",
    "wholesale",
)
MAILTO_RE = re.compile(r"mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", re.I)
EMAIL_RE = re.compile(r"\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b")
CONTACT_PATHS = (
    "/contact",
    "/contacto",
    "/contact-us",
    "/contacts",
    "/kontakt",
    "/contactez-nous",
)


def _fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        raw = response.read(500_000)
    return raw.decode("utf-8", errors="replace")


def _robots_url(base: str) -> str:
    parsed = urllib.parse.urlparse(base)
    return f"{parsed.scheme}://{parsed.netloc}/robots.txt"


def permitido_por_robots(url: str) -> bool:
    try:
        robots = _fetch(_robots_url(url))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return False
    path = urllib.parse.urlparse(url).path or "/"
    reglas: dict[str, list[str]] = {"*": []}
    current = "*"
    for line in robots.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("user-agent:"):
            current = line.split(":", 1)[1].strip()
            reglas.setdefault(current, [])
            continue
        if line.lower().startswith("disallow:"):
            reglas.setdefault(current, []).append(line.split(":", 1)[1].strip())
    for key in ("*", current):
        for rule in reglas.get(key, []):
            if rule and path.startswith(rule):
                return False
    return True


def _dominio_base(web: str) -> str:
    host = urllib.parse.urlparse(web).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _email_valido(email: str, web: str) -> bool:
    email = email.lower().strip()
    local, _, domain = email.partition("@")
    if not local or not domain:
        return False
    if local.split("+")[0] not in GENERIC_LOCAL:
        return False
    base = _dominio_base(web)
    return domain == base or domain.endswith("." + base)


def _emails_en_html(html: str, web: str) -> list[str]:
    candidatos: list[str] = []
    for match in MAILTO_RE.finditer(html):
        candidatos.append(match.group(1))
    for match in EMAIL_RE.finditer(html):
        candidatos.append(match.group(1))
    vistos: set[str] = set()
    ordenados: list[str] = []
    for email in candidatos:
        if not _email_valido(email, web):
            continue
        low = email.lower()
        if low in vistos:
            continue
        vistos.add(low)
        ordenados.append(low)
    return ordenados


def _urls_contacto(web: str) -> list[str]:
    parsed = urllib.parse.urlparse(web)
    base = f"{parsed.scheme}://{parsed.netloc}"
    urls = [web]
    for path in CONTACT_PATHS:
        urls.append(base + path)
    return urls


def extraer_correo_publico(web: str) -> tuple[str, str]:
    """Devuelve (correo, url_fuente). Nunca adivina correos."""
    if not web.startswith(("http://", "https://")):
        return "", ""
    for url in _urls_contacto(web):
        if not permitido_por_robots(url):
            continue
        time.sleep(FETCH_DELAY)
        try:
            html = unescape(_fetch(url))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            continue
        emails = _emails_en_html(html, web)
        if emails:
            return emails[0], url
    return "", ""
