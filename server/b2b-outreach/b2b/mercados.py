from __future__ import annotations

import json
from pathlib import Path

from b2b.paths import ROOT, state_file

MERCADOS_PATH = ROOT / "config" / "mercados.json"


def _cargar_archivo() -> dict:
    return json.loads(MERCADOS_PATH.read_text(encoding="utf-8"))


def cargar_mercados(*, solo_activos: bool = False) -> list[dict]:
    filas = list((_cargar_archivo().get("mercados") or []))
    if solo_activos:
        filas = [m for m in filas if m.get("activo") is True]
    filas.sort(key=lambda m: (int(m.get("prioridad") or 999), (m.get("nombre") or "").lower()))
    return filas


def mercados_activos() -> list[dict]:
    """Mercados a buscar. Lo inactivo no entra en consultas ni en el cursor."""
    return cargar_mercados(solo_activos=True)


def mercado_por_nombre(nombre: str, *, solo_activos: bool = True) -> dict | None:
    clave = (nombre or "").strip().casefold()
    if not clave:
        return None
    for row in cargar_mercados(solo_activos=solo_activos):
        if (row.get("nombre") or "").strip().casefold() == clave:
            return row
        if (row.get("id") or "").strip().casefold() == clave:
            return row
    return None


def mercado_activo(nombre: str) -> bool:
    return mercado_por_nombre(nombre, solo_activos=True) is not None


def nombres_activos() -> list[str]:
    return [m["nombre"] for m in mercados_activos() if m.get("nombre")]


def como_reglas(mercado: dict) -> dict:
    """Forma compatible con country_rules / prospector (`pais`, `idiomas`)."""
    idioma = mercado.get("idioma") or "en"
    return {
        "pais": mercado.get("nombre") or "",
        "idiomas": [idioma],
        "idioma": idioma,
        "iso3166": mercado.get("iso3166") or "",
        "ciudades": list(mercado.get("ciudades") or []),
        "territorio": "Estados Unidos" if (mercado.get("iso3166") or "") == "US" else "",
        "prioridad": mercado.get("prioridad"),
        "activo": mercado.get("activo") is True,
        "id": mercado.get("id") or "",
    }


def siguiente_mercado(nombre: str | None) -> dict | None:
    activos = mercados_activos()
    if not activos:
        return None
    if not nombre:
        return activos[0]
    for i, row in enumerate(activos):
        if (row.get("nombre") or "") == nombre:
            return activos[(i + 1) % len(activos)]
    return activos[0]


def cursor_path() -> Path:
    return state_file("busqueda_cursor.json")


def cargar_cursor() -> dict:
    path = cursor_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {"mercado": "", "consulta_idx": 0}


def guardar_cursor(mercado: str, consulta_idx: int) -> None:
    path = cursor_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"mercado": mercado or "", "consulta_idx": max(0, int(consulta_idx))}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def resolver_cursor() -> tuple[dict, int]:
    """Mercado activo actual y el índice de la siguiente consulta."""
    estado = cargar_cursor()
    actuales = mercados_activos()
    if not actuales:
        raise ValueError("No hay mercados activos en config/mercados.json")
    nombre = (estado.get("mercado") or "").strip()
    idx = int(estado.get("consulta_idx") or 0)
    actual = mercado_por_nombre(nombre, solo_activos=True) if nombre else None
    if actual is None:
        actual = actuales[0]
        idx = 0
        guardar_cursor(actual["nombre"], 0)
    return actual, idx
