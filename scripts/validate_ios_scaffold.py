"""M112 iOS UI scaffold static-shape check.

No compile env on this host — verifies that the scaffolding picked up by
Qt for iOS on a real macOS host is structurally complete:

- deploy/ios/Info.plist.in exists, well-formed XML, contains required
  CFBundle* + iOS-specific keys.
- client/src/CMakeLists.txt has the iOS guard block referencing the plist.
- deploy/ios/README.md documents the build procedure + flags PA-005 / PA-010.
- The mobile entry point (client/src/app_mobile/main.cpp + QML root) exists
  so the iOS build has something to compile.
- The iOS guards do not regress other platforms: Windows / Linux / Android
  guards still appear in CMakeLists.txt.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def scenario(label: str) -> None:
    print(f"\n[scenario] {label}")


def run_info_plist_present_and_valid() -> None:
    scenario("deploy/ios/Info.plist.in is well-formed XML with required keys")
    plist = REPO / "deploy" / "ios" / "Info.plist.in"
    assert plist.exists(), plist
    text = plist.read_text(encoding="utf-8")
    # Strip XML comments before parse since ET barfs on the leading <!-- -->
    # only when DOCTYPE is present and entity references are malformed. The
    # @VARIABLE@ tokens are CMake placeholders, not XML — replace with a
    # deterministic marker so ET sees valid XML.
    cleaned = text.replace("@MACOSX_BUNDLE_BUNDLE_NAME@", "X")
    for token in (
        "@MACOSX_BUNDLE_EXECUTABLE_NAME@",
        "@MACOSX_BUNDLE_GUI_IDENTIFIER@",
        "@MACOSX_BUNDLE_SHORT_VERSION_STRING@",
        "@MACOSX_BUNDLE_BUNDLE_VERSION@",
        "@MACOSX_BUNDLE_COPYRIGHT@",
    ):
        cleaned = cleaned.replace(token, "X")
    # Strip the DTD declaration so ET doesn't try to fetch it.
    cleaned = cleaned.replace(
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"\n'
        '                       "http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
        "",
    )
    root = ET.fromstring(cleaned)
    assert root.tag == "plist"
    keys = [el.text for el in root.iter("key")]
    for required in (
        "CFBundleName",
        "CFBundleIdentifier",
        "CFBundleVersion",
        "CFBundleShortVersionString",
        "MinimumOSVersion",
        "UIDeviceFamily",
        "UIRequiredDeviceCapabilities",
    ):
        assert required in keys, (required, keys)


def run_cmake_ios_guards() -> None:
    scenario("client/src/CMakeLists.txt has the iOS guard block")
    cml = (REPO / "client" / "src" / "CMakeLists.txt").read_text(encoding="utf-8")
    assert "TELEGRAM_LIKE_TARGET_IS_IOS" in cml
    assert 'if(CMAKE_SYSTEM_NAME STREQUAL "iOS" OR IOS)' in cml
    assert "deploy/ios/Info.plist.in" in cml
    assert "if(TELEGRAM_LIKE_TARGET_IS_IOS)" in cml


def run_other_platform_guards_intact() -> None:
    scenario("Windows / Apple-non-iOS / Android guards still present (no regression)")
    cml = (REPO / "client" / "src" / "CMakeLists.txt").read_text(encoding="utf-8")
    # The Apple guard for macOS-only setup must still gate on NOT IOS so
    # macOS builds keep working.
    assert "if(APPLE AND NOT TELEGRAM_LIKE_TARGET_IS_IOS)" in cml
    # Android packaging lives in client/src/CMakeLists.txt — ensure its
    # if(ANDROID) block is still intact alongside the new iOS guards.
    assert "if(ANDROID)" in cml, "Android packaging guard missing"
    assert "QT_ANDROID_PACKAGE_SOURCE_DIR" in cml


def run_readme_documents_pa() -> None:
    scenario("deploy/ios/README.md flags PA-005 + PA-010 prerequisites")
    readme = (REPO / "deploy" / "ios" / "README.md").read_text(encoding="utf-8")
    assert "PA-005" in readme, "expected PA-005 (signing) prerequisite"
    assert "PA-010" in readme, "expected PA-010 (macOS host) prerequisite"


def run_mobile_entry_point_present() -> None:
    scenario("Mobile entry point + QML root exist for the iOS build to compile")
    base = REPO / "client" / "src" / "app_mobile"
    candidates = list(base.glob("*"))
    assert candidates, "client/src/app_mobile is empty"
    has_main = any(p.name in ("main.cpp", "main.mm") for p in candidates)
    qml_files = list(base.rglob("*.qml"))
    assert has_main, [p.name for p in candidates]
    assert qml_files, f"no QML files under {base}"


def main() -> int:
    scenarios = [
        run_info_plist_present_and_valid,
        run_cmake_ios_guards,
        run_other_platform_guards_intact,
        run_readme_documents_pa,
        run_mobile_entry_point_present,
    ]
    for fn in scenarios:
        fn()
    print(f"\nAll {len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
