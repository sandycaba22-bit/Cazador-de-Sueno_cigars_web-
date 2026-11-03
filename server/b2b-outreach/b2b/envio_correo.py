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
from b2b.zona_horaria import (
    aplicar_zona,
    en_ventana,
    frase_programado,
    ordenar_ola,
    primer_hueco,
)

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
    from b2b.io_atomico import escribir_json

    escribir_json(_ruta_envios(), data)


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
    """El 15 era el reparto de dos cuentas. Con una sola, el defecto es el techo de 24 h."""
    return max(1, _int_env("B2B_ENVIO_MAX_POR_CUENTA", 30))


def _techo_cuenta(activas: list[dict]) -> int:
    """Una cuenta usa las 30 de CORREOS_MAX_DIA. Un 15 viejo en el entorno no la parte a la mitad."""
    if len(activas) <= 1:
        return _tope_24h()
    return max_por_cuenta()


def cuentas_activas() -> list[dict]:
    """Solo la cuenta 1. Una cuenta 2 vacía, o con la dirección vieja, no es una cuenta."""
    real = envio_real()
    activas = []
    omitidas = []
    for n in (1,):
        correo = (
            os.getenv(f"CORREO_REMITENTE_{n}", "").strip()
            or os.getenv(f"EMAIL_REMITENTE_{n}", "").strip()
        )
        clave = (
            os.getenv(f"CORREO_CLAVE_{n}", "").strip()
            or os.getenv(f"EMAIL_CLAVE_{n}", "").strip()
        )
        if not correo or "@" not in correo:
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
    """Día del operador (por defecto Santo Domingo). Solo para la rampa y las tandas, no para el tope de 24 h."""
    from b2b.zona_horaria import zona_operador

    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(zona_operador()).strftime("%Y-%m-%d")


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
        if item.get("estado") not in (None, "en_cola", "programado"):
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
    if len(activas) <= 1:
        return total
    idx = next((i for i, c in enumerate(activas) if c["n"] == n), 0)
    base, resto = divmod(total, len(activas))
    parte = base + (1 if idx < resto else 0)
    return max(0, min(max_por_cuenta(), parte))


def _tope_24h() -> int:
    """Techo duro en 24 horas corridas. Si la variable falta o no es un número, 30."""
    return max(1, _int_env("CORREOS_MAX_DIA", 30))


def _dia_de_envio(envio: dict, momento_campo: str = "cuando") -> str:
    marca = _parse_marca(envio.get(momento_campo) or "")
    if marca is not None:
        return _dia_rd(marca)
    return str(envio.get("dia") or "")


def _enviados_dia(data: dict, n: int | None, momento: datetime) -> int:
    dia = _dia_rd(momento)
    total = 0
    for envio in data.get("envios") or []:
        if not envio.get("ok"):
            continue
        if n is not None and envio.get("cuenta") != n:
            continue
        if _dia_de_envio(envio) == dia:
            total += 1
    return total


def _en_cola_dia(n: int | None, momento: datetime, *, excluir_token: str = "") -> int:
    dia = _dia_rd(momento)
    total = 0
    for _path, item in items_en_cola():
        if excluir_token and item.get("token") == excluir_token:
            continue
        if n is not None and item.get("cuenta") != n:
            continue
        cuando = _parse_marca(item.get("enviar_despues_de") or "")
        if cuando is not None and _dia_rd(cuando) == dia:
            total += 1
    return total


def _alinear(marca: datetime | None, ancla: datetime) -> tuple[datetime, datetime] | None:
    if marca is None:
        return None
    if ancla.tzinfo is None:
        ancla = ancla.replace(tzinfo=timezone.utc)
    if marca.tzinfo is None:
        marca = marca.replace(tzinfo=timezone.utc)
    return marca, ancla


def _dentro_de_24h(marca: datetime | None, ancla: datetime) -> bool:
    """Envíos ya hechos: (ancla-24h, ancla]. No es el día calendario."""
    par = _alinear(marca, ancla)
    if par is None:
        return False
    marca, ancla = par
    return ancla - timedelta(hours=24) < marca <= ancla


def _solapa_24h(marca: datetime | None, ancla: datetime) -> bool:
    """Cola: cuenta lo programado hasta 24 h antes o después, para no amontonar."""
    par = _alinear(marca, ancla)
    if par is None:
        return False
    marca, ancla = par
    return abs((marca - ancla).total_seconds()) <= 24 * 3600


def _enviados_hoy(data: dict, n: int, momento: datetime) -> int:
    return sum(
        1
        for e in data.get("envios") or []
        if e.get("cuenta") == n and e.get("ok") and _dentro_de_24h(_parse_marca(e.get("cuando") or ""), momento)
    )


def _total_hoy(data: dict, momento: datetime) -> int:
    return sum(
        1
        for e in data.get("envios") or []
        if e.get("ok") and _dentro_de_24h(_parse_marca(e.get("cuando") or ""), momento)
    )


def _en_cola_hoy(n: int | None, momento: datetime, *, excluir_token: str = "") -> int:
    total = 0
    for _path, item in items_en_cola():
        if excluir_token and item.get("token") == excluir_token:
            continue
        if n is not None and item.get("cuenta") != n:
            continue
        cuando = _parse_marca(item.get("enviar_despues_de") or "")
        if _solapa_24h(cuando, momento):
            total += 1
    return total


def _marcas_comprometidas(data: dict, ancla: datetime, *, excluir_token: str = "") -> list[datetime]:
    marcas: list[datetime] = []
    for envio in data.get("envios") or []:
        if not envio.get("ok"):
            continue
        marca = _parse_marca(envio.get("cuando") or "")
        if _dentro_de_24h(marca, ancla):
            marcas.append(marca)
    for _path, item in items_en_cola():
        if excluir_token and item.get("token") == excluir_token:
            continue
        marca = _parse_marca(item.get("enviar_despues_de") or "")
        if _solapa_24h(marca, ancla):
            marcas.append(marca)
    return marcas


def _comprometidos_cuenta(data: dict, n: int, momento: datetime, *, excluir_token: str = "") -> int:
    return _enviados_hoy(data, n, momento) + _en_cola_hoy(n, momento, excluir_token=excluir_token)


def _total_comprometido(data: dict, momento: datetime, *, excluir_token: str = "") -> int:
    return _total_hoy(data, momento) + _en_cola_hoy(None, momento, excluir_token=excluir_token)


def _activas_sin_pausa(data: dict | None = None) -> list[dict]:
    data = data if data is not None else _load()
    pausadas = data.get("pausadas") or {}
    return [c for c in cuentas_activas() if str(c["n"]) not in pausadas]


def _cuenta_cabe(data: dict, cuenta: dict, activas: list[dict], momento: datetime, *, excluir_token: str = "") -> bool:
    n = cuenta["n"]
    if _comprometidos_cuenta(data, n, momento, excluir_token=excluir_token) >= _techo_cuenta(activas):
        return False
    cupo = _cupo_cuenta(n, activas, momento)
    dia = _enviados_dia(data, n, momento) + _en_cola_dia(n, momento, excluir_token=excluir_token)
    return dia < cupo


def _total_cabe(data: dict, momento: datetime, *, excluir_token: str = "") -> bool:
    if _total_comprometido(data, momento, excluir_token=excluir_token) >= _tope_24h():
        return False
    dia = _enviados_dia(data, None, momento) + _en_cola_dia(None, momento, excluir_token=excluir_token)
    return dia < _tope_efectivo(momento)


def _al_dia_siguiente(momento: datetime, lead: dict) -> datetime:
    from b2b.zonas import tz as tz_lugar

    zona = tz_lugar(str(lead.get("zona_iana") or "America/New_York"))
    local = momento.astimezone(zona)
    manana = datetime(local.year, local.month, local.day, tzinfo=zona) + timedelta(days=1)
    return primer_hueco(manana.astimezone(timezone.utc), lead)


def elegir_cuenta(momento: datetime | None = None, *, excluir_token: str = "") -> dict | None:
    momento = momento or _ahora()
    data = _load()
    activas = _activas_sin_pausa(data)
    if not activas:
        return None
    if not _total_cabe(data, momento, excluir_token=excluir_token):
        return None
    inicio = int(data.get("turno") or 0) % len(activas)
    candidatos = []
    for i, cuenta in enumerate(activas):
        if _cuenta_cabe(data, cuenta, activas, momento, excluir_token=excluir_token):
            carga = _comprometidos_cuenta(data, cuenta["n"], momento, excluir_token=excluir_token)
            candidatos.append(((carga, (i - inicio) % len(activas)), cuenta))
    if not candidatos:
        return None
    candidatos.sort(key=lambda fila: fila[0])
    return candidatos[0][1]


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
    es_seguimiento: bool = False,
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
    if not es_seguimiento:
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
    """Primer hueco local del negocio. Si el cupo de 24 h está lleno, el siguiente hueco libre."""
    ahora = ahora or _ahora()
    if ahora.tzinfo is None:
        ahora = ahora.replace(tzinfo=timezone.utc)
    aplicar_zona(lead)
    ultimo = ahora
    hay_cola = False
    for _path, item in items_en_cola():
        marca = _parse_marca(item.get("enviar_despues_de") or "")
        if not marca:
            continue
        hay_cola = True
        if marca > ultimo:
            ultimo = marca
    previsto = (ultimo + _delta_pausa()) if hay_cola else ahora
    if previsto < ahora:
        previsto = ahora
    previsto = primer_hueco(previsto, lead)
    data = _load()
    if not _activas_sin_pausa(data):
        return previsto
    for _ in range(21):
        if elegir_cuenta(previsto) is not None:
            return previsto
        lleno_24h = _total_comprometido(data, previsto) >= _tope_24h()
        activas = _activas_sin_pausa(data)
        cuentas_24h = bool(activas) and all(
            _comprometidos_cuenta(data, c["n"], previsto) >= max_por_cuenta() for c in activas
        )
        if lleno_24h or cuentas_24h:
            marcas = _marcas_comprometidas(data, previsto)
            if not marcas:
                return previsto
            previsto = primer_hueco(min(marcas) + timedelta(hours=24, seconds=1), lead)
        else:
            previsto = _al_dia_siguiente(previsto, lead)
    return previsto


def texto_ventana(lead: dict, ahora: datetime | None = None) -> str:
    ahora = ahora or _ahora()
    if ahora.tzinfo is None:
        ahora = ahora.replace(tzinfo=timezone.utc)
    aplicar_zona(lead)
    return frase_programado(programar_momento(lead, ahora), lead, ahora)


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
        "zona_iana": lead.get("zona_iana") or "",
        "puntaje": lead.get("puntaje"),
        "nombre": lead.get("nombre") or "",
        "message_id": lead.get("message_id"),
        "intentos": 0,
        "estado": "programado",
        "lead": {
            "nombre": lead.get("nombre") or "",
            "correo": lead.get("correo") or "",
            "web": lead.get("web") or "",
            "idioma": lead.get("idioma") or "en",
            "pais": lead.get("pais") or "",
            "estado": lead.get("estado") or lead.get("pais") or "",
            "ciudad": lead.get("ciudad") or "",
            "lat": lead.get("lat"),
            "lon": lead.get("lon"),
            "tipo": lead.get("tipo") or "",
            "puntaje": lead.get("puntaje"),
            "zona_iana": lead.get("zona_iana") or "",
            "zona_fuente": lead.get("zona_fuente") or "",
            "zona_exacta": bool(lead.get("zona_exacta")),
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
        "zona": ((item.get("lead") or {}).get("zona_busqueda")
                 or (item.get("lead") or {}).get("estado")
                 or item.get("lugar")
                 or ""),
    })
    data["ultimo_envio"] = momento.isoformat(timespec="seconds")
    _save(data)
    registrar_message_id_enviado(message_id)
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


def _recuperar_tras_fallo_correo(item: dict, motivo: str) -> None:
    """Tras ⏳ el cupo ya se cerró: si SMTP falla, reabre el lead y avisa por Telegram."""
    nombre = item.get("nombre") or item.get("correo") or "el local"
    motivo_limpio = (motivo or "error SMTP").strip()[:300]
    from b2b.alertas_operador import alertar

    alertar(
        f"smtp_recupera_{item.get('token') or nombre}",
        f"⚠️ Correo falló después de encolar a {nombre}: {motivo_limpio}. Reabrí la tarjeta.",
    )
    lead = dict(item.get("lead") or {})
    lead.setdefault("nombre", item.get("nombre") or "")
    lead.setdefault("correo", item.get("correo") or "")
    lead.setdefault("web", (item.get("lead") or {}).get("web") or "")
    lead["telegram_notificado"] = False
    lead.pop("caducada_final", None)
    lead["estado_tarjeta"] = "smtp_fallo"
    lead["omitido_motivo"] = ""
    lead["motivo_smtp_fallo"] = motivo_limpio
    try:
        guardar_estado_lead(lead, "aprobado", motivo_smtp_fallo=motivo_limpio)
    except Exception as exc:
        registrar_evento({"evento": "recupera_smtp_estado_fallo", "error": _error(exc)})
    inbox_path = ""
    try:
        from b2b.telegram_gestion import resolver_pendiente

        pend = resolver_pendiente(item.get("token") or "") or {}
        inbox_path = (pend.get("inbox_path") or "").strip()
    except Exception:
        inbox_path = ""
    from b2b.paths import queue_dir

    cola = queue_dir()
    dest: Path | None = None
    if inbox_path:
        candidato = Path(inbox_path)
        if candidato.is_file() or candidato.parent.is_dir():
            dest = candidato
    if dest is None and cola is not None:
        slug = re.sub(r"[^a-z0-9]+", "-", (lead.get("nombre") or "lead").casefold()).strip("-")[:50] or "lead"
        dest = cola / "inbox" / f"smtp-fallo-{slug}.json"
    if dest is None:
        registrar_evento({
            "evento": "recupera_smtp_sin_inbox",
            "nombre": nombre,
            "motivo": motivo_limpio,
        })
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    previo = {}
    if dest.is_file():
        try:
            previo = json.loads(dest.read_text(encoding="utf-8"))
            if not isinstance(previo, dict):
                previo = {}
        except (OSError, json.JSONDecodeError):
            previo = {}
    previo.update(lead)
    previo["telegram_notificado"] = False
    previo.pop("caducada_final", None)
    previo["estado_tarjeta"] = "smtp_fallo"
    dest.write_text(json.dumps(previo, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    registrar_evento({
        "evento": "tarjeta_reabierta_smtp_fallo",
        "nombre": nombre,
        "motivo": motivo_limpio,
        "inbox": str(dest),
    })


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

        from b2b.telegram_prospecto import teclado_cerrado

        editar_mensaje_telegram(int(message_id), texto, teclado_cerrado())
    except Exception as exc:
        registrar_evento({"evento": "editar_tarjeta_fallo", "error": _error(exc)})


def _reprogramar_por_tope(item: dict, path: Path, momento: datetime) -> None:
    lead = dict(item.get("lead") or {})
    lead.setdefault("estado", item.get("lugar") or "")
    lead.setdefault("pais", item.get("lugar") or "")
    aplicar_zona(lead)
    marcas = _marcas_comprometidas(_load(), momento, excluir_token=item.get("token") or "")
    base = (min(marcas) + timedelta(hours=24, seconds=1)) if marcas else (momento + timedelta(hours=24))
    siguiente = primer_hueco(base, lead)
    item["enviar_despues_de"] = siguiente.isoformat(timespec="seconds")
    item["estado"] = "programado"
    item["zona_iana"] = lead.get("zona_iana") or ""
    item["lead"] = {**(item.get("lead") or {}), **{k: lead.get(k) for k in ("zona_iana", "zona_fuente", "zona_exacta")}}
    path.write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _editar_estado(item, frase_programado(siguiente, lead, momento))


def _fallo_temporal(item: dict, path: Path, momento: datetime, exc: BaseException) -> None:
    intentos = int(item.get("intentos") or 0) + 1
    item["intentos"] = intentos
    if intentos >= 3:
        item["estado"] = "fallo"
        motivo = _error(exc)
        item["motivo_fallo"] = motivo
        _archivar_item(path, item)
        nombre = item.get("nombre") or item.get("correo") or "el local"
        registrar_evento({"evento": "smtp_fallo", "error": motivo, "cuenta": item.get("cuenta")})
        from b2b.alertas_operador import alertar

        alertar(
            f"smtp_{item.get('token') or nombre}",
            f"⚠️ Fallo SMTP a {nombre}: {motivo[:240]}",
        )
        _editar_estado(item, f"Falló: {motivo[:180]}")
        _recuperar_tras_fallo_correo(item, motivo)
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
        activas = _activas_sin_pausa(data)
        if candidata is not None and _total_cabe(data, momento, excluir_token=token):
            if _cuenta_cabe(data, candidata, activas, momento, excluir_token=token):
                return candidata
    return elegir_cuenta(momento, excluir_token=token)


def _cuerpo_seguimiento(nombre: str, idioma: str, paso: int, cuenta: str) -> str:
    from b2b.redactor import WHOLESALE_URL, asegurar_pie

    if idioma == "es":
        texto = (
            f"Hola, equipo de {nombre}:\n\n"
            f"Les escribo de nuevo, {paso} días después, por si pudieron ver la línea. "
            f"El catálogo sigue aquí: {WHOLESALE_URL}\n"
        )
    else:
        texto = (
            f"Hello {nombre} team,\n\n"
            f"I'm writing again, {paso} days later, in case you had a chance to look at the line. "
            f"The catalog is still here: {WHOLESALE_URL}\n"
        )
    if cuenta:
        texto += f"\n{cuenta}\n"
    return asegurar_pie(texto, "es" if idioma == "es" else "en")


def _materializar_seguimientos(ahora: datetime) -> None:
    """Pasa a la cola los seguimientos (días 4 y 10) cuyo hueco local ya llegó."""
    from b2b.redactor import asunto_correo
    from b2b.seguimiento import marcar_plan, planes_listos

    for clave, seg, plan in planes_listos(ahora):
        lead = dict(seg.get("lead") or {})
        lead.setdefault("correo", seg.get("correo") or "")
        lead.setdefault("nombre", seg.get("nombre") or "")
        dia = int(plan.get("dia") or 0)
        ok, motivo = puede_enviar_correo(lead, ahora, es_seguimiento=True)
        if not ok:
            marcar_plan(clave, dia, "cancelado", motivo)
            continue
        token = "seg-" + re.sub(r"[^a-z0-9]+", "-", clave.lower()).strip("-")[:40] + f"-{dia}"
        path = outbox_dir() / f"{token}.json"
        if path.is_file() or (archivo_dir() / f"{token}.json").is_file():
            marcar_plan(clave, dia, "programado", "", materializado=True)
            continue
        aplicar_zona(lead)
        idioma = lead.get("idioma") or "en"
        elegida = elegir_cuenta(ahora)
        cuenta = (elegida or {}).get("correo") or ""
        cuando = _parse_marca(plan.get("enviar_despues_de") or "") or ahora
        item = {
            "token": token,
            "tipo": "seguimiento",
            "paso": dia,
            "correo": (lead.get("correo") or "").strip(),
            "dominio": _dominio_correo(lead.get("correo") or ""),
            "cuenta": (elegida or {}).get("n"),
            "cuenta_correo": cuenta,
            "asunto": "Re: " + asunto_correo(lead.get("nombre") or "", idioma),
            "variante": "A",
            "cuerpo": _cuerpo_seguimiento(lead.get("nombre") or "your shop", idioma, dia, cuenta),
            "enviar_despues_de": cuando.isoformat(timespec="seconds"),
            "lugar": lugar_del_lead(lead),
            "zona_iana": lead.get("zona_iana") or "",
            "puntaje": lead.get("puntaje"),
            "nombre": lead.get("nombre") or "",
            "intentos": 0,
            "estado": "programado",
            "lead": lead,
        }
        path.write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        marcar_plan(clave, dia, "programado", "", materializado=True)


def texto_cola_programada(limite: int = 20) -> str:
    filas = []
    for _path, item in items_en_cola():
        cuando = _parse_marca(item.get("enviar_despues_de") or "")
        if cuando is None:
            continue
        lead = dict(item.get("lead") or {})
        lead.setdefault("ciudad", "")
        lead.setdefault("estado", item.get("lugar") or "")
        lead.setdefault("zona_iana", item.get("zona_iana") or "")
        filas.append((cuando, item, lead))
    filas.sort(key=lambda fila: fila[0])
    if not filas:
        return "📧 No hay correos programados."
    from b2b.zona_horaria import linea_horario

    lineas = [f"📧 Programados: {len(filas)}"]
    for cuando, item, lead in filas[:limite]:
        lineas.append(f"• {item.get('nombre') or '—'} — {linea_horario(cuando, lead)}")
    if len(filas) > limite:
        lineas.append(f"… y {len(filas) - limite} más.")
    return "\n".join(lineas)


def procesar_outbox(ahora: datetime | None = None) -> int:
    from b2b.telegram_control import esta_pausado

    if esta_pausado():
        return 0
    ahora = ahora or _ahora()
    if ahora.tzinfo is None:
        ahora = ahora.replace(tzinfo=timezone.utc)
    _materializar_seguimientos(ahora)
    hechos = 0
    listos = []
    for path, item in items_en_cola():
        cuando = _parse_marca(item.get("enviar_despues_de") or "")
        if not cuando or cuando > ahora:
            continue
        fila = dict(item)
        fila["_path"] = path
        fila["_cuando_orden"] = cuando
        listos.append(fila)
    for item in ordenar_ola(listos):
        path = item.pop("_path")
        item.pop("_cuando_orden", None)
        lead = dict(item.get("lead") or {})
        lead["correo"] = item.get("correo") or lead.get("correo")
        lead["nombre"] = item.get("nombre") or lead.get("nombre")
        lead.setdefault("estado", item.get("lugar") or lead.get("estado") or "")
        lead.setdefault("pais", lead.get("pais") or item.get("lugar") or "")
        aplicar_zona(lead)
        item["zona_iana"] = lead.get("zona_iana") or ""
        item["lead"] = lead
        if not en_ventana(ahora, lead):
            siguiente = primer_hueco(ahora, lead)
            item["enviar_despues_de"] = siguiente.isoformat(timespec="seconds")
            item["estado"] = "programado"
            path.write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            _editar_estado(item, frase_programado(siguiente, lead, ahora))
            continue
        es_seguimiento = item.get("tipo") == "seguimiento"
        ok_envio, motivo_envio = puede_enviar_correo(lead, ahora, es_seguimiento=es_seguimiento)
        if not ok_envio:
            item["estado"] = "omitido"
            item["motivo_fallo"] = motivo_envio
            _editar_estado(item, "Omitida")
            _archivar_item(path, item)
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
        if es_seguimiento and item.get("cuerpo"):
            asunto, cuerpo, variante = item.get("asunto") or "", item["cuerpo"], item.get("variante") or "A"
        else:
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
            _recuperar_tras_fallo_correo(item, error_catalogo)
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
                item["motivo_fallo"] = _error(exc)
                guardar_estado_lead(lead, "reboto")
                _editar_estado(item, "⚠️ Rebotó al enviar")
                _archivar_item(path, item)
                _recuperar_tras_fallo_correo(item, item["motivo_fallo"])
                continue
            _fallo_temporal(item, path, ahora, exc)
            continue
        if envio_real():
            _registrar_ok(item, ahora, msg["Message-ID"])
        else:
            _registrar_simulado(item, ahora, msg["Message-ID"])
        _avanzar_turno(cuenta)
        from b2b.zonas import tz as tz_lugar

        hora = ahora.astimezone(tz_lugar(str(lead.get("zona_iana") or "America/New_York"))).strftime("%H:%M")
        item["estado"] = "enviado"
        item["message_id_correo"] = msg["Message-ID"]
        nombre = lead.get("nombre") or item.get("correo") or "el negocio"
        _editar_estado(item, f"Enviado a {nombre} a las {hora}")
        try:
            from b2b.despachador_tarjetas import cerrar_tarjeta
            from b2b.seguimiento import registrar_enviado

            tok = item.get("token") or ""
            if tok:
                cerrar_tarjeta(tok, ahora=ahora, espera_seg=0)
            lead_seg = dict(item.get("lead") or {})
            lead_seg.setdefault("correo", item.get("correo") or "")
            lead_seg.setdefault("nombre", item.get("nombre") or "")
            lead_seg.setdefault("web", (item.get("lead") or {}).get("web") or "")
            registrar_enviado(lead_seg, "correo", cuando=ahora)
            if not es_seguimiento:
                from b2b.seguimiento import anotar_planes_correo

                anotar_planes_correo(lead_seg, ahora)
        except Exception as exc:
            registrar_evento({"evento": "cierre_tras_smtp_fallo", "error": str(exc)[:200]})
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
    item = encolar_envio(lead, token, ahora=ahora)
    if not item:
        return "⚠️ No envié: no se pudo preparar el correo (dirección postal, baja o cupo)"
    cuando = _parse_marca(item.get("enviar_despues_de") or "") or ahora
    datos = dict(item.get("lead") or lead)
    datos.setdefault("zona_iana", item.get("zona_iana") or "")
    return frase_programado(cuando, datos, ahora)


def prueba_correo_cuentas() -> str:
    """Login SMTP de la cuenta 1 y un correo de prueba a ella misma."""
    notas = []
    vistos = False
    for n in (1,):
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
        return "No hay cuentas. Define EMAIL_REMITENTE_1 en el .env del servidor."
    return "\n".join(notas)


_NO_REPLY_RE = re.compile(
    r"^(no[-_]?reply|noreply|donotreply|mailer-daemon|notification|notifications|"
    r"notify|bounce|bounces|auto[-_]?reply)@",
    re.I,
)


def _ruta_imap_estado() -> Path:
    return _state_file("imap_bajas_estado.json")


def _cargar_imap_estado() -> dict:
    path = _ruta_imap_estado()
    if not path.is_file():
        return {"procesados": [], "message_ids_nuestros": [], "ultimo_check": "", "backoff_hasta": ""}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"procesados": [], "message_ids_nuestros": [], "ultimo_check": "", "backoff_hasta": ""}
    data.setdefault("procesados", [])
    data.setdefault("message_ids_nuestros", [])
    return data


def _guardar_imap_estado(data: dict) -> None:
    from b2b.io_atomico import escribir_json

    data["procesados"] = list(data.get("procesados") or [])[-5000:]
    data["message_ids_nuestros"] = list(data.get("message_ids_nuestros") or [])[-2000:]
    escribir_json(_ruta_imap_estado(), data)


def registrar_message_id_enviado(message_id: str) -> None:
    mid = (message_id or "").strip()
    if not mid:
        return
    data = _cargar_imap_estado()
    if mid not in data["message_ids_nuestros"]:
        data["message_ids_nuestros"].append(mid)
        _guardar_imap_estado(data)


def _correos_contactados() -> set[str]:
    vistos: set[str] = set()
    arch = archivo_dir()
    if arch.is_dir():
        for path in arch.glob("*.json"):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(item, dict):
                c = (item.get("correo") or "").strip().lower()
                if c:
                    vistos.add(c)
    path = _state_file("registro_leads.json")
    if path.is_file():
        try:
            reg = json.loads(path.read_text(encoding="utf-8"))
            for c in reg.get("correos") or []:
                if c:
                    vistos.add(str(c).strip().lower())
        except (OSError, json.JSONDecodeError):
            pass
    return vistos


_RE_FINAL = re.compile(r"final-recipient:\s*rfc822;\s*([^\s<>]+@[^\s<>]+)", re.I)
_RE_FAILED = re.compile(r"[\w.+\-]+@[\w.\-]+\.[a-z]{2,}", re.I)


def correo_de_rebote(from_hdr: str, subject: str, cuerpo: str) -> str:
    """Si el mensaje es un rebote de Mail Delivery Subsystem, devuelve el correo inválido."""
    texto = f"{from_hdr}\n{subject}\n{cuerpo}"
    bajo = texto.lower()
    if "mail delivery subsystem" not in bajo and "mailer-daemon" not in bajo:
        return ""
    m = _RE_FINAL.search(texto)
    if m:
        return m.group(1).strip().lower().rstrip(".,;")
    for candidato in _RE_FAILED.findall(texto):
        c = candidato.strip().lower()
        if c.endswith(("@gmail.com",)) and "cazadordesueno" in c:
            continue
        if "mailer-daemon" in c or c.startswith("mailer-daemon"):
            continue
        return c
    return ""


def aplicar_rebote(correo: str, lead: dict | None = None) -> str:
    """Marca el correo inválido y deja el lead en WhatsApp o formulario."""
    correo = (correo or "").strip().lower()
    if not correo:
        return ""
    marcar_correo_invalido(correo)
    datos = dict(lead or {})
    datos["correo"] = correo
    datos["correo_invalido"] = correo
    datos["sin_correo_publico"] = True
    tiene_tel = bool((datos.get("telefono") or datos.get("whatsapp") or datos.get("telefono_internacional") or "").strip())
    canal = "whatsapp" if tiene_tel else "formulario"
    datos["canal_siguiente"] = canal
    datos.pop("correo", None)
    try:
        guardar_estado_lead(
            {"nombre": datos.get("nombre") or correo, "correo": correo, "web": datos.get("web") or ""},
            "reboto",
            canal_siguiente=canal,
        )
    except Exception as exc:
        registrar_evento({"evento": "rebote_estado_fallo", "error": _error(exc)})
    from b2b.alertas_operador import alertar

    alertar(
        f"rebote_{correo}",
        f"⚠️ Rebote (Mail Delivery Subsystem) de {correo}. Lo marqué inválido y el lead pasa a {canal}.",
    )
    registrar_evento({"evento": "rebote_correo", "correo": correo, "canal": canal})
    return canal


def _es_remitente_ruido(direccion: str) -> bool:
    d = (direccion or "").strip().lower()
    if not d or "@" not in d:
        return True
    if _NO_REPLY_RE.search(d):
        return True
    host = d.split("@", 1)[-1]
    if host.endswith((".metamail.com", "priority.instagram.com", "facebookmail.com", "mail.instagram.com")):
        return True
    return False


def _imap_intervalo_seg() -> int:
    try:
        return max(60, int(os.getenv("B2B_IMAP_INTERVALO_SEG", "900") or "900"))
    except ValueError:
        return 900


def revisar_unsubscribe() -> list[str]:
    """Lee IMAP solo para respuestas a nuestros envíos. Ignora no-reply y no repite UIDs."""
    if os.getenv("B2B_ENVIO_REAL", "0").strip() != "1":
        return []
    import email
    import imaplib
    from email.header import decode_header
    from email.utils import parseaddr

    estado = _cargar_imap_estado()
    ahora = _ahora()
    backoff = _parse_marca(estado.get("backoff_hasta") or "")
    if backoff and ahora < backoff:
        return []
    ultimo = _parse_marca(estado.get("ultimo_check") or "")
    if ultimo and (ahora - ultimo).total_seconds() < _imap_intervalo_seg():
        return []

    host = os.getenv("IMAP_HOST", "imap.gmail.com").strip() or "imap.gmail.com"
    bajados: list[str] = []
    nuestros = {m.strip() for m in estado.get("message_ids_nuestros") or [] if m}
    contactados = _correos_contactados()
    procesados = set(estado.get("procesados") or [])

    def _decodificar(valor: str) -> str:
        partes = []
        for texto, enc in decode_header(valor or ""):
            if isinstance(texto, bytes):
                partes.append(texto.decode(enc or "utf-8", errors="replace"))
            else:
                partes.append(texto)
        return "".join(partes)

    for n in (1,):
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
            for num in ids[-40:]:
                clave_uid = f"{n}:{num.decode() if isinstance(num, bytes) else num}"
                if clave_uid in procesados:
                    continue
                _t, msg_data = imap.fetch(num, "(RFC822.HEADER BODY.PEEK[TEXT])")
                crudo = b""
                for parte in msg_data or []:
                    if isinstance(parte, tuple) and len(parte) > 1:
                        crudo += parte[1] or b""
                msg = email.message_from_bytes(crudo)
                mid = (msg.get("Message-ID") or "").strip()
                if mid and mid in procesados:
                    procesados.add(clave_uid)
                    continue
                from_hdr = _decodificar(msg.get("From") or "")
                _, origen = parseaddr(from_hdr)
                origen = (origen or "").strip().lower()
                in_reply = (msg.get("In-Reply-To") or "") + " " + (msg.get("References") or "")
                es_respuesta = any(m and m in in_reply for m in nuestros)
                es_contactado = origen in contactados
                procesados.add(clave_uid)
                if mid:
                    procesados.add(mid)
                cuerpo = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            payload = part.get_payload(decode=True) or b""
                            cuerpo += payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                else:
                    payload = msg.get_payload(decode=True) or b""
                    if isinstance(payload, bytes):
                        cuerpo = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
                    else:
                        cuerpo = str(payload)
                asunto = _decodificar(msg.get("Subject") or "")
                fallido = correo_de_rebote(from_hdr, asunto, cuerpo)
                if fallido:
                    aplicar_rebote(fallido, {"correo": fallido, "nombre": fallido})
                    continue
                if _es_remitente_ruido(origen) or origen == correo.lower():
                    continue
                if not re.search(r"\bunsubscribe\b|\bBAJA\b", cuerpo + " " + asunto, re.I):
                    continue
                if not (es_respuesta or es_contactado):
                    continue
                excluir_correo(origen, "unsubscribe")
                bajados.append(origen)
                registrar_evento({"evento": "exclusion_correo", "correo": origen, "cuenta": n})
            imap.logout()
        except Exception as exc:
            estado["backoff_hasta"] = (ahora + timedelta(minutes=30)).isoformat(timespec="seconds")
            detalle = _error(exc).replace(clave, "[clave]")
            registrar_evento({"evento": "imap_bajas_fallo", "cuenta": n, "error": detalle})
            from b2b.alertas_operador import alertar

            alertar(f"imap_{n}", f"⚠️ Fallo IMAP en la cuenta {n}: {detalle[:240]}")
    estado["procesados"] = list(procesados)[-5000:]
    estado["ultimo_check"] = ahora.isoformat(timespec="seconds")
    _guardar_imap_estado(estado)
    return bajados
