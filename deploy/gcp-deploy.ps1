# Despliegue con cuenta de servicio GCP
# Coloca el JSON de la cuenta de servicio en: deploy/gcp-service-account.json
# O define: $env:GOOGLE_APPLICATION_CREDENTIALS = "ruta\al\archivo.json"

param(
    [string]$ServiceAccountJson = "$PSScriptRoot\gcp-service-account.json",
    [string]$ProjectId = "",
    [string]$Zone = "us-east1-b",
    [string]$Instance = "jaragoexpresselite",
    [string]$ServerIp = "34.24.248.250"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Gcloud = @(
    "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
    "C:\Program Files\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $Gcloud) { throw "Instala Google Cloud SDK primero." }
if (-not (Test-Path $ServiceAccountJson)) { throw "No se encontró $ServiceAccountJson" }

$env:GOOGLE_APPLICATION_CREDENTIALS = $ServiceAccountJson
& $Gcloud auth activate-service-account --key-file=$ServiceAccountJson | Out-Null
if ($ProjectId) { & $Gcloud config set project $ProjectId | Out-Null }

Write-Host "==> Subiendo sitio a la VM..."
& $Gcloud compute scp --recurse "$ProjectRoot\index.html" "$ProjectRoot\style.css" "$ProjectRoot\intro.js" "$ProjectRoot\logo-render.js" "$ProjectRoot\nav.js" "$ProjectRoot\robots.txt" "$ProjectRoot\sitemap.xml" "${Instance}:/tmp/cazador-upload/" --zone=$Zone
& $Gcloud compute scp --recurse "$ProjectRoot\img" "$ProjectRoot\images" "$ProjectRoot\vitolas" "$ProjectRoot\deploy" "${Instance}:/tmp/cazador-upload/" --zone=$Zone

Write-Host "==> Instalando en servidor..."
$cmd = @'
sudo mkdir -p /var/www/cazador-de-suenos-cigars
sudo cp -r /tmp/cazador-upload/* /var/www/cazador-de-suenos-cigars/
sudo chown -R $USER:$USER /var/www/cazador-de-suenos-cigars
bash /var/www/cazador-de-suenos-cigars/deploy/remote-install.sh
'@ -join "`n"
& $Gcloud compute ssh $Instance --zone=$Zone --command=$cmd

Write-Host "==> Verificando..."
@("http://$ServerIp/", "http://cazadordesuenocigars.com/", "http://cazadordesuenocigars.com/vitolas/el-emperador.html") | ForEach-Object {
    try { $r = Invoke-WebRequest $_ -UseBasicParsing -TimeoutSec 20; Write-Host "OK $($r.StatusCode) $_" } catch { Write-Warning "FAIL $_" }
}
