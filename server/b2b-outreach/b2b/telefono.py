from __future__ import annotations

import re

# Prefijo internacional por ISO3166-1. Los del plan norteamericano (+1) traen el código de área
# dentro del número nacional: "(242) 555-1234".
NANP = {
    "US", "CA", "PR", "VI", "BS", "JM", "BB", "KY", "TC", "TT", "SX", "DO", "AG", "LC", "VC",
    "GD", "KN", "DM", "AI", "VG", "BM", "MS",
}
PREFIJOS = {
    "AW": "297", "CW": "599", "BQ": "599", "MF": "590", "GP": "590", "BL": "590", "MQ": "596",
    "GF": "594", "HT": "509", "PA": "507", "CR": "506", "CU": "53", "MX": "52", "CO": "57",
    "MU": "230", "SC": "248", "MT": "356", "CY": "357", "NG": "234", "GH": "233", "ZA": "27",
    "KE": "254", "SN": "221", "CI": "225", "MA": "212", "CV": "238", "AO": "244", "AE": "971",
    "GB": "44", "FR": "33", "DE": "49", "ES": "34", "IT": "39", "NL": "31", "BE": "32",
    "CH": "41", "PT": "351",
}
# Países donde el 0 inicial forma parte del número (no es prefijo troncal).
CONSERVAN_CERO = {"IT"}


def _iso(pais: str) -> str:
    from b2b.osm_places import _iso_para_pais

    try:
        return _iso_para_pais(pais)
    except ValueError:
        from b2b.paises_cola import entry_por_pais

        # Los estados tienen su ISO nacional en la cola de mercados activos.
        entry = entry_por_pais(pais) or {}
        return (entry.get("iso3166") or "").strip().upper()


def internacional(pais: str, numero: str) -> str:
    """'+<prefijo><número>' a partir del formato nacional de Google; '' si no se puede asegurar."""
    numero = (numero or "").strip()
    if not numero:
        return ""
    if numero.startswith("+"):
        digitos = re.sub(r"\D", "", numero)
        return f"+{digitos}" if 8 <= len(digitos) <= 15 else ""
    digitos = re.sub(r"\D", "", numero)
    iso = _iso(pais)
    if iso in NANP:
        if len(digitos) == 11 and digitos.startswith("1"):
            return f"+{digitos}"
        return f"+1{digitos}" if len(digitos) == 10 else ""
    prefijo = PREFIJOS.get(iso)
    if not prefijo:
        return ""
    if digitos.startswith("0") and iso not in CONSERVAN_CERO:
        digitos = digitos[1:]
    total = prefijo + digitos
    return f"+{total}" if 8 <= len(total) <= 15 else ""


def _digitos(numero: str) -> str:
    return re.sub(r"\D", "", numero or "")


def _region(pais: str) -> str:
    """ISO de dos letras. Acepta 'DO' o 'Florida'."""
    region = (pais or "").strip()
    if len(region) == 2 and region.isalpha():
        return region.upper()
    return _iso(region) if region else ""


def formato_visible(numero: str, pais: str = "") -> str:
    """Formato legible. NANP queda como +1 (809) 464-5016."""
    bruto = (numero or "").strip()
    if not bruto:
        return ""
    iso = _region(pais)
    if bruto.startswith("+"):
        intl = bruto
    else:
        intl = internacional(pais, bruto) if pais and len(pais.strip()) != 2 else ""
        digitos_brutos = _digitos(bruto)
        if not intl and (iso in NANP or not iso):
            if len(digitos_brutos) == 10:
                intl = f"+1{digitos_brutos}"
            elif len(digitos_brutos) == 11 and digitos_brutos.startswith("1"):
                intl = f"+{digitos_brutos}"
        if not intl:
            intl = internacional(pais or "DO", bruto)
    digitos = _digitos(intl or bruto)
    if len(digitos) == 10 and iso in NANP:
        digitos = f"1{digitos}"
        intl = f"+{digitos}"
    if len(digitos) == 11 and digitos.startswith("1"):
        area, central, linea = digitos[1:4], digitos[4:7], digitos[7:11]
        return f"+1 ({area}) {central}-{linea}"
    if intl:
        return intl if intl.startswith("+") else f"+{digitos}"
    return bruto


def clasificar_linea(numero: str, pais: str = "") -> str:
    """'movil', 'fijo' o 'incierto'. Fijo e incierto no deben abrir WhatsApp."""
    intl = (numero or "").strip()
    if intl and not intl.startswith("+"):
        intl = internacional(pais, intl) or intl
    digitos = _digitos(intl)
    if len(digitos) < 8:
        return "incierto"
    if not intl.startswith("+"):
        intl = f"+{digitos}"
    try:
        import phonenumbers
        from phonenumbers import PhoneNumberType
    except ImportError:
        return "incierto"
    try:
        region = _iso(pais) or None
        parsed = phonenumbers.parse(intl, region)
    except Exception:
        return "incierto"
    if not phonenumbers.is_possible_number(parsed):
        return "incierto"
    tipo = phonenumbers.number_type(parsed)
    moviles = {
        PhoneNumberType.MOBILE,
        PhoneNumberType.FIXED_LINE_OR_MOBILE,
        PhoneNumberType.VOIP,
        PhoneNumberType.PERSONAL_NUMBER,
    }
    fijos = {
        PhoneNumberType.FIXED_LINE,
        PhoneNumberType.TOLL_FREE,
        PhoneNumberType.PREMIUM_RATE,
        PhoneNumberType.SHARED_COST,
        PhoneNumberType.UAN,
        PhoneNumberType.VOICEMAIL,
        PhoneNumberType.PAGER,
    }
    if tipo in moviles and phonenumbers.is_valid_number(parsed):
        return "movil"
    if tipo in fijos:
        return "fijo"
    return "incierto"


def apto_whatsapp(lead: dict) -> bool:
    """WhatsApp publicado, o teléfono que phonenumbers marca como móvil."""
    publicado = _digitos(lead.get("whatsapp") or "")
    if len(publicado) >= 8:
        return True
    pais = (lead.get("pais") or lead.get("estado") or "").strip()
    for campo in ("telefono_internacional", "telefono"):
        numero = (lead.get(campo) or "").strip()
        if numero and clasificar_linea(numero, pais) == "movil":
            return True
    return False
