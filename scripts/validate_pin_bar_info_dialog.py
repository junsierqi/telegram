"""Validator for M144 + M145 — pin message top bar + chat info dialog.

Static analysis on client/src/app_desktop/main.cpp confirming:

  M144 — Pin message top bar
    - QPushButton* pin_bar_ member with QString pin_bar_target_id_.
    - The bar is constructed in the central layout above the bubble view
      (`messages_`), starts hidden, and uses Qt::PointingHandCursor.
    - render_store() finds the first non-deleted pinned message in the
      selected conversation, fills the bar's text with sender + snippet,
      themes background/border via active palette tokens, and toggles
      visibility based on whether anything is pinned.
    - Click handler routes through messages_->setSearchHighlight(...,
      pin_bar_target_id_) so the bubble scrolls to + outlines the
      pinned message.

  M145 — Chat info dialog
    - QToolButton* chat_info_btn_ in the chat header is the overflow menu,
      while details_toggle_btn_ owns the always-visible right-info toggle.
    - The overflow menu exposes "Chat info" and invokes
      show_chat_info_dialog() which constructs a
      WA_DeleteOnClose QDialog populated from store_.selected_conversation()
      with: title + participant count, members QListWidget, pinned
      messages QListWidget, attachment count + sync version footer.

Pure static — runs without Qt.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
MAIN = REPO / "client" / "src" / "app_desktop" / "main.cpp"


def main() -> int:
    if not MAIN.exists():
        print(f"[FAIL] missing {MAIN}")
        return 1
    m = MAIN.read_text(encoding="utf-8")

    print("[scenario] M144 — pin_bar_ widget declared + constructed + visible-by-need")
    assert "QPushButton* pin_bar_" in m, "pin_bar_ member missing"
    assert "QString pin_bar_target_id_" in m, "pin_bar_target_id_ member missing"
    assert 'pin_bar_->setObjectName("pinBar")' in m, "pin_bar_ must have objectName 'pinBar'"
    assert "pin_bar_->setVisible(false)" in m, "pin_bar_ must start hidden"
    assert "Qt::PointingHandCursor" in m, "pin_bar_ should use the hand cursor"
    # Inserted into the center layout BEFORE the bubble list.
    pin_idx = m.find("center_layout->addWidget(pin_bar_)")
    bubble_idx = m.find("center_layout->addWidget(messages_, 1)")
    assert 0 <= pin_idx < bubble_idx, "pin_bar_ must be inserted above messages_ in center_layout"
    print("[ok ] pin_bar_ declared, hidden, inserted above bubble view")

    print("[scenario] M144 — render_store fills the bar from the first pinned message")
    rs_match = re.search(r"void\s+render_store\s*\(\s*\)\s*\{(?P<body>.*?)\n\s{4}\}", m, re.DOTALL)
    assert rs_match, "render_store body not found"
    rs = rs_match.group("body")
    assert "pin_bar_" in rs, "render_store must touch pin_bar_"
    assert "selected_conversation()" in rs, "render_store must read the selected conversation"
    assert ".pinned" in rs and ".deleted" in rs, "render_store must filter pinned + non-deleted"
    assert "pin_bar_->setVisible(true)" in rs, "render_store must show the bar when pinned exists"
    assert "pin_bar_->setVisible(false)" in rs, "render_store must hide the bar when nothing pinned"
    assert "pin_bar_target_id_" in rs, "render_store must record the target message id"
    # Theme tokens flow through.
    assert "t.surface_muted" in rs and "t.text_primary" in rs, \
        "render_store must theme the pin bar background + text"
    print("[ok ] render_store keeps pin_bar_ in sync with the conversation snapshot")

    print("[scenario] M144 — click jumps to the pinned message via setSearchHighlight")
    click_match = re.search(
        r"QObject::connect\s*\(\s*pin_bar_\s*,[^}]+messages_->setSearchHighlight",
        m, re.DOTALL,
    )
    assert click_match, "pin_bar_ click must call messages_->setSearchHighlight"
    print("[ok ] pin_bar_ click routes through setSearchHighlight")

    print("[scenario] M145 — chat_info_btn_ in header + show_chat_info_dialog wired")
    assert "QToolButton* chat_info_btn_" in m, "chat_info_btn_ member missing"
    assert 'chat_info_btn_->setObjectName("chatInfoBtn")' in m, "chat_info_btn_ object name"
    assert "QToolButton* details_toggle_btn_" in m, "details_toggle_btn_ member missing"
    assert 'details_toggle_btn_->setToolTip(QStringLiteral("Show or hide info panel"))' in m, \
        "split-panel info toggle tooltip missing"
    assert 'chat_info_btn_->setToolTip(QStringLiteral("More"))' in m, \
        "overflow menu tooltip missing"
    assert 'menu.addAction("Chat info", [this] { show_chat_info_dialog(); });' in m, \
        "overflow menu must expose the legacy Chat info dialog"
    assert "QObject::connect(details_toggle_btn_, &QToolButton::clicked" in m, \
        "details toggle must be clickable"
    print("[ok ] header overflow + split-panel info controls wired")

    print("[scenario] M145 — show_chat_info_dialog populates 4 sections")
    body_match = re.search(
        r"void\s+show_chat_info_dialog\s*\(\s*\)\s*\{(?P<body>.*?)\n\s{4}\}",
        m, re.DOTALL,
    )
    assert body_match, "show_chat_info_dialog body not found"
    body = body_match.group("body")
    assert "WA_DeleteOnClose" in body, "dialog must auto-clean via WA_DeleteOnClose"
    assert "selected_conversation()" in body, "dialog must read selected_conversation()"
    # Sections: title, members, pinned, attachment count.
    assert "participant_user_ids" in body, "dialog must list participants"
    assert "Pinned" in body and "pinned" in body, "dialog must show pinned messages section"
    assert "Attachments" in body or "attachment_count" in body, \
        "dialog must show attachment count summary"
    assert "sync_version" in body, "dialog footer should expose sync version"
    print("[ok ] dialog assembles title + members + pinned + attachment summary")

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
