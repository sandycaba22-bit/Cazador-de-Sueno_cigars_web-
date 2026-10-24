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
EMPRESA_FIRMA = "Cazador de Sueño Cigars SRL"
NOMBRE_VP = "Yaniris Agustina Ureña"


def _firma(idioma: str) -> tuple[str, bool]:
    """Firma fija de la vicepresidenta; contacto opcional vía FIRMA_*."""
    lineas = [
        NOMBRE_VP,
        CARGO_VP.get(idioma, CARGO_VP["en"]),
        EMPRESA_FIRMA,
    ]
    email = os.getenv("FIRMA_EMAIL", "cazadordesueno1@gmail.com").strip()
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
        "es": "Quedamos atentos: con gusto coordinamos una llamada. "
        "Muestras comerciales disponibles para comercios con licencia.",
        "en": "We'd be glad to set up a call. Commercial samples available for licensed retailers.",
        "fr": "Nous serions ravis d'organiser un appel. "
        "Échantillons commerciaux disponibles pour les détaillants agréés.",
        "nl": "We plannen graag een call. Commerciële samples beschikbaar voor erkende verkooppunten.",
        "de": "Gern vereinbaren wir ein Gespräch oder senden Handelsmuster.",
        "it": "Saremo lieti di fissare una call o inviare campioni commerciali.",
        "pt": "Teremos prazer em agendar uma chamada. Amostras comerciais disponíveis para retalhistas licenciados.",
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
            "Somos Cazador de Sueño Cigars SRL, fábrica en Santiago de los Caballeros, "
            "República Dominicana. Elaboramos puros premium 100% hechos a mano.\n\n"
            f"{bloque_cat}\n\n{angulo}\n\n"
            f"{linea_pdf}\n"
            f"{portal}\n\n"
            f"{cierre}\n\n{baja}\n\n"
        )
    elif idioma == "fr":
        cuerpo = (
            f"Bonjour l'équipe de {nombre_local},\n\n"
            "Nous sommes Cazador de Sueño Cigars SRL, manufacture à Santiago de los Caballeros, "
            "République dominicaine. Cigares premium 100% faits main.\n\n"
            f"{bloque_cat}\n\n{angulo}\n\n"
            f"{linea_pdf}\n"
            f"{portal}\n\n"
            f"{cierre}\n\n{baja}\n\n"
        )
    elif idioma == "nl":
        cuerpo = (
            f"Hallo team van {nombre_local},\n\n"
            "Wij zijn Cazador de Sueño Cigars SRL, fabriek in Santiago de los Caballeros, "
            "Dominicaanse Republiek. Premium sigaren, 100% handgemaakt.\n\n"
            f"{bloque_cat}\n\n{angulo}\n\n"
            f"{linea_pdf}\n"
            f"{portal}\n\n"
            f"{cierre}\n\n{baja}\n\n"
        )
    elif idioma == "pt":
        cuerpo = (
            f"Olá, equipa da {nombre_local},\n\n"
            "Somos a Cazador de Sueño Cigars SRL, fábrica em Santiago de los Caballeros, "
            "República Dominicana. Charutos premium 100% feitos à mão.\n\n"
            f"{bloque_cat}\n\n{angulo}\n\n"
            f"{linea_pdf}\n"
            f"{portal}\n\n"
            f"{cierre}\n\n{baja}\n\n"
        )
    else:
        cuerpo = (
            f"Hello {nombre_local} team,\n\n"
            "We are Cazador de Sueño Cigars SRL, a factory in Santiago de los Caballeros, "
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


EMAIL_VP_VENTAS = "cazadordesueno1@gmail.com"


TIPO_IDIOMA = {
    "tienda": {"es": "tabaquería", "en": "cigar shop", "fr": "cave à cigares", "nl": "sigarenwinkel",
               "pt": "tabacaria"},
    "lounge": {"es": "lounge de cigarros", "en": "cigar lounge", "fr": "lounge cigare", "nl": "sigarenlounge",
               "pt": "lounge de charutos"},
    "distribuidor": {"es": "distribuidora", "en": "distribution business", "fr": "société de distribution",
                     "nl": "distributiebedrijf", "pt": "distribuidora"},
    "hotel": {"es": "hotel", "en": "hotel", "fr": "hôtel", "nl": "hotel", "pt": "hotel"},
    "casino": {"es": "casino", "en": "casino", "fr": "casino", "nl": "casino", "pt": "casino"},
    "duty_free": {"es": "tienda duty free", "en": "duty free shop", "fr": "boutique duty free",
                  "nl": "duty-free winkel", "pt": "loja duty free"},
}

MUESTRAS = {
    "es": "Muestras comerciales disponibles para comercios con licencia.",
    "en": "Commercial samples available for licensed retailers.",
    "fr": "Échantillons commerciaux disponibles pour les détaillants agréés.",
    "nl": "Commerciële samples beschikbaar voor erkende verkooppunten.",
    "pt": "Amostras comerciais disponíveis para retalhistas licenciados.",
}


def tipo_en_idioma(tipo: str, idioma: str) -> str:
    """'tienda' → 'cigar shop' / 'tabaquería' / 'cave à cigares' (nunca 'your tienda')."""
    tabla = TIPO_IDIOMA.get((tipo or "tienda").lower()) or TIPO_IDIOMA["tienda"]
    return tabla.get(idioma, tabla["en"])


def _catalogo(idioma: str) -> tuple[str, str]:
    """(url del PDF, aviso al cliente si se usa el PDF en inglés)."""
    cat = resolver_catalogo_pdf(idioma)
    aviso = cat.aviso_cliente
    return cat.url or WHOLESALE_URL, (f"{aviso}\n" if aviso else "")


def _validar(texto: str) -> str:
    if PROHIBIDO_RE.search(texto):
        raise ValueError("Borrador contiene términos prohibidos (precios o aduana/FDA).")
    return texto


def asunto_correo(nombre_local: str, idioma: str) -> str:
    nombre = (nombre_local or "").strip() or "your shop"
    idioma = idioma if idioma in MUESTRAS else "en"
    asuntos = {
        "es": f"Puros dominicanos para {nombre}",
        "en": f"Handmade Dominican cigars for {nombre}",
        "fr": f"Cigares dominicains pour {nombre}",
        "nl": f"Dominicaanse sigaren voor {nombre}",
        "pt": f"Charutos dominicanos para {nombre}",
    }
    return asuntos.get(idioma, asuntos["en"])


def borrador_corto(nombre_local: str, idioma: str, tipo: str = "tienda") -> str:
    """WhatsApp / Instagram: presentación breve, catálogo PDF y muestra."""
    nombre = (nombre_local or "").strip() or "there"
    catalogo, aviso = _catalogo(idioma)
    t = tipo_en_idioma(tipo, idioma)

    if idioma == "es":
        return _validar(
            f"Saludos, equipo de {nombre}.\n"
            f"Somos Cazador de Sueño Cigars SRL, fábrica boutique de puros premium hechos a mano en Santiago, "
            f"República Dominicana. Nos gustaría presentar nuestra línea a su {t}.\n"
            f"{aviso}Catálogo mayorista: {catalogo}\n"
            "Ofrecemos una muestra gratuita (free sample) para evaluación. ¿Conversamos?\n"
            f"Atentamente,\n{NOMBRE_VP} - {CARGO_VP['es']}"
        )
    if idioma == "fr":
        return _validar(
            f"Bonjour l'équipe de {nombre},\n"
            f"Nous sommes Cazador de Sueño Cigars SRL, manufacture de cigares faits main à Santiago, "
            f"République dominicaine. Nous souhaitons présenter notre gamme à votre {t}.\n"
            f"{aviso}Catalogue grossiste : {catalogo}\n"
            "Un échantillon gratuit est disponible pour évaluation. Pouvons-nous échanger ?\n"
            f"Cordialement,\n{NOMBRE_VP} - {CARGO_VP['fr']}"
        )
    
    texto = (
        f"Hello {nombre} team,\n"
        f"We are Cazador de Sueño Cigars SRL, a boutique cigar factory in Santiago, Dominican Republic. We craft 100% handmade premium cigars and would love to introduce our portfolio to your {tipo_en_idioma(tipo, 'en')}.\n"
        f"{aviso}Wholesale Catalog: {catalogo}\n"
        "We're happy to provide a free sample for your consideration. Open to a brief chat?\n"
        "Best,\n"
        "Yaniris Agustina Ureña - VP of Sales"
    )
    return texto

def borrador_correo(nombre_local: str, idioma: str, tipo: str = "tienda") -> str:
    """Versión correo: asunto, firma de la VP y línea de STOP (solo en correo)."""
    nombre = (nombre_local or "").strip() or "there"
    catalogo, aviso = _catalogo("en")
    t = tipo_en_idioma(tipo, "en")
    
    texto = (
        f"Subject: Handmade Dominican cigars for {nombre}\n\n"
        f"Hello {nombre} team,\n\n"
        "We are Cazador de Sueño Cigars SRL, a boutique cigar factory in Santiago de los Caballeros, Dominican Republic, "
        f"making 100% handmade premium cigars. We would like to explore placing our line in your {t}.\n\n"
        f"Wholesale catalog: {catalogo}\n"
        "A free sample is available for evaluation. Would a short call work for you?\n\n"
        "Best regards,\n"
        "Yaniris Agustina Ureña\n"
        "Vice President, Sales\n"
        "Cazador de Sueño Cigars SRL\n"
        "cazadordesueno1@gmail.com\n\n"
        "If you prefer not to receive further messages, reply STOP."
    )
    return _validar(texto)

def presentacion_prospecto_telegram(nombre_local: str, idioma: str, tipo: str = "tienda") -> str:
    """Compatibilidad: versión correo (firma VP + catálogo + STOP)."""
    return borrador_correo(nombre_local, idioma, tipo)


def texto_corto_prospecto_buscar(nombre_local: str, idioma: str, tipo: str = "tienda") -> str:
    """Compatibilidad: plantilla corta de WhatsApp / Instagram."""
    return borrador_corto(nombre_local, idioma, tipo)


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
    
    # Requerimiento 1: Redacción B2B Corta y Directa
    draft = borrador_corto(nombre_local, idioma, tipo)
    
    correo_txt = (correo or "").strip()
    telefono = (meta.get("telefono") or "").strip()
    ciudad = (meta.get("ciudad") or pais.strip()).strip()
    direccion = (meta.get("direccion") or "").strip()
    
    estado_contacto = []
    if telefono:
        estado_contacto.append("📞 Teléfono OK")
    if correo_txt:
        estado_contacto.append("✉️ Correo OK")
    if not estado_contacto:
        estado_contacto.append("⚠️ Sin contacto directo")
    estado_contacto_str = " | ".join(estado_contacto)

    # Requerimiento 3: Tarjeta Limpia
    texto = (
        "Cazador de Sueño Cigars SRL · Prospecto B2B\n"
        f"Negocio: {nombre_local.strip()}\n"
        f"Tipo: {tipo.title()}\n"
        f"Ciudad/País: {ciudad}\n"
        f"Contacto: {estado_contacto_str}\n"
    )
    texto += "\nBorrador (3-4 líneas):\n" + draft
    if sin_correo:
        texto += "\nNota: sin correo publicado; confirmar otro canal de contacto."

    markdown = (
        "*Cazador de Sueño Cigars SRL · Prospecto B2B*\n"
        f"*Negocio:* {md_escape(nombre_local.strip())}\n"
        f"*Tipo:* {md_escape(tipo.title())}\n"
        f"*Ciudad/País:* {md_escape(ciudad)}\n"
        f"*Contacto:* {md_escape(estado_contacto_str)}\n"
    )
    markdown += "\n*Borrador sugerido:*\n```\n" + code_escape(draft) + "\n```"

    # Requerimiento 2: Botones Interactivos de Acción (Inline Keyboards)
    import urllib.parse
    
    botones = []
    
    if telefono:
        # Limpiar número de teléfono (quitar espacios, guiones, paréntesis)
        tel_limpio = __import__('re').sub(r"[^\d+]", "", telefono)
        if not tel_limpio.startswith("+"):
            tel_limpio = "+" + tel_limpio
            
        mensaje_wa = urllib.parse.quote(draft)
        wa_url = f"https://wa.me/{tel_limpio}?text={mensaje_wa}"
        botones.append([{"text": "📲 Enviar WhatsApp", "url": wa_url}])
        
    if correo_txt:
        asunto = asunto_correo(nombre_local, idioma)
        # Usar borrador_correo para el email que es más formal
        draft_correo = borrador_correo(nombre_local, idioma, tipo)
        asunto_q = urllib.parse.quote(asunto)
        body_q = urllib.parse.quote(draft_correo)
        mailto_url = f"mailto:{correo_txt}?subject={asunto_q}&body={body_q}"
        botones.append([{"text": "✉️ Enviar Correo", "url": mailto_url}])
        
    if direccion or nombre_local:
        query = urllib.parse.quote(f"{nombre_local} {ciudad}".strip())
        maps_url = f"https://www.google.com/maps/search/?api=1&query={query}"
        botones.append([{"text": "📍 Google Maps", "url": maps_url}])

    reply_markup = {"inline_keyboard": botones} if botones else None

    paquete = {
        "markdown": markdown,
        "texto": texto,
        "idioma": idioma,
        "semaforo": sem_nombre,
        "borrador": draft,
    }
    if reply_markup:
        paquete["reply_markup"] = reply_markup
        
    return paquete
