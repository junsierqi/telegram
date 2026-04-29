"""Server-side per-(user, conversation) drafts (M99).

A draft is an unsent message text the user is half-typing. Storing it on
the server means it follows the user across devices — start typing on the
desktop, finish on the phone. Telegram does this. Implementation is a
simple keyed map; no message persistence in conversation history until
the actual MESSAGE_SEND fires.

Empty text on save auto-clears the draft (same UX as Telegram). Sending a
message in the conversation should also clear the draft — that's wired in
ChatService.send_message via this service's clear() method.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from ..protocol import ErrorCode, ServiceError
from ..state import DraftRecord, InMemoryState


class DraftsService:
    def __init__(
        self,
        state: InMemoryState,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._state = state
        self._clock = clock or time.time
        self._lock = threading.Lock()

    def save(
        self,
        user_id: str,
        conversation_id: str,
        text: str,
        *,
        reply_to_message_id: str = "",
    ) -> tuple[DraftRecord, bool]:
        """Returns (record, cleared). When `text` is empty after stripping,
        we auto-clear the draft and return `cleared=True`. The returned
        record reflects the post-state — for cleared drafts it carries the
        empty text but the conversation_id field stays so the client can
        diff against its local cache."""
        if not conversation_id:
            raise ServiceError(ErrorCode.UNKNOWN_CONVERSATION)
        if conversation_id not in self._state.conversations:
            raise ServiceError(ErrorCode.UNKNOWN_CONVERSATION)
        # Author must be a participant — drafts for conversations you can't
        # read are pointless and would leak conversation existence.
        conv = self._state.conversations[conversation_id]
        if user_id not in conv.participant_user_ids:
            raise ServiceError(ErrorCode.CONVERSATION_ACCESS_DENIED)

        now_ms = int(self._clock() * 1000)
        key = (user_id, conversation_id)
        with self._lock:
            if not text or not text.strip():
                self._state.drafts.pop(key, None)
                self._state.save_runtime_state()
                return DraftRecord(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    text="",
                    reply_to_message_id="",
                    updated_at_ms=now_ms,
                ), True
            record = DraftRecord(
                user_id=user_id,
                conversation_id=conversation_id,
                text=text,
                reply_to_message_id=reply_to_message_id,
                updated_at_ms=now_ms,
            )
            self._state.drafts[key] = record
        self._state.save_runtime_state()
        return record, False

    def clear(self, user_id: str, conversation_id: str) -> bool:
        with self._lock:
            removed = self._state.drafts.pop((user_id, conversation_id), None) is not None
        if removed:
            self._state.save_runtime_state()
        return removed

    def list_for_user(self, user_id: str) -> list[DraftRecord]:
        return [
            r for (uid, _cid), r in self._state.drafts.items()
            if uid == user_id
        ]

    def describe(self) -> str:
        return f"drafts service tracks {len(self._state.drafts)} drafts"
