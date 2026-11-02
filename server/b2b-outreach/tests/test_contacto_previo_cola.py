"""No reabrir tarjetas ya contactadas; tanda mañana libera cupo; estado viejo compatible."""
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

from b2b.contacto_previo import motivo_ya_contactado, ya_contactado
from b2b.despachador_tarjetas import (
    _load,
    _save,
    abiertas_ahora,
    cerrar_tarjeta,
    despachar,
    sellar_tanda,
)
from b2b.telegram_gestion import token_callback

AHORA = datetime(2026, 11, 2, 13, 8, tzinfo=timezone.utc)  # 09:08 AST


class TestExecutiveCigarNoReabre(unittest.TestCase):
    """Caso real: correo 14:00 UTC y tarjeta reabierta 19:40 UTC → ya no debe pasar."""

    def test_omitir_si_esta_en_envios_correo(self):
        with tempfile.TemporaryDirectory() as tmp:
            cola = Path(tmp)
            data_dir = cola / "data"
            data_dir.mkdir()
            (data_dir / "envios_correo.json").write_text(
                json.dumps({
                    "envios": [{
                        "correo": "info@executivecigarshop.com",
                        "dominio": "executivecigarshop.com",
                        "ok": True,
                        "cuando": "2026-11-02T14:00:00+00:00",
                        "nombre": "Executive Cigar Shop",
                    }],
                    "simulados": [],
                }),
                encoding="utf-8",
            )
            inbox = cola / "inbox"
            inbox.mkdir()
            lead = {
                "nombre": "Executive Cigar Shop",
                "pais": "Florida",
                "correo": "info@executivecigarshop.com",
                "web": "https://executivecigarshop.com",
                "telefono": "+13055550100",
                "puntaje": 9,
                "telegram_notificado": False,
            }
            path = inbox / "exec.json"
            path.write_text(json.dumps(lead), encoding="utf-8")
            enviados = []

            def _enviar(l, _p, _path):
                enviados.append(l["nombre"])
                return True

            with patch.dict(os.environ, {
                "B2B_QUEUE_DIR": str(cola),
                "B2B_DATA_DIR": str(data_dir),
                "B2B_TARJETAS_ABIERTAS_MAX": "2",
                "B2B_TELEGRAM_MAX_POR_HORA": "100",
            }), patch("b2b.despachador_tarjetas.puede_enviar_telegram", return_value=True), patch(
                "b2b.contacto_previo.state_file", side_effect=lambda n: data_dir / n
            ):
                self.assertEqual(motivo_ya_contactado(lead), "ya_correo")
                self.assertEqual(despachar(cola, ahora=AHORA + timedelta(hours=5, minutes=40), enviar=_enviar), 0)
            self.assertEqual(enviados, [])
            guardado = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(guardado["telegram_notificado"])
            self.assertEqual(guardado.get("omitido_motivo"), "ya_correo")

    def test_cierre_tras_correo_en_cola_libera_cupo_manana(self):
        """Si el correo queda en cola SMTP, cerrar_tarjeta debe dejar pasar la tanda de las 9."""
        with tempfile.TemporaryDirectory() as tmp:
            cola = Path(tmp)
            data_dir = cola / "data"
            data_dir.mkdir()
            inbox = cola / "inbox"
            inbox.mkdir()
            with patch.dict(os.environ, {
                "B2B_QUEUE_DIR": str(cola),
                "B2B_DATA_DIR": str(data_dir),
                "B2B_TARJETAS_ABIERTAS_MAX": "1",
                "B2B_TELEGRAM_MAX_POR_HORA": "100",
            }), patch("b2b.despachador_tarjetas.puede_enviar_telegram", return_value=True):
                viejo = {
                    "nombre": "Executive Cigar Shop",
                    "pais": "Florida",
                    "correo": "info@executivecigarshop.com",
                    "web": "https://executivecigarshop.com",
                    "telefono": "+13055550100",
                    "telegram_notificado": True,
                    "puntaje": 8,
                }
                (inbox / "viejo.json").write_text(json.dumps(viejo), encoding="utf-8")
                tok = token_callback(viejo)
                estado = _load()
                estado["abiertas"] = {
                    tok: {
                        "enviada_en": (AHORA - timedelta(hours=5)).isoformat(),
                        "inbox": str(inbox / "viejo.json"),
                        "caducidad_veces": 0,
                    }
                }
                _save(estado)
                # Sin cerrar: la mañana no despacha (cupo 1 ocupado).
                nuevo = {
                    "nombre": "Morning Cigar Lounge",
                    "pais": "Florida",
                    "correo": "hello@morningcigar.example",
                    "web": "https://morningcigar.example",
                    "telefono": "+13055550999",
                    "telegram_notificado": False,
                    "puntaje": 9,
                }
                (inbox / "nuevo.json").write_text(json.dumps(nuevo), encoding="utf-8")
                enviados = []

                def _enviar(l, _p, _path):
                    enviados.append(l["nombre"])
                    return True

                self.assertEqual(despachar(cola, ahora=AHORA, enviar=_enviar), 0)
                # Tras "confirmar correo" se cierra el cupo → sale la de la mañana.
                cerrar_tarjeta(tok, ahora=AHORA, espera_seg=0)
                self.assertEqual(despachar(cola, ahora=AHORA, enviar=_enviar), 1)
                self.assertEqual(enviados, ["Morning Cigar Lounge"])


class TestTandaMananaResumen(unittest.TestCase):
    def test_sellar_deja_resumen_aunque_aun_no_despache(self):
        with tempfile.TemporaryDirectory() as tmp:
            cola = Path(tmp)
            inbox = cola / "inbox"
            inbox.mkdir()
            with patch.dict(os.environ, {
                "B2B_QUEUE_DIR": str(cola),
                "B2B_DATA_DIR": str(cola / "data"),
            }):
                for i in range(3):
                    (inbox / f"{i}.json").write_text(json.dumps({
                        "nombre": f"Shop {i}",
                        "pais": "Florida",
                        "telegram_notificado": False,
                        "correo": f"a{i}@x.example",
                        "web": f"https://x{i}.example",
                    }), encoding="utf-8")
                n = sellar_tanda(inbox, 15)
                self.assertEqual(n, 3)
                estado = _load()
                self.assertTrue(estado.get("resumenes"))
                bloque = next(iter(estado["resumenes"].values()))
                self.assertIn("Tanda", bloque["etiqueta"])
                self.assertEqual(bloque["total"], 3)
                self.assertEqual(bloque["objetivo"], 15)


class TestEstadoViejoCompatible(unittest.TestCase):
    def test_despachador_json_sin_estado_tarjeta(self):
        with tempfile.TemporaryDirectory() as tmp:
            cola = Path(tmp)
            with patch.dict(os.environ, {
                "B2B_QUEUE_DIR": str(cola),
                "B2B_DATA_DIR": str(cola / "data"),
            }):
                path = cola / "data" / "despachador_tarjetas.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                # Formato antiguo (sin campos nuevos).
                path.write_text(json.dumps({
                    "abiertas": {},
                    "al_final": [],
                    "pospuestos": {},
                    "forzar": 0,
                    "proxima_en": "",
                    "resumenes": {},
                }) + "\n", encoding="utf-8")
                self.assertEqual(abiertas_ahora(AHORA), {})
                data = _load()
                self.assertIn("abiertas", data)
                self.assertIn("resumenes", data)


class TestSeguimientoTambienCuenta(unittest.TestCase):
    def test_seguimiento_por_correo(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "seguimiento.json").write_text(json.dumps({
                "items": {
                    "executive|executivecigarshop.com": {
                        "correo": "info@executivecigarshop.com",
                        "canal": "correo",
                        "cuando": "2026-11-02T14:00:00+00:00",
                    }
                }
            }), encoding="utf-8")
            with patch("b2b.contacto_previo.state_file", side_effect=lambda n: data_dir / n):
                self.assertTrue(ya_contactado({
                    "correo": "info@executivecigarshop.com",
                    "web": "https://executivecigarshop.com",
                    "nombre": "Executive Cigar Shop",
                }))


if __name__ == "__main__":
    unittest.main()
