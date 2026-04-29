"""Validator for block-user list + per-conversation mute (M98).

Scenarios:
  1. block_user marks the relation; list_blocked reflects it.
  2. unblock removes the entry; double-unblock returns NOT_BLOCKED.
  3. Re-blocking the same user returns ALREADY_BLOCKED.
  4. Sending a 1:1 message to a recipient who blocked the sender returns
     BLOCKED_BY_RECIPIENT; the existing message_deliver flow is untouched
     (no message persisted).
  5. Group sends are NOT blocked even when one participant has another
     blocked — Telegram parity.
  6. set_mute with -1 / future epoch / 0 round-trips through get_mute.
  7. set_mute with an unknown conversation returns UNKNOWN_CONVERSATION.
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


def _block(app, sess, target, seq):
    return app.dispatch({
        **make_envelope(MessageType.BLOCK_USER_REQUEST, correlation_id=f"corr_b_{seq}",
                        session_id=sess["session_id"], actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"target_user_id": target},
    })


def _unblock(app, sess, target, seq):
    return app.dispatch({
        **make_envelope(MessageType.UNBLOCK_USER_REQUEST, correlation_id=f"corr_u_{seq}",
                        session_id=sess["session_id"], actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"target_user_id": target},
    })


def _list_blocked(app, sess, seq):
    return app.dispatch({
        **make_envelope(MessageType.BLOCKED_USERS_LIST_REQUEST, correlation_id=f"corr_lb_{seq}",
                        session_id=sess["session_id"], actor_user_id=sess["user_id"], sequence=seq),
        "payload": {},
    })


def _send(app, sess, conv, text, seq):
    return app.dispatch({
        **make_envelope(MessageType.MESSAGE_SEND, correlation_id=f"corr_s_{seq}",
                        session_id=sess["session_id"], actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"conversation_id": conv, "text": text},
    })


def _set_mute(app, sess, conv, until, seq):
    return app.dispatch({
        **make_envelope(MessageType.CONVERSATION_MUTE_UPDATE_REQUEST, correlation_id=f"corr_m_{seq}",
                        session_id=sess["session_id"], actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"conversation_id": conv, "muted_until_ms": until},
    })


def scenario_block_then_list():
    print("[scenario] block_user round-trips through list")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    resp = _block(app, alice, "u_bob", 2)
    assert resp["type"] == "block_user_ack", resp
    assert resp["payload"] == {"target_user_id": "u_bob", "blocked": True}
    listed = _list_blocked(app, alice, 3)
    assert listed["type"] == "blocked_users_list_response", listed
    assert listed["payload"]["blocked"][0]["user_id"] == "u_bob"
    assert listed["payload"]["blocked"][0]["blocked_at_ms"] > 0
    print("[ok ] block + list round-trip")


def scenario_already_blocked_and_not_blocked():
    print("[scenario] re-block -> ALREADY_BLOCKED; double-unblock -> NOT_BLOCKED")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    _block(app, alice, "u_bob", 2)
    again = _block(app, alice, "u_bob", 3)
    assert again["type"] == "error" and again["payload"]["code"] == "already_blocked", again
    _unblock(app, alice, "u_bob", 4)
    again2 = _unblock(app, alice, "u_bob", 5)
    assert again2["type"] == "error" and again2["payload"]["code"] == "not_blocked", again2
    print("[ok ] idempotency-error codes wired")


def scenario_blocked_recipient_blocks_dm():
    print("[scenario] bob blocked alice -> alice's DM to bob gets BLOCKED_BY_RECIPIENT")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    bob = _login(app, "bob", "bob_pw", "dev_b", 2)
    _block(app, bob, "u_alice", 3)
    resp = _send(app, alice, "conv_alice_bob", "hello, are you there?", 4)
    assert resp["type"] == "error", resp
    assert resp["payload"]["code"] == "blocked_by_recipient", resp
    # Confirm message NOT persisted (only the 2 seed messages remain).
    conv = app.state.conversations["conv_alice_bob"]
    assert all(m.get("text") != "hello, are you there?" for m in conv.messages)
    print("[ok ] DM blocked + not persisted")


def scenario_group_send_unaffected_by_block():
    print("[scenario] block in a 3+ member group doesn't gate sends")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    bob = _login(app, "bob", "bob_pw", "dev_b", 2)
    # Register carol so we can build a 3-member group up front.
    reg = app.dispatch({
        **make_envelope(MessageType.REGISTER_REQUEST, correlation_id="corr_reg", sequence=3),
        "payload": {"username": "carol", "password": "carol_pw",
                    "display_name": "Carol", "device_id": "dev_c"},
    })
    assert reg["type"] == "register_response", reg
    carol_user_id = reg["payload"]["user_id"]  # auto-generated, e.g. u_auto_1
    # Group with 3 explicit participants from the start.
    create = app.dispatch({
        **make_envelope(MessageType.CONVERSATION_CREATE, correlation_id="corr_gc",
                        session_id=alice["session_id"], actor_user_id=alice["user_id"], sequence=4),
        "payload": {"participant_user_ids": ["u_bob", carol_user_id], "title": "Three"},
    })
    assert create["type"] == "conversation_updated", create
    group_id = create["payload"]["conversation_id"]
    # Sanity: group really has 3 members.
    conv = app.state.conversations[group_id]
    assert sorted(conv.participant_user_ids) == sorted(["u_alice", "u_bob", carol_user_id]), \
        conv.participant_user_ids
    # bob blocks alice
    _block(app, bob, "u_alice", 5)
    # alice's send into the 3-member group must NOT be gated by the block.
    resp = _send(app, alice, group_id, "group hello", 6)
    assert resp["type"] == "message_deliver", resp
    print("[ok ] group send unaffected by block")


def scenario_mute_round_trip():
    print("[scenario] set_mute(-1 / future / 0) round-trips through get_mute")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    # Mute forever
    r1 = _set_mute(app, alice, "conv_alice_bob", -1, 2)
    assert r1["type"] == "conversation_mute_update_response", r1
    assert r1["payload"]["muted_until_ms"] == -1
    assert app.block_mute_service.get_mute("u_alice", "conv_alice_bob") == -1
    # Mute until far future
    far = 9_999_999_999_999
    r2 = _set_mute(app, alice, "conv_alice_bob", far, 3)
    assert r2["payload"]["muted_until_ms"] == far
    # Unmute
    r3 = _set_mute(app, alice, "conv_alice_bob", 0, 4)
    assert r3["payload"]["muted_until_ms"] == 0
    assert app.block_mute_service.get_mute("u_alice", "conv_alice_bob") == 0
    print("[ok ] mute -1 / future / 0 all round-trip")


def scenario_mute_unknown_conversation():
    print("[scenario] set_mute on unknown conversation_id -> UNKNOWN_CONVERSATION")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    r = _set_mute(app, alice, "conv_does_not_exist", -1, 2)
    assert r["type"] == "error", r
    assert r["payload"]["code"] == "unknown_conversation", r
    print("[ok ] unknown conversation rejected")


def main() -> int:
    scenarios = [
        scenario_block_then_list,
        scenario_already_blocked_and_not_blocked,
        scenario_blocked_recipient_blocks_dm,
        scenario_group_send_unaffected_by_block,
        scenario_mute_round_trip,
        scenario_mute_unknown_conversation,
    ]
    for s in scenarios:
        s()
    print(f"\nAll {len(scenarios)}/{len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
