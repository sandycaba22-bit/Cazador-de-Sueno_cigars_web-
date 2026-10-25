"""Clasifica correos de negocio. No envía nada."""
from __future__ import annotations

import re

from b2b.website import _dominio_base

_EMAIL_RE = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$", re.I)
_GRATIS = {
    "gmail.com",
    "googlemail.com",
    "hotmail.com",
    "outlook.com",
    "live.com",
    "msn.com",
    "yahoo.com",
    "yahoo.es",
    "yahoo.co.uk",
    "icloud.com",
    "me.com",
    "aol.com",
    "proton.me",
    "protonmail.com",
    "gmx.com",
    "gmx.de",
    "mail.com",
}
_ROLES = {
    "info",
    "contact",
    "contacto",
    "sales",
    "ventas",
    "wholesale",
    "purchasing",
    "compras",
    "import",
    "imports",
    "importer",
    "procurement",
    "einkauf",
    "achats",
    "buyer",
    "commercial",
    "b2b",
    "hello",
    "shop",
}


def clasificar_correo(email: str, web: str = "") -> str:
    """corporativo, corporativo_personal, gratuito o invalido."""
    texto = (email or "").strip().lower()
    if not _EMAIL_RE.match(texto):
        return "invalido"
    local, _, dominio = texto.partition("@")
    if dominio in _GRATIS:
        return "gratuito"
    base = _dominio_base(web) if (web or "").strip() else ""
    if base and dominio != base and not dominio.endswith("." + base):
        return "invalido"
    buzon = local.split("+")[0]
    if buzon in _ROLES:
        return "corporativo"
    return "corporativo_personal"


def correo_utilizable(email: str, web: str = "") -> bool:
    return clasificar_correo(email, web) in {"corporativo", "corporativo_personal"}
