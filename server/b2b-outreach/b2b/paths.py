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


def queue_dir() -> Path | None:
    raw = os.getenv("B2B_QUEUE_DIR", "").strip()
    return Path(raw) if raw else None


def data_file(name: str) -> Path:
    """JSON de configuración versionado en el repo (country_rules, osm_iso, etc.)."""
    return DATA / name


def state_file(name: str) -> Path:
    """Datos que escribe el bot (registro leads, presupuesto Places)."""
    explicit = os.getenv("B2B_DATA_DIR", "").strip()
    if explicit:
        return Path(explicit) / name
    cola = queue_dir()
    if cola:
        return cola / "data" / name
    return DATA / name


def log_dir() -> Path:
    explicit = os.getenv("B2B_LOG_DIR", "").strip()
    if explicit:
        return Path(explicit)
    cola = queue_dir()
    if cola:
        return cola / "logs"
    return ROOT / "logs"
