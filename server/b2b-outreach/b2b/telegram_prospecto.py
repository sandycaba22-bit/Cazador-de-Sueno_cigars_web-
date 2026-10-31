from __future__ import annotations

import json
import re
import sys
import urllib.parse
from pathlib import Path

from b2b.contacto_web import numero_whatsapp
from b2b.idioma import idioma_para_lead
from b2b.lead_score import priorizar_leads_contacto
from b2b.mapas import google_maps_url
from b2b.redactor import (
    CARGO_VP,
    EMAIL_VP_VENTAS,
    EMPRESA_FIRMA,
    NOMBRE_VP,
    OPT_OUT,
    asunto_correo,
    borrador_corto,
    whatsapp_empresa,
)
from b2b.telegram_control import puede_enviar_telegram, registrar_envio_telegram
from b2b.website import es_url_mapa
from b2b.telegram_gestion import (
    puede_avisar_prospecto,
    registrar_pendiente,
    tiene_medio_contacto,
    token_callback,
    ya_gestionado_telegram,
)

LIMITE_TELEGRAM = 4096
TIPO_TARJETA = {
    "tienda": "Shop",
    "lounge": "Lounge",
    "distribuidor": "Distributor",
    "hotel": "Hotel",
    "casino": "Casino",
    "duty_free": "Duty Free",
}
_RE_ESTADO_ZIP = re.compile(r"^[A-Z]{2}(\s+\d{5}(-\d{4})?)?$")
_RE_ZIP = re.compile(r"^\d{5}(-\d{4})?$")


def _maps_url(lead: dict) -> str:
    return google_maps_url(lead)


def ciudad_lead(lead: dict, pais: str = "") -> str:
    """Ciudad para la tarjeta: campo ciudad o último tramo útil de la dirección."""
    if (lead.get("ciudad") or "").strip():
        return lead["ciudad"].strip()
    dir_ = (lead.get("direccion") or "").strip()
    if not dir_:
        return (pais or lead.get("pais") or "").strip()
    partes = [p.strip() for p in dir_.replace("\n", ",").split(",") if p.strip()]
    pais_l = (pais or lead.get("pais") or "").strip().lower()
    alias_pais = {pais_l, "united states", "usa", "u.s.a.", "us", "ee.uu.", "eeuu"}
    if partes and partes[-1].strip().lower() in alias_pais:
        partes = partes[:-1]
    if not partes:
        return (pais or "").strip()
    last = partes[-1]
    if _RE_ESTADO_ZIP.fullmatch(last) or _RE_ZIP.fullmatch(last):
        return partes[-2] if len(partes) >= 2 else last
    return last


def estado_contacto(lead: dict) -> str:
    tel = bool((lead.get("telefono") or lead.get("whatsapp") or "").strip())
    mail = bool((lead.get("correo") or "").strip())
    if tel and mail:
        return "Teléfono y correo confirmados"
    if tel:
        return "Teléfono confirmado"
    if mail:
        return "Correo confirmado"
    return "Sin teléfono ni correo"


MAX_URL_BOTON = 1900


def link_whatsapp(lead: dict, borrador: str) -> str:
    num = numero_whatsapp(lead)
    if not num:
        return ""
    url = f"https://wa.me/{num}?text={urllib.parse.quote(borrador)}"
    # Si el texto no cabe en un botón, se abre el chat sin texto (el borrador está en el mensaje).
    return url if len(url) <= MAX_URL_BOTON else f"https://wa.me/{num}"


def _whatsapp_visible(lead: dict) -> str:
    """Línea 'WhatsApp: …' con el origen del número, sin inventar nada."""
    publicado = re.sub(r"\D", "", lead.get("whatsapp") or "")
    if len(publicado) >= 8:
        return f"📲 WhatsApp: +{publicado} (publicado en su web)"
    num = numero_whatsapp(lead)
    if num:
        return f"📲 WhatsApp: +{num} (número de Google; confirmar si es celular)"
    return ""


def _idioma_lead(lead: dict, pais: str) -> str:
    return idioma_para_lead(
        pais,
        idioma_web=(lead.get("idioma_web") or "").strip(),
        preferido=(lead.get("idioma") or "").strip(),
        web=lead.get("web") or "",
    )


def cuerpo_mailto(nombre: str, idioma: str, tipo: str) -> str:
    corto = borrador_corto(nombre, idioma, tipo)
    firma = (
        f"{NOMBRE_VP}\n{CARGO_VP.get(idioma, CARGO_VP['en'])}\n{EMPRESA_FIRMA}\n"
        f"{EMAIL_VP_VENTAS}\nWhatsApp {whatsapp_empresa()}"
    )
    opt = OPT_OUT.get(idioma, OPT_OUT["en"])
    return f"{corto}\n\n{firma}\n\n{opt}"


def link_mailto(lead: dict, pais: str) -> str:
    correo = (lead.get("correo") or "").strip()
    if not correo or "@" not in correo:
        return ""
    nombre = lead.get("nombre") or "—"
    tipo = lead.get("tipo") or lead.get("tipo_negocio") or "tienda"
    idioma = _idioma_lead(lead, pais)
    asunto = urllib.parse.quote(asunto_correo(nombre, idioma))
    cuerpo = urllib.parse.quote(cuerpo_mailto(nombre, idioma, tipo))
    url = f"mailto:{correo}?subject={asunto}&body={cuerpo}"
    return url if len(url) <= MAX_URL_BOTON else f"mailto:{correo}?subject={asunto}"


def _calificacion(lead: dict) -> str:
    rating = lead.get("rating")
    if rating in (None, ""):
        return ""
    resenas = lead.get("user_rating_count")
    extra = f" ({resenas} reseñas)" if resenas not in (None, "") else ""
    return f"⭐ {rating}{extra}"


def datos_contacto(lead: dict) -> list[str]:
    """Líneas con todo lo verificable del negocio; solo aparece lo que el lead realmente trae."""
    lineas = []
    for linea in (
        _calificacion(lead),
        f"🗺 {lead['direccion'].strip()}" if (lead.get("direccion") or "").strip() else "",
        f"📞 Tel: {lead['telefono'].strip()}" if (lead.get("telefono") or "").strip() else "",
        _whatsapp_visible(lead),
        f"✉️ Correo: {lead['correo'].strip()}" if (lead.get("correo") or "").strip() else "",
        f"🌐 Web: {lead['web'].strip()}" if (lead.get("web") or "").strip() else "",
        f"📷 Instagram: {lead['instagram'].strip()}" if (lead.get("instagram") or "").strip() else "",
        f"👍 Facebook: {lead['facebook'].strip()}" if (lead.get("facebook") or "").strip() else "",
        f"📝 Formulario: {lead['formulario'].strip()}" if (lead.get("formulario") or "").strip() else "",
    ):
        if linea:
            lineas.append(linea)
    return lineas


def _web_corta(lead: dict) -> str:
    web = (lead.get("web") or "").strip()
    if not web.startswith(("http://", "https://")):
        return ""
    host = urllib.parse.urlparse(web).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _instagram_corto(lead: dict) -> str:
    raw = (lead.get("instagram") or "").strip()
    if not raw:
        return ""
    hallado = re.search(r"instagram\.com/([^/?#]+)", raw, re.I)
    if hallado:
        return "@" + hallado.group(1).strip("/")
    return raw if raw.startswith("@") else raw


def _linea_verificacion(lead: dict, pais: str) -> str:
    resumen = (lead.get("resumen_verificacion") or "").strip()
    if resumen:
        return f"✔ {resumen}"
    partes = []
    rating = lead.get("rating")
    if rating not in (None, ""):
        resenas = lead.get("user_rating_count")
        extra = f" ({resenas})" if resenas not in (None, "") else ""
        partes.append(f"⭐ {rating}{extra}")
    if (lead.get("telefono") or "").strip():
        partes.append("Tel")
    if (lead.get("correo") or "").strip():
        partes.append("Correo")
    if partes:
        return "✔ " + " · ".join(partes)
    return ""


def _rellenar_correo(lead: dict) -> None:
    if lead.get("cuerpo_editado"):
        lead["cuerpo"] = lead["cuerpo_editado"]
        if not lead.get("asunto"):
            from b2b.redactor import asunto_correo

            lead["asunto"] = asunto_correo(
                lead.get("nombre") or "",
                lead.get("idioma") or "en",
                lead.get("asunto_variante") or "A",
            )
        return
    if lead.get("asunto") and lead.get("cuerpo"):
        return
    from b2b.envio_correo import preparar_cuerpo

    idioma = lead.get("idioma") or "en"
    lead.setdefault("idioma", idioma)
    if not lead.get("asunto_variante"):
        from b2b.telegram_gestion import token_callback

        lead["asunto_variante"] = "A" if int(token_callback(lead), 16) % 2 == 0 else "B"
    cuenta = ""
    try:
        from b2b.envio_correo import elegir_cuenta

        elegida = elegir_cuenta()
        if elegida:
            cuenta = elegida["correo"]
    except Exception:
        cuenta = ""
    asunto, cuerpo, variante = preparar_cuerpo(lead, cuenta)
    lead["asunto"] = asunto
    lead["cuerpo"] = cuerpo
    lead["asunto_variante"] = variante


def mensaje_prospecto_completo(lead: dict, pais: str) -> str:
    from b2b.tarjeta import construir_tarjeta

    lead.setdefault("pais", pais)
    lead.setdefault("idioma", _idioma_lead(lead, pais))
    if (lead.get("correo") or "").strip():
        try:
            _rellenar_correo(lead)
        except Exception:
            pass
    return construir_tarjeta(lead)


def texto_con_estado(texto: str, linea: str) -> str:
    partes = (texto or "").split("\n", 1)
    resto = partes[1] if len(partes) > 1 else ""
    # Quita un estado previo pegado en la segunda línea.
    if resto.startswith(("⏳", "📤", "⚠️", "🗑", "⏭")):
        resto = resto.split("\n", 1)[1] if "\n" in resto else ""
    return partes[0] + "\n" + linea + ("\n" + resto if resto else "")


def teclado_prospecto(lead: dict, pais: str, token: str) -> dict:
    from b2b.tarjeta import construir_teclado

    datos = dict(lead)
    datos["token"] = token
    datos.setdefault("pais", pais or lead.get("pais") or "")
    return construir_teclado(datos)


def teclado_en_cola(lead: dict, token: str) -> dict:
    filas: list[list[dict]] = [
        [{"text": "↩️ Cancelar envío", "callback_data": f"b2bx:{token}"}],
    ]
    contacto: list[dict] = []
    web = (lead.get("web") or "").strip()
    mapa = _maps_url(lead)
    if web.startswith(("http://", "https://")) and not es_url_mapa(web):
        contacto.append({"text": "🌐 Web", "url": web})
    if mapa:
        contacto.append({"text": "📍 Mapa", "url": mapa})
    if contacto:
        filas.append(contacto)
    return {"inline_keyboard": filas}


def teclado_cerrado() -> dict:
    return {"inline_keyboard": []}


def _teclado_prospecto(token: str, lead: dict | None = None, pais: str = "") -> dict:
    """Compatibilidad: teclado con gestión; si hay lead, añade wa.me / mailto / Maps."""
    if lead:
        return teclado_prospecto(lead, pais or lead.get("pais") or "", token)
    return {
        "inline_keyboard": [
            [
                {"text": "Enviado", "callback_data": f"b2be:{token}"},
                {"text": "Descartar", "callback_data": f"b2bd:{token}"},
            ]
        ]
    }


def _registrar_fallo_telegram(lead: dict, exc: BaseException) -> None:
    from b2b.logging_ops import registrar_evento

    registrar_evento(
        {
            "evento": "telegram_prospecto_fallo",
            "nombre": lead.get("nombre") or "",
            "error": str(exc)[:400],
        }
    )
    print(f"Telegram no envió {lead.get('nombre') or 'prospecto'}: {exc}", file=sys.stderr)


def enviar_prospecto_telegram(
    lead: dict,
    pais: str,
    *,
    simulado: bool = False,
    inbox_path: str = "",
) -> bool:
    if not puede_avisar_prospecto(lead) and not tiene_medio_contacto(lead):
        return False
    if ya_gestionado_telegram(lead) or lead.get("telegram_notificado"):
        return False

    lead = dict(lead)
    lead.setdefault("pais", pais)
    if not simulado and not (lead.get("correo") or "").strip():
        try:
            from b2b.contacto_web import completar_correo

            completar_correo(lead)
        except Exception:
            pass
    texto = mensaje_prospecto_completo(lead, pais)
    token = token_callback(lead)

    if simulado:
        teclado = teclado_prospecto(lead, pais, token)
        etiquetas = [btn.get("text") or "" for fila in teclado["inline_keyboard"] for btn in fila]
        print("=== TELEGRAM SIMULADO (prospecto) ===", file=sys.stderr)
        print(texto, file=sys.stderr)
        print("[Botones: " + " | ".join(etiquetas) + "]", file=sys.stderr)
        print("=== fin ===", file=sys.stderr)
        return True

    if not puede_enviar_telegram():
        return False

    from telegram_bot import TelegramFormatError, enviar_mensaje_telegram, load_local_env

    load_local_env()
    registrar_pendiente(token, lead, inbox_path)
    teclado = teclado_prospecto(lead, pais, token)
    try:
        try:
            message_id = enviar_mensaje_telegram(texto, reply_markup=teclado, parse_mode="HTML")
        except TelegramFormatError:
            from b2b.tarjeta import _sin_html

            message_id = enviar_mensaje_telegram(_sin_html(texto), reply_markup=teclado)
    except Exception as exc:
        _registrar_fallo_telegram(lead, exc)
        return False
    from b2b.telegram_gestion import actualizar_pendiente

    actualizar_pendiente(token, message_id=message_id, texto_tarjeta=texto, cuerpo=lead.get("cuerpo") or "", asunto=lead.get("asunto") or "")
    registrar_envio_telegram()
    return True


def reintentar_avisos_cola(cola_dir: Path, *, simulado: bool = False) -> int:
    """Reintenta avisos que no salieron. Un 401 no mueve el lead a failed ni aborta."""
    inbox = cola_dir / "inbox"
    failed = cola_dir / "failed"
    inbox.mkdir(parents=True, exist_ok=True)
    if failed.is_dir():
        for path in list(failed.glob("*.json")):
            dest = inbox / path.name
            if dest.exists():
                dest = inbox / f"reintento-{path.name}"
            try:
                path.replace(dest)
            except OSError as exc:
                _registrar_fallo_telegram({"nombre": path.name}, exc)
            nota = Path(str(path) + ".error.txt")
            if nota.is_file():
                try:
                    nota.unlink()
                except OSError:
                    pass
    enviados = 0
    pendientes: list[tuple[Path, dict]] = []
    for path in sorted(inbox.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or data.get("telegram_notificado"):
            continue
        pendientes.append((path, data))
    ordenados = priorizar_leads_contacto([d for _, d in pendientes])
    por_id = {id(d): p for p, d in pendientes}
    for data in ordenados:
        path = por_id[id(data)]
        if ya_gestionado_telegram(data):
            data["telegram_notificado"] = True
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            continue
        pais = (data.get("pais") or "").strip()
        try:
            ok = enviar_prospecto_telegram(data, pais, simulado=simulado, inbox_path=str(path))
        except Exception as exc:
            _registrar_fallo_telegram(data, exc)
            continue
        if not ok:
            continue
        data["telegram_notificado"] = True
        data.pop("telegram_error", None)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        enviados += 1
    return enviados


# Compatibilidad con código anterior
def enviar_prospecto_dos_mensajes(lead: dict, pais: str, *, simulado: bool = False) -> bool:
    return enviar_prospecto_telegram(lead, pais, simulado=simulado)
