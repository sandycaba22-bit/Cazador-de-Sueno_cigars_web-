"""Motor de correo: texto, topes, horario y simulado sin SMTP."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from b2b.envio_correo import (
    construir_mensaje,
    encolar_envio,
    elegir_cuenta,
    envio_real,
    puede_enviar_correo,
    procesar_outbox,
    tope_rampa,
)
from b2b.redactor import WHOLESALE_URL, asunto_con_tope, direccion_postal, pie_correo
from b2b.telegram_gestion import agregar_no_contactar
from b2b.zonas import en_horario_laboral, siguiente_habil

DIR = "Calle La Barranquita, Sector Las Minas, Calle 3, Edificio 3, Santiago de los Caballeros, República Dominicana"
LUNES = datetime(2026, 10, 26, 15, 0, tzinfo=timezone.utc)  # 11:00 EDT
DOMINGO = datetime(2026, 10, 25, 16, 0, tzinfo=timezone.utc)


def _lead(correo="info@primecigar.example", **extra):
    base = {
        "nombre": "Prime Cigar",
        "correo": correo,
        "web": "https://primecigar.example",
        "idioma": "en",
        "tipo": "lounge",
        "pais": "Florida",
        "estado": "Florida",
        "asunto_variante": "A",
    }
    base.update(extra)
    return base


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._env = patch.dict(
            os.environ,
            {
                "B2B_QUEUE_DIR": self.tmp.name,
                "B2B_DATA_DIR": str(Path(self.tmp.name) / "data"),
                "B2B_ENVIO_REAL": "0",
                "EMPRESA_DIRECCION_POSTAL": DIR,
                "EMPRESA_DIRECCION_POSTAL_EN": "",
                "CORREO_REMITENTE_1": "uno@gmail.com",
                "CORREO_CLAVE_1": "clave-1",
                "CORREO_REMITENTE_2": "dos@gmail.com",
                "CORREO_CLAVE_2": "clave-2",
                "B2B_ENVIO_RAMPA": "10,20,30",
                "B2B_ENVIO_FECHA_INICIO": "2026-10-26",
                "B2B_ENVIO_MAX_POR_CUENTA": "15",
                "B2B_ENVIO_PAUSA_MIN": "2",
                "B2B_ENVIO_PAUSA_MAX": "2",
                "B2B_ENVIO_HORA_INICIO": "9",
                "B2B_ENVIO_HORA_FIN": "17",
            },
            clear=False,
        )
        self._env.start()
        self._pausa = patch("b2b.telegram_control.esta_pausado", return_value=False)
        self._pausa.start()

    def tearDown(self):
        self._pausa.stop()
        self._env.stop()
        self.tmp.cleanup()


class TestMensaje(unittest.TestCase):
    def test_texto_plano_un_enlace_y_baja(self):
        with patch.dict(os.environ, {"EMPRESA_DIRECCION_POSTAL": DIR, "EMPRESA_DIRECCION_POSTAL_EN": ""}):
            from b2b.redactor import cuerpo_sin_asunto

            cuerpo = cuerpo_sin_asunto("Prime Cigar", "en", "lounge", cuenta="uno@gmail.com")
            self.assertIn("Dominican Republic", cuerpo)
            self.assertNotIn("República Dominicana", cuerpo)
            self.assertIn("reply STOP", cuerpo)
            self.assertNotIn("responda BAJA", cuerpo)
            self.assertEqual(cuerpo.count("https://"), 1)
            self.assertIn(WHOLESALE_URL, cuerpo)
            msg = construir_mensaje(_lead(), "uno@gmail.com", cuerpo, "Handmade Dominican cigars for Prime Cigar")
        self.assertIsInstance(msg, EmailMessage)
        self.assertEqual(msg.get_content_type(), "text/plain")
        self.assertIn("mailto:uno@gmail.com?subject=BAJA", msg["List-Unsubscribe"])
        self.assertTrue(msg["Message-ID"])
        self.assertEqual(msg["Reply-To"], "uno@gmail.com")
        self.assertEqual(list(msg.iter_attachments()), [])

    def test_pie_en_espanol_no_mezcla_el_ingles(self):
        with patch.dict(os.environ, {"EMPRESA_DIRECCION_POSTAL": DIR, "EMPRESA_DIRECCION_POSTAL_EN": ""}):
            pie = pie_correo("es")
            self.assertIn("República Dominicana", pie)
            self.assertIn("responda BAJA", pie)
            self.assertNotIn("reply STOP", pie)
            self.assertIn("Dominican Republic", direccion_postal("en"))

    def test_asunto_no_pasa_de_70(self):
        largo = "Prime Cigar & Whiskey Bar of the Downtown"
        asunto = asunto_con_tope("Dominican boutique cigars — wholesale sample for {nombre}", largo)
        self.assertLessEqual(len(asunto), 70)
        self.assertIn("…", asunto)
        self.assertTrue(asunto.startswith("Dominican boutique cigars — wholesale sample for "))

    def test_sin_direccion_no_envia(self):
        with patch.dict(os.environ, {"EMPRESA_DIRECCION_POSTAL": "", "B2B_QUEUE_DIR": tempfile.mkdtemp(), "B2B_DATA_DIR": tempfile.mkdtemp()}):
            ok, motivo = puede_enviar_correo(_lead(), LUNES)
        self.assertFalse(ok)
        self.assertIn("dirección", motivo)


class TestTopes(_Base):
    def test_alterna_cuentas_y_no_repite_dominio(self):
        uno = elegir_cuenta(LUNES)
        self.assertEqual(uno["n"], 1)
        item = encolar_envio(_lead(), "tok1", ahora=LUNES)
        self.assertIsNotNone(item)
        with patch("b2b.envio_correo.random.randint", return_value=2):
            procesar_outbox(LUNES + __import__("datetime").timedelta(minutes=5))
        dos = elegir_cuenta(LUNES)
        self.assertEqual(dos["n"], 2)
        ok, motivo = puede_enviar_correo(_lead("ventas@primecigar.example"), LUNES)
        self.assertFalse(ok)
        self.assertIn("dominio", motivo)

    def test_rampa_semana_1_es_10(self):
        self.assertEqual(tope_rampa(LUNES), 10)

    def test_una_cuenta_no_se_lleva_toda_la_rampa(self):
        os.environ["CORREO_CLAVE_2"] = ""
        os.environ["B2B_ENVIO_RAMPA"] = "30,30,30"
        os.environ["B2B_ENVIO_FECHA_INICIO"] = "2026-09-01"
        os.environ["B2B_ENVIO_MAX_POR_CUENTA"] = "15"
        cuenta = elegir_cuenta(LUNES)
        self.assertEqual(cuenta["n"], 1)
        from b2b.envio_correo import _cupo_cuenta, cuentas_activas

        activas = cuentas_activas()
        self.assertEqual(len(activas), 1)
        self.assertEqual(_cupo_cuenta(1, activas, LUNES), 15)

    def test_no_contactar(self):
        agregar_no_contactar("Prime Cigar", "https://primecigar.example", "test")
        ok, motivo = puede_enviar_correo(_lead(), LUNES)
        self.assertFalse(ok)
        self.assertIn("no contactar", motivo)

    def test_simulado_no_abre_smtp(self):
        with patch("b2b.envio_correo.random.randint", return_value=2):
            self.assertIsNotNone(encolar_envio(_lead("otro@tienda.example"), "tok-sim", ahora=LUNES))
        with patch("smtplib.SMTP") as smtp:
            self.assertFalse(envio_real())
            procesar_outbox(LUNES + __import__("datetime").timedelta(minutes=5))
        smtp.assert_not_called()
        eml = list(Path(os.environ["B2B_DATA_DIR"]).glob("outbox_simulado/*.eml"))
        self.assertEqual(len(eml), 1)

    def test_auth_pausa_solo_esa_cuenta(self):
        import smtplib

        os.environ["B2B_ENVIO_REAL"] = "1"
        encolar_envio(_lead("a@shop-auth.example"), "tok-auth", ahora=LUNES)

        class _SMTP:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def ehlo(self):
                pass

            def starttls(self):
                pass

            def login(self, user, password):
                raise smtplib.SMTPAuthenticationError(535, b"bad")

            def send_message(self, msg):
                raise AssertionError("no debía enviar")

        avisos = []
        with patch("smtplib.SMTP", _SMTP), patch("telegram_bot.enviar_texto_telegram", side_effect=avisos.append), patch(
            "b2b.envio_correo.random.randint", return_value=2
        ):
            procesar_outbox(LUNES + __import__("datetime").timedelta(minutes=5))
            procesar_outbox(LUNES + __import__("datetime").timedelta(minutes=5))
        from b2b.envio_correo import _load

        self.assertIn("1", _load()["pausadas"])
        self.assertEqual(sum(1 for t in avisos if "cuenta 1" in t), 1)

    def test_domingo_pasa_al_lunes(self):
        encolar_envio(_lead("b@domingo.example"), "tok-dom", ahora=LUNES)
        carpeta = Path(os.environ["B2B_QUEUE_DIR"]) / "outbox"
        path = next(carpeta.glob("*.json"))
        item = json.loads(path.read_text(encoding="utf-8"))
        item["enviar_despues_de"] = DOMINGO.isoformat()
        path.write_text(json.dumps(item), encoding="utf-8")
        procesar_outbox(DOMINGO)
        item = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(item["estado"], "en_cola")
        self.assertFalse(en_horario_laboral(DOMINGO, "Florida", 9, 17))
        nuevo = datetime.fromisoformat(item["enviar_despues_de"])
        self.assertEqual(siguiente_habil(DOMINGO, "Florida", 9, 17).hour, 9)
        self.assertEqual(nuevo.astimezone(siguiente_habil(DOMINGO, "Florida").tzinfo).weekday(), 0)


if __name__ == "__main__":
    unittest.main()
