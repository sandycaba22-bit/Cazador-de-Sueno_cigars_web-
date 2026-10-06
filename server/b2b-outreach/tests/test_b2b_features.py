from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from b2b.budget import registrar_llamada
from b2b.catalogo_check import CatalogoError, verificar_catalogo
from b2b.country_rules import (
    ALIASES,
    buscar_pais,
    cargar_reglas,
    paises_prioridad_busqueda,
    paises_prioridad_inicial,
)
from b2b.idioma import idioma_para_pais
from b2b.lead_score import califica_lead, puntuar_lead


class TestPrioridadInicial(unittest.TestCase):
    def test_orden_islas_luego_africa(self):
        data = cargar_reglas()
        prio = data["prioridad_inicial"]
        caribe = data["prioridad_caribe"]
        self.assertEqual(prio[0], "Aruba")
        self.assertEqual(caribe[0], "Aruba")
        self.assertIn("Barbados", caribe)
        self.assertIn("Haiti", caribe)
        self.assertNotIn("Nigeria", caribe)
        self.assertIn("Nigeria", prio)
        self.assertLess(prio.index("Mauritius"), prio.index("Nigeria"))
        self.assertEqual(prio[-1], "Angola")
        self.assertEqual(len(paises_prioridad_inicial()), len(prio))

    def test_busqueda_default_solo_caribe(self):
        islas = [p["pais"] for p in paises_prioridad_busqueda()]
        self.assertEqual(islas[0], "Aruba")
        self.assertIn("Sint Maarten", islas)
        self.assertNotIn("Nigeria", islas)
        self.assertNotIn("Dominican Republic", islas)

    def test_tipos_incluyen_casino(self):
        tipos = cargar_reglas()["orden_tipos_negocio"]
        self.assertIn("casino", tipos)
        self.assertIn("distribuidor", tipos)


class TestIdiomaPais(unittest.TestCase):
    def test_senegal_frances(self):
        self.assertEqual(idioma_para_pais("Senegal"), "fr")

    def test_aruba_ingles(self):
        self.assertEqual(idioma_para_pais("Aruba"), "en")

    def test_angola_portugues(self):
        self.assertEqual(idioma_para_pais("Angola"), "pt")

    def test_cabo_verde_portugues(self):
        self.assertEqual(idioma_para_pais("Cape Verde"), "pt")


class TestAliasUSA(unittest.TestCase):
    def test_alias_resuelven_united_states(self):
        for clave in ("USA", "U.S.A.", "EE.UU.", "Estados Unidos"):
            entry = buscar_pais(clave)
            self.assertIsNotNone(entry, clave)
            self.assertEqual(entry["pais"], "United States")

    def test_canada(self):
        self.assertEqual(buscar_pais("Canadá")["pais"], "Canada")
        self.assertIn("canada", ALIASES)


class TestPuntajeLead(unittest.TestCase):
    def test_distribuidor_con_web_pasa_minimo(self):
        lead = {
            "tipo": "distribuidor",
            "web": "https://example.com",
            "telefono": "+1",
            "correo": "info@example.com",
        }
        score, _ = puntuar_lead(lead)
        self.assertGreaterEqual(score, 4)
        self.assertTrue(califica_lead(lead))

    def test_lead_debil_no_califica(self):
        lead = {"tipo": "tienda", "web": ""}
        self.assertFalse(califica_lead(lead))


class TestPresupuestoPlaces(unittest.TestCase):
    def test_tope_detiene_busqueda(self):
        from b2b import places as places_mod

        with patch.object(places_mod, "puede_llamar", return_value=False), patch.object(
            places_mod, "registrar_presupuesto_agotado", lambda: Path("logs/test.jsonl")
        ):
            leads, llamadas = places_mod.buscar_en_pais(
                "Aruba",
                ["tienda"],
                5,
                simulado=False,
            )
        self.assertEqual(leads, [])
        self.assertEqual(llamadas, 0)


class TestCatalogoFaltante(unittest.TestCase):
    def test_sin_catalogo_falla(self):
        with patch(
            "b2b.catalogo_check.CATALOG_SCRIPT",
            Path("/no/existe/build_wholesale_catalog.py"),
        ):
            with self.assertRaises(CatalogoError):
                verificar_catalogo("en")


class TestBorradorIdioma(unittest.TestCase):
    def test_senegal_frances(self):
        from b2b.redactor import borrador_prospecto

        draft = borrador_prospecto("fr", "Boutique Test", "tienda")
        self.assertIn("Bonjour", draft)
        self.assertIn("Catalogue grossiste PDF", draft)

    def test_aruba_ingles(self):
        from b2b.redactor import borrador_prospecto

        draft = borrador_prospecto("en", "Aruba Shop", "tienda")
        self.assertIn("Hello Aruba Shop", draft)
        self.assertIn("Wholesale catalog PDF", draft)


if __name__ == "__main__":
    unittest.main()
