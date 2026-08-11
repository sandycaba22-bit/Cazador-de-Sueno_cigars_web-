# Despliegue en Producción — Cazador de Sueños Cigars

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
# En tu máquina local, desde la carpeta del proyecto
cd C:\Users\sandy\cazador-de-suenos-cigars

# Subir todo el sitio (excluye deploy si no lo necesitas en servidor)
scp -r index.html style.css intro.js logo-render.js nav.js robots.txt sitemap.xml img images vitolas USUARIO@IP_EXTERNA:/var/www/cazador-de-suenos-cigars/
```

### Opción B — Con rsync (Git Bash o WSL)

```bash
rsync -avz --delete \
  --exclude 'deploy/' \
  --exclude '.git/' \
  ./ USUARIO@IP_EXTERNA:/var/www/cazador-de-suenos-cigars/
```

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

## Mantenimiento

```bash
# Actualizar sitio tras cambios locales
rsync -avz --delete --exclude 'deploy/' ./ USUARIO@IP:/var/www/cazador-de-suenos-cigars/
sudo systemctl reload nginx
```

---

## Resumen de rutas en servidor

| Ruta | Uso |
|------|-----|
| `/var/www/cazador-de-suenos-cigars/` | Raíz del sitio |
| `/etc/nginx/sites-available/cazador-de-suenos` | Config Nginx |
| `/etc/letsencrypt/live/www.cazadordesuenocigars.com/` | Certificados SSL |
