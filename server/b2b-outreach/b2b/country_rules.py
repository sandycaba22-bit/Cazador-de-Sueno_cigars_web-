from __future__ import annotations

import json
import os
from datetime import date, datetime
from difflib import unified_diff
from pathlib import Path

from b2b.paths import data_file

RULES_PATH = data_file("country_rules.json")


def cargar_reglas() -> dict:
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def guardar_reglas(data: dict) -> None:
    RULES_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _semaforo(dificultad: int) -> str:
    if dificultad <= 2:
        return "VERDE"
    if dificultad == 3:
        return "AMARILLO"
    return "ROJO"


def _alerta_antiguedad(entry: dict) -> bool:
    verificado = entry.get("verificado_el")
    if not verificado:
        return entry.get("estado") != "preliminar" or entry.get("dificultad", 5) >= 4
    try:
        cuando = datetime.strptime(verificado, "%Y-%m-%d").date()
    except ValueError:
        return True
    return (date.today() - cuando).days > 90


def imprimir_tabla_reglas() -> None:
    data = cargar_reglas()
    paises = sorted(data.get("paises", []), key=lambda p: (p.get("dificultad", 5), p.get("pais", "")))
    print(f"{'Sem':<7} {'Dif':<4} {'Estado':<14} {'País':<22} Licencia (resumen)")
    print("-" * 90)
    for entry in paises:
        dif = int(entry.get("dificultad", 5))
        sem = _semaforo(dif)
        estado = entry.get("estado", "sin_verificar")
        pais = entry.get("pais", "?")
        lic = (entry.get("licencia_comprador") or "")[:42]
        marca = ""
        if estado in ("sin_verificar", "preliminar") and dif >= 4:
            marca = " [!]"
        if _alerta_antiguedad(entry):
            marca += " [REVISAR>90d]"
        print(f"{sem:<7} {dif:<4} {estado:<14} {pais:<22} {lic}{marca}")
    print("\nPrioridad inicial:", ", ".join(data.get("prioridad_inicial", [])))


ALIASES = {
    "sint maarten": "Sint Maarten",
    "st maarten": "Sint Maarten",
    "saint martin": "Saint Martin",
    "st. maarten": "Sint Maarten",
    "curaçao": "Curacao",
    "curacao": "Curacao",
    "curazao": "Curacao",
    "república dominicana": "Dominican Republic",
    "republica dominicana": "Dominican Republic",
    "usa": "United States",
    "u.s.": "United States",
    "u.s.a.": "United States",
    "u.s.a": "United States",
    "estados unidos": "United States",
    "ee.uu.": "United States",
    "eeuu": "United States",
    "canadá": "Canada",
    "canada": "Canada",
    "islas caimán": "Cayman Islands",
    "islas caiman": "Cayman Islands",
    "cayman": "Cayman Islands",
    "mauricio": "Mauritius",
    "seychelles": "Seychelles",
    "malta": "Malta",
    "chipre": "Cyprus",
    "costa de marfil": "Côte d'Ivoire",
    "cote d'ivoire": "Côte d'Ivoire",
    "ivory coast": "Côte d'Ivoire",
    "cabo verde": "Cape Verde",
    "senegal": "Senegal",
    "nigeria": "Nigeria",
    "ghana": "Ghana",
    "sudáfrica": "South Africa",
    "sudafrica": "South Africa",
    "south africa": "South Africa",
    "kenia": "Kenya",
    "kenya": "Kenya",
    "marruecos": "Morocco",
    "morocco": "Morocco",
    "angola": "Angola",
    "haiti": "Haiti",
    "haití": "Haiti",
}


def buscar_pais(nombre: str) -> dict | None:
    clave = nombre.strip().lower()
    canon = ALIASES.get(clave, nombre.strip())
    canon_l = canon.lower()
    for entry in cargar_reglas().get("paises", []):
        if entry.get("pais", "").lower() == canon_l:
            return entry
    for entry in cargar_reglas().get("paises", []):
        if entry.get("pais", "").lower() == clave:
            return entry
    return None


def _nombres_prioridad_busqueda(zona: str | None = None) -> list[str]:
    data = cargar_reglas()
    zona = (zona or os.getenv("B2B_ZONA_BUSQUEDA", "caribe") or "caribe").strip().lower()
    if zona in ("global", "todas", "all"):
        return list(data.get("prioridad_inicial", []))
    if zona in ("africa", "africa_europa", "afrika"):
        return list(data.get("prioridad_africa_europa") or [])
    caribe = data.get("prioridad_caribe")
    if caribe:
        return list(caribe)
    return list(data.get("prioridad_inicial", []))


def _incluir_en_busqueda(entry: dict) -> bool:
    if (os.getenv("B2B_OMITIR_MERCADO_LOCAL", "0") or "0").strip().lower() in (
        "0",
        "false",
        "no",
    ):
        return True
    territorio = (entry.get("territorio") or "").strip().lower()
    return territorio != "local"


def paises_prioridad_busqueda(zona: str | None = None) -> list[dict]:
    """Orden de --buscar sin --pais (default: solo islas / Caribe)."""
    out: list[dict] = []
    for nombre in _nombres_prioridad_busqueda(zona):
        entry = buscar_pais(nombre)
        if entry and _incluir_en_busqueda(entry):
            out.append(entry)
    return out


def paises_prioridad_inicial() -> list[dict]:
    """Lista completa prioridad_inicial (tests y compat)."""
    out: list[dict] = []
    for nombre in cargar_reglas().get("prioridad_inicial", []):
        entry = buscar_pais(nombre)
        if entry:
            out.append(entry)
    return out


def paises_ordenados_por_dificultad() -> list[dict]:
    data = cargar_reglas()
    prioridad = {p: i for i, p in enumerate(data.get("prioridad_inicial", []))}
    paises = list(data.get("paises", []))

    def key(entry):
        pais = entry.get("pais", "")
        return (prioridad.get(pais, 999), pais)

    return sorted(paises, key=key)


def revisar_reglas_propuesta(pais_nombre: str) -> str:
    """Propone diff humano; no escribe country_rules.json solo."""
    actual = cargar_reglas()
    entry = buscar_pais(pais_nombre)
    if entry is None:
        raise ValueError(f"País no encontrado en country_rules.json: {pais_nombre}")
    propuesto = json.loads(json.dumps(actual))
    canon = entry.get("pais", pais_nombre)
    for item in propuesto["paises"]:
        if item.get("pais", "").lower() == canon.lower():
            item["nota_revision"] = (
                f"Revisión sugerida {date.today().isoformat()}: confirmar con agente aduanal "
                f"y fuente oficial antes de pasar a verificado."
            )
            item["fuentes"] = list(item.get("fuentes") or [])
            item["fuentes"].append(
                {
                    "url": item["fuentes"][0]["url"] if item.get("fuentes") else "https://",
                    "tipo": "pendiente_oficial",
                    "consulta": date.today().isoformat(),
                    "nota": "Revisar manualmente portal aduanero oficial del país.",
                }
            )
            break
    antes = json.dumps(actual, indent=2, ensure_ascii=False) + "\n"
    despues = json.dumps(propuesto, indent=2, ensure_ascii=False) + "\n"
    diff = unified_diff(
        antes.splitlines(keepends=True),
        despues.splitlines(keepends=True),
        fromfile="country_rules.json (actual)",
        tofile="country_rules.json (propuesta)",
    )
    texto = "".join(diff)
    if not texto.strip():
        return "Sin cambios propuestos."
    return texto
