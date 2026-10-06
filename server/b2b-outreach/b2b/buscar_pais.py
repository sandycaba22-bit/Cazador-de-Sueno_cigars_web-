from __future__ import annotations

from pathlib import Path

from b2b.buscar_filtros import dedupe_y_fusionar
from b2b.fuentes.dealers import buscar_dealers_pais
from b2b.fuentes.directorios import buscar_directorios_pais
from b2b.logging_ops import registrar_evento
from b2b.osm_places import OsmIslaFallida, buscar_en_pais_osm


def recolectar_leads_pais(
    pais: str,
    tipos: list[str],
    limite: int,
    tipo_filtro: str = "",
    simulado: bool = False,
) -> tuple[list[dict], int, dict]:
    """OSM + dealers + directorios (gratis). Devuelve leads, llamadas OSM, stats."""
    stats: dict = {
        "osm": 0,
        "dealers": 0,
        "directorio": 0,
        "osm_raw": {},
        "dealers_saltadas": [],
        "directorios_saltadas": [],
    }
    if simulado:
        from b2b.places import buscar_en_pais

        leads, llamadas, _ = buscar_en_pais(pais, tipos, limite, simulado=True, fuente="simulado")
        return leads, llamadas, stats

    todos: list[dict] = []
    llamadas = 0
    osm_meta: dict = {}
    try:
        osm_leads, llamadas, osm_meta = buscar_en_pais_osm(pais, tipos, limite, tipo_filtro)
        stats["osm"] = len(osm_leads)
        stats["osm_raw"] = osm_meta
        todos.extend(osm_leads)
    except OsmIslaFallida:
        raise
    except RuntimeError as error:
        registrar_evento({"evento": "osm_fallo_pais", "pais": pais, "error": str(error)[:300]})

    d_leads, d_skip = buscar_dealers_pais(pais, limite)
    stats["dealers"] = len(d_leads)
    stats["dealers_saltadas"] = d_skip
    todos.extend(d_leads)

    dir_leads, dir_skip = buscar_directorios_pais(pais, limite)
    stats["directorio"] = len(dir_leads)
    stats["directorios_saltadas"] = dir_skip
    todos.extend(dir_leads)

    descartes: list[dict] = list(osm_meta.get("descartes") or [])
    descartes_fusion: list[dict] = []
    fusionados = dedupe_y_fusionar(todos, descartes_fusion)
    descartes.extend(descartes_fusion)
    stats["descartes"] = descartes
    registrar_evento(
        {
            "evento": "buscar_pais_fuentes",
            "pais": pais,
            "osm": stats["osm"],
            "dealers": stats["dealers"],
            "directorio": stats["directorio"],
            "fusionados": len(fusionados),
            "osm_raw": osm_meta,
            "descartes": descartes,
        }
    )
    return fusionados[:limite], llamadas, stats
