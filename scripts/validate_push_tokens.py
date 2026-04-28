"""Validator for the push notification protocol surface (M84).

Drives an in-process ServerApplication to verify:
  1. PUSH_TOKEN_REGISTER persists a (user, device, platform, token) record
     and ACKs with registered=True.
  2. PUSH_TOKEN_LIST_REQUEST returns the registered tokens for the actor.
  3. Sending a message to a recipient with NO fresh session enqueues a
     mock delivery in PushTokenService.pending_deliveries.
  4. The same recipient, while ONLINE, does NOT enqueue a mock delivery
     (live fan-out covers it).
  5. PUSH_TOKEN_UNREGISTER removes the record and the next list returns
     empty for that platform.
  6. Empty-payload registration is rejected with INVALID_REGISTRATION_PAYLOAD.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402


def _login(app, user, password, device, seq):
    resp = app.dispatch({
        **make_envelope(MessageType.LOGIN_REQUEST, correlation_id=f"corr_login_{seq}", sequence=seq),
        "payload": {"username": user, "password": password, "device_id": device},
    })
    assert resp["type"] == "login_response", resp
    return resp["payload"]


def _push_register(app, sess, platform, token, seq):
    return app.dispatch({
        **make_envelope(MessageType.PUSH_TOKEN_REGISTER, correlation_id=f"corr_pr_{seq}",
                        session_id=sess["session_id"], actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"platform": platform, "token": token},
    })


def _push_unregister(app, sess, platform, token, seq):
    return app.dispatch({
        **make_envelope(MessageType.PUSH_TOKEN_UNREGISTER, correlation_id=f"corr_pu_{seq}",
                        session_id=sess["session_id"], actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"platform": platform, "token": token},
    })


def _push_list(app, sess, seq):
    return app.dispatch({
        **make_envelope(MessageType.PUSH_TOKEN_LIST_REQUEST, correlation_id=f"corr_pl_{seq}",
                        session_id=sess["session_id"], actor_user_id=sess["user_id"], sequence=seq),
        "payload": {},
    })


def _send_message(app, sess, conversation_id, text, seq):
    return app.dispatch({
        **make_envelope(MessageType.MESSAGE_SEND, correlation_id=f"corr_ms_{seq}",
                        session_id=sess["session_id"], actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"conversation_id": conversation_id, "text": text},
    })


def scenario_register_returns_ack_and_persists():
    print("[scenario] register -> ACK registered=True; list returns the row")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice", 1)
    resp = _push_register(app, alice, "fcm", "fcm_token_abc", 2)
    assert resp["type"] == "push_token_ack", resp
    assert resp["payload"] == {"platform": "fcm", "token": "fcm_token_abc", "registered": True}
    listed = _push_list(app, alice, 3)
    assert listed["type"] == "push_token_list_response", listed
    tokens = listed["payload"]["tokens"]
    assert len(tokens) == 1
    assert tokens[0]["platform"] == "fcm"
    assert tokens[0]["token"] == "fcm_token_abc"
    assert tokens[0]["user_id"] == "u_alice"
    assert tokens[0]["device_id"] == "dev_alice"
    assert tokens[0]["registered_at_ms"] > 0
    print("[ok ] registration ACK + list round-trip")


def scenario_offline_recipient_gets_mock_push():
    print("[scenario] message_send to offline recipient enqueues mock push")
    app = ServerApplication(presence_ttl_seconds=5.0)
    bob = _login(app, "bob", "bob_pw", "dev_bob", 1)
    # Register bob's push token while bob is online.
    _push_register(app, bob, "fcm", "fcm_token_bob", 2)
    # Drop bob to offline by deleting his session — simulates a stale TCP
    # connection. (Cleaner than waiting on real TTL elapse in a unit test.)
    del app.state.sessions[bob["session_id"]]
    # Alice logs in and sends a message into the seed conversation.
    alice = _login(app, "alice", "alice_pw", "dev_alice", 3)
    app.push_token_service.drain_pending()  # drain anything from pre-state
    resp = _send_message(app, alice, "conv_alice_bob", "ping while bob is offline", 4)
    assert resp["type"] == "message_deliver", resp
    pending = app.push_token_service.drain_pending()
    bob_pushes = [p for p in pending if p.user_id == "u_bob"]
    assert len(bob_pushes) == 1, f"expected exactly one bob push, got {pending}"
    assert bob_pushes[0].platform == "fcm"
    assert bob_pushes[0].token == "fcm_token_bob"
    assert bob_pushes[0].kind == "message_deliver"
    assert "bob is offline" in bob_pushes[0].body_summary
    print("[ok ] offline recipient enqueued via mock push")


def scenario_online_recipient_does_not_get_mock_push():
    print("[scenario] message_send to online recipient does NOT enqueue mock push")
    app = ServerApplication(presence_ttl_seconds=5.0)
    bob = _login(app, "bob", "bob_pw", "dev_bob", 1)
    _push_register(app, bob, "fcm", "fcm_token_bob", 2)
    alice = _login(app, "alice", "alice_pw", "dev_alice", 3)
    app.push_token_service.drain_pending()
    _send_message(app, alice, "conv_alice_bob", "ping while bob is online", 4)
    pending = app.push_token_service.drain_pending()
    bob_pushes = [p for p in pending if p.user_id == "u_bob"]
    assert bob_pushes == [], f"expected no bob push (live), got {bob_pushes}"
    print("[ok ] live fan-out short-circuits mock push")


def scenario_unregister_removes_token():
    print("[scenario] unregister removes the token; list goes empty")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice", 1)
    _push_register(app, alice, "fcm", "fcm_token_abc", 2)
    resp = _push_unregister(app, alice, "fcm", "fcm_token_abc", 3)
    assert resp["type"] == "push_token_ack", resp
    assert resp["payload"]["registered"] is False
    listed = _push_list(app, alice, 4)
    assert listed["payload"]["tokens"] == []
    print("[ok ] unregister tear-down round-trip")


def scenario_empty_payload_rejected():
    print("[scenario] register with empty platform+token -> INVALID_REGISTRATION_PAYLOAD error")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice", 1)
    resp = _push_register(app, alice, "", "", 2)
    assert resp["type"] == "error", resp
    assert resp["payload"]["code"] == "invalid_registration_payload", resp
    print("[ok ] empty payload rejected with typed error")


def scenario_token_replace_is_idempotent():
    print("[scenario] re-register same (user, device, platform) replaces token in place")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice", 1)
    _push_register(app, alice, "fcm", "fcm_token_v1", 2)
    _push_register(app, alice, "fcm", "fcm_token_v2", 3)
    listed = _push_list(app, alice, 4)
    tokens = listed["payload"]["tokens"]
    assert len(tokens) == 1, f"expected 1 token after rotation, got {tokens}"
    assert tokens[0]["token"] == "fcm_token_v2"
    print("[ok ] token rotation replaces in place")


def main() -> int:
    scenarios = [
        scenario_register_returns_ack_and_persists,
        scenario_offline_recipient_gets_mock_push,
        scenario_online_recipient_does_not_get_mock_push,
        scenario_unregister_removes_token,
        scenario_empty_payload_rejected,
        scenario_token_replace_is_idempotent,
    ]
    for s in scenarios:
        s()
    print(f"\nAll {len(scenarios)}/{len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
