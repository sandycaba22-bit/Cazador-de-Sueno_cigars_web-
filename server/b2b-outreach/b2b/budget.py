from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from b2b.paths import state_file

# Parcheable en tests; None = state_file() en cada llamada (respeta --simulado).
BUDGET_PATH: Path | None = None

DEFAULT_DIA = 30
DEFAULT_MES = 900


def budget_path() -> Path:
    return BUDGET_PATH or state_file("places_budget.json")


def _entero_env(*nombres: str, default: int) -> int:
    for nombre in nombres:
        raw = os.getenv(nombre, "").strip()
        if raw:
            try:
                return max(1, int(raw))
            except ValueError:
                continue
    return default


def max_calls() -> int:
    """Tope diario (GOOGLE_PLACES_MAX_CALLS_PER_DAY; MAX_PLACES_CALLS_DIA es el nombre viejo)."""
    return _entero_env("GOOGLE_PLACES_MAX_CALLS_PER_DAY", "MAX_PLACES_CALLS_DIA", default=DEFAULT_DIA)


def max_calls_mes() -> int:
    return _entero_env("GOOGLE_PLACES_MAX_CALLS_PER_MONTH", default=DEFAULT_MES)


def _hoy() -> date:
    return date.today()


def _load() -> dict:
    hoy = _hoy()
    data: dict = {}
    path = budget_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    if data.get("fecha") != hoy.isoformat():
        data["fecha"] = hoy.isoformat()
        data["llamadas"] = 0
    if data.get("mes") != hoy.strftime("%Y-%m"):
        data["mes"] = hoy.strftime("%Y-%m")
        data["llamadas_mes"] = 0
    data.setdefault("llamadas", 0)
    data.setdefault("llamadas_mes", 0)
    data.setdefault("avisos", {})
    return data


def _save(data: dict) -> None:
    path = budget_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def motivo_bloqueo() -> str:
    """'' si se puede llamar; 'mensual' o 'diario' si se llegó al tope."""
    data = _load()
    if int(data["llamadas_mes"]) >= max_calls_mes():
        return "mensual"
    if int(data["llamadas"]) >= max_calls():
        return "diario"
    return ""


def puede_llamar() -> bool:
    return not motivo_bloqueo()


def registrar_llamada(cantidad: int = 1) -> int:
    data = _load()
    data["llamadas"] = int(data["llamadas"]) + cantidad
    data["llamadas_mes"] = int(data["llamadas_mes"]) + cantidad
    _save(data)
    return data["llamadas"]


def estado() -> dict:
    data = _load()
    return {
        "dia": int(data["llamadas"]),
        "max_dia": max_calls(),
        "mes": int(data["llamadas_mes"]),
        "max_mes": max_calls_mes(),
    }


def marcar_aviso(motivo: str) -> bool:
    """True la primera vez que se avisa del tope en este día/mes (para no repetir en Telegram)."""
    data = _load()
    periodo = data["mes"] if motivo == "mensual" else data["fecha"]
    if data["avisos"].get(motivo) == periodo:
        return False
    data["avisos"][motivo] = periodo
    _save(data)
    return True
