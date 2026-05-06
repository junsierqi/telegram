"""Validate P0-M1 composer RPC semantics.

Covers Telegram-like send options now exposed by the desktop composer:
silent sends suppress offline push notifications while still delivering,
and scheduled sends stay hidden from sync until their due timestamp.
"""
from __future__ import annotations

import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402


def _login(app: ServerApplication, user: str, password: str, device: str, seq: int) -> dict:
    resp = app.dispatch({
        **make_envelope(MessageType.LOGIN_REQUEST, correlation_id=f"corr_login_{seq}", sequence=seq),
        "payload": {"username": user, "password": password, "device_id": device},
    })
    assert resp["type"] == "login_response", resp
    return resp["payload"]


def _send(app: ServerApplication, session: dict, payload: dict, seq: int) -> dict:
    return app.dispatch({
        **make_envelope(
            MessageType.MESSAGE_SEND,
            correlation_id=f"corr_send_{seq}",
            session_id=session["session_id"],
            actor_user_id=session["user_id"],
            sequence=seq,
        ),
        "payload": payload,
    })


def _sync(app: ServerApplication, session: dict, seq: int) -> dict:
    return app.dispatch({
        **make_envelope(
            MessageType.CONVERSATION_SYNC,
            correlation_id=f"corr_sync_{seq}",
            session_id=session["session_id"],
            actor_user_id=session["user_id"],
            sequence=seq,
        ),
        "payload": {},
    })


def _texts(sync: dict, conversation_id: str) -> list[str]:
    conversations = sync["payload"]["conversations"]
    for conversation in conversations:
        if conversation["conversation_id"] == conversation_id:
            return [message["text"] for message in conversation["messages"]]
    return []


def scenario_silent_send_suppresses_offline_push() -> None:
    print("[scenario] silent MESSAGE_SEND delivers but skips offline push")
    app = ServerApplication(presence_ttl_seconds=5.0)
    bob = _login(app, "bob", "bob_pw", "dev_bob", 1)
    app.dispatch({
        **make_envelope(
            MessageType.PUSH_TOKEN_REGISTER,
            correlation_id="corr_push_register",
            session_id=bob["session_id"],
            actor_user_id=bob["user_id"],
            sequence=2,
        ),
        "payload": {"platform": "fcm", "token": "token_bob"},
    })
    del app.state.sessions[bob["session_id"]]
    alice = _login(app, "alice", "alice_pw", "dev_alice", 3)
    app.push_token_service.drain_pending()
    resp = _send(app, alice, {
        "conversation_id": "conv_alice_bob",
        "text": "silent ping",
        "silent": True,
    }, 4)
    assert resp["type"] == "message_deliver", resp
    assert resp["payload"]["silent"] is True, resp
    assert app.push_token_service.drain_pending() == []
    print("[ok ] silent field round-trips and offline notification is suppressed")


def scenario_scheduled_send_hidden_until_due() -> None:
    print("[scenario] scheduled MESSAGE_SEND is hidden until release_due_scheduled")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice", 1)
    now = int(time.time() * 1000)
    due = now + 60_000
    resp = _send(app, alice, {
        "conversation_id": "conv_alice_bob",
        "text": "future ping",
        "scheduled_at_ms": due,
    }, 2)
    assert resp["type"] == "message_deliver", resp
    assert resp["payload"]["scheduled"] is True, resp
    assert resp["payload"]["scheduled_at_ms"] == due, resp
    assert "future ping" not in _texts(_sync(app, alice, 3), "conv_alice_bob")
    app.chat_service.release_due_scheduled(now_ms=due)
    assert "future ping" in _texts(_sync(app, alice, 4), "conv_alice_bob")
    print("[ok ] future message is hidden, then visible after due release")


def main() -> int:
    scenario_silent_send_suppresses_offline_push()
    scenario_scheduled_send_hidden_until_due()
    print("\nAll 2/2 composer scheduled/silent scenarios passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
