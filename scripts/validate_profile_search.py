"""Validator for profile/account and user discovery."""
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


def _login(app: ServerApplication, username: str, password: str, device_id: str, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(MessageType.LOGIN_REQUEST, correlation_id=f"login_{seq}", sequence=seq),
            "payload": {"username": username, "password": password, "device_id": device_id},
        }
    )["payload"]


def _profile_get(app: ServerApplication, session: dict, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.PROFILE_GET_REQUEST,
                correlation_id=f"profile_get_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {},
        }
    )


def _profile_update(app: ServerApplication, session: dict, display_name: str, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.PROFILE_UPDATE_REQUEST,
                correlation_id=f"profile_update_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {"display_name": display_name},
        }
    )


def _search(app: ServerApplication, session: dict, query: str, seq: int, limit: int = 20) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.USER_SEARCH_REQUEST,
                correlation_id=f"user_search_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {"query": query, "limit": limit},
        }
    )


def _add_contact(app: ServerApplication, session: dict, target_user_id: str, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.CONTACT_ADD,
                correlation_id=f"contact_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {"target_user_id": target_user_id},
        }
    )


def test_profile_get_and_update() -> None:
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    before = _profile_get(app, alice, 2)
    assert before["type"] == "profile_response", before
    assert before["payload"]["username"] == "alice"
    assert before["payload"]["display_name"] == "Alice"

    updated = _profile_update(app, alice, "Alice Updated", 3)
    assert updated["type"] == "profile_response", updated
    assert updated["payload"]["display_name"] == "Alice Updated"
    assert app.state.users["u_alice"].display_name == "Alice Updated"


def test_profile_update_validates_display_name() -> None:
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    empty = _profile_update(app, alice, "   ", 2)
    assert empty["type"] == "error"
    assert empty["payload"]["code"] == "invalid_registration_payload"
    too_long = _profile_update(app, alice, "x" * 65, 3)
    assert too_long["type"] == "error"
    assert too_long["payload"]["code"] == "invalid_registration_payload"


def test_user_search_finds_username_display_and_excludes_self() -> None:
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    resp = _search(app, alice, "bo", 2)
    assert resp["type"] == "user_search_response", resp
    results = resp["payload"]["results"]
    assert [item["user_id"] for item in results] == ["u_bob"]
    assert results[0]["username"] == "bob"
    assert results[0]["display_name"] == "Bob"
    assert results[0]["is_contact"] is False

    self_resp = _search(app, alice, "alice", 3)
    assert self_resp["type"] == "user_search_response"
    assert self_resp["payload"]["results"] == []


def test_user_search_contact_and_online_flags() -> None:
    clock = FakeClock()
    app = ServerApplication(clock=clock, presence_ttl_seconds=5.0)
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    _login(app, "bob", "bob_pw", "dev_bob_win", 2)
    _add_contact(app, alice, "u_bob", 3)

    online = _search(app, alice, "bob", 4)
    result = online["payload"]["results"][0]
    assert result["is_contact"] is True
    assert result["online"] is True

    clock.t += 6.0
    offline = _search(app, alice, "bob", 5)
    assert offline["payload"]["results"][0]["online"] is False


def test_profile_update_persists_json_state() -> None:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        app = ServerApplication(state_file=path)
        alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
        _profile_update(app, alice, "Alice Persistent", 2)

        app2 = ServerApplication(state_file=path)
        assert app2.state.users["u_alice"].display_name == "Alice Persistent"
    finally:
        Path(path).unlink(missing_ok=True)


SCENARIOS = [
    ("profile_get_and_update", test_profile_get_and_update),
    ("profile_update_validates_display_name", test_profile_update_validates_display_name),
    ("user_search_finds_username_display_and_excludes_self", test_user_search_finds_username_display_and_excludes_self),
    ("user_search_contact_and_online_flags", test_user_search_contact_and_online_flags),
    ("profile_update_persists_json_state", test_profile_update_persists_json_state),
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
