#!/usr/bin/env bash
# Ejecutar EN LA VM (terminal SSH de GCP) si el despliegue desde Windows no conecta.
# Requiere que los archivos ya estén en /var/www/cazador-de-suenos-cigars/

set -euo pipefail

SITE_ROOT="/var/www/cazador-de-suenos-cigars"
DOMAIN="cazadordesuenocigars.com"
WWW="www.cazadordesuenocigars.com"

echo "==> Instalando Nginx y Certbot..."
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y nginx certbot python3-certbot-nginx

echo "==> Configurando sitio HTTP..."
sudo mkdir -p "$SITE_ROOT"
sudo cp "$SITE_ROOT/deploy/nginx-cazador-http-bootstrap.conf" /etc/nginx/sites-available/cazador-de-suenos
sudo ln -sf /etc/nginx/sites-available/cazador-de-suenos /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl restart nginx

echo "==> Permisos..."
sudo chown -R www-data:www-data "$SITE_ROOT"
sudo find "$SITE_ROOT" -type f -exec chmod 644 {} \;
sudo find "$SITE_ROOT" -type d -exec chmod 755 {} \;

echo "==> Verificación HTTP..."
curl -sI "http://127.0.0.1/" | head -n 1
curl -sI "http://127.0.0.1/vitolas/el-emperador.html" | head -n 1

echo ""
echo "HTTP listo. Si DNS apunta a esta VM, ejecuta SSL:"
echo "  sudo certbot --nginx -d $WWW -d $DOMAIN"
echo "  sudo cp $SITE_ROOT/deploy/nginx-cazador-de-suenos.conf /etc/nginx/sites-available/cazador-de-suenos"
echo "  sudo nginx -t && sudo systemctl reload nginx"
