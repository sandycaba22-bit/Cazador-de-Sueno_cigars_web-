from __future__ import annotations

import re

from b2b.country_rules import buscar_pais
from b2b.idioma import idioma_para_lead
from b2b.redactor import semaforo_aduana, texto_corto_prospecto_buscar
from b2b.telegram_control import puede_enviar_telegram, registrar_envio_telegram


def _solo_digitos(tel: str) -> str:
    return re.sub(r"\D", "", tel or "")


def linea_whatsapp(lead: dict) -> str:
    wa = (lead.get("whatsapp") or "").strip()
    tel = (lead.get("telefono") or "").strip()
    if wa:
        num = _solo_digitos(wa)
        if num:
            return f"💬 WhatsApp: https://wa.me/{num}"
    if tel:
        num = _solo_digitos(tel)
        if len(num) >= 8:
            return f"💬 posible WhatsApp: https://wa.me/{num}"
    return "💬 WhatsApp: —"


def linea_web(lead: dict) -> str:
    web = (lead.get("web") or "").strip()
    if not web or web == "—":
        return "🌐 web: —"
    estado = (lead.get("web_estado") or lead.get("calidad_nota") or "sin chequeo").strip()
    http = lead.get("web_http")
    extra = f" ({estado}"
    if http is not None:
        extra += f", HTTP {http}"
    extra += ")"
    return f"🌐 {web}{extra}"


def linea_maps(lead: dict) -> str:
    lat = lead.get("lat")
    lon = lead.get("lon")
    if lat is None or lon is None:
        return "🗺️ mapa: sin coordenadas"
    return f"🗺️ https://www.google.com/maps/search/?api=1&query={lat},{lon}"


def mensaje_ficha_prospecto(lead: dict, pais: str) -> str:
    entry = buscar_pais(pais)
    idioma = idioma_para_lead(
        pais,
        idioma_web=(lead.get("idioma_web") or "").strip(),
        preferido=(lead.get("idioma") or "").strip(),
        web=lead.get("web") or "",
    )
    dif = lead.get("dificultad_aduana")
    if dif is None and entry:
        dif = entry.get("dificultad")
    _sem, etiqueta = semaforo_aduana(dif)
    estado = (lead.get("estado_reglas") or (entry or {}).get("estado") or "preliminar")
    nombre = lead.get("nombre") or "—"
    tipo = lead.get("tipo") or lead.get("tipo_negocio") or "tienda"
    tel = (lead.get("telefono") or "").strip() or "—"
    correo = (lead.get("correo") or "").strip()
    correo_txt = correo if correo else "sin correo publicado"
    dir_ = (lead.get("direccion") or "").strip() or "—"
    lineas = [
        f"📍 NUEVO PROSPECTO · {pais}",
        f"🏪 {nombre} · {tipo}",
        f"📞 {tel}",
        linea_whatsapp(lead),
        f"✉️ {correo_txt}",
        linea_web(lead),
        f"📌 {dir_}",
        linea_maps(lead),
        f"🛃 aduana: {etiqueta} ({estado}) · idioma borrador: {idioma}",
    ]
    return "\n".join(lineas)


def enviar_prospecto_dos_mensajes(lead: dict, pais: str, *, simulado: bool = False) -> bool:
    if simulado or not puede_enviar_telegram():
        return False
    from telegram_bot import enviar_texto_telegram, load_local_env

    load_local_env()
    ficha = mensaje_ficha_prospecto(lead, pais)
    idioma = idioma_para_lead(
        pais,
        idioma_web=(lead.get("idioma_web") or "").strip(),
        preferido=(lead.get("idioma") or "").strip(),
        web=lead.get("web") or "",
    )
    tipo = lead.get("tipo") or lead.get("tipo_negocio") or "tienda"
    texto2 = texto_corto_prospecto_buscar(lead.get("nombre") or "", idioma, tipo)
    enviar_texto_telegram(ficha)
    registrar_envio_telegram()
    if puede_enviar_telegram():
        enviar_texto_telegram("——— Texto para el cliente (copiar) ———\n\n" + texto2)
        registrar_envio_telegram()
    return True
