"""Validator for M139 — Telegram-style settings page polish + runtime theme toggle.

Static analysis on:
  - design_tokens.h: `set_active_theme(bool)` + `is_dark_theme()` helpers
    expose runtime theme switching now that the M135 cache is mutable.
  - app_desktop/main.cpp:
    - settings nav has icon-prefixed entries including the new
      "Appearance" category.
    - Appearance page wires QRadioButton{Light,Dark} to a lambda that
      flips `set_active_theme(...)`, re-applies `telegram_stylesheet()`,
      saves to QSettings, and re-renders the bubble view.
    - main() reads the persisted preference from QSettings BEFORE
      constructing the window so the first paint matches the saved
      mode (and falls through to active_theme()'s env-var seed when
      no preference is recorded).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
TOKENS = REPO / "client" / "src" / "app_desktop" / "design_tokens.h"
MAIN = REPO / "client" / "src" / "app_desktop" / "main.cpp"


def main() -> int:
    for p in (TOKENS, MAIN):
        if not p.exists():
            print(f"[FAIL] missing {p}")
            return 1

    tokens = TOKENS.read_text(encoding="utf-8")
    m = MAIN.read_text(encoding="utf-8")

    print("[scenario] design_tokens.h exposes set_active_theme + is_dark_theme")
    assert "set_active_theme" in tokens, "design_tokens.h must expose set_active_theme(bool)"
    assert "is_dark_theme" in tokens, "design_tokens.h must expose is_dark_theme()"
    # Mutable cache (a static const Theme*&  helper accessor).
    assert "theme_cache_ref" in tokens, \
        "active_theme cache must be mutable via theme_cache_ref helper"
    print("[ok ] runtime theme switch helpers present")

    print("[scenario] settings nav has icon-prefixed entries including Appearance")
    nav_match = re.search(
        r"NavEntry\s+nav_entries\s*\[\]\s*=\s*\{(?P<body>.*?)\};",
        m, re.DOTALL,
    )
    assert nav_match, "settings nav_entries[] table not found"
    body = nav_match.group("body")
    assert "Appearance" in body, "Appearance entry missing from nav_entries"
    # Each entry is (glyph, label) — at least 8 entries with non-empty glyphs.
    pairs = re.findall(r'\{\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\}', body)
    assert len(pairs) >= 8, f"expected >= 8 nav entries, got {len(pairs)}"
    for glyph, label in pairs:
        assert glyph, f"nav entry {label!r} has empty glyph"
    print(f"[ok ] {len(pairs)} icon-prefixed nav entries; Appearance present")

    print("[scenario] Appearance page constructs Light/Dark radios + apply lambda")
    assert "QRadioButton(\"Light\")" in m, "Appearance page missing Light radio"
    assert "QRadioButton(\"Dark\")" in m, "Appearance page missing Dark radio"
    assert "appearance_light_" in m and "appearance_dark_" in m, \
        "appearance_light_ / appearance_dark_ members must be wired"
    # The toggle lambda must call set_active_theme + re-apply stylesheet
    # + save to QSettings + re-render.
    assert "set_active_theme" in m, "main.cpp must call design::set_active_theme"
    assert "setStyleSheet(telegram_stylesheet" in m, \
        "toggle must re-apply telegram_stylesheet() to QApplication"
    assert "appearance/dark_theme" in m, \
        "toggle must persist preference under QSettings key 'appearance/dark_theme'"
    assert "render_store()" in m, "toggle must re-render the bubble view via render_store()"
    print("[ok ] Light/Dark toggle invokes set_active_theme + re-stylesheet + persist + render")

    print("[scenario] main() seeds active_theme from QSettings before window construction")
    main_func_match = re.search(
        r"int\s+main\s*\([^)]*\)\s*\{(?P<body>.*?)\n\}\s*$",
        m, re.DOTALL,
    )
    assert main_func_match, "could not locate main() body"
    main_body = main_func_match.group("body")
    assert "QSettings" in main_body, "main() must construct a QSettings"
    assert "appearance/dark_theme" in main_body, \
        "main() must read the appearance/dark_theme key"
    assert "set_active_theme" in main_body, \
        "main() must seed the runtime theme from the saved value"
    # Order check: QSettings load must precede DesktopWindow construction.
    qs_idx = main_body.find("QSettings")
    win_idx = main_body.find("DesktopWindow window")
    assert 0 <= qs_idx < win_idx, \
        "QSettings load must run BEFORE DesktopWindow window(args)"
    print("[ok ] persisted theme loaded before first paint")

    print("\nAll 4/4 scenarios passed.")
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
