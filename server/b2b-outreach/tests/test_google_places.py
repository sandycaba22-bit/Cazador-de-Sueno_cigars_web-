"""Google Places (New) como fuente principal, con respuestas simuladas (sin clave real)."""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from b2b import budget, contacto_web, places  # noqa: E402
from b2b.descartes import entrada_sin_contacto  # noqa: E402
from b2b.fuente_leads import resolver_fuente_leads  # noqa: E402
from b2b.idioma import idioma_para_lead, idioma_para_pais  # noqa: E402
from b2b.redactor import borrador_correo, borrador_corto, tipo_en_idioma  # noqa: E402
from b2b.telegram_gestion import tiene_medio_contacto  # noqa: E402
from b2b.telegram_prospecto import (  # noqa: E402
    enviar_prospecto_telegram, mensaje_prospecto_completo, teclado_prospecto,
)

FIXTURE = ROOT / "tests" / "fixtures" / "google_places_new_aruba.json"
FIXTURE_FLORIDA = ROOT / "tests" / "fixtures" / "google_places_new_florida.json"
CLAVE_FALSA = "AIzaSyFAKE-test-key-0123456789abcdefghij"
MASCARA_PEDIDA = (
    "places.id,places.displayName,places.formattedAddress,"
    "places.nationalPhoneNumber,places.internationalPhoneNumber,"
    "places.websiteUri,places.googleMapsUri,"
    "places.rating,places.userRatingCount,places.businessStatus,places.types,nextPageToken"
)
MAPS_EMPORIUM = (
    "https://www.google.com/maps/search/?api=1&query=Aruba%20Cigar%20Emporium"
    "&query_place_id=ChIJ-emporium-aw"
)
DESCARTES_FIXTURE = [
    "Google: CLOSED_PERMANENTLY",
]
OPERATIVOS_POR_RATING = [
    "New Leaf Cigars",
    "La Casa del Habano Aruba",
    "Aruba Cigar Emporium",
    "Eagle Beach Cigars",
    "Smoke Corner Tobacconist",
    "Palm Beach Cigar Lounge",
]
OPERATIVOS_FLORIDA = [
    "Miami New Leaf Cigars",
    "La Casa del Habano Miami",
    "Miami Cigar Emporium",
    "Biscayne Cigars",
    "Miami Smoke Corner Tobacconist",
    "Brickell Cigar Lounge",
]
MAPS_EMPORIUM_FLORIDA = (
    "https://www.google.com/maps/search/?api=1&query=Miami%20Cigar%20Emporium"
    "&query_place_id=ChIJ-emporium-miami-test"
)


class _Respuesta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class GoogleBase(unittest.TestCase):
    fixture = FIXTURE

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patches = [
            mock.patch.object(budget, "BUDGET_PATH", self.tmp / "places_budget.json"),
            mock.patch.object(places, "cache_path", return_value=self.tmp / "google_places_cache.json"),
            mock.patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": CLAVE_FALSA}),
            mock.patch.object(places, "registrar_presupuesto_agotado"),
        ]
        for p in self.patches:
            p.start()
        places._GOOGLE_DESACTIVADO.clear()
        for var in ("GOOGLE_PLACES_MAX_CALLS_PER_DAY", "MAX_PLACES_CALLS_DIA", "B2B_GOOGLE_MAX_DIARIO",
                    "GOOGLE_PLACES_MAX_CALLS_PER_RUN",
                    "GOOGLE_PLACES_MIN_RATING", "GOOGLE_PLACES_MIN_RESENAS"):
            os.environ.pop(var, None)
        self.peticiones: list = []

    def tearDown(self):
        places._GOOGLE_DESACTIVADO.clear()
        for p in reversed(self.patches):
            p.stop()

    def _urlopen_ok(self, request, timeout=0):
        self.peticiones.append(request)
        return _Respuesta(self.fixture.read_bytes())


class TestLlamadaApi(GoogleBase):
    def setUp(self):
        super().setUp()
        # Estos tests completan todas las ciudades; los topes tienen su propia clase.
        os.environ["GOOGLE_PLACES_MAX_CALLS_PER_DAY"] = "1000"
        os.environ["GOOGLE_PLACES_MAX_CALLS_PER_RUN"] = "1000"

    def test_un_post_por_busqueda_con_mascara_exacta_y_sin_details(self):
        with mock.patch.object(places.urllib.request, "urlopen", side_effect=self._urlopen_ok):
            leads, llamadas, stats = places.buscar_google_pais("Florida", ["tienda", "lounge"])
        consultas = [c for _t, _i, c in places.consultas_google("Florida", ["tienda", "lounge"])]
        self.assertEqual(llamadas, len(consultas))
        self.assertEqual(len(self.peticiones), len(consultas))
        for req in self.peticiones:
            self.assertEqual(req.full_url, "https://places.googleapis.com/v1/places:searchText")
            self.assertEqual(req.get_method(), "POST")
            self.assertEqual(req.get_header("X-goog-fieldmask"), MASCARA_PEDIDA)
            self.assertEqual(req.get_header("X-goog-api-key"), CLAVE_FALSA)
            self.assertNotIn(CLAVE_FALSA, req.full_url)
        textos = [json.loads(r.data)["textQuery"] for r in self.peticiones]
        self.assertEqual(textos, consultas)

    def test_terminos_por_ciudad_en_ingles(self):
        fl = [c for _t, _i, c in places.consultas_google("Florida", [])]
        self.assertTrue(any("cigar shop in Miami, Florida" == q for q in fl))
        self.assertTrue(any("cigar lounge in Miami, Florida" == q for q in fl))
        self.assertTrue(any("tobacconist in Miami, Florida" == q for q in fl))
        pr = [c for _t, _i, c in places.consultas_google("Puerto Rico", [])]
        self.assertTrue(any("cigar lounge in San Juan, Puerto Rico" == q for q in pr))
        jm = [c for _t, _i, c in places.consultas_google("Jamaica", [])]
        self.assertTrue(any("cigar shop in Kingston, Jamaica" == q for q in jm))

    def test_operativos_pasan_sin_web_telefono_ni_resenas(self):
        with mock.patch.object(self, "fixture", FIXTURE_FLORIDA), \
                mock.patch.object(places.urllib.request, "urlopen", side_effect=self._urlopen_ok), \
                mock.patch.object(places, "registrar_evento") as log:
            leads, _ll, stats = places.buscar_google_pais("Florida", ["tienda"])
        self.assertEqual([l["nombre"] for l in leads], OPERATIVOS_FLORIDA)
        self.assertEqual([d["motivo"] for d in stats["descartes"]], DESCARTES_FIXTURE)
        self.assertTrue(all(d["etapa"] == "google_estado" for d in stats["descartes"]))
        por_nombre = {l["nombre"]: l for l in leads}
        casa = por_nombre["La Casa del Habano Miami"]
        emporium = por_nombre["Miami Cigar Emporium"]
        eagle = por_nombre["Biscayne Cigars"]
        self.assertEqual(casa["web"], "")
        self.assertEqual(casa["instagram"], "https://www.instagram.com/casadelhabanomiami/")
        self.assertEqual(emporium["web"], "https://miamicigaremporium.example/")
        self.assertEqual(emporium["telefono"], "(305) 555-0123")
        self.assertEqual(emporium["telefono_internacional"], "+13055550123")
        self.assertEqual(emporium["maps_url"], MAPS_EMPORIUM_FLORIDA)
        self.assertEqual(eagle["web"], "")
        self.assertTrue(eagle["telefono"])
        self.assertTrue(eagle["maps_url"])
        for lead in leads:
            self.assertNotIn("maps", lead["web"])
            self.assertIn("Miami, FL", lead["direccion"])
        crudos = [c.args[0] for c in log.call_args_list if c.args and c.args[0].get("evento") == "google_place_crudo"]
        self.assertEqual(len(crudos), 1)
        self.assertTrue(crudos[0]["campos_presentes"]["internationalPhoneNumber"])
        for campo in (
            "websiteUri", "nationalPhoneNumber", "internationalPhoneNumber",
            "rating", "userRatingCount", "businessStatus", "googleMapsUri",
        ):
            self.assertIn(campo, crudos[0]["campos_presentes"])

    def test_rating_telefono_y_web_no_descartan(self):
        raw = {
            "businessStatus": "OPERATIONAL",
            "displayName": {"text": "Oranjestad Cigar Shop"},
            "types": ["store"],
            "rating": 3.1,
            "userRatingCount": 1,
        }
        lead = places._normalizar_place(raw, "Florida")
        self.assertEqual(places.motivo_descarte_google(raw, lead), "")
        cerrado = {**raw, "businessStatus": "CLOSED_TEMPORARILY"}
        self.assertEqual(places.motivo_descarte_google(cerrado, lead), "Google: CLOSED_TEMPORARILY")
        bar = {
            "businessStatus": "OPERATIONAL",
            "displayName": {"text": "Joe Sports Bar"},
            "types": ["bar"],
        }
        bar_lead = places._normalizar_place(bar, "Florida")
        self.assertEqual(places.motivo_descarte_google(bar, bar_lead), "bar/café sin humidor")
        licor = {
            "businessStatus": "OPERATIONAL",
            "displayName": {"text": "Sunny Liquor Store"},
            "types": ["liquor_store"],
        }
        licor_lead = places._normalizar_place(licor, "Florida")
        self.assertEqual(places.motivo_descarte_google(licor, licor_lead), "excluir_siempre")

    def test_cache_no_repite_isla_en_el_mes(self):
        with mock.patch.object(places.urllib.request, "urlopen", side_effect=self._urlopen_ok):
            primeros, ll1, _ = places.buscar_google_pais("Florida", ["tienda"])
            segundos, ll2, stats2 = places.buscar_google_pais("Florida", ["tienda"])
        self.assertGreater(ll1, 0)
        self.assertEqual(ll2, 0)
        self.assertEqual(stats2["google_cache"], ll1)
        self.assertEqual([l["place_id"] for l in primeros], [l["place_id"] for l in segundos])
        self.assertTrue(places.isla_buscada_este_mes("Florida", [c for _t, _i, c in places.consultas_google("Florida", ["tienda"])]))
        cache = json.loads((self.tmp / "google_places_cache.json").read_text(encoding="utf-8"))
        self.assertIn("ChIJ-emporium-aw", cache["places"])


class TestPresupuesto(GoogleBase):
    def test_tope_diario_para_y_avisa_una_vez(self):
        os.environ["GOOGLE_PLACES_MAX_CALLS_PER_DAY"] = "2"
        with mock.patch.object(places.urllib.request, "urlopen", side_effect=self._urlopen_ok), \
                mock.patch("b2b.telegram_buscar.notificar_buscar") as aviso:
            _l, llamadas, stats = places.buscar_google_pais("Florida", ["tienda", "lounge"])
            places.buscar_google_pais("Jamaica", ["tienda"])
        self.assertEqual(llamadas, 2)
        self.assertEqual(len(self.peticiones), 2)
        self.assertEqual(stats["presupuesto_agotado"], "diario")
        aviso.assert_called_once()
        self.assertIn("tope diario", aviso.call_args[0][0])
        self.assertIn("mañana", aviso.call_args[0][0])

    def test_tope_mensual_900(self):
        hoy = budget._hoy()
        budget._save({"fecha": hoy.isoformat(), "llamadas": 0,
                      "mes": hoy.strftime("%Y-%m"), "llamadas_mes": 900, "avisos": {}})
        self.assertEqual(budget.max_calls_mes(), 900)
        self.assertEqual(budget.motivo_bloqueo(), "mensual")
        with mock.patch.object(places.urllib.request, "urlopen", side_effect=self._urlopen_ok), \
                mock.patch("b2b.telegram_buscar.notificar_buscar") as aviso:
            _l, llamadas, stats = places.buscar_google_pais("Aruba", ["tienda"])
        self.assertEqual(llamadas, 0)
        self.assertEqual(stats["presupuesto_agotado"], "mensual")
        self.assertIn("tope mensual", aviso.call_args[0][0])

    def test_sigue_al_dia_siguiente(self):
        ayer = budget._hoy() - timedelta(days=1)
        budget._save({"fecha": ayer.isoformat(), "llamadas": 30, "tandas": {"manana": 15, "tarde": 15},
                      "mes": budget._hoy().strftime("%Y-%m"), "llamadas_mes": 30,
                      "avisos": {"diario": ayer.isoformat()}})
        self.assertEqual(budget.max_calls(), 30)
        self.assertTrue(budget.puede_llamar())
        self.assertEqual(budget.estado()["mes"], 30)
        self.assertTrue(budget.marcar_aviso("diario"))

    def test_contador_persistente_en_data(self):
        with mock.patch.object(budget, "BUDGET_PATH", None):
            self.assertEqual(budget.budget_path().name, "places_budget.json")
            self.assertEqual(budget.budget_path().parent.name, "data")


class TestTandas(GoogleBase):
    def _a_las(self, hora):
        return mock.patch.object(budget, "_ahora", return_value=datetime(2026, 10, 7, hora, 0))

    def test_tanda_por_hora(self):
        with self._a_las(9):
            self.assertEqual(budget.tanda_actual(), "manana")
        with self._a_las(15):
            self.assertEqual(budget.tanda_actual(), "tarde")

    def test_quince_por_tanda_y_treinta_al_dia(self):
        self.assertEqual(budget.max_calls_tanda(), 15)
        with self._a_las(9):
            for _ in range(15):
                self.assertTrue(budget.puede_llamar())
                budget.registrar_llamada()
            self.assertEqual(budget.motivo_bloqueo(), "tanda")
        with self._a_las(15):
            self.assertTrue(budget.puede_llamar())
            for _ in range(15):
                budget.registrar_llamada()
            self.assertEqual(budget.motivo_bloqueo(), "diario")
            est = budget.estado()
        self.assertEqual((est["dia"], est["tanda_llamadas"], est["max_tanda"]), (30, 15, 15))
        guardado = json.loads((self.tmp / "places_budget.json").read_text(encoding="utf-8"))
        self.assertEqual(guardado["tandas"], {"manana": 15, "tarde": 15})

    def test_tanda_nunca_supera_el_diario(self):
        with mock.patch.dict(os.environ, {"GOOGLE_PLACES_MAX_CALLS_PER_RUN": "50"}):
            self.assertEqual(budget.max_calls_tanda(), 30)
        with mock.patch.dict(os.environ, {"GOOGLE_PLACES_MAX_CALLS_PER_DAY": "10"}):
            self.assertEqual(budget.max_calls_tanda(), 10)

    def test_tanda_llena_para_google_y_avisa_la_tarde(self):
        with self._a_las(9):
            budget.registrar_llamada(15)
            with mock.patch.object(places.urllib.request, "urlopen", side_effect=self._urlopen_ok), \
                    mock.patch("b2b.telegram_buscar.notificar_buscar") as aviso:
                _l, llamadas, stats = places.buscar_google_pais("Aruba", ["tienda"])
                places.buscar_google_pais("Curacao", ["tienda"])
        self.assertEqual((llamadas, len(self.peticiones)), (0, 0))
        self.assertEqual(stats["presupuesto_agotado"], "tanda")
        aviso.assert_called_once()
        self.assertIn("tanda de la mañana completa (15/15", aviso.call_args[0][0])
        self.assertIn("15:00", aviso.call_args[0][0])

    def test_corrida_se_corta_en_quince(self):
        consultas = [c for _t, _i, c in places.consultas_google("Aruba", ["tienda", "lounge"])]
        with self._a_las(9):
            budget.registrar_llamada(15 - 2)
            with mock.patch.object(places.urllib.request, "urlopen", side_effect=self._urlopen_ok), \
                    mock.patch("b2b.telegram_buscar.notificar_buscar"):
                _l, llamadas, _s = places.buscar_google_pais("Aruba", ["tienda", "lounge"])
            self.assertGreater(len(consultas), 2)
            self.assertEqual(llamadas, 2)
            self.assertEqual(budget.estado()["tanda_llamadas"], 15)


class TestErroresGoogle(GoogleBase):
    OSM = [{"nombre": "Tabaco OSM", "pais": "Aruba", "place_id": "osm:node/1", "telefono": "+297 5800000"}]

    def _error(self, codigo):
        def _falla(request, timeout=0):
            self.peticiones.append(request)
            raise urllib.error.HTTPError(request.full_url, codigo, "x", {}, io.BytesIO(b"{}"))

        return _falla

    def test_error_google_no_llama_osm(self):
        for codigo in (400, 429, 500, 503):
            with self.subTest(codigo=codigo):
                places._GOOGLE_DESACTIVADO.clear()
                self.peticiones.clear()
                with mock.patch.object(places.urllib.request, "urlopen", side_effect=self._error(codigo)), \
                        mock.patch.object(places, "_buscar_osm") as osm, \
                        mock.patch.object(places, "_notificar"):
                    leads, _ll, stats = places.buscar_en_pais("Aruba", ["tienda"], 5, fuente="google")
                    leads2, _l2, stats2 = places.buscar_en_pais("Curacao", ["tienda"], 5, fuente="google")
                osm.assert_not_called()
                self.assertEqual(leads, [])
                self.assertIn(str(codigo), stats["google_error"])
                self.assertEqual(len(self.peticiones), 1)
                self.assertEqual(leads2, [])
                self.assertIn(f"HTTP {codigo}", stats2["google_omitido"])

    def test_ambas_si_google_falla_sigue_con_osm(self):
        places._GOOGLE_DESACTIVADO.clear()
        with mock.patch.object(places.urllib.request, "urlopen", side_effect=self._error(500)), \
                mock.patch.object(places, "_buscar_osm", return_value=(self.OSM, 1, {"descartes": []})) as osm, \
                mock.patch.object(places, "_notificar"):
            leads, _ll, stats = places.buscar_en_pais("Aruba", ["tienda"], 5, fuente="ambas")
        osm.assert_called_once()
        self.assertEqual([l["nombre"] for l in leads], ["Tabaco OSM"])
        self.assertIn("500", stats["google_error"])

    def test_sin_respuesta_no_llama_osm(self):
        with mock.patch.dict(os.environ, {"FUENTE_LEADS": "google"}), \
                mock.patch.object(places.urllib.request, "urlopen", side_effect=TimeoutError("timed out")), \
                mock.patch.object(places, "_buscar_osm") as osm, \
                mock.patch.object(places, "_notificar") as aviso:
            leads, _ll, _stats = places.buscar_en_pais("Aruba", ["tienda"], 5, fuente="google")
        osm.assert_not_called()
        self.assertEqual(leads, [])
        self.assertIn("no respondió", aviso.call_args[0][0])
        self.assertIn("no consulto OpenStreetMap", aviso.call_args[0][0])

    def test_cuota_429_avisa_una_vez_al_dia(self):
        with mock.patch.object(places.urllib.request, "urlopen", side_effect=self._error(429)), \
                mock.patch.object(places, "_buscar_osm", return_value=(self.OSM, 1, {"descartes": []})), \
                mock.patch.object(places, "_notificar") as aviso:
            places.buscar_en_pais("Aruba", ["tienda"], 5, fuente="ambas")
            places._GOOGLE_DESACTIVADO.clear()
            places.buscar_en_pais("Aruba", ["lounge"], 5, fuente="ambas")
        aviso.assert_called_once()
        self.assertIn("429 (cuota de Google agotada)", aviso.call_args[0][0])
        self.assertIn("OpenStreetMap", aviso.call_args[0][0])

    def test_error_a_mitad_conserva_lo_ya_encontrado(self):
        respuestas = iter([FIXTURE.read_bytes()])

        def _primera_ok(request, timeout=0):
            try:
                return _Respuesta(next(respuestas))
            except StopIteration:
                raise urllib.error.HTTPError(request.full_url, 502, "x", {}, io.BytesIO(b"")) from None

        with mock.patch.object(places.urllib.request, "urlopen", side_effect=_primera_ok), \
                mock.patch.object(places, "_notificar"):
            leads, llamadas, stats = places.buscar_google_pais("Aruba", ["tienda", "lounge"])
        self.assertEqual(llamadas, 1)
        self.assertEqual([l["nombre"] for l in leads], OPERATIVOS_POR_RATING)
        self.assertIn("502", stats["google_error"])


class TestTelefonoInternacional(unittest.TestCase):
    def test_florida_numero_nacional_sin_campo_internacional(self):
        from b2b.telefono import internacional

        self.assertEqual(internacional("Florida", "(305) 555-0123"), "+13055550123")
        raw = {
            "id": "ChIJ-miami-nacional-test",
            "displayName": {"text": "Miami Cigar Shop"},
            "formattedAddress": "100 Brickell Avenue, Miami, FL 33131, USA",
            "nationalPhoneNumber": "(305) 555-0123",
            "businessStatus": "OPERATIONAL",
            "types": ["store"],
        }
        self.assertNotIn("internationalPhoneNumber", raw)
        lead = places._normalizar_place(raw, "Florida")
        self.assertEqual(lead["telefono"], "(305) 555-0123")
        self.assertEqual(lead["telefono_internacional"], "+13055550123")
        self.assertEqual(places.motivo_descarte_google(raw, lead), "")

    def test_prefijos(self):
        from b2b.telefono import internacional

        self.assertEqual(internacional("Aruba", "583 1111"), "+2975831111")
        self.assertEqual(internacional("Bahamas", "(242) 555-1234"), "+12425551234")
        self.assertEqual(internacional("Martinique", "0596 12 34 56"), "+596596123456")
        self.assertEqual(internacional("Curacao", "+599 9 465 0000"), "+59994650000")
        self.assertEqual(internacional("Bahamas", "555-1234"), "")
        self.assertEqual(internacional("Narnia", "583 1111"), "")


class TestRotacion(GoogleBase):
    def test_islas_agotadas_solo_si_todas_buscadas_este_mes(self):
        with mock.patch.object(places.urllib.request, "urlopen", side_effect=self._urlopen_ok), \
                mock.patch.dict(os.environ, {"GOOGLE_PLACES_MAX_CALLS_PER_DAY": "1000",
                                              "GOOGLE_PLACES_MAX_CALLS_PER_RUN": "1000"}):
            self.assertFalse(places.islas_agotadas_google(["Puerto Rico"]))
            places.buscar_google_pais("Puerto Rico", ["tienda", "lounge"])
        self.assertTrue(places.islas_agotadas_google(["Puerto Rico"]))
        self.assertFalse(places.islas_agotadas_google(["Puerto Rico", "Jamaica"]))
        self.assertFalse(places.islas_agotadas_google([]))

    def _prospectar(self, fuente, agotadas):
        import prospector

        with mock.patch.object(prospector, "resolver_fuente_leads", return_value=fuente), \
                mock.patch.object(places, "islas_agotadas_google", return_value=agotadas), \
                mock.patch.object(prospector, "registrar_evento"), \
                mock.patch.object(prospector, "prospectar_turno_global", return_value={"modo": "global"}) as glob, \
                mock.patch.object(prospector, "prospectar_prioridad_inicial", return_value={"modo": "islas"}) as islas:
            out = prospector._prospectar(None, 9, self.tmp / "inbox", False, False, "", False)
        return out, glob, islas

    def test_islas_agotadas_pasa_a_rotacion_global(self):
        out, glob, islas = self._prospectar("ambas", True)
        self.assertEqual(out["modo"], "global")
        islas.assert_not_called()
        self.assertIsNone(glob.call_args[0][0])

    def test_con_islas_pendientes_sigue_en_islas(self):
        self.assertEqual(self._prospectar("ambas", False)[0]["modo"], "islas")
        with mock.patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": ""}):
            self.assertEqual(self._prospectar("ambas", True)[0]["modo"], "islas")
        self.assertEqual(self._prospectar("osm", True)[0]["modo"], "islas")

    def test_fin_de_cola_global_vuelve_a_empezar(self):
        import prospector
        from b2b import buscar_global

        with mock.patch.object(buscar_global, "siguiente_pais_cola", side_effect=[None, {"pais": "Florida"}]), \
                mock.patch.object(buscar_global, "guardar_estado_global") as guardar, \
                mock.patch.object(prospector, "registrar_evento"), \
                mock.patch.object(prospector, "resolver_fuente_leads", return_value="ambas"), \
                mock.patch.object(prospector, "prospectar_un_pais", return_value={"pais": "Florida"}) as uno:
            out = prospector.prospectar_turno_global(None, 9, self.tmp / "inbox", solo_listar=True)
        guardar.assert_called_once_with({"pais_idx": 0, "celda_idx": 0, "completo": False, "pais": ""})
        self.assertEqual(uno.call_args[0][0]["pais"], "Florida")
        self.assertNotIn("fin_cola", out)


class TestClaveDesdeEnv(unittest.TestCase):
    def test_env_del_modulo_rellena_clave_vacia_sin_pisar_otras(self):
        import telegram_bot

        tmp = Path(tempfile.mkdtemp())
        (tmp / ".env").write_text(f"GOOGLE_PLACES_API_KEY={CLAVE_FALSA}\nTELEGRAM_CHAT_ID=999\n", encoding="utf-8")
        with mock.patch.object(telegram_bot, "HERE", tmp), \
                mock.patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": "", "TELEGRAM_CHAT_ID": "123"}):
            telegram_bot.load_local_env()
            self.assertEqual(os.environ["GOOGLE_PLACES_API_KEY"], CLAVE_FALSA)
            self.assertEqual(os.environ["TELEGRAM_CHAT_ID"], "123")


class TestSinClave(GoogleBase):
    def test_sin_clave_google_no_cae_a_osm(self):
        with mock.patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": ""}):
            for valor in ("ambas", "auto"):
                with mock.patch.dict(os.environ, {"FUENTE_LEADS": valor}):
                    self.assertEqual(resolver_fuente_leads(), "osm")
            with mock.patch.dict(os.environ, {"FUENTE_LEADS": "google"}):
                self.assertEqual(resolver_fuente_leads(), "google")
            with mock.patch.object(places, "_buscar_osm") as osm, \
                    mock.patch.object(places.urllib.request, "urlopen") as red:
                leads, _ll, stats = places.buscar_en_pais("Aruba", ["tienda"], 5, fuente="google")
        osm.assert_not_called()
        red.assert_not_called()
        self.assertEqual(leads, [])
        self.assertIn("sin GOOGLE_PLACES_API_KEY", stats["google_omitido"])

    def test_con_clave_auto_es_ambas(self):
        with mock.patch.dict(os.environ, {"FUENTE_LEADS": "auto"}):
            self.assertEqual(resolver_fuente_leads(), "ambas")
        with mock.patch.dict(os.environ, {"FUENTE_LEADS": "google"}):
            self.assertEqual(resolver_fuente_leads(), "google")

    def test_error_http_no_filtra_la_clave(self):
        def _403(request, timeout=0):
            cuerpo = json.dumps({"error": {"message": f"API key {CLAVE_FALSA} not valid"}}).encode()
            raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, io.BytesIO(cuerpo))

        with mock.patch.object(places.urllib.request, "urlopen", side_effect=_403), \
                mock.patch.object(places, "registrar_evento") as evento, \
                mock.patch.object(places, "_buscar_osm") as osm:
            leads, _ll, stats = places.buscar_en_pais("Aruba", ["tienda"], 5, fuente="google")
            _leads2, _l2, stats2 = places.buscar_en_pais("Curacao", ["tienda"], 5, fuente="google")
        osm.assert_not_called()
        self.assertEqual(leads, [])
        self.assertNotIn(CLAVE_FALSA, json.dumps(stats))
        self.assertNotIn(CLAVE_FALSA, str(evento.call_args_list))
        self.assertIn("***", stats["google_error"])
        self.assertIn("HTTP 403", stats2["google_omitido"])


class TestAmbasFuentes(GoogleBase):
    def test_google_primero_y_osm_duplicado_se_fusiona(self):
        osm = [
            {"nombre": "Emporium (OSM)", "pais": "Aruba", "place_id": "osm:node/9",
             "telefono": "+297 583-1111", "fuente": "openstreetmap"},
            {"nombre": "Tabaquería San Nicolas", "pais": "Aruba", "place_id": "osm:node/10",
             "telefono": "+297 584 9999", "fuente": "openstreetmap"},
        ]
        with mock.patch.object(places.urllib.request, "urlopen", side_effect=self._urlopen_ok), \
                mock.patch.object(places, "_buscar_osm", return_value=(osm, 1, {"descartes": []})):
            leads, _ll, stats = places.buscar_en_pais("Aruba", ["tienda"], 10, fuente="ambas")
        nombres = [l["nombre"] for l in leads]
        self.assertEqual(nombres, OPERATIVOS_POR_RATING + ["Tabaquería San Nicolas"])
        fusion = [d for d in stats["descartes"] if d["motivo"] == "fusionado_misma_clave"]
        self.assertEqual(len(fusion), 1)
        self.assertEqual(fusion[0]["nombres"], ["Aruba Cigar Emporium", "Emporium (OSM)"])
        no_seguros = [d for d in stats["descartes"] if d["motivo"].startswith("Google:")]
        self.assertEqual(len(no_seguros), len(DESCARTES_FIXTURE))
        self.assertEqual(len(leads) + len(stats["descartes"]), 7 + len(osm))


class TestFlujoCompletoIsla(GoogleBase):
    def test_aruba_google_cuadra_con_negocios_seguros(self):
        import prospector
        from b2b import calidad_lead, leads_store

        reglas = {"pais": "Aruba", "dificultad": 2, "estado": "preliminar"}
        inbox = self.tmp / "cola" / "inbox"
        web_ok = {"web_clase": "OK", "web_estado": "OK", "web_http": 200, "fecha_chequeo": ""}
        with mock.patch.dict(os.environ, {"B2B_DATA_DIR": str(self.tmp / "data"),
                                          "B2B_LOG_DIR": str(self.tmp / "logs")}), \
                mock.patch.object(leads_store, "SEEN_PATH", self.tmp / "registro.json"), \
                mock.patch.object(places.urllib.request, "urlopen", side_effect=self._urlopen_ok), \
                mock.patch.object(places, "_buscar_osm", return_value=([], 0, {"descartes": []})), \
                mock.patch.object(contacto_web, "obtener_html", return_value="<p>Premium cigars</p>"), \
                mock.patch.object(calidad_lead, "chequear_web", return_value=web_ok), \
                mock.patch.object(prospector.time, "sleep"):
            stats = prospector.prospectar_un_pais(
                reglas, 10, inbox, fuente="google", notificar_telegram_buscar=False
            )
        c = stats["conteo"]
        self.assertEqual(c["encontrados"], 7)
        self.assertEqual(c["sin_clasificar"], 0)
        self.assertEqual(c["descartados"], len(DESCARTES_FIXTURE))
        self.assertEqual(c["nuevos"], 5)
        self.assertEqual(c["dudosos"], 1)
        self.assertEqual(c["sin_contacto"], 0)
        encolados = [json.loads(p.read_text(encoding="utf-8")) for p in inbox.glob("*.json")]
        self.assertEqual(
            sorted(e["nombre"] for e in encolados),
            [
                "Aruba Cigar Emporium",
                "Eagle Beach Cigars",
                "New Leaf Cigars",
                "Palm Beach Cigar Lounge",
                "Smoke Corner Tobacconist",
            ],
        )
        emporium = next(e for e in encolados if e["nombre"] == "Aruba Cigar Emporium")
        self.assertEqual(emporium["maps_url"], MAPS_EMPORIUM)
        self.assertTrue(emporium["vende_cigarros"])
        dudosos = [json.loads(p.read_text(encoding="utf-8")) for p in (inbox.parent / "dudoso").glob("*.json")]
        casa = dudosos[0]
        self.assertEqual(casa["nombre"], "La Casa del Habano Aruba")
        self.assertEqual(casa["instagram"], "https://www.instagram.com/casadelhabanoaruba/")
        self.assertEqual(casa["web"], "—")

    def test_instagram_con_cigar_es_senal_extra(self):
        from b2b.nombres_busqueda import clasificar_aceptacion

        lead = {"nombre": "Casa del Habano", "web": "", "instagram": "https://www.instagram.com/cigar.house.aw/"}
        self.assertEqual(clasificar_aceptacion(lead)[0], "aceptado")


HOME = """<html lang="en"><body><h1>Aruba Cigar Emporium</h1>
<p>Premium cigars, humidor and accessories in Oranjestad.</p>
<a href="/contact-us">Contact us</a>
<a href="https://www.instagram.com/p/abc123/">post</a>
<a href="https://www.instagram.com/arubacigaremporium/">Instagram</a>
<a href="https://wa.me/2975831111">WhatsApp</a>
</body></html>"""
CONTACTO = """<html><body><a href="mailto:info@arubacigaremporium.aw">info@arubacigaremporium.aw</a>
<form action="/send"><input type="email" name="email"><textarea name="msg"></textarea></form></body></html>"""
SIN_FORM = """<html><body><p>Fine cigars since 1990.</p><form role="search"><input name="q"></form></body></html>"""


class TestContactoWeb(unittest.TestCase):
    def setUp(self):
        contacto_web._CACHE_HTML.clear()

    def _paginas(self, mapa):
        visitadas = []

        def fetch(url):
            visitadas.append(url)
            if url not in mapa:
                raise urllib.error.URLError("404")
            return mapa[url]

        return visitadas, fetch

    def test_extrae_correo_instagram_whatsapp_y_formulario_real(self):
        web = "https://www.arubacigaremporium.aw/"
        visitadas, fetch = self._paginas({web: HOME, "https://www.arubacigaremporium.aw/contact-us": CONTACTO})
        with mock.patch.object(contacto_web.http_polite, "permitido_robots", return_value=True), \
                mock.patch.object(contacto_web.http_polite, "fetch_url", side_effect=fetch):
            info = contacto_web.extraer_contactos(web)
        self.assertEqual(info["correo"], "info@arubacigaremporium.aw")
        self.assertEqual(info["instagram"], "https://www.instagram.com/arubacigaremporium")
        self.assertEqual(info["whatsapp"], "2975831111")
        self.assertEqual(info["formulario"], "https://www.arubacigaremporium.aw/contact-us")
        self.assertTrue(info["vende_cigarros"])
        self.assertEqual(visitadas, [web, "https://www.arubacigaremporium.aw/contact-us"])

    def test_no_inventa_formulario_ni_paginas(self):
        web = "https://cigars.example-shop.aw/"
        visitadas, fetch = self._paginas({web: SIN_FORM})
        with mock.patch.object(contacto_web.http_polite, "permitido_robots", return_value=True), \
                mock.patch.object(contacto_web.http_polite, "fetch_url", side_effect=fetch):
            info = contacto_web.extraer_contactos(web)
        self.assertEqual(info["formulario"], "")
        self.assertEqual(info["correo"], "")
        self.assertEqual(visitadas, [web])

    def test_redes_y_mapas_no_se_visitan_como_web(self):
        with mock.patch.object(contacto_web.http_polite, "fetch_url") as fetch:
            for url in ("https://www.instagram.com/x/", "https://facebook.com/x", "https://maps.google.com/?cid=1"):
                self.assertIsNone(contacto_web.extraer_contactos(url)["vende_cigarros"])
        fetch.assert_not_called()
        lead = contacto_web.normalizar_canales({"web": "https://www.facebook.com/cigarbar"})
        self.assertEqual((lead["web"], lead["facebook"]), ("", "https://www.facebook.com/cigarbar"))
        lead = contacto_web.normalizar_canales({"web": "https://maps.app.goo.gl/abc"})
        self.assertEqual((lead["web"], lead["maps_url"]), ("", "https://maps.app.goo.gl/abc"))


class TestMensajeTelegram(unittest.TestCase):
    def _lead_google(self, *, fixture=FIXTURE, pais="Aruba", **extra):
        lead = places._normalizar_place(json.loads(fixture.read_text(encoding="utf-8"))["places"][1], pais)
        lead["tipo"] = lead["tipo_negocio"]
        lead.update(extra)
        return lead

    def test_mensaje_con_todos_los_campos(self):
        lead = self._lead_google(fixture=FIXTURE_FLORIDA, pais="Florida")
        msg = mensaje_prospecto_completo(lead, "Florida")
        for esperado in (
            "La Casa del Habano Miami",
            "Shop · Miami",
            "Teléfono confirmado",
            "your cigar shop",
        ):
            self.assertIn(esperado, msg)
        self.assertIn("Brickell Mall", lead["direccion"])
        self.assertIn("Miami, FL", lead["direccion"])
        self.assertEqual((lead["rating"], lead["user_rating_count"]), (4.8, 40))
        self.assertEqual(lead["telefono"], "(305) 555-0222")
        self.assertEqual(lead["telefono_internacional"], "+13055550222")
        self.assertEqual(lead["instagram"], "https://www.instagram.com/casadelhabanomiami/")
        self.assertEqual(lead["web"], "")
        botones = teclado_prospecto(lead, "Florida", "test")
        urls = [b.get("url", "") for fila in botones["inline_keyboard"] for b in fila]
        self.assertTrue(any(url.startswith(
            "https://wa.me/13055550222?text=Hello%20La%20Casa%20del%20Habano%20Miami"
        ) for url in urls))
        self.assertIn(lead["maps_url"], urls)
        self.assertIn("query_place_id=ChIJ-casa-habano-miami-test", lead["maps_url"])
        self.assertNotIn("🌐 Web:", msg)
        self.assertNotIn("STOP", msg)
        self.assertNotIn("Versión correo", msg)
        self.assertLessEqual(len(msg), 4096)

    def test_con_correo_agrega_version_correo_con_stop(self):
        from urllib.parse import unquote

        lead = self._lead_google(correo="info@casadelhabano.aw")
        msg = mensaje_prospecto_completo(lead, "Florida")
        botones = teclado_prospecto(lead, "Florida", "test")
        urls = [b.get("url", "") for fila in botones["inline_keyboard"] for b in fila]
        correo = next(unquote(url) for url in urls if url.startswith("mailto:"))
        self.assertIn("info@casadelhabano.aw", correo)
        self.assertIn("reply STOP", correo)
        self.assertNotIn("STOP", msg)

    def test_sin_telefono_ni_web_entra_y_lo_dice_en_el_aviso(self):
        lead = places._normalizar_place(json.loads(FIXTURE.read_text(encoding="utf-8"))["places"][3], "Aruba")
        self.assertFalse(tiene_medio_contacto(lead))
        self.assertFalse(lead.get("telefono"))
        self.assertFalse(lead.get("web"))
        msg = mensaje_prospecto_completo(lead, "Florida")
        self.assertIn("Sin teléfono ni correo", msg)
        botones = teclado_prospecto(lead, "Florida", "test")
        urls = [b.get("url", "") for fila in botones["inline_keyboard"] for b in fila]
        self.assertIn(lead["maps_url"], urls)
        self.assertFalse(any("wa.me" in url for url in urls))
        self.assertTrue(enviar_prospecto_telegram(lead, "Florida", simulado=True))
        fila = entrada_sin_contacto(lead)
        self.assertIn("query_place_id=ChIJ-smoke-lounge-aw", fila["maps_url"])
        self.assertEqual(fila["web"], "")

    def test_solo_instagram_es_canal_real(self):
        self.assertTrue(tiene_medio_contacto({"instagram": "https://www.instagram.com/x"}))
        self.assertFalse(tiene_medio_contacto({"maps_url": "https://maps.google.com/?cid=1"}))

    def test_wa_me_solo_con_numero_internacional(self):
        self.assertNotIn("wa.me", mensaje_prospecto_completo(
            {"nombre": "X Cigars", "tipo": "tienda", "telefono": "583 1111"}, "Aruba"))


class TestIdiomaYPlantillas(unittest.TestCase):
    def test_idioma_por_isla(self):
        for isla in ("Florida", "Texas", "California", "New York", "Virginia", "Jamaica",
                     "District of Columbia", "Alaska", "Hawaii"):
            with self.subTest(isla=isla):
                self.assertEqual(idioma_para_pais(isla), "en")
        for isla in ("Puerto Rico", "puerto rico", "PUERTO RICO"):
            with self.subTest(isla=isla):
                self.assertEqual(idioma_para_pais(isla), "es")
        self.assertEqual(idioma_para_pais("Puerto Rico"), "es")
        self.assertEqual(idioma_para_lead("Jamaica", idioma_web="es", web="https://x-shop.jm/"), "en")

    def test_tipo_traducido(self):
        self.assertEqual(tipo_en_idioma("tienda", "en"), "cigar shop")
        self.assertEqual(tipo_en_idioma("tienda", "fr"), "cave à cigares")
        self.assertEqual(tipo_en_idioma("tienda", "es"), "tabaquería")
        for idioma in ("en", "fr", "es", "nl"):
            for tipo in ("tienda", "lounge", "distribuidor", "duty_free", "hotel", "casino"):
                texto = borrador_corto("Shop", idioma, tipo) + borrador_correo("Shop", idioma, tipo)
                self.assertNotIn("tienda", texto.replace("tienda duty free", ""))
                self.assertNotIn("duty_free", texto)

    def test_corto_sin_stop_y_correo_con_stop(self):
        corto = borrador_corto("Cigar House", "en", "tienda")
        correo = borrador_correo("Cigar House", "en", "tienda")
        self.assertIn("your cigar shop", corto)
        self.assertNotIn("STOP", corto)
        self.assertIn("reply STOP", correo)
        for texto in (corto, correo):
            self.assertIn("free sample", texto.lower())
            self.assertIn("Cazador de Sueño Cigars SRL", texto)
            self.assertIn("Yaniris Agustina Ureña", texto)
            self.assertNotIn("this week", texto.lower())
        self.assertIn("votre cave à cigares", borrador_corto("Cave", "fr", "tienda"))
        self.assertIn("su tabaquería", borrador_corto("Tabaquería", "es", "tienda"))


class TestCeroYReintento(unittest.TestCase):
    def test_aviso_cero_dice_el_motivo(self):
        from b2b.telegram_buscar import texto_cero_prospectos

        self.assertIn("error de Google (HTTP 403)", texto_cero_prospectos({"google_error": "HTTP 403"}))
        self.assertIn("presupuesto de Google agotado", texto_cero_prospectos({"presupuesto": True}))
        self.assertIn("todo repetido (3)", texto_cero_prospectos({"repetidos": 3}))
        texto = texto_cero_prospectos({"descartes": [{"motivo": "Google: CLOSED_PERMANENTLY"}, {"motivo": "Google: CLOSED_PERMANENTLY"}]})
        self.assertIn("Google: CLOSED_PERMANENTLY ×2", texto)

    def test_failed_se_puede_reintentar(self):
        from b2b.buscar_filtros import clasificar_novedad_detalle
        from b2b.leads_store import marcar_visto

        raiz = Path(tempfile.mkdtemp())
        cola = raiz / "cola"
        failed = cola / "failed"
        failed.mkdir(parents=True)
        lead = {
            "nombre": "Caribbean Cigar Company",
            "pais": "Aruba",
            "place_id": "ChIJ-caribbean",
            "web": "https://caribbean-cigar.example/",
            "fuente": "google_places",
        }
        (failed / "caribbean.json").write_text(json.dumps(lead), encoding="utf-8")
        with mock.patch.dict(os.environ, {"B2B_QUEUE_DIR": str(raiz)}):
            marcar_visto(lead["place_id"], lead["web"])
            nuevos, repetidos, _det = clasificar_novedad_detalle([dict(lead)], cola)
        self.assertEqual([l["nombre"] for l in nuevos], ["Caribbean Cigar Company"])
        self.assertEqual(repetidos, [])
        inbox = cola / "inbox"
        inbox.mkdir()
        (inbox / "caribbean.json").write_text(json.dumps(lead), encoding="utf-8")
        nuevos2, repetidos2, _det2 = clasificar_novedad_detalle([dict(lead)], cola)
        self.assertEqual(nuevos2, [])
        self.assertEqual(len(repetidos2), 1)

    def test_telegram_401_no_aborta(self):
        lead = {
            "nombre": "Caribbean Cigar Company",
            "pais": "Aruba",
            "place_id": "ChIJ-caribbean",
            "maps_url": "https://maps.google.com/?cid=1",
            "fuente": "google_places",
            "tipo": "tienda",
        }
        from b2b import telegram_gestion

        with mock.patch("telegram_bot.enviar_mensaje_telegram", side_effect=RuntimeError("Telegram respondió 401: unauthorized")), \
                mock.patch("telegram_bot.load_local_env"), \
                mock.patch.object(telegram_gestion, "PENDIENTES_PATH", Path(tempfile.mkdtemp()) / "pend.json"):
            ok = enviar_prospecto_telegram(lead, "Aruba")
        self.assertFalse(ok)

    def test_osm_tiene_tope_de_tiempo(self):
        from b2b import osm_places

        self.assertEqual(osm_places.OVERPASS_TIMEOUT_SEC, 15)
        self.assertEqual(osm_places._REINTENTOS_ISLA, 2)
        self.assertEqual(osm_places._TOPE_SEGUNDOS_ISLA, 120)


if __name__ == "__main__":
    unittest.main()
