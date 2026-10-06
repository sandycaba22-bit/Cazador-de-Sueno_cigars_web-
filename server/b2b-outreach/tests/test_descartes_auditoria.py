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
    clasificar_novedad_detalle,
    dedupe_y_fusionar,
    duplicado_contra,
    motivo_descarte_osm,
    motivo_rechazo_generico,
)
from b2b.descartes import append_isla_en_archivo_diario, lineas_resumen_descartes
from b2b.osm_places import _motivo_si_sin_lead


class TestMotivosDescarte(unittest.TestCase):
    def test_vape_etiqueta(self):
        self.assertEqual(
            motivo_descarte_osm("Cloud Vape Shop", {"shop": "tobacco"}),
            "vape/smoke shop",
        )

    def test_rechazo_generico_vape(self):
        lead = {"nombre": "Juul Store", "fuente": "openstreetmap"}
        self.assertEqual(motivo_rechazo_generico(lead), "vape/smoke shop")

    def test_osm_bar_sin_humidor(self):
        el = {
            "type": "node",
            "id": 1,
            "tags": {"name": "Sunset Bar", "amenity": "bar"},
        }
        self.assertEqual(_motivo_si_sin_lead(el, "Aruba"), "bar/café sin humidor")


class TestDuplicadoContra(unittest.TestCase):
    def test_encuentra_inbox(self):
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
            path = inbox / "100-cigar.json"
            path.write_text(json.dumps(lead), encoding="utf-8")
            hit = duplicado_contra(dict(lead), cola)
            self.assertIsNotNone(hit)
            self.assertEqual(hit[0], "inbox")
            self.assertTrue(hit[1])

    def test_clasificar_detalle_repetido(self):
        with tempfile.TemporaryDirectory() as tmp:
            cola = Path(tmp)
            inbox = cola / "inbox"
            inbox.mkdir()
            lead = {"nombre": "Humidor X", "web": "https://hx.test", "place_id": "p1"}
            (inbox / "1.json").write_text(json.dumps(lead), encoding="utf-8")
            nuevos, repetidos, det = clasificar_novedad_detalle([dict(lead)], cola)
            self.assertEqual(len(repetidos), 1)
            self.assertEqual(det[0]["contra"], "inbox")


class TestAuditoriaArchivo(unittest.TestCase):
    def test_dedupe_registra_auditoria(self):
        auditoria: list = []
        lead = {"nombre": "Elf Bar", "fuente": "openstreetmap", "_osm_tags": {"shop": "tobacco"}}
        dedupe_y_fusionar([lead], auditoria)
        self.assertEqual(len(auditoria), 1)

    def test_lineas_telegram_max_diez(self):
        descartes = [{"nombre": f"N{i}", "motivo": "filtro"} for i in range(15)]
        lineas = lineas_resumen_descartes(descartes, [], max_items=10)
        self.assertLessEqual(sum(1 for ln in lineas if ln.startswith("·")), 10)
        self.assertTrue(any("más" in ln for ln in lineas))

    def test_append_archivo_diario(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("b2b.descartes.state_file", lambda name: Path(tmp) / name):
                append_isla_en_archivo_diario(
                    "Aruba",
                    [{"nombre": "Vape Co", "motivo": "vape/smoke shop"}],
                    [],
                )
                files = list(Path(tmp).glob("descartados_*.json"))
                self.assertEqual(len(files), 1)
                data = json.loads(files[0].read_text(encoding="utf-8"))
                self.assertIn("Aruba", data["islas"])


if __name__ == "__main__":
    unittest.main()
