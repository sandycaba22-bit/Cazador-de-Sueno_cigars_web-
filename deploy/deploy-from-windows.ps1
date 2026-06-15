# Despliegue Cazador de Sueños Cigars — Windows PowerShell
# Uso: .\deploy\deploy-from-windows.ps1 -SshUser TU_USUARIO -ServerIp 35.237.216.105

param(
    [Parameter(Mandatory = $true)]
    [string]$SshUser,

    [string]$ServerIp = "35.237.216.105",

    [string]$RemotePath = "/var/www/cazador-de-suenos-cigars"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Remote = "${SshUser}@${ServerIp}"

Write-Host "==> Verificando conexión SSH a $Remote ..."
ssh -o BatchMode=yes -o ConnectTimeout=15 $Remote "echo SSH OK && whoami"

Write-Host "==> Creando directorio remoto..."
ssh $Remote "sudo mkdir -p $RemotePath && sudo chown -R `$USER:`$USER $RemotePath"

Write-Host "==> Subiendo archivos del sitio..."
$items = @(
    "index.html", "style.css", "intro.js", "logo-render.js", "nav.js",
    "robots.txt", "sitemap.xml", "img", "images", "vitolas"
)
foreach ($item in $items) {
    $local = Join-Path $ProjectRoot $item
    if (-not (Test-Path $local)) {
        Write-Warning "No encontrado: $item"
        continue
    }
    scp -r $local "${Remote}:${RemotePath}/"
}

Write-Host "==> Subiendo scripts de deploy..."
scp -r (Join-Path $ProjectRoot "deploy") "${Remote}:${RemotePath}/"

Write-Host "==> Ejecutando setup en servidor..."
ssh $Remote "chmod +x $RemotePath/deploy/setup-server.sh && bash $RemotePath/deploy/setup-server.sh"

Write-Host "==> Validando respuestas HTTP..."
$urls = @(
    "http://${ServerIp}/",
    "http://${ServerIp}/vitolas/el-emperador.html",
    "http://${ServerIp}/vitolas/el-sultan.html",
    "http://${ServerIp}/vitolas/ligero-007.html"
)
foreach ($url in $urls) {
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 15
        Write-Host "OK $($r.StatusCode) $url"
    } catch {
        Write-Warning "FAIL $url — $($_.Exception.Message)"
    }
}

Write-Host ""
Write-Host "Despliegue completado."
Write-Host "Acceso por IP: http://${ServerIp}/"
Write-Host "Dominio (tras DNS + certbot): https://www.cazadordesuenocigars.com/"
