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
from b2b.country_rules import buscar_pais, cargar_reglas, paises_ordenados_por_dificultad, paises_prioridad_inicial
from b2b.idioma import idioma_para_lead
from b2b.lead_score import califica_lead, puntuar_lead
from b2b.leads_store import en_lista_no_contactar, marcar_visto, ya_visto
from b2b.logging_ops import registrar_busqueda, registrar_presupuesto_agotado
from b2b.places import PresupuestoPlacesAgotado, buscar_en_pais
from b2b.website import analizar_sitio_prospecto

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


def encolar(leads: list[dict], inbox: Path, reglas: dict) -> list[Path]:
    inbox.mkdir(parents=True, exist_ok=True)
    escritos: list[Path] = []
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
        time.sleep(0.05)
    return escritos


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
) -> dict:
    pais = reglas["pais"]
    tipos = _tipos_busqueda()
    try:
        leads, llamadas = buscar_en_pais(
            pais, tipos, max_leads, simulado=simulado, tipo_filtro=tipo_filtro
        )
    except PresupuestoPlacesAgotado:
        registrar_presupuesto_agotado()
        return {
            "pais": pais,
            "encolados": 0,
            "leads": 0,
            "llamadas": 0,
            "presupuesto_agotado": True,
        }
    if solo_listar:
        for lead in leads:
            print(json.dumps(enriquecer_lead(dict(lead), reglas), ensure_ascii=False))
        registrar_busqueda(pais, llamadas, len(leads), simulado)
        return {"pais": pais, "encolados": 0, "leads": len(leads), "llamadas": llamadas}

    paths = encolar(leads, inbox, reglas)
    registrar_busqueda(pais, llamadas, len(paths), simulado)
    return {"pais": pais, "encolados": len(paths), "leads": len(leads), "llamadas": llamadas}


def prospectar(
    pais_cli: str | None,
    max_leads: int,
    inbox: Path,
    simulado: bool = False,
    solo_listar: bool = False,
    tipo_filtro: str = "",
) -> dict:
    if pais_cli and pais_cli.strip():
        reglas = resolver_pais_objetivo(pais_cli)
        return prospectar_un_pais(
            reglas, max_leads, inbox, simulado, solo_listar, tipo_filtro
        )
    return prospectar_prioridad_inicial(
        max_leads, inbox, simulado, solo_listar, tipo_filtro
    )


def prospectar_prioridad_inicial(
    max_leads: int,
    inbox: Path,
    simulado: bool = False,
    solo_listar: bool = False,
    tipo_filtro: str = "",
) -> dict:
    paises = paises_prioridad_inicial()
    if not paises:
        raise ValueError("prioridad_inicial vacía en country_rules.json")
    total_encolados = 0
    total_leads = 0
    total_llamadas = 0
    presupuesto_agotado = False
    for reglas in paises:
        if not simulado and not puede_llamar():
            registrar_presupuesto_agotado()
            presupuesto_agotado = True
            break
        stats = prospectar_un_pais(
            reglas, max_leads, inbox, simulado, solo_listar, tipo_filtro
        )
        total_encolados += int(stats.get("encolados", 0))
        total_leads += int(stats.get("leads", 0))
        total_llamadas += int(stats.get("llamadas", 0))
        if stats.get("presupuesto_agotado"):
            presupuesto_agotado = True
            break
    return {
        "pais": "prioridad_inicial",
        "encolados": total_encolados,
        "leads": total_leads,
        "llamadas": total_llamadas,
        "presupuesto_agotado": presupuesto_agotado,
        "paises_recorridos": len(paises),
    }
