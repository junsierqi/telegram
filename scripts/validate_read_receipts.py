"""Validator for REQ-READ-RECEIPTS (E6)."""
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
    assert resp["type"] == "login_response", resp
    return resp["payload"]


def _send_message(app, session, conv_id, text, seq):
    return app.dispatch(
        {
            **make_envelope(
                MessageType.MESSAGE_SEND,
                correlation_id=f"corr_msg_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {"conversation_id": conv_id, "text": text},
        }
    )


def _mark_read(app, session, conv_id, message_id, seq, corr=None):
    return app.dispatch(
        {
            **make_envelope(
                MessageType.MESSAGE_READ,
                correlation_id=corr or f"corr_read_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {"conversation_id": conv_id, "message_id": message_id},
        }
    )


def _sync(app, session, seq):
    return app.dispatch(
        {
            **make_envelope(
                MessageType.CONVERSATION_SYNC,
                correlation_id=f"corr_sync_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {},
        }
    )


def test_mark_read_advances_pointer_and_pushes() -> None:
    registry = ConnectionRegistry()
    alice_inbox = Inbox()
    bob_inbox = Inbox()

    app = ServerApplication(connection_registry=registry)
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    bob = _login(app, "bob", "bob_pw", "dev_bob_win", 2)
    registry.register(alice["session_id"], alice_inbox.writer)
    registry.register(bob["session_id"], bob_inbox.writer)

    m1 = _send_message(app, alice, "conv_alice_bob", "hello", seq=3)
    message_id = m1["payload"]["message_id"]

    # bob reads — response goes to bob, push goes to alice
    read_resp = _mark_read(app, bob, "conv_alice_bob", message_id, seq=4)
    assert read_resp["type"] == "message_read_update"
    assert read_resp["payload"]["reader_user_id"] == "u_bob"
    assert read_resp["payload"]["last_read_message_id"] == message_id

    push = alice_inbox.pop_type("message_read_update")
    assert push is not None, "alice did not receive read update"
    assert push["payload"]["reader_user_id"] == "u_bob"
    assert push["payload"]["last_read_message_id"] == message_id

    # bob should NOT receive an echoed push (he got the response)
    assert bob_inbox.pop_type("message_read_update") is None


def test_forward_only_advancement() -> None:
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    bob = _login(app, "bob", "bob_pw", "dev_bob_win", 2)

    m1 = _send_message(app, alice, "conv_alice_bob", "one", seq=3)
    m2 = _send_message(app, alice, "conv_alice_bob", "two", seq=4)
    m3 = _send_message(app, alice, "conv_alice_bob", "three", seq=5)

    # bob reads up to m3, then tries to mark m1 — pointer should NOT move backward
    _mark_read(app, bob, "conv_alice_bob", m3["payload"]["message_id"], seq=6)
    back = _mark_read(app, bob, "conv_alice_bob", m1["payload"]["message_id"], seq=7)
    assert back["type"] == "message_read_update"
    assert back["payload"]["last_read_message_id"] == m3["payload"]["message_id"]


def test_unknown_message_rejected() -> None:
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    bob = _login(app, "bob", "bob_pw", "dev_bob_win", 2)
    _send_message(app, alice, "conv_alice_bob", "hello", seq=3)

    resp = _mark_read(app, bob, "conv_alice_bob", "msg_999999", seq=4, corr="corr_ghost")
    assert resp["type"] == "error"
    assert resp["payload"]["code"] == "unknown_message"


def test_non_participant_denied() -> None:
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    _send_message(app, alice, "conv_alice_bob", "hi", seq=3)
    # register carol externally, put her in a separate conversation — NOT conv_alice_bob
    reg = app.dispatch(
        {
            **make_envelope(MessageType.REGISTER_REQUEST, correlation_id="corr_reg_carol", sequence=4),
            "payload": {
                "username": "carol", "password": "carol_pw_ok",
                "display_name": "Carol", "device_id": "dev_carol",
            },
        }
    )
    carol = reg["payload"]

    # carol tries to mark read a message in conv_alice_bob — access denied
    message_id = app.state.conversations["conv_alice_bob"].messages[-1]["message_id"]
    resp = _mark_read(app, carol, "conv_alice_bob", message_id, seq=5, corr="corr_carol_read")
    assert resp["type"] == "error"
    assert resp["payload"]["code"] == "conversation_access_denied"


def test_read_markers_in_conversation_sync() -> None:
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    bob = _login(app, "bob", "bob_pw", "dev_bob_win", 2)
    m1 = _send_message(app, alice, "conv_alice_bob", "hi", seq=3)
    _mark_read(app, bob, "conv_alice_bob", m1["payload"]["message_id"], seq=4)

    sync_resp = _sync(app, alice, seq=5)
    conv = sync_resp["payload"]["conversations"][0]
    assert conv["read_markers"] == {"u_bob": m1["payload"]["message_id"]}


def test_read_markers_persist() -> None:
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        app = ServerApplication(state_file=path)
        alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
        bob = _login(app, "bob", "bob_pw", "dev_bob_win", 2)
        m1 = _send_message(app, alice, "conv_alice_bob", "hi", seq=3)
        _mark_read(app, bob, "conv_alice_bob", m1["payload"]["message_id"], seq=4)

        app2 = ServerApplication(state_file=path)
        record = app2.state.conversations["conv_alice_bob"]
        assert record.read_markers.get("u_bob") == m1["payload"]["message_id"]
    finally:
        Path(path).unlink(missing_ok=True)


SCENARIOS = [
    ("mark_read_advances_pointer_and_pushes", test_mark_read_advances_pointer_and_pushes),
    ("forward_only_advancement", test_forward_only_advancement),
    ("unknown_message_rejected", test_unknown_message_rejected),
    ("non_participant_denied", test_non_participant_denied),
    ("read_markers_in_conversation_sync", test_read_markers_in_conversation_sync),
    ("read_markers_persist", test_read_markers_persist),
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
