from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from b2b.paths import state_file

CONTROL_PATH = state_file("telegram_control.json")

USPS_ESTADOS = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming",
}
MERCADOS_ACTIVOS = {nombre.casefold(): nombre for nombre in USPS_ESTADOS.values()}
MERCADOS_ACTIVOS.update({"puerto rico": "Puerto Rico", "jamaica": "Jamaica"})


def mercado_canonico(nombre: str) -> str:
    nombre = (nombre or "").strip()
    return USPS_ESTADOS.get(nombre.upper()) or MERCADOS_ACTIVOS.get(nombre.casefold(), "")


def _pendientes_activos() -> dict:
    from b2b.telegram_gestion import _load_pendientes

    return {
        key: {**lead, "pais": mercado_canonico(lead.get("pais"))}
        for key, lead in _load_pendientes().items()
        if isinstance(lead, dict) and mercado_canonico(lead.get("pais"))
    }


def _load() -> dict:
    if not CONTROL_PATH.is_file():
        return {"pausado": False, "envios_hora": []}
    try:
        return json.loads(CONTROL_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"pausado": False, "envios_hora": []}


def _save(data: dict) -> None:
    CONTROL_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONTROL_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def esta_pausado() -> bool:
    return bool(_load().get("pausado"))


def set_pausado(valor: bool) -> None:
    data = _load()
    data["pausado"] = valor
    _save(data)


def _limite_por_hora() -> int:
    try:
        return max(1, int(os.getenv("B2B_TELEGRAM_MAX_POR_HORA", "30") or "30"))
    except ValueError:
        return 30


def pausa_entre_mensajes() -> None:
    try:
        sec = float(os.getenv("B2B_TELEGRAM_PAUSE_SEC", "4") or "4")
    except ValueError:
        sec = 4.0
    if sec > 0:
        time.sleep(sec)


def _podar_envios(data: dict) -> dict:
    ahora = time.time()
    ventana = [t for t in data.get("envios_hora") or [] if ahora - float(t) < 3600]
    data["envios_hora"] = ventana
    return data


def puede_enviar_telegram() -> bool:
    if esta_pausado():
        return False
    data = _podar_envios(_load())
    _save(data)
    return len(data.get("envios_hora") or []) < _limite_por_hora()


def registrar_envio_telegram() -> None:
    data = _podar_envios(_load())
    data.setdefault("envios_hora", []).append(time.time())
    _save(data)


def _telegram_post(token: str, method: str, payload: dict) -> dict | None:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None


def _cerrar_botones(token: str, chat_id: str, cb: dict) -> None:
    cb_id = cb.get("id")
    if cb_id:
        _telegram_post(token, "answerCallbackQuery", {"callback_query_id": cb_id})
    msg_id = (cb.get("message") or {}).get("message_id")
    if msg_id:
        _telegram_post(
            token,
            "editMessageReplyMarkup",
            {"chat_id": chat_id, "message_id": msg_id, "reply_markup": {"inline_keyboard": []}},
        )


def _manejar_solicitud_precio(token: str, chat_id: str, cb: dict, data: str) -> str | None:
    cid = str((cb.get("message") or {}).get("chat", {}).get("id", ""))
    if cid != str(chat_id):
        return None
    estado = "aprobado" if data.startswith("b2ba:") else "rechazado"
    solicitud_id = data.split(":", 1)[-1]
    from b2b.supabase_client import actualizar_solicitud

    guardado = actualizar_solicitud(solicitud_id, estado)
    _cerrar_botones(token, chat_id, cb)
    etiqueta = "✅ Acceso aprobado" if estado == "aprobado" else "🗑 Acceso rechazado"
    if not guardado:
        return f"{etiqueta} ({solicitud_id}). Supabase no confirmó el cambio."
    return f"{etiqueta} ({solicitud_id})."


def _answer(token: str, cb: dict, texto: str) -> None:
    cb_id = cb.get("id")
    if cb_id:
        _telegram_post(
            token,
            "answerCallbackQuery",
            {"callback_query_id": cb_id, "text": (texto or "")[:180]},
        )


def _editar_tarjeta(token: str, chat_id: str, message_id, texto: str, markup: dict | None) -> None:
    if not message_id:
        return
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": (texto or "")[:4096],
        "disable_web_page_preview": True,
    }
    if markup is not None:
        payload["reply_markup"] = markup
    if "<pre>" in (texto or "") or "<code>" in (texto or ""):
        payload["parse_mode"] = "HTML"
    _telegram_post(token, "editMessageText", payload)


def _lead_de_pendiente(pend: dict) -> dict:
    lead = dict(pend)
    lead.setdefault("nombre", pend.get("nombre") or "")
    lead.setdefault("web", pend.get("web") or "")
    lead.setdefault("pais", pend.get("pais") or "")
    return lead


def _manejar_callback(token: str, chat_id: str, cb: dict) -> str | None:
    from b2b.despachador_tarjetas import anotar_decision, cerrar_tarjeta, posponer
    from b2b.envio_correo import cancelar_envio, encolar_envio, puede_enviar_correo
    from b2b.leads_store import guardar_estado_lead
    from b2b.telegram_gestion import (
        actualizar_pendiente,
        agregar_no_contactar,
        marcar_gestionado_telegram,
        resolver_pendiente,
    )
    from b2b.telegram_prospecto import teclado_cerrado, teclado_en_cola, teclado_prospecto, texto_con_estado

    data = (cb.get("data") or "").strip()
    if data.startswith("b2ba:"):
        return _manejar_solicitud_precio(token, chat_id, cb, data)
    if data.startswith("b2bx:"):
        tok = data.split(":", 1)[-1]
        if cancelar_envio(tok):
            _answer(token, cb, "Envío cancelado")
            pend = resolver_pendiente(tok) or {}
            lead = _lead_de_pendiente(pend)
            texto = texto_con_estado(pend.get("texto_tarjeta") or lead.get("nombre") or "—", "↩️ Envío cancelado")
            msg_id = (cb.get("message") or {}).get("message_id") or pend.get("message_id")
            _editar_tarjeta(token, chat_id, msg_id, texto, teclado_prospecto(lead, lead.get("pais") or "", tok))
            actualizar_pendiente(tok, estado_envio="cancelado", texto_tarjeta=texto)
            return f"↩️ Cancelado: {lead.get('nombre') or '—'}"
        return _manejar_solicitud_precio(token, chat_id, cb, data)
    if not data.startswith("b2b"):
        return None
    cid = str((cb.get("message") or {}).get("chat", {}).get("id", ""))
    if cid != str(chat_id):
        return None
    if data.startswith("b2bq:") and data.count(":") >= 2:
        tok = data.split(":")[-1]
    else:
        tok = data.split(":", 1)[-1] if ":" in data else ""
    if not tok:
        return None
    pend = resolver_pendiente(tok) or {}
    lead = _lead_de_pendiente(pend)
    msg_id = (cb.get("message") or {}).get("message_id") or pend.get("message_id")
    base = pend.get("texto_tarjeta") or ""

    if data.startswith("b2bm:"):
        from b2b.envio_correo import preparar_cuerpo
        from b2b.tarjeta import teclado_preview

        cuenta = ""
        try:
            from b2b.envio_correo import elegir_cuenta

            elegida = elegir_cuenta()
            if elegida:
                cuenta = elegida["correo"]
        except Exception:
            cuenta = ""
        try:
            asunto, cuerpo, _variante = preparar_cuerpo(lead, cuenta)
        except Exception as exc:
            _answer(token, cb, "No pude armar el correo")
            return f"⚠️ No pude armar el correo: {exc}"
        preview = (
            f"Para: {lead.get('correo') or '—'}\n"
            f"De: {cuenta or '(sin cuenta configurada)'}\n"
            f"Asunto: {asunto}\n\n"
            f"{cuerpo}"
        )
        _answer(token, cb, "Vista previa")
        _telegram_post(token, "sendMessage", {
            "chat_id": chat_id,
            "text": preview[:4096],
            "reply_markup": teclado_preview(tok),
        })
        actualizar_pendiente(tok, asunto=asunto, cuerpo=cuerpo, espera="")
        return None

    if data.startswith("b2bn:"):
        cancelar_envio(tok)
        _answer(token, cb, "Cancelado")
        actualizar_pendiente(tok, estado_envio="", espera="")
        return "Cancelado. No se envió el correo."

    if data.startswith("b2bs:"):
        if pend.get("estado_envio") in ("en_cola", "enviado"):
            _answer(token, cb, "Ya está en cola")
            return "Ya está en cola o enviado."
        from b2b.envio_correo import enviar_confirmado

        resultado = enviar_confirmado(lead, tok)
        _answer(token, cb, (resultado or "Listo")[:180])
        if resultado.startswith("✅") or resultado.startswith("⏳") or "B2B_ENVIO_REAL=0" in resultado:
            texto = texto_con_estado(base or lead.get("nombre") or "—", resultado.split("\n", 1)[0][:180])
            markup = teclado_en_cola(lead, tok) if resultado.startswith("⏳") else teclado_cerrado()
            _editar_tarjeta(token, chat_id, msg_id, texto, markup)
            estado = "en_cola" if resultado.startswith("⏳") else "enviado"
            actualizar_pendiente(tok, estado_envio=estado, texto_tarjeta=texto)
            if estado == "enviado":
                guardar_estado_lead(lead, "enviado", canal="correo")
                from b2b.seguimiento import registrar_enviado

                registrar_enviado(lead, "correo")
                anotar_decision(lead, "aprobadas")
                cerrar_tarjeta(tok)
        return resultado

    if data.startswith("b2bt:"):
        _answer(token, cb, "Respóndeme a este mensaje con el cuerpo nuevo")
        actualizar_pendiente(tok, espera="cuerpo")
        return "Respóndeme a este mensaje con el cuerpo nuevo"

    if data.startswith("b2bl:"):
        resultado = posponer(tok, pend.get("inbox_path") or "", )
        if resultado == "limite":
            _answer(token, cb, "Ya se pospuso 2 veces")
            return "Ya se pospuso 2 veces. Aprueba o descarta."
        _answer(token, cb, "Al final de la cola")
        texto = texto_con_estado(base or lead.get("nombre") or "—", "⏭ Más tarde")
        _editar_tarjeta(token, chat_id, msg_id, texto, teclado_cerrado())
        actualizar_pendiente(tok, estado_envio="despues", texto_tarjeta=texto)
        return None

    if data.startswith("b2bq:"):
        from b2b.telegram_dudosos import MOTIVOS, avanzar, guardar_motivo

        partes = data.split(":")
        codigo = partes[1] if len(partes) > 2 else ""
        motivo = guardar_motivo(lead, codigo)
        _answer(token, cb, motivo)
        _editar_tarjeta(
            token, chat_id, msg_id,
            texto_con_estado(base or (lead.get("nombre") or "—"), f"🗑 {motivo}"),
            teclado_cerrado(),
        )
        from b2b.telegram_dudosos import _load as _load_dudosos

        if tok in (_load_dudosos().get("pendientes") or []):
            siguiente_tok, siguiente = avanzar()
            if siguiente_tok and siguiente:
                _enviar_dudoso(token, chat_id, siguiente_tok, siguiente)
        return f"Motivo guardado: {MOTIVOS.get(codigo, motivo)}"

    if data.startswith("b2bu:"):
        from b2b.telegram_dudosos import avanzar, aprobar

        nombre = aprobar(lead)
        _answer(token, cb, "Aprobado")
        _editar_tarjeta(
            token, chat_id, msg_id,
            texto_con_estado(base or nombre, "✅ Aprobado, pasa a la cola"),
            teclado_cerrado(),
        )
        siguiente_tok, siguiente = avanzar()
        if siguiente_tok and siguiente:
            _enviar_dudoso(token, chat_id, siguiente_tok, siguiente)
        return f"Aprobado: {nombre}. Entra en la cola normal."

    if data.startswith("b2bd:"):
        from b2b.tarjeta import teclado_motivo

        marcar_gestionado_telegram(lead, "descartado")
        agregar_no_contactar(lead.get("nombre") or "", lead.get("web") or "", motivo="telegram_descartar")
        guardar_estado_lead(lead, "descartado")
        anotar_decision(lead, "descartadas")
        cerrar_tarjeta(tok)
        _answer(token, cb, "Descartado")
        texto = texto_con_estado(base or (lead.get("nombre") or "—"), "🗑 Descartado")
        _editar_tarjeta(token, chat_id, msg_id, texto, teclado_cerrado())
        _telegram_post(token, "sendMessage", {
            "chat_id": chat_id,
            "text": f"¿Por qué descartamos {lead.get('nombre') or 'este negocio'}?",
            "reply_markup": teclado_motivo(tok),
        })
        return f"🗑 Descartado: {lead.get('nombre') or '—'}"

    if data.startswith("b2be:"):
        from b2b.seguimiento import registrar_enviado

        marcar_gestionado_telegram(lead, "enviado")
        canal = "correo" if pend.get("estado_envio") == "enviado" else (
            "whatsapp" if (lead.get("telefono") or lead.get("whatsapp")) else "manual"
        )
        guardar_estado_lead(lead, "enviado", canal=canal)
        registrar_enviado(lead, canal)
        cerrar_tarjeta(tok)
        _answer(token, cb, "Marcado enviado")
        texto = texto_con_estado(base or (lead.get("nombre") or "—"), f"📤 Enviado por {canal}")
        _editar_tarjeta(token, chat_id, msg_id, texto, teclado_cerrado())
        return f"✅ Enviado: {lead.get('nombre') or '—'} ({canal})"
    return None


def _enviar_dudoso(token: str, chat_id: str, tok: str, lead: dict) -> None:
    from b2b.tarjeta import construir_tarjeta, teclado_dudoso

    datos = dict(lead)
    datos["token"] = tok
    _telegram_post(token, "sendMessage", {
        "chat_id": chat_id,
        "text": construir_tarjeta(datos)[:4096],
        "parse_mode": "HTML",
        "reply_markup": teclado_dudoso(datos),
    })


def _manejar_respuesta(token: str, chat_id: str, message_id, texto: str) -> str | None:
    from b2b.envio_correo import correo_valido
    from b2b.redactor import asegurar_pie
    from b2b.telegram_gestion import actualizar_pendiente, pendiente_por_mensaje
    from b2b.telegram_prospecto import mensaje_prospecto_completo, teclado_prospecto

    tok, pend = pendiente_por_mensaje(message_id)
    if not tok or not pend:
        return None
    lead = _lead_de_pendiente(pend)
    bruto = (texto or "").strip()
    if pend.get("espera") == "cuerpo" or (len(bruto) > 40 and "@" not in bruto.split()[0]):
        idioma = lead.get("idioma") or "en"
        cuerpo = asegurar_pie(bruto, idioma)
        lead["cuerpo_editado"] = cuerpo
        lead["cuerpo"] = cuerpo
        lead["asunto"] = pend.get("asunto") or lead.get("asunto")
        nuevo = mensaje_prospecto_completo(lead, lead.get("pais") or "")
        _editar_tarjeta(token, chat_id, message_id, nuevo, teclado_prospecto(lead, lead.get("pais") or "", tok))
        actualizar_pendiente(tok, cuerpo=cuerpo, cuerpo_editado=cuerpo, texto_tarjeta=nuevo, espera="")
        return "Texto actualizado. La dirección y la baja quedan en el correo."
    if correo_valido(bruto):
        lead["correo"] = bruto
        lead["fuente_correo"] = "manual_telegram"
        lead["sin_correo_publico"] = False
        nuevo = mensaje_prospecto_completo(lead, lead.get("pais") or "")
        _editar_tarjeta(token, chat_id, message_id, nuevo, teclado_prospecto(lead, lead.get("pais") or "", tok))
        actualizar_pendiente(
            tok,
            correo=bruto,
            fuente_correo="manual_telegram",
            texto_tarjeta=nuevo,
            cuerpo=lead.get("cuerpo") or "",
            asunto=lead.get("asunto") or "",
        )
        return f"Correo guardado: {bruto}"
    return None


def procesar_comandos_chat(token: str, chat_id: str) -> list[str]:
    """Lee updates: /pausa, /seguir, /estado, /stats, /pendientes y botones Enviado/Descartar."""
    data = _load()
    offset = int(data.get("update_offset") or 0)
    url = f"https://api.telegram.org/bot{token}/getUpdates?timeout=1&limit=10&offset={offset}"
    acks: list[str] = []
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return acks
    for upd in body.get("result") or []:
        uid = int(upd.get("update_id") or 0)
        if uid >= offset:
            data["update_offset"] = uid + 1
        cb = upd.get("callback_query")
        if cb:
            ack = _manejar_callback(token, chat_id, cb)
            if ack:
                acks.append(ack)
            continue
        msg = upd.get("message") or {}
        raw = (msg.get("text") or "").strip()
        text = raw.lower()
        cid = str(msg.get("chat", {}).get("id", ""))
        if cid != str(chat_id):
            continue
        reply = msg.get("reply_to_message") or {}
        if reply.get("message_id") and raw and not raw.startswith("/"):
            ack = _manejar_respuesta(token, chat_id, reply.get("message_id"), raw)
            if ack:
                acks.append(ack)
            continue

        if text in ("/pausa", "pausa"):
            set_pausado(True)
            acks.append("⏸ Tarjetas y envíos pausados (/seguir para reanudar).")
        elif text in ("/seguir", "seguir", "/resume"):
            set_pausado(False)
            acks.append("▶️ Tarjetas y envíos reanudados.")
        elif text in ("/cola",):
            from b2b.despachador_tarjetas import texto_cola
            from b2b.paths import queue_dir

            cola = queue_dir() or state_file("x").parent
            acks.append(texto_cola(cola))
        elif text.startswith("/ritmo"):
            from b2b.despachador_tarjetas import set_ritmo

            partes = text.split()
            if len(partes) == 2 and partes[1] in ("1", "2", "3"):
                n = set_ritmo(int(partes[1]))
                acks.append(f"Ritmo: {n} tarjeta(s) abierta(s).")
            else:
                acks.append("Usa /ritmo 1, /ritmo 2 o /ritmo 3.")
        elif text in ("/siguiente",):
            from b2b.despachador_tarjetas import forzar_siguiente

            forzar_siguiente()
            acks.append("Sale la siguiente tarjeta.")
        elif text == "/pendientes":
            from b2b.despachador_tarjetas import forzar_siguiente

            pend = _pendientes_activos()
            forzar_siguiente()
            acks.append(
                f"📋 Tienes {len(pend)} leads pendientes (mercados retirados excluidos). "
                "La siguiente tarjeta sale con los mismos botones."
            )
        elif text == "/dudosos":
            from b2b.telegram_dudosos import actual, preparar_tanda

            data_d = preparar_tanda()
            tok_d, lead_d = actual(data_d)
            total = len(data_d.get("pendientes") or [])
            if not tok_d or not lead_d:
                acks.append("No hay dudosos en la carpeta de la cola.")
            else:
                _enviar_dudoso(token, chat_id, tok_d, lead_d)
                acks.append(f"Dudosos: {total} en esta tanda. Sale el primero; el siguiente, al aprobar o descartar.")
        elif text in ("/prueba_correo", "/prueba-correo"):
            from b2b.envio_correo import prueba_correo_cuentas

            acks.append(prueba_correo_cuentas())
        elif text == "/stats":
            pend = _pendientes_activos()
            stats = {}
            for p in pend.values():
                pais = p.get("pais", "Unknown")
                stats[pais] = stats.get(pais, 0) + 1
            if not stats:
                acks.append("📊 No hay leads pendientes.")
            else:
                lineas = ["📊 Pendientes por estado (excluye retirados):"]
                for p, c in sorted(stats.items(), key=lambda x: x[1], reverse=True):
                    lineas.append(f"- {p}: {c}")
                acks.append("\n".join(lineas))
        elif text.startswith("/estado "):
            estado_req = text.replace("/estado ", "").strip().lower()
            objetivo = mercado_canonico(estado_req)
            pend = _pendientes_activos()
            matches = [
                p.get("nombre", "Unknown") for p in pend.values()
                if objetivo and p["pais"] == objetivo
            ]
            if not matches:
                acks.append(f"🔍 No hay leads pendientes para el estado '{estado_req.upper()}'.")
            else:
                lineas = [f"📍 Leads pendientes en {estado_req.upper()} ({len(matches)}):"]
                for m in matches[:20]: # limit to 20 so telegram doesn't complain about message size
                    lineas.append(f"- {m}")
                if len(matches) > 20:
                    lineas.append(f"... y {len(matches)-20} más.")
                acks.append("\n".join(lineas))

    _save(data)
    return acks

