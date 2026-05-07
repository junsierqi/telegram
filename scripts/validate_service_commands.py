"""Validate service/bot command handling through the control plane."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402
from server.server.state import ConversationRecord  # noqa: E402


def login(app: ServerApplication) -> dict:
    return app.dispatch(
        {
            **make_envelope(MessageType.LOGIN_REQUEST, correlation_id="login"),
            "payload": {
                "username": "alice",
                "password": "alice_pw",
                "device_id": "dev_alice_win",
            },
        }
    )["payload"]


def command(app: ServerApplication, session: dict, value: str, seq: int = 2) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.SERVICE_COMMAND,
                correlation_id=f"svc_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {
                "conversation_id": "service_telegram",
                "command": value,
            },
        }
    )


def sync(app: ServerApplication, session: dict, seq: int = 20) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.CONVERSATION_SYNC,
                correlation_id=f"sync_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {},
        }
    )


def main() -> int:
    app = ServerApplication()
    session = login(app)
    app.state.conversations["service_telegram"] = ConversationRecord(
        conversation_id="service_telegram",
        participant_user_ids=[session["user_id"]],
        title="Telegram",
    )

    print("[scenario] /start command returns official service response")
    response = command(app, session, "/start")
    assert response["type"] == "message_deliver", response
    payload = response["payload"]
    assert payload["sender_user_id"] == "telegram", payload
    assert "Use /help" in payload["text"], payload
    messages = app.state.conversations["service_telegram"].messages
    assert messages[-2]["text"] == "/start", messages
    assert messages[-1]["reply_to_message_id"] == messages[-2]["message_id"], messages
    print("[ok ] service command stores user command and official reply")

    print("[scenario] /help and /security are supported")
    help_response = command(app, session, "/help", 3)
    security_response = command(app, session, "/security", 4)
    assert "Available commands" in help_response["payload"]["text"], help_response
    assert "Security alerts" in security_response["payload"]["text"], security_response
    print("[ok ] built-in service commands return deterministic replies")

    print("[scenario] unknown command is handled inside service conversation")
    unknown = command(app, session, "/unknown", 5)
    assert unknown["type"] == "message_deliver", unknown
    assert "Unknown service command" in unknown["payload"]["text"], unknown
    print("[ok ] unknown service commands produce guidance instead of errors")

    print("[scenario] empty service command is rejected")
    empty = command(app, session, "   ", 6)
    assert empty["type"] == "error", empty
    assert empty["payload"]["code"] == "empty_message", empty
    print("[ok ] empty commands return the existing empty_message error")

    print("[scenario] service command history appears in conversation sync")
    synced = sync(app, session)
    conversations = synced["payload"]["conversations"]
    service = next(c for c in conversations if c["conversation_id"] == "service_telegram")
    texts = [m["text"] for m in service["messages"]]
    assert "/start" in texts and "/security" in texts, texts
    assert any(m["sender_user_id"] == "telegram" for m in service["messages"]), service
    print("[ok ] sync exposes command and service reply history")

    print("\nAll 5/5 service command scenarios passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
