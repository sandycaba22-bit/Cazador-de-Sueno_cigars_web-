from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from b2b.nombres_busqueda import clasificar_aceptacion, contiene_fuerte, lead_desde_etiquetas


class TestCasosReales(unittest.TestCase):
    def test_old_havana_cigars_entra(self):
        lead = lead_desde_etiquetas("Old Havana Cigars", "", {})
        bucket, _ = clasificar_aceptacion(lead)
        self.assertEqual(bucket, "aceptado")
        self.assertTrue(contiene_fuerte("Old Havana Cigars"))

    def test_marfa_hangout_dudoso(self):
        lead = lead_desde_etiquetas(
            "Marfa's Good Hangout",
            "https://example-hangout.test",
            {"amenity": "bar"},
        )
        bucket, _ = clasificar_aceptacion(lead)
        self.assertEqual(bucket, "dudoso")

    def test_williburger_dominio_excluido(self):
        lead = lead_desde_etiquetas(
            "Marfa's Good Hangout",
            "https://williburger.club",
            {"shop": "tobacco"},
        )
        bucket, _ = clasificar_aceptacion(lead)
        self.assertEqual(bucket, "excluido")

    def test_tobacco_road_bar_dudoso(self):
        lead = lead_desde_etiquetas("Tobacco Road Bar", "", {"amenity": "bar"})
        bucket, _ = clasificar_aceptacion(lead)
        self.assertEqual(bucket, "dudoso")

    def test_foxies_vape_excluido(self):
        lead = lead_desde_etiquetas("Foxies Vape and Smoke Shop", "", {"shop": "tobacco"})
        bucket, _ = clasificar_aceptacion(lead)
        self.assertEqual(bucket, "excluido")

    def test_cigarette_outlet_excluido(self):
        lead = lead_desde_etiquetas("Cigarette Outlet", "", {})
        bucket, _ = clasificar_aceptacion(lead)
        self.assertEqual(bucket, "excluido")

    def test_osm_tobacco_entra(self):
        lead = lead_desde_etiquetas("Generic", "", {"shop": "tobacco"})
        bucket, motivo = clasificar_aceptacion(lead)
        self.assertEqual(bucket, "aceptado")
        self.assertIn("osm", motivo)


if __name__ == "__main__":
    unittest.main()
