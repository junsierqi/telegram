"""Validator for desktop-era message actions: replies, forwards, reactions and pins."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.connection_registry import ConnectionRegistry  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402


class Inbox:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    def writer(self, message: dict) -> None:
        self.messages.append(message)

    def pop_type(self, type_: str) -> dict | None:
        for i, message in enumerate(self.messages):
            if message.get("type") == type_:
                return self.messages.pop(i)
        return None


def login(app: ServerApplication, username: str, password: str, device_id: str, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(MessageType.LOGIN_REQUEST, correlation_id=f"corr_login_{username}", sequence=seq),
            "payload": {"username": username, "password": password, "device_id": device_id},
        }
    )["payload"]


def send(app: ServerApplication, session: dict, text: str, seq: int, reply_to: str = "") -> dict:
    payload = {"conversation_id": "conv_alice_bob", "text": text}
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    return app.dispatch(
        {
            **make_envelope(
                MessageType.MESSAGE_SEND,
                correlation_id=f"corr_send_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": payload,
        }
    )


def forward(app: ServerApplication, session: dict, source_message_id: str, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.MESSAGE_FORWARD,
                correlation_id=f"corr_forward_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {
                "source_conversation_id": "conv_alice_bob",
                "source_message_id": source_message_id,
                "target_conversation_id": "conv_alice_bob",
            },
        }
    )


def react(app: ServerApplication, session: dict, message_id: str, emoji: str, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.MESSAGE_REACTION,
                correlation_id=f"corr_react_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {"conversation_id": "conv_alice_bob", "message_id": message_id, "emoji": emoji},
        }
    )


def pin(app: ServerApplication, session: dict, message_id: str, pinned: bool, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.MESSAGE_PIN,
                correlation_id=f"corr_pin_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {"conversation_id": "conv_alice_bob", "message_id": message_id, "pinned": pinned},
        }
    )


def sync(app: ServerApplication, session: dict) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.CONVERSATION_SYNC,
                correlation_id="corr_sync",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=99,
            ),
            "payload": {},
        }
    )


def test_reply_forward_reaction_pin_push_and_sync() -> None:
    registry = ConnectionRegistry()
    bob_inbox = Inbox()
    app = ServerApplication(connection_registry=registry)
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    bob = login(app, "bob", "bob_pw", "dev_bob_win", 2)
    registry.register(bob["session_id"], bob_inbox.writer)

    base = send(app, alice, "message actions base", 3)
    base_id = base["payload"]["message_id"]
    bob_inbox.pop_type("message_deliver")

    reply = send(app, bob, "reply to base", 4, reply_to=base_id)
    assert reply["type"] == "message_deliver"
    assert reply["payload"]["reply_to_message_id"] == base_id

    forwarded = forward(app, alice, base_id, 5)
    assert forwarded["type"] == "message_deliver"
    assert forwarded["payload"]["forwarded_from_message_id"] == base_id
    assert forwarded["payload"]["forwarded_from_sender_user_id"] == "u_alice"
    assert bob_inbox.pop_type("message_deliver") is not None

    reaction = react(app, bob, base_id, "+1", 6)
    assert reaction["type"] == "message_reaction_updated"
    assert reaction["payload"]["reaction_summary"] == "+1:1"
    assert bob_inbox.pop_type("message_reaction_updated") is None

    pinned = pin(app, alice, base_id, True, 7)
    assert pinned["type"] == "message_pin_updated"
    assert pinned["payload"]["pinned"] is True
    pin_push = bob_inbox.pop_type("message_pin_updated")
    assert pin_push is not None and pin_push["payload"]["message_id"] == base_id

    synced = sync(app, alice)
    messages = synced["payload"]["conversations"][0]["messages"]
    base_msg = next(message for message in messages if message["message_id"] == base_id)
    reply_msg = next(message for message in messages if message["message_id"] == reply["payload"]["message_id"])
    fwd_msg = next(message for message in messages if message["message_id"] == forwarded["payload"]["message_id"])
    assert base_msg["reaction_summary"] == "+1:1"
    assert base_msg["pinned"] is True
    assert reply_msg["reply_to_message_id"] == base_id
    assert fwd_msg["forwarded_from_message_id"] == base_id


def test_reaction_toggle_and_pin_unpin() -> None:
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    base = send(app, alice, "toggle target", 2)
    base_id = base["payload"]["message_id"]

    first = react(app, alice, base_id, "+1", 3)
    assert first["payload"]["reaction_summary"] == "+1:1"
    second = react(app, alice, base_id, "+1", 4)
    assert second["payload"]["reaction_summary"] == ""

    on = pin(app, alice, base_id, True, 5)
    off = pin(app, alice, base_id, False, 6)
    assert on["payload"]["pinned"] is True
    assert off["payload"]["pinned"] is False


def test_reply_to_unknown_message_rejected() -> None:
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    response = send(app, alice, "bad reply", 2, reply_to="msg_missing")
    assert response["type"] == "error"
    assert response["payload"]["code"] == "unknown_message"


def test_sqlite_persists_message_action_metadata() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = str(Path(tmpdir) / "runtime.sqlite")
        app = ServerApplication(db_file=db_file)
        alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
        base = send(app, alice, "persistent action base", 2)
        base_id = base["payload"]["message_id"]
        reply = send(app, alice, "persistent reply", 3, reply_to=base_id)
        forwarded = forward(app, alice, base_id, 4)
        react(app, alice, base_id, "+1", 5)
        pin(app, alice, base_id, True, 6)

        restarted = ServerApplication(db_file=db_file)
        synced = sync(restarted, alice)
        messages = synced["payload"]["conversations"][0]["messages"]
        base_msg = next(message for message in messages if message["message_id"] == base_id)
        reply_msg = next(message for message in messages if message["message_id"] == reply["payload"]["message_id"])
        fwd_msg = next(message for message in messages if message["message_id"] == forwarded["payload"]["message_id"])
        assert base_msg["reaction_summary"] == "+1:1"
        assert base_msg["pinned"] is True
        assert reply_msg["reply_to_message_id"] == base_id
        assert fwd_msg["forwarded_from_message_id"] == base_id


SCENARIOS = [
    ("reply_forward_reaction_pin_push_and_sync", test_reply_forward_reaction_pin_push_and_sync),
    ("reaction_toggle_and_pin_unpin", test_reaction_toggle_and_pin_unpin),
    ("reply_to_unknown_message_rejected", test_reply_to_unknown_message_rejected),
    ("sqlite_persists_message_action_metadata", test_sqlite_persists_message_action_metadata),
]


def main() -> int:
    failures: list[str] = []
    for name, fn in SCENARIOS:
        try:
            fn()
            print(f"[ok ] {name}")
        except Exception as exc:
            failures.append(f"{name}: {exc}")
            print(f"[FAIL] {name}: {exc}")
    print(f"passed {len(SCENARIOS) - len(failures)}/{len(SCENARIOS)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
