# Acceso SSH a la VM de producción

**Servidor:** `34.24.248.250` (Google Cloud) · **Sitio:** https://cazadordesuenocigar.com

Esta guía es para **conectarte por SSH desde PowerShell** y poder desplegar. El sitio ya
está instalado y funcionando: Nginx, HTTPS y DNS están configurados desde hace tiempo.

> Si algún día hay que montar un servidor desde cero, eso es otra cosa y está en
> [`DEPLOY.md`](DEPLOY.md). No mezcles ambos procedimientos.

---

## Dos cosas que NUNCA debes hacer en este servidor

| Acción | Por qué |
|---|---|
| Ejecutar `setup-server.sh` | Reescribe Nginx con una configuración HTTP para otro dominio (`cazadordesuenocigars.com`, con "s"). Tumba el HTTPS del sitio en vivo. Solo sirve para una instalación desde cero. |
| Subir `index.html` | El del repositorio es una maqueta de 5 KB. La portada real del servidor pesa ~81 KB y no está en git. Subirlo la destruye. |

El script `deploy-from-windows.ps1` ya respeta ambas reglas.

---

## Paso 1 — Averigua tu usuario en el servidor

Abre el SSH del navegador (Compute Engine → VM instances → botón **SSH**) y ejecuta:

```bash
whoami
```

Anota el resultado: es tu `USUARIO`. Deja esa ventana abierta para el paso 4.

## Paso 2 — Comprueba si ya tienes acceso

Puede que no haga falta configurar nada. En PowerShell:

```powershell
ssh TU_USUARIO@34.24.248.250 "echo OK"
```

La primera vez preguntará si confías en el servidor: escribe `yes`.

- Responde `OK` → listo, salta al **paso 6**.
- Pide contraseña o dice `Permission denied` → sigue al paso 3.

## Paso 3 — Crea tu llave SSH (solo si no la tienes)

```powershell
Test-Path $env:USERPROFILE\.ssh\id_ed25519.pub
```

Si devuelve `False`:

```powershell
ssh-keygen -t ed25519 -C "pc-sandy"
```

Pulsa Enter en las tres preguntas. Eso acepta la ruta por defecto y deja la llave sin
contraseña, que es lo práctico aquí: con contraseña te la pedirá en cada despliegue.

Se crean dos archivos en `%USERPROFILE%\.ssh\`:

- `id_ed25519` — llave privada. No se comparte ni se sube a git nunca.
- `id_ed25519.pub` — llave pública. Es la que se copia al servidor.

## Paso 4 — Registra la llave pública en el servidor

Cópiala al portapapeles:

```powershell
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub | Set-Clipboard
```

Vuelve al SSH del navegador y ejecuta esto pegando tu llave donde indica, sin quitar las
comillas:

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo "PEGA_AQUI_TU_LLAVE" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

> Se hace así, y no por **Compute Engine → Metadata → SSH Keys**, porque al pegar una
> llave en Metadata, Google deduce el nombre de usuario del comentario de la llave y suele
> quedar distinto al que usas en el navegador. Por `authorized_keys` la llave queda atada
> exactamente al usuario que ya te funciona.

## Paso 5 — Vuelve a probar

```powershell
ssh TU_USUARIO@34.24.248.250 "echo OK"
```

Debe responder `OK` sin pedir nada más.

## Paso 6 — Despliega

```powershell
cd C:\Users\sandy\Documents\cazador-sueno-web

# Ensayo: muestra qué subiría, sin tocar el servidor
.\deploy\deploy-from-windows.ps1 -SshUser TU_USUARIO -DryRun

# Despliegue real
.\deploy\deploy-from-windows.ps1 -SshUser TU_USUARIO
```

No hace falta `-ServerIp`: la IP correcta es el valor por defecto, y antes de subir nada el
script comprueba que coincida con el registro A del dominio.

---

## Si el paso 5 sigue fallando

Lo más probable es que la VM tenga **OS Login** activado, que ignora las llaves puestas a
mano en `authorized_keys`. Compruébalo desde el SSH del navegador:

```bash
curl -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/project/attributes/enable-oslogin"
```

Si responde `TRUE`, la llave se registra con `gcloud`:

```powershell
gcloud auth login          # con la cuenta de Google dueña del servidor
gcloud compute os-login ssh-keys add --key-file="$env:USERPROFILE\.ssh\id_ed25519.pub"
```

Ojo: el `gcloud` de esta PC está autenticado con una cuenta que **no ve** esta VM (en sus
proyectos ni siquiera está habilitada la API de Compute Engine). Hay que entrar con la
cuenta que usas en el SSH del navegador.

---

## Diagnóstico rápido de conexión

Si SSH falla, esto distingue entre un problema de red y uno de credenciales:

```powershell
Test-NetConnection 34.24.248.250 -Port 22
```

| Resultado | Significado |
|---|---|
| `TcpTestSucceeded : True` | El servidor responde. El problema es de llave o de usuario. |
| Timeout | No hay nadie escuchando en esa IP: servidor apagado, IP equivocada o firewall. |

Y para confirmar que la IP sigue siendo la buena:

```powershell
Resolve-DnsName cazadordesuenocigar.com -Type A
```

Debe devolver `34.24.248.250`. Si devuelve otra cosa, el servidor cambió de dirección y hay
que actualizar el valor por defecto de `-ServerIp` en `deploy-from-windows.ps1`.

---

## Verificación después de desplegar

El script ya verifica esto solo, pero si quieres comprobarlo a mano:

```powershell
curl.exe -I https://cazadordesuenocigar.com/
curl.exe -I https://cazadordesuenocigar.com/checkout.html
curl.exe -I https://cazadordesuenocigar.com/js/commerce-urls.js
curl.exe -I https://cazadordesuenocigar.com/css/checkout-commerce.css
```

Las cuatro deben responder `200`. Si `commerce-urls.js` o `checkout-commerce.css` dan `404`,
el despliegue no subió la capa de comercio y el checkout seguirá con la versión vieja.
