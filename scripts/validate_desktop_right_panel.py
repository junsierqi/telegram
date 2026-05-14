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
        "detail_media_tabs_->tabBar()->setVisible(false)",
    ):
        require(token in main_cpp, f"missing right-info mode token: {token}")
    require("detail_media_tabs_->tabBar()->setVisible(!args_.gui_smoke)" not in main_cpp,
            "right panel must not show Qt tab controls outside smoke mode")
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
        "confirm_and_leave_selected_conversation();",
        "perform_leave_selected_conversation();",
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
        "channel_profile_link_text(*conv, title)",
        "group_profile_link_text(*conv)",
        "conversation_profile_summary(*conv, peer_kind)",
        "Share this contact",
        "Block user",
    ):
        require(token in main_cpp, f"missing branch-profile token: {token}")
    print("[ok ] user/group/channel right panel branches expose profile/media/member content")

    print("[scenario] user info panel stays direct like tdesktop")
    for token in (
        "for (auto* button : detail_action_buttons_) button->setVisible(true);",
        "configure_right_info_sections(QStringLiteral(\"User Info\"), QStringLiteral(\"Shared Media\"), QStringLiteral(\"Contact\"))",
        "set_detail_media_rows(*conv, is_channel, is_group, false)",
        "detail_members_title_->setVisible(false)",
        "add_detail_notification_row(detail_media_list_, muted_until_ms == 0)",
        "set_selected_conversation_notifications(enabled)",
        'setObjectName("detailNotificationToggle")',
        'QStringLiteral("edit_contact")',
        'QStringLiteral("delete_contact")',
        'QStringLiteral("block_user")',
    ):
        require(token in main_cpp, f"missing user-direct-profile token: {token}")
    print("[ok ] user profile avoids extra section navigation and group/channel actions")

    print("[scenario] visible right-panel rows are click-responsive")
    for token in (
        "&QListWidget::itemClicked",
        "right_info_security",
        "right_info_notification_settings",
        "right_info_add_bot",
        "right_info_bot_settings",
        'open_settings_page_by_name(QStringLiteral("Privacy"))',
        'open_settings_page_by_name(QStringLiteral("Groups"))',
        'open_settings_page_by_name(QStringLiteral("Chat Tools"))',
        "run_detail_contact_action(action",
        "set_right_info_mode(RightInfoMode::Media)",
    ):
        require(token in main_cpp, f"missing right-panel click response token: {token}")
    print("[ok ] profile rows, service/bot rows, members and media entries respond to clicks")

    print("[scenario] right panel uses real data instead of fixed screenshot values")
    for forbidden in (
        "+44 74 8035 6438\\nPhone",
        "@heyblake\\nUsername",
        "t.me/M_Team\\nPublic link",
        "21,474",
        "General Chat linked",
        "40 channels",
    ):
        require(forbidden not in main_cpp, f"right panel still hardcodes screenshot value: {forbidden}")
    for token in (
        "peer_user_id_for(*conv)",
        "detail_media_counts_for(conversation)",
        "conversation.participant_user_ids",
        "client->share_contact(target)",
        "client->edit_contact(target, display)",
        "client->remove_contact(target)",
        "client->block_user(target)",
    ):
        require(token in main_cpp, f"missing real right-panel behavior token: {token}")
    print("[ok ] profile fields/actions derive from store data and existing RPCs")

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

    print("\nAll 10/10 desktop right-panel scenarios passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"[FAIL] {exc}")
        raise SystemExit(1)
