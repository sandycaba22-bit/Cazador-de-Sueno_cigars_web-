"""Aísla los tests del estado real (registro_leads, cola, logs) antes de importar b2b.*."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="cds-b2b-tests-"))
os.environ["B2B_QUEUE_DIR"] = str(_TMP / "cola")
for _var in ("B2B_DATA_DIR", "B2B_LOG_DIR", "B2B_SIMULADO"):
    os.environ.pop(_var, None)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def sin_red_ni_credenciales_reales(monkeypatch):
    import telegram_bot

    original = telegram_bot.load_local_env

    def cargar_solo_env_de_prueba():
        if telegram_bot.HERE != ROOT:
            original()

    monkeypatch.setattr(telegram_bot, "load_local_env", cargar_solo_env_de_prueba)
    for nombre in ("GOOGLE_PLACES_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.setenv(nombre, "")
    # Los transportes simulados sustituyen esta barrera dentro de cada test.
    with patch("socket.socket.connect", side_effect=OSError("Red deshabilitada en tests")):
        yield
