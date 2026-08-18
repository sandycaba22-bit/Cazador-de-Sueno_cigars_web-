# Comandos rápidos — IP: 34.24.248.250

## GoDaddy DNS (pegar ahora)

| Tipo  | Nombre | Valor                | TTL |
|-------|--------|----------------------|-----|
| **A** | `@`    | `34.24.248.250`     | 600 |
| **CNAME** | `www` | `cazadordesuenocigars.com.` | 600 |

---

## Subir sitio desde Windows (PowerShell)

```powershell
cd C:\Users\sandy\cazador-de-suenos-cigars
scp -r index.html style.css intro.js logo-render.js nav.js robots.txt sitemap.xml img images vitolas USUARIO@34.24.248.250:/var/www/cazador-de-suenos-cigars/
```

Reemplaza `USUARIO` por tu usuario SSH en la VM (ej. tu nombre de Google o `ubuntu`).

---

## SSH al servidor

```bash
ssh USUARIO@34.24.248.250
```

---

## En el servidor (después de subir archivos)

```bash
sudo chown -R www-data:www-data /var/www/cazador-de-suenos-cigars
sudo cp nginx-cazador-de-suenos.conf /etc/nginx/sites-available/cazador-de-suenos
sudo ln -sf /etc/nginx/sites-available/cazador-de-suenos /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx
sudo certbot --nginx -d www.cazadordesuenocigars.com -d cazadordesuenocigars.com
```

---

## Verificar DNS

```bash
dig www.cazadordesuenocigars.com +short
# Debe mostrar: 34.24.248.250

dig cazadordesuenocigars.com +short
# Debe mostrar: 34.24.248.250
```

---

## Verificar sitio

- http://34.24.248.250 (antes de SSL/DNS)
- https://www.cazadordesuenocigars.com (después de DNS + certbot)
- https://www.cazadordesuenocigars.com/api/ai-sommelier/health (debe devolver `{"ok":true,...}` si el sommelier está en marcha)
