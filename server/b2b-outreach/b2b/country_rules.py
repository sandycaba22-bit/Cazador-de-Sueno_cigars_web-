from __future__ import annotations

import json
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
    "república dominicana": "Dominican Republic",
    "republica dominicana": "Dominican Republic",
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


def paises_ordenados_por_dificultad() -> list[dict]:
    data = cargar_reglas()
    prioridad = {p: i for i, p in enumerate(data.get("prioridad_inicial", []))}
    paises = list(data.get("paises", []))

    def key(entry):
        pais = entry.get("pais", "")
        return (entry.get("dificultad", 5), prioridad.get(pais, 999), pais)

    return sorted(paises, key=key)


def revisar_reglas_propuesta(pais_nombre: str) -> str:
    """Propone diff humano; no escribe country_rules.json solo."""
    actual = cargar_reglas()
    entry = buscar_pais(pais_nombre)
    if entry is None:
        raise ValueError(f"País no encontrado en country_rules.json: {pais_nombre}")
    propuesto = json.loads(json.dumps(actual))
    for item in propuesto["paises"]:
        if item.get("pais", "").lower() == pais_nombre.strip().lower():
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
