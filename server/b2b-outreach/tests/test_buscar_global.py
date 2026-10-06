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
from b2b.redactor import EMAIL_VP_VENTAS, presentacion_prospecto_telegram
from b2b.telegram_gestion import tiene_medio_contacto, token_callback
from b2b.telegram_prospecto import mensaje_prospecto_completo


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
    def test_mensaje_completo_contacto_y_firma(self):
        lead = {
            "nombre": "Test Shop",
            "tipo": "lounge",
            "telefono": "+297 123 4567",
            "web": "https://example.com",
            "correo": "info@example.com",
            "direccion": "Main St",
            "pais": "Aruba",
        }
        msg = mensaje_prospecto_completo(lead, "Aruba")
        self.assertIn("PROSPECTO", msg)
        self.assertIn("wa.me/", msg)
        self.assertIn(EMAIL_VP_VENTAS, msg)
        self.assertIn("Mensaje para copiar", msg)

    def test_tiene_medio_web(self):
        self.assertTrue(tiene_medio_contacto({"web": "https://shop.example"}))

    def test_presentacion_firma_vp(self):
        t = presentacion_prospecto_telegram("Cigar House", "en", "tienda")
        self.assertIn("Yaniris", t)
        self.assertIn("Vice President", t)
        self.assertIn(EMAIL_VP_VENTAS, t)

    def test_token_callback_estable(self):
        lead = {"nombre": "A", "web": "https://a.com", "pais": "Aruba"}
        self.assertEqual(token_callback(lead), token_callback(lead))


class TestTelegramControl(unittest.TestCase):
    def test_pausa_bloquea(self):
        set_pausado(True)
        self.assertFalse(puede_enviar_telegram())
        set_pausado(False)


if __name__ == "__main__":
    unittest.main()
