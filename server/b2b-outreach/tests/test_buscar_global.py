from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from b2b.osm_cuadricula import celdas_desde_bbox, preparar_celdas_pais
from b2b.paises_cola import cargar_paises_cola, entry_por_pais
from b2b.redactor import texto_corto_prospecto_buscar
from b2b.telegram_control import puede_enviar_telegram, set_pausado
from b2b.telegram_prospecto import linea_whatsapp, mensaje_ficha_prospecto


class TestPaisesCola(unittest.TestCase):
    def test_orden_caribe_primero(self):
        fila = cargar_paises_cola()
        self.assertGreater(len(fila), 10)
        self.assertEqual(fila[0].get("zona"), "caribe")
        self.assertEqual(fila[0].get("pais"), "Aruba")

    def test_entry_aruba(self):
        row = entry_por_pais("Aruba")
        self.assertIsNotNone(row)
        self.assertEqual(row["iso3166"], "AW")


class TestCuadricula(unittest.TestCase):
    def test_celdas_aruba_pequeno(self):
        box = {"south": 12.41, "west": -70.07, "north": 12.63, "east": -69.86}
        celdas = celdas_desde_bbox(box, paso=0.45)
        self.assertGreaterEqual(len(celdas), 1)
        self.assertLessEqual(len(celdas), 4)

    def test_preparar_aw(self):
        celdas = preparar_celdas_pais("AW")
        self.assertTrue(celdas)


class TestTelegramProspecto(unittest.TestCase):
    def test_ficha_maps_y_whatsapp(self):
        lead = {
            "nombre": "Test Shop",
            "tipo": "tienda",
            "telefono": "+297 123 4567",
            "whatsapp": "+2977654321",
            "web": "https://example.com",
            "web_estado": "ok",
            "correo": "",
            "direccion": "Main St",
            "lat": 12.5,
            "lon": -70.0,
        }
        msg = mensaje_ficha_prospecto(lead, "Aruba")
        self.assertIn("NUEVO PROSPECTO", msg)
        self.assertIn("wa.me/2977654321", msg)
        self.assertIn("12.5,-70.0", msg)

    def test_posible_whatsapp_sin_tag(self):
        lead = {"telefono": "+1 305 555 0100"}
        self.assertIn("wa.me/", linea_whatsapp(lead))

    def test_texto_corto_seis_lineas(self):
        t = texto_corto_prospecto_buscar("Cigar House", "en", "lounge")
        self.assertLessEqual(len(t.splitlines()), 6)
        self.assertIn("STOP", t)


class TestTelegramControl(unittest.TestCase):
    def test_pausa_bloquea(self):
        set_pausado(True)
        self.assertFalse(puede_enviar_telegram())
        set_pausado(False)


if __name__ == "__main__":
    unittest.main()
