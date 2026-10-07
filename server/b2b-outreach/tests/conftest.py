"""Aísla los tests del estado real (registro_leads, cola, logs) antes de importar b2b.*."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="cds-b2b-tests-"))
os.environ["B2B_QUEUE_DIR"] = str(_TMP / "cola")
for _var in ("B2B_DATA_DIR", "B2B_LOG_DIR", "B2B_SIMULADO"):
    os.environ.pop(_var, None)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
