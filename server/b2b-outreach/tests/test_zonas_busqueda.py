"""Rotación por zona: enfriamiento, peso, tope y cursor. Sin red."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

from b2b.busqueda_cursor import estado_zonas
from b2b.zonas_busqueda import elegir_zonas, registrar_zonas, texto_zonas


AHORA = datetime(2026, 11, 2, 15, 0, tzinfo=timezone.utc)

TABLA = {
    "zonas": [
        {"id": "FL", "pais": "United States", "zona": "Florida", "zona_iana": "America/New_York", "activa": True, "peso": 2},
        {"id": "TX", "pais": "United States", "zona": "Texas", "zona_iana": "America/Chicago", "activa": True, "peso": 2},
        {"id": "CA-ON", "pais": "Canada", "zona": "Ontario", "zona_iana": "America/Toronto", "activa": True, "peso": 1},
        {"id": "CA-BC", "pais": "Canada", "zona": "British Columbia", "zona_iana": "America/Vancouver", "activa": True, "peso": 1},
        {"id": "MX", "pais": "Mexico", "zona": "Mexico", "zona_iana": "America/Mexico_City", "activa": False, "peso": 9},
    ]
}


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "zonas.json"
        self.path.write_text(json.dumps(TABLA), encoding="utf-8")
        self.env = patch.dict(
            os.environ,
            {
                "B2B_ZONAS_BUSQUEDA_PATH": str(self.path),
                "B2B_DATA_DIR": str(Path(self.tmp.name) / "data"),
                "B2B_QUEUE_DIR": self.tmp.name,
                "B2B_ZONA_ENFRIAMIENTO_DIAS": "7",
                "B2B_TARJETAS_POR_ZONA": "2",
                "B2B_NEGOCIOS_POR_ZONA": "2",
            },
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()


class TestRotacion(_Base):
    def test_no_repite_dentro_del_enfriamiento(self):
        registrar_zonas([{"id": "FL", "zona": "Florida", "pais": "United States", "peso": 2}], AHORA)
        manana = AHORA + timedelta(days=1)
        ids = [z["id"] for z in elegir_zonas(3, manana)]
        self.assertNotIn("FL", ids)
        self.assertNotIn("MX", ids)
        despues = AHORA + timedelta(days=7)
        self.assertIn("FL", [z["id"] for z in elegir_zonas(4, despues)])

    def test_si_todas_estan_calientes_igual_elige(self):
        for zona in TABLA["zonas"]:
            if zona["activa"]:
                registrar_zonas([zona], AHORA)
        self.assertEqual(len(elegir_zonas(2, AHORA + timedelta(hours=1))), 2)

    def test_pais_apagado_no_entra_y_el_peso_reparte(self):
        elegidas = elegir_zonas(3, AHORA)
        self.assertNotIn("MX", [z["id"] for z in elegidas])
        estados = sum(1 for z in elegidas if z["pais"] == "United States")
        self.assertEqual(estados, 2)
        self.assertEqual(sum(1 for z in elegidas if z["pais"] == "Canada"), 1)

    def test_el_cursor_avanza_en_cada_tanda(self):
        primera = elegir_zonas(2, AHORA)
        registrar_zonas(primera, AHORA)
        luego = AHORA + timedelta(days=8)
        segunda = elegir_zonas(2, luego)
        registrar_zonas(segunda, luego)
        self.assertNotEqual(
            [z["id"] for z in primera],
            [],
        )
        for zona in segunda:
            self.assertGreaterEqual(int(estado_zonas()[zona["id"]]["veces"]), 1)
            self.assertTrue(estado_zonas()[zona["id"]]["ultima"].startswith("2026-11-10"))

    def test_comando_zonas_lista_activas_y_apagados(self):
        texto = texto_zonas(AHORA)
        self.assertIn("Florida", texto)
        self.assertIn("aún no", texto)
        self.assertIn("Mexico", texto)


class TestTope(unittest.TestCase):
    def test_dos_por_zona_y_prioriza_la_zona_nueva(self):
        from b2b.despachador_tarjetas import despachar

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        cola = Path(tmp.name)
        inbox = cola / "inbox"
        inbox.mkdir()
        env = patch.dict(
            os.environ,
            {
                "B2B_QUEUE_DIR": str(cola),
                "B2B_DATA_DIR": str(cola / "data"),
                "B2B_TARJETAS_ABIERTAS_MAX": "4",
                "B2B_TELEGRAM_MAX_POR_HORA": "100",
                "B2B_TARJETAS_POR_ZONA": "2",
                "B2B_ZONAS_BUSQUEDA_PATH": str(ROOT / "config" / "zonas_busqueda.json"),
            },
        )
        env.start()
        self.addCleanup(env.stop)
        enviados = []

        def _enviar(lead, _pais, path):
            enviados.append(lead["pais"])
            return True

        for i, pais in enumerate(("Florida", "Florida", "Florida", "Texas")):
            lead = {
                "nombre": f"Shop {pais} {i}",
                "pais": pais,
                "estado": pais,
                "correo": f"a{i}@shop{i}.example",
                "web": f"https://shop{i}.example",
                "telefono": "+13055550100",
                "puntaje": 10 - i,
                "telegram_notificado": False,
            }
            (inbox / f"{i}.json").write_text(json.dumps(lead), encoding="utf-8")
        with patch("b2b.despachador_tarjetas.puede_enviar_telegram", return_value=True):
            self.assertEqual(despachar(cola, ahora=AHORA, enviar=_enviar), 3)
        self.assertEqual(enviados.count("Florida"), 2)
        self.assertIn("Texas", enviados)
