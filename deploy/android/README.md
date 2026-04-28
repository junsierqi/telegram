# Android build path (Qt for Android)

This is the prep work for the future Android client. The actual APK build
requires a working Android toolchain that is **not yet installed in this
environment**. See *Pending Action* at the bottom — the toolchain step is
gated on a user decision.

## What ships in this repo right now

- `deploy/android/AndroidManifest.xml` — minimal Qt for Android manifest with
  network permissions and a placeholder app label.
- `client/src/net/` — already structured with `#if defined(_WIN32) / #else`
  split for Winsock vs POSIX sockets. The POSIX branch references
  `<sys/socket.h>` / `<unistd.h>` / `<arpa/inet.h>` and is byte-identical to
  the Linux/macOS path. Android NDK provides Bionic libc which exposes the
  same headers, so the existing code should compile unchanged on Android.
- `chat_client_core` static library is the portable target. `app_chat`
  (interactive CLI) is the realistic first Android binary candidate; the Qt
  Widgets `app_desktop` would also work but a phone UI is a separate redesign
  task.

## What's missing in this environment

```
ANDROID_HOME        d:\android\sdk\        <- path doesn't exist
NDK                 not installed
JDK                 only JDK 1.8 (Qt for Android needs >= 17)
Gradle wrapper      not provisioned
```

So the realistic next step is **install the toolchain** (or unblock the
existing path), not patch the source tree further.

## To produce an APK once the toolchain is in place

```pwsh
# 1. Install Android Studio (or the cmdline-tools-only bundle).
#    Within the SDK Manager install:
#      - Android SDK Platform-Tools
#      - Android SDK Build-Tools 34.0.0+
#      - Android SDK Platform 33+
#      - NDK (Side by side) 26.x
# 2. Install JDK 17 (e.g. Temurin) and set JAVA_HOME.
# 3. Set environment:
$env:ANDROID_HOME = "C:\Android\Sdk"
$env:ANDROID_NDK_ROOT = "$env:ANDROID_HOME\ndk\26.3.11579264"
$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-17.0.13.11-hotspot"

# 4. Configure with Qt for Android (arm64 device):
$qt = "C:\Qt\6.11.0\android_arm64_v8a"
& "$qt\bin\qt-cmake.bat" `
    -S . -B build-android `
    -DANDROID_PLATFORM=android-26 `
    -DCMAKE_ANDROID_ARCH_ABI=arm64-v8a `
    -DQT_HOST_PATH="C:\Qt\6.11.0\msvc2022_64" `
    -DQT_ANDROID_ABIS=arm64-v8a `
    -DTELEGRAM_LIKE_SKIP_WINDEPLOYQT=ON

# 5. Build APK:
cmake --build build-android --target app_chat
cmake --build build-android --target apk
```

## Status

The pure-C++ portion (`chat_client_core` + `app_chat` CLI) is expected to
compile cleanly on Bionic libc once the toolchain is wired. The Qt Widgets
desktop UI (`app_desktop`) will compile but the layout is desktop-shaped;
proper Android UX is a separate milestone (probably Qt Quick + a touch-first
chat layout).

Pending action **PA-007**: install Android SDK + NDK + JDK 17, then run the
sequence above to produce a real APK and verify on an emulator/device.
