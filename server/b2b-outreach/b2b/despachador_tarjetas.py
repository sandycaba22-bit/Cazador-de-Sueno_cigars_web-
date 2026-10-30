"""Suelta tarjetas de a una o dos. Si nadie toca un botón, no sale la siguiente."""
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
    path = _ruta()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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
    mail = 0 if (lead.get("correo") or "").strip() else 1
    try:
        rating = -float(lead.get("rating") or 0)
    except (TypeError, ValueError):
        rating = 0
    try:
        resenas = -int(lead.get("user_rating_count") or 0)
    except (TypeError, ValueError):
        resenas = 0
    return (mail, rating, resenas, (lead.get("nombre") or "").lower())


def _candidatos(inbox: Path) -> list[tuple[Path, dict]]:
    filas = []
    for path in inbox.glob("*.json"):
        data = _leer(path)
        if not data or data.get("telegram_notificado") or data.get("caducada_final"):
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
    from b2b.envio_correo import outbox_dir

    return any(outbox_dir().glob("*.json"))


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
        if veces >= 1:
            if lead is not None:
                lead["caducada_final"] = True
                lead["telegram_notificado"] = True
                _guardar(path, lead)
        else:
            if lead is not None:
                lead["telegram_notificado"] = False
                lead["caducidad_veces"] = veces + 1
                _guardar(path, lead)
        data["abiertas"].pop(token, None)
        cambio = True
    if cambio:
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
    ahora = ahora or _ahora()
    data = _load()
    data["abiertas"].pop(token, None)
    if espera_seg is None:
        espera_seg = random.randint(3, 8)
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
    data["proxima_en"] = (ahora + timedelta(seconds=random.randint(3, 8))).isoformat(timespec="seconds")
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
    from b2b.envio_correo import outbox_dir

    faltan = len(_candidatos(inbox))
    abiertas = len(abiertas_ahora())
    en_correo = len(list(outbox_dir().glob("*.json")))
    return f"📋 Por revisar: {faltan}. Abiertas: {abiertas}. En cola de correo: {en_correo}."


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
        fila = _candidatos(inbox)
        if not fila:
            break
        path, lead = fila[0]
        if int(data.get("forzar") or 0):
            data["forzar"] = 0
            _save(data)
        _numerar(lead, inbox)
        pais = (lead.get("pais") or "").strip()
        try:
            ok = bool(enviar(lead, pais, str(path)))
        except Exception as exc:
            registrar_evento({"evento": "despacho_fallo", "error": str(exc)[:400]})
            ok = False
        if not ok:
            break
        lead["telegram_notificado"] = True
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
        final = [n for n in data.get("al_final") or [] if n != path.name]
        data["al_final"] = final
        _save(data)
        enviados += 1
    return enviados


def resumen_si_toca(cola_dir: Path) -> str:
    return _resumen_pendiente(cola_dir / "inbox")


def sellar_tanda(inbox: Path, objetivo: int | None = None) -> int:
    if objetivo is None:
        try:
            objetivo = max(1, int(os.getenv("B2B_LEADS_POR_TANDA", "15") or "15"))
        except ValueError:
            objetivo = 15
    from b2b.zonas import tz

    ahora = datetime.now(tz("America/Santo_Domingo"))
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
