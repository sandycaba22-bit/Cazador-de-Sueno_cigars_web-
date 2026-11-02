"""Robustez fase 2: sin red. Alertas, arranque, reconciliación, lock, rebote, respaldo, /salud."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from b2b.alertas_operador import alertar
from b2b.arranque import advertencias_arranque, errores_arranque
from b2b.envio_correo import aplicar_rebote, correo_de_rebote
from b2b.io_atomico import escribir_json
from b2b.reconciliar import reconciliar, toca_noche
from b2b.respaldo import RETENCION_DIAS, respaldar_si_toca
from b2b.salud import avisos_periodicos, texto_salud

TOKEN = "123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxx"
CHAT_TARJETAS = "1111111111"
CHAT_MIO = "2222222222"


def _env_ok(**extra):
    base = {
        "TELEGRAM_BOT_TOKEN": TOKEN,
        "TELEGRAM_CHAT_ID": CHAT_TARJETAS,
        "TELEGRAM_ALERTAS_CHAT_ID": CHAT_MIO,
        "B2B_ENVIO_REAL": "0",
        "FUENTE_LEADS": "osm",
        "GOOGLE_PLACES_API_KEY": "",
    }
    base.update(extra)
    return base


class TestAlertasNoVanAlChatDeTarjetas(unittest.TestCase):
    def test_solo_chat_de_alertas_y_sin_red_si_falta(self):
        enviados = []

        def _enviar(token, chat, texto):
            enviados.append((chat, texto))

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {
                **_env_ok(),
                "B2B_DATA_DIR": str(Path(tmp) / "data"),
                "B2B_QUEUE_DIR": str(Path(tmp) / "cola"),
            }, clear=False):
                self.assertTrue(alertar("smtp", "fallo smtp", cooldown_seg=0, enviar=_enviar))
                self.assertFalse(alertar("smtp", "otra", cooldown_seg=3600, enviar=_enviar))
                self.assertEqual(enviados, [(CHAT_MIO, "fallo smtp")])
                self.assertNotIn(CHAT_TARJETAS, {c for c, _ in enviados})

    def test_sin_chat_de_alertas_no_llama_a_telegram(self):
        def _enviar(*_a, **_k):
            raise AssertionError("no debía haber red")

        with tempfile.TemporaryDirectory() as tmp:
            env = _env_ok()
            env["TELEGRAM_ALERTAS_CHAT_ID"] = ""
            with patch.dict(os.environ, {**env, "B2B_DATA_DIR": str(Path(tmp) / "data")}, clear=False):
                self.assertFalse(alertar("x", "hola", cooldown_seg=0, enviar=_enviar))


class TestArranque(unittest.TestCase):
    def test_falta_token_o_chat_o_gmail(self):
        with patch.dict(os.environ, {
            "TELEGRAM_BOT_TOKEN": "",
            "TELEGRAM_CHAT_ID": "abc",
            "TELEGRAM_ALERTAS_CHAT_ID": CHAT_TARJETAS,
            "B2B_ENVIO_REAL": "1",
            "FUENTE_LEADS": "google",
            "GOOGLE_PLACES_API_KEY": "",
            "CORREO_REMITENTE_1": "",
            "CORREO_CLAVE_1": "",
            "EMAIL_REMITENTE_1": "",
            "EMAIL_CLAVE_1": "",
            "CORREO_REMITENTE_2": "",
            "CORREO_CLAVE_2": "",
            "EMAIL_REMITENTE_2": "",
            "EMAIL_CLAVE_2": "",
        }, clear=False):
            texto = "\n".join(errores_arranque())
            avisos = "\n".join(advertencias_arranque())
            self.assertIn("TELEGRAM_BOT_TOKEN", texto)
            self.assertIn("TELEGRAM_CHAT_ID", texto)
            self.assertNotIn("TELEGRAM_ALERTAS", texto)
            self.assertIn("GOOGLE_PLACES_API_KEY", avisos)
            self.assertIn("clave de aplicación", avisos)

    def test_sin_chat_de_alertas_no_aborta(self):
        with patch.dict(os.environ, _env_ok(TELEGRAM_ALERTAS_CHAT_ID=""), clear=False):
            self.assertEqual(errores_arranque(), [])
            self.assertTrue(any("arranca" in a for a in advertencias_arranque()))

    def test_ok_no_toca_red(self):
        with patch.dict(os.environ, _env_ok(), clear=False):
            self.assertEqual(errores_arranque(), [])


class TestReconciliar(unittest.TestCase):
    def test_cierra_abierta_ya_contactada(self):
        with tempfile.TemporaryDirectory() as tmp:
            cola = Path(tmp) / "cola"
            data = Path(tmp) / "data"
            inbox = cola / "inbox"
            inbox.mkdir(parents=True)
            (data).mkdir()
            (data / "envios_correo.json").write_text(json.dumps({
                "envios": [{"correo": "info@shop.example", "ok": True}],
                "simulados": [],
            }), encoding="utf-8")
            lead = {
                "nombre": "Shop",
                "correo": "info@shop.example",
                "web": "https://shop.example",
                "telegram_notificado": True,
            }
            path = inbox / "shop.json"
            path.write_text(json.dumps(lead), encoding="utf-8")
            with patch.dict(os.environ, {"B2B_QUEUE_DIR": str(cola), "B2B_DATA_DIR": str(data)}):
                from b2b.despachador_tarjetas import _load, _save
                from b2b.telegram_gestion import token_callback

                tok = token_callback(lead)
                estado = _load()
                estado["abiertas"] = {tok: {"enviada_en": "2026-11-02T12:00:00+00:00", "inbox": str(path)}}
                _save(estado)
                lineas = reconciliar(cola)
                from b2b.despachador_tarjetas import _load as cargar

                self.assertIn(tok, (cargar().get("abiertas") or {}))
                self.assertTrue(any(l.startswith("Revisaría:") for l in lineas))
                lineas_aplicar = reconciliar(cola, aplicar=True)
                self.assertNotIn(tok, (cargar().get("abiertas") or {}))
            self.assertTrue(any("Cerré tarjeta" in l for l in lineas_aplicar))
            self.assertTrue(json.loads(path.read_text(encoding="utf-8")).get("telegram_notificado"))


class TestAtomico(unittest.TestCase):
    def test_replace_deja_json_valido(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "estado.json"
            escribir_json(path, {"a": 1})
            escribir_json(path, {"a": 2, "b": "ñ"})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["a"], 2)
            self.assertFalse(list(Path(tmp).glob("*.tmp.*")))
            self.assertFalse((Path(tmp) / "estado.json.lock").exists())


class TestRebote(unittest.TestCase):
    def test_mail_delivery_subsystem(self):
        cuerpo = "Final-Recipient: rfc822; info@executivecigarshop.com\nStatus: 5.1.1"
        self.assertEqual(
            correo_de_rebote("Mail Delivery Subsystem <mailer-daemon@googlemail.com>", "Delivery Status", cuerpo),
            "info@executivecigarshop.com",
        )
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"B2B_DATA_DIR": str(Path(tmp) / "data"), "B2B_QUEUE_DIR": str(Path(tmp))}):
                with patch("b2b.alertas_operador.alertar", return_value=True) as aviso:
                    canal = aplicar_rebote("info@executivecigarshop.com", {"telefono": "+13055550100", "nombre": "Exec"})
                self.assertEqual(canal, "whatsapp")
                self.assertTrue(aviso.called)
                from b2b.envio_correo import _load

                self.assertIn("info@executivecigarshop.com", _load()["invalidos"])


class TestRespaldo(unittest.TestCase):
    def test_retiene_14_dias(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            data.mkdir()
            (data / "envios_correo.json").write_text("{}", encoding="utf-8")
            ahora = datetime(2026, 11, 2, 3, 0)
            with patch.dict(os.environ, {"B2B_DATA_DIR": str(data), "B2B_QUEUE_DIR": str(Path(tmp))}):
                self.assertIsNotNone(respaldar_si_toca(ahora))
                viejo = Path(tmp) / "respaldos" / "2026-10-01"
                viejo.mkdir(parents=True)
                (viejo / "x.json").write_text("{}", encoding="utf-8")
                respaldar_si_toca(ahora)
                self.assertFalse(viejo.exists())
                self.assertTrue((Path(tmp) / "respaldos" / "2026-11-02" / "envios_correo.json").is_file())
        self.assertEqual(RETENCION_DIAS, 14)


class TestSalud(unittest.TestCase):
    def test_texto_y_avisos_sin_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            cola = Path(tmp)
            (cola / "inbox").mkdir()
            (cola / "inbox" / "a.json").write_text(json.dumps({
                "nombre": "A", "telegram_notificado": False,
            }), encoding="utf-8")
            data = cola / "data"
            data.mkdir()
            (data / "imap_bajas_estado.json").write_text(json.dumps({
                "ultimo_check": "2026-11-02T10:00:00+00:00",
            }), encoding="utf-8")
            ahora = datetime(2026, 11, 2, 16, 0, tzinfo=timezone.utc)
            with patch.dict(os.environ, {
                "B2B_QUEUE_DIR": str(cola),
                "B2B_DATA_DIR": str(data),
                "B2B_ENVIO_REAL": "1",
                "FUENTE_LEADS": "osm",
            }):
                texto = texto_salud(cola, ahora)
                self.assertIn("Cola inbox: 1", texto)
                self.assertIn("Última lectura IMAP", texto)
                claves = [c for c, _ in avisos_periodicos(cola, ahora)]
                self.assertIn("sin_tarjetas_3h", claves)
                self.assertIn("imap_sin_lectura_1h", claves)

    def test_noche_a_las_2(self):
        from datetime import datetime as dt

        local = dt(2026, 11, 2, 2, 5)
        self.assertTrue(toca_noche(local, ""))
        self.assertFalse(toca_noche(local, "2026-11-02"))


class TestCortafuegos(unittest.TestCase):
    def test_api_telegram_falla_el_test(self):
        import urllib.request

        from b2b.cortafuegos_tests import LlamadaRealProhibida

        with self.assertRaises(LlamadaRealProhibida):
            urllib.request.urlopen("https://api.telegram.org/botx/getMe", timeout=1)


class TestGetUpdates409(unittest.TestCase):
    def test_409_avisa_sin_abrir_socket_real(self):
        avisos = []

        def _cap(clave, texto, **_kw):
            avisos.append((clave, texto))
            return True

        def _abrir(*_a, **_k):
            raise urllib.error.HTTPError("https://api.telegram.org/botx/getUpdates", 409, "Conflict", {}, BytesIO(b""))

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"B2B_DATA_DIR": str(Path(tmp)), "B2B_QUEUE_DIR": str(Path(tmp))}):
                with patch("urllib.request.urlopen", side_effect=_abrir), patch(
                    "b2b.alertas_operador.alertar", side_effect=_cap
                ):
                    from b2b.telegram_control import procesar_comandos_chat

                    self.assertEqual(procesar_comandos_chat(TOKEN, CHAT_TARJETAS), [])
        self.assertEqual(avisos[0][0], "getupdates_409")


if __name__ == "__main__":
    unittest.main()
