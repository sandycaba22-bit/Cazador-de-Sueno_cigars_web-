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


@lru_cache(maxsize=1)
def cargar_vitolas_catalogo() -> tuple[dict, ...]:
    """Lee VITOLAS del generador PDF sin importar Pillow/reportlab."""
    if not CATALOG_SCRIPT.is_file():
        raise FileNotFoundError(f"No se encontró el catálogo: {CATALOG_SCRIPT}")
    tree = ast.parse(CATALOG_SCRIPT.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "VITOLAS":
                vitolas = ast.literal_eval(node.value)
                if not isinstance(vitolas, list):
                    raise ValueError("VITOLAS no es una lista.")
                if len(vitolas) != 6:
                    raise ValueError(f"Se esperaban 6 vitolas en el catálogo; hay {len(vitolas)}.")
                return tuple(vitolas)
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
    return "es" if idioma == "es" else "en"


def _fortaleza(vitola: dict, idioma: str) -> str:
    lk = _lang_key(idioma)
    raw = vitola["strength"][lk]
    if idioma == "es":
        return FORTALEZA_ES.get(raw, raw)
    if idioma == "fr":
        return FORTALEZA_FR.get(vitola["strength"]["en"], vitola["strength"]["en"])
    if idioma == "nl":
        return FORTALEZA_NL.get(vitola["strength"]["en"], vitola["strength"]["en"])
    return FORTALEZA_EN.get(raw, raw)


def linea_vitola(vitola: dict, idioma: str) -> str:
    """Nombres y capas tal como en el PDF mayorista (claves es/en del catálogo)."""
    lk = _lang_key(idioma)
    nombre = vitola["name"][lk]
    capa = vitola["wrapper"][lk]
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
    return f"• {nombre} — {capa} wrapper, {fortaleza} strength"


def lineas_vitolas(idioma: str) -> str:
    return "\n".join(linea_vitola(v, idioma) for v in vitolas_ordenadas())


def intro_vitolas(idioma: str) -> str:
    textos = {
        "es": "Nos gustaría presentar nuestra línea mayorista—seis vitolas, abriendo con nuestras referencias de entrada:",
        "en": "We'd like to introduce our wholesale line—six vitolas, led by our opening references:",
        "fr": "Nous présentons notre ligne grossiste—six vitolas, en tête nos références d'ouverture :",
        "nl": "We presenteren onze groothandelslijn—zes vitolas, geleid door onze instapreferenties:",
        "de": "Gern stellen wir unsere Großhandelslinie vor—sechs Vitolas, angeführt von unseren Einstiegsreferenzen:",
        "it": "Presentiamo la nostra linea wholesale—sei vitole, con le nostre referenze di apertura:",
    }
    return textos.get(idioma, textos["en"])


def bloque_vitolas(idioma: str) -> str:
    return intro_vitolas(idioma) + "\n" + lineas_vitolas(idioma)
