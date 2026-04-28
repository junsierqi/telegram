param(
    [string]$BuildDir = "build-codex",
    [string]$Config = "Debug",
    [string]$OutDir = "artifacts/windows-desktop",
    [switch]$IncludeDebugSymbols,
    [switch]$SkipQtDeploy,
    [switch]$Zip,
    [switch]$Installer,
    [string]$AppVersion = "0.1.0-dev",
    [string]$AppPublisher = "Telegram-like Project",
    [string]$AppUrl = "https://example.invalid/telegram-like",
    [string]$IsccPath = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

if ([System.IO.Path]::IsPathRooted($BuildDir)) {
    $buildRoot = $BuildDir
} else {
    $buildRoot = Join-Path $repoRoot $BuildDir
}

if ([System.IO.Path]::IsPathRooted($OutDir)) {
    $artifactRoot = $OutDir
} else {
    $artifactRoot = Join-Path $repoRoot $OutDir
}

$binaryDir = Join-Path $buildRoot "client\src\$Config"
if (!(Test-Path $binaryDir)) {
    throw "Build output directory not found: $binaryDir"
}

$requiredExecutables = @(
    "app_desktop.exe",
    "app_chat.exe",
    "telegram_like_client.exe"
)

foreach ($exe in $requiredExecutables) {
    $path = Join-Path $binaryDir $exe
    if (!(Test-Path $path)) {
        throw "Required executable not found: $path"
    }
}

New-Item -ItemType Directory -Force -Path $artifactRoot | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$stageDir = Join-Path $artifactRoot "telegram_like_windows_desktop_$stamp"
New-Item -ItemType Directory -Force -Path $stageDir | Out-Null

foreach ($exe in $requiredExecutables) {
    Copy-Item -Path (Join-Path $binaryDir $exe) -Destination $stageDir
}

if ($IncludeDebugSymbols) {
    Get-ChildItem -Path $binaryDir -Filter "*.pdb" | ForEach-Object {
        Copy-Item -Path $_.FullName -Destination $stageDir
    }
}

if (!$SkipQtDeploy) {
    $qtDeploy = Get-Command "windeployqt" -ErrorAction SilentlyContinue
    if ($null -ne $qtDeploy) {
        & $qtDeploy.Source (Join-Path $stageDir "app_desktop.exe")
        if ($LASTEXITCODE -ne 0) {
            throw "windeployqt failed with exit code $LASTEXITCODE"
        }
    } else {
        Write-Warning "windeployqt was not found on PATH; Qt runtime DLLs were not staged."
    }
}

$packageReadme = @"
telegram_like Windows desktop package

Start the Python server first:
  python -m server.main --tcp-server

Then run:
  app_desktop.exe

Developer utilities included:
  app_chat.exe
  telegram_like_client.exe
"@
$packageReadme | Set-Content -Encoding UTF8 -Path (Join-Path $stageDir "README_PACKAGE.txt")

$manifest = [ordered]@{
    package = "telegram_like_windows_desktop"
    created_at = (Get-Date).ToString("o")
    build_dir = (Resolve-Path $binaryDir).Path
    config = $Config
    include_debug_symbols = [bool]$IncludeDebugSymbols
    qt_deploy_attempted = -not [bool]$SkipQtDeploy
    executables = $requiredExecutables
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 -Path (Join-Path $stageDir "manifest.json")

$hashLines = Get-ChildItem -Path $stageDir -File -Recurse |
    Where-Object { $_.Name -ne "SHA256SUMS.txt" } |
    Sort-Object FullName |
    ForEach-Object {
        $relative = $_.FullName.Substring($stageDir.Length).TrimStart("\", "/").Replace("\", "/")
        $hash = Get-FileHash -Algorithm SHA256 -Path $_.FullName
        "$($hash.Hash.ToLowerInvariant())  $relative"
    }
$hashLines | Set-Content -Encoding ASCII -Path (Join-Path $stageDir "SHA256SUMS.txt")

if ($Zip) {
    $zipPath = "$stageDir.zip"
    Compress-Archive -Path (Join-Path $stageDir "*") -DestinationPath $zipPath -Force
    $zipHash = Get-FileHash -Algorithm SHA256 -Path $zipPath
    "$($zipHash.Hash.ToLowerInvariant())  $([System.IO.Path]::GetFileName($zipPath))" |
        Set-Content -Encoding ASCII -Path "$zipPath.sha256"
    Write-Host "Created package zip: $zipPath"
    Write-Host "Created package zip checksum: $zipPath.sha256"
}

if ($Installer) {
    if (!(Test-Path $IsccPath)) {
        throw "Inno Setup compiler not found at: $IsccPath. Install Inno Setup 6 or pass -IsccPath."
    }

    $templatePath = Join-Path $repoRoot "deploy\windows\telegram_like_desktop.iss.template"
    if (!(Test-Path $templatePath)) {
        throw "Inno Setup template missing: $templatePath"
    }

    $installerOutputDir = Join-Path $artifactRoot "installers"
    New-Item -ItemType Directory -Force -Path $installerOutputDir | Out-Null
    $outputBaseName = "telegram_like_desktop_setup_$stamp"

    $iss = (Get-Content -Raw -Path $templatePath).
        Replace("{APP_VERSION}",      $AppVersion).
        Replace("{APP_PUBLISHER}",    $AppPublisher).
        Replace("{APP_URL}",          $AppUrl).
        Replace("{SOURCE_STAGE_DIR}", $stageDir).
        Replace("{OUTPUT_DIR}",       $installerOutputDir).
        Replace("{OUTPUT_BASE_NAME}", $outputBaseName)

    $issTempPath = Join-Path $stageDir "telegram_like_desktop.generated.iss"
    Set-Content -Encoding UTF8 -Path $issTempPath -Value $iss

    & $IsccPath $issTempPath
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup compiler exited with $LASTEXITCODE"
    }
    $installerPath = Join-Path $installerOutputDir "$outputBaseName.exe"
    if (!(Test-Path $installerPath)) {
        throw "Installer was not produced at expected path: $installerPath"
    }
    $installerHash = Get-FileHash -Algorithm SHA256 -Path $installerPath
    "$($installerHash.Hash.ToLowerInvariant())  $([System.IO.Path]::GetFileName($installerPath))" |
        Set-Content -Encoding ASCII -Path "$installerPath.sha256"
    Write-Host "Created installer: $installerPath"
    Write-Host "Created installer checksum: $installerPath.sha256"
    Write-Host "Code signing not applied — supply Authenticode cert via signtool then re-run with the SignTool directive uncommented in the .iss template."
}

Write-Host "Created package directory: $stageDir"
