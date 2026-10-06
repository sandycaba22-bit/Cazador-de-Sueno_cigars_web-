from __future__ import annotations

import re
from dataclasses import dataclass, field

from b2b.buscar_filtros import dominio_web
from b2b.web_check import chequear_web
from b2b.website import web_confiable_para_idioma

SENAL_FUERTE_RE = re.compile(
    r"cigar|cigarro|cigare|sigaar|tabac|humidor|tabaco|tobacco|tabak|charuto|puro",
    re.I,
)
CIGAR_LOUNGE_RE = re.compile(r"cigar\s+lounge|lounge\s+cigar|humidor", re.I)

BLACKLIST_TIPO_RE = re.compile(
    r"\b(burger|hamburg|restaurant|pizza|grill|barbecue|bbq|"
    r"vape|vaping|gas\s*station|supermarket|supermercado|pharmacy|farmacia|"
    r"salon|church|iglesia|school|escuela|hostel|hotel\s*hostel)\b",
    re.I,
)
BLACKLIST_DOMINIO_RE = re.compile(
    r"(burger|hamburg|pizza|grill|vape|gasstation|pharmacy|salon|hostel|"
    r"restaurant|sushi|kebab|wings)",
    re.I,
)


@dataclass
class StatsCalidad:
    aceptados: int = 0
    dudosos: int = 0
    web_caida: int = 0
    descartados_web: int = 0
    descartados_tipo: int = 0


@dataclass
class ResultadoCalidad:
    bucket: str
    motivo: str = ""
    descarte: dict = field(default_factory=dict)


def _texto_lead(lead: dict) -> str:
    partes = [
        lead.get("nombre") or "",
        lead.get("web") or "",
        lead.get("direccion") or "",
    ]
    tags = lead.get("_osm_tags") or {}
    for val in tags.values():
        partes.append(str(val))
    return " ".join(partes)


def osm_shop_tabaco(lead: dict) -> bool:
    tags = lead.get("_osm_tags") or {}
    shop = (tags.get("shop") or "").lower()
    return shop in ("tobacco", "cigar") or bool(lead.get("osm_shop_tobacco"))


def tiene_senal_fuerte(lead: dict) -> bool:
    if osm_shop_tabaco(lead):
        return True
    return bool(SENAL_FUERTE_RE.search(_texto_lead(lead)))


def _bar_restaurant_permitido(lead: dict) -> bool:
    tags = lead.get("_osm_tags") or {}
    amenity = (tags.get("amenity") or "").lower()
    if amenity not in ("bar", "pub", "restaurant", "cafe"):
        return True
    texto = _texto_lead(lead).lower()
    if tags.get("cigar") == "yes":
        return True
    if CIGAR_LOUNGE_RE.search(texto):
        return True
    if "humidor" in texto:
        return True
    return False


def motivo_descarte_tipo(lead: dict) -> str | None:
    nombre = lead.get("nombre") or ""
    dom = dominio_web(lead.get("web") or "")
    blob = f"{nombre} {dom}"
    if BLACKLIST_DOMINIO_RE.search(dom):
        return "tipo/dominio no cigarro (lista negra)"
    if BLACKLIST_TIPO_RE.search(blob) and not tiene_senal_fuerte(lead):
        return "tipo/dominio no cigarro (lista negra)"
    if not _bar_restaurant_permitido(lead):
        return "bar/restaurant sin humidor ni cigar lounge"
    return None


def evaluar_senal_cigarro(lead: dict) -> ResultadoCalidad:
    motivo_tipo = motivo_descarte_tipo(lead)
    if motivo_tipo:
        return ResultadoCalidad(
            bucket="descartado",
            motivo=motivo_tipo,
            descarte={"nombre": lead.get("nombre") or "—", "motivo": motivo_tipo, "etapa": "calidad_tipo"},
        )
    if not tiene_senal_fuerte(lead):
        return ResultadoCalidad(
            bucket="dudoso",
            motivo="sin señal fuerte tabaco/cigarro",
            descarte={"nombre": lead.get("nombre") or "—", "motivo": "dudoso: sin señal fuerte", "etapa": "calidad"},
        )
    return ResultadoCalidad(bucket="aceptado")


def aplicar_reglas_web(lead: dict, web_info: dict, *, simulado: bool = False) -> ResultadoCalidad:
    lead["web_estado"] = web_info.get("web_estado") or "omitido"
    if web_info.get("web_http") is not None:
        lead["web_http"] = web_info["web_http"]
    lead["fecha_chequeo"] = web_info.get("fecha_chequeo") or ""

    clase = web_info.get("web_clase") or "OMITIDO"
    if simulado or clase in ("OMITIDO", "ROBOTS"):
        return ResultadoCalidad(bucket="aceptado")

    if clase == "OK":
        return ResultadoCalidad(bucket="aceptado")

    if clase == "ERROR_TEMPORAL" or web_info.get("web_estado") == "web_no_verificada":
        lead["calidad_nota"] = "web_no_verificada"
        return ResultadoCalidad(bucket="aceptado")

    if clase == "MUERTA":
        if osm_shop_tabaco(lead):
            lead["calidad_nota"] = "web_caida"
            lead["web_estado"] = "web_caida"
            return ResultadoCalidad(bucket="aceptado", motivo="web_caida")

        telefono = (lead.get("telefono") or "").strip()
        correo = (lead.get("correo") or "").strip()
        if telefono:
            return ResultadoCalidad(
                bucket="solo_telefono",
                motivo="web muerta, solo teléfono",
            )
        if not telefono and not correo:
            return ResultadoCalidad(
                bucket="descartado",
                motivo="web muerta y sin otro contacto",
                descarte={
                    "nombre": lead.get("nombre") or "—",
                    "motivo": "web muerta y sin otro contacto",
                    "etapa": "calidad_web",
                },
            )
        return ResultadoCalidad(bucket="aceptado", motivo="web muerta pero hay correo")

    return ResultadoCalidad(bucket="aceptado")


def evaluar_lead_completo(lead: dict, *, simulado: bool = False) -> ResultadoCalidad:
    base = evaluar_senal_cigarro(lead)
    if base.bucket in ("descartado", "dudoso"):
        return base

    web = (lead.get("web") or "").strip()
    if web.startswith(("http://", "https://")) and web_confiable_para_idioma(web):
        info = chequear_web(web, simulado=simulado)
        web_res = aplicar_reglas_web(lead, info, simulado=simulado)
        if web_res.bucket == "descartado":
            return web_res
        if web_res.bucket == "solo_telefono":
            return web_res
        if lead.get("calidad_nota") == "web_caida":
            web_res.bucket = "aceptado"
            web_res.motivo = "web_caida"
        if base.bucket == "aceptado" and web_res.bucket == "aceptado":
            return web_res if web_res.motivo else base
        return web_res

    return base


def clasificar_lote(
    leads: list[dict], *, simulado: bool = False
) -> tuple[list[dict], list[dict], list[dict], list[dict], StatsCalidad]:
    """Devuelve aceptados, dudosos, solo_telefono, descartes de calidad, stats."""
    aceptados: list[dict] = []
    dudosos: list[dict] = []
    solo_telefono: list[dict] = []
    descartes: list[dict] = []
    stats = StatsCalidad()

    for raw in leads:
        lead = dict(raw)
        res = evaluar_lead_completo(lead, simulado=simulado)
        if res.descarte:
            descartes.append(res.descarte)
        if res.bucket == "descartado":
            if "web muerta" in (res.motivo or ""):
                stats.descartados_web += 1
            else:
                stats.descartados_tipo += 1
            continue
        if res.bucket == "dudoso":
            lead["calidad_bucket"] = "dudoso"
            lead["calidad_motivo"] = res.motivo
            dudosos.append(lead)
            stats.dudosos += 1
            descartes.append(
                {"nombre": lead.get("nombre") or "—", "motivo": res.motivo, "etapa": "calidad"}
            )
            continue
        if res.bucket == "solo_telefono":
            lead["calidad_bucket"] = "solo_telefono"
            lead["calidad_motivo"] = res.motivo
            solo_telefono.append(lead)
            continue
        if lead.get("calidad_nota") == "web_caida":
            stats.web_caida += 1
        lead["calidad_bucket"] = "aceptado"
        aceptados.append(lead)
        stats.aceptados += 1

    return aceptados, dudosos, solo_telefono, descartes, stats
