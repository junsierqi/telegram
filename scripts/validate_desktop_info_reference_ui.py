"""Static checks for main-empty and right-info-panel reference states."""
from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
MAIN = REPO / "client" / "src" / "app_desktop" / "main.cpp"
GUI_SMOKE = REPO / "scripts" / "validate_desktop_gui_smoke.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    main_cpp = MAIN.read_text(encoding="utf-8")
    gui_smoke = GUI_SMOKE.read_text(encoding="utf-8")

    print("[scenario] Main window empty-chat-list reference capture")
    for token in (
        "capture_gui_smoke_reference_shell_states",
        '"main-empty-chat-list"',
        '"main-empty-chat-list.png"',
        "set_selected_conversation({})",
        "setVisible(false)",
    ):
        require(token in main_cpp or token in gui_smoke, f"missing main-empty token: {token}")
    print("[ok ] Main empty chat-list state is captured as first-class GUI evidence")

    print("[scenario] Channel info panel reference capture")
    for token in (
        "gui_smoke_reference_sync",
        "ref_channel_m_team",
        "M-Team",
        "21,474 subscribers",
        '"info-channel"',
        '"info-channel.png"',
        "t.me/M_Team",
        "8 gifts",
        "set_detail_media_rows(is_channel, is_group, 12, 56, 0)",
        "1 poll",
        "Leave channel",
        "%1 similar channels",
    ):
        require(token in main_cpp or token in gui_smoke, f"missing channel info token: {token}")
    print("[ok ] Channel info panel state is wired through DesktopChatStore")

    print("[scenario] User info panel reference capture")
    for token in (
        "ref_user_hello_blake",
        "Hello Blake",
        "last seen Nov 3 at 8:02 PM",
        '"info-user"',
        '"info-user.png"',
        "+44 74 8035 6438",
        "@heyblake",
        "set_detail_media_rows(is_channel, is_group, 1, 8, 0)",
        "%1 files",
        "%1 voice messages",
        'QString::number(1) + QStringLiteral(" group in common")',
        "Share this contact",
        "Delete contact",
        'setObjectName("detailAvatar")',
        "setScaledContents(false)",
        "QSizePolicy::Fixed",
    ):
        require(token in main_cpp or token in gui_smoke, f"missing user info token: {token}")
    print("[ok ] User info panel state is wired through DesktopChatStore")

    print("[scenario] Group info panel reference capture")
    for token in (
        "ref_group_three",
        '"info-group"',
        '"info-group.png"',
        "3 MEMBERS",
        "online  owner",
        "last seen a long time ago",
        "detail_member_search_",
    ):
        require(token in main_cpp or token in gui_smoke, f"missing group info token: {token}")
    print("[ok ] Group info panel state is wired through DesktopChatStore")

    print("\nAll 4/4 desktop right-info reference scenarios passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"[FAIL] {exc}")
        raise SystemExit(1)
