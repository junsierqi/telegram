"""D6: control-plane input event injection.

Scenarios:
- requester sends key-down -> remote_input_ack seq=1 kind=key; event appears in InputService log
- multiple events -> sequence numbers are monotonic
- target user (non-requester) sends event -> REMOTE_INPUT_DENIED
- unknown remote_session_id -> UNKNOWN_REMOTE_SESSION
- session not yet approved -> REMOTE_SESSION_NOT_ACTIVE
- terminated session -> REMOTE_SESSION_NOT_ACTIVE
- unknown kind -> UNSUPPORTED_INPUT_KIND
- known kind missing required data fields -> INVALID_INPUT_PAYLOAD
- each kind (key / mouse_move / mouse_button / scroll) round-trips
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import ErrorCode, MessageType, make_envelope  # noqa: E402


def _login(app: ServerApplication, username: str, password: str, device_id: str, seq: int) -> dict:
    response = app.dispatch(
        {
            **make_envelope(
                MessageType.LOGIN_REQUEST, correlation_id=f"corr_{username}", sequence=seq
            ),
            "payload": {"username": username, "password": password, "device_id": device_id},
        }
    )
    return response["payload"]


def _setup_approved(app: ServerApplication) -> tuple[dict, dict, str]:
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    bob = _login(app, "bob", "bob_pw", "dev_bob_win", 2)
    invite = app.dispatch(
        {
            **make_envelope(
                MessageType.REMOTE_INVITE,
                correlation_id="corr_inv",
                session_id=alice["session_id"],
                actor_user_id=alice["user_id"],
                sequence=3,
            ),
            "payload": {
                "requester_device_id": alice["device_id"],
                "target_device_id": "dev_bob_win",
            },
        }
    )
    rs_id = invite["payload"]["remote_session_id"]
    app.dispatch(
        {
            **make_envelope(
                MessageType.REMOTE_APPROVE,
                correlation_id="corr_app",
                session_id=bob["session_id"],
                actor_user_id=bob["user_id"],
                sequence=4,
            ),
            "payload": {"remote_session_id": rs_id},
        }
    )
    return alice, bob, rs_id


def _inject(app: ServerApplication, sess: dict, rs_id: str, kind: str, data: dict, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.REMOTE_INPUT_EVENT,
                correlation_id=f"corr_input_{seq}",
                session_id=sess["session_id"],
                actor_user_id=sess["user_id"],
                sequence=seq,
            ),
            "payload": {"remote_session_id": rs_id, "kind": kind, "data": data},
        }
    )


def scenario(label: str) -> None:
    print(f"\n[scenario] {label}")


def run_basic_key_event() -> None:
    scenario("requester key-down -> ack seq=1 kind=key + log entry")
    app = ServerApplication()
    alice, _, rs_id = _setup_approved(app)
    response = _inject(app, alice, rs_id, "key", {"action": "down", "key": "Enter"}, 5)
    assert response["type"] == "remote_input_ack", response
    assert response["payload"] == {
        "remote_session_id": rs_id,
        "sequence": 1,
        "kind": "key",
    }, response
    log = app.input_service.event_log
    assert len(log) == 1
    assert log[0]["kind"] == "key"
    assert log[0]["data"] == {"action": "down", "key": "Enter"}


def run_sequence_monotonic() -> None:
    scenario("multiple events -> sequence advances")
    app = ServerApplication()
    alice, _, rs_id = _setup_approved(app)
    seqs = []
    for i, (kind, data) in enumerate([
        ("key", {"action": "down", "key": "A"}),
        ("mouse_move", {"x": 100, "y": 200}),
        ("mouse_button", {"action": "down", "button": "left"}),
        ("scroll", {"dx": 0, "dy": -1}),
    ]):
        response = _inject(app, alice, rs_id, kind, data, 5 + i)
        assert response["type"] == "remote_input_ack", response
        seqs.append(response["payload"]["sequence"])
    assert seqs == [1, 2, 3, 4], seqs


def run_target_denied() -> None:
    scenario("target (non-requester) sends event -> REMOTE_INPUT_DENIED")
    app = ServerApplication()
    _, bob, rs_id = _setup_approved(app)
    response = _inject(app, bob, rs_id, "key", {"action": "down", "key": "A"}, 5)
    assert response["type"] == "error", response
    assert response["payload"]["code"] == ErrorCode.REMOTE_INPUT_DENIED.value


def run_unknown_session() -> None:
    scenario("unknown remote_session_id -> UNKNOWN_REMOTE_SESSION")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    response = _inject(app, alice, "remote_nope", "key", {"action": "down", "key": "A"}, 2)
    assert response["payload"]["code"] == ErrorCode.UNKNOWN_REMOTE_SESSION.value


def run_pre_approval_rejected() -> None:
    scenario("before approve -> REMOTE_SESSION_NOT_ACTIVE")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    _login(app, "bob", "bob_pw", "dev_bob_win", 2)
    invite = app.dispatch(
        {
            **make_envelope(
                MessageType.REMOTE_INVITE,
                correlation_id="corr_inv",
                session_id=alice["session_id"],
                actor_user_id=alice["user_id"],
                sequence=3,
            ),
            "payload": {
                "requester_device_id": alice["device_id"],
                "target_device_id": "dev_bob_win",
            },
        }
    )
    rs_id = invite["payload"]["remote_session_id"]
    response = _inject(app, alice, rs_id, "key", {"action": "down", "key": "A"}, 4)
    assert response["payload"]["code"] == ErrorCode.REMOTE_SESSION_NOT_ACTIVE.value


def run_terminated_rejected() -> None:
    scenario("after terminate -> REMOTE_SESSION_NOT_ACTIVE")
    app = ServerApplication()
    alice, bob, rs_id = _setup_approved(app)
    app.dispatch(
        {
            **make_envelope(
                MessageType.REMOTE_TERMINATE,
                correlation_id="corr_term",
                session_id=bob["session_id"],
                actor_user_id=bob["user_id"],
                sequence=5,
            ),
            "payload": {"remote_session_id": rs_id},
        }
    )
    response = _inject(app, alice, rs_id, "key", {"action": "down", "key": "A"}, 6)
    assert response["payload"]["code"] == ErrorCode.REMOTE_SESSION_NOT_ACTIVE.value


def run_unknown_kind() -> None:
    scenario("kind='teleport' -> UNSUPPORTED_INPUT_KIND")
    app = ServerApplication()
    alice, _, rs_id = _setup_approved(app)
    response = _inject(app, alice, rs_id, "teleport", {}, 5)
    assert response["payload"]["code"] == ErrorCode.UNSUPPORTED_INPUT_KIND.value


def run_missing_data_fields() -> None:
    scenario("mouse_move without y -> INVALID_INPUT_PAYLOAD")
    app = ServerApplication()
    alice, _, rs_id = _setup_approved(app)
    response = _inject(app, alice, rs_id, "mouse_move", {"x": 10}, 5)
    assert response["payload"]["code"] == ErrorCode.INVALID_INPUT_PAYLOAD.value


def run_log_captures_all_kinds() -> None:
    scenario("input log records all four kinds with payload intact")
    app = ServerApplication()
    alice, _, rs_id = _setup_approved(app)
    events = [
        ("key", {"action": "up", "key": "Tab"}),
        ("mouse_move", {"x": 50, "y": 75}),
        ("mouse_button", {"action": "up", "button": "right"}),
        ("scroll", {"dx": 3, "dy": 0}),
    ]
    for i, (kind, data) in enumerate(events):
        assert _inject(app, alice, rs_id, kind, data, 5 + i)["type"] == "remote_input_ack"
    log = app.input_service.event_log
    assert [e["kind"] for e in log] == [k for k, _ in events]
    for entry, (kind, data) in zip(log, events):
        assert entry["data"] == data, entry


def main() -> int:
    scenarios = [
        run_basic_key_event,
        run_sequence_monotonic,
        run_target_denied,
        run_unknown_session,
        run_pre_approval_rejected,
        run_terminated_rejected,
        run_unknown_kind,
        run_missing_data_fields,
        run_log_captures_all_kinds,
    ]
    for fn in scenarios:
        fn()
    print(f"\nAll {len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
