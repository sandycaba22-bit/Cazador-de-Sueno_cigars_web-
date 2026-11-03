"""Rotación de búsqueda por zona. Si falta el archivo, el buscador sigue como antes."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from b2b.paths import ROOT

TERMINOS_ZONA = ("cigar shop", "cigar lounge", "cigar distributor")


def _int_env(nombre: str, defecto: int) -> int:
    try:
        return int(os.getenv(nombre, "") or defecto)
    except ValueError:
        return defecto


def enfriamiento_dias() -> int:
    """Días sin repetir una zona. Si la variable falta o no es un número, 7."""
    return max(0, _int_env("B2B_ZONA_ENFRIAMIENTO_DIAS", 7))


def negocios_por_zona() -> int:
    """1 o 2 mejores por zona. Si falta, 2. Nunca más de 2."""
    return min(2, max(1, _int_env("B2B_NEGOCIOS_POR_ZONA", 2)))


def tarjetas_por_zona() -> int:
    """Tope de tarjetas de la misma zona en una tanda. Si falta, 2."""
    return max(1, _int_env("B2B_TARJETAS_POR_ZONA", 2))


def _ruta() -> Path:
    explicita = (os.getenv("B2B_ZONAS_BUSQUEDA_PATH", "") or "").strip()
    if explicita:
        return Path(explicita)
    return ROOT / "config" / "zonas_busqueda.json"


def cargar() -> list[dict]:
    path = _ruta()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    zonas = data.get("zonas") if isinstance(data, dict) else None
    if not isinstance(zonas, list):
        return []
    salida = []
    for zona in zonas:
        if not isinstance(zona, dict):
            continue
        ident = str(zona.get("id") or "").strip()
        nombre = str(zona.get("zona") or "").strip()
        if not ident or not nombre:
            continue
        salida.append({
            "id": ident,
            "pais": str(zona.get("pais") or nombre).strip(),
            "zona": nombre,
            "zona_iana": str(zona.get("zona_iana") or "").strip(),
            "activa": bool(zona.get("activa")),
            "peso": max(1, int(zona.get("peso") or 1)),
        })
    return salida


def activas() -> list[dict]:
    return [z for z in cargar() if z["activa"]]


def hay_zonas() -> bool:
    return bool(activas())


def _ahora(momento: datetime | None = None) -> datetime:
    momento = momento or datetime.now(timezone.utc)
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(timezone.utc)


def _parse(valor: str) -> datetime | None:
    if not valor:
        return None
    try:
        momento = datetime.fromisoformat(valor)
    except ValueError:
        return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(timezone.utc)


def _estado() -> dict:
    from b2b.busqueda_cursor import estado_zonas

    return estado_zonas()


def _ultima(zona: dict, estado: dict) -> datetime | None:
    return _parse(str((estado.get(zona["id"]) or {}).get("ultima") or ""))


def _fria(zona: dict, estado: dict, ahora: datetime) -> bool:
    ultima = _ultima(zona, estado)
    if ultima is None:
        return True
    return ahora - ultima >= timedelta(days=enfriamiento_dias())


def elegir_zonas(n: int, ahora: datetime | None = None) -> list[dict]:
    """Las n zonas menos recientes. El peso del país reparte la tanda. No repite en el enfriamiento."""
    ahora = _ahora(ahora)
    zonas = activas()
    if n <= 0 or not zonas:
        return []
    estado = _estado()
    bolsa = [z for z in zonas if _fria(z, estado, ahora)] or list(zonas)
    elegidas: list[dict] = []
    usadas: set[str] = set()
    cuenta: dict[str, int] = {}
    while len(elegidas) < n:
        candidatos = [z for z in bolsa if z["id"] not in usadas]
        if not candidatos:
            break

        def clave(zona: dict) -> tuple:
            peso = zona["peso"]
            ratio = cuenta.get(zona["pais"], 0) / peso
            ultima = _ultima(zona, estado)
            marca = ultima.timestamp() if ultima else 0.0
            return (ratio, -peso, marca, zona["zona"])

        mejor = min(candidatos, key=clave)
        elegidas.append(mejor)
        usadas.add(mejor["id"])
        cuenta[mejor["pais"]] = cuenta.get(mejor["pais"], 0) + 1
    return elegidas


def termino_de(zona: dict, estado: dict | None = None) -> str:
    estado = estado if estado is not None else _estado()
    veces = int((estado.get(zona["id"]) or {}).get("veces") or 0)
    return TERMINOS_ZONA[veces % len(TERMINOS_ZONA)]


def consulta_de(zona: dict, termino: str) -> str:
    return f"{termino} in {zona['zona']}, {zona['pais']}"


def registrar_zonas(zonas: list[dict], ahora: datetime | None = None, *, termino: str = "") -> None:
    """Anota la pasada. El cursor se escribe entero, de una vez."""
    if not zonas:
        return
    from b2b.busqueda_cursor import guardar_zonas

    ahora = _ahora(ahora)
    estado = _estado()
    for zona in zonas:
        previo = dict(estado.get(zona["id"]) or {})
        previo["ultima"] = ahora.isoformat(timespec="seconds")
        previo["veces"] = int(previo.get("veces") or 0) + 1
        previo["termino"] = termino or termino_de(zona, estado)
        previo["zona"] = zona["zona"]
        previo["pais"] = zona["pais"]
        estado[zona["id"]] = previo
    guardar_zonas(estado)


def texto_zonas(ahora: datetime | None = None) -> str:
    ahora = _ahora(ahora)
    estado = _estado()
    lineas = ["Zonas de búsqueda"]
    for zona in cargar():
        if not zona["activa"]:
            continue
        ultima = _ultima(zona, estado)
        if ultima is None:
            cuando = "aún no"
        else:
            cuando = ultima.strftime("%Y-%m-%d %H:%M UTC")
        fria = "libre" if _fria(zona, estado, ahora) else "en enfriamiento"
        lineas.append(f"- {zona['zona']} ({zona['pais']}): {cuando} · {fria}")
    if len(lineas) == 1:
        lineas.append("No hay zonas activas.")
    apagadas = [z["pais"] for z in cargar() if not z["activa"]]
    if apagadas:
        lineas.append("Apagados: " + ", ".join(apagadas))
    return "\n".join(lineas)


def resumen_por_zona(dia: str) -> list[str]:
    """Líneas del día: buscadas, encontradas, tarjetas y enviadas."""
    from b2b.paths import log_dir

    grupos: dict[str, dict] = {}

    def fila(nombre: str) -> dict:
        return grupos.setdefault(nombre, {"buscadas": 0, "encontradas": 0, "tarjetas": 0, "enviadas": 0})

    path = log_dir() / f"busqueda-{dia.replace('-', '')}.jsonl"
    if path.is_file():
        try:
            with path.open(encoding="utf-8") as handle:
                for linea in handle:
                    try:
                        ev = json.loads(linea)
                    except json.JSONDecodeError:
                        continue
                    if ev.get("evento") != "busqueda_zona":
                        continue
                    item = fila(str(ev.get("zona") or ev.get("pais") or "sin zona"))
                    item["buscadas"] += 1
                    item["encontradas"] += int(ev.get("encontradas") or 0)
                    item["tarjetas"] += int(ev.get("tarjetas") or 0)
        except OSError:
            pass
    from b2b.envio_correo import _load

    for envio in _load().get("envios") or []:
        if not envio.get("ok") or str(envio.get("dia") or "") != dia:
            continue
        item = fila(str(envio.get("zona") or "sin zona"))
        item["enviadas"] += 1
    if not grupos:
        return []
    lineas = ["Por zona:"]
    for nombre, item in sorted(grupos.items(), key=lambda par: (-par[1]["buscadas"], par[0])):
        lineas.append(
            f"- {nombre}: buscadas {item['buscadas']}, encontradas {item['encontradas']}, "
            f"tarjetas {item['tarjetas']}, enviadas {item['enviadas']}"
        )
    return lineas
