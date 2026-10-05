"""Pruebas de humo locales (sin Telegram ni Google reales)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
BOT = ROOT / "telegram_bot.py"


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PY, str(BOT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def main() -> int:
    checks = []

    entrenar = run(["--entrenar"])
    checks.append(("entrenar", entrenar.returncode == 0))

    reglas = run(["--reglas"])
    checks.append(("reglas", reglas.returncode == 0 and "Martinique" in reglas.stdout))

    buscar = run(
        ["--buscar", "--pais", "Martinique", "--max", "2", "--simulado", "--solo-listar"]
    )
    checks.append(("buscar_dry", buscar.returncode == 0 and "fixture" in buscar.stdout.lower()))

    registro = ROOT / "data" / "registro_leads.json"
    if registro.is_file():
        registro.unlink()
    encolar = run(["--buscar", "--pais", "Martinique", "--max", "2", "--simulado"])
    checks.append(("encolar", encolar.returncode == 0 and "Encolados" in encolar.stdout))

    cola = run(["--vigilar", "--una-pasada", "--imprimir"])
    checks.append(("cola", cola.returncode == 0 and "prospecto B2B" in cola.stdout))

    manual = run(
        [
            "--nombre",
            "Le Cercle du Cigare",
            "--pais",
            "Martinique",
            "--web",
            "https://lecercle.mq",
            "--correo",
            "contacto@lecercle.mq",
            "--imprimir",
        ]
    )
    checks.append(("manual", manual.returncode == 0 and "BAJA" in manual.stdout or "STOP" in manual.stdout))

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"[{'OK' if ok else 'FAIL'}] {name}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
