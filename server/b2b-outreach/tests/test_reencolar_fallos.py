"""reencolar_fallos_telegram: reconstruye leads y dry-run por nombre."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import reencolar_fallos_telegram as script  # noqa: E402


class TestReencolarFallos(unittest.TestCase):
    def test_dry_run_reconstruye_desde_sent_cache_y_omite_contactados(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cola = root / "cola"
            data = root / "data"
            logs = root / "logs"
            for p in (cola / "sent", cola / "inbox", data, logs):
                p.mkdir(parents=True)
            (logs / "busqueda-20261022.jsonl").write_text(
                "\n".join([
                    json.dumps({
                        "evento": "telegram_prospecto_fallo",
                        "nombre": "Alpha Cigar Lounge",
                        "error": "BUTTON_URL_INVALID",
                    }),
                    json.dumps({
                        "evento": "telegram_prospecto_fallo",
                        "nombre": "Beta Smoke Shop",
                        "error": "BUTTON_URL_INVALID",
                    }),
                    json.dumps({
                        "evento": "telegram_prospecto_fallo",
                        "nombre": "Gamma Cigars",
                        "error": "BUTTON_URL_INVALID",
                    }),
                    json.dumps({
                        "evento": "telegram_prospecto_fallo",
                        "nombre": "Delta Missing Co",
                        "error": "BUTTON_URL_INVALID",
                    }),
                ]) + "\n",
                encoding="utf-8",
            )
            (cola / "sent" / "alpha.json").write_text(json.dumps({
                "nombre": "Alpha Cigar Lounge",
                "correo": "hello@alpha.example",
                "web": "https://alpha.example",
                "telegram_notificado": True,
            }), encoding="utf-8")
            (data / "envios_correo.json").write_text(json.dumps({
                "envios": [{
                    "correo": "info@beta.example",
                    "dominio": "beta.example",
                    "ok": True,
                    "cuando": "2026-10-22T12:00:00+00:00",
                }],
                "simulados": [],
            }), encoding="utf-8")
            (data / "leads_estado.json").write_text(json.dumps({
                "leads": {
                    "beta smoke shop|beta.example|info@beta.example": {
                        "nombre": "Beta Smoke Shop",
                        "correo": "info@beta.example",
                        "web": "https://beta.example",
                        "estado": "enviado",
                    }
                }
            }), encoding="utf-8")
            (data / "google_places_cache.json").write_text(json.dumps({
                "busquedas": {},
                "places": {
                    "places/ChIJgamma": {
                        "id": "places/ChIJgamma",
                        "displayName": {"text": "Gamma Cigars"},
                        "websiteUri": "https://gamma.example",
                        "nationalPhoneNumber": "+13055550123",
                        "formattedAddress": "Miami, FL",
                        "pais": "Florida",
                    }
                },
            }), encoding="utf-8")
            import io

            buf = io.StringIO()
            with patch.dict(os.environ, {
                "B2B_QUEUE_DIR": str(cola),
                "B2B_DATA_DIR": str(data),
                "B2B_LOG_DIR": str(logs),
            }), patch("sys.stdout", buf):
                code = script.main(["--dry-run"])
            self.assertEqual(code, 0)
            texto = buf.getvalue()
            self.assertIn("Reencolaría: Alpha Cigar Lounge ← sent", texto)
            self.assertIn("Omitido (ya_correo): Beta Smoke Shop", texto)
            self.assertIn("Reencolaría: Gamma Cigars ← google_places_cache", texto)
            self.assertIn("Omitido (sin_lead): Delta Missing Co", texto)
            self.assertIn("Total a reencolar: 2", texto)
            # dry-run no escribe inbox
            self.assertEqual(list((cola / "inbox").glob("*.json")), [])


if __name__ == "__main__":
    unittest.main()
