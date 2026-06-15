# Comandos rápidos — IP: 35.237.216.105

## GoDaddy DNS (pegar ahora)

| Tipo  | Nombre | Valor                | TTL |
|-------|--------|----------------------|-----|
| **A** | `@`    | `35.237.216.105`     | 600 |
| **CNAME** | `www` | `cazadordesuenocigars.com.` | 600 |

---

## Subir sitio desde Windows (PowerShell)

```powershell
cd C:\Users\sandy\cazador-de-suenos-cigars
scp -r index.html style.css intro.js logo-render.js nav.js robots.txt sitemap.xml img images vitolas USUARIO@35.237.216.105:/var/www/cazador-de-suenos-cigars/
```

Reemplaza `USUARIO` por tu usuario SSH en la VM (ej. tu nombre de Google o `ubuntu`).

---

## SSH al servidor

```bash
ssh USUARIO@35.237.216.105
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
# Debe mostrar: 35.237.216.105

dig cazadordesuenocigars.com +short
# Debe mostrar: 35.237.216.105
```

---

## Verificar sitio

- http://35.237.216.105 (antes de SSL/DNS)
- https://www.cazadordesuenocigars.com (después de DNS + certbot)
