#!/usr/bin/env bash
# Despliegue completo — pegar en terminal SSH de GCP (botón SSH en la VM jaragoexpresselite)
set -euo pipefail

SITE_ROOT="/var/www/cazador-de-suenos-cigars"
DOMAIN="cazadordesuenocigars.com"
WWW="www.cazadordesuenocigars.com"

echo "=== 1/5 Instalando Nginx y Certbot ==="
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y nginx certbot python3-certbot-nginx unzip

echo "=== 2/5 Preparando directorio ==="
sudo mkdir -p "$SITE_ROOT"
sudo chown -R "$USER:$USER" "$SITE_ROOT"

echo "=== 3/5 Esperando archivos del sitio en $SITE_ROOT ==="
echo "    Sube el ZIP del proyecto aquí y descomprímelo, o ejecuta scp desde Cloud Shell."
echo "    Debe existir: $SITE_ROOT/index.html"

if [[ ! -f "$SITE_ROOT/index.html" ]]; then
  echo "ERROR: No hay index.html. Sube archivos primero."
  echo "Desde Cloud Shell en tu navegador:"
  echo "  gcloud compute scp --recurse LOCAL_PATH jaragoexpresselite:$SITE_ROOT --zone=TU_ZONA"
  exit 1
fi

echo "=== 4/5 Configurando Nginx ==="
sudo tee /etc/nginx/sites-available/cazador-de-suenos > /dev/null <<'NGINX'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name cazadordesuenocigars.com www.cazadordesuenocigars.com _;
    root /var/www/cazador-de-suenos-cigars;
    index index.html;
    gzip on;
    gzip_types text/plain text/css application/javascript image/svg+xml;
    location ~* \.(jpg|jpeg|png|gif|webp|ico|css|js|pdf|woff2?)$ {
        expires 30d;
        try_files $uri =404;
    }
    location / { try_files $uri $uri/ =404; }
    autoindex off;
}
NGINX

sudo ln -sf /etc/nginx/sites-available/cazador-de-suenos /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl restart nginx

sudo chown -R www-data:www-data "$SITE_ROOT"
sudo find "$SITE_ROOT" -type f -exec chmod 644 {} \;
sudo find "$SITE_ROOT" -type d -exec chmod 755 {} \;

echo "=== 5/5 Verificando ==="
curl -sI "http://127.0.0.1/" | head -1
curl -sI "http://127.0.0.1/vitolas/el-emperador.html" | head -1
echo ""
echo "Sitio HTTP activo."
echo "SSL: sudo certbot --nginx -d $WWW -d $DOMAIN"
