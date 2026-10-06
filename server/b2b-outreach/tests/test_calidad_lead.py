from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from b2b.calidad_lead import aplicar_reglas_web, evaluar_lead_completo, evaluar_senal_cigarro


class TestSenalFuerte(unittest.TestCase):
    def test_hangout_sin_senal_es_dudoso(self):
        lead = {
            "nombre": "Marfa's Good Hangout",
            "web": "https://example-hangout.test",
            "fuente": "openstreetmap",
            "_osm_tags": {"name": "Marfa's Good Hangout"},
        }
        res = evaluar_senal_cigarro(lead)
        self.assertEqual(res.bucket, "dudoso")

    def test_burger_dominio_descartado(self):
        lead = {
            "nombre": "Marfa's Good Hangout",
            "web": "https://williburger.club",
            "fuente": "openstreetmap",
            "_osm_tags": {"shop": "tobacco"},
        }
        res = evaluar_senal_cigarro(lead)
        self.assertEqual(res.bucket, "descartado")

    def test_shop_tobacco_es_fuerte(self):
        lead = {
            "nombre": "Island Smoke",
            "web": "",
            "_osm_tags": {"shop": "tobacco"},
        }
        res = evaluar_senal_cigarro(lead)
        self.assertEqual(res.bucket, "aceptado")


class TestWebCheck(unittest.TestCase):
    def test_tobacco_web_muerta_queda_web_caida(self):
        lead = {
            "nombre": "Tabaco X",
            "web": "https://tabaco.test",
            "_osm_tags": {"shop": "tobacco"},
        }
        info = {"web_clase": "MUERTA", "web_estado": "MUERTA", "web_http": 404, "fecha_chequeo": "x"}
        res = aplicar_reglas_web(lead, info)
        self.assertEqual(res.bucket, "aceptado")
        self.assertEqual(lead.get("calidad_nota"), "web_caida")

    def test_evaluar_completo_burger(self):
        lead = {
            "nombre": "Marfa's Good Hangout",
            "web": "https://williburger.club",
            "_osm_tags": {"shop": "tobacco"},
        }
        with patch("b2b.calidad_lead.chequear_web") as mock_chk:
            res = evaluar_lead_completo(lead, simulado=False)
        mock_chk.assert_not_called()
        self.assertEqual(res.bucket, "descartado")


if __name__ == "__main__":
    unittest.main()
