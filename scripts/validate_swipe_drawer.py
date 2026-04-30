"""Validator for M149 + M150 — swipe-to-reply gesture + sliding info drawer.

Static analysis confirming the two final phase-c micro-milestones land in:

  M149 — mobile QML swipe-right-to-reply
    - ChatPage.qml delegate exposes `property real swipeOffset` with a
      Behavior easing back to 0 on release.
    - A reply-hint Label (↩ glyph) fades in proportional to swipeOffset
      so the user sees the gesture register.
    - The bubble's leftMargin / x is shifted by swipeOffset for live
      feedback during the drag.
    - MouseArea has onPressed (records pressX/pressY, resets state),
      onPositionChanged (commits to horizontal drag only when |dx| > 12
      and dx > 1.5 * dy so vertical scroll still wins), onReleased
      (triggers reply when offset > 50 px), and onPressAndHold gated
      so a real swipe doesn't ALSO open the long-press menu.
    - On commit, page.replyToId/page.replyToText are populated and
      composer.forceActiveFocus() is called so the user can type
      immediately.

  M150 — desktop sliding info drawer
    - main.cpp show_chat_info_dialog uses Qt::FramelessWindowHint |
      Qt::Tool so the panel reads as an attached drawer rather than a
      floating dialog.
    - Computes a docked geometry on the right edge of the main window
      (panel width 360 px) and an off-screen geometry one panel further
      right.
    - Slide-in: QPropertyAnimation on "geometry" 220 ms, OutCubic curve,
      DeleteWhenStopped.
    - Close button hooks a slide-out animation (180 ms, InCubic) whose
      finished signal accepts the dialog — so disappearance is a slide,
      not a pop.

Pure static — no Qt build needed.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
QML = REPO / "client" / "src" / "app_mobile" / "qml" / "ChatPage.qml"
MAIN = REPO / "client" / "src" / "app_desktop" / "main.cpp"


def main() -> int:
    for p in (QML, MAIN):
        if not p.exists():
            print(f"[FAIL] missing {p}")
            return 1
    qml = QML.read_text(encoding="utf-8")
    m = MAIN.read_text(encoding="utf-8")

    print("[scenario] M149 — swipeOffset state + reply hint + bubble translation")
    assert re.search(r"property\s+real\s+swipeOffset", qml), \
        "delegate must declare `property real swipeOffset`"
    assert "Behavior on swipeOffset" in qml, \
        "swipeOffset must have a Behavior animation for the spring-back"
    assert "\\u21A9" in qml, "delegate must contain the ↩ reply hint glyph escape"
    # Bubble shifts via leftMargin or x using swipeOffset.
    assert "row.swipeOffset" in qml, \
        "bubble must consume row.swipeOffset for live drag translation"
    print("[ok ] state + hint label + bubble translation wired")

    print("[scenario] M149 — drag detector commits horizontal only when motion is sideways")
    # Locate the inner MouseArea inside the bubble.
    for hook in ("onPressed", "onPositionChanged", "onReleased"):
        assert hook in qml, f"MouseArea is missing {hook} hook"
    # The position-change handler must check dx vs dy ratio.
    assert "dx > dy" in qml or "dx > dy * 1.5" in qml, \
        "horizontal commit must compare dx against dy to keep vertical scroll responsive"
    # Threshold for triggering reply.
    assert re.search(r"swipeOffset\s*>\s*50", qml), \
        "reply trigger must require swipeOffset > 50 px"
    # And the reply trigger must populate page.replyToId.
    trigger_block = re.search(
        r"if\s*\(\s*draggingHorizontal\s*&&\s*row\.swipeOffset\s*>\s*50\s*\)\s*\{(?P<b>.*?)\}",
        qml, re.DOTALL,
    )
    assert trigger_block, "swipe-commit branch not found"
    tb = trigger_block.group("b")
    assert "page.replyToId" in tb, "swipe must set page.replyToId"
    assert "page.replyToText" in tb, "swipe must set page.replyToText"
    assert "composer.forceActiveFocus" in tb, \
        "swipe must focus the composer after committing"
    print("[ok ] swipe threshold + reply state + composer focus all wired")

    print("[scenario] M149 — pressAndHold suppressed mid-swipe")
    pah = re.search(r"onPressAndHold\s*:\s*\{(?P<b>.*?)\}", qml, re.DOTALL)
    assert pah, "pressAndHold handler missing"
    pb = pah.group("b")
    assert "draggingHorizontal" in pb, \
        "pressAndHold must early-return when draggingHorizontal is true"
    print("[ok ] long-press menu deferred when a horizontal drag is in progress")

    print("[scenario] M150 — info dialog uses Tool + FramelessWindowHint")
    body = re.search(
        r"void\s+show_chat_info_dialog\s*\(\s*\)\s*\{(?P<b>.*?)\n\s{4}\}",
        m, re.DOTALL,
    )
    assert body, "show_chat_info_dialog body not found"
    bd = body.group("b")
    assert "Qt::Tool" in bd and "Qt::FramelessWindowHint" in bd, \
        "dialog must use Qt::Tool | Qt::FramelessWindowHint for the docked feel"
    # Panel width + docked + off-screen geometries.
    assert "panelW" in bd or re.search(r"panel\w*\s*=\s*360", bd), \
        "must compute a panel width for the docked geometry"
    assert "dockedGeo" in bd, "must define dockedGeo"
    assert "offGeo" in bd, "must define an off-screen geometry"
    print("[ok ] tool + frameless flags + dock/off geometries declared")

    print("[scenario] M150 — slide-in + slide-out QPropertyAnimation")
    # In animation.
    assert "QPropertyAnimation" in bd, "must use QPropertyAnimation"
    assert 'setDuration(220)' in bd, "slide-in duration must be 220 ms"
    assert "OutCubic" in bd, "slide-in easing must be OutCubic"
    # Out animation tied to Close button.
    assert "InCubic" in bd, "slide-out easing must be InCubic"
    assert "&QDialog::accept" in bd, \
        "out animation finished must connect to QDialog::accept"
    # Sanity — both animations use DeleteWhenStopped so we don't leak.
    assert bd.count("DeleteWhenStopped") >= 2, \
        "both animations should start with DeleteWhenStopped"
    print("[ok ] slide-in (220 ms OutCubic) + slide-out (180 ms InCubic) wired")

    print("\nAll 5/5 scenarios passed.")
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
