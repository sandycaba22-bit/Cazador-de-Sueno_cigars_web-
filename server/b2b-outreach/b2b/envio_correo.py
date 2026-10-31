"""Cola de correo B2B. Con B2B_ENVIO_REAL=0 no abre SMTP: escribe un .eml."""
from __future__ import annotations

import json
import os
import random
import re
import ssl
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
    asegurar_pie,
    asunto_outreach,
    cuerpo_sin_asunto,
    direccion_postal,
)
from b2b.zonas import en_horario_laboral, siguiente_habil

_RE_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_RE_ENLACE = re.compile(r"https?://", re.I)

DOMINIOS_GRATUITOS = frozenset({
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "aol.com",
    "icloud.com",
    "me.com",
    "msn.com",
    "proton.me",
    "protonmail.com",
})


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
        return {"envios": [], "simulados": [], "pausadas": {}, "avisos": {}, "turno": 0, "invalidos": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"envios": [], "simulados": [], "pausadas": {}, "avisos": {}, "turno": 0, "invalidos": []}
    data.setdefault("envios", [])
    data.setdefault("simulados", [])
    data.setdefault("pausadas", {})
    data.setdefault("avisos", {})
    data.setdefault("turno", 0)
    data.setdefault("invalidos", [])
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


def archivo_dir() -> Path:
    path = outbox_dir() / "archivo"
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


def _tope_efectivo(momento: datetime | None = None) -> int:
    """La rampa no puede pasar de CORREOS_MAX_DIA (techo diario)."""
    return min(tope_rampa(momento), max(1, _int_env("CORREOS_MAX_DIA", 30)))


def max_por_cuenta() -> int:
    return max(1, _int_env("B2B_ENVIO_MAX_POR_CUENTA", 15))


def cuentas_activas() -> list[dict]:
    """Con REAL=0 basta el remitente. Con REAL=1 sin clave la cuenta se omite."""
    real = envio_real()
    activas = []
    omitidas = []
    for n in (1, 2):
        correo = (
            os.getenv(f"CORREO_REMITENTE_{n}", "").strip()
            or os.getenv(f"EMAIL_REMITENTE_{n}", "").strip()
        )
        clave = (
            os.getenv(f"CORREO_CLAVE_{n}", "").strip()
            or os.getenv(f"EMAIL_CLAVE_{n}", "").strip()
        )
        if not correo:
            continue
        if real and not clave:
            omitidas.append(n)
            continue
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


def _parse_marca(valor: str) -> datetime | None:
    if not valor:
        return None
    try:
        momento = datetime.fromisoformat(valor)
    except ValueError:
        return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento


def items_en_cola() -> list[tuple[Path, dict]]:
    filas = []
    for path in sorted(outbox_dir().glob("*.json")):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if item.get("estado") not in (None, "en_cola"):
            continue
        filas.append((path, item))
    return filas


def _envios_recientes(data: dict, dias: int = 30) -> list[dict]:
    corte = _ahora() - timedelta(days=dias)
    salida = []
    for item in data.get("envios") or []:
        cuando = _parse_marca(item.get("cuando") or "")
        if cuando and cuando >= corte:
            salida.append(item)
    return salida


def _cupo_cuenta(n: int, activas: list[dict], momento: datetime) -> int:
    if not activas:
        return 0
    total = _tope_efectivo(momento)
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


def _en_cola_hoy(n: int | None, momento: datetime, *, excluir_token: str = "") -> int:
    dia = _dia_rd(momento)
    total = 0
    for _path, item in items_en_cola():
        if excluir_token and item.get("token") == excluir_token:
            continue
        if n is not None and item.get("cuenta") != n:
            continue
        cuando = _parse_marca(item.get("enviar_despues_de") or "")
        if cuando and _dia_rd(cuando) == dia:
            total += 1
    return total


def _comprometidos_cuenta(data: dict, n: int, momento: datetime, *, excluir_token: str = "") -> int:
    return _enviados_hoy(data, n, momento) + _en_cola_hoy(n, momento, excluir_token=excluir_token)


def _total_comprometido(data: dict, momento: datetime, *, excluir_token: str = "") -> int:
    return _total_hoy(data, momento) + _en_cola_hoy(None, momento, excluir_token=excluir_token)


def _activas_sin_pausa(data: dict | None = None) -> list[dict]:
    data = data if data is not None else _load()
    pausadas = data.get("pausadas") or {}
    return [c for c in cuentas_activas() if str(c["n"]) not in pausadas]


def elegir_cuenta(momento: datetime | None = None, *, excluir_token: str = "") -> dict | None:
    momento = momento or _ahora()
    data = _load()
    activas = _activas_sin_pausa(data)
    if not activas:
        return None
    if _total_comprometido(data, momento, excluir_token=excluir_token) >= _tope_efectivo(momento):
        return None
    inicio = int(data.get("turno") or 0)
    for salto in range(len(activas)):
        cuenta = activas[(inicio + salto) % len(activas)]
        cupo = _cupo_cuenta(cuenta["n"], activas, momento)
        if _comprometidos_cuenta(data, cuenta["n"], momento, excluir_token=excluir_token) < cupo:
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


def _dominio_bloquea_30d(dominio: str) -> bool:
    return bool(dominio) and dominio.lower() not in DOMINIOS_GRATUITOS


def puede_enviar_correo(
    lead: dict,
    momento: datetime | None = None,
    *,
    solo_si_hay_cupo_hoy: bool = False,
) -> tuple[bool, str]:
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
    if esta_excluido(bajo):
        return False, "en la lista de exclusión"
    dom = _dominio_correo(bajo)
    for previo in _envios_recientes(data, 30):
        if (previo.get("correo") or "").lower() == bajo:
            return False, "ese correo ya recibió un mensaje"
        if _dominio_bloquea_30d(dom) and previo.get("dominio") == dom:
            return False, "ese dominio ya recibió un mensaje"
    activas = _activas_sin_pausa(data)
    if not activas:
        return False, "sin cuenta de correo activa"
    if solo_si_hay_cupo_hoy and elegir_cuenta(momento) is None:
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


def _remitentes_conocidos() -> list[str]:
    vistos = []
    for n in (1, 2):
        correo = os.getenv(f"CORREO_REMITENTE_{n}", "").strip()
        if correo and correo not in vistos:
            vistos.append(correo)
    return vistos


def preparar_cuerpo(lead: dict, cuenta: str) -> tuple[str, str, str]:
    idioma = lead.get("idioma") or "en"
    tipo = lead.get("tipo") or lead.get("tipo_negocio") or "tienda"
    variante = (lead.get("asunto_variante") or "A").upper()
    if variante not in ("A", "B"):
        variante = "A"
    asunto = (lead.get("asunto") or "").strip() or asunto_outreach(lead.get("nombre") or "")
    editado = (lead.get("cuerpo_editado") or "").strip()
    if editado:
        cuerpo = editado
        for otro in _remitentes_conocidos():
            if otro != cuenta and otro in cuerpo:
                cuerpo = cuerpo.replace(otro, cuenta)
        cuerpo = asegurar_pie(cuerpo, idioma)
        return asunto, _limpiar_firma(cuerpo, cuenta), variante
    cuerpo = cuerpo_sin_asunto(lead.get("nombre") or "", idioma, tipo, cuenta=cuenta, variante=variante)
    return asunto, _limpiar_firma(cuerpo, cuenta), variante


def _limpiar_firma(cuerpo: str, cuenta: str) -> str:
    """Quita el correo mal escrito y deja el de la cuenta que envía."""
    texto = cuerpo or ""
    correcto = (cuenta or "").strip()
    texto = texto.replace("cazardordesuenol@gmail.com", correcto or "cazadordesueno1@gmail.com")
    for bruto in ("8094645016", "+18094645016"):
        if bruto in texto:
            from b2b.redactor import whatsapp_empresa

            texto = texto.replace(bruto, whatsapp_empresa())
    return texto


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


def _delta_pausa() -> timedelta:
    """60–120 s si CORREOS_PAUSA_*_SEG está definido; si no, la pausa vieja en minutos."""
    if os.getenv("CORREOS_PAUSA_MIN_SEG") or os.getenv("CORREOS_PAUSA_MAX_SEG"):
        minimo = _int_env("CORREOS_PAUSA_MIN_SEG", 60)
        maximo = _int_env("CORREOS_PAUSA_MAX_SEG", 120)
        if maximo < minimo:
            maximo = minimo
        return timedelta(seconds=random.randint(minimo, maximo))
    return timedelta(minutes=_pausa_minutos())


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
    for _path, item in items_en_cola():
        marca = _parse_marca(item.get("enviar_despues_de") or "")
        if marca and marca > ultimo:
            ultimo = marca
    previsto = ultimo + _delta_pausa()
    if not en_horario_laboral(previsto, lugar, inicio, fin):
        previsto = siguiente_habil(previsto, lugar, inicio, fin)
    data = _load()
    if _total_comprometido(data, previsto) >= _tope_efectivo(previsto):
        previsto = siguiente_habil(previsto + timedelta(hours=12), lugar, inicio, fin)
        while _total_comprometido(data, previsto) >= _tope_efectivo(previsto):
            previsto = siguiente_habil(previsto + timedelta(hours=12), lugar, inicio, fin)
    return previsto


def texto_ventana(lead: dict, ahora: datetime | None = None) -> str:
    ahora = ahora or _ahora()
    lugar = lugar_del_lead(lead)
    inicio, fin = _horas()
    previsto = programar_momento(lead, ahora)
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
    preferida = elegir_cuenta(ahora)
    activas = _activas_sin_pausa()
    if not activas:
        return None
    cuenta_correo = (preferida or activas[0])["correo"]
    asunto, cuerpo, variante = preparar_cuerpo(lead, cuenta_correo)
    if not direccion_postal("es") or not any(m in cuerpo for m in ("BAJA", "STOP", "unsubscribe")):
        _avisar_una_vez("sin_direccion", "⚠️ No envié: falta EMPRESA_DIRECCION_POSTAL.")
        return None
    cuando = programar_momento(lead, ahora)
    item = {
        "token": token,
        "correo": (lead.get("correo") or "").strip(),
        "dominio": _dominio_correo(lead.get("correo") or ""),
        "cuenta": (preferida or {}).get("n"),
        "cuenta_correo": cuenta_correo,
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
            "estado": lead.get("estado") or lead.get("pais") or "",
            "tipo": lead.get("tipo") or "",
            "asunto_variante": variante,
            "cuerpo_editado": lead.get("cuerpo_editado") or "",
            "asunto": asunto,
        },
    }
    path = outbox_dir() / f"{token}.json"
    path.write_text(json.dumps(item, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    guardar_estado_lead(lead, "en_cola", cuenta=item.get("cuenta"), variante=variante, asunto=asunto)
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
    data["ultimo_envio"] = momento.isoformat(timespec="seconds")
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


def _registrar_simulado(item: dict, momento: datetime, message_id: str) -> None:
    data = _load()
    data.setdefault("simulados", []).append({
        "correo": item.get("correo") or "",
        "dominio": item.get("dominio") or "",
        "cuenta": item.get("cuenta"),
        "variante": item.get("variante") or "",
        "asunto": item.get("asunto") or "",
        "cuando": momento.isoformat(timespec="seconds"),
        "dia": _dia_rd(momento),
        "message_id": message_id,
        "nombre": item.get("nombre") or "",
    })
    _save(data)
    lead = item.get("lead") or {"nombre": item.get("nombre") or "", "correo": item.get("correo") or ""}
    guardar_estado_lead(
        lead,
        "aprobado_simulado",
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
    contexto = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=30, context=contexto) as smtp:
            smtp.login(cuenta["correo"], cuenta["clave"])
            smtp.send_message(msg)
        return
    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls(context=contexto)
        smtp.ehlo()
        smtp.login(cuenta["correo"], cuenta["clave"])
        smtp.send_message(msg)


def _cuenta_por_numero(n: int) -> dict | None:
    for cuenta in _activas_sin_pausa():
        if cuenta["n"] == n:
            return cuenta
    return None


def _archivar_item(path: Path, item: dict) -> None:
    dest = archivo_dir() / path.name
    dest.write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        path.unlink()
    except OSError:
        pass


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


def _reprogramar_por_tope(item: dict, path: Path, momento: datetime) -> None:
    lugar = item.get("lugar") or "Florida"
    inicio, fin = _horas()
    siguiente = siguiente_habil(momento + timedelta(hours=12), lugar, inicio, fin)
    item["enviar_despues_de"] = siguiente.isoformat(timespec="seconds")
    item["estado"] = "en_cola"
    path.write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    from b2b.zonas import ahora_local

    local = ahora_local(siguiente, lugar)
    _editar_estado(
        item,
        f"⏳ En cola · sale el {local.strftime('%Y-%m-%d')} a las {local.strftime('%H:%M')} (hora del local)",
    )


def _fallo_temporal(item: dict, path: Path, momento: datetime, exc: BaseException) -> None:
    intentos = int(item.get("intentos") or 0) + 1
    item["intentos"] = intentos
    if intentos >= 3:
        item["estado"] = "fallo"
        motivo = _error(exc)
        item["motivo_fallo"] = motivo
        _archivar_item(path, item)
        nombre = item.get("nombre") or item.get("correo") or "el local"
        _avisar_una_vez(
            f"fallo_{item.get('token') or path.stem}",
            f"⚠️ No pude enviar a {nombre}: {motivo}",
        )
        registrar_evento({"evento": "smtp_fallo", "error": motivo, "cuenta": item.get("cuenta")})
        return
    espera = timedelta(minutes=2 ** intentos)
    item["enviar_despues_de"] = (momento + espera).isoformat(timespec="seconds")
    path.write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _elegir_cuenta_al_enviar(item: dict, momento: datetime) -> dict | None:
    token = item.get("token") or ""
    data = _load()
    preferida_n = item.get("cuenta")
    if preferida_n is not None:
        try:
            preferida_n = int(preferida_n)
        except (TypeError, ValueError):
            preferida_n = None
    if preferida_n is not None:
        candidata = _cuenta_por_numero(preferida_n)
        if candidata is not None:
            cupo = _cupo_cuenta(candidata["n"], _activas_sin_pausa(data), momento)
            if _comprometidos_cuenta(data, candidata["n"], momento, excluir_token=token) < cupo:
                if _total_comprometido(data, momento, excluir_token=token) < _tope_efectivo(momento):
                    return candidata
    return elegir_cuenta(momento, excluir_token=token)


def procesar_outbox(ahora: datetime | None = None) -> int:
    from b2b.telegram_control import esta_pausado

    if esta_pausado():
        return 0
    ahora = ahora or _ahora()
    if ahora.tzinfo is None:
        ahora = ahora.replace(tzinfo=timezone.utc)
    hechos = 0
    inicio, fin = _horas()
    for path, item in items_en_cola():
        cuando = _parse_marca(item.get("enviar_despues_de") or "")
        if not cuando or cuando > ahora:
            continue
        lugar = item.get("lugar") or "Florida"
        if not en_horario_laboral(ahora, lugar, inicio, fin):
            siguiente = siguiente_habil(ahora, lugar, inicio, fin)
            item["enviar_despues_de"] = siguiente.isoformat(timespec="seconds")
            item["estado"] = "en_cola"
            path.write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            from b2b.zonas import ahora_local

            local = ahora_local(siguiente, lugar)
            _editar_estado(
                item,
                f"⏳ En cola · sale el {local.strftime('%Y-%m-%d')} a las {local.strftime('%H:%M')} (hora del local)",
            )
            continue
        cuenta = _elegir_cuenta_al_enviar(item, ahora)
        if cuenta is None:
            _reprogramar_por_tope(item, path, ahora)
            continue
        lead = dict(item.get("lead") or {})
        lead["correo"] = item.get("correo") or lead.get("correo")
        lead["nombre"] = item.get("nombre") or lead.get("nombre")
        lead["asunto_variante"] = item.get("variante") or lead.get("asunto_variante") or "A"
        if item.get("asunto"):
            lead["asunto"] = item["asunto"]
        asunto, cuerpo, variante = preparar_cuerpo(lead, cuenta["correo"])
        item["cuenta"] = cuenta["n"]
        item["cuenta_correo"] = cuenta["correo"]
        item["asunto"] = asunto
        item["cuerpo"] = cuerpo
        item["variante"] = variante
        msg = construir_mensaje(lead, cuenta["correo"], cuerpo, asunto)
        listo, error_catalogo = _catalogo_ok(lead.get("idioma") or "en")
        if not listo:
            item["estado"] = "fallo"
            item["motivo_fallo"] = error_catalogo
            _archivar_item(path, item)
            _avisar_una_vez(
                f"catalogo_{item.get('token') or path.stem}",
                f"⚠️ No envié a {item.get('nombre') or item.get('correo')}: {error_catalogo}",
            )
            continue
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
                guardar_estado_lead(lead, "reboto")
                _editar_estado(item, "⚠️ Rebotó al enviar")
                _archivar_item(path, item)
                continue
            _fallo_temporal(item, path, ahora, exc)
            continue
        if envio_real():
            _registrar_ok(item, ahora, msg["Message-ID"])
        else:
            _registrar_simulado(item, ahora, msg["Message-ID"])
        _avanzar_turno(cuenta)
        from b2b.zonas import ahora_local

        hora = ahora_local(ahora, lugar).strftime("%H:%M")
        item["estado"] = "enviado"
        item["message_id_correo"] = msg["Message-ID"]
        _editar_estado(item, f"📤 {modo} {hora} desde cuenta {cuenta['n']}")
        _archivar_item(path, item)
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


def _ruta_exclusiones() -> Path:
    return _state_file("exclusiones_correo.json")


def _cargar_exclusiones() -> list[str]:
    path = _ruta_exclusiones()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [str(c).strip().lower() for c in (data.get("correos") or []) if str(c).strip()]


def esta_excluido(correo: str) -> bool:
    return (correo or "").strip().lower() in set(_cargar_exclusiones())


def excluir_correo(correo: str, motivo: str = "unsubscribe") -> None:
    bajo = (correo or "").strip().lower()
    if "@" not in bajo:
        return
    path = _ruta_exclusiones()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    else:
        data = {}
    correos = list(data.get("correos") or [])
    if bajo not in {c.lower() for c in correos}:
        correos.append(bajo)
    data["correos"] = correos
    motivos = dict(data.get("motivos") or {})
    motivos[bajo] = motivo
    data["motivos"] = motivos
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    registrar_evento({"evento": "exclusion_correo", "correo": bajo, "motivo": motivo})


def _catalogo_ok(idioma: str) -> tuple[bool, str]:
    from b2b.catalogo_check import catalogo_listo_para_envio

    return catalogo_listo_para_envio(idioma)


def _resultado_envio(token: str, correo: str) -> str:
    path = outbox_dir() / f"{token}.json"
    arch = archivo_dir() / f"{token}.json"
    if arch.is_file():
        try:
            item = json.loads(arch.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            item = {}
        if item.get("estado") == "enviado":
            if not envio_real():
                return (
                    f"⚠️ No envié por SMTP: B2B_ENVIO_REAL=0. "
                    f"El borrador quedó guardado y no salió a {item.get('correo') or correo}."
                )
            return f"✅ Enviado a {item.get('correo') or correo}"
        motivo = item.get("motivo_fallo") or item.get("estado") or "error"
        return f"⚠️ No envié: {motivo}"
    if path.is_file():
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            item = {}
        if item.get("motivo_fallo"):
            return f"⚠️ No envié: {item['motivo_fallo']}"
        cuando = item.get("enviar_despues_de") or ""
        return f"⏳ Quedó en cola. Sale después de {cuando}"
    return f"⚠️ No envié: no hubo confirmación para {correo}"


def _espera_pausa_manual(ahora: datetime) -> int:
    if not (os.getenv("CORREOS_PAUSA_MIN_SEG") or os.getenv("CORREOS_PAUSA_MAX_SEG")):
        return 0
    ultimo = _parse_marca((_load().get("ultimo_envio") or ""))
    if not ultimo:
        return 0
    minimo = _int_env("CORREOS_PAUSA_MIN_SEG", 60)
    falta = minimo - (ahora - ultimo).total_seconds()
    return max(0, int(falta))


def enviar_confirmado(lead: dict, token: str, ahora: datetime | None = None) -> str:
    """Confirma y envía. Siempre devuelve el resultado, nunca silencio."""
    ahora = ahora or _ahora()
    correo = (lead.get("correo") or "").strip()
    ok, motivo = puede_enviar_correo(lead, ahora)
    if not ok:
        return f"⚠️ No envié: {motivo}"
    listo, error_catalogo = _catalogo_ok(lead.get("idioma") or "en")
    if not listo:
        return f"⚠️ No envié: {error_catalogo}"
    espera = _espera_pausa_manual(ahora)
    item = encolar_envio(lead, token, ahora=ahora)
    if not item:
        return "⚠️ No envié: no se pudo preparar el correo (dirección postal, baja o cupo)"
    path = outbox_dir() / f"{token}.json"
    if espera > 0 and path.is_file():
        cuando = (ahora + timedelta(seconds=espera)).isoformat(timespec="seconds")
        try:
            guardado = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            guardado = {}
        guardado["enviar_despues_de"] = cuando
        path.write_text(json.dumps(guardado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return f"⚠️ No envié todavía: pausa entre envíos, faltan {espera} s. Quedó en cola."
    if path.is_file():
        try:
            guardado = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            guardado = {}
        guardado["enviar_despues_de"] = (ahora - timedelta(seconds=1)).isoformat(timespec="seconds")
        path.write_text(json.dumps(guardado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    procesar_outbox(ahora)
    return _resultado_envio(token, correo)


def prueba_correo_cuentas() -> str:
    """Login SMTP de las dos cuentas y un correo de prueba a ellas mismas."""
    notas = []
    vistos = False
    for n in (1, 2):
        correo = (
            os.getenv(f"CORREO_REMITENTE_{n}", "").strip()
            or os.getenv(f"EMAIL_REMITENTE_{n}", "").strip()
        )
        clave = (
            os.getenv(f"CORREO_CLAVE_{n}", "").strip()
            or os.getenv(f"EMAIL_CLAVE_{n}", "").strip()
        )
        if not correo and not clave:
            continue
        vistos = True
        if not correo:
            notas.append(f"Cuenta {n}: falta EMAIL_REMITENTE_{n}")
            continue
        if not clave:
            notas.append(f"Cuenta {n}: falta la clave de aplicación (EMAIL_CLAVE_{n})")
            continue
        lead = {
            "nombre": "Cazador de Sueño",
            "correo": correo,
            "idioma": "es",
            "tipo": "tienda",
            "pais": "República Dominicana",
        }
        try:
            asunto, cuerpo, _variante = preparar_cuerpo(lead, correo)
            asunto = "Prueba SMTP Cazador de Sueño"
            msg = construir_mensaje(lead, correo, "Prueba de login SMTP del bot B2B.\n\n" + cuerpo, asunto)
            _enviar_smtp({"n": n, "correo": correo, "clave": clave}, msg)
            notas.append(f"OK {correo}")
        except Exception as exc:
            texto = _error(exc).replace(clave, "[clave]")
            notas.append(f"ERROR {correo}: {texto}")
    if not vistos:
        return "No hay cuentas. Define EMAIL_REMITENTE_1 y EMAIL_REMITENTE_2 en el .env del servidor."
    return "\n".join(notas)


def revisar_unsubscribe() -> list[str]:
    """Lee respuestas IMAP. 'unsubscribe' entra en la lista de exclusión."""
    if os.getenv("B2B_ENVIO_REAL", "0").strip() != "1":
        return []
    import imaplib

    host = os.getenv("IMAP_HOST", "imap.gmail.com").strip() or "imap.gmail.com"
    bajados = []
    for n in (1, 2):
        correo = (
            os.getenv(f"CORREO_REMITENTE_{n}", "").strip()
            or os.getenv(f"EMAIL_REMITENTE_{n}", "").strip()
        )
        clave = (
            os.getenv(f"CORREO_CLAVE_{n}", "").strip()
            or os.getenv(f"EMAIL_CLAVE_{n}", "").strip()
        )
        if not correo or not clave:
            continue
        try:
            imap = imaplib.IMAP4_SSL(host, 993)
            imap.login(correo, clave)
            imap.select("INBOX")
            _tipo, datos = imap.search(None, "UNSEEN")
            ids = (datos[0] or b"").split() if datos else []
            for num in ids[-30:]:
                _t, msg_data = imap.fetch(num, "(BODY.PEEK[TEXT] BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])")
                crudo = b""
                for parte in msg_data or []:
                    if isinstance(parte, tuple) and len(parte) > 1:
                        crudo += parte[1] or b""
                texto = crudo.decode("utf-8", errors="replace")
                if not re.search(r"\bunsubscribe\b|\bBAJA\b", texto, re.I):
                    continue
                origen = ""
                hallado = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", texto)
                if hallado:
                    origen = hallado.group(0).lower()
                if origen and origen != correo.lower():
                    excluir_correo(origen, "unsubscribe")
                    bajados.append(origen)
            imap.logout()
        except Exception as exc:
            registrar_evento({"evento": "imap_bajas_fallo", "cuenta": n, "error": _error(exc).replace(clave, "[clave]")})
    return bajados
