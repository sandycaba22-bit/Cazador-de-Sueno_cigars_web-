from __future__ import annotations

import json

from b2b.paths import data_file


def cargar_paises_cola() -> list[dict]:
    path = data_file("paises_cola.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    zonas = data.get("zonas_orden") or []
    paises = list(data.get("paises") or [])
    orden_zona = {z: i for i, z in enumerate(zonas)}

    def key(row: dict) -> tuple:
        return (
            orden_zona.get(row.get("zona") or "resto", 99),
            int(row.get("prioridad") or 999),
            (row.get("pais") or "").lower(),
        )

    paises.sort(key=key)
    return paises


def entry_por_pais(nombre: str) -> dict | None:
    nom = (nombre or "").strip().lower()
    for row in cargar_paises_cola():
        if (row.get("pais") or "").strip().lower() == nom:
            return row
    return None
