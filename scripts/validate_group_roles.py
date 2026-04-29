"""Validator for per-conversation roles + permission gating (M103).

Scenarios:
  1. Creator becomes owner; sync surfaces roles[creator]="owner".
  2. Owner promotes a member to admin; conversation_sync reflects it.
     Owner demotes back to member; the role entry disappears.
  3. Non-owner trying to set a role -> CONVERSATION_PERMISSION_DENIED.
  4. set_role with role="owner" or "" -> CONVERSATION_INVALID_ROLE.
  5. set_role on the owner -> CONVERSATION_OWNER_ROLE_IMMUTABLE.
  6. add_participant in a >2-member group by a plain member ->
     CONVERSATION_PERMISSION_DENIED. By an admin -> ok.
  7. remove_participant by a non-admin (not self) -> denied. By an
     admin -> ok. Admin trying to remove another admin -> denied (only
     owner can). Owner can remove anyone (except themselves through
     this RPC).
  8. Self-removal (leaving) is always allowed regardless of role.
  9. 1:1 conversations are unaffected — no roles entry; either side
     can still add/remove participants the way they always could.
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


def _register(app, username, seq):
    return app.dispatch({
        **make_envelope(MessageType.REGISTER_REQUEST,
                        correlation_id=f"corr_r_{seq}", sequence=seq),
        "payload": {"username": username, "password": f"{username}_password",
                    "display_name": username.title(),
                    "device_id": f"dev_{username}"},
    })["payload"]


def _create_group(app, sess, others, seq):
    return app.dispatch({
        **make_envelope(MessageType.CONVERSATION_CREATE,
                        correlation_id=f"corr_gc_{seq}",
                        session_id=sess["session_id"],
                        actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"participant_user_ids": others, "title": "G"},
    })


def _set_role(app, sess, conv, target, role, seq):
    return app.dispatch({
        **make_envelope(MessageType.CONVERSATION_ROLE_UPDATE_REQUEST,
                        correlation_id=f"corr_role_{seq}",
                        session_id=sess["session_id"],
                        actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"conversation_id": conv, "target_user_id": target, "role": role},
    })


def _add(app, sess, conv, target, seq):
    return app.dispatch({
        **make_envelope(MessageType.CONVERSATION_ADD_PARTICIPANT,
                        correlation_id=f"corr_a_{seq}",
                        session_id=sess["session_id"],
                        actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"conversation_id": conv, "user_id": target},
    })


def _remove(app, sess, conv, target, seq):
    return app.dispatch({
        **make_envelope(MessageType.CONVERSATION_REMOVE_PARTICIPANT,
                        correlation_id=f"corr_r_{seq}",
                        session_id=sess["session_id"],
                        actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"conversation_id": conv, "user_id": target},
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


def _setup_group_with_three(app):
    """alice as owner; bob, carol as members."""
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    _login(app, "bob", "bob_pw", "dev_b", 2)
    carol = _register(app, "carol", 3)
    create = _create_group(app, alice, ["u_bob", carol["user_id"]], 4)
    return alice, carol, create["payload"]["conversation_id"]


def scenario_creator_is_owner():
    print("[scenario] conversation creator is the owner")
    app = ServerApplication()
    alice, carol, conv_id = _setup_group_with_three(app)
    sync = _sync(app, alice, 5)
    conv = _conv_in_sync(sync, conv_id)
    assert conv["roles"].get("u_alice") == "owner", conv
    # Bob/Carol have no entry -> implicit member.
    assert "u_bob" not in conv["roles"], conv
    print("[ok ] creator owns the conversation")


def scenario_promote_demote():
    print("[scenario] owner promotes + demotes via CONVERSATION_ROLE_UPDATE_REQUEST")
    app = ServerApplication()
    alice, carol, conv_id = _setup_group_with_three(app)
    r1 = _set_role(app, alice, conv_id, "u_bob", "admin", 5)
    assert r1["type"] == "conversation_updated", r1
    assert r1["payload"]["roles"].get("u_bob") == "admin", r1
    r2 = _set_role(app, alice, conv_id, "u_bob", "member", 6)
    assert "u_bob" not in r2["payload"]["roles"], r2
    print("[ok ] promote/demote round-trip")


def scenario_only_owner_sets_role():
    print("[scenario] non-owner setting a role -> CONVERSATION_PERMISSION_DENIED")
    app = ServerApplication()
    alice, carol, conv_id = _setup_group_with_three(app)
    bob = _login(app, "bob", "bob_pw", "dev_b", 5)
    r = _set_role(app, bob, conv_id, "u_alice", "member", 6)
    assert r["type"] == "error" and r["payload"]["code"] == "conversation_permission_denied", r
    print("[ok ] only owner may set roles")


def scenario_invalid_role():
    print("[scenario] role='owner' or '' -> CONVERSATION_INVALID_ROLE")
    app = ServerApplication()
    alice, carol, conv_id = _setup_group_with_three(app)
    r1 = _set_role(app, alice, conv_id, "u_bob", "owner", 5)
    assert r1["type"] == "error" and r1["payload"]["code"] == "conversation_invalid_role", r1
    r2 = _set_role(app, alice, conv_id, "u_bob", "", 6)
    assert r2["type"] == "error" and r2["payload"]["code"] == "conversation_invalid_role", r2
    print("[ok ] invalid role rejected")


def scenario_owner_role_immutable():
    print("[scenario] set_role on the owner -> CONVERSATION_OWNER_ROLE_IMMUTABLE")
    app = ServerApplication()
    alice, carol, conv_id = _setup_group_with_three(app)
    r = _set_role(app, alice, conv_id, "u_alice", "admin", 5)
    assert r["type"] == "error" and r["payload"]["code"] == "conversation_owner_role_immutable", r
    print("[ok ] owner role is immutable")


def scenario_add_remove_gated_by_role():
    print("[scenario] add/remove participant gated by role in groups")
    app = ServerApplication()
    alice, carol, conv_id = _setup_group_with_three(app)
    bob = _login(app, "bob", "bob_pw", "dev_b", 5)
    # Register dave so we have a fresh user to add.
    dave = _register(app, "dave", 6)
    # Bob (plain member) tries to add dave -> denied.
    r = _add(app, bob, conv_id, dave["user_id"], 7)
    assert r["type"] == "error" and r["payload"]["code"] == "conversation_permission_denied", r
    # Owner promotes bob to admin.
    _set_role(app, alice, conv_id, "u_bob", "admin", 8)
    # Now bob can add dave.
    r2 = _add(app, bob, conv_id, dave["user_id"], 9)
    assert r2["type"] == "conversation_updated", r2
    # Carol (still member) tries to remove dave -> denied.
    carol_sess = _login(app, "carol", "carol_password", "dev_carol", 10)
    r3 = _remove(app, carol_sess, conv_id, dave["user_id"], 11)
    assert r3["type"] == "error" and r3["payload"]["code"] == "conversation_permission_denied", r3
    # Bob (admin) can remove dave.
    r4 = _remove(app, bob, conv_id, dave["user_id"], 12)
    assert r4["type"] == "conversation_updated", r4
    print("[ok ] add/remove gated by role")


def scenario_admin_cannot_remove_admin():
    print("[scenario] admin removing another admin -> denied; owner can")
    app = ServerApplication()
    alice, carol, conv_id = _setup_group_with_three(app)
    bob = _login(app, "bob", "bob_pw", "dev_b", 5)
    # Promote both bob and carol to admin.
    _set_role(app, alice, conv_id, "u_bob", "admin", 6)
    _set_role(app, alice, conv_id, carol["user_id"], "admin", 7)
    # Bob (admin) tries to remove carol (admin) -> denied.
    r = _remove(app, bob, conv_id, carol["user_id"], 8)
    assert r["type"] == "error" and r["payload"]["code"] == "conversation_permission_denied", r
    # Owner removes carol -> ok.
    r2 = _remove(app, alice, conv_id, carol["user_id"], 9)
    assert r2["type"] == "conversation_updated", r2
    print("[ok ] admin can't kick admin; owner can")


def scenario_owner_cannot_be_removed():
    print("[scenario] removing the owner via remove_participant -> denied")
    app = ServerApplication()
    alice, carol, conv_id = _setup_group_with_three(app)
    bob = _login(app, "bob", "bob_pw", "dev_b", 5)
    _set_role(app, alice, conv_id, "u_bob", "admin", 6)
    r = _remove(app, bob, conv_id, "u_alice", 7)
    assert r["type"] == "error" and r["payload"]["code"] == "conversation_permission_denied", r
    print("[ok ] owner cannot be kicked")


def scenario_self_removal_always_allowed():
    print("[scenario] anyone can leave (remove themselves)")
    app = ServerApplication()
    alice, carol, conv_id = _setup_group_with_three(app)
    bob = _login(app, "bob", "bob_pw", "dev_b", 5)
    # Bob (plain member) leaves.
    r = _remove(app, bob, conv_id, "u_bob", 6)
    assert r["type"] == "conversation_updated", r
    assert "u_bob" not in r["payload"]["participant_user_ids"], r
    print("[ok ] self-removal allowed")


def scenario_one_on_one_unaffected():
    print("[scenario] 1:1 conversations are not gated by role")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    _login(app, "bob", "bob_pw", "dev_b", 2)
    # conv_alice_bob is a seeded 1:1 with no roles map.
    sync = _sync(app, alice, 3)
    one = _conv_in_sync(sync, "conv_alice_bob")
    assert len(one["participant_user_ids"]) == 2 and one["roles"] == {}, one
    print("[ok ] 1:1 unaffected by M103 (no roles)")


def main() -> int:
    scenarios = [
        scenario_creator_is_owner,
        scenario_promote_demote,
        scenario_only_owner_sets_role,
        scenario_invalid_role,
        scenario_owner_role_immutable,
        scenario_add_remove_gated_by_role,
        scenario_admin_cannot_remove_admin,
        scenario_owner_cannot_be_removed,
        scenario_self_removal_always_allowed,
        scenario_one_on_one_unaffected,
    ]
    for s in scenarios:
        s()
    print(f"\nAll {len(scenarios)}/{len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
