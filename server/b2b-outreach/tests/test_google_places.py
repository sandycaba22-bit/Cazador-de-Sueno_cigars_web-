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
from b2b.telegram_prospecto import enviar_prospecto_telegram, mensaje_prospecto_completo  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "google_places_new_aruba.json"
CLAVE_FALSA = "AIzaSyFAKE-test-key-0123456789abcdefghij"
MASCARA_PEDIDA = (
    "places.id,places.displayName,places.formattedAddress,places.nationalPhoneNumber,"
    "places.websiteUri,places.rating,places.userRatingCount,places.businessStatus,places.types"
)
MAPS_EMPORIUM = (
    "https://www.google.com/maps/search/?api=1&query=Aruba%20Cigar%20Emporium"
    "&query_place_id=ChIJ-emporium-aw"
)
DESCARTES_FIXTURE = [
    "Google: CLOSED_PERMANENTLY",
    "Google: sin teléfono",
    "Google: rating 3.6 (mínimo 4.0)",
    "Google: 2 reseñas (mínimo 5)",
    "Google: sin sitio web",
]


class _Respuesta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class GoogleBase(unittest.TestCase):
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
        for var in ("GOOGLE_PLACES_MAX_CALLS_PER_DAY", "MAX_PLACES_CALLS_DIA", "GOOGLE_PLACES_MAX_CALLS_PER_RUN",
                    "GOOGLE_PLACES_MIN_RATING", "GOOGLE_PLACES_MIN_RESENAS"):
            os.environ.pop(var, None)
        self.peticiones: list = []

    def tearDown(self):
        places._GOOGLE_DESACTIVADO.clear()
        for p in reversed(self.patches):
            p.stop()

    def _urlopen_ok(self, request, timeout=0):
        self.peticiones.append(request)
        return _Respuesta(FIXTURE.read_bytes())


class TestLlamadaApi(GoogleBase):
    def test_un_post_por_busqueda_con_mascara_exacta_y_sin_details(self):
        with mock.patch.object(places.urllib.request, "urlopen", side_effect=self._urlopen_ok):
            leads, llamadas, stats = places.buscar_google_pais("Aruba", ["tienda", "lounge"])
        consultas = [c for _t, _i, c in places.consultas_google("Aruba", ["tienda", "lounge"])]
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

    def test_terminos_en_idioma_local(self):
        aruba = [c for _t, _i, c in places.consultas_google("Aruba", [])]
        self.assertIn("cigar shop Aruba", aruba)
        self.assertIn("cigar lounge Aruba", aruba)
        self.assertIn("sigarenwinkel Aruba", aruba)
        self.assertIn("tabaquería Aruba", aruba)
        self.assertIn("tobacconist Aruba", aruba)
        martinica = [c for _t, _i, c in places.consultas_google("Martinique", [])]
        self.assertIn("cave à cigares Martinique", martinica)
        self.assertNotIn("tabaquería Martinique", martinica)
        pr = [c for _t, _i, c in places.consultas_google("Puerto Rico", [])]
        self.assertIn("tabaquería Puerto Rico", pr)

    def test_solo_negocios_seguros_ordenados_y_canales(self):
        with mock.patch.object(places.urllib.request, "urlopen", side_effect=self._urlopen_ok):
            leads, _ll, stats = places.buscar_google_pais("Aruba", ["tienda"])
        self.assertEqual([l["nombre"] for l in leads], ["La Casa del Habano Aruba", "Aruba Cigar Emporium"])
        self.assertEqual([d["motivo"] for d in stats["descartes"]], DESCARTES_FIXTURE)
        self.assertTrue(all(d["etapa"] == "google_negocio_seguro" for d in stats["descartes"]))
        casa, emporium = leads
        self.assertEqual(casa["web"], "")
        self.assertEqual(casa["instagram"], "https://www.instagram.com/casadelhabanoaruba/")
        self.assertEqual(emporium["web"], "https://www.arubacigaremporium.aw/")
        self.assertEqual(emporium["telefono"], "583 1111")
        self.assertEqual(emporium["telefono_internacional"], "+2975831111")
        self.assertEqual(emporium["maps_url"], MAPS_EMPORIUM)
        for lead in leads:
            self.assertNotIn("maps", lead["web"])

    def test_umbral_de_resenas_y_rating_configurable(self):
        raw = {"businessStatus": "OPERATIONAL", "nationalPhoneNumber": "1", "websiteUri": "https://a.aw/",
               "rating": 4.0, "userRatingCount": 5}
        self.assertEqual(places.motivo_no_seguro(raw), "")
        with mock.patch.dict(os.environ, {"GOOGLE_PLACES_MIN_RESENAS": "10", "GOOGLE_PLACES_MIN_RATING": "4.5"}):
            self.assertEqual(places.motivo_no_seguro(raw), "Google: rating 4.0 (mínimo 4.5)")
            self.assertEqual(places.motivo_no_seguro({**raw, "rating": 4.7}), "Google: 5 reseñas (mínimo 10)")
        self.assertEqual(places.motivo_no_seguro({**raw, "rating": None}), "Google: sin valoraciones")
        self.assertEqual(places.motivo_no_seguro({**raw, "websiteUri": "https://maps.google.com/?cid=1"}),
                         "Google: sin sitio web")

    def test_cache_no_repite_isla_en_el_mes(self):
        with mock.patch.object(places.urllib.request, "urlopen", side_effect=self._urlopen_ok):
            primeros, ll1, _ = places.buscar_google_pais("Aruba", ["tienda"])
            segundos, ll2, stats2 = places.buscar_google_pais("Aruba", ["tienda"])
        self.assertGreater(ll1, 0)
        self.assertEqual(ll2, 0)
        self.assertEqual(stats2["google_cache"], ll1)
        self.assertEqual([l["place_id"] for l in primeros], [l["place_id"] for l in segundos])
        self.assertTrue(places.isla_buscada_este_mes("Aruba", [c for _t, _i, c in places.consultas_google("Aruba", ["tienda"])]))
        cache = json.loads((self.tmp / "google_places_cache.json").read_text(encoding="utf-8"))
        self.assertIn("ChIJ-emporium-aw", cache["places"])


class TestPresupuesto(GoogleBase):
    def test_tope_diario_para_y_avisa_una_vez(self):
        os.environ["GOOGLE_PLACES_MAX_CALLS_PER_DAY"] = "2"
        with mock.patch.object(places.urllib.request, "urlopen", side_effect=self._urlopen_ok), \
                mock.patch("b2b.telegram_buscar.notificar_buscar") as aviso:
            _l, llamadas, stats = places.buscar_google_pais("Aruba", ["tienda", "lounge"])
            places.buscar_google_pais("Curacao", ["tienda"])
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

    def test_4xx_y_5xx_conmutan_a_osm(self):
        for codigo in (400, 429, 500, 503):
            with self.subTest(codigo=codigo):
                places._GOOGLE_DESACTIVADO.clear()
                self.peticiones.clear()
                with mock.patch.object(places.urllib.request, "urlopen", side_effect=self._error(codigo)), \
                        mock.patch.object(places, "_buscar_osm", return_value=(self.OSM, 1, {"descartes": []})), \
                        mock.patch.object(places, "_notificar"):
                    leads, _ll, stats = places.buscar_en_pais("Aruba", ["tienda"], 5, fuente="google")
                    leads2, _l2, stats2 = places.buscar_en_pais("Curacao", ["tienda"], 5, fuente="ambas")
                self.assertEqual([l["nombre"] for l in leads], ["Tabaco OSM"])
                self.assertIn(str(codigo), stats["google_error"])
                self.assertEqual(len(self.peticiones), 1)
                self.assertEqual([l["nombre"] for l in leads2], ["Tabaco OSM"])
                self.assertIn(f"HTTP {codigo}", stats2["google_omitido"])

    def test_sin_respuesta_conmuta_a_osm(self):
        with mock.patch.object(places.urllib.request, "urlopen", side_effect=TimeoutError("timed out")), \
                mock.patch.object(places, "_buscar_osm", return_value=(self.OSM, 1, {"descartes": []})), \
                mock.patch.object(places, "_notificar") as aviso:
            leads, _ll, stats = places.buscar_en_pais("Aruba", ["tienda"], 5, fuente="google")
        self.assertEqual([l["nombre"] for l in leads], ["Tabaco OSM"])
        self.assertIn("no respondió", aviso.call_args[0][0])

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
        self.assertEqual([l["nombre"] for l in leads], ["La Casa del Habano Aruba", "Aruba Cigar Emporium"])
        self.assertIn("502", stats["google_error"])


class TestTelefonoInternacional(unittest.TestCase):
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
        with mock.patch.object(places.urllib.request, "urlopen", side_effect=self._urlopen_ok):
            self.assertFalse(places.islas_agotadas_google(["Aruba"]))
            places.buscar_google_pais("Aruba", ["tienda", "lounge"])
        self.assertTrue(places.islas_agotadas_google(["Aruba"]))
        self.assertFalse(places.islas_agotadas_google(["Aruba", "Curacao"]))
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

        with mock.patch.object(buscar_global, "siguiente_pais_cola", side_effect=[None, {"pais": "Aruba"}]), \
                mock.patch.object(buscar_global, "guardar_estado_global") as guardar, \
                mock.patch.object(prospector, "registrar_evento"), \
                mock.patch.object(prospector, "resolver_fuente_leads", return_value="ambas"), \
                mock.patch.object(prospector, "prospectar_un_pais", return_value={"pais": "Aruba"}) as uno:
            out = prospector.prospectar_turno_global(None, 9, self.tmp / "inbox", solo_listar=True)
        guardar.assert_called_once_with({"pais_idx": 0, "celda_idx": 0, "completo": False, "pais": ""})
        self.assertEqual(uno.call_args[0][0]["pais"], "Aruba")
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
    def test_sin_clave_solo_osm_sin_fallar(self):
        osm = [{"nombre": "Tabaco OSM", "pais": "Aruba", "place_id": "osm:node/1",
                "telefono": "+297 5800000", "fuente": "openstreetmap"}]
        with mock.patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": ""}):
            for valor in ("google", "ambas", "auto"):
                with mock.patch.dict(os.environ, {"FUENTE_LEADS": valor}):
                    self.assertEqual(resolver_fuente_leads(), "osm")
            with mock.patch.object(places, "_buscar_osm", return_value=(osm, 1, {"descartes": []})), \
                    mock.patch.object(places.urllib.request, "urlopen") as red:
                leads, _ll, stats = places.buscar_en_pais("Aruba", ["tienda"], 5, fuente="ambas")
        red.assert_not_called()
        self.assertEqual([l["nombre"] for l in leads], ["Tabaco OSM"])
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

        osm = [{"nombre": "Tabaco OSM", "pais": "Aruba", "place_id": "osm:node/1", "telefono": "+297 5800000"}]
        with mock.patch.object(places.urllib.request, "urlopen", side_effect=_403), \
                mock.patch.object(places, "registrar_evento") as evento, \
                mock.patch.object(places, "_buscar_osm", return_value=(osm, 1, {"descartes": []})):
            leads, _ll, stats = places.buscar_en_pais("Aruba", ["tienda"], 5, fuente="google")
            leads2, _l2, stats2 = places.buscar_en_pais("Curacao", ["tienda"], 5, fuente="google")
        self.assertEqual(len(leads), 1)
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
        self.assertEqual(nombres, ["La Casa del Habano Aruba", "Aruba Cigar Emporium", "Tabaquería San Nicolas"])
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
        self.assertEqual(c["nuevos"], 1)
        self.assertEqual(c["dudosos"], 1)
        self.assertEqual(c["sin_contacto"], 0)
        encolados = [json.loads(p.read_text(encoding="utf-8")) for p in inbox.glob("*.json")]
        self.assertEqual([e["nombre"] for e in encolados], ["Aruba Cigar Emporium"])
        self.assertEqual(encolados[0]["maps_url"], MAPS_EMPORIUM)
        self.assertTrue(encolados[0]["vende_cigarros"])
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
    def _lead_google(self, **extra):
        lead = places._normalizar_place(json.loads(FIXTURE.read_text(encoding="utf-8"))["places"][1], "Aruba")
        lead["tipo"] = lead["tipo_negocio"]
        lead.update(extra)
        return lead

    def test_mensaje_con_todos_los_campos(self):
        msg = mensaje_prospecto_completo(self._lead_google(), "Aruba")
        for esperado in (
            "PROSPECTO · Aruba",
            "La Casa del Habano Aruba",
            "Tipo: tabaquería",
            "Renaissance Mall",
            "⭐ 4.8 (40 reseñas)",
            "📞 Teléfono: 588 2222",
            "https://wa.me/2975882222?text=Hello%20La%20Casa%20del%20Habano",
            "📸 Instagram: https://www.instagram.com/casadelhabanoaruba/",
            "🗺️ Google Maps: https://www.google.com/maps/search/?api=1&query=La%20Casa%20del%20Habano%20Aruba"
            "&query_place_id=ChIJ-casa-habano-aw",
            "your cigar shop",
        ):
            self.assertIn(esperado, msg)
        self.assertNotIn("🌐 Web:", msg)
        self.assertNotIn("STOP", msg)
        self.assertNotIn("Versión correo", msg)
        self.assertLessEqual(len(msg), 4096)

    def test_con_correo_agrega_version_correo_con_stop(self):
        msg = mensaje_prospecto_completo(self._lead_google(correo="info@casadelhabano.aw"), "Aruba")
        self.assertIn("Versión correo", msg)
        self.assertIn("reply STOP", msg)

    def test_solo_mapa_va_a_sin_contacto_sin_borrador(self):
        lead = places._normalizar_place(json.loads(FIXTURE.read_text(encoding="utf-8"))["places"][3], "Aruba")
        self.assertFalse(tiene_medio_contacto(lead))
        self.assertFalse(enviar_prospecto_telegram(lead, "Aruba", simulado=True))
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
        for isla in ("Aruba", "Curazao", "Sint Maarten", "Bahamas", "Caimán", "Jamaica", "Barbados",
                     "Turcos y Caicos", "Trinidad"):
            with self.subTest(isla=isla):
                self.assertEqual(idioma_para_pais(isla), "en")
        for isla in ("Saint Martin", "Guadalupe", "Martinica"):
            with self.subTest(isla=isla):
                self.assertEqual(idioma_para_pais(isla), "fr")
        self.assertEqual(idioma_para_pais("Puerto Rico"), "es")
        self.assertEqual(idioma_para_lead("Sint Maarten", idioma_web="nl", web="https://x-shop.sx/"), "en")

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
            self.assertIn("commercial samples available for licensed retailers", texto.lower())
            self.assertNotIn("this week", texto.lower())
        self.assertIn("votre cave à cigares", borrador_corto("Cave", "fr", "tienda"))
        self.assertIn("su tabaquería", borrador_corto("Tabaquería", "es", "tienda"))


if __name__ == "__main__":
    unittest.main()
