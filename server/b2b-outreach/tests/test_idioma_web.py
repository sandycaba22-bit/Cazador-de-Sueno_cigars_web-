from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from b2b.idioma import idioma_para_lead
from b2b.website import detectar_idioma_html


class TestIdiomaWeb(unittest.TestCase):
    def test_html_lang_en(self):
        html = '<!DOCTYPE html><html lang="en-GB"><head><title>Shop</title></head><body></body></html>'
        codigo, fuente = detectar_idioma_html(html)
        self.assertEqual(codigo, "en")
        self.assertEqual(fuente, "html lang")

    def test_texto_frances(self):
        html = (
            "<html><body><h1>Boutique</h1>"
            "<p>Contactez-nous pour nos cigares et humidor grossiste à propos.</p></body></html>"
        )
        codigo, fuente = detectar_idioma_html(html)
        self.assertEqual(codigo, "fr")
        self.assertEqual(fuente, "texto web")

    def test_web_prioriza_sobre_pais(self):
        self.assertEqual(
            idioma_para_lead("Angola", idioma_web="en"),
            "en",
        )
        self.assertEqual(
            idioma_para_lead("Aruba", idioma_web="es"),
            "es",
        )

    def test_preferido_explicito_gana(self):
        self.assertEqual(
            idioma_para_lead("Senegal", idioma_web="en", preferido="fr"),
            "fr",
        )


if __name__ == "__main__":
    unittest.main()
