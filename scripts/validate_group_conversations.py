"""Validator for REQ-GROUP-CONVERSATIONS (E5).

Uses direct dispatch (no socket) — we only care about service + push semantics
captured in an in-memory ConnectionRegistry stub.
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


def _login(app, username, password, device_id, seq):
    resp = app.dispatch(
        {
            **make_envelope(MessageType.LOGIN_REQUEST, correlation_id=f"corr_{username}", sequence=seq),
            "payload": {"username": username, "password": password, "device_id": device_id},
        }
    )
    assert resp["type"] == "login_response", resp
    return resp["payload"]


def _register(app, username, password, display_name, device_id, seq):
    resp = app.dispatch(
        {
            **make_envelope(MessageType.REGISTER_REQUEST, correlation_id=f"corr_reg_{username}", sequence=seq),
            "payload": {
                "username": username, "password": password,
                "display_name": display_name, "device_id": device_id,
            },
        }
    )
    assert resp["type"] == "register_response", resp
    return resp["payload"]


def _create(app, session, others, title, seq, corr="corr_create"):
    return app.dispatch(
        {
            **make_envelope(
                MessageType.CONVERSATION_CREATE,
                correlation_id=corr,
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {"participant_user_ids": others, "title": title},
        }
    )


def _add(app, session, conv_id, new_uid, seq, corr="corr_add"):
    return app.dispatch(
        {
            **make_envelope(
                MessageType.CONVERSATION_ADD_PARTICIPANT,
                correlation_id=corr,
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {"conversation_id": conv_id, "user_id": new_uid},
        }
    )


def _remove(app, session, conv_id, uid, seq, corr="corr_rm"):
    return app.dispatch(
        {
            **make_envelope(
                MessageType.CONVERSATION_REMOVE_PARTICIPANT,
                correlation_id=corr,
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {"conversation_id": conv_id, "user_id": uid},
        }
    )


def _send_message(app, session, conv_id, text, seq, corr="corr_msg"):
    return app.dispatch(
        {
            **make_envelope(
                MessageType.MESSAGE_SEND,
                correlation_id=corr,
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {"conversation_id": conv_id, "text": text},
        }
    )


def test_create_group_with_three_participants() -> None:
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    _login(app, "bob", "bob_pw", "dev_bob_win", 2)
    carol = _register(app, "carol", "carol_pw_ok", "Carol", "dev_carol_mac", 3)

    resp = _create(app, alice, ["u_bob", carol["user_id"]], "Work Crew", seq=4)
    assert resp["type"] == "conversation_updated", resp
    payload = resp["payload"]
    assert payload["title"] == "Work Crew"
    assert set(payload["participant_user_ids"]) == {"u_alice", "u_bob", carol["user_id"]}
    assert payload["messages"] == []
    assert payload["conversation_id"].startswith("conv_")


def test_create_dedupes_and_rejects_unknown() -> None:
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)

    # Dedupe: same uid twice + creator echoed still yields 2 participants
    _login(app, "bob", "bob_pw", "dev_bob_win", 2)
    resp = _create(app, alice, ["u_bob", "u_bob", "u_alice"], "Dup Test", seq=3)
    assert resp["type"] == "conversation_updated"
    assert sorted(resp["payload"]["participant_user_ids"]) == ["u_alice", "u_bob"]

    # Unknown user id rejected
    bad = _create(app, alice, ["u_ghost"], "Bad", seq=4, corr="corr_bad")
    assert bad["type"] == "error"
    assert bad["payload"]["code"] == "unknown_user"

    # Lonely (only self) rejected
    solo = _create(app, alice, [], "Solo", seq=5, corr="corr_solo")
    assert solo["type"] == "error"
    assert solo["payload"]["code"] == "conversation_too_few_participants"


def test_add_remove_participant_lifecycle() -> None:
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    _login(app, "bob", "bob_pw", "dev_bob_win", 2)
    carol = _register(app, "carol", "carol_pw_ok", "Carol", "dev_carol_mac", 3)

    created = _create(app, alice, ["u_bob"], "Pair", seq=4)
    conv_id = created["payload"]["conversation_id"]

    # add carol
    add_resp = _add(app, alice, conv_id, carol["user_id"], seq=5)
    assert add_resp["type"] == "conversation_updated"
    assert carol["user_id"] in add_resp["payload"]["participant_user_ids"]

    # adding carol again -> already present
    dup = _add(app, alice, conv_id, carol["user_id"], seq=6, corr="corr_dup_add")
    assert dup["type"] == "error"
    assert dup["payload"]["code"] == "conversation_participant_already_present"

    # remove carol
    rm_resp = _remove(app, alice, conv_id, carol["user_id"], seq=7)
    assert rm_resp["type"] == "conversation_updated"
    assert carol["user_id"] not in rm_resp["payload"]["participant_user_ids"]

    # remove unknown -> not present
    miss = _remove(app, alice, conv_id, carol["user_id"], seq=8, corr="corr_miss_rm")
    assert miss["type"] == "error"
    assert miss["payload"]["code"] == "conversation_participant_not_present"


def test_non_participant_cannot_modify() -> None:
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    bob = _login(app, "bob", "bob_pw", "dev_bob_win", 2)
    carol = _register(app, "carol", "carol_pw_ok", "Carol", "dev_carol_mac", 3)

    # alice creates a 2-person convo NOT including bob
    created = _create(app, alice, [carol["user_id"]], "AC", seq=4)
    conv_id = created["payload"]["conversation_id"]

    # bob (non-participant) tries to add someone -> access denied
    bad = _add(app, bob, conv_id, "u_alice", seq=5, corr="corr_bad_add")
    assert bad["type"] == "error"
    assert bad["payload"]["code"] == "conversation_access_denied"


def test_message_fanout_in_group_and_update_push() -> None:
    registry = ConnectionRegistry()
    inbox_alice = Inbox()
    inbox_bob = Inbox()
    inbox_carol = Inbox()

    app = ServerApplication(connection_registry=registry)
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    bob = _login(app, "bob", "bob_pw", "dev_bob_win", 2)
    carol = _register(app, "carol", "carol_pw_ok", "Carol", "dev_carol_mac", 3)

    registry.register(alice["session_id"], inbox_alice.writer)
    registry.register(bob["session_id"], inbox_bob.writer)
    registry.register(carol["session_id"], inbox_carol.writer)

    # alice creates group with bob + carol
    created = _create(app, alice, ["u_bob", carol["user_id"]], "Team", seq=4)
    conv_id = created["payload"]["conversation_id"]

    # bob and carol should receive a CONVERSATION_UPDATED push, alice not
    assert inbox_bob.pop_type("conversation_updated") is not None
    assert inbox_carol.pop_type("conversation_updated") is not None
    assert inbox_alice.pop_type("conversation_updated") is None

    # alice sends a message — bob + carol both receive push
    _send_message(app, alice, conv_id, "hi team", seq=5)
    push_b = inbox_bob.pop_type("message_deliver")
    push_c = inbox_carol.pop_type("message_deliver")
    assert push_b is not None and push_b["payload"]["text"] == "hi team"
    assert push_c is not None and push_c["payload"]["text"] == "hi team"

    # remove carol — carol gets a push even though she's no longer a participant
    _remove(app, alice, conv_id, carol["user_id"], seq=6)
    removed_push = inbox_carol.pop_type("conversation_updated")
    assert removed_push is not None
    assert carol["user_id"] not in removed_push["payload"]["participant_user_ids"]


def test_group_persists_across_restart() -> None:
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        app = ServerApplication(state_file=path)
        alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
        _login(app, "bob", "bob_pw", "dev_bob_win", 2)
        carol = _register(app, "carol", "carol_pw_ok", "Carol", "dev_carol_mac", 3)
        created = _create(app, alice, ["u_bob", carol["user_id"]], "Persist", seq=4)
        conv_id = created["payload"]["conversation_id"]
        _send_message(app, alice, conv_id, "hello", seq=5)

        # restart
        app2 = ServerApplication(state_file=path)
        record = app2.state.conversations[conv_id]
        assert record.title == "Persist"
        assert set(record.participant_user_ids) == {"u_alice", "u_bob", carol["user_id"]}
        assert len(record.messages) == 1
    finally:
        Path(path).unlink(missing_ok=True)


SCENARIOS = [
    ("create_group_with_three_participants", test_create_group_with_three_participants),
    ("create_dedupes_and_rejects_unknown", test_create_dedupes_and_rejects_unknown),
    ("add_remove_participant_lifecycle", test_add_remove_participant_lifecycle),
    ("non_participant_cannot_modify", test_non_participant_cannot_modify),
    ("message_fanout_in_group_and_update_push", test_message_fanout_in_group_and_update_push),
    ("group_persists_across_restart", test_group_persists_across_restart),
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
