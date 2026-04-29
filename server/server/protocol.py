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
    UNKNOWN_UPLOAD = "unknown_upload"
    UPLOAD_TOO_LARGE = "upload_too_large"
    UPLOAD_CHUNK_OUT_OF_ORDER = "upload_chunk_out_of_order"
    UPLOAD_SIZE_MISMATCH = "upload_size_mismatch"
    UPLOAD_LIMIT_REACHED = "upload_limit_reached"
    INVALID_PHONE_NUMBER = "invalid_phone_number"
    PHONE_OTP_RATE_LIMITED = "phone_otp_rate_limited"
    INVALID_OTP_CODE = "invalid_otp_code"
    OTP_EXPIRED = "otp_expired"
    OTP_ATTEMPTS_EXHAUSTED = "otp_attempts_exhausted"
    RATE_LIMITED = "rate_limited"
    TWO_FA_ALREADY_ENABLED = "two_fa_already_enabled"
    TWO_FA_NOT_ENABLED = "two_fa_not_enabled"
    INVALID_TWO_FA_CODE = "invalid_two_fa_code"
    TWO_FA_REQUIRED = "two_fa_required"
    ACCOUNT_DELETE_AUTH_FAILED = "account_delete_auth_failed"
    BLOCKED_BY_RECIPIENT = "blocked_by_recipient"
    ALREADY_BLOCKED = "already_blocked"
    NOT_BLOCKED = "not_blocked"
    # M102 polls
    NOT_A_POLL = "not_a_poll"
    POLL_CLOSED = "poll_closed"
    POLL_INVALID_OPTION = "poll_invalid_option"
    POLL_TOO_FEW_OPTIONS = "poll_too_few_options"
    POLL_CLOSE_DENIED = "poll_close_denied"
    # M103 group permissions + admin roles
    CONVERSATION_PERMISSION_DENIED = "conversation_permission_denied"
    CONVERSATION_OWNER_ROLE_IMMUTABLE = "conversation_owner_role_immutable"
    CONVERSATION_INVALID_ROLE = "conversation_invalid_role"


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
    ErrorCode.UNKNOWN_UPLOAD: "No active upload session matches that id.",
    ErrorCode.UPLOAD_TOO_LARGE: "Upload exceeds the maximum allowed total size.",
    ErrorCode.UPLOAD_CHUNK_OUT_OF_ORDER: "Upload chunks must arrive in monotonically increasing sequence.",
    ErrorCode.UPLOAD_SIZE_MISMATCH: "Stitched chunk total does not match the declared upload size.",
    ErrorCode.UPLOAD_LIMIT_REACHED: "Maximum concurrent uploads per user reached.",
    ErrorCode.INVALID_PHONE_NUMBER: "Phone number is missing or not in E.164 format.",
    ErrorCode.PHONE_OTP_RATE_LIMITED: "Too many OTP requests for this phone number; wait before retrying.",
    ErrorCode.INVALID_OTP_CODE: "OTP code does not match the most recent issued code.",
    ErrorCode.OTP_EXPIRED: "OTP code has expired; request a new one.",
    ErrorCode.OTP_ATTEMPTS_EXHAUSTED: "Too many OTP verification attempts; request a new code.",
    ErrorCode.RATE_LIMITED: "Too many requests for this session; slow down and retry.",
    ErrorCode.TWO_FA_ALREADY_ENABLED: "Two-factor authentication is already enabled for this account.",
    ErrorCode.TWO_FA_NOT_ENABLED: "Two-factor authentication is not enabled for this account.",
    ErrorCode.INVALID_TWO_FA_CODE: "TOTP code does not match; check the authenticator app and retry.",
    ErrorCode.TWO_FA_REQUIRED: "Two-factor authentication is required; include two_fa_code on login.",
    ErrorCode.ACCOUNT_DELETE_AUTH_FAILED: "Account delete must be confirmed with the current password (and TOTP if 2FA is enabled).",
    ErrorCode.BLOCKED_BY_RECIPIENT: "The recipient has blocked you; the message was not delivered.",
    ErrorCode.ALREADY_BLOCKED: "That user is already on your block list.",
    ErrorCode.NOT_BLOCKED: "That user is not on your block list.",
    ErrorCode.NOT_A_POLL: "That message is not a poll; vote/close are not applicable.",
    ErrorCode.POLL_CLOSED: "Voting on this poll has been closed by the author.",
    ErrorCode.POLL_INVALID_OPTION: "The selected option index is out of range for this poll.",
    ErrorCode.POLL_TOO_FEW_OPTIONS: "A poll must have at least two options.",
    ErrorCode.POLL_CLOSE_DENIED: "Only the poll author can close the poll.",
    ErrorCode.CONVERSATION_PERMISSION_DENIED: "Your role in this conversation does not allow that action.",
    ErrorCode.CONVERSATION_OWNER_ROLE_IMMUTABLE: "The conversation owner's role cannot be changed.",
    ErrorCode.CONVERSATION_INVALID_ROLE: "Role must be one of: owner, admin, member.",
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
    PUSH_TOKEN_REGISTER = "push_token_register"
    PUSH_TOKEN_UNREGISTER = "push_token_unregister"
    PUSH_TOKEN_LIST_REQUEST = "push_token_list_request"
    PUSH_TOKEN_LIST_RESPONSE = "push_token_list_response"
    PUSH_TOKEN_ACK = "push_token_ack"
    # Chunked attachment upload (M88) — for files >1 MB the small-file
    # MESSAGE_SEND_ATTACHMENT path is bypassed in favour of init/chunk/complete.
    ATTACHMENT_UPLOAD_INIT_REQUEST = "attachment_upload_init_request"
    ATTACHMENT_UPLOAD_INIT_RESPONSE = "attachment_upload_init_response"
    ATTACHMENT_UPLOAD_CHUNK_REQUEST = "attachment_upload_chunk_request"
    ATTACHMENT_UPLOAD_CHUNK_ACK = "attachment_upload_chunk_ack"
    ATTACHMENT_UPLOAD_COMPLETE_REQUEST = "attachment_upload_complete_request"
    # Phone-number + OTP authentication (M90)
    PHONE_OTP_REQUEST = "phone_otp_request"
    PHONE_OTP_REQUEST_RESPONSE = "phone_otp_request_response"
    PHONE_OTP_VERIFY_REQUEST = "phone_otp_verify_request"
    PHONE_OTP_VERIFY_RESPONSE = "phone_otp_verify_response"
    # M94 TOTP 2FA
    TWO_FA_ENABLE_REQUEST = "two_fa_enable_request"
    TWO_FA_ENABLE_RESPONSE = "two_fa_enable_response"
    TWO_FA_VERIFY_REQUEST = "two_fa_verify_request"
    TWO_FA_VERIFY_RESPONSE = "two_fa_verify_response"
    TWO_FA_DISABLE_REQUEST = "two_fa_disable_request"
    TWO_FA_DISABLE_RESPONSE = "two_fa_disable_response"
    # M95 GDPR-style account lifecycle
    ACCOUNT_EXPORT_REQUEST = "account_export_request"
    ACCOUNT_EXPORT_RESPONSE = "account_export_response"
    ACCOUNT_DELETE_REQUEST = "account_delete_request"
    ACCOUNT_DELETE_RESPONSE = "account_delete_response"
    # M98 block + mute
    BLOCK_USER_REQUEST = "block_user_request"
    UNBLOCK_USER_REQUEST = "unblock_user_request"
    BLOCKED_USERS_LIST_REQUEST = "blocked_users_list_request"
    BLOCKED_USERS_LIST_RESPONSE = "blocked_users_list_response"
    BLOCK_USER_ACK = "block_user_ack"
    CONVERSATION_MUTE_UPDATE_REQUEST = "conversation_mute_update_request"
    CONVERSATION_MUTE_UPDATE_RESPONSE = "conversation_mute_update_response"
    # M99 server-side drafts
    DRAFT_SAVE_REQUEST = "draft_save_request"
    DRAFT_SAVE_RESPONSE = "draft_save_response"
    DRAFT_LIST_REQUEST = "draft_list_request"
    DRAFT_LIST_RESPONSE = "draft_list_response"
    DRAFT_CLEAR_REQUEST = "draft_clear_request"
    DRAFT_CLEAR_RESPONSE = "draft_clear_response"
    # M100 pinned + archived chats (per-user)
    CONVERSATION_PIN_TOGGLE_REQUEST = "conversation_pin_toggle_request"
    CONVERSATION_PIN_TOGGLE_RESPONSE = "conversation_pin_toggle_response"
    CONVERSATION_ARCHIVE_TOGGLE_REQUEST = "conversation_archive_toggle_request"
    CONVERSATION_ARCHIVE_TOGGLE_RESPONSE = "conversation_archive_toggle_response"
    # M101 profile + group avatars
    PROFILE_AVATAR_UPDATE_REQUEST = "profile_avatar_update_request"
    PROFILE_AVATAR_UPDATE_RESPONSE = "profile_avatar_update_response"
    CONVERSATION_AVATAR_UPDATE_REQUEST = "conversation_avatar_update_request"
    CONVERSATION_AVATAR_UPDATE_RESPONSE = "conversation_avatar_update_response"
    # M102 polls (live as a special message type in conversation history)
    POLL_CREATE_REQUEST = "poll_create_request"
    POLL_VOTE_REQUEST = "poll_vote_request"
    POLL_CLOSE_REQUEST = "poll_close_request"
    POLL_UPDATED = "poll_updated"
    # M103 group permissions + admin roles
    CONVERSATION_ROLE_UPDATE_REQUEST = "conversation_role_update_request"
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
    # M94: optional. When the user has 2FA enabled, login fails with
    # TWO_FA_REQUIRED unless this carries a valid 6-digit TOTP code.
    two_fa_code: str = ""


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
    avatar_attachment_id: str = ""  # M101


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
class PollOptionDescriptor:
    """Vote option carried inside PollDescriptor.options. Tallies are
    computed live on the server from the (poll → user_id → option_index)
    map kept on the message dict, not stored separately."""
    text: str
    vote_count: int = 0


@dataclass(slots=True)
class PollDescriptor:
    """M102 poll state. `multiple_choice` toggles whether one user can
    select more than one option. `closed` freezes voting (only the
    author may close). The `voters` list reports which option indices
    the *requesting* user voted for — None for non-voters."""
    options: list[PollOptionDescriptor] = field(default_factory=list)
    multiple_choice: bool = False
    closed: bool = False
    total_voters: int = 0


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
    # M102: poll state. `poll` is None for normal messages; for polls the
    # poll question lives in `text` and `poll` carries the option list,
    # current tallies, vote rule, and closed flag. Embedded directly so
    # one round-trip surfaces both the chat history and the poll status.
    poll: "PollDescriptor | None" = None


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
    # M100 per-user view flags. These reflect the actor's preferences only,
    # not a global property of the conversation. Sync materializes them
    # from the per-(user, conversation) maps in InMemoryState.
    pinned: bool = False
    archived: bool = False
    # M101: group/conversation avatar pointer. Empty = default.
    avatar_attachment_id: str = ""
    # M103: per-(conversation, user) role map. Same canonical strings as
    # the server side ("owner", "admin", "member"). Missing entries are
    # implicit members; the client can still use this to render badges
    # or gate UI affordances.
    roles: dict[str, str] = field(default_factory=dict)


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
class PushTokenRegisterRequestPayload:
    """Mobile client tells the server which platform-issued push token (FCM
    registration ID, APNs device token, …) corresponds to its session/device,
    so the server can deliver wake-ups when the TCP control plane is offline.

    `platform` is the free-form transport label: "fcm" / "apns" / "wns" /
    "mock" — server treats it opaquely and just stores it alongside the
    token so a future delivery worker can pick the right transport.
    """
    platform: str
    token: str


@dataclass(slots=True)
class PushTokenUnregisterRequestPayload:
    platform: str
    token: str


@dataclass(slots=True)
class PushTokenAckPayload:
    platform: str
    token: str
    registered: bool  # True for register, False for unregister


@dataclass(slots=True)
class PushTokenDescriptor:
    user_id: str
    device_id: str
    platform: str
    token: str
    registered_at_ms: int


@dataclass(slots=True)
class PushTokenListResponsePayload:
    tokens: list[PushTokenDescriptor]


@dataclass(slots=True)
class AttachmentUploadInitRequestPayload:
    """Begin a chunked upload. The 1 MB inline send-attachment path is still
    fast for small files; this path lifts the cap up to 64 MB by streaming."""
    conversation_id: str
    filename: str
    mime_type: str
    total_size_bytes: int


@dataclass(slots=True)
class AttachmentUploadInitResponsePayload:
    upload_id: str
    chunk_size: int  # server-suggested max chunk byte size for the client


@dataclass(slots=True)
class AttachmentUploadChunkRequestPayload:
    upload_id: str
    sequence: int      # 0-based monotonic chunk index
    content_b64: str


@dataclass(slots=True)
class AttachmentUploadChunkAckPayload:
    upload_id: str
    sequence: int
    received_bytes: int  # cumulative bytes received so far


@dataclass(slots=True)
class AttachmentUploadCompleteRequestPayload:
    upload_id: str
    caption: str = ""


@dataclass(slots=True)
class PhoneOtpRequestPayload:
    """Client asks the server to issue and 'send' an OTP to this phone number.
    The actual SMS transport is pluggable (MockSender by default — code goes
    to stderr/log + a test queue, perfect for first-party clients during
    development; TwilioSender wires to a real gateway via PA-009)."""
    phone_number: str  # E.164 format, e.g. "+15551234567"


@dataclass(slots=True)
class PhoneOtpRequestResponsePayload:
    phone_number: str
    code_length: int
    expires_in_seconds: int


@dataclass(slots=True)
class PhoneOtpVerifyRequestPayload:
    """Submit the 6-digit code the user typed in. Server creates / re-uses a
    user keyed by phone number, mints a session, and returns the same shape
    LOGIN_RESPONSE would produce so client code paths converge."""
    phone_number: str
    code: str
    device_id: str
    display_name: str = ""


@dataclass(slots=True)
class PhoneOtpVerifyResponsePayload:
    session_id: str
    user_id: str
    display_name: str
    device_id: str
    new_account: bool


# ---- M94 TOTP 2FA ----

@dataclass(slots=True)
class TwoFaEnableResponsePayload:
    """Server-issued enrollment material. Client renders the URI as a QR
    code, the user scans into an authenticator app, then submits the first
    code via TWO_FA_VERIFY_REQUEST to flip 2FA on."""
    secret: str          # base32-encoded TOTP secret
    provisioning_uri: str  # otpauth://totp/...


@dataclass(slots=True)
class TwoFaVerifyRequestPayload:
    code: str            # 6-digit TOTP code from the authenticator app


@dataclass(slots=True)
class TwoFaVerifyResponsePayload:
    enabled: bool


@dataclass(slots=True)
class TwoFaDisableRequestPayload:
    code: str            # require a fresh TOTP to turn 2FA off


# ---- M95 account lifecycle ----

@dataclass(slots=True)
class AccountExportResponsePayload:
    """User-readable JSON dump of everything the server keeps about this
    account: profile, devices, sessions, contacts, push tokens, and the
    messages this user authored (with conversation context). Treat as
    PII-grade output: must only flow back to the requester themselves."""
    exported_at_ms: int
    user_id: str
    profile: dict[str, Any]
    devices: list[dict[str, Any]]
    sessions: list[dict[str, Any]]
    contacts: list[dict[str, Any]]
    push_tokens: list[dict[str, Any]]
    authored_messages: list[dict[str, Any]]


@dataclass(slots=True)
class AccountDeleteRequestPayload:
    """Confirms the deletion intent: server verifies password (+ TOTP code
    if 2FA is enabled). This is a two-factor confirmation by design — losing
    the account is irreversible."""
    password: str
    two_fa_code: str = ""


@dataclass(slots=True)
class AccountDeleteResponsePayload:
    user_id: str
    sessions_revoked: int
    devices_removed: int
    push_tokens_removed: int
    messages_tombstoned: int
    contacts_removed: int


# ---- M98 block + mute ----

@dataclass(slots=True)
class BlockUserRequestPayload:
    """target_user_id is the user being added to / removed from the actor's
    block list. Block is one-directional in our model: A blocking B prevents
    B from sending DMs to A but doesn't affect groups they share."""
    target_user_id: str


@dataclass(slots=True)
class BlockUserAckPayload:
    target_user_id: str
    blocked: bool  # true after BLOCK_USER, false after UNBLOCK_USER


@dataclass(slots=True)
class BlockedUserDescriptor:
    user_id: str
    blocked_at_ms: int


@dataclass(slots=True)
class BlockedUsersListResponsePayload:
    blocked: list[BlockedUserDescriptor]


@dataclass(slots=True)
class ConversationMuteUpdateRequestPayload:
    """muted_until_ms semantics:
       0  -> not muted (un-mute)
      -1  -> muted forever
       N  -> muted until wall-clock ms epoch N
    """
    conversation_id: str
    muted_until_ms: int


@dataclass(slots=True)
class ConversationMuteUpdateResponsePayload:
    conversation_id: str
    muted_until_ms: int


# ---- M99 drafts ----

@dataclass(slots=True)
class DraftSaveRequestPayload:
    """Save / overwrite the draft for (current user, conversation_id).
    Empty text auto-clears the draft (same UX as Telegram). Optional
    reply_to_message_id lets a half-typed reply follow the user across
    devices."""
    conversation_id: str
    text: str
    reply_to_message_id: str = ""


@dataclass(slots=True)
class DraftDescriptor:
    conversation_id: str
    text: str
    reply_to_message_id: str
    updated_at_ms: int


@dataclass(slots=True)
class DraftSaveResponsePayload:
    draft: DraftDescriptor
    cleared: bool   # true when an empty text auto-cleared the entry


@dataclass(slots=True)
class DraftListResponsePayload:
    drafts: list[DraftDescriptor]


@dataclass(slots=True)
class DraftClearRequestPayload:
    conversation_id: str


@dataclass(slots=True)
class DraftClearResponsePayload:
    conversation_id: str
    cleared: bool   # false if there was nothing to clear


# ---- M100 pinned + archived chats (per-user) ----

@dataclass(slots=True)
class ConversationPinToggleRequestPayload:
    """Toggle the per-user pinned flag for a conversation. `pinned=true`
    pins, `pinned=false` unpins. Pinning is a per-user preference — bob
    pinning conv_alice_bob does not affect alice's view."""
    conversation_id: str
    pinned: bool


@dataclass(slots=True)
class ConversationPinToggleResponsePayload:
    conversation_id: str
    pinned: bool


@dataclass(slots=True)
class ConversationArchiveToggleRequestPayload:
    """Same shape as pin: per-user archive flag. Archived conversations
    typically render in a separate list on the client; the server just
    persists the flag and exposes it via conversation_sync."""
    conversation_id: str
    archived: bool


@dataclass(slots=True)
class ConversationArchiveToggleResponsePayload:
    conversation_id: str
    archived: bool


# ---- M101 profile + group avatars ----

@dataclass(slots=True)
class ProfileAvatarUpdateRequestPayload:
    """Set or clear the actor's profile avatar. Empty `attachment_id`
    clears it (revert to default). The bytes themselves come from the
    chunked upload pipeline — we only persist the pointer here."""
    avatar_attachment_id: str


@dataclass(slots=True)
class ProfileAvatarUpdateResponsePayload:
    user_id: str
    avatar_attachment_id: str


@dataclass(slots=True)
class ConversationAvatarUpdateRequestPayload:
    """Set or clear a group/conversation avatar. Only participants may
    update; UNKNOWN_CONVERSATION + CONVERSATION_ACCESS_DENIED enforced."""
    conversation_id: str
    avatar_attachment_id: str


@dataclass(slots=True)
class ConversationAvatarUpdateResponsePayload:
    conversation_id: str
    avatar_attachment_id: str


# ---- M102 polls ----

@dataclass(slots=True)
class PollCreateRequestPayload:
    """Author posts a poll into a conversation. The question goes into
    `text`; `options` is a list of option strings. `multiple_choice`
    flips between Telegram's "single answer" and "multiple answers"
    poll modes."""
    conversation_id: str
    question: str
    options: list[str]
    multiple_choice: bool = False


@dataclass(slots=True)
class PollVoteRequestPayload:
    """User votes on (conversation_id, message_id). `option_indices` is
    a list because multiple-choice polls accept >=1 indices in a single
    request. For single-choice polls only the first index is honored;
    sending more is rejected."""
    conversation_id: str
    message_id: str
    option_indices: list[int]


@dataclass(slots=True)
class PollCloseRequestPayload:
    """Close voting. Only the poll author may invoke; everyone else
    receives POLL_CLOSE_DENIED."""
    conversation_id: str
    message_id: str


@dataclass(slots=True)
class PollUpdatedPayload:
    """Server -> all participants whenever a poll's tallies or closed
    state change. Carries the canonical post-state of the poll so the
    client can re-render without recomputing."""
    conversation_id: str
    message_id: str
    poll: PollDescriptor


# ---- M103 group permissions + admin roles ----

@dataclass(slots=True)
class ConversationRoleUpdateRequestPayload:
    """Set the target_user_id's role in a conversation. Only owners can
    promote a member to admin or demote an admin to member. The owner
    role itself is immutable — there is exactly one owner (the
    creator), and they can't be demoted via this RPC."""
    conversation_id: str
    target_user_id: str
    role: str  # "admin" | "member"


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
            two_fa_code=payload.get("two_fa_code", ""),
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
    if message_type == MessageType.PUSH_TOKEN_REGISTER:
        return PushTokenRegisterRequestPayload(
            platform=payload.get("platform", ""),
            token=payload.get("token", ""),
        )
    if message_type == MessageType.PUSH_TOKEN_UNREGISTER:
        return PushTokenUnregisterRequestPayload(
            platform=payload.get("platform", ""),
            token=payload.get("token", ""),
        )
    if message_type == MessageType.PUSH_TOKEN_LIST_REQUEST:
        return {}
    if message_type == MessageType.ATTACHMENT_UPLOAD_INIT_REQUEST:
        return AttachmentUploadInitRequestPayload(
            conversation_id=payload.get("conversation_id", ""),
            filename=payload.get("filename", ""),
            mime_type=payload.get("mime_type", ""),
            total_size_bytes=int(payload.get("total_size_bytes", 0)),
        )
    if message_type == MessageType.ATTACHMENT_UPLOAD_CHUNK_REQUEST:
        return AttachmentUploadChunkRequestPayload(
            upload_id=payload.get("upload_id", ""),
            sequence=int(payload.get("sequence", 0)),
            content_b64=payload.get("content_b64", ""),
        )
    if message_type == MessageType.ATTACHMENT_UPLOAD_COMPLETE_REQUEST:
        return AttachmentUploadCompleteRequestPayload(
            upload_id=payload.get("upload_id", ""),
            caption=payload.get("caption", ""),
        )
    if message_type == MessageType.PHONE_OTP_REQUEST:
        return PhoneOtpRequestPayload(
            phone_number=payload.get("phone_number", ""),
        )
    if message_type == MessageType.PHONE_OTP_VERIFY_REQUEST:
        return PhoneOtpVerifyRequestPayload(
            phone_number=payload.get("phone_number", ""),
            code=payload.get("code", ""),
            device_id=payload.get("device_id", ""),
            display_name=payload.get("display_name", ""),
        )
    if message_type == MessageType.TWO_FA_ENABLE_REQUEST:
        return {}
    if message_type == MessageType.TWO_FA_VERIFY_REQUEST:
        return TwoFaVerifyRequestPayload(code=payload.get("code", ""))
    if message_type == MessageType.TWO_FA_DISABLE_REQUEST:
        return TwoFaDisableRequestPayload(code=payload.get("code", ""))
    if message_type == MessageType.ACCOUNT_EXPORT_REQUEST:
        return {}
    if message_type == MessageType.ACCOUNT_DELETE_REQUEST:
        return AccountDeleteRequestPayload(
            password=payload.get("password", ""),
            two_fa_code=payload.get("two_fa_code", ""),
        )
    if message_type in (MessageType.BLOCK_USER_REQUEST, MessageType.UNBLOCK_USER_REQUEST):
        return BlockUserRequestPayload(target_user_id=payload.get("target_user_id", ""))
    if message_type == MessageType.BLOCKED_USERS_LIST_REQUEST:
        return {}
    if message_type == MessageType.CONVERSATION_MUTE_UPDATE_REQUEST:
        return ConversationMuteUpdateRequestPayload(
            conversation_id=payload.get("conversation_id", ""),
            muted_until_ms=int(payload.get("muted_until_ms", 0)),
        )
    if message_type == MessageType.DRAFT_SAVE_REQUEST:
        return DraftSaveRequestPayload(
            conversation_id=payload.get("conversation_id", ""),
            text=payload.get("text", ""),
            reply_to_message_id=payload.get("reply_to_message_id", ""),
        )
    if message_type == MessageType.DRAFT_LIST_REQUEST:
        return {}
    if message_type == MessageType.DRAFT_CLEAR_REQUEST:
        return DraftClearRequestPayload(conversation_id=payload.get("conversation_id", ""))
    if message_type == MessageType.CONVERSATION_PIN_TOGGLE_REQUEST:
        return ConversationPinToggleRequestPayload(
            conversation_id=payload.get("conversation_id", ""),
            pinned=bool(payload.get("pinned", False)),
        )
    if message_type == MessageType.CONVERSATION_ARCHIVE_TOGGLE_REQUEST:
        return ConversationArchiveToggleRequestPayload(
            conversation_id=payload.get("conversation_id", ""),
            archived=bool(payload.get("archived", False)),
        )
    if message_type == MessageType.PROFILE_AVATAR_UPDATE_REQUEST:
        return ProfileAvatarUpdateRequestPayload(
            avatar_attachment_id=payload.get("avatar_attachment_id", ""),
        )
    if message_type == MessageType.CONVERSATION_AVATAR_UPDATE_REQUEST:
        return ConversationAvatarUpdateRequestPayload(
            conversation_id=payload.get("conversation_id", ""),
            avatar_attachment_id=payload.get("avatar_attachment_id", ""),
        )
    if message_type == MessageType.POLL_CREATE_REQUEST:
        return PollCreateRequestPayload(
            conversation_id=payload.get("conversation_id", ""),
            question=payload.get("question", ""),
            options=list(payload.get("options", [])),
            multiple_choice=bool(payload.get("multiple_choice", False)),
        )
    if message_type == MessageType.POLL_VOTE_REQUEST:
        return PollVoteRequestPayload(
            conversation_id=payload.get("conversation_id", ""),
            message_id=payload.get("message_id", ""),
            option_indices=[int(i) for i in payload.get("option_indices", [])],
        )
    if message_type == MessageType.POLL_CLOSE_REQUEST:
        return PollCloseRequestPayload(
            conversation_id=payload.get("conversation_id", ""),
            message_id=payload.get("message_id", ""),
        )
    if message_type == MessageType.CONVERSATION_ROLE_UPDATE_REQUEST:
        return ConversationRoleUpdateRequestPayload(
            conversation_id=payload.get("conversation_id", ""),
            target_user_id=payload.get("target_user_id", ""),
            role=payload.get("role", ""),
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
