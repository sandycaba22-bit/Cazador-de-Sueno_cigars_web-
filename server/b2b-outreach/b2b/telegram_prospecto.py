from __future__ import annotations

import re
import sys
import time

from b2b.country_rules import buscar_pais
from b2b.idioma import idioma_para_lead
from b2b.redactor import presentacion_prospecto_telegram
from b2b.telegram_control import puede_enviar_telegram, pausa_entre_mensajes, registrar_envio_telegram
from b2b.telegram_gestion import (
    registrar_pendiente,
    tiene_medio_contacto,
    token_callback,
    urls_formulario_contacto,
    ya_gestionado_telegram,
)


def _solo_digitos(tel: str) -> str:
    return re.sub(r"\D", "", tel or "")


def _tipo_etiqueta(tipo: str) -> str:
    return (tipo or "tienda").replace("_", " ")


def _lineas_contacto(lead: dict) -> list[str]:
    lineas: list[str] = []
    tel = (lead.get("telefono") or "").strip()
    if tel:
        lineas.append(f"📞 Teléfono: {tel}")
        num = _solo_digitos(tel)
        if len(num) >= 8:
            lineas.append(f"💬 WhatsApp: https://wa.me/{num}")
    correo = (lead.get("correo") or "").strip()
    if correo:
        lineas.append(f"✉️ Correo: {correo}")
    web = (lead.get("web") or "").strip()
    if web and web != "—":
        lineas.append(f"🌐 Web: {web}")
        for url in urls_formulario_contacto(web):
            lineas.append(f"📝 Formulario / contacto: {url}")
    if not lineas:
        lineas.append("— sin contacto publicado")
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
    presentacion = presentacion_prospecto_telegram(nombre, idioma, tipo)
    bloque_contacto = "\n".join(_lineas_contacto(lead))
    partes = [
        f"📍 PROSPECTO · {pais}",
        f"🏪 {nombre}",
        f"📋 Tipo: {_tipo_etiqueta(tipo)}",
        f"📌 Dirección: {dir_}",
        "",
        "——— Contacto ———",
        bloque_contacto,
        "",
        "——— Mensaje para copiar (tú envías al cliente) ———",
        presentacion,
    ]
    texto = "\n".join(partes)
    if len(texto) > 4000:
        texto = texto[:3990] + "\n…"
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
