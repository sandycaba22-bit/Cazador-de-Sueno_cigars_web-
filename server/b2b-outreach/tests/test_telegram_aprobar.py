"""Aprobar encola un solo correo, cancelar lo saca, y un correo manual activa el botón."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import b2b.leads_store as ls
import b2b.telegram_control as tc
import b2b.telegram_gestion as tg
from b2b.telegram_prospecto import teclado_prospecto

DIR = "Calle La Barranquita, Sector Las Minas, Calle 3, Edificio 3, Santiago de los Caballeros, República Dominicana"


def _lead(**extra):
    base = {
        "nombre": "Prime Cigar",
        "web": "https://primecigar.example",
        "correo": "info@primecigar.example",
        "telefono": "+13055550100",
        "pais": "Florida",
        "estado": "Florida",
        "tipo": "lounge",
        "idioma": "en",
        "direccion": "Miami, FL",
        "texto_tarjeta": "Tarjeta 1 de 1\n🏪 Prime Cigar",
    }
    base.update(extra)
    return base


class TestAprobar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        raiz = Path(self.tmp.name)
        self.env = patch.dict(
            os.environ,
            {
                "B2B_QUEUE_DIR": str(raiz),
                "B2B_DATA_DIR": str(raiz / "data"),
                "B2B_ENVIO_REAL": "0",
                "EMPRESA_DIRECCION_POSTAL": DIR,
                "CORREO_REMITENTE_1": "uno@gmail.com",
                "CORREO_CLAVE_1": "x",
                "CORREO_REMITENTE_2": "",
                "CORREO_CLAVE_2": "",
                "B2B_ENVIO_FECHA_INICIO": "2026-10-26",
                "B2B_ENVIO_RAMPA": "10,20,30",
                "B2B_ENVIO_PAUSA_MIN": "2",
                "B2B_ENVIO_PAUSA_MAX": "2",
            },
        )
        self.env.start()
        self.patches = [
            patch.object(ls, "NO_CONTACT_STATE_PATH", raiz / "nc.json"),
            patch.object(tg, "GESTION_PATH", raiz / "gest.json"),
            patch.object(tg, "PENDIENTES_PATH", raiz / "pend.json"),
            patch.object(tc, "_telegram_post", return_value={"ok": True}),
            patch("b2b.despachador_tarjetas.puede_enviar_telegram", return_value=True),
        ]
        for p in self.patches:
            p.start()
        self.lead = _lead()
        self.tok = tg.token_callback(self.lead)
        tg.registrar_pendiente(self.tok, self.lead, str(raiz / "inbox" / "a.json"))

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.env.stop()
        self.tmp.cleanup()

    def _cb(self, data):
        return {
            "id": "cb1",
            "data": data,
            "message": {"message_id": 9, "chat": {"id": 42}},
        }

    def test_aprobar_dos_veces_es_un_solo_correo(self):
        tc._manejar_callback("t", "42", self._cb(f"b2bs:{self.tok}"))
        tc._manejar_callback("t", "42", self._cb(f"b2bs:{self.tok}"))
        cola = list(Path(os.environ["B2B_QUEUE_DIR"]).glob("outbox/*.json"))
        self.assertEqual(len(cola), 1)

    def test_cancelar_saca_el_correo(self):
        tc._manejar_callback("t", "42", self._cb(f"b2bs:{self.tok}"))
        tc._manejar_callback("t", "42", self._cb(f"b2bx:{self.tok}"))
        self.assertEqual(list(Path(os.environ["B2B_QUEUE_DIR"]).glob("outbox/*.json")), [])

    def test_responder_con_correo_activa_el_boton(self):
        lead = _lead(nombre="Local Sin Correo", correo="", fuente_correo="", web="https://sincorrreo.example")
        tok = tg.token_callback(lead)
        tg.registrar_pendiente(tok, {**lead, "message_id": 15, "texto_tarjeta": "Tarjeta\nSin correo público"})
        textos = [b["text"] for fila in teclado_prospecto(lead, "Florida", tok)["inline_keyboard"] for b in fila]
        self.assertNotIn("✅ Aprobar y enviar correo", textos)
        ack = tc._manejar_respuesta("t", "42", 15, "ventas@primecigar.example")
        self.assertIn("ventas@primecigar.example", ack)
        guardado = tg.resolver_pendiente(tok)
        self.assertEqual(guardado["fuente_correo"], "manual_telegram")
        textos = [
            b["text"]
            for fila in teclado_prospecto(guardado, "Florida", tok)["inline_keyboard"]
            for b in fila
        ]
        self.assertIn("✅ Aprobar y enviar correo", textos)

    def test_pendiente_guarda_el_lead_y_caduca_a_las_48h(self):
        guardado = tg.resolver_pendiente(self.tok)
        for campo in ("nombre", "correo", "telefono", "web", "tipo", "idioma", "creado_en"):
            self.assertIn(campo, guardado)
        self.assertEqual(guardado["correo"], "info@primecigar.example")
        tg.actualizar_pendiente(
            self.tok,
            creado_en=(datetime.now(timezone.utc) - timedelta(hours=49)).isoformat(),
        )
        self.assertIsNone(tg.resolver_pendiente(self.tok))

    def test_editar_agrega_la_baja_si_falta(self):
        tg.actualizar_pendiente(self.tok, message_id=9, espera="cuerpo", idioma="en")
        tc._manejar_respuesta("t", "42", 9, "Hello team, we can talk tomorrow.")
        cuerpo = tg.resolver_pendiente(self.tok)["cuerpo"]
        self.assertIn("reply STOP", cuerpo)
        self.assertIn("Dominican Republic", cuerpo)


if __name__ == "__main__":
    unittest.main()
