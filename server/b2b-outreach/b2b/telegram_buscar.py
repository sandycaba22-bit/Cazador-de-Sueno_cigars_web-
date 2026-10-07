from __future__ import annotations

import os
import sys

from b2b.descartes import resumen_motivos
from b2b.logging_ops import registrar_evento


def _aviso_cero_habilitado() -> bool:
    return (os.getenv("BUSCAR_AVISO_CERO", "0") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def notificar_buscar(texto: str, simulado: bool = False) -> None:
    """Envía texto al chat B2B; no lanza excepción (el barrido sigue)."""
    if not (texto or "").strip():
        return
    if simulado:
        print(f"[Telegram simulado] {texto.strip()}", file=sys.stderr)
        return
    try:
        from telegram_bot import enviar_texto_telegram, load_local_env

        load_local_env()
        enviar_texto_telegram(texto.strip())
    except Exception as exc:
        msg = str(exc)[:400]
        registrar_evento({"evento": "telegram_buscar_fallo", "mensaje": msg})
        print(f"Aviso Telegram no enviado: {msg}", file=sys.stderr)


def texto_conteo_isla(isla: str, conteo: dict, descartes: list | None = None) -> str:
    """Resumen corto; la suma de categorías es igual a 'encontrados'."""
    partes = [
        f"{conteo.get('encolados', 0)} encolados",
        f"{conteo.get('descartados', 0)} descartados",
        f"{conteo.get('dudosos', 0)} dudosos",
        f"{conteo.get('repetidos', 0)} repetidos",
        f"{conteo.get('sin_contacto', 0)} sin contacto",
    ]
    if conteo.get("solo_telefono"):
        partes.insert(3, f"{conteo['solo_telefono']} solo teléfono")
    if conteo.get("pendiente_limite"):
        partes.append(f"{conteo['pendiente_limite']} pendientes (límite)")
    lineas = [f"📍 {isla}: {conteo.get('encontrados', 0)} encontrados = " + " · ".join(partes)]
    if descartes:
        lineas.append("Descartes: " + resumen_motivos(descartes))
    if conteo.get("sin_clasificar"):
        lineas.append(f"⚠️ {conteo['sin_clasificar']} sin clasificar (revisar log)")
    return "\n".join(lineas)


def avisar_isla_encontradas(
    isla: str,
    conteo: dict,
    simulado: bool = False,
    descartes: list | None = None,
) -> None:
    if int(conteo.get("encontrados", 0)) <= 0 and not _aviso_cero_habilitado():
        return
    notificar_buscar(texto_conteo_isla(isla, conteo, descartes), simulado=simulado)


def avisar_isla_fallida(isla: str, simulado: bool = False) -> None:
    notificar_buscar(f"⚠️ {isla}: Overpass no respondió tras reintentos.", simulado=simulado)


def avisar_resumen_barrido(
    total: int,
    por_isla: dict[str, int],
    contacto_por_isla: dict[str, int],
    islas_fallidas: list[str],
    zona: str,
    simulado: bool = False,
    detalle_islas: dict[str, dict] | None = None,
) -> None:
    lineas = [f"📊 Resumen ({zona}): {total} encolado(s)"]
    for isla, cantidad in por_isla.items():
        c = contacto_por_isla.get(isla, 0)
        lineas.append(f"• {isla}: {cantidad} ({c} con contacto)")
    if islas_fallidas:
        lineas.append("⚠️ " + ", ".join(islas_fallidas))
    notificar_buscar("\n".join(lineas), simulado=simulado)


def enviar_prueba_telegram() -> None:
    notificar_buscar("✅ Prueba Telegram buscar OK (cds-b2b-buscar).", simulado=False)
