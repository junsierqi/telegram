"""Static checks for the Apple (macOS + iOS) build path.

Runs locally + in CI to catch CMake guard slips that would either leak
Apple-only properties to non-Apple builds or skip the bundle config on a
real macOS host. Doesn't attempt the actual build — that's the
linux-cpp / linux-desktop / macos-build CI jobs.

Scenarios:
  1. deploy/macos/Info.plist.in exists and has CFBundle* templating.
  2. deploy/ios/Info.plist.in exists and has iOS-specific keys.
  3. deploy/macos/README.md + deploy/ios/README.md exist + document the
     untested-by-CI iOS situation.
  4. CMakeLists.txt has if(APPLE AND NOT IOS) blocks for app_desktop AND
     app_mobile that set MACOSX_BUNDLE_INFO_PLIST.
  5. CMakeLists.txt has an if(IOS) block on app_mobile pointing at the
     iOS Info.plist + setting XCODE_ATTRIBUTE_TARGETED_DEVICE_FAMILY.
  6. ci.yml has a macos-build job using macos-latest + Homebrew qt@6.
  7. The Apple blocks DON'T leak property names outside the if-guards
     (i.e. no top-level MACOSX_BUNDLE_INFO_PLIST that fires on every host).
  8. No new Apple-only includes leaked into shared client source files
     (anything Cocoa/Foundation/UIKit must stay out of cross-platform code).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MACOS_PLIST = REPO / "deploy" / "macos" / "Info.plist.in"
IOS_PLIST = REPO / "deploy" / "ios" / "Info.plist.in"
MACOS_README = REPO / "deploy" / "macos" / "README.md"
IOS_README = REPO / "deploy" / "ios" / "README.md"
CMAKE = REPO / "client" / "src" / "CMakeLists.txt"
CI = REPO / ".github" / "workflows" / "ci.yml"
SHARED_SOURCES = list((REPO / "client" / "src").rglob("*.cpp")) + \
                 list((REPO / "client" / "src").rglob("*.h"))

SCENARIOS: list[tuple[str, callable]] = []


def scenario(name):
    def deco(fn):
        SCENARIOS.append((name, fn))
        return fn
    return deco


@scenario("macos_info_plist_present_and_templated")
def _t1():
    text = MACOS_PLIST.read_text(encoding="utf-8")
    for needle in ("@MACOSX_BUNDLE_BUNDLE_NAME@",
                   "@MACOSX_BUNDLE_GUI_IDENTIFIER@",
                   "@MACOSX_BUNDLE_SHORT_VERSION_STRING@",
                   "<key>LSMinimumSystemVersion</key>",
                   "<key>NSHighResolutionCapable</key>"):
        assert needle in text, f"macOS Info.plist missing: {needle}"


@scenario("ios_info_plist_present_with_required_keys")
def _t2():
    text = IOS_PLIST.read_text(encoding="utf-8")
    for needle in ("<key>UIDeviceFamily</key>",
                   "<key>MinimumOSVersion</key>",
                   "<key>UISupportedInterfaceOrientations</key>",
                   "<key>UIRequiredDeviceCapabilities</key>",
                   "@MACOSX_BUNDLE_BUNDLE_NAME@"):
        assert needle in text, f"iOS Info.plist missing: {needle}"


@scenario("readmes_exist_and_document_untested_ios")
def _t3():
    macos = MACOS_README.read_text(encoding="utf-8")
    ios = IOS_README.read_text(encoding="utf-8")
    assert "macos-build" in macos, "macOS README should reference the macos-build CI job"
    assert "brew install qt@6" in macos, "macOS README should show the brew install"
    # Be honest with future readers about the iOS situation.
    assert "untested" in ios.lower() or "not been verified" in ios.lower(), \
        "iOS README should disclose that the path hasn't been built locally / in CI"
    assert "qt-cmake" in ios, "iOS README should show the qt-cmake invocation"
    assert "PA-005" in ios or "Apple Developer" in ios, \
        "iOS README should reference the Developer-Program PA"


@scenario("cmake_has_local_ios_boolean")
def _t4_pre():
    text = CMAKE.read_text(encoding="utf-8")
    assert "TELEGRAM_LIKE_TARGET_IS_IOS" in text, \
        "CMake should define a local boolean (handles both Qt's IOS var + bare CMAKE_SYSTEM_NAME=iOS)"
    assert 'CMAKE_SYSTEM_NAME STREQUAL "iOS"' in text, \
        "Local iOS detection should consult the canonical CMAKE_SYSTEM_NAME"


# Match either the local-boolean form or the legacy `IOS`/`APPLE AND NOT IOS`
# form so the validator survives both refactors.
APPLE_NOT_IOS_PATTERNS = [
    r"if\(APPLE AND NOT TELEGRAM_LIKE_TARGET_IS_IOS\)",
    r"if\(APPLE AND NOT IOS\)",
]
IOS_PATTERNS = [
    r"if\(TELEGRAM_LIKE_TARGET_IS_IOS\)",
    r"if\(IOS\)",
]


def _find_blocks(text: str, openers: list[str]) -> list[str]:
    blocks: list[str] = []
    for opener in openers:
        for opener_match in re.finditer(opener, text):
            # Walk forward counting nested if()/endif() to find the matching close.
            depth = 1
            i = opener_match.end()
            while i < len(text) and depth > 0:
                m = re.search(r"\bif\s*\(|\bendif\s*\(\s*\)", text[i:])
                if not m:
                    break
                token = m.group(0)
                if token.startswith("endif"):
                    depth -= 1
                else:
                    depth += 1
                i += m.end()
            blocks.append(text[opener_match.start():i])
    return blocks


@scenario("cmake_has_apple_blocks_for_both_targets")
def _t4():
    text = CMAKE.read_text(encoding="utf-8")
    apple_blocks = _find_blocks(text, APPLE_NOT_IOS_PATTERNS)
    assert apple_blocks, "CMake should have an APPLE/non-iOS guarded block"
    has_desktop = any("app_desktop PROPERTIES" in b for b in apple_blocks)
    has_mobile = any("app_mobile PROPERTIES" in b for b in apple_blocks)
    assert has_desktop, "macOS guard should configure app_desktop"
    assert has_mobile, "macOS guard should configure app_mobile"


@scenario("cmake_has_ios_block_pointing_at_ios_plist")
def _t5():
    text = CMAKE.read_text(encoding="utf-8")
    ios_blocks = _find_blocks(text, IOS_PATTERNS)
    assert ios_blocks, "CMake should have an iOS guard block"
    assert any("deploy/ios/Info.plist.in" in b for b in ios_blocks), \
        "iOS block should set MACOSX_BUNDLE_INFO_PLIST to the iOS plist"
    assert any("XCODE_ATTRIBUTE_TARGETED_DEVICE_FAMILY" in b for b in ios_blocks), \
        "iOS block should set TARGETED_DEVICE_FAMILY for iPhone+iPad"


@scenario("ci_macos_build_job_present")
def _t6():
    text = CI.read_text(encoding="utf-8")
    assert "macos-build:" in text, "CI must declare a macos-build job"
    assert "macos-latest" in text, "macos-build job should use macos-latest runner"
    assert "brew install qt@6" in text or "qt@6" in text, \
        "macos-build should install Qt 6 via Homebrew"
    assert "app_desktop.app" in text, \
        "macos-build should confirm .app bundle materialised"
    assert "app_mobile.app" in text, \
        "macos-build should confirm app_mobile.app materialised"


@scenario("apple_properties_only_inside_apple_guards")
def _t7():
    text = CMAKE.read_text(encoding="utf-8")
    # MACOSX_BUNDLE_INFO_PLIST and every XCODE_ATTRIBUTE_* property are
    # Apple-only and must never appear at top level — only inside an
    # if(APPLE...) / if(...IS_IOS) / if(IOS) block.
    apple_props = [
        "MACOSX_BUNDLE_INFO_PLIST",
        "XCODE_ATTRIBUTE_TARGETED_DEVICE_FAMILY",
        "XCODE_ATTRIBUTE_PRODUCT_BUNDLE_IDENTIFIER",
    ]
    # Accept any of these opener forms as "an Apple guard".
    apple_opener = re.compile(
        r"if\((APPLE|IOS|TELEGRAM_LIKE_TARGET_IS_IOS|"
        r"APPLE AND NOT IOS|APPLE AND NOT TELEGRAM_LIKE_TARGET_IS_IOS)[^)]*\)"
    )
    for prop in apple_props:
        for occurrence in re.finditer(re.escape(prop), text):
            preceding = text[:occurrence.start()]
            ifs = list(apple_opener.finditer(preceding))
            endifs_after_last_if = preceding.rfind("endif()")
            last_if_pos = ifs[-1].start() if ifs else -1
            assert last_if_pos > endifs_after_last_if, (
                f"{prop} at offset {occurrence.start()} is not inside a "
                f"current Apple guard block — would leak to non-Apple "
                f"platforms."
            )


@scenario("no_apple_only_includes_in_shared_sources")
def _t8():
    # Headers like <Cocoa/Cocoa.h>, <Foundation/Foundation.h>, <UIKit/UIKit.h>
    # only exist on Apple SDKs. They must never show up in the cross-platform
    # client source tree without a guard.
    forbidden = ("<Cocoa/", "<Foundation/", "<UIKit/", "<AppKit/")
    for path in SHARED_SOURCES:
        text = path.read_text(encoding="utf-8", errors="replace")
        for needle in forbidden:
            if needle in text:
                # If it appears, must be inside an #ifdef __APPLE__ /
                # #if defined(__APPLE__) guard.
                idx = text.index(needle)
                pre = text[:idx]
                guard_open = max(pre.rfind("#ifdef __APPLE__"),
                                 pre.rfind("#if defined(__APPLE__"))
                guard_close = pre.rfind("#endif")
                assert guard_open > guard_close, (
                    f"{path.relative_to(REPO)} includes {needle} outside "
                    f"#if defined(__APPLE__) — would break Win/Linux/Android."
                )


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
