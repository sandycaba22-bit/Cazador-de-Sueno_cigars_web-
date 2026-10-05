# Prospector B2B — Google Places + enriquecimiento web → inbox/
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from b2b.country_rules import buscar_pais, cargar_reglas, paises_ordenados_por_dificultad
from b2b.idioma import idioma_para_pais
from b2b.leads_store import en_lista_no_contactar, marcar_visto, ya_visto
from b2b.logging_ops import registrar_busqueda
from b2b.places import buscar_en_pais
from b2b.website import extraer_correo_publico

SLUG_RE = __import__("re").compile(r"[^a-z0-9]+")


def _slug(texto: str) -> str:
    return SLUG_RE.sub("-", texto.lower()).strip("-")


def resolver_pais_objetivo(pais_cli: str | None) -> dict:
    if pais_cli and pais_cli.strip():
        entry = buscar_pais(pais_cli)
        if entry is None:
            raise ValueError(f"País no configurado en country_rules.json: {pais_cli}")
        return entry
    data = cargar_reglas()
    for nombre in data.get("prioridad_inicial", []):
        entry = buscar_pais(nombre)
        if entry:
            return entry
    return paises_ordenados_por_dificultad()[0]


def enriquecer_lead(lead: dict, reglas: dict) -> dict:
    web = lead.get("web") or ""
    correo = (lead.get("correo") or "").strip()
    fuente_correo = lead.get("fuente_correo") or ""
    if web.startswith(("http://", "https://")) and not correo:
        correo, fuente_correo = extraer_correo_publico(web)
    lead["correo"] = correo
    lead["fuente_correo"] = fuente_correo
    if not correo:
        lead["sin_correo_publico"] = True
    lead["idioma"] = idioma_para_pais(reglas["pais"])
    lead["dificultad_aduana"] = reglas.get("dificultad")
    lead["estado_reglas"] = reglas.get("estado")
    lead["tipo"] = lead.get("tipo_negocio") or lead.get("tipo") or "tienda"
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
        "dificultad_aduana": lead.get("dificultad_aduana"),
        "estado_reglas": lead.get("estado_reglas"),
        "fuente_correo": lead.get("fuente_correo") or "",
        "place_id": lead.get("place_id") or "",
        "sin_correo_publico": bool(lead.get("sin_correo_publico")),
        "tipo_negocio": lead.get("tipo") or "tienda",
    }


def encolar(leads: list[dict], inbox: Path, reglas: dict) -> list[Path]:
    inbox.mkdir(parents=True, exist_ok=True)
    escritos: list[Path] = []
    for lead in leads:
        if en_lista_no_contactar(lead.get("nombre", ""), lead.get("web", "")):
            continue
        if ya_visto(lead.get("place_id", ""), lead.get("web", "")):
            continue
        payload = lead_a_inbox(enriquecer_lead(lead, reglas))
        path = inbox / f"{int(time.time())}-{_slug(payload['nombre'])[:40]}.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        marcar_visto(payload.get("place_id", ""), payload.get("web", ""))
        escritos.append(path)
        time.sleep(0.05)
    return escritos


def prospectar(
    pais_cli: str | None,
    max_leads: int,
    inbox: Path,
    simulado: bool = False,
    solo_listar: bool = False,
    tipo_filtro: str = "",
) -> dict:
    reglas = resolver_pais_objetivo(pais_cli)
    pais = reglas["pais"]
    tipos = cargar_reglas().get("orden_tipos_negocio") or [
        "distribuidor",
        "tienda",
        "lounge",
        "hotel",
        "duty_free",
    ]
    leads, llamadas = buscar_en_pais(
        pais, tipos, max_leads, simulado=simulado, tipo_filtro=tipo_filtro
    )
    if solo_listar:
        for lead in leads:
            print(json.dumps(enriquecer_lead(dict(lead), reglas), ensure_ascii=False))
        registrar_busqueda(pais, llamadas, len(leads), simulado)
        return {"pais": pais, "encolados": 0, "leads": len(leads), "llamadas": llamadas}

    paths = encolar(leads, inbox, reglas)
    registrar_busqueda(pais, llamadas, len(paths), simulado)
    return {"pais": pais, "encolados": len(paths), "leads": len(leads), "llamadas": llamadas}
