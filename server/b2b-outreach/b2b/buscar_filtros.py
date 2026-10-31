from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
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
    """Dominio de la web propia; '' para links de mapa (OSM, Google Maps)."""
    from b2b.website import dominio_negocio

    return dominio_negocio(web or "")


def clave_dedupe(lead: dict) -> str:
    """Orden: dominio propio, place_id (osm:node/…), teléfono, nombre+país."""
    dom = dominio_web(lead.get("web") or "")
    if dom:
        return f"dom:{dom}"
    pid = (lead.get("place_id") or "").strip()
    if pid:
        return f"id:{pid}"
    tel = re.sub(r"\D", "", lead.get("telefono") or "")[-10:]
    nom = normalizar_nombre(lead.get("nombre") or "")
    if tel:
        return f"tel:{tel}|{nom[:30]}"
    return f"nom:{nom}|{lead.get('pais','')}"


def motivo_descarte_osm(nombre: str, tags: dict) -> str | None:
    """Etiqueta de motivo si descartar_lead_osm descartaría; None si pasa."""
    if not descartar_lead_osm(nombre, tags):
        return None
    shop = (tags.get("shop") or "").lower()
    if shop == "e-cigarette":
        return "vape/smoke shop"
    if tags.get("amenity") == "fuel":
        return "gasolinera"
    joined = f"{nombre} {' '.join(tags.values())}".lower()
    if VAPE_DESCARTAR_RE.search(joined) and not NAME_BUSCAR_RE.search(nombre):
        return "vape/smoke shop"
    if GASOLINERA_RE.search(joined) and shop not in ("tobacco", "cigar"):
        return "gasolinera"
    if shop == "convenience" and not NAME_BUSCAR_RE.search(nombre):
        return "colmado/convenience sin nombre cigarro"
    amenity = (tags.get("amenity") or "").lower()
    if amenity in ("cafe", "bar", "pub", "restaurant"):
        return "bar/café sin humidor"
    return "filtro OSM"


def motivo_rechazo_generico(lead: dict) -> str | None:
    """Motivo si no pasa reglas de nombre (JSON) ni filtros OSM legacy."""
    from b2b.nombres_busqueda import clasificar_aceptacion

    nombre = lead.get("nombre") or ""
    fuente = (lead.get("fuente") or "").lower()
    if (fuente.startswith("dealer:") or fuente == "directorio") and not nombre.strip():
        return "sin nombre"
    bucket, motivo = clasificar_aceptacion(lead)
    if bucket == "excluido":
        return motivo
    tags = lead.get("_osm_tags") or {}
    if tags and descartar_lead_osm(nombre, tags):
        return motivo_descarte_osm(nombre, tags) or "filtro OSM"
    if bucket in ("aceptado", "dudoso"):
        return None
    return motivo or "sin señal tabaco/cigarro"


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
    for key in ("web", "telefono", "correo", "direccion", "place_id", "instagram", "facebook", "maps_url"):
        if not (out.get(key) or "").strip() and (otro.get(key) or "").strip():
            out[key] = otro[key]
    fuentes = {out.get("fuente", ""), otro.get("fuente", "")} - {""}
    if len(fuentes) > 1:
        out["fuente"] = "+".join(sorted(fuentes))
    return out


def dedupe_y_fusionar(
    leads: list[dict],
    auditoria: list[dict] | None = None,
    fusionados_log: list[dict] | None = None,
) -> list[dict]:
    por_clave: dict[str, dict] = {}
    orden: list[str] = []
    for lead in leads:
        motivo = motivo_rechazo_generico(lead)
        if motivo:
            if auditoria is not None:
                auditoria.append(
                    {
                        "nombre": lead.get("nombre") or "—",
                        "motivo": motivo,
                        "etapa": "fusion_fuentes",
                        "fuente": lead.get("fuente") or "",
                    }
                )
            continue
        clave = clave_dedupe(lead)
        if clave in por_clave:
            if fusionados_log is not None:
                base = por_clave[clave].get("nombre") or "—"
                nombre = lead.get("nombre") or "—"
                fusionados_log.append(
                    {
                        "nombre": nombre,
                        "motivo": "fusionado_misma_clave",
                        "etapa": "fusion_fuentes",
                        "clave": clave,
                        "fusionado_en": base,
                        "nombres": [base, nombre],
                        "fuente": lead.get("fuente") or "",
                    }
                )
            por_clave[clave] = fusionar_leads(por_clave[clave], lead)
        else:
            por_clave[clave] = lead
            orden.append(clave)
    return [por_clave[k] for k in orden]


def _claves_cruce(lead: dict) -> list[str]:
    claves = []
    dom = dominio_web(lead.get("web") or "")
    if dom:
        claves.append(f"dom:{dom}")
    tel = re.sub(r"\D", "", lead.get("telefono_internacional") or lead.get("telefono") or "")[-10:]
    if len(tel) >= 8:
        claves.append(f"tel:{tel}")
    correo = (lead.get("correo") or "").strip().lower()
    if "@" in correo:
        claves.append(f"mail:{correo}")
    nom = normalizar_nombre(lead.get("nombre") or "")
    if len(nom) >= 4:
        claves.append(f"nom:{nom}")
    return claves


def combinar_fuentes(
    principales: list[dict], respaldo: list[dict], fusiones: list[dict] | None = None
) -> list[dict]:
    """Google (principal) + OSM (respaldo): el mismo negocio en ambas se fusiona y queda registrado."""
    out = [dict(l) for l in principales]
    indice: dict[str, int] = {}
    for i, lead in enumerate(out):
        for clave in _claves_cruce(lead):
            indice.setdefault(clave, i)
    for lead in respaldo:
        hit = next(((c, indice[c]) for c in _claves_cruce(lead) if c in indice), None)
        if hit is None:
            out.append(lead)
            for clave in _claves_cruce(lead):
                indice.setdefault(clave, len(out) - 1)
            continue
        clave, i = hit
        base = out[i].get("nombre") or "—"
        nombre = lead.get("nombre") or "—"
        if fusiones is not None:
            fusiones.append(
                {
                    "nombre": nombre,
                    "motivo": "fusionado_misma_clave",
                    "etapa": "fusion_google_osm",
                    "clave": clave,
                    "fusionado_en": base,
                    "nombres": [base, nombre],
                    "fuente": lead.get("fuente") or "",
                }
            )
        out[i] = fusionar_leads(out[i], lead)
    return out


def indice_cola_por_clave(cola_dir: Path) -> dict[str, tuple[str, Path]]:
    idx: dict[str, tuple[str, Path]] = {}
    for sub in ("inbox", "sent", "failed"):
        carpeta = cola_dir / sub
        if not carpeta.is_dir():
            continue
        for path in carpeta.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            cl = clave_dedupe(data)
            if cl not in idx:
                idx[cl] = (sub, path)
    return idx


def cargar_claves_cola(cola_dir: Path) -> set[str]:
    return set(indice_cola_por_clave(cola_dir).keys())


def archivo_en_cola(cola_dir: Path, sub: str, lead: dict) -> Path | None:
    """JSON de esa carpeta que es el mismo negocio (clave, place_id o dominio)."""
    carpeta = cola_dir / sub
    if not carpeta.is_dir():
        return None
    clave = clave_dedupe(lead)
    pid = (lead.get("place_id") or "").strip()
    dom = dominio_web(lead.get("web") or "")
    for path in carpeta.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if clave_dedupe(data) == clave:
            return path
        if pid and (data.get("place_id") or "").strip() == pid:
            return path
        if dom and dominio_web(data.get("web") or "") == dom:
            return path
        correo = (lead.get("correo") or "").strip().lower()
        if correo and (data.get("correo") or "").strip().lower() == correo:
            return path
        tel = re.sub(r"\D", "", lead.get("telefono_internacional") or lead.get("telefono") or "")[-10:]
        otro = re.sub(r"\D", "", data.get("telefono_internacional") or data.get("telefono") or "")[-10:]
        if len(tel) >= 8 and tel == otro:
            return path
    return None


def solo_reintento_failed(lead: dict, cola_dir: Path | None) -> bool:
    """True si el único rastro en la cola es failed: el envío se puede reintentar."""
    if cola_dir is None or not cola_dir.is_dir():
        return False
    if archivo_en_cola(cola_dir, "inbox", lead) or archivo_en_cola(cola_dir, "sent", lead):
        return False
    return archivo_en_cola(cola_dir, "failed", lead) is not None


def duplicado_contra(lead: dict, cola_dir: Path | None) -> tuple[str, str] | None:
    """Ubicación (inbox/sent/registro_leads) y fecha si ya existe.

    Un archivo en failed no cuenta: el aviso de Telegram falló y se reintenta.
    """
    from b2b.descartes import _iso_desde_mtime
    from b2b.leads_store import contacto_visto, seen_path, ya_visto

    if cola_dir and cola_dir.is_dir():
        clave = clave_dedupe(lead)
        hit = indice_cola_por_clave(cola_dir).get(clave)
        if hit and hit[0] != "failed":
            sub, path = hit
            return sub, _iso_desde_mtime(path)
        for sub in ("inbox", "sent"):
            path = archivo_en_cola(cola_dir, sub, lead)
            if path is not None:
                return sub, _iso_desde_mtime(path)
    if (
        ya_visto(lead.get("place_id", ""), lead.get("web", "")) or contacto_visto(lead)
    ) and not solo_reintento_failed(lead, cola_dir):
        reg = seen_path()
        fecha = _iso_desde_mtime(reg) if reg.is_file() else ""
        return "registro_leads", fecha
    return None


def clasificar_novedad_detalle(
    leads: list[dict], cola_dir: Path | None, vistos_registro: set[str] | None = None
) -> tuple[list[dict], list[dict], list[dict]]:
    vistos = vistos_registro or set()
    nuevos: list[dict] = []
    repetidos: list[dict] = []
    repetidos_detalle: list[dict] = []
    for lead in leads:
        clave = clave_dedupe(lead)
        dup = duplicado_contra(lead, cola_dir)
        if clave in vistos or dup:
            repetidos.append(lead)
            if dup:
                contra, fecha = dup
            else:
                contra, fecha = "registro_leads", ""
            repetidos_detalle.append(
                {
                    "nombre": lead.get("nombre") or "—",
                    "motivo": "repetido",
                    "contra": contra,
                    "fecha": fecha,
                }
            )
        else:
            nuevos.append(lead)
    return nuevos, repetidos, repetidos_detalle


def clasificar_novedad(
    leads: list[dict], cola_dir: Path | None, vistos_registro: set[str] | None = None
) -> tuple[list[dict], list[dict]]:
    """Separa nuevos vs repetidos (cola + registro_leads vía ya_visto)."""
    nuevos, repetidos, _det = clasificar_novedad_detalle(leads, cola_dir, vistos_registro)
    return nuevos, repetidos
