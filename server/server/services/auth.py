from __future__ import annotations

import re
import time
from typing import Callable, Optional, TYPE_CHECKING

from ..crypto import hash_password, verify_password
from ..protocol import ErrorCode, ServiceError
from ..state import DeviceRecord, InMemoryState, SessionRecord, UserRecord

if TYPE_CHECKING:
    from ..redis_cache import RedisCacheBridge


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{2,31}$")
MIN_PASSWORD_LENGTH = 8

# Cap the auth-cache TTL even when the operator hasn't configured an explicit
# session_ttl_seconds (which defaults to 0 = "no expiry"). Without a cap the
# cached entry would survive forever and miss touch-driven last_seen updates
# on other replicas; 60s gives a small but bounded staleness window.
_DEFAULT_AUTH_CACHE_TTL_SECONDS = 60


class AuthService:
    def __init__(
        self,
        state: InMemoryState,
        *,
        clock: Callable[[], float] | None = None,
        session_ttl_seconds: float = 0.0,
        redis_cache: "Optional[RedisCacheBridge]" = None,
    ) -> None:
        self._state = state
        self._clock = clock or time.time
        self._session_ttl_seconds = max(0.0, float(session_ttl_seconds))
        self._session_counter = self._next_session_counter()
        self._user_counter = self._next_user_counter()
        # M117: optional Redis hot-state cache. When set, resolve_session
        # checks the cache first; login / register write through; the TTL
        # eviction path invalidates. Without it, behaviour is identical to
        # pre-M117.
        self._cache = redis_cache

    def bind_redis_cache(self, cache: "Optional[RedisCacheBridge]") -> None:
        self._cache = cache

    @property
    def _cache_ttl_seconds(self) -> int:
        if self._session_ttl_seconds > 0:
            return max(1, int(self._session_ttl_seconds))
        return _DEFAULT_AUTH_CACHE_TTL_SECONDS

    def _next_session_counter(self) -> int:
        highest = 0
        for session_id in self._state.sessions:
            if not session_id.startswith("sess_"):
                continue
            try:
                highest = max(highest, int(session_id.removeprefix("sess_")))
            except ValueError:
                continue
        return highest + 1

    def _next_user_counter(self) -> int:
        highest = 0
        for user_id in self._state.users:
            if not user_id.startswith("u_auto_"):
                continue
            try:
                highest = max(highest, int(user_id.removeprefix("u_auto_")))
            except ValueError:
                continue
        return highest + 1

    def describe(self) -> str:
        return "auth service ready for credential validation, token issue and trusted devices"

    def login(self, username: str, password: str, device_id: str) -> dict[str, str]:
        for user in self._state.users.values():
            if user.username != username:
                continue
            if not verify_password(password, user.password_hash):
                raise ServiceError(ErrorCode.INVALID_CREDENTIALS)
            existing_device = self._state.devices.get(device_id)
            if existing_device is not None and existing_device.user_id != user.user_id:
                raise ServiceError(ErrorCode.DEVICE_ID_TAKEN)
            if existing_device is None:
                self._state.devices[device_id] = DeviceRecord(
                    device_id=device_id,
                    user_id=user.user_id,
                    label=device_id,
                    platform="unknown",
                )

            session_id = f"sess_{self._session_counter}"
            self._session_counter += 1
            now = self._clock()
            self._state.sessions[session_id] = SessionRecord(
                session_id=session_id,
                user_id=user.user_id,
                device_id=device_id,
                last_seen_at=now,
            )
            if existing_device is None:
                self._state.save_runtime_state()
            else:
                self._state.persist_session(self._state.sessions[session_id])
            self._write_session_cache(session_id, user.user_id, device_id, now)
            return {
                "session_id": session_id,
                "user_id": user.user_id,
                "display_name": user.display_name,
                "device_id": device_id,
            }

        raise ServiceError(ErrorCode.INVALID_CREDENTIALS)

    def register(
        self,
        *,
        username: str,
        password: str,
        display_name: str,
        device_id: str,
        device_label: str = "",
        platform: str = "unknown",
    ) -> dict[str, str]:
        if not USERNAME_PATTERN.match(username):
            raise ServiceError(ErrorCode.INVALID_REGISTRATION_PAYLOAD)
        if len(password) < MIN_PASSWORD_LENGTH:
            raise ServiceError(ErrorCode.WEAK_PASSWORD)
        if not display_name.strip():
            raise ServiceError(ErrorCode.INVALID_REGISTRATION_PAYLOAD)
        if not device_id.strip():
            raise ServiceError(ErrorCode.INVALID_REGISTRATION_PAYLOAD)

        for existing in self._state.users.values():
            if existing.username.lower() == username.lower():
                raise ServiceError(ErrorCode.USERNAME_TAKEN)
        if device_id in self._state.devices:
            raise ServiceError(ErrorCode.DEVICE_ID_TAKEN)

        user_id = f"u_auto_{self._user_counter}"
        self._user_counter += 1
        self._state.users[user_id] = UserRecord(
            user_id=user_id,
            username=username,
            password_hash=hash_password(password),
            display_name=display_name,
        )
        self._state.devices[device_id] = DeviceRecord(
            device_id=device_id,
            user_id=user_id,
            label=device_label or username,
            platform=platform,
        )

        session_id = f"sess_{self._session_counter}"
        self._session_counter += 1
        now = self._clock()
        self._state.sessions[session_id] = SessionRecord(
            session_id=session_id,
            user_id=user_id,
            device_id=device_id,
            last_seen_at=now,
        )
        self._state.save_runtime_state()
        self._write_session_cache(session_id, user_id, device_id, now)
        return {
            "session_id": session_id,
            "user_id": user_id,
            "display_name": display_name,
            "device_id": device_id,
        }

    def resolve_session(self, session_id: str) -> SessionRecord:
        # M117: cache fast path. On hit we trust the cached fields and only
        # apply the TTL freshness check; on miss we fall through to the
        # in-memory state and write back. The cache TTL is bounded by the
        # configured session_ttl (or 60s if unlimited) so a stale cached
        # last_seen can't delay a touch-driven refresh by more than the
        # cache TTL — which is also why the dispatch layer doesn't need an
        # explicit cross-service touch-fanout for single-process deployments.
        if self._cache is not None:
            try:
                cached = self._cache.get_session(session_id)
            except Exception:
                cached = None
            if cached is not None:
                last_seen_at = float(cached.get("last_seen_at", 0.0))
                if (
                    self._session_ttl_seconds > 0
                    and self._clock() - last_seen_at > self._session_ttl_seconds
                ):
                    self._evict_session(session_id)
                    raise ServiceError(ErrorCode.INVALID_SESSION)
                return SessionRecord(
                    session_id=str(cached.get("session_id", session_id)),
                    user_id=str(cached.get("user_id", "")),
                    device_id=str(cached.get("device_id", "")),
                    last_seen_at=last_seen_at,
                )

        session = self._state.sessions.get(session_id)
        if session is None:
            self._invalidate_session_cache(session_id)
            raise ServiceError(ErrorCode.INVALID_SESSION)
        if self._session_ttl_seconds > 0 and self._clock() - session.last_seen_at > self._session_ttl_seconds:
            self._evict_session(session_id)
            raise ServiceError(ErrorCode.INVALID_SESSION)
        # Hot path miss -> write back so the next call short-circuits.
        self._write_session_cache(
            session.session_id, session.user_id, session.device_id, session.last_seen_at
        )
        return session

    # ---- M117 cache helpers ----

    def refresh_session_cache(self, session_id: str, *, last_seen_at: float) -> None:
        """Hook for PresenceService.touch (and any other writer that bumps
        last_seen_at on the live SessionRecord) to keep the auth cache in
        sync. No-op if no cache is bound or the session is unknown.
        """
        session = self._state.sessions.get(session_id)
        if session is None:
            return
        self._write_session_cache(
            session.session_id, session.user_id, session.device_id, last_seen_at
        )

    def _write_session_cache(
        self, session_id: str, user_id: str, device_id: str, last_seen_at: float
    ) -> None:
        if self._cache is None:
            return
        try:
            self._cache.set_session(
                session_id,
                user_id=user_id,
                device_id=device_id,
                last_seen_at=last_seen_at,
            )
        except Exception:
            pass

    def _invalidate_session_cache(self, session_id: str) -> None:
        if self._cache is None:
            return
        try:
            self._cache.invalidate_session(session_id)
        except Exception:
            pass

    def _evict_session(self, session_id: str) -> None:
        """Drop both the in-memory session and its cached entry. Used by the
        TTL expiry path so the next call sees a clean miss and the user is
        forced to re-authenticate."""
        self._state.sessions.pop(session_id, None)
        self._state.save_runtime_state()
        self._invalidate_session_cache(session_id)
