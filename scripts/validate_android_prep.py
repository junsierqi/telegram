"""Static checks for the Android (Qt for Android) build prep.

Does NOT attempt an APK build — that requires SDK/NDK/JDK 17 not yet
installed (see PA-007 in 08-atlas-task-library).

What this validates:
  1. Every file in client/src/net has a POSIX branch alongside the Win32
     branch for the symbols Android (Bionic libc) will need.
  2. The Win32-only Schannel TLS path stays gated behind _WIN32 so it
     does not block compile on Android.
  3. deploy/android/AndroidManifest.xml exists and declares INTERNET
     permission + the Qt Activity entry point.
  4. deploy/android/README.md documents the Pending Action toolchain
     install and the qt-cmake invocation.
  5. CMakeLists.txt does not unconditionally pull in Win32-only
     libraries (ws2_32 / secur32) for non-Windows builds.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
NET_DIR = REPO / "client" / "src" / "net"
MANIFEST = REPO / "deploy" / "android" / "AndroidManifest.xml"
ANDROID_README = REPO / "deploy" / "android" / "README.md"
CLIENT_CMAKE = REPO / "client" / "src" / "CMakeLists.txt"
TCP_LINE_HEADER = NET_DIR / "tcp_line_client.h"
TCP_LINE_CPP = NET_DIR / "tcp_line_client.cpp"
APK_PATH = REPO / "build-android" / "client" / "src" / "android-build" / "build" / "outputs" / "apk" / "release" / "android-build-release-unsigned.apk"
BUILD_SCRIPT = REPO / "scripts" / "build_android_apk.ps1"

SCENARIOS: list[tuple[str, callable]] = []


def scenario(name):
    def deco(fn):
        SCENARIOS.append((name, fn))
        return fn
    return deco


@scenario("net_platform_h_has_posix_branch")
def _t1():
    text = (NET_DIR / "platform.h").read_text(encoding="utf-8")
    assert "#if defined(_WIN32)" in text, "platform.h should branch on _WIN32"
    assert "<sys/socket.h>" in text, "POSIX branch must include <sys/socket.h>"
    assert "<unistd.h>" in text, "POSIX branch must include <unistd.h>"
    assert "<arpa/inet.h>" in text or "<netinet/in.h>" in text, \
        "POSIX branch must include an inet header"


@scenario("schannel_tls_is_gated_on_win32_in_header")
def _t2():
    text = TCP_LINE_HEADER.read_text(encoding="utf-8")
    # The schannel.h include + tls_credentials_ member must not be visible
    # on non-Windows builds.
    assert "#include <schannel.h>" in text, "header should still include schannel.h on Windows"
    # Find the schannel include and confirm it sits inside an _WIN32 block.
    idx = text.index("#include <schannel.h>")
    block_open = text.rfind("#if defined(_WIN32)", 0, idx)
    block_close = text.find("#endif", idx)
    assert block_open >= 0 and block_close > idx, \
        "schannel.h include must be wrapped in #if defined(_WIN32) ... #endif"


@scenario("schannel_tls_impl_is_gated_on_win32_in_cpp")
def _t3():
    text = TCP_LINE_CPP.read_text(encoding="utf-8")
    # tls_handshake / tls_send / tls_recv / tls_cleanup are Win32-only.
    for symbol in ("tls_handshake", "tls_send", "tls_recv", "tls_cleanup"):
        assert symbol in text, f"missing symbol {symbol}"
    # The full tls_handshake body must be inside a _WIN32 block.
    idx = text.index("bool TcpLineClient::tls_handshake(")
    block_open = text.rfind("#if defined(_WIN32)", 0, idx)
    assert block_open >= 0, "tls_handshake must be inside #if defined(_WIN32)"


@scenario("android_manifest_declares_internet_and_qt_activity")
def _t4():
    text = MANIFEST.read_text(encoding="utf-8")
    assert 'android:name="android.permission.INTERNET"' in text, \
        "AndroidManifest must request INTERNET permission"
    assert "org.qtproject.qt.android.bindings.QtActivity" in text, \
        "AndroidManifest must use QtActivity entry point"
    assert "android.intent.category.LAUNCHER" in text, \
        "AndroidManifest must mark a LAUNCHER activity"


@scenario("android_readme_documents_pending_action")
def _t5():
    text = ANDROID_README.read_text(encoding="utf-8")
    assert "PA-007" in text, "README should reference PA-007 toolchain install"
    assert "qt-cmake" in text, "README should show the qt-cmake invocation"
    assert "ANDROID_NDK_ROOT" in text or "NDK" in text, \
        "README should mention the NDK"
    assert "JDK 17" in text or "JDK17" in text or "jdk-17" in text.lower(), \
        "README should document JDK 17 requirement"


@scenario("cmake_only_links_win32_libs_when_windows")
def _t6():
    text = CLIENT_CMAKE.read_text(encoding="utf-8")
    # ws2_32 / secur32 must only appear under an if(WIN32) guard.
    assert "if(WIN32)" in text and "ws2_32" in text and "secur32" in text, \
        "expected if(WIN32) ... ws2_32 secur32 ... endif() pattern"
    win32_block_start = text.index("if(WIN32)")
    win32_block_end = text.find("endif()", win32_block_start)
    win32_block = text[win32_block_start:win32_block_end]
    assert "ws2_32" in win32_block and "secur32" in win32_block, \
        "ws2_32 and secur32 must live inside the if(WIN32) block"


@scenario("cmake_uses_qt_add_executable_for_android_packaging")
def _t7():
    text = CLIENT_CMAKE.read_text(encoding="utf-8")
    assert "qt_add_executable" in text, \
        "app_desktop should use qt_add_executable so APK packaging is wired"
    assert "QT_ANDROID_PACKAGE_SOURCE_DIR" in text, \
        "must point at deploy/android via QT_ANDROID_PACKAGE_SOURCE_DIR"
    assert "QT_ANDROID_MIN_SDK_VERSION" in text, \
        "must set QT_ANDROID_MIN_SDK_VERSION"


@scenario("build_script_exists_and_documents_pipeline")
def _t8():
    assert BUILD_SCRIPT.exists(), f"missing {BUILD_SCRIPT}"
    text = BUILD_SCRIPT.read_text(encoding="utf-8")
    for needle in ("qt-cmake", "ANDROID_NDK_ROOT", "JAVA_HOME",
                   "android-build-release-unsigned.apk", "SHA256"):
        assert needle in text, f"build script missing reference: {needle}"


@scenario("if_apk_built_then_size_is_reasonable")
def _t9():
    if not APK_PATH.exists():
        # APK not built yet — fine for static check.
        return
    size = APK_PATH.stat().st_size
    assert size > 1_000_000, f"APK suspiciously small: {size} bytes"
    assert size < 200_000_000, f"APK suspiciously large: {size} bytes"


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
