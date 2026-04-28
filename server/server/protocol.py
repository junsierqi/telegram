from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """Typed error codes. The wire format uses these snake_case values.

    Keep in sync with shared/include/shared/protocol/errors.h.
    """

    UNKNOWN = "unknown"
    INVALID_CREDENTIALS = "invalid_credentials"
    INVALID_SESSION = "invalid_session"
    SESSION_ACTOR_MISMATCH = "session_actor_mismatch"
    UNSUPPORTED_MESSAGE_TYPE = "unsupported_message_type"
    UNKNOWN_CONVERSATION = "unknown_conversation"
    CONVERSATION_ACCESS_DENIED = "conversation_access_denied"
    EMPTY_MESSAGE = "empty_message"
    UNKNOWN_REMOTE_SESSION = "unknown_remote_session"
    UNKNOWN_REQUESTER_DEVICE = "unknown_requester_device"
    UNKNOWN_TARGET_DEVICE = "unknown_target_device"
    REQUESTER_DEVICE_USER_MISMATCH = "requester_device_user_mismatch"
    REQUESTER_DEVICE_SESSION_MISMATCH = "requester_device_session_mismatch"
    DEVICE_ACTION_DENIED = "device_action_denied"
    SELF_REMOTE_SESSION_NOT_ALLOWED = "self_remote_session_not_allowed"
    REMOTE_SESSION_NOT_AWAITING_APPROVAL = "remote_session_not_awaiting_approval"
    REMOTE_APPROVAL_DENIED = "remote_approval_denied"
    REMOTE_REJECTION_DENIED = "remote_rejection_denied"
    REMOTE_CANCEL_DENIED = "remote_cancel_denied"
    REMOTE_TERMINATE_DENIED = "remote_terminate_denied"
    REMOTE_DISCONNECT_DENIED = "remote_disconnect_denied"
    REMOTE_RENDEZVOUS_DENIED = "remote_rendezvous_denied"
    REMOTE_SESSION_ALREADY_TERMINAL = "remote_session_already_terminal"
    REMOTE_SESSION_NOT_ACTIVE = "remote_session_not_active"
    REMOTE_SESSION_NOT_READY_FOR_RENDEZVOUS = "remote_session_not_ready_for_rendezvous"
    REMOTE_INPUT_DENIED = "remote_input_denied"
    UNSUPPORTED_INPUT_KIND = "unsupported_input_kind"
    INVALID_INPUT_PAYLOAD = "invalid_input_payload"
    USERNAME_TAKEN = "username_taken"
    WEAK_PASSWORD = "weak_password"
    DEVICE_ID_TAKEN = "device_id_taken"
    INVALID_REGISTRATION_PAYLOAD = "invalid_registration_payload"
    UNKNOWN_USER = "unknown_user"
    CONVERSATION_PARTICIPANT_ALREADY_PRESENT = "conversation_participant_already_present"
    CONVERSATION_PARTICIPANT_NOT_PRESENT = "conversation_participant_not_present"
    CONVERSATION_TOO_FEW_PARTICIPANTS = "conversation_too_few_participants"
    UNKNOWN_MESSAGE = "unknown_message"
    MESSAGE_EDIT_DENIED = "message_edit_denied"
    MESSAGE_DELETE_DENIED = "message_delete_denied"
    MESSAGE_ALREADY_DELETED = "message_already_deleted"
    CONTACT_SELF_NOT_ALLOWED = "contact_self_not_allowed"
    CONTACT_ALREADY_ADDED = "contact_already_added"
    CONTACT_NOT_PRESENT = "contact_not_present"
    ATTACHMENT_TOO_LARGE = "attachment_too_large"
    INVALID_ATTACHMENT_PAYLOAD = "invalid_attachment_payload"
    UNKNOWN_ATTACHMENT = "unknown_attachment"
    ATTACHMENT_ACCESS_DENIED = "attachment_access_denied"


_ERROR_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.UNKNOWN: "Unknown error.",
    ErrorCode.INVALID_CREDENTIALS: "The username or password is invalid.",
    ErrorCode.INVALID_SESSION: "The session id is unknown or has expired.",
    ErrorCode.SESSION_ACTOR_MISMATCH: "The actor user does not own this session.",
    ErrorCode.UNSUPPORTED_MESSAGE_TYPE: "The server does not know how to handle this message type.",
    ErrorCode.UNKNOWN_CONVERSATION: "No conversation matches that id.",
    ErrorCode.CONVERSATION_ACCESS_DENIED: "The sender is not a participant of this conversation.",
    ErrorCode.EMPTY_MESSAGE: "A message cannot be empty.",
    ErrorCode.UNKNOWN_REMOTE_SESSION: "No remote session matches that id.",
    ErrorCode.UNKNOWN_REQUESTER_DEVICE: "The requester device is unknown.",
    ErrorCode.UNKNOWN_TARGET_DEVICE: "The target device is unknown.",
    ErrorCode.REQUESTER_DEVICE_USER_MISMATCH: "Requester device does not belong to the actor user.",
    ErrorCode.REQUESTER_DEVICE_SESSION_MISMATCH: "Requester device does not match the current session.",
    ErrorCode.DEVICE_ACTION_DENIED: "That device cannot be modified by this session.",
    ErrorCode.SELF_REMOTE_SESSION_NOT_ALLOWED: "A user cannot remote-control their own device.",
    ErrorCode.REMOTE_SESSION_NOT_AWAITING_APPROVAL: "Action requires the session to be awaiting approval.",
    ErrorCode.REMOTE_APPROVAL_DENIED: "Only the target user can approve this remote session.",
    ErrorCode.REMOTE_REJECTION_DENIED: "Only the target user can reject this remote session.",
    ErrorCode.REMOTE_CANCEL_DENIED: "Only participants can cancel this remote session.",
    ErrorCode.REMOTE_TERMINATE_DENIED: "Only participants can terminate this remote session.",
    ErrorCode.REMOTE_DISCONNECT_DENIED: "Only participants can mark this remote session disconnected.",
    ErrorCode.REMOTE_RENDEZVOUS_DENIED: "Only participants can request rendezvous info.",
    ErrorCode.REMOTE_SESSION_ALREADY_TERMINAL: "The remote session is already in a terminal state.",
    ErrorCode.REMOTE_SESSION_NOT_ACTIVE: "Action requires the session to be in an active (post-approval) state.",
    ErrorCode.REMOTE_SESSION_NOT_READY_FOR_RENDEZVOUS: "Rendezvous info is only available after approval.",
    ErrorCode.REMOTE_INPUT_DENIED: "Only the requester of an active remote session can inject input events.",
    ErrorCode.UNSUPPORTED_INPUT_KIND: "Unsupported input kind.",
    ErrorCode.INVALID_INPUT_PAYLOAD: "Input payload missing required fields for this kind.",
    ErrorCode.USERNAME_TAKEN: "That username is already registered.",
    ErrorCode.WEAK_PASSWORD: "Password is too short (minimum 8 characters).",
    ErrorCode.DEVICE_ID_TAKEN: "That device_id is already registered.",
    ErrorCode.INVALID_REGISTRATION_PAYLOAD: "Registration payload is missing or malformed.",
    ErrorCode.UNKNOWN_USER: "No user matches that user_id.",
    ErrorCode.CONVERSATION_PARTICIPANT_ALREADY_PRESENT: "That user is already a participant in this conversation.",
    ErrorCode.CONVERSATION_PARTICIPANT_NOT_PRESENT: "That user is not a participant in this conversation.",
    ErrorCode.CONVERSATION_TOO_FEW_PARTICIPANTS: "A conversation must have at least two participants.",
    ErrorCode.UNKNOWN_MESSAGE: "No message matches that id in this conversation.",
    ErrorCode.MESSAGE_EDIT_DENIED: "Only the original sender can edit this message.",
    ErrorCode.MESSAGE_DELETE_DENIED: "Only the original sender can delete this message.",
    ErrorCode.MESSAGE_ALREADY_DELETED: "That message has already been deleted.",
    ErrorCode.CONTACT_SELF_NOT_ALLOWED: "A user cannot add themselves as a contact.",
    ErrorCode.CONTACT_ALREADY_ADDED: "That user is already in your contact list.",
    ErrorCode.CONTACT_NOT_PRESENT: "That user is not in your contact list.",
    ErrorCode.ATTACHMENT_TOO_LARGE: "Attachment exceeds the maximum allowed size.",
    ErrorCode.INVALID_ATTACHMENT_PAYLOAD: "Attachment payload is missing fields or malformed.",
    ErrorCode.UNKNOWN_ATTACHMENT: "No attachment matches that id.",
    ErrorCode.ATTACHMENT_ACCESS_DENIED: "You are not a participant of the attachment's conversation.",
}


def error_message(code: ErrorCode) -> str:
    return _ERROR_MESSAGES.get(code, "Unknown error.")


class ServiceError(ValueError):
    """Raised by services to signal a typed error outcome.

    The dispatch layer turns this into a typed ERROR response payload.
    """

    def __init__(self, code: ErrorCode, message: str | None = None) -> None:
        self.code = code
        self.human_message = message or error_message(code)
        super().__init__(code.value)


class MessageType(StrEnum):
    LOGIN_REQUEST = "login_request"
    LOGIN_RESPONSE = "login_response"
    REGISTER_REQUEST = "register_request"
    REGISTER_RESPONSE = "register_response"
    PROFILE_GET_REQUEST = "profile_get_request"
    PROFILE_UPDATE_REQUEST = "profile_update_request"
    PROFILE_RESPONSE = "profile_response"
    USER_SEARCH_REQUEST = "user_search_request"
    USER_SEARCH_RESPONSE = "user_search_response"
    PRESENCE_UPDATE = "presence_update"  # fanned out by presence service on transitions
    PRESENCE_QUERY_REQUEST = "presence_query_request"
    PRESENCE_QUERY_RESPONSE = "presence_query_response"
    HEARTBEAT_PING = "heartbeat_ping"
    HEARTBEAT_ACK = "heartbeat_ack"
    CONVERSATION_SYNC = "conversation_sync"
    CONVERSATION_CREATE = "conversation_create"
    CONVERSATION_ADD_PARTICIPANT = "conversation_add_participant"
    CONVERSATION_REMOVE_PARTICIPANT = "conversation_remove_participant"
    CONVERSATION_UPDATED = "conversation_updated"
    MESSAGE_SEND = "message_send"
    MESSAGE_DELIVER = "message_deliver"
    MESSAGE_READ = "message_read"
    MESSAGE_READ_UPDATE = "message_read_update"
    MESSAGE_EDIT = "message_edit"
    MESSAGE_EDITED = "message_edited"
    MESSAGE_DELETE = "message_delete"
    MESSAGE_DELETED = "message_deleted"
    MESSAGE_FORWARD = "message_forward"
    MESSAGE_REACTION = "message_reaction"
    MESSAGE_REACTION_UPDATED = "message_reaction_updated"
    MESSAGE_PIN = "message_pin"
    MESSAGE_PIN_UPDATED = "message_pin_updated"
    MESSAGE_SEARCH_REQUEST = "message_search_request"
    MESSAGE_SEARCH_RESPONSE = "message_search_response"
    MESSAGE_SEND_ATTACHMENT = "message_send_attachment"
    ATTACHMENT_FETCH_REQUEST = "attachment_fetch_request"
    ATTACHMENT_FETCH_RESPONSE = "attachment_fetch_response"
    DEVICE_LIST_REQUEST = "device_list_request"
    DEVICE_LIST_RESPONSE = "device_list_response"
    DEVICE_REVOKE_REQUEST = "device_revoke_request"
    DEVICE_TRUST_UPDATE_REQUEST = "device_trust_update_request"
    CONTACT_ADD = "contact_add"
    CONTACT_REMOVE = "contact_remove"
    CONTACT_LIST_REQUEST = "contact_list_request"
    CONTACT_LIST_RESPONSE = "contact_list_response"
    REMOTE_INVITE = "remote_invite"
    REMOTE_APPROVE = "remote_approve"
    REMOTE_REJECT = "remote_reject"
    REMOTE_CANCEL = "remote_cancel"
    REMOTE_TERMINATE = "remote_terminate"
    REMOTE_DISCONNECT = "remote_disconnect"
    REMOTE_RENDEZVOUS_REQUEST = "remote_rendezvous_request"
    REMOTE_INPUT_EVENT = "remote_input_event"
    REMOTE_INPUT_ACK = "remote_input_ack"
    REMOTE_SESSION_STATE = "remote_session_state"
    REMOTE_RENDEZVOUS_INFO = "remote_rendezvous_info"
    REMOTE_RELAY_ASSIGNMENT = "remote_relay_assignment"
    REMOTE_SESSION_TERMINATED = "remote_session_terminated"
    ERROR = "error"


@dataclass(slots=True)
class Envelope:
    type: MessageType
    correlation_id: str
    session_id: str
    actor_user_id: str
    sequence: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "correlation_id": self.correlation_id,
            "session_id": self.session_id,
            "actor_user_id": self.actor_user_id,
            "sequence": self.sequence,
        }


@dataclass(slots=True)
class RequestMessage:
    envelope: Envelope
    payload: Any

    @property
    def type(self) -> MessageType:
        return self.envelope.type


@dataclass(slots=True)
class ResponseMessage:
    envelope: Envelope
    payload: Any

    def to_dict(self) -> dict[str, Any]:
        if hasattr(self.payload, "__dataclass_fields__"):
            payload = asdict(self.payload)
        else:
            payload = self.payload
        return {**self.envelope.to_dict(), "payload": payload}


@dataclass(slots=True)
class ErrorResponsePayload:
    code: str
    message: str


@dataclass(slots=True)
class LoginResponsePayload:
    session_id: str
    user_id: str
    display_name: str
    device_id: str


@dataclass(slots=True)
class EmptyPayload:
    pass


@dataclass(slots=True)
class LoginRequestPayload:
    username: str
    password: str
    device_id: str


@dataclass(slots=True)
class RegisterRequestPayload:
    username: str
    password: str
    display_name: str
    device_id: str
    device_label: str = ""
    platform: str = "unknown"


@dataclass(slots=True)
class RegisterResponsePayload:
    session_id: str
    user_id: str
    display_name: str
    device_id: str


@dataclass(slots=True)
class ProfileUpdateRequestPayload:
    display_name: str


@dataclass(slots=True)
class ProfileResponsePayload:
    user_id: str
    username: str
    display_name: str


@dataclass(slots=True)
class UserSearchRequestPayload:
    query: str
    limit: int = 20


@dataclass(slots=True)
class UserSearchResultDescriptor:
    user_id: str
    username: str
    display_name: str
    online: bool
    is_contact: bool


@dataclass(slots=True)
class UserSearchResponsePayload:
    results: list[UserSearchResultDescriptor]


@dataclass(slots=True)
class MessageSendRequestPayload:
    conversation_id: str
    text: str
    reply_to_message_id: str = ""


@dataclass(slots=True)
class RemoteInviteRequestPayload:
    requester_device_id: str
    target_device_id: str


@dataclass(slots=True)
class RemoteApproveRequestPayload:
    remote_session_id: str


@dataclass(slots=True)
class RemoteSessionActionRequestPayload:
    remote_session_id: str


@dataclass(slots=True)
class RemoteDisconnectRequestPayload:
    remote_session_id: str
    reason: str = "peer_disconnected"


@dataclass(slots=True)
class DeviceDescriptor:
    device_id: str
    label: str
    platform: str
    trusted: bool
    active: bool


@dataclass(slots=True)
class DeviceListResponsePayload:
    devices: list[DeviceDescriptor]


@dataclass(slots=True)
class DeviceRevokeRequestPayload:
    device_id: str


@dataclass(slots=True)
class DeviceTrustUpdateRequestPayload:
    device_id: str
    trusted: bool


@dataclass(slots=True)
class ContactDescriptor:
    user_id: str
    display_name: str
    online: bool


@dataclass(slots=True)
class ContactTargetRequestPayload:
    target_user_id: str


@dataclass(slots=True)
class ContactListResponsePayload:
    contacts: list[ContactDescriptor]


@dataclass(slots=True)
class MessageDescriptor:
    message_id: str
    sender_user_id: str
    text: str
    created_at_ms: int = 0
    edited: bool = False
    deleted: bool = False
    attachment_id: str = ""
    filename: str = ""
    mime_type: str = ""
    size_bytes: int = 0
    reply_to_message_id: str = ""
    forwarded_from_conversation_id: str = ""
    forwarded_from_message_id: str = ""
    forwarded_from_sender_user_id: str = ""
    reaction_summary: str = ""
    pinned: bool = False


@dataclass(slots=True)
class ConversationChangeDescriptor:
    version: int
    kind: str
    message_id: str = ""
    sender_user_id: str = ""
    text: str = ""
    reader_user_id: str = ""
    last_read_message_id: str = ""
    reply_to_message_id: str = ""
    forwarded_from_conversation_id: str = ""
    forwarded_from_message_id: str = ""
    forwarded_from_sender_user_id: str = ""
    reaction_summary: str = ""
    pinned: bool = False


@dataclass(slots=True)
class ConversationDescriptor:
    conversation_id: str
    participant_user_ids: list[str]
    messages: list[MessageDescriptor]
    title: str = ""
    read_markers: dict[str, str] = field(default_factory=dict)
    version: int = 0
    changes: list[ConversationChangeDescriptor] = field(default_factory=list)
    next_before_message_id: str = ""
    has_more: bool = False


@dataclass(slots=True)
class MessageReadRequestPayload:
    conversation_id: str
    message_id: str


@dataclass(slots=True)
class MessageReadUpdatePayload:
    conversation_id: str
    reader_user_id: str
    last_read_message_id: str


@dataclass(slots=True)
class MessageEditRequestPayload:
    conversation_id: str
    message_id: str
    text: str


@dataclass(slots=True)
class MessageEditedPayload:
    conversation_id: str
    message_id: str
    text: str
    sender_user_id: str
    edited: bool = True


@dataclass(slots=True)
class MessageDeleteRequestPayload:
    conversation_id: str
    message_id: str


@dataclass(slots=True)
class MessageDeletedPayload:
    conversation_id: str
    message_id: str
    sender_user_id: str
    deleted: bool = True


@dataclass(slots=True)
class MessageForwardRequestPayload:
    source_conversation_id: str
    source_message_id: str
    target_conversation_id: str


@dataclass(slots=True)
class MessageReactionRequestPayload:
    conversation_id: str
    message_id: str
    emoji: str


@dataclass(slots=True)
class MessageReactionUpdatedPayload:
    conversation_id: str
    message_id: str
    actor_user_id: str
    emoji: str
    reaction_summary: str


@dataclass(slots=True)
class MessagePinRequestPayload:
    conversation_id: str
    message_id: str
    pinned: bool


@dataclass(slots=True)
class MessagePinUpdatedPayload:
    conversation_id: str
    message_id: str
    actor_user_id: str
    pinned: bool


@dataclass(slots=True)
class MessageSearchRequestPayload:
    query: str
    conversation_id: str = ""
    limit: int = 50
    offset: int = 0


@dataclass(slots=True)
class MessageSearchResultDescriptor:
    conversation_id: str
    conversation_title: str
    message_id: str
    sender_user_id: str
    text: str
    created_at_ms: int = 0
    attachment_id: str = ""
    filename: str = ""
    snippet: str = ""


@dataclass(slots=True)
class MessageSearchResponsePayload:
    results: list[MessageSearchResultDescriptor]
    next_offset: int = 0
    has_more: bool = False


@dataclass(slots=True)
class ConversationCreateRequestPayload:
    participant_user_ids: list[str]
    title: str = ""


@dataclass(slots=True)
class ConversationParticipantRequestPayload:
    conversation_id: str
    user_id: str


@dataclass(slots=True)
class ConversationSyncRequestPayload:
    cursors: dict[str, str] = field(default_factory=dict)
    versions: dict[str, int] = field(default_factory=dict)
    history_limits: dict[str, int] = field(default_factory=dict)
    before_message_ids: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class ConversationSyncResponsePayload:
    conversations: list[ConversationDescriptor]


@dataclass(slots=True)
class MessageDeliverPayload:
    conversation_id: str
    message_id: str
    sender_user_id: str
    text: str
    created_at_ms: int = 0
    attachment_id: str = ""
    filename: str = ""
    mime_type: str = ""
    size_bytes: int = 0
    reply_to_message_id: str = ""
    forwarded_from_conversation_id: str = ""
    forwarded_from_message_id: str = ""
    forwarded_from_sender_user_id: str = ""


@dataclass(slots=True)
class MessageSendAttachmentRequestPayload:
    conversation_id: str
    caption: str
    filename: str
    mime_type: str
    content_b64: str
    size_bytes: int


@dataclass(slots=True)
class AttachmentFetchRequestPayload:
    attachment_id: str


@dataclass(slots=True)
class AttachmentFetchResponsePayload:
    attachment_id: str
    conversation_id: str
    uploader_user_id: str
    filename: str
    mime_type: str
    size_bytes: int
    content_b64: str


@dataclass(slots=True)
class RemoteSessionStatePayload:
    remote_session_id: str
    state: str
    target_user_id: str
    target_device_id: str


@dataclass(slots=True)
class RemoteRelayAssignmentPayload:
    remote_session_id: str
    state: str
    relay_region: str
    relay_endpoint: str


@dataclass(slots=True)
class RemoteSessionTerminatedPayload:
    remote_session_id: str
    state: str
    detail: str


@dataclass(slots=True)
class RemoteRendezvousCandidate:
    kind: str  # "host" | "srflx" | "relay"
    address: str
    port: int
    priority: int


@dataclass(slots=True)
class RemoteRendezvousInfoPayload:
    remote_session_id: str
    state: str
    candidates: list[RemoteRendezvousCandidate]
    relay_region: str
    relay_endpoint: str


# Input events are small and vary by kind, so carry a generic payload dict
# alongside the kind string. Dispatch validates required fields per kind.
@dataclass(slots=True)
class RemoteInputEventRequestPayload:
    remote_session_id: str
    kind: str  # "key" | "mouse_move" | "mouse_button" | "scroll"
    data: dict[str, Any]


@dataclass(slots=True)
class RemoteInputAckPayload:
    remote_session_id: str
    sequence: int
    kind: str


@dataclass(slots=True)
class HeartbeatPingRequestPayload:
    client_timestamp_ms: int = 0


@dataclass(slots=True)
class HeartbeatAckPayload:
    session_id: str
    server_timestamp_ms: int
    client_timestamp_ms: int


@dataclass(slots=True)
class PresenceQueryRequestPayload:
    user_ids: list[str]


@dataclass(slots=True)
class PresenceUserStatus:
    user_id: str
    online: bool
    last_seen_at_ms: int


@dataclass(slots=True)
class PresenceQueryResponsePayload:
    users: list[PresenceUserStatus]
    server_timestamp_ms: int


@dataclass(slots=True)
class PresenceUpdatePayload:
    """Pushed to peers (anyone sharing a conversation) when a user's online
    state transitions. Subscribers update their local presence cache without
    needing to poll PRESENCE_QUERY_REQUEST."""
    user_id: str
    online: bool
    last_seen_at_ms: int


def make_envelope(
    message_type: MessageType,
    *,
    correlation_id: str,
    session_id: str = "",
    actor_user_id: str = "",
    sequence: int = 0,
) -> dict[str, Any]:
    return Envelope(
        type=message_type,
        correlation_id=correlation_id,
        session_id=session_id,
        actor_user_id=actor_user_id,
        sequence=sequence,
    ).to_dict()


def parse_request(message: dict[str, Any]) -> RequestMessage:
    payload = message.get("payload", {})
    message_type = MessageType(message["type"])
    return RequestMessage(
        envelope=Envelope(
            type=message_type,
            correlation_id=message.get("correlation_id", "corr_missing"),
            session_id=message.get("session_id", ""),
            actor_user_id=message.get("actor_user_id", ""),
            sequence=message.get("sequence", 0),
        ),
        payload=parse_request_payload(message_type, payload),
    )


def parse_request_payload(message_type: MessageType, payload: dict[str, Any]) -> Any:
    if message_type == MessageType.LOGIN_REQUEST:
        return LoginRequestPayload(
            username=payload["username"],
            password=payload["password"],
            device_id=payload["device_id"],
        )
    if message_type == MessageType.CONVERSATION_CREATE:
        return ConversationCreateRequestPayload(
            participant_user_ids=list(payload.get("participant_user_ids", [])),
            title=payload.get("title", ""),
        )
    if message_type in (
        MessageType.CONVERSATION_ADD_PARTICIPANT,
        MessageType.CONVERSATION_REMOVE_PARTICIPANT,
    ):
        return ConversationParticipantRequestPayload(
            conversation_id=payload["conversation_id"],
            user_id=payload["user_id"],
        )
    if message_type == MessageType.MESSAGE_READ:
        return MessageReadRequestPayload(
            conversation_id=payload["conversation_id"],
            message_id=payload["message_id"],
        )
    if message_type == MessageType.MESSAGE_EDIT:
        return MessageEditRequestPayload(
            conversation_id=payload["conversation_id"],
            message_id=payload["message_id"],
            text=payload["text"],
        )
    if message_type == MessageType.MESSAGE_DELETE:
        return MessageDeleteRequestPayload(
            conversation_id=payload["conversation_id"],
            message_id=payload["message_id"],
        )
    if message_type == MessageType.MESSAGE_FORWARD:
        return MessageForwardRequestPayload(
            source_conversation_id=payload["source_conversation_id"],
            source_message_id=payload["source_message_id"],
            target_conversation_id=payload["target_conversation_id"],
        )
    if message_type == MessageType.MESSAGE_REACTION:
        return MessageReactionRequestPayload(
            conversation_id=payload["conversation_id"],
            message_id=payload["message_id"],
            emoji=payload["emoji"],
        )
    if message_type == MessageType.MESSAGE_PIN:
        return MessagePinRequestPayload(
            conversation_id=payload["conversation_id"],
            message_id=payload["message_id"],
            pinned=bool(payload.get("pinned", True)),
        )
    if message_type == MessageType.MESSAGE_SEARCH_REQUEST:
        return MessageSearchRequestPayload(
            query=payload.get("query", ""),
            conversation_id=payload.get("conversation_id", ""),
            limit=int(payload.get("limit", 50)),
            offset=int(payload.get("offset", 0)),
        )
    if message_type == MessageType.MESSAGE_SEND_ATTACHMENT:
        return MessageSendAttachmentRequestPayload(
            conversation_id=payload["conversation_id"],
            caption=payload.get("caption", ""),
            filename=payload["filename"],
            mime_type=payload.get("mime_type", "application/octet-stream"),
            content_b64=payload["content_b64"],
            size_bytes=int(payload["size_bytes"]),
        )
    if message_type == MessageType.ATTACHMENT_FETCH_REQUEST:
        return AttachmentFetchRequestPayload(attachment_id=payload["attachment_id"])
    if message_type == MessageType.REGISTER_REQUEST:
        return RegisterRequestPayload(
            username=payload["username"],
            password=payload["password"],
            display_name=payload["display_name"],
            device_id=payload["device_id"],
            device_label=payload.get("device_label", ""),
            platform=payload.get("platform", "unknown"),
        )
    if message_type == MessageType.PROFILE_UPDATE_REQUEST:
        return ProfileUpdateRequestPayload(display_name=payload["display_name"])
    if message_type == MessageType.USER_SEARCH_REQUEST:
        return UserSearchRequestPayload(
            query=payload.get("query", ""),
            limit=int(payload.get("limit", 20)),
        )
    if message_type == MessageType.CONVERSATION_SYNC:
        raw_cursors = payload.get("cursors", {})
        cursors = raw_cursors if isinstance(raw_cursors, dict) else {}
        raw_versions = payload.get("versions", {})
        versions = raw_versions if isinstance(raw_versions, dict) else {}
        raw_history_limits = payload.get("history_limits", payload.get("message_limits", {}))
        history_limits = raw_history_limits if isinstance(raw_history_limits, dict) else {}
        raw_before_message_ids = payload.get("before_message_ids", {})
        before_message_ids = raw_before_message_ids if isinstance(raw_before_message_ids, dict) else {}
        return ConversationSyncRequestPayload(
            cursors={str(key): str(value) for key, value in cursors.items() if str(value)},
            versions={
                str(key): int(value)
                for key, value in versions.items()
            },
            history_limits={
                str(key): int(value)
                for key, value in history_limits.items()
            },
            before_message_ids={
                str(key): str(value)
                for key, value in before_message_ids.items()
                if str(value)
            },
        )
    if message_type in (
        MessageType.DEVICE_LIST_REQUEST,
        MessageType.CONTACT_LIST_REQUEST,
        MessageType.PROFILE_GET_REQUEST,
    ):
        return EmptyPayload()
    if message_type in (MessageType.CONTACT_ADD, MessageType.CONTACT_REMOVE):
        return ContactTargetRequestPayload(target_user_id=payload["target_user_id"])
    if message_type == MessageType.DEVICE_REVOKE_REQUEST:
        return DeviceRevokeRequestPayload(device_id=payload["device_id"])
    if message_type == MessageType.DEVICE_TRUST_UPDATE_REQUEST:
        return DeviceTrustUpdateRequestPayload(
            device_id=payload["device_id"],
            trusted=bool(payload["trusted"]),
        )
    if message_type == MessageType.MESSAGE_SEND:
        return MessageSendRequestPayload(
            conversation_id=payload["conversation_id"],
            text=payload["text"],
            reply_to_message_id=payload.get("reply_to_message_id", ""),
        )
    if message_type == MessageType.REMOTE_INVITE:
        return RemoteInviteRequestPayload(
            requester_device_id=payload["requester_device_id"],
            target_device_id=payload["target_device_id"],
        )
    if message_type == MessageType.REMOTE_APPROVE:
        return RemoteApproveRequestPayload(remote_session_id=payload["remote_session_id"])
    if message_type in (
        MessageType.REMOTE_REJECT,
        MessageType.REMOTE_CANCEL,
        MessageType.REMOTE_TERMINATE,
        MessageType.REMOTE_RENDEZVOUS_REQUEST,
    ):
        return RemoteSessionActionRequestPayload(remote_session_id=payload["remote_session_id"])
    if message_type == MessageType.REMOTE_DISCONNECT:
        return RemoteDisconnectRequestPayload(
            remote_session_id=payload["remote_session_id"],
            reason=payload.get("reason", "peer_disconnected"),
        )
    if message_type == MessageType.REMOTE_INPUT_EVENT:
        return RemoteInputEventRequestPayload(
            remote_session_id=payload["remote_session_id"],
            kind=payload["kind"],
            data=payload.get("data", {}),
        )
    if message_type == MessageType.HEARTBEAT_PING:
        return HeartbeatPingRequestPayload(
            client_timestamp_ms=int(payload.get("client_timestamp_ms", 0)),
        )
    if message_type == MessageType.PRESENCE_QUERY_REQUEST:
        return PresenceQueryRequestPayload(
            user_ids=list(payload.get("user_ids", [])),
        )
    return payload


def make_response(
    message_type: MessageType,
    *,
    correlation_id: str,
    session_id: str = "",
    actor_user_id: str = "",
    sequence: int = 1,
    payload: dict[str, Any] | None = None,
) -> ResponseMessage:
    return ResponseMessage(
        envelope=Envelope(
            type=message_type,
            correlation_id=correlation_id,
            session_id=session_id,
            actor_user_id=actor_user_id,
            sequence=sequence,
        ),
        payload={} if payload is None else payload,
    )
