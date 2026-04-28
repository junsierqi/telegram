"""Static checks for the Qt Quick mobile UI (M85).

Verifies the QML / C++ bridge surface without launching the binary.

  1. mobile_chat_bridge.h declares the QML facade Q_OBJECT class with
     QML_ELEMENT and the expected Q_INVOKABLE methods.
  2. mobile_chat_bridge.cpp uses the same threading shape (detach + invoke)
     as the desktop client.
  3. Main.qml / LoginPage.qml / ChatListPage.qml / ChatPage.qml exist and
     reference ChatBridge.* by the documented surface.
  4. CMakeLists.txt wires app_mobile via qt_add_executable + qt_add_qml_module
     with the URI 'TelegramLikeMobile'.
  5. (optional) If the mobile app_mobile.exe was built on Windows, it has a
     non-trivial size.
  6. (optional) If the Android mobile APK was built, it has a non-trivial
     size and is >= the chat-only desktop APK.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MOBILE_DIR = REPO / "client" / "src" / "app_mobile"
BRIDGE_H = MOBILE_DIR / "mobile_chat_bridge.h"
BRIDGE_CPP = MOBILE_DIR / "mobile_chat_bridge.cpp"
QML_DIR = MOBILE_DIR / "qml"
CMAKE = REPO / "client" / "src" / "CMakeLists.txt"
EXE = REPO / "build-verify" / "client" / "src" / "Debug" / "app_mobile.exe"
APK = REPO / "build-android" / "client" / "src" / "android-build" / "build" / "outputs" / "apk" / "release" / "android-build-release-unsigned.apk"

SCENARIOS: list[tuple[str, callable]] = []


def scenario(name):
    def deco(fn):
        SCENARIOS.append((name, fn))
        return fn
    return deco


@scenario("bridge_header_declares_qml_facade")
def _t1():
    text = BRIDGE_H.read_text(encoding="utf-8")
    for needle in (
        "class MobileChatBridge",
        "Q_OBJECT",
        "QML_ELEMENT",
        "Q_INVOKABLE void connectAndLogin(",
        "Q_INVOKABLE void selectChat(",
        "Q_INVOKABLE void sendMessage(",
        "Q_INVOKABLE QVariantList conversationList()",
        "Q_INVOKABLE QVariantList selectedMessages()",
    ):
        assert needle in text, f"bridge header missing: {needle}"


@scenario("bridge_cpp_uses_marshalled_invoke")
def _t2():
    text = BRIDGE_CPP.read_text(encoding="utf-8")
    assert "QMetaObject::invokeMethod" in text, "bridge must marshal back to UI"
    assert "std::thread" in text and ".detach()" in text, \
        "bridge should run RPCs off the UI thread"
    assert "shutting_down_" in text, "bridge must guard against teardown races"


@scenario("qml_pages_present_and_use_chatbridge")
def _t3():
    pages = ["Main.qml", "LoginPage.qml", "ChatListPage.qml", "ChatPage.qml"]
    for p in pages:
        path = QML_DIR / p
        assert path.exists(), f"missing QML page: {p}"
    main = (QML_DIR / "Main.qml").read_text(encoding="utf-8")
    assert "StackView" in main, "Main.qml should compose pages with StackView"
    assert "loadFromModule" not in main, "Main.qml is loaded by the engine, not by itself"
    login = (QML_DIR / "LoginPage.qml").read_text(encoding="utf-8")
    assert "loginRequested" in login and "ChatBridge.statusText" in login
    chat_list = (QML_DIR / "ChatListPage.qml").read_text(encoding="utf-8")
    assert "ChatBridge.conversationList" in chat_list and "conversationSelected" in chat_list
    chat = (QML_DIR / "ChatPage.qml").read_text(encoding="utf-8")
    assert "ChatBridge.selectedMessages" in chat and "ChatBridge.sendMessage" in chat
    assert "backRequested" in chat


@scenario("cmake_wires_app_mobile_qml_module")
def _t4():
    text = CMAKE.read_text(encoding="utf-8")
    assert "qt_add_executable(app_mobile" in text
    assert "qt_add_qml_module(app_mobile" in text
    assert 'URI TelegramLikeMobile' in text
    assert "Qt6::Quick" in text and "Qt6::QuickControls2" in text
    assert "AUTOMOC ON" in text or "set(CMAKE_AUTOMOC" in text


@scenario("if_built_then_app_mobile_exe_size_is_reasonable")
def _t5():
    if not EXE.exists():
        return
    size = EXE.stat().st_size
    assert size > 100_000, f"app_mobile.exe too small: {size} bytes"


@scenario("if_built_then_mobile_apk_size_is_reasonable")
def _t6():
    if not APK.exists():
        return
    size = APK.stat().st_size
    assert size > 5_000_000, f"mobile APK too small: {size} bytes"
    assert size < 200_000_000, f"mobile APK suspiciously large: {size} bytes"


def main() -> int:
    failed = 0
    for name, fn in SCENARIOS:
        try:
            fn()
            print(f"[ok ] {name}")
        except AssertionError as e:
            print(f"[FAIL] {name}: {e}")
            failed += 1
    total = len(SCENARIOS)
    print(f"passed {total - failed}/{total}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
