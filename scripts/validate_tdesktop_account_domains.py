from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402


def login(app: ServerApplication) -> dict:
    response = app.dispatch(
        {
            **make_envelope(MessageType.LOGIN_REQUEST, correlation_id="login", sequence=1),
            "payload": {"username": "alice", "password": "alice_pw", "device_id": "dev_alice_win"},
        }
    )
    assert response["type"] == "login_response", response
    return response["payload"]


def dispatch(app: ServerApplication, session: dict, msg_type: MessageType, payload: dict, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                msg_type,
                correlation_id=f"acc_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": payload,
        }
    )


def scenario_account_settings_roundtrip() -> None:
    print("[scenario] settings notification/privacy/security/proxy fields persist")
    app = ServerApplication()
    alice = login(app)
    updated = dispatch(
        app,
        alice,
        MessageType.ACCOUNT_SETTINGS_UPDATE_REQUEST,
        {
            "notifications_enabled": False,
            "message_preview_enabled": False,
            "who_can_add_to_groups": "contacts",
            "phone_number_visibility": "nobody",
            "two_step_verification_enabled": True,
            "passcode_lock_enabled": True,
            "proxy_mode": "custom",
            "proxy_host": "127.0.0.1",
            "proxy_port": 1080,
            "proxy_secret": "secret",
        },
        2,
    )
    assert updated["type"] == "account_settings_response", updated
    assert updated["payload"]["notifications_enabled"] is False, updated
    assert updated["payload"]["phone_number_visibility"] == "nobody", updated
    assert updated["payload"]["proxy_host"] == "127.0.0.1", updated
    fetched = dispatch(app, alice, MessageType.ACCOUNT_SETTINGS_GET_REQUEST, {}, 3)
    assert fetched["payload"] == updated["payload"], fetched
    print("[ok ] account settings persist and fetch through backend")


def scenario_account_features_roundtrip() -> None:
    print("[scenario] premium/wallet/stories/emoji/gift feature state is real")
    app = ServerApplication()
    alice = login(app)
    initial = dispatch(app, alice, MessageType.ACCOUNT_FEATURES_GET_REQUEST, {}, 4)
    assert initial["type"] == "account_features_response", initial
    update = dispatch(
        app,
        alice,
        MessageType.ACCOUNT_FEATURES_UPDATE_REQUEST,
        {
            "emoji_status": "star",
            "story_title": "Desktop Story",
            "story_text": "hello",
            "gift_title": "Telegram Gift",
            "gift_recipient_user_id": "u_bob",
        },
        5,
    )
    assert update["type"] == "account_features_response", update
    assert update["payload"]["emoji_status"] == "star", update
    assert update["payload"]["stories_count"] == 1, update
    assert update["payload"]["last_story_title"] == "Desktop Story", update
    assert update["payload"]["last_gift_title"] == "Telegram Gift", update
    fetched = dispatch(app, alice, MessageType.ACCOUNT_FEATURES_GET_REQUEST, {}, 6)
    assert fetched["payload"] == update["payload"], fetched
    print("[ok ] account feature domains persist and fetch through backend")


def main() -> int:
    scenario_account_settings_roundtrip()
    scenario_account_features_roundtrip()
    print("\nAll 2/2 tdesktop account-domain scenarios passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
