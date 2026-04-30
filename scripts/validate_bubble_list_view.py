"""Validator for M138 — BubbleListView replaces QTextBrowser on the desktop.

Static analysis on the desktop sources to confirm:

  1. bubble_list_view.h declares the three Q_OBJECT classes
     (BubbleMessageModel, BubbleDelegate, BubbleListView) with the expected
     public surface — setStore, setBubblePalette, refresh, setSearchHighlight
     plus the messageContextMenuRequested + messageActivated signals.
  2. bubble_list_view.cpp paints a rounded bubble (drawRoundedRect), a
     gradient for outgoing bubbles (QLinearGradient), an avatar ellipse
     (drawEllipse) for peers, and emits the four tick glyphs.
  3. main.cpp:
     - includes app_desktop/bubble_list_view.h
     - holds messages_ as BubbleListView* (no longer QTextBrowser)
     - wires messageContextMenuRequested to a QMenu with the existing
       reply/forward/react/pin/unpin/edit/delete actions
     - render_store calls setStore + setBubblePalette + refresh +
       setSearchHighlight (no setHtml left as the primary view path)
  4. CMakeLists.txt registers bubble_list_view.cpp/.h on app_desktop and
     turns AUTOMOC on so Q_OBJECT generates moc_*.cpp.
  5. desktop_chat_store.h exposes current_user_id() (used by main.cpp to
     pass the user_id into the model).

Pure static — runs without Qt. The actual Qt build is verified by the
Windows CI job and the local build-local/.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
HEADER = REPO / "client" / "src" / "app_desktop" / "bubble_list_view.h"
SRC = REPO / "client" / "src" / "app_desktop" / "bubble_list_view.cpp"
MAIN = REPO / "client" / "src" / "app_desktop" / "main.cpp"
CMAKE = REPO / "client" / "src" / "CMakeLists.txt"
STORE_H = REPO / "client" / "src" / "app_desktop" / "desktop_chat_store.h"


def main() -> int:
    for p in (HEADER, SRC, MAIN, CMAKE, STORE_H):
        if not p.exists():
            print(f"[FAIL] missing {p}")
            return 1

    h = HEADER.read_text(encoding="utf-8")
    cpp = SRC.read_text(encoding="utf-8")
    main_cpp = MAIN.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")
    store_h = STORE_H.read_text(encoding="utf-8")

    print("[scenario] bubble_list_view.h declares 3 Q_OBJECT classes + signals")
    for cls in ("class BubbleMessageModel", "class BubbleDelegate", "class BubbleListView"):
        assert cls in h, f"{cls!r} not declared"
    # Q_OBJECT macro on each.
    q_obj_count = h.count("Q_OBJECT")
    assert q_obj_count >= 3, f"expected 3 Q_OBJECT macros, found {q_obj_count}"
    # Public API of BubbleListView.
    for member in ("setStore", "setBubblePalette", "refresh", "setSearchHighlight"):
        assert re.search(rf"void\s+{re.escape(member)}\b", h), \
            f"BubbleListView missing {member}()"
    # Signals.
    assert re.search(r"signals:[^}]*messageContextMenuRequested\s*\(", h, re.DOTALL), \
        "BubbleListView missing messageContextMenuRequested signal"
    assert re.search(r"signals:[^}]*messageActivated\s*\(", h, re.DOTALL), \
        "BubbleListView missing messageActivated signal"
    print(f"[ok ] 3 Q_OBJECT classes, public API + signals present")

    print("[scenario] bubble_list_view.cpp paints bubble + gradient + avatar + ticks")
    assert "drawRoundedRect" in cpp, "delegate must call drawRoundedRect for the bubble shape"
    assert "QLinearGradient" in cpp, "outgoing bubbles need a QLinearGradient"
    assert "drawEllipse" in cpp, "peer avatar requires drawEllipse"
    # Tick glyphs — encoded as UTF-8 escape sequences in the source.
    assert "\\xe2\\x8c\\x9b" in cpp, "missing ⌛ glyph (pending)"
    assert "\\xe2\\x9c\\x95" in cpp, "missing ✕ glyph (failed)"
    assert "\\xe2\\x9c\\x93" in cpp, "missing ✓ glyph (sent/read)"
    # Reply quote vertical bar.
    assert "fillRect" in cpp, "reply quote requires fillRect for the accent bar"
    # Reaction chip rendering.
    assert "drawRoundedRect" in cpp and "drawText" in cpp and "Qt::AlignCenter" in cpp, \
        "delegate must paint reaction chips + footer text alignments"
    print("[ok ] paint() uses rounded rect + gradient + ellipse + tick glyphs + chip layout")

    print("[scenario] main.cpp swaps QTextBrowser for BubbleListView")
    assert "#include \"app_desktop/bubble_list_view.h\"" in main_cpp, \
        "main.cpp must include the new header"
    # The member declaration must be BubbleListView*.
    assert "BubbleListView* messages_" in main_cpp, \
        "messages_ must be declared as BubbleListView*"
    # No QTextBrowser usage left for the primary view.
    assert "new QTextBrowser" not in main_cpp, \
        "main.cpp still constructs a QTextBrowser — should be BubbleListView"
    assert "messages_->setHtml(" not in main_cpp, \
        "messages_->setHtml(...) is gone — render_store should drive the bubble view"
    # render_store wires through the new API.
    assert "messages_->setStore(" in main_cpp, "render_store must call setStore"
    assert "messages_->setBubblePalette(" in main_cpp, "render_store must call setBubblePalette"
    assert "messages_->refresh()" in main_cpp, "render_store must call refresh()"
    assert "messages_->setSearchHighlight(" in main_cpp, \
        "render_store must call setSearchHighlight"
    print("[ok ] BubbleListView wired in main.cpp; render_store drives setStore + palette + refresh")

    print("[scenario] right-click context menu wires reply/forward/react/pin/edit/delete")
    assert "messageContextMenuRequested" in main_cpp, \
        "main.cpp must subscribe to messageContextMenuRequested"
    # Each action is invoked from the menu.
    for entry in ("reply_message", "forward_message", "react_to_message",
                  "pin_message(true)", "pin_message(false)",
                  "edit_message_action", "delete_message_action"):
        assert entry in main_cpp, f"context menu missing wiring to {entry}"
    print("[ok ] context menu invokes all 7 message actions")

    print("[scenario] CMake registers bubble_list_view sources + AUTOMOC ON")
    assert "app_desktop/bubble_list_view.cpp" in cmake, \
        "qt_add_executable must list bubble_list_view.cpp"
    assert "app_desktop/bubble_list_view.h" in cmake, \
        "qt_add_executable must list bubble_list_view.h (so AUTOMOC scans it)"
    assert re.search(r"set_target_properties\s*\(\s*app_desktop\s+PROPERTIES[^)]*AUTOMOC\s+ON",
                     cmake, re.DOTALL), \
        "app_desktop must have AUTOMOC ON"
    print("[ok ] CMake target updated + AUTOMOC enabled")

    print("[scenario] DesktopChatStore exposes current_user_id() for the model")
    assert re.search(r"const\s+std::string&\s+current_user_id\s*\(\s*\)\s*const", store_h), \
        "DesktopChatStore must expose `const std::string& current_user_id() const`"
    print("[ok ] current_user_id() public getter present")

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
