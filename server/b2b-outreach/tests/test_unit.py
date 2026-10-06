from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from b2b.budget import max_calls, registrar_llamada
from b2b.idioma import idioma_para_pais
from b2b.leads_store import en_lista_no_contactar, marcar_visto, ya_visto
from b2b.places import buscar_en_pais
from b2b.redactor import PROHIBIDO_RE, borrador_prospecto, generar_tarjeta_telegram
from b2b.website import _email_valido, _emails_en_html


class TestEmail(unittest.TestCase):
    def test_solo_genericos(self):
        self.assertTrue(_email_valido("info@example.com", "https://www.example.com"))
        self.assertFalse(_email_valido("john.doe@example.com", "https://www.example.com"))

    def test_extraccion_html(self):
        html = '<a href="mailto:contacto@miempresa.com">Contacto</a>'
        emails = _emails_en_html(html, "https://miempresa.com")
        self.assertEqual(emails, ["contacto@miempresa.com"])


class TestIdioma(unittest.TestCase):
    def test_sint_maarten_nl(self):
        self.assertEqual(idioma_para_pais("Sint Maarten"), "nl")

    def test_aruba_en(self):
        self.assertEqual(idioma_para_pais("Aruba"), "en")

    def test_barbados_en(self):
        self.assertEqual(idioma_para_pais("Barbados"), "en")


class TestDedup(unittest.TestCase):
    def test_place_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = Path(tmp) / "registro_leads.json"
            with patch("b2b.leads_store.SEEN_PATH", reg):
                marcar_visto("abc123", "https://shop.test")
                self.assertTrue(ya_visto("abc123", ""))
                self.assertFalse(ya_visto("otro", ""))


class TestNoContactar(unittest.TestCase):
    def test_bloqueo(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "no_contactar.json"
            path.write_text(
                json.dumps({"negocios": [{"nombre": "Bloqueado SA", "web": "https://bloqueado.test"}]}),
                encoding="utf-8",
            )
            with patch("b2b.leads_store.NO_CONTACT_PATH", path):
                self.assertTrue(en_lista_no_contactar("Bloqueado SA", ""))


class TestBudget(unittest.TestCase):
    def test_tope(self):
        from b2b import budget as budget_mod

        with tempfile.TemporaryDirectory() as tmp:
            budget = Path(tmp) / "places_budget.json"
            with patch.object(budget_mod, "BUDGET_PATH", budget), patch.object(
                budget_mod, "max_calls", lambda: 2
            ):
                self.assertTrue(budget_mod.puede_llamar())
                budget_mod.registrar_llamada(1)
                budget_mod.registrar_llamada(1)
                self.assertFalse(budget_mod.puede_llamar())


class TestRedactor(unittest.TestCase):
    def test_seis_vitolas_catalogo(self):
        from b2b.catalogo_vitolas import cargar_vitolas_catalogo, vitolas_ordenadas

        self.assertEqual(len(cargar_vitolas_catalogo()), 6)
        orden = [v["name"]["es"] for v in vitolas_ordenadas()]
        self.assertEqual(orden[0], "El Sultán")
        self.assertEqual(orden[1], "Ligero 007")
        self.assertEqual(len(orden), 6)

    def test_sin_precios_y_baja(self):
        draft = borrador_prospecto("en", "Test Shop", "tienda")
        self.assertNotRegex(draft, PROHIBIDO_RE)
        self.assertIn("STOP", draft)
        self.assertIn("six vitolas", draft.lower())
        self.assertIn("The Sultan", draft)
        self.assertNotIn("El Sultán", draft)
        self.assertIn("We'd be glad to set up a call", draft)

    def test_angulos_diferentes(self):
        d = borrador_prospecto("en", "X", "distribuidor")
        t = borrador_prospecto("en", "X", "tienda")
        h = borrador_prospecto("en", "X", "hotel")
        self.assertNotEqual(d, t)
        self.assertIn("humidor", h.lower())

    def test_tarjeta_sin_correo(self):
        paquete = generar_tarjeta_telegram(
            "Demo",
            "Barbados",
            "https://example-bb.test",
            "",
            {"sin_correo_publico": True, "tipo": "tienda", "dificultad_aduana": 2},
        )
        self.assertIn("sin correo publicado", paquete["texto"])
        self.assertIn("Yaniris Agustina Ureña", paquete["texto"])


class TestProspectarSimulado(unittest.TestCase):
    def test_sin_duplicados_place_id(self):
        leads, _, _stats = buscar_en_pais("Sint Maarten", ["tienda", "distribuidor"], 15, simulado=True)
        ids = [lead["place_id"] for lead in leads]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
