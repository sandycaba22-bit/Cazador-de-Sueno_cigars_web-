#!/usr/bin/env bash
# Arregla CORS del dominio vivo, trae DO (shipping.js) y reinicia PM2.
# Uso (en el servidor, como cazadordesueno1):
#   bash deploy/fix-pm2-commerce.sh
#
# PayPal OAuth 502: este script NO inventa el Client ID. Si el ID tiene menos
# de ~40 caracteres está truncado en el .env — hay que pegar el completo desde
# https://developer.paypal.com/ (app Sandbox).

set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/Cazador-de-Suenos-Siga-Web}"
APP_NAME="${APP_NAME:-cazador-web}"
DOMAIN_LIVE="https://cazadordesuenocigar.com"
DOMAIN_WWW="https://www.cazadordesuenocigar.com"
DOMAIN_LEGACY="https://www.cazadordesuenocigars.com"
WANTED_CORS="${DOMAIN_LIVE},${DOMAIN_WWW},${DOMAIN_LEGACY}"

cd "$REPO_DIR"
echo "==> Repo: $REPO_DIR"
echo "==> $(git log -1 --oneline)"

echo "==> git pull origin main"
git fetch origin main
git pull --ff-only origin main || git reset --hard origin/main
echo "    $(git log -1 --oneline)"

# Localiza el .env que usa el proceso (ecosystem o .env en repo / commerce)
ENV_CANDIDATES=(
  "$REPO_DIR/.env"
  "$REPO_DIR/server/commerce/.env"
  "$HOME/.cazador-commerce.env"
  "/etc/cazador-de-suenos/commerce.env"
)

ENV_FILE=""
for f in "${ENV_CANDIDATES[@]}"; do
  if [[ -f "$f" ]]; then
    ENV_FILE="$f"
    break
  fi
done

if [[ -z "$ENV_FILE" ]]; then
  ENV_FILE="$REPO_DIR/.env"
  touch "$ENV_FILE"
  echo "==> Creado $ENV_FILE"
fi

echo "==> Actualizando CORS en $ENV_FILE"
if grep -q '^COMMERCE_CORS_ORIGINS=' "$ENV_FILE"; then
  sed -i "s|^COMMERCE_CORS_ORIGINS=.*|COMMERCE_CORS_ORIGINS=${WANTED_CORS}|" "$ENV_FILE"
else
  printf '\nCOMMERCE_CORS_ORIGINS=%s\n' "$WANTED_CORS" >> "$ENV_FILE"
fi

# Avisos PayPal (sin imprimir secretos)
if grep -qE '^PAYPAL_CLIENT_ID=.' "$ENV_FILE"; then
  ID_LEN="$(grep -E '^PAYPAL_CLIENT_ID=' "$ENV_FILE" | head -n1 | cut -d= -f2- | tr -d '\r' | wc -c)"
  ID_LEN=$((ID_LEN))
  echo "    PAYPAL_CLIENT_ID length≈${ID_LEN}"
  if [[ "$ID_LEN" -lt 40 ]]; then
    echo "    ERROR: Client ID parece truncado (<40 chars). OAuth devolverá 502."
    echo "    Pega el Client ID completo de la app Sandbox en PayPal Developer."
  fi
else
  echo "    AVISO: no hay PAYPAL_CLIENT_ID en $ENV_FILE"
fi

if ! grep -qE '^PAYPAL_CLIENT_SECRET=.+' "$ENV_FILE"; then
  echo "    AVISO: PAYPAL_CLIENT_SECRET vacío o ausente"
fi

if grep -q '^PAYPAL_MODE=' "$ENV_FILE"; then
  sed -i 's|^PAYPAL_MODE=.*|PAYPAL_MODE=sandbox|' "$ENV_FILE"
else
  printf '\nPAYPAL_MODE=sandbox\n' >> "$ENV_FILE"
fi

# Confirmar DO en el shipping que cargará Node
if grep -q "{ code: 'DO'" "$REPO_DIR/js/shipping.js" || grep -q 'code: "DO"' "$REPO_DIR/js/shipping.js"; then
  echo "==> DO presente en js/shipping.js"
else
  echo "==> ERROR: DO no está en js/shipping.js tras el pull"
  exit 1
fi

echo "==> pm2 restart $APP_NAME"
pm2 restart "$APP_NAME"
sleep 2
pm2 describe "$APP_NAME" | head -n 40 || true

echo "==> Verificación local"
curl -sS http://127.0.0.1:8788/api/commerce/health || curl -sS http://127.0.0.1:3000/api/commerce/health || true
echo
echo "Listo. Desde fuera comprueba:"
echo "  curl -sS ${DOMAIN_LIVE}/api/commerce/config"
echo "  curl -sS -X POST ${DOMAIN_LIVE}/api/commerce/quote -H 'Content-Type: application/json' -H 'Origin: ${DOMAIN_LIVE}' -d '{\"items\":[{\"productId\":\"emperador\",\"unitType\":\"box\",\"quantity\":1}],\"country\":\"DO\"}'"
