"""Verify every protocol error path returns {code: ErrorCode, message: str}.

Asserts:
- Every error response carries both `code` (typed wire value) and `message` (human text).
- `code` matches the ErrorCode enum; `message` matches the code's registered human message.
- A representative path per error code is covered.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import (  # noqa: E402
    ErrorCode,
    MessageType,
    error_message,
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
    return response


def invite(app: ServerApplication, sess: dict, target_device_id: str, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.REMOTE_INVITE,
                correlation_id=f"corr_invite_{seq}",
                session_id=sess["session_id"],
                actor_user_id=sess["user_id"],
                sequence=seq,
            ),
            "payload": {
                "requester_device_id": sess["device_id"],
                "target_device_id": target_device_id,
            },
        }
    )


def expect_error(response: dict, expected_code: ErrorCode, *, exact_message: bool = True) -> None:
    assert response["type"] == "error", f"expected error, got: {response}"
    payload = response["payload"]
    assert "code" in payload and "message" in payload, f"missing code/message in {payload}"
    assert payload["code"] == expected_code.value, (
        f"code mismatch: expected {expected_code.value}, got {payload['code']}"
    )
    assert payload["message"], f"empty message for {expected_code.value}"
    if exact_message:
        assert payload["message"] == error_message(expected_code), (
            f"message mismatch for {expected_code.value}: "
            f"got {payload['message']!r}, expected {error_message(expected_code)!r}"
        )


def scenario(label: str) -> None:
    print(f"\n[scenario] {label}")


def run_invalid_credentials() -> None:
    scenario("login with wrong password -> INVALID_CREDENTIALS")
    app = ServerApplication()
    response = login(app, "alice", "wrong_password", "dev_alice_win", 1)
    expect_error(response, ErrorCode.INVALID_CREDENTIALS)


def run_invalid_session() -> None:
    scenario("use unknown session_id -> INVALID_SESSION")
    app = ServerApplication()
    response = app.dispatch(
        {
            **make_envelope(
                MessageType.CONVERSATION_SYNC,
                correlation_id="corr_sync",
                session_id="sess_does_not_exist",
                actor_user_id="u_alice",
                sequence=1,
            ),
            "payload": {},
        }
    )
    expect_error(response, ErrorCode.INVALID_SESSION)


def run_session_actor_mismatch() -> None:
    scenario("actor_user_id != session owner -> SESSION_ACTOR_MISMATCH")
    app = ServerApplication()
    login_payload = login(app, "alice", "alice_pw", "dev_alice_win", 1)["payload"]
    response = app.dispatch(
        {
            **make_envelope(
                MessageType.CONVERSATION_SYNC,
                correlation_id="corr_sync",
                session_id=login_payload["session_id"],
                actor_user_id="u_bob",
                sequence=2,
            ),
            "payload": {},
        }
    )
    expect_error(response, ErrorCode.SESSION_ACTOR_MISMATCH)


def run_unknown_conversation() -> None:
    scenario("message_send to unknown conversation -> UNKNOWN_CONVERSATION")
    app = ServerApplication()
    sess = login(app, "alice", "alice_pw", "dev_alice_win", 1)["payload"]
    response = app.dispatch(
        {
            **make_envelope(
                MessageType.MESSAGE_SEND,
                correlation_id="corr_send",
                session_id=sess["session_id"],
                actor_user_id=sess["user_id"],
                sequence=2,
            ),
            "payload": {"conversation_id": "conv_does_not_exist", "text": "hi"},
        }
    )
    expect_error(response, ErrorCode.UNKNOWN_CONVERSATION)


def run_empty_message() -> None:
    scenario("empty message_send text -> EMPTY_MESSAGE")
    app = ServerApplication()
    sess = login(app, "alice", "alice_pw", "dev_alice_win", 1)["payload"]
    response = app.dispatch(
        {
            **make_envelope(
                MessageType.MESSAGE_SEND,
                correlation_id="corr_send",
                session_id=sess["session_id"],
                actor_user_id=sess["user_id"],
                sequence=2,
            ),
            "payload": {"conversation_id": "conv_alice_bob", "text": "   "},
        }
    )
    expect_error(response, ErrorCode.EMPTY_MESSAGE)


def run_unknown_target_device() -> None:
    scenario("remote_invite with missing target device -> UNKNOWN_TARGET_DEVICE")
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)["payload"]
    response = invite(app, alice, "dev_does_not_exist", 2)
    expect_error(response, ErrorCode.UNKNOWN_TARGET_DEVICE)


def run_self_remote() -> None:
    scenario("remote_invite where target device belongs to actor -> SELF_REMOTE_SESSION_NOT_ALLOWED")
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)["payload"]
    response = invite(app, alice, "dev_alice_win", 2)
    expect_error(response, ErrorCode.SELF_REMOTE_SESSION_NOT_ALLOWED)


def run_remote_approval_denied() -> None:
    scenario("someone else's device approves -> REMOTE_APPROVAL_DENIED")
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)["payload"]
    invite_resp = invite(app, alice, "dev_bob_win", 2)
    rs_id = invite_resp["payload"]["remote_session_id"]
    # Alice approves her own invite — she's not the target
    response = app.dispatch(
        {
            **make_envelope(
                MessageType.REMOTE_APPROVE,
                correlation_id="corr_bad_approve",
                session_id=alice["session_id"],
                actor_user_id=alice["user_id"],
                sequence=3,
            ),
            "payload": {"remote_session_id": rs_id},
        }
    )
    expect_error(response, ErrorCode.REMOTE_APPROVAL_DENIED)


def run_remote_session_not_ready_for_rendezvous() -> None:
    scenario("rendezvous before approve -> REMOTE_SESSION_NOT_READY_FOR_RENDEZVOUS")
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)["payload"]
    login(app, "bob", "bob_pw", "dev_bob_win", 2)
    invite_resp = invite(app, alice, "dev_bob_win", 3)
    rs_id = invite_resp["payload"]["remote_session_id"]
    response = app.dispatch(
        {
            **make_envelope(
                MessageType.REMOTE_RENDEZVOUS_REQUEST,
                correlation_id="corr_rdv",
                session_id=alice["session_id"],
                actor_user_id=alice["user_id"],
                sequence=4,
            ),
            "payload": {"remote_session_id": rs_id},
        }
    )
    expect_error(response, ErrorCode.REMOTE_SESSION_NOT_READY_FOR_RENDEZVOUS)


def run_unsupported_message_type() -> None:
    scenario("unhandled message type reaches dispatch fallback -> UNSUPPORTED_MESSAGE_TYPE")
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)["payload"]
    # A valid MessageType enum value that has no dispatch handler must reach
    # the generic UNSUPPORTED_MESSAGE_TYPE fallback. HEARTBEAT_ACK is a
    # response-direction type — the server only ever emits it, so dispatch
    # has no inbound handler.
    response = app.dispatch(
        {
            **make_envelope(
                MessageType.HEARTBEAT_ACK,
                correlation_id="corr_unh",
                session_id=alice["session_id"],
                actor_user_id=alice["user_id"],
                sequence=2,
            ),
            "payload": {},
        }
    )
    expect_error(response, ErrorCode.UNSUPPORTED_MESSAGE_TYPE, exact_message=False)


def run_code_catalog_complete() -> None:
    scenario("every ErrorCode has a human message (no 'Unknown error.' fallbacks except UNKNOWN)")
    default = error_message(ErrorCode.UNKNOWN)
    for code in ErrorCode:
        if code is ErrorCode.UNKNOWN:
            continue
        msg = error_message(code)
        assert msg != default, f"{code.value} falls back to unknown message"


def main() -> int:
    scenarios = [
        run_invalid_credentials,
        run_invalid_session,
        run_session_actor_mismatch,
        run_unknown_conversation,
        run_empty_message,
        run_unknown_target_device,
        run_self_remote,
        run_remote_approval_denied,
        run_remote_session_not_ready_for_rendezvous,
        run_unsupported_message_type,
        run_code_catalog_complete,
    ]
    for fn in scenarios:
        fn()
    print(f"\nAll {len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
