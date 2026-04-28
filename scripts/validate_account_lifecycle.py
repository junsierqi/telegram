"""Validator for account export + delete (M95).

Drives an in-process ServerApplication through register → operate → export
→ delete and asserts:

  1. Export contains profile + devices + sessions + contacts + push tokens
     + authored messages with correct shape.
  2. Delete with wrong password -> ACCOUNT_DELETE_AUTH_FAILED, account intact.
  3. Delete with correct password tombstones authored messages, removes
     sessions / devices / push tokens / contacts (both directions).
  4. Other users still see the conversation but the deleted user's
     messages now show sender=u_deleted, deleted=true.
  5. After delete, login with the same username fails (UNKNOWN_USER /
     INVALID_CREDENTIALS) — same code path.
  6. 2FA-protected accounts require fresh TOTP code on delete.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402
from server.server.services.two_fa import generate_totp_code  # noqa: E402


def _login(app, user, password, device, seq, two_fa_code: str = ""):
    return app.dispatch({
        **make_envelope(MessageType.LOGIN_REQUEST, correlation_id=f"corr_login_{seq}", sequence=seq),
        "payload": {
            "username": user, "password": password, "device_id": device,
            "two_fa_code": two_fa_code,
        },
    })


def _send(app, sess, conv, text, seq):
    return app.dispatch({
        **make_envelope(MessageType.MESSAGE_SEND, correlation_id=f"corr_send_{seq}",
                        session_id=sess["session_id"], actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"conversation_id": conv, "text": text},
    })


def _add_contact(app, sess, target, seq):
    return app.dispatch({
        **make_envelope(MessageType.CONTACT_ADD, correlation_id=f"corr_ca_{seq}",
                        session_id=sess["session_id"], actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"target_user_id": target},
    })


def _push_register(app, sess, platform, token, seq):
    return app.dispatch({
        **make_envelope(MessageType.PUSH_TOKEN_REGISTER, correlation_id=f"corr_pr_{seq}",
                        session_id=sess["session_id"], actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"platform": platform, "token": token},
    })


def _export(app, sess, seq):
    return app.dispatch({
        **make_envelope(MessageType.ACCOUNT_EXPORT_REQUEST, correlation_id=f"corr_exp_{seq}",
                        session_id=sess["session_id"], actor_user_id=sess["user_id"], sequence=seq),
        "payload": {},
    })


def _delete(app, sess, password, two_fa_code, seq):
    return app.dispatch({
        **make_envelope(MessageType.ACCOUNT_DELETE_REQUEST, correlation_id=f"corr_del_{seq}",
                        session_id=sess["session_id"], actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"password": password, "two_fa_code": two_fa_code},
    })


def scenario_export_returns_full_snapshot():
    print("[scenario] export returns profile + devices + sessions + contacts + push tokens + authored messages")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice", 1)["payload"]
    _send(app, alice, "conv_alice_bob", "hello world", 2)
    _send(app, alice, "conv_alice_bob", "second message", 3)
    _add_contact(app, alice, "u_bob", 4)
    _push_register(app, alice, "fcm", "fcm_token_alice", 5)
    resp = _export(app, alice, 6)
    assert resp["type"] == "account_export_response", resp
    body = resp["payload"]
    assert body["user_id"] == "u_alice"
    assert body["profile"]["username"] == "alice"
    # at least one device, one session
    assert any(d["device_id"] == "dev_alice" for d in body["devices"])
    assert any(s["device_id"] == "dev_alice" for s in body["sessions"])
    # contacts captured
    assert any(c["target_user_id"] == "u_bob" for c in body["contacts"])
    # push tokens captured
    assert any(t["token"] == "fcm_token_alice" for t in body["push_tokens"])
    # authored messages: at least the two we sent (plus whatever was in seed)
    sent_texts = {m["text"] for m in body["authored_messages"] if m["text"]}
    assert "hello world" in sent_texts and "second message" in sent_texts
    print("[ok ] export populates every expected section")


def scenario_delete_with_wrong_password_keeps_account():
    print("[scenario] delete with wrong password -> ACCOUNT_DELETE_AUTH_FAILED, account intact")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice", 1)["payload"]
    resp = _delete(app, alice, "WRONG", "", 2)
    assert resp["type"] == "error", resp
    assert resp["payload"]["code"] == "account_delete_auth_failed", resp
    # account + session still exist
    assert "u_alice" in app.state.users
    assert alice["session_id"] in app.state.sessions
    print("[ok ] wrong password rejected; user record intact")


def scenario_delete_tombstones_messages():
    print("[scenario] delete tombstones authored messages + removes session/device/contacts")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice", 1)["payload"]
    bob = _login(app, "bob", "bob_pw", "dev_bob", 2)["payload"]
    _send(app, alice, "conv_alice_bob", "before delete", 3)
    _add_contact(app, alice, "u_bob", 4)
    _add_contact(app, bob, "u_alice", 5)  # bob has alice as a contact too
    _push_register(app, alice, "fcm", "fcm_token_alice", 6)
    # snapshot pre-delete
    pre_msg_count = sum(1 for m in app.state.conversations["conv_alice_bob"].messages
                        if m.get("sender_user_id") == "u_alice")
    assert pre_msg_count >= 1
    # do the delete
    resp = _delete(app, alice, "alice_pw", "", 7)
    assert resp["type"] == "account_delete_response", resp
    summary = resp["payload"]
    assert summary["user_id"] == "u_alice"
    assert summary["messages_tombstoned"] == pre_msg_count
    assert summary["sessions_revoked"] >= 1
    assert summary["devices_removed"] >= 1
    assert summary["push_tokens_removed"] >= 1
    assert summary["contacts_removed"] >= 1  # both directions
    # alice gone
    assert "u_alice" not in app.state.users
    assert alice["session_id"] not in app.state.sessions
    # alice's messages tombstoned
    conv = app.state.conversations["conv_alice_bob"]
    for msg in conv.messages:
        if msg.get("text") == "before delete":
            assert msg["sender_user_id"] == "u_deleted"
            assert msg.get("deleted") is True
            break
    # bob's contact list shouldn't reference alice anymore
    assert "u_alice" not in app.state.contacts.get("u_bob", [])
    # bob's session intact
    assert bob["session_id"] in app.state.sessions
    print("[ok ] tombstone + cleanup all sides")


def scenario_login_after_delete_fails():
    print("[scenario] post-delete login with same username -> INVALID_CREDENTIALS")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice", 1)["payload"]
    _delete(app, alice, "alice_pw", "", 2)
    relogin = _login(app, "alice", "alice_pw", "dev_alice_2", 3)
    assert relogin["type"] == "error", relogin
    assert relogin["payload"]["code"] == "invalid_credentials", relogin
    print("[ok ] deleted username can't log back in")


def scenario_delete_with_2fa_requires_totp():
    print("[scenario] 2FA-protected account: delete needs valid two_fa_code")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice", 1)["payload"]
    # Enable 2FA
    enr = app.dispatch({
        **make_envelope(MessageType.TWO_FA_ENABLE_REQUEST, correlation_id="corr_2fa_e",
                        session_id=alice["session_id"], actor_user_id=alice["user_id"], sequence=2),
        "payload": {},
    })
    secret = enr["payload"]["secret"]
    app.dispatch({
        **make_envelope(MessageType.TWO_FA_VERIFY_REQUEST, correlation_id="corr_2fa_v",
                        session_id=alice["session_id"], actor_user_id=alice["user_id"], sequence=3),
        "payload": {"code": generate_totp_code(secret)},
    })
    # Delete WITHOUT a code -> rejected
    resp = _delete(app, alice, "alice_pw", "", 4)
    assert resp["type"] == "error", resp
    assert resp["payload"]["code"] == "account_delete_auth_failed", resp
    # Delete WITH the right code -> succeeds
    resp = _delete(app, alice, "alice_pw", generate_totp_code(secret), 5)
    assert resp["type"] == "account_delete_response", resp
    print("[ok ] 2FA-protected delete requires fresh TOTP")


def main() -> int:
    scenarios = [
        scenario_export_returns_full_snapshot,
        scenario_delete_with_wrong_password_keeps_account,
        scenario_delete_tombstones_messages,
        scenario_login_after_delete_fails,
        scenario_delete_with_2fa_requires_totp,
    ]
    for s in scenarios:
        s()
    print(f"\nAll {len(scenarios)}/{len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
