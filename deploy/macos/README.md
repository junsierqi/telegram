# macOS desktop build path

The Qt Widgets `app_desktop` and Qt Quick `app_mobile` binaries are wired
to package as macOS `.app` bundles. CMake `if(APPLE AND NOT IOS)` blocks
in `client/src/CMakeLists.txt` set the bundle properties + point at
`deploy/macos/Info.plist.in` for the plist template.

> **Heads-up — not yet built locally.** This project's main development
> environment is Windows + WSL Linux; no macOS host is currently available
> to author and verify the build at the time these files landed. The
> CMake config is **structured to compile on macOS as soon as a CI runner
> or developer machine picks it up** (see `.github/workflows/ci.yml`
> `macos-build` job). Treat this README as a developer hand-off, not a
> walkthrough that's been verified end-to-end.

## What CI verifies automatically

`.github/workflows/ci.yml` includes a `macos-build` job that runs on
`macos-latest`, installs Qt 6 via Homebrew, configures CMake with
`-DCMAKE_PREFIX_PATH=$(brew --prefix qt@6)`, and builds:

  * `chat_client_core` (Qt-free portable library — same source the
    Windows / Linux / Android builds compile)
  * `app_chat`, `telegram_like_client`, `app_desktop_store_test`,
    `json_parser_test`, `remote_session_smoke` (also Qt-free)
  * `app_desktop` (Qt Widgets) — packaged as `app_desktop.app`
  * `app_mobile` (Qt Quick) — packaged as `app_mobile.app`

Then runs the same `_sweep_validators.py` + the two C++ test binaries.

## One-shot manual build

```bash
brew install qt@6 cmake ninja
export PATH="$(brew --prefix qt@6)/bin:$PATH"
cmake -S . -B build-macos -GNinja -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_PREFIX_PATH="$(brew --prefix qt@6)"
cmake --build build-macos --target \
    chat_client_core app_desktop app_mobile \
    app_chat telegram_like_client \
    app_desktop_store_test json_parser_test remote_session_smoke

# .app bundles are at:
ls build-macos/client/src/app_desktop.app
ls build-macos/client/src/app_mobile.app

# Run the C++ tests:
./build-macos/client/src/json_parser_test
./build-macos/client/src/app_desktop_store_test
```

## Bundle properties controlled by CMake

The `if(APPLE AND NOT IOS)` block sets, on each Apple-bundled target:

| Property | Value |
|---|---|
| `MACOSX_BUNDLE` | `TRUE` (Qt's qt_add_executable already enables this) |
| `MACOSX_BUNDLE_BUNDLE_NAME` | "Telegram-like" / "Telegram-like Mobile" |
| `MACOSX_BUNDLE_GUI_IDENTIFIER` | `com.example.telegramlike.<target>` |
| `MACOSX_BUNDLE_BUNDLE_VERSION` | `0.1.0-dev` |
| `MACOSX_BUNDLE_SHORT_VERSION_STRING` | `0.1.0` |
| `MACOSX_BUNDLE_COPYRIGHT` | `Telegram-like Project` |
| `MACOSX_BUNDLE_INFO_PLIST` | path to `deploy/macos/Info.plist.in` |

`Info.plist.in` is a `configure_file()`-style template; CMake substitutes
the `@VARIABLE@` tokens at configure time. `NSAllowsArbitraryLoads` is
true so the dev self-signed TLS cert path works; production builds must
toggle that off and ship ATS-compliant pinned roots.

## Pending

- ~~**Qt framework embedding via `macdeployqt`**~~ — wired POST_BUILD in
  `client/src/CMakeLists.txt` as of M113 (2026-04-29). On macOS, when
  `macdeployqt` is on PATH the build automatically embeds Qt frameworks
  and (for `app_mobile`) the QML modules into the `.app` bundle. Disable
  with `-DTELEGRAM_LIKE_SKIP_MACDEPLOYQT=ON` for CI builds where Qt is
  guaranteed to stay on PATH and you want to keep build-link parity.
- Code signing (`-DCMAKE_XCODE_ATTRIBUTE_CODE_SIGN_IDENTITY=...`) — gated on
  PA-005 (developer cert procurement).
- `.dmg` packaging — `macdeployqt -dmg` produces it once Qt is embedded.
- Notarization via `xcrun notarytool` — requires an Apple Developer
  account, also PA-005.
- Universal binary (`-DCMAKE_OSX_ARCHITECTURES="arm64;x86_64"`) — currently
  the CI runner builds for whichever arch it happens to be on (macos-latest
  is now Apple Silicon, so the bundle is arm64-only).
