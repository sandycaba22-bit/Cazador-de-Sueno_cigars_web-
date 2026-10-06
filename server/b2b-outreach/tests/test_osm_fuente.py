from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from b2b.fuente_leads import resolver_fuente_leads
from b2b.lead_score import califica_lead, puntuar_lead
from b2b.osm_places import buscar_en_pais_osm


class TestFuenteLeads(unittest.TestCase):
    def test_auto_sin_google_usa_osm(self):
        with patch.dict("os.environ", {"GOOGLE_PLACES_API_KEY": "", "FUENTE_LEADS": "auto"}, clear=False):
            self.assertEqual(resolver_fuente_leads(), "osm")

    def test_simulado_forzado(self):
        with patch.dict("os.environ", {"GOOGLE_PLACES_API_KEY": "x", "FUENTE_LEADS": "auto"}, clear=False):
            self.assertEqual(resolver_fuente_leads(forzar_simulado=True), "simulado")


class TestPuntajeOsm(unittest.TestCase):
    def test_tienda_osm_con_telefono_califica(self):
        lead = {
            "tipo": "tienda",
            "fuente": "openstreetmap",
            "telefono": "+221 33 000 0000",
            "web": "https://www.openstreetmap.org/node/1",
        }
        score, _ = puntuar_lead(lead)
        self.assertGreaterEqual(score, 4)
        self.assertTrue(califica_lead(lead))


class TestOsmBuscar(unittest.TestCase):
    def test_parsea_respuesta_overpass(self):
        sample = {
            "elements": [
                {
                    "type": "node",
                    "id": 99,
                    "lat": 14.0,
                    "lon": -17.0,
                    "tags": {
                        "name": "Dakar Tobacco Shop",
                        "shop": "tobacco",
                        "phone": "+221111",
                    },
                }
            ]
        }

        def fake_fetch(_query: str) -> list[dict]:
            return sample["elements"]

        with patch("b2b.osm_places._fetch_overpass", fake_fetch):
            leads, llamadas = buscar_en_pais_osm("Senegal", ["tienda", "distribuidor"], 1)
        self.assertGreaterEqual(llamadas, 1)
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0]["fuente"], "openstreetmap")
        self.assertTrue(leads[0]["place_id"].startswith("osm/"))


if __name__ == "__main__":
    unittest.main()
