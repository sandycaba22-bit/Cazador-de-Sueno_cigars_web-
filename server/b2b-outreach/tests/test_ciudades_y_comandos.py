"""Regresiones de ciudades, paginacion, presupuesto y comandos, sin servicios reales."""
from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from b2b import budget, places, telegram_control as tc, telegram_gestion as tg
from b2b.country_rules import cargar_reglas


class TestPresupuestoCompatible(unittest.TestCase):
    def test_respaldo_deprecado_y_precedencia(self):
        nombres = ("GOOGLE_PLACES_MAX_CALLS_PER_DAY", "MAX_PLACES_CALLS_DIA", "B2B_GOOGLE_MAX_DIARIO")
        with patch.dict(os.environ, {nombre: "" for nombre in nombres}):
            self.assertEqual(budget.max_calls(), 30)
            os.environ[nombres[2]] = "200"
            self.assertEqual(budget.max_calls(), 200)
            os.environ[nombres[1]] = "40"
            self.assertEqual(budget.max_calls(), 40)
            os.environ[nombres[0]] = "25"
            self.assertEqual(budget.max_calls(), 25)
            os.environ[nombres[0]] = "invalido"
            self.assertEqual(budget.max_calls(), 40)

    def test_ejemplo_solo_publica_limite_canonico(self):
        ejemplo = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")
        self.assertEqual(ejemplo.count("GOOGLE_PLACES_MAX_CALLS_PER_DAY="), 1)
        self.assertNotIn("MAX_PLACES_CALLS_DIA=", ejemplo)
        self.assertNotIn("B2B_GOOGLE_MAX_DIARIO=", ejemplo)


class TestCiudadesYPaginacion(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.tmp = Path(temporal.name)
        for parche in (
            patch.object(budget, "BUDGET_PATH", self.tmp / "budget.json"),
            patch.object(places, "cache_path", return_value=self.tmp / "cache.json"),
            patch.object(places, "registrar_evento"),
            patch.object(places, "_notificar"),
            patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": "clave-ficticia",
                                    "GOOGLE_PLACES_MAX_CALLS_PER_DAY": "1000",
                                    "GOOGLE_PLACES_MAX_CALLS_PER_RUN": "1000",
                                    "GOOGLE_PLACES_MAX_CALLS_PER_MONTH": "2000"}),
        ):
            parche.start()
            self.addCleanup(parche.stop)
        places._GOOGLE_DESACTIVADO.clear()
        self.addCleanup(places._GOOGLE_DESACTIVADO.clear)

    def test_todas_las_ciudades_y_terminos_en_ingles(self):
        reglas = cargar_reglas()
        for mercado in reglas["paises"]:
            consultas = places.consultas_google(mercado["pais"], [])
            self.assertEqual(len(consultas), len(mercado["ciudades"]) * 12)
            for ciudad in mercado["ciudades"]:
                self.assertIn(("tienda", "en", f"cigar shop in {ciudad}, {mercado['pais']}"), consultas)
            self.assertTrue(all(idioma == "en" for _, idioma, _ in consultas))
        self.assertIn(("tienda", "en", "cigar shop in Miami, Florida"),
                      places.consultas_google("Florida", []))

    def test_tres_paginas_con_token_y_contabilidad(self):
        paginas = [
            {"places": [{"id": "miami-1"}], "nextPageToken": "segunda"},
            {"places": [{"id": "miami-2"}], "nextPageToken": "tercera"},
            {"places": [{"id": "miami-3"}]},
        ]
        with patch.object(places.urllib.request, "urlopen",
                          side_effect=[io.BytesIO(json.dumps(p).encode()) for p in paginas]) as red:
            resultados = places._post_search("cigar shop in Miami, Florida", "en")
        self.assertEqual([p["id"] for p in resultados], ["miami-1", "miami-2", "miami-3"])
        cuerpos = [json.loads(llamada.args[0].data) for llamada in red.call_args_list]
        self.assertNotIn("pageToken", cuerpos[0])
        self.assertEqual(cuerpos[1]["pageToken"], "segunda")
        self.assertEqual(cuerpos[2]["pageToken"], "tercera")
        self.assertTrue(all(c["textQuery"] == cuerpos[0]["textQuery"] for c in cuerpos))
        self.assertTrue(all(c["languageCode"] == "en" for c in cuerpos))
        self.assertIn("nextPageToken", red.call_args.args[0].get_header("X-goog-fieldmask"))
        self.assertEqual(budget.estado()["dia"], 3)

    def test_tope_se_revisa_antes_de_cada_pagina(self):
        pagina = {"places": [{"id": "miami-1"}], "nextPageToken": "segunda"}
        with patch.dict(os.environ, {"GOOGLE_PLACES_MAX_CALLS_PER_DAY": "1"}), \
                patch.object(places.urllib.request, "urlopen",
                             return_value=io.BytesIO(json.dumps(pagina).encode())) as red:
            with self.assertRaisesRegex(places.PresupuestoPlacesAgotado, "diario"):
                places._post_search("cigar shop in Miami, Florida", "en")
        self.assertEqual(red.call_count, 1)
        self.assertEqual(budget.estado()["dia"], 1)

    def test_cache_no_repite_ninguna_consulta_completada(self):
        respuesta = {"places": [{"id": "miami-1", "displayName": {"text": "Miami Cigars"},
                                "businessStatus": "OPERATIONAL", "types": ["store"]}]}
        with patch.object(places.urllib.request, "urlopen",
                          side_effect=lambda *_a, **_k: io.BytesIO(json.dumps(respuesta).encode())) as red:
            primeros, llamadas, _ = places.buscar_google_pais("Florida", [])
        self.assertEqual(llamadas, len(places.consultas_google("Florida", [])))
        self.assertEqual(red.call_count, llamadas)
        with patch.object(places.urllib.request, "urlopen",
                          side_effect=AssertionError("El cache no debe llamar a Google")):
            segundos, nuevas, stats = places.buscar_google_pais("Florida", [])
        self.assertEqual(nuevas, 0)
        self.assertEqual(stats["google_cache"], llamadas)
        self.assertEqual(primeros, segundos)

    def test_busqueda_parcial_no_se_marca_completa_en_cache(self):
        pagina = {"places": [{"id": "miami-1"}], "nextPageToken": "segunda"}
        with patch.dict(os.environ, {"GOOGLE_PLACES_MAX_CALLS_PER_DAY": "1"}), \
                patch.object(places.urllib.request, "urlopen",
                             return_value=io.BytesIO(json.dumps(pagina).encode())):
            _, _, stats = places.buscar_google_pais("Florida", [])
        self.assertEqual(stats["presupuesto_agotado"], "diario")
        self.assertEqual(places._load_cache()["busquedas"], {})


class TestComandosSimulados(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        tmp = Path(temporal.name)
        for parche in (patch.object(tc, "CONTROL_PATH", tmp / "control.json"),
                       patch.object(tg, "PENDIENTES_PATH", tmp / "pendientes.json")):
            parche.start()
            self.addCleanup(parche.stop)
        self.pendientes = {
            "fl1": {"nombre": "Miami Cigars", "pais": "Florida"},
            "fl2": {"nombre": "Tampa Cigars", "pais": "fL"},
            "tx": {"nombre": "Dallas Cigars", "pais": "Texas"},
            "pr": {"nombre": "San Juan Cigars", "pais": "Puerto Rico"},
            "jm": {"nombre": "Kingston Cigars", "pais": "Jamaica"},
        }
        for i, pais in enumerate(("Aruba", "Martinica", "Turks and Caicos Islands",
                                 "Islas Caimán", "Curazao", "French Guiana", "Caribe francés")):
            self.pendientes[f"retirado{i}"] = {"nombre": f"Retirado {i}", "pais": pais}
        tg._save_pendientes(self.pendientes)

    def comando(self, texto, chat="42"):
        cuerpo = {"ok": True, "result": [
            {"update_id": 1, "message": {"chat": {"id": chat}, "text": texto}}
        ]}
        with patch.object(tc.urllib.request, "urlopen",
                          return_value=io.BytesIO(json.dumps(cuerpo).encode())) as red:
            respuestas = tc.procesar_comandos_chat("token-ficticio", "42")
        red.assert_called_once()
        self.assertEqual(tg._load_pendientes(), self.pendientes)
        return respuestas

    def test_stats_solo_mercados_activos(self):
        respuesta = self.comando("/stats")[0]
        for linea in ("Florida: 2", "Texas: 1", "Puerto Rico: 1", "Jamaica: 1"):
            self.assertIn(linea, respuesta)
        self.assertNotIn("Retirado", respuesta)
        self.assertNotIn("Aruba", respuesta)

    def test_pendientes_excluye_retirados(self):
        self.assertIn("5 leads pendientes", self.comando("/pendientes")[0])

    def test_estado_fl_y_nombre_completo_sin_mayusculas(self):
        for consulta in ("/estado FL", "/estado fl", "/estado Florida", "/ESTADO fLoRiDa"):
            respuesta = self.comando(consulta)[0]
            self.assertIn("Miami Cigars", respuesta)
            self.assertIn("Tampa Cigars", respuesta)
            self.assertNotIn("Dallas Cigars", respuesta)
            self.assertNotIn("Retirado", respuesta)

    def test_tabla_usps_completa_y_sin_iniciales(self):
        self.assertEqual(len(tc.USPS_ESTADOS), 51)
        for codigo, nombre in tc.USPS_ESTADOS.items():
            self.assertEqual(tc.mercado_canonico(codigo.lower()), nombre)
            self.assertEqual(tc.mercado_canonico(nombre.upper()), nombre)
        for codigo in ("TX", "CA", "NY", "DC", "VA", "WV"):
            tg._save_pendientes({**self.pendientes, "usps": {
                "nombre": "USPS Cigars", "pais": tc.USPS_ESTADOS[codigo],
            }})
            self.pendientes = tg._load_pendientes()
            self.assertIn("USPS Cigars", self.comando(f"/estado {codigo}")[0])

    def test_estado_retirado_y_chat_no_autorizado(self):
        self.assertIn("No hay leads", self.comando("/estado Aruba")[0])
        self.assertEqual(self.comando("/stats", chat="99"), [])
