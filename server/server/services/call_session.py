"""Voice / video call session service (M109).

State machine:

    (none) --invite--> ringing
    ringing --accept--> accepted
    ringing --decline--> declined (terminal)
    ringing --end (by caller) --> canceled (terminal)
    accepted --end (by either) --> ended (terminal)

The same per-session AES-256-GCM relay key (M106) seals the call's media
plane: `accept` mints the key (lazy, on first accept) so both peers see
the same value when they call `rendezvous`.

Call records are in-memory only — runtime restart drops in-flight calls,
which is acceptable for a real-time channel.
"""
from __future__ import annotations

from ..media_crypto import generate_key_b64
from ..protocol import (
    CallRendezvousInfoPayload,
    CallStatePayload,
    ErrorCode,
    ServiceError,
)
from ..state import CallRecord, InMemoryState


_RINGING = "ringing"
_ACCEPTED = "accepted"
_DECLINED = "declined"
_ENDED = "ended"
_CANCELED = "canceled"
_TERMINAL = frozenset({_DECLINED, _ENDED, _CANCELED})
_ACTIVE = frozenset({_RINGING, _ACCEPTED})

_SUPPORTED_KINDS = frozenset({"audio", "video"})


def _resolve_user_id_for_device(state: InMemoryState, device_id: str) -> str:
    """Return the owning user_id for a device, or "" if unknown."""
    record = state.devices.get(device_id) if hasattr(state, "devices") else None
    if record is not None:
        return record.user_id
    # Fallback: walk sessions table (covers older state shapes used in tests).
    for session in state.sessions.values():
        if session.device_id == device_id:
            return session.user_id
    return ""


class CallSessionService:
    def __init__(self, state: InMemoryState, *, default_relay: str = "relay.example.internal:5000") -> None:
        self._state = state
        self._counter = 0
        self._default_relay = default_relay

    def describe(self) -> str:
        return "voice/video call session service (M109)"

    # ---- public API ----

    def create_invite(
        self,
        *,
        caller_user_id: str,
        caller_device_id: str,
        callee_user_id: str,
        callee_device_id: str,
        kind: str,
    ) -> CallStatePayload:
        if kind not in _SUPPORTED_KINDS:
            raise ServiceError(ErrorCode.CALL_INVALID_KIND)
        if not callee_user_id:
            # Fall back to looking up by device_id so callers can pass an empty
            # user_id when they only know the target device.
            callee_user_id = _resolve_user_id_for_device(self._state, callee_device_id)
        if not callee_user_id:
            raise ServiceError(ErrorCode.UNKNOWN_USER)
        self._counter += 1
        call_id = f"call_{self._counter}"
        record = CallRecord(
            call_id=call_id,
            caller_user_id=caller_user_id,
            caller_device_id=caller_device_id,
            callee_user_id=callee_user_id,
            callee_device_id=callee_device_id,
            kind=kind,
            state=_RINGING,
            relay_endpoint=self._default_relay,
            relay_region="dev",
        )
        self._state.calls[call_id] = record
        return self._to_state_payload(record, detail="ringing")

    def accept(self, call_id: str, actor_user_id: str) -> CallStatePayload:
        record = self._lookup(call_id)
        if actor_user_id != record.callee_user_id:
            raise ServiceError(ErrorCode.CALL_PARTICIPANT_DENIED)
        if record.state != _RINGING:
            raise ServiceError(ErrorCode.CALL_NOT_RINGING)
        record.state = _ACCEPTED
        if not record.relay_key_b64:
            record.relay_key_b64 = generate_key_b64()
        return self._to_state_payload(record, detail="accepted")

    def decline(self, call_id: str, actor_user_id: str) -> CallStatePayload:
        record = self._lookup(call_id)
        if actor_user_id != record.callee_user_id:
            raise ServiceError(ErrorCode.CALL_PARTICIPANT_DENIED)
        if record.state != _RINGING:
            raise ServiceError(ErrorCode.CALL_NOT_RINGING)
        record.state = _DECLINED
        return self._to_state_payload(record, detail="declined_by_callee")

    def end(self, call_id: str, actor_user_id: str) -> CallStatePayload:
        record = self._lookup(call_id)
        if actor_user_id not in (record.caller_user_id, record.callee_user_id):
            raise ServiceError(ErrorCode.CALL_PARTICIPANT_DENIED)
        if record.state in _TERMINAL:
            raise ServiceError(ErrorCode.CALL_ALREADY_TERMINAL)
        if record.state == _RINGING:
            # Caller hung up while it was still ringing -> caller-side cancel.
            if actor_user_id != record.caller_user_id:
                raise ServiceError(ErrorCode.CALL_NOT_ACTIVE)
            record.state = _CANCELED
            detail = "canceled_by_caller"
        else:
            record.state = _ENDED
            role = "caller" if actor_user_id == record.caller_user_id else "callee"
            detail = f"ended_by_{role}"
        return self._to_state_payload(record, detail=detail)

    def rendezvous(self, call_id: str, actor_user_id: str) -> CallRendezvousInfoPayload:
        record = self._lookup(call_id)
        if actor_user_id not in (record.caller_user_id, record.callee_user_id):
            raise ServiceError(ErrorCode.CALL_PARTICIPANT_DENIED)
        if record.state != _ACCEPTED:
            raise ServiceError(ErrorCode.CALL_NOT_ACTIVE)
        return CallRendezvousInfoPayload(
            call_id=call_id,
            state=record.state,
            relay_region=record.relay_region,
            relay_endpoint=record.relay_endpoint,
            relay_key_b64=record.relay_key_b64,
        )

    # ---- internals ----

    def _lookup(self, call_id: str) -> CallRecord:
        record = self._state.calls.get(call_id)
        if record is None:
            raise ServiceError(ErrorCode.UNKNOWN_CALL)
        return record

    @staticmethod
    def _to_state_payload(record: CallRecord, *, detail: str) -> CallStatePayload:
        return CallStatePayload(
            call_id=record.call_id,
            caller_user_id=record.caller_user_id,
            caller_device_id=record.caller_device_id,
            callee_user_id=record.callee_user_id,
            callee_device_id=record.callee_device_id,
            kind=record.kind,
            state=record.state,
            detail=detail,
        )
