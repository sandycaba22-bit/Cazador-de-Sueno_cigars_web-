from __future__ import annotations

import os
import sys

from b2b.descartes import lineas_resumen_descartes
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
    if simulado or not (texto or "").strip():
        return
    try:
        from telegram_bot import enviar_texto_telegram, load_local_env

        load_local_env()
        enviar_texto_telegram(texto.strip())
    except Exception as exc:
        msg = str(exc)[:400]
        registrar_evento({"evento": "telegram_buscar_fallo", "mensaje": msg})
        print(f"Aviso Telegram no enviado: {msg}", file=sys.stderr)


def avisar_isla_encontradas(
    isla: str,
    encontrados: int,
    fuente_stats: dict,
    nuevos: int,
    repetidos: int,
    con_contacto: int,
    simulado: bool = False,
    descartes: list | None = None,
    repetidos_detalle: list | None = None,
    stats_calidad: dict | None = None,
) -> None:
    cal = stats_calidad or fuente_stats.get("calidad") or {}
    acept = int(cal.get("aceptados", 0))
    dud = int(cal.get("dudosos", 0))
    wc = int(cal.get("web_caida", 0))
    dw = int(cal.get("descartados_web", 0))
    dt = int(cal.get("descartados_tipo", 0))
    extra_desc = lineas_resumen_descartes(descartes or [], repetidos_detalle or [])
    tiene_detalle = bool(extra_desc)
    if encontrados <= 0 and nuevos <= 0 and not _aviso_cero_habilitado() and not tiene_detalle:
        return
    resumen_cal = (
        f"aceptados {acept} · dudosos {dud} · web_caida {wc} · "
        f"desc web {dw} · desc tipo {dt}"
    )
    if encontrados <= 0 and nuevos <= 0 and _aviso_cero_habilitado():
        lineas = [
            f"📍 {isla}: 0 encontrados · {resumen_cal} · "
            f"0 nuevos · {repetidos} repetidos · {con_contacto} con contacto",
        ]
        lineas.extend(extra_desc)
        notificar_buscar("\n".join(lineas), simulado=simulado)
        return
    lineas = [
        f"📍 {isla}: {encontrados} encontrados · {resumen_cal} · "
        f"{nuevos} nuevos · {repetidos} repetidos · {con_contacto} con contacto",
    ]
    lineas.extend(extra_desc)
    notificar_buscar("\n".join(lineas), simulado=simulado)


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
    lineas = [f"📊 Barrido ({zona}) — {total} prospecto(s) nuevo(s) encolado(s)"]
    detalle = detalle_islas or {}
    for isla, cantidad in por_isla.items():
        c = contacto_por_isla.get(isla, 0)
        extra = detalle.get(isla) or {}
        if extra:
            osm = int(extra.get("osm", 0))
            dealers = int(extra.get("dealers", 0))
            web = int(extra.get("directorio", 0)) + int(extra.get("web_enriquecidos", 0))
            lineas.append(
                f"• {isla}: {cantidad} encolados ({c} con tel/correo) — "
                f"encontrados {extra.get('encontrados', '?')} "
                f"(OSM {osm}, dealers {dealers}, web {web})"
            )
        elif cantidad > 0:
            lineas.append(f"• {isla}: {cantidad} ({c} con tel/correo)")
    if islas_fallidas:
        lineas.append("Islas fallidas: " + ", ".join(islas_fallidas))
    notificar_buscar("\n".join(lineas), simulado=simulado)


def enviar_prueba_telegram() -> None:
    notificar_buscar("✅ Prueba Telegram buscar OK (cds-b2b-buscar).", simulado=False)
