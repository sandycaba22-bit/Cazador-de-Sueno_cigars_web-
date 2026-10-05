from __future__ import annotations

import os
import re

from b2b.catalogo_vitolas import intro_vitolas, lineas_vitolas, vitolas_ordenadas
from b2b.country_rules import buscar_pais
from b2b.idioma import idioma_para_pais
from b2b.paths import KNOWLEDGE

WHOLESALE_URL = "https://www.cazadordesuenocigars.com/wholesale.html"
PDF_ES = "https://www.cazadordesuenocigars.com/catalogo/CazadorDeSuenos_Wholesale_ES.pdf"
PDF_EN = "https://www.cazadordesuenocigars.com/catalogo/CazadorDeSuenos_Wholesale_EN.pdf"

PROHIBIDO_RE = re.compile(
    r"\$\s?\d|USD\s?\d|\bprecio[s]?\b|\bprice list\b|\bpricing\b|autorizado por aduana|"
    r"libre de trabas|aprobado por la FDA|FDA approved|customs.?free",
    re.I,
)

OPT_OUT = {
    "es": "Si no desea recibir más mensajes, responda BAJA.",
    "en": "If you prefer not to receive further messages, reply STOP.",
    "fr": "Si vous ne souhaitez plus recevoir de messages, répondez STOP.",
    "nl": "Als u geen berichten meer wilt ontvangen, antwoord met STOP.",
    "de": "Wenn Sie keine weiteren Nachrichten wünschen, antworten Sie STOP.",
    "it": "Per non ricevere altri messaggi, risponda STOP.",
}

MD_V2_SPECIAL = set(r"_*[]()~`>#+-=|{}.")


def _pdf(idioma: str) -> str:
    return PDF_ES if idioma == "es" else PDF_EN


def _resumen_entrenamiento() -> str:
    path = KNOWLEDGE / "resumen_entrenamiento.md"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return ""


def _firma(idioma: str) -> tuple[str, bool]:
    """Devuelve bloque de firma y si está completa."""
    nombre = os.getenv("SENDER_NAME", "").strip()
    contacto = os.getenv("SENDER_CONTACT", "").strip()
    if not nombre or not contacto:
        return "", False
    cierres = {
        "es": "Atentamente,",
        "en": "Best regards,",
        "fr": "Cordialement,",
        "nl": "Met vriendelijke groet,",
        "de": "Mit freundlichen Grüßen,",
        "it": "Cordiali saluti,",
    }
    return f"{cierres.get(idioma, cierres['en'])}\n{nombre}\n{contacto}", True


def _angulo_tipo(idioma: str, tipo: str) -> str:
    """Ángulo según tipo; informado por knowledge/ (sin citar marcas al cliente)."""
    tipo = (tipo or "tienda").lower()
    _ = _resumen_entrenamiento()
    tabla = {
        "distribuidor": {
            "es": (
                "Estamos abiertos a conversar exclusividad territorial, volúmenes mínimos, calendario de "
                "muestras y material de punto de venta."
            ),
            "en": (
                "We're open to discussing territorial exclusivity, minimum volumes, sample timing and "
                "point-of-sale support."
            ),
            "fr": (
                "Nous sommes ouverts à discuter de l'exclusivité territoriale, des volumes minimum, "
                "du calendrier d'échantillons et du support point de vente."
            ),
            "nl": (
                "We bespreken graag territoriale exclusiviteit, minimumvolumes, sampleplanning en "
                "ondersteuning op het verkooppunt."
            ),
        },
        "tienda": {
            "es": (
                "Para su tienda, nos gustaría presentar la línea completa con rotación estable y una "
                "experiencia de fumada consistente para sus clientes habituales."
            ),
            "en": (
                "For your shop, we'd like to introduce our full line with steady rotation and a "
                "consistent smoking experience for your regular customers."
            ),
            "fr": (
                "Pour votre boutique, nous présentons la ligne complète avec une rotation régulière et "
                "une expérience de fumée cohérente pour votre clientèle."
            ),
            "nl": (
                "Voor uw winkel presenteren we de volledige lijn met stabiele rotatie en een consistente "
                "rookervaring voor vaste klanten."
            ),
        },
        "lounge": {
            "es": (
                "Para su lounge, destacamos perfiles de fortaleza variados y origen dominicano artesanal "
                "para recomendación al cliente en mesa."
            ),
            "en": (
                "For your lounge, we highlight varied strength profiles and handmade Dominican origin for "
                "table-side recommendations."
            ),
            "fr": (
                "Pour votre lounge, nous mettons en avant des profils de force variés et une origine "
                "dominicaine artisanale pour vos recommandations."
            ),
            "nl": (
                "Voor uw lounge benadrukken we uiteenlopende krachtprofielen en dominicaanse ambacht voor "
                "advies aan tafel."
            ),
        },
        "hotel": {
            "es": (
                "Para el humidor de su hotel o resort, proponemos una selección premium compacta de las "
                "seis vitolas, adecuada para huéspedes y servicio de lounge."
            ),
            "en": (
                "For your hotel or resort humidor, we propose a compact premium selection from our six "
                "vitolas, suited to guest gifting and lounge service."
            ),
            "fr": (
                "Pour l'humidor de votre hôtel ou resort, nous proposons une sélection premium compacte "
                "parmi nos six vitolas, adaptée aux clients et au lounge."
            ),
            "nl": (
                "Voor de humidor van uw hotel of resort stellen we een compact premium assortiment uit "
                "onze zes vitolas voor, geschikt voor gasten en lounge-service."
            ),
        },
        "duty_free": {
            "es": "Para duty free, el mix y los volúmenes se acuerdan con su importador local.",
            "en": "For duty free, mix and volumes are agreed with your local importer.",
            "fr": "Pour le duty free, assortiment et volumes avec votre importateur local.",
            "nl": "Voor duty free worden mix en volumes met uw lokale importeur afgestemd.",
        },
    }
    bloque = tabla.get(tipo) or tabla["tienda"]
    return bloque.get(idioma, bloque["en"])


def _cierre_contacto(idioma: str) -> str:
    textos = {
        "es": "Quedamos atentos: con gusto coordinamos una llamada o el envío de muestras comerciales.",
        "en": "We'd be glad to set up a call or send commercial samples.",
        "fr": "Nous serions ravis d'organiser un appel ou d'envoyer des échantillons commerciaux.",
        "nl": "We plannen graag een call of sturen commerciële samples.",
        "de": "Gern vereinbaren wir ein Gespräch oder senden Handelsmuster.",
        "it": "Saremo lieti di fissare una call o inviare campioni commerciali.",
    }
    return textos.get(idioma, textos["en"])


def _nota_interna_aduana(entry: dict | None) -> str:
    if not entry:
        return "Confirmar requisitos de importación con agente aduanal antes de ofertar."
    dif = int(entry.get("dificultad", 5))
    estado = entry.get("estado", "sin_verificar")
    if dif >= 4 or estado in ("sin_verificar", "preliminar"):
        return "Confirmar requisitos de importación con agente aduanal antes de ofertar."
    return ""


def semaforo_aduana(dificultad: int | None) -> tuple[str, str]:
    dif = int(dificultad or 5)
    if dif <= 2:
        return "VERDE", f"verde · dificultad {dif}"
    if dif == 3:
        return "AMARILLO", f"amarillo · dificultad {dif}"
    return "ROJO", f"rojo · dificultad {dif}"


def borrador_prospecto(
    idioma: str,
    nombre_local: str,
    tipo_negocio: str = "tienda",
    sin_correo_publico: bool = False,
) -> str:
    pdf = _pdf(idioma)
    baja = OPT_OUT.get(idioma, OPT_OUT["en"])
    angulo = _angulo_tipo(idioma, tipo_negocio)
    bloque_cat = intro_vitolas(idioma) + "\n" + lineas_vitolas(idioma)
    firma, firma_ok = _firma(idioma)
    cierre = _cierre_contacto(idioma)

    if idioma == "es":
        cuerpo = (
            f"Saludos, equipo de {nombre_local}.\n\n"
            "Somos Cazador de Sueños Cigar SRL, fábrica en Santiago de los Caballeros, "
            "República Dominicana. Elaboramos puros premium 100% hechos a mano.\n\n"
            f"{bloque_cat}\n\n{angulo}\n\n"
            f"Catálogo mayorista en PDF (sin tarifas publicadas en línea): {pdf}\n"
            f"Portal B2B: {WHOLESALE_URL}\n\n"
            f"{cierre}\n\n{baja}\n\n"
        )
    elif idioma == "fr":
        cuerpo = (
            f"Bonjour l'équipe de {nombre_local},\n\n"
            "Nous sommes Cazador de Sueños Cigar SRL, manufacture à Santiago de los Caballeros, "
            "République dominicaine. Cigares premium 100% faits main.\n\n"
            f"{bloque_cat}\n\n{angulo}\n\n"
            f"Catalogue grossiste PDF (sans tarifs publiés en ligne) : {pdf}\n"
            f"Portail B2B : {WHOLESALE_URL}\n\n"
            f"{cierre}\n\n{baja}\n\n"
        )
    elif idioma == "nl":
        cuerpo = (
            f"Hallo team van {nombre_local},\n\n"
            "Wij zijn Cazador de Sueños Cigar SRL, fabriek in Santiago de los Caballeros, "
            "Dominicaanse Republiek. Premium sigaren, 100% handgemaakt.\n\n"
            f"{bloque_cat}\n\n{angulo}\n\n"
            f"Groothandelscatalogus PDF (zonder gepubliceerde tarieven online): {pdf}\n"
            f"B2B-portaal: {WHOLESALE_URL}\n\n"
            f"{cierre}\n\n{baja}\n\n"
        )
    else:
        cuerpo = (
            f"Hello {nombre_local} team,\n\n"
            "We are Cazador de Sueños Cigar SRL, a factory in Santiago de los Caballeros, "
            "Dominican Republic. Premium cigars, 100% handmade.\n\n"
            f"{bloque_cat}\n\n{angulo}\n\n"
            f"Wholesale catalog PDF (without listed prices): {pdf}\n"
            f"B2B portal: {WHOLESALE_URL}\n\n"
            f"{cierre}\n\n{baja}\n\n"
        )

    if firma_ok:
        cuerpo += firma
    else:
        cuerpo += "Cazador de Sueños Cigar SRL"

    if sin_correo_publico:
        notas = {
            "es": "\n(Nota: sin correo genérico publicado; contactar por teléfono o web.)\n",
            "en": "\n(Note: no generic business email published; contact via phone or website.)\n",
            "fr": "\n(Note : pas d'e-mail générique public ; contact par téléphone ou site.)\n",
            "nl": "\n(Let op: geen publiek generiek e-mailadres; contact via telefoon of website.)\n",
        }
        cuerpo += notas.get(idioma, notas["en"])

    if PROHIBIDO_RE.search(cuerpo):
        raise ValueError("Borrador contiene texto prohibido (precios o aduana/FDA).")
    if idioma == "en" and "El Sultán" in cuerpo:
        raise ValueError("Mezcla de idiomas en borrador inglés (usar nombre EN del catálogo).")
    return cuerpo


def md_escape(value):
    return "".join("\\" + ch if ch in MD_V2_SPECIAL else ch for ch in str(value))


def code_escape(value):
    return str(value).replace("\\", "\\\\").replace("`", "\\`").replace("```", "'''")


def generar_tarjeta_telegram(
    nombre_local: str,
    pais: str,
    web: str,
    correo: str,
    meta: dict | None = None,
) -> dict:
    meta = meta or {}
    entry = buscar_pais(pais)
    idioma = meta.get("idioma") or idioma_para_pais(pais)
    if idioma == "pap":
        meta["nota_idioma"] = "Papiamento: revisar borrador con hablante nativo."
        idioma = "en"
    dificultad = meta.get("dificultad_aduana", meta.get("dificultad_pais"))
    if dificultad is None and entry:
        dificultad = entry.get("dificultad")
    sem_nombre, sem_etiqueta = semaforo_aduana(dificultad)
    tipo = meta.get("tipo") or meta.get("tipo_negocio") or "tienda"
    sin_correo = bool(meta.get("sin_correo_publico")) or not (correo or "").strip()
    draft = borrador_prospecto(idioma, nombre_local, tipo, sin_correo)
    correo_txt = (correo or "").strip() or "sin correo publicado, contactar por teléfono o web"
    telefono = (meta.get("telefono") or "").strip() or "—"
    direccion = (meta.get("direccion") or "").strip() or "—"
    notas_internas: list[str] = []
    aduana = _nota_interna_aduana(entry)
    if aduana:
        notas_internas.append(aduana)
    _, firma_ok = _firma(idioma)
    if not firma_ok:
        notas_internas.append("falta firma")
    if meta.get("estado_reglas") in ("sin_verificar", "preliminar") and not aduana:
        notas_internas.append("Confirmar requisitos de importación con agente aduanal antes de ofertar.")
    nota_interna = " · ".join(dict.fromkeys(notas_internas))

    texto = (
        "Cazador de Sueños · prospecto B2B\n"
        f"Nombre: {nombre_local.strip()}\n"
        f"Tipo: {tipo}\n"
        f"País: {pais.strip()}\n"
        f"Idioma borrador: {idioma}\n"
        f"Aduana: {sem_etiqueta} ({meta.get('estado_reglas') or (entry or {}).get('estado', 'preliminar')})\n"
        f"Teléfono: {telefono}\n"
        f"Correo: {correo_txt}\n"
        f"Web: {web.strip()}\n"
        f"Dirección: {direccion}\n"
    )
    if meta.get("fuente_correo"):
        texto += f"Fuente correo: {meta['fuente_correo']}\n"
    if nota_interna:
        texto += f"NOTA INTERNA (no enviar al prospecto): {nota_interna}\n"
    texto += "\nBorrador listo:\n" + draft

    markdown = (
        "*Cazador de Sueños · prospecto B2B*\n"
        f"*Nombre:* {md_escape(nombre_local.strip())}\n"
        f"*Tipo:* {md_escape(tipo)}\n"
        f"*País:* {md_escape(pais.strip())}\n"
        f"*Idioma:* {md_escape(idioma)}\n"
        f"*Aduana:* {md_escape(sem_etiqueta)}\n"
        f"*Teléfono:* {md_escape(telefono)}\n"
        f"*Correo:* {md_escape(correo_txt)}\n"
        f"*Web:* {md_escape(web.strip())}\n"
        f"*Dirección:* {md_escape(direccion)}\n"
    )
    if nota_interna:
        markdown += f"*Nota interna:* {md_escape(nota_interna)}\n"
    markdown += "\n*Borrador listo:*\n```\n" + code_escape(draft) + "\n```"

    return {
        "markdown": markdown,
        "texto": texto,
        "idioma": idioma,
        "semaforo": sem_nombre,
        "borrador": draft,
    }
