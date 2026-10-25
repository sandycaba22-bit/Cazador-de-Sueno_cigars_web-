"""Cola de exportación por fases. No sustituye la búsqueda de estados de USA."""
from __future__ import annotations

import json
import unicodedata

from b2b.paths import data_file

_ALIASES = {
    "puerto rico": "Puerto Rico",
    "us virgin islands": "US Virgin Islands",
    "usvi": "US Virgin Islands",
    "islas virgenes": "US Virgin Islands",
    "islas virgenes de ee. uu.": "US Virgin Islands",
    "bahamas": "Bahamas",
    "cayman islands": "Cayman Islands",
    "islas caiman": "Cayman Islands",
    "caiman": "Cayman Islands",
    "turks and caicos islands": "Turks and Caicos Islands",
    "turks and caicos": "Turks and Caicos Islands",
    "turks y caicos": "Turks and Caicos Islands",
    "sint maarten": "Sint Maarten",
    "st. maarten": "Sint Maarten",
    "st maarten": "Sint Maarten",
    "aruba": "Aruba",
    "curacao": "Curacao",
    "curazao": "Curacao",
    "barbados": "Barbados",
    "saint barthelemy": "Saint Barthelemy",
    "st. barths": "Saint Barthelemy",
    "st barths": "Saint Barthelemy",
    "saint barths": "Saint Barthelemy",
    "spain": "Spain",
    "espana": "Spain",
    "germany": "Germany",
    "alemania": "Germany",
    "deutschland": "Germany",
    "switzerland": "Switzerland",
    "suiza": "Switzerland",
    "schweiz": "Switzerland",
    "united kingdom": "United Kingdom",
    "reino unido": "United Kingdom",
    "uk": "United Kingdom",
    "united arab emirates": "United Arab Emirates",
    "dubai": "United Arab Emirates",
    "dubái": "United Arab Emirates",
    "eau": "United Arab Emirates",
    "uae": "United Arab Emirates",
    "hong kong": "Hong Kong",
    "macao": "Macao",
    "macau": "Macao",
    "panama": "Panama",
    "colon": "Panama",
}


def _norm(texto: str) -> str:
    plano = unicodedata.normalize("NFKD", (texto or "").strip().lower())
    return "".join(c for c in plano if not unicodedata.combining(c))


def es_canada(nombre: str = "", iso: str = "") -> bool:
    if (iso or "").strip().upper() == "CA":
        return True
    return _norm(nombre) in {"canada", "ca"}


def _canon(nombre: str) -> str:
    return _ALIASES.get(_norm(nombre), (nombre or "").strip())


def cargar_mercados() -> list[dict]:
    """Fase 1 y luego fase 2. Canadá se descarta aunque aparezca en el archivo."""
    data = json.loads(data_file("mercados_exportacion.json").read_text(encoding="utf-8"))
    filas = []
    for row in data.get("mercados") or []:
        if not isinstance(row, dict) or not row.get("activo", True):
            continue
        if es_canada(row.get("pais") or "", row.get("iso3166") or ""):
            continue
        filas.append(row)
    filas.sort(key=lambda row: (int(row.get("fase") or 9), int(row.get("prioridad") or 999)))
    return filas


def mercado(nombre: str) -> dict | None:
    if es_canada(nombre):
        return None
    canon = _canon(nombre).lower()
    for row in cargar_mercados():
        if (row.get("pais") or "").lower() == canon:
            return row
    return None


def idioma_exportacion(nombre: str) -> str:
    row = mercado(nombre)
    return (row or {}).get("idioma") or ""


def terminos() -> list[dict]:
    data = json.loads(data_file("mercados_exportacion.json").read_text(encoding="utf-8"))
    filas = [t for t in data.get("terminos") or [] if isinstance(t, dict)]
    filas.sort(key=lambda row: int(row.get("nivel") or 9))
    return filas


def consultas_exportacion(nombre: str) -> list[tuple[int, str, str]]:
    """Consultas de este mercado: nivel 1 (distribuidor, importador, duty free) antes que tiendas."""
    row = mercado(nombre)
    if row is None:
        return []
    pais = row["pais"]
    ciudades = list(row.get("ciudades") or [pais])
    salida: list[tuple[int, str, str]] = []
    for termino in terminos():
        nivel = int(termino.get("nivel") or 9)
        tipo = termino.get("tipo") or "tienda"
        texto = termino.get("texto") or ""
        for ciudad in ciudades:
            salida.append((nivel, tipo, f"{texto} in {ciudad}, {pais}"))
    return salida
