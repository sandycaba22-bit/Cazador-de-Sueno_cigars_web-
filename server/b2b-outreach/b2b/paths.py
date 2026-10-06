from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Dominio canónico (sitio en producción). No usar subdominios GoDaddy ni cazadordesuenocigars.com.
SITE_CANONICAL = "https://www.cazadordesuenocigar.com"
WHOLESALE_URL = f"{SITE_CANONICAL}/wholesale.html"
CATALOGO_PDF_BASE = f"{SITE_CANONICAL}/catalogo"

KNOWLEDGE = ROOT / "knowledge"
DATA = ROOT / "data"
FIXTURES = ROOT / "tests" / "fixtures"


def data_file(name: str) -> Path:
    return DATA / name
