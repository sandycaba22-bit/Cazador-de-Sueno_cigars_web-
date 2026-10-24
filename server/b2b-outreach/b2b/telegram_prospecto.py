from __future__ import annotations

import json
import re
import sys
import urllib.parse
from pathlib import Path

from b2b.contacto_web import numero_whatsapp
from b2b.idioma import idioma_para_lead
from b2b.lead_score import priorizar_leads_contacto
from b2b.redactor import (
    CARGO_VP,
    EMAIL_VP_VENTAS,
    EMPRESA_FIRMA,
    NOMBRE_VP,
    OPT_OUT,
    asunto_correo,
    borrador_corto,
)
from b2b.telegram_control import puede_enviar_telegram, pausa_entre_mensajes, registrar_envio_telegram
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
    url = (lead.get("maps_url") or "").strip()
    if url:
        return url
    web = (lead.get("web") or "").strip()
    return web if es_url_mapa(web) else ""


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


def link_whatsapp(lead: dict, borrador: str) -> str:
    num = numero_whatsapp(lead)
    if not num:
        return ""
    return f"https://wa.me/{num}?text={urllib.parse.quote(borrador)}"


def _idioma_lead(lead: dict, pais: str) -> str:
    return idioma_para_lead(
        pais,
        idioma_web=(lead.get("idioma_web") or "").strip(),
        preferido=(lead.get("idioma") or "").strip(),
        web=lead.get("web") or "",
    )


def cuerpo_mailto(nombre: str, idioma: str, tipo: str) -> str:
    corto = borrador_corto(nombre, idioma, tipo)
    firma = f"{NOMBRE_VP}\n{CARGO_VP.get(idioma, CARGO_VP['en'])}\n{EMPRESA_FIRMA}\n{EMAIL_VP_VENTAS}"
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
    return f"mailto:{correo}?subject={asunto}&body={cuerpo}"


def mensaje_prospecto_completo(lead: dict, pais: str) -> str:
    nombre = lead.get("nombre") or "—"
    tipo = lead.get("tipo") or lead.get("tipo_negocio") or "tienda"
    etiqueta = TIPO_TARJETA.get((tipo or "").lower(), "Shop")
    ciudad = ciudad_lead(lead, pais) or pais
    idioma = _idioma_lead(lead, pais)
    corto = borrador_corto(nombre, idioma, tipo)
    partes = [
        f"🏪 {nombre}",
        f"📋 {etiqueta} · {ciudad}",
        f"📡 {estado_contacto(lead)}",
        "",
        corto,
    ]
    texto = "\n".join(partes)
    if len(texto) > LIMITE_TELEGRAM:
        texto = texto[: LIMITE_TELEGRAM - 10] + "\n…"
    return texto


def teclado_prospecto(lead: dict, pais: str, token: str) -> dict:
    acciones: list[dict] = []
    tipo = lead.get("tipo") or lead.get("tipo_negocio") or "tienda"
    idioma = _idioma_lead(lead, pais)
    corto = borrador_corto(lead.get("nombre") or "—", idioma, tipo)
    wa = link_whatsapp(lead, corto)
    mail = link_mailto(lead, pais)
    maps = _maps_url(lead)
    if wa:
        acciones.append({"text": "📲 Enviar WhatsApp", "url": wa})
    if mail:
        acciones.append({"text": "✉️ Enviar Correo", "url": mail})
    if maps:
        acciones.append({"text": "📍 Google Maps", "url": maps})
    filas: list[list[dict]] = []
    if acciones:
        filas.append(acciones)
    filas.append(
        [
            {"text": "Enviado", "callback_data": f"b2be:{token}"},
            {"text": "Descartar", "callback_data": f"b2bd:{token}"},
        ]
    )
    return {"inline_keyboard": filas}


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

    from telegram_bot import enviar_mensaje_telegram, load_local_env

    load_local_env()
    registrar_pendiente(token, lead, inbox_path)
    try:
        enviar_mensaje_telegram(texto, reply_markup=teclado_prospecto(lead, pais, token))
    except Exception as exc:
        _registrar_fallo_telegram(lead, exc)
        return False
    registrar_envio_telegram()
    pausa_entre_mensajes()
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
