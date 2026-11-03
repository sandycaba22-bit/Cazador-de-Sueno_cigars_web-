"""Horario local del negocio: ventanas, cambios de hora, tope de 24 h y seguimientos."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from b2b.envio_correo import encolar_envio, procesar_outbox
from b2b.zona_horaria import (
    en_ventana,
    frase_programado,
    ordenar_ola,
    primer_hueco,
    resolver_zona,
)

DIR = "Calle La Barranquita, Sector Las Minas, Calle 3, Edificio 3, Santiago de los Caballeros, República Dominicana"
NY = ZoneInfo("America/New_York")
LA = ZoneInfo("America/Los_Angeles")
RD = ZoneInfo("America/Santo_Domingo")


def _lead(**extra):
    base = {
        "nombre": "Prime Cigar",
        "correo": "info@primecigar.example",
        "web": "https://primecigar.example",
        "idioma": "en",
        "tipo": "lounge",
        "pais": "Florida",
        "estado": "Florida",
        "ciudad": "Miami",
        "lat": 25.7617,
        "lon": -80.1918,
        "puntaje": 8,
    }
    base.update(extra)
    return base


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            os.environ,
            {
                "B2B_QUEUE_DIR": self.tmp.name,
                "B2B_DATA_DIR": str(Path(self.tmp.name) / "data"),
                "B2B_ENVIO_REAL": "0",
                "EMPRESA_DIRECCION_POSTAL": DIR,
                "CORREO_REMITENTE_1": "uno@gmail.com",
                "CORREO_CLAVE_1": "clave-1",
                "CORREO_REMITENTE_2": "",
                "CORREO_CLAVE_2": "",
                "EMAIL_REMITENTE_2": "",
                "EMAIL_CLAVE_2": "",
                "B2B_ENVIO_RAMPA": "30,30,30",
                "B2B_ENVIO_FECHA_INICIO": "2026-01-01",
                "B2B_ENVIO_MAX_POR_CUENTA": "15",
                "CORREOS_MAX_DIA": "30",
                "B2B_ENVIO_PAUSA_MIN": "2",
                "B2B_ENVIO_PAUSA_MAX": "2",
                "B2B_ENVIO_VENTANAS_LOCALES": "09:00-11:30,13:30-16:00",
                "B2B_ENVIO_DIAS": "1,2,3,4,5",
                "B2B_ZONA_OPERADOR": "America/Santo_Domingo",
                "SMTP_PORT": "587",
            },
            clear=False,
        )
        self.env.start()
        self.pausa = patch("b2b.telegram_control.esta_pausado", return_value=False)
        self.pausa.start()

    def tearDown(self):
        self.pausa.stop()
        self.env.stop()
        self.tmp.cleanup()


class TestZona(unittest.TestCase):
    def test_panhandle_el_paso_y_arizona_sin_cambio(self):
        pensacola = resolver_zona({"estado": "Florida", "lat": 30.4213, "lon": -87.2169})
        self.assertEqual(pensacola["iana"], "America/Chicago")
        self.assertTrue(pensacola["exacta"])
        el_paso = resolver_zona({"estado": "Texas", "lat": 31.7619, "lon": -106.4850})
        self.assertEqual(el_paso["iana"], "America/Denver")
        dallas = resolver_zona({"estado": "Texas", "lat": 32.7767, "lon": -96.7970})
        self.assertEqual(dallas["iana"], "America/Chicago")
        phoenix = ZoneInfo("America/Phoenix")
        enero = datetime(2027, 1, 15, 18, tzinfo=timezone.utc)
        julio = datetime(2027, 7, 15, 18, tzinfo=timezone.utc)
        self.assertEqual(enero.astimezone(phoenix).utcoffset(), timedelta(hours=-7))
        self.assertEqual(julio.astimezone(phoenix).utcoffset(), timedelta(hours=-7))
        self.assertEqual(ZoneInfo("America/Puerto_Rico").utcoffset(enero), timedelta(hours=-4))
        self.assertEqual(ZoneInfo("America/Puerto_Rico").utcoffset(julio), timedelta(hours=-4))
        self.assertEqual(ZoneInfo("America/Jamaica").utcoffset(enero), timedelta(hours=-5))
        self.assertEqual(ZoneInfo("America/Jamaica").utcoffset(julio), timedelta(hours=-5))

    def test_canada_toronto_cambia_saskatchewan_no(self):
        self.assertEqual(resolver_zona({"estado": "Ontario"})["iana"], "America/Toronto")
        self.assertEqual(resolver_zona({"pais": "Saskatchewan"})["iana"], "America/Regina")
        invierno = datetime(2027, 1, 15, 18, tzinfo=timezone.utc)
        verano = datetime(2027, 7, 15, 18, tzinfo=timezone.utc)
        self.assertNotEqual(
            invierno.astimezone(ZoneInfo("America/Toronto")).utcoffset(),
            verano.astimezone(ZoneInfo("America/Toronto")).utcoffset(),
        )
        regina = ZoneInfo("America/Regina")
        self.assertEqual(invierno.astimezone(regina).utcoffset(), verano.astimezone(regina).utcoffset())

    def test_sin_punto_avisa_que_es_la_zona_del_estado(self):
        info = resolver_zona({"estado": "Florida", "ciudad": "Tampa"})
        self.assertEqual(info["iana"], "America/New_York")
        self.assertFalse(info["exacta"])
        self.assertEqual(info["fuente"], "estado")


class TestVentanas(_Base):
    def test_cambio_de_hora_noviembre_y_marzo(self):
        antes = datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc)
        self.assertEqual(antes.astimezone(NY).utcoffset(), timedelta(hours=-4))
        despues = datetime(2026, 11, 1, 7, 0, tzinfo=timezone.utc)
        self.assertEqual(despues.astimezone(NY).utcoffset(), timedelta(hours=-5))
        hueco = primer_hueco(datetime(2026, 11, 1, 5, 0, tzinfo=timezone.utc), _lead())
        local = hueco.astimezone(NY)
        self.assertEqual((local.hour, local.minute), (9, 0))
        self.assertEqual(local.utcoffset(), timedelta(hours=-5))

        antes_m = datetime(2027, 3, 14, 6, 30, tzinfo=timezone.utc)
        self.assertEqual(antes_m.astimezone(NY).utcoffset(), timedelta(hours=-5))
        despues_m = datetime(2027, 3, 14, 8, 0, tzinfo=timezone.utc)
        self.assertEqual(despues_m.astimezone(NY).utcoffset(), timedelta(hours=-4))
        hueco_m = primer_hueco(antes_m, _lead())
        local_m = hueco_m.astimezone(NY)
        self.assertEqual((local_m.hour, local_m.minute), (9, 0))
        self.assertEqual(local_m.utcoffset(), timedelta(hours=-4))

    def test_aprobada_a_las_3am_rd_sale_a_las_9_de_miami(self):
        ahora = datetime(2026, 11, 3, 3, 0, tzinfo=RD).astimezone(timezone.utc)
        self.assertEqual(ahora.astimezone(NY).hour, 2)
        with patch("b2b.envio_correo.random.randint", return_value=2):
            item = encolar_envio(_lead(), "tok-3am", ahora=ahora)
        cuando = datetime.fromisoformat(item["enviar_despues_de"])
        self.assertEqual(item["estado"], "programado")
        self.assertEqual(cuando.astimezone(NY).strftime("%H:%M"), "09:00")
        self.assertEqual(cuando.astimezone(RD).strftime("%H:%M"), "10:00")
        self.assertEqual(
            frase_programado(cuando, _lead(), ahora),
            "Se enviará hoy 09:00 hora de Miami (10:00 hora RD)",
        )
        with patch("smtplib.SMTP") as smtp:
            self.assertEqual(procesar_outbox(ahora), 0)
        smtp.assert_not_called()

    def test_viernes_por_la_noche_pasa_al_lunes(self):
        viernes = datetime(2026, 11, 6, 23, 30, tzinfo=NY)
        self.assertEqual(viernes.weekday(), 4)
        hueco = primer_hueco(viernes, _lead())
        local = hueco.astimezone(NY)
        self.assertEqual(local.weekday(), 0)
        self.assertEqual(local.date().isoformat(), "2026-11-09")
        self.assertEqual((local.hour, local.minute), (9, 0))

    def test_los_angeles_y_miami_a_la_misma_hora_utc(self):
        ahora = datetime(2026, 11, 4, 15, 0, tzinfo=timezone.utc)
        miami = _lead()
        la = _lead(
            nombre="LA Cigar",
            correo="info@la.example",
            web="https://la.example",
            estado="California",
            pais="California",
            ciudad="Los Angeles",
            lat=34.0522,
            lon=-118.2437,
        )
        self.assertEqual(primer_hueco(ahora, miami), ahora)
        self.assertEqual(primer_hueco(ahora, la).astimezone(LA).strftime("%H:%M"), "09:00")
        self.assertEqual(primer_hueco(ahora, la), datetime(2026, 11, 4, 17, 0, tzinfo=timezone.utc))

    def test_igual_con_tz_utc_y_santo_domingo(self):
        ahora = datetime(2026, 11, 4, 15, 0, tzinfo=timezone.utc)
        lead = _lead(estado="California", pais="California", ciudad="Los Angeles", lat=34.05, lon=-118.24)
        esperado = primer_hueco(ahora, lead)
        for nombre in ("UTC", "America/Santo_Domingo"):
            with patch.dict(os.environ, {"TZ": nombre}):
                self.assertEqual(primer_hueco(ahora, dict(lead)), esperado)

    def test_hueco_de_mediodia_y_defecto_seguro(self):
        mediodia = datetime(2026, 11, 4, 17, 0, tzinfo=timezone.utc)  # 12:00 EST
        self.assertFalse(en_ventana(mediodia, _lead()))
        self.assertEqual(primer_hueco(mediodia, _lead()).astimezone(NY).strftime("%H:%M"), "13:30")
        os.environ.pop("B2B_ENVIO_VENTANAS_LOCALES", None)
        os.environ.pop("B2B_ENVIO_DIAS", None)
        os.environ["B2B_ENVIO_VENTANAS_LOCALES"] = "no-es-una-hora"
        madrugada = datetime(2026, 11, 4, 8, 0, tzinfo=timezone.utc)  # 03:00 EST
        self.assertFalse(en_ventana(madrugada, _lead()))
        domingo = datetime(2026, 11, 8, 15, 0, tzinfo=timezone.utc)
        self.assertFalse(en_ventana(domingo, _lead()))
        self.assertTrue(en_ventana(datetime(2026, 11, 4, 15, 0, tzinfo=timezone.utc), _lead()))

    def test_feriado_del_json_salta_el_dia(self):
        path = Path(self.tmp.name) / "ventanas.json"
        path.write_text(json.dumps({
            "paises": {
                "Florida": {
                    "feriados": ["2026-11-03"],
                    "dias": [1, 2, 3, 4, 5],
                }
            }
        }), encoding="utf-8")
        os.environ["B2B_VENTANAS_PATH"] = str(path)
        martes = datetime(2026, 11, 3, 15, 0, tzinfo=timezone.utc)
        self.assertFalse(en_ventana(martes, _lead()))
        self.assertEqual(primer_hueco(martes, _lead()).astimezone(NY).date().isoformat(), "2026-11-04")

    def test_accion_de_gracias_pasa_al_viernes(self):
        os.environ.pop("B2B_VENTANAS_PATH", None)
        gracias = datetime(2026, 11, 26, 15, 0, tzinfo=timezone.utc)
        self.assertFalse(en_ventana(gracias, _lead()))
        hueco = primer_hueco(gracias, _lead()).astimezone(NY)
        self.assertEqual(hueco.date().isoformat(), "2026-11-27")
        self.assertEqual(hueco.strftime("%H:%M"), "09:00")
        canada = datetime(2026, 7, 1, 15, 0, tzinfo=timezone.utc)
        lead_ca = _lead(pais="Ontario", estado="Ontario", ciudad="Toronto", lat=43.65, lon=-79.38)
        self.assertFalse(en_ventana(canada, lead_ca))
        self.assertEqual(primer_hueco(canada, lead_ca).astimezone(ZoneInfo("America/Toronto")).date().isoformat(), "2026-07-02")


class TestCupo(_Base):
    def test_tope_de_30_en_24_horas_corridas(self):
        from b2b.envio_correo import _load, _save

        ahora = datetime(2026, 11, 4, 15, 0, tzinfo=timezone.utc)
        data = _load()
        antiguo = (ahora - timedelta(hours=20)).isoformat()
        for i in range(30):
            data["envios"].append({
                "correo": f"ya{i}@shop{i}.example",
                "dominio": f"shop{i}.example",
                "cuenta": 1 if i < 15 else 2,
                "ok": True,
                "cuando": antiguo,
            })
        _save(data)
        with patch("b2b.envio_correo.random.randint", return_value=2):
            item = encolar_envio(_lead(correo="nuevo@otra.example", web="https://otra.example"), "tok-31", ahora=ahora)
        cuando = datetime.fromisoformat(item["enviar_despues_de"])
        self.assertGreaterEqual(cuando, datetime.fromisoformat(antiguo) + timedelta(hours=24))
        self.assertNotEqual(cuando, ahora)

    def test_una_sola_cuenta_aunque_la_segunda_este_vacia(self):
        from b2b.envio_correo import cuentas_activas

        ahora = datetime(2026, 11, 4, 15, 0, tzinfo=timezone.utc)
        os.environ["B2B_ENVIO_MAX_POR_CUENTA"] = "15"
        os.environ["CORREO_REMITENTE_2"] = ""
        os.environ["EMAIL_REMITENTE_2"] = "   "
        self.assertEqual([c["n"] for c in cuentas_activas()], [1])
        with patch("b2b.envio_correo.random.randint", return_value=2), patch("smtplib.SMTP") as smtp:
            os.environ["B2B_ENVIO_REAL"] = "1"
            for i in range(4):
                self.assertIsNotNone(encolar_envio(
                    _lead(correo=f"info{i}@shop{i}.example", web=f"https://shop{i}.example", nombre=f"Shop {i}"),
                    f"tok{i}",
                    ahora=ahora,
                ))
            self.assertEqual(procesar_outbox(ahora + timedelta(minutes=20)), 4)
        smtp.assert_called()
        cuentas = []
        archivo = Path(self.tmp.name) / "outbox" / "archivo"
        for path in sorted(archivo.glob("*.json")):
            cuentas.append(json.loads(path.read_text(encoding="utf-8")).get("cuenta"))
        self.assertEqual(cuentas, [1, 1, 1, 1])

    def test_ola_este_centro_pacifico(self):
        ahora = datetime(2026, 11, 4, 16, 0, tzinfo=timezone.utc)
        items = [
            {"nombre": "P", "puntaje": 5, "zona_iana": "America/Los_Angeles", "lead": {}, "_cuando_orden": ahora},
            {"nombre": "E2", "puntaje": 9, "zona_iana": "America/New_York", "lead": {}, "_cuando_orden": ahora},
            {"nombre": "C", "puntaje": 5, "zona_iana": "America/Chicago", "lead": {}, "_cuando_orden": ahora},
            {"nombre": "E1", "puntaje": 4, "zona_iana": "America/New_York", "lead": {}, "_cuando_orden": ahora},
        ]
        orden = [item["nombre"] for item in ordenar_ola(items)]
        self.assertEqual(orden, ["E2", "C", "P", "E1"])


class TestSeguimiento(_Base):
    def test_dias_4_y_10_caen_en_dia_habil(self):
        from b2b.seguimiento import _load, anotar_planes_correo

        cuando = datetime(2026, 11, 4, 14, 0, tzinfo=timezone.utc)  # miércoles 09:00 EST
        anotar_planes_correo(_lead(), cuando)
        planes = next(iter(_load()["items"].values()))["correos_programados"]
        self.assertEqual([p["dia"] for p in planes], [4, 10])
        for plan in planes:
            momento = datetime.fromisoformat(plan["enviar_despues_de"])
            local = momento.astimezone(NY)
            self.assertLess(local.weekday(), 5)
            self.assertTrue(en_ventana(momento, _lead()))
            self.assertGreaterEqual((local.hour, local.minute), (9, 0))
            self.assertLess((local.hour, local.minute), (11, 30))
        self.assertEqual(datetime.fromisoformat(planes[0]["enviar_despues_de"]).astimezone(NY).date().isoformat(), "2026-11-09")
        self.assertEqual(datetime.fromisoformat(planes[1]["enviar_despues_de"]).astimezone(NY).date().isoformat(), "2026-11-16")

    def test_baja_cancela_el_seguimiento(self):
        from b2b.envio_correo import excluir_correo
        from b2b.seguimiento import _load, anotar_planes_correo

        lead = _lead()
        cuando = datetime(2026, 11, 4, 14, 0, tzinfo=timezone.utc)
        anotar_planes_correo(lead, cuando)
        clave = next(iter(_load()["items"]))
        data = _load()
        data["items"][clave]["correos_programados"][0]["enviar_despues_de"] = cuando.isoformat()
        from b2b.seguimiento import _save
        _save(data)
        excluir_correo(lead["correo"], "unsubscribe")
        self.assertEqual(procesar_outbox(cuando), 0)
        plan = _load()["items"][clave]["correos_programados"][0]
        self.assertEqual(plan["estado"], "cancelado")
        self.assertEqual(list(Path(self.tmp.name).glob("outbox/*.json")), [])


if __name__ == "__main__":
    unittest.main()
