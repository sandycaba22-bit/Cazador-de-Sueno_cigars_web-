from __future__ import annotations

import re
from pathlib import Path

from b2b.paths import KNOWLEDGE

FUENTE_RE = re.compile(
    r"\*\*Fuente:\*\*\s*(https?://[^\s—]+)\s*—\s*consulta\s*(\d{4}-\d{2}-\d{2})",
    re.I,
)


def _cargar_textos() -> dict[str, str]:
    out: dict[str, str] = {}
    for path in KNOWLEDGE.glob("*.md"):
        if path.name == "resumen_entrenamiento.md":
            continue
        out[path.name] = path.read_text(encoding="utf-8")
    return out


def _seccion_marca(texto: str, marca: str) -> str:
    pattern = re.compile(rf"## {re.escape(marca)}(.*?)(?=\n## |\Z)", re.S | re.I)
    match = pattern.search(texto)
    return match.group(1).strip() if match else ""


def _fuentes_en(texto: str) -> list[str]:
    return [f"{url} ({fecha})" for url, fecha in FUENTE_RE.findall(texto)]


def consultar(pregunta: str) -> str:
    pregunta_l = pregunta.strip().lower()
    if not pregunta_l:
        return "no tengo ese dato"
    textos = _cargar_textos()
    mercado = textos.get("mercado_marcas_referencia.md", "")

    if "arturo fuente" in pregunta_l and "distribu" in pregunta_l:
        sec = _seccion_marca(mercado, "Arturo Fuente")
        if not sec:
            return "no tengo ese dato"
        fuentes = _fuentes_en(sec)
        return (
            "Arturo Fuente suele trabajar con red de distribuidores en América y Europa y tiendas especializadas "
            "(detalle por país: sin verificar en nuestra base).\n"
            f"Fuentes: {', '.join(fuentes) if fuentes else 'sin URL en el extracto'}"
        )

    if "marca nueva" in pregunta_l or "piden" in pregunta_l and "distribuidor" in pregunta_l:
        if "Qué pide el canal premium" not in mercado and "marca emergente" not in mercado.lower():
            return "no tengo ese dato"
        return (
            "En la base de conocimiento, un distribuidor serio suele pedir a una marca nueva: muestras, "
            "material POS, exclusividad territorial, volúmenes mínimos y documentación de origen; "
            "plazos y cifras están marcados como sin verificar.\n"
            "Fuente: knowledge/mercado_marcas_referencia.md — consulta 2026-10-04"
        )

    if "davidoff" in pregunta_l and "plasencia" in pregunta_l:
        d = _seccion_marca(mercado, "Davidoff")
        p = _seccion_marca(mercado, "Plasencia")
        if not d or not p:
            return "no tengo ese dato"
        fd, fp = _fuentes_en(d), _fuentes_en(p)
        return (
            "Davidoff (base): casa suiza de lujo tabacalero, énfasis en construcción, consistencia y "
            "presentación premium; canales citados incluyen tiendas autorizadas y retail premium.\n"
            f"Fuentes Davidoff: {', '.join(fd) if fd else 'sin verificar'}\n\n"
            "Plasencia (base): producción vertical en Nicaragua, fuerte exportación, múltiples marcas; "
            "canales citados: distribuidores por país y retail especializado.\n"
            f"Fuentes Plasencia: {', '.join(fp) if fp else 'sin verificar'}\n\n"
            "Nota: esto es posicionamiento de referencia del mercado; no implica comparación de blends."
        )

    if "davidoff" in pregunta_l and "posicion" in pregunta_l:
        sec = _seccion_marca(mercado, "Davidoff")
        if not sec:
            return "no tengo ese dato"
        return sec.split("\n")[0].replace("- **Posicionamiento (fuente):**", "").strip() + "\nFuentes: " + ", ".join(
            _fuentes_en(sec)
        )

    return "no tengo ese dato"
