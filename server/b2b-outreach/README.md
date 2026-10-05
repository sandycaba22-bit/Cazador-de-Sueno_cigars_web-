# Aviso B2B de Cazador de Sueños

El script recibe un prospecto que ya tienes y te deja en Telegram el borrador listo para enviar. El foco comercial es abrir con **El Sultán** y **Ligero 007** ante distribuidores, lounges y tiendas de puro premium.

No rastrea internet, no arma listas por su cuenta y no escribe al prospecto. El mensaje al local lo envías tú.

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
```

En el servidor el secreto no va dentro de `/var/www`. Va fuera del sitio:

```bash
sudo install -d -o root -g www-data -m 750 /etc/cazador-de-suenos
sudo install -o root -g www-data -m 640 /dev/null /etc/cazador-de-suenos/b2b-outreach.env
sudo nano /etc/cazador-de-suenos/b2b-outreach.env
```

Mismas dos variables. El chat id es el tuyo.

## Prueba de humo

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

## PM2

Misma cola, otra forma de tenerlo en segundo plano. No arranques systemd y PM2 a la vez.

```bash
cd /var/www/html/server/b2b-outreach
pm2 start ecosystem.config.cjs
pm2 save
```

El archivo de entorno de systemd no lo carga PM2. Exporta `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` en el entorno de ese proceso, o deja el `.env` junto al script fuera de cualquier carpeta pública.
