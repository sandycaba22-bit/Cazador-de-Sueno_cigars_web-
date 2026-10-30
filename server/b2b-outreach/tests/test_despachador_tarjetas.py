"""Goteo: como máximo N tarjetas abiertas, y la siguiente espera 3–8 s."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from b2b.despachador_tarjetas import cerrar_tarjeta, despachar, posponer, ritmo_maximo, sellar_tanda, set_ritmo
from b2b.telegram_gestion import token_callback

AHORA = datetime(2026, 10, 29, 15, 0, tzinfo=timezone.utc)


def _escribir(inbox: Path, i: int, rating: float) -> Path:
    lead = {
        "nombre": f"Cigar Shop {i:02d}",
        "pais": "Florida",
        "web": f"https://shop{i}.example",
        "correo": f"info@shop{i}.example",
        "tipo": "tienda",
        "idioma": "en",
        "rating": rating,
        "user_rating_count": 10 + i,
        "telefono": "+13055550100",
        "telegram_notificado": False,
    }
    path = inbox / f"{i:02d}.json"
    path.write_text(json.dumps(lead), encoding="utf-8")
    return path


class TestDespachador(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cola = Path(self.tmp.name)
        self.inbox = self.cola / "inbox"
        self.inbox.mkdir()
        self.env = patch.dict(
            os.environ,
            {
                "B2B_QUEUE_DIR": str(self.cola),
                "B2B_DATA_DIR": str(self.cola / "data"),
                "B2B_TARJETAS_ABIERTAS_MAX": "2",
                "B2B_TELEGRAM_MAX_POR_HORA": "100",
            },
        )
        self.env.start()
        self.puede = patch("b2b.despachador_tarjetas.puede_enviar_telegram", return_value=True)
        self.puede.start()
        self.enviados: list[dict] = []

        def _enviar(lead, pais, path):
            lead = dict(lead)
            lead["_path"] = path
            self.enviados.append(lead)
            return True

        self.enviar = _enviar

    def tearDown(self):
        self.puede.stop()
        self.env.stop()
        self.tmp.cleanup()

    def test_salen_solo_dos_y_la_siguiente_espera(self):
        for i in range(15):
            _escribir(self.inbox, i, 5 - i / 100)
        sellar_tanda(self.inbox, 15)
        self.assertEqual(despachar(self.cola, ahora=AHORA, enviar=self.enviar), 2)
        self.assertEqual(len(self.enviados), 2)
        self.assertEqual(self.enviados[0]["numero_tarjeta"], 1)
        self.assertEqual(self.enviados[0]["tanda_total"], 15)
        self.assertIn("Tanda", self.enviados[0]["tanda_etiqueta"])
        tok = token_callback(self.enviados[0])
        cerrar_tarjeta(tok, ahora=AHORA, espera_seg=5)
        self.assertEqual(despachar(self.cola, ahora=AHORA + timedelta(seconds=2), enviar=self.enviar), 0)
        self.assertEqual(despachar(self.cola, ahora=AHORA + timedelta(seconds=5), enviar=self.enviar), 1)
        self.assertEqual(len(self.enviados), 3)

    def test_mas_tarde_va_al_final_y_ritmo_1(self):
        paths = [_escribir(self.inbox, i, 5 - i) for i in range(3)]
        sellar_tanda(self.inbox, 3)
        despachar(self.cola, ahora=AHORA, enviar=self.enviar)
        primero = self.enviados[0]
        self.assertEqual(posponer(token_callback(primero), primero["_path"], ahora=AHORA), "pospuesto")
        self.enviados.clear()
        despachar(self.cola, ahora=AHORA + timedelta(seconds=8), enviar=self.enviar)
        self.assertNotEqual(self.enviados[0]["nombre"], primero["nombre"])
        set_ritmo(1)
        self.assertEqual(ritmo_maximo(), 1)
        self.assertEqual(despachar(self.cola, ahora=AHORA + timedelta(seconds=20), enviar=self.enviar), 0)

    def test_caducada_se_reencola_una_vez_y_sin_envio_no_marca(self):
        path = _escribir(self.inbox, 1, 5)
        sellar_tanda(self.inbox, 1)
        os.environ["B2B_TARJETAS_ABIERTAS_MAX"] = "1"
        despachar(self.cola, ahora=AHORA, enviar=self.enviar)
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(data["telegram_notificado"])
        from b2b.despachador_tarjetas import _load, _save

        estado = _load()
        tok = next(iter(estado["abiertas"]))
        estado["abiertas"][tok]["enviada_en"] = (AHORA - timedelta(hours=49)).isoformat()
        _save(estado)
        antes = len(self.enviados)
        despachar(self.cola, ahora=AHORA, enviar=self.enviar)
        self.assertGreater(len(self.enviados), antes)
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["caducidad_veces"], 1)
        estado = _load()
        tok = next(iter(estado["abiertas"]))
        estado["abiertas"][tok]["enviada_en"] = (AHORA - timedelta(hours=49)).isoformat()
        _save(estado)
        antes = len(self.enviados)
        despachar(self.cola, ahora=AHORA, enviar=self.enviar)
        self.assertEqual(len(self.enviados), antes)
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(data["caducada_final"])

    def test_fallo_de_envio_no_marca_notificado(self):
        path = _escribir(self.inbox, 7, 4)

        def _no(_lead, _pais, _path):
            return False

        self.assertEqual(despachar(self.cola, ahora=AHORA, enviar=_no), 0)
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertFalse(data["telegram_notificado"])

    def test_ya_gestionado_al_frente_no_bloquea(self):
        import b2b.telegram_gestion as tg

        primero = _escribir(self.inbox, 1, 5.0)
        segundo = _escribir(self.inbox, 2, 4.9)
        lead1 = json.loads(primero.read_text(encoding="utf-8"))
        gest = self.cola / "data" / "gest.json"
        gest.parent.mkdir(parents=True, exist_ok=True)
        with patch.object(tg, "GESTION_PATH", gest):
            tg.marcar_gestionado_telegram(lead1, "descartado")
            sellar_tanda(self.inbox, 2)
            self.assertEqual(despachar(self.cola, ahora=AHORA, enviar=self.enviar), 1)
        self.assertEqual(self.enviados[0]["nombre"], "Cigar Shop 02")
        data1 = json.loads(primero.read_text(encoding="utf-8"))
        self.assertTrue(data1["telegram_notificado"])
        self.assertEqual(data1.get("omitido_motivo"), "omitido")
        data2 = json.loads(segundo.read_text(encoding="utf-8"))
        self.assertTrue(data2["telegram_notificado"])


if __name__ == "__main__":
    unittest.main()
