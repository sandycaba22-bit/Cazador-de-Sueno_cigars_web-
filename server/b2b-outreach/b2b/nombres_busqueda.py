from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from b2b.buscar_filtros import dominio_web
from b2b.paths import data_file

WEB_CIGAR_RE = re.compile(r"\bcigars?\b|\bcigarros?\b|\bcigares?\b|\bhumidor\b|\btabaquer", re.I)


def _escape_phrase(phrase: str) -> str:
    p = phrase.strip()
    if not p:
        return ""
    if " " in p:
        return re.escape(p).replace(r"\ ", r"\s+")
    return re.escape(p)


def _boundary_pattern(phrase: str, *, plural_s: bool = False) -> str:
    core = _escape_phrase(phrase)
    if not core:
        return ""
    if " " in phrase.strip():
        return rf"(?<![\wáéíóúñ]){core}(?![\wáéíóúñ])"
    suf = r"s?" if plural_s else ""
    return rf"(?<![\wáéíóúñ]){core}{suf}(?![\wáéíóúñ])"


@lru_cache(maxsize=1)
def _listas() -> dict[str, list[str]]:
    path = data_file("nombres_busqueda.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "fuertes": list(data.get("fuertes") or []),
        "debiles": list(data.get("debiles") or []),
        "excluir_siempre": list(data.get("excluir_siempre") or []),
        "excluir_dominio": list(data.get("excluir_dominio") or []),
    }


def _compilar(lista: tuple[str, ...], *, plural_s: bool = False) -> re.Pattern[str] | None:
    parts = [_boundary_pattern(x, plural_s=plural_s) for x in lista if x.strip()]
    parts = [p for p in parts if p]
    if not parts:
        return None
    return re.compile("|".join(parts), re.I)


@lru_cache(maxsize=1)
def regex_fuertes() -> re.Pattern[str] | None:
    return _compilar(tuple(_listas()["fuertes"]), plural_s=True)


@lru_cache(maxsize=1)
def regex_debiles() -> re.Pattern[str] | None:
    return _compilar(tuple(_listas()["debiles"]), plural_s=False)


@lru_cache(maxsize=1)
def regex_excluir() -> re.Pattern[str] | None:
    return _compilar(tuple(_listas()["excluir_siempre"]), plural_s=True)


def _ascii_overpass(texto: str) -> str:
    import unicodedata

    norm = unicodedata.normalize("NFKD", texto)
    return norm.encode("ascii", "ignore").decode("ascii")


def overpass_regex_alternativas(lista_key: str) -> str:
    """Alternativas para Overpass name~ (flag ,i en la consulta)."""
    items = _listas()[lista_key]
    out: list[str] = []
    for raw in items:
        t = _ascii_overpass(raw.strip())
        if not t:
            continue
        if " " in t:
            partes = [re.escape(p) for p in t.split()]
            out.append(".*".join(partes))
        else:
            out.append(re.escape(t))
    return "|".join(out) if out else "cigar"


def texto_nombre_web(lead: dict) -> str:
    partes = [lead.get("nombre") or "", lead.get("web") or ""]
    return " ".join(partes)


def osm_shop_tabaco(lead: dict) -> bool:
    tags = lead.get("_osm_tags") or {}
    shop = (tags.get("shop") or "").lower()
    return shop in ("tobacco", "cigar") or bool(lead.get("osm_shop_tobacco"))


def _liquor_sin_humidor(texto: str) -> bool:
    low = texto.lower()
    if not re.search(r"\b(liquor|liquor\s*store|wine\s*shop|bottle\s*shop)\b", low):
        return False
    if "humidor" in low or WEB_CIGAR_RE.search(low):
        return False
    return True


def dominio_excluido(web: str) -> bool:
    dom = dominio_web(web).lower()
    if not dom:
        return False
    for frag in _listas()["excluir_dominio"]:
        if frag.lower() in dom:
            return True
    return False


def contiene_excluir(texto: str, web: str = "") -> bool:
    if web and dominio_excluido(web):
        return True
    if _liquor_sin_humidor(texto):
        return True
    rx = regex_excluir()
    return bool(rx and rx.search(texto))


def contiene_fuerte(texto: str) -> bool:
    rx = regex_fuertes()
    return bool(rx and rx.search(texto))


def contiene_debil(texto: str) -> bool:
    rx = regex_debiles()
    return bool(rx and rx.search(texto))


def senal_extra(lead: dict) -> bool:
    tags = lead.get("_osm_tags") or {}
    if tags.get("cigar") == "yes":
        return True
    texto = texto_nombre_web(lead)
    if "humidor" in texto.lower():
        return True
    if contiene_fuerte(texto):
        return True
    fuente = (lead.get("fuente") or "").lower()
    if fuente.startswith("dealer:"):
        return True
    for campo in ("web", "instagram", "facebook"):
        url = (lead.get(campo) or "").strip()
        if url.startswith(("http://", "https://")) and WEB_CIGAR_RE.search(url):
            return True
    return False


def clasificar_aceptacion(lead: dict) -> tuple[str, str]:
    """
    Devuelve (bucket, motivo): aceptado | dudoso | excluido.
    Reglas (a) OSM shop tobacco/cigar, (b) fuerte sin excluir, (c) débil + extra.
    """
    web = lead.get("web") or ""
    if osm_shop_tabaco(lead):
        texto = texto_nombre_web(lead)
        if contiene_excluir(texto, web) and not contiene_fuerte(texto):
            return "excluido", "excluir_siempre (a pesar de shop OSM)"
        return "aceptado", "osm shop=tobacco/cigar"

    texto = texto_nombre_web(lead)
    if contiene_excluir(texto, web):
        return "excluido", "excluir_siempre"

    if contiene_fuerte(texto):
        return "aceptado", "palabra fuerte en nombre/web"

    if contiene_debil(texto):
        if senal_extra(lead):
            return "aceptado", "palabra débil + señal extra"
        return "dudoso", "solo palabra débil sin señal extra"

    tags = lead.get("_osm_tags") or {}
    if tags.get("cigar") == "yes" or tags.get("smoking") == "yes":
        return "dudoso", "etiqueta smoking/cigar sin nombre claro"

    return "dudoso", "sin señal fuerte ni débil reconocida"


def lead_desde_etiquetas(nombre: str, web: str, tags: dict, pais: str = "") -> dict:
    return {
        "nombre": nombre,
        "web": web,
        "pais": pais,
        "_osm_tags": dict(tags),
        "osm_shop_tobacco": (tags.get("shop") or "").lower() in ("tobacco", "cigar"),
        "fuente": "openstreetmap",
    }
