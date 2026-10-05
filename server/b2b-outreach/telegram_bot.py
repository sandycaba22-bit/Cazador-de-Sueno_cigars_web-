# Bot B2B de Cazador de Sueños Cigar SRL
#
# Recibe un prospecto que tú ya tienes (local, país, web, correo), arma el
# borrador en su idioma y te lo deja en tu Telegram. No busca locales, no
# rastrea webs y no escribe al prospecto: el cierre lo haces tú.
#
# Dependencias en el servidor: python3, python3-pip, y luego
#   pip3 install -r /var/www/html/server/b2b-outreach/requirements.txt
# (python-dotenv y requests). El detalle de systemd y PM2 está en README.md.
#
# Prueba de humo, sin llamar a Telegram:
#   python3 telegram_bot.py --nombre "Le Cercle du Cigare" --pais "Martinique" \
#     --web "https://lecercle.mq" --correo "contacto@lecercle.mq" --imprimir

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

WHOLESALE_URL = "https://www.cazadordesuenocigars.com/wholesale.html"
VITOLAS = "El Sultán y Ligero 007"
VITOLA_PAR = {
    "es": "El Sultán y Ligero 007",
    "en": "El Sultán and Ligero 007",
    "fr": "El Sultán et Ligero 007",
    "de": "El Sultán und Ligero 007",
    "it": "El Sultán e Ligero 007",
}
HERE = Path(__file__).resolve().parent
TELEGRAM_ATTEMPTS = 3
TELEGRAM_TIMEOUT = 20
RETRY_STATUSES = {429, 500, 502, 503, 504}

# Referencia de mostrador. Sitúa la casa. No afirma que un puro de
# Cazador de Sueños sea el mismo blend ni que supere a esas marcas.
CASAS_REFERENCIA = (
    "Davidoff",
    "Arturo Fuente",
    "Plasencia",
    "La Aurora",
    "Cohiba",
)

CASA = {
    "capa": "San Andrés",
    "capote": "Olor Dominicano",
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
    "en": "the Cibao mountain range and premium selections",
    "fr": "la cordillère du Cibao et des sélections premium",
    "de": "der Cibao-Kordillere und Premium-Selektionen",
    "it": "la cordigliera del Cibao e selezioni premium",
}

POSICIONAMIENTO = {
    "es": (
        "En el mostrador donde el cliente ya reconoce a {casas}, nuestra respuesta "
        "es propia: puros {maestria} en {origen}, con capa {capa}, capote {capote} "
        "y tripa de {tripa}."
    ),
    "en": (
        "On the shelf where guests already know {casas}, our answer is our own: "
        "cigars {maestria} in {origen}, with a {capa} wrapper, {capote} binder "
        "and filler from {tripa}."
    ),
    "fr": (
        "Sur le linéaire où le client reconnaît déjà {casas}, notre réponse est "
        "la nôtre : cigares {maestria} à {origen}, cape {capa}, sous-cape {capote} "
        "et tripe de {tripa}."
    ),
    "de": (
        "Im Humidor, in dem Gäste {casas} bereits kennen, ist unsere Antwort eine "
        "eigene: Zigarren {maestria} in {origen}, mit Deckblatt {capa}, Umblatt "
        "{capote} und Einlage aus {tripa}."
    ),
    "it": (
        "Sul banco dove l'ospite riconosce già {casas}, la nostra risposta è "
        "nostra: sigari {maestria} a {origen}, con capa {capa}, sottocapa {capote} "
        "e ripieno di {tripa}."
    ),
}

VITOLA_LINEA = {
    "es": f"Para abrir la conversación proponemos dos vitolas de la casa: {VITOLA_PAR['es']}.",
    "en": f"To open the conversation we suggest two house vitolas: {VITOLA_PAR['en']}.",
    "fr": f"Pour ouvrir l'échange, nous proposons deux vitolas de la maison : {VITOLA_PAR['fr']}.",
    "de": f"Für den Einstieg schlagen wir zwei Vitolas des Hauses vor: {VITOLA_PAR['de']}.",
    "it": f"Per aprire il dialogo proponiamo due vitole della casa: {VITOLA_PAR['it']}.",
}

NOMBRE_IDIOMA = {
    "es": "español",
    "en": "inglés",
    "fr": "francés",
    "de": "alemán",
    "it": "italiano",
}

# Islas y territorios del Caribe. La prioridad es comercial (ruta corta
# desde Santiago), no un dictamen de aduana. La importación la confirma
# el comprador en su territorio.
CARIBE = (
    "martinique",
    "guadeloupe",
    "guyane",
    "haiti",
    "haïti",
    "saint-martin",
    "st. martin",
    "saint martin",
    "sint maarten",
    "st. maarten",
    "saint maarten",
    "st. barth",
    "saint bart",
    "saint-barth",
    "aruba",
    "curacao",
    "curaçao",
    "bonaire",
    "saba",
    "statia",
    "eustatius",
    "bahamas",
    "jamaica",
    "barbados",
    "trinidad",
    "tobago",
    "cayman",
    "antigua",
    "barbuda",
    "saint lucia",
    "st. lucia",
    "grenada",
    "dominica",
    "saint kitts",
    "st. kitts",
    "nevis",
    "turks",
    "caicos",
    "anguilla",
    "montserrat",
    "puerto rico",
    "virgin",
    "dominicana",
    "dominican",
)

FRENCH = (
    "martinique",
    "guadeloupe",
    "guyane",
    "france",
    "st. barth",
    "saint bart",
    "saint-barth",
    "saint-martin",
    "st. martin",
    "saint martin",
    "haiti",
    "haïti",
)
GERMAN = (
    "germany",
    "austria",
    "switzerland",
    "deutschland",
    "österreich",
    "schweiz",
    "suisse",
)
ITALIAN = ("italy", "italia")
SPANISH = (
    "dominicana",
    "dominican",
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

PLACEHOLDERS = {
    "",
    "TU_TOKEN_DE_TELEGRAM",
    "TU_CHAT_ID",
    "AQUÍ_VAS_A_PONER_TU_NUMERO_DE_CHAT_ID",
    "AQUI_VAS_A_PONER_TU_NUMERO_DE_CHAT_ID",
}
MD_V2_SPECIAL = set(r"_*[]()~`>#+-=|{}.!")
TOKEN_IN_TEXT = re.compile(r"\d{6,}:[A-Za-z0-9_-]{20,}")


class TelegramTransientError(RuntimeError):
    pass


class TelegramFormatError(RuntimeError):
    pass


def load_local_env():
    """Lee el .env junto al script. No pisa variables que ya vengan del servicio."""
    env_path = HERE / ".env"
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)
        return
    except ImportError:
        pass
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
    if token in PLACEHOLDERS or chat_id in PLACEHOLDERS:
        raise RuntimeError(
            "Faltan TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID. "
            "En local van en server/b2b-outreach/.env. "
            "En el servidor van en /etc/cazador-de-suenos/b2b-outreach.env. "
            "No los subas al repositorio."
        )
    if ":" not in token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN no tiene el formato que entrega BotFather.")
    if not re.fullmatch(r"-?\d+", chat_id):
        raise RuntimeError("TELEGRAM_CHAT_ID tiene que ser el número de tu chat.")
    return token, chat_id


def _contains_any(text, places):
    return any(place in text for place in places)


def detectar_idioma_por_pais(pais):
    pais_lower = pais.strip().lower()
    if _contains_any(pais_lower, FRENCH):
        return "fr"
    if _contains_any(pais_lower, GERMAN):
        return "de"
    if _contains_any(pais_lower, ITALIAN):
        return "it"
    if _contains_any(pais_lower, SPANISH):
        return "es"
    return "en"


def clasificar_mercado(pais):
    """Prioriza el Caribe. No descarta el resto: lo marca como estándar."""
    if _contains_any(pais.strip().lower(), CARIBE):
        return {
            "zona": "caribe",
            "prioridad": "alta",
            "orden": 0,
            "etiqueta": (
                "Alta · Caribe, ruta corta desde Santiago. "
                "La importación la confirma el comprador."
            ),
        }
    return {
        "zona": "internacional",
        "prioridad": "estandar",
        "orden": 1,
        "etiqueta": (
            "Estándar · mercado internacional. "
            "El comprador confirma licencia e impuestos de su país."
        ),
    }


def nombres_casas():
    return ", ".join(CASAS_REFERENCIA)


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


def md_escape(value):
    return "".join("\\" + ch if ch in MD_V2_SPECIAL else ch for ch in str(value))


def code_escape(value):
    return str(value).replace("\\", "\\\\").replace("`", "\\`").replace("```", "'''")


def borrador_prospecto(idioma, nombre_local):
    posicion = linea_posicionamiento(idioma)
    vitola = VITOLA_LINEA.get(idioma, VITOLA_LINEA["en"])
    origen = ORIGEN_IDIOMA.get(idioma, ORIGEN_IDIOMA["en"])
    if idioma == "fr":
        return (
            f"Bonjour l'équipe de {nombre_local},\n\n"
            "Nous sommes Cazador de Sueños Cigar SRL, manufacture à "
            f"{origen}.\n\n"
            f"{posicion}\n\n"
            f"{vitola}\n\n"
            "Nous souhaitons vous présenter notre collection de gros et notre "
            "catalogue pour votre établissement. Le portail B2B :\n"
            f"{WHOLESALE_URL}\n\n"
            "Cordialement,\n"
            "L'équipe Cazador de Sueños"
        )
    if idioma == "de":
        return (
            f"Hallo {nombre_local} Team,\n\n"
            "wir sind Cazador de Sueños Cigar SRL, eine Manufaktur in "
            f"{origen}.\n\n"
            f"{posicion}\n\n"
            f"{vitola}\n\n"
            "Gern stellen wir Ihnen unsere Großhandelskollektion für Ihre Lounge "
            "oder Ihr Geschäft vor. Unser B2B-Portal:\n"
            f"{WHOLESALE_URL}\n\n"
            "Mit freundlichen Grüßen\n"
            "Cazador de Sueños"
        )
    if idioma == "it":
        return (
            f"Buongiorno team di {nombre_local},\n\n"
            "siamo Cazador de Sueños Cigar SRL, una manifattura a "
            f"{origen}.\n\n"
            f"{posicion}\n\n"
            f"{vitola}\n\n"
            "Vorremmo presentarvi la collezione all'ingrosso e il catalogo per "
            "il vostro locale. Il portale B2B:\n"
            f"{WHOLESALE_URL}\n\n"
            "Cordiali saluti,\n"
            "Il team Cazador de Sueños"
        )
    if idioma == "es":
        return (
            f"Saludos, equipo de {nombre_local}.\n\n"
            "Somos Cazador de Sueños Cigar SRL, fábrica en "
            f"{origen}.\n\n"
            f"{posicion}\n\n"
            f"{vitola}\n\n"
            "Queremos presentarles el catálogo mayorista para su establecimiento. "
            "El portal B2B está aquí:\n"
            f"{WHOLESALE_URL}\n\n"
            "Atentamente,\n"
            "Equipo de Cazador de Sueños"
        )
    return (
        f"Hello {nombre_local} team,\n\n"
        "we are Cazador de Sueños Cigar SRL, a factory in "
        f"{origen}.\n\n"
        f"{posicion}\n\n"
        f"{vitola}\n\n"
        "We would like to introduce our wholesale collection and catalog to your "
        "lounge or shop. Our B2B portal:\n"
        f"{WHOLESALE_URL}\n\n"
        "Best regards,\n"
        "Cazador de Sueños Team"
    )


def generar_mensaje_multilingue(nombre_local, pais, web, correo):
    idioma = detectar_idioma_por_pais(pais)
    mercado = clasificar_mercado(pais)
    draft = borrador_prospecto(idioma, nombre_local.strip())
    texto = (
        "Cazador de Sueños · prospecto B2B\n"
        f"Prioridad: {mercado['etiqueta']}\n"
        f"Vitolas para abrir: {VITOLAS}\n"
        f"Local: {nombre_local.strip()}\n"
        f"País: {pais.strip()}\n"
        f"Web: {web.strip()}\n"
        f"Correo: {correo.strip()}\n"
        f"Idioma del borrador: {NOMBRE_IDIOMA[idioma]}\n"
        "Estado: aviso interno. El mensaje al prospecto lo envías tú.\n\n"
        "Borrador listo:\n"
        f"{draft}"
    )
    markdown = (
        "*Cazador de Sueños · prospecto B2B*\n"
        f"*Prioridad:* {md_escape(mercado['etiqueta'])}\n"
        f"*Vitolas para abrir:* {md_escape(VITOLAS)}\n"
        f"*Local:* {md_escape(nombre_local.strip())}\n"
        f"*País:* {md_escape(pais.strip())}\n"
        f"*Web:* {md_escape(web.strip())}\n"
        f"*Correo:* {md_escape(correo.strip())}\n"
        f"*Idioma del borrador:* {md_escape(NOMBRE_IDIOMA[idioma])}\n"
        "*Estado:* aviso interno\\. El mensaje al prospecto lo envías tú\\.\n\n"
        "*Borrador listo:*\n"
        f"```\n{code_escape(draft)}\n```"
    )
    return {
        "markdown": markdown,
        "texto": texto,
        "idioma": idioma,
        "mercado": mercado,
    }


def sanitizar_error(exc, token=""):
    text = str(exc)
    if token:
        text = text.replace(token, "[token]")
    text = TOKEN_IN_TEXT.sub("[token]", text)
    return text[:500]


def _esperar(intento):
    time.sleep(min(8, 2 ** (intento - 1)))


def _post_urllib(url, payload, token):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TELEGRAM_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        limpio = sanitizar_error(detail, token)
        if error.code in RETRY_STATUSES:
            raise TelegramTransientError(f"Telegram respondió {error.code}: {limpio}") from error
        if error.code == 400:
            raise TelegramFormatError(f"Telegram rechazó el formato: {limpio}") from error
        raise RuntimeError(f"Telegram respondió {error.code}: {limpio}") from error
    except urllib.error.URLError as error:
        raise TelegramTransientError(sanitizar_error(error.reason, token)) from error


def _post_requests(url, payload, token):
    import requests

    try:
        response = requests.post(url, json=payload, timeout=TELEGRAM_TIMEOUT)
    except requests.RequestException as error:
        raise TelegramTransientError(sanitizar_error(error, token)) from error
    if response.status_code in RETRY_STATUSES:
        raise TelegramTransientError(
            f"Telegram respondió {response.status_code}: {sanitizar_error(response.text, token)}"
        )
    if response.status_code == 400:
        raise TelegramFormatError(
            f"Telegram rechazó el formato: {sanitizar_error(response.text, token)}"
        )
    if response.status_code >= 400:
        raise RuntimeError(
            f"Telegram respondió {response.status_code}: {sanitizar_error(response.text, token)}"
        )
    return response.json()


def _enviar_payload(payload):
    token, _chat_id = telegram_credentials()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    ultimo = "Telegram no respondió."
    for intento in range(1, TELEGRAM_ATTEMPTS + 1):
        try:
            try:
                import requests  # noqa: F401

                body = _post_requests(url, payload, token)
            except ImportError:
                body = _post_urllib(url, payload, token)
        except TelegramTransientError as error:
            ultimo = sanitizar_error(error, token)
            if intento == TELEGRAM_ATTEMPTS:
                break
            _esperar(intento)
            continue
        if not isinstance(body, dict) or not body.get("ok"):
            raise RuntimeError(f"Telegram rechazó el mensaje: {sanitizar_error(body, token)}")
        return body
    raise TelegramTransientError(ultimo)


def enviar_alerta_telegram(paquete):
    token, chat_id = telegram_credentials()
    base = {
        "chat_id": chat_id,
        "disable_web_page_preview": True,
    }
    try:
        return _enviar_payload({**base, "text": paquete["markdown"], "parse_mode": "MarkdownV2"})
    except TelegramFormatError:
        return _enviar_payload({**base, "text": paquete["texto"]})


def validar_prospecto(nombre, pais, web, correo):
    nombre = (nombre or "").strip()
    pais = (pais or "").strip()
    web = (web or "").strip()
    correo = (correo or "").strip()
    errores = []
    if not nombre:
        errores.append("--nombre")
    if not pais:
        errores.append("--pais")
    if not web.startswith(("http://", "https://")):
        errores.append("--web (tiene que empezar por http:// o https://)")
    if "@" not in correo or correo.startswith("@") or correo.endswith("@"):
        errores.append("--correo")
    if errores:
        raise ValueError("Revisa estos datos: " + ", ".join(errores))
    return nombre, pais, web, correo


def _dirs(queue_dir):
    inbox = queue_dir / "inbox"
    sent = queue_dir / "sent"
    failed = queue_dir / "failed"
    for carpeta in (inbox, sent, failed):
        carpeta.mkdir(parents=True, exist_ok=True)
    return inbox, sent, failed


def _liberar_bloqueos_viejos(inbox):
    ahora = time.time()
    for lock in inbox.glob("*.lock"):
        try:
            if ahora - lock.stat().st_mtime > 120:
                lock.unlink()
        except OSError:
            continue


def _reclamar(path):
    lock = path.with_suffix(path.suffix + ".lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return None
    os.close(fd)
    return lock


def _leer_lead(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("El archivo tiene que ser un objeto JSON.")
    return validar_prospecto(
        data.get("nombre"),
        data.get("pais"),
        data.get("web"),
        data.get("correo"),
    )


def _archivar(path, destino, nota=None):
    destino.mkdir(parents=True, exist_ok=True)
    final = destino / f"{time.strftime('%Y%m%d-%H%M%S')}-{path.name}"
    path.replace(final)
    if nota:
        final.with_suffix(final.suffix + ".error.txt").write_text(nota, encoding="utf-8")
    return final


def resolver_cola(explicita=""):
    if explicita:
        return Path(explicita).expanduser()
    configured = os.getenv("B2B_QUEUE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    if str(HERE).replace("\\", "/").startswith("/var/www/"):
        return Path("/var/lib/cazador-de-suenos/b2b-outreach")
    return HERE / "cola"


def segundos_de_espera():
    try:
        return max(5, int(os.getenv("B2B_POLL_SECONDS", "15") or "15"))
    except ValueError:
        return 15


def procesar_archivo(path, sent, failed, imprimir=False):
    lock = _reclamar(path)
    if lock is None:
        return None
    try:
        nombre, pais, web, correo = _leer_lead(path)
        paquete = generar_mensaje_multilingue(nombre, pais, web, correo)
        if imprimir:
            print(paquete["markdown"])
            print(f"\nIdioma: {paquete['idioma']}")
            print(f"Prioridad: {paquete['mercado']['prioridad']}")
        else:
            enviar_alerta_telegram(paquete)
            print(
                f"Alerta enviada ({paquete['idioma']}, {paquete['mercado']['prioridad']}): {path.name}"
            )
        _archivar(path, sent)
        return paquete
    except Exception as error:
        nota = sanitizar_error(error)
        print(f"No se pudo procesar {path.name}: {nota}", file=sys.stderr)
        if path.exists():
            _archivar(path, failed, nota)
        return None
    finally:
        try:
            lock.unlink()
        except OSError:
            pass


def _orden_inbox(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        pais = data.get("pais", "") if isinstance(data, dict) else ""
        return (clasificar_mercado(str(pais))["orden"], path.name)
    except (OSError, json.JSONDecodeError, TypeError):
        return (1, path.name)


def pasar_cola(queue_dir, imprimir=False):
    inbox, sent, failed = _dirs(queue_dir)
    _liberar_bloqueos_viejos(inbox)
    archivos = sorted(
        (path for path in inbox.glob("*.json") if path.is_file()),
        key=_orden_inbox,
    )
    hechos = 0
    for path in archivos:
        if procesar_archivo(path, sent, failed, imprimir=imprimir) is not None:
            hechos += 1
    return hechos


def vigilar(queue_dir, imprimir=False, una_pasada=False):
    intervalo = segundos_de_espera()
    while True:
        pasar_cola(queue_dir, imprimir=imprimir)
        if una_pasada:
            return
        time.sleep(intervalo)


def construir_parser():
    parser = argparse.ArgumentParser(
        description="Arma un borrador B2B y lo envía a tu Telegram. No contacta al prospecto."
    )
    parser.add_argument("--nombre", help="Nombre del local, lounge o distribuidor")
    parser.add_argument("--pais", help="País o territorio")
    parser.add_argument("--web", help="Sitio web, con http:// o https://")
    parser.add_argument("--correo", help="Correo del prospecto")
    parser.add_argument(
        "--imprimir",
        action="store_true",
        help="Muestra el mensaje y no llama a Telegram",
    )
    parser.add_argument(
        "--vigilar",
        action="store_true",
        help="Vigila la cola inbox/*.json y avisa por cada prospecto",
    )
    parser.add_argument(
        "--una-pasada",
        action="store_true",
        help="Con --vigilar, procesa lo que haya y termina",
    )
    parser.add_argument(
        "--cola",
        default="",
        help="Directorio de la cola. Por defecto B2B_QUEUE_DIR o server/b2b-outreach/cola",
    )
    return parser


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    load_local_env()
    parser = construir_parser()
    args = parser.parse_args(argv)

    if args.vigilar:
        cola = resolver_cola(args.cola)
        vigilar(cola, imprimir=args.imprimir, una_pasada=args.una_pasada)
        return 0

    try:
        nombre, pais, web, correo = validar_prospecto(
            args.nombre, args.pais, args.web, args.correo
        )
    except ValueError as error:
        parser.error(str(error))

    paquete = generar_mensaje_multilingue(nombre, pais, web, correo)
    if args.imprimir:
        print(paquete["markdown"])
        print(f"\nIdioma: {paquete['idioma']}")
        print(f"Prioridad: {paquete['mercado']['prioridad']}")
        print(f"Zona: {paquete['mercado']['zona']}")
        return 0

    enviar_alerta_telegram(paquete)
    print(f"Alerta enviada a Telegram ({paquete['idioma']}, {paquete['mercado']['prioridad']}).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, TelegramTransientError) as error:
        print(sanitizar_error(error), file=sys.stderr)
        raise SystemExit(1)
