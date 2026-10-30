"""verificar_local: fuera del estado o sin cigarros no entra a la cola."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from b2b.verificacion_local import verificar_local


def _lead(**extra):
    base = {
        "nombre": "Prime Cigar Lounge",
        "web": "https://primecigar.example",
        "telefono": "+1 305-555-0100",
        "direccion": "10 Ocean Dr, Miami, FL 33139",
        "business_status": "OPERATIONAL",
        "rating": 4.7,
        "user_rating_count": 212,
        "vende_cigarros": True,
        "tipo": "lounge",
        "pais": "Florida",
    }
    base.update(extra)
    return base


class TestVerificacionLocal(unittest.TestCase):
    def test_local_completo_pasa(self):
        ok, motivos, resumen = verificar_local(_lead(), "Florida")
        self.assertTrue(ok, motivos)
        self.assertIn("Local verificado", resumen)
        self.assertIn("Dirección en FL", resumen)
        self.assertIn("Web con cigarros", resumen)

    def test_rechaza_direccion_de_otro_estado(self):
        ok, motivos, _resumen = verificar_local(
            _lead(direccion="1 Peachtree St, Atlanta, GA 30303"),
            "Florida",
        )
        self.assertFalse(ok)
        self.assertTrue(any("dirección" in m for m in motivos))

    def test_rechaza_sin_senal_de_cigarros(self):
        ok, motivos, _resumen = verificar_local(
            _lead(nombre="Ocean View Bar", vende_cigarros=False, tipo="hotel"),
            "FL",
        )
        self.assertFalse(ok)
        self.assertTrue(any("cigarro" in m for m in motivos))

    def test_virginia_no_es_west_virginia(self):
        ok, _motivos, _resumen = verificar_local(
            _lead(direccion="100 Capitol St, Charleston, WV 25301", nombre="Capitol Cigars"),
            "Virginia",
        )
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
