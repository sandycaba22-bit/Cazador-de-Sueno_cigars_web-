from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from b2b.buscar_filtros import (
    clasificar_novedad,
    clave_dedupe,
    dedupe_y_fusionar,
    descartar_lead_osm,
)
from b2b.osm_places import _elemento_a_lead, buscar_en_pais_osm


class TestFiltroVapes(unittest.TestCase):
    def test_descarta_vape_shop_sin_cigarro(self):
        self.assertTrue(descartar_lead_osm("Cloud Vape Shop", {"shop": "tobacco"}))

    def test_acepta_tabaco_clasico(self):
        self.assertFalse(descartar_lead_osm("Island Tobacco", {"shop": "tobacco"}))


class TestDedupe(unittest.TestCase):
    def test_fusiona_mismo_dominio(self):
        a = {"nombre": "A", "web": "https://www.foo.com", "telefono": "", "fuente": "openstreetmap"}
        b = {"nombre": "A Shop", "web": "http://foo.com/contact", "telefono": "+1 809 555 0100", "fuente": "dealer:davidoff"}
        out = dedupe_y_fusionar([a, b])
        self.assertEqual(len(out), 1)
        self.assertIn("+1 809 555 0100", out[0]["telefono"])

    def test_clave_dedupe_dominio(self):
        self.assertEqual(
            clave_dedupe({"nombre": "X", "web": "https://www.ejemplo.com"}),
            clave_dedupe({"nombre": "Y", "web": "http://ejemplo.com/p"}),
        )


class TestConteoNovedad(unittest.TestCase):
    def test_repetido_en_inbox(self):
        with tempfile.TemporaryDirectory() as tmp:
            cola = Path(tmp)
            inbox = cola / "inbox"
            inbox.mkdir()
            lead = {
                "nombre": "Cigar Point",
                "web": "https://cigarpoint.example",
                "telefono": "",
                "place_id": "osm/node/1",
            }
            (inbox / "1.json").write_text(json.dumps(lead), encoding="utf-8")
            nuevos, repetidos = clasificar_novedad([dict(lead)], cola)
            self.assertEqual(len(repetidos), 1)
            self.assertEqual(len(nuevos), 0)


class TestOverpassWay(unittest.TestCase):
    def test_elemento_way_con_center(self):
        el = {
            "type": "way",
            "id": 42,
            "center": {"lat": 25.76, "lon": -80.19},
            "tags": {"name": "Miami Humidor Lounge", "shop": "tobacco", "phone": "+13055550100"},
        }
        lead = _elemento_a_lead(el, "Florida")
        self.assertIsNotNone(lead)
        self.assertEqual(lead["place_id"], "osm/way/42")

    def test_buscar_devuelve_meta(self):
        sample = {
            "elements": [
                {
                    "type": "way",
                    "id": 7,
                    "center": {"lat": 18.46, "lon": -66.11},
                    "tags": {"name": "San Juan Cigars", "shop": "cigar"},
                }
            ]
        }

        def fake_fetch(_query: str, rotar_desde: int = 0) -> list[dict]:
            return sample["elements"]

        with patch("b2b.osm_places._fetch_overpass", fake_fetch), patch(
            "b2b.osm_places._pausa_entre_consultas"
        ):
            leads, llamadas, meta = buscar_en_pais_osm("Puerto Rico", ["tienda"], 5)
        self.assertGreaterEqual(llamadas, 1)
        self.assertEqual(meta.get("ways"), 1)
        self.assertGreaterEqual(len(leads), 1)


if __name__ == "__main__":
    unittest.main()
