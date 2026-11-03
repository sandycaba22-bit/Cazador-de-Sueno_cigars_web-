"""Alertas sin chat propio: tarjetas, correo o solo log. Una por causa y hora."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from b2b.alertas_operador import alertar


class TestAlertas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            os.environ,
            {
                "B2B_DATA_DIR": str(Path(self.tmp.name) / "data"),
                "B2B_QUEUE_DIR": self.tmp.name,
                "TELEGRAM_BOT_TOKEN": "1:tokenfalso",
                "TELEGRAM_CHAT_ID": "111",
                "TELEGRAM_ALERTAS_CHAT_ID": "",
                "B2B_ALERTAS_EN_CHAT_TARJETAS": "0",
                "B2B_ALERTAS_CORREO": "",
                "B2B_ENVIO_REAL": "0",
                "CORREO_REMITENTE_1": "uno@gmail.com",
                "CORREO_CLAVE_1": "clave-1",
            },
            clear=False,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_sin_canal_solo_log(self):
        def _enviar(*_a, **_k):
            raise AssertionError("no debía llamar a Telegram")

        self.assertFalse(alertar("smtp", "fallo", cooldown_seg=0, enviar=_enviar))
        self.assertFalse(alertar("smtp", "otra", cooldown_seg=3600, enviar=_enviar))

    def test_chat_de_tarjetas_lleva_prefijo_y_no_botones(self):
        os.environ["B2B_ALERTAS_EN_CHAT_TARJETAS"] = "1"
        enviados = []

        def _enviar(token, chat, texto):
            enviados.append((chat, texto))

        self.assertTrue(alertar("google", "tope", cooldown_seg=0, enviar=_enviar))
        self.assertEqual(enviados, [("111", "ALERTA\ntope")])
        self.assertFalse(alertar("google", "otra", cooldown_seg=3600, enviar=_enviar))
        self.assertEqual(len(enviados), 1)
        os.environ["B2B_UNDER_TEST"] = "0"
        capturado = {}

        def _urlopen(req, timeout=0):
            capturado.update(json.loads(req.data.decode("utf-8")))

            class _R:
                def read(self):
                    return b""

                def __enter__(self):
                    return self

                def __exit__(self, *_a):
                    return False

            return _R()

        with patch("urllib.request.urlopen", _urlopen):
            from b2b.alertas_operador import _enviar as enviar_real

            enviar_real("1:tokenfalso", "111", "ALERTA\ntope")
        self.assertNotIn("reply_markup", capturado)

    def test_correo_con_la_cuenta_1_y_una_vez_por_hora(self):
        os.environ["B2B_ALERTAS_CORREO"] = "operador@example.com"
        llamadas = []

        def _correo(destino, texto):
            llamadas.append((destino, texto))
            return True

        with patch("b2b.alertas_operador._correo_alerta", _correo):
            self.assertTrue(alertar("imap", "sin lectura", cooldown_seg=0))
            self.assertFalse(alertar("imap", "sigue", cooldown_seg=3600))
        self.assertEqual(llamadas, [("operador@example.com", "sin lectura")])

    def test_el_chat_propio_no_usa_el_de_las_tarjetas(self):
        os.environ["TELEGRAM_ALERTAS_CHAT_ID"] = "222"
        os.environ["B2B_ALERTAS_EN_CHAT_TARJETAS"] = "1"
        os.environ["B2B_ALERTAS_CORREO"] = "operador@example.com"
        enviados = []
        with patch("b2b.alertas_operador._correo_alerta", side_effect=AssertionError("correo")):
            self.assertTrue(alertar("smtp", "fallo", cooldown_seg=0, enviar=lambda t, c, x: enviados.append(c)))
        self.assertEqual(enviados, ["222"])
