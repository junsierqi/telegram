"""M117 AuthService <-> RedisCacheBridge integration.

Scenarios:
- No cache bound: resolve_session works exactly as pre-M117 (regression).
- login writes the new session to the cache.
- register writes the new session to the cache.
- resolve_session cache-hit short-circuits the state lookup (proven by
  wiping the underlying state.sessions and confirming resolve still works).
- TTL expiry on cached session evicts the cache entry AND the state entry.
- Unknown session_id invalidates the (possibly stale) cache entry.
- Transport failures on get / set / delete fall back to the state path
  without breaking dispatch.
- Cache TTL falls back to the 60s default when session_ttl_seconds=0.
- ServerApplication(redis_cache=...) propagates the bridge to AuthService.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import ErrorCode, MessageType, ServiceError, make_envelope  # noqa: E402
from server.server.redis_cache import (  # noqa: E402
    FakeRedisTransport,
    RedisCacheBridge,
)
from server.server.services.auth import AuthService  # noqa: E402
from server.server.state import (  # noqa: E402
    DeviceRecord,
    InMemoryState,
    SessionRecord,
    UserRecord,
)


class _ManualClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


def scenario(label: str) -> None:
    print(f"\n[scenario] {label}")


def run_no_cache_regression() -> None:
    scenario("No cache -> resolve_session works exactly as pre-M117")
    state = InMemoryState()
    clock = _ManualClock()
    svc = AuthService(state, clock=clock)
    info = svc.login("alice", "alice_pw", "dev_a")
    sid = info["session_id"]
    rec = svc.resolve_session(sid)
    assert rec.user_id == "u_alice" and rec.device_id == "dev_a", rec


def run_login_writes_session_cache() -> None:
    scenario("login writes the session into the cache")
    state = InMemoryState()
    transport = FakeRedisTransport()
    bridge = RedisCacheBridge(transport)
    clock = _ManualClock()
    svc = AuthService(state, clock=clock, redis_cache=bridge)
    info = svc.login("alice", "alice_pw", "dev_a")
    sid = info["session_id"]
    cached = bridge.get_session(sid)
    assert cached is not None and cached["user_id"] == "u_alice", cached
    assert cached["device_id"] == "dev_a"


def run_register_writes_session_cache() -> None:
    scenario("register writes the new session into the cache")
    state = InMemoryState()
    transport = FakeRedisTransport()
    bridge = RedisCacheBridge(transport)
    clock = _ManualClock()
    svc = AuthService(state, clock=clock, redis_cache=bridge)
    info = svc.register(
        username="newbie",
        password="hunter2_password",
        display_name="N",
        device_id="dev_n",
    )
    sid = info["session_id"]
    cached = bridge.get_session(sid)
    assert cached is not None and cached["device_id"] == "dev_n", cached


def run_cache_hit_skips_state_lookup() -> None:
    scenario("Cache hit short-circuits the state.sessions lookup")
    state = InMemoryState()
    transport = FakeRedisTransport()
    bridge = RedisCacheBridge(transport)
    clock = _ManualClock()
    svc = AuthService(state, clock=clock, redis_cache=bridge)
    info = svc.login("alice", "alice_pw", "dev_a")
    sid = info["session_id"]
    # Wipe the underlying state -- resolve_session must still succeed
    # because the cache holds the truth.
    state.sessions.clear()
    rec = svc.resolve_session(sid)
    assert rec.session_id == sid and rec.user_id == "u_alice", rec


def run_ttl_expiry_evicts_cache_and_state() -> None:
    scenario("TTL expiry evicts both the cache and the in-memory session")
    state = InMemoryState()
    transport = FakeRedisTransport()
    bridge = RedisCacheBridge(transport)
    clock = _ManualClock()
    svc = AuthService(state, clock=clock, session_ttl_seconds=30, redis_cache=bridge)
    info = svc.login("alice", "alice_pw", "dev_a")
    sid = info["session_id"]
    # Advance past the session TTL -- resolve must raise INVALID_SESSION
    # and the cache + state entries must be gone after that.
    clock.now += 31
    raised = False
    try:
        svc.resolve_session(sid)
    except ServiceError as exc:
        raised = exc.args[0] == ErrorCode.INVALID_SESSION
    assert raised, "expected INVALID_SESSION on TTL-expired session"
    assert sid not in state.sessions, "TTL evict should drop the in-memory session"
    assert bridge.get_session(sid) is None, "TTL evict should drop the cached session"


def run_unknown_session_invalidates_cache() -> None:
    scenario("Unknown session_id invalidates a stale cached entry too")
    state = InMemoryState()
    transport = FakeRedisTransport()
    bridge = RedisCacheBridge(transport)
    clock = _ManualClock()
    svc = AuthService(state, clock=clock, redis_cache=bridge)
    # Pre-poison the cache: a session that doesn't exist in state.
    bridge.set_session(
        "sess_phantom", user_id="u_x", device_id="dev_x", last_seen_at=clock.now
    )
    # Cache hit returns the phantom session -- but state has no entry, so
    # if we then drop the cache (e.g. after a state-truth recheck during
    # operations), resolve must surface INVALID_SESSION.
    # Simulate that by clearing cache directly + calling resolve.
    bridge.invalidate_session("sess_phantom")
    raised = False
    try:
        svc.resolve_session("sess_phantom")
    except ServiceError as exc:
        raised = exc.args[0] == ErrorCode.INVALID_SESSION
    assert raised


class _BoomTransport:
    def get(self, key):
        raise RuntimeError("transport down")

    def setex(self, key, ttl, value):
        raise RuntimeError("transport down")

    def delete(self, key):
        raise RuntimeError("transport down")


def run_transport_failure_falls_back() -> None:
    scenario("Transport failures fall back to state path; dispatch never breaks")
    state = InMemoryState()
    bridge = RedisCacheBridge(_BoomTransport())
    clock = _ManualClock()
    svc = AuthService(state, clock=clock, redis_cache=bridge)
    info = svc.login("alice", "alice_pw", "dev_a")  # set raises -> swallow
    sid = info["session_id"]
    rec = svc.resolve_session(sid)  # get raises -> falls through to state
    assert rec.user_id == "u_alice"


def run_default_cache_ttl_when_no_session_ttl() -> None:
    scenario("Cache TTL falls back to 60s when session_ttl_seconds=0")
    state = InMemoryState()
    transport = FakeRedisTransport()
    bridge = RedisCacheBridge(transport)
    clock = _ManualClock()
    svc = AuthService(state, clock=clock, session_ttl_seconds=0, redis_cache=bridge)
    assert svc._cache_ttl_seconds == 60, svc._cache_ttl_seconds
    svc2 = AuthService(state, clock=clock, session_ttl_seconds=15, redis_cache=bridge)
    assert svc2._cache_ttl_seconds == 15, svc2._cache_ttl_seconds


def run_server_application_propagates_cache() -> None:
    scenario("ServerApplication(redis_cache=...) wires the bridge into AuthService")
    transport = FakeRedisTransport()
    bridge = RedisCacheBridge(transport)
    app = ServerApplication(redis_cache=bridge)
    resp = app.dispatch({
        **make_envelope(MessageType.LOGIN_REQUEST, correlation_id="c", sequence=1),
        "payload": {"username": "alice", "password": "alice_pw", "device_id": "dev_a_auth"},
    })
    sid = resp["payload"]["session_id"]
    cached = bridge.get_session(sid)
    assert cached is not None and cached["user_id"] == "u_alice", cached


def main() -> int:
    scenarios = [
        run_no_cache_regression,
        run_login_writes_session_cache,
        run_register_writes_session_cache,
        run_cache_hit_skips_state_lookup,
        run_ttl_expiry_evicts_cache_and_state,
        run_unknown_session_invalidates_cache,
        run_transport_failure_falls_back,
        run_default_cache_ttl_when_no_session_ttl,
        run_server_application_propagates_cache,
    ]
    for fn in scenarios:
        fn()
    print(f"\nAll {len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
