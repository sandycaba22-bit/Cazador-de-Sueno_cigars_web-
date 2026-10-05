from __future__ import annotations

from b2b.country_rules import buscar_pais

# Papiamento: solo bajo revisión explícita (no auto en producción).
PAPIAMENTO_PAISES = {"aruba", "curacao", "curaçao"}


def idioma_para_pais(pais: str, preferido: str = "") -> str:
    entry = buscar_pais(pais)
    idiomas = list((entry or {}).get("idiomas") or ["en"])
    pref = (preferido or "").strip().lower()
    if pref in idiomas:
        return pref
    if pref == "pap" and pais.strip().lower() in PAPIAMENTO_PAISES:
        return "pap"
    pais_l = pais.strip().lower()
    if pais_l in PAPIAMENTO_PAISES:
        if "en" in idiomas:
            return "en"
        if "es" in idiomas:
            return "es"
    if "fr" in idiomas and pais_l in {"martinique", "guadeloupe", "french guiana"}:
        return "fr"
    if "nl" in idiomas and any(x in pais_l for x in ("sint maarten", "saint martin", "aruba", "curacao")):
        return "nl"
    return idiomas[0] if idiomas else "en"
