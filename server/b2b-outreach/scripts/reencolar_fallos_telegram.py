#!/usr/bin/env python3
"""Reencola prospectos con evento telegram_prospecto_fallo desde logs/busqueda-*.jsonl.

Uso (en el servidor, con la cola real):
  cd /var/www/html/server/b2b-outreach
  B2B_QUEUE_DIR=/var/lib/cazador-de-suenos/b2b-outreach \\
    python3 scripts/reencolar_fallos_telegram.py

No marca como enviados. Solo pone telegram_notificado=false y quita caducada_final.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

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


def main() -> int:
    nombres = _nombres_fallidos()
    if not nombres:
        print("No hay telegram_prospecto_fallo en los logs.")
        return 0
    cola = _cola()
    tocados = 0
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
            data["telegram_notificado"] = False
            data.pop("caducada_final", None)
            if (data.get("estado_tarjeta") or "") == "vencido":
                data["estado_tarjeta"] = "reencolada"
            dest = cola / "inbox" / path.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            if path.resolve() != dest.resolve() and path.is_file():
                try:
                    path.unlink()
                except OSError:
                    pass
            tocados += 1
            print(f"Reencolado: {data.get('nombre')} ← {carpeta_nombre}/{path.name}")
    print(f"Total reencolados: {tocados} (candidatos en log: {len(nombres)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
