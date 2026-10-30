"""Cola de exportación, plantillas e registro manual. No envía mensajes."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from b2b.correo_corporativo import clasificar_correo
from b2b.idioma import idioma_para_pais
from b2b.mercados_exportacion import cargar_mercados, consultas_exportacion, es_canada
from b2b.redactor import PROHIBIDO_RE, borrador_correo, borrador_corto
from b2b import registro_control as registro


FASE_1 = [
    "Puerto Rico", "US Virgin Islands", "Bahamas", "Cayman Islands",
    "Turks and Caicos Islands", "Sint Maarten", "Aruba", "Curacao",
    "Barbados", "Saint Barthelemy",
]
FASE_2 = [
    "Spain", "Germany", "Switzerland", "United Kingdom",
    "United Arab Emirates", "Hong Kong", "Macao", "Panama",
]
IDIOMAS = {
    "Puerto Rico": "es", "US Virgin Islands": "en", "Bahamas": "en",
    "Cayman Islands": "en", "Turks and Caicos Islands": "en", "Sint Maarten": "en",
    "Aruba": "en", "Curacao": "en", "Barbados": "en", "Saint Barthelemy": "fr",
    "Spain": "es", "Germany": "de", "Switzerland": "de", "United Kingdom": "en",
    "United Arab Emirates": "en", "Hong Kong": "zh", "Macao": "zh", "Panama": "es",
}


class TestColaExportacion(unittest.TestCase):
    def test_fases_idiomas_y_sin_canada(self):
        mercados = cargar_mercados()
        nombres = [m["pais"] for m in mercados]
        self.assertEqual(nombres, FASE_1 + FASE_2)
        self.assertTrue(all(es_canada(nombre) is False for nombre in nombres))
        self.assertTrue(es_canada("Canada") and es_canada("Canadá") and es_canada("", "CA"))
        for row in mercados:
            self.assertEqual(row["idioma"], IDIOMAS[row["pais"]])
            self.assertEqual(idioma_para_pais(row["pais"]), row["idioma"])
        self.assertEqual(idioma_para_pais("St. Barths"), "fr")
        self.assertEqual(idioma_para_pais("Dubái"), "en")
        self.assertEqual(idioma_para_pais("Alemania"), "de")
        self.assertEqual(idioma_para_pais("Florida"), "en")
        self.assertEqual(idioma_para_pais("Saint Martin"), "fr")
        self.assertNotIn("Canada", nombres)
        self.assertNotIn("Singapore", nombres)

    def test_nivel_1_antes_que_tiendas(self):
        consultas = consultas_exportacion("Puerto Rico")
        self.assertEqual(len(consultas), 14)
        tipos = [tipo for _, tipo, _ in consultas]
        corte = tipos.index("tienda")
        self.assertGreater(corte, 0)
        self.assertTrue(all(tipo in {"distribuidor", "duty_free"} for tipo in tipos[:corte]))
        self.assertIn("cigar distributor in San Juan, Puerto Rico", consultas[0][2])
        self.assertEqual(consultas_exportacion("Canada"), [])


class TestPlantillas(unittest.TestCase):
    def test_firma_yaniris_y_aviso_de_edad(self):
        esperados = {
            "es": "mayores de edad",
            "en": "licensed businesses",
            "fr": "titulaires d'une licence",
            "de": "Zigarren-Großhandel",
            "zh": "僅限成年人",
        }
        for idioma, marca in esperados.items():
            corto = borrador_corto("Casa", idioma, "distribuidor")
            correo = borrador_correo("Casa", idioma, "distribuidor")
            for texto in (corto, correo):
                self.assertIn("Yaniris Agustina Ureña", texto)
                self.assertNotRegex(texto, PROHIBIDO_RE)
            self.assertNotIn("STOP", corto)
            self.assertIn(marca, corto)
            self.assertIn("BAJA" if idioma == "es" else "STOP", correo)
            for ajena in ("Davidoff", "Arturo Fuente", "Plasencia", "La Aurora", "Cohiba"):
                self.assertNotIn(ajena, correo)

    def test_correo_ingles_conserva_el_cierre(self):
        correo = borrador_correo("Cigar House", "en", "tienda")
        self.assertIn("reply STOP", correo)
        self.assertIn("free sample", correo.lower())
        self.assertIn("your cigar shop", borrador_corto("Cigar House", "en", "tienda"))


class TestCorreoCorporativo(unittest.TestCase):
    def test_clasificacion(self):
        self.assertEqual(clasificar_correo("info@shop.com", "https://shop.com"), "corporativo")
        self.assertEqual(clasificar_correo("purchasing@shop.com", "https://www.shop.com"), "corporativo")
        self.assertEqual(clasificar_correo("john.doe@shop.com", "https://shop.com"), "corporativo_personal")
        self.assertEqual(clasificar_correo("buyer@gmail.com", "https://shop.com"), "gratuito")
        self.assertEqual(clasificar_correo("info@otro.com", "https://shop.com"), "invalido")
        self.assertEqual(clasificar_correo("no-es-correo", "https://shop.com"), "invalido")


class TestRegistroManual(unittest.TestCase):
    def setUp(self):
        temporal = Path(self.id().replace(".", "_"))
        carpeta = Path(__file__).resolve().parent / "_tmp_registro"
        carpeta.mkdir(exist_ok=True)
        self.path = carpeta / f"{temporal.name}.json"
        if self.path.exists():
            self.path.unlink()
        self.parche = patch.object(registro, "REGISTRO_PATH", self.path)
        self.parche.start()
        self.addCleanup(self.parche.stop)
        self.addCleanup(self.path.unlink, missing_ok=True)

    def test_sin_aprobacion_no_hay_envio(self):
        with redirect_stdout(io.StringIO()) as salida:
            row = registro.preparar("Casa del Puro", "Germany", "distribuidor", correo="einkauf@casa.test")
        texto = salida.getvalue()
        self.assertIn("empresa=Casa del Puro", texto)
        self.assertIn("pais=Germany", texto)
        self.assertIn("tipo=distribuidor", texto)
        self.assertIn("idioma=de", texto)
        self.assertIn("estado=borrador", texto)
        self.assertIn("ts=", texto)
        with patch("urllib.request.urlopen", side_effect=AssertionError("no enviar")):
            negado = registro.confirmar_envio(row["id"])
        self.assertEqual(negado["motivo"], "requiere_aprobacion")
        self.assertEqual(negado["estado"], "borrador")

    def test_limite_diario_pausa_y_correo_gratuito(self):
        base = datetime(2026, 10, 25, 12, 0, tzinfo=datetime.now().astimezone().tzinfo)
        with patch.dict(os_env(), {"B2B_ENVIOS_MAX_DIA": "1", "B2B_PAUSA_ENTRE_ENVIOS_SEC": "120"}):
            bueno = registro.preparar("Import AG", "Switzerland", "distribuidor", correo="import@import.test")
            otro = registro.preparar("Casa Dos", "Barbados", "tienda", correo="info@dos.test")
            gratis = registro.preparar("Gmail Shop", "Spain", "tienda", correo="shop@gmail.com")
            registro.aprobar(bueno["id"])
            registro.aprobar(otro["id"])
            registro.aprobar(gratis["id"])
            with patch("urllib.request.urlopen", side_effect=AssertionError("no enviar")):
                primero = registro.confirmar_envio(bueno["id"], ahora=base)
                lleno = registro.confirmar_envio(otro["id"], ahora=base + timedelta(hours=2))
                bloqueado = registro.confirmar_envio(gratis["id"], ahora=base + timedelta(hours=3))
        self.assertTrue(primero.get("ok"))
        self.assertEqual(primero["estado"], "enviado")
        self.assertEqual(lleno["motivo"], "limite_diario")
        self.assertEqual(lleno["estado"], "aprobado")
        self.assertEqual(bloqueado["motivo"], "correo_no_corporativo")

    def test_pausa_entre_confirmaciones(self):
        base = datetime(2026, 10, 25, 15, 0, tzinfo=datetime.now().astimezone().tzinfo)
        with patch.dict(os_env(), {"B2B_ENVIOS_MAX_DIA": "5", "B2B_PAUSA_ENTRE_ENVIOS_SEC": "120"}):
            primero = registro.preparar("Uno", "Panama", "duty_free", correo="info@uno.test")
            segundo = registro.preparar("Dos", "Hong Kong", "tienda", correo="sales@dos.test")
            registro.aprobar(primero["id"])
            registro.aprobar(segundo["id"])
            registro.confirmar_envio(primero["id"], ahora=base)
            temprano = registro.confirmar_envio(segundo["id"], ahora=base + timedelta(seconds=10))
            a_tiempo = registro.confirmar_envio(segundo["id"], ahora=base + timedelta(seconds=121))
        self.assertEqual(temprano["motivo"], "pausa")
        self.assertEqual(temprano["estado"], "aprobado")
        self.assertTrue(a_tiempo.get("ok"))
        self.assertEqual(a_tiempo["idioma"], "zh")

    def test_canada_no_entra(self):
        with self.assertRaises(ValueError):
            registro.preparar("Maple Cigars", "Canada", "distribuidor")


def os_env():
    import os
    return os.environ


if __name__ == "__main__":
    unittest.main()
