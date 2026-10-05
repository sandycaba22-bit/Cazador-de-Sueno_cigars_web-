from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from b2b.paths import ROOT

LOG_DIR = ROOT / "logs"
TOKEN_RE = re.compile(r"\d{6,}:[A-Za-z0-9_-]{20,}")


def _sanitizar(texto: str) -> str:
    return TOKEN_RE.sub("[token]", str(texto))[:500]


def registrar_busqueda(
    pais: str,
    llamadas_api: int,
    prospectos_nuevos: int,
    simulado: bool,
) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    dia = datetime.now().strftime("%Y%m%d")
    path = LOG_DIR / f"busqueda-{dia}.jsonl"
    evento = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "pais": _sanitizar(pais),
        "llamadas_api": llamadas_api,
        "prospectos_nuevos": prospectos_nuevos,
        "modo": "simulado" if simulado else "live",
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(evento, ensure_ascii=False) + "\n")
    return path
