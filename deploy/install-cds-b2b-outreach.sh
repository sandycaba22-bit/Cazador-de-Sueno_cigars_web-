#!/usr/bin/env bash
# Instala units systemd del buscador B2B. NO pisa b2b-outreach.env si ya existe.
#
#   sudo bash /var/www/html/deploy/install-cds-b2b-outreach.sh
#
# Restaurar credenciales desde un archivo local (p. ej. tras subir .env con scp):
#   sudo bash .../install-cds-b2b-outreach.sh --merge-secrets /tmp/b2b-outreach.env

set -euo pipefail

SITE_ROOT="${SITE_ROOT:-/var/www/html}"
ENV_FILE="${ENV_FILE:-/etc/cazador-de-suenos/b2b-outreach.env}"
EXAMPLE="$SITE_ROOT/server/b2b-outreach/.env.example"
B2B_DIR="$SITE_ROOT/server/b2b-outreach"
DATA_DIR=/var/lib/cazador-de-suenos/b2b-outreach

MERGE_SECRETS=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --merge-secrets)
      MERGE_SECRETS="${2:-}"
      shift 2
      ;;
    *)
      echo "Opción desconocida: $1" >&2
      exit 1
      ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  echo "Ejecuta con sudo." >&2
  exit 1
fi

if [[ ! -f "$B2B_DIR/telegram_bot.py" ]]; then
  echo "No encuentro $B2B_DIR/telegram_bot.py" >&2
  exit 1
fi

install -d -m 0750 -o root -g www-data /etc/cazador-de-suenos
install -d -m 0750 -o www-data -g www-data "$DATA_DIR"/{inbox,sent,failed,dudoso,solo_telefono,logs,data}

_env_has_valid_telegram() {
  local f="$1"
  [[ -f "$f" ]] || return 1
  local token chat
  token="$(grep -E '^TELEGRAM_BOT_TOKEN=' "$f" | head -1 | cut -d= -f2- | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  chat="$(grep -E '^TELEGRAM_CHAT_ID=' "$f" | head -1 | cut -d= -f2- | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  [[ -n "$token" && "$token" == *:* ]] || return 1
  [[ "$token" != *PEGA_AQUI* && "$token" != *TU_TOKEN* ]] || return 1
  [[ -n "$chat" && "$chat" =~ ^-?[0-9]+$ ]] || return 1
  [[ "$chat" != *PEGA_AQUI* && "$chat" != *TU_CHAT* ]] || return 1
  return 0
}

_merge_key_from() {
  local src="$1" key="$2" dest="$3"
  local val
  val="$(grep -E "^${key}=" "$src" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '\r' || true)"
  val="$(echo "$val" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  [[ -n "$val" ]] || return 0
  if grep -qE "^${key}=" "$dest"; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$dest"
  else
    printf '%s=%s\n' "$key" "$val" >> "$dest"
  fi
}

if [[ -n "$MERGE_SECRETS" ]]; then
  if [[ ! -f "$MERGE_SECRETS" ]]; then
    echo "No existe $MERGE_SECRETS" >&2
    exit 1
  fi
  if ! _env_has_valid_telegram "$MERGE_SECRETS"; then
    echo "El archivo fuente no tiene TELEGRAM_* válidos." >&2
    exit 1
  fi
  if [[ ! -f "$ENV_FILE" ]]; then
    if [[ -f "$EXAMPLE" ]]; then
      cp "$EXAMPLE" "$ENV_FILE"
    else
      touch "$ENV_FILE"
    fi
  fi
  for key in TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID SENDER_NAME SENDER_CONTACT FIRMA_EMAIL FIRMA_TELEFONO; do
    _merge_key_from "$MERGE_SECRETS" "$key" "$ENV_FILE"
  done
  chown root:www-data "$ENV_FILE"
  chmod 0640 "$ENV_FILE"
  echo "Credenciales fusionadas en $ENV_FILE (sin mostrar valores)."
fi

if [[ -f "$ENV_FILE" ]]; then
  echo "Conservo $ENV_FILE (no se sobrescribe)."
  chown root:www-data "$ENV_FILE"
  chmod 0640 "$ENV_FILE"
elif [[ -f "$EXAMPLE" ]]; then
  echo "Creando $ENV_FILE desde .env.example (completa TELEGRAM_* antes de buscar)."
  cp "$EXAMPLE" "$ENV_FILE"
  chown root:www-data "$ENV_FILE"
  chmod 0640 "$ENV_FILE"
else
  echo "Falta $EXAMPLE; crea $ENV_FILE a mano." >&2
  exit 1
fi

if ! _env_has_valid_telegram "$ENV_FILE"; then
  if _env_has_valid_telegram "$B2B_DIR/.env"; then
    echo "Restaurando TELEGRAM_* desde $B2B_DIR/.env hacia $ENV_FILE..."
    for key in TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID SENDER_NAME SENDER_CONTACT FIRMA_EMAIL FIRMA_TELEFONO; do
      _merge_key_from "$B2B_DIR/.env" "$key" "$ENV_FILE"
    done
  fi
fi

if grep -qE '^FUENTE_LEADS=' "$ENV_FILE"; then
  sed -i 's|^FUENTE_LEADS=.*|FUENTE_LEADS=osm|' "$ENV_FILE"
else
  printf '\nFUENTE_LEADS=osm\n' >> "$ENV_FILE"
fi

for unit in cds-b2b-outreach.service cds-b2b-buscar.service cds-b2b-buscar.timer; do
  if [[ -f "$B2B_DIR/$unit" ]]; then
    cp "$B2B_DIR/$unit" "/etc/systemd/system/$unit"
  fi
done

systemctl daemon-reload
systemctl enable cds-b2b-outreach.service 2>/dev/null || true
systemctl enable cds-b2b-buscar.timer 2>/dev/null || true

if _env_has_valid_telegram "$ENV_FILE"; then
  echo "Telegram: credenciales OK en $ENV_FILE."
else
  echo "AVISO: $ENV_FILE aún sin TELEGRAM_* válidos. Usa --merge-secrets o edita a mano." >&2
fi

echo "Listo. Reinicia: systemctl restart cds-b2b-outreach.service && systemctl start cds-b2b-buscar.service"
