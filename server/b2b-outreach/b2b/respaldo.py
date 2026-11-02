"""Copia diaria de data/ (14 días) y rotación de logs viejos."""
from __future__ import annotations

import shutil
from datetime import datetime, timedelta
from pathlib import Path

from b2b.paths import log_dir, state_file

RETENCION_DIAS = 14


def _raiz_data() -> Path:
    return state_file("x").parent


def _raiz_respaldos() -> Path:
    cola = _raiz_data().parent
    return cola / "respaldos"


def respaldar_si_toca(ahora: datetime | None = None) -> Path | None:
    ahora = ahora or datetime.now()
    dia = ahora.strftime("%Y-%m-%d")
    dest_root = _raiz_respaldos()
    dest = dest_root / dia
    marca = dest_root / f".hecho-{dia}"
    if marca.is_file():
        _purgar(dest_root, ahora)
        return None
    origen = _raiz_data()
    if not origen.is_dir():
        return None
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    for path in origen.glob("*.json"):
        shutil.copy2(path, dest / path.name)
    marca.write_text(dia, encoding="utf-8")
    _purgar(dest_root, ahora)
    _rotar_logs(ahora)
    return dest


def _purgar(dest_root: Path, ahora: datetime) -> None:
    limite = (ahora - timedelta(days=RETENCION_DIAS)).date()
    if not dest_root.is_dir():
        return
    for path in dest_root.iterdir():
        if not path.is_dir():
            continue
        try:
            dia = datetime.strptime(path.name, "%Y-%m-%d").date()
        except ValueError:
            continue
        if dia < limite:
            shutil.rmtree(path, ignore_errors=True)
            marca = dest_root / f".hecho-{path.name}"
            if marca.is_file():
                marca.unlink()


def _rotar_logs(ahora: datetime) -> None:
    from b2b.logging_ops import _limpiar_viejos

    dest = log_dir()
    dest.mkdir(parents=True, exist_ok=True)
    _limpiar_viejos(dest)
