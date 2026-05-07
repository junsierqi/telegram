from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MAIN = ROOT / "client" / "src" / "app_desktop" / "main.cpp"
CLIENT_H = ROOT / "client" / "src" / "transport" / "control_plane_client.h"
CLIENT_CPP = ROOT / "client" / "src" / "transport" / "control_plane_client.cpp"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    main_cpp = MAIN.read_text(encoding="utf-8")
    client_h = CLIENT_H.read_text(encoding="utf-8")
    client_cpp = CLIENT_CPP.read_text(encoding="utf-8")

    print("[scenario] typed client exposes settings/features account domains")
    for token in (
        "AccountSettingsResult",
        "AccountFeaturesResult",
        "account_settings_get",
        "account_settings_update",
        "account_features_get",
        "account_features_update",
    ):
        require(token in client_h, f"missing client declaration: {token}")
    for token in (
        '"account_settings_get_request"',
        '"account_settings_update_request"',
        '"account_features_get_request"',
        '"account_features_update_request"',
    ):
        require(token in client_cpp, f"missing client wire token: {token}")
    print("[ok ] account-domain RPCs are wrapped by ControlPlaneClient")

    print("[scenario] desktop Settings and drawer/profile entries call backend")
    for token in (
        "sync_account_settings_to_backend",
        '"settingsBackendSyncButton"',
        "client->account_settings_update",
        "open_account_features_surface",
        "update_emoji_status_from_dialog",
        "publish_story_from_dialog",
        "send_gift_to_selected_chat",
        "client->account_features_get",
        "client->account_features_update",
        '"drawerEmojiStatusAction"',
    ):
        require(token in main_cpp, f"missing desktop account-domain token: {token}")
    require("Gift actions are represented by account storage" not in main_cpp,
            "Gift must no longer be a local account-storage placeholder")
    require("Wallet is represented by account storage" not in main_cpp,
            "Wallet must no longer be a local account-storage placeholder")
    print("[ok ] Settings/Gift/Wallet/Stories/Emoji Status are backend-routed")

    print("\nAll 2/2 desktop account-domain wiring scenarios passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"[FAIL] {exc}")
        raise SystemExit(1)
