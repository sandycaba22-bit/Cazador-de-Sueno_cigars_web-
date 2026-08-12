# Despliegue desde Google Cloud Shell (navegador)

Si SSH desde tu PC falla, usa **Cloud Shell** en [console.cloud.google.com](https://console.cloud.google.com).

## 1. Subir proyecto a la VM

En Cloud Shell, ajusta `ZONE` (ej. `us-east1-b`):

```bash
ZONE=us-east1-b
INSTANCE=jaragoexpresselite

# Opción A: si el proyecto está en tu PC, súbelo primero a Cloud Shell con el botón "Upload"
# Luego:
gcloud compute scp --recurse ~/cazador-de-suenos-cigars $INSTANCE:/tmp/ --zone=$ZONE
gcloud compute ssh $INSTANCE --zone=$ZONE --command="sudo mkdir -p /var/www/cazador-de-suenos-cigars && sudo cp -r /tmp/cazador-de-suenos-cigars/* /var/www/cazador-de-suenos-cigars/ && sudo chown -R \$USER:\$USER /var/www/cazador-de-suenos-cigars"
```

## 2. Instalar Nginx en la VM

```bash
gcloud compute ssh $INSTANCE --zone=$ZONE --command="bash /var/www/cazador-de-suenos-cigars/deploy/remote-install.sh"
```

## 3. SSL (cuando DNS esté correcto)

```bash
gcloud compute ssh $INSTANCE --zone=$ZONE
sudo certbot --nginx -d www.cazadordesuenocigars.com -d cazadordesuenocigars.com
sudo cp /var/www/cazador-de-suenos-cigars/deploy/nginx-cazador-de-suenos.conf /etc/nginx/sites-available/cazador-de-suenos
sudo nginx -t && sudo systemctl reload nginx
```

## 4. Verificar

- http://cazadordesuenocigars.com/
- http://cazadordesuenocigars.com/vitolas/el-sultan.html
- https://www.cazadordesuenocigars.com/ (tras SSL)

## DNS GoDaddy — corregir www

| Tipo | Nombre | Valor correcto |
|---|---|---|
| A | @ | 34.24.248.250 |
| CNAME | www | cazadordesuenocigars.com. |

**Problema actual:** `www` apunta a `cazadordesuenocigars.com` (dominio distinto con IPs de GoDaddy).

## Clave SSH para Cursor (tu PC)

Añade en **Compute Engine → Metadata → SSH Keys**:

```
sandy:ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMXO6X+3xr7SJ5fxcEJHmt1czKVTj8Ids1ud20BTFawk sandy@DESKTOP-K4JIII1
```

Luego Cursor podrá conectar con `ssh sandy@34.24.248.250`.
