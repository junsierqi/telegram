"""M113 macOS UI scaffold static-shape check.

No macOS host on this CI; verifies the scaffolding picked up by
`brew install qt@6 && cmake -G Ninja` on a real macOS host:

- deploy/macos/Info.plist.in is well-formed XML and contains the
  required CFBundle* + LSMinimumSystemVersion + NSHighResolutionCapable.
- client/src/CMakeLists.txt has the macOS bundle property block (gated on
  APPLE AND NOT IOS) for both app_desktop and app_mobile.
- The new macdeployqt POST_BUILD step (M113) is present and gated on
  TELEGRAM_LIKE_SKIP_MACDEPLOYQT so CI can opt out.
- README documents the build procedure + flags PA-005.
- No regression on Windows windeployqt POST_BUILD — both blocks coexist.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def scenario(label: str) -> None:
    print(f"\n[scenario] {label}")


def run_macos_info_plist_present_and_valid() -> None:
    scenario("deploy/macos/Info.plist.in is well-formed XML with required keys")
    plist = REPO / "deploy" / "macos" / "Info.plist.in"
    text = plist.read_text(encoding="utf-8")
    cleaned = text
    for token in (
        "@MACOSX_BUNDLE_BUNDLE_NAME@",
        "@MACOSX_BUNDLE_EXECUTABLE_NAME@",
        "@MACOSX_BUNDLE_GUI_IDENTIFIER@",
        "@MACOSX_BUNDLE_SHORT_VERSION_STRING@",
        "@MACOSX_BUNDLE_BUNDLE_VERSION@",
        "@MACOSX_BUNDLE_COPYRIGHT@",
    ):
        cleaned = cleaned.replace(token, "X")
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
        "LSMinimumSystemVersion",
        "NSHighResolutionCapable",
    ):
        assert required in keys, (required, keys)


def run_cmake_macos_bundle_block() -> None:
    scenario("client/src/CMakeLists.txt sets MACOSX_BUNDLE_* on both targets")
    cml = (REPO / "client" / "src" / "CMakeLists.txt").read_text(encoding="utf-8")
    desktop_idx = cml.find("MACOSX_BUNDLE_GUI_IDENTIFIER \"com.example.telegramlike.desktop\"")
    mobile_idx = cml.find("MACOSX_BUNDLE_GUI_IDENTIFIER \"com.example.telegramlike.mobile\"")
    assert desktop_idx != -1, "app_desktop macOS bundle identifier missing"
    assert mobile_idx != -1, "app_mobile macOS bundle identifier missing"
    assert "deploy/macos/Info.plist.in" in cml


def run_macdeployqt_post_build_present() -> None:
    scenario("M113 macdeployqt POST_BUILD step present and opt-out gated")
    cml = (REPO / "client" / "src" / "CMakeLists.txt").read_text(encoding="utf-8")
    assert "TELEGRAM_LIKE_SKIP_MACDEPLOYQT" in cml, "skip flag missing"
    assert "find_program(TELEGRAM_LIKE_MACDEPLOYQT macdeployqt" in cml, "find_program missing"
    # POST_BUILD runs on both targets.
    assert cml.count("${TELEGRAM_LIKE_MACDEPLOYQT}") >= 2, (
        "expected macdeployqt POST_BUILD on both app_desktop and app_mobile"
    )


def run_no_windows_post_build_regression() -> None:
    scenario("Windows windeployqt POST_BUILD still present (no regression)")
    cml = (REPO / "client" / "src" / "CMakeLists.txt").read_text(encoding="utf-8")
    assert "TELEGRAM_LIKE_WINDEPLOYQT" in cml
    assert cml.count("${TELEGRAM_LIKE_WINDEPLOYQT}") >= 2, (
        "expected windeployqt POST_BUILD on both app_desktop and app_mobile"
    )


def run_readme_updated() -> None:
    scenario("deploy/macos/README.md flags PA-005 + notes M113 macdeployqt POST_BUILD")
    readme = (REPO / "deploy" / "macos" / "README.md").read_text(encoding="utf-8")
    assert "PA-005" in readme
    assert "M113" in readme, "expected M113 reference in README"
    assert "macdeployqt" in readme


def main() -> int:
    scenarios = [
        run_macos_info_plist_present_and_valid,
        run_cmake_macos_bundle_block,
        run_macdeployqt_post_build_present,
        run_no_windows_post_build_regression,
        run_readme_updated,
    ]
    for fn in scenarios:
        fn()
    print(f"\nAll {len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
