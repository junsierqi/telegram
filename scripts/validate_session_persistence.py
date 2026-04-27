"""Login sessions survive server restart.

Scenarios:
- login → destroy server instance → new instance loads same state-file → old session_id still resolves
- counter recovers from highest persisted sess_N (no duplicate IDs after restart)
- no state-file → sessions are in-memory only (regression guard)
- typed error code surfaces when a session that was never persisted is reused
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import (  # noqa: E402
    ErrorCode,
    MessageType,
    make_envelope,
)


def login(app: ServerApplication, username: str, password: str, device_id: str, seq: int) -> dict:
    response = app.dispatch(
        {
            **make_envelope(
                MessageType.LOGIN_REQUEST, correlation_id=f"corr_login_{username}", sequence=seq
            ),
            "payload": {"username": username, "password": password, "device_id": device_id},
        }
    )
    assert response["type"] == "login_response", response
    return response["payload"]


def conv_sync_as(app: ServerApplication, session_id: str, user_id: str, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.CONVERSATION_SYNC,
                correlation_id=f"corr_sync_{seq}",
                session_id=session_id,
                actor_user_id=user_id,
                sequence=seq,
            ),
            "payload": {},
        }
    )


def scenario(label: str) -> None:
    print(f"\n[scenario] {label}")


def run_session_survives_restart() -> None:
    scenario("login -> restart -> same session_id still resolves")
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "runtime.json"
        app1 = ServerApplication(state_file=str(state_path))
        alice = login(app1, "alice", "alice_pw", "dev_alice_win", 1)
        sid = alice["session_id"]
        del app1

        app2 = ServerApplication(state_file=str(state_path))
        response = conv_sync_as(app2, sid, alice["user_id"], 2)
        assert response["type"] == "conversation_sync", response


def run_counter_recovers() -> None:
    scenario("restart picks counter past the highest persisted sess_N")
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "runtime.json"
        app1 = ServerApplication(state_file=str(state_path))
        a1 = login(app1, "alice", "alice_pw", "dev_alice_win", 1)
        a2 = login(app1, "bob", "bob_pw", "dev_bob_win", 2)
        a3 = login(app1, "alice", "alice_pw", "dev_alice_win", 3)
        assert a1["session_id"] == "sess_1"
        assert a2["session_id"] == "sess_2"
        assert a3["session_id"] == "sess_3"
        del app1

        app2 = ServerApplication(state_file=str(state_path))
        a4 = login(app2, "bob", "bob_pw", "dev_bob_win", 1)
        assert a4["session_id"] == "sess_4", (
            f"counter collision: new login got {a4['session_id']}, expected sess_4"
        )


def run_no_state_file_is_in_memory_only() -> None:
    scenario("without --state-file sessions are in-memory only")
    app1 = ServerApplication()
    alice = login(app1, "alice", "alice_pw", "dev_alice_win", 1)
    sid = alice["session_id"]
    del app1

    app2 = ServerApplication()
    response = conv_sync_as(app2, sid, alice["user_id"], 2)
    assert response["type"] == "error", response
    assert response["payload"]["code"] == ErrorCode.INVALID_SESSION.value, response


def run_unknown_session_still_typed_error() -> None:
    scenario("unknown session id across restart still returns INVALID_SESSION")
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "runtime.json"
        app1 = ServerApplication(state_file=str(state_path))
        login(app1, "alice", "alice_pw", "dev_alice_win", 1)
        del app1

        app2 = ServerApplication(state_file=str(state_path))
        response = conv_sync_as(app2, "sess_does_not_exist", "u_alice", 1)
        assert response["type"] == "error", response
        assert response["payload"]["code"] == ErrorCode.INVALID_SESSION.value, response


def run_conversation_and_remote_session_survive_too() -> None:
    scenario("persistence is cumulative — sessions + conversations + remote sessions all survive")
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "runtime.json"
        app1 = ServerApplication(state_file=str(state_path))
        alice = login(app1, "alice", "alice_pw", "dev_alice_win", 1)
        # send a message
        app1.dispatch(
            {
                **make_envelope(
                    MessageType.MESSAGE_SEND,
                    correlation_id="corr_send",
                    session_id=alice["session_id"],
                    actor_user_id=alice["user_id"],
                    sequence=2,
                ),
                "payload": {"conversation_id": "conv_alice_bob", "text": "survives"},
            }
        )
        # create remote invite
        app1.dispatch(
            {
                **make_envelope(
                    MessageType.REMOTE_INVITE,
                    correlation_id="corr_invite",
                    session_id=alice["session_id"],
                    actor_user_id=alice["user_id"],
                    sequence=3,
                ),
                "payload": {
                    "requester_device_id": "dev_alice_win",
                    "target_device_id": "dev_bob_win",
                },
            }
        )
        del app1

        app2 = ServerApplication(state_file=str(state_path))
        assert alice["session_id"] in app2.state.sessions
        texts = [m["text"] for m in app2.state.conversations["conv_alice_bob"].messages]
        assert "survives" in texts, texts
        assert any(
            r.state == "awaiting_approval"
            for r in app2.state.remote_sessions.values()
        ), app2.state.remote_sessions


def main() -> int:
    scenarios = [
        run_session_survives_restart,
        run_counter_recovers,
        run_no_state_file_is_in_memory_only,
        run_unknown_session_still_typed_error,
        run_conversation_and_remote_session_survive_too,
    ]
    for fn in scenarios:
        fn()
    print(f"\nAll {len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
