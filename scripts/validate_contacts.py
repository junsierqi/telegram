"""Validator for REQ-CONTACTS (E8)."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t


def _login(app, username, password, device_id, seq):
    resp = app.dispatch(
        {
            **make_envelope(MessageType.LOGIN_REQUEST, correlation_id=f"corr_{username}", sequence=seq),
            "payload": {"username": username, "password": password, "device_id": device_id},
        }
    )
    return resp["payload"]


def _add(app, session, target_id, seq, corr=None):
    return app.dispatch(
        {
            **make_envelope(
                MessageType.CONTACT_ADD, correlation_id=corr or f"corr_add_{seq}",
                session_id=session["session_id"], actor_user_id=session["user_id"], sequence=seq,
            ),
            "payload": {"target_user_id": target_id},
        }
    )


def _remove(app, session, target_id, seq, corr=None):
    return app.dispatch(
        {
            **make_envelope(
                MessageType.CONTACT_REMOVE, correlation_id=corr or f"corr_rm_{seq}",
                session_id=session["session_id"], actor_user_id=session["user_id"], sequence=seq,
            ),
            "payload": {"target_user_id": target_id},
        }
    )


def _list(app, session, seq, corr=None):
    return app.dispatch(
        {
            **make_envelope(
                MessageType.CONTACT_LIST_REQUEST, correlation_id=corr or f"corr_list_{seq}",
                session_id=session["session_id"], actor_user_id=session["user_id"], sequence=seq,
            ),
            "payload": {},
        }
    )


def test_add_then_list_shows_contact() -> None:
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    resp = _add(app, alice, "u_bob", seq=2)
    assert resp["type"] == "contact_list_response", resp
    contacts = resp["payload"]["contacts"]
    assert len(contacts) == 1
    assert contacts[0]["user_id"] == "u_bob"
    assert contacts[0]["display_name"] == "Bob"


def test_duplicate_add_rejected() -> None:
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    _add(app, alice, "u_bob", seq=2)
    dup = _add(app, alice, "u_bob", seq=3, corr="corr_dup")
    assert dup["type"] == "error"
    assert dup["payload"]["code"] == "contact_already_added"


def test_self_add_rejected() -> None:
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    resp = _add(app, alice, "u_alice", seq=2, corr="corr_self")
    assert resp["type"] == "error"
    assert resp["payload"]["code"] == "contact_self_not_allowed"


def test_unknown_user_rejected() -> None:
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    resp = _add(app, alice, "u_ghost", seq=2, corr="corr_ghost")
    assert resp["type"] == "error"
    assert resp["payload"]["code"] == "unknown_user"


def test_remove_requires_present() -> None:
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    # remove without having added
    resp = _remove(app, alice, "u_bob", seq=2, corr="corr_missing_rm")
    assert resp["type"] == "error"
    assert resp["payload"]["code"] == "contact_not_present"

    # add then remove works
    _add(app, alice, "u_bob", seq=3)
    ok = _remove(app, alice, "u_bob", seq=4)
    assert ok["type"] == "contact_list_response"
    assert ok["payload"]["contacts"] == []


def test_directed_not_mutual() -> None:
    """Alice adds Bob; Bob's list is empty."""
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    bob = _login(app, "bob", "bob_pw", "dev_bob_win", 2)
    _add(app, alice, "u_bob", seq=3)

    alice_list = _list(app, alice, seq=4)["payload"]["contacts"]
    bob_list = _list(app, bob, seq=5)["payload"]["contacts"]
    assert len(alice_list) == 1 and alice_list[0]["user_id"] == "u_bob"
    assert bob_list == []


def test_online_flag_mirrors_presence_ttl() -> None:
    clock = FakeClock(start=1000.0)
    app = ServerApplication(clock=clock, presence_ttl_seconds=5.0)
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    _login(app, "bob", "bob_pw", "dev_bob_win", 2)
    _add(app, alice, "u_bob", seq=3)

    # freshly logged in — online
    contacts = _list(app, alice, seq=4)["payload"]["contacts"]
    assert contacts[0]["online"] is True

    # advance past TTL — offline
    clock.t += 6.0
    # need to refresh alice's session too or her call errors? AuthService.resolve_session
    # doesn't require freshness; it only checks presence for the target. So alice can still dispatch.
    contacts_stale = _list(app, alice, seq=5)["payload"]["contacts"]
    assert contacts_stale[0]["online"] is False


def test_contacts_persist() -> None:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        app = ServerApplication(state_file=path)
        alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
        _add(app, alice, "u_bob", seq=2)

        app2 = ServerApplication(state_file=path)
        assert app2.state.contacts.get("u_alice") == ["u_bob"]
    finally:
        Path(path).unlink(missing_ok=True)


SCENARIOS = [
    ("add_then_list_shows_contact", test_add_then_list_shows_contact),
    ("duplicate_add_rejected", test_duplicate_add_rejected),
    ("self_add_rejected", test_self_add_rejected),
    ("unknown_user_rejected", test_unknown_user_rejected),
    ("remove_requires_present", test_remove_requires_present),
    ("directed_not_mutual", test_directed_not_mutual),
    ("online_flag_mirrors_presence_ttl", test_online_flag_mirrors_presence_ttl),
    ("contacts_persist", test_contacts_persist),
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
