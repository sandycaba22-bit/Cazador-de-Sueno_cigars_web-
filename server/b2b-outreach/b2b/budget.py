from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path

from b2b.paths import state_file

# Parcheable en tests; None = state_file() en cada llamada (respeta --simulado).
BUDGET_PATH: Path | None = None

DEFAULT_DIA = 30
DEFAULT_MES = 900
DEFAULT_TANDA = 15
DEFAULT_TZ = "America/Santo_Domingo"
HORA_CORTE_TARDE = 12
TANDAS = ("manana", "tarde")


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
    """Tope diario canónico; los dos nombres anteriores siguen como respaldo deprecado."""
    return _entero_env(
        "GOOGLE_PLACES_MAX_CALLS_PER_DAY", "MAX_PLACES_CALLS_DIA", "B2B_GOOGLE_MAX_DIARIO",
        default=DEFAULT_DIA,
    )


def max_calls_mes() -> int:
    return _entero_env("GOOGLE_PLACES_MAX_CALLS_PER_MONTH", default=DEFAULT_MES)


def max_calls_tanda() -> int:
    """Tope por tanda (mañana / tarde); nunca mayor que el diario."""
    return min(_entero_env("GOOGLE_PLACES_MAX_CALLS_PER_RUN", default=DEFAULT_TANDA), max_calls())


def _ahora() -> datetime:
    nombre = os.getenv("B2B_TZ", "").strip() or DEFAULT_TZ
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(nombre))
    except Exception:
        return datetime.now()


def _hoy() -> date:
    return _ahora().date()


def tanda_actual() -> str:
    """'manana' antes de las 12:00 (hora de B2B_TZ), 'tarde' después."""
    return "manana" if _ahora().hour < HORA_CORTE_TARDE else "tarde"


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
        data["tandas"] = {}
    if data.get("mes") != hoy.strftime("%Y-%m"):
        data["mes"] = hoy.strftime("%Y-%m")
        data["llamadas_mes"] = 0
    data.setdefault("llamadas", 0)
    data.setdefault("llamadas_mes", 0)
    data.setdefault("tandas", {})
    data.setdefault("avisos", {})
    return data


def _save(data: dict) -> None:
    path = budget_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def motivo_bloqueo() -> str:
    """'' si se puede llamar; 'mensual', 'diario' o 'tanda' si se llegó al tope."""
    data = _load()
    if int(data["llamadas_mes"]) >= max_calls_mes():
        return "mensual"
    if int(data["llamadas"]) >= max_calls():
        return "diario"
    if int(data["tandas"].get(tanda_actual(), 0)) >= max_calls_tanda():
        return "tanda"
    return ""


def puede_llamar() -> bool:
    return not motivo_bloqueo()


def registrar_llamada(cantidad: int = 1) -> int:
    data = _load()
    tanda = tanda_actual()
    data["llamadas"] = int(data["llamadas"]) + cantidad
    data["llamadas_mes"] = int(data["llamadas_mes"]) + cantidad
    data["tandas"][tanda] = int(data["tandas"].get(tanda, 0)) + cantidad
    _save(data)
    return data["llamadas"]


def estado() -> dict:
    data = _load()
    tanda = tanda_actual()
    return {
        "dia": int(data["llamadas"]),
        "max_dia": max_calls(),
        "mes": int(data["llamadas_mes"]),
        "max_mes": max_calls_mes(),
        "tanda": tanda,
        "tanda_llamadas": int(data["tandas"].get(tanda, 0)),
        "max_tanda": max_calls_tanda(),
    }


def marcar_aviso(motivo: str) -> bool:
    """True la primera vez que se avisa de este motivo en su periodo (para no repetir en Telegram)."""
    data = _load()
    if motivo == "mensual":
        periodo = data["mes"]
    elif motivo == "tanda":
        periodo = f"{data['fecha']}:{tanda_actual()}"
    else:
        periodo = data["fecha"]
    if data["avisos"].get(motivo) == periodo:
        return False
    data["avisos"][motivo] = periodo
    _save(data)
    return True
