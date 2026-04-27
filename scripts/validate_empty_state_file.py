"""Verify that an empty or whitespace-only --state-file is treated as 'start fresh'.

Previous behavior: json.loads('') → JSONDecodeError at startup.
Current behavior: empty file is skipped, defaults are used, first save populates it.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402


def scenario(label: str) -> None:
    print(f"\n[scenario] {label}")


def run_scenario_empty_file() -> None:
    scenario("empty state-file -> startup OK, then writes populate it")
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "runtime.json"
        state_path.write_text("", encoding="utf-8")

        app = ServerApplication(state_file=str(state_path))
        login = app.dispatch(
            {
                **make_envelope(
                    MessageType.LOGIN_REQUEST, correlation_id="corr_login", sequence=1
                ),
                "payload": {
                    "username": "alice",
                    "password": "alice_pw",
                    "device_id": "dev_alice_win",
                },
            }
        )
        assert login["type"] == "login_response", login

        send = app.dispatch(
            {
                **make_envelope(
                    MessageType.MESSAGE_SEND,
                    correlation_id="corr_send",
                    session_id=login["payload"]["session_id"],
                    actor_user_id=login["payload"]["user_id"],
                    sequence=2,
                ),
                "payload": {
                    "conversation_id": "conv_alice_bob",
                    "text": "post-empty-state-file message",
                },
            }
        )
        assert send["type"] == "message_deliver", send

        contents = state_path.read_text(encoding="utf-8")
        assert contents.strip(), "state file should have been populated after send"
        assert "post-empty-state-file message" in contents, contents


def run_scenario_whitespace_file() -> None:
    scenario("whitespace-only state-file -> same as empty")
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "runtime.json"
        state_path.write_text("   \n\n  \t\n", encoding="utf-8")
        app = ServerApplication(state_file=str(state_path))
        assert app.state.state_file == state_path.resolve()


def run_scenario_missing_file() -> None:
    scenario("missing state-file -> startup OK, first save creates it")
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "nested" / "runtime.json"
        assert not state_path.exists()
        app = ServerApplication(state_file=str(state_path))
        login = app.dispatch(
            {
                **make_envelope(
                    MessageType.LOGIN_REQUEST, correlation_id="corr_login", sequence=1
                ),
                "payload": {
                    "username": "alice",
                    "password": "alice_pw",
                    "device_id": "dev_alice_win",
                },
            }
        )
        app.dispatch(
            {
                **make_envelope(
                    MessageType.MESSAGE_SEND,
                    correlation_id="corr_send",
                    session_id=login["payload"]["session_id"],
                    actor_user_id=login["payload"]["user_id"],
                    sequence=2,
                ),
                "payload": {
                    "conversation_id": "conv_alice_bob",
                    "text": "first message creates file",
                },
            }
        )
        assert state_path.exists()


def run_scenario_existing_valid_file_still_works() -> None:
    scenario("non-empty state-file -> still loads normally (regression guard)")
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "runtime.json"
        app1 = ServerApplication(state_file=str(state_path))
        login = app1.dispatch(
            {
                **make_envelope(
                    MessageType.LOGIN_REQUEST, correlation_id="corr_login", sequence=1
                ),
                "payload": {
                    "username": "alice",
                    "password": "alice_pw",
                    "device_id": "dev_alice_win",
                },
            }
        )
        app1.dispatch(
            {
                **make_envelope(
                    MessageType.MESSAGE_SEND,
                    correlation_id="corr_send",
                    session_id=login["payload"]["session_id"],
                    actor_user_id=login["payload"]["user_id"],
                    sequence=2,
                ),
                "payload": {
                    "conversation_id": "conv_alice_bob",
                    "text": "persisted message",
                },
            }
        )
        del app1

        app2 = ServerApplication(state_file=str(state_path))
        conv = app2.state.conversations["conv_alice_bob"]
        texts = [m["text"] for m in conv.messages]
        assert "persisted message" in texts, texts


def main() -> int:
    scenarios = [
        run_scenario_empty_file,
        run_scenario_whitespace_file,
        run_scenario_missing_file,
        run_scenario_existing_valid_file_still_works,
    ]
    for fn in scenarios:
        fn()
    print(f"\nAll {len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
