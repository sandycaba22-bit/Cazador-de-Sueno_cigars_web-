from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / "knowledge"
DATA = ROOT / "data"
FIXTURES = ROOT / "tests" / "fixtures"


def data_file(name: str) -> Path:
    return DATA / name
