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
HTML_LANG_RE = re.compile(
    r"<html[^>]*\slang=[\"']([a-zA-Z]{2,3}(?:[-_][a-zA-Z]{2,8})?)[\"']",
    re.I,
)
META_CONTENT_LANG_RE = re.compile(
    r"<meta[^>]+(?:http-equiv=[\"']content-language[\"'][^>]+content="
    r"|[\"']content[\"'][^>]+http-equiv=[\"']content-language[\"'])[\"']([^\"']+)[\"']",
    re.I,
)
OG_LOCALE_RE = re.compile(
    r"<meta[^>]+property=[\"']og:locale[\"'][^>]+content=[\"']([^\"']+)[\"']",
    re.I,
)
OG_LOCALE_ALT_RE = re.compile(
    r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+property=[\"']og:locale[\"']",
    re.I,
)
TAG_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.I | re.S)
STRIP_TAG_RE = re.compile(r"<[^>]+>")

IDIOMAS_BORRADOR = frozenset({"es", "en", "fr", "pt", "nl", "de", "it"})
MARCADORES_TEXTO: dict[str, tuple[str, ...]] = {
    "es": (
        "contacto",
        "tienda",
        "sobre nosotros",
        "envío",
        "puros",
        "cigarros",
        "humidor",
        "mayorista",
    ),
    "en": (
        "contact us",
        "about us",
        "shipping",
        "cigars",
        "humidor",
        "wholesale",
        "shop",
    ),
    "fr": (
        "contactez",
        "boutique",
        "à propos",
        "cigares",
        "humidor",
        "grossiste",
    ),
    "pt": (
        "contacto",
        "loja",
        "sobre nós",
        "charutos",
        "humidor",
        "grossista",
    ),
    "nl": ("contact", "winkel", "over ons", "sigaren", "wholesale"),
    "de": ("kontakt", "über uns", "zigarren", "humidor", "großhandel"),
    "it": ("contatti", "chi siamo", "sigari", "umidor", "ingrosso"),
}
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


def _normalizar_codigo_idioma(raw: str) -> str:
    token = (raw or "").strip().lower().replace("_", "-")
    if not token:
        return ""
    primario = token.split(",")[0].strip().split("-")[0]
    if primario in IDIOMAS_BORRADOR:
        return primario
    return ""


def _texto_visible(html: str) -> str:
    sin_bloques = TAG_RE.sub(" ", html)
    return STRIP_TAG_RE.sub(" ", sin_bloques)


def detectar_idioma_html(html: str) -> tuple[str, str]:
    """Devuelve (código idioma, fuente) a partir del HTML ya descargado."""
    cabecera = html[:12000]
    for regex, fuente in (
        (HTML_LANG_RE, "html lang"),
        (META_CONTENT_LANG_RE, "meta content-language"),
        (OG_LOCALE_RE, "og:locale"),
        (OG_LOCALE_ALT_RE, "og:locale"),
    ):
        match = regex.search(cabecera)
        if match:
            codigo = _normalizar_codigo_idioma(match.group(1))
            if codigo:
                return codigo, fuente
    texto = _texto_visible(html)[:20000].lower()
    if len(texto.strip()) < 40:
        return "", ""
    puntajes = {
        lang: sum(texto.count(palabra) for palabra in palabras)
        for lang, palabras in MARCADORES_TEXTO.items()
    }
    mejor = max(puntajes, key=puntajes.get)
    if puntajes[mejor] >= 2:
        return mejor, "texto web"
    return "", ""


def detectar_idioma_desde_web(web: str) -> tuple[str, str]:
    """Una petición a la home (robots permitiendo)."""
    if not web.startswith(("http://", "https://")):
        return "", ""
    if not permitido_por_robots(web):
        return "", ""
    time.sleep(FETCH_DELAY)
    try:
        html = unescape(_fetch(web))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return "", ""
    return detectar_idioma_html(html)


def analizar_sitio_prospecto(web: str) -> dict[str, str]:
    """Correo público + idioma del sitio en una sola pasada (respeta robots y pausa)."""
    vacio = {
        "correo": "",
        "fuente_correo": "",
        "idioma_web": "",
        "idioma_fuente": "",
    }
    if not web.startswith(("http://", "https://")):
        return vacio
    correo = ""
    fuente_correo = ""
    idioma_web = ""
    idioma_fuente = ""
    for url in _urls_contacto(web):
        if not permitido_por_robots(url):
            continue
        time.sleep(FETCH_DELAY)
        try:
            html = unescape(_fetch(url))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            continue
        if not idioma_web:
            idioma_web, idioma_fuente = detectar_idioma_html(html)
        if not correo:
            emails = _emails_en_html(html, web)
            if emails:
                correo, fuente_correo = emails[0], url
        if correo and idioma_web:
            break
    return {
        "correo": correo,
        "fuente_correo": fuente_correo,
        "idioma_web": idioma_web,
        "idioma_fuente": idioma_fuente,
    }


def _urls_contacto(web: str) -> list[str]:
    parsed = urllib.parse.urlparse(web)
    base = f"{parsed.scheme}://{parsed.netloc}"
    urls = [web]
    for path in CONTACT_PATHS:
        urls.append(base + path)
    return urls


def extraer_correo_publico(web: str) -> tuple[str, str]:
    """Devuelve (correo, url_fuente). Nunca adivina correos."""
    info = analizar_sitio_prospecto(web)
    return info["correo"], info["fuente_correo"]
