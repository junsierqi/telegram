"""Validator for M140 — desktop typing indicator (3-dot pulse animation).

Static analysis on:
  - typing_indicator.{h,cpp}: Q_OBJECT widget with QTimer-driven phase
    animation, public setActive(peer, on), setDotColor / setLabelColor,
    custom paintEvent painting 3 dots with alpha fall-off + optional
    "X is typing" label.
  - main.cpp: instantiates TypingIndicator in the chat header subtitle
    row, themes it via render_store(), and exposes a TELEGRAM_LIKE_DEMO_TYPING
    env-var hook so the animation is visible even before the
    backend protocol pulse exists.
  - CMakeLists.txt: registers the new sources on app_desktop.

The actual TYPING_START / TYPING_STOP fanout is intentionally a separate
milestone — this primitive just ships the UI half so the future hook is
a one-line change.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
HEADER = REPO / "client" / "src" / "app_desktop" / "typing_indicator.h"
SRC = REPO / "client" / "src" / "app_desktop" / "typing_indicator.cpp"
MAIN = REPO / "client" / "src" / "app_desktop" / "main.cpp"
CMAKE = REPO / "client" / "src" / "CMakeLists.txt"


def main() -> int:
    for p in (HEADER, SRC, MAIN, CMAKE):
        if not p.exists():
            print(f"[FAIL] missing {p}")
            return 1
    h = HEADER.read_text(encoding="utf-8")
    cpp = SRC.read_text(encoding="utf-8")
    m = MAIN.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")

    print("[scenario] TypingIndicator class declared with Q_OBJECT + public API")
    assert "class TypingIndicator" in h, "TypingIndicator class missing"
    assert "Q_OBJECT" in h, "TypingIndicator must be a Q_OBJECT"
    for member in ("setActive", "setDotColor", "setLabelColor",
                   "paintEvent", "active"):
        assert re.search(rf"\b{re.escape(member)}\b", h), \
            f"TypingIndicator missing {member}"
    print("[ok ] header declares 5+ public methods")

    print("[scenario] paintEvent draws 3 dots driven by a QTimer")
    assert "QTimer" in cpp, "TypingIndicator implementation must use QTimer"
    assert "drawEllipse" in cpp, "paint must call drawEllipse for the dots"
    assert "QPainter" in cpp, "paintEvent must use QPainter"
    # Three-phase animation — at least one place computes the alpha per dot.
    assert re.search(r"setAlpha\s*\(", cpp), "dot alpha must be modulated for the pulse"
    # Show/hide gating.
    assert "setVisible(active_)" in cpp or "setVisible(false)" in cpp, \
        "indicator must auto-hide when inactive"
    print("[ok ] QTimer animation + per-dot alpha + visibility gate present")

    print("[scenario] main.cpp wires TypingIndicator into the chat header")
    assert '#include "app_desktop/typing_indicator.h"' in m, \
        "main.cpp must include typing_indicator.h"
    assert "typing_indicator_" in m, "DesktopWindow must declare typing_indicator_ member"
    assert "new telegram_like::client::app_desktop::TypingIndicator" in m, \
        "TypingIndicator must be constructed in the chat header"
    # Themed via render_store — dot/label color setters fed from active_theme.
    assert "typing_indicator_->setDotColor" in m, \
        "render_store must theme the indicator dot color"
    assert "typing_indicator_->setLabelColor" in m, \
        "render_store must theme the indicator label color"
    # Demo env var hook present.
    assert "TELEGRAM_LIKE_DEMO_TYPING" in m, \
        "env-var demo hook must be wired for visual smoke"
    print("[ok ] member + construction + theming + demo hook all wired")

    print("[scenario] CMake registers typing_indicator sources on app_desktop")
    assert "app_desktop/typing_indicator.cpp" in cmake, \
        "qt_add_executable must list typing_indicator.cpp"
    assert "app_desktop/typing_indicator.h" in cmake, \
        "qt_add_executable must list typing_indicator.h (AUTOMOC scan)"
    print("[ok ] CMake target updated")

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
