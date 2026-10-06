from __future__ import annotations

from b2b.catalogo_vitolas import CATALOG_SCRIPT, vitolas_ordenadas

WHOLESALE_URL = "https://www.cazadordesuenocigars.com/wholesale.html"
PDF_ES = "https://www.cazadordesuenocigars.com/catalogo/CazadorDeSuenos_Wholesale_ES.pdf"
PDF_EN = "https://www.cazadordesuenocigars.com/catalogo/CazadorDeSuenos_Wholesale_EN.pdf"


class CatalogoError(Exception):
    """Catálogo mayorista no disponible; no se debe generar borrador."""


def pdf_para_idioma(idioma: str) -> str:
    return PDF_ES if idioma == "es" else PDF_EN


def verificar_catalogo(idioma: str) -> None:
    """Comprueba vitolas locales y URLs de catálogo antes de redactar."""
    if not CATALOG_SCRIPT.is_file():
        raise CatalogoError(
            f"No se encontró el generador de catálogo: {CATALOG_SCRIPT}. "
            "Despliega catalogo/build_wholesale_catalog.py en el servidor."
        )
    if len(vitolas_ordenadas()) != 6:
        raise CatalogoError("El catálogo debe listar exactamente 6 vitolas.")
    pdf = pdf_para_idioma(idioma)
    if not pdf.startswith("https://") or not WHOLESALE_URL.startswith("https://"):
        raise CatalogoError("Faltan enlaces al PDF mayorista o al portal B2B.")
