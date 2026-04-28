from __future__ import annotations

import base64
import binascii
import time

from ..protocol import (
    AttachmentFetchResponsePayload,
    ConversationChangeDescriptor,
    ConversationDescriptor,
    ErrorCode,
    MessageDeletedPayload,
    MessageDeliverPayload,
    MessageDescriptor,
    MessageEditedPayload,
    MessagePinUpdatedPayload,
    MessageSearchResultDescriptor,
    MessageReadUpdatePayload,
    MessageReactionUpdatedPayload,
    ServiceError,
)
from ..state import AttachmentRecord, ConversationRecord, InMemoryState
from .attachment_store import AttachmentBlobStore

MAX_ATTACHMENT_SIZE_BYTES = 1_048_576  # 1 MB
MAX_CONVERSATION_CHANGES = 512

# Chunked upload tunables (M88).
DEFAULT_CHUNK_SIZE_BYTES = 1_048_576       # 1 MB suggested chunk
MAX_CHUNKED_UPLOAD_BYTES = 64 * 1_048_576  # 64 MB hard cap per upload
MAX_ACTIVE_UPLOADS_PER_USER = 8
# Server-wide cap so a 1000-user system can't OOM on 8000 concurrent
# in-memory upload buffers. Hits before MAX_ACTIVE_UPLOADS_PER_USER for
# users beyond ~125 concurrent uploaders. Operators can lift this once the
# blob store gains a streaming write path.
MAX_ACTIVE_UPLOADS_TOTAL = 256


class _UploadSession:
    """Per-upload state held in memory while the client streams chunks.

    Lives only inside ChatService; not persisted. If the server restarts
    mid-upload the client must restart from init — the same as Telegram's
    own upload contract.
    """
    __slots__ = (
        "upload_id", "user_id", "conversation_id", "filename", "mime_type",
        "total_size_bytes", "next_sequence", "buffer",
    )

    def __init__(self, upload_id: str, user_id: str, conversation_id: str,
                 filename: str, mime_type: str, total_size_bytes: int) -> None:
        self.upload_id = upload_id
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.filename = filename
        self.mime_type = mime_type
        self.total_size_bytes = total_size_bytes
        self.next_sequence = 0
        self.buffer = bytearray()


class ChatService:
    def __init__(self, state: InMemoryState, attachment_store: AttachmentBlobStore | None = None) -> None:
        self._state = state
        self._attachment_store = attachment_store or AttachmentBlobStore(None)
        self._message_counter = self._next_message_counter()
        self._conversation_counter = self._next_conversation_counter()
        self._attachment_counter = self._next_attachment_counter()
        self._upload_counter = 0
        self._uploads: dict[str, _UploadSession] = {}

    def describe(self) -> str:
        return "chat service ready for conversation membership, message persistence and fan-out"

    def sync_for_user(self, user_id: str) -> list[ConversationDescriptor]:
        return [
            self._descriptor(conversation)
            for conversation in self._state.conversations.values()
            if user_id in conversation.participant_user_ids
        ]

    def sync_for_user_since(
        self,
        user_id: str,
        cursors: dict[str, str],
        versions: dict[str, int] | None = None,
        history_limits: dict[str, int] | None = None,
        before_message_ids: dict[str, str] | None = None,
    ) -> list[ConversationDescriptor]:
        versions = versions or {}
        history_limits = history_limits or {}
        before_message_ids = before_message_ids or {}
        conversations: list[ConversationDescriptor] = []
        for conversation in self._state.conversations.values():
            if user_id not in conversation.participant_user_ids:
                continue
            history_limit = int(history_limits.get(conversation.conversation_id, 0))
            if history_limit > 0:
                page, next_before_message_id, has_more = self._message_history_page(
                    conversation,
                    limit=history_limit,
                    before_message_id=before_message_ids.get(conversation.conversation_id, ""),
                )
                conversations.append(
                    self._descriptor(
                        conversation,
                        messages=page,
                        next_before_message_id=next_before_message_id,
                        has_more=has_more,
                    )
                )
                continue
            cursor = cursors.get(conversation.conversation_id, "")
            version = int(versions.get(conversation.conversation_id, 0))
            if not cursor:
                conversations.append(self._descriptor(conversation))
                continue
            messages = self._messages_after(conversation, cursor)
            changes = self._changes_after(conversation, version)
            if messages is None or changes is None:
                conversations.append(self._descriptor(conversation))
            elif messages or changes:
                conversations.append(
                    self._descriptor(conversation, messages=messages, changes=changes)
                )
        return conversations

    def send_message(
        self, *, conversation_id: str, sender_user_id: str, text: str, reply_to_message_id: str = ""
    ) -> MessageDeliverPayload:
        conversation = self._state.conversations.get(conversation_id)
        if conversation is None:
            raise ServiceError(ErrorCode.UNKNOWN_CONVERSATION)
        if sender_user_id not in conversation.participant_user_ids:
            raise ServiceError(ErrorCode.CONVERSATION_ACCESS_DENIED)
        if not text.strip():
            raise ServiceError(ErrorCode.EMPTY_MESSAGE)
        if reply_to_message_id:
            reply_to = self._find_message(conversation, reply_to_message_id)
            if reply_to.get("deleted"):
                raise ServiceError(ErrorCode.MESSAGE_ALREADY_DELETED)
        message = {
            "message_id": f"msg_{self._message_counter}",
            "sender_user_id": sender_user_id,
            "text": text,
            "created_at_ms": self._now_ms(),
        }
        if reply_to_message_id:
            message["reply_to_message_id"] = reply_to_message_id
        self._message_counter += 1
        conversation.messages.append(message)
        self._state.save_runtime_state()
        return MessageDeliverPayload(
            conversation_id=conversation_id,
            message_id=message["message_id"],
            sender_user_id=sender_user_id,
            text=text,
            created_at_ms=int(message["created_at_ms"]),
            reply_to_message_id=reply_to_message_id,
        )

    # ---- chunked upload (M88) ----

    def init_upload(
        self,
        *,
        conversation_id: str,
        user_id: str,
        filename: str,
        mime_type: str,
        total_size_bytes: int,
    ) -> tuple[str, int]:
        self._require_participant(conversation_id, user_id)
        if not filename.strip():
            raise ServiceError(ErrorCode.INVALID_ATTACHMENT_PAYLOAD)
        if total_size_bytes <= 0:
            raise ServiceError(ErrorCode.INVALID_ATTACHMENT_PAYLOAD)
        if total_size_bytes > MAX_CHUNKED_UPLOAD_BYTES:
            raise ServiceError(ErrorCode.UPLOAD_TOO_LARGE)
        if len(self._uploads) >= MAX_ACTIVE_UPLOADS_TOTAL:
            raise ServiceError(ErrorCode.UPLOAD_LIMIT_REACHED)
        active = sum(1 for s in self._uploads.values() if s.user_id == user_id)
        if active >= MAX_ACTIVE_UPLOADS_PER_USER:
            raise ServiceError(ErrorCode.UPLOAD_LIMIT_REACHED)
        self._upload_counter += 1
        upload_id = f"upl_{self._upload_counter}"
        self._uploads[upload_id] = _UploadSession(
            upload_id=upload_id,
            user_id=user_id,
            conversation_id=conversation_id,
            filename=filename,
            mime_type=mime_type or "application/octet-stream",
            total_size_bytes=total_size_bytes,
        )
        return upload_id, DEFAULT_CHUNK_SIZE_BYTES

    def accept_upload_chunk(
        self,
        *,
        upload_id: str,
        user_id: str,
        sequence: int,
        content_b64: str,
    ) -> int:
        session = self._uploads.get(upload_id)
        if session is None or session.user_id != user_id:
            raise ServiceError(ErrorCode.UNKNOWN_UPLOAD)
        if sequence != session.next_sequence:
            raise ServiceError(ErrorCode.UPLOAD_CHUNK_OUT_OF_ORDER)
        if not content_b64:
            # Empty body would silently no-op and force the client to
            # eventually trip UPLOAD_SIZE_MISMATCH at complete time. Reject
            # up-front so the client gets a useful, immediate error.
            raise ServiceError(ErrorCode.INVALID_ATTACHMENT_PAYLOAD)
        try:
            chunk = base64.b64decode(content_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ServiceError(ErrorCode.INVALID_ATTACHMENT_PAYLOAD) from exc
        if len(session.buffer) + len(chunk) > session.total_size_bytes:
            # Refuse to over-fill the declared size; the upload as a whole
            # would fail UPLOAD_SIZE_MISMATCH on complete anyway.
            raise ServiceError(ErrorCode.UPLOAD_SIZE_MISMATCH)
        session.buffer.extend(chunk)
        session.next_sequence += 1
        return len(session.buffer)

    def complete_upload(
        self,
        *,
        upload_id: str,
        user_id: str,
        caption: str,
    ) -> MessageDeliverPayload:
        session = self._uploads.get(upload_id)
        if session is None or session.user_id != user_id:
            raise ServiceError(ErrorCode.UNKNOWN_UPLOAD)
        if len(session.buffer) != session.total_size_bytes:
            # Tear down the session — client must restart from init.
            self._uploads.pop(upload_id, None)
            raise ServiceError(ErrorCode.UPLOAD_SIZE_MISMATCH)

        # Same persistence path as the small-file send_attachment_message:
        # write through the blob store when it has a backing root, otherwise
        # keep the bytes inline so fetch_attachment can still serve them.
        decoded = bytes(session.buffer)
        attachment_id = f"att_{self._attachment_counter}"
        self._attachment_counter += 1
        storage_key = self._attachment_store.put(attachment_id, decoded)
        inline_b64 = "" if storage_key else base64.b64encode(decoded).decode("ascii")
        self._state.attachments[attachment_id] = AttachmentRecord(
            attachment_id=attachment_id,
            conversation_id=session.conversation_id,
            uploader_user_id=user_id,
            filename=session.filename,
            mime_type=session.mime_type,
            size_bytes=session.total_size_bytes,
            content_b64=inline_b64,
            storage_key=storage_key,
        )
        message_id = f"msg_{self._message_counter}"
        self._message_counter += 1
        message = {
            "message_id": message_id,
            "sender_user_id": user_id,
            "text": caption,
            "attachment_id": attachment_id,
            "created_at_ms": self._now_ms(),
        }
        conversation = self._require_participant(session.conversation_id, user_id)
        conversation.messages.append(message)
        self._state.save_runtime_state()
        # Session served its purpose; release memory.
        self._uploads.pop(upload_id, None)
        return MessageDeliverPayload(
            conversation_id=session.conversation_id,
            message_id=message_id,
            sender_user_id=user_id,
            text=caption,
            created_at_ms=int(message["created_at_ms"]),
            attachment_id=attachment_id,
            filename=session.filename,
            mime_type=session.mime_type,
            size_bytes=session.total_size_bytes,
        )

    def send_attachment_message(
        self,
        *,
        conversation_id: str,
        sender_user_id: str,
        caption: str,
        filename: str,
        mime_type: str,
        content_b64: str,
        declared_size_bytes: int,
    ) -> MessageDeliverPayload:
        conversation = self._require_participant(conversation_id, sender_user_id)
        if not filename.strip():
            raise ServiceError(ErrorCode.INVALID_ATTACHMENT_PAYLOAD)
        if declared_size_bytes < 0 or declared_size_bytes > MAX_ATTACHMENT_SIZE_BYTES:
            raise ServiceError(ErrorCode.ATTACHMENT_TOO_LARGE)
        if not content_b64:
            raise ServiceError(ErrorCode.INVALID_ATTACHMENT_PAYLOAD)
        try:
            decoded = base64.b64decode(content_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ServiceError(ErrorCode.INVALID_ATTACHMENT_PAYLOAD) from exc
        if len(decoded) != declared_size_bytes:
            raise ServiceError(ErrorCode.INVALID_ATTACHMENT_PAYLOAD)
        if len(decoded) > MAX_ATTACHMENT_SIZE_BYTES:
            raise ServiceError(ErrorCode.ATTACHMENT_TOO_LARGE)

        attachment_id = f"att_{self._attachment_counter}"
        self._attachment_counter += 1
        storage_key = self._attachment_store.put(attachment_id, decoded)
        self._state.attachments[attachment_id] = AttachmentRecord(
            attachment_id=attachment_id,
            conversation_id=conversation_id,
            uploader_user_id=sender_user_id,
            filename=filename,
            mime_type=mime_type or "application/octet-stream",
            size_bytes=declared_size_bytes,
            content_b64="" if storage_key else content_b64,
            storage_key=storage_key,
        )

        message_id = f"msg_{self._message_counter}"
        self._message_counter += 1
        message = {
            "message_id": message_id,
            "sender_user_id": sender_user_id,
            "text": caption,
            "attachment_id": attachment_id,
            "created_at_ms": self._now_ms(),
        }
        conversation.messages.append(message)
        self._state.save_runtime_state()

        return MessageDeliverPayload(
            conversation_id=conversation_id,
            message_id=message_id,
            sender_user_id=sender_user_id,
            text=caption,
            created_at_ms=int(message["created_at_ms"]),
            attachment_id=attachment_id,
            filename=filename,
            mime_type=mime_type or "application/octet-stream",
            size_bytes=declared_size_bytes,
        )

    def fetch_attachment(
        self, *, attachment_id: str, requester_user_id: str
    ) -> AttachmentFetchResponsePayload:
        attachment = self._state.attachments.get(attachment_id)
        if attachment is None:
            raise ServiceError(ErrorCode.UNKNOWN_ATTACHMENT)
        conversation = self._state.conversations.get(attachment.conversation_id)
        if conversation is None or requester_user_id not in conversation.participant_user_ids:
            raise ServiceError(ErrorCode.ATTACHMENT_ACCESS_DENIED)
        content_b64 = attachment.content_b64
        if attachment.storage_key:
            content_b64 = base64.b64encode(
                self._attachment_store.get(attachment.storage_key)
            ).decode("ascii")
        return AttachmentFetchResponsePayload(
            attachment_id=attachment.attachment_id,
            conversation_id=attachment.conversation_id,
            uploader_user_id=attachment.uploader_user_id,
            filename=attachment.filename,
            mime_type=attachment.mime_type,
            size_bytes=attachment.size_bytes,
            content_b64=content_b64,
        )

    def create_conversation(
        self,
        *,
        creator_user_id: str,
        other_user_ids: list[str],
        title: str = "",
    ) -> ConversationDescriptor:
        participants: list[str] = [creator_user_id]
        for uid in other_user_ids:
            if uid == creator_user_id:
                continue
            if uid in participants:
                continue
            if uid not in self._state.users:
                raise ServiceError(ErrorCode.UNKNOWN_USER)
            participants.append(uid)
        if len(participants) < 2:
            raise ServiceError(ErrorCode.CONVERSATION_TOO_FEW_PARTICIPANTS)

        conversation_id = f"conv_{self._conversation_counter}"
        self._conversation_counter += 1
        record = ConversationRecord(
            conversation_id=conversation_id,
            participant_user_ids=participants,
            messages=[],
            title=title,
        )
        self._state.conversations[conversation_id] = record
        self._state.save_runtime_state()
        return self._descriptor(record)

    def add_participant(
        self, *, conversation_id: str, actor_user_id: str, new_user_id: str
    ) -> ConversationDescriptor:
        conversation = self._require_participant(conversation_id, actor_user_id)
        if new_user_id not in self._state.users:
            raise ServiceError(ErrorCode.UNKNOWN_USER)
        if new_user_id in conversation.participant_user_ids:
            raise ServiceError(ErrorCode.CONVERSATION_PARTICIPANT_ALREADY_PRESENT)
        conversation.participant_user_ids.append(new_user_id)
        self._record_change(conversation, kind="conversation_updated")
        self._state.save_runtime_state()
        return self._descriptor(conversation)

    def remove_participant(
        self, *, conversation_id: str, actor_user_id: str, target_user_id: str
    ) -> ConversationDescriptor:
        conversation = self._require_participant(conversation_id, actor_user_id)
        if target_user_id not in conversation.participant_user_ids:
            raise ServiceError(ErrorCode.CONVERSATION_PARTICIPANT_NOT_PRESENT)
        conversation.participant_user_ids.remove(target_user_id)
        self._record_change(conversation, kind="conversation_updated")
        self._state.save_runtime_state()
        return self._descriptor(conversation)

    def edit_message(
        self,
        *,
        conversation_id: str,
        actor_user_id: str,
        message_id: str,
        new_text: str,
    ) -> MessageEditedPayload:
        conversation = self._require_participant(conversation_id, actor_user_id)
        message = self._find_message(conversation, message_id)
        if message["sender_user_id"] != actor_user_id:
            raise ServiceError(ErrorCode.MESSAGE_EDIT_DENIED)
        if message.get("deleted"):
            raise ServiceError(ErrorCode.MESSAGE_ALREADY_DELETED)
        if not new_text.strip():
            raise ServiceError(ErrorCode.EMPTY_MESSAGE)
        message["text"] = new_text
        message["edited"] = True
        self._record_change(
            conversation,
            kind="message_edited",
            message_id=message_id,
            sender_user_id=actor_user_id,
            text=new_text,
        )
        self._state.save_runtime_state()
        return MessageEditedPayload(
            conversation_id=conversation_id,
            message_id=message_id,
            text=new_text,
            sender_user_id=actor_user_id,
        )

    def delete_message(
        self,
        *,
        conversation_id: str,
        actor_user_id: str,
        message_id: str,
    ) -> MessageDeletedPayload:
        conversation = self._require_participant(conversation_id, actor_user_id)
        message = self._find_message(conversation, message_id)
        if message["sender_user_id"] != actor_user_id:
            raise ServiceError(ErrorCode.MESSAGE_DELETE_DENIED)
        if message.get("deleted"):
            raise ServiceError(ErrorCode.MESSAGE_ALREADY_DELETED)
        message["deleted"] = True
        message["text"] = ""
        self._record_change(
            conversation,
            kind="message_deleted",
            message_id=message_id,
            sender_user_id=actor_user_id,
        )
        self._state.save_runtime_state()
        return MessageDeletedPayload(
            conversation_id=conversation_id,
            message_id=message_id,
            sender_user_id=actor_user_id,
        )

    def forward_message(
        self,
        *,
        source_conversation_id: str,
        source_message_id: str,
        target_conversation_id: str,
        actor_user_id: str,
    ) -> MessageDeliverPayload:
        source_conversation = self._require_participant(source_conversation_id, actor_user_id)
        target_conversation = self._require_participant(target_conversation_id, actor_user_id)
        source = self._find_message(source_conversation, source_message_id)
        if source.get("deleted"):
            raise ServiceError(ErrorCode.MESSAGE_ALREADY_DELETED)
        text = str(source.get("text", ""))
        if not text.strip() and not source.get("attachment_id"):
            raise ServiceError(ErrorCode.EMPTY_MESSAGE)
        message = {
            "message_id": f"msg_{self._message_counter}",
            "sender_user_id": actor_user_id,
            "text": text,
            "created_at_ms": self._now_ms(),
            "forwarded_from_conversation_id": source_conversation_id,
            "forwarded_from_message_id": source_message_id,
            "forwarded_from_sender_user_id": str(source.get("sender_user_id", "")),
        }
        if source.get("attachment_id"):
            message["attachment_id"] = str(source.get("attachment_id", ""))
        self._message_counter += 1
        target_conversation.messages.append(message)
        self._state.save_runtime_state()
        filename, mime_type, size_bytes = self._attachment_meta(message)
        return MessageDeliverPayload(
            conversation_id=target_conversation_id,
            message_id=message["message_id"],
            sender_user_id=actor_user_id,
            text=text,
            created_at_ms=int(message["created_at_ms"]),
            attachment_id=str(message.get("attachment_id", "")),
            filename=filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            forwarded_from_conversation_id=source_conversation_id,
            forwarded_from_message_id=source_message_id,
            forwarded_from_sender_user_id=str(source.get("sender_user_id", "")),
        )

    def toggle_reaction(
        self,
        *,
        conversation_id: str,
        actor_user_id: str,
        message_id: str,
        emoji: str,
    ) -> MessageReactionUpdatedPayload:
        conversation = self._require_participant(conversation_id, actor_user_id)
        message = self._find_message(conversation, message_id)
        if message.get("deleted"):
            raise ServiceError(ErrorCode.MESSAGE_ALREADY_DELETED)
        emoji = emoji.strip()
        if not emoji or len(emoji) > 16:
            raise ServiceError(ErrorCode.EMPTY_MESSAGE)
        reactions = message.setdefault("reactions", {})
        if not isinstance(reactions, dict):
            reactions = {}
            message["reactions"] = reactions
        users = reactions.setdefault(emoji, [])
        if not isinstance(users, list):
            users = []
            reactions[emoji] = users
        if actor_user_id in users:
            users.remove(actor_user_id)
            if not users:
                reactions.pop(emoji, None)
        else:
            users.append(actor_user_id)
            users.sort()
        summary = self._reaction_summary(message)
        self._record_change(
            conversation,
            kind="message_reaction_updated",
            message_id=message_id,
            sender_user_id=actor_user_id,
            reaction_summary=summary,
        )
        self._state.save_runtime_state()
        return MessageReactionUpdatedPayload(
            conversation_id=conversation_id,
            message_id=message_id,
            actor_user_id=actor_user_id,
            emoji=emoji,
            reaction_summary=summary,
        )

    def set_pin(
        self,
        *,
        conversation_id: str,
        actor_user_id: str,
        message_id: str,
        pinned: bool,
    ) -> MessagePinUpdatedPayload:
        conversation = self._require_participant(conversation_id, actor_user_id)
        message = self._find_message(conversation, message_id)
        if message.get("deleted"):
            raise ServiceError(ErrorCode.MESSAGE_ALREADY_DELETED)
        message["pinned"] = bool(pinned)
        self._record_change(
            conversation,
            kind="message_pin_updated",
            message_id=message_id,
            sender_user_id=actor_user_id,
            pinned=bool(pinned),
        )
        self._state.save_runtime_state()
        return MessagePinUpdatedPayload(
            conversation_id=conversation_id,
            message_id=message_id,
            actor_user_id=actor_user_id,
            pinned=bool(pinned),
        )

    def search_messages(
        self,
        *,
        user_id: str,
        query: str,
        conversation_id: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[MessageSearchResultDescriptor], int, bool]:
        needle = query.strip().casefold()
        if not needle:
            raise ServiceError(ErrorCode.EMPTY_MESSAGE)
        limit = max(1, min(limit, 100))
        offset = max(0, offset)
        matches: list[MessageSearchResultDescriptor] = []
        for conversation in self._state.conversations.values():
            if user_id not in conversation.participant_user_ids:
                continue
            if conversation_id and conversation.conversation_id != conversation_id:
                continue
            for message in conversation.messages:
                if message.get("deleted"):
                    continue
                haystack = " ".join(
                    [
                        str(message.get("message_id", "")),
                        str(message.get("sender_user_id", "")),
                        str(message.get("text", "")),
                        str(message.get("attachment_id", "")),
                        self._attachment_meta(message)[0],
                    ]
                ).casefold()
                if needle not in haystack:
                    continue
                text = str(message.get("text", ""))
                snippet = text if len(text) <= 120 else text[:117] + "..."
                matches.append(
                    MessageSearchResultDescriptor(
                        conversation_id=conversation.conversation_id,
                        conversation_title=conversation.title,
                        message_id=str(message.get("message_id", "")),
                        sender_user_id=str(message.get("sender_user_id", "")),
                        text=text,
                        created_at_ms=int(message.get("created_at_ms", 0)),
                        attachment_id=str(message.get("attachment_id", "")),
                        filename=self._attachment_meta(message)[0],
                        snippet=snippet or str(message.get("message_id", "")),
                    )
                )
        results = matches[offset: offset + limit]
        next_offset = offset + len(results)
        return results, next_offset, next_offset < len(matches)

    def _find_message(self, conversation: ConversationRecord, message_id: str) -> dict:
        for message in conversation.messages:
            if message.get("message_id") == message_id:
                return message
        raise ServiceError(ErrorCode.UNKNOWN_MESSAGE)

    def mark_read(
        self,
        *,
        conversation_id: str,
        reader_user_id: str,
        message_id: str,
    ) -> MessageReadUpdatePayload:
        conversation = self._require_participant(conversation_id, reader_user_id)
        # Index map ensures forward-only advancement
        index_by_id = {m["message_id"]: i for i, m in enumerate(conversation.messages)}
        if message_id not in index_by_id:
            raise ServiceError(ErrorCode.UNKNOWN_MESSAGE)
        current = conversation.read_markers.get(reader_user_id)
        current_idx = index_by_id[current] if current in index_by_id else -1
        new_idx = index_by_id[message_id]
        effective_id = message_id if new_idx >= current_idx else current  # type: ignore[assignment]
        conversation.read_markers[reader_user_id] = effective_id
        if effective_id != current:
            self._record_change(
                conversation,
                kind="read_marker",
                reader_user_id=reader_user_id,
                last_read_message_id=effective_id,
            )
        self._state.save_runtime_state()
        return MessageReadUpdatePayload(
            conversation_id=conversation_id,
            reader_user_id=reader_user_id,
            last_read_message_id=effective_id,
        )

    def _require_participant(
        self, conversation_id: str, user_id: str
    ) -> ConversationRecord:
        conversation = self._state.conversations.get(conversation_id)
        if conversation is None:
            raise ServiceError(ErrorCode.UNKNOWN_CONVERSATION)
        if user_id not in conversation.participant_user_ids:
            raise ServiceError(ErrorCode.CONVERSATION_ACCESS_DENIED)
        return conversation

    def _descriptor(
        self,
        conversation: ConversationRecord,
        *,
        messages: list[dict] | None = None,
        changes: list[dict[str, object]] | None = None,
        next_before_message_id: str = "",
        has_more: bool = False,
    ) -> ConversationDescriptor:
        source_messages = conversation.messages if messages is None else messages
        return ConversationDescriptor(
            conversation_id=conversation.conversation_id,
            participant_user_ids=list(conversation.participant_user_ids),
            messages=[
                MessageDescriptor(
                    message_id=message["message_id"],
                    sender_user_id=message["sender_user_id"],
                    text=message["text"],
                    created_at_ms=int(message.get("created_at_ms", 0)),
                    edited=bool(message.get("edited", False)),
                    deleted=bool(message.get("deleted", False)),
                    attachment_id=str(message.get("attachment_id", "")),
                    filename=self._attachment_meta(message)[0],
                    mime_type=self._attachment_meta(message)[1],
                    size_bytes=self._attachment_meta(message)[2],
                    reply_to_message_id=str(message.get("reply_to_message_id", "")),
                    forwarded_from_conversation_id=str(message.get("forwarded_from_conversation_id", "")),
                    forwarded_from_message_id=str(message.get("forwarded_from_message_id", "")),
                    forwarded_from_sender_user_id=str(message.get("forwarded_from_sender_user_id", "")),
                    reaction_summary=self._reaction_summary(message),
                    pinned=bool(message.get("pinned", False)),
                )
                for message in source_messages
            ],
            title=conversation.title,
            read_markers=dict(conversation.read_markers),
            version=conversation.change_seq,
            changes=[
                ConversationChangeDescriptor(
                    version=int(change.get("version", 0)),
                    kind=str(change.get("kind", "")),
                    message_id=str(change.get("message_id", "")),
                    sender_user_id=str(change.get("sender_user_id", "")),
                    text=str(change.get("text", "")),
                    reader_user_id=str(change.get("reader_user_id", "")),
                    last_read_message_id=str(change.get("last_read_message_id", "")),
                    reply_to_message_id=str(change.get("reply_to_message_id", "")),
                    forwarded_from_conversation_id=str(change.get("forwarded_from_conversation_id", "")),
                    forwarded_from_message_id=str(change.get("forwarded_from_message_id", "")),
                    forwarded_from_sender_user_id=str(change.get("forwarded_from_sender_user_id", "")),
                    reaction_summary=str(change.get("reaction_summary", "")),
                    pinned=bool(change.get("pinned", False)),
                )
                for change in ([] if changes is None else changes)
            ],
            next_before_message_id=next_before_message_id,
            has_more=has_more,
        )

    def _message_history_page(
        self,
        conversation: ConversationRecord,
        *,
        limit: int,
        before_message_id: str = "",
    ) -> tuple[list[dict], str, bool]:
        limit = max(1, min(limit, 100))
        end = len(conversation.messages)
        if before_message_id:
            for index, message in enumerate(conversation.messages):
                if message.get("message_id") == before_message_id:
                    end = index
                    break
            else:
                end = 0
        start = max(0, end - limit)
        page = conversation.messages[start:end]
        has_more = start > 0
        next_before_message_id = str(page[0].get("message_id", "")) if has_more and page else ""
        return page, next_before_message_id, has_more

    def _attachment_meta(self, message: dict) -> tuple[str, str, int]:
        attachment_id = str(message.get("attachment_id", ""))
        attachment = self._state.attachments.get(attachment_id)
        if attachment is None:
            return "", "", 0
        return attachment.filename, attachment.mime_type, attachment.size_bytes

    def _reaction_summary(self, message: dict) -> str:
        reactions = message.get("reactions", {})
        if not isinstance(reactions, dict):
            return ""
        parts: list[str] = []
        for emoji in sorted(str(key) for key in reactions):
            users = reactions.get(emoji, [])
            if not isinstance(users, list) or not users:
                continue
            parts.append(f"{emoji}:{len(users)}")
        return ",".join(parts)

    def _messages_after(
        self, conversation: ConversationRecord, cursor_message_id: str
    ) -> list[dict] | None:
        for index, message in enumerate(conversation.messages):
            if message.get("message_id") == cursor_message_id:
                return conversation.messages[index + 1 :]
        return None

    def _changes_after(
        self, conversation: ConversationRecord, version: int
    ) -> list[dict[str, object]] | None:
        if conversation.changes:
            oldest_version = int(conversation.changes[0].get("version", 0))
            if version < oldest_version - 1:
                return None
        return [
            change for change in conversation.changes
            if int(change.get("version", 0)) > version
        ]

    def _record_change(
        self,
        conversation: ConversationRecord,
        *,
        kind: str,
        message_id: str = "",
        sender_user_id: str = "",
        text: str = "",
        reader_user_id: str = "",
        last_read_message_id: str = "",
        reply_to_message_id: str = "",
        forwarded_from_conversation_id: str = "",
        forwarded_from_message_id: str = "",
        forwarded_from_sender_user_id: str = "",
        reaction_summary: str = "",
        pinned: bool = False,
    ) -> None:
        conversation.change_seq += 1
        conversation.changes.append(
            {
                "version": conversation.change_seq,
                "kind": kind,
                "message_id": message_id,
                "sender_user_id": sender_user_id,
                "text": text,
                "reader_user_id": reader_user_id,
                "last_read_message_id": last_read_message_id,
                "reply_to_message_id": reply_to_message_id,
                "forwarded_from_conversation_id": forwarded_from_conversation_id,
                "forwarded_from_message_id": forwarded_from_message_id,
                "forwarded_from_sender_user_id": forwarded_from_sender_user_id,
                "reaction_summary": reaction_summary,
                "pinned": pinned,
            }
        )
        if len(conversation.changes) > MAX_CONVERSATION_CHANGES:
            conversation.changes = conversation.changes[-MAX_CONVERSATION_CHANGES:]

    def _now_ms(self) -> int:
        return int(time.time() * 1000)

    def _next_message_counter(self) -> int:
        highest = 1
        for conversation in self._state.conversations.values():
            for message in conversation.messages:
                message_id = message.get("message_id", "")
                if not message_id.startswith("msg_"):
                    continue
                try:
                    highest = max(highest, int(message_id.removeprefix("msg_")))
                except ValueError:
                    continue
        return highest + 1

    def _next_conversation_counter(self) -> int:
        highest = 0
        for conversation_id in self._state.conversations:
            if not conversation_id.startswith("conv_"):
                continue
            suffix = conversation_id.removeprefix("conv_")
            try:
                highest = max(highest, int(suffix))
            except ValueError:
                continue
        return highest + 1

    def _next_attachment_counter(self) -> int:
        highest = 0
        for attachment_id in self._state.attachments:
            if not attachment_id.startswith("att_"):
                continue
            try:
                highest = max(highest, int(attachment_id.removeprefix("att_")))
            except ValueError:
                continue
        return highest + 1
