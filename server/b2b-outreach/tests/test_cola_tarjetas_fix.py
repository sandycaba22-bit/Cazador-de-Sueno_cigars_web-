"""Regresiones del plan fix/b2b-cola-tarjetas."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from b2b.busqueda_cursor import indice_actual, tomar_consultas
from b2b.despachador_tarjetas import cerrar_tarjeta, despachar, ritmo_maximo
from b2b.envio_correo import (
    _es_remitente_ruido,
    revisar_unsubscribe,
)
from b2b.nombres_busqueda import clasificar_aceptacion
from b2b.telegram_gestion import token_callback
from b2b.telegram_urls import es_error_url_boton, filtrar_teclado, url_boton_valida
from b2b.tarjeta import construir_tarjeta, construir_teclado

AHORA = datetime(2026, 11, 3, 15, 0, tzinfo=timezone.utc)


class TestColaDosAbiertas(unittest.TestCase):
    def test_ritmo_default_2_y_siguiente_inmediata(self):
        with tempfile.TemporaryDirectory() as tmp:
            cola = Path(tmp)
            inbox = cola / "inbox"
            inbox.mkdir()
            with patch.dict(os.environ, {
                "B2B_QUEUE_DIR": str(cola),
                "B2B_DATA_DIR": str(cola / "data"),
                "B2B_TARJETAS_ABIERTAS_MAX": "2",
                "B2B_TELEGRAM_MAX_POR_HORA": "100",
            }), patch("b2b.despachador_tarjetas.puede_enviar_telegram", return_value=True):
                for i in range(4):
                    lead = {
                        "nombre": f"Shop {i}",
                        "pais": "Florida",
                        "web": f"https://s{i}.example",
                        "correo": f"a{i}@s.example",
                        "puntaje": 10 - i,
                        "telegram_notificado": False,
                        "telefono": "+13055550100",
                    }
                    (inbox / f"{i}.json").write_text(json.dumps(lead), encoding="utf-8")
                enviados = []

                def _enviar(lead, _p, _path):
                    enviados.append(lead["nombre"])
                    return True

                self.assertEqual(ritmo_maximo(), 2)
                self.assertEqual(despachar(cola, ahora=AHORA, enviar=_enviar), 2)
                self.assertEqual(enviados, ["Shop 0", "Shop 1"])
                tok = token_callback({"nombre": "Shop 0", "pais": "Florida", "web": "https://s0.example"})
                # token real del primero
                from b2b.despachador_tarjetas import _load

                tok = next(iter(_load()["abiertas"]))
                cerrar_tarjeta(tok, ahora=AHORA)  # espera 0
                self.assertEqual(despachar(cola, ahora=AHORA, enviar=_enviar), 1)
                self.assertIn("Shop 2", enviados)


class TestUrlInvalida(unittest.TestCase):
    def test_filtra_mailto_y_espacios(self):
        self.assertFalse(url_boton_valida("mailto:a@b.com"))
        self.assertFalse(url_boton_valida("https://maps.example/bad place"))
        self.assertTrue(url_boton_valida("https://maps.example/ok"))
        kb = filtrar_teclado({
            "inline_keyboard": [[
                {"text": "Mal", "url": "mailto:x@y.com"},
                {"text": "Ok", "url": "https://ok.example/"},
                {"text": "Enviado", "callback_data": "b2be:t"},
            ]]
        })
        urls = [b.get("url") for fila in kb["inline_keyboard"] for b in fila if "url" in b]
        self.assertEqual(urls, ["https://ok.example/"])
        self.assertTrue(es_error_url_boton(RuntimeError("Telegram rechazó: BUTTON_URL_INVALID")))


class TestExclusionCorreo(unittest.TestCase):
    def test_ignora_noreply(self):
        self.assertTrue(_es_remitente_ruido("no-reply@messaging.metamail.com"))
        self.assertTrue(_es_remitente_ruido("notification@priority.instagram.com"))
        self.assertFalse(_es_remitente_ruido("buyer@cigarshop.example"))

    def test_sin_real_no_toca_imap(self):
        with patch.dict(os.environ, {"B2B_ENVIO_REAL": "0"}):
            self.assertEqual(revisar_unsubscribe(), [])


class TestCursorBusqueda(unittest.TestCase):
    def test_avanza_entre_tandas(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("b2b.busqueda_cursor.state_file", return_value=Path(tmp) / "busqueda_cursor.json"):
                todas = [("tienda", "en", f"q{i}") for i in range(5)]
                a = tomar_consultas("Florida", todas, 2)
                self.assertEqual([c[2] for c in a], ["q0", "q1"])
                self.assertEqual(indice_actual("Florida"), 2)
                b = tomar_consultas("Florida", todas, 2)
                self.assertEqual([c[2] for c in b], ["q2", "q3"])


class TestDedupeDudosoYRevisar(unittest.TestCase):
    def test_excluir_con_cigar_va_a_revisar(self):
        bucket, motivo = clasificar_aceptacion({
            "nombre": "Miami Vape & Cigar Shop",
            "web": "https://example.com",
        })
        self.assertEqual(bucket, "revisar")
        self.assertIn("cigarro", motivo)

    def test_dudoso_unico_por_place_id(self):
        from prospector import _escribir_lead_cola

        with tempfile.TemporaryDirectory() as tmp:
            carpeta = Path(tmp)
            p1 = _escribir_lead_cola(
                carpeta,
                {"nombre": "A", "place_id": "pid-1", "calidad_motivo": "dudoso"},
                unico_por_place_id=True,
            )
            p2 = _escribir_lead_cola(
                carpeta,
                {"nombre": "A", "place_id": "pid-1", "calidad_motivo": "otra"},
                unico_por_place_id=True,
            )
            self.assertEqual(p1, p2)
            self.assertEqual(len(list(carpeta.glob("*.json"))), 1)
            data = json.loads(p2.read_text(encoding="utf-8"))
            self.assertTrue(data.get("primera_fecha"))


class TestContenidoTarjeta(unittest.TestCase):
    def test_para_nunca_vacio_y_saludo_con_nombre(self):
        texto = construir_tarjeta({
            "nombre": "Cuban Crafters",
            "tipo": "tienda",
            "pais": "Florida",
            "formulario": "https://cubancrafters.example/contact",
            "idioma": "en",
        })
        self.assertIn("Para:", texto)
        self.assertNotIn("Para: —", texto)
        self.assertIn("Hello Cuban Crafters team", texto)
        kb = construir_teclado({
            "nombre": "Cuban Crafters",
            "formulario": "https://cubancrafters.example/contact",
            "token": "abc",
        })
        textos = [b["text"] for fila in kb["inline_keyboard"] for b in fila]
        self.assertIn("📝 Formulario", textos)
        self.assertIn("✅ Enviado", textos)


class TestEmbudo(unittest.TestCase):
    def test_texto_embudo(self):
        from b2b.embudo import texto_embudo

        t = texto_embudo(AHORA)
        self.assertIn("Embudo B2B", t)


if __name__ == "__main__":
    unittest.main()
