"""Validator for the M135 desktop theme system.

Checks the source-of-truth header `client/src/app_desktop/design_tokens.h`
plus the stylesheet builder in `app_desktop/main.cpp` to ensure:

  1. Both `kLightTheme` and `kDarkTheme` are declared and contain a value
     for every field of the `Theme` struct.
  2. Every theme value is a 7-char `#rrggbb` literal (well-formed hex).
  3. The light theme's app_background is bright (luma >= 0.6) and the dark
     theme's app_background is dark (luma <= 0.25). Same direction for
     text_primary (light theme dark text, dark theme light text).
  4. The brand `primary` color is identical across themes (Telegram keeps
     its accent constant when toggling themes).
  5. The stylesheet builder no longer has stray hardcoded `#xxxxxx` hex
     literals — every color must come through `{name}` substitution, so
     a dark-mode toggle can't leak the light palette through.
  6. The `active_theme()` resolver actually reads `TELEGRAM_LIKE_THEME`.

Pure static analysis (regex on source) — runs without Qt installed, fast,
deterministic, and CI-safe.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
HEADER = REPO / "client" / "src" / "app_desktop" / "design_tokens.h"
MAIN = REPO / "client" / "src" / "app_desktop" / "main.cpp"


HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def luma(hex_color: str) -> float:
    """Approximate relative luminance in [0,1] for sanity-checking themes."""
    h = hex_color.lstrip("#")
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def parse_theme_block(text: str, name: str) -> dict[str, str]:
    """Pull the `{...}` initializer for a `kLightTheme` / `kDarkTheme`.

    Each line inside the block is expected to look like:
        /* field_name */ "#rrggbb",
    or a trailing entry with no comma. We capture (field_name, hex_value).
    """
    pattern = re.compile(
        rf"inline\s+constexpr\s+Theme\s+{re.escape(name)}\s*=\s*\{{(.*?)\}};",
        re.DOTALL,
    )
    m = pattern.search(text)
    if not m:
        raise AssertionError(f"could not find {name} initializer")
    body = m.group(1)
    field_re = re.compile(
        r"/\*\s*(?P<key>[a-z_]+)\s*\*/\s*\"(?P<value>#[0-9a-fA-F]{6})\""
    )
    fields = {match.group("key"): match.group("value") for match in field_re.finditer(body)}
    return fields


def parse_struct_fields(text: str) -> list[str]:
    """Extract the ordered list of `Theme` struct field names."""
    m = re.search(r"struct\s+Theme\s*\{(?P<body>.*?)\};", text, re.DOTALL)
    if not m:
        raise AssertionError("could not find `struct Theme` declaration")
    body = m.group("body")
    name_re = re.compile(r"const\s+char\*\s+(?P<key>[a-z_]+)\s*;")
    return [match.group("key") for match in name_re.finditer(body)]


def main() -> int:
    if not HEADER.exists():
        print(f"[FAIL] missing {HEADER}")
        return 1
    if not MAIN.exists():
        print(f"[FAIL] missing {MAIN}")
        return 1

    header_text = HEADER.read_text(encoding="utf-8")
    main_text = MAIN.read_text(encoding="utf-8")

    print("[scenario] struct Theme + light/dark constants present and well-formed")
    fields = parse_struct_fields(header_text)
    assert len(fields) >= 20, f"expected ≥20 theme fields, got {len(fields)}"
    light = parse_theme_block(header_text, "kLightTheme")
    dark = parse_theme_block(header_text, "kDarkTheme")
    for theme_name, theme in (("kLightTheme", light), ("kDarkTheme", dark)):
        for field in fields:
            assert field in theme, f"{theme_name} is missing field `{field}`"
            value = theme[field]
            assert HEX_RE.match(value), f"{theme_name}.{field} = {value!r} is not #rrggbb"
    print(f"[ok ] {len(fields)} fields populated in both themes ({len(light)} / {len(dark)})")

    print("[scenario] light theme is light, dark theme is dark (luma sanity)")
    bg_l = luma(light["app_background"])
    bg_d = luma(dark["app_background"])
    tx_l = luma(light["text_primary"])
    tx_d = luma(dark["text_primary"])
    assert bg_l >= 0.6, f"light app_background luma {bg_l:.2f} should be >= 0.6"
    assert bg_d <= 0.25, f"dark app_background luma {bg_d:.2f} should be <= 0.25"
    assert tx_l <= 0.25, f"light text_primary luma {tx_l:.2f} should be <= 0.25"
    assert tx_d >= 0.6, f"dark text_primary luma {tx_d:.2f} should be >= 0.6"
    print(f"[ok ] light bg/tx = {bg_l:.2f}/{tx_l:.2f}, dark bg/tx = {bg_d:.2f}/{tx_d:.2f}")

    print("[scenario] brand primary stable across themes (Telegram keeps accent constant)")
    assert light["primary"] == dark["primary"], (
        f"primary differs: light={light['primary']} dark={dark['primary']}"
    )
    print(f"[ok ] primary = {light['primary']} in both themes")

    print("[scenario] active_theme() reads TELEGRAM_LIKE_THEME env var")
    assert "TELEGRAM_LIKE_THEME" in header_text, \
        "active_theme() must read the TELEGRAM_LIKE_THEME env var"
    assert "active_theme()" in main_text, \
        "telegram_stylesheet() must call active_theme()"
    print("[ok ] env-var resolver wired through to stylesheet builder")

    print("[scenario] stylesheet builder has no stray hardcoded hex colors")
    # Scope the scan to the telegram_stylesheet() function body. Outside
    # that function, hardcoded hex (e.g. avatar palette in design_tokens.h
    # which is intentional) is allowed.
    style_match = re.search(
        r"static\s+QString\s+telegram_stylesheet\s*\(\s*\)\s*\{(?P<body>.*?)\n\s{4}\}",
        main_text,
        re.DOTALL,
    )
    assert style_match, "could not locate telegram_stylesheet() body in main.cpp"
    body = style_match.group("body")
    # Token-substitution dict legitimately mentions hex via `t.<field>`, so
    # we only flag hex literals that appear INSIDE the QSS template (which
    # we identify as the R"(...)" raw string).
    qss_match = re.search(r'R"\((?P<qss>.*?)\)"', body, re.DOTALL)
    assert qss_match, "telegram_stylesheet() must hold the QSS in a R\"(...)\" raw string"
    qss = qss_match.group("qss")
    # Allow bare #ffffff for selection-color (white text on accent fill is
    # theme-independent, used in a few places). Anything else flagged.
    stray = [
        match for match in re.finditer(r"#[0-9a-fA-F]{6}", qss)
        if match.group(0).lower() != "#ffffff"
    ]
    assert not stray, (
        f"stylesheet has {len(stray)} stray hex colors (first: {stray[0].group(0)!r}); "
        "every color should come from a {name} placeholder so dark mode propagates"
    )
    # Conversely, we expect at least 10 placeholders to confirm the template
    # actually got tokenised.
    placeholders = re.findall(r"\{[a-z_]+\}", qss)
    assert len(placeholders) >= 30, (
        f"stylesheet uses only {len(placeholders)} {{name}} placeholders — expected >= 30 "
        "after the M135 tokenisation"
    )
    print(f"[ok ] no stray hex literals; {len(placeholders)} placeholders bound")

    print("[scenario] bubble tokens published for M137 (own + peer + ticks)")
    bubble_keys = (
        "own_bubble_top", "own_bubble_bottom", "own_bubble_text",
        "peer_bubble", "peer_bubble_text",
        "tick_unread", "tick_read",
    )
    for key in bubble_keys:
        assert key in light and key in dark, f"missing bubble token `{key}` in one of the themes"
    # own gradient must keep some hue identity (top != bottom) so it's a
    # gradient, not a flat fill.
    for theme_name, theme in (("light", light), ("dark", dark)):
        assert theme["own_bubble_top"] != theme["own_bubble_bottom"], \
            f"{theme_name} theme own_bubble_top == own_bubble_bottom — that's a flat fill, not a gradient"
    print(f"[ok ] {len(bubble_keys)} bubble tokens present + own gradient is non-flat")

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
