from __future__ import annotations

from dataclasses import dataclass, field

from b2b.nombres_busqueda import clasificar_aceptacion
from b2b.web_check import chequear_web
from b2b.website import web_confiable_para_idioma


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


def osm_shop_tabaco(lead: dict) -> bool:
    tags = lead.get("_osm_tags") or {}
    shop = (tags.get("shop") or "").lower()
    return shop in ("tobacco", "cigar") or bool(lead.get("osm_shop_tobacco"))


def evaluar_senal_cigarro(lead: dict) -> ResultadoCalidad:
    bucket, motivo = clasificar_aceptacion(lead)
    if bucket == "excluido":
        return ResultadoCalidad(
            bucket="descartado",
            motivo=motivo,
            descarte={
                "nombre": lead.get("nombre") or "—",
                "motivo": motivo,
                "etapa": "calidad_nombre",
            },
        )
    if bucket == "dudoso":
        return ResultadoCalidad(
            bucket="dudoso",
            motivo=motivo,
            descarte={
                "nombre": lead.get("nombre") or "—",
                "motivo": motivo,
                "etapa": "calidad_nombre",
            },
        )
    return ResultadoCalidad(bucket="aceptado", motivo=motivo)


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


def confirmar_cigarros_google(lead: dict, base: ResultadoCalidad, *, simulado: bool = False) -> ResultadoCalidad:
    """Google: la web propia decide si un nombre ambiguo vende cigarros."""
    if simulado or "google" not in (lead.get("fuente") or "").lower() or base.bucket == "descartado":
        return base
    from b2b.contacto_web import vende_cigarros

    confirma = vende_cigarros((lead.get("web") or "").strip())
    if confirma is None:
        return base
    lead["vende_cigarros"] = confirma
    if confirma:
        return ResultadoCalidad(bucket="aceptado", motivo="web confirma cigarros")
    if base.bucket == "dudoso":
        motivo = "sin señal de cigarros en el nombre ni en la web"
        return ResultadoCalidad(
            bucket="dudoso",
            motivo=motivo,
            descarte={"nombre": lead.get("nombre") or "—", "motivo": motivo, "etapa": "calidad_web"},
        )
    return base


def evaluar_lead_completo(lead: dict, *, simulado: bool = False) -> ResultadoCalidad:
    base = confirmar_cigarros_google(lead, evaluar_senal_cigarro(lead), simulado=simulado)
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
        if res.bucket == "descartado":
            descartes.append(
                res.descarte
                or {"nombre": lead.get("nombre") or "—", "motivo": res.motivo or "calidad", "etapa": "calidad"}
            )
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
