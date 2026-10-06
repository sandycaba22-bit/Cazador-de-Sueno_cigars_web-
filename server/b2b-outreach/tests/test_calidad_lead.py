from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from b2b.calidad_lead import (
    aplicar_reglas_web,
    evaluar_lead_completo,
    evaluar_senal_cigarro,
    motivo_descarte_tipo,
)
from b2b.web_check import chequear_web


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
        self.assertIsNotNone(motivo_descarte_tipo(lead))
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
    def test_500_reintenta_y_queda_no_verificada(self):
        calls = {"n": 0}

        def fake_get(url):
            calls["n"] += 1
            return "ERROR_TEMPORAL", 500, b"", None

        with patch("b2b.web_check._get_una_vez", side_effect=fake_get), patch(
            "b2b.web_check.time.sleep", lambda *_: None
        ), patch("b2b.web_check.permitido_robots", return_value=True):
            info = chequear_web("https://ejemplo.test", simulado=False)
        self.assertEqual(info["web_estado"], "web_no_verificada")
        self.assertGreaterEqual(calls["n"], 3)

    def test_404_es_muerta(self):
        with patch("b2b.web_check._get_una_vez", return_value=("MUERTA", 404, b"", None)), patch(
            "b2b.web_check.permitido_robots", return_value=True
        ), patch("b2b.web_check._respetar_pausa_dominio", lambda *_: None), patch(
            "b2b.web_check._marcar_dominio", lambda *_: None
        ):
            info = chequear_web("https://muerta.test", simulado=False)
        self.assertEqual(info["web_clase"], "MUERTA")

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

    def test_web_muerta_sin_contacto_descartada(self):
        lead = {"nombre": "Foo", "web": "https://foo.test", "_osm_tags": {"amenity": "cafe"}}
        info = {"web_clase": "MUERTA", "web_estado": "MUERTA", "web_http": 404, "fecha_chequeo": "x"}
        res = aplicar_reglas_web(lead, info)
        self.assertEqual(res.bucket, "descartado")

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
