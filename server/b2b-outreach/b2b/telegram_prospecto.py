from __future__ import annotations

import sys
import urllib.parse

from b2b.contacto_web import numero_whatsapp
from b2b.idioma import idioma_para_lead
from b2b.redactor import borrador_correo, borrador_corto, tipo_en_idioma
from b2b.telegram_control import puede_enviar_telegram, pausa_entre_mensajes, registrar_envio_telegram
from b2b.website import dominio_negocio, es_url_mapa
from b2b.telegram_gestion import (
    registrar_pendiente,
    tiene_medio_contacto,
    token_callback,
    ya_gestionado_telegram,
)

LIMITE_TELEGRAM = 4096


def _maps_url(lead: dict) -> str:
    url = (lead.get("maps_url") or "").strip()
    if url:
        return url
    web = (lead.get("web") or "").strip()
    return web if es_url_mapa(web) else ""


def _linea_rating(lead: dict) -> str:
    rating = lead.get("rating")
    reviews = lead.get("user_rating_count")
    if rating in (None, ""):
        return "⭐ Sin calificación en Google"
    try:
        return f"⭐ {float(rating):.1f} ({int(reviews or 0)} reseñas)"
    except (TypeError, ValueError):
        return "⭐ Sin calificación en Google"


def link_whatsapp(lead: dict, borrador: str) -> str:
    num = numero_whatsapp(lead)
    if not num:
        return ""
    return f"https://wa.me/{num}?text={urllib.parse.quote(borrador)}"


def _lineas_contacto(lead: dict, wa: str) -> list[str]:
    lineas: list[str] = []
    tel = (lead.get("telefono") or "").strip()
    if tel:
        lineas.append(f"📞 Teléfono: {tel}")
    if wa:
        lineas.append(f"💬 WhatsApp con borrador: {wa}")
    correo = (lead.get("correo") or "").strip()
    if correo:
        lineas.append(f"✉️ Correo: {correo}")
    web = (lead.get("web") or "").strip()
    if dominio_negocio(web):
        lineas.append(f"🌐 Web: {web}")
    for campo, icono, etiqueta in (
        ("instagram", "📸", "Instagram"),
        ("facebook", "👍", "Facebook"),
        ("formulario", "📝", "Formulario"),
    ):
        valor = (lead.get(campo) or "").strip()
        if valor:
            lineas.append(f"{icono} {etiqueta}: {valor}")
    maps = _maps_url(lead)
    if maps:
        lineas.append(f"🗺️ Google Maps: {maps}")
    return lineas


def mensaje_prospecto_completo(lead: dict, pais: str) -> str:
    nombre = lead.get("nombre") or "—"
    tipo = lead.get("tipo") or lead.get("tipo_negocio") or "tienda"
    dir_ = (lead.get("direccion") or "").strip() or "—"
    idioma = idioma_para_lead(
        pais,
        idioma_web=(lead.get("idioma_web") or "").strip(),
        preferido=(lead.get("idioma") or "").strip(),
        web=lead.get("web") or "",
    )
    corto = borrador_corto(nombre, idioma, tipo)
    wa = link_whatsapp(lead, corto)
    partes = [
        f"📍 PROSPECTO · {pais}",
        f"🏪 {nombre}",
        f"📋 Tipo: {tipo_en_idioma(tipo, 'es')}",
        f"📌 Dirección: {dir_}",
        _linea_rating(lead),
        "",
        "——— Contacto ———",
        *_lineas_contacto(lead, wa),
        "",
        "——— Mensaje WhatsApp / Instagram (tú lo envías) ———",
        corto,
    ]
    if (lead.get("correo") or "").strip():
        partes += ["", "——— Versión correo ———", borrador_correo(nombre, idioma, tipo)]
    texto = "\n".join(partes)
    if len(texto) > LIMITE_TELEGRAM and wa:
        texto = texto.replace(f"💬 WhatsApp con borrador: {wa}", f"💬 WhatsApp: https://wa.me/{numero_whatsapp(lead)}")
    if len(texto) > LIMITE_TELEGRAM:
        texto = texto[: LIMITE_TELEGRAM - 10] + "\n…"
    return texto


def _teclado_prospecto(token: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "Enviado", "callback_data": f"b2be:{token}"},
                {"text": "Descartar", "callback_data": f"b2bd:{token}"},
            ]
        ]
    }


def enviar_prospecto_telegram(
    lead: dict,
    pais: str,
    *,
    simulado: bool = False,
    inbox_path: str = "",
) -> bool:
    if not tiene_medio_contacto(lead):
        return False
    if ya_gestionado_telegram(lead) or lead.get("telegram_notificado"):
        return False

    lead = dict(lead)
    lead.setdefault("pais", pais)
    texto = mensaje_prospecto_completo(lead, pais)
    token = token_callback(lead)

    if simulado:
        print("=== TELEGRAM SIMULADO (prospecto) ===", file=sys.stderr)
        print(texto, file=sys.stderr)
        print("[Botones: Enviado | Descartar]", file=sys.stderr)
        print("=== fin ===", file=sys.stderr)
        return True

    if not puede_enviar_telegram():
        return False

    from telegram_bot import enviar_mensaje_telegram, load_local_env

    load_local_env()
    registrar_pendiente(token, lead, inbox_path)
    enviar_mensaje_telegram(texto, reply_markup=_teclado_prospecto(token))
    registrar_envio_telegram()
    pausa_entre_mensajes()
    return True


# Compatibilidad con código anterior
def enviar_prospecto_dos_mensajes(lead: dict, pais: str, *, simulado: bool = False) -> bool:
    return enviar_prospecto_telegram(lead, pais, simulado=simulado)
