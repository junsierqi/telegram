"""Per-user pinned + archived conversation flags (M100).

These flags are *per-user preferences*, not properties of the
conversation. Pinning conv_alice_bob from bob's account doesn't change
how alice sees that same conversation. Pinned ordering on the client is
the client's job — the server just persists which ids the user has
pinned/archived.

Both flags are independent: a chat can be pinned-and-archived, or
either, or neither. Telegram's UI hides archived chats by default but
still lists them in a separate "Archived" folder; mirroring that is the
client's choice.
"""
from __future__ import annotations

import threading
from typing import Callable

from ..protocol import ErrorCode, ServiceError
from ..state import InMemoryState


class ConversationFlagsService:
    def __init__(self, state: InMemoryState) -> None:
        self._state = state
        self._lock = threading.Lock()

    # ---- pinned ------------------------------------------------------

    def set_pinned(self, user_id: str, conversation_id: str, pinned: bool) -> bool:
        """Returns the post-state pinned bool. Raises UNKNOWN_CONVERSATION
        for ids that don't exist; raises CONVERSATION_ACCESS_DENIED if
        the user isn't a participant — pinning a conversation you can't
        read is meaningless and would leak existence."""
        self._guard(user_id, conversation_id)
        with self._lock:
            bag = self._state.pinned_conversations.setdefault(user_id, set())
            if pinned:
                bag.add(conversation_id)
            else:
                bag.discard(conversation_id)
                # Drop empty buckets so JSON snapshot stays compact.
                if not bag:
                    self._state.pinned_conversations.pop(user_id, None)
        self._state.save_runtime_state()
        return pinned

    def is_pinned(self, user_id: str, conversation_id: str) -> bool:
        return conversation_id in self._state.pinned_conversations.get(user_id, set())

    def list_pinned(self, user_id: str) -> set[str]:
        return set(self._state.pinned_conversations.get(user_id, set()))

    # ---- archived ----------------------------------------------------

    def set_archived(self, user_id: str, conversation_id: str, archived: bool) -> bool:
        self._guard(user_id, conversation_id)
        with self._lock:
            bag = self._state.archived_conversations.setdefault(user_id, set())
            if archived:
                bag.add(conversation_id)
            else:
                bag.discard(conversation_id)
                if not bag:
                    self._state.archived_conversations.pop(user_id, None)
        self._state.save_runtime_state()
        return archived

    def is_archived(self, user_id: str, conversation_id: str) -> bool:
        return conversation_id in self._state.archived_conversations.get(user_id, set())

    def list_archived(self, user_id: str) -> set[str]:
        return set(self._state.archived_conversations.get(user_id, set()))

    # ---- helpers -----------------------------------------------------

    def _guard(self, user_id: str, conversation_id: str) -> None:
        if not conversation_id or conversation_id not in self._state.conversations:
            raise ServiceError(ErrorCode.UNKNOWN_CONVERSATION)
        conv = self._state.conversations[conversation_id]
        if user_id not in conv.participant_user_ids:
            raise ServiceError(ErrorCode.CONVERSATION_ACCESS_DENIED)

    def describe(self) -> str:
        pinned = sum(len(s) for s in self._state.pinned_conversations.values())
        archived = sum(len(s) for s in self._state.archived_conversations.values())
        return f"conversation flags service ({pinned} pinned, {archived} archived)"
