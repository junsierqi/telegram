"""Targeted lifecycle test for remote_rendezvous_request / remote_rendezvous_info.

Covers:
- approved -> rendezvous -> returns info + transitions to negotiating
- negotiating -> rendezvous -> returns info idempotently, stays negotiating
- awaiting_approval -> rendezvous -> not_ready_for_rendezvous
- terminated -> rendezvous -> not_ready_for_rendezvous
- non-participant (via actor_user_id mismatch) -> session_actor_mismatch
- unknown remote_session_id -> unknown_remote_session
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
    assert response["type"] == "login_response", response
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
    assert response["type"] == "remote_session_state", response
    return response["payload"]["remote_session_id"]


def approve(app: ServerApplication, approver_session: dict, remote_session_id: str, seq: int) -> None:
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
    assert response["type"] == "remote_relay_assignment", response


def terminate(app: ServerApplication, session: dict, remote_session_id: str, seq: int) -> None:
    response = app.dispatch(
        {
            **make_envelope(
                MessageType.REMOTE_TERMINATE,
                correlation_id=f"corr_term_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": {"remote_session_id": remote_session_id},
        }
    )
    assert response["type"] == "remote_session_terminated", response


def rendezvous(
    app: ServerApplication,
    session: dict,
    remote_session_id: str,
    seq: int,
    *,
    actor_override: str | None = None,
) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.REMOTE_RENDEZVOUS_REQUEST,
                correlation_id=f"corr_rdv_{seq}",
                session_id=session["session_id"],
                actor_user_id=actor_override or session["user_id"],
                sequence=seq,
            ),
            "payload": {"remote_session_id": remote_session_id},
        }
    )


def scenario(label: str) -> None:
    print(f"\n[scenario] {label}")


def run_scenario_approved_to_negotiating() -> None:
    scenario("approved -> rendezvous returns info + transitions to negotiating")
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    bob = login(app, "bob", "bob_pw", "dev_bob_win", 2)
    rs_id = invite(app, alice, "dev_bob_win", 3)
    approve(app, bob, rs_id, 4)
    response = rendezvous(app, alice, rs_id, 5)
    assert response["type"] == "remote_rendezvous_info", response
    p = response["payload"]
    assert p["remote_session_id"] == rs_id, p
    assert p["state"] == "negotiating", p
    assert len(p["candidates"]) >= 3, p
    kinds = {c["kind"] for c in p["candidates"]}
    assert {"host", "srflx", "relay"}.issubset(kinds), kinds
    assert p["relay_region"] == "us-west", p
    assert p["relay_endpoint"].startswith("relay-usw"), p


def run_scenario_idempotent_in_negotiating() -> None:
    scenario("negotiating -> rendezvous again -> stays negotiating, same info")
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    bob = login(app, "bob", "bob_pw", "dev_bob_win", 2)
    rs_id = invite(app, alice, "dev_bob_win", 3)
    approve(app, bob, rs_id, 4)
    first = rendezvous(app, alice, rs_id, 5)
    assert first["payload"]["state"] == "negotiating"
    second = rendezvous(app, bob, rs_id, 6)
    assert second["type"] == "remote_rendezvous_info", second
    assert second["payload"]["state"] == "negotiating", second


def run_scenario_pre_approval_rejected() -> None:
    scenario("awaiting_approval -> rendezvous -> not_ready_for_rendezvous")
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    login(app, "bob", "bob_pw", "dev_bob_win", 2)
    rs_id = invite(app, alice, "dev_bob_win", 3)
    response = rendezvous(app, alice, rs_id, 4)
    assert response["type"] == "error", response
    assert response["payload"]["code"] == "remote_session_not_ready_for_rendezvous", response


def run_scenario_terminated_rejected() -> None:
    scenario("terminated -> rendezvous -> not_ready_for_rendezvous")
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    bob = login(app, "bob", "bob_pw", "dev_bob_win", 2)
    rs_id = invite(app, alice, "dev_bob_win", 3)
    approve(app, bob, rs_id, 4)
    terminate(app, alice, rs_id, 5)
    response = rendezvous(app, alice, rs_id, 6)
    assert response["type"] == "error", response
    assert response["payload"]["code"] == "remote_session_not_ready_for_rendezvous", response


def run_scenario_actor_mismatch() -> None:
    scenario("actor_user_id mismatch -> session_actor_mismatch")
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    bob = login(app, "bob", "bob_pw", "dev_bob_win", 2)
    rs_id = invite(app, alice, "dev_bob_win", 3)
    approve(app, bob, rs_id, 4)
    response = rendezvous(app, alice, rs_id, 5, actor_override="u_bob")
    assert response["type"] == "error", response
    assert response["payload"]["code"] == "session_actor_mismatch", response


def run_scenario_unknown_session() -> None:
    scenario("unknown remote_session_id -> unknown_remote_session")
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    login(app, "bob", "bob_pw", "dev_bob_win", 2)
    response = rendezvous(app, alice, "remote_does_not_exist", 3)
    assert response["type"] == "error", response
    assert response["payload"]["code"] == "unknown_remote_session", response


def main() -> int:
    scenarios = [
        run_scenario_approved_to_negotiating,
        run_scenario_idempotent_in_negotiating,
        run_scenario_pre_approval_rejected,
        run_scenario_terminated_rejected,
        run_scenario_actor_mismatch,
        run_scenario_unknown_session,
    ]
    for fn in scenarios:
        fn()
    print(f"\nAll {len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
