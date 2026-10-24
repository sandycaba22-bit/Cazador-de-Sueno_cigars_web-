#!/bin/bash
# Limpieza total del servidor — Cazador de Sueño Cigars SRL
# Ejecutar en la VM de Google Cloud: bash cleanup-server.sh
set -euo pipefail

echo "=== Respaldo ==="
sudo mkdir -p /root/backups
sudo tar -czf "/root/backups/pre-cazador-$(date +%Y%m%d-%H%M).tar.gz" /var/www/ 2>/dev/null || true

echo "=== Detener servicios web ==="
sudo systemctl stop nginx 2>/dev/null || true
sudo systemctl stop apache2 2>/dev/null || true

echo "=== Eliminar sitios viejos ==="
sudo rm -rf /var/www/html/*
sudo rm -rf /var/www/cazadordesuenos 2>/dev/null || true
sudo rm -rf /var/www/cazador* 2>/dev/null || true

echo "=== Limpiar configs Nginx viejas ==="
sudo rm -f /etc/nginx/sites-enabled/default
sudo rm -f /etc/nginx/sites-enabled/cazador* 2>/dev/null || true
sudo rm -f /etc/nginx/sites-available/cazador* 2>/dev/null || true

echo "=== Preparar carpeta nueva ==="
sudo mkdir -p /var/www/cazador-de-suenos-cigars
sudo chown -R "$USER:$USER" /var/www/cazador-de-suenos-cigars

echo "=== Listo. Sube el proyecto y configura Nginx. ==="
ls -la /var/www/
