from __future__ import annotations

from ..protocol import ContactDescriptor, ErrorCode, ServiceError
from ..state import InMemoryState
from .presence import PresenceService


class ContactsService:
    def __init__(self, state: InMemoryState, presence: PresenceService) -> None:
        self._state = state
        self._presence = presence

    def describe(self) -> str:
        return "contacts service ready for directed contact lists"

    def add(self, *, owner_user_id: str, target_user_id: str) -> list[ContactDescriptor]:
        if owner_user_id == target_user_id:
            raise ServiceError(ErrorCode.CONTACT_SELF_NOT_ALLOWED)
        if target_user_id not in self._state.users:
            raise ServiceError(ErrorCode.UNKNOWN_USER)
        owned = self._state.contacts.setdefault(owner_user_id, [])
        if target_user_id in owned:
            raise ServiceError(ErrorCode.CONTACT_ALREADY_ADDED)
        owned.append(target_user_id)
        self._state.save_runtime_state()
        return self.list(owner_user_id)

    def remove(self, *, owner_user_id: str, target_user_id: str) -> list[ContactDescriptor]:
        owned = self._state.contacts.get(owner_user_id, [])
        if target_user_id not in owned:
            raise ServiceError(ErrorCode.CONTACT_NOT_PRESENT)
        owned.remove(target_user_id)
        self._state.contact_aliases.get(owner_user_id, {}).pop(target_user_id, None)
        self._state.save_runtime_state()
        return self.list(owner_user_id)

    def edit(
        self, *, owner_user_id: str, target_user_id: str, display_name: str
    ) -> list[ContactDescriptor]:
        owned = self._state.contacts.get(owner_user_id, [])
        if target_user_id not in owned:
            raise ServiceError(ErrorCode.CONTACT_NOT_PRESENT)
        display_name = display_name.strip()
        if not display_name:
            raise ServiceError(ErrorCode.INVALID_REGISTRATION_PAYLOAD)
        if len(display_name) > 64:
            raise ServiceError(ErrorCode.INVALID_REGISTRATION_PAYLOAD)
        self._state.contact_aliases.setdefault(owner_user_id, {})[target_user_id] = display_name
        self._state.save_runtime_state()
        return self.list(owner_user_id)

    def share(self, *, owner_user_id: str, target_user_id: str) -> tuple[str, str, str]:
        if target_user_id not in self._state.contacts.get(owner_user_id, []):
            raise ServiceError(ErrorCode.CONTACT_NOT_PRESENT)
        user = self._state.users.get(target_user_id)
        if user is None:
            raise ServiceError(ErrorCode.UNKNOWN_USER)
        alias = self._state.contact_aliases.get(owner_user_id, {}).get(target_user_id)
        display_name = alias or user.display_name
        username = user.username
        share_text = f"{display_name} (@{username})"
        return display_name, username, share_text

    def list(self, owner_user_id: str) -> list[ContactDescriptor]:
        descriptors: list[ContactDescriptor] = []
        aliases = self._state.contact_aliases.get(owner_user_id, {})
        for target_user_id in self._state.contacts.get(owner_user_id, []):
            user = self._state.users.get(target_user_id)
            if user is None:
                continue
            descriptors.append(
                ContactDescriptor(
                    user_id=target_user_id,
                    display_name=aliases.get(target_user_id, user.display_name),
                    online=self._presence.is_user_online(target_user_id),
                )
            )
        return descriptors
