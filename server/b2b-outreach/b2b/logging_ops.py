from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from b2b.paths import log_dir
TOKEN_RE = re.compile(r"\d{6,}:[A-Za-z0-9_-]{20,}")
_MAX_LOG_BYTES = 2_000_000
_DIAS_CONSERVAR = 14


def _sanitizar(texto: str) -> str:
    return TOKEN_RE.sub("[token]", str(texto))[:500]


def _rotar_si_hace_falta(path: Path) -> None:
    try:
        if path.is_file() and path.stat().st_size >= _MAX_LOG_BYTES:
            stamp = datetime.now().strftime("%H%M%S")
            path.rename(path.with_name(f"{path.stem}-{stamp}{path.suffix}"))
    except OSError:
        pass


def _limpiar_viejos(dest: Path) -> None:
    limite = datetime.now() - timedelta(days=_DIAS_CONSERVAR)
    for path in dest.glob("busqueda-*.jsonl"):
        try:
            if datetime.fromtimestamp(path.stat().st_mtime) < limite:
                path.unlink()
        except OSError:
            continue


def registrar_evento(evento: dict) -> Path:
    dest = log_dir()
    dest.mkdir(parents=True, exist_ok=True)
    dia = datetime.now().strftime("%Y%m%d")
    path = dest / f"busqueda-{dia}.jsonl"
    _rotar_si_hace_falta(path)
    if "ts" not in evento:
        evento = {**evento, "ts": datetime.now().isoformat(timespec="seconds")}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(evento, ensure_ascii=False) + "\n")
    # Limpieza ocasional (barata): cada ~50 eventos del día no; al escribir basta a veces.
    if path.stat().st_size < 800:
        _limpiar_viejos(dest)
    return path


def registrar_presupuesto_agotado() -> Path:
    return registrar_evento(
        {
            "evento": "presupuesto_places_agotado",
            "mensaje": "Tope diario MAX_PLACES_CALLS_DIA alcanzado; búsqueda detenida.",
        }
    )


def registrar_osm_fallo(pais: str, mensaje: str) -> Path:
    return registrar_evento(
        {
            "evento": "osm_fallo",
            "pais": _sanitizar(pais),
            "mensaje": _sanitizar(mensaje),
        }
    )


def registrar_busqueda(
    pais: str,
    llamadas_api: int,
    prospectos_nuevos: int,
    simulado: bool,
    fuente: str = "",
) -> Path:
    payload: dict = {
        "evento": "busqueda_pais",
        "pais": _sanitizar(pais),
        "llamadas_api": llamadas_api,
        "prospectos_nuevos": prospectos_nuevos,
        "modo": "simulado" if simulado else "live",
    }
    if fuente:
        payload["fuente"] = fuente
    return registrar_evento(payload)
