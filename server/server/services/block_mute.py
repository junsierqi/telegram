"""Block-user list + per-conversation mute (M98).

Two related but independent surfaces:

  * Block list: A blocks B prevents B's MESSAGE_SEND from delivering when
    the conversation is a 1:1 between exactly the two of them. Group
    membership is not affected — Telegram itself doesn't quietly drop
    blocked users from groups, it leaves moderation to admins.

  * Per-conversation mute: a flag the client uses to suppress local
    notifications. Server stores it + exposes via conversation_sync; we
    don't filter pushes on the server because the muted user still wants
    badge counts and history.

Both states are in-memory only for now (matching push_tokens). Persistence
to SQLite/Postgres follows the same pattern when the rest of the per-user
state moves to durable storage.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from ..protocol import ErrorCode, ServiceError
from ..state import BlockedUserEntry, ConversationMuteEntry, InMemoryState


class BlockMuteService:
    def __init__(
        self,
        state: InMemoryState,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._state = state
        self._clock = clock or time.time
        self._lock = threading.Lock()

    # ---- block ----

    def block(self, blocker_user_id: str, target_user_id: str) -> None:
        if not target_user_id or target_user_id == blocker_user_id:
            raise ServiceError(ErrorCode.CONTACT_SELF_NOT_ALLOWED)
        if target_user_id not in self._state.users:
            raise ServiceError(ErrorCode.UNKNOWN_USER)
        now_ms = int(self._clock() * 1000)
        with self._lock:
            entries = self._state.blocked_users.setdefault(blocker_user_id, [])
            for e in entries:
                if e.target_user_id == target_user_id:
                    raise ServiceError(ErrorCode.ALREADY_BLOCKED)
            entries.append(BlockedUserEntry(
                target_user_id=target_user_id,
                blocked_at_ms=now_ms,
            ))
        self._state.save_runtime_state()

    def unblock(self, blocker_user_id: str, target_user_id: str) -> None:
        with self._lock:
            entries = self._state.blocked_users.get(blocker_user_id, [])
            new_entries = [e for e in entries if e.target_user_id != target_user_id]
            if len(new_entries) == len(entries):
                raise ServiceError(ErrorCode.NOT_BLOCKED)
            self._state.blocked_users[blocker_user_id] = new_entries
        self._state.save_runtime_state()

    def list_blocked(self, blocker_user_id: str) -> list[BlockedUserEntry]:
        return list(self._state.blocked_users.get(blocker_user_id, []))

    def is_blocked_by(self, blocker_user_id: str, candidate_target: str) -> bool:
        """Returns True if blocker_user_id has put candidate_target on their
        block list. Used by the chat send path to refuse messages from a
        sender the recipient blocked.
        """
        entries = self._state.blocked_users.get(blocker_user_id, [])
        return any(e.target_user_id == candidate_target for e in entries)

    # ---- mute ----

    def set_mute(
        self, user_id: str, conversation_id: str, muted_until_ms: int,
    ) -> int:
        """muted_until_ms semantics:
            0  -> not muted (delete the entry)
           -1  -> muted forever
            N  -> muted until ms-epoch N (clipped to >= now if in past)
        Returns the persisted muted_until_ms.
        """
        if not conversation_id:
            raise ServiceError(ErrorCode.UNKNOWN_CONVERSATION)
        if conversation_id not in self._state.conversations:
            raise ServiceError(ErrorCode.UNKNOWN_CONVERSATION)
        with self._lock:
            key = (user_id, conversation_id)
            if muted_until_ms == 0:
                self._state.conversation_mutes.pop(key, None)
                stored = 0
            else:
                stored = muted_until_ms
                self._state.conversation_mutes[key] = ConversationMuteEntry(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    muted_until_ms=stored,
                )
        self._state.save_runtime_state()
        return stored

    def get_mute(self, user_id: str, conversation_id: str) -> int:
        entry = self._state.conversation_mutes.get((user_id, conversation_id))
        if entry is None:
            return 0
        # Auto-clear if expiry already passed (client sees 0 = not muted).
        if entry.muted_until_ms > 0 and entry.muted_until_ms < int(self._clock() * 1000):
            with self._lock:
                self._state.conversation_mutes.pop((user_id, conversation_id), None)
            return 0
        return entry.muted_until_ms

    def describe(self) -> str:
        return (
            f"block + mute service — "
            f"{sum(len(v) for v in self._state.blocked_users.values())} blocks, "
            f"{len(self._state.conversation_mutes)} active mutes"
        )
