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
    require('menu.addAction("Search"' in m, "overflow menu must expose Search")
    require('menu.addAction("Chat info", [this] { show_chat_info_dialog(); });' in m,
            "overflow menu must expose Chat info")
    require('"Hide Info" : "Show Info"' in m, "overflow menu must toggle info panel state")
    print("[ok ] top overflow menu is wired")

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
    for token in ("Emoji", "Stickers", "emojiGrid", "stickerGrid", "[sticker:wave]",
                  "[sticker:party]", "stickerWaveAction", "composer_->insert(token)"):
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
        require(f'menu.addAction("{label}"' in body.group("body"),
                f"message context menu missing {label}")
    print("[ok ] message context menu covers all message actions")

    print("\nAll 4/4 desktop popup-state scenarios passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"[FAIL] {exc}")
        raise SystemExit(1)
