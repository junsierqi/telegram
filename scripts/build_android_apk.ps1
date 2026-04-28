# Build the Android APK for app_desktop using Qt for Android.
#
# Wrapper around the qt-cmake / cmake --target apk dance, with all the
# environment plumbing (JDK, SDK, NDK, Ninja, gradle proxy) folded in.
# The actual mechanics live in client/src/CMakeLists.txt's qt_add_executable
# block + deploy/android/AndroidManifest.xml.
#
# Output: D:/office-ai/telegram/build-android/client/src/android-build/
#         build/outputs/apk/release/android-build-release-unsigned.apk
#
# Notes:
# - First run will pull the Gradle distribution + Android dependencies via
#   the proxy in $env:USERPROFILE\.gradle\gradle.properties.
# - APK is unsigned. Signing is gated on PA-005 (same Authenticode-style
#   action as the Windows installer signing path; for Android the cert is
#   a separate keystore but the procurement decision is the same).
param(
    [string]$BuildDir   = "build-android",
    [string]$AndroidAbi = "arm64-v8a",
    [string]$ApiPlatform = "android-26",
    [string]$JavaHome   = "C:\Program Files\Java\jdk-21.0.11",
    [string]$AndroidHome = "D:\android\sdk",
    [string]$AndroidNdk = "D:\android\sdk\ndk\30.0.14904198",
    [string]$QtAndroidPrefix = "C:\Qt\6.11.0\android_arm64_v8a",
    [string]$QtHostPrefix    = "C:\Qt\6.11.0\msvc2022_64",
    [switch]$Reconfigure
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$buildPath = if ([System.IO.Path]::IsPathRooted($BuildDir)) { $BuildDir } else { Join-Path $repoRoot $BuildDir }

# Toolchain env
$env:JAVA_HOME         = $JavaHome
$env:ANDROID_HOME      = $AndroidHome
$env:ANDROID_SDK_ROOT  = $AndroidHome
$env:ANDROID_NDK_ROOT  = $AndroidNdk
$env:ANDROID_NDK_HOME  = $AndroidNdk
$env:Path = "$JavaHome\bin;C:\Qt\Tools\Ninja;C:\Qt\Tools\CMake_64\bin;$env:Path"

# The android-37.0 platform dir (non-standard naming) needs a junction so
# androiddeployqt finds 'android-37'. Created idempotently.
$plat = Join-Path $AndroidHome "platforms\android-37"
$plat0 = Join-Path $AndroidHome "platforms\android-37.0"
if ((Test-Path $plat0) -and -not (Test-Path $plat)) {
    cmd /c mklink /J "$plat" "$plat0" | Out-Null
    Write-Host "Created platforms\android-37 junction"
}

# Gradle proxy stub (corporate egress). User's existing ~/.gradle/gradle.properties
# wins if it already has proxy settings, so we only seed when absent.
$gradleProps = Join-Path $env:USERPROFILE ".gradle\gradle.properties"
if (-not (Test-Path $gradleProps)) {
    Write-Host "No gradle.properties found — leaving alone (set systemProp.https.proxyHost/Port if your network needs egress proxy)."
}

if ($Reconfigure -and (Test-Path $buildPath)) {
    Write-Host "Wiping $buildPath for clean reconfigure"
    Remove-Item -Recurse -Force $buildPath
}

if (-not (Test-Path (Join-Path $buildPath "CMakeCache.txt"))) {
    Write-Host "Configuring with qt-cmake (target $AndroidAbi, platform $ApiPlatform)..."
    & "$QtAndroidPrefix\bin\qt-cmake.bat" `
        -S "$repoRoot" -B "$buildPath" `
        -GNinja -DCMAKE_BUILD_TYPE=Release `
        "-DCMAKE_ANDROID_ARCH_ABI=$AndroidAbi" `
        "-DANDROID_ABI=$AndroidAbi" `
        "-DANDROID_PLATFORM=$ApiPlatform" `
        "-DANDROID_NDK=$AndroidNdk" `
        "-DCMAKE_ANDROID_NDK=$AndroidNdk" `
        "-DQT_HOST_PATH=$QtHostPrefix" `
        -DTELEGRAM_LIKE_SKIP_WINDEPLOYQT=ON
    if ($LASTEXITCODE -ne 0) { throw "qt-cmake configure failed ($LASTEXITCODE)" }
}

# Always wipe android-build/ so androiddeployqt regenerates a fresh manifest+gradle tree.
$androidBuild = Join-Path $buildPath "client\src\android-build"
if (Test-Path $androidBuild) { Remove-Item -Recurse -Force $androidBuild }

Write-Host "Building APK target..."
& "C:\Qt\Tools\CMake_64\bin\cmake.exe" --build "$buildPath" --target apk
if ($LASTEXITCODE -ne 0) { throw "APK build failed ($LASTEXITCODE)" }

$apk = Join-Path $buildPath "client\src\android-build\build\outputs\apk\release\android-build-release-unsigned.apk"
if (-not (Test-Path $apk)) { throw "APK not produced at $apk" }

$size = (Get-Item $apk).Length
$hash = Get-FileHash -Algorithm SHA256 -Path $apk
Write-Host ""
Write-Host "APK: $apk"
Write-Host "Size: $size bytes"
Write-Host "SHA256: $($hash.Hash.ToLowerInvariant())"
