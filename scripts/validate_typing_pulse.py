"""Validator for M146 — TYPING_PULSE protocol fanout.

Server-side primitive: when one participant in a conversation dispatches
a TYPING_PULSE the server fills sender_user_id, fans the message out to
every OTHER participant via the connection registry, and acknowledges
the originator. Clients render the visual via TypingIndicator (M140)
and decay locally — server holds no state, so a missed STOP doesn't leak.

Scenarios:
  1. Bob sends TYPING_PULSE(is_typing=true, conv=alice_bob).
     - Alice's inbox receives a TYPING_PULSE push with sender_user_id=u_bob
       and is_typing=True.
     - Bob's own response is the same envelope (acknowledgement, not an
       error).
  2. Bob sends TYPING_PULSE(is_typing=false) — Alice sees the false too,
     so she can short-circuit her local 5s decay.
  3. A non-participant cannot fan typing into a conversation: charlie
     attempting TYPING_PULSE on conv_alice_bob gets a
     CONVERSATION_ACCESS_DENIED error and Alice's inbox stays empty.
  4. Sending TYPING_PULSE on a non-existent conversation returns
     UNKNOWN_CONVERSATION (and again no fanout).
"""
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


def login(app: ServerApplication, username: str, password: str, device_id: str, seq: int) -> dict:
    return app.dispatch({
        **make_envelope(MessageType.LOGIN_REQUEST, correlation_id=f"corr_{username}", sequence=seq),
        "payload": {"username": username, "password": password, "device_id": device_id},
    })["payload"]


def typing(app: ServerApplication, session: dict, conv: str, is_typing: bool, seq: int) -> dict:
    return app.dispatch({
        **make_envelope(
            MessageType.TYPING_PULSE,
            correlation_id=f"corr_typ_{seq}",
            session_id=session["session_id"],
            actor_user_id=session["user_id"],
            sequence=seq,
        ),
        "payload": {"conversation_id": conv, "is_typing": is_typing},
    })


def main() -> int:
    registry = ConnectionRegistry()
    app = ServerApplication(connection_registry=registry)
    alice = login(app, "alice", "alice_pw", "dev_alice_typ", 1)
    bob = login(app, "bob", "bob_pw", "dev_bob_typ", 2)
    alice_inbox = Inbox()
    registry.register(alice["session_id"], alice_inbox.writer)

    print("[scenario] bob's TYPING_PULSE(true) fans out to alice + acks bob")
    response = typing(app, bob, "conv_alice_bob", True, 3)
    assert response["type"] == "typing_pulse", response
    assert response["payload"]["is_typing"] is True
    assert response["payload"]["sender_user_id"] == bob["user_id"]
    pushed = alice_inbox.pop_type("typing_pulse")
    assert pushed is not None, f"alice should have received the typing pulse, got: {alice_inbox.messages}"
    assert pushed["payload"]["sender_user_id"] == bob["user_id"]
    assert pushed["payload"]["conversation_id"] == "conv_alice_bob"
    assert pushed["payload"]["is_typing"] is True
    print("[ok ] bob -> alice typing pulse delivered")

    print("[scenario] bob's TYPING_PULSE(false) also propagates so alice can short-circuit decay")
    response = typing(app, bob, "conv_alice_bob", False, 4)
    assert response["payload"]["is_typing"] is False
    pushed = alice_inbox.pop_type("typing_pulse")
    assert pushed is not None, "alice should have received the typing-stopped pulse"
    assert pushed["payload"]["is_typing"] is False
    print("[ok ] STOP variant fans through unchanged")

    print("[scenario] non-participant can't fan typing into someone else's conversation")
    charlie_reg = app.dispatch({
        **make_envelope(MessageType.REGISTER_REQUEST, correlation_id="corr_charlie_reg", sequence=5),
        "payload": {
            "username": "charlie",
            "password": "charlie_pw",
            "device_id": "dev_charlie_typ",
            "display_name": "Charlie",
        },
    })
    assert charlie_reg["type"] == "register_response", charlie_reg
    charlie = charlie_reg["payload"]
    response = typing(app, charlie, "conv_alice_bob", True, 6)
    assert response["type"] == "error", f"charlie should be rejected, got {response}"
    assert response["payload"]["code"] == "conversation_access_denied", response
    leak = alice_inbox.pop_type("typing_pulse")
    assert leak is None, f"alice must not see typing from a non-participant, got {leak}"
    print("[ok ] non-participant rejected with conversation_access_denied + no fanout leak")

    print("[scenario] unknown conversation returns unknown_conversation")
    response = typing(app, alice, "conv_does_not_exist", True, 7)
    assert response["type"] == "error", response
    assert response["payload"]["code"] == "unknown_conversation", response
    print("[ok ] unknown_conversation surfaced")

    print("\nAll 4/4 scenarios passed.")
    return 0


if __name__ == "__main__":
    import traceback
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(f"[FAIL] {exc}")
        traceback.print_exc()
        sys.exit(1)
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}")
        traceback.print_exc()
        sys.exit(1)
