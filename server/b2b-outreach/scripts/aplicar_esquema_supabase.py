"""Aplica supabase/001_b2b.sql si SUPABASE_DB_URL está definida.

La clave anónima no puede crear tablas. Sin la URL de Postgres el script
no toca nada y deja el SQL listo para el editor de Supabase.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

SQL = Path(__file__).resolve().parents[1] / "supabase" / "001_b2b.sql"


def main() -> int:
    url = os.getenv("SUPABASE_DB_URL", "").strip()
    if not url:
        print("Falta SUPABASE_DB_URL. Abre el SQL Editor y ejecuta:")
        print(SQL)
        return 2
    psql = shutil.which("psql")
    if not psql:
        print("psql no está instalado. Ejecuta el archivo SQL en el editor de Supabase:")
        print(SQL)
        return 2
    run = subprocess.run([psql, url, "-v", "ON_ERROR_STOP=1", "-f", str(SQL)], check=False)
    return run.returncode


if __name__ == "__main__":
    sys.exit(main())
