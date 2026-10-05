from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from b2b.paths import data_file

BUDGET_PATH = data_file("places_budget.json")


def max_calls() -> int:
    try:
        return max(1, int(os.getenv("MAX_PLACES_CALLS_DIA", "200") or "200"))
    except ValueError:
        return 200


def _load() -> dict:
    if not BUDGET_PATH.is_file():
        return {"fecha": date.today().isoformat(), "llamadas": 0}
    data = json.loads(BUDGET_PATH.read_text(encoding="utf-8"))
    if data.get("fecha") != date.today().isoformat():
        return {"fecha": date.today().isoformat(), "llamadas": 0}
    return data


def _save(data: dict) -> None:
    BUDGET_PATH.parent.mkdir(parents=True, exist_ok=True)
    BUDGET_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def puede_llamar() -> bool:
    return _load()["llamadas"] < max_calls()


def registrar_llamada(cantidad: int = 1) -> int:
    data = _load()
    data["llamadas"] = int(data.get("llamadas", 0)) + cantidad
    _save(data)
    return data["llamadas"]
