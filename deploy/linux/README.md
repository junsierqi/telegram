# Linux desktop build path

The Qt Widgets `app_desktop` and Qt Quick `app_mobile` binaries build clean
on Ubuntu 24.04 (Qt 6.4 from apt) using the same CMakeLists.txt that drives
the Windows MSVC and Android NDK builds. Linked tested against:

- Ubuntu 24.04 LTS (WSL2 + native)
- GCC 13.2
- Qt 6.4.2 (system)
- CMake 3.28+, Ninja 1.11+

The CI workflow (`linux-cpp` job) covers the no-Qt portable targets on
every push; a `linux-desktop` job builds `app_desktop` + `app_mobile` once
Qt 6 is provisioned.

## One-shot install + build

```bash
sudo apt-get install -y \
    build-essential cmake ninja-build \
    qt6-base-dev qt6-tools-dev libgl1-mesa-dev \
    qt6-declarative-dev \
    qml6-module-qtquick qml6-module-qtquick-controls \
    qml6-module-qtquick-window qml6-module-qtquick-layouts

cmake -S . -B build-linux -GNinja -DCMAKE_BUILD_TYPE=Release
cmake --build build-linux --target app_desktop app_mobile \
    chat_client_core json_parser_test app_desktop_store_test \
    app_chat telegram_like_client remote_session_smoke

./build-linux/client/src/json_parser_test
./build-linux/client/src/app_desktop_store_test
```

## Output binaries

| Target | Path | Notes |
|---|---|---|
| `app_desktop` | `build-linux/client/src/app_desktop` | Qt Widgets shell — same source as Windows |
| `app_mobile` | `build-linux/client/src/app_mobile` | Qt Quick shell, also runs as desktop preview |
| `app_chat` | `build-linux/client/src/app_chat` | Console CLI (no Qt) |
| `telegram_like_client` | `build-linux/client/src/telegram_like_client` | Legacy demo |
| `app_desktop_store_test` | … | C++ store regression suite (20/20) |
| `json_parser_test` | … | C++ JSON parser tests (9/9) |
| `remote_session_smoke` | … | Negative-path round-trip for remote-control RPCs |

## Source-version notes

Two compatibility points between Qt 6.4 (apt) and Qt 6.5+ (Qt installer):

- `qt_policy(SET QTP0001 NEW)` is gated behind `if(COMMAND qt_policy)` in
  `client/src/CMakeLists.txt` — Qt 6.4 simply uses the default `:/qt/qml/`
  resource prefix, which is what we want anyway.
- `QQmlApplicationEngine::loadFromModule` is Qt 6.5+. The `app_mobile`
  entrypoint falls back to `engine.load(QUrl("qrc:/qt/qml/TelegramLikeMobile/Main.qml"))`
  when built against older Qt.

## .desktop file

`telegram-like.desktop` ships an XDG-compliant launcher entry. A future
distribution-package milestone would install it under `/usr/share/applications/`
together with an icon at `/usr/share/icons/hicolor/256x256/apps/telegram-like.png`.

## Pending

- Build a `.deb` / `.rpm` / AppImage (currently no package format wired —
  CI just produces the raw binaries)
- Validate on Fedora / Arch / Alpine (only Ubuntu 24.04 verified so far)
- Wire `windeployqt` analogue (`linuxdeployqt` or `linuxdeploy`) so the
  binary tree is portable, not tied to system Qt
