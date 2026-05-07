"""Cross-client tdesktop account-domain parity checks.

Static coverage for the current Mobile Qt Quick + browser slice:
- mobile bridge exposes account settings/features RPCs and result signals.
- mobile Settings/Profile QML routes settings, emoji status, stories and gifts.
- browser right panel exposes account settings/features, shared media paging
  and message action RPCs over the WebSocket bridge.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MOBILE = REPO / "client" / "src" / "app_mobile"
WEB = REPO / "server" / "web"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assert_tokens(text: str, tokens: tuple[str, ...], label: str) -> None:
    for token in tokens:
        assert token in text, f"{label} missing: {token}"


def scenario_mobile_bridge() -> None:
    print("[scenario] mobile bridge exposes account-domain RPCs")
    h = _read(MOBILE / "mobile_chat_bridge.h")
    cpp = _read(MOBILE / "mobile_chat_bridge.cpp")
    _assert_tokens(h, (
        "Q_INVOKABLE void refreshAccountSettings(",
        "Q_INVOKABLE void saveAccountSettings(",
        "Q_INVOKABLE void refreshAccountFeatures(",
        "Q_INVOKABLE void setEmojiStatus(",
        "Q_INVOKABLE void publishStory(",
        "Q_INVOKABLE void sendGift(",
        "void accountSettingsReady(",
        "void accountFeaturesReady(",
    ), "mobile bridge header")
    _assert_tokens(cpp, (
        "client->account_settings_get()",
        "client->account_settings_update(",
        "client->account_features_get()",
        "client->account_features_update(",
        "emit accountSettingsReady(",
        "emit accountFeaturesReady(",
    ), "mobile bridge implementation")


def scenario_mobile_qml() -> None:
    print("[scenario] mobile QML wires account settings/features controls")
    settings = _read(MOBILE / "qml" / "SettingsPage.qml")
    profile = _read(MOBILE / "qml" / "ProfilePage.qml")
    _assert_tokens(settings, (
        "ChatBridge.refreshAccountSettings()",
        "ChatBridge.saveAccountSettings(",
        "ChatBridge.refreshAccountFeatures()",
        "ChatBridge.setEmojiStatus(",
        "Telegram account settings",
        "Premium / Wallet / Stories",
    ), "mobile settings QML")
    _assert_tokens(profile, (
        "ChatBridge.refreshAccountFeatures()",
        "ChatBridge.setEmojiStatus(",
        "ChatBridge.publishStory(",
        "ChatBridge.sendGift(",
        "Stories and gifts",
    ), "mobile profile QML")


def scenario_browser_right_panel() -> None:
    print("[scenario] browser right panel exposes settings/features/shared-media UI")
    html = _read(WEB / "index.html")
    js = _read(WEB / "app.js")
    _assert_tokens(html, (
        'id="rightPanel"',
        'id="loadSharedMedia"',
        'id="saveWebSettings"',
        'id="saveEmojiStatus"',
        'id="publishWebStory"',
        'id="sendWebGift"',
    ), "browser HTML")
    _assert_tokens(js, (
        "account_settings_get_request",
        "account_settings_update_request",
        "account_features_get_request",
        "account_features_update_request",
        "shared_media_page_request",
        "message_reaction",
        "message_pin",
        "message_edit",
        "message_delete",
    ), "browser JavaScript")


def main() -> int:
    scenarios = (
        scenario_mobile_bridge,
        scenario_mobile_qml,
        scenario_browser_right_panel,
    )
    for fn in scenarios:
        fn()
    print(f"All {len(scenarios)}/{len(scenarios)} cross-client account parity scenarios passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
