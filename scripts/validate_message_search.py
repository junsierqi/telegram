"""Validator for server-side message search."""
from __future__ import annotations

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402


def login(app: ServerApplication, username: str, password: str, device_id: str, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(MessageType.LOGIN_REQUEST, correlation_id=f"login_{username}", sequence=seq),
            "payload": {"username": username, "password": password, "device_id": device_id},
        }
    )["payload"]


def send(app: ServerApplication, session: dict, text: str, seq: int) -> str:
    response = app.dispatch(
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
    return response["payload"]["message_id"]


def send_attachment(app: ServerApplication, session: dict, filename: str, seq: int) -> str:
    response = app.dispatch(
        {
            **make_envelope(
                MessageType.MESSAGE_SEND_ATTACHMENT,
                correlation_id=f"send_attachment_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {
                "conversation_id": "conv_alice_bob",
                "caption": "attachment search caption",
                "filename": filename,
                "mime_type": "text/plain",
                "content_b64": base64.b64encode(b"attachment body").decode("ascii"),
                "size_bytes": len(b"attachment body"),
            },
        }
    )
    assert response["type"] == "message_deliver", response
    return response["payload"]["message_id"]


def search(app: ServerApplication, session: dict, query: str, conversation_id: str = "", seq: int = 50) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.MESSAGE_SEARCH_REQUEST,
                correlation_id=f"search_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {"query": query, "conversation_id": conversation_id, "limit": 10},
        }
    )


def test_global_search_finds_message() -> None:
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    mid = send(app, alice, "server side searchable token", 2)
    response = search(app, alice, "searchable token", seq=3)
    assert response["type"] == "message_search_response"
    assert any(result["message_id"] == mid for result in response["payload"]["results"]), response


def test_conversation_filter_scopes_results() -> None:
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    send(app, alice, "scoped search target", 2)
    hit = search(app, alice, "scoped", "conv_alice_bob", seq=3)
    miss = search(app, alice, "scoped", "conv_missing", seq=4)
    assert len(hit["payload"]["results"]) == 1, hit
    assert miss["payload"]["results"] == [], miss


def test_non_participant_cannot_search_private_conversation() -> None:
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    carol = app.auth_service.register(
        username="carol_search",
        password="carol_search_pw",
        display_name="Carol Search",
        device_id="dev_carol_search",
    )
    send(app, alice, "private alice bob only", 2)
    response = search(app, carol, "private alice", seq=3)
    assert response["payload"]["results"] == [], response


def test_attachment_filename_is_searchable() -> None:
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    mid = send_attachment(app, alice, "quarterly-plan-search-token.txt", 2)
    response = search(app, alice, "plan-search-token", seq=3)
    result = next(result for result in response["payload"]["results"] if result["message_id"] == mid)
    assert result["filename"] == "quarterly-plan-search-token.txt", response
    assert result["attachment_id"], response


def test_empty_search_rejected() -> None:
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    response = search(app, alice, "   ", seq=2)
    assert response["type"] == "error"
    assert response["payload"]["code"] == "empty_message"


SCENARIOS = [
    ("global_search_finds_message", test_global_search_finds_message),
    ("conversation_filter_scopes_results", test_conversation_filter_scopes_results),
    ("non_participant_cannot_search_private_conversation", test_non_participant_cannot_search_private_conversation),
    ("attachment_filename_is_searchable", test_attachment_filename_is_searchable),
    ("empty_search_rejected", test_empty_search_rejected),
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
