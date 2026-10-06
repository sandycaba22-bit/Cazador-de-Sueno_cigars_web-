# Prospector B2B — Google Places + enriquecimiento web → inbox/
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from b2b.budget import puede_llamar
from b2b.country_rules import (
    buscar_pais,
    cargar_reglas,
    paises_ordenados_por_dificultad,
    paises_prioridad_busqueda,
    paises_prioridad_inicial,
)
from b2b.idioma import idioma_para_lead
from b2b.lead_score import califica_lead, puntuar_lead
from b2b.leads_store import en_lista_no_contactar, marcar_visto, ya_visto
from b2b.logging_ops import registrar_busqueda, registrar_presupuesto_agotado
from b2b.fuente_leads import resolver_fuente_leads
from b2b.places import PresupuestoPlacesAgotado, buscar_en_pais
from b2b.telegram_buscar import avisar_isla_encontradas, avisar_isla_fallida, avisar_resumen_barrido
from b2b.website import analizar_sitio_prospecto, web_confiable_para_idioma

SLUG_RE = __import__("re").compile(r"[^a-z0-9]+")


def _slug(texto: str) -> str:
    return SLUG_RE.sub("-", texto.lower()).strip("-")


def resolver_pais_objetivo(pais_cli: str | None) -> dict:
    if pais_cli and pais_cli.strip():
        entry = buscar_pais(pais_cli)
        if entry is None:
            raise ValueError(f"País no configurado en country_rules.json: {pais_cli}")
        return entry
    lista = paises_prioridad_inicial()
    if lista:
        return lista[0]
    return paises_ordenados_por_dificultad()[0]


def enriquecer_lead(lead: dict, reglas: dict) -> dict:
    web = lead.get("web") or ""
    correo = (lead.get("correo") or "").strip()
    fuente_correo = lead.get("fuente_correo") or ""
    idioma_web = (lead.get("idioma_web") or "").strip()
    idioma_fuente = (lead.get("idioma_fuente") or "").strip()
    if web.startswith(("http://", "https://")):
        info = analizar_sitio_prospecto(web)
        if not correo:
            correo = info["correo"]
            fuente_correo = info["fuente_correo"]
        if not idioma_web:
            idioma_web = info["idioma_web"]
            idioma_fuente = info["idioma_fuente"]
    if web and not web_confiable_para_idioma(web):
        idioma_web = ""
        idioma_fuente = ""
    lead["correo"] = correo
    lead["fuente_correo"] = fuente_correo
    lead["idioma_web"] = idioma_web
    lead["idioma_fuente"] = idioma_fuente
    if not correo:
        lead["sin_correo_publico"] = True
    lead["idioma"] = idioma_para_lead(
        reglas["pais"],
        idioma_web=idioma_web,
        preferido=(lead.get("idioma") or "").strip(),
        web=web,
    )
    lead["dificultad_aduana"] = reglas.get("dificultad")
    lead["estado_reglas"] = reglas.get("estado")
    lead["tipo"] = lead.get("tipo_negocio") or lead.get("tipo") or "tienda"
    score, detalle = puntuar_lead(lead)
    lead["puntaje"] = score
    lead["puntaje_detalle"] = detalle
    return lead


def lead_a_inbox(lead: dict) -> dict:
    return {
        "nombre": lead["nombre"],
        "pais": lead["pais"],
        "web": lead.get("web") or "—",
        "correo": lead.get("correo") or "",
        "tipo": lead.get("tipo") or "tienda",
        "telefono": lead.get("telefono") or "",
        "direccion": lead.get("direccion") or "",
        "idioma": lead.get("idioma") or "en",
        "idioma_web": lead.get("idioma_web") or "",
        "idioma_fuente": lead.get("idioma_fuente") or "",
        "dificultad_aduana": lead.get("dificultad_aduana"),
        "estado_reglas": lead.get("estado_reglas"),
        "fuente_correo": lead.get("fuente_correo") or "",
        "place_id": lead.get("place_id") or "",
        "sin_correo_publico": bool(lead.get("sin_correo_publico")),
        "tipo_negocio": lead.get("tipo") or "tienda",
        "puntaje": lead.get("puntaje"),
        "puntaje_detalle": lead.get("puntaje_detalle"),
        "rating": lead.get("rating"),
        "user_rating_count": lead.get("user_rating_count"),
    }


def _payload_tiene_contacto(payload: dict) -> bool:
    return bool((payload.get("telefono") or "").strip() or (payload.get("correo") or "").strip())


def encolar(leads: list[dict], inbox: Path, reglas: dict) -> tuple[list[Path], int]:
    inbox.mkdir(parents=True, exist_ok=True)
    escritos: list[Path] = []
    con_contacto = 0
    for lead in leads:
        if en_lista_no_contactar(lead.get("nombre", ""), lead.get("web", "")):
            continue
        if ya_visto(lead.get("place_id", ""), lead.get("web", "")):
            continue
        enriquecido = enriquecer_lead(dict(lead), reglas)
        if not califica_lead(enriquecido):
            continue
        payload = lead_a_inbox(enriquecido)
        path = inbox / f"{int(time.time())}-{_slug(payload['nombre'])[:40]}.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        marcar_visto(payload.get("place_id", ""), payload.get("web", ""))
        escritos.append(path)
        if _payload_tiene_contacto(payload):
            con_contacto += 1
        time.sleep(0.05)
    return escritos, con_contacto


def _tipos_busqueda() -> list[str]:
    return cargar_reglas().get("orden_tipos_negocio") or [
        "distribuidor",
        "tienda",
        "lounge",
        "hotel",
        "casino",
        "duty_free",
    ]


def prospectar_un_pais(
    reglas: dict,
    max_leads: int,
    inbox: Path,
    simulado: bool = False,
    solo_listar: bool = False,
    tipo_filtro: str = "",
    fuente: str = "",
) -> dict:
    pais = reglas["pais"]
    tipos = _tipos_busqueda()
    if not fuente:
        fuente = "simulado" if simulado else resolver_fuente_leads()
    try:
        leads, llamadas = buscar_en_pais(
            pais,
            tipos,
            max_leads,
            simulado=simulado,
            tipo_filtro=tipo_filtro,
            fuente=fuente,
        )
    except PresupuestoPlacesAgotado:
        registrar_presupuesto_agotado()
        return {
            "pais": pais,
            "encolados": 0,
            "leads": 0,
            "llamadas": 0,
            "presupuesto_agotado": True,
            "fuente": fuente,
        }
    except ValueError as error:
        from b2b.logging_ops import registrar_osm_fallo

        if fuente == "osm":
            registrar_osm_fallo(pais, str(error))
        return {
            "pais": pais,
            "encolados": 0,
            "leads": 0,
            "llamadas": 0,
            "fuente": fuente,
            "error": str(error)[:200],
        }
    except RuntimeError as error:
        from b2b.logging_ops import registrar_osm_fallo
        from b2b.osm_places import OsmIslaFallida

        if isinstance(error, OsmIslaFallida) or fuente == "osm":
            registrar_osm_fallo(pais, str(error))
        isla_fallida = isinstance(error, OsmIslaFallida)
        return {
            "pais": pais,
            "encolados": 0,
            "leads": 0,
            "llamadas": 0,
            "fuente": fuente,
            "error": str(error)[:200],
            "isla_fallida": isla_fallida,
        }
    if solo_listar:
        for lead in leads:
            print(json.dumps(enriquecer_lead(dict(lead), reglas), ensure_ascii=False))
        registrar_busqueda(pais, llamadas, len(leads), simulado, fuente=fuente)
        return {
            "pais": pais,
            "encolados": 0,
            "leads": len(leads),
            "llamadas": llamadas,
            "fuente": fuente,
        }

    paths, con_contacto = encolar(leads, inbox, reglas)
    registrar_busqueda(pais, llamadas, len(paths), simulado, fuente=fuente)
    return {
        "pais": pais,
        "encolados": len(paths),
        "con_contacto": con_contacto,
        "leads": len(leads),
        "llamadas": llamadas,
        "fuente": fuente,
    }


def _telegram_tras_isla(stats: dict, simulado: bool, solo_listar: bool) -> None:
    if solo_listar:
        return
    pais = str(stats.get("pais", ""))
    if stats.get("isla_fallida"):
        avisar_isla_fallida(pais, simulado=simulado)
        return
    encolados = int(stats.get("encolados", 0))
    avisar_isla_encontradas(
        pais,
        encolados,
        int(stats.get("con_contacto", 0)),
        simulado=simulado,
    )


def prospectar(
    pais_cli: str | None,
    max_leads: int,
    inbox: Path,
    simulado: bool = False,
    solo_listar: bool = False,
    tipo_filtro: str = "",
) -> dict:
    fuente = "simulado" if simulado else resolver_fuente_leads()
    import os

    zona = os.getenv("B2B_ZONA_BUSQUEDA", "caribe")
    if pais_cli and pais_cli.strip():
        reglas = resolver_pais_objetivo(pais_cli)
        out = prospectar_un_pais(
            reglas, max_leads, inbox, simulado, solo_listar, tipo_filtro, fuente=fuente
        )
        if "fuente" not in out:
            out["fuente"] = fuente
        _telegram_tras_isla(out, simulado, solo_listar)
        if not solo_listar:
            enc = int(out.get("encolados", 0))
            avisar_resumen_barrido(
                enc,
                {out["pais"]: enc} if enc else {},
                {out["pais"]: int(out.get("con_contacto", 0))} if enc else {},
                [out["pais"]] if out.get("isla_fallida") else [],
                out["pais"],
                simulado=simulado,
            )
        return out
    return prospectar_prioridad_inicial(
        max_leads, inbox, simulado, solo_listar, tipo_filtro, fuente=fuente, zona=zona
    )


def _max_paises_por_pasada() -> int:
    import os

    try:
        return max(1, int(os.getenv("B2B_MAX_PAISES_POR_BUSCAR", "18") or "18"))
    except ValueError:
        return 18


def prospectar_prioridad_inicial(
    max_leads: int,
    inbox: Path,
    simulado: bool = False,
    solo_listar: bool = False,
    tipo_filtro: str = "",
    fuente: str = "",
    zona: str | None = None,
) -> dict:
    paises = paises_prioridad_busqueda(zona)
    if not paises:
        raise ValueError("Lista de países vacía para la zona de búsqueda (country_rules.json)")
    max_paises = _max_paises_por_pasada()
    if not fuente:
        fuente = "simulado" if simulado else resolver_fuente_leads()
    total_encolados = 0
    total_leads = 0
    total_llamadas = 0
    presupuesto_agotado = False
    paises_usados = 0
    islas_fallidas: list[str] = []
    encolados_por_isla: dict[str, int] = {}
    contacto_por_isla: dict[str, int] = {}
    for reglas in paises:
        if paises_usados >= max_paises:
            break
        if solo_listar:
            restante = max_leads
        else:
            restante = max(0, max_leads - total_encolados)
            if restante <= 0:
                break
        print(f"Buscando en: {reglas['pais']}…", file=sys.stderr)
        if fuente == "google" and not simulado and not puede_llamar():
            registrar_presupuesto_agotado()
            presupuesto_agotado = True
            break
        stats = prospectar_un_pais(
            reglas,
            restante,
            inbox,
            simulado,
            solo_listar,
            tipo_filtro,
            fuente=fuente,
        )
        paises_usados += 1
        enc = int(stats.get("encolados", 0))
        total_encolados += enc
        total_leads += int(stats.get("leads", 0))
        total_llamadas += int(stats.get("llamadas", 0))
        nombre_isla = str(stats.get("pais", reglas["pais"]))
        if enc > 0:
            encolados_por_isla[nombre_isla] = enc
            contacto_por_isla[nombre_isla] = int(stats.get("con_contacto", 0))
        _telegram_tras_isla(stats, simulado, solo_listar)
        if stats.get("isla_fallida"):
            islas_fallidas.append(nombre_isla)
        if stats.get("presupuesto_agotado"):
            presupuesto_agotado = True
            break
        if fuente == "osm" and not simulado:
            restantes = max_paises - paises_usados
            if restantes > 0 and total_encolados < max_leads:
                time.sleep(4)
    import os

    if islas_fallidas:
        print(
            "Islas sin respuesta Overpass (reintentar): " + ", ".join(islas_fallidas),
            file=sys.stderr,
        )
    zona_label = (zona or os.getenv("B2B_ZONA_BUSQUEDA", "caribe") or "caribe").strip()
    if not solo_listar:
        avisar_resumen_barrido(
            total_encolados,
            encolados_por_isla,
            contacto_por_isla,
            islas_fallidas,
            zona_label,
            simulado=simulado,
        )
    return {
        "pais": f"zona:{zona_label}",
        "encolados": total_encolados,
        "leads": total_leads,
        "llamadas": total_llamadas,
        "presupuesto_agotado": presupuesto_agotado,
        "paises_recorridos": paises_usados,
        "fuente": fuente,
        "zona": zona_label,
        "islas_fallidas": islas_fallidas,
    }
