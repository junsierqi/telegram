"""Validator for the first PostgreSQL repository-backed persistence slice."""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402
from server.server.repositories import POSTGRES_SCHEMA_VERSION, PostgresStateRepository  # noqa: E402


DSN = os.getenv(
    "TELEGRAM_TEST_PG_DSN",
    "postgresql://telegram:telegram_dev_password@127.0.0.1:5432/telegram",
)


def dispatch_register(app: ServerApplication, username: str, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(MessageType.REGISTER_REQUEST, correlation_id=f"reg_{seq}", sequence=seq),
            "payload": {
                "username": username,
                "password": "pg_repo_pw_123",
                "display_name": "Postgres Repo",
                "device_id": f"dev_{username}",
                "device_label": "Postgres Test Device",
                "platform": "linux",
            },
        }
    )


def login(
    app: ServerApplication,
    username: str,
    seq: int,
    password: str = "pg_repo_pw_123",
    device_id: str | None = None,
) -> dict:
    return app.dispatch(
        {
            **make_envelope(MessageType.LOGIN_REQUEST, correlation_id=f"login_{seq}", sequence=seq),
            "payload": {
                "username": username,
                "password": password,
                "device_id": device_id or f"dev_{username}",
            },
        }
    )


def list_devices(app: ServerApplication, session: dict, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.DEVICE_LIST_REQUEST,
                correlation_id=f"devices_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {},
        }
    )


def list_contacts(app: ServerApplication, session: dict, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.CONTACT_LIST_REQUEST,
                correlation_id=f"contacts_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {},
        }
    )


def send_message(app: ServerApplication, session: dict, text: str, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.MESSAGE_SEND,
                correlation_id=f"send_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {"conversation_id": "conv_alice_bob", "text": text},
        }
    )


def send_attachment(app: ServerApplication, session: dict, content: bytes, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.MESSAGE_SEND_ATTACHMENT,
                correlation_id=f"att_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {
                "conversation_id": "conv_alice_bob",
                "caption": "pg attachment",
                "filename": "pg.bin",
                "mime_type": "application/octet-stream",
                "content_b64": base64.b64encode(content).decode("ascii"),
                "size_bytes": len(content),
            },
        }
    )


def fetch_attachment(app: ServerApplication, session: dict, attachment_id: str, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.ATTACHMENT_FETCH_REQUEST,
                correlation_id=f"fetch_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {"attachment_id": attachment_id},
        }
    )


def add_contact(app: ServerApplication, session: dict, target_user_id: str, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.CONTACT_ADD,
                correlation_id=f"contact_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {"target_user_id": target_user_id},
        }
    )


def remote_invite(app: ServerApplication, session: dict, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.REMOTE_INVITE,
                correlation_id=f"remote_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {
                "requester_device_id": "dev_alice_win",
                "target_device_id": "dev_bob_win",
            },
        }
    )


def edit_message(app: ServerApplication, session: dict, message_id: str, text: str, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.MESSAGE_EDIT,
                correlation_id=f"edit_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {
                "conversation_id": "conv_alice_bob",
                "message_id": message_id,
                "text": text,
            },
        }
    )


def sync(app: ServerApplication, session: dict, seq: int, payload: dict | None = None) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.CONVERSATION_SYNC,
                correlation_id=f"sync_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": payload or {},
        }
    )


def test_postgres_persists_user_session_device() -> None:
    repository = PostgresStateRepository(DSN)
    assert repository.schema_version() >= POSTGRES_SCHEMA_VERSION
    username = "pg_repo_user"
    app = ServerApplication(pg_dsn=DSN)
    response = dispatch_register(app, username, 1)
    if response["type"] == "error" and response["payload"]["code"] == "username_taken":
        response = login(app, username, 2)
    assert response["type"] in {"register_response", "login_response"}, response
    session = response["payload"]
    first_devices = list_devices(app, session, 3)
    assert first_devices["type"] == "device_list_response", first_devices
    assert any(device["device_id"] == f"dev_{username}" for device in first_devices["payload"]["devices"])

    restarted = ServerApplication(pg_dsn=DSN)
    assert username in {user.username for user in restarted.state.users.values()}
    assert session["session_id"] in restarted.state.sessions
    assert f"dev_{username}" in restarted.state.devices
    second_devices = list_devices(restarted, session, 4)
    assert second_devices["type"] == "device_list_response", second_devices
    assert any(device["device_id"] == f"dev_{username}" for device in second_devices["payload"]["devices"])


def test_postgres_persists_conversation_message_change_log() -> None:
    app = ServerApplication(pg_dsn=DSN)
    response = login(app, "alice", 20, password="alice_pw", device_id="dev_alice_win")
    assert response["type"] == "login_response", response
    session = response["payload"]
    text = "pg conversation repository message"
    sent = send_message(app, session, text, 21)
    assert sent["type"] == "message_deliver", sent
    message_id = sent["payload"]["message_id"]
    edited = edit_message(app, session, message_id, text + " edited", 22)
    assert edited["type"] == "message_edited", edited

    restarted = ServerApplication(pg_dsn=DSN)
    restored = sync(restarted, session, 23)
    assert restored["type"] == "conversation_sync", restored
    conversations = restored["payload"]["conversations"]
    conversation = next(c for c in conversations if c["conversation_id"] == "conv_alice_bob")
    message = next(m for m in conversation["messages"] if m["message_id"] == message_id)
    assert message["text"] == text + " edited", message
    incremental = sync(
        restarted,
        session,
        24,
        {
            "cursors": {"conv_alice_bob": message_id},
            "versions": {"conv_alice_bob": 0},
        },
    )
    assert incremental["type"] == "conversation_sync", incremental
    delta_conversation = next(
        c for c in incremental["payload"]["conversations"]
        if c["conversation_id"] == "conv_alice_bob"
    )
    assert any(
        change["kind"] == "message_edited" and change["message_id"] == message_id
        for change in delta_conversation["changes"]
    ), delta_conversation


def test_postgres_persists_contacts_attachments_remote_sessions() -> None:
    app = ServerApplication(pg_dsn=DSN)
    response = login(app, "alice", 40, password="alice_pw", device_id="dev_alice_win")
    assert response["type"] == "login_response", response
    alice = response["payload"]
    contact = add_contact(app, alice, "u_bob", 41)
    if contact["type"] == "error" and contact["payload"].get("code") == "contact_already_added":
        contact = list_contacts(app, alice, 410)
    assert contact["type"] == "contact_list_response", contact
    assert any(c["user_id"] == "u_bob" for c in contact["payload"]["contacts"]), contact
    body = b"pg-attachment-bytes"
    attached = send_attachment(app, alice, body, 42)
    assert attached["type"] == "message_deliver", attached
    attachment_id = attached["payload"]["attachment_id"]
    remote = remote_invite(app, alice, 43)
    assert remote["type"] == "remote_session_state", remote
    remote_session_id = remote["payload"]["remote_session_id"]

    restarted = ServerApplication(pg_dsn=DSN)
    assert restarted.state.contacts.get("u_alice") == ["u_bob"], restarted.state.contacts
    assert attachment_id in restarted.state.attachments, restarted.state.attachments
    assert remote_session_id in restarted.state.remote_sessions, restarted.state.remote_sessions
    assert restarted.state.remote_sessions[remote_session_id].state == "awaiting_approval"
    fetched = fetch_attachment(restarted, alice, attachment_id, 44)
    assert fetched["type"] == "attachment_fetch_response", fetched
    assert base64.b64decode(fetched["payload"]["content_b64"]) == body


SCENARIOS = [
    ("postgres_persists_user_session_device", test_postgres_persists_user_session_device),
    ("postgres_persists_conversation_message_change_log", test_postgres_persists_conversation_message_change_log),
    (
        "postgres_persists_contacts_attachments_remote_sessions",
        test_postgres_persists_contacts_attachments_remote_sessions,
    ),
]


def main() -> int:
    failures: list[str] = []
    for name, fn in SCENARIOS:
        try:
            fn()
            print(f"[ok ] {name}")
        except Exception as exc:
            failures.append(f"{name}: {exc}")
            print(f"[FAIL] {name}: {exc}")
    print(f"passed {len(SCENARIOS) - len(failures)}/{len(SCENARIOS)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
