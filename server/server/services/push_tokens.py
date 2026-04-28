"""Push notification token registry + offline-recipient mock dispatch.

In Telegram-style products the server wakes mobile clients via FCM (Android)
or APNs (iOS) when the persistent TCP control plane isn't connected. This
service is the protocol surface for that:

  * `register(user, device, platform, token)` and `unregister(user, ...)`
    keep the (user_id, device_id, platform) -> token mapping.
  * `tokens_for_user(user_id)` is the fan-out lookup.
  * `notify_offline_recipient(user_id, kind, body_summary)` records a
    "would-have-been-pushed" entry into `pending_deliveries`.

The actual wire transport to FCM / APNs is intentionally NOT here — that's
PA-008 (acquire FCM service account JSON / APNs token, plumb httpx client).
The mock queue gives validators something to assert on without external
dependencies, and the same `pending_deliveries` cursor is what a real
delivery worker would drain.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Iterable

from ..protocol import ErrorCode, ServiceError
from ..state import InMemoryState, PushTokenRecord


@dataclass(slots=True)
class PendingDelivery:
    user_id: str
    device_id: str
    platform: str
    token: str
    kind: str            # e.g., "message_deliver"
    body_summary: str    # short text shown in the OS notification banner
    enqueued_at_ms: int


class PushTokenService:
    def __init__(
        self,
        state: InMemoryState,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._state = state
        self._clock = clock or time.time
        # In-memory mock queue for offline deliveries. A future FCM/APNs
        # worker drains this list. Tests reach in via drain_pending().
        self.pending_deliveries: list[PendingDelivery] = []

    # ---- registration ----

    def register(self, user_id: str, device_id: str, platform: str, token: str) -> PushTokenRecord:
        if not platform or not token:
            raise ServiceError(ErrorCode.INVALID_REGISTRATION_PAYLOAD,
                               "platform and token are required")
        # Replace any existing matching record so token rotation is idempotent.
        self._state.push_tokens = [
            r for r in self._state.push_tokens
            if not (r.user_id == user_id and r.device_id == device_id
                    and r.platform == platform)
        ]
        record = PushTokenRecord(
            user_id=user_id,
            device_id=device_id,
            platform=platform,
            token=token,
            registered_at_ms=int(self._clock() * 1000),
        )
        self._state.push_tokens.append(record)
        self._state.save_runtime_state()
        return record

    def unregister(self, user_id: str, device_id: str, platform: str, token: str) -> bool:
        before = len(self._state.push_tokens)
        self._state.push_tokens = [
            r for r in self._state.push_tokens
            if not (r.user_id == user_id and r.device_id == device_id
                    and r.platform == platform and r.token == token)
        ]
        removed = before > len(self._state.push_tokens)
        if removed:
            self._state.save_runtime_state()
        return removed

    def tokens_for_user(self, user_id: str) -> list[PushTokenRecord]:
        return [r for r in self._state.push_tokens if r.user_id == user_id]

    def all_tokens(self) -> list[PushTokenRecord]:
        return list(self._state.push_tokens)

    # ---- mock dispatch ----

    def notify_offline_recipient(
        self, user_id: str, kind: str, body_summary: str,
    ) -> list[PendingDelivery]:
        """Record a 'would-have-been-pushed' entry per registered token for
        the given user. Returns the entries enqueued so callers can also
        observe them without scanning the full queue.
        """
        enqueued: list[PendingDelivery] = []
        now_ms = int(self._clock() * 1000)
        for record in self.tokens_for_user(user_id):
            entry = PendingDelivery(
                user_id=record.user_id,
                device_id=record.device_id,
                platform=record.platform,
                token=record.token,
                kind=kind,
                body_summary=body_summary,
                enqueued_at_ms=now_ms,
            )
            self.pending_deliveries.append(entry)
            enqueued.append(entry)
        return enqueued

    def drain_pending(self) -> list[PendingDelivery]:
        """Return + clear all pending entries. A real FCM/APNs worker would
        call this on a tick and then POST to the platform."""
        out = self.pending_deliveries
        self.pending_deliveries = []
        return out

    def describe(self) -> str:
        return (
            f"push token service tracks {len(self._state.push_tokens)} tokens "
            f"with {len(self.pending_deliveries)} mock deliveries queued"
        )
