from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

NAME_BUSCAR_RE = re.compile(
    r"cigar|cigarro|tabac|tabak|sigaar|tobacco|humidor|habano|havana|"
    r"smoke|estanco|tabaqueria|tabaquería|charuto|puro",
    re.I,
)

VAPE_DESCARTAR_RE = re.compile(
    r"\b(vape|vaping|e-?\s*cig|disposable|elf\s*bar|geek\s*bar|juul|pod\s*shop)\b",
    re.I,
)
GASOLINERA_RE = re.compile(r"\b(gas\s*station|petrol|shell|esso|bp\s+shop|repsol)\b", re.I)


def normalizar_nombre(nombre: str) -> str:
    texto = unicodedata.normalize("NFKD", (nombre or "").lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


def dominio_web(web: str) -> str:
    try:
        host = urlparse(web).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def clave_dedupe(lead: dict) -> str:
    dom = dominio_web(lead.get("web") or "")
    tel = re.sub(r"\D", "", lead.get("telefono") or "")[-10:]
    nom = normalizar_nombre(lead.get("nombre") or "")
    if dom:
        return f"dom:{dom}"
    if tel:
        return f"tel:{tel}|{nom[:30]}"
    if lead.get("place_id"):
        return f"id:{lead['place_id']}"
    return f"nom:{nom}|{lead.get('pais','')}"


def descartar_lead_osm(nombre: str, tags: dict) -> bool:
    shop = (tags.get("shop") or "").lower()
    if shop == "e-cigarette":
        return True
    if tags.get("amenity") == "fuel":
        return True
    joined = f"{nombre} {' '.join(tags.values())}".lower()
    if VAPE_DESCARTAR_RE.search(joined) and not NAME_BUSCAR_RE.search(nombre):
        return True
    if GASOLINERA_RE.search(joined) and shop not in ("tobacco", "cigar"):
        return True
    if shop == "convenience" and not NAME_BUSCAR_RE.search(nombre):
        return True
    if shop in ("tobacco", "cigar", "duty_free", "alcohol"):
        return False
    if tags.get("cigar") == "yes" or tags.get("smoking") == "yes":
        return False
    if NAME_BUSCAR_RE.search(nombre):
        return False
    if shop == "tobacco":
        return False
    return True


def aceptar_lead_generico(lead: dict) -> bool:
    nombre = lead.get("nombre") or ""
    fuente = (lead.get("fuente") or "").lower()
    if fuente.startswith("dealer:") or fuente == "directorio":
        return bool(nombre.strip())
    tags = lead.get("_osm_tags") or {}
    if tags:
        return not descartar_lead_osm(nombre, tags)
    joined = nombre.lower()
    if VAPE_DESCARTAR_RE.search(joined) and not NAME_BUSCAR_RE.search(joined):
        return False
    return bool(NAME_BUSCAR_RE.search(nombre) or lead.get("osm_shop_tobacco"))


def fusionar_leads(base: dict, otro: dict) -> dict:
    out = dict(base)
    for key in ("web", "telefono", "correo", "direccion", "place_id"):
        if not (out.get(key) or "").strip() and (otro.get(key) or "").strip():
            out[key] = otro[key]
    fuentes = {out.get("fuente", ""), otro.get("fuente", "")} - {""}
    if len(fuentes) > 1:
        out["fuente"] = "+".join(sorted(fuentes))
    return out


def dedupe_y_fusionar(leads: list[dict]) -> list[dict]:
    por_clave: dict[str, dict] = {}
    orden: list[str] = []
    for lead in leads:
        if not aceptar_lead_generico(lead):
            continue
        clave = clave_dedupe(lead)
        if clave in por_clave:
            por_clave[clave] = fusionar_leads(por_clave[clave], lead)
        else:
            por_clave[clave] = lead
            orden.append(clave)
    return [por_clave[k] for k in orden]


def cargar_claves_cola(cola_dir: Path) -> set[str]:
    claves: set[str] = set()
    for sub in ("inbox", "sent", "failed"):
        carpeta = cola_dir / sub
        if not carpeta.is_dir():
            continue
        for path in carpeta.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict):
                claves.add(clave_dedupe(data))
    return claves


def clasificar_novedad(
    leads: list[dict], cola_dir: Path | None, vistos_registro: set[str] | None = None
) -> tuple[list[dict], list[dict]]:
    """Separa nuevos vs repetidos (cola + registro_leads vía ya_visto)."""
    from b2b.leads_store import ya_visto

    en_cola = cargar_claves_cola(cola_dir) if cola_dir else set()
    vistos = vistos_registro or set()
    nuevos: list[dict] = []
    repetidos: list[dict] = []
    for lead in leads:
        clave = clave_dedupe(lead)
        if (
            clave in en_cola
            or clave in vistos
            or ya_visto(lead.get("place_id", ""), lead.get("web", ""))
        ):
            repetidos.append(lead)
        else:
            nuevos.append(lead)
    return nuevos, repetidos
