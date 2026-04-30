"""Validator for the M136 mobile (QML) theme.

Mirror checks for the desktop validator (validate_theme_tokens.py): every
desktop kLightTheme / kDarkTheme color token has a matching property in
client/src/app_mobile/qml/Theme.qml so the two surfaces share one palette
spec. Also verifies:

  - Theme.qml is registered in client/src/CMakeLists.txt's qt_add_qml_module
    QML_FILES list (otherwise the QML loader can't find the type).
  - Main.qml hangs a Theme instance off the root and forwards `darkMode`
    from a `themeDarkMode` context property.
  - app_mobile/main.cpp pushes the env-var-derived flag into the QML
    engine via `setContextProperty("themeDarkMode", ...)`.

Pure static analysis. Runs in CI without Qt installed.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
THEME_QML = REPO / "client" / "src" / "app_mobile" / "qml" / "Theme.qml"
MAIN_QML = REPO / "client" / "src" / "app_mobile" / "qml" / "Main.qml"
MOBILE_MAIN_CPP = REPO / "client" / "src" / "app_mobile" / "main.cpp"
DESKTOP_TOKENS = REPO / "client" / "src" / "app_desktop" / "design_tokens.h"
CMAKE = REPO / "client" / "src" / "CMakeLists.txt"


HEX_RE = re.compile(r'^"#[0-9a-fA-F]{6}"$')


def parse_qml_colors(text: str, prefix: str) -> dict[str, str]:
    """Extract `readonly property color <prefix><CamelCase>: "#rrggbb"` rows."""
    pat = re.compile(
        rf'readonly\s+property\s+color\s+(?P<key>{re.escape(prefix)}[A-Z][A-Za-z]*)\s*:\s*"(?P<value>#[0-9a-fA-F]{{6}})"'
    )
    return {m.group("key"): m.group("value") for m in pat.finditer(text)}


def parse_desktop_theme(text: str, name: str) -> dict[str, str]:
    pat = re.compile(
        rf"inline\s+constexpr\s+Theme\s+{re.escape(name)}\s*=\s*\{{(.*?)\}};",
        re.DOTALL,
    )
    m = pat.search(text)
    assert m, f"could not find {name}"
    body = m.group(1)
    field = re.compile(r'/\*\s*(?P<key>[a-z_]+)\s*\*/\s*"(?P<value>#[0-9a-fA-F]{6})"')
    return {fm.group("key"): fm.group("value") for fm in field.finditer(body)}


def snake_to_camel(s: str, prefix: str) -> str:
    """app_background -> lightAppBackground or darkAppBackground."""
    parts = s.split("_")
    return prefix + "".join(p[:1].upper() + p[1:] for p in parts)


def main() -> int:
    for path in (THEME_QML, MAIN_QML, MOBILE_MAIN_CPP, DESKTOP_TOKENS, CMAKE):
        if not path.exists():
            print(f"[FAIL] missing {path}")
            return 1

    theme_text = THEME_QML.read_text(encoding="utf-8")
    main_text = MAIN_QML.read_text(encoding="utf-8")
    cpp_text = MOBILE_MAIN_CPP.read_text(encoding="utf-8")
    desktop_text = DESKTOP_TOKENS.read_text(encoding="utf-8")
    cmake_text = CMAKE.read_text(encoding="utf-8")

    print("[scenario] Theme.qml exists with light + dark color sets")
    light_qml = parse_qml_colors(theme_text, "light")
    dark_qml = parse_qml_colors(theme_text, "dark")
    assert len(light_qml) >= 16, f"expected >=16 light* tokens, got {len(light_qml)}"
    assert len(dark_qml) >= 16, f"expected >=16 dark* tokens, got {len(dark_qml)}"
    assert set(light_qml.keys()) == {snake_to_camel(k.replace("light", ""), "light") for k in light_qml}, \
        "light tokens must use lightCamelCase naming"
    print(f"[ok ] {len(light_qml)} light tokens, {len(dark_qml)} dark tokens")

    print("[scenario] desktop ↔ mobile parity (every shared token has matching hex)")
    desktop_light = parse_desktop_theme(desktop_text, "kLightTheme")
    desktop_dark = parse_desktop_theme(desktop_text, "kDarkTheme")
    # Tokens we expect to share between the two surfaces. Mobile may legitimately
    # carry fewer (no border_input, no splitter — those are Qt Widget-specific).
    shared = (
        "app_background", "surface", "surface_muted", "chat_area",
        "border", "border_subtle", "selection_tint", "hover",
        "text_primary", "text_secondary", "text_muted",
        "own_bubble_top", "own_bubble_bottom", "own_bubble_text",
        "peer_bubble", "peer_bubble_text", "tick_unread", "tick_read",
    )
    mismatches = []
    for snake_key in shared:
        light_camel = snake_to_camel(snake_key, "light")
        dark_camel = snake_to_camel(snake_key, "dark")
        if light_qml.get(light_camel) != desktop_light.get(snake_key):
            mismatches.append(f"light.{snake_key}: qml={light_qml.get(light_camel)} cpp={desktop_light.get(snake_key)}")
        if dark_qml.get(dark_camel) != desktop_dark.get(snake_key):
            mismatches.append(f"dark.{snake_key}: qml={dark_qml.get(dark_camel)} cpp={desktop_dark.get(snake_key)}")
    assert not mismatches, "desktop/mobile palette drift:\n  " + "\n  ".join(mismatches)
    print(f"[ok ] {len(shared)} shared tokens match between desktop kThemes and Theme.qml")

    print("[scenario] Theme.qml exposes resolved (active) palette via darkMode switch")
    # Each shared token should also have a top-level `<key>: darkMode ? dark... : light...`
    for snake_key in shared:
        camel = snake_to_camel(snake_key, "")
        camel = camel[:1].lower() + camel[1:]  # appBackground, etc.
        # Match either single-line conditional or multi-line continuation.
        pat = re.compile(
            rf"readonly\s+property\s+color\s+{re.escape(camel)}\s*:\s*"
            rf"darkMode\s*\?\s*dark{re.escape(camel[:1].upper() + camel[1:])}",
        )
        assert pat.search(theme_text), \
            f"Theme.qml missing active `{camel}` property that switches on darkMode"
    print(f"[ok ] {len(shared)} active properties switch on darkMode")

    print("[scenario] Main.qml hangs a Theme off the root and reads themeDarkMode")
    assert "Theme {" in main_text, "Main.qml must instantiate `Theme { ... }`"
    assert "themeDarkMode" in main_text, \
        "Main.qml must reference the `themeDarkMode` context property"
    assert "theme.appBackground" in main_text or "theme.chatArea" in main_text, \
        "Main.qml must consume at least one resolved theme property"
    print("[ok ] Main.qml wires Theme + context property")

    print("[scenario] mobile/main.cpp pushes themeDarkMode from env var")
    assert "TELEGRAM_LIKE_THEME" in cpp_text, \
        "mobile main.cpp must read the TELEGRAM_LIKE_THEME env var"
    assert 'setContextProperty' in cpp_text and 'themeDarkMode' in cpp_text, \
        "mobile main.cpp must setContextProperty(\"themeDarkMode\", ...)"
    print("[ok ] env var → engine context property wired in main.cpp")

    print("[scenario] Theme.qml registered in qt_add_qml_module QML_FILES")
    assert "app_mobile/qml/Theme.qml" in cmake_text, \
        "client/src/CMakeLists.txt qt_add_qml_module must list app_mobile/qml/Theme.qml"
    print("[ok ] Theme.qml registered in QML module")

    print("\nAll 6/6 scenarios passed.")
    return 0


if __name__ == "__main__":
    import traceback
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(f"[FAIL] {exc}")
        traceback.print_exc()
        sys.exit(1)
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}")
        traceback.print_exc()
        sys.exit(1)
