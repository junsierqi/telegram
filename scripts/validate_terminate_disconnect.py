"""Targeted lifecycle test for remote session terminate/disconnect flows.

Runs in-process against ServerApplication. Covers:
- terminate by requester from approved state
- terminate by target from approved state
- disconnect by either peer from approved state
- reject of terminate / disconnect from pre-approval state (awaiting_approval)
- reject of terminate / disconnect from already-terminal state
- reject of terminate / disconnect by non-participant
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402


def login(app: ServerApplication, username: str, password: str, device_id: str, seq: int) -> dict:
    response = app.dispatch(
        {
            **make_envelope(MessageType.LOGIN_REQUEST, correlation_id=f"corr_login_{username}", sequence=seq),
            "payload": {"username": username, "password": password, "device_id": device_id},
        }
    )
    assert response["type"] == "login_response", f"login failed for {username}: {response}"
    return response["payload"]


def invite(app: ServerApplication, requester_session: dict, target_device_id: str, seq: int) -> str:
    response = app.dispatch(
        {
            **make_envelope(
                MessageType.REMOTE_INVITE,
                correlation_id=f"corr_invite_{seq}",
                session_id=requester_session["session_id"],
                actor_user_id=requester_session["user_id"],
                sequence=seq,
            ),
            "payload": {
                "requester_device_id": requester_session["device_id"],
                "target_device_id": target_device_id,
            },
        }
    )
    assert response["type"] == "remote_session_state", f"invite failed: {response}"
    return response["payload"]["remote_session_id"]


def approve(app: ServerApplication, approver_session: dict, remote_session_id: str, seq: int) -> dict:
    response = app.dispatch(
        {
            **make_envelope(
                MessageType.REMOTE_APPROVE,
                correlation_id=f"corr_approve_{seq}",
                session_id=approver_session["session_id"],
                actor_user_id=approver_session["user_id"],
                sequence=seq,
            ),
            "payload": {"remote_session_id": remote_session_id},
        }
    )
    assert response["type"] == "remote_relay_assignment", f"approve failed: {response}"
    return response


def send_lifecycle(
    app: ServerApplication,
    sess: dict,
    mtype: MessageType,
    remote_session_id: str,
    seq: int,
    *,
    extra_payload: dict | None = None,
) -> dict:
    payload = {"remote_session_id": remote_session_id}
    if extra_payload:
        payload.update(extra_payload)
    return app.dispatch(
        {
            **make_envelope(
                mtype,
                correlation_id=f"corr_{mtype.value}_{seq}",
                session_id=sess["session_id"],
                actor_user_id=sess["user_id"],
                sequence=seq,
            ),
            "payload": payload,
        }
    )


def expect_terminated(response: dict, expected_state: str, expected_detail: str) -> None:
    assert response["type"] == "remote_session_terminated", f"expected terminated, got: {response}"
    assert response["payload"]["state"] == expected_state, response
    assert response["payload"]["detail"] == expected_detail, response


def expect_error(response: dict, expected_code: str) -> None:
    assert response["type"] == "error", f"expected error, got: {response}"
    assert response["payload"]["code"] == expected_code, response
    assert response["payload"]["message"], f"empty human message in {response}"


def scenario(label: str) -> None:
    print(f"\n[scenario] {label}")


def run_scenario_terminate_by_requester() -> None:
    scenario("approved -> terminate by requester -> terminated")
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    bob = login(app, "bob", "bob_pw", "dev_bob_win", 2)
    rs_id = invite(app, alice, "dev_bob_win", 3)
    approve(app, bob, rs_id, 4)
    response = send_lifecycle(app, alice, MessageType.REMOTE_TERMINATE, rs_id, 5)
    expect_terminated(response, "terminated", "terminated_by_requester")


def run_scenario_terminate_by_target() -> None:
    scenario("approved -> terminate by target -> terminated")
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    bob = login(app, "bob", "bob_pw", "dev_bob_win", 2)
    rs_id = invite(app, alice, "dev_bob_win", 3)
    approve(app, bob, rs_id, 4)
    response = send_lifecycle(app, bob, MessageType.REMOTE_TERMINATE, rs_id, 5)
    expect_terminated(response, "terminated", "terminated_by_target")


def run_scenario_disconnect() -> None:
    scenario("approved -> disconnect with reason -> disconnected")
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    bob = login(app, "bob", "bob_pw", "dev_bob_win", 2)
    rs_id = invite(app, alice, "dev_bob_win", 3)
    approve(app, bob, rs_id, 4)
    response = send_lifecycle(
        app, alice, MessageType.REMOTE_DISCONNECT, rs_id, 5,
        extra_payload={"reason": "network_drop"},
    )
    expect_terminated(response, "disconnected", "network_drop")


def run_scenario_terminate_pre_approval() -> None:
    scenario("awaiting_approval -> terminate -> rejected (not_active)")
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    login(app, "bob", "bob_pw", "dev_bob_win", 2)
    rs_id = invite(app, alice, "dev_bob_win", 3)
    response = send_lifecycle(app, alice, MessageType.REMOTE_TERMINATE, rs_id, 4)
    expect_error(response, "remote_session_not_active")


def run_scenario_terminate_terminal() -> None:
    scenario("terminated -> terminate again -> already_terminal")
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    bob = login(app, "bob", "bob_pw", "dev_bob_win", 2)
    rs_id = invite(app, alice, "dev_bob_win", 3)
    approve(app, bob, rs_id, 4)
    send_lifecycle(app, alice, MessageType.REMOTE_TERMINATE, rs_id, 5)
    response = send_lifecycle(app, alice, MessageType.REMOTE_TERMINATE, rs_id, 6)
    expect_error(response, "remote_session_already_terminal")


def run_scenario_terminate_by_non_participant() -> None:
    scenario("approved -> terminate by non-participant -> denied")
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    bob = login(app, "bob", "bob_pw", "dev_bob_win", 2)
    rs_id = invite(app, alice, "dev_bob_win", 3)
    approve(app, bob, rs_id, 4)
    fake_session = {"session_id": "not_a_real_session", "user_id": "u_alice"}
    response = send_lifecycle(app, fake_session, MessageType.REMOTE_TERMINATE, rs_id, 5)
    expect_error(response, "invalid_session")


def run_scenario_disconnect_by_non_participant() -> None:
    scenario("approved -> disconnect with session_actor_mismatch -> denied")
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    bob = login(app, "bob", "bob_pw", "dev_bob_win", 2)
    rs_id = invite(app, alice, "dev_bob_win", 3)
    approve(app, bob, rs_id, 4)
    response = app.dispatch(
        {
            **make_envelope(
                MessageType.REMOTE_DISCONNECT,
                correlation_id="corr_evil",
                session_id=alice["session_id"],
                actor_user_id="u_bob",
                sequence=5,
            ),
            "payload": {"remote_session_id": rs_id, "reason": "forced"},
        }
    )
    expect_error(response, "session_actor_mismatch")


def run_scenario_disconnect_after_terminate() -> None:
    scenario("terminated -> disconnect -> already_terminal")
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    bob = login(app, "bob", "bob_pw", "dev_bob_win", 2)
    rs_id = invite(app, alice, "dev_bob_win", 3)
    approve(app, bob, rs_id, 4)
    send_lifecycle(app, alice, MessageType.REMOTE_TERMINATE, rs_id, 5)
    response = send_lifecycle(app, bob, MessageType.REMOTE_DISCONNECT, rs_id, 6)
    expect_error(response, "remote_session_already_terminal")


def main() -> int:
    scenarios = [
        run_scenario_terminate_by_requester,
        run_scenario_terminate_by_target,
        run_scenario_disconnect,
        run_scenario_terminate_pre_approval,
        run_scenario_terminate_terminal,
        run_scenario_terminate_by_non_participant,
        run_scenario_disconnect_by_non_participant,
        run_scenario_disconnect_after_terminate,
    ]
    for fn in scenarios:
        fn()
    print(f"\nAll {len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
