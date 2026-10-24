from __future__ import annotations

from b2b.mercados import mercado_por_nombre, mercados_activos


def cargar_paises_cola() -> list[dict]:
    """Cola de búsqueda: solo mercados con activo=true, por prioridad."""
    return [
        {
            "pais": m["nombre"],
            "iso3166": m.get("iso3166") or "",
            "idioma": m.get("idioma") or "en",
            "prioridad": m.get("prioridad") or 999,
            "activo": True,
            "ciudades": list(m.get("ciudades") or []),
        }
        for m in mercados_activos()
    ]


def entry_por_pais(nombre: str) -> dict | None:
    m = mercado_por_nombre(nombre, solo_activos=True)
    if m is None:
        return None
    return {
        "pais": m["nombre"],
        "iso3166": m.get("iso3166") or "",
        "idioma": m.get("idioma") or "en",
        "prioridad": m.get("prioridad") or 999,
        "activo": True,
        "ciudades": list(m.get("ciudades") or []),
    }
