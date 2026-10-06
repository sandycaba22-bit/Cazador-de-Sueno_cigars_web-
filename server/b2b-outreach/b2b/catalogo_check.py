from __future__ import annotations

import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from functools import lru_cache

from b2b.catalogo_vitolas import CATALOG_SCRIPT, vitolas_ordenadas
from b2b.paths import CATALOGO_PDF_BASE, WHOLESALE_URL

PDF_DOMINIO = CATALOGO_PDF_BASE
PDF_NOMBRE = "CazadorDeSuenos_Wholesale_{suffix}.pdf"

IDIOMA_A_SUFIJO = {
    "es": "ES",
    "en": "EN",
    "fr": "FR",
    "pt": "PT",
}

AVISO_PDF_EN_INGLES = {
    "es": "El catálogo PDF está disponible en inglés:",
    "en": "",
    "fr": "Le catalogue PDF est disponible en anglais :",
    "pt": "O catálogo PDF está disponível em inglês:",
    "nl": "The wholesale catalog PDF is available in English:",
    "de": "The wholesale catalog PDF is available in English:",
    "it": "The wholesale catalog PDF is available in English:",
}


class CatalogoError(Exception):
    """Catálogo mayorista no disponible; no se debe generar borrador."""


@dataclass(frozen=True)
class CatalogoPdf:
    url: str
    idioma_solicitado: str
    idioma_pdf: str
    uso_fallback_en: bool

    @property
    def aviso_cliente(self) -> str:
        if not self.uso_fallback_en:
            return ""
        return AVISO_PDF_EN_INGLES.get(self.idioma_solicitado, AVISO_PDF_EN_INGLES["en"])

    @property
    def nota_interna(self) -> str:
        if not self.uso_fallback_en:
            return ""
        return (
            f"catálogo {self.idioma_solicitado} no disponible, se usó EN"
        )


def _suffix(idioma: str) -> str:
    return IDIOMA_A_SUFIJO.get(idioma, "EN")


def url_pdf_suffix(suffix: str) -> str:
    return f"{PDF_DOMINIO}/{PDF_NOMBRE.format(suffix=suffix)}"


def pdf_url_para_idioma(idioma: str) -> str:
    return url_pdf_suffix(_suffix(idioma))


def _pdf_local(suffix: str):
    if not CATALOG_SCRIPT.is_file():
        return None
    local = CATALOG_SCRIPT.parent / PDF_NOMBRE.format(suffix=suffix)
    return local if local.is_file() else None


@lru_cache(maxsize=16)
def _pdf_remoto_disponible(url: str) -> bool:
    if os.getenv("B2B_SKIP_PDF_HEAD", "").strip().lower() in ("1", "true", "yes"):
        return False
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            return 200 <= response.status < 400
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return False


def pdf_disponible(idioma: str) -> bool:
    suffix = _suffix(idioma)
    if _pdf_local(suffix) is not None:
        return True
    return _pdf_remoto_disponible(url_pdf_suffix(suffix))


def verificar_vitolas() -> None:
    if not CATALOG_SCRIPT.is_file():
        raise CatalogoError(
            f"No se encontró el generador de catálogo: {CATALOG_SCRIPT}. "
            "Despliega catalogo/build_wholesale_catalog.py en el servidor."
        )
    if len(vitolas_ordenadas()) != 6:
        raise CatalogoError("El catálogo debe listar exactamente 6 vitolas.")
    if not WHOLESALE_URL.startswith("https://"):
        raise CatalogoError("Falta enlace al portal B2B.")


def verificar_catalogo(idioma: str) -> None:
    """Compat: asegura vitolas y que exista al menos un PDF usable."""
    verificar_vitolas()
    resolver_catalogo_pdf(idioma)


def resolver_catalogo_pdf(idioma: str) -> CatalogoPdf:
    verificar_vitolas()
    solicitado = idioma or "en"
    if pdf_disponible(solicitado):
        suf = _suffix(solicitado)
        return CatalogoPdf(
            url=url_pdf_suffix(suf),
            idioma_solicitado=solicitado,
            idioma_pdf=solicitado,
            uso_fallback_en=False,
        )
    if solicitado != "en" and pdf_disponible("en"):
        return CatalogoPdf(
            url=url_pdf_suffix("EN"),
            idioma_solicitado=solicitado,
            idioma_pdf="en",
            uso_fallback_en=True,
        )
    raise CatalogoError(
        f"No hay PDF mayorista para idioma «{solicitado}» ni fallback EN disponible."
    )


def pdf_para_idioma(idioma: str) -> str:
    """URL del PDF a insertar en el borrador (con fallback EN si aplica)."""
    return resolver_catalogo_pdf(idioma).url
