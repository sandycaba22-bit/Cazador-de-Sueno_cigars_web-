#!/usr/bin/env python3
"""Reencola prospectos con evento telegram_prospecto_fallo desde logs/busqueda-*.jsonl.

Uso (en el servidor, con la cola real):
  cd /var/www/html/server/b2b-outreach
  B2B_QUEUE_DIR=/var/lib/cazador-de-suenos/b2b-outreach \\
    python3 scripts/reencolar_fallos_telegram.py --dry-run
  B2B_QUEUE_DIR=/var/lib/cazador-de-suenos/b2b-outreach \\
    python3 scripts/reencolar_fallos_telegram.py

No marca como enviados. Solo pone telegram_notificado=false y quita caducada_final.
Omite los que ya tienen correo en envios_correo/seguimiento o están en no_contactar.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from b2b.contacto_previo import motivo_ya_contactado  # noqa: E402
from b2b.paths import log_dir  # noqa: E402


def _cola() -> Path:
    raw = (os.getenv("B2B_QUEUE_DIR") or "").strip()
    return Path(raw) if raw else ROOT / "cola"


def _nombres_fallidos() -> set[str]:
    nombres: set[str] = set()
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
                        nombres.add(nom.casefold())
        except OSError:
            continue
    return nombres


def _candidatos(nombres: set[str]) -> list[tuple[str, Path, dict]]:
    cola = _cola()
    filas: list[tuple[str, Path, dict]] = []
    for carpeta_nombre in ("inbox", "sent", "failed", "dudoso"):
        carpeta = cola / carpeta_nombre
        if not carpeta.is_dir():
            continue
        for path in list(carpeta.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            if (data.get("nombre") or "").strip().casefold() not in nombres:
                continue
            filas.append((carpeta_nombre, path, data))
    return filas


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
    tocados = 0
    omitidos = 0
    for carpeta_nombre, path, data in _candidatos(nombres):
        motivo = motivo_ya_contactado(data)
        if motivo:
            omitidos += 1
            print(f"Omitido ({motivo}): {data.get('nombre')} ← {carpeta_nombre}/{path.name}")
            continue
        dest = _cola() / "inbox" / path.name
        if args.dry_run:
            tocados += 1
            print(f"[dry-run] Reencolaría: {data.get('nombre')} ← {carpeta_nombre}/{path.name}")
            continue
        data["telegram_notificado"] = False
        data.pop("caducada_final", None)
        if (data.get("estado_tarjeta") or "") == "vencido":
            data["estado_tarjeta"] = "reencolada"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if path.resolve() != dest.resolve() and path.is_file():
            try:
                path.unlink()
            except OSError:
                pass
        tocados += 1
        print(f"Reencolado: {data.get('nombre')} ← {carpeta_nombre}/{path.name}")
    pref = "[dry-run] " if args.dry_run else ""
    print(
        f"{pref}Total {'a reencolar' if args.dry_run else 'reencolados'}: {tocados} "
        f"(omitidos ya contactados: {omitidos}; nombres en log: {len(nombres)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
