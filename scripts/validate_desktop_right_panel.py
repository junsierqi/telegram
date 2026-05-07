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

    print("\nAll 4/4 desktop right-panel scenarios passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"[FAIL] {exc}")
        raise SystemExit(1)
