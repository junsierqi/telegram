"""Account lifecycle service (M95) — GDPR-style export + delete.

Two RPC entry points (post-authenticated only):

  ACCOUNT_EXPORT_REQUEST  -> dict snapshot of everything the server keeps
                              about the user. Read-only.
  ACCOUNT_DELETE_REQUEST  -> verify password + (optional) TOTP, then scrub
                              the user, sessions, devices, push tokens,
                              and replace authored messages with a
                              "Deleted Account" tombstone (Telegram
                              behavior: messages stay so other peers
                              keep their conversation history).

Returned counts are useful for client UX ("we removed N messages"). The
worst-case mutation surface is bounded by the user's own footprint, so
this runs in O(N) over the user's data.
"""
from __future__ import annotations

import time
from dataclasses import asdict
from typing import Callable, Optional

from ..crypto import verify_password
from ..protocol import ErrorCode, ServiceError
from ..state import InMemoryState
from .two_fa import TwoFAService, verify_totp


TOMBSTONE_USER_ID = "u_deleted"
TOMBSTONE_DISPLAY = "Deleted Account"


class AccountLifecycleService:
    def __init__(
        self,
        state: InMemoryState,
        *,
        clock: Callable[[], float] | None = None,
        two_fa_service: Optional[TwoFAService] = None,
    ) -> None:
        self._state = state
        self._clock = clock or time.time
        # Optional dependency on TwoFAService so account delete can flush
        # any pending 2FA enrollment that never confirmed (M97 leak fix).
        # Optional because legacy tests construct the service standalone.
        self._two_fa = two_fa_service

    # ---- export ----

    def export(self, user_id: str) -> dict:
        user = self._state.users.get(user_id)
        if user is None:
            raise ServiceError(ErrorCode.UNKNOWN_USER)
        profile = {
            "user_id": user.user_id,
            "username": user.username,
            "display_name": user.display_name,
            "two_fa_enabled": bool(user.two_fa_secret),
        }
        devices = [
            asdict(d) for d in self._state.devices.values() if d.user_id == user_id
        ]
        sessions = [
            {
                "session_id": s.session_id,
                "device_id": s.device_id,
                "last_seen_at": s.last_seen_at,
            }
            for s in self._state.sessions.values()
            if s.user_id == user_id
        ]
        contacts_for_me = list(self._state.contacts.get(user_id, []))
        # also list users who have me as a contact (read-only — we don't
        # leak who, just that there are inbound references)
        push_tokens = [
            asdict(t) for t in self._state.push_tokens if t.user_id == user_id
        ]
        authored_messages: list[dict] = []
        for conv in self._state.conversations.values():
            for msg in conv.messages:
                if msg.get("sender_user_id") == user_id:
                    authored_messages.append({
                        "conversation_id": conv.conversation_id,
                        "message_id": msg.get("message_id"),
                        "text": msg.get("text", ""),
                        "created_at_ms": msg.get("created_at_ms"),
                        "attachment_id": msg.get("attachment_id", ""),
                    })
        return {
            "exported_at_ms": int(self._clock() * 1000),
            "user_id": user_id,
            "profile": profile,
            "devices": devices,
            "sessions": sessions,
            "contacts": [{"target_user_id": cid} for cid in contacts_for_me],
            "push_tokens": push_tokens,
            "authored_messages": authored_messages,
        }

    # ---- delete ----

    def delete(self, user_id: str, *, password: str, two_fa_code: str = "") -> dict:
        user = self._state.users.get(user_id)
        if user is None:
            raise ServiceError(ErrorCode.UNKNOWN_USER)
        # Confirm password (constant-time via verify_password's hmac.compare_digest).
        if not password or not verify_password(password, user.password_hash):
            raise ServiceError(ErrorCode.ACCOUNT_DELETE_AUTH_FAILED)
        if user.two_fa_secret:
            if not two_fa_code or not verify_totp(user.two_fa_secret, two_fa_code,
                                                  at=self._clock()):
                raise ServiceError(ErrorCode.ACCOUNT_DELETE_AUTH_FAILED)

        sessions_revoked = 0
        for sid in list(self._state.sessions):
            if self._state.sessions[sid].user_id == user_id:
                del self._state.sessions[sid]
                sessions_revoked += 1

        devices_removed = 0
        for did in list(self._state.devices):
            if self._state.devices[did].user_id == user_id:
                del self._state.devices[did]
                devices_removed += 1

        push_tokens_removed_before = len(self._state.push_tokens)
        self._state.push_tokens = [
            t for t in self._state.push_tokens if t.user_id != user_id
        ]
        push_tokens_removed = push_tokens_removed_before - len(self._state.push_tokens)

        # Contacts: remove user_id as owner, and remove user_id from
        # everyone else's lists too so they don't reference a dead user.
        contacts_removed = 0
        if user_id in self._state.contacts:
            contacts_removed += len(self._state.contacts.pop(user_id, []))
        for owner_id, target_list in self._state.contacts.items():
            new_list = [t for t in target_list if t != user_id]
            if len(new_list) != len(target_list):
                contacts_removed += len(target_list) - len(new_list)
                self._state.contacts[owner_id] = new_list

        # Messages: tombstone authorship instead of deleting. This matches
        # Telegram's behavior (other peers keep their conversation history;
        # the deleted account just shows up as "Deleted Account").
        messages_tombstoned = 0
        for conv in self._state.conversations.values():
            # Replace participant references too — the deleted user shouldn't
            # remain in the participant list.
            if user_id in conv.participant_user_ids:
                conv.participant_user_ids = [
                    p for p in conv.participant_user_ids if p != user_id
                ]
            for msg in conv.messages:
                if msg.get("sender_user_id") == user_id:
                    msg["sender_user_id"] = TOMBSTONE_USER_ID
                    msg["text"] = ""
                    msg["deleted"] = True
                    messages_tombstoned += 1

        # Drop any in-flight 2FA enrollment for this user_id so the
        # secret doesn't dangle in TwoFAService._pending forever.
        if self._two_fa is not None:
            self._two_fa.discard_pending_enrollment(user_id)

        # Finally drop the user record itself.
        self._state.users.pop(user_id, None)
        self._state.save_runtime_state()

        return {
            "user_id": user_id,
            "sessions_revoked": sessions_revoked,
            "devices_removed": devices_removed,
            "push_tokens_removed": push_tokens_removed,
            "messages_tombstoned": messages_tombstoned,
            "contacts_removed": contacts_removed,
        }

    def describe(self) -> str:
        return "account lifecycle service — GDPR-style export + tombstoning delete"
