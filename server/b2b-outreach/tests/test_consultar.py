from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from b2b.consultar import consultar


class TestConsultar(unittest.TestCase):
    def test_arturo_fuente(self):
        r = consultar("¿Cómo distribuye Arturo Fuente?")
        self.assertIn("arturofuente.com", r.lower())
        self.assertNotEqual(r, "no tengo ese dato")

    def test_marca_nueva(self):
        r = consultar("¿Qué le piden a una marca nueva los distribuidores?")
        self.assertIn("muestras", r.lower())

    def test_desconocido(self):
        self.assertEqual(consultar("¿Cuál es el precio del petróleo?"), "no tengo ese dato")


if __name__ == "__main__":
    unittest.main()
