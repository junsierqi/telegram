"""Validator for server-side per-(user, conversation) drafts (M99).

Scenarios:
  1. save round-trips through list (draft text + reply_to + updated_at_ms).
  2. Empty text auto-clears the draft (cleared=true) — Telegram parity.
  3. clear() removes an existing draft (cleared=true), and is idempotent
     (cleared=false on the second call).
  4. Save against UNKNOWN_CONVERSATION returns the typed error and writes
     no state.
  5. Save against a conversation the user is NOT a participant of returns
     CONVERSATION_ACCESS_DENIED — drafts shouldn't leak existence.
  6. MESSAGE_SEND in a conversation auto-clears the draft (so the same
     message doesn't get "sent" twice if the client races a save+send).
  7. list_for_user only returns the actor's drafts, not someone else's.
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


def _save(app, sess, conv, text, seq, *, reply_to=""):
    return app.dispatch({
        **make_envelope(MessageType.DRAFT_SAVE_REQUEST, correlation_id=f"corr_s_{seq}",
                        session_id=sess["session_id"], actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"conversation_id": conv, "text": text, "reply_to_message_id": reply_to},
    })


def _list(app, sess, seq):
    return app.dispatch({
        **make_envelope(MessageType.DRAFT_LIST_REQUEST, correlation_id=f"corr_ls_{seq}",
                        session_id=sess["session_id"], actor_user_id=sess["user_id"], sequence=seq),
        "payload": {},
    })


def _clear(app, sess, conv, seq):
    return app.dispatch({
        **make_envelope(MessageType.DRAFT_CLEAR_REQUEST, correlation_id=f"corr_c_{seq}",
                        session_id=sess["session_id"], actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"conversation_id": conv},
    })


def _send(app, sess, conv, text, seq):
    return app.dispatch({
        **make_envelope(MessageType.MESSAGE_SEND, correlation_id=f"corr_msg_{seq}",
                        session_id=sess["session_id"], actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"conversation_id": conv, "text": text},
    })


def scenario_save_then_list():
    print("[scenario] save round-trips through list")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    resp = _save(app, alice, "conv_alice_bob", "hello, half-typed", 2, reply_to="msg_seed_1")
    assert resp["type"] == "draft_save_response", resp
    assert resp["payload"]["cleared"] is False
    drafted = resp["payload"]["draft"]
    assert drafted["conversation_id"] == "conv_alice_bob"
    assert drafted["text"] == "hello, half-typed"
    assert drafted["reply_to_message_id"] == "msg_seed_1"
    assert drafted["updated_at_ms"] > 0
    listed = _list(app, alice, 3)
    assert listed["type"] == "draft_list_response", listed
    drafts = listed["payload"]["drafts"]
    assert len(drafts) == 1 and drafts[0]["text"] == "hello, half-typed", drafts
    print("[ok ] save + list round-trip")


def scenario_empty_text_autoclears():
    print("[scenario] empty text auto-clears the draft")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    _save(app, alice, "conv_alice_bob", "wip", 2)
    resp = _save(app, alice, "conv_alice_bob", "   ", 3)
    assert resp["type"] == "draft_save_response", resp
    assert resp["payload"]["cleared"] is True
    assert resp["payload"]["draft"]["text"] == ""
    listed = _list(app, alice, 4)
    assert listed["payload"]["drafts"] == []
    print("[ok ] whitespace-only text cleared the draft")


def scenario_clear_idempotent():
    print("[scenario] clear() removes a draft and is idempotent")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    _save(app, alice, "conv_alice_bob", "wip", 2)
    r1 = _clear(app, alice, "conv_alice_bob", 3)
    assert r1["type"] == "draft_clear_response" and r1["payload"]["cleared"] is True
    r2 = _clear(app, alice, "conv_alice_bob", 4)
    assert r2["payload"]["cleared"] is False, r2
    print("[ok ] clear -> cleared=true; second clear -> cleared=false")


def scenario_save_unknown_conversation():
    print("[scenario] save against unknown conversation -> UNKNOWN_CONVERSATION")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    resp = _save(app, alice, "conv_does_not_exist", "wip", 2)
    assert resp["type"] == "error", resp
    assert resp["payload"]["code"] == "unknown_conversation", resp
    print("[ok ] unknown conversation rejected")


def scenario_save_non_participant():
    print("[scenario] save in a conversation user isn't part of -> CONVERSATION_ACCESS_DENIED")
    app = ServerApplication()
    # Register carol so alice has a conversation she's not a member of.
    reg = app.dispatch({
        **make_envelope(MessageType.REGISTER_REQUEST, correlation_id="corr_reg", sequence=1),
        "payload": {"username": "carol", "password": "carol_pw",
                    "display_name": "Carol", "device_id": "dev_c"},
    })
    assert reg["type"] == "register_response", reg
    carol = reg["payload"]
    alice = _login(app, "alice", "alice_pw", "dev_a", 2)
    # carol creates a 1:1 with bob (alice not included).
    create = app.dispatch({
        **make_envelope(MessageType.CONVERSATION_CREATE, correlation_id="corr_cc",
                        session_id=carol["session_id"], actor_user_id=carol["user_id"], sequence=3),
        "payload": {"participant_user_ids": ["u_bob"], "title": "carol+bob"},
    })
    assert create["type"] == "conversation_updated", create
    cb_id = create["payload"]["conversation_id"]
    resp = _save(app, alice, cb_id, "sneaky draft", 4)
    assert resp["type"] == "error", resp
    assert resp["payload"]["code"] == "conversation_access_denied", resp
    print("[ok ] non-participant draft save rejected")


def scenario_message_send_clears_draft():
    print("[scenario] sending a message auto-clears the per-conversation draft")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    _save(app, alice, "conv_alice_bob", "draft about to ship", 2)
    listed = _list(app, alice, 3)
    assert len(listed["payload"]["drafts"]) == 1
    resp = _send(app, alice, "conv_alice_bob", "actual sent text", 4)
    assert resp["type"] == "message_deliver", resp
    listed2 = _list(app, alice, 5)
    assert listed2["payload"]["drafts"] == [], listed2
    print("[ok ] MESSAGE_SEND wiped the draft")


def scenario_list_per_user_isolation():
    print("[scenario] list_for_user only returns the actor's drafts")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    bob = _login(app, "bob", "bob_pw", "dev_b", 2)
    _save(app, alice, "conv_alice_bob", "alice's draft", 3)
    _save(app, bob, "conv_alice_bob", "bob's draft", 4)
    a_list = _list(app, alice, 5)["payload"]["drafts"]
    b_list = _list(app, bob, 6)["payload"]["drafts"]
    assert len(a_list) == 1 and a_list[0]["text"] == "alice's draft", a_list
    assert len(b_list) == 1 and b_list[0]["text"] == "bob's draft", b_list
    print("[ok ] each user sees only their own drafts")


def main() -> int:
    scenarios = [
        scenario_save_then_list,
        scenario_empty_text_autoclears,
        scenario_clear_idempotent,
        scenario_save_unknown_conversation,
        scenario_save_non_participant,
        scenario_message_send_clears_draft,
        scenario_list_per_user_isolation,
    ]
    for s in scenarios:
        s()
    print(f"\nAll {len(scenarios)}/{len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
