"""Static validator for RC-004 desktop popup/menu states.

Checks the four popup surfaces that still matter for desktop parity:

- top overflow menu
- attachment menu
- emoji/sticker panel
- message context menu
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
MAIN = REPO / "client" / "src" / "app_desktop" / "main.cpp"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    m = MAIN.read_text(encoding="utf-8")

    print("[scenario] top overflow menu")
    require("chat_info_btn_" in m and 'setObjectName("chatInfoBtn")' in m,
            "chat overflow button missing")
    require('menu.setObjectName("topOverflowMenu")' in m, "top overflow menu objectName missing")
    require('menu.addAction(line_icon("search"' in m, "overflow menu must expose Search")
    require('menu.addAction(line_icon("profile"' in m and '"Chat info"' in m,
            "overflow menu must expose Chat info")
    require("configure_telegram_menu(&menu)" in m, "popup menus must use Telegram-like menu styling")
    require('"Hide Info" : "Show Info"' in m, "overflow menu must toggle info panel state")
    print("[ok ] top overflow menu is wired")

    print("[scenario] send options menu")
    require('menu.setObjectName("sendOptionsMenu")' in m, "send options menu objectName missing")
    require('"Send without sound"' in m and '"Schedule message"' in m,
            "send options menu must expose tdesktop-style send choices")
    require("customContextMenuRequested" in m, "send button must expose its options from right click")
    print("[ok ] send button exposes Telegram-style send options")

    print("[scenario] send-as identity menu")
    require('menu.setObjectName("sendAsMenu")' in m, "send-as menu objectName missing")
    require('"Personal account"' in m and '"Channel identity"' in m and '"Group identity"' in m,
            "send-as menu must expose identity choices")
    print("[ok ] send-as menu exposes identity choices")

    print("[scenario] attachment menu")
    require("QObject::connect(attach_, &QPushButton::clicked" in m,
            "attachment button click handler missing")
    require('menu.setObjectName("attachmentMenu")' in m, "attachment menu objectName missing")
    for token in ('menu.addAction(line_icon("photo"', '"Photo or Video"',
                  'menu.addAction(line_icon("files"', '"File"', '"Save Received File"'):
        require(token in m, f"attachment menu missing {token}")
    print("[ok ] attachment menu covers media, file and save")

    print("[scenario] emoji/sticker panel")
    require("emoji_panel_" in m and 'setObjectName("emojiStickerPanel")' in m,
            "emoji/sticker popup panel missing")
    require("show_emoji_sticker_panel()" in m, "emoji/sticker popup function missing")
    for token in ("QWidgetAction", "Emoji", "Stickers", "emojiGrid", "stickerGrid",
                  "[sticker:wave]", "[sticker:party]", "emojiGridButton",
                  "composer_->insert(token)"):
        require(token in m, f"emoji/sticker panel missing {token}")
    print("[ok ] emoji/sticker panel inserts composer tokens")

    print("[scenario] message context menu")
    body = re.search(r"messageContextMenuRequested(?P<body>.*?)menu\.exec\(globalPos\);", m, re.DOTALL)
    require(body is not None, "message context menu body missing")
    require('menu.setObjectName("messageContextMenu")' in body.group("body"),
            "message context menu objectName missing")
    require("can_modify_message" in body.group("body") and "setEnabled(can_modify)" in body.group("body"),
            "message context menu must disable edit/delete for non-owned/deleted messages")
    for label in ("Reply", "Forward", "React", "Pin", "Unpin", "Edit", "Delete"):
        require(f'"{label}"' in body.group("body") and "line_icon(" in body.group("body"),
                f"message context menu missing {label}")
    require("add_quick_reaction_selector(&menu, message_id)" in body.group("body"),
            "message context menu must expose quick reaction selector")
    require('"Save Attachment"' in body.group("body") and '"Copy Attachment ID"' in body.group("body"),
            "message context menu must expose attachment actions when available")
    print("[ok ] message context menu covers all message actions")

    print("\nAll 6/6 desktop popup-state scenarios passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"[FAIL] {exc}")
        raise SystemExit(1)
