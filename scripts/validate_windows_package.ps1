param(
    [string]$BuildDir = "build-codex",
    [string]$OutDir = "artifacts/package-validation"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
if ([System.IO.Path]::IsPathRooted($OutDir)) {
    $artifactRoot = $OutDir
} else {
    $artifactRoot = Join-Path $repoRoot $OutDir
}

New-Item -ItemType Directory -Force -Path $artifactRoot | Out-Null

$packageScript = Join-Path $PSScriptRoot "package_windows_desktop.ps1"
& $packageScript `
    -BuildDir $BuildDir `
    -OutDir $artifactRoot `
    -SkipQtDeploy `
    -Zip

$latest = Get-ChildItem -Path $artifactRoot -Directory |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1
if ($null -eq $latest) {
    throw "No package directory was produced under $artifactRoot"
}

$required = @(
    "app_desktop.exe",
    "app_chat.exe",
    "telegram_like_client.exe",
    "README_PACKAGE.txt",
    "manifest.json",
    "SHA256SUMS.txt"
)

foreach ($name in $required) {
    $path = Join-Path $latest.FullName $name
    if (!(Test-Path $path)) {
        throw "Expected package file is missing: $path"
    }
}

$manifest = Get-Content (Join-Path $latest.FullName "manifest.json") -Raw | ConvertFrom-Json
if ($manifest.package -ne "telegram_like_windows_desktop") {
    throw "Unexpected package manifest name: $($manifest.package)"
}

$hashFile = Join-Path $latest.FullName "SHA256SUMS.txt"
$hashes = Get-Content $hashFile
foreach ($name in @("app_desktop.exe", "app_chat.exe", "telegram_like_client.exe", "manifest.json")) {
    if (!($hashes | Where-Object { $_ -match "  $([regex]::Escape($name))$" })) {
        throw "Missing SHA256 entry for $name"
    }
}

$zipPath = "$($latest.FullName).zip"
$zipHashPath = "$zipPath.sha256"
if (!(Test-Path $zipPath)) {
    throw "Expected package zip is missing: $zipPath"
}
if (!(Test-Path $zipHashPath)) {
    throw "Expected package zip checksum is missing: $zipHashPath"
}

Write-Host "[ok ] windows_package_artifacts"
Write-Host "package_dir=$($latest.FullName)"
Write-Host "package_zip=$zipPath"
