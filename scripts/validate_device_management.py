"""Validator for C5 device management flows."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402


def _login(app: ServerApplication, username: str, password: str, device_id: str, seq: int) -> dict:
    resp = app.dispatch(
        {
            **make_envelope(MessageType.LOGIN_REQUEST, correlation_id=f"login_{seq}", sequence=seq),
            "payload": {"username": username, "password": password, "device_id": device_id},
        }
    )
    assert resp["type"] == "login_response", resp
    return resp["payload"]


def _register(app: ServerApplication, username: str, device_id: str, seq: int) -> dict:
    resp = app.dispatch(
        {
            **make_envelope(MessageType.REGISTER_REQUEST, correlation_id=f"reg_{seq}", sequence=seq),
            "payload": {
                "username": username,
                "password": "password_ok",
                "display_name": username.title(),
                "device_id": device_id,
                "device_label": f"{username} device",
                "platform": "windows",
            },
        }
    )
    assert resp["type"] == "register_response", resp
    return resp["payload"]


def _device_list(app: ServerApplication, session: dict, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.DEVICE_LIST_REQUEST,
                correlation_id=f"devices_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {},
        }
    )


def _trust(app: ServerApplication, session: dict, device_id: str, trusted: bool, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.DEVICE_TRUST_UPDATE_REQUEST,
                correlation_id=f"trust_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {"device_id": device_id, "trusted": trusted},
        }
    )


def _revoke(app: ServerApplication, session: dict, device_id: str, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.DEVICE_REVOKE_REQUEST,
                correlation_id=f"revoke_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {"device_id": device_id},
        }
    )


def test_trust_update_and_revoke() -> None:
    app = ServerApplication()
    primary = _register(app, "c5user", "dev_c5_primary", 1)
    secondary = _login(app, "c5user", "password_ok", "dev_c5_primary", 2)
    app.state.devices["dev_c5_secondary"] = app.state.devices["dev_c5_primary"].__class__(
        device_id="dev_c5_secondary",
        user_id=primary["user_id"],
        label="secondary",
        platform="windows",
    )
    app.auth_service.login("c5user", "password_ok", "dev_c5_secondary")

    untrust = _trust(app, secondary, "dev_c5_secondary", False, 3)
    assert untrust["type"] == "device_list_response", untrust
    device = next(d for d in untrust["payload"]["devices"] if d["device_id"] == "dev_c5_secondary")
    assert device["trusted"] is False

    trust = _trust(app, secondary, "dev_c5_secondary", True, 4)
    device = next(d for d in trust["payload"]["devices"] if d["device_id"] == "dev_c5_secondary")
    assert device["trusted"] is True

    revoke = _revoke(app, secondary, "dev_c5_secondary", 5)
    assert revoke["type"] == "device_list_response", revoke
    assert all(s.device_id != "dev_c5_secondary" for s in app.state.sessions.values())


def test_cannot_revoke_current_device() -> None:
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    revoke = _revoke(app, alice, "dev_alice_win", 2)
    assert revoke["type"] == "error", revoke
    assert revoke["payload"]["code"] == "device_action_denied"


def test_device_management_persists_sqlite() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_file = str(Path(tmp) / "runtime.sqlite")
        app = ServerApplication(db_file=db_file)
        alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
        _trust(app, alice, "dev_alice_win", False, 2)
        app2 = ServerApplication(db_file=db_file)
        alice2 = _login(app2, "alice", "alice_pw", "dev_alice_win", 3)
        devices = _device_list(app2, alice2, 4)
        device = next(d for d in devices["payload"]["devices"] if d["device_id"] == "dev_alice_win")
        assert device["trusted"] is False
        del app2
        del app


SCENARIOS = [
    ("trust_update_and_revoke", test_trust_update_and_revoke),
    ("cannot_revoke_current_device", test_cannot_revoke_current_device),
    ("device_management_persists_sqlite", test_device_management_persists_sqlite),
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
