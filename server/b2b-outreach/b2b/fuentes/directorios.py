from __future__ import annotations

import json
import re
from html import unescape

from b2b.fuentes.http_polite import fetch_url, permitido_robots
from b2b.paths import data_file

EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")


def _cargar_config() -> list[dict]:
    path = data_file("directorios.json")
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("directorios") or [])


def buscar_directorios_pais(pais: str, limite: int = 15) -> tuple[list[dict], list[str]]:
    saltadas: list[str] = []
    leads: list[dict] = []
    for entry in _cargar_config():
        if (entry.get("pais") or "").strip().lower() != pais.strip().lower():
            continue
        for url in entry.get("urls") or []:
            url = str(url).strip()
            if not url:
                continue
            if not permitido_robots(url):
                saltadas.append(f"directorio:{url} (robots.txt)")
                continue
            try:
                html = fetch_url(url)
            except Exception as exc:
                saltadas.append(f"directorio:{url} ({type(exc).__name__})")
                continue
            texto = unescape(re.sub(r"<[^>]+>", "\n", html))
            for linea in texto.splitlines():
                linea = linea.strip()
                if len(linea) < 10:
                    continue
                if not re.search(r"cigar|tabac|tobacco|humidor|puro|charuto", linea, re.I):
                    continue
                mail = EMAIL_RE.search(linea)
                tel = PHONE_RE.search(linea)
                leads.append(
                    {
                        "nombre": linea[:80],
                        "pais": pais,
                        "web": url,
                        "telefono": tel.group(0).strip() if tel else "",
                        "correo": mail.group(0).strip() if mail else "",
                        "direccion": "",
                        "place_id": f"directorio:{hash(linea + url) & 0xFFFFFF}",
                        "tipo_negocio": "tienda",
                        "fuente": "directorio",
                    }
                )
                if len(leads) >= limite:
                    return leads[:limite], saltadas
    return leads[:limite], saltadas
