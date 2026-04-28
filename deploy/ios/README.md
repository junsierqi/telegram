# iOS build path (Qt for iOS, untested-by-CI)

The Qt Quick `app_mobile` target is wired to package as an iOS `.app`
bundle when CMake `if(IOS)` activates. This file documents the procedure;
**the build has not been verified locally or by CI** because:

- A working iOS toolchain requires Xcode + macOS, neither available in
  this project's main development environment.
- Qt for iOS only ships in the **macOS Qt installer** (it's not in the
  Windows Qt installer, and not in Homebrew's `qt@6`). So the GitHub
  Actions `macos-build` job builds desktop macOS but does **not** attempt
  iOS — that would require either provisioning Qt for iOS in CI (license
  + image space) or hand-building Qt 6 from source on the runner.
- iOS code signing is double-gated: developer cert (PA-005) AND a
  provisioning profile bound to a registered device or App Store
  distribution account.

## What's in the repo

- `deploy/ios/Info.plist.in` — `configure_file()` template with
  `@VARIABLE@` substitutions for CFBundle* fields, MinimumOSVersion 14.0,
  iPhone + iPad UIDeviceFamily, portrait + landscape orientations,
  arm64 UIRequiredDeviceCapabilities, NSAppTransportSecurity allowing
  the local self-signed TLS cert path (production builds must tighten).
- `client/src/CMakeLists.txt` `if(IOS)` block on `app_mobile`:
  - `MACOSX_BUNDLE TRUE` (Qt's qt_add_executable already does this)
  - `MACOSX_BUNDLE_INFO_PLIST` -> `deploy/ios/Info.plist.in`
  - `XCODE_ATTRIBUTE_TARGETED_DEVICE_FAMILY 1,2`
  - `XCODE_ATTRIBUTE_PRODUCT_BUNDLE_IDENTIFIER`
  - `MACOSX_BUNDLE_BUNDLE_NAME`, `MACOSX_BUNDLE_GUI_IDENTIFIER`,
    `MACOSX_BUNDLE_BUNDLE_VERSION`, `MACOSX_BUNDLE_SHORT_VERSION_STRING`

## Procedure on a real macOS host

```bash
# 1. Install Xcode 15+ from the App Store and accept the license.
sudo xcodebuild -license accept

# 2. Install Qt for iOS via the official Qt online installer
#    (Qt 6.7+ recommended). Pick:
#       Qt 6.7.x -> iOS
#    The installer puts everything under e.g. ~/Qt/6.7.0/ios/
QT_IOS=~/Qt/6.7.0/ios
QT_HOST=~/Qt/6.7.0/macos

# 3. Configure with qt-cmake, generating an Xcode project so signing /
#    provisioning works through the standard Xcode flow:
$QT_IOS/bin/qt-cmake \
    -S . -B build-ios -G Xcode \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_SYSTEM_NAME=iOS \
    -DCMAKE_OSX_DEPLOYMENT_TARGET=14.0 \
    -DCMAKE_OSX_ARCHITECTURES=arm64 \
    -DQT_HOST_PATH=$QT_HOST \
    -DTELEGRAM_LIKE_SKIP_WINDEPLOYQT=ON

# 4. Build for a device (replace TEAM_ID with your Apple Developer team):
xcodebuild -project build-ios/telegram_like.xcodeproj \
    -scheme app_mobile -configuration Release \
    -destination 'generic/platform=iOS' \
    -allowProvisioningUpdates \
    DEVELOPMENT_TEAM=TEAM_ID build

# Or for the Simulator (no signing needed):
xcodebuild -project build-ios/telegram_like.xcodeproj \
    -scheme app_mobile -configuration Debug \
    -destination 'generic/platform=iOS Simulator' build
```

## Anticipated portability issues

The following are **expected to compile cleanly** but flagged here so a
future iOS-running developer knows where to look first if a snag turns up:

| Code path | Risk |
|---|---|
| `client/src/net/tcp_line_client.{h,cpp}` Schannel TLS | Already gated behind `#if defined(_WIN32)` (verified by `validate_android_prep.py` scenario). iOS picks the POSIX branch — same path Android already exercises on Bionic libc. |
| `client/src/net/platform.h` POSIX socket headers | `<sys/socket.h>`, `<unistd.h>`, `<arpa/inet.h>` — all present on iOS SDK. |
| Qt Quick / QML rendering | Qt 6 supports iOS for Quick + QuickControls2 since 6.2; the `Main.qml` / `LoginPage.qml` etc. don't use any desktop-only modules (no Window flags / no platform integration plugin). |
| `qt_add_qml_module(... URI TelegramLikeMobile ...)` | Same shape that builds on Win + Android; URIs survive the iOS toolchain. |
| Hand-rolled JSON parser, network code | All stdlib. No Apple-specific headers needed. |

## Pending external dependencies

- **PA-005** — Apple Developer Program membership ($99/year) for code
  signing + provisioning profiles + App Store Connect upload
- **PA-010** (new) — A macOS host (Mac mini / Mac Studio / cloud Mac)
  capable of running Xcode 15+ and Qt for iOS, plus a registered iOS
  device or Simulator runtime
