#!/usr/bin/env python3
"""Comprueba el latido desde OTRO proceso. No lo llames desde --vigilar.

--vigilar solo escribe data/salud_latido.txt. Si ese proceso se cae, no puede
avisar. Este script lo lee un timer de systemd (cds-b2b-latido.timer).

  cd /var/www/html/server/b2b-outreach
  B2B_QUEUE_DIR=/var/lib/cazador-de-suenos/b2b-outreach python3 scripts/comprobar_latido.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from b2b.alertas_operador import alertar
    from b2b.salud import servicio_estuvo_caido

    if not servicio_estuvo_caido():
        print("Latido reciente.")
        return 0
    texto = "⚠️ El servicio B2B estuvo caído: el latido lleva más de 15 min sin actualizarse."
    alertar("servicio_caido", texto)
    print(texto, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
