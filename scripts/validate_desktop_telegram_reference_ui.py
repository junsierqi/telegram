"""Static checks for the Telegram Desktop screenshot-parity shell.

The validator keeps the visual-parity slice honest without requiring a GUI:

- conversation list uses a custom delegate with avatar/title/snippet/time/unread roles
- sidebar exposes the hamburger button, rounded Search field, and birthday banner
- center chat surface hides developer-only advanced panels by default
- composer/header controls use Telegram-style icon buttons/placeholders
- light chat background uses the green Telegram-like wash from the references
- right details panel is a live profile/channel/group summary, not the settings form
- hamburger opens a Telegram-style account drawer
- Settings opens a centered modal matching the reference settings screen
- GUI smoke mode exists to exercise drawer/settings/profile interactions in app_desktop itself
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
MAIN = REPO / "client" / "src" / "app_desktop" / "main.cpp"
TOKENS = REPO / "client" / "src" / "app_desktop" / "design_tokens.h"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    main_cpp = MAIN.read_text(encoding="utf-8")
    tokens = TOKENS.read_text(encoding="utf-8")

    print("[scenario] custom Telegram-style conversation row delegate")
    require("class ChatListDelegate final" in main_cpp, "ChatListDelegate is missing")
    for role in ("ChatTitleRole", "ChatSnippetRole", "ChatTimeRole", "ChatUnreadRole", "ChatAvatarSeedRole"):
        require(role in main_cpp, f"{role} must be defined and populated")
    require("setItemDelegate(new ChatListDelegate" in main_cpp, "chat list must use ChatListDelegate")
    require("drawEllipse(avatar)" in main_cpp, "delegate must paint circular avatars")
    require("drawRoundedRect(badgeRect" in main_cpp, "delegate must paint unread badges")
    print("[ok ] avatar/title/snippet/time/unread delegate is wired")

    print("[scenario] reference sidebar shell")
    require('setObjectName("hamburgerButton")' in main_cpp, "hamburger menu button missing")
    require('setObjectName("sidebarSearchInput")' in main_cpp, "rounded sidebar search input missing")
    require('setObjectName("birthdayBanner")' in main_cpp, "birthday banner missing")
    require('setPlaceholderText("Search")' in main_cpp, "search placeholder should match reference")
    print("[ok ] hamburger, search pill, and birthday banner are present")

    print("[scenario] center chat surface and composer polish")
    require('setPlaceholderText("Write a message...")' in main_cpp, "composer placeholder mismatch")
    require('message_search_results_->setVisible(false)' in main_cpp, "server search panel should be hidden by default")
    require('message_action_wrap->setVisible(false)' in main_cpp, "advanced message action strip should be hidden by default")
    require('transfer_wrap->setVisible(false)' in main_cpp, "transfer debug strip should be hidden by default")
    require("qlineargradient(x1:0,y1:0,x2:1,y2:1" in main_cpp, "chat surface gradient missing")
    require('"#d9e7bd"' in tokens, "light chat_area token should use Telegram-like green wash")
    print("[ok ] chat area and composer match the screenshot direction")

    print("[scenario] right-side details panel is available like the reference")
    require("details_panel_->setVisible(true)" in main_cpp, "right details panel should be visible by default")
    require('details_toggle_btn_->setToolTip(QStringLiteral("Show or hide info panel"))' in main_cpp,
            "header must expose a dedicated right info panel toggle")
    require("QObject::connect(details_toggle_btn_, &QToolButton::clicked" in main_cpp,
            "right info panel toggle must be clickable")
    require("QToolButton#hamburgerButton, QToolButton#chatInfoBtn" in main_cpp, "icon toolbutton styling missing")
    require("QStatusBar" in main_cpp and "max-height:0px" in main_cpp, "status bar should not consume visible screenshot space")
    print("[ok ] details panel and chrome styling are wired")

    print("[scenario] 1:1 right profile/channel/group summary panel")
    require("details_stack_" in main_cpp, "details panel must use a stack so info and legacy settings are separated")
    for token in ("profileDetailsPage", "detailAvatar", "detailTitle", "detailSubtitle",
                  "detailLink", "detailMediaRows", "detailMembers"):
        require(token in main_cpp, f"{token} missing from details profile page")
    require("void update_details_profile_panel()" in main_cpp, "details profile page must be refreshed from selected chat")
    require("update_details_profile_panel();" in main_cpp, "render_store must refresh the details profile panel")
    require("setToolButtonStyle(Qt::ToolButtonTextUnderIcon)" in main_cpp,
            "right panel action buttons should use Telegram-like icon-over-text layout")
    require("set_detail_media_rows" in main_cpp and "QListWidgetItem(line_icon(icon_key" in main_cpp,
            "right panel media rows must use drawn line icons instead of rich-text glyph rows")
    for token in ("set_detail_action_texts", "CONTACT ACTIONS", "Share this contact", "MEMBERS",
                  "Leave channel", "Report"):
        require(token in main_cpp, f"typed right info panel content missing: {token}")
    print("[ok ] right panel has live chat/contact/channel summary content")

    print("[scenario] screenshot #4 hamburger account drawer")
    require("void show_account_drawer()" in main_cpp, "account drawer function missing")
    require('setObjectName("accountDrawer")' in main_cpp, "account drawer object name missing")
    for label in ("My Profile", "Wallet", "New Group", "New Channel", "Contacts",
                  "Calls", "Saved Messages", "Settings", "Night Mode"):
        require(label in main_cpp, f"drawer row missing: {label}")
    require("QIcon line_icon" in main_cpp, "single-color drawn line icon helper missing")
    require('add_row("profile", "My Profile")' in main_cpp,
            "drawer rows must use drawn line icons instead of emoji text prefixes")
    require("QPropertyAnimation(dlg, \"geometry\", dlg)" in main_cpp, "drawer must slide with geometry animation")
    require("[this] { show_account_drawer(); }" in main_cpp, "hamburger must open the account drawer")
    require("focusChanged" in main_cpp and "close_drawer" in main_cpp, "drawer must close from outside focus/row interactions")
    print("[ok ] hamburger opens a Telegram-like left account drawer")

    print("[scenario] screenshot #5 centered settings modal")
    require("void show_settings_dialog()" in main_cpp, "settings modal function missing")
    require('setObjectName("settingsModal")' in main_cpp, "settings modal object name missing")
    for label in ("My Account", "Notifications and Sounds", "Privacy and Security", "Chat Settings",
                  "Folders", "Advanced", "Speakers and Camera", "Battery and Animations",
                  "Language", "Default interface scale", "Telegram Premium", "My Stars"):
        require(label in main_cpp, f"settings modal row missing: {label}")
    require('add_settings_row("bell", "Notifications and Sounds")' in main_cpp,
            "settings modal rows must use drawn line icons instead of emoji text prefixes")
    require("QSlider(Qt::Horizontal)" in main_cpp, "settings modal must include interface scale slider")
    require("show_settings_dialog();" in main_cpp, "settings drawer row must open centered settings dialog")
    print("[ok ] settings opens as a Telegram-style centered modal")

    print("[scenario] contacts flow uses Telegram-style modal backed by real RPCs")
    require("void show_contacts_dialog()" in main_cpp, "contacts modal function missing")
    require('setObjectName("contactsModal")' in main_cpp, "contacts modal object name missing")
    require('setObjectName("contactsSearchInput")' in main_cpp, "contacts modal search/add input missing")
    require("client->list_contacts()" in main_cpp and "client->add_contact(user_id)" in main_cpp,
            "contacts modal must use real contact RPCs")
    require('target.rfind("u_", 0) != 0' in main_cpp and "client->search_users(target, 1)" in main_cpp,
            "contacts modal should resolve usernames/display names before add_contact")
    require("--smoke-two-client-flow" in main_cpp, "desktop binary must expose two-client real-backend smoke")
    two_client = REPO / "scripts" / "validate_desktop_two_client_flow.py"
    require(two_client.exists(), "two-client backend flow validator missing")
    require("--smoke-two-client-flow" in two_client.read_text(encoding="utf-8"),
            "two-client validator must run the desktop binary flow")
    print("[ok ] contacts modal and real two-client flow validator are wired")

    print("[scenario] startup uses real login/network state instead of mock chat data")
    require('std::string conversation;' in main_cpp,
            "desktop GUI must not default into conv_alice_bob on startup")
    require('std::string user;' in main_cpp and 'std::string password;' in main_cpp,
            "desktop GUI login form must not ship with Alice/Bob test credentials prefilled")
    gui_smoke_start = main_cpp.find("static transport::SyncResult gui_smoke_reference_sync()")
    gui_smoke_end = main_cpp.find("bool capture_gui_smoke_reference_shell_states()", gui_smoke_start)
    runtime_main_cpp = main_cpp
    if gui_smoke_start >= 0 and gui_smoke_end > gui_smoke_start:
        runtime_main_cpp = main_cpp[:gui_smoke_start] + main_cpp[gui_smoke_end:]
    hello_pos = runtime_main_cpp.find("Hello Blake")
    if hello_pos >= 0:
        nearby = runtime_main_cpp[max(0, hello_pos - 260):hello_pos + 260]
        require("args_.gui_smoke" in nearby,
                "screenshot-only contact aliases must not appear in runtime UI")
    for fake_text in ('t.me/example', 'XZMQ   online   owner', 'last seen 3/31/2025',
                      '40 similar channels', '4 files', '4 voice messages',
                      '1 group in common'):
        require(fake_text not in main_cpp, f"runtime UI must not contain screenshot/mock data: {fake_text}")
    require('remembered.setValue(QStringLiteral("auth/remembered"), true)' in main_cpp,
            "successful login must persist a remembered login marker")
    require("has_remembered_login_" in main_cpp and "connecting_" in main_cpp,
            "startup must model remembered-login reconnect/loading state")
    require('setObjectName("connectionNotice")' in main_cpp and "last_connection_error_" in main_cpp,
            "remembered-login connection failure must show an in-window no-network notice")
    require('setObjectName("reconnectIndicator")' in main_cpp and "Waiting for network" in main_cpp,
            "remembered-login no-network state should mirror reference-25 with a sidebar loading indicator")
    require("void show_login_dialog()" in main_cpp and 'setObjectName("loginModal")' in main_cpp,
            "first-run startup must show a Telegram-style login prompt")
    require("QTimer::singleShot(180, this, [this] { show_login_dialog(); })" in main_cpp,
            "first-run login prompt should open automatically")
    require("Use the login prompt to connect" in main_cpp and "Log in to start messaging" in main_cpp,
            "logged-out startup must visibly explain how to log in")
    require("login_dialog_->accept();" in main_cpp and "login_status_->setText(qstr(\"Connection failed: \" + message))" in main_cpp,
            "login modal must wait for real server auth result instead of closing immediately")
    login_dialog_body = main_cpp[main_cpp.find("void show_login_dialog()"):main_cpp.find("void show_contacts_dialog()")]
    require("dlg->accept();" not in login_dialog_body,
            "login button must not close the modal before server login/register succeeds")
    bubble_cpp = (REPO / "client" / "src" / "app_desktop" / "bubble_list_view.cpp").read_text(encoding="utf-8")
    bubble_h = (REPO / "client" / "src" / "app_desktop" / "bubble_list_view.h").read_text(encoding="utf-8")
    require("setEmptyStateText" in bubble_cpp and "Select a chat to start messaging" in bubble_h,
            "center pane must show Telegram-style empty-chat prompt")
    print("[ok ] startup no longer opens a fake/default contact conversation")

    print("[scenario] New Group/New Channel/Search/Attachment use Telegram-style entry points")
    for token in ('setObjectName("newGroupModal")', 'setObjectName("newChannelModal")',
                  'setObjectName("searchResultsModal")', 'setObjectName("searchResultsList")',
                  'setObjectName("telegramCreateInput")'):
        require(token in main_cpp, f"Telegram-style interaction modal missing: {token}")
    require("void show_conversation_create_dialog(bool channel_mode)" in main_cpp,
            "New Group/New Channel must open a Telegram-style create dialog")
    require("client->create_conversation(ids, title)" in main_cpp,
            "create dialogs must use the real conversation RPC")
    require("show_search_results_dialog(chat_filter_->text().trimmed())" in main_cpp,
            "sidebar search should open the Telegram-style search results surface")
    require("menu.addAction(line_icon(\"photo\"" in main_cpp and "Save Received File" in main_cpp,
            "attachment button must open a Telegram-style attachment menu")
    print("[ok ] primary interaction entry points moved out of debug controls")

    print("[scenario] pixel-parity wallpaper and executable GUI smoke")
    require("paintTelegramDoodleWallpaper" in (REPO / "client" / "src" / "app_desktop" / "bubble_list_view.cpp").read_text(encoding="utf-8"),
            "BubbleListView must paint Telegram doodle wallpaper")
    require("--gui-smoke" in main_cpp, "app_desktop must expose --gui-smoke")
    require("run_gui_interaction_smoke" in main_cpp, "GUI interaction smoke method missing")
    require("hamburger_button_->click()" in main_cpp, "GUI smoke must actually click the hamburger button")
    require("details_toggle_btn_->click()" in main_cpp, "GUI smoke must exercise right info panel toggle")
    require("drawerSettingsButton" in main_cpp and "settings->click()" in main_cpp,
            "GUI smoke must actually click drawer Settings")
    for shot in (
        "main-window",
        "account-drawer",
        "side-menu-overlay",
        "side-menu-empty-scrolled",
        "service-chat",
        "channel-pinned-unread",
        "profile-modal",
        "new-group-dialog",
        "new-channel-dialog",
        "contacts-dialog",
        "logined-no-network",
        "settings-modal",
    ):
        require(shot in main_cpp, f"GUI smoke must save {shot} screenshot")
    for token in ("desktop gui smoke ok", "account drawer did not open", "settings modal did not open"):
        require(token in main_cpp, f"GUI smoke marker missing: {token}")
    diff_script = (REPO / "scripts" / "validate_desktop_image_diff.py").read_text(encoding="utf-8")
    require("def read_png" in diff_script and "def diff_images" in diff_script,
            "pixel diff validator must decode and compare PNGs")
    gui_smoke = (REPO / "scripts" / "validate_desktop_gui_smoke.py").read_text(encoding="utf-8")
    require("validate_desktop_image_diff.py" in gui_smoke,
            "GUI smoke validator must run pixel diff after screenshots")
    print("[ok ] doodle wallpaper and executable GUI smoke are wired")

    print("\nAll 11/11 desktop reference UI scenarios passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"[FAIL] {exc}")
        raise SystemExit(1)
