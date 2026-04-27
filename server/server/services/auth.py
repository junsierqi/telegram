from __future__ import annotations

import re
import time
from typing import Callable

from ..crypto import hash_password, verify_password
from ..protocol import ErrorCode, ServiceError
from ..state import DeviceRecord, InMemoryState, SessionRecord, UserRecord


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{2,31}$")
MIN_PASSWORD_LENGTH = 8


class AuthService:
    def __init__(
        self,
        state: InMemoryState,
        *,
        clock: Callable[[], float] | None = None,
        session_ttl_seconds: float = 0.0,
    ) -> None:
        self._state = state
        self._clock = clock or time.time
        self._session_ttl_seconds = max(0.0, float(session_ttl_seconds))
        self._session_counter = self._next_session_counter()
        self._user_counter = self._next_user_counter()

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
            self._state.sessions[session_id] = SessionRecord(
                session_id=session_id,
                user_id=user.user_id,
                device_id=device_id,
                last_seen_at=self._clock(),
            )
            self._state.save_runtime_state()
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
        self._state.sessions[session_id] = SessionRecord(
            session_id=session_id,
            user_id=user_id,
            device_id=device_id,
            last_seen_at=self._clock(),
        )
        self._state.save_runtime_state()
        return {
            "session_id": session_id,
            "user_id": user_id,
            "display_name": display_name,
            "device_id": device_id,
        }

    def resolve_session(self, session_id: str) -> SessionRecord:
        session = self._state.sessions.get(session_id)
        if session is None:
            raise ServiceError(ErrorCode.INVALID_SESSION)
        if self._session_ttl_seconds > 0 and self._clock() - session.last_seen_at > self._session_ttl_seconds:
            self._state.sessions.pop(session_id, None)
            self._state.save_runtime_state()
            raise ServiceError(ErrorCode.INVALID_SESSION)
        return session
