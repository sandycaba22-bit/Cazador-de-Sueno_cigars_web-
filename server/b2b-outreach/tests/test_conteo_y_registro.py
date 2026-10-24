"""Registro de leads sin enlaces de mapa, aislamiento de --simulado y conteo por categoría."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import prospector  # noqa: E402
from b2b import leads_store as ls  # noqa: E402
from b2b import paths  # noqa: E402
from b2b.buscar_filtros import clave_dedupe, dedupe_y_fusionar  # noqa: E402
from b2b.calidad_lead import StatsCalidad  # noqa: E402
from b2b.telegram_buscar import texto_conteo_isla  # noqa: E402
from b2b.website import dominio_negocio, es_url_mapa  # noqa: E402

MAPAS = [
    "https://www.openstreetmap.org/node/123",
    "https://maps.google.com/?cid=1",
    "https://g.page/negocio",
    "https://goo.gl/maps/abc",
    "https://maps.app.goo.gl/xyz",
    "https://www.google.com/maps/place/Foo",
    "https://lh3.googleusercontent.com/p/abc",
]


class TestUrlsMapa(unittest.TestCase):
    def test_mapas_no_son_dominio_de_negocio(self):
        for url in MAPAS:
            with self.subTest(url=url):
                self.assertTrue(es_url_mapa(url))
                self.assertEqual(dominio_negocio(url), "")

    def test_web_propia_si(self):
        self.assertFalse(es_url_mapa("https://www.cigarbar.aw/contact"))
        self.assertEqual(dominio_negocio("https://www.cigarbar.aw/contact"), "cigarbar.aw")
        self.assertEqual(dominio_negocio("https://www.google.com/"), "google.com")


class TestRegistroLeads(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.seen = self.tmp / "registro_leads.json"
        self.patch = mock.patch.object(ls, "SEEN_PATH", self.seen)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def test_marcar_visto_ignora_mapas(self):
        for url in MAPAS:
            ls.marcar_visto("", url)
        data = json.loads(self.seen.read_text(encoding="utf-8"))
        self.assertEqual(data["dominios"], [])

    def test_ya_visto_ignora_mapas_aunque_el_registro_este_contaminado(self):
        self.seen.write_text(
            json.dumps({"place_ids": [], "dominios": ["openstreetmap.org", "maps.google.com"]}),
            encoding="utf-8",
        )
        for url in MAPAS:
            with self.subTest(url=url):
                self.assertFalse(ls.ya_visto("", url))

    def test_web_real_si_se_registra(self):
        ls.marcar_visto("osm:node/1", "https://cigarbar.aw/")
        self.assertTrue(ls.ya_visto("", "https://www.cigarbar.aw/menu"))
        self.assertTrue(ls.ya_visto("osm:node/1", ""))

    def test_fixtures_y_dominios_de_prueba_no_se_registran(self):
        ls.marcar_visto("fixture-lounge", "https://demo.test/")
        ls.marcar_visto("", "https://example.com/")
        data = json.loads(self.seen.read_text(encoding="utf-8"))
        self.assertEqual(data, {"place_ids": [], "dominios": []})
        self.assertFalse(ls.ya_visto("fixture-lounge", ""))


class TestDedupeEnlacesOsm(unittest.TestCase):
    def test_seis_leads_osm_con_place_id_distinto_son_seis(self):
        leads = [
            {"nombre": f"Cigar Shop {i}", "pais": "Florida", "place_id": f"osm:{t}/{i}",
             "web": f"https://www.openstreetmap.org/{t}/{i}", "fuente": "osm"}
            for i, t in zip(range(1, 7), ("node", "way", "node", "way", "node", "node"))
        ]
        fusiones: list[dict] = []
        salida = dedupe_y_fusionar(leads, [], fusiones)
        self.assertEqual(len(salida), 6)
        self.assertEqual(fusiones, [])
        self.assertEqual(len({clave_dedupe(l) for l in leads}), 6)
        self.assertTrue(all(clave_dedupe(l).startswith("id:osm:") for l in leads))

    def test_place_id_antes_que_telefono(self):
        a = {"nombre": "Cigar A", "place_id": "osm:node/1", "telefono": "+297 5800000"}
        b = {"nombre": "Cigar A", "place_id": "osm:node/2", "telefono": "+297 5800000"}
        self.assertNotEqual(clave_dedupe(a), clave_dedupe(b))
        self.assertEqual(clave_dedupe({"web": "https://cigar.aw/", "place_id": "osm:node/9"}), "dom:cigar.aw")

    def test_fusion_deja_rastro(self):
        leads = [
            {"nombre": "Cigar Bar Uno", "web": "https://cigarbar.aw/", "place_id": "osm:node/1"},
            {"nombre": "Cigar Bar Uno (dealer)", "web": "https://www.cigarbar.aw/es", "fuente": "dealer:x"},
        ]
        fusiones: list[dict] = []
        self.assertEqual(len(dedupe_y_fusionar(leads, [], fusiones)), 1)
        self.assertEqual(len(fusiones), 1)
        f = fusiones[0]
        self.assertEqual(f["motivo"], "fusionado_misma_clave")
        self.assertEqual(f["nombres"], ["Cigar Bar Uno", "Cigar Bar Uno (dealer)"])
        self.assertEqual(f["clave"], "dom:cigarbar.aw")

    def test_buscar_pais_reporta_fusiones_en_descartes(self):
        from b2b import buscar_pais as bp

        osm = [
            {"nombre": "Cigar Bar Uno", "pais": "Puerto Rico", "web": "https://cigarbar.aw/",
             "place_id": "osm:node/1", "fuente": "osm"},
            {"nombre": "Cigar Bar Uno", "pais": "Puerto Rico", "web": "https://cigarbar.aw/",
             "place_id": "osm:node/2", "fuente": "osm"},
            {"nombre": "Tabaco Dos", "pais": "Puerto Rico", "web": "https://www.openstreetmap.org/node/3",
             "place_id": "osm:node/3", "fuente": "osm"},
        ]
        with mock.patch.object(bp, "buscar_en_pais_osm", return_value=(osm, 0, {"descartes": []})), \
                mock.patch.object(bp, "buscar_dealers_pais", return_value=([], [])), \
                mock.patch.object(bp, "buscar_directorios_pais", return_value=([], [])), \
                mock.patch.object(bp, "registrar_evento"):
            leads, _ll, stats = bp.recolectar_leads_pais("Puerto Rico", ["tienda"], 10, "", simulado=False)
        self.assertEqual(len(leads), 2)
        motivos = [d.get("motivo") for d in stats["descartes"]]
        self.assertIn("fusionado_misma_clave", motivos)
        self.assertEqual(len(leads) + motivos.count("fusionado_misma_clave"), len(osm))


class TestSimuladoAislado(unittest.TestCase):
    def test_state_file_y_logs_van_a_temporal(self):
        with mock.patch.dict(os.environ, {"B2B_SIMULADO": "1", "B2B_DATA_DIR": "/var/lib/prod"}):
            self.assertEqual(paths.state_file("registro_leads.json").parent, paths.dir_simulado() / "data")
            self.assertEqual(ls.seen_path(), paths.dir_simulado() / "data" / "registro_leads.json")
            self.assertEqual(paths.log_dir(), paths.dir_simulado() / "logs")

    def test_prospectar_simulado_no_toca_registro_real(self):
        real = paths.state_file("registro_leads.json")
        antes = real.read_bytes() if real.is_file() else None
        inbox = Path(tempfile.mkdtemp()) / "cola" / "inbox"
        with mock.patch.object(prospector.time, "sleep"), mock.patch(
            "telegram_bot.load_local_env"
        ), mock.patch("b2b.telegram_control.procesar_comandos_chat", return_value=[]):
            prospector.prospectar("Florida", 2, inbox, simulado=True)
        despues = real.read_bytes() if real.is_file() else None
        self.assertEqual(antes, despues)
        self.assertNotIn("B2B_SIMULADO", os.environ)


def _lead(i: int, **extra) -> dict:
    base = {
        "nombre": f"Lead {i}",
        "pais": "Jamaica",
        "place_id": f"osm:node/{i}",
        "web": f"https://www.openstreetmap.org/node/{i}",
        "direccion": f"Calle {i}, Kingston",
        "fuente": "osm",
        "tipo_negocio": "tienda",
        "telefono": f"+1876555{i:04d}",
    }
    base.update(extra)
    return base


class TestConteoIsla(unittest.TestCase):
    """Escenario tipo Jamaica: todas las categorías deben sumar 'encontrados'."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.env = mock.patch.dict(
            os.environ,
            {"B2B_DATA_DIR": str(self.tmp / "data"), "B2B_LOG_DIR": str(self.tmp / "logs")},
        )
        self.env.start()
        self.seen = mock.patch.object(ls, "SEEN_PATH", self.tmp / "data" / "registro_leads.json")
        self.seen.start()
        ls.marcar_visto("osm:node/2", "")

    def tearDown(self):
        self.seen.stop()
        self.env.stop()

    def test_suma_de_categorias_igual_a_encontrados(self):
        leads = [
            _lead(1),
            _lead(2),
            _lead(3, telefono=""),
            _lead(4, nombre="Dudoso"),
            _lead(5, nombre="Malo"),
            _lead(6),
            _lead(7),
        ]
        descartes_fuente = [{"nombre": "Sin nombre OSM", "motivo": "sin nombre", "etapa": "osm"}]

        def fake_clasificar(items):
            acept = [l for l in items if l["nombre"] not in ("Dudoso", "Malo")]
            dud = [dict(l, calidad_motivo="tipo dudoso") for l in items if l["nombre"] == "Dudoso"]
            desc = [{"nombre": "Malo", "motivo": "no vende cigarros", "etapa": "calidad"}]
            return acept, dud, [], desc, StatsCalidad(aceptados=len(acept), dudosos=len(dud))

        inbox = self.tmp / "cola" / "inbox"
        reglas = {"pais": "Jamaica", "idioma": "en"}
        with mock.patch.object(
            prospector, "buscar_en_pais", return_value=(leads, 0, {"descartes": descartes_fuente})
        ), mock.patch.object(prospector, "clasificar_lote", side_effect=fake_clasificar), mock.patch.object(
            prospector, "enriquecer_lead", side_effect=lambda lead, _r, **_kw: dict(lead, puntaje=9)
        ), mock.patch.object(prospector, "califica_lead", return_value=True), mock.patch.object(
            prospector, "priorizar_leads_contacto", side_effect=list
        ), mock.patch.object(
            prospector.time, "sleep"
        ):
            stats = prospector.prospectar_un_pais(
                reglas, 2, inbox, fuente="osm", notificar_telegram_buscar=False
            )

        c = stats["conteo"]
        self.assertEqual(c["encontrados"], 8)
        self.assertEqual(c["sin_clasificar"], 0)
        self.assertEqual(c["repetidos"], 1)
        self.assertEqual(c["descartados"], 2)
        self.assertEqual(c["dudosos"], 1)
        self.assertEqual(c["sin_contacto"], 1)
        self.assertEqual(c["encolados"], 2)
        self.assertEqual(c["nuevos"], 2)
        self.assertEqual(c["pendiente_limite"], 1)
        suma = sum(c[k] for k in prospector.CATEGORIAS_RESUMEN)
        self.assertEqual(suma, c["encontrados"])

        archivos = list((self.tmp / "data").glob("sin_contacto_*.json"))
        self.assertEqual(len(archivos), 1)
        fila = json.loads(archivos[0].read_text(encoding="utf-8"))["islas"]["Jamaica"][0]
        self.assertEqual(
            (fila["nombre"], fila["fuente"], fila["direccion"]), ("Lead 3", "osm", "Calle 3, Kingston")
        )

        texto = texto_conteo_isla("Jamaica", c, stats["descartes"])
        self.assertIn("8 encontrados = 2 nuevos · 1 repetidos · 2 descartados · 1 dudosos", texto)
        self.assertIn("1 sin contacto", texto)
        self.assertNotIn("sin clasificar", texto)

    def test_aviso_si_no_cuadra(self):
        c = prospector.conteo_isla(encontrados=3, descartados=0, repetidos=0, resultado={"encolados": [1]})
        self.assertEqual(c["sin_clasificar"], 2)
        self.assertIn("2 sin clasificar", texto_conteo_isla("X", c))


if __name__ == "__main__":
    unittest.main()
