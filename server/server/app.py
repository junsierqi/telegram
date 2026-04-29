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
    AttachmentUploadInitRequestPayload,
    AttachmentUploadInitResponsePayload,
    AttachmentUploadChunkRequestPayload,
    AttachmentUploadChunkAckPayload,
    AttachmentUploadCompleteRequestPayload,
    PhoneOtpRequestPayload,
    PhoneOtpRequestResponsePayload,
    PhoneOtpVerifyRequestPayload,
    PhoneOtpVerifyResponsePayload,
    TwoFaEnableResponsePayload,
    TwoFaVerifyRequestPayload,
    TwoFaVerifyResponsePayload,
    TwoFaDisableRequestPayload,
    AccountExportResponsePayload,
    AccountDeleteRequestPayload,
    AccountDeleteResponsePayload,
    BlockUserRequestPayload,
    BlockUserAckPayload,
    BlockedUserDescriptor,
    BlockedUsersListResponsePayload,
    ConversationMuteUpdateRequestPayload,
    ConversationMuteUpdateResponsePayload,
    DraftSaveRequestPayload,
    DraftSaveResponsePayload,
    DraftDescriptor,
    DraftListResponsePayload,
    DraftClearRequestPayload,
    DraftClearResponsePayload,
    ConversationPinToggleRequestPayload,
    ConversationPinToggleResponsePayload,
    ConversationArchiveToggleRequestPayload,
    ConversationArchiveToggleResponsePayload,
    ProfileAvatarUpdateRequestPayload,
    ProfileAvatarUpdateResponsePayload,
    ConversationAvatarUpdateRequestPayload,
    ConversationAvatarUpdateResponsePayload,
    PollCreateRequestPayload,
    PollVoteRequestPayload,
    PollCloseRequestPayload,
    PollUpdatedPayload,
    PollDescriptor,
    PollOptionDescriptor,
    ConversationRoleUpdateRequestPayload,
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
from .services.observability import Observability
from .services.phone_otp import PhoneOtpService
from .services.rate_limiter import RateLimiter
from .services.account_lifecycle import AccountLifecycleService
from .services.block_mute import BlockMuteService
from .services.drafts import DraftsService
from .services.conversation_flags import ConversationFlagsService
from .services.polls import PollsService
from .services.two_fa import TwoFAService
from .services.presence import DEFAULT_TTL_SECONDS, PresenceService
from .services.push_dispatch import PushDispatchWorker
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
        self.phone_otp_service = PhoneOtpService(self.state, clock=self.clock)
        self.observability = Observability(clock=self.clock)
        self.rate_limiter = RateLimiter()
        self.two_fa_service = TwoFAService(self.state, clock=self.clock)
        self.account_lifecycle_service = AccountLifecycleService(
            self.state, clock=self.clock, two_fa_service=self.two_fa_service,
        )
        self.block_mute_service = BlockMuteService(self.state, clock=self.clock)
        self.drafts_service = DraftsService(self.state, clock=self.clock)
        self.conversation_flags_service = ConversationFlagsService(self.state)
        self.polls_service = PollsService(self.state, clock=self.clock)
        # Cheap default health check: state file load completed if we got here.
        self.observability.health.register("state_loaded", lambda: (True, "ok"))
        self.observability.health.register(
            "active_session_count",
            lambda: (True, f"{len(self.state.sessions)}"),
        )
        # Default worker uses the LogOnlyTransport for every platform —
        # safe in any environment, no credentials required. A future
        # M91 wiring (PA-008) supplies an FCMHttpTransport via
        # set_push_dispatch_worker / a custom transport_for callback.
        self.push_dispatch_worker = PushDispatchWorker(self.push_token_service)
        self.connection_registry = connection_registry or ConnectionRegistry()

    def dispatch(self, message: dict[str, Any]) -> dict[str, Any]:
        # Wrap the real dispatcher so every inbound request gets a counter +
        # latency histogram tagged by message_type + outcome (ok|error).
        # Using the wall clock works because this is for monitoring, not
        # security; FakeClock is fine in tests too.
        start = time.time()
        message_type = message.get("type") or "unknown"
        try:
            response = self._dispatch_inner(message)
        except Exception:
            self.observability.metrics.inc(
                "dispatch_requests_total",
                labels={"type": message_type, "outcome": "exception"},
            )
            raise
        outcome = "error" if response.get("type") == "error" else "ok"
        self.observability.metrics.inc(
            "dispatch_requests_total",
            labels={"type": message_type, "outcome": outcome},
        )
        self.observability.metrics.observe(
            "dispatch_request_duration_seconds",
            time.time() - start,
            labels={"type": message_type},
        )
        return response

    def _dispatch_inner(self, message: dict[str, Any]) -> dict[str, Any]:
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
                # M94: if the user has 2FA on, require + verify the code
                # before issuing the session. We do this AFTER password
                # verification so we don't leak which usernames have 2FA.
                user_id = login_result["user_id"]
                if self.two_fa_service.is_enabled(user_id):
                    if not payload.two_fa_code:
                        # Roll back the freshly-issued session so the failed
                        # login doesn't count against the session count.
                        self.state.sessions.pop(login_result["session_id"], None)
                        return self._error_response(
                            correlation_id=correlation_id,
                            session_id=session_id,
                            actor_user_id=actor_user_id,
                            message=ServiceError(ErrorCode.TWO_FA_REQUIRED),
                        )
                    if not self.two_fa_service.verify_login_code(user_id, payload.two_fa_code):
                        self.state.sessions.pop(login_result["session_id"], None)
                        return self._error_response(
                            correlation_id=correlation_id,
                            session_id=session_id,
                            actor_user_id=actor_user_id,
                            message=ServiceError(ErrorCode.INVALID_TWO_FA_CODE),
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
            assert isinstance(payload, RegisterRequestPayload)
            limited = self._rate_check(
                op="register_request", key=payload.username,
                correlation_id=correlation_id,
                session_id=session_id, actor_user_id=actor_user_id,
            )
            if limited is not None:
                return limited
            try:
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

        # ---- Phone OTP (pre-authenticated) ----
        if message_type == MessageType.PHONE_OTP_REQUEST:
            assert isinstance(payload, PhoneOtpRequestPayload)
            limited = self._rate_check(
                op="phone_otp_request", key=payload.phone_number,
                correlation_id=correlation_id,
                session_id="", actor_user_id="",
            )
            if limited is not None:
                return limited
            try:
                code_length, ttl = self.phone_otp_service.request_code(payload.phone_number)
                return make_response(
                    MessageType.PHONE_OTP_REQUEST_RESPONSE,
                    correlation_id=correlation_id,
                    session_id="",
                    actor_user_id="",
                    payload=PhoneOtpRequestResponsePayload(
                        phone_number=payload.phone_number,
                        code_length=code_length,
                        expires_in_seconds=ttl,
                    ),
                ).to_dict()
            except ServiceError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id="",
                    actor_user_id="",
                    message=exc,
                )

        if message_type == MessageType.PHONE_OTP_VERIFY_REQUEST:
            assert isinstance(payload, PhoneOtpVerifyRequestPayload)
            limited = self._rate_check(
                op="phone_otp_verify_request", key=payload.phone_number,
                correlation_id=correlation_id,
                session_id="", actor_user_id="",
            )
            if limited is not None:
                return limited
            try:
                user, sid, new_account = self.phone_otp_service.verify_code(
                    payload.phone_number, payload.code,
                    device_id=payload.device_id,
                    display_name=payload.display_name,
                )
                # New phone-registered users + new sessions both count as
                # an offline -> online presence transition. Reuse the same
                # hook AuthService.login already triggers.
                self.presence_service.notify_session_started(sid)
                return make_response(
                    MessageType.PHONE_OTP_VERIFY_RESPONSE,
                    correlation_id=correlation_id,
                    session_id=sid,
                    actor_user_id=user.user_id,
                    payload=PhoneOtpVerifyResponsePayload(
                        session_id=sid,
                        user_id=user.user_id,
                        display_name=user.display_name,
                        device_id=payload.device_id,
                        new_account=new_account,
                    ),
                ).to_dict()
            except ServiceError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id="",
                    actor_user_id="",
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
                    avatar_attachment_id=user.avatar_attachment_id,
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
                        avatar_attachment_id=user.avatar_attachment_id,
                    ),
                ).to_dict()
            except ValueError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.PROFILE_AVATAR_UPDATE_REQUEST:
            assert isinstance(payload, ProfileAvatarUpdateRequestPayload)
            user = self.state.users[session.user_id]
            user.avatar_attachment_id = payload.avatar_attachment_id
            self.state.save_runtime_state()
            return make_response(
                MessageType.PROFILE_AVATAR_UPDATE_RESPONSE,
                correlation_id=correlation_id,
                session_id=session_id,
                actor_user_id=session.user_id,
                payload=ProfileAvatarUpdateResponsePayload(
                    user_id=user.user_id,
                    avatar_attachment_id=user.avatar_attachment_id,
                ),
            ).to_dict()

        if message_type == MessageType.CONVERSATION_AVATAR_UPDATE_REQUEST:
            try:
                assert isinstance(payload, ConversationAvatarUpdateRequestPayload)
                conv = self.state.conversations.get(payload.conversation_id)
                if conv is None:
                    raise ServiceError(ErrorCode.UNKNOWN_CONVERSATION)
                if session.user_id not in conv.participant_user_ids:
                    raise ServiceError(ErrorCode.CONVERSATION_ACCESS_DENIED)
                conv.avatar_attachment_id = payload.avatar_attachment_id
                self.state.save_runtime_state()
                return make_response(
                    MessageType.CONVERSATION_AVATAR_UPDATE_RESPONSE,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=ConversationAvatarUpdateResponsePayload(
                        conversation_id=conv.conversation_id,
                        avatar_attachment_id=conv.avatar_attachment_id,
                    ),
                ).to_dict()
            except ServiceError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type in (
            MessageType.POLL_CREATE_REQUEST,
            MessageType.POLL_VOTE_REQUEST,
            MessageType.POLL_CLOSE_REQUEST,
        ):
            try:
                if message_type == MessageType.POLL_CREATE_REQUEST:
                    assert isinstance(payload, PollCreateRequestPayload)
                    msg = self.polls_service.create(
                        conversation_id=payload.conversation_id,
                        sender_user_id=session.user_id,
                        question=payload.question,
                        options=payload.options,
                        multiple_choice=payload.multiple_choice,
                    )
                elif message_type == MessageType.POLL_VOTE_REQUEST:
                    assert isinstance(payload, PollVoteRequestPayload)
                    msg = self.polls_service.vote(
                        conversation_id=payload.conversation_id,
                        message_id=payload.message_id,
                        voter_user_id=session.user_id,
                        option_indices=payload.option_indices,
                    )
                else:
                    assert isinstance(payload, PollCloseRequestPayload)
                    msg = self.polls_service.close(
                        conversation_id=payload.conversation_id,
                        message_id=payload.message_id,
                        actor_user_id=session.user_id,
                    )
                # Build the canonical post-state PollDescriptor.
                raw = self.polls_service.descriptor_from_message(msg)
                assert raw is not None
                poll_desc = PollDescriptor(
                    options=[
                        PollOptionDescriptor(text=o["text"], vote_count=o["vote_count"])
                        for o in raw["options"]
                    ],
                    multiple_choice=raw["multiple_choice"],
                    closed=raw["closed"],
                    total_voters=raw["total_voters"],
                )
                conv_id = (
                    payload.conversation_id
                    if hasattr(payload, "conversation_id")
                    else ""
                )
                update = PollUpdatedPayload(
                    conversation_id=conv_id,
                    message_id=msg["message_id"],
                    poll=poll_desc,
                )
                # Fanout to every participant — same channel chat
                # messages travel on, so subscribers receive one push.
                self._fanout_to_conversation(
                    conversation_id=conv_id,
                    origin_session_id=session_id,
                    actor_user_id=session.user_id,
                    message_type=MessageType.POLL_UPDATED,
                    payload=update,
                    correlation_id=f"poll_{msg['message_id']}",
                )
                return make_response(
                    MessageType.POLL_UPDATED,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=update,
                ).to_dict()
            except ServiceError as exc:
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
            # M100: layer per-user pinned/archived flags onto the descriptors
            # the chat service produced. Done here (not in chat.py) so the
            # chat service stays unaware of per-user view preferences.
            pinned_set = self.conversation_flags_service.list_pinned(session.user_id)
            archived_set = self.conversation_flags_service.list_archived(session.user_id)
            for conv in conversations:
                conv.pinned = conv.conversation_id in pinned_set
                conv.archived = conv.conversation_id in archived_set
            return make_response(
                MessageType.CONVERSATION_SYNC,
                correlation_id=correlation_id,
                session_id=session_id,
                actor_user_id=session.user_id,
                payload=ConversationSyncResponsePayload(conversations=conversations),
            ).to_dict()

        if message_type == MessageType.MESSAGE_SEND:
            limited = self._rate_check(
                op="message_send", key=session_id,
                correlation_id=correlation_id,
                session_id=session_id, actor_user_id=session.user_id,
            )
            if limited is not None:
                return limited
            try:
                assert isinstance(payload, MessageSendRequestPayload)
                # M98: 1-on-1 send is rejected when the recipient has the
                # sender on their block list. Group sends are unaffected:
                # Telegram doesn't silently drop blocked users from groups.
                conv = self.state.conversations.get(payload.conversation_id)
                if conv is not None and len(conv.participant_user_ids) == 2:
                    other_id = next(
                        (uid for uid in conv.participant_user_ids
                         if uid != session.user_id),
                        None,
                    )
                    if other_id and self.block_mute_service.is_blocked_by(
                            other_id, session.user_id):
                        return self._error_response(
                            correlation_id=correlation_id,
                            session_id=session_id,
                            actor_user_id=session.user_id,
                            message=ServiceError(ErrorCode.BLOCKED_BY_RECIPIENT),
                        )
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
                # M99: a successful send clears any draft this user had for
                # the conversation — Telegram parity. Silent no-op if no
                # draft exists.
                self.drafts_service.clear(session.user_id, payload.conversation_id)
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
            limited = self._rate_check(
                op="message_send_attachment", key=session_id,
                correlation_id=correlation_id,
                session_id=session_id, actor_user_id=session.user_id,
            )
            if limited is not None:
                return limited
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

        if message_type == MessageType.CONVERSATION_ROLE_UPDATE_REQUEST:
            try:
                assert isinstance(payload, ConversationRoleUpdateRequestPayload)
                descriptor = self.chat_service.set_role(
                    conversation_id=payload.conversation_id,
                    actor_user_id=session.user_id,
                    target_user_id=payload.target_user_id,
                    role=payload.role,
                )
                self._fanout_to_conversation(
                    conversation_id=descriptor.conversation_id,
                    origin_session_id=session_id,
                    actor_user_id=session.user_id,
                    message_type=MessageType.CONVERSATION_UPDATED,
                    payload=descriptor,
                    correlation_id=f"push_role_{descriptor.conversation_id}_{payload.target_user_id}",
                )
                return make_response(
                    MessageType.CONVERSATION_UPDATED,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=descriptor,
                ).to_dict()
            except ServiceError as exc:
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
            limited = self._rate_check(
                op="presence_query_request", key=session_id,
                correlation_id=correlation_id,
                session_id=session_id, actor_user_id=session.user_id,
            )
            if limited is not None:
                return limited
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

        # ---- TOTP 2FA ----
        if message_type == MessageType.TWO_FA_ENABLE_REQUEST:
            try:
                secret, uri = self.two_fa_service.begin_enable(session.user_id)
                return make_response(
                    MessageType.TWO_FA_ENABLE_RESPONSE,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=TwoFaEnableResponsePayload(
                        secret=secret,
                        provisioning_uri=uri,
                    ),
                ).to_dict()
            except ServiceError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.TWO_FA_VERIFY_REQUEST:
            try:
                assert isinstance(payload, TwoFaVerifyRequestPayload)
                self.two_fa_service.confirm_enable(session.user_id, payload.code)
                return make_response(
                    MessageType.TWO_FA_VERIFY_RESPONSE,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=TwoFaVerifyResponsePayload(enabled=True),
                ).to_dict()
            except ServiceError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.TWO_FA_DISABLE_REQUEST:
            try:
                assert isinstance(payload, TwoFaDisableRequestPayload)
                self.two_fa_service.disable(session.user_id, payload.code)
                return make_response(
                    MessageType.TWO_FA_DISABLE_RESPONSE,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=TwoFaVerifyResponsePayload(enabled=False),
                ).to_dict()
            except ServiceError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        # ---- M95 Account lifecycle ----
        if message_type == MessageType.ACCOUNT_EXPORT_REQUEST:
            export = self.account_lifecycle_service.export(session.user_id)
            return make_response(
                MessageType.ACCOUNT_EXPORT_RESPONSE,
                correlation_id=correlation_id,
                session_id=session_id,
                actor_user_id=session.user_id,
                payload=AccountExportResponsePayload(
                    exported_at_ms=export["exported_at_ms"],
                    user_id=export["user_id"],
                    profile=export["profile"],
                    devices=export["devices"],
                    sessions=export["sessions"],
                    contacts=export["contacts"],
                    push_tokens=export["push_tokens"],
                    authored_messages=export["authored_messages"],
                ),
            ).to_dict()

        if message_type == MessageType.ACCOUNT_DELETE_REQUEST:
            try:
                assert isinstance(payload, AccountDeleteRequestPayload)
                # Capture the user id before delete() drops the record.
                target_user_id = session.user_id
                summary = self.account_lifecycle_service.delete(
                    target_user_id,
                    password=payload.password,
                    two_fa_code=payload.two_fa_code,
                )
                return make_response(
                    MessageType.ACCOUNT_DELETE_RESPONSE,
                    correlation_id=correlation_id,
                    session_id="",      # session was just revoked
                    actor_user_id="",   # user no longer exists
                    payload=AccountDeleteResponsePayload(
                        user_id=summary["user_id"],
                        sessions_revoked=summary["sessions_revoked"],
                        devices_removed=summary["devices_removed"],
                        push_tokens_removed=summary["push_tokens_removed"],
                        messages_tombstoned=summary["messages_tombstoned"],
                        contacts_removed=summary["contacts_removed"],
                    ),
                ).to_dict()
            except ServiceError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        # ---- M98 block + mute ----
        if message_type == MessageType.BLOCK_USER_REQUEST:
            try:
                assert isinstance(payload, BlockUserRequestPayload)
                self.block_mute_service.block(session.user_id, payload.target_user_id)
                return make_response(
                    MessageType.BLOCK_USER_ACK,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=BlockUserAckPayload(
                        target_user_id=payload.target_user_id,
                        blocked=True,
                    ),
                ).to_dict()
            except ServiceError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.UNBLOCK_USER_REQUEST:
            try:
                assert isinstance(payload, BlockUserRequestPayload)
                self.block_mute_service.unblock(session.user_id, payload.target_user_id)
                return make_response(
                    MessageType.BLOCK_USER_ACK,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=BlockUserAckPayload(
                        target_user_id=payload.target_user_id,
                        blocked=False,
                    ),
                ).to_dict()
            except ServiceError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.BLOCKED_USERS_LIST_REQUEST:
            entries = self.block_mute_service.list_blocked(session.user_id)
            return make_response(
                MessageType.BLOCKED_USERS_LIST_RESPONSE,
                correlation_id=correlation_id,
                session_id=session_id,
                actor_user_id=session.user_id,
                payload=BlockedUsersListResponsePayload(
                    blocked=[
                        BlockedUserDescriptor(
                            user_id=e.target_user_id,
                            blocked_at_ms=e.blocked_at_ms,
                        )
                        for e in entries
                    ],
                ),
            ).to_dict()

        if message_type == MessageType.CONVERSATION_MUTE_UPDATE_REQUEST:
            try:
                assert isinstance(payload, ConversationMuteUpdateRequestPayload)
                stored = self.block_mute_service.set_mute(
                    session.user_id, payload.conversation_id, payload.muted_until_ms,
                )
                return make_response(
                    MessageType.CONVERSATION_MUTE_UPDATE_RESPONSE,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=ConversationMuteUpdateResponsePayload(
                        conversation_id=payload.conversation_id,
                        muted_until_ms=stored,
                    ),
                ).to_dict()
            except ServiceError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.DRAFT_SAVE_REQUEST:
            try:
                assert isinstance(payload, DraftSaveRequestPayload)
                record, cleared = self.drafts_service.save(
                    session.user_id,
                    payload.conversation_id,
                    payload.text,
                    reply_to_message_id=payload.reply_to_message_id,
                )
                return make_response(
                    MessageType.DRAFT_SAVE_RESPONSE,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=DraftSaveResponsePayload(
                        draft=DraftDescriptor(
                            conversation_id=record.conversation_id,
                            text=record.text,
                            reply_to_message_id=record.reply_to_message_id,
                            updated_at_ms=record.updated_at_ms,
                        ),
                        cleared=cleared,
                    ),
                ).to_dict()
            except ServiceError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.DRAFT_LIST_REQUEST:
            drafts = self.drafts_service.list_for_user(session.user_id)
            return make_response(
                MessageType.DRAFT_LIST_RESPONSE,
                correlation_id=correlation_id,
                session_id=session_id,
                actor_user_id=session.user_id,
                payload=DraftListResponsePayload(
                    drafts=[
                        DraftDescriptor(
                            conversation_id=d.conversation_id,
                            text=d.text,
                            reply_to_message_id=d.reply_to_message_id,
                            updated_at_ms=d.updated_at_ms,
                        )
                        for d in drafts
                    ],
                ),
            ).to_dict()

        if message_type == MessageType.DRAFT_CLEAR_REQUEST:
            assert isinstance(payload, DraftClearRequestPayload)
            removed = self.drafts_service.clear(session.user_id, payload.conversation_id)
            return make_response(
                MessageType.DRAFT_CLEAR_RESPONSE,
                correlation_id=correlation_id,
                session_id=session_id,
                actor_user_id=session.user_id,
                payload=DraftClearResponsePayload(
                    conversation_id=payload.conversation_id,
                    cleared=removed,
                ),
            ).to_dict()

        if message_type == MessageType.CONVERSATION_PIN_TOGGLE_REQUEST:
            try:
                assert isinstance(payload, ConversationPinToggleRequestPayload)
                stored = self.conversation_flags_service.set_pinned(
                    session.user_id, payload.conversation_id, payload.pinned,
                )
                return make_response(
                    MessageType.CONVERSATION_PIN_TOGGLE_RESPONSE,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=ConversationPinToggleResponsePayload(
                        conversation_id=payload.conversation_id, pinned=stored,
                    ),
                ).to_dict()
            except ServiceError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.CONVERSATION_ARCHIVE_TOGGLE_REQUEST:
            try:
                assert isinstance(payload, ConversationArchiveToggleRequestPayload)
                stored = self.conversation_flags_service.set_archived(
                    session.user_id, payload.conversation_id, payload.archived,
                )
                return make_response(
                    MessageType.CONVERSATION_ARCHIVE_TOGGLE_RESPONSE,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=ConversationArchiveToggleResponsePayload(
                        conversation_id=payload.conversation_id, archived=stored,
                    ),
                ).to_dict()
            except ServiceError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.ATTACHMENT_UPLOAD_INIT_REQUEST:
            try:
                assert isinstance(payload, AttachmentUploadInitRequestPayload)
                upload_id, chunk_size = self.chat_service.init_upload(
                    conversation_id=payload.conversation_id,
                    user_id=session.user_id,
                    filename=payload.filename,
                    mime_type=payload.mime_type,
                    total_size_bytes=payload.total_size_bytes,
                )
                return make_response(
                    MessageType.ATTACHMENT_UPLOAD_INIT_RESPONSE,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=AttachmentUploadInitResponsePayload(
                        upload_id=upload_id, chunk_size=chunk_size,
                    ),
                ).to_dict()
            except ServiceError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.ATTACHMENT_UPLOAD_CHUNK_REQUEST:
            try:
                assert isinstance(payload, AttachmentUploadChunkRequestPayload)
                received_bytes = self.chat_service.accept_upload_chunk(
                    upload_id=payload.upload_id,
                    user_id=session.user_id,
                    sequence=payload.sequence,
                    content_b64=payload.content_b64,
                )
                return make_response(
                    MessageType.ATTACHMENT_UPLOAD_CHUNK_ACK,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=AttachmentUploadChunkAckPayload(
                        upload_id=payload.upload_id,
                        sequence=payload.sequence,
                        received_bytes=received_bytes,
                    ),
                ).to_dict()
            except ServiceError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

        if message_type == MessageType.ATTACHMENT_UPLOAD_COMPLETE_REQUEST:
            try:
                assert isinstance(payload, AttachmentUploadCompleteRequestPayload)
                message_result = self.chat_service.complete_upload(
                    upload_id=payload.upload_id,
                    user_id=session.user_id,
                    caption=payload.caption,
                )
                self._fanout_to_conversation(
                    conversation_id=message_result.conversation_id,
                    origin_session_id=session_id,
                    actor_user_id=session.user_id,
                    message_type=MessageType.MESSAGE_DELIVER,
                    payload=message_result,
                    correlation_id=f"push_{message_result.message_id}",
                )
                self._enqueue_mock_pushes_for_offline_recipients(
                    conversation_id=message_result.conversation_id,
                    sender_user_id=session.user_id,
                    body_summary=(message_result.text or message_result.filename or "")[:80],
                )
                return make_response(
                    MessageType.MESSAGE_DELIVER,
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    payload=message_result,
                ).to_dict()
            except ServiceError as exc:
                return self._error_response(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    actor_user_id=session.user_id,
                    message=exc,
                )

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

    def _rate_check(
        self,
        *,
        op: str,
        key: str,
        correlation_id: str,
        session_id: str,
        actor_user_id: str,
    ) -> dict[str, Any] | None:
        """Returns None when the request is allowed, or a typed RATE_LIMITED
        error response when the bucket is empty. Increments
        `rate_limited_total{type=op}` so operators see the rejections."""
        if self.rate_limiter.try_acquire(op, key):
            return None
        self.observability.metrics.inc(
            "rate_limited_total", labels={"type": op},
        )
        return self._error_response(
            correlation_id=correlation_id,
            session_id=session_id,
            actor_user_id=actor_user_id,
            message=ServiceError(ErrorCode.RATE_LIMITED),
        )

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
