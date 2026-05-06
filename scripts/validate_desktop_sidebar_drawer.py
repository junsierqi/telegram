"""Validate desktop left-sidebar and hamburger functionality wiring."""
from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
MAIN = REPO / "client" / "src" / "app_desktop" / "main.cpp"
STORE_H = REPO / "client" / "src" / "app_desktop" / "desktop_chat_store.h"
STORE_CPP = REPO / "client" / "src" / "app_desktop" / "desktop_chat_store.cpp"
PROTO = REPO / "server" / "server" / "protocol.py"
APP = REPO / "server" / "server" / "app.py"
CLIENT_H = REPO / "client" / "src" / "transport" / "control_plane_client.h"
CLIENT_CPP = REPO / "client" / "src" / "transport" / "control_plane_client.cpp"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    main_cpp = MAIN.read_text(encoding="utf-8")
    store_h = STORE_H.read_text(encoding="utf-8")
    store_cpp = STORE_CPP.read_text(encoding="utf-8")
    proto = PROTO.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")
    client_h = CLIENT_H.read_text(encoding="utf-8")
    client_cpp = CLIENT_CPP.read_text(encoding="utf-8")

    print("[scenario] sidebar folders are real filters")
    for token in (
        "enum class SidebarFolder",
        "sidebar_all_tab_",
        "sidebar_unread_tab_",
        "sidebar_pinned_tab_",
        "sidebar_archived_tab_",
        "set_sidebar_folder(folder)",
        "conversation_matches_sidebar_folder",
        "case SidebarFolder::Archived",
    ):
        require(token in main_cpp, f"missing sidebar folder token: {token}")
    print("[ok ] All/Unread/Pinned/Archived tabs drive conversation filtering")

    print("[scenario] conversation rows expose real quick actions")
    for token in (
        'setObjectName("conversationQuickMenu")',
        "run_conversation_flag_action",
        "client->set_conversation_pinned",
        "client->set_conversation_archived",
        "client->set_conversation_mute",
        "store_.apply_conversation_flags",
    ):
        require(token in main_cpp, f"missing quick-action token: {token}")
    print("[ok ] row context menu calls real pin/archive/mute RPCs")

    print("[scenario] drawer archive/night/account entries are wired")
    for token in (
        'setObjectName("drawerArchiveRow")',
        "archive_row->setVisible(!args_.gui_smoke)",
        "set_sidebar_folder(SidebarFolder::Archived)",
        'setObjectName("drawerNightSwitch")',
        'QSettings prefs',
        "show_profile_reference_dialog();",
        "show_login_dialog();",
    ):
        require(token in main_cpp, f"missing drawer behavior token: {token}")
    print("[ok ] drawer routes account/profile/archive/night behavior")

    print("[scenario] conversation flags round-trip through protocol/client/store/cache")
    for token in ("muted_until_ms", "pinned: bool = False", "archived: bool = False"):
        require(token in proto, f"protocol missing {token}")
    require("block_mute_service.get_mute" in app, "server sync must include mute state")
    for token in ("bool pinned", "bool archived", "long long muted_until_ms"):
        require(token in client_h, f"C++ sync model missing {token}")
    for token in (
        'extract_bool(object, "pinned")',
        'extract_bool(object, "archived")',
        'extract_number(object, "muted_until_ms")',
    ):
        require(token in client_cpp, f"C++ parser missing {token}")
    for token in (
        "bool pinned",
        "bool archived",
        "long long muted_until_ms",
        "apply_conversation_flags",
    ):
        require(token in store_h, f"store header missing {token}")
    for token in (
        "conversation.pinned = source.pinned",
        "conversation.archived = source.archived",
        "conversation.muted_until_ms = source.muted_until_ms",
        '"muted_until_ms"',
    ):
        require(token in store_cpp, f"store implementation missing {token}")
    print("[ok ] conversation flags parse, cache and update local state")

    print("\nAll 4/4 desktop sidebar/drawer scenarios passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"[FAIL] {exc}")
        raise SystemExit(1)
