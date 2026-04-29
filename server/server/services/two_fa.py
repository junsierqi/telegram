"""TOTP 2FA service (M94).

Implements RFC 6238 Time-based One-Time Password using only the standard
library (`hmac`, `hashlib`, `secrets`, `struct`, `base64`, `time`).

Workflow:

  1. Client calls TWO_FA_ENABLE_REQUEST. Server generates a fresh base32
     secret + provisioning URI (`otpauth://totp/...`), stores the secret
     against the user but marks it pending until the next step.
  2. Client renders the URI as a QR code, the user scans into an
     authenticator app, gets a 6-digit code, sends TWO_FA_VERIFY_REQUEST.
  3. Server verifies the code with ±1 step tolerance and flips 2FA on.
     Subsequent LOGIN_REQUESTs must include a fresh 2FA code.

The `_pending_secrets` dict holds enrollment-in-progress secrets so they
don't clutter UserRecord until verified — same pattern Authy / Google
Authenticator use server-side.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import threading
import time
import urllib.parse
from typing import Callable, Optional

from ..protocol import ErrorCode, ServiceError
from ..state import InMemoryState, UserRecord


SECRET_BYTES = 20         # 160 bits, RFC 6238 recommended
DIGITS = 6
TIME_STEP_SECONDS = 30
WINDOW_TOLERANCE = 1      # accept t-30s, t, t+30s


def _generate_secret_b32() -> str:
    raw = secrets.token_bytes(SECRET_BYTES)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def generate_totp_code(secret_b32: str, *, at: float | None = None,
                       digits: int = DIGITS, step: int = TIME_STEP_SECONDS) -> str:
    """Compute the RFC 6238 TOTP code for the given secret at a wall-clock
    instant. Used by the verify path here AND by tests / clients.
    """
    pad = "=" * (-len(secret_b32) % 8)
    key = base64.b32decode(secret_b32 + pad, casefold=True)
    counter = int((at if at is not None else time.time()) // step)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % (10 ** digits)).zfill(digits)


def verify_totp(secret_b32: str, code: str, *, at: float | None = None,
                tolerance: int = WINDOW_TOLERANCE) -> bool:
    if not code or len(code) != DIGITS or not code.isdigit():
        return False
    now = at if at is not None else time.time()
    for delta in range(-tolerance, tolerance + 1):
        candidate = generate_totp_code(secret_b32, at=now + delta * TIME_STEP_SECONDS)
        # constant-time compare so we don't leak timing info per-digit
        if hmac.compare_digest(candidate, code):
            return True
    return False


def provisioning_uri(username: str, secret_b32: str, *,
                     issuer: str = "Telegram-like") -> str:
    """RFC-shape otpauth:// URI for QR code rendering. Authenticator apps
    parse the issuer + label + secret + digits + period."""
    label = f"{issuer}:{username}"
    params = urllib.parse.urlencode({
        "secret": secret_b32,
        "issuer": issuer,
        "algorithm": "SHA1",
        "digits": DIGITS,
        "period": TIME_STEP_SECONDS,
    })
    return f"otpauth://totp/{urllib.parse.quote(label)}?{params}"


class TwoFAService:
    def __init__(
        self,
        state: InMemoryState,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._state = state
        self._clock = clock or time.time
        # user_id -> pending_secret_b32 (enrollment in flight, not yet flipped on)
        self._pending: dict[str, str] = {}
        # Same threading rationale as PhoneOtpService: ThreadedTCPServer can
        # run two dispatch calls in parallel, so a confirm racing against a
        # second confirm could pop _pending after the first read and the
        # second sees None. One lock guards every mutation here.
        self._lock = threading.Lock()

    def is_enabled(self, user_id: str) -> bool:
        user = self._state.users.get(user_id)
        return bool(user and user.two_fa_secret)

    # ---- enroll ----

    def begin_enable(self, user_id: str) -> tuple[str, str]:
        user = self._state.users.get(user_id)
        if user is None:
            raise ServiceError(ErrorCode.UNKNOWN_USER)
        if user.two_fa_secret:
            raise ServiceError(ErrorCode.TWO_FA_ALREADY_ENABLED)
        secret_b32 = _generate_secret_b32()
        with self._lock:
            self._pending[user_id] = secret_b32
        uri = provisioning_uri(user.username, secret_b32)
        return secret_b32, uri

    def confirm_enable(self, user_id: str, code: str) -> UserRecord:
        with self._lock:
            secret_b32 = self._pending.get(user_id)
            if secret_b32 is None:
                raise ServiceError(ErrorCode.TWO_FA_NOT_ENABLED)
            if not verify_totp(secret_b32, code, at=self._clock()):
                raise ServiceError(ErrorCode.INVALID_TWO_FA_CODE)
            user = self._state.users.get(user_id)
            if user is None:
                raise ServiceError(ErrorCode.UNKNOWN_USER)
            user.two_fa_secret = secret_b32
            self._pending.pop(user_id, None)
        self._state.save_runtime_state()
        return user

    def discard_pending_enrollment(self, user_id: str) -> None:
        """Called by the account lifecycle service when a user is being
        deleted to release any pending 2FA enrollment that never confirmed.
        Without this, the secret would dangle forever in _pending and (if
        a future user_id ever recycled the same string) would be picked up
        on the next confirm_enable. Safe to call when no enrollment exists."""
        with self._lock:
            self._pending.pop(user_id, None)

    # ---- runtime use ----

    def verify_login_code(self, user_id: str, code: str) -> bool:
        user = self._state.users.get(user_id)
        if user is None or not user.two_fa_secret:
            return True  # nothing to verify
        return verify_totp(user.two_fa_secret, code, at=self._clock())

    def disable(self, user_id: str, code: str) -> None:
        user = self._state.users.get(user_id)
        if user is None or not user.two_fa_secret:
            raise ServiceError(ErrorCode.TWO_FA_NOT_ENABLED)
        if not verify_totp(user.two_fa_secret, code, at=self._clock()):
            raise ServiceError(ErrorCode.INVALID_TWO_FA_CODE)
        user.two_fa_secret = ""
        self._state.save_runtime_state()

    def describe(self) -> str:
        return "two-factor service — RFC 6238 TOTP, stdlib-only"
