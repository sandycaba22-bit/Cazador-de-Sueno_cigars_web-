# Aviso B2B de Cazador de Sueño Cigars SRL

El script recibe un prospecto que ya tienes y te deja en Telegram el borrador listo para enviar. El foco comercial es abrir con **El Sultán** y **Ligero 007** ante distribuidores, lounges y tiendas de puro premium.

Con `--buscar`, el bot localiza negocios B2B públicos con **Google Places (New)** (`FUENTE_LEADS=google`). Sin clave para y avisa; no cae a OpenStreetMap. Los mercados salen de `config/mercados.json` (solo `activo: true`). Respeta `robots.txt` al leer webs, encola JSON en `inbox/` y avisa por Telegram. **Nunca** escribe al prospecto: el mensaje lo envías tú.

Idioma del borrador: **1)** idioma guardado en el lead, **2)** reglas por país/estado en `country_rules.json`, **3)** señales del sitio (`html lang`, meta, texto visible). El catálogo PDF sigue el idioma del borrador (ES/EN/FR/PT).

## Google Places (New)

- **Clave:** `GOOGLE_PLACES_API_KEY` en `/var/www/html/server/b2b-outreach/.env` o en `/etc/cazador-de-suenos/b2b-outreach.env`. Si en `/etc` está con valor, gana esa; si está vacía, se usa la del `.env` del módulo. Nunca se imprime, ni en logs ni en errores (se reemplaza por `***`).
- **Fuente:** `FUENTE_LEADS=google` (solo Places; default). `ambas` añade OSM de respaldo. `osm` es solo Overpass. `auto` equivale a google si hay clave.
- **Llamada:** una sola `POST https://places.googleapis.com/v1/places:searchText` por búsqueda (`pageSize` 20), con `X-Goog-FieldMask: places.id,places.displayName,places.formattedAddress,places.nationalPhoneNumber,places.websiteUri,places.rating,places.userRatingCount,places.businessStatus,places.types`. **Sin Place Details.** El número internacional (para `wa.me`) se arma con el prefijo del país (`b2b/telefono.py`) y el link de Google Maps con el `place_id`.
- **Búsquedas por estado/ciudad y tipo:** términos en inglés y consulta por ciudad, p. ej. `cigar shop in Miami, Florida`, `cigar lounge in Las Vegas, Nevada`. Lista base: cigar shop, cigar lounge, cigar bar, tobacconist, cigar distributor, tobacco wholesaler, humidor, hotel resort cigar lounge, steakhouse humidor, casino cigar room, golf club cigar lounge, liquor store humidor.
- **Negocios seguros:** `businessStatus = OPERATIONAL`, teléfono o sitio web, y señal de cigarro (tienda, lounge, distribuidor u hotel/resort con humidor). Cerrados permanentes y duplicados (`place_id` o teléfono) se descartan. Rating y reseñas ordenan, no descartan. Si hay web propia se visita (`b2b/contacto_web.py`) para correo e Instagram **solo si aparecen en la página**.
- **Canales:** si `websiteUri` es Instagram o Facebook se guarda como red social, no como web. Un link de mapa nunca cuenta como web ni como contacto.
- **Presupuesto en dos tandas:** el timer corre a las 09:00 y a las 15:00 (hora de Santo Domingo, `B2B_TZ`). Cada tanda gasta como máximo `GOOGLE_PLACES_MAX_CALLS_PER_RUN` (15) búsquedas; el día, `GOOGLE_PLACES_MAX_CALLS_PER_DAY` (30); el mes, `GOOGLE_PLACES_MAX_CALLS_PER_MONTH` (900). Contador en `data/places_budget.json`. Al llegar a un tope: para limpio, guarda el cursor y avisa una vez por Telegram.
- **Errores:** cualquier 4xx/5xx o falta de respuesta apaga Google por el resto de la corrida y avisa por Telegram. Lo ya encontrado en ese estado se conserva.
- **Caché:** `data/google_places_cache.json` guarda cada búsqueda del mes; una consulta ya vista no gasta llamadas.
- **Rotación:** `config/mercados.json` (50 estados + DC, Florida primero; Puerto Rico y Jamaica al final, prioridad baja). Cursor en `data/busqueda_cursor.json`: la siguiente corrida sigue en el mismo estado e índice de consulta. Lo inactivo no se busca.

Mensaje por prospecto en Telegram: nombre, tipo, isla, dirección, calificación y reseñas, teléfono, link `wa.me` con el borrador ya escrito (solo con número internacional), correo, web, Instagram, Facebook, formulario encontrado, Google Maps y botones **Enviado / Descartar**. Plantilla corta para WhatsApp/Instagram (sin STOP) y, si hay correo, versión correo con la línea de STOP. Sin ningún canal real no hay borrador: el negocio va a `sin_contacto_YYYYMMDD.json` con su link de Maps.

Los textos del PDF mayorista y de las vitolas en el borrador salen de `catalogo/build_wholesale_catalog.py` (traducciones fijas, no API). Para regenerar los cuatro PDF y subirlos al sitio:

```bash
cd catalogo
python build_wholesale_catalog.py
```

Sube `CazadorDeSuenos_Wholesale_{ES,EN,FR,PT}.pdf` a `https://www.cazadordesuenocigar.com/catalogo/`.

**Buscador:** Google Places. `--simulado` es solo para pruebas con fixtures. Objetivo: **`--buscar --limite 9`**.

Un prospecto de Estados Unidos queda como prioridad alta. Puerto Rico y Jamaica entran después. El script no tramita aduana ni salta controles.

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
FUENTE_LEADS=google
GOOGLE_PLACES_API_KEY=
GOOGLE_PLACES_MAX_CALLS_PER_DAY=30
GOOGLE_PLACES_MAX_CALLS_PER_MONTH=900
```

En el servidor el secreto no va dentro de `/var/www`. Va fuera del sitio:

```bash
sudo bash /var/www/html/deploy/install-cds-b2b-outreach.sh
sudo nano /etc/cazador-de-suenos/b2b-outreach.env   # solo la primera vez, si faltan TELEGRAM_*
```

**No copies** `.env.example` encima de `/etc/cazador-de-suenos/b2b-outreach.env` si ya tiene credenciales.
El instalador **nunca sobrescribe** un archivo que ya existe.

Mismas dos variables. El chat id es el tuyo.

## Entrenamiento de marca (`knowledge/`)

```bash
cd server/b2b-outreach
python telegram_bot.py --entrenar
python telegram_bot.py --reglas
python telegram_bot.py --revisar-reglas Florida
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
python telegram_bot.py --buscar Florida --limite 3 --simulado --solo-listar
```

Google: pon `GOOGLE_PLACES_API_KEY` (y deja `FUENTE_LEADS=google`). Las pruebas de Google usan respuestas simuladas: `python -m pytest tests/test_google_places.py`.

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
  --nombre "Prime Cigar & Whiskey Bar" \
  --pais "Florida" \
  --web "https://primecigarbar.example.com" \
  --correo "contact@primecigarbar.example.com" \
  --imprimir
```

Tiene que salir en inglés o español según reglas, con El Sultán y Ligero 007.

La prueba real, la que sí te escribe por Telegram, es el mismo comando sin `--imprimir`. `--nombre`, `--pais`, `--web` y `--correo` son obligatorios. La web tiene que llevar `http://` o `https://`.

## Cola 24/7

Cada archivo `inbox/*.json` es un prospecto. El proceso lee uno, te avisa y lo mueve a `sent/`. Si falla, lo mueve a `failed/` con un `.error.txt` que no incluye el token. Para reintentarlo, devuelve el JSON a `inbox/`. Entre vueltas no acumula prospectos en memoria: duerme y vuelve a mirar la carpeta.

En producción la cola es `/var/lib/cazador-de-suenos/b2b-outreach`.

```json
{
  "nombre": "Miami Cigar Lounge",
  "pais": "Florida",
  "web": "https://miamicigars.example",
  "correo": "buyer@miamicigars.example"
}
```

Ese JSON se deja en `inbox/`. Los de Estados Unidos se atienden primero.

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

Buscador en dos tandas diarias (09:00 y 15:00, hasta 9 prospectos y 15 búsquedas Google cada una):

```bash
sudo cp /var/www/html/server/b2b-outreach/cds-b2b-buscar.service /etc/systemd/system/
sudo cp /var/www/html/server/b2b-outreach/cds-b2b-buscar.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cds-b2b-buscar.timer
sudo systemctl start cds-b2b-buscar.service   # prueba manual
journalctl -u cds-b2b-buscar.service -n 30
```

El instalador agrega a `/etc/cazador-de-suenos/b2b-outreach.env` las variables que falten (`FUENTE_LEADS=google`, `GOOGLE_PLACES_API_KEY=` vacía y los topes) sin cambiar las existentes, y deja `server/b2b-outreach/.env` legible para `www-data` (`root:www-data`, 0640). Para activar Google basta con pegar la clave en uno de los dos archivos; la próxima tanda ya la usa.

## Despliegue

```bash
cd ~/Cazador-de-Suenos-Siga-Web
BRANCH=cursor/b2b-buscador-global bash deploy/deploy-on-server.sh
```

Copia `server/b2b-outreach` a `/var/www/html` (sin `.env`, cola, logs ni estado), ejecuta el instalador y reinicia `cds-b2b-outreach` (y `cds-b2b-buscar` si estaba corriendo).

## PM2

Misma cola, otra forma de tenerlo en segundo plano. No arranques systemd y PM2 a la vez.

```bash
cd /var/www/html/server/b2b-outreach
pm2 start ecosystem.config.cjs
pm2 save
```

El archivo de entorno de systemd no lo carga PM2. Exporta `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` en el entorno de ese proceso, o deja el `.env` junto al script fuera de cualquier carpeta pública.
