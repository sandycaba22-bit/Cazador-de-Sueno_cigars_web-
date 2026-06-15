# Acceso SSH a la VM GCP — 35.237.216.105

## Estado detectado

| Comprobación | Resultado |
|---|---|
| Puerto 22 (SSH) | Abierto |
| Puerto 80 (HTTP) | Cerrado — Nginx no configurado aún |
| Puerto 443 (HTTPS) | Cerrado |
| DNS cazadordesuenocigars.com | No configurado |
| Clave SSH en `C:\Users\sandy\.ssh\` | **No existe** (solo `known_hosts`) |

Sin clave privada, el despliegue automático desde esta PC no puede completarse.

---

## Opción A — SSH desde Google Cloud Console (recomendada, sin instalar nada)

1. Entra a [console.cloud.google.com](https://console.cloud.google.com) → **Compute Engine** → **VM instances**.
2. Verifica que la VM esté **Running**.
3. Clic en **SSH** (abre terminal en el navegador).
4. En la VM, pega y ejecuta:

```bash
sudo mkdir -p /var/www/cazador-de-suenos-cigars
sudo chown -R $USER:$USER /var/www/cazador-de-suenos-cigars
```

5. En tu PC (PowerShell), sube el sitio — reemplaza `USUARIO` por el que muestra `whoami` en la VM:

```powershell
cd C:\Users\sandy\cazador-de-suenos-cigars
scp -r index.html style.css intro.js logo-render.js nav.js robots.txt sitemap.xml img images vitolas deploy USUARIO@35.237.216.105:/var/www/cazador-de-suenos-cigars/
```

6. De vuelta en la VM SSH:

```bash
bash /var/www/cazador-de-suenos-cigars/deploy/setup-server.sh
```

7. Abre firewall GCP si hace falta: **VPC network → Firewall** → regla `allow-http-https` con TCP 80 y 443.

---

## Opción B — Crear clave SSH en Windows y agregarla a la VM

```powershell
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\id_ed25519_gcp -N '""'
Get-Content $env:USERPROFILE\.ssh\id_ed25519_gcp.pub
```

Copia la línea pública y en GCP:
**Compute Engine → Metadata → SSH Keys → Add item**

Luego despliega:

```powershell
cd C:\Users\sandy\cazador-de-suenos-cigars
.\deploy\deploy-from-windows.ps1 -SshUser TU_USUARIO -ServerIp 35.237.216.105
```

Si usas clave custom:

```powershell
$env:SSH_KEY = "$env:USERPROFILE\.ssh\id_ed25519_gcp"
ssh -i $env:SSH_KEY USUARIO@35.237.216.105
```

---

## DNS GoDaddy (después de que HTTP por IP funcione)

| Tipo | Nombre | Valor |
|---|---|---|
| A | @ | 35.237.216.105 |
| CNAME | www | cazadordesuenocigars.com. |

Luego en la VM:

```bash
sudo certbot --nginx -d www.cazadordesuenocigars.com -d cazadordesuenocigars.com
sudo cp /var/www/cazador-de-suenos-cigars/deploy/nginx-cazador-de-suenos.conf /etc/nginx/sites-available/cazador-de-suenos
sudo nginx -t && sudo systemctl reload nginx
```

---

## Verificación post-despliegue

```bash
curl -I http://35.237.216.105/
curl -I http://35.237.216.105/vitolas/el-emperador.html
curl -I http://35.237.216.105/vitolas/el-sultan.html
```

En navegador:
- http://35.237.216.105/ (inmediato)
- https://www.cazadordesuenocigars.com/ (tras DNS + certbot)
