from __future__ import annotations

from pathlib import Path

from prospector import prospectar


def ejecutar_busqueda(
    pais_cli: str | None,
    limite: int,
    cola_inbox: Path,
    dry_run: bool = False,
    solo_listar: bool = False,
    simulado: bool | None = None,
    tipo_filtro: str = "",
) -> list:
    sim = dry_run if simulado is None else simulado
    result = prospectar(
        pais_cli,
        limite,
        cola_inbox,
        simulado=sim,
        solo_listar=solo_listar,
        tipo_filtro=tipo_filtro,
    )
    return list(range(result.get("encolados", 0)))
