from __future__ import annotations

import os
import re

from b2b.catalogo_check import WHOLESALE_URL, resolver_catalogo_pdf, verificar_vitolas
from b2b.catalogo_vitolas import intro_vitolas, lineas_vitolas, vitolas_ordenadas
from b2b.country_rules import buscar_pais
from b2b.idioma import idioma_para_lead
from b2b.website import detectar_idioma_desde_web, web_confiable_para_idioma
from b2b.paths import KNOWLEDGE

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
    "pt": "Se preferir não receber mais mensagens, responda STOP.",
}

MD_V2_SPECIAL = set(r"_*[]()~`>#+-=|{}.")


def _resumen_entrenamiento() -> str:
    path = KNOWLEDGE / "resumen_entrenamiento.md"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return ""


CARGO_VP = {
    "es": "Vicepresidenta de Ventas",
    "en": "Vice President, Sales",
    "fr": "Vice-présidente, Ventes",
    "pt": "Vice-presidente, Vendas",
    "nl": "Vice President, Sales",
    "de": "Vice President, Sales",
    "it": "Vice President, Sales",
}
EMPRESA_FIRMA = "Cazador de Sueños Cigar SRL"
NOMBRE_VP = "Yaniris Agustina Ureña"


def _firma(idioma: str) -> tuple[str, bool]:
    """Firma fija de la vicepresidenta; contacto opcional vía FIRMA_*."""
    lineas = [
        NOMBRE_VP,
        CARGO_VP.get(idioma, CARGO_VP["en"]),
        EMPRESA_FIRMA,
    ]
    email = os.getenv("FIRMA_EMAIL", "").strip()
    telefono = os.getenv("FIRMA_TELEFONO", "").strip()
    if email:
        lineas.append(email)
    if telefono:
        lineas.append(telefono)
    return "\n".join(lineas), True


def _linea_pdf(idioma: str, pdf: str, aviso: str) -> str:
    prefijos = {
        "es": "Catálogo mayorista en PDF (sin tarifas publicadas en línea)",
        "fr": "Catalogue grossiste PDF (sans tarifs publiés en ligne)",
        "pt": "Catálogo grossista PDF (sem preços publicados online)",
        "nl": "Groothandelscatalogus PDF (zonder gepubliceerde tarieven online)",
        "en": "Wholesale catalog PDF (without listed prices)",
    }
    pref = prefijos.get(idioma, prefijos["en"])
    if aviso:
        return f"{aviso}\n{pref}: {pdf}"
    return f"{pref}: {pdf}"


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
            "pt": (
                "Estamos abertos a discutir exclusividade territorial, volumes mínimos, calendário de amostras "
                "e apoio no ponto de venda."
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
            "pt": (
                "Para a sua loja, apresentamos a linha completa com rotação estável e uma experiência de fumo "
                "consistente para os seus clientes habituais."
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
            "pt": (
                "Para o seu lounge, destacamos perfis de fortaleza variados e origem dominicana artesanal para "
                "recomendações à mesa."
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
            "pt": (
                "Para o humidor do seu hotel ou resort, propomos uma seleção premium compacta das seis vitolas, "
                "adequada a hóspedes e serviço de lounge."
            ),
        },
        "duty_free": {
            "es": "Para duty free, el mix y los volúmenes se acuerdan con su importador local.",
            "en": "For duty free, mix and volumes are agreed with your local importer.",
            "fr": "Pour le duty free, assortiment et volumes avec votre importateur local.",
            "nl": "Voor duty free worden mix en volumes met uw lokale importeur afgestemd.",
            "pt": "Para duty free, mix e volumes acordam-se com o importador local.",
        },
        "casino": {
            "es": "Para su casino o área premium, proponemos un surtido compacto de vitolas de rotación estable para humidor de piso.",
            "en": "For your casino or premium floor, we propose a compact rotation of vitolas suited to on-floor humidor service.",
            "fr": "Pour votre casino ou espace premium, nous proposons un assortiment compact pour humidor de salle.",
            "nl": "Voor uw casino of premiumruimte stellen we een compact assortiment voor voor humidor-service.",
            "pt": "Para o seu casino ou área premium, propomos um sortido compacto para humidor de piso.",
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
        "pt": "Teremos prazer em agendar uma chamada ou enviar amostras comerciais.",
    }
    return textos.get(idioma, textos["en"])


def _nota_interna_aduana(entry: dict | None) -> str:
    """Solo informativa; no bloquea envío del borrador."""
    if not entry:
        return ""
    lic = (entry.get("licencia_comprador") or "").strip()
    if lic.upper().startswith("BORRADOR"):
        return "Reglas aduaneras en borrador en country_rules; confirmar con importador."
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
    verificar_vitolas()
    cat = resolver_catalogo_pdf(idioma)
    pdf = cat.url
    linea_pdf = _linea_pdf(idioma, pdf, cat.aviso_cliente)
    baja = OPT_OUT.get(idioma, OPT_OUT["en"])
    angulo = _angulo_tipo(idioma, tipo_negocio)
    bloque_cat = intro_vitolas(idioma) + "\n" + lineas_vitolas(idioma)
    firma, _firma_ok = _firma(idioma)
    cierre = _cierre_contacto(idioma)
    portal = {
        "es": f"Portal B2B: {WHOLESALE_URL}",
        "fr": f"Portail B2B : {WHOLESALE_URL}",
        "pt": f"Portal B2B: {WHOLESALE_URL}",
        "nl": f"B2B-portaal: {WHOLESALE_URL}",
        "en": f"B2B portal: {WHOLESALE_URL}",
    }.get(idioma, f"B2B portal: {WHOLESALE_URL}")

    if idioma == "es":
        cuerpo = (
            f"Saludos, equipo de {nombre_local}.\n\n"
            "Somos Cazador de Sueños Cigar SRL, fábrica en Santiago de los Caballeros, "
            "República Dominicana. Elaboramos puros premium 100% hechos a mano.\n\n"
            f"{bloque_cat}\n\n{angulo}\n\n"
            f"{linea_pdf}\n"
            f"{portal}\n\n"
            f"{cierre}\n\n{baja}\n\n"
        )
    elif idioma == "fr":
        cuerpo = (
            f"Bonjour l'équipe de {nombre_local},\n\n"
            "Nous sommes Cazador de Sueños Cigar SRL, manufacture à Santiago de los Caballeros, "
            "République dominicaine. Cigares premium 100% faits main.\n\n"
            f"{bloque_cat}\n\n{angulo}\n\n"
            f"{linea_pdf}\n"
            f"{portal}\n\n"
            f"{cierre}\n\n{baja}\n\n"
        )
    elif idioma == "nl":
        cuerpo = (
            f"Hallo team van {nombre_local},\n\n"
            "Wij zijn Cazador de Sueños Cigar SRL, fabriek in Santiago de los Caballeros, "
            "Dominicaanse Republiek. Premium sigaren, 100% handgemaakt.\n\n"
            f"{bloque_cat}\n\n{angulo}\n\n"
            f"{linea_pdf}\n"
            f"{portal}\n\n"
            f"{cierre}\n\n{baja}\n\n"
        )
    elif idioma == "pt":
        cuerpo = (
            f"Olá, equipa da {nombre_local},\n\n"
            "Somos a Cazador de Sueños Cigar SRL, fábrica em Santiago de los Caballeros, "
            "República Dominicana. Charutos premium 100% feitos à mão.\n\n"
            f"{bloque_cat}\n\n{angulo}\n\n"
            f"{linea_pdf}\n"
            f"{portal}\n\n"
            f"{cierre}\n\n{baja}\n\n"
        )
    else:
        cuerpo = (
            f"Hello {nombre_local} team,\n\n"
            "We are Cazador de Sueños Cigar SRL, a factory in Santiago de los Caballeros, "
            "Dominican Republic. Premium cigars, 100% handmade.\n\n"
            f"{bloque_cat}\n\n{angulo}\n\n"
            f"{linea_pdf}\n"
            f"{portal}\n\n"
            f"{cierre}\n\n{baja}\n\n"
        )

    cuerpo += firma

    if sin_correo_publico:
        notas = {
            "es": "\n(Nota: sin correo genérico publicado; contactar por teléfono o web.)\n",
            "en": "\n(Note: no generic business email published; contact via phone or website.)\n",
            "fr": "\n(Note : pas d'e-mail générique public ; contact par téléphone ou site.)\n",
            "nl": "\n(Let op: geen publiek generiek e-mailadres; contact via telefoon of website.)\n",
            "pt": "\n(Nota: sem e-mail genérico publicado; contactar por telefone ou site.)\n",
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


def texto_corto_prospecto_buscar(nombre_local: str, idioma: str, tipo: str = "tienda") -> str:
    """Mensaje 2 del flujo --buscar (≤6 líneas). No reemplaza borrador_prospecto."""
    nombre = (nombre_local or "").strip() or "there"
    cat = resolver_catalogo_pdf(idioma)
    catalogo = cat.url or WHOLESALE_URL
    opt = OPT_OUT.get(idioma, OPT_OUT["en"])
    tipo_txt = tipo.replace("_", " ")
    bloques = {
        "es": (
            f"Hola, {nombre}: soy Yaniris (Cazador de Sueños, fábrica en Santiago, RD).\n"
            f"Queremos poner nuestros cigarros en su {tipo_txt}.\n"
            f"Catálogo mayorista: {catalogo}\n"
            "¿Llamada breve o muestras esta semana?\n"
            f"{opt}"
        ),
        "en": (
            f"Hello {nombre} — Yaniris, Cazador de Sueños (factory in Santiago, DR).\n"
            f"We'd like our cigars in your {tipo_txt}.\n"
            f"Wholesale catalog: {catalogo}\n"
            "Short call or samples this week?\n"
            f"{opt}"
        ),
        "fr": (
            f"Bonjour {nombre} — Yaniris, Cazador de Sueños (Santiago, RD).\n"
            f"Nous proposons nos cigares pour votre {tipo_txt}.\n"
            f"Catalogue grossiste : {catalogo}\n"
            "Un appel ou des échantillons cette semaine ?\n"
            f"{opt}"
        ),
        "nl": (
            f"Hallo {nombre} — Yaniris, Cazador de Sueños (fabriek Santiago, DR).\n"
            f"Graag onze sigaren in uw {tipo_txt}.\n"
            f"Groothandelscatalogus: {catalogo}\n"
            "Kort gesprek of stalen deze week?\n"
            f"{opt}"
        ),
        "pt": (
            f"Olá {nombre} — Yaniris, Cazador de Sueños (Santiago, RD).\n"
            f"Queremos os nossos charutos na sua {tipo_txt}.\n"
            f"Catálogo grossista: {catalogo}\n"
            "Chamada breve ou amostras esta semana?\n"
            f"{opt}"
        ),
    }
    texto = bloques.get(idioma, bloques["en"])
    if len(texto.splitlines()) > 6:
        raise ValueError("Texto corto supera 6 líneas.")
    if PROHIBIDO_RE.search(texto):
        raise ValueError("Texto corto contiene términos prohibidos.")
    return texto


def generar_tarjeta_telegram(
    nombre_local: str,
    pais: str,
    web: str,
    correo: str,
    meta: dict | None = None,
) -> dict:
    meta = meta or {}
    entry = buscar_pais(pais)
    idioma_web = (meta.get("idioma_web") or "").strip()
    idioma_fuente = (meta.get("idioma_fuente") or "").strip()
    preferido = (meta.get("idioma") or "").strip()
    if web.startswith(("http://", "https://")) and web_confiable_para_idioma(web):
        if not idioma_web:
            idioma_web, idioma_fuente = detectar_idioma_desde_web(web)
    else:
        idioma_web = ""
        idioma_fuente = ""
    idioma = idioma_para_lead(
        pais,
        idioma_web=idioma_web,
        preferido=preferido,
        web=web,
    )
    if idioma == "pap":
        meta["nota_idioma"] = "Papiamento: revisar borrador con hablante nativo."
        idioma = "en"
    dificultad = meta.get("dificultad_aduana", meta.get("dificultad_pais"))
    if dificultad is None and entry:
        dificultad = entry.get("dificultad")
    sem_nombre, sem_etiqueta = semaforo_aduana(dificultad)
    tipo = meta.get("tipo") or meta.get("tipo_negocio") or "tienda"
    sin_correo = bool(meta.get("sin_correo_publico")) or not (correo or "").strip()
    cat = resolver_catalogo_pdf(idioma)
    draft = borrador_prospecto(idioma, nombre_local, tipo, sin_correo)
    correo_txt = (correo or "").strip() or "sin correo publicado, contactar por teléfono o web"
    telefono = (meta.get("telefono") or "").strip() or "—"
    direccion = (meta.get("direccion") or "").strip() or "—"
    notas_internas: list[str] = []
    aduana = _nota_interna_aduana(entry)
    if aduana:
        notas_internas.append(aduana)
    if cat.nota_interna:
        notas_internas.append(cat.nota_interna)
    nota_interna = " · ".join(dict.fromkeys(notas_internas))

    texto = (
        "Cazador de Sueños · prospecto B2B\n"
        f"Nombre: {nombre_local.strip()}\n"
        f"Tipo: {tipo}\n"
        f"País: {pais.strip()}\n"
        f"Idioma borrador: {idioma}"
        + (f" ({idioma_fuente})" if idioma_fuente else "")
        + "\n"
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
        f"*Idioma:* {md_escape(idioma)}"
        + (f" _({md_escape(idioma_fuente)})_" if idioma_fuente else "")
        + "\n"
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
