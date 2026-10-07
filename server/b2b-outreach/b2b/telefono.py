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
        return ""


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
