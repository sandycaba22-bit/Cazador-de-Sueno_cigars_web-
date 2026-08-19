#!/usr/bin/env bash
# Inserta en el Nginx en vivo el proxy a cds-commerce y el bloqueo de
# /server/, /data/ y /deploy/ SIN sustituir el certificado SSL.
#
# Uso:
#   sudo bash /var/www/cazador-de-suenos-cigars/deploy/ensure-nginx-commerce.sh

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Ejecuta este script con sudo." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Se necesita python3 para parchear Nginx sin tocar el SSL." >&2
  exit 1
fi

CONF=""
for candidate in \
  /etc/nginx/sites-available/cazador-de-suenos \
  /etc/nginx/sites-enabled/cazador-de-suenos \
  /etc/nginx/sites-enabled/default
do
  if [[ -f "$candidate" ]] && grep -q 'root /var/www/cazador-de-suenos-cigars' "$candidate"; then
    CONF="$candidate"
    break
  fi
done

if [[ -z "$CONF" ]]; then
  for candidate in /etc/nginx/sites-enabled/* /etc/nginx/sites-available/*; do
    [[ -f "$candidate" ]] || continue
    if grep -q 'root /var/www/cazador-de-suenos-cigars' "$candidate"; then
      CONF="$candidate"
      break
    fi
  done
fi

if [[ -z "$CONF" ]]; then
  echo "No encuentro un server block con root /var/www/cazador-de-suenos-cigars." >&2
  echo "Copia a mano deploy/nginx-cazador-de-suenos.conf y ejecuta nginx -t." >&2
  exit 1
fi

stamp="$(date +%Y%m%d-%H%M%S)"
cp -a "$CONF" "${CONF}.bak-cds-${stamp}"
echo "Respaldo: ${CONF}.bak-cds-${stamp}"

python3 - "$CONF" << 'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
needle = "root /var/www/cazador-de-suenos-cigars"
idx = text.find(needle)
if idx < 0:
    raise SystemExit(f"No está el root del sitio en {path}")

line_end = text.find("\n", idx)
if line_end < 0:
    line_end = len(text)

deny = """
    # BEGIN cds-private-paths
    location ^~ /data/ { deny all; return 404; }
    location ^~ /server/ { deny all; return 404; }
    location ^~ /deploy/ { deny all; return 404; }
    location ~ /\\.env { deny all; return 404; }
    # END cds-private-paths
"""

proxy = """
    # BEGIN cds-commerce-proxy
    location /api/commerce {
        proxy_pass http://127.0.0.1:8788;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_connect_timeout 10s;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
        proxy_buffering off;
        proxy_cache off;
    }
    # END cds-commerce-proxy
"""

changed = False
if "location ^~ /server/" not in text:
    text = text[: line_end + 1] + deny + text[line_end + 1 :]
    changed = True
    print("Insertado bloqueo de /server/, /data/ y /deploy/")
else:
    print("Nginx ya bloquea /server/")

if "location /api/commerce" not in text:
    # Recalcular por si acabamos de insertar el deny.
    idx = text.find(needle)
    line_end = text.find("\n", idx)
    text = text[: line_end + 1] + proxy + text[line_end + 1 :]
    changed = True
    print("Insertado proxy /api/commerce → 127.0.0.1:8788")
else:
    print("Nginx ya tiene /api/commerce")

if changed:
    path.write_text(text, encoding="utf-8")
    print(f"Actualizado {path}")
else:
    print("Nada que cambiar")
PY

nginx -t
systemctl reload nginx
echo "Nginx recargado con proxy de comercio y rutas privadas bloqueadas."
