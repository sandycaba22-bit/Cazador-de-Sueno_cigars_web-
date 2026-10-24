# Despliegue en Producción — Cazador de Sueño Cigars SRL

**Dominio:** `www.cazadordesuenocigars.com` (canónico)  
**Servidor:** Google Cloud Compute Engine (VM)  
**DNS:** GoDaddy  
**Stack:** Nginx + Let's Encrypt (Certbot)

---

## Requisitos previos

1. VM en Google Cloud con IP externa estática reservada.
2. Firewall GCP: puertos **22** (SSH), **80** (HTTP) y **443** (HTTPS) abiertos.
3. Acceso SSH a la VM (`gcloud compute ssh NOMBRE_VM --zone=ZONA` o cliente SSH).
4. Dominio `cazadordesuenocigars.com` en GoDaddy.

---

## PASO 1 — Limpieza total en Google Cloud (SSH)

### 1.1 Conectarse al servidor

```bash
# Desde Google Cloud Shell o tu terminal (ajusta nombre y zona)
gcloud compute ssh NOMBRE_DE_TU_VM --zone=us-central1-a

# O SSH directo
ssh USUARIO@IP_EXTERNA_DEL_SERVIDOR
```

### 1.2 Identificar qué hay instalado (no borrar a ciegas)

```bash
# Ver sitios web actuales
sudo ls -la /var/www/
sudo ls -la /etc/nginx/sites-enabled/ 2>/dev/null || sudo ls -la /etc/apache2/sites-enabled/ 2>/dev/null

# Ver qué proceso sirve el puerto 80
sudo ss -tlnp | grep ':80\|:443'
```

### 1.3 Respaldo rápido (recomendado antes de borrar)

```bash
sudo mkdir -p /root/backups
sudo tar -czf /root/backups/sitio-viejo-$(date +%Y%m%d).tar.gz /var/www/ 2>/dev/null
sudo tar -czf /root/backups/nginx-viejo-$(date +%Y%m%d).tar.gz /etc/nginx/ 2>/dev/null
```

### 1.4 Eliminar sitio viejo y archivos basura

```bash
# Detener servicios web momentáneamente
sudo systemctl stop nginx 2>/dev/null || sudo systemctl stop apache2 2>/dev/null

# Vaciar directorios web antiguos (ajusta rutas si tu servidor usa otras)
sudo rm -rf /var/www/html/*
sudo rm -rf /var/www/cazadordesuenos/* 2>/dev/null
sudo rm -rf /var/www/cazador* 2>/dev/null

# Eliminar configuraciones viejas de Nginx
sudo rm -f /etc/nginx/sites-enabled/default
sudo rm -f /etc/nginx/sites-enabled/cazador* 2>/dev/null
sudo rm -f /etc/nginx/sites-available/cazador* 2>/dev/null

# Si usabas Apache en lugar de Nginx
sudo a2dissite 000-default.conf 2>/dev/null
sudo rm -f /etc/apache2/sites-enabled/*cazador* 2>/dev/null

# Crear carpeta limpia para el proyecto nuevo
sudo mkdir -p /var/www/cazador-de-suenos-cigars
sudo chown -R $USER:$USER /var/www/cazador-de-suenos-cigars
```

### 1.5 Instalar Nginx y Certbot (si no están)

```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
sudo systemctl enable nginx
```

---

## PASO 2 — Subir el proyecto nuevo

### Opción A — Desde tu PC (Windows PowerShell)

```powershell
cd C:\Users\sandy\Documents\cazador-sueno-web

# Ensayo: muestra qué subiría sin tocar el servidor
.\deploy\deploy-from-windows.ps1 -SshUser TU_USUARIO -DryRun

# Despliegue real
.\deploy\deploy-from-windows.ps1 -SshUser TU_USUARIO
```

El script respalda el sitio antes de sobrescribir, sube la capa de comercio
(`checkout.html`, `order-confirmation.html`, `style.css`, `css/`, `js/`, `config/`,
`locales/`, `assets/`, `vitolas/`), restaura permisos y verifica el resultado por HTTPS.

### Opción B — Con rsync (Git Bash o WSL)

```bash
rsync -avz \
  --exclude 'deploy/' --exclude '.git/' \
  --exclude 'index.html' --exclude 'index_temp.html' --exclude 'index_server.html' \
  --exclude 'admin.html' --exclude 'cart-test.html' \
  --exclude '.env' --exclude 'server/commerce/.env' --exclude '.commerce-data/' \
  ./ USUARIO@IP_EXTERNA:/var/www/cazador-de-suenos-cigars/
```

> No uses `--delete` ni subas `index.html`. Ver la advertencia de abajo.

### Permisos en el servidor

```bash
sudo chown -R www-data:www-data /var/www/cazador-de-suenos-cigars
sudo find /var/www/cazador-de-suenos-cigars -type f -exec chmod 644 {} \;
sudo find /var/www/cazador-de-suenos-cigars -type d -exec chmod 755 {} \;
```

---

## PASO 3 — Configurar Nginx

```bash
# Copiar configuración (sube deploy/nginx-cazador-de-suenos.conf al servidor primero)
sudo cp nginx-cazador-de-suenos.conf /etc/nginx/sites-available/cazador-de-suenos
sudo ln -sf /etc/nginx/sites-available/cazador-de-suenos /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Probar sintaxis
sudo nginx -t

# Reiniciar
sudo systemctl restart nginx
```

### SSL con Let's Encrypt (HTTPS)

```bash
sudo certbot --nginx -d www.cazadordesuenocigars.com -d cazadordesuenocigars.com
```

Certbot configurará el certificado y actualizará Nginx. Renovación automática:

```bash
sudo certbot renew --dry-run
```

---

## PASO 4 — DNS en GoDaddy

Entra a **GoDaddy → Mis Productos → cazadordesuenocigars.com → Administrar DNS**.

Elimina registros conflictivos antiguos (A/CNAME duplicados o forwarding viejo).

### Registros exactos a crear

| Tipo  | Nombre | Valor                          | TTL  |
|-------|--------|--------------------------------|------|
| **A** | `@`    | `TU_IP_EXTERNA_DE_GOOGLE_CLOUD` | 600  |
| **CNAME** | `www` | `cazadordesuenocigars.com.`         | 600  |

> El punto final en `cazadordesuenocigars.com.` en CNAME es correcto en GoDaddy.

### Alternativa (si CNAME en www da problemas)

| Tipo | Nombre | Valor                          | TTL |
|------|--------|--------------------------------|-----|
| **A** | `@`  | `TU_IP_EXTERNA_DE_GOOGLE_CLOUD` | 600 |
| **A** | `www`| `TU_IP_EXTERNA_DE_GOOGLE_CLOUD` | 600 |

### Redirección sin www → www

No uses el "reenviador" de GoDaddy si Nginx ya redirige. La configuración Nginx incluida hace:

- `http://cazadordesuenocigars.com` → `https://www.cazadordesuenocigars.com`
- `https://cazadordesuenocigars.com` → `https://www.cazadordesuenocigars.com`
- Sitio canónico solo en **www** con HTTPS.

### Propagación DNS

Puede tardar **15 minutos a 48 horas**. Verificar:

```bash
dig www.cazadordesuenocigars.com +short
dig cazadordesuenocigars.com +short
```

---

## PASO 5 — Verificación final

```bash
curl -I http://cazadordesuenocigars.com
curl -I https://www.cazadordesuenocigars.com
curl -I https://www.cazadordesuenocigars.com/vitolas/ligero-007.html
```

Debes ver **301** hacia `https://www.cazadordesuenocigars.com` en el dominio sin www.

En el navegador:

- https://www.cazadordesuenocigars.com
- https://www.cazadordesuenocigars.com/vitolas/el-sultan.html
- Candado SSL activo

---

## PASO 6 — API de comercio (cds-commerce)

El checkout nuevo no calcula precios en el navegador. Nginx reenvía `/api/commerce` al proceso Node en `127.0.0.1:8788`, que firma el total, cobra con CardNET/PayPal/transferencia y guarda los pedidos **fuera** del webroot.

El script de Windows ya sube `server/commerce` (nunca un `.env`), parchea Nginx y arranca el servicio. Si lo haces a mano en el servidor:

```bash
sudo bash /var/www/cazador-de-suenos-cigars/deploy/ensure-nginx-commerce.sh
sudo bash /var/www/cazador-de-suenos-cigars/deploy/install-cds-commerce.sh
curl -sS http://127.0.0.1:8788/api/commerce/health
curl -sS https://www.cazadordesuenocigars.com/api/commerce/health
```

`ensure-nginx-commerce.sh` inserta el proxy a `:8788` y el bloqueo de `/server/` **sin sustituir el certificado SSL**. No uses `setup-server.sh` en un sitio que ya tiene HTTPS.

Edita las claves (el instalador no pisa un fichero que ya exista):

```bash
sudo nano /etc/cazador-de-suenos/commerce.env
# Obligatorio: COMMERCE_QUOTE_SECRET (el instalador la genera si el fichero es nuevo)
# Sandbox: COMMERCE_SANDBOX_ENABLED=false (retirado del checkout; no ofrecerlo)
# CardNET: CARDNET_ENABLED=true + PUBLIC/PRIVATE_ACCOUNT_KEY + CARDNET_USD_DOP_RATE si liquidas en DOP
# PayPal Sandbox: PAYPAL_ENABLED=true + PAYPAL_CLIENT_ID + PAYPAL_CLIENT_SECRET + PAYPAL_MODE=sandbox
# PayPal Live:    PAYPAL_ENABLED=true + PAYPAL_CLIENT_ID + PAYPAL_CLIENT_SECRET + PAYPAL_MODE=live
sudo systemctl restart cds-commerce
sudo journalctl -u cds-commerce -f
```

### Activación local de PayPal Sandbox

Para probar el checkout en tu PC, coloca las claves en uno de estos dos archivos:

- `C:\Users\sandy\cazador-de-suenos-cigars\.env`
- `C:\Users\sandy\cazador-de-suenos-cigars\server\commerce\.env`

Variables mínimas:

```env
PAYPAL_ENABLED=true
PAYPAL_CLIENT_ID=TU_CLIENT_ID_SANDBOX
PAYPAL_CLIENT_SECRET=TU_CLIENT_SECRET_SANDBOX
PAYPAL_MODE=sandbox
PAYPAL_CURRENCY=USD
```

### Cambio de Sandbox a Live

1. Crea la app Live en PayPal Developer.
2. Sustituye `PAYPAL_CLIENT_ID` y `PAYPAL_CLIENT_SECRET` por las credenciales Live.
3. Cambia `PAYPAL_MODE=live`.
4. Reinicia `cds-commerce`.
5. Verifica `https://www.cazadordesuenocigars.com/api/commerce/health`.

Comprueba que Nginx **no** sirve el código ni los pedidos:

```bash
curl -I https://www.cazadordesuenocigars.com/server/commerce/server.js   # 404
curl -I https://www.cazadordesuenocigars.com/data/orders.json            # 404
```

Si el sitio ya tenía el Nginx viejo, copia la config nueva (incluye el proxy a `:8788` y el bloqueo de `/server/` y `/data/`):

```bash
sudo cp /var/www/cazador-de-suenos-cigars/deploy/nginx-cazador-de-suenos.conf \
        /etc/nginx/sites-available/cazador-de-suenos
sudo nginx -t && sudo systemctl reload nginx
```

---

## Mantenimiento

```powershell
# Actualizar sitio tras cambios locales
.\deploy\deploy-from-windows.ps1 -SshUser TU_USUARIO
```

En el servidor, recargar Nginx y los procesos Node:

```bash
sudo systemctl reload nginx
sudo systemctl restart cds-commerce
sudo systemctl restart cds-ai-sommelier
curl -sS http://127.0.0.1:8788/api/commerce/health
```

### Advertencia: index.html está desincronizado

La portada que sirve el servidor pesa unos 81 KB y **no existe en el repositorio**: fue
editada directamente en producción. El `index.html` de este repositorio es una maqueta de
comercio de 5 KB. Subirlo borraría la portada real del sitio.

Por eso el script de despliegue **excluye `index.html` por defecto**. Para arreglarlo de
raíz, baja la portada real del servidor al repositorio y confírmala en git:

```powershell
scp USUARIO@IP:/var/www/cazador-de-suenos-cigars/index.html .\index.html
```

Solo después tiene sentido usar `-IncludeIndex`.

### Advertencia: no ejecutes setup-server.sh en un sitio en producción

`setup-server.sh` reinstala Nginx con una configuración *bootstrap* HTTP para el dominio
`cazadordesuenocigars.com`. El sitio en vivo es `cazadordesuenocigar.com` con HTTPS, así que
ejecutarlo tumbaría el certificado y el dominio. Úsalo únicamente en una instalación desde cero.

---

## Sommelier IA (Gemini)

El chat flotante llama a `/api/ai-sommelier`. Nginx reenvía al proceso Node en `127.0.0.1:8787`. La clave de Gemini **nunca** va al navegador.

1. Instalar Node.js 18+ en la VM (`node -v`).
2. Crear la clave en [Google AI Studio](https://aistudio.google.com/apikey).
3. En el servidor:

```bash
sudo mkdir -p /etc/cazador-de-suenos
sudo nano /etc/cazador-de-suenos/ai-sommelier.env
# Contenido:
# GEMINI_API_KEY=tu_clave
# GEMINI_MODEL=gemini-2.5-flash
# HOUSE_WHATSAPP=+1 809-464-5016
# HOUSE_WHATSAPP_E164=18094645016
# HOUSE_EMAIL=cazadordesueno1@gmail.com
# LOG_REPLIES=true
# PORT=8787
# HOST=127.0.0.1

sudo chown www-data:www-data /var/www/cazador-de-suenos-cigars/server/ai-sommelier/data
sudo chmod 750 /var/www/cazador-de-suenos-cigars/server/ai-sommelier/data

sudo cp /var/www/cazador-de-suenos-cigars/server/ai-sommelier/cds-ai-sommelier.service /etc/systemd/system/cds-ai-sommelier.service
sudo systemctl daemon-reload
sudo systemctl enable --now cds-ai-sommelier
sudo nginx -t && sudo systemctl reload nginx
curl -s http://127.0.0.1:8787/api/ai-sommelier/health

# Ver en vivo lo que responde el Maestro Tabaquero:
sudo journalctl -u cds-ai-sommelier -f
```

Los leads B2B quedan en `server/ai-sommelier/data/leads.jsonl`. El widget también abre WhatsApp `+1 809-464-5016` con el resumen del lead.

---

## Resumen de rutas en servidor

| Ruta | Uso |
|------|-----|
| `/var/www/cazador-de-suenos-cigars/` | Raíz del sitio |
| `/etc/nginx/sites-available/cazador-de-suenos` | Config Nginx |
| `/etc/letsencrypt/live/www.cazadordesuenocigars.com/` | Certificados SSL |
| `/etc/cazador-de-suenos/ai-sommelier.env` | Clave Gemini (no versionar) |
| `/etc/cazador-de-suenos/commerce.env` | Claves CardNET/PayPal y firma de cotizaciones (no versionar) |
| `/var/lib/cazador-de-suenos/commerce/` | Pedidos (fuera del webroot, modo 0700) |
| `127.0.0.1:8787` | Proceso Node del sommelier |
| `127.0.0.1:8788` | Proceso Node de comercio (cds-commerce) |
