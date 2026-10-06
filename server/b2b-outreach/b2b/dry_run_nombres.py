from __future__ import annotations

import sys

import os

from b2b.nombres_busqueda import clasificar_aceptacion
from b2b.osm_places import _iso_para_pais, _nombre_log_osm, _tag, obtener_elementos_osm_pais


def _lead_desde_elemento(el: dict, pais: str) -> dict:
    tags = el.get("tags") or {}
    nombre = _tag(tags, "name", "brand", "operator") or _nombre_log_osm(el, tags)
    web = _tag(tags, "website", "contact:website", "url")
    return {
        "nombre": nombre,
        "web": web,
        "pais": pais,
        "_osm_tags": dict(tags),
        "osm_shop_tobacco": (tags.get("shop") or "").lower() in ("tobacco", "cigar"),
        "fuente": "openstreetmap",
    }


def _dry_run_max_celdas() -> int:
    try:
        return max(1, int(os.getenv("B2B_DRY_RUN_MAX_CELDAS", "6") or "6"))
    except ValueError:
        return 6


def _usar_cuadricula_dry_run(iso: str) -> bool:
    if os.getenv("B2B_DRY_RUN_CUADRICULA", "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    from b2b.osm_cuadricula import preparar_celdas_pais

    try:
        return len(preparar_celdas_pais(iso)) > 20
    except ValueError:
        return False


def dry_run_nombres_isla(pais: str, *, limite_elementos: int = 500) -> dict[str, list[dict]]:
    iso = _iso_para_pais(pais)
    max_c = _dry_run_max_celdas()
    if _usar_cuadricula_dry_run(iso):
        from b2b.osm_cuadricula import obtener_elementos_cuadricula

        print(
            f"(dry-run: cuadrícula, {max_c} celda(s) — bbox grande o B2B_DRY_RUN_CUADRICULA=1)",
            file=sys.stderr,
        )
        elementos, _llamadas = obtener_elementos_cuadricula(iso, max_celdas=max_c)
        if not elementos:
            raise RuntimeError(f"Sin elementos OSM en cuadrícula para {pais}")
    else:
        try:
            elementos, _llamadas = obtener_elementos_osm_pais(pais)
        except RuntimeError:
            from b2b.osm_cuadricula import obtener_elementos_cuadricula

            elementos, _llamadas = obtener_elementos_cuadricula(iso, max_celdas=max_c)
            if not elementos:
                raise
            print(
                f"(dry-run: consulta país completa falló; usando {max_c} celda(s) de cuadrícula)",
                file=sys.stderr,
            )
    if limite_elementos > 0:
        elementos = elementos[:limite_elementos]
    buckets: dict[str, list[dict]] = {"aceptado": [], "dudoso": [], "excluido": []}
    vistos: set[str] = set()
    for el in elementos:
        lead = _lead_desde_elemento(el, pais)
        clave = f"{lead['nombre']}|{lead.get('_osm_tags', {}).get('shop', '')}"
        if clave in vistos:
            continue
        vistos.add(clave)
        bucket, motivo = clasificar_aceptacion(lead)
        buckets[bucket].append(
            {
                "nombre": lead["nombre"],
                "motivo": motivo,
                "web": lead.get("web") or "",
                "shop": (lead.get("_osm_tags") or {}).get("shop") or "",
            }
        )
    return buckets


def imprimir_dry_run(pais: str, buckets: dict[str, list[dict]]) -> None:
    print(f"=== Dry-run nombres: {pais} ===", file=sys.stderr)
    for bucket in ("aceptado", "dudoso", "excluido"):
        items = buckets.get(bucket) or []
        titulo = {"aceptado": "ENTRA", "dudoso": "DUDOSO", "excluido": "EXCLUIDO"}[bucket]
        print(f"\n--- {titulo} ({len(items)}) ---")
        for row in sorted(items, key=lambda x: (x.get("nombre") or "").lower()):
            extra = row.get("shop") or ""
            web = row.get("web") or ""
            suf = f" [{extra}]" if extra else ""
            web_s = f" · {web[:50]}" if web else ""
            print(f"  · {row['nombre']}{suf} — {row['motivo']}{web_s}")
