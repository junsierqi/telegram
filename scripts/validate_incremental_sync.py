"""Validator for C6 conversation_sync cursors and durable deltas."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402
from server.server.services.chat import MAX_CONVERSATION_CHANGES  # noqa: E402


def login(app: ServerApplication, username: str, password: str, device_id: str, seq: int) -> dict:
    response = app.dispatch(
        {
            **make_envelope(MessageType.LOGIN_REQUEST, correlation_id=f"login_{seq}", sequence=seq),
            "payload": {
                "username": username,
                "password": password,
                "device_id": device_id,
            },
        }
    )
    assert response["type"] == MessageType.LOGIN_RESPONSE.value, response
    return response


def send_message(app: ServerApplication, session: dict, text: str, seq: int) -> dict:
    response = app.dispatch(
        {
            **make_envelope(
                MessageType.MESSAGE_SEND,
                correlation_id=f"send_{seq}",
                session_id=session["payload"]["session_id"],
                actor_user_id=session["payload"]["user_id"],
                sequence=seq,
            ),
            "payload": {
                "conversation_id": "conv_alice_bob",
                "text": text,
            },
        }
    )
    assert response["type"] == MessageType.MESSAGE_DELIVER.value, response
    return response


def sync(app: ServerApplication, session: dict, cursors: dict[str, str] | None, seq: int) -> dict:
    payload = {} if cursors is None else {"cursors": cursors}
    return sync_with_versions(app, session, payload, seq)


def sync_with_versions(app: ServerApplication, session: dict, payload: dict, seq: int) -> dict:
    response = app.dispatch(
        {
            **make_envelope(
                MessageType.CONVERSATION_SYNC,
                correlation_id=f"sync_{seq}",
                session_id=session["payload"]["session_id"],
                actor_user_id=session["payload"]["user_id"],
                sequence=seq,
            ),
            "payload": payload,
        }
    )
    assert response["type"] == MessageType.CONVERSATION_SYNC.value, response
    return response


def messages_for(response: dict, conversation_id: str) -> list[dict]:
    for conversation in response["payload"]["conversations"]:
        if conversation["conversation_id"] == conversation_id:
            return conversation["messages"]
    return []


def conversation_for(response: dict, conversation_id: str) -> dict:
    for conversation in response["payload"]["conversations"]:
        if conversation["conversation_id"] == conversation_id:
            return conversation
    return {}


def edit_message(app: ServerApplication, session: dict, message_id: str, text: str, seq: int) -> dict:
    response = app.dispatch(
        {
            **make_envelope(
                MessageType.MESSAGE_EDIT,
                correlation_id=f"edit_{seq}",
                session_id=session["payload"]["session_id"],
                actor_user_id=session["payload"]["user_id"],
                sequence=seq,
            ),
            "payload": {
                "conversation_id": "conv_alice_bob",
                "message_id": message_id,
                "text": text,
            },
        }
    )
    assert response["type"] == MessageType.MESSAGE_EDITED.value, response
    return response


def delete_message(app: ServerApplication, session: dict, message_id: str, seq: int) -> dict:
    response = app.dispatch(
        {
            **make_envelope(
                MessageType.MESSAGE_DELETE,
                correlation_id=f"delete_{seq}",
                session_id=session["payload"]["session_id"],
                actor_user_id=session["payload"]["user_id"],
                sequence=seq,
            ),
            "payload": {
                "conversation_id": "conv_alice_bob",
                "message_id": message_id,
            },
        }
    )
    assert response["type"] == MessageType.MESSAGE_DELETED.value, response
    return response


def mark_read(app: ServerApplication, session: dict, message_id: str, seq: int) -> dict:
    response = app.dispatch(
        {
            **make_envelope(
                MessageType.MESSAGE_READ,
                correlation_id=f"read_{seq}",
                session_id=session["payload"]["session_id"],
                actor_user_id=session["payload"]["user_id"],
                sequence=seq,
            ),
            "payload": {
                "conversation_id": "conv_alice_bob",
                "message_id": message_id,
            },
        }
    )
    assert response["type"] == MessageType.MESSAGE_READ_UPDATE.value, response
    return response


def register(app: ServerApplication, username: str, user_id_hint: str, device_id: str, seq: int) -> dict:
    response = app.dispatch(
        {
            **make_envelope(MessageType.REGISTER_REQUEST, correlation_id=f"reg_{seq}", sequence=seq),
            "payload": {
                "username": username,
                "password": f"{username}_pw_ok",
                "display_name": user_id_hint,
                "device_id": device_id,
            },
        }
    )
    assert response["type"] == MessageType.REGISTER_RESPONSE.value, response
    return response


def add_participant(app: ServerApplication, session: dict, user_id: str, seq: int) -> dict:
    response = app.dispatch(
        {
            **make_envelope(
                MessageType.CONVERSATION_ADD_PARTICIPANT,
                correlation_id=f"add_{seq}",
                session_id=session["payload"]["session_id"],
                actor_user_id=session["payload"]["user_id"],
                sequence=seq,
            ),
            "payload": {
                "conversation_id": "conv_alice_bob",
                "user_id": user_id,
            },
        }
    )
    assert response["type"] == MessageType.CONVERSATION_UPDATED.value, response
    return response


def remove_participant(app: ServerApplication, session: dict, user_id: str, seq: int) -> dict:
    response = app.dispatch(
        {
            **make_envelope(
                MessageType.CONVERSATION_REMOVE_PARTICIPANT,
                correlation_id=f"remove_{seq}",
                session_id=session["payload"]["session_id"],
                actor_user_id=session["payload"]["user_id"],
                sequence=seq,
            ),
            "payload": {
                "conversation_id": "conv_alice_bob",
                "user_id": user_id,
            },
        }
    )
    assert response["type"] == MessageType.CONVERSATION_UPDATED.value, response
    return response


def test_cursor_returns_only_new_messages() -> None:
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    full = sync(app, alice, None, 2)
    seed_messages = messages_for(full, "conv_alice_bob")
    assert seed_messages, full
    cursor = seed_messages[-1]["message_id"]

    first = send_message(app, alice, "after cursor 1", 3)
    second = send_message(app, alice, "after cursor 2", 4)
    delta = sync(app, alice, {"conv_alice_bob": cursor}, 5)
    ids = [m["message_id"] for m in messages_for(delta, "conv_alice_bob")]
    assert ids == [first["payload"]["message_id"], second["payload"]["message_id"]], ids


def test_no_changes_returns_no_conversations() -> None:
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    full = sync(app, alice, None, 2)
    cursor = messages_for(full, "conv_alice_bob")[-1]["message_id"]
    delta = sync(app, alice, {"conv_alice_bob": cursor}, 3)
    assert delta["payload"]["conversations"] == [], delta


def test_unknown_cursor_falls_back_to_full_conversation() -> None:
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    delta = sync(app, alice, {"conv_alice_bob": "msg_missing"}, 2)
    messages = messages_for(delta, "conv_alice_bob")
    assert messages and messages[0]["message_id"] == "msg_1", delta


def test_new_conversations_are_included_without_cursor() -> None:
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    bob = login(app, "bob", "bob_pw", "dev_bob_win", 2)
    full = sync(app, alice, None, 3)
    cursor = messages_for(full, "conv_alice_bob")[-1]["message_id"]
    create = app.dispatch(
        {
            **make_envelope(
                MessageType.CONVERSATION_CREATE,
                correlation_id="create_4",
                session_id=alice["payload"]["session_id"],
                actor_user_id=alice["payload"]["user_id"],
                sequence=4,
            ),
            "payload": {
                "participant_user_ids": [bob["payload"]["user_id"]],
                "title": "New thread",
            },
        }
    )
    assert create["type"] == MessageType.CONVERSATION_UPDATED.value, create
    delta = sync(app, alice, {"conv_alice_bob": cursor}, 5)
    conversation_ids = [c["conversation_id"] for c in delta["payload"]["conversations"]]
    assert create["payload"]["conversation_id"] in conversation_ids, delta


def test_edit_delete_and_read_marker_return_as_deltas() -> None:
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    full = sync(app, alice, None, 2)
    conversation = conversation_for(full, "conv_alice_bob")
    cursor = conversation["messages"][-1]["message_id"]
    version = int(conversation.get("version", 0))

    sent = send_message(app, alice, "delta target", 3)
    cursor = sent["payload"]["message_id"]
    after_append = sync_with_versions(
        app,
        alice,
        {"cursors": {"conv_alice_bob": cursor}, "versions": {"conv_alice_bob": version}},
        4,
    )
    version = int(conversation_for(after_append, "conv_alice_bob").get("version", version))

    edit_message(app, alice, cursor, "delta edited", 5)
    mark_read(app, alice, cursor, 6)
    delete_message(app, alice, cursor, 7)
    delta = sync_with_versions(
        app,
        alice,
        {"cursors": {"conv_alice_bob": cursor}, "versions": {"conv_alice_bob": version}},
        8,
    )
    changed = conversation_for(delta, "conv_alice_bob")
    assert changed["messages"] == [], changed
    kinds = [change["kind"] for change in changed["changes"]]
    assert kinds == ["message_edited", "read_marker", "message_deleted"], changed
    assert changed["changes"][0]["text"] == "delta edited", changed
    assert changed["changes"][1]["last_read_message_id"] == cursor, changed


def test_delta_log_persists_json_and_sqlite() -> None:
    for mode in ("json", "sqlite"):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ("runtime.json" if mode == "json" else "runtime.sqlite")
            kwargs = {"state_file": str(path)} if mode == "json" else {"db_file": str(path)}
            app = ServerApplication(**kwargs)
            alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
            full = sync(app, alice, None, 2)
            conversation = conversation_for(full, "conv_alice_bob")
            cursor = conversation["messages"][-1]["message_id"]
            version = int(conversation.get("version", 0))
            edit_message(app, alice, cursor, f"persisted delta {mode}", 3)

            app2 = ServerApplication(**kwargs)
            alice2 = login(app2, "alice", "alice_pw", "dev_alice_win", 4)
            delta = sync_with_versions(
                app2,
                alice2,
                {"cursors": {"conv_alice_bob": cursor}, "versions": {"conv_alice_bob": version}},
                5,
            )
            changed = conversation_for(delta, "conv_alice_bob")
            assert changed["changes"][0]["text"] == f"persisted delta {mode}", changed


def test_membership_changes_return_as_metadata_deltas() -> None:
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    carol = register(app, "carol", "Carol", "dev_carol_mac", 2)
    full = sync(app, alice, None, 3)
    conversation = conversation_for(full, "conv_alice_bob")
    cursor = conversation["messages"][-1]["message_id"]
    version = int(conversation.get("version", 0))

    add_participant(app, alice, carol["payload"]["user_id"], 4)
    delta = sync_with_versions(
        app,
        alice,
        {"cursors": {"conv_alice_bob": cursor}, "versions": {"conv_alice_bob": version}},
        5,
    )
    changed = conversation_for(delta, "conv_alice_bob")
    assert changed["messages"] == [], changed
    assert changed["changes"][0]["kind"] == "conversation_updated", changed
    assert carol["payload"]["user_id"] in changed["participant_user_ids"], changed
    version = int(changed["version"])

    remove_participant(app, alice, carol["payload"]["user_id"], 6)
    delta = sync_with_versions(
        app,
        alice,
        {"cursors": {"conv_alice_bob": cursor}, "versions": {"conv_alice_bob": version}},
        7,
    )
    changed = conversation_for(delta, "conv_alice_bob")
    assert changed["changes"][0]["kind"] == "conversation_updated", changed
    assert carol["payload"]["user_id"] not in changed["participant_user_ids"], changed


def test_compacted_change_log_falls_back_to_full_conversation() -> None:
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    carol = register(app, "carol", "Carol", "dev_carol_mac", 2)
    full = sync(app, alice, None, 3)
    cursor = messages_for(full, "conv_alice_bob")[-1]["message_id"]

    seq = 4
    for _ in range((MAX_CONVERSATION_CHANGES // 2) + 2):
        add_participant(app, alice, carol["payload"]["user_id"], seq)
        seq += 1
        remove_participant(app, alice, carol["payload"]["user_id"], seq)
        seq += 1
    record = app.state.conversations["conv_alice_bob"]
    assert len(record.changes) == MAX_CONVERSATION_CHANGES, len(record.changes)
    assert int(record.changes[0]["version"]) > 1, record.changes[0]

    delta = sync_with_versions(
        app,
        alice,
        {"cursors": {"conv_alice_bob": cursor}, "versions": {"conv_alice_bob": 0}},
        seq,
    )
    changed = conversation_for(delta, "conv_alice_bob")
    assert messages_for(delta, "conv_alice_bob")[0]["message_id"] == "msg_1", changed


SCENARIOS = [
    ("cursor_returns_only_new_messages", test_cursor_returns_only_new_messages),
    ("no_changes_returns_no_conversations", test_no_changes_returns_no_conversations),
    ("unknown_cursor_falls_back_to_full_conversation", test_unknown_cursor_falls_back_to_full_conversation),
    ("new_conversations_are_included_without_cursor", test_new_conversations_are_included_without_cursor),
    ("edit_delete_and_read_marker_return_as_deltas", test_edit_delete_and_read_marker_return_as_deltas),
    ("delta_log_persists_json_and_sqlite", test_delta_log_persists_json_and_sqlite),
    ("membership_changes_return_as_metadata_deltas", test_membership_changes_return_as_metadata_deltas),
    ("compacted_change_log_falls_back_to_full_conversation", test_compacted_change_log_falls_back_to_full_conversation),
]


def main() -> int:
    passed = 0
    for name, fn in SCENARIOS:
        try:
            fn()
            print(f"[ok ] {name}")
            passed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[FAIL] {name}: {exc}")
    print(f"passed {passed}/{len(SCENARIOS)}")
    return 0 if passed == len(SCENARIOS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
