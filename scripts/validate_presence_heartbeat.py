"""Validator for REQ-PRESENCE-HEARTBEAT.

Uses an injected fake clock + short TTL to verify:
- login populates last_seen_at
- is_device_online / is_user_online respect TTL (stale sessions flip offline)
- HEARTBEAT_PING refreshes last_seen_at + returns typed HEARTBEAT_ACK
- PRESENCE_QUERY_REQUEST returns per-user online + last_seen_at_ms
- DEVICE_LIST_RESPONSE.active mirrors presence TTL
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, delta: float) -> None:
        self.t += delta


def _login(app: ServerApplication, username: str, password: str, device_id: str, seq: int) -> dict:
    resp = app.dispatch(
        {
            **make_envelope(MessageType.LOGIN_REQUEST, correlation_id=f"corr_{username}", sequence=seq),
            "payload": {"username": username, "password": password, "device_id": device_id},
        }
    )
    assert resp["type"] == "login_response", resp
    return resp["payload"]


def _heartbeat(app: ServerApplication, session_id: str, user_id: str, seq: int, client_ts: int = 0) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.HEARTBEAT_PING,
                correlation_id=f"corr_hb_{seq}",
                session_id=session_id,
                actor_user_id=user_id,
                sequence=seq,
            ),
            "payload": {"client_timestamp_ms": client_ts},
        }
    )


def _presence_query(app: ServerApplication, session_id: str, user_id: str, ids: list[str], seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.PRESENCE_QUERY_REQUEST,
                correlation_id=f"corr_q_{seq}",
                session_id=session_id,
                actor_user_id=user_id,
                sequence=seq,
            ),
            "payload": {"user_ids": ids},
        }
    )


def _device_list(app: ServerApplication, session_id: str, user_id: str, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.DEVICE_LIST_REQUEST,
                correlation_id=f"corr_dev_{seq}",
                session_id=session_id,
                actor_user_id=user_id,
                sequence=seq,
            ),
            "payload": {},
        }
    )


def test_login_populates_last_seen() -> None:
    clock = FakeClock(start=1000.0)
    app = ServerApplication(clock=clock, presence_ttl_seconds=5.0)
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    session = app.state.sessions[alice["session_id"]]
    assert session.last_seen_at == 1000.0
    assert app.presence_service.is_user_online("u_alice") is True
    assert app.presence_service.is_device_online("dev_alice_win") is True


def test_stale_session_flips_offline() -> None:
    clock = FakeClock(start=1000.0)
    app = ServerApplication(clock=clock, presence_ttl_seconds=5.0)
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    assert app.presence_service.is_user_online("u_alice") is True

    clock.advance(4.9)
    assert app.presence_service.is_user_online("u_alice") is True, "still within TTL"

    clock.advance(0.2)  # 5.1s past login — past 5.0 TTL
    assert app.presence_service.is_user_online("u_alice") is False
    assert app.presence_service.is_device_online("dev_alice_win") is False
    # session record still present, just stale
    assert alice["session_id"] in app.state.sessions


def test_heartbeat_refreshes_last_seen() -> None:
    clock = FakeClock(start=1000.0)
    app = ServerApplication(clock=clock, presence_ttl_seconds=5.0)
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)

    clock.advance(4.0)
    ack = _heartbeat(app, alice["session_id"], alice["user_id"], seq=2, client_ts=999)
    assert ack["type"] == "heartbeat_ack"
    assert ack["payload"]["session_id"] == alice["session_id"]
    assert ack["payload"]["client_timestamp_ms"] == 999
    assert ack["payload"]["server_timestamp_ms"] == 1004000  # (1000+4) * 1000

    # now push past original TTL window — should still be online because heartbeat refreshed
    clock.advance(4.9)  # 8.9s past login, but only 4.9s past heartbeat
    assert app.presence_service.is_user_online("u_alice") is True

    clock.advance(0.2)  # 5.1s past heartbeat
    assert app.presence_service.is_user_online("u_alice") is False


def test_presence_query_returns_typed_status() -> None:
    clock = FakeClock(start=1000.0)
    app = ServerApplication(clock=clock, presence_ttl_seconds=5.0)
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    _login(app, "bob", "bob_pw", "dev_bob_win", 2)

    clock.advance(1.0)
    resp = _presence_query(app, alice["session_id"], alice["user_id"], ["u_alice", "u_bob", "u_ghost"], seq=3)
    assert resp["type"] == "presence_query_response"
    users = resp["payload"]["users"]
    assert len(users) == 3
    by_id = {u["user_id"]: u for u in users}
    assert by_id["u_alice"]["online"] is True
    assert by_id["u_bob"]["online"] is True
    assert by_id["u_ghost"]["online"] is False
    assert by_id["u_ghost"]["last_seen_at_ms"] == 0
    assert by_id["u_alice"]["last_seen_at_ms"] == 1000000  # login time * 1000
    assert resp["payload"]["server_timestamp_ms"] == 1001000


def test_device_list_active_mirrors_ttl() -> None:
    clock = FakeClock(start=1000.0)
    app = ServerApplication(clock=clock, presence_ttl_seconds=5.0)
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)

    resp = _device_list(app, alice["session_id"], alice["user_id"], seq=2)
    assert resp["type"] == "device_list_response"
    devices = resp["payload"]["devices"]
    alice_dev = next(d for d in devices if d["device_id"] == "dev_alice_win")
    assert alice_dev["active"] is True

    clock.advance(6.0)
    resp_after = _device_list(app, alice["session_id"], alice["user_id"], seq=3)
    alice_dev_after = next(d for d in resp_after["payload"]["devices"] if d["device_id"] == "dev_alice_win")
    assert alice_dev_after["active"] is False, f"expected stale device inactive, got {alice_dev_after}"


def test_multi_session_user_online_if_any_fresh() -> None:
    clock = FakeClock(start=1000.0)
    app = ServerApplication(clock=clock, presence_ttl_seconds=5.0)
    alice_a = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    clock.advance(3.0)
    alice_b = _login(app, "alice", "alice_pw", "dev_alice_win", 2)
    assert alice_a["session_id"] != alice_b["session_id"]

    clock.advance(4.0)  # session A is now 7s old (stale), session B is 4s old (fresh)
    assert app.presence_service.is_session_fresh(alice_a["session_id"]) is False
    assert app.presence_service.is_session_fresh(alice_b["session_id"]) is True
    assert app.presence_service.is_user_online("u_alice") is True

    clock.advance(2.0)  # both stale now
    assert app.presence_service.is_user_online("u_alice") is False


SCENARIOS = [
    ("login_populates_last_seen", test_login_populates_last_seen),
    ("stale_session_flips_offline", test_stale_session_flips_offline),
    ("heartbeat_refreshes_last_seen", test_heartbeat_refreshes_last_seen),
    ("presence_query_returns_typed_status", test_presence_query_returns_typed_status),
    ("device_list_active_mirrors_ttl", test_device_list_active_mirrors_ttl),
    ("multi_session_user_online_if_any_fresh", test_multi_session_user_online_if_any_fresh),
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
