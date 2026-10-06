from __future__ import annotations

import sys

from b2b.logging_ops import registrar_evento


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
    isla: str, nuevas: int, con_contacto: int, simulado: bool = False
) -> None:
    if nuevas <= 0:
        return
    notificar_buscar(
        f"📍 {isla}: {nuevas} tiendas nuevas encontradas ({con_contacto} con teléfono/correo)",
        simulado=simulado,
    )


def avisar_isla_fallida(isla: str, simulado: bool = False) -> None:
    notificar_buscar(f"⚠️ {isla}: Overpass no respondió tras reintentos.", simulado=simulado)


def avisar_resumen_barrido(
    total: int,
    por_isla: dict[str, int],
    contacto_por_isla: dict[str, int],
    islas_fallidas: list[str],
    zona: str,
    simulado: bool = False,
) -> None:
    lineas = [f"📊 Barrido OSM ({zona}) — {total} tienda(s) nueva(s) encolada(s)"]
    for isla, cantidad in por_isla.items():
        if cantidad > 0:
            c = contacto_por_isla.get(isla, 0)
            lineas.append(f"• {isla}: {cantidad} ({c} con tel/correo)")
    if islas_fallidas:
        lineas.append("Islas fallidas: " + ", ".join(islas_fallidas))
    notificar_buscar("\n".join(lineas), simulado=simulado)
