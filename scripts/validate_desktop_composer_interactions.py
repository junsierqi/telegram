"""Static validator for desktop composer interaction parity.

Locks P1 composer behavior that is not fully covered by backend smokes:
send-as state, compact composer status, emoji/sticker preview and recent
tokens, and preservation of the existing silent/scheduled send paths.
"""
from __future__ import annotations

import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
MAIN = REPO / "client" / "src" / "app_desktop" / "main.cpp"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    main_cpp = MAIN.read_text(encoding="utf-8")

    print("[scenario] send-as menu owns selectable identity state")
    for token in (
        "send_as_identity_",
        "send_as_label_",
        "set_send_as_identity",
        "update_send_as_button",
        "action->setCheckable(true)",
        "action->setChecked(send_as_identity_ == key)",
        '"Channel identity"',
        '"Group identity"',
    ):
        require(token in main_cpp, f"missing send-as state token: {token}")
    print("[ok ] send-as selection is retained in desktop UI state")

    print("[scenario] composer status label reflects active mode")
    for token in (
        'setObjectName("composerStatusLabel")',
        "composer_status_label_",
        "refresh_composer_status",
        "composer_reply_mode_",
        '"Send as "',
        "composer_status_label_->setVisible(!parts.isEmpty())",
    ):
        require(token in main_cpp, f"missing composer status token: {token}")
    print("[ok ] composer status line is wired")

    print("[scenario] emoji/sticker panel has preview and recent tokens")
    for token in (
        'setObjectName("emojiStickerPanel")',
        'setObjectName("emojiStickerPreview")',
        '"emojiRecentGrid"',
        "recent_composer_tokens_",
        "remember_recent_composer_token",
        "insert_composer_token",
        "composer_->insert(token)",
        "while (recent_composer_tokens_.size() > 10)",
    ):
        require(token in main_cpp, f"missing emoji/recent token: {token}")
    print("[ok ] emoji/sticker panel tracks recent selections")

    print("[scenario] send options remain real send paths")
    for token in (
        '"Send without sound"',
        '"Schedule message"',
        "send_message(true)",
        "send_message(false, scheduled_at_ms)",
        "client->send_message(conversation, text, silent, scheduled_at_ms)",
    ):
        require(token in main_cpp, f"missing send option token: {token}")
    print("[ok ] silent/scheduled sends still route through backend RPC")

    print("\nAll 4/4 desktop composer interaction scenarios passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"[FAIL] {exc}")
        raise SystemExit(1)
