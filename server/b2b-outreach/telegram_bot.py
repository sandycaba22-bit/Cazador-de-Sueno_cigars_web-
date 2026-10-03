# Bot B2B de Cazador de Sueños Cigar SRL
# Arma un borrador comercial según el país y lo envía a tu Telegram.
# No busca locales ni escribe a terceros: el envío al prospecto lo haces tú.

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

WHOLESALE_URL = "https://www.cazadordesuenocigars.com/wholesale.html"

# Referencia de mostrador. Sirve para situar la casa, no para afirmar
# que un puro de Cazador de Sueños es el mismo blend ni que lo supera.
CASAS_REFERENCIA = (
    {"nombre": "Davidoff", "eje": "construcción precisa y presentación de casa"},
    {"nombre": "Arturo Fuente", "eje": "tradición dominicana de gran formato"},
    {"nombre": "Plasencia", "eje": "consistencia de exportación"},
    {"nombre": "La Aurora", "eje": "legado fabril dominicano"},
    {"nombre": "Cohiba", "eje": "referencia de puro de alta gama en el mostrador internacional"},
)

CASA = {
    "origen": "Santiago de los Caballeros, República Dominicana",
    "maestria": "100% hechos a mano por maestros torcedores",
    "capa": "San Andrés",
    "capote": "Olor Dominicano",
    "tripa": "cordillera del Cibao y selecciones premium",
}

POSICIONAMIENTO = {
    "es": (
        "En el mostrador donde el cliente ya reconoce a {casas}, nuestra respuesta "
        "es propia: puros {maestria} en {origen}, con capa {capa}, capote {capote} "
        "y tripa de la {tripa}."
    ),
    "en": (
        "On the shelf where guests already know {casas}, our answer is our own: "
        "cigars {maestria} in {origen}, with a {capa} wrapper, {capote} binder, "
        "and filler from the {tripa}."
    ),
    "fr": (
        "Sur le linéaire où le client reconnaît déjà {casas}, notre réponse est "
        "la nôtre : cigares {maestria} à {origen}, cape {capa}, sous-cape {capote} "
        "et tripe de la {tripa}."
    ),
    "de": (
        "Im Humidor, in dem Gäste {casas} bereits kennen, ist unsere Antwort eine "
        "eigene: Zigarren {maestria} in {origen}, mit Deckblatt {capa}, Umblatt "
        "{capote} und Einlage aus der {tripa}."
    ),
    "it": (
        "Sul banco dove l'ospite riconosce già {casas}, la nostra risposta è "
        "nostra: sigari {maestria} a {origen}, con capa {capa}, sottocapa {capote} "
        "e ripieno della {tripa}."
    ),
}

MAESTRA_IDIOMA = {
    "es": "100% hechos a mano por maestros torcedores",
    "en": "100% handmade by master torcedores",
    "fr": "100% faits main par des maîtres torcedores",
    "de": "100% von Meister-Torcedores von Hand gerollt",
    "it": "fatti a mano al 100% da maestri torcedores",
}

ORIGEN_IDIOMA = {
    "es": "Santiago de los Caballeros, República Dominicana",
    "en": "Santiago de los Caballeros, Dominican Republic",
    "fr": "Santiago de los Caballeros, République dominicaine",
    "de": "Santiago de los Caballeros, Dominikanische Republik",
    "it": "Santiago de los Caballeros, Repubblica Dominicana",
}

TRIPA_IDIOMA = {
    "es": "cordillera del Cibao y selecciones premium",
    "en": "Cibao mountain range and premium selections",
    "fr": "cordillère du Cibao et sélections premium",
    "de": "Cibao-Kordillere und Premium-Selektionen",
    "it": "cordigliera del Cibao e selezioni premium",
}

FRENCH = ("martinique", "guadeloupe", "france", "st. barths", "saint bart", "haiti", "haïti")
GERMAN = ("germany", "austria", "switzerland", "deutschland", "österreich", "schweiz", "suisse")
ITALIAN = ("italy", "italia")
SPANISH = (
    "dominicana",
    "españa",
    "espana",
    "spain",
    "mexico",
    "méxico",
    "puerto rico",
    "cuba",
    "colombia",
    "argentina",
    "chile",
)


def load_local_env():
    env_path = Path(__file__).with_name(".env")
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def telegram_credentials():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    placeholders = {
        "",
        "TU_TOKEN_DE_TELEGRAM",
        "TU_CHAT_ID",
        "AQUÍ_VAS_A_PONER_TU_NUMERO_DE_CHAT_ID",
        "AQUI_VAS_A_PONER_TU_NUMERO_DE_CHAT_ID",
    }
    if token in placeholders or chat_id in placeholders:
        raise RuntimeError(
            "Faltan TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID. "
            "Cópialos en server/b2b-outreach/.env (no los subas al repositorio)."
        )
    return token, chat_id


def detectar_idioma_por_pais(pais):
    pais_lower = pais.strip().lower()
    if any(place in pais_lower for place in FRENCH):
        return "fr"
    if any(place in pais_lower for place in GERMAN):
        return "de"
    if any(place in pais_lower for place in ITALIAN):
        return "it"
    if any(place in pais_lower for place in SPANISH):
        return "es"
    return "en"


def nombres_casas():
    return ", ".join(casa["nombre"] for casa in CASAS_REFERENCIA)


def linea_posicionamiento(idioma):
    plantilla = POSICIONAMIENTO.get(idioma, POSICIONAMIENTO["en"])
    return plantilla.format(
        casas=nombres_casas(),
        maestria=MAESTRA_IDIOMA.get(idioma, MAESTRA_IDIOMA["en"]),
        origen=ORIGEN_IDIOMA.get(idioma, ORIGEN_IDIOMA["en"]),
        capa=CASA["capa"],
        capote=CASA["capote"],
        tripa=TRIPA_IDIOMA.get(idioma, TRIPA_IDIOMA["en"]),
    )


def html_escape(value):
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def generar_mensaje_multilingue(nombre_local, pais, web, correo):
    idioma = detectar_idioma_por_pais(pais)
    nombre = html_escape(nombre_local)
    lugar = html_escape(pais)
    sitio = html_escape(web)
    email = html_escape(correo)

    posicion = linea_posicionamiento(idioma)

    if idioma == "fr":
        draft = (
            f"Bonjour l'équipe de {nombre_local},\n\n"
            "Nous sommes Cazador de Sueños Cigar SRL, manufacture à Santiago de los "
            "Caballeros, République dominicaine.\n\n"
            f"{posicion}\n\n"
            "Nous souhaitons vous présenter notre collection de gros et notre catalogue "
            "exclusif pour votre établissement. Découvrez notre portail B2B ici :\n"
            f"{WHOLESALE_URL}\n\n"
            "Cordialement,\n"
            "L'équipe Cazador de Sueños"
        )
        header = (
            "🔥 <b>NOUVEAU PROSPECT B2B</b>\n\n"
            f"🏢 <b>Établissement :</b> {nombre}\n"
            f"📍 <b>Lieu :</b> {lugar}\n"
            f"🌐 <b>Site web :</b> {sitio}\n"
            f"📧 <b>E-mail :</b> {email}\n\n"
            "📋 <b>Message prêt à envoyer (français) :</b>"
        )
    elif idioma == "de":
        draft = (
            f"Hallo {nombre_local} Team,\n\n"
            "wir sind Cazador de Sueños Cigar SRL, eine Manufaktur in Santiago de los "
            "Caballeros, Dominikanische Republik.\n\n"
            f"{posicion}\n\n"
            "Gern stellen wir Ihnen unsere Großhandelskollektion für Ihre Lounge oder "
            "Ihr Resort vor. Unser B2B-Portal:\n"
            f"{WHOLESALE_URL}\n\n"
            "Mit freundlichen Grüßen\n"
            "Cazador de Sueños"
        )
        header = (
            "🔥 <b>NEUER B2B-LEAD</b>\n\n"
            f"🏢 <b>Lokal:</b> {nombre}\n"
            f"📍 <b>Standort:</b> {lugar}\n"
            f"🌐 <b>Webseite:</b> {sitio}\n"
            f"📧 <b>E-Mail:</b> {email}\n\n"
            "📋 <b>Nachricht zum Senden (Deutsch):</b>"
        )
    elif idioma == "it":
        draft = (
            f"Buongiorno team di {nombre_local},\n\n"
            "siamo Cazador de Sueños Cigar SRL, una manifattura a Santiago de los "
            "Caballeros, Repubblica Dominicana.\n\n"
            f"{posicion}\n\n"
            "Vorremmo presentarvi la collezione all'ingrosso e il catalogo per il vostro "
            "locale. Il portale B2B:\n"
            f"{WHOLESALE_URL}\n\n"
            "Cordiali saluti,\n"
            "Il team Cazador de Sueños"
        )
        header = (
            "🔥 <b>NUOVO CONTATTO B2B</b>\n\n"
            f"🏢 <b>Locale:</b> {nombre}\n"
            f"📍 <b>Luogo:</b> {lugar}\n"
            f"🌐 <b>Sito:</b> {sitio}\n"
            f"📧 <b>Email:</b> {email}\n\n"
            "📋 <b>Messaggio pronto (italiano):</b>"
        )
    elif idioma == "es":
        draft = (
            f"Saludos, equipo de {nombre_local}.\n\n"
            "Somos Cazador de Sueños Cigar SRL, fábrica en Santiago de los Caballeros, "
            "República Dominicana.\n\n"
            f"{posicion}\n\n"
            "Queremos presentarles el catálogo mayorista para su establecimiento. "
            "El portal B2B está aquí:\n"
            f"{WHOLESALE_URL}\n\n"
            "Atentamente,\n"
            "Equipo de Cazador de Sueños"
        )
        header = (
            "🔥 <b>NUEVO CONTACTO B2B</b>\n\n"
            f"🏢 <b>Local:</b> {nombre}\n"
            f"📍 <b>Ubicación:</b> {lugar}\n"
            f"🌐 <b>Sitio web:</b> {sitio}\n"
            f"📧 <b>Correo:</b> {email}\n\n"
            "📋 <b>Mensaje listo para enviar (español):</b>"
        )
    else:
        draft = (
            f"Hello {nombre_local} team,\n\n"
            "we are Cazador de Sueños Cigar SRL, a factory in Santiago de los Caballeros, "
            "Dominican Republic.\n\n"
            f"{posicion}\n\n"
            "We would like to introduce our wholesale collection and catalog to your "
            "lounge or resort. Our B2B portal:\n"
            f"{WHOLESALE_URL}\n\n"
            "Best regards,\n"
            "Cazador de Sueños Team"
        )
        header = (
            "🔥 <b>NEW B2B LEAD</b>\n\n"
            f"🏢 <b>Venue:</b> {nombre}\n"
            f"📍 <b>Location:</b> {lugar}\n"
            f"🌐 <b>Website:</b> {sitio}\n"
            f"📧 <b>Email:</b> {email}\n\n"
            "📋 <b>Ready-to-send message (English):</b>"
        )

    return f"{header}\n<pre>{html_escape(draft)}</pre>", idioma


def enviar_alerta_telegram(mensaje):
    token, chat_id = telegram_credentials()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps(
        {
            "chat_id": chat_id,
            "text": mensaje,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram respondió {error.code}: {detail}") from error
    if not body.get("ok"):
        raise RuntimeError(f"Telegram rechazó el mensaje: {body}")
    return body


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    load_local_env()
    parser = argparse.ArgumentParser(
        description="Arma un borrador B2B y lo envía a tu Telegram."
    )
    parser.add_argument("--nombre", help="Nombre del local")
    parser.add_argument("--pais", help="País o territorio")
    parser.add_argument("--web", default="", help="Sitio web del local")
    parser.add_argument("--correo", default="", help="Correo del local")
    parser.add_argument(
        "--imprimir",
        action="store_true",
        help="Muestra el mensaje y no llama a Telegram",
    )
    args = parser.parse_args()

    if not args.nombre or not args.pais:
        print("Bot B2B de Cazador de Sueños listo.")
        print(f"Origen: {CASA['origen']}")
        print(f"Capa {CASA['capa']} · capote {CASA['capote']} · {CASA['maestria']}")
        print(f"Referencia de mostrador: {nombres_casas()}")
        print("Uso: python telegram_bot.py --nombre \"Lounge\" --pais \"Martinique\" --web \"https://...\" --correo \"a@b.com\"")
        return

    mensaje, idioma = generar_mensaje_multilingue(
        args.nombre, args.pais, args.web or "—", args.correo or "—"
    )
    if args.imprimir:
        print(mensaje)
        print(f"\nIdioma: {idioma}")
        return

    enviar_alerta_telegram(mensaje)
    print(f"Alerta enviada a Telegram ({idioma}).")


if __name__ == "__main__":
    main()
