from __future__ import annotations

from ..media_crypto import generate_key_b64
from ..protocol import (
    ErrorCode,
    RemoteRelayAssignmentPayload,
    RemoteRendezvousCandidate,
    RemoteRendezvousInfoPayload,
    RemoteSessionStatePayload,
    RemoteSessionTerminatedPayload,
    ServiceError,
)
from ..state import InMemoryState, RemoteSessionRecord


def _stable_octet(device_id: str) -> int:
    """Deterministic 1..254 octet derived from device_id for placeholder host candidates."""
    if not device_id:
        return 1
    return (sum(ord(c) for c in device_id) % 254) + 1


class RemoteSessionService:
    def __init__(self, state: InMemoryState) -> None:
        self._state = state
        self._counter = self._next_remote_counter()

    def describe(self) -> str:
        return "remote-session service reserved for invite approval, capability lookup and relay coordination"

    def create_invite(
        self,
        *,
        requester_user_id: str,
        requester_device_id: str,
        target_device_id: str,
    ) -> RemoteSessionStatePayload:
        requester_device = self._state.devices.get(requester_device_id)
        if requester_device is None:
            raise ServiceError(ErrorCode.UNKNOWN_REQUESTER_DEVICE)
        if requester_device.user_id != requester_user_id:
            raise ServiceError(ErrorCode.REQUESTER_DEVICE_USER_MISMATCH)

        target = self._state.devices.get(target_device_id)
        if target is None:
            raise ServiceError(ErrorCode.UNKNOWN_TARGET_DEVICE)
        if target.user_id == requester_user_id:
            raise ServiceError(ErrorCode.SELF_REMOTE_SESSION_NOT_ALLOWED)
        remote_session_id = f"remote_{self._counter}"
        self._counter += 1
        record = RemoteSessionRecord(
            remote_session_id=remote_session_id,
            requester_user_id=requester_user_id,
            requester_device_id=requester_device_id,
            target_user_id=target.user_id,
            target_device_id=target_device_id,
            state="awaiting_approval",
        )
        self._state.remote_sessions[remote_session_id] = record
        self._state.save_runtime_state()
        return RemoteSessionStatePayload(
            remote_session_id=remote_session_id,
            state=record.state,
            target_user_id=record.target_user_id,
            target_device_id=record.target_device_id,
        )

    def approve(self, remote_session_id: str, approver_user_id: str) -> RemoteRelayAssignmentPayload:
        record = self._state.remote_sessions.get(remote_session_id)
        if record is None:
            raise ServiceError(ErrorCode.UNKNOWN_REMOTE_SESSION)
        if record.target_user_id != approver_user_id:
            raise ServiceError(ErrorCode.REMOTE_APPROVAL_DENIED)
        if record.state != "awaiting_approval":
            raise ServiceError(ErrorCode.REMOTE_SESSION_NOT_AWAITING_APPROVAL)
        record.state = "approved"
        record.relay_region = "us-west"
        record.relay_endpoint = "relay-usw.example.internal:5000"
        self._state.save_runtime_state()
        return RemoteRelayAssignmentPayload(
            remote_session_id=remote_session_id,
            state=record.state,
            relay_region=record.relay_region,
            relay_endpoint=record.relay_endpoint,
        )

    def reject(self, remote_session_id: str, approver_user_id: str) -> RemoteSessionStatePayload:
        record = self._state.remote_sessions.get(remote_session_id)
        if record is None:
            raise ServiceError(ErrorCode.UNKNOWN_REMOTE_SESSION)
        if record.target_user_id != approver_user_id:
            raise ServiceError(ErrorCode.REMOTE_REJECTION_DENIED)
        if record.state != "awaiting_approval":
            raise ServiceError(ErrorCode.REMOTE_SESSION_NOT_AWAITING_APPROVAL)
        record.state = "rejected"
        self._state.save_runtime_state()
        return RemoteSessionStatePayload(
            remote_session_id=remote_session_id,
            state=record.state,
            target_user_id=record.target_user_id,
            target_device_id=record.target_device_id,
        )

    _TERMINAL_STATES = ("cancelled", "rejected", "terminated", "disconnected")
    _ACTIVE_STATES = ("approved", "negotiating", "connecting", "streaming", "controlling")
    _RENDEZVOUS_SOURCE_STATES = ("approved", "negotiating")

    def cancel(self, remote_session_id: str, actor_user_id: str) -> RemoteSessionTerminatedPayload:
        record = self._state.remote_sessions.get(remote_session_id)
        if record is None:
            raise ServiceError(ErrorCode.UNKNOWN_REMOTE_SESSION)
        if actor_user_id not in (record.requester_user_id, record.target_user_id):
            raise ServiceError(ErrorCode.REMOTE_CANCEL_DENIED)
        if record.state in self._TERMINAL_STATES:
            raise ServiceError(ErrorCode.REMOTE_SESSION_ALREADY_TERMINAL)
        record.state = "cancelled"
        self._state.save_runtime_state()
        return RemoteSessionTerminatedPayload(
            remote_session_id=remote_session_id,
            state=record.state,
            detail="cancelled_by_participant",
        )

    def terminate(
        self, remote_session_id: str, actor_user_id: str
    ) -> RemoteSessionTerminatedPayload:
        record = self._state.remote_sessions.get(remote_session_id)
        if record is None:
            raise ServiceError(ErrorCode.UNKNOWN_REMOTE_SESSION)
        if actor_user_id not in (record.requester_user_id, record.target_user_id):
            raise ServiceError(ErrorCode.REMOTE_TERMINATE_DENIED)
        if record.state in self._TERMINAL_STATES:
            raise ServiceError(ErrorCode.REMOTE_SESSION_ALREADY_TERMINAL)
        if record.state not in self._ACTIVE_STATES:
            raise ServiceError(ErrorCode.REMOTE_SESSION_NOT_ACTIVE)
        role = (
            "requester"
            if actor_user_id == record.requester_user_id
            else "target"
        )
        record.state = "terminated"
        self._state.save_runtime_state()
        return RemoteSessionTerminatedPayload(
            remote_session_id=remote_session_id,
            state=record.state,
            detail=f"terminated_by_{role}",
        )

    def request_rendezvous(
        self, remote_session_id: str, actor_user_id: str
    ) -> RemoteRendezvousInfoPayload:
        record = self._state.remote_sessions.get(remote_session_id)
        if record is None:
            raise ServiceError(ErrorCode.UNKNOWN_REMOTE_SESSION)
        if actor_user_id not in (record.requester_user_id, record.target_user_id):
            raise ServiceError(ErrorCode.REMOTE_RENDEZVOUS_DENIED)
        if record.state not in self._RENDEZVOUS_SOURCE_STATES:
            raise ServiceError(ErrorCode.REMOTE_SESSION_NOT_READY_FOR_RENDEZVOUS)
        if record.state == "approved":
            record.state = "negotiating"
            self._state.save_runtime_state()
        # M106 / D9: lazily mint a per-session AES-256-GCM key the first time
        # either peer asks for rendezvous info; persist so both sides observe
        # the same key on subsequent calls.
        if not record.relay_key_b64:
            record.relay_key_b64 = generate_key_b64()
            self._state.save_runtime_state()

        candidates = [
            RemoteRendezvousCandidate(
                kind="host",
                address=f"10.0.0.{_stable_octet(record.requester_device_id)}",
                port=50000,
                priority=100,
            ),
            RemoteRendezvousCandidate(
                kind="host",
                address=f"10.0.0.{_stable_octet(record.target_device_id)}",
                port=50000,
                priority=100,
            ),
            RemoteRendezvousCandidate(
                kind="srflx",
                address="203.0.113.10",
                port=50000,
                priority=50,
            ),
            RemoteRendezvousCandidate(
                kind="relay",
                address=record.relay_endpoint.split(":")[0] if record.relay_endpoint else "relay.example.internal",
                port=int(record.relay_endpoint.split(":")[-1]) if ":" in record.relay_endpoint else 5000,
                priority=10,
            ),
        ]
        return RemoteRendezvousInfoPayload(
            remote_session_id=remote_session_id,
            state=record.state,
            candidates=candidates,
            relay_region=record.relay_region,
            relay_endpoint=record.relay_endpoint,
            relay_key_b64=record.relay_key_b64,
        )

    def disconnect(
        self,
        remote_session_id: str,
        actor_user_id: str,
        reason: str,
    ) -> RemoteSessionTerminatedPayload:
        record = self._state.remote_sessions.get(remote_session_id)
        if record is None:
            raise ServiceError(ErrorCode.UNKNOWN_REMOTE_SESSION)
        if actor_user_id not in (record.requester_user_id, record.target_user_id):
            raise ServiceError(ErrorCode.REMOTE_DISCONNECT_DENIED)
        if record.state in self._TERMINAL_STATES:
            raise ServiceError(ErrorCode.REMOTE_SESSION_ALREADY_TERMINAL)
        if record.state not in self._ACTIVE_STATES:
            raise ServiceError(ErrorCode.REMOTE_SESSION_NOT_ACTIVE)
        record.state = "disconnected"
        self._state.save_runtime_state()
        return RemoteSessionTerminatedPayload(
            remote_session_id=remote_session_id,
            state=record.state,
            detail=reason or "peer_disconnected",
        )

    def _next_remote_counter(self) -> int:
        highest = 0
        for remote_session_id in self._state.remote_sessions:
            if not remote_session_id.startswith("remote_"):
                continue
            try:
                highest = max(highest, int(remote_session_id.removeprefix("remote_")))
            except ValueError:
                continue
        return highest + 1
