from __future__ import annotations

import time
from typing import Callable

from ..protocol import DeviceDescriptor, PresenceUserStatus
from ..protocol import ErrorCode, ServiceError
from ..state import InMemoryState


DEFAULT_TTL_SECONDS = 30.0


class PresenceService:
    def __init__(
        self,
        state: InMemoryState,
        *,
        clock: Callable[[], float] | None = None,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
    ) -> None:
        self._state = state
        self._clock = clock or time.time
        self._ttl = float(ttl_seconds)

    @property
    def ttl_seconds(self) -> float:
        return self._ttl

    def describe(self) -> str:
        return (
            f"presence service ready for heartbeat processing (ttl={self._ttl:.0f}s), "
            "online state and active device tracking"
        )

    def touch(self, session_id: str) -> float:
        """Record a fresh last_seen_at for a session. Returns the timestamp written.

        No-ops silently for unknown session_ids — the dispatcher already rejects
        those before reaching us with SESSION_ACTOR_MISMATCH / INVALID_SESSION.
        """
        session = self._state.sessions.get(session_id)
        now = self._clock()
        if session is None:
            return now
        session.last_seen_at = now
        self._state.save_runtime_state()
        return now

    def is_session_fresh(self, session_id: str) -> bool:
        session = self._state.sessions.get(session_id)
        if session is None:
            return False
        return (self._clock() - session.last_seen_at) <= self._ttl

    def is_device_online(self, device_id: str) -> bool:
        now = self._clock()
        for session in self._state.sessions.values():
            if session.device_id != device_id:
                continue
            if (now - session.last_seen_at) <= self._ttl:
                return True
        return False

    def is_user_online(self, user_id: str) -> bool:
        now = self._clock()
        for session in self._state.sessions.values():
            if session.user_id != user_id:
                continue
            if (now - session.last_seen_at) <= self._ttl:
                return True
        return False

    def last_seen_ms(self, user_id: str) -> int:
        """Highest last_seen_at across the user's sessions, in milliseconds.

        Returns 0 if the user has no sessions at all.
        """
        latest = 0.0
        for session in self._state.sessions.values():
            if session.user_id != user_id:
                continue
            if session.last_seen_at > latest:
                latest = session.last_seen_at
        return int(latest * 1000)

    def list_devices(self, user_id: str) -> list[DeviceDescriptor]:
        devices: list[DeviceDescriptor] = []
        for device in self._state.devices.values():
            if device.user_id != user_id:
                continue
            devices.append(
                DeviceDescriptor(
                    device_id=device.device_id,
                    label=device.label,
                    platform=device.platform,
                    trusted=device.trusted,
                    active=self.is_device_online(device.device_id),
                )
            )
        return devices

    def revoke_device(self, user_id: str, current_session_id: str, device_id: str) -> list[DeviceDescriptor]:
        device = self._state.devices.get(device_id)
        if device is None or device.user_id != user_id:
            raise ServiceError(ErrorCode.UNKNOWN_REQUESTER_DEVICE)
        current_session = self._state.sessions.get(current_session_id)
        if current_session is not None and current_session.device_id == device_id:
            raise ServiceError(ErrorCode.DEVICE_ACTION_DENIED)
        self._state.sessions = {
            sid: session
            for sid, session in self._state.sessions.items()
            if not (session.user_id == user_id and session.device_id == device_id)
        }
        device.active = False
        self._state.save_runtime_state()
        return self.list_devices(user_id)

    def update_trust(self, user_id: str, device_id: str, trusted: bool) -> list[DeviceDescriptor]:
        device = self._state.devices.get(device_id)
        if device is None or device.user_id != user_id:
            raise ServiceError(ErrorCode.UNKNOWN_REQUESTER_DEVICE)
        device.trusted = bool(trusted)
        self._state.save_runtime_state()
        return self.list_devices(user_id)

    def query_users(self, user_ids: list[str]) -> list[PresenceUserStatus]:
        result: list[PresenceUserStatus] = []
        for user_id in user_ids:
            result.append(
                PresenceUserStatus(
                    user_id=user_id,
                    online=self.is_user_online(user_id),
                    last_seen_at_ms=self.last_seen_ms(user_id),
                )
            )
        return result

    def now_ms(self) -> int:
        return int(self._clock() * 1000)
