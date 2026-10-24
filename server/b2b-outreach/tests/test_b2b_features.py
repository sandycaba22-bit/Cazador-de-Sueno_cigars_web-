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
    def test_orden_estados_y_mercados_activos(self):
        data = cargar_reglas()
        prio = data["prioridad_inicial"]
        mercados = [p["pais"] for p in data["paises"]]
        self.assertEqual(prio[0], "Florida")
        self.assertEqual(prio[1], "Texas")
        self.assertIn("Puerto Rico", mercados)
        self.assertIn("Jamaica", mercados)
        self.assertNotIn("Nigeria", mercados)
        self.assertEqual(len(mercados), 53)
        self.assertLess(prio.index("California"), prio.index("Wyoming"))
        self.assertEqual(prio[-1], "District of Columbia")
        self.assertEqual(len(paises_prioridad_inicial()), len(prio))

    def test_busqueda_default_estados_configurados(self):
        islas = [p["pais"] for p in paises_prioridad_busqueda()]
        self.assertEqual(islas[0], "Florida")
        self.assertIn("Virginia", islas)
        self.assertNotIn("Nigeria", islas)
        self.assertIn("District of Columbia", islas)
        self.assertEqual(islas, cargar_reglas()["prioridad_inicial"])

    def test_tipos_incluyen_casino(self):
        tipos = cargar_reglas()["orden_tipos_negocio"]
        self.assertIn("casino", tipos)
        self.assertIn("distribuidor", tipos)


class TestIdiomaPais(unittest.TestCase):
    def test_puerto_rico_espanol(self):
        self.assertEqual(idioma_para_pais("Puerto Rico"), "es")

    def test_florida_ingles(self):
        self.assertEqual(idioma_para_pais("Florida"), "en")

    def test_jamaica_ingles(self):
        self.assertEqual(idioma_para_pais("Jamaica"), "en")

    def test_puerto_rico_preferido_ingles(self):
        self.assertEqual(idioma_para_pais("Puerto Rico", preferido="en"), "en")


class TestAliasUSA(unittest.TestCase):
    def test_alias_nacionales_no_inventan_un_estado(self):
        for clave in ("USA", "U.S.A.", "EE.UU.", "Estados Unidos"):
            entry = buscar_pais(clave)
            self.assertIsNone(entry, clave)
            self.assertEqual(ALIASES[clave.lower()], "United States")

    def test_nombres_activos_sin_mayusculas(self):
        for nombre in ("Florida", "Puerto Rico", "Jamaica"):
            self.assertEqual(buscar_pais(nombre.lower())["pais"], nombre)


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

        with patch.object(places_mod.budget, "motivo_bloqueo", return_value="diario"), patch.object(
            places_mod, "_avisar_tope"
        ), patch.object(places_mod, "_post_search") as post, patch.object(
            places_mod, "cache_path", return_value=Path(tempfile.mkdtemp()) / "cache.json"
        ):
            leads, llamadas, stats = places_mod.buscar_google_pais("Florida", ["tienda"])
        post.assert_not_called()
        self.assertEqual(leads, [])
        self.assertEqual(llamadas, 0)
        self.assertEqual(stats["presupuesto_agotado"], "diario")


class TestCatalogoFaltante(unittest.TestCase):
    def test_sin_catalogo_falla(self):
        with patch(
            "b2b.catalogo_check.CATALOG_SCRIPT",
            Path("/no/existe/build_wholesale_catalog.py"),
        ):
            with self.assertRaises(CatalogoError):
                verificar_catalogo("en")


class TestBorradorIdioma(unittest.TestCase):
    def test_catalogo_frances_preservado(self):
        from b2b.redactor import borrador_prospecto

        draft = borrador_prospecto("fr", "Boutique Test", "tienda")
        self.assertIn("Bonjour", draft)
        self.assertIn("Catalogue grossiste PDF", draft)

    def test_florida_ingles(self):
        from b2b.redactor import borrador_prospecto

        draft = borrador_prospecto("en", "Florida Shop", "tienda")
        self.assertIn("Hello Florida Shop", draft)
        self.assertIn("Wholesale catalog PDF", draft)


if __name__ == "__main__":
    unittest.main()
