"""Validator for REQ-MESSAGE-EDIT-DELETE (E7)."""
from __future__ import annotations

import sys
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
        for i, m in enumerate(self.messages):
            if m.get("type") == type_:
                return self.messages.pop(i)
        return None


def _login(app, username, password, device_id, seq):
    resp = app.dispatch(
        {
            **make_envelope(MessageType.LOGIN_REQUEST, correlation_id=f"corr_{username}", sequence=seq),
            "payload": {"username": username, "password": password, "device_id": device_id},
        }
    )
    return resp["payload"]


def _send(app, session, conv_id, text, seq):
    return app.dispatch(
        {
            **make_envelope(
                MessageType.MESSAGE_SEND, correlation_id=f"corr_send_{seq}",
                session_id=session["session_id"], actor_user_id=session["user_id"], sequence=seq,
            ),
            "payload": {"conversation_id": conv_id, "text": text},
        }
    )


def _edit(app, session, conv_id, message_id, new_text, seq, corr=None):
    return app.dispatch(
        {
            **make_envelope(
                MessageType.MESSAGE_EDIT, correlation_id=corr or f"corr_edit_{seq}",
                session_id=session["session_id"], actor_user_id=session["user_id"], sequence=seq,
            ),
            "payload": {"conversation_id": conv_id, "message_id": message_id, "text": new_text},
        }
    )


def _delete(app, session, conv_id, message_id, seq, corr=None):
    return app.dispatch(
        {
            **make_envelope(
                MessageType.MESSAGE_DELETE, correlation_id=corr or f"corr_delete_{seq}",
                session_id=session["session_id"], actor_user_id=session["user_id"], sequence=seq,
            ),
            "payload": {"conversation_id": conv_id, "message_id": message_id},
        }
    )


def test_edit_own_message_pushes_update() -> None:
    registry = ConnectionRegistry()
    alice_inbox = Inbox()
    bob_inbox = Inbox()
    app = ServerApplication(connection_registry=registry)
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    bob = _login(app, "bob", "bob_pw", "dev_bob_win", 2)
    registry.register(alice["session_id"], alice_inbox.writer)
    registry.register(bob["session_id"], bob_inbox.writer)

    sent = _send(app, alice, "conv_alice_bob", "halo", seq=3)
    mid = sent["payload"]["message_id"]
    # drain bob's inbox of the send push
    bob_inbox.pop_type("message_deliver")

    resp = _edit(app, alice, "conv_alice_bob", mid, "hello (fixed)", seq=4)
    assert resp["type"] == "message_edited"
    assert resp["payload"]["text"] == "hello (fixed)"
    assert resp["payload"]["edited"] is True

    # bob got a push, alice got only the response
    push = bob_inbox.pop_type("message_edited")
    assert push is not None and push["payload"]["text"] == "hello (fixed)"
    assert alice_inbox.pop_type("message_edited") is None

    # storage reflects edit
    msg = app.state.conversations["conv_alice_bob"].messages[-1]
    assert msg["text"] == "hello (fixed)"
    assert msg["edited"] is True


def test_edit_others_message_denied() -> None:
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    bob = _login(app, "bob", "bob_pw", "dev_bob_win", 2)
    sent = _send(app, alice, "conv_alice_bob", "mine", seq=3)
    mid = sent["payload"]["message_id"]

    resp = _edit(app, bob, "conv_alice_bob", mid, "mine too", seq=4, corr="corr_steal")
    assert resp["type"] == "error"
    assert resp["payload"]["code"] == "message_edit_denied"


def test_edit_empty_text_rejected() -> None:
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    _login(app, "bob", "bob_pw", "dev_bob_win", 2)
    sent = _send(app, alice, "conv_alice_bob", "x", seq=3)
    mid = sent["payload"]["message_id"]

    resp = _edit(app, alice, "conv_alice_bob", mid, "   ", seq=4, corr="corr_blank")
    assert resp["type"] == "error"
    assert resp["payload"]["code"] == "empty_message"


def test_delete_own_message_soft_deletes() -> None:
    registry = ConnectionRegistry()
    bob_inbox = Inbox()
    app = ServerApplication(connection_registry=registry)
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    bob = _login(app, "bob", "bob_pw", "dev_bob_win", 2)
    registry.register(bob["session_id"], bob_inbox.writer)

    sent = _send(app, alice, "conv_alice_bob", "secret", seq=3)
    mid = sent["payload"]["message_id"]
    bob_inbox.pop_type("message_deliver")

    resp = _delete(app, alice, "conv_alice_bob", mid, seq=4)
    assert resp["type"] == "message_deleted"
    assert resp["payload"]["deleted"] is True

    # bob receives push
    push = bob_inbox.pop_type("message_deleted")
    assert push is not None and push["payload"]["message_id"] == mid

    # storage: message stays (for id continuity) but text cleared + deleted=True
    msg = next(m for m in app.state.conversations["conv_alice_bob"].messages if m["message_id"] == mid)
    assert msg.get("deleted") is True
    assert msg["text"] == ""

    # Sync exposes deleted flag
    sync = app.dispatch(
        {
            **make_envelope(
                MessageType.CONVERSATION_SYNC, correlation_id="corr_sync",
                session_id=bob["session_id"], actor_user_id=bob["user_id"], sequence=5,
            ),
            "payload": {},
        }
    )
    conv = sync["payload"]["conversations"][0]
    soft = next(m for m in conv["messages"] if m["message_id"] == mid)
    assert soft["deleted"] is True and soft["text"] == ""


def test_delete_idempotency_rejected() -> None:
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    _login(app, "bob", "bob_pw", "dev_bob_win", 2)
    sent = _send(app, alice, "conv_alice_bob", "x", seq=3)
    mid = sent["payload"]["message_id"]
    _delete(app, alice, "conv_alice_bob", mid, seq=4)

    again = _delete(app, alice, "conv_alice_bob", mid, seq=5, corr="corr_again")
    assert again["type"] == "error"
    assert again["payload"]["code"] == "message_already_deleted"


def test_edit_after_delete_rejected() -> None:
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    _login(app, "bob", "bob_pw", "dev_bob_win", 2)
    sent = _send(app, alice, "conv_alice_bob", "x", seq=3)
    mid = sent["payload"]["message_id"]
    _delete(app, alice, "conv_alice_bob", mid, seq=4)

    resp = _edit(app, alice, "conv_alice_bob", mid, "revived", seq=5, corr="corr_revive")
    assert resp["type"] == "error"
    assert resp["payload"]["code"] == "message_already_deleted"


def test_delete_others_denied() -> None:
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    bob = _login(app, "bob", "bob_pw", "dev_bob_win", 2)
    sent = _send(app, alice, "conv_alice_bob", "x", seq=3)
    mid = sent["payload"]["message_id"]

    resp = _delete(app, bob, "conv_alice_bob", mid, seq=4, corr="corr_bobdel")
    assert resp["type"] == "error"
    assert resp["payload"]["code"] == "message_delete_denied"


def test_edit_unknown_message_rejected() -> None:
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    _login(app, "bob", "bob_pw", "dev_bob_win", 2)

    resp = _edit(app, alice, "conv_alice_bob", "msg_ghost", "noop", seq=3, corr="corr_ghost_edit")
    assert resp["type"] == "error"
    assert resp["payload"]["code"] == "unknown_message"


SCENARIOS = [
    ("edit_own_message_pushes_update", test_edit_own_message_pushes_update),
    ("edit_others_message_denied", test_edit_others_message_denied),
    ("edit_empty_text_rejected", test_edit_empty_text_rejected),
    ("delete_own_message_soft_deletes", test_delete_own_message_soft_deletes),
    ("delete_idempotency_rejected", test_delete_idempotency_rejected),
    ("edit_after_delete_rejected", test_edit_after_delete_rejected),
    ("delete_others_denied", test_delete_others_denied),
    ("edit_unknown_message_rejected", test_edit_unknown_message_rejected),
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
