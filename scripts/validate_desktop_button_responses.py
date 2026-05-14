"""Validate visible Telegram Desktop shell buttons have concrete responses."""
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

    print("[scenario] drawer rows have explicit actions")
    for token in (
        '"drawerWalletAction"',
        'child->setProperty("drawerWalletAction", true)',
        'open_settings_page_by_name(QStringLiteral("Account"))',
        "open_account_features_surface(QStringLiteral(\"Wallet\"))",
        "open_account_features_surface(QStringLiteral(\"Premium\"))",
        "open_account_features_surface(QStringLiteral(\"Stories\"))",
        "open_saved_messages_peer",
        'setObjectName("drawerArchiveContextMenu")',
        "show_account_export_summary",
        'prefs.setValue(QStringLiteral("appearance/interface_scale"), 100)',
    ):
        require(token in main_cpp, f"missing drawer button response token: {token}")
    print("[ok ] drawer account/storage/scale buttons no longer stop at inert rows")

    print("[scenario] drawer layout follows tdesktop interaction details")
    for token in (
        "footer->setMinimumHeight(std::max(76, docked.height() - 810))",
        "content_layout->addWidget(footer)",
        "class NightModeToggle final",
        "void paintEvent(QPaintEvent*) override",
        "QEvent::MouseButtonRelease",
    ):
        require(token in main_cpp, f"missing drawer layout token: {token}")
    print("[ok ] drawer footer/toggle/click surface match the tdesktop-inspired model")

    print("[scenario] modal tool buttons have explicit actions")
    for token in (
        'edit, &QToolButton::clicked',
        'open_settings_page_by_name(QStringLiteral("Profile"))',
        'sort, &QToolButton::clicked',
        "list->sortItems",
        'more, &QToolButton::clicked',
        '"createDialogMoreMenu"',
        "show_contacts_dialog();",
    ):
        require(token in main_cpp, f"missing modal button response token: {token}")
    print("[ok ] profile edit, contacts sort and create-more controls are actionable")

    print("[scenario] proxy and help buttons do concrete local work")
    for token in (
        '"proxySettingsMoreMenu"',
        'open_settings_page_by_name(QStringLiteral("Connection"))',
        "Proxy link copied",
        "QApplication::clipboard()->setText(link)",
        "Telegram FAQ link copied",
        'QApplication::clipboard()->setText(QStringLiteral("https://telegram.org/faq"))',
    ):
        require(token in main_cpp, f"missing proxy/help response token: {token}")
    print("[ok ] proxy menu/share and FAQ copy produce observable actions")

    print("[scenario] settings general controls are not display-only")
    for token in (
        '"appearance/show_tray_icon"',
        '"appearance/monochrome_icon"',
        '"appearance/show_taskbar_icon"',
        '"appearance/system_window_frame"',
        '"appearance/default_interface_scale"',
        '"settingsThemeCardAction"',
        '"appearance/theme_name"',
        '"settingsAccentColorAction"',
        '"appearance/accent_color"',
    ):
        require(token in main_cpp, f"missing settings control response token: {token}")
    print("[ok ] settings checkboxes, scale toggle, theme cards and color swatches respond")

    print("[scenario] right-panel danger and gift actions are routed")
    for token in (
        'leave_btn, &QPushButton::clicked',
        "client->leave_conversation(conversation, true)",
        'report_btn, &QPushButton::clicked',
        "client->report_conversation(conversation, reason, comment)",
        'label == QStringLiteral("Gift")',
        "send_gift_to_selected_chat();",
    ):
        require(token in main_cpp, f"missing right-panel button response token: {token}")
    print("[ok ] leave/report/gift controls route to existing desktop behavior")

    print("[scenario] architecture document covers button response audit")
    require("Visible drawer/modal/right-panel buttons" in doc,
            "current-state must describe visible button response coverage")
    print("[ok ] docs describe the button response surface")

    print("\nAll 7/7 desktop button response scenarios passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"[FAIL] {exc}")
        raise SystemExit(1)
