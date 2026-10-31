"""Una sola tarjeta y un solo teclado para todas las rutas de Telegram."""
from __future__ import annotations

import re

from b2b.mapas import apple_maps_url, google_maps_url, waze_url
from b2b.redactor import (
    NOMBRE_VP,
    WHOLESALE_URL,
    borrador_correo,
    borrador_corto,
    tipo_en_idioma,
    whatsapp_empresa,
)
from b2b.telefono import apto_whatsapp, formato_visible
from b2b.website import es_url_mapa

LIMITE_TELEGRAM = 4096
TIPO_TARJETA = {
    "tienda": "Shop",
    "lounge": "Lounge",
    "distribuidor": "Distributor",
    "hotel": "Hotel",
    "casino": "Casino",
    "duty_free": "Duty Free",
}


def _esc(valor: str) -> str:
    return (
        (valor or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _sin_html(texto: str) -> str:
    plano = re.sub(r"<[^>]+>", "", texto or "")
    return (
        plano.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
    )


def _token(prospecto: dict) -> str:
    token = (prospecto.get("token") or "").strip()
    if token:
        return token
    from b2b.telegram_gestion import token_callback

    return token_callback(prospecto)


def _ciudad_estado(prospecto: dict) -> str:
    from b2b.telegram_prospecto import ciudad_lead

    pais = (prospecto.get("pais") or "").strip()
    ciudad = (prospecto.get("ciudad") or "").strip() or ciudad_lead(prospecto, pais)
    estado = (prospecto.get("estado") or "").strip()
    if not estado and pais and pais.lower() not in ciudad.lower():
        estado = pais
    if ciudad and estado and ciudad.lower() != estado.lower():
        return f"{ciudad}, {estado}"
    return ciudad or estado or pais


def _telefono_visible(prospecto: dict) -> str:
    pais = (prospecto.get("pais") or prospecto.get("estado") or "").strip()
    bruto = (prospecto.get("telefono_internacional") or prospecto.get("telefono") or "").strip()
    if not bruto:
        return ""
    return formato_visible(bruto, pais) or bruto


def _web_corta(prospecto: dict) -> str:
    web = (prospecto.get("web") or "").strip()
    if not web.startswith(("http://", "https://")) or es_url_mapa(web):
        return ""
    from urllib.parse import urlparse

    host = urlparse(web).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _instagram(prospecto: dict) -> str:
    raw = (prospecto.get("instagram") or "").strip()
    if not raw:
        return ""
    hallado = re.search(r"instagram\.com/([^/?#]+)", raw, re.I)
    if hallado:
        return "@" + hallado.group(1).strip("/")
    return raw if raw.startswith("@") else raw


def _borrador(prospecto: dict) -> str:
    if (prospecto.get("cuerpo") or "").strip():
        return prospecto["cuerpo"].strip()
    nombre = prospecto.get("nombre") or "—"
    tipo = prospecto.get("tipo") or prospecto.get("tipo_negocio") or "tienda"
    idioma = (prospecto.get("idioma") or "en").strip() or "en"
    if (prospecto.get("correo") or "").strip():
        try:
            return borrador_correo(nombre, idioma, tipo)
        except Exception:
            return borrador_corto(nombre, idioma, tipo)
    return borrador_corto(nombre, idioma, tipo)


def _guiones(prospecto: dict) -> tuple[str, str]:
    idioma = "es" if (prospecto.get("idioma") or "").strip() == "es" else "en"
    tipo = prospecto.get("tipo") or prospecto.get("tipo_negocio") or "tienda"
    trato = tipo_en_idioma(tipo, idioma)
    try:
        from b2b.catalogo_check import resolver_catalogo_pdf

        url = resolver_catalogo_pdf(idioma).url
    except Exception:
        url = WHOLESALE_URL
    wa = whatsapp_empresa()
    if idioma == "es":
        llamada = (
            f"Hola, habla {NOMBRE_VP} de Cazador de Sueño Cigars. "
            f"Hacemos puros premium a mano en República Dominicana y queremos ofrecer "
            f"una muestra a su {trato}. ¿Puedo hablar con quien compra?"
        )
        sms = (
            f"Hola, Yaniris de Cazador de Sueño Cigars. Puros dominicanos hechos a mano "
            f"para su {trato}. Catálogo: {url}. WhatsApp {wa}"
        )
    else:
        llamada = (
            f"Hello, this is {NOMBRE_VP} - VP of Sales at Cazador de Sueño Cigars. "
            f"We make handmade premium cigars in the Dominican Republic and would like "
            f"to offer your {trato} a free sample. May I speak with the buyer?"
        )
        sms = (
            f"Hi, Yaniris from Cazador de Sueño Cigars. Handmade Dominican cigars for your {trato}. "
            f"Catalog: {url}. WhatsApp {wa}"
        )
    return llamada, sms


def construir_tarjeta(prospecto: dict) -> str:
    """Texto HTML de la tarjeta. Siempre incluye el borrador en un bloque copiable."""
    datos = dict(prospecto or {})
    nombre = datos.get("nombre") or "—"
    tipo = (datos.get("tipo") or datos.get("tipo_negocio") or "tienda").lower()
    etiqueta = TIPO_TARJETA.get(tipo, (tipo or "shop").title())
    lugar = _ciudad_estado(datos)
    lineas: list[str] = []
    numero = datos.get("numero_tarjeta")
    total = datos.get("tanda_total")
    if numero and total:
        cab = f"Tarjeta {numero} de {total}"
        if datos.get("tanda_etiqueta"):
            cab += f" · {datos['tanda_etiqueta']}"
        lineas.append(_esc(cab))
    if datos.get("puntaje") not in (None, ""):
        lineas.append(_esc(f"Score: {datos['puntaje']}"))
    lineas.append(f"🏪 {_esc(nombre)}")
    lineas.append(f"📋 {_esc(etiqueta)} · {_esc(lugar)}")
    direccion = (datos.get("direccion") or "").strip()
    if direccion:
        lineas.append(f"📍 {_esc(direccion)}")
    rating = datos.get("rating")
    if rating not in (None, ""):
        resenas = datos.get("user_rating_count")
        extra = f" ({resenas} reseñas)" if resenas not in (None, "") else ""
        lineas.append(_esc(f"⭐ {rating}{extra}"))
    resumen = (datos.get("resumen_verificacion") or "").strip()
    if resumen:
        lineas.append(f"✔ {_esc(resumen)}")
    telefono = _telefono_visible(datos)
    if telefono:
        lineas.append(f"📞 {_esc(telefono)}")
        if not apto_whatsapp(datos):
            lineas.append("Posible fijo: llamar")
    publicado = re.sub(r"\D", "", datos.get("whatsapp") or "")
    if len(publicado) >= 8:
        pais = (datos.get("pais") or datos.get("estado") or "").strip()
        lineas.append(f"📲 {_esc(formato_visible(publicado, pais) or ('+' + publicado))}")
    correo = (datos.get("correo") or "").strip()
    if correo:
        lineas.append(f"✉️ <code>{_esc(correo)}</code>")
    else:
        if telefono:
            lineas.append("Solo teléfono")
        else:
            lineas.append("Sin teléfono ni correo")
    web = _web_corta(datos)
    insta = _instagram(datos)
    if web:
        lineas.append(f"🌐 {_esc(web)}")
    if insta:
        lineas.append(f"📷 {_esc(insta)}")
    if not correo and telefono:
        llamada, sms = _guiones(datos)
        lineas.append("")
        lineas.append("Guion de llamada:")
        lineas.append(f"<pre>{_esc(llamada)}</pre>")
        lineas.append("SMS:")
        lineas.append(f"<pre>{_esc(sms)}</pre>")
    lineas.append("")
    lineas.append("Borrador sugerido:")
    lineas.append(f"<pre>{_esc(_borrador(datos))}</pre>")
    texto = "\n".join(lineas)
    if len(texto) > LIMITE_TELEGRAM:
        texto = texto[: LIMITE_TELEGRAM - 1] + "…"
    return texto


def texto_plano(prospecto: dict) -> str:
    return _sin_html(construir_tarjeta(prospecto))


def construir_teclado(prospecto: dict) -> dict:
    """Fila de correo/WhatsApp, fila de mapas, y Enviado + Descartar siempre."""
    datos = dict(prospecto or {})
    token = _token(datos)
    filas: list[list[dict]] = []
    contacto: list[dict] = []
    if (datos.get("correo") or "").strip():
        contacto.append({"text": "✉️ Enviar correo", "callback_data": f"b2bm:{token}"})
    if apto_whatsapp(datos):
        from b2b.telegram_prospecto import link_whatsapp
        from b2b.idioma import idioma_para_lead

        idioma = (datos.get("idioma") or "").strip() or idioma_para_lead(
            datos.get("pais") or "",
            idioma_web=(datos.get("idioma_web") or "").strip(),
            preferido=(datos.get("idioma") or "").strip(),
            web=datos.get("web") or "",
        )
        tipo = datos.get("tipo") or datos.get("tipo_negocio") or "tienda"
        try:
            corto = borrador_corto(datos.get("nombre") or "—", idioma, tipo)
        except Exception:
            corto = ""
        url = link_whatsapp(datos, corto)
        if url:
            contacto.append({"text": "📲 WhatsApp", "url": url})
    if contacto:
        filas.append(contacto)
    mapas: list[dict] = []
    for texto, url in (
        ("Google Maps", google_maps_url(datos)),
        ("Apple Maps", apple_maps_url(datos)),
        ("Waze", waze_url(datos)),
    ):
        if url:
            mapas.append({"text": texto, "url": url})
    if mapas:
        filas.append(mapas)
    filas.append(
        [
            {"text": "✅ Enviado", "callback_data": f"b2be:{token}"},
            {"text": "🗑 Descartar", "callback_data": f"b2bd:{token}"},
        ]
    )
    return {"inline_keyboard": filas}


def teclado_dudoso(prospecto: dict) -> dict:
    token = _token(prospecto)
    return {
        "inline_keyboard": [[
            {"text": "Aprobar", "callback_data": f"b2bu:{token}"},
            {"text": "Descartar", "callback_data": f"b2bd:{token}"},
        ]]
    }


def teclado_motivo(token: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "No vende cigarros", "callback_data": f"b2bq:n:{token}"},
                {"text": "Cerrado", "callback_data": f"b2bq:c:{token}"},
            ],
            [
                {"text": "Ya contactado", "callback_data": f"b2bq:y:{token}"},
                {"text": "Otro", "callback_data": f"b2bq:o:{token}"},
            ],
        ]
    }


def teclado_preview(token: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "Confirmar envío", "callback_data": f"b2bs:{token}"},
                {"text": "Editar", "callback_data": f"b2bt:{token}"},
                {"text": "Cancelar", "callback_data": f"b2bn:{token}"},
            ]
        ]
    }
