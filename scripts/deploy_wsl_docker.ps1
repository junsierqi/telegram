param(
    [ValidateSet("sqlite", "postgres")]
    [string]$Mode = "sqlite",
    [switch]$NoBuild,
    [switch]$NoSmoke
)

$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$wslRepo = "/mnt/" + $repo.Substring(0, 1).ToLower() + $repo.Substring(2).Replace("\", "/")
$compose = "deploy/docker/docker-compose.yml"

function Quote-Bash([string]$value) {
    return "'" + $value.Replace("'", "'\''") + "'"
}

function Invoke-Wsl([string]$command) {
    $proxyPrefix = @()
    foreach ($name in "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy") {
        $value = [Environment]::GetEnvironmentVariable($name)
        if ($value) {
            $proxyPrefix += "$name=$(Quote-Bash $value)"
        }
    }
    $prefix = ($proxyPrefix -join " ")
    if ($prefix) {
        $command = "$prefix $command"
    }
    wsl bash -lc $command
    if ($LASTEXITCODE -ne 0) {
        throw "WSL command failed with exit code $LASTEXITCODE"
    }
}

$profileArg = ""
if ($Mode -eq "postgres") {
    $profileArg = "--profile postgres"
}

if (-not $NoBuild) {
    Invoke-Wsl "cd '$wslRepo' && docker compose -f '$compose' $profileArg build telegram-server"
}

$services = "telegram-server"
if ($Mode -eq "postgres") {
    $services = "postgres telegram-server-postgres"
}

Invoke-Wsl "cd '$wslRepo' && docker compose -f '$compose' $profileArg up -d $services"

if (-not $NoSmoke) {
    python (Join-Path $PSScriptRoot "validate_docker_deploy.py")
}

Write-Host "Docker deployment is running. Stop it with:"
Write-Host "  wsl bash -lc `"cd '$wslRepo' && docker compose -f '$compose' $profileArg down`""
