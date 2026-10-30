"""Cola de correo B2B. Con B2B_ENVIO_REAL=0 no abre SMTP: escribe un .eml."""
from __future__ import annotations

import json
import os
import random
import re
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

from b2b.leads_store import en_lista_no_contactar, guardar_estado_lead
from b2b.logging_ops import registrar_evento
from b2b.paths import state_file as _state_file
from b2b.redactor import (
    EMPRESA_FIRMA,
    NOMBRE_VP,
    WHOLESALE_URL,
    asunto_correo,
    cuerpo_sin_asunto,
    direccion_postal,
)
from b2b.zonas import en_horario_laboral, siguiente_habil

_RE_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_RE_ENLACE = re.compile(r"https?://", re.I)


def _error(exc: BaseException) -> str:
    try:
        from telegram_bot import sanitizar_error

        return sanitizar_error(exc)
    except Exception:
        return str(exc)[:500]


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _ruta_envios() -> Path:
    return _state_file("envios_correo.json")


def _load() -> dict:
    path = _ruta_envios()
    if not path.is_file():
        return {"envios": [], "pausadas": {}, "avisos": {}, "turno": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"envios": [], "pausadas": {}, "avisos": {}, "turno": 0}
    data.setdefault("envios", [])
    data.setdefault("pausadas", {})
    data.setdefault("avisos", {})
    data.setdefault("turno", 0)
    return data


def _save(data: dict) -> None:
    path = _ruta_envios()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def envio_real() -> bool:
    return os.getenv("B2B_ENVIO_REAL", "0").strip() == "1"


def outbox_dir() -> Path:
    from b2b.paths import queue_dir

    cola = queue_dir()
    base = cola if cola else _state_file("x").parent
    path = base / "outbox"
    path.mkdir(parents=True, exist_ok=True)
    return path


def dir_simulado_eml() -> Path:
    path = _state_file("x").parent / "outbox_simulado"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _int_env(nombre: str, defecto: int) -> int:
    try:
        return int(os.getenv(nombre, str(defecto)) or defecto)
    except ValueError:
        return defecto


def _fecha_inicio() -> datetime:
    bruto = os.getenv("B2B_ENVIO_FECHA_INICIO", "2026-11-02").strip() or "2026-11-02"
    try:
        return datetime.strptime(bruto, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime(2026, 11, 2, tzinfo=timezone.utc)


def tope_rampa(momento: datetime | None = None) -> int:
    momento = momento or _ahora()
    partes = [p.strip() for p in os.getenv("B2B_ENVIO_RAMPA", "10,20,30").split(",") if p.strip()]
    nums = []
    for p in partes:
        try:
            nums.append(int(p))
        except ValueError:
            continue
    if not nums:
        nums = [10, 20, 30]
    while len(nums) < 3:
        nums.append(nums[-1])
    dias = (momento.date() - _fecha_inicio().date()).days
    if dias < 7:
        return nums[0]
    if dias < 14:
        return nums[1]
    return nums[2]


def max_por_cuenta() -> int:
    return max(1, _int_env("B2B_ENVIO_MAX_POR_CUENTA", 15))


def cuentas_activas() -> list[dict]:
    """Sin clave de aplicación la cuenta se omite, sin error y sin avisar cada vez."""
    real = envio_real()
    activas = []
    omitidas = []
    for n in (1, 2):
        correo = os.getenv(f"CORREO_REMITENTE_{n}", "").strip()
        clave = os.getenv(f"CORREO_CLAVE_{n}", "").strip()
        if not correo:
            continue
        if not clave:
            omitidas.append(n)
            continue
        if real or clave:
            activas.append({"n": n, "correo": correo, "clave": clave})
    if omitidas:
        data = _load()
        cambio = False
        for n in omitidas:
            clave_aviso = f"sin_clave_{n}"
            if not data["avisos"].get(clave_aviso):
                data["avisos"][clave_aviso] = True
                cambio = True
                registrar_evento({"evento": "cuenta_sin_clave", "cuenta": n})
        if cambio:
            _save(data)
    return activas


def _dia_rd(momento: datetime) -> str:
    from b2b.zonas import tz

    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(tz("America/Santo_Domingo")).strftime("%Y-%m-%d")


def _envios_recientes(data: dict, dias: int = 30) -> list[dict]:
    corte = _ahora() - timedelta(days=dias)
    salida = []
    for item in data.get("envios") or []:
        try:
            cuando = datetime.fromisoformat(item.get("cuando") or "")
        except ValueError:
            continue
        if cuando.tzinfo is None:
            cuando = cuando.replace(tzinfo=timezone.utc)
        if cuando >= corte:
            salida.append(item)
    return salida


def _cupo_cuenta(n: int, activas: list[dict], momento: datetime) -> int:
    if not activas:
        return 0
    total = tope_rampa(momento)
    idx = next((i for i, c in enumerate(activas) if c["n"] == n), 0)
    base, resto = divmod(total, len(activas))
    parte = base + (1 if idx < resto else 0)
    return max(0, min(max_por_cuenta(), parte))


def _enviados_hoy(data: dict, n: int, momento: datetime) -> int:
    dia = _dia_rd(momento)
    return sum(1 for e in data.get("envios") or [] if e.get("cuenta") == n and e.get("dia") == dia and e.get("ok"))


def _total_hoy(data: dict, momento: datetime) -> int:
    dia = _dia_rd(momento)
    return sum(1 for e in data.get("envios") or [] if e.get("dia") == dia and e.get("ok"))


def elegir_cuenta(momento: datetime | None = None) -> dict | None:
    momento = momento or _ahora()
    data = _load()
    activas = [c for c in cuentas_activas() if str(c["n"]) not in data.get("pausadas", {})]
    if not activas:
        return None
    if _total_hoy(data, momento) >= tope_rampa(momento):
        return None
    inicio = int(data.get("turno") or 0)
    for salto in range(len(activas)):
        cuenta = activas[(inicio + salto) % len(activas)]
        if _enviados_hoy(data, cuenta["n"], momento) < _cupo_cuenta(cuenta["n"], activas, momento):
            return cuenta
    return None


def _avanzar_turno(cuenta: dict) -> None:
    data = _load()
    activas = cuentas_activas()
    if not activas:
        return
    idx = next((i for i, c in enumerate(activas) if c["n"] == cuenta["n"]), 0)
    data["turno"] = (idx + 1) % len(activas)
    _save(data)


def correo_valido(valor: str) -> bool:
    texto = (valor or "").strip()
    if not _RE_CORREO.match(texto):
        return False
    bajo = texto.lower()
    if "noreply" in bajo or "no-reply" in bajo:
        return False
    return True


def _dominio_correo(correo: str) -> str:
    partes = (correo or "").strip().lower().split("@")
    return partes[-1] if len(partes) == 2 else ""


def puede_enviar_correo(lead: dict, momento: datetime | None = None) -> tuple[bool, str]:
    momento = momento or _ahora()
    correo = (lead.get("correo") or "").strip()
    if not correo_valido(correo):
        return False, "correo no válido"
    if not direccion_postal("es"):
        return False, "falta la dirección postal"
    if en_lista_no_contactar(lead.get("nombre") or "", lead.get("web") or ""):
        return False, "en no contactar"
    data = _load()
    bajo = correo.lower()
    if bajo in {c.lower() for c in data.get("invalidos") or []}:
        return False, "correo inválido"
    dom = _dominio_correo(bajo)
    for previo in _envios_recientes(data, 30):
        if (previo.get("correo") or "").lower() == bajo:
            return False, "ese correo ya recibió un mensaje"
        if dom and previo.get("dominio") == dom:
            return False, "ese dominio ya recibió un mensaje"
    if elegir_cuenta(momento) is None:
        return False, "tope diario de envío"
    return True, ""


def construir_mensaje(
    lead: dict,
    cuenta: str,
    cuerpo: str,
    asunto: str,
    *,
    in_reply_to: str = "",
    references: str = "",
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = f'"{NOMBRE_VP} — {EMPRESA_FIRMA}" <{cuenta}>'
    msg["To"] = (lead.get("correo") or "").strip()
    msg["Reply-To"] = cuenta
    msg["Subject"] = asunto
    msg["Message-ID"] = make_msgid(domain=cuenta.split("@")[-1] or "localhost")
    msg["Date"] = formatdate(localtime=True)
    msg["List-Unsubscribe"] = f"<mailto:{cuenta}?subject=BAJA>"
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = references or in_reply_to
    msg.set_content(cuerpo or "")
    return msg


def _un_solo_enlace(cuerpo: str) -> bool:
    return len(_RE_ENLACE.findall(cuerpo or "")) == 1 and WHOLESALE_URL in (cuerpo or "")


def preparar_cuerpo(lead: dict, cuenta: str) -> tuple[str, str, str]:
    idioma = lead.get("idioma") or "en"
    tipo = lead.get("tipo") or lead.get("tipo_negocio") or "tienda"
    variante = (lead.get("asunto_variante") or "A").upper()
    if variante not in ("A", "B"):
        variante = "A"
    asunto = asunto_correo(lead.get("nombre") or "", idioma, variante)
    cuerpo = lead.get("cuerpo_editado") or cuerpo_sin_asunto(
        lead.get("nombre") or "", idioma, tipo, cuenta=cuenta, variante=variante
    )
    if cuenta and cuenta not in cuerpo:
        cuerpo = cuerpo_sin_asunto(lead.get("nombre") or "", idioma, tipo, cuenta=cuenta, variante=variante)
    return asunto, cuerpo, variante


def _avisar_una_vez(clave: str, texto: str) -> None:
    data = _load()
    if data["avisos"].get(clave):
        return
    data["avisos"][clave] = True
    _save(data)
    registrar_evento({"evento": "aviso_envio", "clave": clave})
    try:
        from telegram_bot import enviar_texto_telegram

        enviar_texto_telegram(texto)
    except Exception as exc:
        registrar_evento({"evento": "aviso_telegram_fallo", "error": _error(exc)})


def pausar_cuenta(n: int, motivo: str) -> None:
    data = _load()
    if str(n) in data["pausadas"]:
        return
    data["pausadas"][str(n)] = motivo
    _save(data)
    _avisar_una_vez(f"auth_{n}", f"⚠️ La cuenta {n} quedó pausada: falló la autenticación. Sigo con la otra.")


def marcar_correo_invalido(correo: str) -> None:
    data = _load()
    invalidos = list(data.get("invalidos") or [])
    bajo = correo.strip().lower()
    if bajo and bajo not in invalidos:
        invalidos.append(bajo)
    data["invalidos"] = invalidos
    _save(data)


def _pausa_minutos() -> int:
    minimo = _int_env("B2B_ENVIO_PAUSA_MIN", 2)
    maximo = _int_env("B2B_ENVIO_PAUSA_MAX", 5)
    if maximo < minimo:
        maximo = minimo
    return random.randint(minimo, maximo)


def _horas() -> tuple[int, int]:
    return _int_env("B2B_ENVIO_HORA_INICIO", 9), _int_env("B2B_ENVIO_HORA_FIN", 17)


def lugar_del_lead(lead: dict) -> str:
    return (lead.get("estado") or lead.get("pais") or "Florida").strip() or "Florida"


def programar_momento(lead: dict, ahora: datetime | None = None) -> datetime:
    ahora = ahora or _ahora()
    if ahora.tzinfo is None:
        ahora = ahora.replace(tzinfo=timezone.utc)
    lugar = lugar_del_lead(lead)
    inicio, fin = _horas()
    ultimo = ahora
    for path in sorted(outbox_dir().glob("*.json")):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        try:
            marca = datetime.fromisoformat(item.get("enviar_despues_de") or "")
        except ValueError:
            continue
        if marca.tzinfo is None:
            marca = marca.replace(tzinfo=timezone.utc)
        if marca > ultimo:
            ultimo = marca
    previsto = ultimo + timedelta(minutes=_pausa_minutos())
    if not en_horario_laboral(previsto, lugar, inicio, fin):
        previsto = siguiente_habil(previsto, lugar, inicio, fin)
    return previsto


def texto_ventana(lead: dict, ahora: datetime | None = None) -> str:
    ahora = ahora or _ahora()
    lugar = lugar_del_lead(lead)
    inicio, fin = _horas()
    previsto = programar_momento(lead, ahora)
    local = previsto
    from b2b.zonas import ahora_local

    local = ahora_local(previsto, lugar)
    hora_fin = (local + timedelta(minutes=max(1, _int_env("B2B_ENVIO_PAUSA_MAX", 5) - _int_env("B2B_ENVIO_PAUSA_MIN", 2)))).strftime("%H:%M")
    if local.date() == ahora_local(ahora, lugar).date() and en_horario_laboral(previsto, lugar, inicio, fin):
        return f"Sale hoy entre {local.strftime('%H:%M')} y {hora_fin} (hora del local)"
    return f"Sale el {local.strftime('%Y-%m-%d')} a las {local.strftime('%H:%M')} (hora del local)"


def encolar_envio(lead: dict, token: str, *, ahora: datetime | None = None) -> dict | None:
    ahora = ahora or _ahora()
    ok, motivo = puede_enviar_correo(lead, ahora)
    if not ok:
        if motivo == "falta la dirección postal":
            _avisar_una_vez("sin_direccion", "⚠️ No envié: falta EMPRESA_DIRECCION_POSTAL.")
        return None
    cuenta = elegir_cuenta(ahora)
    if cuenta is None:
        return None
    asunto, cuerpo, variante = preparar_cuerpo(lead, cuenta["correo"])
    if not direccion_postal("es") or "BAJA" not in cuerpo and "STOP" not in cuerpo:
        _avisar_una_vez("sin_direccion", "⚠️ No envié: falta EMPRESA_DIRECCION_POSTAL.")
        return None
    cuando = programar_momento(lead, ahora)
    item = {
        "token": token,
        "correo": (lead.get("correo") or "").strip(),
        "dominio": _dominio_correo(lead.get("correo") or ""),
        "cuenta": cuenta["n"],
        "cuenta_correo": cuenta["correo"],
        "asunto": asunto,
        "variante": variante,
        "cuerpo": cuerpo,
        "enviar_despues_de": cuando.isoformat(timespec="seconds"),
        "lugar": lugar_del_lead(lead),
        "nombre": lead.get("nombre") or "",
        "message_id": lead.get("message_id"),
        "intentos": 0,
        "estado": "en_cola",
        "lead": {
            "nombre": lead.get("nombre") or "",
            "correo": lead.get("correo") or "",
            "web": lead.get("web") or "",
            "idioma": lead.get("idioma") or "en",
            "pais": lead.get("pais") or "",
            "tipo": lead.get("tipo") or "",
        },
    }
    path = outbox_dir() / f"{token}.json"
    path.write_text(json.dumps(item, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    guardar_estado_lead(lead, "en_cola", cuenta=cuenta["n"], variante=variante, asunto=asunto)
    return item


def cancelar_envio(token: str) -> bool:
    path = outbox_dir() / f"{token}.json"
    if not path.is_file():
        return False
    try:
        item = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        item = {}
    try:
        path.unlink()
    except OSError:
        return False
    lead = item.get("lead") or {"nombre": item.get("nombre") or "", "correo": item.get("correo") or ""}
    guardar_estado_lead(lead, "aprobado")
    return True


def _registrar_ok(item: dict, momento: datetime, message_id: str) -> None:
    data = _load()
    data["envios"].append({
        "correo": item.get("correo") or "",
        "dominio": item.get("dominio") or "",
        "cuenta": item.get("cuenta"),
        "variante": item.get("variante") or "",
        "asunto": item.get("asunto") or "",
        "cuando": momento.isoformat(timespec="seconds"),
        "dia": _dia_rd(momento),
        "ok": True,
        "message_id": message_id,
        "nombre": item.get("nombre") or "",
    })
    _save(data)
    lead = item.get("lead") or {"nombre": item.get("nombre") or "", "correo": item.get("correo") or ""}
    guardar_estado_lead(
        lead,
        "enviado",
        cuenta=item.get("cuenta"),
        variante=item.get("variante"),
        asunto=item.get("asunto"),
        message_id=message_id,
        cuando=momento.isoformat(timespec="seconds"),
    )


def _escribir_eml(msg: EmailMessage, token: str) -> Path:
    dest = dir_simulado_eml() / f"{token}.eml"
    dest.write_bytes(msg.as_bytes())
    return dest


def _enviar_smtp(cuenta: dict, msg: EmailMessage) -> None:
    import smtplib

    host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip() or "smtp.gmail.com"
    port = _int_env("SMTP_PORT", 587)
    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(cuenta["correo"], cuenta["clave"])
        smtp.send_message(msg)


def _cuenta_por_numero(n: int) -> dict | None:
    for cuenta in cuentas_activas():
        if cuenta["n"] == n and str(n) not in _load().get("pausadas", {}):
            return cuenta
    return None


def _editar_estado(item: dict, linea: str) -> None:
    try:
        from b2b.telegram_gestion import actualizar_pendiente, resolver_pendiente
        from b2b.telegram_prospecto import texto_con_estado

        token = item.get("token") or ""
        pend = resolver_pendiente(token) or {}
        message_id = pend.get("message_id") or item.get("message_id")
        if not message_id:
            return
        base = pend.get("texto_tarjeta") or ""
        if not base:
            return
        texto = texto_con_estado(base, linea)
        actualizar_pendiente(token, texto_tarjeta=texto, estado_envio=item.get("estado"))
        from telegram_bot import editar_mensaje_telegram

        from b2b.telegram_prospecto import teclado_en_cola, teclado_cerrado

        markup = teclado_en_cola(pend, token) if item.get("estado") == "en_cola" else teclado_cerrado()
        editar_mensaje_telegram(int(message_id), texto, markup)
    except Exception as exc:
        registrar_evento({"evento": "editar_tarjeta_fallo", "error": _error(exc)})


def _fallo_temporal(item: dict, path: Path, momento: datetime, exc: BaseException) -> None:
    intentos = int(item.get("intentos") or 0) + 1
    item["intentos"] = intentos
    if intentos >= 3:
        item["estado"] = "fallo"
        path.write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        registrar_evento({"evento": "smtp_fallo", "error": _error(exc), "cuenta": item.get("cuenta")})
        return
    espera = timedelta(minutes=2 ** intentos)
    item["enviar_despues_de"] = (momento + espera).isoformat(timespec="seconds")
    path.write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def procesar_outbox(ahora: datetime | None = None) -> int:
    from b2b.telegram_control import esta_pausado

    if esta_pausado():
        return 0
    ahora = ahora or _ahora()
    if ahora.tzinfo is None:
        ahora = ahora.replace(tzinfo=timezone.utc)
    hechos = 0
    inicio, fin = _horas()
    for path in sorted(outbox_dir().glob("*.json")):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if item.get("estado") not in (None, "en_cola"):
            continue
        try:
            cuando = datetime.fromisoformat(item.get("enviar_despues_de") or "")
        except ValueError:
            continue
        if cuando.tzinfo is None:
            cuando = cuando.replace(tzinfo=timezone.utc)
        if cuando > ahora:
            continue
        lugar = item.get("lugar") or "Florida"
        if not en_horario_laboral(ahora, lugar, inicio, fin):
            siguiente = siguiente_habil(ahora, lugar, inicio, fin)
            item["enviar_despues_de"] = siguiente.isoformat(timespec="seconds")
            item["estado"] = "en_cola"
            path.write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            local = siguiente_habil(ahora, lugar, inicio, fin)
            _editar_estado(item, f"⏳ En cola · sale el {local.strftime('%Y-%m-%d')} a las {local.strftime('%H:%M')} (hora del local)")
            continue
        cuenta = _cuenta_por_numero(int(item.get("cuenta") or 0))
        if cuenta is None:
            otra = elegir_cuenta(ahora)
            if otra is None:
                continue
            cuenta = otra
            item["cuenta"] = cuenta["n"]
            item["cuenta_correo"] = cuenta["correo"]
        lead = item.get("lead") or {}
        lead = dict(lead)
        lead["correo"] = item.get("correo") or lead.get("correo")
        lead["nombre"] = item.get("nombre") or lead.get("nombre")
        msg = construir_mensaje(lead, cuenta["correo"], item.get("cuerpo") or "", item.get("asunto") or "")
        try:
            if not envio_real():
                _escribir_eml(msg, item.get("token") or path.stem)
                modo = "SIMULADO"
            else:
                _enviar_smtp(cuenta, msg)
                modo = "Enviado"
        except Exception as exc:
            codigo = getattr(exc, "smtp_code", None)
            nombre_exc = type(exc).__name__
            if nombre_exc == "SMTPAuthenticationError":
                pausar_cuenta(int(cuenta["n"]), "auth")
                item["cuenta"] = None
                path.write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                continue
            if codigo in (550, 553) or nombre_exc == "SMTPRecipientsRefused":
                marcar_correo_invalido(item.get("correo") or "")
                item["estado"] = "reboto"
                path.write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                guardar_estado_lead(lead, "reboto")
                _editar_estado(item, "⚠️ Rebotó al enviar")
                continue
            _fallo_temporal(item, path, ahora, exc)
            continue
        _registrar_ok(item, ahora, msg["Message-ID"])
        _avanzar_turno(cuenta)
        from b2b.zonas import ahora_local

        hora = ahora_local(ahora, lugar).strftime("%H:%M")
        item["estado"] = "enviado"
        item["message_id_correo"] = msg["Message-ID"]
        path.write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _editar_estado(item, f"📤 {modo} {hora} desde cuenta {cuenta['n']}")
        hechos += 1
    return hechos


def probar_envio(destino: str) -> list[str]:
    """Manda (o simula) el ejemplo con cada cuenta activa a la dirección indicada."""
    if not direccion_postal("es"):
        _avisar_una_vez("sin_direccion", "⚠️ No envié la prueba: falta EMPRESA_DIRECCION_POSTAL.")
        return ["Falta EMPRESA_DIRECCION_POSTAL."]
    activas = cuentas_activas()
    if not activas:
        return ["No hay cuentas activas (falta el correo o la clave de aplicación)."]
    notas = []
    lead = {
        "nombre": "Prime Cigar & Whiskey Bar",
        "tipo": "lounge",
        "idioma": "en",
        "correo": destino.strip(),
        "pais": "Florida",
        "estado": "Florida",
    }
    for cuenta in activas:
        asunto, cuerpo, _variante = preparar_cuerpo({**lead, "asunto_variante": "A"}, cuenta["correo"])
        msg = construir_mensaje(lead, cuenta["correo"], cuerpo, asunto)
        if not envio_real():
            dest = _escribir_eml(msg, f"prueba-{cuenta['n']}")
            notas.append(f"SIMULADO cuenta {cuenta['n']} → {dest.name}")
            continue
        try:
            _enviar_smtp(cuenta, msg)
            notas.append(f"Enviado con la cuenta {cuenta['n']}")
        except Exception as exc:
            notas.append(f"Cuenta {cuenta['n']}: {_error(exc)}")
    return notas

