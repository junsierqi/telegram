from __future__ import annotations

import time
from typing import Any, Callable

from .protocol import (
    AttachmentFetchRequestPayload,
    ContactListResponsePayload,
    ContactTargetRequestPayload,
    ConversationCreateRequestPayload,
    ConversationDescriptor,
    ConversationParticipantRequestPayload,
    ConversationSyncRequestPayload,
    ConversationSyncResponsePayload,
    DeviceListResponsePayload,
    DeviceRevokeRequestPayload,
    DeviceTrustUpdateRequestPayload,
    ErrorCode,
    ErrorResponsePayload,
    HeartbeatAckPayload,
    HeartbeatPingRequestPayload,
    LoginRequestPayload,
    LoginResponsePayload,
    RegisterRequestPayload,
    RegisterResponsePayload,
    ProfileResponsePayload,
    ProfileUpdateRequestPayload,
    MessageDeleteRequestPayload,
    MessageEditRequestPayload,
    MessageForwardRequestPayload,
    MessagePinRequestPayload,
    MessageReactionRequestPayload,
    MessageReadRequestPayload,
    MessageSearchRequestPayload,
    MessageSearchResponsePayload,
    MessageSendAttachmentRequestPayload,
    MessageSendRequestPayload,
    MessageType,
    PresenceQueryRequestPayload,
    PresenceQueryResponsePayload,
    PresenceUpdatePayload,
    PushTokenAckPayload,
    PushTokenDescriptor,
    PushTokenListResponsePayload,
    PushTokenRegisterRequestPayload,
    PushTokenUnregisterRequestPayload,
    RemoteApproveRequestPayload,
    RemoteDisconnectRequestPayload,
    RemoteInputAckPayload,
    RemoteInputEventRequestPayload,
    RemoteInviteRequestPayload,
    RemoteSessionActionRequestPayload,
    ServiceError,
    UserSearchRequestPayload,
    UserSearchResponsePayload,
    UserSearchResultDescriptor,
    error_message,
    make_envelope,
    make_response,
    parse_request,
)
from .connection_registry import ConnectionRegistry
from .services.auth import AuthService
from .services.attachment_store import AttachmentBlobStore
from .services.chat import ChatService
from .services.contacts import ContactsService
from .services.input import InputService
from .services.presence import DEFAULT_TTL_SECONDS, PresenceService
from .services.push_tokens import PushTokenService
from .services.remote_session import RemoteSessionService
from .state import InMemoryState


class ServerApplication:
    def __init__(
        self,
        state_file: str | None = None,
        *,
        db_file: str | None = None,
        pg_dsn: str | None = None,
        connection_registry: ConnectionRegistry | None = None,
        clock: Callable[[], float] | None = None,
        presence_ttl_seconds: float = DEFAULT_TTL_SECONDS,
        session_ttl_seconds: float = 0.0,
        attachment_dir: str | None = None,
    ) -> None:
        self.state = InMemoryState(state_file=state_file, db_file=db_file, pg_dsn=pg_dsn)
        self.clock = clock or time.time
        self.auth_service = AuthService(
            self.state,
            clock=self.clock,
            session_ttl_seconds=session_ttl_seconds,
        )
        self.chat_service = ChatService(self.state, attachment_store=AttachmentBlobStore(attachment_dir))
        self.presence_service = PresenceService(
            self.state, clock=self.clock, ttl_seconds=presence_ttl_seconds
        )
        self.presence_service.set_transition_handler(self._fanout_presence_transition)
        self.remote_session_service = RemoteSessionService(self.state)
        self.input_service = InputService(self.state)
        self.contacts_service = ContactsService(self.state, self.presence_service)
        self.push_token_service = PushTokenService(self.state, clock=self.clock)
        self.connection_registry = connection_registry or ConnectionRegistry()

    def dispatch(self, message: dict[str, Any]) -> dict[str, Any]:
        correlation_id = message.get("correlation_id", "corr_invalid_request")
        session_id = message.get("session_id", "")
        actor_user_id = message.get("actor_user_id", "")

        try:
            request = parse_request(message)
        except (KeyError, TypeError, ValueError) as exc:
            return self._error_response(
                correlation_id=correlation_id,
                session_id=session_id,
                actor_user_id=actor_user_id,
                message=exc,
            )

        message_type = request.type
        payload = request.payload
        correlation_id = request.envelope.correlation_id
        session_id = request.envelope.session_id
        actor_user_id = request.envelope.actor_user_id

        if message_type == MessageType.LOGIN_REQUEST:
            try:
                assert isinstance(payload, LoginRequestPayload)
                login_result = self.auth_service.login(
                    payload.username, payload.password, payload.device_id
                )
                self.presence_service.notify_session_started(login_result["session_id"])
                return make_response(
                    MessageType.LOGIN_RESPONSE,
                    correlation_id=correlation_id,
                    session_id=login_result["session_id"],
                    actor_user_id=login_result["user_id"],
                    payload=LoginResponsePayload(
                        session_id=login_result["session_id"],
                        user_id=login_result["user_id"],
                        display_name=login_result["display_name"],
                        device_id=login_result["device_id"],
                    ),
                ).to_dict()
            except ValueError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=actor_user_id,
                    message=exc,
                )

        if message_type == MessageType.REGISTER_REQUEST:
            try:
                assert isinstance(payload, RegisterRequestPayload)
                register_result = self.auth_service.register(
                    username=payload.username,
                    password=payload.password,
                    display_name=payload.display_name,
                    device_id=payload.device_id,
                    device_label=payload.device_label,
                    platform=payload.platform,
                )
                self.presence_service.notify_session_started(register_result["session_id"])
                return make_response(
                    MessageType.REGISTER_RESPONSE,
                    correlation_id=correlation_id,
                    session_id=register_result["session_id"],
                    actor_user_id=register_result["user_id"],
                    payload=RegisterResponsePayload(
                        session_id=register_result["session_id"],
                        user_id=register_result["user_id"],
                        display_name=register_result["display_name"],
                        device_id=register_result["device_id"],
                    ),
                ).to_dict()
            except ValueError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=actor_user_id,
                    message=exc,
                )

        try:
            session = self.auth_service.resolve_session(session_id)
        except ValueError as exc:
            return self._error_response(
                correlation_id=correlation_id,
                session_id=session_id,
                actor_user_id=actor_user_id,
                message=exc,
            )

        if session.user_id != actor_user_id:
            return self._error_response(
                correlation_id=correlation_id,
                session_id=session_id,
                actor_user_id=actor_user_id,
                message=error_message(ErrorCode.SESSION_ACTOR_MISMATCH),
                code=ErrorCode.SESSION_ACTOR_MISMATCH,
            )

        if message_type == MessageType.PROFILE_GET_REQUEST:
            user = self.state.users[session.user_id]
            return make_response(
                MessageType.PROFILE_RESPONSE,
                correlation_id=correlation_id,
                session_id=session_id,
                actor_user_id=session.user_id,
                payload=ProfileResponsePayload(
                    user_id=user.user_id,
                    username=user.username,
                    display_name=user.display_name,
                ),
            ).to_dict()

        if message_type == MessageType.PROFILE_UPDATE_REQUEST:
            try:
                assert isinstance(payload, ProfileUpdateRequestPayload)
                display_name = payload.display_name.strip()
                if not display_name or len(display_name) > 64:
                    raise ServiceError(ErrorCode.INVALID_REGISTRATION_PAYLOAD)
                user = self.state.users[session.user_id]
                user.display_name = display_name
                self.state.save_runtime_state()
                return make_response(
                    MessageType.PROFILE_RESPONSE,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=ProfileResponsePayload(
                        user_id=user.user_id,
                        username=user.username,
                        display_name=user.display_name,
                    ),
                ).to_dict()
            except ValueError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.USER_SEARCH_REQUEST:
            try:
                assert isinstance(payload, UserSearchRequestPayload)
                query = payload.query.strip().casefold()
                limit = max(1, min(int(payload.limit), 50))
                if not query:
                    raise ServiceError(ErrorCode.INVALID_REGISTRATION_PAYLOAD)
                contact_ids = set(self.state.contacts.get(session.user_id, []))
                results: list[UserSearchResultDescriptor] = []
                for user in sorted(self.state.users.values(), key=lambda item: item.username):
                    if user.user_id == session.user_id:
                        continue
                    haystack = " ".join([user.user_id, user.username, user.display_name]).casefold()
                    if query not in haystack:
                        continue
                    results.append(
                        UserSearchResultDescriptor(
                            user_id=user.user_id,
                            username=user.username,
                            display_name=user.display_name,
                            online=self.presence_service.is_user_online(user.user_id),
                            is_contact=user.user_id in contact_ids,
                        )
                    )
                    if len(results) >= limit:
                        break
                return make_response(
                    MessageType.USER_SEARCH_RESPONSE,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=UserSearchResponsePayload(results=results),
                ).to_dict()
            except ValueError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.CONTACT_ADD:
            try:
                assert isinstance(payload, ContactTargetRequestPayload)
                contacts = self.contacts_service.add(
                    owner_user_id=session.user_id,
                    target_user_id=payload.target_user_id,
                )
                return make_response(
                    MessageType.CONTACT_LIST_RESPONSE,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=ContactListResponsePayload(contacts=contacts),
                ).to_dict()
            except ValueError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.CONTACT_REMOVE:
            try:
                assert isinstance(payload, ContactTargetRequestPayload)
                contacts = self.contacts_service.remove(
                    owner_user_id=session.user_id,
                    target_user_id=payload.target_user_id,
                )
                return make_response(
                    MessageType.CONTACT_LIST_RESPONSE,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=ContactListResponsePayload(contacts=contacts),
                ).to_dict()
            except ValueError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.CONTACT_LIST_REQUEST:
            contacts = self.contacts_service.list(session.user_id)
            return make_response(
                MessageType.CONTACT_LIST_RESPONSE,
                correlation_id=correlation_id,
                session_id=session_id,
                actor_user_id=session.user_id,
                payload=ContactListResponsePayload(contacts=contacts),
            ).to_dict()

        if message_type == MessageType.DEVICE_LIST_REQUEST:
            devices = self.presence_service.list_devices(session.user_id)
            return make_response(
                MessageType.DEVICE_LIST_RESPONSE,
                correlation_id=correlation_id,
                session_id=session_id,
                actor_user_id=session.user_id,
                payload=DeviceListResponsePayload(devices=devices),
            ).to_dict()

        if message_type == MessageType.DEVICE_REVOKE_REQUEST:
            assert isinstance(payload, DeviceRevokeRequestPayload)
            try:
                devices = self.presence_service.revoke_device(
                    session.user_id, session.session_id, payload.device_id
                )
            except ServiceError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )
            return make_response(
                MessageType.DEVICE_LIST_RESPONSE,
                correlation_id=correlation_id,
                session_id=session_id,
                actor_user_id=session.user_id,
                payload=DeviceListResponsePayload(devices=devices),
            ).to_dict()

        if message_type == MessageType.DEVICE_TRUST_UPDATE_REQUEST:
            assert isinstance(payload, DeviceTrustUpdateRequestPayload)
            try:
                devices = self.presence_service.update_trust(
                    session.user_id, payload.device_id, payload.trusted
                )
            except ServiceError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )
            return make_response(
                MessageType.DEVICE_LIST_RESPONSE,
                correlation_id=correlation_id,
                session_id=session_id,
                actor_user_id=session.user_id,
                payload=DeviceListResponsePayload(devices=devices),
            ).to_dict()

        if message_type == MessageType.CONVERSATION_SYNC:
            assert isinstance(payload, ConversationSyncRequestPayload)
            conversations = self.chat_service.sync_for_user_since(
                session.user_id,
                payload.cursors,
                payload.versions,
                payload.history_limits,
                payload.before_message_ids,
            )
            return make_response(
                MessageType.CONVERSATION_SYNC,
                correlation_id=correlation_id,
                session_id=session_id,
                actor_user_id=session.user_id,
                payload=ConversationSyncResponsePayload(conversations=conversations),
            ).to_dict()

        if message_type == MessageType.MESSAGE_SEND:
            try:
                assert isinstance(payload, MessageSendRequestPayload)
                message_result = self.chat_service.send_message(
                    conversation_id=payload.conversation_id,
                    sender_user_id=session.user_id,
                    text=payload.text,
                    reply_to_message_id=payload.reply_to_message_id,
                )
                self._fanout_to_conversation(
                    conversation_id=payload.conversation_id,
                    origin_session_id=session_id,
                    actor_user_id=session.user_id,
                    message_type=MessageType.MESSAGE_DELIVER,
                    payload=message_result,
                    correlation_id=f"push_{message_result.message_id}",
                )
                self._enqueue_mock_pushes_for_offline_recipients(
                    conversation_id=payload.conversation_id,
                    sender_user_id=session.user_id,
                    body_summary=message_result.text[:80],
                )
                return make_response(
                    MessageType.MESSAGE_DELIVER,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=message_result,
                ).to_dict()
            except ValueError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.MESSAGE_SEND_ATTACHMENT:
            try:
                assert isinstance(payload, MessageSendAttachmentRequestPayload)
                message_result = self.chat_service.send_attachment_message(
                    conversation_id=payload.conversation_id,
                    sender_user_id=session.user_id,
                    caption=payload.caption,
                    filename=payload.filename,
                    mime_type=payload.mime_type,
                    content_b64=payload.content_b64,
                    declared_size_bytes=payload.size_bytes,
                )
                self._fanout_to_conversation(
                    conversation_id=payload.conversation_id,
                    origin_session_id=session_id,
                    actor_user_id=session.user_id,
                    message_type=MessageType.MESSAGE_DELIVER,
                    payload=message_result,
                    correlation_id=f"push_{message_result.message_id}",
                )
                return make_response(
                    MessageType.MESSAGE_DELIVER,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=message_result,
                ).to_dict()
            except ValueError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.MESSAGE_FORWARD:
            try:
                assert isinstance(payload, MessageForwardRequestPayload)
                message_result = self.chat_service.forward_message(
                    source_conversation_id=payload.source_conversation_id,
                    source_message_id=payload.source_message_id,
                    target_conversation_id=payload.target_conversation_id,
                    actor_user_id=session.user_id,
                )
                self._fanout_to_conversation(
                    conversation_id=payload.target_conversation_id,
                    origin_session_id=session_id,
                    actor_user_id=session.user_id,
                    message_type=MessageType.MESSAGE_DELIVER,
                    payload=message_result,
                    correlation_id=f"push_{message_result.message_id}",
                )
                return make_response(
                    MessageType.MESSAGE_DELIVER,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=message_result,
                ).to_dict()
            except ValueError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.ATTACHMENT_FETCH_REQUEST:
            try:
                assert isinstance(payload, AttachmentFetchRequestPayload)
                fetched = self.chat_service.fetch_attachment(
                    attachment_id=payload.attachment_id,
                    requester_user_id=session.user_id,
                )
                return make_response(
                    MessageType.ATTACHMENT_FETCH_RESPONSE,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=fetched,
                ).to_dict()
            except ValueError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.MESSAGE_REACTION:
            try:
                assert isinstance(payload, MessageReactionRequestPayload)
                updated = self.chat_service.toggle_reaction(
                    conversation_id=payload.conversation_id,
                    actor_user_id=session.user_id,
                    message_id=payload.message_id,
                    emoji=payload.emoji,
                )
                self._fanout_to_conversation(
                    conversation_id=payload.conversation_id,
                    origin_session_id=session_id,
                    actor_user_id=session.user_id,
                    message_type=MessageType.MESSAGE_REACTION_UPDATED,
                    payload=updated,
                    correlation_id=f"push_reaction_{payload.message_id}_{session.user_id}",
                )
                return make_response(
                    MessageType.MESSAGE_REACTION_UPDATED,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=updated,
                ).to_dict()
            except ValueError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.MESSAGE_PIN:
            try:
                assert isinstance(payload, MessagePinRequestPayload)
                updated = self.chat_service.set_pin(
                    conversation_id=payload.conversation_id,
                    actor_user_id=session.user_id,
                    message_id=payload.message_id,
                    pinned=payload.pinned,
                )
                self._fanout_to_conversation(
                    conversation_id=payload.conversation_id,
                    origin_session_id=session_id,
                    actor_user_id=session.user_id,
                    message_type=MessageType.MESSAGE_PIN_UPDATED,
                    payload=updated,
                    correlation_id=f"push_pin_{payload.message_id}_{session.user_id}",
                )
                return make_response(
                    MessageType.MESSAGE_PIN_UPDATED,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=updated,
                ).to_dict()
            except ValueError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.MESSAGE_SEARCH_REQUEST:
            try:
                assert isinstance(payload, MessageSearchRequestPayload)
                results, next_offset, has_more = self.chat_service.search_messages(
                    user_id=session.user_id,
                    query=payload.query,
                    conversation_id=payload.conversation_id,
                    limit=payload.limit,
                    offset=payload.offset,
                )
                return make_response(
                    MessageType.MESSAGE_SEARCH_RESPONSE,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=MessageSearchResponsePayload(
                        results=results,
                        next_offset=next_offset,
                        has_more=has_more,
                    ),
                ).to_dict()
            except ValueError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.MESSAGE_EDIT:
            try:
                assert isinstance(payload, MessageEditRequestPayload)
                edited = self.chat_service.edit_message(
                    conversation_id=payload.conversation_id,
                    actor_user_id=session.user_id,
                    message_id=payload.message_id,
                    new_text=payload.text,
                )
                self._fanout_to_conversation(
                    conversation_id=payload.conversation_id,
                    origin_session_id=session_id,
                    actor_user_id=session.user_id,
                    message_type=MessageType.MESSAGE_EDITED,
                    payload=edited,
                    correlation_id=f"push_edit_{payload.message_id}",
                )
                return make_response(
                    MessageType.MESSAGE_EDITED,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=edited,
                ).to_dict()
            except ValueError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.MESSAGE_DELETE:
            try:
                assert isinstance(payload, MessageDeleteRequestPayload)
                deleted = self.chat_service.delete_message(
                    conversation_id=payload.conversation_id,
                    actor_user_id=session.user_id,
                    message_id=payload.message_id,
                )
                self._fanout_to_conversation(
                    conversation_id=payload.conversation_id,
                    origin_session_id=session_id,
                    actor_user_id=session.user_id,
                    message_type=MessageType.MESSAGE_DELETED,
                    payload=deleted,
                    correlation_id=f"push_delete_{payload.message_id}",
                )
                return make_response(
                    MessageType.MESSAGE_DELETED,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=deleted,
                ).to_dict()
            except ValueError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.MESSAGE_READ:
            try:
                assert isinstance(payload, MessageReadRequestPayload)
                update = self.chat_service.mark_read(
                    conversation_id=payload.conversation_id,
                    reader_user_id=session.user_id,
                    message_id=payload.message_id,
                )
                self._fanout_to_conversation(
                    conversation_id=payload.conversation_id,
                    origin_session_id=session_id,
                    actor_user_id=session.user_id,
                    message_type=MessageType.MESSAGE_READ_UPDATE,
                    payload=update,
                    correlation_id=f"push_read_{payload.conversation_id}_{session.user_id}",
                )
                return make_response(
                    MessageType.MESSAGE_READ_UPDATE,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=update,
                ).to_dict()
            except ValueError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.CONVERSATION_CREATE:
            try:
                assert isinstance(payload, ConversationCreateRequestPayload)
                descriptor = self.chat_service.create_conversation(
                    creator_user_id=session.user_id,
                    other_user_ids=payload.participant_user_ids,
                    title=payload.title,
                )
                self._fanout_to_conversation(
                    conversation_id=descriptor.conversation_id,
                    origin_session_id=session_id,
                    actor_user_id=session.user_id,
                    message_type=MessageType.CONVERSATION_UPDATED,
                    payload=descriptor,
                    correlation_id=f"push_create_{descriptor.conversation_id}",
                )
                return make_response(
                    MessageType.CONVERSATION_UPDATED,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=descriptor,
                ).to_dict()
            except ValueError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.CONVERSATION_ADD_PARTICIPANT:
            try:
                assert isinstance(payload, ConversationParticipantRequestPayload)
                descriptor = self.chat_service.add_participant(
                    conversation_id=payload.conversation_id,
                    actor_user_id=session.user_id,
                    new_user_id=payload.user_id,
                )
                self._fanout_to_conversation(
                    conversation_id=descriptor.conversation_id,
                    origin_session_id=session_id,
                    actor_user_id=session.user_id,
                    message_type=MessageType.CONVERSATION_UPDATED,
                    payload=descriptor,
                    correlation_id=f"push_add_{descriptor.conversation_id}_{payload.user_id}",
                )
                return make_response(
                    MessageType.CONVERSATION_UPDATED,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=descriptor,
                ).to_dict()
            except ValueError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.CONVERSATION_REMOVE_PARTICIPANT:
            try:
                assert isinstance(payload, ConversationParticipantRequestPayload)
                descriptor = self.chat_service.remove_participant(
                    conversation_id=payload.conversation_id,
                    actor_user_id=session.user_id,
                    target_user_id=payload.user_id,
                )
                # Push to the remaining participants AND the just-removed user
                # (they should know they were kicked) via an explicit user set.
                notify_user_ids = list(descriptor.participant_user_ids)
                if payload.user_id not in notify_user_ids:
                    notify_user_ids.append(payload.user_id)
                self._fanout_to_users(
                    user_ids=notify_user_ids,
                    origin_session_id=session_id,
                    actor_user_id=session.user_id,
                    message_type=MessageType.CONVERSATION_UPDATED,
                    payload=descriptor,
                    correlation_id=f"push_remove_{descriptor.conversation_id}_{payload.user_id}",
                )
                return make_response(
                    MessageType.CONVERSATION_UPDATED,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=descriptor,
                ).to_dict()
            except ValueError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.REMOTE_INVITE:
            try:
                assert isinstance(payload, RemoteInviteRequestPayload)
                if payload.requester_device_id != session.device_id:
                    raise ServiceError(ErrorCode.REQUESTER_DEVICE_SESSION_MISMATCH)
                remote_result = self.remote_session_service.create_invite(
                    requester_user_id=session.user_id,
                    requester_device_id=session.device_id,
                    target_device_id=payload.target_device_id,
                )
                return make_response(
                    MessageType.REMOTE_SESSION_STATE,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=remote_result,
                ).to_dict()
            except ValueError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.REMOTE_APPROVE:
            try:
                assert isinstance(payload, RemoteApproveRequestPayload)
                remote_result = self.remote_session_service.approve(
                    payload.remote_session_id,
                    session.user_id,
                )
                return make_response(
                    MessageType.REMOTE_RELAY_ASSIGNMENT,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=remote_result,
                ).to_dict()
            except ValueError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.REMOTE_REJECT:
            try:
                assert isinstance(payload, RemoteSessionActionRequestPayload)
                remote_result = self.remote_session_service.reject(
                    payload.remote_session_id,
                    session.user_id,
                )
                return make_response(
                    MessageType.REMOTE_SESSION_STATE,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=remote_result,
                ).to_dict()
            except ValueError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.REMOTE_CANCEL:
            try:
                assert isinstance(payload, RemoteSessionActionRequestPayload)
                remote_result = self.remote_session_service.cancel(
                    payload.remote_session_id,
                    session.user_id,
                )
                return make_response(
                    MessageType.REMOTE_SESSION_TERMINATED,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=remote_result,
                ).to_dict()
            except ValueError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.REMOTE_TERMINATE:
            try:
                assert isinstance(payload, RemoteSessionActionRequestPayload)
                remote_result = self.remote_session_service.terminate(
                    payload.remote_session_id,
                    session.user_id,
                )
                return make_response(
                    MessageType.REMOTE_SESSION_TERMINATED,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=remote_result,
                ).to_dict()
            except ValueError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.REMOTE_DISCONNECT:
            try:
                assert isinstance(payload, RemoteDisconnectRequestPayload)
                remote_result = self.remote_session_service.disconnect(
                    payload.remote_session_id,
                    session.user_id,
                    payload.reason,
                )
                return make_response(
                    MessageType.REMOTE_SESSION_TERMINATED,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=remote_result,
                ).to_dict()
            except ValueError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.REMOTE_RENDEZVOUS_REQUEST:
            try:
                assert isinstance(payload, RemoteSessionActionRequestPayload)
                remote_result = self.remote_session_service.request_rendezvous(
                    payload.remote_session_id,
                    session.user_id,
                )
                return make_response(
                    MessageType.REMOTE_RENDEZVOUS_INFO,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=remote_result,
                ).to_dict()
            except ValueError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.HEARTBEAT_PING:
            assert isinstance(payload, HeartbeatPingRequestPayload)
            self.presence_service.touch(session_id)
            return make_response(
                MessageType.HEARTBEAT_ACK,
                correlation_id=correlation_id,
                session_id=session_id,
                actor_user_id=session.user_id,
                payload=HeartbeatAckPayload(
                    session_id=session_id,
                    server_timestamp_ms=self.presence_service.now_ms(),
                    client_timestamp_ms=payload.client_timestamp_ms,
                ),
            ).to_dict()

        if message_type == MessageType.PRESENCE_QUERY_REQUEST:
            assert isinstance(payload, PresenceQueryRequestPayload)
            users = self.presence_service.query_users(payload.user_ids)
            return make_response(
                MessageType.PRESENCE_QUERY_RESPONSE,
                correlation_id=correlation_id,
                session_id=session_id,
                actor_user_id=session.user_id,
                payload=PresenceQueryResponsePayload(
                    users=users,
                    server_timestamp_ms=self.presence_service.now_ms(),
                ),
            ).to_dict()

        if message_type == MessageType.REMOTE_INPUT_EVENT:
            try:
                assert isinstance(payload, RemoteInputEventRequestPayload)
                ack = self.input_service.inject(
                    remote_session_id=payload.remote_session_id,
                    actor_user_id=session.user_id,
                    kind=payload.kind,
                    data=payload.data,
                )
                return make_response(
                    MessageType.REMOTE_INPUT_ACK,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=RemoteInputAckPayload(
                        remote_session_id=ack["remote_session_id"],
                        sequence=ack["sequence"],
                        kind=ack["kind"],
                    ),
                ).to_dict()
            except ValueError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.PUSH_TOKEN_REGISTER:
            try:
                assert isinstance(payload, PushTokenRegisterRequestPayload)
                self.push_token_service.register(
                    user_id=session.user_id,
                    device_id=session.device_id,
                    platform=payload.platform,
                    token=payload.token,
                )
                return make_response(
                    MessageType.PUSH_TOKEN_ACK,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=PushTokenAckPayload(
                        platform=payload.platform,
                        token=payload.token,
                        registered=True,
                    ),
                ).to_dict()
            except ServiceError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.PUSH_TOKEN_UNREGISTER:
            assert isinstance(payload, PushTokenUnregisterRequestPayload)
            self.push_token_service.unregister(
                user_id=session.user_id,
                device_id=session.device_id,
                platform=payload.platform,
                token=payload.token,
            )
            return make_response(
                MessageType.PUSH_TOKEN_ACK,
                correlation_id=correlation_id,
                session_id=session_id,
                actor_user_id=session.user_id,
                payload=PushTokenAckPayload(
                    platform=payload.platform,
                    token=payload.token,
                    registered=False,
                ),
            ).to_dict()

        if message_type == MessageType.PUSH_TOKEN_LIST_REQUEST:
            tokens = [
                PushTokenDescriptor(
                    user_id=r.user_id,
                    device_id=r.device_id,
                    platform=r.platform,
                    token=r.token,
                    registered_at_ms=r.registered_at_ms,
                )
                for r in self.push_token_service.tokens_for_user(session.user_id)
            ]
            return make_response(
                MessageType.PUSH_TOKEN_LIST_RESPONSE,
                correlation_id=correlation_id,
                session_id=session_id,
                actor_user_id=session.user_id,
                payload=PushTokenListResponsePayload(tokens=tokens),
            ).to_dict()

        return self._error_response(
            correlation_id=correlation_id,
            session_id=session_id,
            actor_user_id=actor_user_id,
            message=f"Unsupported message type: {message_type.value}",
            code=ErrorCode.UNSUPPORTED_MESSAGE_TYPE,
        )

    def _fanout_to_conversation(
        self,
        *,
        conversation_id: str,
        origin_session_id: str,
        actor_user_id: str,
        message_type: MessageType,
        payload: Any,
        correlation_id: str,
    ) -> list[str]:
        conversation = self.state.conversations.get(conversation_id)
        if conversation is None:
            return []
        return self._fanout_to_users(
            user_ids=list(conversation.participant_user_ids),
            origin_session_id=origin_session_id,
            actor_user_id=actor_user_id,
            message_type=message_type,
            payload=payload,
            correlation_id=correlation_id,
        )

    def _fanout_to_users(
        self,
        *,
        user_ids: list[str],
        origin_session_id: str,
        actor_user_id: str,
        message_type: MessageType,
        payload: Any,
        correlation_id: str,
    ) -> list[str]:
        """Push an envelope to every session of the given users except origin.

        Skips sessions tied to origin_session_id (the requester already got the
        synchronous response). Returns session_ids that actually received the
        push — missing sessions (logged-out users) are silently dropped.
        """
        delivered_to: list[str] = []
        seen_sessions: set[str] = set()
        for user_id in user_ids:
            for session in self.state.sessions_for_user(user_id):
                if session.session_id == origin_session_id:
                    continue
                if session.session_id in seen_sessions:
                    continue
                seen_sessions.add(session.session_id)
                envelope = make_response(
                    message_type,
                    correlation_id=correlation_id,
                    session_id=session.session_id,
                    actor_user_id=actor_user_id,
                    sequence=0,
                    payload=payload,
                ).to_dict()
                if self.connection_registry.push(session.session_id, envelope):
                    delivered_to.append(session.session_id)
        return delivered_to

    def _enqueue_mock_pushes_for_offline_recipients(
        self,
        *,
        conversation_id: str,
        sender_user_id: str,
        body_summary: str,
    ) -> None:
        """For every conversation participant that has NO fresh session, queue
        a mock push delivery via PushTokenService. The actual FCM/APNs HTTP
        transport is PA-008 — for now this just records intent so validators
        can assert the wake-up surface fired."""
        conversation = self.state.conversations.get(conversation_id)
        if conversation is None:
            return
        for user_id in conversation.participant_user_ids:
            if user_id == sender_user_id:
                continue
            if self.presence_service.is_user_online(user_id):
                continue
            self.push_token_service.notify_offline_recipient(
                user_id=user_id,
                kind="message_deliver",
                body_summary=body_summary,
            )

    def _fanout_presence_transition(self, user_id: str, online: bool) -> None:
        """Wired into PresenceService as transition_handler. Fans out
        PRESENCE_UPDATE to every user who shares at least one conversation
        with the transitioning user (the cheapest available subscriber set).
        """
        peer_ids: set[str] = set()
        for conversation in self.state.conversations.values():
            if user_id not in conversation.participant_user_ids:
                continue
            for pid in conversation.participant_user_ids:
                if pid != user_id:
                    peer_ids.add(pid)
        if not peer_ids:
            return
        payload = PresenceUpdatePayload(
            user_id=user_id,
            online=online,
            last_seen_at_ms=self.presence_service.last_seen_ms(user_id),
        )
        # origin_session_id="" so every peer session receives the push (the
        # transitioning user themselves doesn't need it).
        self._fanout_to_users(
            user_ids=sorted(peer_ids),
            origin_session_id="",
            actor_user_id=user_id,
            message_type=MessageType.PRESENCE_UPDATE,
            payload=payload,
            correlation_id=f"push_presence_{user_id}_{'on' if online else 'off'}",
        )

    def _error_response(
        self,
        *,
        correlation_id: str,
        session_id: str,
        actor_user_id: str,
        message: str | ServiceError,
        code: ErrorCode | None = None,
    ) -> dict[str, Any]:
        if isinstance(message, ServiceError):
            code = message.code
            human = message.human_message
        else:
            human = message if isinstance(message, str) else str(message)
            if code is None:
                code = ErrorCode.UNKNOWN
        return make_response(
            MessageType.ERROR,
            correlation_id=correlation_id,
            session_id=session_id,
            actor_user_id=actor_user_id,
            payload=ErrorResponsePayload(code=code.value, message=human),
        ).to_dict()

    def run(self) -> None:
        print("[server] control plane starting")
        print(f"[server] {self.auth_service.describe()}")
        print(f"[server] {self.chat_service.describe()}")
        print(f"[server] {self.presence_service.describe()}")
        print(f"[server] {self.remote_session_service.describe()}")

        login_response = self.dispatch(
            {
                **make_envelope(
                    MessageType.LOGIN_REQUEST,
                    correlation_id="corr_login_1",
                    sequence=1,
                ),
                "payload": {
                    "username": "alice",
                    "password": "alice_pw",
                    "device_id": "dev_alice_win",
                },
            }
        )
        print(f"[server] demo login response: {login_response}")

        session_id = login_response["payload"]["session_id"]
        actor_user_id = login_response["payload"]["user_id"]

        devices_response = self.dispatch(
            {
                **make_envelope(
                    MessageType.DEVICE_LIST_REQUEST,
                    correlation_id="corr_devices_1",
                    session_id=session_id,
                    actor_user_id=actor_user_id,
                    sequence=2,
                ),
                "payload": {},
            }
        )
        print(f"[server] demo device list response: {devices_response}")

        chat_sync_response = self.dispatch(
            {
                **make_envelope(
                    MessageType.CONVERSATION_SYNC,
                    correlation_id="corr_sync_1",
                    session_id=session_id,
                    actor_user_id=actor_user_id,
                    sequence=3,
                ),
                "payload": {},
            }
        )
        print(f"[server] demo conversation sync response: {chat_sync_response}")

        message_send_response = self.dispatch(
            {
                **make_envelope(
                    MessageType.MESSAGE_SEND,
                    correlation_id="corr_msg_1",
                    session_id=session_id,
                    actor_user_id=actor_user_id,
                    sequence=4,
                ),
                "payload": {
                    "conversation_id": "conv_alice_bob",
                    "text": "control plane chat message from alice",
                },
            }
        )
        print(f"[server] demo message send response: {message_send_response}")

        invite_response = self.dispatch(
            {
                **make_envelope(
                    MessageType.REMOTE_INVITE,
                    correlation_id="corr_remote_1",
                    session_id=session_id,
                    actor_user_id=actor_user_id,
                    sequence=5,
                ),
                "payload": {
                    "requester_device_id": "dev_alice_win",
                    "target_device_id": "dev_bob_win",
                },
            }
        )
        print(f"[server] demo remote invite response: {invite_response}")

        bob_login_response = self.dispatch(
            {
                **make_envelope(
                    MessageType.LOGIN_REQUEST,
                    correlation_id="corr_login_2",
                    sequence=6,
                ),
                "payload": {
                    "username": "bob",
                    "password": "bob_pw",
                    "device_id": "dev_bob_win",
                },
            }
        )
        print(f"[server] demo bob login response: {bob_login_response}")

        approve_response = self.dispatch(
            {
                **make_envelope(
                    MessageType.REMOTE_APPROVE,
                    correlation_id="corr_remote_2",
                    session_id=bob_login_response["payload"]["session_id"],
                    actor_user_id=bob_login_response["payload"]["user_id"],
                    sequence=7,
                ),
                "payload": {
                    "remote_session_id": invite_response["payload"]["remote_session_id"]
                },
            }
        )
        print(f"[server] demo remote approval response: {approve_response}")


def create_app(
    state_file: str | None = None,
    *,
    db_file: str | None = None,
    pg_dsn: str | None = None,
    attachment_dir: str | None = None,
    session_ttl_seconds: float = 0.0,
) -> ServerApplication:
    return ServerApplication(
        state_file=state_file,
        db_file=db_file,
        pg_dsn=pg_dsn,
        attachment_dir=attachment_dir,
        session_ttl_seconds=session_ttl_seconds,
    )
