from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from b2b.catalogo_check import pdf_url_para_idioma
from b2b.paths import CATALOGO_PDF_BASE, SITE_CANONICAL, WHOLESALE_URL


class TestUrlsCanonicas(unittest.TestCase):
    def test_dominio_unico_sin_godaddy_legacy(self):
        self.assertEqual(SITE_CANONICAL, "https://www.cazadordesuenocigar.com")
        self.assertNotIn("cazadordesuenocigars.com", WHOLESALE_URL)
        self.assertNotIn("godaddy", WHOLESALE_URL.lower())
        self.assertTrue(WHOLESALE_URL.startswith(SITE_CANONICAL))
        self.assertTrue(CATALOGO_PDF_BASE.startswith(SITE_CANONICAL))

    def test_pdf_en_dominio_canonico(self):
        url = pdf_url_para_idioma("es")
        self.assertIn("www.cazadordesuenocigar.com/catalogo/", url)
        self.assertIn("_ES.pdf", url)


if __name__ == "__main__":
    unittest.main()
