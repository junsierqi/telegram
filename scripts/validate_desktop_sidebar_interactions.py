"""Static validator for desktop sidebar and drawer interactions.

Locks the P1 left-column behavior that sits above the existing protocol
validators: folder count visibility, row quick actions, mark-as-read, drawer
account expansion, archive count and animated night-mode toggle.
"""
from __future__ import annotations

import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
MAIN = REPO / "client" / "src" / "app_desktop" / "main.cpp"
STORE_H = REPO / "client" / "src" / "app_desktop" / "desktop_chat_store.h"
STORE_CPP = REPO / "client" / "src" / "app_desktop" / "desktop_chat_store.cpp"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    main_cpp = MAIN.read_text(encoding="utf-8")
    store_h = STORE_H.read_text(encoding="utf-8")
    store_cpp = STORE_CPP.read_text(encoding="utf-8")

    print("[scenario] folder tabs show live counts")
    for token in (
        "SidebarFolderCounts",
        "sidebar_folder_counts",
        "refresh_sidebar_folder_counts",
        "set_sidebar_folder_tab_text",
        'QStringLiteral("All")',
        'QStringLiteral("Archived")',
    ):
        require(token in main_cpp, f"missing folder count token: {token}")
    print("[ok ] folder tabs expose count state")

    print("[scenario] conversation row quick menu has tdesktop-style actions")
    for token in (
        'setObjectName("conversationQuickMenu")',
        'setObjectName("conversationFolderRouteMenu")',
        '"Show in folder"',
        '"Mark as read"',
        "run_mark_conversation_read",
        "client->mark_read(conversation_id, message_id)",
    ):
        require(token in main_cpp, f"missing row quick-action token: {token}")
    print("[ok ] row menu routes folder selection and mark-as-read")

    print("[scenario] local store can clear unread from mark-as-read")
    require("mark_conversation_read" in store_h, "store header missing mark_conversation_read")
    for token in (
        "conversation.unread_count = 0",
        "apply_read_marker(conversation_id, current_user_id_, message_id)",
    ):
        require(token in store_cpp, f"store implementation missing {token}")
    print("[ok ] store clears unread and updates the local read marker")

    print("[scenario] drawer account/archive/night details are wired")
    for token in (
        'setObjectName("drawerAccountSwitchRow")',
        "drawer_accounts_expanded_",
        "accounts->setVisible(drawer_accounts_expanded_)",
        "folder_counts.archived",
        'setObjectName("drawerNightAnimatedToggle")',
        "animated_night->setCheckable(true)",
        "night->setVisible(false)",
        "QSettings prefs",
    ):
        require(token in main_cpp, f"missing drawer interaction token: {token}")
    print("[ok ] drawer exposes account switch, archive count and animated night toggle")

    print("\nAll 4/4 desktop sidebar interaction scenarios passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"[FAIL] {exc}")
        raise SystemExit(1)
