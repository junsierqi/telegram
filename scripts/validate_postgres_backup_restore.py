"""Validator for PostgreSQL application-level backup/restore.

This is intentionally repository-level rather than pg_dump-level: it verifies
that the runtime payload reconstructed from PostgreSQL can restore a fresh
repository snapshot with users, sessions, messages, contacts, attachments and
remote sessions intact.
"""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402
from server.server.repositories import PostgresStateRepository  # noqa: E402


DSN = os.getenv(
    "TELEGRAM_TEST_PG_DSN",
    "postgresql://telegram:telegram_dev_password@127.0.0.1:5432/telegram",
)


def login(app: ServerApplication, username: str, password: str, device_id: str, seq: int) -> dict:
    response = app.dispatch(
        {
            **make_envelope(MessageType.LOGIN_REQUEST, correlation_id=f"login_{seq}", sequence=seq),
            "payload": {"username": username, "password": password, "device_id": device_id},
        }
    )
    assert response["type"] == "login_response", response
    return response["payload"]


def dispatch(app: ServerApplication, session: dict, msg_type: MessageType, payload: dict, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                msg_type,
                correlation_id=f"backup_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": payload,
        }
    )


def seed_state() -> tuple[dict, str, str]:
    app = ServerApplication(pg_dsn=DSN)
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    sent = dispatch(
        app,
        alice,
        MessageType.MESSAGE_SEND,
        {"conversation_id": "conv_alice_bob", "text": "backup restore marker"},
        2,
    )
    assert sent["type"] == "message_deliver", sent
    contact = dispatch(app, alice, MessageType.CONTACT_ADD, {"target_user_id": "u_bob"}, 3)
    if contact["type"] == "error" and contact["payload"].get("code") == "contact_already_added":
        contact = dispatch(app, alice, MessageType.CONTACT_LIST_REQUEST, {}, 30)
    assert contact["type"] == "contact_list_response", contact
    body = b"backup-restore-bytes"
    attached = dispatch(
        app,
        alice,
        MessageType.MESSAGE_SEND_ATTACHMENT,
        {
            "conversation_id": "conv_alice_bob",
            "caption": "backup attachment",
            "filename": "backup.bin",
            "mime_type": "application/octet-stream",
            "content_b64": base64.b64encode(body).decode("ascii"),
            "size_bytes": len(body),
        },
        4,
    )
    assert attached["type"] == "message_deliver", attached
    remote = dispatch(
        app,
        alice,
        MessageType.REMOTE_INVITE,
        {"requester_device_id": "dev_alice_win", "target_device_id": "dev_bob_win"},
        5,
    )
    assert remote["type"] == "remote_session_state", remote
    return alice, attached["payload"]["attachment_id"], remote["payload"]["remote_session_id"]


def minimal_payload_from(payload: dict) -> dict:
    return {
        "users": payload["users"],
        "devices": payload["devices"],
        "sessions": payload["sessions"],
        "conversations": [],
        "contacts": {},
        "attachments": [],
        "remote_sessions": [],
    }


def test_backup_restore_round_trip() -> None:
    alice, attachment_id, remote_session_id = seed_state()
    repository = PostgresStateRepository(DSN)
    backup = repository.load()
    assert backup is not None
    assert backup["contacts"].get("u_alice") == ["u_bob"], backup["contacts"]
    assert any(
        message.get("text") == "backup restore marker"
        for conversation in backup["conversations"]
        for message in conversation.get("messages", [])
    )
    assert any(att["attachment_id"] == attachment_id for att in backup["attachments"])
    assert any(rs["remote_session_id"] == remote_session_id for rs in backup["remote_sessions"])

    repository.save(minimal_payload_from(backup))
    stripped = repository.load()
    assert stripped is not None
    assert stripped["contacts"] == {}, stripped["contacts"]
    assert stripped["attachments"] == [], stripped["attachments"]
    assert stripped["remote_sessions"] == [], stripped["remote_sessions"]

    repository.save(backup)
    restored_app = ServerApplication(pg_dsn=DSN)
    restored = repository.load()
    assert restored is not None
    assert restored["contacts"].get("u_alice") == ["u_bob"], restored["contacts"]
    assert attachment_id in restored_app.state.attachments
    assert remote_session_id in restored_app.state.remote_sessions
    fetched = dispatch(
        restored_app,
        alice,
        MessageType.ATTACHMENT_FETCH_REQUEST,
        {"attachment_id": attachment_id},
        6,
    )
    assert fetched["type"] == "attachment_fetch_response", fetched
    assert base64.b64decode(fetched["payload"]["content_b64"]) == b"backup-restore-bytes"


SCENARIOS = [("backup_restore_round_trip", test_backup_restore_round_trip)]


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
