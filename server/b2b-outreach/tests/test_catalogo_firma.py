from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from b2b.catalogo_check import CatalogoError, pdf_url_para_idioma, resolver_catalogo_pdf
from b2b.redactor import CARGO_VP, _firma, borrador_prospecto


class TestPdfPorIdioma(unittest.TestCase):
    def test_urls_por_idioma(self):
        self.assertIn("_EN.pdf", pdf_url_para_idioma("en"))
        self.assertIn("_FR.pdf", pdf_url_para_idioma("fr"))
        self.assertIn("_PT.pdf", pdf_url_para_idioma("pt"))
        self.assertIn("_ES.pdf", pdf_url_para_idioma("es"))

    def test_resolver_idioma_local_es(self):
        cat = resolver_catalogo_pdf("es")
        self.assertIn("_ES.pdf", cat.url)
        self.assertFalse(cat.uso_fallback_en)

    @patch("b2b.catalogo_check.pdf_disponible")
    def test_fallback_fr_con_aviso(self, mock_disp):
        mock_disp.side_effect = lambda lang: lang == "en"
        cat = resolver_catalogo_pdf("fr")
        self.assertIn("_EN.pdf", cat.url)
        self.assertTrue(cat.uso_fallback_en)
        self.assertIn("anglais", cat.aviso_cliente.lower())
        self.assertIn("fr", cat.nota_interna)

    @patch("b2b.catalogo_check.pdf_disponible", return_value=False)
    def test_sin_ningun_pdf_falla(self, _mock):
        with self.assertRaises(CatalogoError):
            resolver_catalogo_pdf("en")


class TestFirma(unittest.TestCase):
    def test_cargo_por_idioma(self):
        self.assertEqual(CARGO_VP["fr"], "Vice-présidente, Ventes")
        self.assertEqual(CARGO_VP["pt"], "Vice-presidente, Vendas")
        bloque, ok = _firma("en")
        self.assertTrue(ok)
        self.assertIn("Vice President, Sales", bloque)
        self.assertIn("Yaniris Agustina Ureña", bloque)

    def test_sin_contacto_no_lineas_vacias(self):
        with patch.dict(os.environ, {"FIRMA_EMAIL": "", "FIRMA_TELEFONO": ""}, clear=False):
            bloque, _ = _firma("es")
        self.assertNotIn("\n\n", bloque)
        self.assertEqual(bloque.count("\n"), 2)

    def test_con_contacto(self):
        with patch.dict(
            os.environ,
            {"FIRMA_EMAIL": "ventas@test.com", "FIRMA_TELEFONO": "+1 809 464 5016"},
            clear=False,
        ):
            bloque, _ = _firma("es")
        self.assertIn("ventas@test.com", bloque)
        self.assertIn("809", bloque)


class TestBorradorCatalogoEnCuerpo(unittest.TestCase):
    @patch("b2b.catalogo_check.pdf_disponible")
    def test_fr_pdf_en_cuerpo(self, mock_disp):
        mock_disp.side_effect = lambda lang: lang == "fr"
        draft = borrador_prospecto("fr", "Shop", "tienda")
        self.assertIn("_FR.pdf", draft)

    @patch("b2b.catalogo_check.pdf_disponible")
    def test_fallback_texto_en_borrador(self, mock_disp):
        mock_disp.side_effect = lambda lang: lang == "en"
        draft = borrador_prospecto("pt", "Shop", "tienda")
        self.assertIn("inglês", draft.lower())
        self.assertIn("_EN.pdf", draft)


if __name__ == "__main__":
    unittest.main()
