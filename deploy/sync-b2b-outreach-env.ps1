# Sube server/b2b-outreach/.env local a /etc/cazador-de-suenos/b2b-outreach.env en la VM.
# No imprime secretos. Requiere: ssh USUARIO@34.24.248.250 funciona (ver deploy/GCP-SSH-SETUP.md).

param(
    [string]$Server = "34.24.248.250",
    [string]$User = "",
    [string]$SiteRoot = "/var/www/html",
    [string]$LocalEnv = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $LocalEnv) {
    $LocalEnv = Join-Path $RepoRoot "server\b2b-outreach\.env"
}
if (-not (Test-Path $LocalEnv)) {
    throw "No existe $LocalEnv"
}
if (-not $User) {
    $User = $env:B2B_SSH_USER
}
if (-not $User) {
    throw "Indica -User TU_USUARIO (whoami en la VM) o `$env:B2B_SSH_USER"
}

$tokenLine = Select-String -Path $LocalEnv -Pattern '^\s*TELEGRAM_BOT_TOKEN=' | Select-Object -First 1
if (-not $tokenLine -or $tokenLine.Line -notmatch ':\S+') {
    throw "TELEGRAM_BOT_TOKEN inválido en .env local"
}

$tmp = Join-Path $env:TEMP ("b2b-outreach-env-{0}.tmp" -f [guid]::NewGuid().ToString("n"))
Copy-Item -LiteralPath $LocalEnv -Destination $tmp -Force
try {
    $remote = "${User}@${Server}"
    & scp $tmp "${remote}:/tmp/b2b-outreach.env.merge"
    if ($LASTEXITCODE -ne 0) { throw "scp falló (exit $LASTEXITCODE). Configura SSH: deploy/GCP-SSH-SETUP.md" }
    $install = "$SiteRoot/deploy/install-cds-b2b-outreach.sh"
    $cmd = @(
        "sudo bash $install --merge-secrets /tmp/b2b-outreach.env.merge",
        "rm -f /tmp/b2b-outreach.env.merge",
        "sudo systemctl restart cds-b2b-outreach.service",
        "sudo systemctl start cds-b2b-buscar.service",
        "journalctl -u cds-b2b-buscar.service -n 20 --no-pager 2>/dev/null | grep -viE 'TELEGRAM_BOT_TOKEN|:[A-Za-z0-9_-]{20,}' || true"
    ) -join " && "
    & ssh $remote $cmd
    if ($LASTEXITCODE -ne 0) { throw "ssh falló (exit $LASTEXITCODE)" }
    Write-Host "OK: env restaurado, servicios reiniciados. Revisa Telegram y journalctl."
}
finally {
    Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
}
