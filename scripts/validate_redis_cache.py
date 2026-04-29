"""M111 Redis hot-state cache bridge.

Scenarios:
- FakeRedisTransport: presence set/get round-trip, TTL expiry honored,
  invalidate_presence drops the entry.
- FakeRedisTransport: session set/get round-trip + invalidate.
- Bad cached JSON -> get returns None (defensive).
- RedisHttpTransport(dry_run=True): operations log + record calls without
  raising; get returns None (cache miss in dry_run).
- RedisHttpTransport(dry_run=False, no creds) -> PermissionError surfaces
  PA-011 procurement requirement.
- Two threads writing to the same key don't corrupt each other's payloads.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.redis_cache import (  # noqa: E402
    FakeRedisTransport,
    RedisCacheBridge,
    RedisHttpTransport,
)


class _ManualClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


def scenario(label: str) -> None:
    print(f"\n[scenario] {label}")


def run_presence_round_trip() -> None:
    scenario("FakeRedis: presence set/get + TTL expiry + invalidate")
    clock = _ManualClock()
    bridge = RedisCacheBridge(FakeRedisTransport(clock=clock), presence_ttl=60)
    bridge.set_presence("u_alice", online=True, last_seen_at_ms=12345)
    got = bridge.get_presence("u_alice")
    assert got == {"user_id": "u_alice", "online": True, "last_seen_at_ms": 12345}, got
    # Advance past TTL.
    clock.now += 61
    assert bridge.get_presence("u_alice") is None
    # Re-set then invalidate.
    bridge.set_presence("u_alice", online=False, last_seen_at_ms=999)
    bridge.invalidate_presence("u_alice")
    assert bridge.get_presence("u_alice") is None


def run_session_round_trip() -> None:
    scenario("FakeRedis: session set/get + invalidate")
    bridge = RedisCacheBridge(FakeRedisTransport())
    bridge.set_session("sess_42", user_id="u_alice", device_id="dev_1", last_seen_at=12.5)
    got = bridge.get_session("sess_42")
    assert got is not None and got["user_id"] == "u_alice" and got["device_id"] == "dev_1", got
    assert got["last_seen_at"] == 12.5
    bridge.invalidate_session("sess_42")
    assert bridge.get_session("sess_42") is None


def run_bad_cached_json_returns_none() -> None:
    scenario("Corrupted cached payload -> get returns None (defensive)")
    transport = FakeRedisTransport()
    bridge = RedisCacheBridge(transport)
    transport.setex("tg:presence:u_alice", 60, b"\xff\xfe not json")
    assert bridge.get_presence("u_alice") is None


def run_http_transport_dry_run() -> None:
    scenario("RedisHttpTransport(dry_run=True): logs + records, never raises")
    http = RedisHttpTransport(dry_run=True)
    bridge = RedisCacheBridge(http)
    bridge.set_presence("u_bob", online=True, last_seen_at_ms=1)
    bridge.set_session("sess_1", user_id="u_bob", device_id="d", last_seen_at=0.0)
    assert bridge.get_presence("u_bob") is None  # dry_run cache miss
    assert bridge.get_session("sess_1") is None
    bridge.invalidate_session("sess_1")
    ops = [c[0] for c in http.calls]
    assert ops == ["setex", "setex", "get", "get", "delete"], ops


def run_http_transport_missing_creds_raises() -> None:
    scenario("RedisHttpTransport(dry_run=False, no creds) -> PermissionError (PA-011)")
    http = RedisHttpTransport(dry_run=False, endpoint_url="", token="")
    bridge = RedisCacheBridge(http)
    try:
        bridge.set_presence("u_x", online=True, last_seen_at_ms=0)
    except PermissionError as exc:
        assert "PA-011" in str(exc), f"expected PA-011 in error: {exc}"
    else:
        raise AssertionError("expected PermissionError but call returned normally")


def run_concurrent_writes_no_corruption() -> None:
    scenario("Two threads writing different presence entries don't corrupt each other")
    bridge = RedisCacheBridge(FakeRedisTransport())
    n = 200

    def writer(uid: str) -> None:
        for i in range(n):
            bridge.set_presence(uid, online=(i % 2 == 0), last_seen_at_ms=i)

    t1 = threading.Thread(target=writer, args=("u_a",))
    t2 = threading.Thread(target=writer, args=("u_b",))
    t1.start(); t2.start(); t1.join(); t2.join()
    a = bridge.get_presence("u_a")
    b = bridge.get_presence("u_b")
    assert a is not None and a["user_id"] == "u_a"
    assert b is not None and b["user_id"] == "u_b"
    assert a["last_seen_at_ms"] == n - 1
    assert b["last_seen_at_ms"] == n - 1


def main() -> int:
    scenarios = [
        run_presence_round_trip,
        run_session_round_trip,
        run_bad_cached_json_returns_none,
        run_http_transport_dry_run,
        run_http_transport_missing_creds_raises,
        run_concurrent_writes_no_corruption,
    ]
    for fn in scenarios:
        fn()
    print(f"\nAll {len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
