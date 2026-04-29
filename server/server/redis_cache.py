"""Redis hot-state cache bridge with pluggable transport (M111).

Mirrors the pattern established by M91's PushDispatchWorker:
- Default transport is `FakeRedisTransport`, an in-memory dict that satisfies
  the same surface (get / setex / delete) so tests and dev workflows don't
  need a real Redis.
- `RedisHttpTransport` is a stub that knows how to talk to a Redis REST
  gateway (Upstash, AWS API Gateway -> ElastiCache via Lambda, etc.). It is
  gated on PA-011 (Redis endpoint + token) — without those, calls log and
  no-op so callers can still exercise the bridge in dry_run mode.

Cache targets covered by the bridge:
- Presence (per-user online/last_seen) — written on every PRESENCE_UPDATE
  fan-out; read by PresenceQueryService via a `from_cache` fast path.
- Session lookup (per session_id) — written on login, invalidated on logout
  / device revoke; read by the auth path before falling through to
  InMemoryState. This is opt-in: callers wire `state.bind_redis_cache(bridge)`
  to enable it, otherwise nothing changes.

The actual PresenceService / Auth path integration is gated on a separate
opt-in (state.bind_redis_cache) so adopting the bridge doesn't break tests
or the validator sweep.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Optional, Protocol


_LOG = logging.getLogger(__name__)


PRESENCE_TTL_SECONDS = 300
SESSION_TTL_SECONDS = 3600


class RedisTransport(Protocol):
    def get(self, key: str) -> Optional[bytes]: ...
    def setex(self, key: str, ttl_seconds: int, value: bytes) -> None: ...
    def delete(self, key: str) -> None: ...


class FakeRedisTransport:
    """In-memory transport with TTL semantics. Thread-safe."""

    def __init__(self, *, clock=time.monotonic) -> None:
        self._data: dict[str, tuple[float, bytes]] = {}
        self._lock = threading.Lock()
        self._clock = clock

    def get(self, key: str) -> Optional[bytes]:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at <= self._clock():
                del self._data[key]
                return None
            return value

    def setex(self, key: str, ttl_seconds: int, value: bytes) -> None:
        with self._lock:
            self._data[key] = (self._clock() + ttl_seconds, value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    # Test helpers.

    def keys(self) -> list[str]:
        with self._lock:
            return list(self._data.keys())

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


class RedisHttpTransport:
    """Stub for a real Redis REST gateway (Upstash-shaped).

    Every operation is HTTP. Without `dry_run=True` and lacking endpoint /
    token, get/setex/delete raise PermissionError so callers see PA-011 is
    needed. With `dry_run=True` they log + no-op so the bridge can be wired
    end-to-end before procurement.
    """

    def __init__(
        self,
        *,
        endpoint_url: str = "",
        token: str = "",
        dry_run: bool = True,
        logger=_LOG,
    ) -> None:
        self.endpoint_url = endpoint_url
        self.token = token
        self.dry_run = dry_run
        self._log = logger
        self._calls: list[tuple[str, str, int, int]] = []  # (op, key, ttl, len)

    def _check(self, op: str, key: str) -> None:
        if not self.dry_run and (not self.endpoint_url or not self.token):
            raise PermissionError(
                "RedisHttpTransport requires PA-011 (endpoint + token); "
                "run with dry_run=True for now"
            )
        self._log.info("redis.%s key=%s dry_run=%s", op, key, self.dry_run)

    def get(self, key: str) -> Optional[bytes]:
        self._check("get", key)
        self._calls.append(("get", key, 0, 0))
        return None  # cache miss in dry_run

    def setex(self, key: str, ttl_seconds: int, value: bytes) -> None:
        self._check("setex", key)
        self._calls.append(("setex", key, ttl_seconds, len(value)))

    def delete(self, key: str) -> None:
        self._check("delete", key)
        self._calls.append(("delete", key, 0, 0))

    @property
    def calls(self) -> list[tuple[str, str, int, int]]:
        return list(self._calls)


class RedisCacheBridge:
    def __init__(
        self,
        transport: Optional[RedisTransport] = None,
        *,
        presence_ttl: int = PRESENCE_TTL_SECONDS,
        session_ttl: int = SESSION_TTL_SECONDS,
        key_prefix: str = "tg:",
    ) -> None:
        self._transport: RedisTransport = transport or FakeRedisTransport()
        self._presence_ttl = presence_ttl
        self._session_ttl = session_ttl
        self._prefix = key_prefix

    @property
    def transport(self) -> RedisTransport:
        return self._transport

    # ---- presence ----

    def set_presence(self, user_id: str, *, online: bool, last_seen_at_ms: int) -> None:
        body = json.dumps({
            "user_id": user_id,
            "online": online,
            "last_seen_at_ms": last_seen_at_ms,
        }).encode("utf-8")
        self._transport.setex(self._presence_key(user_id), self._presence_ttl, body)

    def get_presence(self, user_id: str) -> Optional[dict]:
        raw = self._transport.get(self._presence_key(user_id))
        if raw is None:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

    def invalidate_presence(self, user_id: str) -> None:
        self._transport.delete(self._presence_key(user_id))

    # ---- session ----

    def set_session(
        self, session_id: str, *, user_id: str, device_id: str, last_seen_at: float
    ) -> None:
        body = json.dumps({
            "session_id": session_id,
            "user_id": user_id,
            "device_id": device_id,
            "last_seen_at": last_seen_at,
        }).encode("utf-8")
        self._transport.setex(self._session_key(session_id), self._session_ttl, body)

    def get_session(self, session_id: str) -> Optional[dict]:
        raw = self._transport.get(self._session_key(session_id))
        if raw is None:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

    def invalidate_session(self, session_id: str) -> None:
        self._transport.delete(self._session_key(session_id))

    # ---- internals ----

    def _presence_key(self, user_id: str) -> str:
        return f"{self._prefix}presence:{user_id}"

    def _session_key(self, session_id: str) -> str:
        return f"{self._prefix}session:{session_id}"
