"""Cola global de tarjetas: hasta N abiertas; al resolver una sale la siguiente."""
from __future__ import annotations

import json
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from b2b.logging_ops import registrar_evento
from b2b.paths import state_file
from b2b.telegram_control import esta_pausado, puede_enviar_telegram

_CADUCIDAD = timedelta(hours=48)
# Original + 2 reenvíos; al 3.er vencimiento queda "vencido" y no bloquea.
_MAX_REENVIOS = 2


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _ruta() -> Path:
    return state_file("despachador_tarjetas.json")


def _load() -> dict:
    path = _ruta()
    if not path.is_file():
        return {"abiertas": {}, "al_final": [], "pospuestos": {}, "forzar": 0, "proxima_en": "", "resumenes": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"abiertas": {}, "al_final": [], "pospuestos": {}, "forzar": 0, "proxima_en": "", "resumenes": {}}
    data.setdefault("abiertas", {})
    data.setdefault("al_final", [])
    data.setdefault("pospuestos", {})
    data.setdefault("forzar", 0)
    data.setdefault("proxima_en", "")
    data.setdefault("resumenes", {})
    return data


def _save(data: dict) -> None:
    from b2b.io_atomico import escribir_json

    escribir_json(_ruta(), data)


def ritmo_maximo() -> int:
    data = _load()
    if data.get("ritmo"):
        try:
            return max(1, min(3, int(data["ritmo"])))
        except (TypeError, ValueError):
            pass
    try:
        return max(1, min(3, int(os.getenv("B2B_TARJETAS_ABIERTAS_MAX", "2") or "2")))
    except ValueError:
        return 2


def set_ritmo(n: int) -> int:
    n = max(1, min(3, int(n)))
    data = _load()
    data["ritmo"] = n
    _save(data)
    return n


def _parse(marca: str) -> datetime | None:
    if not marca:
        return None
    try:
        momento = datetime.fromisoformat(marca)
    except ValueError:
        return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento


def _leer(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _guardar(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _orden(lead: dict) -> tuple:
    """Cola global por puntaje (mayor primero). Sin ordenar por tanda ni por nombre primero."""
    try:
        puntaje = -float(lead.get("puntaje") or 0)
    except (TypeError, ValueError):
        puntaje = 0.0
    try:
        rating = -float(lead.get("rating") or 0)
    except (TypeError, ValueError):
        rating = 0.0
    try:
        resenas = -int(lead.get("user_rating_count") or 0)
    except (TypeError, ValueError):
        resenas = 0
    mail = 0 if (lead.get("correo") or "").strip() else 1
    return (puntaje, mail, rating, resenas, (lead.get("nombre") or "").lower())


def _candidatos(inbox: Path) -> list[tuple[Path, dict]]:
    filas = []
    for path in inbox.glob("*.json"):
        data = _leer(path)
        if not data:
            continue
        if data.get("telegram_notificado") or data.get("caducada_final"):
            continue
        if (data.get("estado_tarjeta") or "").strip().lower() == "vencido":
            continue
        filas.append((path, data))
    data = _load()
    final = list(data.get("al_final") or [])

    def clave(item: tuple[Path, dict]) -> tuple:
        path, lead = item
        if path.name in final:
            return (1, final.index(path.name), _orden(lead))
        return (0, 0, _orden(lead))

    filas.sort(key=clave)
    return filas


def abiertas_ahora(ahora: datetime | None = None) -> dict:
    ahora = ahora or _ahora()
    data = _load()
    vivas = {}
    for token, info in (data.get("abiertas") or {}).items():
        enviada = _parse(info.get("enviada_en") or "")
        if enviada and ahora - enviada >= _CADUCIDAD:
            continue
        vivas[token] = info
    return vivas


def hay_trabajo(inbox: Path, ahora: datetime | None = None) -> bool:
    if abiertas_ahora(ahora) or _candidatos(inbox):
        return True
    from b2b.envio_correo import items_en_cola

    return bool(items_en_cola())


def _liberar_caducadas(inbox: Path, ahora: datetime) -> None:
    data = _load()
    cambio = False
    for token, info in list((data.get("abiertas") or {}).items()):
        enviada = _parse(info.get("enviada_en") or "")
        if not enviada or ahora - enviada < _CADUCIDAD:
            continue
        path = Path(info.get("inbox") or "")
        lead = _leer(path) if path.is_file() else None
        veces = int((lead or {}).get("caducidad_veces") or info.get("caducidad_veces") or 0)
        from b2b.contacto_previo import motivo_ya_contactado

        ya = motivo_ya_contactado(lead or {}) if lead else ""
        if ya or veces >= _MAX_REENVIOS:
            # Ya contactado o vencida definitiva: sale de abiertas y no bloquea la cola.
            if lead is not None:
                lead["caducada_final"] = True
                lead["estado_tarjeta"] = "ya_contactado" if ya else "vencido"
                # Si ya hubo correo, no reabrir; si solo venció sin contacto, tampoco reenviar.
                lead["telegram_notificado"] = True if ya else False
                if ya:
                    lead["omitido_motivo"] = ya
                _guardar(path, lead)
            registrar_evento({
                "evento": "tarjeta_vencida" if not ya else "tarjeta_cerrada_ya_contactado",
                "token": token,
                "nombre": (lead or {}).get("nombre") or "",
                "reenvios": veces,
                "motivo": ya or "vencido",
            })
        else:
            if lead is not None:
                lead["telegram_notificado"] = False
                lead["caducidad_veces"] = veces + 1
                lead["estado_tarjeta"] = "reencolada"
                _guardar(path, lead)
        data["abiertas"].pop(token, None)
        cambio = True
    if cambio:
        data["proxima_en"] = ""
        _save(data)


def _numerar(lead: dict, inbox: Path) -> None:
    tanda = lead.get("tanda_id") or ""
    previos = 0
    total = 0
    for path in inbox.glob("*.json"):
        otro = _leer(path)
        if not otro or (tanda and otro.get("tanda_id") != tanda):
            continue
        total += 1
        if otro.get("telegram_notificado"):
            previos += 1
    lead["numero_tarjeta"] = previos + 1
    lead["tanda_total"] = int(lead.get("tanda_total") or total or 1)


def _enviar_default(lead: dict, pais: str, inbox_path: str) -> bool:
    from b2b.telegram_prospecto import enviar_prospecto_telegram

    return bool(enviar_prospecto_telegram(lead, pais, inbox_path=inbox_path))


def cerrar_tarjeta(token: str, *, ahora: datetime | None = None, espera_seg: int | None = None) -> None:
    """Al resolver (enviar/omitir) la siguiente sale de inmediato (espera 0 por defecto)."""
    ahora = ahora or _ahora()
    data = _load()
    data["abiertas"].pop(token, None)
    if espera_seg is None:
        espera_seg = 0
    data["proxima_en"] = (ahora + timedelta(seconds=int(espera_seg))).isoformat(timespec="seconds")
    _save(data)


def posponer(token: str, inbox_path: str, *, ahora: datetime | None = None) -> str:
    """Manda el lead al final. A la tercera vez se queda como pendiente normal."""
    ahora = ahora or _ahora()
    path = Path(inbox_path) if inbox_path else None
    lead = _leer(path) if path and path.is_file() else None
    if lead is None:
        return "sin_lead"
    clave = path.name if path else token
    data = _load()
    veces = int((data.get("pospuestos") or {}).get(clave) or 0)
    if veces >= 2:
        return "limite"
    data["pospuestos"][clave] = veces + 1
    final = [n for n in data.get("al_final") or [] if n != clave]
    final.append(clave)
    data["al_final"] = final
    lead["telegram_notificado"] = False
    _guardar(path, lead)
    data["abiertas"].pop(token, None)
    data["proxima_en"] = ahora.isoformat(timespec="seconds")
    _anotar(data, lead, "despues")
    _save(data)
    return "pospuesto"


def _anotar(data: dict, lead: dict, decision: str) -> None:
    tanda = lead.get("tanda_id") or ""
    if not tanda:
        return
    resumenes = data.setdefault("resumenes", {})
    bloque = resumenes.setdefault(tanda, {
        "etiqueta": lead.get("tanda_etiqueta") or "Tanda",
        "total": int(lead.get("tanda_total") or 0),
        "objetivo": int(lead.get("tanda_objetivo") or 0),
        "aviso": lead.get("tanda_aviso") or "",
        "aprobadas": 0,
        "descartadas": 0,
        "despues": 0,
        "claves": {},
        "enviado": False,
    })
    clave = (lead.get("place_id") or lead.get("nombre") or "").strip()
    previa = (bloque.get("claves") or {}).get(clave)
    if previa == "aprobadas":
        bloque["aprobadas"] = max(0, int(bloque["aprobadas"]) - 1)
    elif previa == "descartadas":
        bloque["descartadas"] = max(0, int(bloque["descartadas"]) - 1)
    elif previa == "despues":
        bloque["despues"] = max(0, int(bloque["despues"]) - 1)
    bloque["claves"][clave] = decision
    bloque[decision] = int(bloque.get(decision) or 0) + 1


def anotar_decision(lead: dict, decision: str) -> None:
    data = _load()
    _anotar(data, lead, decision)
    _save(data)


def forzar_siguiente() -> None:
    data = _load()
    if int(data.get("forzar") or 0) >= 1:
        return
    data["forzar"] = 1
    data["proxima_en"] = ""
    _save(data)


def _resumen_pendiente(inbox: Path) -> str:
    data = _load()
    if _candidatos(inbox) or abiertas_ahora():
        return ""
    for tanda, bloque in (data.get("resumenes") or {}).items():
        if bloque.get("enviado"):
            continue
        et = bloque.get("etiqueta") or "Tanda"
        total = int(bloque.get("total") or 0)
        objetivo = int(bloque.get("objetivo") or total)
        a = int(bloque.get("aprobadas") or 0)
        d = int(bloque.get("descartadas") or 0)
        p = int(bloque.get("despues") or 0)
        rev = a + d + p
        if rev <= 0:
            continue
        linea = f"✅ {et} completa: {rev} revisadas · {a} aprobadas · {d} descartadas · {p} para después"
        if objetivo and total < objetivo:
            aviso = bloque.get("aviso") or "tope Google / sin más candidatos válidos"
            linea = f"{et}: {total} de {objetivo} ({aviso})\n" + linea
        bloque["enviado"] = True
        data["resumenes"][tanda] = bloque
        _save(data)
        return linea
    return ""


def texto_cola(inbox: Path) -> str:
    from b2b.envio_correo import items_en_cola

    faltan = len(_candidatos(inbox))
    abiertas = len(abiertas_ahora())
    en_correo = len(items_en_cola())
    return f"📋 Por revisar: {faltan}. Abiertas: {abiertas}. En cola de correo: {en_correo}."


def _cupo_tanda() -> int:
    for nombre in ("TANDA_OBJETIVO", "B2B_TARJETAS_POR_TANDA", "B2B_LEADS_POR_TANDA"):
        raw = (os.getenv(nombre) or "").strip()
        if not raw:
            continue
        try:
            return max(1, int(raw))
        except ValueError:
            continue
    return 15


def _cupo_dia() -> int:
    try:
        return max(1, int(os.getenv("B2B_TARJETAS_POR_DIA", "30") or "30"))
    except ValueError:
        return 30


def _bloque_dia(data: dict, ahora: datetime) -> tuple[dict, str]:
    from b2b.zona_horaria import zona_operador

    local = ahora.astimezone(zona_operador())
    dia = local.strftime("%Y-%m-%d")
    bloque = dict(data.get("tarjetas_dia") or {})
    if bloque.get("dia") != dia:
        bloque = {"dia": dia, "manana": 0, "tarde": 0}
    mitad = "manana" if local.hour < 12 else "tarde"
    return bloque, mitad


def _cabe_en_el_dia(ahora: datetime) -> bool:
    bloque, mitad = _bloque_dia(_load(), ahora)
    if int(bloque.get(mitad) or 0) >= _cupo_tanda():
        return False
    total = int(bloque.get("manana") or 0) + int(bloque.get("tarde") or 0)
    return total < _cupo_dia()


def _anotar_tarjeta_dia(data: dict, ahora: datetime) -> None:
    bloque, mitad = _bloque_dia(data, ahora)
    bloque[mitad] = int(bloque.get(mitad) or 0) + 1
    data["tarjetas_dia"] = bloque


def despachar(
    cola_dir: Path,
    *,
    ahora: datetime | None = None,
    enviar=None,
) -> int:
    ahora = ahora or _ahora()
    inbox = cola_dir / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    _liberar_caducadas(inbox, ahora)
    if esta_pausado():
        return 0
    enviar = enviar or _enviar_default
    enviados = 0
    intentados: set[str] = set()
    while True:
        data = _load()
        abiertas = abiertas_ahora(ahora)
        cupo = ritmo_maximo() + (1 if int(data.get("forzar") or 0) else 0)
        if len(abiertas) >= cupo:
            break
        proxima = _parse(data.get("proxima_en") or "")
        if proxima and ahora < proxima:
            break
        if not puede_enviar_telegram():
            break
        if not _cabe_en_el_dia(ahora):
            break
        fila = [(p, lead) for p, lead in _candidatos(inbox) if p.name not in intentados]
        if not fila:
            break
        path, lead = fila[0]
        intentados.add(path.name)
        from b2b.contacto_previo import motivo_ya_contactado
        from b2b.telegram_gestion import puede_avisar_prospecto, tiene_medio_contacto, ya_gestionado_telegram

        if ya_gestionado_telegram(lead) or not (puede_avisar_prospecto(lead) or tiene_medio_contacto(lead)):
            lead["telegram_notificado"] = True
            lead["omitido_motivo"] = "omitido"
            _guardar(path, lead)
            continue
        motivo_contacto = motivo_ya_contactado(lead)
        if motivo_contacto:
            # Ya hubo correo/seguimiento: no reabrir tarjeta; libera cupo si estaba abierta.
            lead["telegram_notificado"] = True
            lead["omitido_motivo"] = motivo_contacto
            lead["estado_tarjeta"] = "ya_contactado"
            _guardar(path, lead)
            from b2b.telegram_gestion import token_callback

            cerrar_tarjeta(token_callback(lead), ahora=ahora, espera_seg=0)
            registrar_evento({
                "evento": "tarjeta_omitida_ya_contactado",
                "nombre": lead.get("nombre") or "",
                "correo": lead.get("correo") or "",
                "motivo": motivo_contacto,
            })
            continue
        if int(data.get("forzar") or 0):
            data["forzar"] = 0
            _save(data)
        _numerar(lead, inbox)
        pais = (lead.get("pais") or "").strip()
        try:
            ok = bool(enviar(lead, pais, str(path)))
        except Exception as exc:
            registrar_evento({"evento": "despacho_fallo", "error": str(exc)[:400], "nombre": lead.get("nombre") or ""})
            ok = False
        if not ok:
            # No marcar notificado ni archivar: la tarjeta sigue pendiente.
            # Al final de la cola; no se reintenta en esta misma pasada.
            data = _load()
            final = [n for n in data.get("al_final") or [] if n != path.name]
            final.append(path.name)
            data["al_final"] = final
            _save(data)
            continue
        lead["telegram_notificado"] = True
        lead["estado_tarjeta"] = "abierta"
        _guardar(path, lead)
        from b2b.telegram_gestion import token_callback

        token = token_callback(lead)
        data = _load()
        data["abiertas"][token] = {
            "enviada_en": ahora.isoformat(timespec="seconds"),
            "inbox": str(path),
            "caducidad_veces": int(lead.get("caducidad_veces") or 0),
        }
        data["proxima_en"] = ""
        _anotar_tarjeta_dia(data, ahora)
        final = [n for n in data.get("al_final") or [] if n != path.name]
        data["al_final"] = final
        _save(data)
        enviados += 1
    return enviados


def resumen_si_toca(cola_dir: Path) -> str:
    return _resumen_pendiente(cola_dir / "inbox")


def sellar_tanda(inbox: Path, objetivo: int | None = None) -> int:
    if objetivo is None:
        objetivo = _cupo_tanda()
    from b2b.zona_horaria import zona_operador

    ahora = datetime.now(zona_operador())
    etiqueta = "Tanda mañana" if ahora.hour < 12 else "Tanda tarde"
    tanda_id = ahora.strftime("%Y%m%d-%H%M%S")
    pendientes = []
    for path in sorted(inbox.glob("*.json")):
        data = _leer(path)
        if not data or data.get("tanda_id") or data.get("telegram_notificado"):
            continue
        pendientes.append((path, data))
    total = len(pendientes)
    if not total:
        return 0
    aviso = "" if total >= objetivo else "tope Google / sin más candidatos válidos"
    for path, data in pendientes:
        data["tanda_id"] = tanda_id
        data["tanda_etiqueta"] = etiqueta
        data["tanda_objetivo"] = objetivo
        data["tanda_total"] = total
        data["tanda_aviso"] = aviso
        _guardar(path, data)
    # Deja rastro en resumenes aunque aún no se haya despachado ninguna tarjeta.
    estado = _load()
    resumenes = estado.setdefault("resumenes", {})
    if tanda_id not in resumenes:
        resumenes[tanda_id] = {
            "etiqueta": etiqueta,
            "total": total,
            "objetivo": objetivo,
            "aviso": aviso,
            "aprobadas": 0,
            "descartadas": 0,
            "despues": 0,
            "claves": {},
            "enviado": False,
        }
        _save(estado)
    return total


def intervalo_poll(hay: bool) -> int:
    if hay:
        try:
            return max(1, int(os.getenv("B2B_TELEGRAM_POLL_SECONDS", "3") or "3"))
        except ValueError:
            return 3
    try:
        return max(5, int(os.getenv("B2B_POLL_SECONDS", "15") or "15"))
    except ValueError:
        return 15
