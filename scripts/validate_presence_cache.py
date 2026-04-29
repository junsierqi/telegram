"""M116 PresenceService <-> RedisCacheBridge integration.

Scenarios:
- No cache bound: PresenceService behaves exactly as pre-M116 (regression
  guard: same shape returned by query_users).
- Cache bound, miss -> compute -> cache write: first query writes a
  presence entry to the FakeRedisTransport keyed by tg:presence:<user_id>;
  second query reads it back without scanning sessions.
- touch refreshes the cache (last_seen_at_ms advances even though state is
  not re-scanned by the second query).
- notify_session_started writes a fresh cache entry (no stale offline).
- revoke_device invalidates the cached entry; next query recomputes.
- Cache TTL is bounded by presence TTL (cached entry expires when the
  underlying session would have gone stale).
- Transport throwing on get/set doesn't break the dispatch path: fall back
  to a state scan + don't propagate.
- ServerApplication kwarg propagates the bridge into PresenceService.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402
from server.server.redis_cache import (  # noqa: E402
    FakeRedisTransport,
    RedisCacheBridge,
)
from server.server.services.presence import PresenceService  # noqa: E402
from server.server.state import InMemoryState, SessionRecord  # noqa: E402


class _ManualClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


def _seed_session(state: InMemoryState, *, sid: str, user_id: str, device_id: str, last_seen_at: float) -> None:
    state.sessions[sid] = SessionRecord(
        session_id=sid,
        user_id=user_id,
        device_id=device_id,
        last_seen_at=last_seen_at,
    )


def scenario(label: str) -> None:
    print(f"\n[scenario] {label}")


def run_no_cache_regression() -> None:
    scenario("No cache bound -> behaves exactly as pre-M116")
    state = InMemoryState()
    clock = _ManualClock()
    svc = PresenceService(state, clock=clock, ttl_seconds=30)
    _seed_session(state, sid="s1", user_id="u_a", device_id="d_a", last_seen_at=clock.now)
    assert svc.is_user_online("u_a") is True
    assert svc.last_seen_ms("u_a") == int(clock.now * 1000)
    # Stale: advance clock past TTL
    clock.now += 60
    assert svc.is_user_online("u_a") is False


def run_cache_miss_then_hit() -> None:
    scenario("First query misses + writes cache; second query hits cache")
    state = InMemoryState()
    transport = FakeRedisTransport()
    bridge = RedisCacheBridge(transport)
    clock = _ManualClock()
    svc = PresenceService(state, clock=clock, ttl_seconds=30, redis_cache=bridge)
    _seed_session(state, sid="s1", user_id="u_a", device_id="d_a", last_seen_at=clock.now)

    assert "tg:presence:u_a" not in transport.keys()
    online1 = svc.is_user_online("u_a")
    assert online1 is True
    assert "tg:presence:u_a" in transport.keys(), transport.keys()

    # Replace the underlying state with a stale session — without cache the
    # answer would flip to offline, but the cache hit must short-circuit.
    state.sessions.clear()
    online2 = svc.is_user_online("u_a")
    assert online2 is True, "expected cached online answer to win"


def run_touch_refreshes_cache() -> None:
    scenario("touch updates the cached last_seen_at_ms in-place")
    state = InMemoryState()
    transport = FakeRedisTransport()
    bridge = RedisCacheBridge(transport)
    clock = _ManualClock()
    svc = PresenceService(state, clock=clock, ttl_seconds=30, redis_cache=bridge)
    _seed_session(state, sid="s1", user_id="u_a", device_id="d_a", last_seen_at=clock.now)
    svc.is_user_online("u_a")  # populate cache
    initial_last_seen = svc.last_seen_ms("u_a")

    clock.now += 5
    svc.touch("s1")
    refreshed = bridge.get_presence("u_a")
    assert refreshed is not None and refreshed["last_seen_at_ms"] == int(clock.now * 1000), refreshed
    assert refreshed["last_seen_at_ms"] > initial_last_seen


def run_notify_session_started_writes_cache() -> None:
    scenario("notify_session_started writes a fresh online entry")
    state = InMemoryState()
    transport = FakeRedisTransport()
    bridge = RedisCacheBridge(transport)
    clock = _ManualClock()
    # Pre-seed cache with stale offline so we can verify it's overwritten.
    bridge.set_presence("u_a", online=False, last_seen_at_ms=0)
    svc = PresenceService(state, clock=clock, ttl_seconds=30, redis_cache=bridge)
    _seed_session(state, sid="s1", user_id="u_a", device_id="d_a", last_seen_at=clock.now)
    svc.notify_session_started("s1")
    cached = bridge.get_presence("u_a")
    assert cached == {
        "user_id": "u_a",
        "online": True,
        "last_seen_at_ms": int(clock.now * 1000),
    }, cached


def run_revoke_device_invalidates_cache() -> None:
    scenario("revoke_device clears the cached entry")
    state = InMemoryState()
    transport = FakeRedisTransport()
    bridge = RedisCacheBridge(transport)
    clock = _ManualClock()
    # Seed a device + two sessions for the user
    from server.server.state import DeviceRecord, UserRecord
    state.users["u_a"] = UserRecord(user_id="u_a", username="alice", display_name="A", password_hash="x")
    state.devices["d_other"] = DeviceRecord(
        device_id="d_other", user_id="u_a", label="other", platform="x",
        trusted=False, active=True, can_host=False, can_view=False,
    )
    state.devices["d_target"] = DeviceRecord(
        device_id="d_target", user_id="u_a", label="target", platform="x",
        trusted=False, active=True, can_host=False, can_view=False,
    )
    _seed_session(state, sid="s_other", user_id="u_a", device_id="d_other", last_seen_at=clock.now)
    _seed_session(state, sid="s_target", user_id="u_a", device_id="d_target", last_seen_at=clock.now)
    svc = PresenceService(state, clock=clock, ttl_seconds=30, redis_cache=bridge)
    svc.is_user_online("u_a")  # populate cache with the real online answer
    assert "tg:presence:u_a" in transport.keys()

    # Revoke d_target while logged in via s_other (so DEVICE_ACTION_DENIED
    # doesn't fire). revoke_device internally calls _invalidate_cache; the
    # post-revoke transition check re-runs is_user_online which recomputes
    # from the trimmed state and writes the fresh value back. Net effect:
    # cache is refreshed (not absent), and the value matches the recomputed
    # state.
    svc.revoke_device("u_a", current_session_id="s_other", device_id="d_target")
    refreshed = bridge.get_presence("u_a")
    assert refreshed is not None and refreshed["online"] is True, (
        "expected cache to be refreshed with fresh state after revoke",
        refreshed,
    )

    # Now prove the *invalidation* itself happened: clear sessions, manually
    # invalidate via revoke (no other user touches the cache), then a fresh
    # query must recompute from the now-empty state and return offline. This
    # is what catches a regression where _invalidate_cache stops firing.
    state.sessions.clear()
    bridge.set_presence("u_a", online=True, last_seen_at_ms=999_999_999)  # stale
    state.devices["d_target"].active = True  # so revoke can run again
    state.devices["d_other"].active = True
    _seed_session(state, sid="s_keep", user_id="u_a", device_id="d_other", last_seen_at=clock.now)
    _seed_session(state, sid="s_drop", user_id="u_a", device_id="d_target", last_seen_at=clock.now)
    svc.revoke_device("u_a", current_session_id="s_keep", device_id="d_target")
    after = bridge.get_presence("u_a")
    assert after is not None and after["last_seen_at_ms"] == int(clock.now * 1000), (
        "cache must reflect post-revoke state, not the pre-poisoned 999_999_999",
        after,
    )


def run_cache_ttl_bounded_by_presence_ttl() -> None:
    scenario("Cache TTL = presence TTL; expired cache forces a recompute")
    state = InMemoryState()
    cache_clock = _ManualClock()
    # Wire FakeRedis to the same clock so its TTL semantics line up.
    transport = FakeRedisTransport(clock=cache_clock)
    bridge = RedisCacheBridge(transport)
    presence_clock = _ManualClock()
    svc = PresenceService(state, clock=presence_clock, ttl_seconds=10, redis_cache=bridge)
    _seed_session(state, sid="s1", user_id="u_a", device_id="d_a", last_seen_at=presence_clock.now)
    svc.is_user_online("u_a")  # populate cache (TTL=10s in cache)

    # Cache key still present at +5s
    cache_clock.now += 5
    assert transport.get("tg:presence:u_a") is not None

    # Cache expired at +11s; FakeRedis.get returns None on TTL miss.
    cache_clock.now += 6
    assert transport.get("tg:presence:u_a") is None

    # Replace state to confirm a fresh recompute happens.
    state.sessions.clear()
    presence_clock.now += 11
    assert svc.is_user_online("u_a") is False


class _BoomTransport:
    def get(self, key):
        raise RuntimeError("transport down")

    def setex(self, key, ttl, value):
        raise RuntimeError("transport down")

    def delete(self, key):
        raise RuntimeError("transport down")


def run_transport_failure_falls_back() -> None:
    scenario("Transport raising on every op falls back to state-scan + no propagation")
    state = InMemoryState()
    bridge = RedisCacheBridge(_BoomTransport())
    clock = _ManualClock()
    svc = PresenceService(state, clock=clock, ttl_seconds=30, redis_cache=bridge)
    _seed_session(state, sid="s1", user_id="u_a", device_id="d_a", last_seen_at=clock.now)
    # All these must succeed (the cache misbehaves but the dispatch path
    # must keep working).
    assert svc.is_user_online("u_a") is True
    assert svc.last_seen_ms("u_a") == int(clock.now * 1000)
    svc.touch("s1")
    svc.notify_session_started("s1")


def run_server_application_propagates_cache() -> None:
    scenario("ServerApplication(redis_cache=...) wires the bridge into PresenceService")
    transport = FakeRedisTransport()
    bridge = RedisCacheBridge(transport)
    app = ServerApplication(redis_cache=bridge)
    # Login alice so a session exists.
    resp = app.dispatch({
        **make_envelope(MessageType.LOGIN_REQUEST, correlation_id="c", sequence=1),
        "payload": {"username": "alice", "password": "alice_pw", "device_id": "dev_alice_cache"},
    })
    assert resp["payload"]["user_id"] == "u_alice"
    # query presence -> cache populated.
    online = app.presence_service.is_user_online("u_alice")
    assert online is True
    assert "tg:presence:u_alice" in transport.keys(), transport.keys()


def main() -> int:
    scenarios = [
        run_no_cache_regression,
        run_cache_miss_then_hit,
        run_touch_refreshes_cache,
        run_notify_session_started_writes_cache,
        run_revoke_device_invalidates_cache,
        run_cache_ttl_bounded_by_presence_ttl,
        run_transport_failure_falls_back,
        run_server_application_propagates_cache,
    ]
    for fn in scenarios:
        fn()
    print(f"\nAll {len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
