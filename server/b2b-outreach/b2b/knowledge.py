from __future__ import annotations

import re
from pathlib import Path

from b2b.paths import KNOWLEDGE

SOURCE_RE = re.compile(
    r"\*\*Fuente:\*\*\s*(https?://[^\s—]+)\s*—\s*consulta\s*(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)
FUENTE_EN_BLOQUE = re.compile(
    r"\*\*Fuente:\*\*\s*(https?://[^\s—]+)\s*—\s*consulta\s*(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)


def _leer(nombre: str) -> str:
    path = KNOWLEDGE / nombre
    if not path.is_file():
        raise FileNotFoundError(f"No existe {path}")
    return path.read_text(encoding="utf-8")


def validar_fuentes_mercado(texto: str) -> list[str]:
    """Cada bloque con afirmación comercial debe citar Fuente + fecha, o decir sin verificar."""
    errores: list[str] = []
    lineas = texto.splitlines()
    for i, linea in enumerate(lineas, start=1):
        if linea.strip().startswith("- **Posicionamiento") or linea.strip().startswith("- **Canales"):
            ventana = "\n".join(lineas[i - 1 : i + 4])
            if "sin verificar" not in ventana.lower() and not FUENTE_EN_BLOQUE.search(ventana):
                errores.append(f"Línea {i}: falta Fuente + fecha o marca 'sin verificar'")
    if "**Fuente:**" in texto and not SOURCE_RE.search(texto):
        errores.append("Hay menciones a Fuente sin el formato URL + fecha esperado.")
    return errores


def entrenar() -> Path:
    marca = _leer("marca_cazador_de_sueno.md")
    mercado = _leer("mercado_marcas_referencia.md")
    errores = validar_fuentes_mercado(mercado)
    if errores:
        raise RuntimeError(
            "Entrenamiento detenido. Corrige mercado_marcas_referencia.md:\n- "
            + "\n- ".join(errores)
        )
    resumen = KNOWLEDGE / "resumen_entrenamiento.md"
    cuerpo = f"""# Resumen de entrenamiento B2B (generado)

## Marca (extracto operativo)

- Fábrica en Santiago de los Caballeros, RD; portal mayorista sin precios en línea.
- Catálogo mayorista: **seis vitolas** (datos en `catalogo/build_wholesale_catalog.py`); punta de lanza **El Sultán** y **Ligero 007**, luego Emperador, Exquisito, Puro Habano y El Rango.
- Portal y PDF sin precios en línea.

## Ángulos por cliente (aprendizaje de canal premium)

| Tipo | Enfoque del borrador |
|------|----------------------|
| Distribuidor | exclusividad territorial, mínimos, muestras, POS, documentación—lo que pide un importador serio a una línea nueva |
| Tienda | línea completa (6 vitolas), rotación estable, experiencia consistente |
| Lounge | perfiles de fortaleza, recomendación en mesa, origen dominicano artesanal |
| Hotel / resort | selección compacta premium para humidor y huéspedes |
| Duty free | mix y volúmenes vía importador local |

## Marcas de referencia (tono, no comparación)

Usar solo para situar el estante: La Aurora, Davidoff, Arturo Fuente, Plasencia. No afirmar superioridad ni mismo blend.

## Reglas de cumplimiento en borradores

- Sin precios.
- Sin promesas aduaneras ni FDA.
- Línea de baja en idioma local.
- Solo correos genéricos publicados en la web del negocio.

---
Generado desde knowledge/*.md. No editar a mano; ejecutar `--entrenar` de nuevo.
"""
    resumen.write_text(cuerpo, encoding="utf-8")
    return resumen
