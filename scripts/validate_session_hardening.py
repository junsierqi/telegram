"""Validator for production session hardening."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def login(app: ServerApplication, seq: int) -> dict:
    response = app.dispatch(
        {
            **make_envelope(MessageType.LOGIN_REQUEST, correlation_id=f"login_{seq}", sequence=seq),
            "payload": {
                "username": "alice",
                "password": "alice_pw",
                "device_id": "dev_alice_win",
            },
        }
    )
    assert response["type"] == "login_response", response
    return response["payload"]


def sync(app: ServerApplication, session: dict, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.CONVERSATION_SYNC,
                correlation_id=f"sync_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {},
        }
    )


def heartbeat(app: ServerApplication, session: dict, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.HEARTBEAT_PING,
                correlation_id=f"heartbeat_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {"client_timestamp_ms": 0},
        }
    )


def test_session_expires_after_configured_ttl() -> None:
    clock = FakeClock()
    app = ServerApplication(clock=clock, session_ttl_seconds=5)
    session = login(app, 1)
    assert sync(app, session, 2)["type"] == "conversation_sync"
    clock.advance(6)
    expired = sync(app, session, 3)
    assert expired["type"] == "error", expired
    assert expired["payload"]["code"] == "invalid_session", expired
    assert session["session_id"] not in app.state.sessions


def test_heartbeat_refreshes_session_age() -> None:
    clock = FakeClock()
    app = ServerApplication(clock=clock, session_ttl_seconds=5)
    session = login(app, 1)
    clock.advance(4)
    refreshed = heartbeat(app, session, 2)
    assert refreshed["type"] == "heartbeat_ack", refreshed
    clock.advance(4)
    assert sync(app, session, 3)["type"] == "conversation_sync"


def test_zero_ttl_keeps_legacy_sessions_enabled() -> None:
    clock = FakeClock()
    app = ServerApplication(clock=clock, session_ttl_seconds=0)
    session = login(app, 1)
    clock.advance(365 * 24 * 60 * 60)
    assert sync(app, session, 2)["type"] == "conversation_sync"


SCENARIOS = [
    ("session_expires_after_configured_ttl", test_session_expires_after_configured_ttl),
    ("heartbeat_refreshes_session_age", test_heartbeat_refreshes_session_age),
    ("zero_ttl_keeps_legacy_sessions_enabled", test_zero_ttl_keeps_legacy_sessions_enabled),
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
