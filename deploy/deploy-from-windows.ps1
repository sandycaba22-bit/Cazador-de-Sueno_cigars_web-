# Despliegue Cazador de Sueños Cigars - Windows PowerShell
#
# Uso normal (publica el checkout y todo el comercio):
#   .\deploy\deploy-from-windows.ps1 -SshUser TU_USUARIO
#
# Ensayo sin subir nada (muestra exactamente qué haría):
#   .\deploy\deploy-from-windows.ps1 -SshUser TU_USUARIO -DryRun
#
# IMPORTANTE - index.html:
#   El index.html del repositorio es una maqueta de 5 KB, NO la portada real del sitio
#   (la del servidor pesa ~81 KB y fue editada fuera de git). Por eso NO se sube por
#   defecto. Subirlo destruiría la portada en producción. Solo usa -IncludeIndex
#   después de haber sincronizado el index.html real del servidor hacia el repositorio.

param(
    [Parameter(Mandatory = $true)]
    [string]$SshUser,

    # IP del servidor. Debe coincidir con el registro A del dominio: si no coincide,
    # el script avisa antes de subir nada (una IP vieja da "Connection timed out").
    [string]$ServerIp = "34.24.248.250",

    [string]$RemotePath = "/var/www/cazador-de-suenos-cigars",

    [string]$Domain = "cazadordesuenocigar.com",

    # Sube también los archivos históricos del sitio (nav, intro, imágenes, sitemap...).
    # Están en el servidor desde antes y pueden haber sido editados allí: úsalo solo si
    # sabes que la copia local es la buena.
    [switch]$IncludeSiteFiles,

    # Sube index.html. Lee la advertencia de arriba antes de activarlo.
    [switch]$IncludeIndex,

    [switch]$SkipBackup,

    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Remote = "${SshUser}@${ServerIp}"

# --- Qué se publica -----------------------------------------------------------------
# Capa de comercio: es lo que vive en git y lo que el checkout necesita para funcionar.
$CommerceFiles = @(
    "checkout.html",
    "order-confirmation.html",
    "style.css"
)
$CommerceDirs = @(
    "css",       # checkout-onepage.css y estilos del sitio
    "js",        # cart, checkout, catalog, commerce-urls...
    "config",    # products.json y shipping-zones.json: el carrito los pide por fetch
    "locales",   # traducciones del selector de idioma
    "assets",    # imágenes de producto del carrito
    "vitolas"    # páginas de producto (llevan el script commerce-urls.js)
)

# Archivos históricos del sitio. No se tocan salvo que se pidan explícitamente.
$SiteFiles = @(
    "intro.js", "logo-render.js", "nav.js", "age-gate.js", "hero-parallax.js",
    "robots.txt", "sitemap.xml"
)
$SiteDirs = @("img", "images")

# Nunca se publican enteros: maquetas, páginas de prueba, el panel de
# administración y secretos. server/commerce se sube aparte (cds-commerce).
$NeverDeploy = @(
    "index_temp.html", "index_server.html", "cazador-de-suenos-completo.html",
    "cart-test.html", "admin.html", "package.json", ".env.example"
)

$Files = @() + $CommerceFiles
$Dirs = @() + $CommerceDirs

if ($IncludeSiteFiles) {
    $Files += $SiteFiles
    $Dirs += $SiteDirs
}

if ($IncludeIndex) {
    Write-Warning "index.html incluido. Si la copia local sigue siendo la maqueta de 5 KB, esto BORRA la portada real del sitio."
    $answer = Read-Host "Escribe SI para continuar"
    if ($answer -ne "SI") { throw "Cancelado por el usuario." }
    $Files += "index.html"
}

# --- Comprobaciones previas ---------------------------------------------------------
Write-Host "==> Verificando archivos locales..." -ForegroundColor Cyan
$Missing = @()
foreach ($item in ($Files + $Dirs)) {
    if (-not (Test-Path (Join-Path $ProjectRoot $item))) { $Missing += $item }
}
if ($Missing.Count -gt 0) {
    throw "No encontrados en el proyecto: $($Missing -join ', ')"
}

Write-Host "    Archivos: $($Files -join ', ')"
Write-Host "    Carpetas: $($Dirs -join ', ')"
Write-Host "    Excluidos siempre: $($NeverDeploy -join ', ')" -ForegroundColor DarkGray
if (-not $IncludeIndex) {
    Write-Host "    index.html NO se sube (portada del servidor intacta)." -ForegroundColor DarkGray
}

if ($DryRun) {
    Write-Host ""
    Write-Host "Modo ensayo: no se sube nada. Destino habria sido ${Remote}:${RemotePath}/" -ForegroundColor Yellow
    Write-Host "Tambien se subiria server/commerce (sin .env), install-cds-commerce.sh y ensure-nginx-commerce.sh"
    return
}

Write-Host "==> Comprobando que la IP coincide con el DNS del dominio..." -ForegroundColor Cyan
$dnsIps = $null
try {
    $dnsIps = (Resolve-DnsName $Domain -Type A -ErrorAction Stop | Where-Object { $_.IPAddress }).IPAddress
} catch {
    Write-Warning "No se pudo resolver $Domain ($($_.Exception.Message)). Se continua sin comprobar."
}

if ($dnsIps) {
    if ($dnsIps -contains $ServerIp) {
        Write-Host "    $Domain -> $ServerIp" -ForegroundColor Green
    } else {
        Write-Warning "$Domain apunta a $($dnsIps -join ', ') pero vas a desplegar en $ServerIp."
        Write-Warning "Desplegar en la IP equivocada no publica nada, y una IP muerta da 'Connection timed out'."
        $answer = Read-Host "Escribe SI para continuar de todos modos"
        if ($answer -ne "SI") { throw "Cancelado: revisa el parametro -ServerIp." }
    }
}

Write-Host "==> Verificando conexión SSH a $Remote ..." -ForegroundColor Cyan
ssh -o BatchMode=yes -o ConnectTimeout=15 $Remote "echo SSH OK && test -d $RemotePath && echo 'Directorio del sitio OK'"
if ($LASTEXITCODE -ne 0) { throw "No hay acceso SSH o el directorio $RemotePath no existe." }

# --- Respaldo -----------------------------------------------------------------------
if (-not $SkipBackup) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    Write-Host "==> Respaldando sitio actual en el servidor..." -ForegroundColor Cyan
    ssh $Remote "sudo mkdir -p /root/backups && sudo tar -czf /root/backups/sitio-$stamp.tar.gz -C $RemotePath . && echo 'Respaldo: /root/backups/sitio-$stamp.tar.gz'"
    if ($LASTEXITCODE -ne 0) { throw "Falló el respaldo. Se aborta el despliegue." }
}

# --- Subida -------------------------------------------------------------------------
# Los archivos pertenecen a www-data; se cede la propiedad temporalmente para poder escribir.
Write-Host "==> Preparando permisos de escritura..." -ForegroundColor Cyan
ssh $Remote "sudo chown -R `$(id -un):`$(id -gn) $RemotePath"
if ($LASTEXITCODE -ne 0) { throw "No se pudieron ajustar los permisos en el servidor." }

Write-Host "==> Subiendo archivos..." -ForegroundColor Cyan
foreach ($item in ($Files + $Dirs)) {
    $local = Join-Path $ProjectRoot $item
    Write-Host "    -> $item"
    scp -r -q $local "${Remote}:${RemotePath}/"
    if ($LASTEXITCODE -ne 0) { throw "Falló la subida de $item." }
}

# --- cds-commerce: adaptadores de pasarela y precios autoritativos -----------------
# Antes se excluía todo /server, así que el checkout nuevo nunca llegaba a
# producción y Nginx devolvía 404/410 en /api/commerce.
Write-Host "==> Subiendo cds-commerce (pasarelas + API)..." -ForegroundColor Cyan
$stageParent = Join-Path $env:TEMP "cds-commerce-upload"
$stage = Join-Path $stageParent "commerce"
if (Test-Path $stageParent) { Remove-Item -Recurse -Force $stageParent }
New-Item -ItemType Directory -Path $stageParent | Out-Null
Copy-Item (Join-Path $ProjectRoot "server\commerce") $stage -Recurse
Get-ChildItem $stage -Recurse -Force -File | Where-Object {
    $_.Name -eq ".env" -or $_.Name -eq ".env.local" -or $_.Extension -in @(".pem", ".key")
} | Remove-Item -Force
ssh $Remote "mkdir -p $RemotePath/server $RemotePath/deploy"
if ($LASTEXITCODE -ne 0) { throw "No se pudo crear server/ en el destino." }
scp -r -q $stage "${Remote}:${RemotePath}/server/"
if ($LASTEXITCODE -ne 0) { throw "Falló la subida de server/commerce." }
scp -q (Join-Path $ProjectRoot "deploy\install-cds-commerce.sh") "${Remote}:${RemotePath}/deploy/"
if ($LASTEXITCODE -ne 0) { throw "Falló la subida de install-cds-commerce.sh." }
scp -q (Join-Path $ProjectRoot "deploy\ensure-nginx-commerce.sh") "${Remote}:${RemotePath}/deploy/"
if ($LASTEXITCODE -ne 0) { throw "Falló la subida de ensure-nginx-commerce.sh." }
scp -q (Join-Path $ProjectRoot "deploy\nginx-cazador-de-suenos.conf") "${Remote}:${RemotePath}/deploy/"
if ($LASTEXITCODE -ne 0) { throw "Falló la subida de nginx-cazador-de-suenos.conf." }

Write-Host "==> Protegiendo /server/ y activando el proxy /api/commerce..." -ForegroundColor Cyan
ssh $Remote "sudo bash $RemotePath/deploy/ensure-nginx-commerce.sh"
if ($LASTEXITCODE -ne 0) { throw "No se pudo parchear Nginx. El código de comercio no debe quedar público: revisa el servidor." }

Write-Host "==> Restaurando permisos del servidor web..." -ForegroundColor Cyan
ssh $Remote "sudo chown -R www-data:www-data $RemotePath && sudo find $RemotePath -type f -exec chmod 644 {} \; && sudo find $RemotePath -type d -exec chmod 755 {} \;"
if ($LASTEXITCODE -ne 0) { throw "No se pudieron restaurar los permisos. Revisa el servidor antes de continuar." }

# Nota: no se ejecuta setup-server.sh. Ese script reescribe la configuración de Nginx
# con un bootstrap HTTP y tumbaría el HTTPS del sitio en vivo.
Write-Host "==> Instalando / reiniciando cds-commerce..." -ForegroundColor Cyan
ssh $Remote "sudo bash $RemotePath/deploy/install-cds-commerce.sh"
if ($LASTEXITCODE -ne 0) { throw "cds-commerce no arrancó. Revisa journalctl -u cds-commerce en el servidor." }

# --- Verificación -------------------------------------------------------------------
Write-Host "==> Verificando el sitio publicado..." -ForegroundColor Cyan
$cb = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$checks = @(
    @{ Url = "https://$Domain/";                                Contiene = $null },
    @{ Url = "https://$Domain/checkout.html";                   Contiene = "checkout-onepage.css" },
    @{ Url = "https://$Domain/js/checkout.js";                  Contiene = "/api/commerce" },
    @{ Url = "https://$Domain/css/checkout-onepage.css";        Contiene = $null },
    @{ Url = "https://$Domain/order-confirmation.html";         Contiene = $null },
    @{ Url = "https://$Domain/config/products.json";            Contiene = $null },
    @{ Url = "https://$Domain/vitolas/puro-habano.html";        Contiene = "commerce-urls.js" },
    @{ Url = "https://$Domain/api/commerce/health";             Contiene = '"ok":true' },
    @{ Url = "https://$Domain/server/commerce/server.js";       Contiene = $null; Esperado = 404 },
    @{ Url = "https://$Domain/.env";                            Contiene = $null; Esperado = 404 }
)

$fallos = 0
foreach ($check in $checks) {
    $url = "$($check.Url)?cb=$cb"
    $esperado = if ($check.ContainsKey("Esperado")) { [int]$check.Esperado } else { 200 }
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 20
        if ($esperado -ne 200) {
            Write-Warning "EXPUESTO $($check.Url) - se esperaba $esperado y llegó $($r.StatusCode)"
            $fallos++
        } elseif ($check.Contiene -and ($r.Content -notmatch [regex]::Escape($check.Contiene))) {
            Write-Warning "VIEJO  $($check.Url) - responde 200 pero le falta '$($check.Contiene)'"
            $fallos++
        } else {
            Write-Host "    OK $($r.StatusCode)  $($check.Url)" -ForegroundColor Green
        }
    } catch {
        $status = $null
        try { $status = [int]$_.Exception.Response.StatusCode } catch { }
        if ($esperado -ne 200 -and $status -eq $esperado) {
            Write-Host "    OK $status  $($check.Url)" -ForegroundColor Green
        } else {
            Write-Warning "FALLO  $($check.Url) - $($_.Exception.Message)"
            $fallos++
        }
    }
}

Write-Host ""
if ($fallos -eq 0) {
    Write-Host "Despliegue completado y verificado. https://$Domain/checkout.html" -ForegroundColor Green
} else {
    Write-Warning "Despliegue terminado con $fallos comprobacion(es) fallida(s). Revisa el detalle de arriba."
    exit 1
}
