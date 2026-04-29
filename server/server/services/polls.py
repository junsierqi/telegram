"""Polls service (M102).

Polls are stored as a special variant of message inside a conversation's
`messages` list — same routing, paging, and history retention as any
other message. The poll-specific state lives in the message dict under
the `poll` key:

    {
      "message_id": "msg_poll_<n>",
      "sender_user_id": "u_alice",
      "text": "<question>",
      "created_at_ms": ...,
      "poll": {
          "options": ["yes", "no"],
          "multiple_choice": False,
          "closed": False,
          "votes": {"u_bob": [0]},   # user_id -> list of option indices
      }
    }

Tallies are computed from `votes` on each request; we don't double-store
them. Voters can change their vote by sending a fresh POLL_VOTE; the
service overwrites their entry. Multi-choice polls accept any number of
distinct indices per request; single-choice polls require exactly one.
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Callable

from ..protocol import ErrorCode, ServiceError
from ..state import InMemoryState


class PollsService:
    def __init__(
        self,
        state: InMemoryState,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._state = state
        self._clock = clock or time.time
        self._lock = threading.Lock()

    # ---- create ------------------------------------------------------

    def create(
        self,
        *,
        conversation_id: str,
        sender_user_id: str,
        question: str,
        options: list[str],
        multiple_choice: bool,
    ) -> dict:
        if conversation_id not in self._state.conversations:
            raise ServiceError(ErrorCode.UNKNOWN_CONVERSATION)
        conv = self._state.conversations[conversation_id]
        if sender_user_id not in conv.participant_user_ids:
            raise ServiceError(ErrorCode.CONVERSATION_ACCESS_DENIED)
        question = question.strip()
        if not question:
            raise ServiceError(ErrorCode.EMPTY_MESSAGE)
        cleaned_options = [o.strip() for o in options if isinstance(o, str) and o.strip()]
        if len(cleaned_options) < 2:
            raise ServiceError(ErrorCode.POLL_TOO_FEW_OPTIONS)

        message_id = f"msg_poll_{uuid.uuid4().hex[:12]}"
        now_ms = int(self._clock() * 1000)
        record = {
            "message_id": message_id,
            "sender_user_id": sender_user_id,
            "text": question,
            "created_at_ms": now_ms,
            "poll": {
                "options": cleaned_options,
                "multiple_choice": multiple_choice,
                "closed": False,
                "votes": {},
            },
        }
        with self._lock:
            conv.messages.append(record)
        self._state.save_runtime_state()
        return record

    # ---- vote --------------------------------------------------------

    def vote(
        self,
        *,
        conversation_id: str,
        message_id: str,
        voter_user_id: str,
        option_indices: list[int],
    ) -> dict:
        msg, conv = self._lookup_poll(conversation_id, message_id, voter_user_id)
        poll = msg["poll"]
        if poll["closed"]:
            raise ServiceError(ErrorCode.POLL_CLOSED)
        # Normalize: dedupe + sort. Single-choice polls collapse to the
        # first index but reject extra picks so the client can flag UX
        # bugs early instead of silently truncating.
        unique = sorted(set(int(i) for i in option_indices))
        if not unique:
            raise ServiceError(ErrorCode.POLL_INVALID_OPTION)
        opt_count = len(poll["options"])
        if any(i < 0 or i >= opt_count for i in unique):
            raise ServiceError(ErrorCode.POLL_INVALID_OPTION)
        if not poll["multiple_choice"] and len(unique) != 1:
            raise ServiceError(ErrorCode.POLL_INVALID_OPTION)
        with self._lock:
            poll["votes"][voter_user_id] = unique
        self._state.save_runtime_state()
        return msg

    # ---- close -------------------------------------------------------

    def close(
        self,
        *,
        conversation_id: str,
        message_id: str,
        actor_user_id: str,
    ) -> dict:
        msg, _conv = self._lookup_poll(conversation_id, message_id, actor_user_id)
        if msg["sender_user_id"] != actor_user_id:
            raise ServiceError(ErrorCode.POLL_CLOSE_DENIED)
        with self._lock:
            msg["poll"]["closed"] = True
        self._state.save_runtime_state()
        return msg

    # ---- helpers -----------------------------------------------------

    def _lookup_poll(
        self, conversation_id: str, message_id: str, actor_user_id: str,
    ) -> tuple[dict, "object"]:
        if conversation_id not in self._state.conversations:
            raise ServiceError(ErrorCode.UNKNOWN_CONVERSATION)
        conv = self._state.conversations[conversation_id]
        if actor_user_id not in conv.participant_user_ids:
            raise ServiceError(ErrorCode.CONVERSATION_ACCESS_DENIED)
        for m in conv.messages:
            if m.get("message_id") == message_id:
                if not isinstance(m.get("poll"), dict):
                    raise ServiceError(ErrorCode.NOT_A_POLL)
                return m, conv
        raise ServiceError(ErrorCode.UNKNOWN_MESSAGE)

    @staticmethod
    def descriptor_from_message(message: dict) -> dict | None:
        """Build the wire-shape PollDescriptor (as a dict) for clients.
        Returns None for non-poll messages so MessageDescriptor can leave
        the field as None."""
        poll = message.get("poll")
        if not isinstance(poll, dict):
            return None
        votes: dict[str, list[int]] = poll.get("votes", {})  # type: ignore[assignment]
        tallies = [0] * len(poll.get("options", []))
        for picks in votes.values():
            for idx in picks:
                if 0 <= idx < len(tallies):
                    tallies[idx] += 1
        return {
            "options": [
                {"text": text, "vote_count": tallies[i]}
                for i, text in enumerate(poll.get("options", []))
            ],
            "multiple_choice": bool(poll.get("multiple_choice", False)),
            "closed": bool(poll.get("closed", False)),
            "total_voters": len(votes),
        }

    def describe(self) -> str:
        n = sum(
            1
            for c in self._state.conversations.values()
            for m in c.messages
            if isinstance(m.get("poll"), dict)
        )
        return f"polls service tracks {n} polls across conversations"
