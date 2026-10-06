from __future__ import annotations

import json
import re
from html import unescape

from b2b.fuentes.http_polite import fetch_url, permitido_robots

PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")

MARCAS = (
    {
        "marca": "davidoff",
        "url": "https://www.davidoff.com/en-int/find-your-store",
    },
    {
        "marca": "arturofuente",
        "url": "https://www.arturofuente.com/authorized-retailers/",
    },
    {
        "marca": "laaurora",
        "url": "https://www.cigar.laaurora.com/en/where-to-buy/",
    },
    {
        "marca": "plasencia",
        "url": "https://plasencia.com/where-to-buy/",
    },
)

ULTIMAS_SALTADAS: list[str] = []


def _parece_bloqueado(html: str) -> bool:
    low = html[:8000].lower()
    if len(html) < 400:
        return True
    if "sign in" in low and "password" in low:
        return True
    if "enable javascript" in low or "javascript is required" in low:
        return True
    return False


def _pais_en_texto(texto: str, pais: str) -> bool:
    return pais.lower() in texto.lower()


def _bloques_json_ld(html: str) -> list[dict]:
    out: list[dict] = []
    for match in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.I | re.S,
    ):
        try:
            data = json.loads(unescape(match.group(1)))
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            out.extend(x for x in data if isinstance(x, dict))
        elif isinstance(data, dict):
            out.append(data)
    return out


def _lead_desde_ld(item: dict, pais: str, marca: str) -> dict | None:
    nombre = (item.get("name") or "").strip()
    if not nombre:
        return None
    addr = item.get("address") or {}
    if isinstance(addr, str):
        direccion = addr
    else:
        direccion = ", ".join(
            x
            for x in (
                addr.get("streetAddress"),
                addr.get("addressLocality"),
                addr.get("addressCountry"),
            )
            if x
        )
    blob = f"{nombre} {direccion}"
    if not _pais_en_texto(blob, pais) and pais.lower() not in blob.lower():
        return None
    return {
        "nombre": nombre,
        "pais": pais,
        "web": item.get("url") or item.get("sameAs") or "",
        "telefono": item.get("telephone") or "",
        "correo": item.get("email") or "",
        "direccion": direccion,
        "place_id": f"dealer:{marca}:{nombre[:40]}",
        "tipo_negocio": "tienda",
        "fuente": f"dealer:{marca}",
    }


def _parse_heuristic(html: str, pais: str, marca: str) -> list[dict]:
    leads: list[dict] = []
    for item in _bloques_json_ld(html):
        if item.get("@type") in ("Store", "LocalBusiness", "Organization", "Place"):
            lead = _lead_desde_ld(item, pais, marca)
            if lead:
                leads.append(lead)
    if leads:
        return leads
    texto = re.sub(r"<[^>]+>", "\n", html)
    for linea in texto.splitlines():
        linea = unescape(linea).strip()
        if len(linea) < 8 or not _pais_en_texto(linea, pais):
            continue
        if not re.search(r"cigar|tabac|tobacco|humidor|puro|smoke", linea, re.I):
            continue
        tel = PHONE_RE.search(linea)
        mail = EMAIL_RE.search(linea)
        leads.append(
            {
                "nombre": linea[:80],
                "pais": pais,
                "web": "",
                "telefono": tel.group(0).strip() if tel else "",
                "correo": mail.group(0).strip() if mail else "",
                "direccion": linea[:200],
                "place_id": f"dealer:{marca}:{hash(linea) & 0xFFFFFF}",
                "tipo_negocio": "tienda",
                "fuente": f"dealer:{marca}",
            }
        )
    return leads


def buscar_dealers_pais(pais: str, limite: int = 20) -> tuple[list[dict], list[str]]:
    global ULTIMAS_SALTADAS
    saltadas: list[str] = []
    leads: list[dict] = []
    for cfg in MARCAS:
        marca = cfg["marca"]
        url = cfg["url"]
        if not permitido_robots(url):
            saltadas.append(f"dealer:{marca} (robots.txt bloquea)")
            continue
        try:
            html = fetch_url(url)
        except Exception as exc:
            saltadas.append(f"dealer:{marca} (error fetch: {type(exc).__name__})")
            continue
        if _parece_bloqueado(html):
            saltadas.append(f"dealer:{marca} (login/JS o página vacía)")
            continue
        encontrados = _parse_heuristic(html, pais, marca)
        if not encontrados:
            saltadas.append(f"dealer:{marca} (sin coincidencias para {pais})")
        leads.extend(encontrados)
    ULTIMAS_SALTADAS = saltadas
    return leads[:limite], saltadas
