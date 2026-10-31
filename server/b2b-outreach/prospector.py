# Prospector B2B — Google Places + enriquecimiento web → inbox/
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from b2b.country_rules import (
    buscar_pais,
    cargar_reglas,
    paises_ordenados_por_dificultad,
    paises_prioridad_busqueda,
    paises_prioridad_inicial,
)
from b2b.idioma import idioma_para_lead
from b2b.lead_score import califica_lead, priorizar_leads_contacto, puntaje_minimo, puntuar_lead
from b2b.leads_store import en_lista_no_contactar, marcar_visto, ya_visto
from b2b.logging_ops import registrar_busqueda, registrar_evento, registrar_presupuesto_agotado
from b2b.fuente_leads import resolver_fuente_leads
from b2b.places import PresupuestoPlacesAgotado, buscar_en_pais
from b2b.buscar_filtros import archivo_en_cola, clasificar_novedad_detalle, solo_reintento_failed
from b2b.descartes import (
    append_dudoso_diario,
    append_isla_en_archivo_diario,
    append_sin_contacto_diario,
    entrada_descarte,
    entrada_repetido,
    entrada_sin_contacto,
    registrar_log_descartes_isla,
)
from b2b.telegram_buscar import avisar_isla_fallida
from b2b.calidad_lead import StatsCalidad, clasificar_lote
from b2b.telegram_gestion import puede_avisar_prospecto, tiene_medio_contacto
from b2b.contacto_web import extraer_contactos, normalizar_canales
from b2b.website import dominio_negocio, web_confiable_para_idioma

SLUG_RE = __import__("re").compile(r"[^a-z0-9]+")

CATEGORIAS_ENCOLAR = (
    "encolados",
    "descartados",
    "dudosos",
    "solo_telefono",
    "repetidos",
    "sin_contacto",
    "pendiente_limite",
)

CATEGORIAS_RESUMEN = ("nuevos", "repetidos", "descartados", "dudosos", "sin_contacto", "pendiente_limite")


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


def enriquecer_lead(lead: dict, reglas: dict, simulado: bool = False) -> dict:
    normalizar_canales(lead)
    web = lead.get("web") or ""
    correo = (lead.get("correo") or "").strip()
    fuente_correo = lead.get("fuente_correo") or ""
    idioma_web = (lead.get("idioma_web") or "").strip()
    idioma_fuente = (lead.get("idioma_fuente") or "").strip()
    telefono = (lead.get("telefono") or "").strip()
    web_enriquecido = False
    if dominio_negocio(web) and not simulado and web_confiable_para_idioma(web):
        info = extraer_contactos(web)
        if not correo and info["correo"]:
            correo = info["correo"]
            fuente_correo = info["fuente_correo"]
            web_enriquecido = True
        if not telefono and info["telefono"]:
            telefono = info["telefono"]
            web_enriquecido = True
        for campo in ("instagram", "facebook", "whatsapp", "formulario"):
            if not (lead.get(campo) or "").strip() and info[campo]:
                lead[campo] = info[campo]
                web_enriquecido = True
        if info["vende_cigarros"] is not None:
            lead["vende_cigarros"] = info["vende_cigarros"]
        if not idioma_web:
            idioma_web = info["idioma_web"]
            idioma_fuente = info["idioma_fuente"]
    if web and not web_confiable_para_idioma(web):
        idioma_web = ""
        idioma_fuente = ""
    lead["correo"] = correo
    lead["telefono"] = telefono
    lead["fuente_correo"] = fuente_correo
    if web_enriquecido:
        lead["web_enriquecido"] = True
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
        "web_estado": lead.get("web_estado") or "",
        "web_http": lead.get("web_http"),
        "fecha_chequeo": lead.get("fecha_chequeo") or "",
        "calidad_bucket": lead.get("calidad_bucket") or "aceptado",
        "calidad_motivo": lead.get("calidad_motivo") or "",
        "calidad_nota": lead.get("calidad_nota") or "",
        "lat": lead.get("lat"),
        "lon": lead.get("lon"),
        "whatsapp": lead.get("whatsapp") or "",
        "instagram": lead.get("instagram") or "",
        "facebook": lead.get("facebook") or "",
        "formulario": lead.get("formulario") or "",
        "maps_url": lead.get("maps_url") or "",
        "telefono_internacional": lead.get("telefono_internacional") or "",
        "vende_cigarros": lead.get("vende_cigarros"),
        "business_status": lead.get("business_status") or "",
        "fuente": lead.get("fuente") or "",
        "telegram_notificado": bool(lead.get("telegram_notificado")),
        "resumen_verificacion": lead.get("resumen_verificacion") or "",
        "types": list(lead.get("types") or []),
        "ciudad": lead.get("ciudad") or "",
        "estado": lead.get("pais") or "",
    }


def _payload_tiene_contacto(payload: dict) -> bool:
    return tiene_medio_contacto(payload)


def _escribir_lead_cola(carpeta: Path, payload: dict) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    path = carpeta / f"{int(time.time())}-{_slug(payload['nombre'])[:40]}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def encolar(
    leads: list[dict],
    inbox: Path,
    reglas: dict,
    *,
    cola_dir: Path | None = None,
    simulado: bool = False,
    pais: str = "",
    notificar_telegram_buscar: bool | None = None,
    max_encolar: int = 0,
    resultado: dict | None = None,
) -> tuple[list[Path], int, int, StatsCalidad, list[dict]]:
    """Encola y clasifica cada lead en exactamente una categoría de ``resultado``:
    encolados, descartados, dudosos, solo_telefono, repetidos, sin_contacto, pendiente_limite.
    """
    if notificar_telegram_buscar is None:
        notificar_telegram_buscar = True
    res = resultado if resultado is not None else {}
    for clave in CATEGORIAS_ENCOLAR:
        res.setdefault(clave, [])
    inbox.mkdir(parents=True, exist_ok=True)
    cola = cola_dir or inbox.parent
    dudoso_dir = cola / "dudoso"
    solo_tel_dir = cola / "solo_telefono"

    if simulado:
        aceptados = list(leads)
        dudosos = []
        solo_tel = []
        desc_calidad = []
        stats_cal = StatsCalidad(aceptados=len(leads))
    else:
        aceptados, dudosos, solo_tel, desc_calidad, stats_cal = clasificar_lote(leads)
    aceptados = priorizar_leads_contacto(aceptados)
    res["descartados"].extend(desc_calidad)

    escritos: list[Path] = []
    con_contacto = 0
    web_enriquecidos = 0

    def _procesar_bucket(items: list[dict], carpeta: Path, marcar: bool, categoria: str) -> None:
        nonlocal con_contacto, web_enriquecidos
        for lead in items:
            nombre = lead.get("nombre") or "—"
            if en_lista_no_contactar(lead.get("nombre", ""), lead.get("web", "")):
                res["descartados"].append(entrada_descarte(nombre, "lista no contactar", etapa="encolar"))
                continue
            reintento_failed = solo_reintento_failed(lead, cola)
            failed_previo = archivo_en_cola(cola, "failed", lead) if reintento_failed else None
            if marcar and ya_visto(lead.get("place_id", ""), lead.get("web", "")) and not reintento_failed:
                res["repetidos"].append(entrada_repetido(nombre, "registro_leads", ""))
                continue
            if marcar and max_encolar and len(escritos) >= max_encolar:
                res["pendiente_limite"].append(
                    entrada_descarte(nombre, f"límite de {max_encolar} por pasada", etapa="encolar")
                )
                continue
            enriquecido = enriquecer_lead(dict(lead), reglas, simulado=simulado)
            if enriquecido.get("web_enriquecido"):
                web_enriquecidos += 1
            if not puede_avisar_prospecto(enriquecido):
                res["sin_contacto"].append(entrada_sin_contacto(enriquecido))
                continue
            if carpeta == inbox and not califica_lead(enriquecido):
                score = enriquecido.get("puntaje")
                res["descartados"].append(
                    entrada_descarte(
                        nombre, f"puntaje bajo ({score} < {puntaje_minimo()})", etapa="puntaje"
                    )
                )
                continue
            if carpeta == inbox and not simulado:
                from b2b.verificacion_local import verificar_local

                ok_local, motivos, resumen = verificar_local(enriquecido, reglas.get("pais") or pais)
                if not ok_local:
                    res["descartados"].append(
                        entrada_descarte(
                            nombre,
                            "; ".join(motivos) or "verificacion_local",
                            etapa="verificacion_local",
                        )
                    )
                    continue
                enriquecido["resumen_verificacion"] = resumen
            payload = lead_a_inbox(enriquecido)
            path = _escribir_lead_cola(carpeta, payload)
            res[categoria].append({"nombre": nombre, "archivo": path.name})
            if marcar:
                marcar_visto(payload.get("place_id", ""), payload.get("web", ""))
                from b2b.leads_store import registrar_contacto

                registrar_contacto(payload)
                if not simulado:
                    try:
                        from b2b.supabase_client import guardar_lead_b2b

                        guardar_lead_b2b(payload)
                    except Exception as exc:
                        registrar_evento({"evento": "supabase_lead_fallo", "error": str(exc)[:200]})
                escritos.append(path)
                if failed_previo is not None and failed_previo.is_file():
                    try:
                        failed_previo.unlink()
                    except OSError:
                        pass
            if _payload_tiene_contacto(payload):
                con_contacto += 1
            time.sleep(0.05)

    _procesar_bucket(aceptados, inbox, marcar=True, categoria="encolados")
    for lead in dudosos:
        if pais and not simulado:
            append_dudoso_diario(pais, lead, lead.get("calidad_motivo") or "dudoso")
    _procesar_bucket(dudosos, dudoso_dir, marcar=False, categoria="dudosos")
    _procesar_bucket(solo_tel, solo_tel_dir, marcar=False, categoria="solo_telefono")
    if pais:
        append_sin_contacto_diario(pais, res["sin_contacto"])

    return escritos, con_contacto, web_enriquecidos, stats_cal, desc_calidad


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
    modo_global: bool = False,
    notificar_telegram_buscar: bool | None = None,
) -> dict:
    pais = reglas["pais"]
    tipos = _tipos_busqueda()
    if not fuente:
        fuente = "simulado" if simulado else resolver_fuente_leads()
    fuente_stats: dict = {}
    try:
        leads, llamadas, fuente_stats = buscar_en_pais(
            pais,
            tipos,
            max_leads,
            simulado=simulado,
            tipo_filtro=tipo_filtro,
            fuente=fuente,
            modo_global=modo_global,
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
    except Exception as error:
        from b2b.logging_ops import registrar_osm_fallo
        from b2b.osm_places import OsmIslaFallida

        if not isinstance(error, OsmIslaFallida) and not isinstance(error, RuntimeError):
            raise
        if isinstance(error, OsmIslaFallida) or fuente == "osm":
            registrar_osm_fallo(pais, str(error))
        return {
            "pais": pais,
            "encolados": 0,
            "leads": 0,
            "llamadas": 0,
            "fuente": fuente,
            "error": str(error)[:200],
            "isla_fallida": isinstance(error, OsmIslaFallida),
        }
    if solo_listar:
        for lead in leads:
            print(json.dumps(enriquecer_lead(dict(lead), reglas, simulado=simulado), ensure_ascii=False))
        registrar_busqueda(pais, llamadas, len(leads), simulado, fuente=fuente)
        return {
            "pais": pais,
            "encolados": 0,
            "leads": len(leads),
            "llamadas": llamadas,
            "fuente": fuente,
        }

    cola_dir = inbox.parent
    descartes_fuente = list((fuente_stats or {}).get("descartes") or [])
    nuevos, repetidos, repetidos_novedad = clasificar_novedad_detalle(leads, cola_dir)
    resultado: dict = {}
    paths, con_contacto, web_enriquecidos, stats_cal, _desc_calidad = encolar(
        nuevos,
        inbox,
        reglas,
        cola_dir=cola_dir,
        simulado=simulado,
        pais=pais,
        notificar_telegram_buscar=notificar_telegram_buscar,
        max_encolar=max_leads,
        resultado=resultado,
    )
    descartes = descartes_fuente + resultado["descartados"]
    repetidos_detalle = repetidos_novedad + resultado["repetidos"]
    conteo = conteo_isla(
        encontrados=len(descartes_fuente) + len(leads),
        descartados=len(descartes),
        repetidos=len(repetidos_detalle),
        resultado=resultado,
    )
    if conteo["sin_clasificar"]:
        registrar_evento({"evento": "conteo_no_cuadra", "pais": pais, **conteo})
    if not simulado:
        append_isla_en_archivo_diario(pais, descartes, repetidos_detalle)
        registrar_log_descartes_isla(pais, descartes, repetidos_detalle)
    fuente_stats = dict(fuente_stats or {})
    fuente_stats["web_enriquecidos"] = web_enriquecidos
    fuente_stats["descartes"] = descartes
    fuente_stats["calidad"] = {
        "aceptados": stats_cal.aceptados,
        "dudosos": stats_cal.dudosos,
        "web_caida": stats_cal.web_caida,
        "descartados_web": stats_cal.descartados_web,
        "descartados_tipo": stats_cal.descartados_tipo,
    }
    registrar_busqueda(pais, llamadas, len(paths), simulado, fuente=fuente)
    return {
        "pais": pais,
        "encolados": len(paths),
        "con_contacto": con_contacto,
        "encontrados": conteo["encontrados"],
        "nuevos": len(nuevos),
        "repetidos": conteo["repetidos"],
        "conteo": conteo,
        "descartes": descartes,
        "repetidos_detalle": repetidos_detalle,
        "fuente_stats": fuente_stats,
        "stats_calidad": fuente_stats["calidad"],
        "leads": len(leads),
        "llamadas": llamadas,
        "fuente": fuente,
    }


def conteo_isla(*, encontrados: int, descartados: int, repetidos: int, resultado: dict) -> dict:
    """encontrados = nuevos + repetidos + descartados + dudosos + sin_contacto (+ pendiente_limite).

    ``nuevos`` = encolados en inbox + solo_telefono. ``sin_clasificar`` debe ser 0.
    """
    encolados = len(resultado.get("encolados") or [])
    solo_telefono = len(resultado.get("solo_telefono") or [])
    conteo = {
        "encontrados": encontrados,
        "nuevos": encolados + solo_telefono,
        "encolados": encolados,
        "solo_telefono": solo_telefono,
        "repetidos": repetidos,
        "descartados": descartados,
        "dudosos": len(resultado.get("dudosos") or []),
        "sin_contacto": len(resultado.get("sin_contacto") or []),
        "pendiente_limite": len(resultado.get("pendiente_limite") or []),
    }
    suma = sum(conteo[k] for k in CATEGORIAS_RESUMEN)
    conteo["sin_clasificar"] = encontrados - suma
    return conteo


def _diagnostico_cero(stats_list: list[dict]) -> dict:
    descartes: list = []
    repetidos = 0
    errores: list[str] = []
    presupuesto = False
    for stats in stats_list:
        descartes.extend(stats.get("descartes") or [])
        repetidos += int(stats.get("repetidos") or 0)
        fuente_stats = stats.get("fuente_stats") or {}
        err = fuente_stats.get("google_error") or ""
        if not err and stats.get("fuente") == "google" and stats.get("error"):
            err = stats.get("error")
        if err:
            errores.append(str(err)[:200])
        if stats.get("presupuesto_agotado") or fuente_stats.get("presupuesto_agotado"):
            presupuesto = True
    return {
        "presupuesto": presupuesto,
        "google_error": "; ".join(errores[:3]),
        "repetidos": repetidos,
        "descartes": descartes,
    }


def _telegram_tras_isla(stats: dict, simulado: bool, solo_listar: bool) -> None:
    if solo_listar:
        return
    pais = str(stats.get("pais", ""))
    if stats.get("isla_fallida"):
        avisar_isla_fallida(pais, simulado=simulado)


def es_dia_busqueda(ahora: datetime | None = None) -> bool:
    """Lunes–sábado en Santo Domingo. Domingo no busca (el envío de correo sigue Lun–Vie en zonas.py)."""
    from b2b.zonas import tz

    zona = tz("America/Santo_Domingo")
    if ahora is None:
        local = datetime.now(zona)
    elif ahora.tzinfo is None:
        local = ahora.replace(tzinfo=timezone.utc).astimezone(zona)
    else:
        local = ahora.astimezone(zona)
    return local.weekday() < 6  # 0=lun … 5=sáb; 6=domingo


def _stats_domingo() -> dict:
    return {
        "encolados": 0,
        "pais": "",
        "llamadas": 0,
        "fuente": "",
        "motivo": "domingo",
        "modo": "pausado_domingo",
    }


def prospectar(
    pais_cli: str | None,
    max_leads: int,
    inbox: Path,
    simulado: bool = False,
    solo_listar: bool = False,
    tipo_filtro: str = "",
    buscar_global: bool = False,
) -> dict:
    import os

    # El timer ya evita el domingo; esto corta también un start manual o Persistent=true.
    if not simulado and not es_dia_busqueda():
        print("Buscador: domingo en Santo Domingo — no hay búsqueda (lunes a sábado).", file=sys.stderr)
        return _stats_domingo()

    if not simulado:
        return _prospectar(pais_cli, max_leads, inbox, simulado, solo_listar, tipo_filtro, buscar_global)
    previo = os.environ.get("B2B_SIMULADO")
    os.environ["B2B_SIMULADO"] = "1"
    try:
        return _prospectar(pais_cli, max_leads, inbox, simulado, solo_listar, tipo_filtro, buscar_global)
    finally:
        if previo is None:
            os.environ.pop("B2B_SIMULADO", None)
        else:
            os.environ["B2B_SIMULADO"] = previo


def _prospectar(
    pais_cli: str | None,
    max_leads: int,
    inbox: Path,
    simulado: bool,
    solo_listar: bool,
    tipo_filtro: str,
    buscar_global: bool,
) -> dict:
    fuente = "simulado" if simulado else resolver_fuente_leads()
    import os

    if buscar_global:
        return prospectar_turno_global(
            pais_cli,
            max_leads,
            inbox,
            simulado=simulado,
            solo_listar=solo_listar,
            tipo_filtro=tipo_filtro,
        )

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
            from b2b.despachador_tarjetas import sellar_tanda

            sellar_tanda(inbox, max_leads)
        return out
    if _islas_agotadas_en_google(fuente, zona):
        print("Islas ya buscadas en Google este mes: paso a la rotación global.", file=sys.stderr)
        registrar_evento({"evento": "rotacion_global", "zona": zona, "fuente": fuente})
        return prospectar_turno_global(
            None, max_leads, inbox, simulado=simulado, solo_listar=solo_listar, tipo_filtro=tipo_filtro
        )
    return prospectar_prioridad_inicial(
        max_leads, inbox, simulado, solo_listar, tipo_filtro, fuente=fuente, zona=zona
    )


def _islas_agotadas_en_google(fuente: str, zona: str | None) -> bool:
    from b2b.places import google_disponible, islas_agotadas_google

    if fuente not in ("google", "ambas") or not google_disponible():
        return False
    return islas_agotadas_google([p["pais"] for p in paises_prioridad_busqueda(zona)])


def prospectar_turno_global(
    pais_cli: str | None,
    max_leads: int,
    inbox: Path,
    simulado: bool = False,
    solo_listar: bool = False,
    tipo_filtro: str = "",
) -> dict:
    """Un país (o celda parcial) por invocación; cola en data/paises_cola.json."""
    from b2b.buscar_global import avanzar_siguiente_pais, cargar_estado_global, siguiente_pais_cola
    from b2b.paises_cola import entry_por_pais

    if pais_cli and pais_cli.strip():
        reglas = resolver_pais_objetivo(pais_cli)
        fila = entry_por_pais(reglas["pais"])
    else:
        fila = siguiente_pais_cola()
        if fila is None and not simulado:
            from b2b.buscar_global import guardar_estado_global

            guardar_estado_global({"pais_idx": 0, "celda_idx": 0, "completo": False, "pais": ""})
            registrar_evento({"evento": "cola_global_reiniciada"})
            fila = siguiente_pais_cola()
        if fila is None:
            return {
                "pais": "cola_global",
                "encolados": 0,
                "leads": 0,
                "llamadas": 0,
                "fuente": "osm",
                "fin_cola": True,
            }
        reglas = buscar_pais(fila["pais"])
        if reglas is None:
            avanzar_siguiente_pais()
            raise ValueError(f"País en cola sin country_rules.json: {fila['pais']}")

    fuente = "simulado" if simulado else resolver_fuente_leads()
    out = prospectar_un_pais(
        reglas,
        max_leads,
        inbox,
        simulado,
        solo_listar,
        tipo_filtro,
        fuente=fuente,
        modo_global=not simulado,
        notificar_telegram_buscar=not solo_listar,
    )
    out["modo"] = "buscar_global"
    out["fuente"] = fuente
    if not solo_listar and not simulado:
        estado = cargar_estado_global()
        if estado.get("completo"):
            avanzar_siguiente_pais()
            import os as _os

            try:
                pausa = float(_os.getenv("B2B_PAUSA_ENTRE_PAISES_SEC", "90") or "90")
            except ValueError:
                pausa = 90.0
            if pausa > 0:
                time.sleep(pausa)
        _telegram_tras_isla(out, simulado, solo_listar)
    return out


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
    detalle_islas: dict[str, dict] = {}
    stats_corrida: list[dict] = []
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
        stats_corrida.append(stats)
        enc = int(stats.get("encolados", 0))
        total_encolados += enc
        total_leads += int(stats.get("leads", 0))
        total_llamadas += int(stats.get("llamadas", 0))
        nombre_isla = str(stats.get("pais", reglas["pais"]))
        if enc > 0:
            encolados_por_isla[nombre_isla] = enc
            contacto_por_isla[nombre_isla] = int(stats.get("con_contacto", 0))
        fs = stats.get("fuente_stats") or {}
        detalle_islas[nombre_isla] = {
            **fs,
            "encontrados": stats.get("encontrados", stats.get("leads", 0)),
            "web_enriquecidos": fs.get("web_enriquecidos", 0),
        }
        _telegram_tras_isla(stats, simulado, solo_listar)
        if stats.get("isla_fallida"):
            islas_fallidas.append(nombre_isla)
        if stats.get("presupuesto_agotado"):
            presupuesto_agotado = True
            break
        if fuente in ("osm", "google", "ambas") and not simulado:
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
        from b2b.despachador_tarjetas import sellar_tanda

        sellar_tanda(inbox, max_leads)
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
