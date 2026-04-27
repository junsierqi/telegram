"""Input injection service — control-plane message that the requester sends
to drive input on the target (once real input injection exists). For now the
service validates the event shape + authorization, records an in-memory log,
and returns an ack with a monotonic sequence number.

Authorization rule: only the requester_user_id of an active (post-approval,
pre-terminal) remote session can inject input events. The target is the
*recipient* of input, not a source of it.
"""
from __future__ import annotations

from typing import Any

from ..protocol import ErrorCode, ServiceError
from ..state import InMemoryState


_ACTIVE_STATES = ("approved", "negotiating", "connecting", "streaming", "controlling")


# Required fields per kind. Values are the required keys.
_INPUT_SCHEMAS: dict[str, tuple[str, ...]] = {
    "key": ("action", "key"),             # action in {"down", "up"}, key is a human-readable keysym
    "mouse_move": ("x", "y"),             # absolute pixel position; real impl will map to screen dims
    "mouse_button": ("action", "button"), # action in {"down", "up"}, button in {"left","right","middle"}
    "scroll": ("dx", "dy"),               # horizontal/vertical wheel deltas
}


class InputService:
    def __init__(self, state: InMemoryState) -> None:
        self._state = state
        self._sequence = 0
        # Keep the N most recent events in memory for test/observability.
        self._log: list[dict[str, Any]] = []

    def describe(self) -> str:
        return "input service receives key/mouse events for approved remote sessions"

    @property
    def event_log(self) -> list[dict[str, Any]]:
        return list(self._log)

    def inject(self, remote_session_id: str, actor_user_id: str, kind: str, data: dict[str, Any]) -> dict[str, Any]:
        record = self._state.remote_sessions.get(remote_session_id)
        if record is None:
            raise ServiceError(ErrorCode.UNKNOWN_REMOTE_SESSION)
        if actor_user_id != record.requester_user_id:
            raise ServiceError(ErrorCode.REMOTE_INPUT_DENIED)
        if record.state not in _ACTIVE_STATES:
            raise ServiceError(ErrorCode.REMOTE_SESSION_NOT_ACTIVE)

        required = _INPUT_SCHEMAS.get(kind)
        if required is None:
            raise ServiceError(ErrorCode.UNSUPPORTED_INPUT_KIND)
        for key in required:
            if key not in data:
                raise ServiceError(ErrorCode.INVALID_INPUT_PAYLOAD)

        self._sequence += 1
        self._log.append({
            "sequence": self._sequence,
            "remote_session_id": remote_session_id,
            "actor_user_id": actor_user_id,
            "kind": kind,
            "data": dict(data),
        })
        return {
            "remote_session_id": remote_session_id,
            "sequence": self._sequence,
            "kind": kind,
        }
