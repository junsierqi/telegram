"""Phone-number + OTP authentication (M90).

Pluggable Sender protocol so deployments can swap the transport:
  * MockSender   — default; records every code in `outbox` for tests + writes
                   one line to a configurable stream (stderr by default).
  * TwilioSender — stub; activates when a real Twilio account SID + auth
                   token are provided via env vars (PA-009 covers the
                   credential procurement). The HTTP call is intentionally
                   left to a future milestone — uses stdlib `urllib`.

Service contract:
  request_code(phone)   -> (length, ttl_seconds)
  verify_code(phone, code, device_id, display_name)
                        -> (user_record, session_id, new_account_bool)

Request/verify rate limits:
  - 1 code per phone per 30s (PHONE_OTP_RATE_LIMITED on flood)
  - codes expire 5 minutes after issue (OTP_EXPIRED)
  - 5 verify attempts per code, then INVALID_OTP_CODE flips to
    OTP_ATTEMPTS_EXHAUSTED until the next request_code
"""
from __future__ import annotations

import os
import re
import secrets
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol

from ..crypto import hash_password
from ..protocol import ErrorCode, ServiceError
from ..state import DeviceRecord, InMemoryState, SessionRecord, UserRecord


CODE_LENGTH = 6
CODE_TTL_SECONDS = 300
RESEND_COOLDOWN_SECONDS = 30
MAX_VERIFY_ATTEMPTS = 5
# E.164 allows up to 15 digits after the leading "+", at least 7 in practice.
_PHONE_E164 = re.compile(r"^\+[1-9]\d{6,14}$")


@dataclass
class _OtpRecord:
    code: str
    issued_at: float
    expires_at: float
    attempts: int = 0
    exhausted: bool = False


@dataclass
class SentOtp:
    """Mock receipt entry for tests / local debugging."""
    phone_number: str
    code: str
    issued_at_ms: int


class Sender(Protocol):
    name: str

    def send(self, phone_number: str, code: str) -> None:
        ...  # pragma: no cover


class MockSender:
    """Default sender. Records each (phone, code) into `outbox` and writes a
    one-line summary to stream (stderr by default). Tests read `outbox` to
    fish out the issued code without race conditions."""

    name = "mock"

    def __init__(self, stream=None) -> None:
        self._stream = stream if stream is not None else sys.stderr
        self.outbox: list[SentOtp] = []

    def send(self, phone_number: str, code: str) -> None:
        self._stream.write(
            f"[otp:mock] -> {phone_number} code={code}\n"
        )
        self.outbox.append(SentOtp(
            phone_number=phone_number,
            code=code,
            issued_at_ms=int(time.time() * 1000),
        ))

    def latest_for(self, phone_number: str) -> Optional[SentOtp]:
        for entry in reversed(self.outbox):
            if entry.phone_number == phone_number:
                return entry
        return None


class PhoneOtpService:
    def __init__(
        self,
        state: InMemoryState,
        *,
        sender: Optional[Sender] = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._state = state
        self._sender = sender or MockSender()
        self._clock = clock or time.time
        self._codes: dict[str, _OtpRecord] = {}
        self._user_counter = 0
        # ThreadedTCPServer can run two dispatch calls in parallel. The
        # request_code / verify_code paths both mutate _codes (and verify
        # increments record.attempts non-atomically), so an unlocked path
        # could under-count attempts and let an attacker exceed
        # MAX_VERIFY_ATTEMPTS. One lock covers everything inside this
        # service since contention is low (one OTP per phone per 30 s).
        self._lock = threading.Lock()

    @property
    def sender(self) -> Sender:
        return self._sender

    # ---- request ----

    def request_code(self, phone_number: str) -> tuple[int, int]:
        if not phone_number or not _PHONE_E164.match(phone_number):
            raise ServiceError(ErrorCode.INVALID_PHONE_NUMBER)
        now = self._clock()
        with self._lock:
            # Opportunistic purge: every request_code drops every entry that
            # has already expired. Bounds _codes growth at "active flows in
            # the last 5 minutes" instead of letting it accumulate forever
            # for phones that never verify.
            self._codes = {
                phone: rec for phone, rec in self._codes.items()
                if rec.expires_at >= now
            }
            existing = self._codes.get(phone_number)
            if existing is not None and (now - existing.issued_at) < RESEND_COOLDOWN_SECONDS:
                raise ServiceError(ErrorCode.PHONE_OTP_RATE_LIMITED)
            # secrets.choice gives uniform 0-9 digits without seeded RNG bias.
            code = "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))
            self._codes[phone_number] = _OtpRecord(
                code=code,
                issued_at=now,
                expires_at=now + CODE_TTL_SECONDS,
            )
        self._sender.send(phone_number, code)
        return CODE_LENGTH, CODE_TTL_SECONDS

    # ---- verify ----

    def verify_code(
        self, phone_number: str, code: str, *, device_id: str, display_name: str = "",
    ) -> tuple[UserRecord, str, bool]:
        if not phone_number or not _PHONE_E164.match(phone_number):
            raise ServiceError(ErrorCode.INVALID_PHONE_NUMBER)
        now = self._clock()
        with self._lock:
            record = self._codes.get(phone_number)
            if record is None:
                raise ServiceError(ErrorCode.INVALID_OTP_CODE)
            if now > record.expires_at:
                self._codes.pop(phone_number, None)
                raise ServiceError(ErrorCode.OTP_EXPIRED)
            if record.exhausted:
                raise ServiceError(ErrorCode.OTP_ATTEMPTS_EXHAUSTED)
            if not secrets.compare_digest(record.code, code or ""):
                record.attempts += 1
                if record.attempts >= MAX_VERIFY_ATTEMPTS:
                    record.exhausted = True
                    raise ServiceError(ErrorCode.OTP_ATTEMPTS_EXHAUSTED)
                raise ServiceError(ErrorCode.INVALID_OTP_CODE)
            # success — burn the code under lock to prevent a parallel
            # verify from reusing it.
            self._codes.pop(phone_number, None)

        user, new_account = self._upsert_phone_user(phone_number, display_name)
        device = self._upsert_device(user.user_id, device_id)
        session_id = self._next_session_id()
        self._state.sessions[session_id] = SessionRecord(
            session_id=session_id,
            user_id=user.user_id,
            device_id=device.device_id,
            last_seen_at=now,
        )
        self._state.save_runtime_state()
        return user, session_id, new_account

    # ---- helpers ----

    def _upsert_phone_user(self, phone_number: str, display_name: str) -> tuple[UserRecord, bool]:
        # Phone-registered users get a synthetic username "phone:<E.164>" so
        # they don't collide with username/password registrations and the
        # auth pathway can still read .username deterministically.
        synthetic_username = f"phone:{phone_number}"
        for user in self._state.users.values():
            if user.username == synthetic_username:
                return user, False
        user_id = self._next_user_id(phone_number)
        user = UserRecord(
            user_id=user_id,
            username=synthetic_username,
            # No password — phone-OTP-only accounts can't password-login.
            # Hash an unguessable random token so verify_password always fails.
            password_hash=hash_password(secrets.token_hex(32)),
            display_name=display_name or phone_number,
        )
        self._state.users[user_id] = user
        return user, True

    def _upsert_device(self, user_id: str, device_id: str) -> DeviceRecord:
        existing = self._state.devices.get(device_id)
        if existing is not None and existing.user_id == user_id:
            return existing
        # New or reassigned device — create / replace.
        record = DeviceRecord(
            device_id=device_id or f"dev_phone_{secrets.token_hex(4)}",
            user_id=user_id,
            label="Phone client",
            platform="phone",
        )
        self._state.devices[record.device_id] = record
        return record

    def _next_user_id(self, phone_number: str) -> str:
        # Stable per-phone id: u_phone_<digits-only> so reads stay readable.
        digits = "".join(c for c in phone_number if c.isdigit())
        candidate = f"u_phone_{digits}"
        if candidate not in self._state.users:
            return candidate
        # collision-avoidance for unlucky duplicates (shouldn't happen with
        # E.164 uniqueness, but keep deterministic fallback)
        suffix = 1
        while f"{candidate}_{suffix}" in self._state.users:
            suffix += 1
        return f"{candidate}_{suffix}"

    def _next_session_id(self) -> str:
        # Counter-based id matches AuthService.login style ("sess_N").
        existing = sum(1 for sid in self._state.sessions if sid.startswith("sess_"))
        return f"sess_{existing + 1}"

    def describe(self) -> str:
        return (
            f"phone OTP service ready (code_len={CODE_LENGTH}, ttl={CODE_TTL_SECONDS}s, "
            f"sender={self._sender.name})"
        )
