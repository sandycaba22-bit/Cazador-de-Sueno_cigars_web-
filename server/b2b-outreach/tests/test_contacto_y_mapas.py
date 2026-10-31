"""WhatsApp, correo, datos del negocio y mapas en el aviso de Telegram."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b2b.mapas import apple_maps_url, botones_mapa, google_maps_url, waze_url
from b2b.redactor import borrador_corto, borrador_correo
from b2b.telegram_prospecto import link_mailto, link_whatsapp, mensaje_prospecto_completo, teclado_prospecto

LEAD = {
    "nombre": "Miami Cigar Lounge",
    "tipo": "lounge",
    "pais": "Florida",
    "direccion": "123 Brickell Ave, Miami, FL 33131",
    "telefono": "(305) 555-0100",
    "telefono_internacional": "+1 305-555-0100",
    "correo": "info@miamicigar.com",
    "web": "https://miamicigar.com",
    "instagram": "https://www.instagram.com/miamicigar/",
    "rating": 4.8,
    "user_rating_count": 120,
    "place_id": "ChIJ-test",
    "lat": 25.7617,
    "lon": -80.1918,
}


def _urls(lead):
    kb = teclado_prospecto(lead, "Florida", "tok")
    return {b["text"]: b["url"] for fila in kb["inline_keyboard"] for b in fila if "url" in b}


class TestMensaje(unittest.TestCase):
    def test_trae_todos_los_datos_del_negocio(self):
        msg = mensaje_prospecto_completo(LEAD, "Florida")
        for esperado in (
            "Miami Cigar Lounge", "4.8 (120 reseñas)", "+1 (305) 555-0100",
            "info@miamicigar.com", "miamicigar.com", "@miamicigar",
        ):
            self.assertIn(esperado, msg)
        self.assertLessEqual(len(msg), 4096)

    def test_no_inventa_lo_que_no_hay(self):
        msg = mensaje_prospecto_completo({"nombre": "X", "tipo": "tienda", "telefono": "583 1111"}, "Aruba")
        for ausente in ("WhatsApp:", "Correo:", "Web:", "Instagram:", "⭐"):
            self.assertNotIn(ausente, msg)

    def test_whatsapp_publicado_en_la_web_se_marca(self):
        msg = mensaje_prospecto_completo({**LEAD, "whatsapp": "+1 786 555 0199"}, "Florida")
        self.assertIn("info@miamicigar.com", msg)

    def test_borrador_lleva_contacto_de_la_empresa(self):
        for idioma in ("es", "en", "fr"):
            texto = borrador_corto("Miami Cigar Lounge", idioma, "lounge")
            self.assertIn("+1 (809) 464-5016", texto)
            self.assertIn("cazadordesueno1@gmail.com", texto)
            self.assertIn("https://www.cazadordesuenocigar.com/catalogo/", texto)
        correo = borrador_correo("Miami Cigar Lounge", "en", "lounge")
        self.assertIn("WhatsApp +1 (809) 464-5016", correo)


class TestBotones(unittest.TestCase):
    def test_botones_de_contacto_y_mapas(self):
        from b2b.telefono import clasificar_linea
        from b2b.telegram_prospecto import teclado_prospecto as teclado

        kb = teclado(LEAD, "Florida", "tok")
        textos = [b["text"] for fila in kb["inline_keyboard"] for b in fila]
        urls = _urls(LEAD)
        self.assertIn("✉️ Enviar correo", textos)
        self.assertIn("Google Maps", urls)
        self.assertIn("query_place_id=ChIJ-test", urls["Google Maps"])
        self.assertIn("Apple Maps", urls)
        self.assertIn("Waze", urls)
        self.assertNotIn("mailto:", " ".join(urls.values()))
        if clasificar_linea(LEAD["telefono_internacional"], "Florida") == "movil" or LEAD.get("whatsapp"):
            self.assertTrue(urls["📲 WhatsApp"].startswith("https://wa.me/13055550100?text="))
            self.assertIn("+1 (809) 464-5016", unquote(urls["📲 WhatsApp"]))
        else:
            self.assertNotIn("📲 WhatsApp", textos)
        self.assertIn("ll=25.761700,-80.191800", apple_maps_url(LEAD))
        self.assertIn("ll=25.761700,-80.191800", waze_url(LEAD))

    def test_mapas_sin_coordenadas_usan_la_direccion(self):
        lead = {k: v for k, v in LEAD.items() if k not in ("lat", "lon")}
        self.assertIn("q=Miami%20Cigar%20Lounge", apple_maps_url(lead))
        self.assertIn("q=123%20Brickell%20Ave", waze_url(lead))
        self.assertEqual(len(botones_mapa(lead)), 3)

    def test_sin_datos_no_hay_botones_de_mapa(self):
        self.assertEqual(botones_mapa({}), [])
        self.assertEqual(google_maps_url({}), "")
        self.assertEqual(botones_mapa({"lat": 0, "lon": 0}), [])

    def test_url_larga_cae_a_chat_sin_texto(self):
        self.assertEqual(link_whatsapp(LEAD, "x" * 3000), "https://wa.me/13055550100")
        mail = link_mailto({**LEAD, "nombre": "N" * 2000}, "Florida")
        self.assertTrue(mail.startswith("mailto:info@miamicigar.com?subject="))
        self.assertNotIn("&body=", mail)

    def test_siempre_quedan_enviado_y_descartar(self):
        kb = teclado_prospecto({"nombre": "Solo Nombre"}, "Florida", "tok")
        textos = [b["text"] for fila in kb["inline_keyboard"] for b in fila]
        self.assertIn("🗑 Descartar", textos)
        self.assertEqual(kb["inline_keyboard"][-1][0]["text"], "✅ Enviado")
        self.assertEqual(kb["inline_keyboard"][-1][1]["text"], "🗑 Descartar")
        self.assertNotIn("mailto:", str(kb))


if __name__ == "__main__":
    unittest.main()
