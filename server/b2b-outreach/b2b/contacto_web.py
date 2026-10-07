"""Canales de contacto reales de un negocio: web propia, redes y datos extraídos de su web.

Solo se reporta lo que aparece en la página (nunca se adivinan correos ni páginas de contacto).
"""
from __future__ import annotations

import re
import urllib.error
import urllib.parse
from html import unescape

from b2b.fuentes import http_polite
from b2b.website import (
    _emails_en_html,
    _telefonos_en_html,
    _texto_visible,
    detectar_idioma_html,
    dominio_negocio,
    es_url_mapa,
)

REDES = {
    "instagram.com": "instagram",
    "instagr.am": "instagram",
    "facebook.com": "facebook",
    "fb.com": "facebook",
    "m.facebook.com": "facebook",
}

INSTAGRAM_RE = re.compile(r"https?://(?:www\.)?instagram\.com/([A-Za-z0-9_.]{2,30})/?", re.I)
FACEBOOK_RE = re.compile(r"https?://(?:www\.|m\.)?facebook\.com/([A-Za-z0-9_.\-]{2,80})/?", re.I)
WHATSAPP_RE = re.compile(
    r"https?://(?:wa\.me/|api\.whatsapp\.com/send/?\?phone=|(?:web\.)?whatsapp\.com/send/?\?phone=)\+?(\d{8,15})",
    re.I,
)
HREF_RE = re.compile(r"""<a\b[^>]*href\s*=\s*["']([^"'#]+)["'][^>]*>(.*?)</a>""", re.I | re.S)
FORM_RE = re.compile(r"<form\b(.*?)</form>", re.I | re.S)
CONTACTO_RE = re.compile(r"contact|contacto|kontakt|nous-contacter|contactez|contato", re.I)
CIGARROS_RE = re.compile(
    r"cigar|cigarro|cigare|habano|habanos|\bpuros?\b|sigaar|sigaren|humidor|humidificador|tabaquer|"
    r"tobacconist|charuto",
    re.I,
)
INSTAGRAM_NO_PERFIL = {"p", "reel", "reels", "explore", "stories", "accounts", "tv", "share"}
FACEBOOK_NO_PAGINA = {"sharer", "sharer.php", "share", "dialog", "plugins", "tr", "login", "watch"}

_CACHE_HTML: dict[str, str] = {}


def tipo_url(url: str) -> str:
    """'web' (propia), 'instagram', 'facebook', 'mapa' o '' (vacía / no http)."""
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return ""
    if es_url_mapa(url):
        return "mapa"
    host = urllib.parse.urlparse(url).netloc.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    for dominio, red in REDES.items():
        if host == dominio or host.endswith("." + dominio):
            return red
    return "web" if dominio_negocio(url) else ""


def normalizar_canales(lead: dict) -> dict:
    """Mueve redes sociales y links de mapa fuera de 'web' (in place)."""
    web = (lead.get("web") or "").strip()
    clase = tipo_url(web)
    if clase in ("instagram", "facebook"):
        if not lead.get(clase):
            lead[clase] = web
        lead["web"] = ""
    elif clase == "mapa":
        if not lead.get("maps_url"):
            lead["maps_url"] = web
        lead["web"] = ""
    return lead


def obtener_html(url: str) -> str:
    """GET educado (robots + pausa por dominio, vía http_polite). '' si no se pudo."""
    if url in _CACHE_HTML:
        return _CACHE_HTML[url]
    html = ""
    try:
        if http_polite.permitido_robots(url):
            html = unescape(http_polite.fetch_url(url))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
        html = ""
    _CACHE_HTML[url] = html
    return html


def _mismo_sitio(url: str, web: str) -> bool:
    return dominio_negocio(url) == dominio_negocio(web) and bool(dominio_negocio(web))


def _tiene_formulario(html: str) -> bool:
    for match in FORM_RE.finditer(html):
        cuerpo = match.group(1).lower()
        if "search" in cuerpo and "textarea" not in cuerpo:
            continue
        if "textarea" in cuerpo or 'type="email"' in cuerpo or "type='email'" in cuerpo:
            return True
    return False


def _links_contacto(html: str, web: str) -> list[str]:
    out: list[str] = []
    for href, texto in HREF_RE.findall(html):
        destino = urllib.parse.urljoin(web, href.strip())
        if not destino.startswith(("http://", "https://")) or not _mismo_sitio(destino, web):
            continue
        if CONTACTO_RE.search(href) or CONTACTO_RE.search(re.sub(r"<[^>]+>", " ", texto)):
            if destino not in out:
                out.append(destino)
    return out


def _primer_perfil(regex: re.Pattern, html: str, excluidos: set[str], base: str) -> str:
    for match in regex.finditer(html):
        usuario = match.group(1).strip("/")
        if usuario.lower() in excluidos:
            continue
        return f"https://{base}/{usuario}"
    return ""


def extraer_contactos(web: str) -> dict:
    """Visita la home (y una página de contacto enlazada) de una web propia."""
    vacio = {
        "correo": "",
        "fuente_correo": "",
        "telefono": "",
        "instagram": "",
        "facebook": "",
        "whatsapp": "",
        "formulario": "",
        "idioma_web": "",
        "idioma_fuente": "",
        "vende_cigarros": None,
    }
    if tipo_url(web) != "web":
        return vacio
    home = obtener_html(web)
    if not home:
        return vacio
    out = dict(vacio)
    paginas = [(web, home)]
    links = _links_contacto(home, web)
    if links:
        html_contacto = obtener_html(links[0])
        if html_contacto:
            paginas.append((links[0], html_contacto))

    out["idioma_web"], out["idioma_fuente"] = detectar_idioma_html(home)
    texto_total = " ".join(_texto_visible(h) for _u, h in paginas)
    out["vende_cigarros"] = bool(CIGARROS_RE.search(texto_total))
    for url, html in paginas:
        if not out["correo"]:
            correos = _emails_en_html(html, web)
            if correos:
                out["correo"], out["fuente_correo"] = correos[0], url
        if not out["telefono"]:
            tels = _telefonos_en_html(html)
            if tels:
                out["telefono"] = tels[0]
        if not out["instagram"]:
            out["instagram"] = _primer_perfil(INSTAGRAM_RE, html, INSTAGRAM_NO_PERFIL, "www.instagram.com")
        if not out["facebook"]:
            out["facebook"] = _primer_perfil(FACEBOOK_RE, html, FACEBOOK_NO_PAGINA, "www.facebook.com")
        if not out["whatsapp"]:
            wa = WHATSAPP_RE.search(html)
            if wa:
                out["whatsapp"] = wa.group(1)
        if not out["formulario"] and _tiene_formulario(html):
            out["formulario"] = url
    return out


def vende_cigarros(web: str) -> bool | None:
    """True/False según el texto de la web propia; None si no hay web o no se pudo leer."""
    if tipo_url(web) != "web":
        return None
    html = obtener_html(web)
    if not html:
        return None
    return bool(CIGARROS_RE.search(_texto_visible(html)))


def numero_whatsapp(lead: dict) -> str:
    """Dígitos para wa.me: WhatsApp publicado o teléfono internacional. '' si no es fiable."""
    wa = re.sub(r"\D", "", lead.get("whatsapp") or "")
    if len(wa) >= 8:
        return wa
    intl = (lead.get("telefono_internacional") or "").strip()
    tel = (lead.get("telefono") or "").strip()
    for candidato in (intl, tel):
        if candidato.startswith("+"):
            digitos = re.sub(r"\D", "", candidato)
            if len(digitos) >= 8:
                return digitos
    return ""
