#!/usr/bin/env bash
# Instala y arranca cds-commerce en el servidor.
#
# Uso (como root o con sudo), desde cualquier sitio:
#   sudo bash /var/www/cazador-de-suenos-cigars/deploy/install-cds-commerce.sh
#
# No pisa un commerce.env ya existente: ahí viven las claves de CardNET/PayPal.

set -euo pipefail

SITE_ROOT="${SITE_ROOT:-/var/www/cazador-de-suenos-cigars}"
ENV_FILE="${ENV_FILE:-/etc/cazador-de-suenos/commerce.env}"
UNIT_SRC="$SITE_ROOT/server/commerce/cds-commerce.service"
UNIT_DST=/etc/systemd/system/cds-commerce.service
EXAMPLE="$SITE_ROOT/server/commerce/.env.example"
DATA_DIR=/var/lib/cazador-de-suenos/commerce

if [[ $EUID -ne 0 ]]; then
  echo "Ejecuta este script con sudo." >&2
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  echo "Node.js no está en el PATH. Instálalo (>=18) antes de continuar." >&2
  exit 1
fi

NODE_MAJOR="$(node -p "process.versions.node.split('.')[0]")"
if [[ "$NODE_MAJOR" -lt 18 ]]; then
  echo "Se necesita Node.js 18 o superior. Hay $(node -v)." >&2
  exit 1
fi

if [[ ! -f "$SITE_ROOT/server/commerce/server.js" ]]; then
  echo "No encuentro $SITE_ROOT/server/commerce/server.js. Sube el código primero." >&2
  exit 1
fi

install -d -m 0750 -o root -g www-data /etc/cazador-de-suenos
install -d -m 0700 -o www-data -g www-data "$DATA_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  if [[ ! -f "$EXAMPLE" ]]; then
    echo "Falta $EXAMPLE; no puedo crear $ENV_FILE." >&2
    exit 1
  fi
  echo "Creando $ENV_FILE a partir del ejemplo..."
  umask 077
  cp "$EXAMPLE" "$ENV_FILE"
  QUOTE_SECRET="$(openssl rand -hex 32)"
  if grep -q '^COMMERCE_QUOTE_SECRET=' "$ENV_FILE"; then
    sed -i "s|^COMMERCE_QUOTE_SECRET=.*|COMMERCE_QUOTE_SECRET=$QUOTE_SECRET|" "$ENV_FILE"
  else
    printf '\nCOMMERCE_QUOTE_SECRET=%s\n' "$QUOTE_SECRET" >> "$ENV_FILE"
  fi
  chown root:www-data "$ENV_FILE"
  chmod 0640 "$ENV_FILE"
  echo "Generada COMMERCE_QUOTE_SECRET. Completa las claves de CardNET cuando las tengas."
else
  echo "Conservo $ENV_FILE (ya existía)."
  chown root:www-data "$ENV_FILE"
  chmod 0640 "$ENV_FILE"
fi

# En este servidor el sandbox jamás debe quedar encendido: un fallo de CardNET
# se registraría como pedido confirmado.
if grep -q '^COMMERCE_SANDBOX_ENABLED=' "$ENV_FILE"; then
  sed -i 's|^COMMERCE_SANDBOX_ENABLED=.*|COMMERCE_SANDBOX_ENABLED=false|' "$ENV_FILE"
else
  printf '\nCOMMERCE_SANDBOX_ENABLED=false\n' >> "$ENV_FILE"
fi

if ! grep -q '^COMMERCE_QUOTE_SECRET=.\+' "$ENV_FILE"; then
  QUOTE_SECRET="$(openssl rand -hex 32)"
  if grep -q '^COMMERCE_QUOTE_SECRET=' "$ENV_FILE"; then
    sed -i "s|^COMMERCE_QUOTE_SECRET=.*|COMMERCE_QUOTE_SECRET=$QUOTE_SECRET|" "$ENV_FILE"
  else
    printf '\nCOMMERCE_QUOTE_SECRET=%s\n' "$QUOTE_SECRET" >> "$ENV_FILE"
  fi
  echo "Generada COMMERCE_QUOTE_SECRET (no había una clave de firma)."
fi

install -m 0644 "$UNIT_SRC" "$UNIT_DST"

NODE_BIN="$(command -v node)"
sed -i "s|^ExecStart=.*|ExecStart=${NODE_BIN} ${SITE_ROOT}/server/commerce/server.js|" "$UNIT_DST"

# El proceso corre como www-data y solo necesita leer el código. Propietario root
# para que un compromiso del servicio no pueda reescribir los adaptadores.
chown -R root:www-data "$SITE_ROOT/server/commerce"
find "$SITE_ROOT/server/commerce" -type f -exec chmod 644 {} \;
find "$SITE_ROOT/server/commerce" -type d -exec chmod 755 {} \;
if [[ -f "$SITE_ROOT/server/commerce/.env" ]]; then
  chmod 600 "$SITE_ROOT/server/commerce/.env"
  chown root:www-data "$SITE_ROOT/server/commerce/.env"
fi

systemctl daemon-reload
systemctl enable cds-commerce
systemctl restart cds-commerce
sleep 1

if ! systemctl is-active --quiet cds-commerce; then
  echo "cds-commerce no arrancó. Últimos logs:" >&2
  journalctl -u cds-commerce -n 40 --no-pager >&2
  exit 1
fi

HEALTH="$(curl -fsS http://127.0.0.1:8788/api/commerce/health || true)"
if [[ "$HEALTH" != *'"ok":true'* && "$HEALTH" != *'"ok": true'* ]]; then
  echo "El servicio corre pero /health no responde OK:" >&2
  echo "$HEALTH" >&2
  journalctl -u cds-commerce -n 40 --no-pager >&2
  exit 1
fi

echo "cds-commerce activo en 127.0.0.1:8788"
echo "$HEALTH"
echo
echo "Siguiente: sudo nginx -t && sudo systemctl reload nginx"
echo "Luego: curl -sS https://www.cazadordesuenocigars.com/api/commerce/health"
