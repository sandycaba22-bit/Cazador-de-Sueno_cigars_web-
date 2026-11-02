#!/usr/bin/env python3
"""Reencola prospectos con evento telegram_prospecto_fallo desde logs/busqueda-*.jsonl.

Uso (en el servidor, con la cola real):
  cd /var/www/html/server/b2b-outreach
  B2B_QUEUE_DIR=/var/lib/cazador-de-suenos/b2b-outreach \\
    python3 scripts/reencolar_fallos_telegram.py --dry-run
  B2B_QUEUE_DIR=/var/lib/cazador-de-suenos/b2b-outreach \\
    python3 scripts/reencolar_fallos_telegram.py

Si el JSON ya no está en inbox, reconstruye el lead desde sent/, dudoso/, failed/,
leads_estado.json, registro_leads.json o google_places_cache.json.
No marca como enviados. Solo pone telegram_notificado=false y quita caducada_final.
Omite los que ya tienen correo en envios_correo/seguimiento o están en no_contactar.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from b2b.contacto_previo import motivo_ya_contactado  # noqa: E402
from b2b.paths import log_dir, state_file  # noqa: E402


def _cola() -> Path:
    raw = (os.getenv("B2B_QUEUE_DIR") or "").strip()
    return Path(raw) if raw else ROOT / "cola"


def _slug(nombre: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (nombre or "").casefold()).strip("-")
    return (s[:60] or "lead")


def _nombres_fallidos() -> dict[str, str]:
    """nombre.casefold() → nombre original (último visto)."""
    nombres: dict[str, str] = {}
    for path in sorted(log_dir().glob("busqueda-*.jsonl")):
        try:
            with path.open(encoding="utf-8") as handle:
                for linea in handle:
                    try:
                        ev = json.loads(linea)
                    except json.JSONDecodeError:
                        continue
                    if ev.get("evento") != "telegram_prospecto_fallo":
                        continue
                    nom = (ev.get("nombre") or "").strip()
                    if nom:
                        nombres[nom.casefold()] = nom
        except OSError:
            continue
    return nombres


def _leer_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _desde_cola(nombres: set[str]) -> dict[str, tuple[str, Path | None, dict]]:
    """clave → (origen, path|None, lead)."""
    hallados: dict[str, tuple[str, Path | None, dict]] = {}
    cola = _cola()
    for carpeta_nombre in ("inbox", "sent", "failed", "dudoso"):
        carpeta = cola / carpeta_nombre
        if not carpeta.is_dir():
            continue
        for path in list(carpeta.glob("*.json")):
            data = _leer_json(path)
            if not data:
                continue
            clave = (data.get("nombre") or "").strip().casefold()
            if clave not in nombres or clave in hallados:
                continue
            hallados[clave] = (carpeta_nombre, path, data)
    return hallados


def _desde_leads_estado(nombres: set[str], ya: set[str]) -> dict[str, tuple[str, Path | None, dict]]:
    hallados: dict[str, tuple[str, Path | None, dict]] = {}
    data = _leer_json(state_file("leads_estado.json")) or {}
    for item in (data.get("leads") or {}).values():
        if not isinstance(item, dict):
            continue
        clave = (item.get("nombre") or "").strip().casefold()
        if clave not in nombres or clave in ya or clave in hallados:
            continue
        lead = {
            "nombre": item.get("nombre") or "",
            "correo": item.get("correo") or "",
            "web": item.get("web") or "",
            "pais": item.get("pais") or item.get("estado") or "",
            "telegram_notificado": False,
            "fuente": "leads_estado",
        }
        hallados[clave] = ("leads_estado", None, lead)
    return hallados


def _desde_cache_y_registro(nombres: set[str], ya: set[str]) -> dict[str, tuple[str, Path | None, dict]]:
    hallados: dict[str, tuple[str, Path | None, dict]] = {}
    cache = _leer_json(state_file("google_places_cache.json")) or {}
    places = cache.get("places") or {}
    # Por nombre en el caché.
    for pid, raw in places.items():
        if not isinstance(raw, dict):
            continue
        nombre = (raw.get("displayName") or {}).get("text") or raw.get("nombre") or ""
        clave = nombre.strip().casefold()
        if clave not in nombres or clave in ya or clave in hallados:
            continue
        from b2b.places import _normalizar_place

        pais = (raw.get("pais") or "").strip() or "Florida"
        lead = _normalizar_place(raw, pais)
        lead["telegram_notificado"] = False
        lead["place_id"] = lead.get("place_id") or pid
        hallados[clave] = ("google_places_cache", None, lead)
    # registro_leads solo tiene place_ids/dominios: cruza con caché.
    registro = _leer_json(state_file("registro_leads.json")) or {}
    for pid in registro.get("place_ids") or []:
        raw = places.get(pid)
        if not isinstance(raw, dict):
            continue
        nombre = (raw.get("displayName") or {}).get("text") or raw.get("nombre") or ""
        clave = nombre.strip().casefold()
        if clave not in nombres or clave in ya or clave in hallados:
            continue
        from b2b.places import _normalizar_place

        lead = _normalizar_place(raw, (raw.get("pais") or "").strip() or "Florida")
        lead["telegram_notificado"] = False
        lead["place_id"] = lead.get("place_id") or pid
        hallados[clave] = ("registro_leads+cache", None, lead)
    return hallados


def _resolver(nombres: dict[str, str]) -> dict[str, tuple[str, Path | None, dict]]:
    claves = set(nombres)
    hallados = _desde_cola(claves)
    faltan = claves - set(hallados)
    if faltan:
        hallados.update(_desde_leads_estado(faltan, set(hallados)))
    faltan = claves - set(hallados)
    if faltan:
        hallados.update(_desde_cache_y_registro(faltan, set(hallados)))
    return hallados


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo imprime qué reencolaría; no escribe ni mueve archivos.",
    )
    args = parser.parse_args(argv)
    nombres = _nombres_fallidos()
    if not nombres:
        print("No hay telegram_prospecto_fallo en los logs.")
        return 0
    hallados = _resolver(nombres)
    tocados = 0
    omitidos = 0
    for clave in sorted(nombres):
        nombre = nombres[clave]
        if clave not in hallados:
            omitidos += 1
            print(f"Omitido (sin_lead): {nombre}")
            continue
        origen, path, data = hallados[clave]
        motivo = motivo_ya_contactado(data)
        if motivo:
            omitidos += 1
            print(f"Omitido ({motivo}): {nombre} ← {origen}")
            continue
        dest_name = path.name if path is not None else f"reencolado-{_slug(nombre)}.json"
        dest = _cola() / "inbox" / dest_name
        if args.dry_run:
            tocados += 1
            print(f"Reencolaría: {nombre} ← {origen}")
            continue
        data = dict(data)
        data["telegram_notificado"] = False
        data.pop("caducada_final", None)
        data.pop("omitido_motivo", None)
        if (data.get("estado_tarjeta") or "") in ("vencido", "ya_contactado", "correo_en_curso", "correo_enviado"):
            data["estado_tarjeta"] = "reencolada"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if path is not None and path.resolve() != dest.resolve() and path.is_file():
            try:
                path.unlink()
            except OSError:
                pass
        tocados += 1
        print(f"Reencolado: {nombre} ← {origen}")
    pref = "[dry-run] " if args.dry_run else ""
    print(
        f"{pref}Total {'a reencolar' if args.dry_run else 'reencolados'}: {tocados} "
        f"(omitidos: {omitidos}; nombres en log: {len(nombres)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
