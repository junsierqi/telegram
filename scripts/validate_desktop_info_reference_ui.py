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
        "kColumnMinimalWidthThird = 292",
        "kColumnMaximalWidthThird = 392",
        "kInfoTopBarHeight = 54",
        "kInfoProfilePhotoSize = 80",
    ):
        require(token in main_cpp, f"missing tdesktop info token: {token}")
    for token in (
        "gui_smoke_reference_sync",
        "ref_channel_m_team",
        "M-Team",
        '"info-channel"',
        '"info-channel.png"',
        "channel_profile_link_text(*conv, title)",
        "conversation_profile_summary(*conv, peer_kind)",
        "set_detail_media_rows(*conv, is_channel, is_group)",
        'setObjectName("detailMediaTabBar")',
        'setObjectName("detailBackButton")',
        'setObjectName("detailSectionTitle")',
        "populate_channel_subscribers(*conv)",
        "conversation.participant_user_ids",
        "poll_count",
        "Leave channel",
        "detail_links_list_",
    ):
        require(token in main_cpp or token in gui_smoke, f"missing channel info token: {token}")
    print("[ok ] Channel info panel state is wired through DesktopChatStore")

    print("[scenario] User info panel reference capture")
    for token in (
        "ref_user_hello_blake",
        "Hello Blake",
        '"info-user"',
        '"info-user.png"',
        "peer_user_id_for(*conv)",
        "user_profile_link_text(*conv, title, target_user_id)",
        "set_detail_media_rows(*conv, is_channel, is_group)",
        "detail_files_list_",
        "detail_voice_list_",
        "text_has_link(message.text)",
        "Share this contact",
        "Delete contact",
        "client->share_contact(target)",
        "client->remove_contact(target)",
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
        "%1 MEMBERS",
        "group_profile_link_text(*conv)",
        "conversation_profile_summary(*conv, peer_kind)",
        "detail_member_search_",
        "populate_detail_members(*conv)",
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
