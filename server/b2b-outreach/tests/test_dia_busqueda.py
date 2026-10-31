"""La búsqueda corre lunes–sábado; el domingo no. El horario de correo (zonas.py) no se toca."""
from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from b2b.zonas import tz
from prospector import es_dia_busqueda, prospectar

TZ = tz("America/Santo_Domingo")
TIMER = ROOT / "cds-b2b-buscar.timer"


class TestDiaBusqueda(unittest.TestCase):
    def test_lunes_a_sabado_si_domingo_no(self):
        # 2026-11-02 lunes … 2026-11-07 sábado … 2026-11-08 domingo
        self.assertTrue(es_dia_busqueda(datetime(2026, 11, 2, 9, 0, tzinfo=TZ)))
        self.assertTrue(es_dia_busqueda(datetime(2026, 11, 7, 15, 0, tzinfo=TZ)))
        self.assertFalse(es_dia_busqueda(datetime(2026, 11, 8, 9, 0, tzinfo=TZ)))
        self.assertFalse(es_dia_busqueda(datetime(2026, 11, 8, 23, 59, tzinfo=TZ)))

    def test_timer_solo_lunes_a_sabado(self):
        texto = TIMER.read_text(encoding="utf-8")
        self.assertIn("Mon..Sat", texto)
        self.assertIn("09:00:00 America/Santo_Domingo", texto)
        self.assertIn("15:00:00 America/Santo_Domingo", texto)
        self.assertNotRegex(texto, r"(?m)^OnCalendar=\*-\*-\*")

    def test_prospectar_en_domingo_no_busca(self):
        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp) / "inbox"
            inbox.mkdir()
            with patch("prospector.es_dia_busqueda", return_value=False), patch(
                "prospector._prospectar"
            ) as mock_inner:
                out = prospectar(None, 15, inbox, simulado=False)
        self.assertEqual(out["encolados"], 0)
        self.assertEqual(out["motivo"], "domingo")
        mock_inner.assert_not_called()

    def test_simulado_si_corre_en_domingo(self):
        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp) / "inbox"
            inbox.mkdir()
            with patch("prospector.es_dia_busqueda", return_value=False), patch(
                "prospector._prospectar", return_value={"encolados": 0, "pais": "X", "llamadas": 0}
            ) as mock_inner:
                out = prospectar("Florida", 1, inbox, simulado=True)
        mock_inner.assert_called_once()
        self.assertEqual(out["pais"], "X")


class TestZonasCorreoIntacto(unittest.TestCase):
    def test_envio_sigue_sin_sabado_ni_domingo(self):
        from b2b.zonas import en_horario_laboral

        sabado = datetime(2026, 11, 7, 10, 0, tzinfo=TZ)
        domingo = datetime(2026, 11, 8, 10, 0, tzinfo=TZ)
        lunes = datetime(2026, 11, 2, 10, 0, tzinfo=TZ)
        self.assertFalse(en_horario_laboral(sabado, "Florida"))
        self.assertFalse(en_horario_laboral(domingo, "Florida"))
        self.assertTrue(en_horario_laboral(lunes, "Florida"))


if __name__ == "__main__":
    unittest.main()
