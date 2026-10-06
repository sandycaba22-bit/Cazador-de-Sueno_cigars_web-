from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOG_SCRIPT = REPO_ROOT / "catalogo" / "build_wholesale_catalog.py"

ORDEN_PUNTA_ES = ("El Sultán", "Ligero 007")
ORDEN_RESTO_ES = ("El Emperador", "El Exquisito", "Puro Habano", "El Rango")

FORTALEZA_ES = {
    "Alta y sofisticada": "Alta",
    "Medio-fuerte": "Medio-fuerte",
    "Fuerte": "Fuerte",
}
FORTALEZA_EN = {
    "High and sophisticated": "High",
    "Medium-full": "Medium-full",
    "Full": "Full",
}
FORTALEZA_FR = {
    "Full": "Forte",
    "Medium-full": "Moyen-plein",
    "High and sophisticated": "Forte élevée",
}
FORTALEZA_NL = {
    "Full": "Vol",
    "Medium-full": "Medium-vol",
    "High and sophisticated": "Hoog",
}
FORTALEZA_PT = {
    "Full": "Forte",
    "Medium-full": "Médio-cheio",
    "High and sophisticated": "Alta",
}

# Marcadores que no deben aparecer en líneas de vitola de otro idioma.
VITOLA_PROHIBIDO_POR_IDIOMA: dict[str, tuple[str, ...]] = {
    "es": (" wrapper,", " strength", " cape ", " force ", " força ", " dekblad "),
    "en": (" capa ", " fortaleza ", " cape ", " force ", " força ", " dekblad "),
    "fr": (" wrapper,", " strength", " capa ", " fortaleza ", " força "),
    "pt": (" wrapper,", " strength", " cape ", " force ", " fortaleza "),
    "nl": (" wrapper,", " strength", " capa ", " fortaleza ", " força "),
}


def _L_catalogo(es: str, en: str, fr: str, pt: str) -> dict[str, str]:
    return {"es": es, "en": en, "fr": fr, "pt": pt}


CAMPOS_VITOLA_IDIOMA = ("name", "format", "wrapper", "binder", "filler", "strength", "note")
IDIOMAS_CATALOGO = ("es", "en", "fr", "pt")


def _validar_vitolas_catalogo(vitolas: list) -> tuple[dict, ...]:
    if not isinstance(vitolas, list):
        raise ValueError("VITOLAS no es una lista.")
    if len(vitolas) != 6:
        raise ValueError(f"Se esperaban 6 vitolas en el catálogo; hay {len(vitolas)}.")
    for vitola in vitolas:
        for campo in CAMPOS_VITOLA_IDIOMA:
            bloque = vitola.get(campo)
            if not isinstance(bloque, dict):
                raise ValueError(f"Campo «{campo}» debe ser dict por idioma.")
            for lang in IDIOMAS_CATALOGO:
                texto = (bloque.get(lang) or "").strip()
                if not texto:
                    raise ValueError(f"Vitola «{vitola.get('name', {}).get('es', '?')}» "
                                     f"sin texto «{lang}» en «{campo}».")
    return tuple(vitolas)


@lru_cache(maxsize=1)
def cargar_vitolas_catalogo() -> tuple[dict, ...]:
    """Lee VITOLAS del generador PDF sin importar Pillow/reportlab."""
    if not CATALOG_SCRIPT.is_file():
        raise FileNotFoundError(f"No se encontró el catálogo: {CATALOG_SCRIPT}")
    tree = ast.parse(CATALOG_SCRIPT.read_text(encoding="utf-8"))
    sandbox = {"_L": _L_catalogo}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "VITOLAS":
                expr = ast.Expression(body=node.value)
                vitolas = eval(compile(expr, str(CATALOG_SCRIPT), "eval"), {"__builtins__": {}}, sandbox)
                return _validar_vitolas_catalogo(vitolas)
    raise ValueError("No se encontró VITOLAS en build_wholesale_catalog.py")


def vitolas_ordenadas() -> list[dict]:
    by_name = {v["name"]["es"]: v for v in cargar_vitolas_catalogo()}
    ordenadas: list[dict] = []
    for nombre in ORDEN_PUNTA_ES + ORDEN_RESTO_ES:
        if nombre in by_name:
            ordenadas.append(by_name[nombre])
    if len(ordenadas) != 6:
        faltan = set(ORDEN_PUNTA_ES + ORDEN_RESTO_ES) - {v["name"]["es"] for v in ordenadas}
        raise ValueError(f"Faltan vitolas en el catálogo: {', '.join(sorted(faltan))}")
    return ordenadas


def _lang_key(idioma: str) -> str:
    if idioma in IDIOMAS_CATALOGO:
        return idioma
    return "en"


def _fortaleza(vitola: dict, idioma: str) -> str:
    lk = _lang_key(idioma)
    if lk in vitola["strength"]:
        return vitola["strength"][lk]
    raw = vitola["strength"]["en"]
    if idioma == "es":
        return FORTALEZA_ES.get(raw, raw)
    if idioma == "fr":
        return FORTALEZA_FR.get(raw, raw)
    if idioma == "nl":
        return FORTALEZA_NL.get(raw, raw)
    if idioma == "pt":
        return FORTALEZA_PT.get(raw, raw)
    return FORTALEZA_EN.get(raw, raw)


def _capa(vitola: dict, idioma: str) -> str:
    """Texto de capa del catálogo en el idioma del borrador."""
    lk = _lang_key(idioma)
    return vitola["wrapper"].get(lk) or vitola["wrapper"]["en"]


def linea_vitola(vitola: dict, idioma: str) -> str:
    """Nombres del PDF (es/en) y etiquetas de capa/fortaleza en el idioma del borrador."""
    lk = _lang_key(idioma)
    nombre = vitola["name"][lk]
    capa = _capa(vitola, idioma)
    fortaleza = _fortaleza(vitola, idioma)
    if idioma == "es":
        return f"• {nombre} — capa {capa}, fortaleza {fortaleza}"
    if idioma == "fr":
        return f"• {nombre} — cape {capa}, force {fortaleza}"
    if idioma == "nl":
        return f"• {nombre} — dekblad {capa}, kracht {fortaleza}"
    if idioma == "de":
        return f"• {nombre} — Deckblatt {capa}, Stärke {fortaleza}"
    if idioma == "it":
        return f"• {nombre} — capa {capa}, forza {fortaleza}"
    if idioma == "pt":
        return f"• {nombre} — capa {capa}, força {fortaleza}"
    return f"• {nombre} — {capa} wrapper, {fortaleza} strength"


def validar_lineas_vitolas_idioma(idioma: str, bloque: str) -> None:
    """Lanza ValueError si alguna línea mezcla idiomas en capa/fortaleza."""
    prohibidos = VITOLA_PROHIBIDO_POR_IDIOMA.get(idioma, VITOLA_PROHIBIDO_POR_IDIOMA["en"])
    for linea in bloque.splitlines():
        if not linea.strip().startswith("•"):
            continue
        lower = linea.lower()
        for token in prohibidos:
            if token.strip() in lower or token.lower() in lower:
                raise ValueError(f"Vitola en idioma incorrecto ({idioma}): {linea}")


def lineas_vitolas(idioma: str) -> str:
    lineas = "\n".join(linea_vitola(v, idioma) for v in vitolas_ordenadas())
    validar_lineas_vitolas_idioma(idioma, lineas)
    return lineas


def intro_vitolas(idioma: str) -> str:
    textos = {
        "es": "Nos gustaría presentar nuestra línea mayorista—seis vitolas, abriendo con nuestras referencias de entrada:",
        "en": "We'd like to introduce our wholesale line—six vitolas, led by our opening references:",
        "fr": "Nous présentons notre ligne grossiste—six vitolas, en tête nos références d'ouverture :",
        "nl": "We presenteren onze groothandelslijn—zes vitolas, geleid door onze instapreferenties:",
        "de": "Gern stellen wir unsere Großhandelslinie vor—sechs Vitolas, angeführt von unseren Einstiegsreferenzen:",
        "it": "Presentiamo la nostra linea wholesale—sei vitole, con le nostre referenze di apertura:",
        "pt": "Apresentamos a nossa linha grossista—seis vitolas, lideradas pelas nossas referências de abertura:",
    }
    return textos.get(idioma, textos["en"])


def bloque_vitolas(idioma: str) -> str:
    return intro_vitolas(idioma) + "\n" + lineas_vitolas(idioma)
