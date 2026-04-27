"""Validator for production-style history and search paging."""
from __future__ import annotations

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
    assert response["type"] == "message_deliver", response
    return response["payload"]["message_id"]


def sync_page(
    app: ServerApplication,
    session: dict,
    *,
    limit: int,
    before_message_id: str = "",
    seq: int,
) -> dict:
    payload = {"history_limits": {"conv_alice_bob": limit}}
    if before_message_id:
        payload["before_message_ids"] = {"conv_alice_bob": before_message_id}
    return app.dispatch(
        {
            **make_envelope(
                MessageType.CONVERSATION_SYNC,
                correlation_id=f"sync_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": payload,
        }
    )


def search(app: ServerApplication, session: dict, *, limit: int, offset: int, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.MESSAGE_SEARCH_REQUEST,
                correlation_id=f"search_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {
                "query": "paging-token",
                "conversation_id": "conv_alice_bob",
                "limit": limit,
                "offset": offset,
            },
        }
    )


def message_ids(response: dict) -> list[str]:
    conversations = response["payload"]["conversations"]
    assert len(conversations) == 1, response
    return [message["message_id"] for message in conversations[0]["messages"]]


def test_history_pages_from_newest_to_older() -> None:
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    sent = [send(app, alice, f"history page {i}", i + 2) for i in range(5)]

    first = sync_page(app, alice, limit=2, seq=10)
    first_conv = first["payload"]["conversations"][0]
    assert message_ids(first) == sent[-2:], first
    assert first_conv["has_more"] is True, first
    assert first_conv["next_before_message_id"] == sent[-2], first

    second = sync_page(app, alice, limit=2, before_message_id=first_conv["next_before_message_id"], seq=11)
    second_conv = second["payload"]["conversations"][0]
    assert message_ids(second) == sent[-4:-2], second
    assert second_conv["has_more"] is True, second
    assert second_conv["next_before_message_id"] == sent[-4], second

    third = sync_page(app, alice, limit=10, before_message_id=second_conv["next_before_message_id"], seq=12)
    assert message_ids(third) == ["msg_1", sent[0]], third
    assert third["payload"]["conversations"][0]["has_more"] is False, third


def test_search_offset_pages_without_overlap() -> None:
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    sent = [send(app, alice, f"paging-token result {i}", i + 2) for i in range(4)]

    first = search(app, alice, limit=2, offset=0, seq=10)
    first_ids = [result["message_id"] for result in first["payload"]["results"]]
    assert first_ids == sent[:2], first
    assert first["payload"]["has_more"] is True, first
    assert first["payload"]["next_offset"] == 2, first

    second = search(app, alice, limit=2, offset=first["payload"]["next_offset"], seq=11)
    second_ids = [result["message_id"] for result in second["payload"]["results"]]
    assert second_ids == sent[2:], second
    assert second["payload"]["has_more"] is False, second
    assert set(first_ids).isdisjoint(second_ids), (first, second)


SCENARIOS = [
    ("history_pages_from_newest_to_older", test_history_pages_from_newest_to_older),
    ("search_offset_pages_without_overlap", test_search_offset_pages_without_overlap),
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
