"""Static validator for P1 desktop message interaction parity.

The runtime validators cover the transport actions. This script locks the
Telegram Desktop-style UI wiring that makes those actions reachable from the
message surface: hover action menu, quick reactions, attachment actions, and
inline composer edit mode.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
MAIN = REPO / "client" / "src" / "app_desktop" / "main.cpp"
BUBBLE_H = REPO / "client" / "src" / "app_desktop" / "bubble_list_view.h"
BUBBLE_CPP = REPO / "client" / "src" / "app_desktop" / "bubble_list_view.cpp"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    main_cpp = MAIN.read_text(encoding="utf-8")
    bubble_h = BUBBLE_H.read_text(encoding="utf-8")
    bubble_cpp = BUBBLE_CPP.read_text(encoding="utf-8")

    print("[scenario] hover action hit-test opens the message menu")
    for token in (
        "actionButtonRect",
        "viewport()->setCursor(Qt::PointingHandCursor)",
        "emit messageContextMenuRequested",
        "viewport()->mapToGlobal(actionRect.bottomRight())",
    ):
        require(token in bubble_h or token in bubble_cpp, f"missing hover action token: {token}")
    print("[ok ] bubble view exposes Telegram-like hover action menu entry")

    print("[scenario] quick reaction selector")
    require("add_quick_reaction_selector" in main_cpp, "message menu must use reaction selector helper")
    require('reaction_menu->setObjectName("reactionSelectorMenu")' in main_cpp,
            "reaction selector menu objectName missing")
    for token in ('"+1"', '"heart"', '"fire"', '"laugh"', '"sad"', '"Custom reaction..."'):
        require(token in main_cpp, f"reaction selector missing {token}")
    require("reaction_emoji_->setText(token)" in main_cpp and "react_to_message()" in main_cpp,
            "reaction selector must route chosen token to toggle_reaction")
    print("[ok ] quick reaction selector is wired to the existing reaction RPC")

    print("[scenario] attachment message actions")
    for token in (
        "attachment_id_for_message",
        '"Save Attachment"',
        '"Copy Attachment ID"',
        "QApplication::clipboard()->setText",
        "save_attachment()",
    ):
        require(token in main_cpp, f"attachment context action missing {token}")
    print("[ok ] attachment messages expose save/copy actions from the message menu")

    print("[scenario] inline composer edit mode")
    for token in (
        "composer_reply_mode_",
        'composer_reply_mode_ == QLatin1String("Edit")',
        "edit_message_action(composer_->text())",
        "message_full_text_for(message_id)",
        'statusBar()->showMessage("Editing " + message_id',
    ):
        require(token in main_cpp, f"inline edit mode missing {token}")
    edit_body = re.search(r"void edit_message_action\(.*?\n    \}", main_cpp, re.DOTALL)
    require(edit_body is not None and "hide_composer_reply_bar()" in edit_body.group(0),
            "edit submit must clear the composer reply/edit bar")
    print("[ok ] edit action now uses composer edit state instead of immediate modal-only flow")

    print("\nAll 4/4 desktop message interaction scenarios passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"[FAIL] {exc}")
        raise SystemExit(1)
