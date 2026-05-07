"""Static validator for desktop service/detail functionality parity.

Locks Telegram Desktop-style service/bot right-column variants, settings-row
routing, service commands, and shared-media row actions.
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

    print("[scenario] service/bot right panel has an independent branch")
    for token in (
        "is_service_conversation",
        "current_conversation_is_service",
        "set_service_detail_panel",
        '"detailServiceInfoSection"',
        '"detailServiceMediaSection"',
        "Official service",
        '"Notifications"',
        '"Security alerts"',
        '"serviceCommandSuggestionMenu"',
        "show_service_command_suggestions",
        'command + QStringLiteral("  Bot command")',
    ):
        require(token in main_cpp, f"missing service panel token: {token}")
    print("[ok ] service chats no longer reuse the generic user/channel branch")

    print("[scenario] settings modal rows route to real settings pages")
    for token in (
        "open_settings_page_by_name",
        '"settingsActionName"',
        '"settingsGeneralRowAction"',
        'open_settings_page_by_name("Appearance")',
        'open_settings_page_by_name("Connection")',
        'open_settings_page_by_name("Privacy")',
        'open_settings_page_by_name("Chat Tools")',
        'open_settings_page_by_name("Devices")',
        'open_settings_page_by_name("Contacts")',
        "show_proxy_settings_dialog()",
        'open_settings_page_by_name("Advanced")',
    ):
        require(token in main_cpp, f"missing settings routing token: {token}")
    print("[ok ] settings rows map into the existing settings stack")

    print("[scenario] shared media rows carry actionable data")
    for token in (
        "DetailRowKindRole",
        "DetailRowMessageIdRole",
        "DetailRowAttachmentIdRole",
        "DetailRowLinkRole",
        "DetailRowCommandRole",
        "handle_detail_row_activated",
        "show_detail_row_context_menu",
        '"detailRowContextMenu"',
        "QApplication::clipboard()->setText(link)",
        "attachment_id_->setText(attachment_id)",
        "messages_->setSearchHighlight(QString(), message_id)",
        "first_link_in_text",
        "run_service_command",
        "composer_->text().trimmed().startsWith(QLatin1Char('/'))",
        "client->service_command(conversation, command_text)",
        "Sending service command",
        "Service command sent",
        "service command failed",
        'QStringLiteral("/start")',
        'QStringLiteral("/help")',
        'QStringLiteral("/security")',
    ):
        require(token in main_cpp, f"missing shared media action token: {token}")
    print("[ok ] media/files/links/voice rows expose focus/copy/save selection behavior")

    print("[scenario] right info column follows tdesktop open/close sizing")
    for token in (
        "set_details_panel_visible",
        "adjust_window_for_details_panel",
        "availableGeometry()",
        "tdstyle::kColumnMinimalWidthThird",
        "tdstyle::kColumnMaximalWidthThird",
        "args_.gui_smoke",
        "setGeometry(next)",
    ):
        require(token in main_cpp, f"missing right-column sizing token: {token}")
    print("[ok ] right column open/close adjusts window width outside screenshot mode")

    print("\nAll 4/4 desktop service interaction scenarios passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"[FAIL] {exc}")
        raise SystemExit(1)
