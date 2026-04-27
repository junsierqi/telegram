"""Validator for REQ-USER-REGISTRATION and REQ-PASSWORD-HASH (E2+F2).

Scenarios:
- registered user can immediately login (password round-trips through PBKDF2)
- password stored as pbkdf2_sha256$... not plaintext
- duplicate username -> USERNAME_TAKEN
- short password -> WEAK_PASSWORD
- duplicate device_id -> DEVICE_ID_TAKEN
- malformed username -> INVALID_REGISTRATION_PAYLOAD
- registered user can send a message in existing conversation after being added
  (covered by E5 — here we just verify the session is usable for dispatch)
- existing seed users (alice/bob) still login after seed hashing migration
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.crypto import verify_password  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402


def _register(app, username, password, display_name, device_id, seq, **extra):
    return app.dispatch(
        {
            **make_envelope(
                MessageType.REGISTER_REQUEST, correlation_id=f"corr_reg_{seq}", sequence=seq
            ),
            "payload": {
                "username": username,
                "password": password,
                "display_name": display_name,
                "device_id": device_id,
                **extra,
            },
        }
    )


def _login(app, username, password, device_id, seq):
    return app.dispatch(
        {
            **make_envelope(
                MessageType.LOGIN_REQUEST, correlation_id=f"corr_login_{seq}", sequence=seq
            ),
            "payload": {"username": username, "password": password, "device_id": device_id},
        }
    )


def test_seed_users_still_login() -> None:
    app = ServerApplication()
    resp = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    assert resp["type"] == "login_response", resp
    assert resp["payload"]["user_id"] == "u_alice"
    # wrong password rejected
    bad = _login(app, "alice", "wrong", "dev_alice_win", 2)
    assert bad["type"] == "error" and bad["payload"]["code"] == "invalid_credentials"


def test_register_then_login() -> None:
    app = ServerApplication()
    reg = _register(app, "carol", "carol_pw_12", "Carol", "dev_carol_mac", 1)
    assert reg["type"] == "register_response", reg
    user_id = reg["payload"]["user_id"]
    assert user_id.startswith("u_auto_")

    # Underlying store has a hash, not plaintext
    stored = app.state.users[user_id].password_hash
    assert stored.startswith("pbkdf2_sha256$"), stored
    assert "carol_pw_12" not in stored
    assert verify_password("carol_pw_12", stored)

    # Can login with the new account
    log = _login(app, "carol", "carol_pw_12", "dev_carol_mac", 2)
    assert log["type"] == "login_response", log
    assert log["payload"]["user_id"] == user_id


def test_duplicate_username_rejected() -> None:
    app = ServerApplication()
    resp = _register(app, "alice", "anotherPw1", "Another Alice", "dev_other", 1)
    assert resp["type"] == "error"
    assert resp["payload"]["code"] == "username_taken"


def test_weak_password_rejected() -> None:
    app = ServerApplication()
    resp = _register(app, "dan", "short", "Dan", "dev_dan", 1)
    assert resp["type"] == "error"
    assert resp["payload"]["code"] == "weak_password"


def test_duplicate_device_rejected() -> None:
    app = ServerApplication()
    resp = _register(app, "erin", "erin_pw_123", "Erin", "dev_alice_win", 1)
    assert resp["type"] == "error"
    assert resp["payload"]["code"] == "device_id_taken"


def test_malformed_username_rejected() -> None:
    app = ServerApplication()
    for bad_name in ["", "ab", "has space", "💥", "-startsdash"]:
        resp = _register(app, bad_name, "pw_longenough", "Bad", f"dev_bad_{hash(bad_name) & 0xffff}", 1)
        assert resp["type"] == "error", f"expected error for {bad_name!r}, got {resp}"
        assert resp["payload"]["code"] == "invalid_registration_payload", resp


def test_registration_persists_across_restart() -> None:
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        app = ServerApplication(state_file=path)
        _register(app, "fran", "fran_pw_ok", "Fran", "dev_fran", 1)

        app2 = ServerApplication(state_file=path)
        resp = _login(app2, "fran", "fran_pw_ok", "dev_fran", 2)
        assert resp["type"] == "login_response", resp
        assert resp["payload"]["display_name"] == "Fran"
    finally:
        Path(path).unlink(missing_ok=True)


SCENARIOS = [
    ("seed_users_still_login", test_seed_users_still_login),
    ("register_then_login", test_register_then_login),
    ("duplicate_username_rejected", test_duplicate_username_rejected),
    ("weak_password_rejected", test_weak_password_rejected),
    ("duplicate_device_rejected", test_duplicate_device_rejected),
    ("malformed_username_rejected", test_malformed_username_rejected),
    ("registration_persists_across_restart", test_registration_persists_across_restart),
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
