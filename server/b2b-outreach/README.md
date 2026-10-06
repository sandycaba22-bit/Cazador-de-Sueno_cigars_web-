# Aviso B2B de Cazador de Sueños

El script recibe un prospecto que ya tienes y te deja en Telegram el borrador listo para enviar. El foco comercial es abrir con **El Sultán** y **Ligero 007** ante distribuidores, lounges y tiendas de puro premium.

Con `--buscar`, el bot localiza negocios B2B públicos **sin pagar Google** usando **OpenStreetMap** (Overpass, datos abiertos). Si más adelante pones `GOOGLE_PLACES_API_KEY`, `FUENTE_LEADS=auto` puede usar Google. Respeta `robots.txt` al leer webs, encola JSON en `inbox/` y avisa por Telegram. **Nunca** escribe al prospecto: el mensaje lo envías tú.

Al leer la web del prospecto, el idioma del borrador se elige así: **1)** idioma guardado en el lead, **2)** señales del sitio (`html lang`, meta, texto visible), **3)** reglas por país en `country_rules.json`. El catálogo PDF sigue el idioma del borrador (ES/EN/FR/PT).

Los textos del PDF mayorista y de las vitolas en el borrador salen de `catalogo/build_wholesale_catalog.py` (traducciones fijas, no API). Para regenerar los cuatro PDF y subirlos al sitio:

```bash
cd catalogo
python build_wholesale_catalog.py
```

Sube `CazadorDeSuenos_Wholesale_{ES,EN,FR,PT}.pdf` a `https://www.cazadordesuenocigar.com/catalogo/`.

**Buscador:** por defecto **OpenStreetMap** (gratis). `--simulado` es solo para pruebas con fixtures. Objetivo: **`--buscar --limite 9`** (nueve prospectos por pasada). Google Places es opcional cuando quieras pagar API.

Un prospecto del Caribe queda marcado como prioridad alta (ruta corta desde Santiago). El resto entra como mercado internacional. En los dos casos la importación la confirma el comprador en su país. El script no tramita aduana ni salta controles.

## Dependencias

En el servidor, una sola vez:

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip
python3 -m pip install -r /var/www/html/server/b2b-outreach/requirements.txt
```

`requirements.txt` fija `python-dotenv` y `requests`. Si `pip` no está disponible para ese Python, el paquete del sistema es `python3-pip`.

## Credenciales

Local, junto al script, archivo `.env` (no se sube a git):

```text
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
GOOGLE_PLACES_API_KEY=
MAX_PLACES_CALLS_DIA=200
```

En el servidor el secreto no va dentro de `/var/www`. Va fuera del sitio:

```bash
sudo install -d -o root -g www-data -m 750 /etc/cazador-de-suenos
sudo install -o root -g www-data -m 640 /dev/null /etc/cazador-de-suenos/b2b-outreach.env
sudo nano /etc/cazador-de-suenos/b2b-outreach.env
```

Mismas dos variables. El chat id es el tuyo.

## Entrenamiento de marca (`knowledge/`)

```bash
cd server/b2b-outreach
python telegram_bot.py --entrenar
python telegram_bot.py --reglas
python telegram_bot.py --revisar-reglas Martinique
```

`--entrenar` valida fuentes en `knowledge/mercado_marcas_referencia.md` y genera `knowledge/resumen_entrenamiento.md`.

## Buscador global (local)

Negocios reales vía OSM (sin token):

```bash
python telegram_bot.py --buscar Senegal --limite 9 --solo-listar
python telegram_bot.py --buscar --limite 9
python telegram_bot.py --vigilar --una-pasada --imprimir
```

Solo pruebas con datos falsos:

```bash
python telegram_bot.py --buscar Martinique --limite 3 --simulado --solo-listar
```

Google (opcional, de pago): `GOOGLE_PLACES_API_KEY` + `FUENTE_LEADS=google`.

Sin `--pais`, recorre `prioridad_inicial` hasta llenar el límite (p. ej. 9/día). Códigos país OSM: `data/osm_iso3166.json`.

Lista de baja: `data/no_contactar.json`. No se regeneran borradores para esos negocios.

Prueba automatizada local:

```bash
python tests/smoke_local.py
```

## Prueba de humo (manual)

No llama a Telegram:

```bash
python3 /var/www/html/server/b2b-outreach/telegram_bot.py \
  --nombre "Le Cercle du Cigare" \
  --pais "Martinique" \
  --web "https://lecercle.mq" \
  --correo "contacto@lecercle.mq" \
  --imprimir
```

Tiene que salir en francés, prioridad alta, con El Sultán y Ligero 007.

La prueba real, la que sí te escribe por Telegram, es el mismo comando sin `--imprimir`. `--nombre`, `--pais`, `--web` y `--correo` son obligatorios. La web tiene que llevar `http://` o `https://`.

## Cola 24/7

Cada archivo `inbox/*.json` es un prospecto. El proceso lee uno, te avisa y lo mueve a `sent/`. Si falla, lo mueve a `failed/` con un `.error.txt` que no incluye el token. Para reintentarlo, devuelve el JSON a `inbox/`. Entre vueltas no acumula prospectos en memoria: duerme y vuelve a mirar la carpeta.

En producción la cola es `/var/lib/cazador-de-suenos/b2b-outreach`.

```json
{
  "nombre": "Le Cercle du Cigare",
  "pais": "Martinique",
  "web": "https://lecercle.mq",
  "correo": "contacto@lecercle.mq"
}
```

Ese JSON se deja en `inbox/`. Los del Caribe se atienden antes que el resto en la misma pasada.

Una pasada de prueba, sin Telegram:

```bash
python3 /var/www/html/server/b2b-outreach/telegram_bot.py --vigilar --una-pasada --imprimir
```

## systemd

El servicio recomendado es `cds-b2b-outreach.service`. Un solo proceso, reinicio si se cae, tope de memoria 128 MB.

```bash
sudo cp /var/www/html/server/b2b-outreach/cds-b2b-outreach.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cds-b2b-outreach.service
sudo systemctl status cds-b2b-outreach.service
```

Los logs: `journalctl -u cds-b2b-outreach.service -f`

Buscador diario (9 prospectos, OSM gratis):

```bash
sudo cp /var/www/html/server/b2b-outreach/cds-b2b-buscar.service /etc/systemd/system/
sudo cp /var/www/html/server/b2b-outreach/cds-b2b-buscar.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cds-b2b-buscar.timer
sudo systemctl start cds-b2b-buscar.service   # prueba manual
journalctl -u cds-b2b-buscar.service -n 30
```

En `/etc/cazador-de-suenos/b2b-outreach.env` añade `FUENTE_LEADS=osm` (no hace falta Google).

## PM2

Misma cola, otra forma de tenerlo en segundo plano. No arranques systemd y PM2 a la vez.

```bash
cd /var/www/html/server/b2b-outreach
pm2 start ecosystem.config.cjs
pm2 save
```

El archivo de entorno de systemd no lo carga PM2. Exporta `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` en el entorno de ese proceso, o deja el `.env` junto al script fuera de cualquier carpeta pública.
