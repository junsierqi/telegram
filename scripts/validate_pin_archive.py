"""Validator for per-user pinned + archived conversations (M100).

Scenarios:
  1. Pin a conversation, conversation_sync surfaces pinned=true; unpin
     and the flag flips back. archived stays false throughout.
  2. Archive is independent from pin: a chat can be both pinned AND
     archived, or either, or neither.
  3. Per-user isolation: alice pinning conv_alice_bob does NOT affect
     bob's view of the same conversation.
  4. Toggling a conversation the user isn't a member of returns
     CONVERSATION_ACCESS_DENIED (no leak of existence).
  5. Toggling a non-existent conversation returns UNKNOWN_CONVERSATION.
  6. Re-pinning an already-pinned chat is a no-op (idempotent).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402


def _login(app, user, pw, dev, seq):
    resp = app.dispatch({
        **make_envelope(MessageType.LOGIN_REQUEST, correlation_id=f"corr_l_{seq}", sequence=seq),
        "payload": {"username": user, "password": pw, "device_id": dev},
    })
    assert resp["type"] == "login_response", resp
    return resp["payload"]


def _toggle_pin(app, sess, conv, pinned, seq):
    return app.dispatch({
        **make_envelope(MessageType.CONVERSATION_PIN_TOGGLE_REQUEST,
                        correlation_id=f"corr_p_{seq}",
                        session_id=sess["session_id"],
                        actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"conversation_id": conv, "pinned": pinned},
    })


def _toggle_archive(app, sess, conv, archived, seq):
    return app.dispatch({
        **make_envelope(MessageType.CONVERSATION_ARCHIVE_TOGGLE_REQUEST,
                        correlation_id=f"corr_a_{seq}",
                        session_id=sess["session_id"],
                        actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"conversation_id": conv, "archived": archived},
    })


def _sync(app, sess, seq):
    return app.dispatch({
        **make_envelope(MessageType.CONVERSATION_SYNC,
                        correlation_id=f"corr_sync_{seq}",
                        session_id=sess["session_id"],
                        actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"cursors": {}, "versions": {},
                    "history_limits": {}, "before_message_ids": {}},
    })


def _conv_in_sync(sync_resp, conv_id):
    for c in sync_resp["payload"]["conversations"]:
        if c["conversation_id"] == conv_id:
            return c
    return None


def scenario_pin_round_trip():
    print("[scenario] pin + unpin round-trip via conversation_sync")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    r = _toggle_pin(app, alice, "conv_alice_bob", True, 2)
    assert r["type"] == "conversation_pin_toggle_response", r
    assert r["payload"] == {"conversation_id": "conv_alice_bob", "pinned": True}
    sync1 = _sync(app, alice, 3)
    conv = _conv_in_sync(sync1, "conv_alice_bob")
    assert conv is not None and conv["pinned"] is True and conv["archived"] is False, conv
    r2 = _toggle_pin(app, alice, "conv_alice_bob", False, 4)
    assert r2["payload"]["pinned"] is False
    sync2 = _sync(app, alice, 5)
    assert _conv_in_sync(sync2, "conv_alice_bob")["pinned"] is False
    print("[ok ] pin true -> sync.pinned=true; pin false -> sync.pinned=false")


def scenario_pin_and_archive_independent():
    print("[scenario] pinned + archived are independent flags")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    _toggle_pin(app, alice, "conv_alice_bob", True, 2)
    _toggle_archive(app, alice, "conv_alice_bob", True, 3)
    conv = _conv_in_sync(_sync(app, alice, 4), "conv_alice_bob")
    assert conv["pinned"] is True and conv["archived"] is True, conv
    # Unpin without touching archive — archive should stay true.
    _toggle_pin(app, alice, "conv_alice_bob", False, 5)
    conv = _conv_in_sync(_sync(app, alice, 6), "conv_alice_bob")
    assert conv["pinned"] is False and conv["archived"] is True, conv
    print("[ok ] pin/archive flip independently")


def scenario_per_user_isolation():
    print("[scenario] alice pinning doesn't pin bob's view")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    bob = _login(app, "bob", "bob_pw", "dev_b", 2)
    _toggle_pin(app, alice, "conv_alice_bob", True, 3)
    a = _conv_in_sync(_sync(app, alice, 4), "conv_alice_bob")
    b = _conv_in_sync(_sync(app, bob, 5), "conv_alice_bob")
    assert a["pinned"] is True, a
    assert b["pinned"] is False, b
    print("[ok ] per-user view isolation holds")


def scenario_non_participant_rejected():
    print("[scenario] toggling a conversation user isn't part of -> CONVERSATION_ACCESS_DENIED")
    app = ServerApplication()
    # Register carol so we can build a conversation alice isn't part of.
    reg = app.dispatch({
        **make_envelope(MessageType.REGISTER_REQUEST, correlation_id="corr_reg", sequence=1),
        "payload": {"username": "carol", "password": "carol_pw",
                    "display_name": "Carol", "device_id": "dev_c"},
    })
    assert reg["type"] == "register_response", reg
    carol = reg["payload"]
    alice = _login(app, "alice", "alice_pw", "dev_a", 2)
    create = app.dispatch({
        **make_envelope(MessageType.CONVERSATION_CREATE,
                        correlation_id="corr_cc",
                        session_id=carol["session_id"],
                        actor_user_id=carol["user_id"], sequence=3),
        "payload": {"participant_user_ids": ["u_bob"], "title": "carol+bob"},
    })
    cb_id = create["payload"]["conversation_id"]
    r = _toggle_pin(app, alice, cb_id, True, 4)
    assert r["type"] == "error" and r["payload"]["code"] == "conversation_access_denied", r
    r2 = _toggle_archive(app, alice, cb_id, True, 5)
    assert r2["type"] == "error" and r2["payload"]["code"] == "conversation_access_denied", r2
    print("[ok ] non-participant pin/archive both rejected")


def scenario_unknown_conversation():
    print("[scenario] toggling unknown conversation -> UNKNOWN_CONVERSATION")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    r = _toggle_pin(app, alice, "conv_does_not_exist", True, 2)
    assert r["type"] == "error" and r["payload"]["code"] == "unknown_conversation", r
    r2 = _toggle_archive(app, alice, "conv_does_not_exist", True, 3)
    assert r2["type"] == "error" and r2["payload"]["code"] == "unknown_conversation", r2
    print("[ok ] unknown conversation rejected for both ops")


def scenario_re_pin_idempotent():
    print("[scenario] re-pinning an already-pinned chat is a no-op")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    r1 = _toggle_pin(app, alice, "conv_alice_bob", True, 2)
    r2 = _toggle_pin(app, alice, "conv_alice_bob", True, 3)
    assert r1["payload"]["pinned"] is True and r2["payload"]["pinned"] is True
    # The set should still hold exactly one entry.
    assert app.conversation_flags_service.list_pinned("u_alice") == {"conv_alice_bob"}
    print("[ok ] re-pin is idempotent")


def main() -> int:
    scenarios = [
        scenario_pin_round_trip,
        scenario_pin_and_archive_independent,
        scenario_per_user_isolation,
        scenario_non_participant_rejected,
        scenario_unknown_conversation,
        scenario_re_pin_idempotent,
    ]
    for s in scenarios:
        s()
    print(f"\nAll {len(scenarios)}/{len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
