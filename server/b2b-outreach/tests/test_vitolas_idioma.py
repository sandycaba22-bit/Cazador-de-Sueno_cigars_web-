from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from b2b.catalogo_vitolas import lineas_vitolas, validar_lineas_vitolas_idioma
from b2b.idioma import idioma_para_pais
from b2b.redactor import borrador_prospecto


class TestVitolasCoherenciaIdioma(unittest.TestCase):
    IDIOMAS = ("es", "en", "fr", "pt")

    def test_lineas_por_idioma_sin_mezcla(self):
        for idioma in self.IDIOMAS:
            bloque = lineas_vitolas(idioma)
            self.assertEqual(bloque.count("•"), 6, idioma)
            validar_lineas_vitolas_idioma(idioma, bloque)

    def test_borradores_por_pais(self):
        casos = (
            ("Florida", "en"),
            ("Texas", "en"),
            ("California", "en"),
            ("Jamaica", "en"),
            ("Puerto Rico", "es"),
        )
        for pais, idioma_esperado in casos:
            idioma = idioma_para_pais(pais)
            self.assertEqual(idioma, idioma_esperado, pais)
            draft = borrador_prospecto(idioma, "Demo", "tienda")
            vitolas = "\n".join(ln for ln in draft.splitlines() if ln.strip().startswith("•"))
            validar_lineas_vitolas_idioma(idioma, vitolas)


if __name__ == "__main__":
    unittest.main()
