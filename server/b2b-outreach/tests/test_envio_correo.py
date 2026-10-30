"""Motor de correo: texto, topes, horario y simulado sin SMTP."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
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


def _smtp_ok():
    class _SMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def ehlo(self):
            pass

        def starttls(self, context=None):
            self.context = context

        def login(self, user, password):
            pass

        def send_message(self, msg):
            pass

    return _SMTP


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
        os.environ["B2B_ENVIO_REAL"] = "1"
        uno = elegir_cuenta(LUNES)
        self.assertEqual(uno["n"], 1)
        item = encolar_envio(_lead(), "tok1", ahora=LUNES)
        self.assertIsNotNone(item)
        with patch("smtplib.SMTP", _smtp_ok()), patch("b2b.envio_correo.random.randint", return_value=2):
            procesar_outbox(LUNES + timedelta(minutes=5))
        dos = elegir_cuenta(LUNES)
        self.assertEqual(dos["n"], 2)
        ok, motivo = puede_enviar_correo(_lead("ventas@primecigar.example"), LUNES)
        self.assertFalse(ok)
        self.assertIn("dominio", motivo)

    def test_rampa_semana_1_es_10(self):
        self.assertEqual(tope_rampa(LUNES), 10)

    def test_una_cuenta_no_se_lleva_toda_la_rampa(self):
        os.environ["CORREO_REMITENTE_2"] = ""
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
            procesar_outbox(LUNES + timedelta(minutes=5))
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

            def starttls(self, context=None):
                pass

            def login(self, user, password):
                raise smtplib.SMTPAuthenticationError(535, b"bad")

            def send_message(self, msg):
                raise AssertionError("no debía enviar")

        avisos = []
        with patch("smtplib.SMTP", _SMTP), patch("telegram_bot.enviar_texto_telegram", side_effect=avisos.append), patch(
            "b2b.envio_correo.random.randint", return_value=2
        ):
            procesar_outbox(LUNES + timedelta(minutes=5))
            procesar_outbox(LUNES + timedelta(minutes=5))
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

    def test_sin_clave_en_simulado_activa_y_motivos(self):
        from b2b.envio_correo import cuentas_activas

        os.environ["CORREO_CLAVE_1"] = ""
        os.environ["CORREO_CLAVE_2"] = ""
        os.environ["B2B_ENVIO_REAL"] = "0"
        self.assertEqual(len(cuentas_activas()), 2)
        ok, motivo = puede_enviar_correo(_lead("x@shop-sinclave.example"), LUNES)
        self.assertTrue(ok)
        os.environ["B2B_ENVIO_REAL"] = "1"
        self.assertEqual(cuentas_activas(), [])
        ok, motivo = puede_enviar_correo(_lead("y@shop-sinclave.example"), LUNES)
        self.assertFalse(ok)
        self.assertEqual(motivo, "sin cuenta de correo activa")
        self.assertNotIn("tope", motivo)

    def test_tope_solo_cuando_hay_cuentas_y_cupo_lleno(self):
        from b2b.envio_correo import _load, _save

        data = _load()
        for i in range(10):
            data["envios"].append({
                "correo": f"ya{i}@tienda{i}.example",
                "dominio": f"tienda{i}.example",
                "cuenta": 1 if i % 2 == 0 else 2,
                "dia": "2026-10-26",
                "ok": True,
                "cuando": LUNES.isoformat(),
            })
        _save(data)
        ok, motivo = puede_enviar_correo(_lead("nuevo@otra.example"), LUNES, solo_si_hay_cupo_hoy=True)
        self.assertFalse(ok)
        self.assertEqual(motivo, "tope diario de envío")

    def test_simulado_no_quema_lead(self):
        from b2b.envio_correo import _load
        from b2b.leads_store import estado_de_lead

        correo = "mismo@local.example"
        with patch("b2b.envio_correo.random.randint", return_value=2):
            self.assertIsNotNone(encolar_envio(_lead(correo), "tok-sim2", ahora=LUNES))
            procesar_outbox(LUNES + timedelta(minutes=5))
        data = _load()
        self.assertEqual(data["envios"], [])
        self.assertEqual(len(data["simulados"]), 1)
        self.assertEqual(estado_de_lead(_lead(correo)), "aprobado_simulado")
        ok, _motivo = puede_enviar_correo(_lead(correo), LUNES)
        self.assertTrue(ok)
        os.environ["B2B_ENVIO_REAL"] = "1"
        with patch("smtplib.SMTP", _smtp_ok()), patch("b2b.envio_correo.random.randint", return_value=2):
            self.assertIsNotNone(encolar_envio(_lead(correo), "tok-real", ahora=LUNES))
            self.assertEqual(procesar_outbox(LUNES + timedelta(minutes=5)), 1)
        self.assertEqual(len(_load()["envios"]), 1)

    def test_gmail_solo_bloquea_direccion_exacta(self):
        os.environ["B2B_ENVIO_REAL"] = "1"
        with patch("smtplib.SMTP", _smtp_ok()), patch("b2b.envio_correo.random.randint", return_value=2):
            encolar_envio(_lead("dueño@gmail.com", web="https://a.example"), "tok-g1", ahora=LUNES)
            procesar_outbox(LUNES + timedelta(minutes=5))
        ok, motivo = puede_enviar_correo(_lead("otro@gmail.com", web="https://b.example"), LUNES)
        self.assertTrue(ok, motivo)
        ok2, motivo2 = puede_enviar_correo(_lead("dueño@gmail.com", web="https://c.example"), LUNES)
        self.assertFalse(ok2)
        self.assertIn("correo", motivo2)

    def test_aprobar_15_con_rampa_10(self):
        from b2b.envio_correo import items_en_cola
        from b2b.zonas import ahora_local

        os.environ["B2B_ENVIO_REAL"] = "1"
        with patch("b2b.envio_correo.random.randint", return_value=2):
            for i in range(15):
                self.assertIsNotNone(
                    encolar_envio(
                        _lead(f"info{i}@shop{i}.example", web=f"https://shop{i}.example"),
                        f"tok{i}",
                        ahora=LUNES,
                    )
                )
        hoy = []
        manana = []
        for _path, item in items_en_cola():
            cuando = datetime.fromisoformat(item["enviar_despues_de"])
            local = ahora_local(cuando, "Florida")
            if local.date() == ahora_local(LUNES, "Florida").date():
                hoy.append(item)
            else:
                manana.append(item)
        self.assertEqual(len(hoy), 10)
        self.assertEqual(len(manana), 5)
        with patch("smtplib.SMTP", _smtp_ok()):
            hechos = procesar_outbox(LUNES + timedelta(hours=3))
        self.assertEqual(hechos, 10)
        cuentas = []
        archivo = Path(os.environ["B2B_QUEUE_DIR"]) / "outbox" / "archivo"
        for path in sorted(archivo.glob("*.json")):
            cuentas.append(json.loads(path.read_text(encoding="utf-8")).get("cuenta"))
        self.assertEqual(cuentas.count(1), 5)
        self.assertEqual(cuentas.count(2), 5)
        martes = LUNES + timedelta(days=1)
        for _path, item in items_en_cola():
            item["enviar_despues_de"] = martes.isoformat()
            _path.write_text(json.dumps(item), encoding="utf-8")
        with patch("smtplib.SMTP", _smtp_ok()):
            self.assertEqual(procesar_outbox(martes), 5)

    def test_cuerpo_editado_cambia_cuenta_al_enviar(self):
        from b2b.envio_correo import preparar_cuerpo

        lead = _lead(
            "edit@shop.example",
            cuerpo_editado=(
                "Hello team,\n\n"
                "Contact uno@gmail.com please.\n\n"
                "Cazador de Sueño Cigars SRL · Calle La Barranquita, Sector Las Minas, Calle 3, "
                "Edificio 3, Santiago de los Caballeros, Dominican Republic\n"
                "If you prefer not to receive further messages, reply STOP."
            ),
        )
        _asunto, cuerpo, _v = preparar_cuerpo(lead, "dos@gmail.com")
        self.assertIn("dos@gmail.com", cuerpo)
        self.assertNotIn("uno@gmail.com", cuerpo)
        self.assertIn("reply STOP", cuerpo)

    def test_smtp_usa_contexto_ssl(self):
        import ssl as _ssl

        os.environ["B2B_ENVIO_REAL"] = "1"
        seen = {}

        class _SMTP:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def ehlo(self):
                pass

            def starttls(self, context=None):
                seen["context"] = context

            def login(self, user, password):
                pass

            def send_message(self, msg):
                pass

        with patch("smtplib.SMTP", _SMTP), patch("b2b.envio_correo.random.randint", return_value=2):
            encolar_envio(_lead("ssl@shop.example"), "tok-ssl", ahora=LUNES)
            procesar_outbox(LUNES + timedelta(minutes=5))
        self.assertIsInstance(seen.get("context"), _ssl.SSLContext)

    def test_fallo_archiva_y_avisa_una_vez(self):
        os.environ["B2B_ENVIO_REAL"] = "1"
        encolar_envio(_lead("fallo@shop.example"), "tok-fallo", ahora=LUNES)
        avisos = []

        class _SMTP:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def ehlo(self):
                pass

            def starttls(self, context=None):
                pass

            def login(self, user, password):
                pass

            def send_message(self, msg):
                raise TimeoutError("smtp timeout")

        with patch("smtplib.SMTP", _SMTP), patch("telegram_bot.enviar_texto_telegram", side_effect=avisos.append), patch(
            "b2b.envio_correo.random.randint", return_value=2
        ):
            for i in range(3):
                procesar_outbox(LUNES + timedelta(minutes=5 + i * 30))
        archivo = Path(os.environ["B2B_QUEUE_DIR"]) / "outbox" / "archivo"
        self.assertTrue((archivo / "tok-fallo.json").is_file())
        self.assertEqual(len([a for a in avisos if "No pude enviar" in a]), 1)


if __name__ == "__main__":
    unittest.main()
