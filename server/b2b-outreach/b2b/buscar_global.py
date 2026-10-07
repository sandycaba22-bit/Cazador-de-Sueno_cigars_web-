from __future__ import annotations

import os
import time

from b2b.buscar_filtros import dedupe_y_fusionar
from b2b.buscar_pais import recolectar_leads_pais
from b2b.country_rules import buscar_pais
from b2b.logging_ops import registrar_evento
from b2b.osm_cuadricula import (
    buscar_celda,
    cargar_estado_global,
    guardar_estado_global,
    preparar_celdas_pais,
)
from b2b.osm_places import _iso_para_pais
from b2b.paises_cola import cargar_paises_cola, entry_por_pais


def _pausa_larga_entre_celdas() -> None:
    try:
        sec = float(os.getenv("B2B_OSM_CELDA_PAUSE_SEC", "8") or "8")
    except ValueError:
        sec = 8.0
    if sec > 0:
        time.sleep(sec)


def _max_celdas_por_pais() -> int:
    try:
        return max(1, int(os.getenv("B2B_MAX_CELDAS_POR_PAIS", "12") or "12"))
    except ValueError:
        return 12


def recolectar_pais_cuadricula(
    pais: str,
    limite: int,
    *,
    reanudar: bool = True,
) -> tuple[list[dict], int, dict]:
    """Un país por turno: varias celdas con caché y estado en disco."""
    iso = _iso_para_pais(pais)
    celdas = preparar_celdas_pais(iso)
    estado = cargar_estado_global() if reanudar else {"pais_idx": 0, "celda_idx": 0}
    if estado.get("pais") == pais:
        inicio = int(estado.get("celda_idx") or 0)
    else:
        inicio = 0
    todos: list[dict] = []
    descartes: list[dict] = []
    llamadas = 0
    max_c = _max_celdas_por_pais()
    fin = min(len(celdas), inicio + max_c)
    hecho = inicio
    for idx in range(inicio, fin):
        _pausa_larga_entre_celdas()
        batch, ll = buscar_celda(pais, iso, celdas[idx], idx, descartes=descartes)
        llamadas += ll
        todos.extend(batch)
        hecho = idx + 1
        guardar_estado_global(
            {"pais": pais, "iso": iso, "pais_idx": estado.get("pais_idx", 0), "celda_idx": idx + 1}
        )
        if len(todos) >= limite * 3:
            break
    stats = {
        "modo": "cuadricula",
        "celdas": hecho - inicio,
        "celda_inicio": inicio,
        "celda_total": len(celdas),
        "descartes": descartes,
    }
    if hecho >= len(celdas):
        guardar_estado_global({"pais": pais, "iso": iso, "celda_idx": 0, "completo": True})
    registrar_evento(
        {"evento": "buscar_global_celdas", "pais": pais, **stats, "raw": len(todos), "descartes": len(descartes)}
    )
    return todos, llamadas, stats


def siguiente_pais_cola() -> dict | None:
    fila = cargar_paises_cola()
    if not fila:
        return None
    estado = cargar_estado_global()
    idx = int(estado.get("pais_idx") or 0)
    if idx >= len(fila):
        return None
    actual = fila[idx]
    if estado.get("completo") and (estado.get("pais") or "") == (actual.get("pais") or ""):
        idx += 1
        guardar_estado_global({"pais_idx": idx, "celda_idx": 0, "completo": False, "pais": ""})
        if idx >= len(fila):
            return None
        actual = fila[idx]
    if not estado.get("pais") or estado.get("pais") != actual.get("pais"):
        guardar_estado_global(
            {
                "pais_idx": idx,
                "pais": actual.get("pais"),
                "iso": actual.get("iso3166"),
                "celda_idx": int(estado.get("celda_idx") or 0) if estado.get("pais") == actual.get("pais") else 0,
                "completo": False,
            }
        )
    return actual


def avanzar_siguiente_pais() -> None:
    estado = cargar_estado_global()
    guardar_estado_global(
        {
            "pais_idx": int(estado.get("pais_idx") or 0) + 1,
            "celda_idx": 0,
            "completo": False,
        }
    )


def recolectar_leads_global(
    pais: str | None,
    tipos: list[str],
    limite: int,
    tipo_filtro: str = "",
    simulado: bool = False,
) -> tuple[list[dict], int, dict]:
    if simulado:
        reg = buscar_pais(pais) if pais else None
        if not reg:
            return [], 0, {}
        return recolectar_leads_pais(reg["pais"], tipos, limite, tipo_filtro, simulado=True)

    nombre = pais
    if not nombre:
        row = siguiente_pais_cola()
        if not row:
            return [], 0, {"fin_cola": True}
        nombre = row["pais"]
    else:
        row = entry_por_pais(nombre)

    usar_grid = os.getenv("B2B_BUSCAR_CUADRICULA", "1").strip().lower() not in ("0", "false", "no")
    stats: dict = {"pais": nombre, "iso": (row or {}).get("iso3166", "")}
    try:
        if usar_grid and row and row.get("iso3166"):
            try:
                leads, llamadas, grid_stats = recolectar_pais_cuadricula(nombre, limite)
                stats.update(grid_stats)
            except ValueError as grid_err:
                stats["cuadricula_fallback"] = str(grid_err)[:120]
                leads, llamadas, stats_osm = recolectar_leads_pais(
                    nombre, tipos, limite, tipo_filtro, simulado=False
                )
                stats.update(stats_osm)
                return leads, llamadas, stats
            d_leads, llamadas_d, d_stats = _complemento_dealers(nombre, tipos, limite, tipo_filtro)
            stats.update(d_stats)
            descartes_fusion: list[dict] = []
            repetidos_fusion: list[dict] = []
            todos = dedupe_y_fusionar(leads + d_leads, descartes_fusion, repetidos_fusion)
            stats["descartes"] = list(stats.get("descartes") or []) + descartes_fusion
            stats["repetidos_fusion"] = repetidos_fusion
            return todos, llamadas + llamadas_d, stats
        leads, llamadas, stats_osm = recolectar_leads_pais(
            nombre, tipos, limite, tipo_filtro, simulado=False
        )
        stats.update(stats_osm)
        return leads, llamadas, stats
    except ValueError as error:
        stats["error"] = str(error)[:200]
        return [], 0, stats


def _complemento_dealers(pais: str, tipos: list[str], limite: int, tipo_filtro: str) -> tuple[list[dict], int, dict]:
    from b2b.fuentes.dealers import buscar_dealers_pais
    from b2b.fuentes.directorios import buscar_directorios_pais

    d_leads, d_skip = buscar_dealers_pais(pais, limite)
    dir_leads, dir_skip = buscar_directorios_pais(pais, limite)
    stats = {
        "dealers": len(d_leads),
        "directorio": len(dir_leads),
        "dealers_saltadas": d_skip,
        "directorios_saltadas": dir_skip,
    }
    return d_leads + dir_leads, 0, stats
