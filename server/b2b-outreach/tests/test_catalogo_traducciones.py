from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
CATALOG = REPO / "catalogo" / "build_wholesale_catalog.py"
sys.path.insert(0, str(ROOT))

from b2b.catalogo_vitolas import IDIOMAS_CATALOGO, cargar_vitolas_catalogo, lineas_vitolas


class TestCatalogoTraducciones(unittest.TestCase):
    def test_vitolas_cuatro_idiomas_completos(self):
        vitolas = cargar_vitolas_catalogo()
        self.assertEqual(len(vitolas), 6)

    def test_lineas_fr_pt_usan_nombres_locales(self):
        fr = lineas_vitolas("fr")
        self.assertIn("Le Sultan", fr)
        self.assertIn("cape", fr)
        self.assertNotIn(" wrapper,", fr)
        pt = lineas_vitolas("pt")
        self.assertIn("O Sultan", pt)
        self.assertIn("força", pt)

    def test_copy_y_welcome_por_idioma(self):
        tree = ast.parse(CATALOG.read_text(encoding="utf-8"))
        copy_node = welcome_node = None
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "COPY":
                    copy_node = node.value
                if isinstance(target, ast.Name) and target.id == "WELCOME":
                    welcome_node = node.value
        self.assertIsNotNone(copy_node)
        self.assertIsNotNone(welcome_node)
        copy = ast.literal_eval(copy_node)
        welcome = ast.literal_eval(welcome_node)
        for lang in IDIOMAS_CATALOGO:
            self.assertIn(lang, copy)
            self.assertIn(lang, welcome)
            self.assertTrue(len(copy[lang]["catalog"]) > 3)
            self.assertTrue(len(welcome[lang]) > 40)


if __name__ == "__main__":
    unittest.main()
