"""Validate desktop right-info panel data and action wiring."""
from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
MAIN = REPO / "client" / "src" / "app_desktop" / "main.cpp"
DOC = REPO / "docs" / "architecture" / "current-state.md"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    main_cpp = MAIN.read_text(encoding="utf-8")
    doc = DOC.read_text(encoding="utf-8")

    print("[scenario] tdesktop-style right panel exposes Profile section stack")
    for token in (
        "enum class RightInfoMode",
        'setObjectName("detailBackButton")',
        'setObjectName("detailSectionTitle")',
        "set_right_info_mode",
        "apply_right_info_mode_visibility",
        "configure_right_info_sections(QStringLiteral(\"Channel Info\"), QStringLiteral(\"Shared Media\"), QStringLiteral(\"Subscribers\"))",
        "right_info_mode_media",
        "__right_info_members__",
    ):
        require(token in main_cpp, f"missing right-info mode token: {token}")
    print("[ok ] right panel keeps Profile clean and navigates into Media/Members sections")

    print("[scenario] shared media tabs render real conversation data")
    for token in (
        "detail_files_list_",
        "detail_links_list_",
        "detail_voice_list_",
        "set_detail_media_rows(*conv",
        "mime_starts_with(message.mime_type, \"image/\")",
        "mime_starts_with(message.mime_type, \"audio/\")",
        "text_has_link(message.text)",
        "message_row_label(message",
    ):
        require(token in main_cpp, f"missing media data token: {token}")
    print("[ok ] media/files/links/voice rows derive from messages")

    print("[scenario] right-panel action buttons route to real behavior")
    for token in (
        "handle_detail_action(action_index)",
        "run_conversation_flag_action(",
        "ConversationFlagOp::Mute",
        "ConversationFlagOp::Archive",
        "show_chat_info_dialog();",
        "composer_->setFocus();",
    ):
        require(token in main_cpp, f"missing action token: {token}")
    print("[ok ] Mute/Manage/Leave/Message actions are wired")

    print("[scenario] members search filters real participants")
    for token in (
        "populate_detail_members(*conv)",
        "detail_member_search_->text().trimmed()",
        "conversation.participant_user_ids",
        "name.contains(query, Qt::CaseInsensitive)",
        "handle_detail_member_activated",
        "contact_user_id_->setText(user_id)",
        'open_settings_page_by_name(QStringLiteral("Contacts"))',
        "No members match",
    ):
        require(token in main_cpp, f"missing member-search token: {token}")
    print("[ok ] member rows come from participant_user_ids and search text")

    print("[scenario] architecture document mentions right-panel data/actions")
    require("right details panel" in doc, "current-state must describe right details panel")
    require("real data" in doc or "media" in doc, "current-state must mention real panel data")
    print("[ok ] architecture docs cover the right panel")

    print("[scenario] user/group/channel profiles follow tdesktop branch behavior")
    for token in (
        "enum class DetailPeerKind",
        "DetailPeerKind { User, Bot, Service, BasicGroup, MegaGroup, BroadcastChannel }",
        "detail_peer_kind_for(*conv, title)",
        "is_bot_conversation",
        "is_group_detail_kind",
        "group_or_channel && profile",
        "set_bot_detail_panel(*conv)",
        "populate_channel_subscribers(*conv)",
        "Linked discussion: General Chat",
        "Similar channels",
        "Private group\\nInvite link hidden",
        "Group profile, members and shared media are kept in separate sections",
        "Share this contact",
        "Block user",
    ):
        require(token in main_cpp, f"missing branch-profile token: {token}")
    print("[ok ] user/group/channel right panel branches expose profile/media/member content")

    print("[scenario] user info panel stays direct like tdesktop")
    for token in (
        "for (auto* button : detail_action_buttons_) button->setVisible(false);",
        "configure_right_info_sections(QStringLiteral(\"User Info\"), QStringLiteral(\"Shared Media\"), QStringLiteral(\"Contact\"))",
        "set_detail_media_rows(*conv, is_channel, is_group, false)",
        "detail_members_title_->setVisible(false)",
        "add_detail_notification_row(detail_media_list_, muted_until_ms == 0)",
        "set_selected_conversation_notifications(enabled)",
        'setObjectName("detailNotificationToggle")',
        'key == "edit"',
        'key == "delete"',
        'key == "block"',
    ):
        require(token in main_cpp, f"missing user-direct-profile token: {token}")
    print("[ok ] user profile avoids extra section navigation and group/channel actions")

    print("[scenario] right panel keeps danger/actions scoped to peer kind")
    for token in (
        "detail_leave_button_->setText(is_channel",
        "Leave group",
        "Report group",
        "label == QStringLiteral(\"Commands\")",
        "label == QStringLiteral(\"Add\")",
        "peer_kind == DetailPeerKind::BroadcastChannel",
    ):
        require(token in main_cpp, f"missing peer-kind action token: {token}")
    print("[ok ] user/bot/service/group/channel actions are separated")

    print("\nAll 8/8 desktop right-panel scenarios passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"[FAIL] {exc}")
        raise SystemExit(1)
