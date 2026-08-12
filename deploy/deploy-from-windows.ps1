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

    [string]$ServerIp = "35.237.216.105",

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
    "css",       # styles.css + checkout-commerce.css
    "js",        # cart, checkout, commerce-urls, page-visibility, whatsapp-commerce...
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

# Nunca se publican: maquetas, páginas de prueba y el panel de administración.
$NeverDeploy = @(
    "index_temp.html", "index_server.html", "cazador-de-suenos-completo.html",
    "cart-test.html", "admin.html", "package.json", ".env.example", "server", "deploy"
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
    return
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

Write-Host "==> Restaurando permisos del servidor web..." -ForegroundColor Cyan
ssh $Remote "sudo chown -R www-data:www-data $RemotePath && sudo find $RemotePath -type f -exec chmod 644 {} \; && sudo find $RemotePath -type d -exec chmod 755 {} \;"
if ($LASTEXITCODE -ne 0) { throw "No se pudieron restaurar los permisos. Revisa el servidor antes de continuar." }

# Nota: no se ejecuta setup-server.sh. Ese script reescribe la configuración de Nginx
# con un bootstrap HTTP para otro dominio (cazadordesuenocigars.com) y tumbaría el HTTPS
# del sitio en vivo. Solo se usa en una instalación desde cero.
Write-Host "==> Recargando Nginx..." -ForegroundColor Cyan
ssh $Remote "sudo nginx -t && sudo systemctl reload nginx"

# --- Verificación -------------------------------------------------------------------
Write-Host "==> Verificando el sitio publicado..." -ForegroundColor Cyan
$cb = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$checks = @(
    @{ Url = "https://$Domain/";                          Contiene = $null },
    @{ Url = "https://$Domain/checkout.html";             Contiene = "bank-transfer-always" },
    @{ Url = "https://$Domain/js/commerce-urls.js";       Contiene = "getCheckoutUrl" },
    @{ Url = "https://$Domain/js/page-visibility.js";     Contiene = $null },
    @{ Url = "https://$Domain/css/checkout-commerce.css"; Contiene = $null },
    @{ Url = "https://$Domain/order-confirmation.html";   Contiene = $null },
    @{ Url = "https://$Domain/config/products.json";      Contiene = $null },
    @{ Url = "https://$Domain/vitolas/puro-habano.html";  Contiene = "commerce-urls.js" }
)

$fallos = 0
foreach ($check in $checks) {
    $url = "$($check.Url)?cb=$cb"
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 20
        if ($check.Contiene -and ($r.Content -notmatch [regex]::Escape($check.Contiene))) {
            Write-Warning "VIEJO  $($check.Url) - responde 200 pero le falta '$($check.Contiene)'"
            $fallos++
        } else {
            Write-Host "    OK $($r.StatusCode)  $($check.Url)" -ForegroundColor Green
        }
    } catch {
        Write-Warning "FALLO  $($check.Url) - $($_.Exception.Message)"
        $fallos++
    }
}

Write-Host ""
if ($fallos -eq 0) {
    Write-Host "Despliegue completado y verificado. https://$Domain/checkout.html" -ForegroundColor Green
} else {
    Write-Warning "Despliegue terminado con $fallos comprobacion(es) fallida(s). Revisa el detalle de arriba."
    exit 1
}
