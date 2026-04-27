"""Validator for C4a SQLite durable persistence boundary."""
from __future__ import annotations

import base64
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402


def _login(app: ServerApplication, username: str, password: str, device_id: str, seq: int) -> dict:
    response = app.dispatch(
        {
            **make_envelope(MessageType.LOGIN_REQUEST, correlation_id=f"login_{seq}", sequence=seq),
            "payload": {"username": username, "password": password, "device_id": device_id},
        }
    )
    assert response["type"] == "login_response", response
    return response["payload"]


def _send_message(app: ServerApplication, session: dict, text: str, seq: int) -> dict:
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


def _send_attachment(app: ServerApplication, session: dict, content: bytes, seq: int) -> dict:
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
                "caption": "sqlite attachment",
                "filename": "sqlite.bin",
                "mime_type": "application/octet-stream",
                "content_b64": base64.b64encode(content).decode("ascii"),
                "size_bytes": len(content),
            },
        }
    )


def _fetch_attachment(app: ServerApplication, session: dict, attachment_id: str, seq: int) -> dict:
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


def _add_contact(app: ServerApplication, session: dict, target_user_id: str, seq: int) -> dict:
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


def _remote_invite(app: ServerApplication, session: dict, seq: int) -> dict:
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


def test_sqlite_persists_core_state() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_file = str(Path(tmp) / "runtime.sqlite")
        blob_dir = str(Path(tmp) / "blobs")
        app = ServerApplication(db_file=db_file, attachment_dir=blob_dir)
        alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
        bob = _login(app, "bob", "bob_pw", "dev_bob_win", 2)
        _send_message(app, alice, "sqlite survives", 3)
        _add_contact(app, alice, "u_bob", 4)
        remote = _remote_invite(app, alice, 5)
        assert remote["type"] == "remote_session_state", remote
        body = b"sqlite-bytes"
        attached = _send_attachment(app, alice, body, 6)
        attachment_id = attached["payload"]["attachment_id"]

        app2 = ServerApplication(db_file=db_file, attachment_dir=blob_dir)
        assert alice["session_id"] in app2.state.sessions
        assert bob["session_id"] in app2.state.sessions
        assert "u_bob" in app2.state.contacts["u_alice"]
        assert any(m["text"] == "sqlite survives" for m in app2.state.conversations["conv_alice_bob"].messages)
        assert any(r.state == "awaiting_approval" for r in app2.state.remote_sessions.values())

        alice2 = _login(app2, "alice", "alice_pw", "dev_alice_win", 7)
        fetched = _fetch_attachment(app2, alice2, attachment_id, 8)
        assert fetched["type"] == "attachment_fetch_response", fetched
        assert base64.b64decode(fetched["payload"]["content_b64"]) == body
        del app2
        del app


def test_json_mode_still_works() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        state_file = str(Path(tmp) / "runtime.json")
        app = ServerApplication(state_file=state_file)
        alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
        _send_message(app, alice, "json still works", 2)
        app2 = ServerApplication(state_file=state_file)
        assert any(m["text"] == "json still works" for m in app2.state.conversations["conv_alice_bob"].messages)
        del app2
        del app


SCENARIOS = [
    ("sqlite_persists_core_state", test_sqlite_persists_core_state),
    ("json_mode_still_works", test_json_mode_still_works),
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
