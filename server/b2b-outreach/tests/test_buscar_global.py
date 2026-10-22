from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from b2b.osm_cuadricula import celdas_desde_bbox, preparar_celdas_pais
from b2b.paises_cola import cargar_paises_cola, entry_por_pais
from b2b.redactor import texto_corto_prospecto_buscar
from b2b.telegram_control import puede_enviar_telegram, set_pausado
from b2b.redactor import EMAIL_VP_VENTAS, presentacion_prospecto_telegram
from b2b.telegram_gestion import tiene_medio_contacto, token_callback
from b2b.telegram_prospecto import mensaje_prospecto_completo, teclado_prospecto


class TestPaisesCola(unittest.TestCase):
    def test_orden_florida_primero(self):
        fila = cargar_paises_cola()
        self.assertGreater(len(fila), 10)
        self.assertEqual(fila[0].get("zona"), "florida")
        self.assertEqual(fila[0].get("pais"), "Florida")

    def test_entries_activos(self):
        for pais, iso in (("Florida", "US"), ("Puerto Rico", "PR"), ("Jamaica", "JM")):
            row = entry_por_pais(pais)
            self.assertIsNotNone(row)
            self.assertEqual(row["iso3166"], iso)


class TestCuadricula(unittest.TestCase):
    def test_celdas_miami_pequeno(self):
        box = {"south": 25.65, "west": -80.35, "north": 25.87, "east": -80.14}
        celdas = celdas_desde_bbox(box, paso=0.45)
        self.assertGreaterEqual(len(celdas), 1)
        self.assertLessEqual(len(celdas), 4)

    def test_preparar_pr_jm(self):
        for iso in ("PR", "JM"):
            self.assertTrue(preparar_celdas_pais(iso))


class TestTelegramProspecto(unittest.TestCase):
    def test_mensaje_completo_contacto_y_firma(self):
        lead = {
            "nombre": "Test Shop",
            "tipo": "lounge",
            "telefono": "+13055550100",
            "telefono_internacional": "+13055550100",
            "web": "https://example.com",
            "correo": "info@example.com",
            "direccion": "Main St",
            "pais": "Florida",
        }
        msg = mensaje_prospecto_completo(lead, "Florida")
        self.assertIn("Test Shop", msg)
        self.assertIn("Teléfono y correo confirmados", msg)
        self.assertIn("Yaniris Agustina Ureña", msg)
        botones = teclado_prospecto(lead, "Florida", token_callback(lead))
        urls = [b.get("url", "") for fila in botones["inline_keyboard"] for b in fila]
        self.assertTrue(any(url.startswith("https://wa.me/13055550100?") for url in urls))
        correo = next(unquote(url) for url in urls if url.startswith("mailto:"))
        self.assertIn(EMAIL_VP_VENTAS, correo)
        self.assertIn("reply STOP", correo)
        self.assertNotIn("STOP", msg)

    def test_tiene_medio_web(self):
        self.assertTrue(tiene_medio_contacto({"web": "https://shop.example"}))

    def test_presentacion_firma_vp(self):
        t = presentacion_prospecto_telegram("Cigar House", "en", "tienda")
        self.assertIn("Yaniris", t)
        self.assertIn("Vice President", t)
        self.assertIn(EMAIL_VP_VENTAS, t)

    def test_token_callback_estable(self):
        lead = {"nombre": "A", "web": "https://a.com", "pais": "Jamaica"}
        self.assertEqual(token_callback(lead), token_callback(lead))


class TestCallbackDescartar(unittest.TestCase):
    def test_descartar_marca_y_bloquea(self):
        import tempfile
        from unittest.mock import patch

        import b2b.leads_store as ls
        import b2b.telegram_control as tc
        import b2b.telegram_gestion as tg

        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            with patch.object(ls, "NO_CONTACT_STATE_PATH", tmp_p / "nc.json"), patch.object(
                tg, "GESTION_PATH", tmp_p / "gest.json"
            ), patch.object(tg, "PENDIENTES_PATH", tmp_p / "pend.json"), patch.object(
                tc, "_telegram_post", return_value={"ok": True}
            ):
                lead = {"nombre": "Shop X", "web": "https://shopx.test", "pais": "Puerto Rico"}
                tok = tg.token_callback(lead)
                tg.registrar_pendiente(tok, lead)
                cb = {
                    "id": "1",
                    "data": f"b2bd:{tok}",
                    "message": {"chat": {"id": 42}},
                }
                ack = tc._manejar_callback("t", "42", cb)
                self.assertIn("Descartado", ack)
                self.assertTrue(tg.ya_gestionado_telegram(lead))
                self.assertTrue(ls.en_lista_no_contactar("Shop X", "https://shopx.test"))


class TestTelegramControl(unittest.TestCase):
    def test_pausa_bloquea(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "b2b.telegram_control.CONTROL_PATH", Path(tmp) / "control.json"
        ):
            set_pausado(True)
            self.assertFalse(puede_enviar_telegram())
            set_pausado(False)
            self.assertTrue(puede_enviar_telegram())


if __name__ == "__main__":
    unittest.main()
