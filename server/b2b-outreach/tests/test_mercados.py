from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from b2b.mercados import (
    cargar_cursor,
    cargar_mercados,
    guardar_cursor,
    mercado_por_nombre,
    mercados_activos,
    siguiente_mercado,
)
from b2b.places import consultas_google


class TestMercadosConfig(unittest.TestCase):
    def test_cincuenta_estados_dc_y_dos_islas(self):
        todos = cargar_mercados()
        activos = mercados_activos()
        self.assertEqual(len(todos), 53)
        self.assertEqual(len(activos), 53)
        self.assertEqual(activos[0]["nombre"], "Florida")
        self.assertEqual(activos[50]["nombre"], "District of Columbia")
        self.assertEqual(activos[51]["nombre"], "Puerto Rico")
        self.assertEqual(activos[52]["nombre"], "Jamaica")
        self.assertTrue(all(m["activo"] is True for m in activos))

    def test_inactivo_no_genera_consultas(self):
        self.assertEqual(consultas_google("Nigeria", []), [])
        self.assertIsNone(mercado_por_nombre("Nigeria", solo_activos=True))

    def test_cursor_avanza_al_siguiente(self):
        self.assertEqual(siguiente_mercado("Florida")["nombre"], "Texas")
        self.assertEqual(siguiente_mercado("Jamaica")["nombre"], "Florida")


class TestCursorDisco(unittest.TestCase):
    def test_guarda_y_lee(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "busqueda_cursor.json"
            with patch("b2b.mercados.cursor_path", return_value=path):
                guardar_cursor("Florida", 4)
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(data["mercado"], "Florida")
                self.assertEqual(data["consulta_idx"], 4)
                self.assertEqual(cargar_cursor()["consulta_idx"], 4)


if __name__ == "__main__":
    unittest.main()
