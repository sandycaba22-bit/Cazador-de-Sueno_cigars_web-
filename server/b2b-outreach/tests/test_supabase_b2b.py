"""El cliente de Supabase no llama a la red si no hay credenciales."""
from __future__ import annotations

import json
import unittest
from unittest import mock

from b2b import supabase_client as sb
from b2b.telegram_control import _manejar_solicitud_precio


class SupabaseClientTests(unittest.TestCase):
    def test_sin_credenciales_no_escribe(self):
        with mock.patch.dict("os.environ", {}, clear=False):
            for name in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY"):
                __import__("os").environ.pop(name, None)
            self.assertFalse(sb.configurado())
            self.assertFalse(sb.guardar_lead_b2b({"nombre": "Casa", "place_id": "abc"}))

    def test_inserta_lead_con_la_clave_de_servicio(self):
        capturado = {}

        class Respuesta:
            status = 201

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b""

        def urlopen(req, timeout=0):
            capturado["url"] = req.full_url
            capturado["method"] = req.get_method()
            capturado["body"] = json.loads(req.data.decode("utf-8"))
            capturado["auth"] = req.header_items()
            return Respuesta()

        entorno = {
            "SUPABASE_URL": "https://ejemplo.supabase.co",
            "SUPABASE_ANON_KEY": "anon-publica",
            "SUPABASE_SERVICE_ROLE_KEY": "servicio-secreto",
        }
        with mock.patch.dict("os.environ", entorno, clear=False), \
                mock.patch.object(sb.urllib.request, "urlopen", urlopen):
            ok = sb.guardar_lead_b2b({
                "nombre": "Tabacos del Caribe",
                "place_id": "ChIJ-real",
                "direccion": "Calle 1",
                "pais": "República Dominicana",
                "tipo_negocio": "tienda",
                "telefono": "8095550000",
                "fuente": "google_places",
            })
        self.assertTrue(ok)
        self.assertIn("/rest/v1/leads_b2b", capturado["url"])
        self.assertEqual(capturado["body"]["nombre"], "Tabacos del Caribe")
        self.assertEqual(capturado["body"]["place_id"], "ChIJ-real")
        claves = {k.lower(): v for k, v in capturado["auth"]}
        self.assertEqual(claves.get("apikey"), "servicio-secreto")

    def test_boton_de_telegram_actualiza_la_solicitud(self):
        entorno = {
            "SUPABASE_URL": "https://ejemplo.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "servicio-secreto",
        }
        with mock.patch.dict("os.environ", entorno, clear=False), \
                mock.patch.object(sb, "actualizar_solicitud", return_value=True) as actualizar, \
                mock.patch("b2b.telegram_control._cerrar_botones"):
            texto = _manejar_solicitud_precio(
                "token",
                "99",
                {"message": {"chat": {"id": "99"}, "message_id": 4}, "id": "cb1"},
                "b2ba:abc123abc123",
            )
        actualizar.assert_called_once_with("abc123abc123", "aprobado")
        self.assertIn("aprobado", texto.lower())


if __name__ == "__main__":
    unittest.main()
