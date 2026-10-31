"""La tarjeta siempre lleva Enviado y Descartar, y el correo no usa mailto:."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from b2b.redactor import email_empresa, whatsapp_empresa
from b2b.tarjeta import construir_tarjeta, construir_teclado
from b2b.telefono import formato_visible


def _textos(prospecto):
    kb = construir_teclado(prospecto)
    return [b["text"] for fila in kb["inline_keyboard"] for b in fila], kb


class TestCombinaciones(unittest.TestCase):
    def _base(self, **extra):
        lead = {
            "nombre": "Dosal Tobacco",
            "tipo": "tienda",
            "pais": "Florida",
            "ciudad": "Miami",
            "estado": "Florida",
            "direccion": "1 Main St",
            "token": "tok",
        }
        lead.update(extra)
        return lead

    def test_cuatro_combinaciones_siempre_tienen_enviado_y_descartar(self):
        casos = {
            "solo_correo": self._base(correo="info@dosal.example"),
            "solo_telefono": self._base(telefono="+13055550199", telefono_internacional="+13055550199"),
            "ambos": self._base(correo="info@dosal.example", telefono="+13055550199", whatsapp="13055550199"),
            "ninguno": self._base(),
        }
        with patch("b2b.telefono.clasificar_linea", return_value="movil"):
            for nombre, lead in casos.items():
                textos, kb = _textos(lead)
                self.assertIn("✅ Enviado", textos, nombre)
                self.assertIn("🗑 Descartar", textos, nombre)
                self.assertGreaterEqual(len(kb["inline_keyboard"]), 1, nombre)
                self.assertNotIn("mailto:", str(kb), nombre)
                if lead.get("correo"):
                    self.assertIn("✉️ Enviar correo", textos, nombre)
                    boton = next(b for fila in kb["inline_keyboard"] for b in fila if b["text"] == "✉️ Enviar correo")
                    self.assertTrue(boton["callback_data"].startswith("b2bm:"), nombre)
                else:
                    self.assertNotIn("✉️ Enviar correo", textos, nombre)
                if lead.get("telefono") or lead.get("whatsapp"):
                    self.assertIn("📲 WhatsApp", textos, nombre)
                else:
                    self.assertNotIn("📲 WhatsApp", textos, nombre)
        with patch("b2b.telefono.clasificar_linea", return_value="fijo"):
            textos, _kb = _textos(self._base(telefono="+13055550100"))
            self.assertNotIn("📲 WhatsApp", textos)
            self.assertIn("Posible fijo: llamar", construir_tarjeta(self._base(telefono="+13055550100", idioma="en")))
            self.assertIn("Guion de llamada", construir_tarjeta(self._base(telefono="+13055550100", idioma="en")))
        with patch("b2b.telefono.clasificar_linea", return_value="incierto"):
            textos, _kb = _textos(self._base(telefono="555"))
            self.assertNotIn("📲 WhatsApp", textos)

    def test_correo_en_monospace_y_ciudad_estado(self):
        texto = construir_tarjeta(self._base(correo="info@dosal.example", rating=4.8, user_rating_count=12))
        self.assertIn("<code>info@dosal.example</code>", texto)
        self.assertIn("Miami, Florida", texto)
        self.assertIn("Borrador sugerido", texto)
        self.assertIn("<pre>", texto)
        self.assertIn("cigar shop", texto.lower())

    def test_lounge_no_se_cambia_por_shop(self):
        texto = construir_tarjeta(self._base(tipo="lounge", idioma="en", telefono="+13055550199"))
        self.assertIn("Lounge", texto)
        self.assertIn("lounge", texto.lower())

    def test_telefono_yaniris_y_typo(self):
        self.assertEqual(formato_visible("8094645016", "DO"), "+1 (809) 464-5016")
        with patch.dict(os.environ, {"FIRMA_TELEFONO": "", "FIRMA_EMAIL": "cazardordesuenol@gmail.com"}):
            self.assertEqual(whatsapp_empresa(), "+1 (809) 464-5016")
            self.assertEqual(email_empresa(), "cazadordesueno1@gmail.com")
            self.assertNotIn("cazardordesuenol", email_empresa())


if __name__ == "__main__":
    unittest.main()
