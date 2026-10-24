#!/usr/bin/env bash
# Cazador de Sueño Cigars SRL — configuración completa del servidor
# Ejecutar en la VM GCP vía SSH (usuario con sudo)

set -euo pipefail

SITE_ROOT="/var/www/cazador-de-suenos-cigars"
NGINX_AVAILABLE="/etc/nginx/sites-available/cazador-de-suenos"
NGINX_ENABLED="/etc/nginx/sites-enabled/cazador-de-suenos"
DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Instalando dependencias..."
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y nginx certbot python3-certbot-nginx

echo "==> Preparando directorio del sitio..."
sudo mkdir -p "$SITE_ROOT"
sudo chown -R "$USER:$USER" "$SITE_ROOT"

echo "==> Copiando configuración Nginx (bootstrap HTTP)..."
if [[ -f "$DEPLOY_DIR/nginx-cazador-http-bootstrap.conf" ]]; then
  sudo cp "$DEPLOY_DIR/nginx-cazador-http-bootstrap.conf" "$NGINX_AVAILABLE"
else
  echo "ERROR: No se encontró nginx-cazador-http-bootstrap.conf en $DEPLOY_DIR"
  exit 1
fi

sudo ln -sf "$NGINX_AVAILABLE" "$NGINX_ENABLED"
sudo rm -f /etc/nginx/sites-enabled/default

echo "==> Verificando Nginx..."
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl restart nginx

echo "==> Ajustando permisos del sitio..."
if [[ -d "$SITE_ROOT" ]] && [[ -f "$SITE_ROOT/index.html" ]]; then
  sudo chown -R www-data:www-data "$SITE_ROOT"
  sudo find "$SITE_ROOT" -type f -exec chmod 644 {} \;
  sudo find "$SITE_ROOT" -type d -exec chmod 755 {} \;
else
  echo "AVISO: Sube los archivos del sitio a $SITE_ROOT antes de validar."
fi

echo ""
echo "Bootstrap HTTP listo."
echo "Prueba: curl -I http://$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')/"
echo ""
echo "Cuando DNS apunte a esta VM, ejecuta:"
echo "  sudo certbot --nginx -d www.cazadordesuenocigars.com -d cazadordesuenocigars.com"
echo "  sudo cp $DEPLOY_DIR/nginx-cazador-de-suenos.conf $NGINX_AVAILABLE"
echo "  sudo nginx -t && sudo systemctl reload nginx"
