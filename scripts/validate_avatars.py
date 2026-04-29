"""Validator for profile + group avatars (M101).

Avatars are stored as a pointer to an attachment_id from the chunked
upload pipeline, not as inline bytes. Server-side validation in this
milestone is light: we accept any string (including empty) for now and
trust the client to provide an attachment that's been uploaded. The
real bytes round-trip via ATTACHMENT_FETCH and is exercised in
validate_attachments.py.

Scenarios:
  1. Set + clear profile avatar; profile_response surfaces the new
     pointer (and "" after clearing).
  2. Set + clear conversation avatar; conversation_sync surfaces the
     new pointer.
  3. Conversation avatar update by a non-participant returns
     CONVERSATION_ACCESS_DENIED.
  4. Conversation avatar update against an unknown conversation_id
     returns UNKNOWN_CONVERSATION.
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


def _set_profile_avatar(app, sess, attachment_id, seq):
    return app.dispatch({
        **make_envelope(MessageType.PROFILE_AVATAR_UPDATE_REQUEST,
                        correlation_id=f"corr_pa_{seq}",
                        session_id=sess["session_id"],
                        actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"avatar_attachment_id": attachment_id},
    })


def _set_conv_avatar(app, sess, conv, attachment_id, seq):
    return app.dispatch({
        **make_envelope(MessageType.CONVERSATION_AVATAR_UPDATE_REQUEST,
                        correlation_id=f"corr_ca_{seq}",
                        session_id=sess["session_id"],
                        actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"conversation_id": conv, "avatar_attachment_id": attachment_id},
    })


def _profile(app, sess, seq):
    return app.dispatch({
        **make_envelope(MessageType.PROFILE_GET_REQUEST,
                        correlation_id=f"corr_pr_{seq}",
                        session_id=sess["session_id"],
                        actor_user_id=sess["user_id"], sequence=seq),
        "payload": {},
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


def scenario_profile_avatar_round_trip():
    print("[scenario] profile avatar set + clear via profile_response")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    r = _set_profile_avatar(app, alice, "att_avatar_001", 2)
    assert r["type"] == "profile_avatar_update_response", r
    assert r["payload"] == {"user_id": "u_alice", "avatar_attachment_id": "att_avatar_001"}
    p = _profile(app, alice, 3)
    assert p["payload"]["avatar_attachment_id"] == "att_avatar_001", p
    # Clear it.
    r2 = _set_profile_avatar(app, alice, "", 4)
    assert r2["payload"]["avatar_attachment_id"] == ""
    p2 = _profile(app, alice, 5)
    assert p2["payload"]["avatar_attachment_id"] == ""
    print("[ok ] profile avatar set + clear round-trip")


def scenario_conversation_avatar_round_trip():
    print("[scenario] conversation avatar set + clear via sync")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    r = _set_conv_avatar(app, alice, "conv_alice_bob", "att_group_001", 2)
    assert r["type"] == "conversation_avatar_update_response", r
    assert r["payload"]["avatar_attachment_id"] == "att_group_001"
    sync = _sync(app, alice, 3)
    conv = _conv_in_sync(sync, "conv_alice_bob")
    assert conv is not None and conv["avatar_attachment_id"] == "att_group_001", conv
    # Clear.
    _set_conv_avatar(app, alice, "conv_alice_bob", "", 4)
    sync2 = _sync(app, alice, 5)
    assert _conv_in_sync(sync2, "conv_alice_bob")["avatar_attachment_id"] == ""
    print("[ok ] group avatar set + clear surfaces in sync")


def scenario_conv_avatar_non_participant():
    print("[scenario] non-participant updating group avatar -> CONVERSATION_ACCESS_DENIED")
    app = ServerApplication()
    reg = app.dispatch({
        **make_envelope(MessageType.REGISTER_REQUEST, correlation_id="corr_reg", sequence=1),
        "payload": {"username": "carol", "password": "carol_pw",
                    "display_name": "Carol", "device_id": "dev_c"},
    })
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
    r = _set_conv_avatar(app, alice, cb_id, "sneaky", 4)
    assert r["type"] == "error" and r["payload"]["code"] == "conversation_access_denied", r
    print("[ok ] non-participant avatar update rejected")


def scenario_conv_avatar_unknown():
    print("[scenario] avatar update on unknown conversation -> UNKNOWN_CONVERSATION")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    r = _set_conv_avatar(app, alice, "conv_does_not_exist", "att_x", 2)
    assert r["type"] == "error" and r["payload"]["code"] == "unknown_conversation", r
    print("[ok ] unknown conversation rejected")


def main() -> int:
    scenarios = [
        scenario_profile_avatar_round_trip,
        scenario_conversation_avatar_round_trip,
        scenario_conv_avatar_non_participant,
        scenario_conv_avatar_unknown,
    ]
    for s in scenarios:
        s()
    print(f"\nAll {len(scenarios)}/{len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
