"""Cursor de consultas Google: cada tanda avanza a ciudad/consulta distintas."""
from __future__ import annotations

import json
from pathlib import Path

from b2b.paths import state_file


def _ruta() -> Path:
    return state_file("busqueda_cursor.json")


def _load() -> dict:
    path = _ruta()
    if not path.is_file():
        return {"paises": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"paises": {}}
    data.setdefault("paises", {})
    return data


def _save(data: dict) -> None:
    from b2b.io_atomico import escribir_json

    escribir_json(_ruta(), data)


def tomar_consultas(pais: str, todas: list, max_n: int) -> list:
    """Devuelve hasta max_n consultas y avanza el cursor (circular por país)."""
    if not todas or max_n <= 0:
        return []
    data = _load()
    bloque = dict(data["paises"].get(pais) or {})
    total = len(todas)
    # Si cambió el número de consultas (ciudades nuevas), reinicia el cursor.
    if int(bloque.get("total") or 0) != total:
        idx = 0
    else:
        idx = int(bloque.get("indice") or 0) % total
    out = []
    for i in range(min(max_n, total)):
        out.append(todas[(idx + i) % total])
    nuevo = (idx + len(out)) % total
    data["paises"][pais] = {
        "indice": nuevo,
        "total": total,
        "ultima_consulta": out[-1][2] if out else "",
        "pasadas": int(bloque.get("pasadas") or 0) + (1 if nuevo <= idx and len(out) else 0),
    }
    _save(data)
    return out


def indice_actual(pais: str) -> int:
    return int((_load().get("paises") or {}).get(pais, {}).get("indice") or 0)
