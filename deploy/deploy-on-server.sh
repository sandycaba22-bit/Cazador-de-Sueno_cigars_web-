#!/usr/bin/env bash
#
# Despliegue desde el propio servidor (terminal SSH del navegador).
#
#   bash ~/Cazador-de-Suenos-Siga-Web/deploy/deploy-on-server.sh
#
# Trae la ultima version de main desde GitHub y la publica en el directorio que
# sirve Nginx. Respalda antes de sobrescribir y verifica el resultado al final.
#
# NO sube index.html: el del repositorio es una maqueta de 5 KB y la portada real
# del servidor (~81 KB) no esta en git. Subirla la destruiria.

set -euo pipefail

# El script vive dentro del repositorio, asi que deduce su raiz a partir de su propia
# ubicacion. Da igual como se llame la carpeta donde se haya clonado.
REPO_DIR="${REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SITE_ROOT="${SITE_ROOT:-/var/www/cazador-de-suenos-cigars}"
BRANCH="${BRANCH:-main}"
DOMAIN="${DOMAIN:-cazadordesuenocigar.com}"

# Capa de comercio: lo que vive en git y lo que el checkout necesita.
FILES=(checkout.html order-confirmation.html style.css)
DIRS=(css js config locales assets vitolas)

azul()  { printf '\033[1;36m%s\033[0m\n' "$1"; }
verde() { printf '\033[1;32m%s\033[0m\n' "$1"; }
rojo()  { printf '\033[1;31m%s\033[0m\n' "$1"; }

# --- Comprobaciones previas ---------------------------------------------------
if [[ ! -d "$REPO_DIR/.git" ]]; then
  rojo "No hay un repositorio git en $REPO_DIR."
  echo "Ejecuta el script desde dentro del repositorio clonado, por ejemplo:"
  echo "  bash ~/Cazador-de-Suenos-Siga-Web/deploy/deploy-on-server.sh"
  exit 1
fi

echo "Repositorio: $REPO_DIR"

if [[ ! -d "$SITE_ROOT" ]]; then
  rojo "No existe el directorio del sitio: $SITE_ROOT"
  exit 1
fi

# --- 1. Traer la ultima version ------------------------------------------------
azul "==> Actualizando el repositorio desde GitHub..."
cd "$REPO_DIR"
git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"
echo "    $(git log --oneline -1)"

for item in "${FILES[@]}" "${DIRS[@]}"; do
  if [[ ! -e "$REPO_DIR/$item" ]]; then
    rojo "Falta en el repositorio: $item"
    exit 1
  fi
done

# --- 2. Respaldo ---------------------------------------------------------------
STAMP="$(date +%Y%m%d-%H%M%S)"
azul "==> Respaldando el sitio actual..."
sudo mkdir -p /root/backups
sudo tar -czf "/root/backups/sitio-$STAMP.tar.gz" -C "$SITE_ROOT" .
echo "    /root/backups/sitio-$STAMP.tar.gz"

# --- 3. Publicar ---------------------------------------------------------------
azul "==> Publicando archivos..."
for f in "${FILES[@]}"; do
  echo "    -> $f"
  sudo cp -a "$REPO_DIR/$f" "$SITE_ROOT/$f"
done
for d in "${DIRS[@]}"; do
  echo "    -> $d/"
  sudo mkdir -p "$SITE_ROOT/$d"
  # El punto final copia el CONTENIDO del directorio, no el directorio dentro de si mismo.
  sudo cp -a "$REPO_DIR/$d/." "$SITE_ROOT/$d/"
done

azul "==> Ajustando permisos..."
sudo chown -R www-data:www-data "$SITE_ROOT"
sudo find "$SITE_ROOT" -type f -exec chmod 644 {} \;
sudo find "$SITE_ROOT" -type d -exec chmod 755 {} \;

# Los archivos estaticos no necesitan recarga, pero no cuesta nada y cubre el caso
# de que se haya tocado la configuracion de Nginx.
azul "==> Recargando Nginx..."
sudo nginx -t && sudo systemctl reload nginx

# --- 4. Verificacion ------------------------------------------------------------
azul "==> Verificando el sitio publicado..."
fallos=0

comprobar() {
  local ruta="$1" texto="${2:-}"
  local url="https://$DOMAIN$ruta?cb=$STAMP"
  local codigo
  codigo="$(curl -s -o /tmp/deploy-check -w '%{http_code}' "$url" || echo 000)"
  if [[ "$codigo" != "200" ]]; then
    rojo "    HTTP $codigo  $ruta"
    fallos=$((fallos + 1))
  elif [[ -n "$texto" ]] && ! grep -q "$texto" /tmp/deploy-check; then
    rojo "    VIEJO      $ruta (responde 200 pero le falta '$texto')"
    fallos=$((fallos + 1))
  else
    verde "    OK 200     $ruta"
  fi
}

comprobar "/"
comprobar "/checkout.html" "bank-transfer-always"
comprobar "/order-confirmation.html"
comprobar "/js/commerce-urls.js" "getCheckoutUrl"
comprobar "/css/checkout-commerce.css"
comprobar "/config/products.json"
comprobar "/vitolas/puro-habano.html" "commerce-urls.js"
rm -f /tmp/deploy-check

echo
if [[ "$fallos" -eq 0 ]]; then
  verde "Despliegue completado y verificado: https://$DOMAIN/checkout.html"
else
  rojo "Terminado con $fallos comprobacion(es) fallida(s)."
  echo "Para volver al estado anterior:"
  echo "  sudo tar -xzf /root/backups/sitio-$STAMP.tar.gz -C $SITE_ROOT"
  exit 1
fi
