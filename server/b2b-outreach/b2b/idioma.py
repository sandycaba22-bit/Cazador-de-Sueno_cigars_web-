from __future__ import annotations

from b2b.country_rules import buscar_pais

PAPIAMENTO_PAISES = {"aruba", "curacao", "curaçao"}
IDIOMAS_BORRADOR = frozenset({"es", "en", "fr", "pt", "nl", "de", "it"})


def idioma_para_lead(
    pais: str,
    *,
    idioma_web: str = "",
    preferido: str = "",
) -> str:
    """Prioridad: preferido explícito → idioma detectado en la web → reglas por país."""
    pref = (preferido or "").strip().lower()
    if pref in IDIOMAS_BORRADOR:
        return pref
    web = (idioma_web or "").strip().lower().split("-")[0]
    if web in IDIOMAS_BORRADOR:
        return web
    return idioma_para_pais(pais, preferido)


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
    if "pt" in idiomas:
        return "pt"
    if "fr" in idiomas:
        return "fr"
    if "nl" in idiomas and any(
        x in pais_l for x in ("sint maarten", "saint martin", "aruba", "curacao")
    ):
        return "nl"
    if "fr" in idiomas:
        return "fr"
    if "es" in idiomas:
        return "es"
    return idiomas[0] if idiomas else "en"
