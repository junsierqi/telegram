"""Per-session authorization for the UDP media plane.

Rules being verified:
- Unknown session_id -> packet dropped silently (probe times out).
- Logged-in session but no approved remote session -> dropped.
- Logged-in + target participant in an active remote session -> echo works.
- After terminate -> dropped again (state leaves the active set).
- Raw ThreadedUdpMediaServer with no authorizer still accepts everything (regression guard).
"""
from __future__ import annotations

import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.main import _build_session_authorizer  # noqa: E402
from server.server.app import ServerApplication  # noqa: E402
from server.server.media_plane import (  # noqa: E402
    ACK_PREFIX,
    ACK_SEP,
    send_probe,
    serve_udp_in_thread,
)
from server.server.protocol import MessageType, make_envelope  # noqa: E402


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def scenario(label: str) -> None:
    print(f"\n[scenario] {label}")


def _login(app: ServerApplication, username: str, password: str, device_id: str, seq: int) -> dict:
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


def _invite(app: ServerApplication, alice: dict, seq: int) -> str:
    response = app.dispatch(
        {
            **make_envelope(
                MessageType.REMOTE_INVITE,
                correlation_id=f"corr_invite_{seq}",
                session_id=alice["session_id"],
                actor_user_id=alice["user_id"],
                sequence=seq,
            ),
            "payload": {
                "requester_device_id": alice["device_id"],
                "target_device_id": "dev_bob_win",
            },
        }
    )
    assert response["type"] == "remote_session_state", response
    return response["payload"]["remote_session_id"]


def _approve(app: ServerApplication, bob: dict, rs_id: str, seq: int) -> None:
    response = app.dispatch(
        {
            **make_envelope(
                MessageType.REMOTE_APPROVE,
                correlation_id=f"corr_approve_{seq}",
                session_id=bob["session_id"],
                actor_user_id=bob["user_id"],
                sequence=seq,
            ),
            "payload": {"remote_session_id": rs_id},
        }
    )
    assert response["type"] == "remote_relay_assignment", response


def _terminate(app: ServerApplication, bob: dict, rs_id: str, seq: int) -> None:
    response = app.dispatch(
        {
            **make_envelope(
                MessageType.REMOTE_TERMINATE,
                correlation_id=f"corr_term_{seq}",
                session_id=bob["session_id"],
                actor_user_id=bob["user_id"],
                sequence=seq,
            ),
            "payload": {"remote_session_id": rs_id},
        }
    )
    assert response["type"] == "remote_session_terminated", response


def _expect_timeout(host: str, port: int, session_id: str) -> None:
    try:
        send_probe(host, port, session_id, b"should be dropped", timeout=0.6)
    except socket.timeout:
        return
    raise AssertionError(f"expected silent drop for session_id={session_id!r} but got a response")


def _expect_ack(host: str, port: int, session_id: str, payload: bytes) -> None:
    echo = send_probe(host, port, session_id, payload, timeout=1.0)
    expected = ACK_PREFIX + session_id.encode() + ACK_SEP + payload
    assert echo == expected, f"expected {expected!r}, got {echo!r}"


def run_unknown_session_dropped() -> None:
    scenario("unknown session_id -> silently dropped")
    app = ServerApplication()
    port = _find_free_port()
    thread, server = serve_udp_in_thread(
        "127.0.0.1", port, authorizer=_build_session_authorizer(app.state)
    )
    try:
        time.sleep(0.05)
        _expect_timeout("127.0.0.1", port, "sess_never_existed")
    finally:
        server.shutdown()
        thread.join(timeout=2.0)


def run_logged_in_but_no_remote_dropped() -> None:
    scenario("logged-in without an approved remote session -> dropped")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    port = _find_free_port()
    thread, server = serve_udp_in_thread(
        "127.0.0.1", port, authorizer=_build_session_authorizer(app.state)
    )
    try:
        time.sleep(0.05)
        _expect_timeout("127.0.0.1", port, alice["session_id"])
    finally:
        server.shutdown()
        thread.join(timeout=2.0)


def run_authorized_after_approve() -> None:
    scenario("logged-in + participant in approved remote session -> echo works")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    bob = _login(app, "bob", "bob_pw", "dev_bob_win", 2)
    rs_id = _invite(app, alice, 3)
    _approve(app, bob, rs_id, 4)

    port = _find_free_port()
    thread, server = serve_udp_in_thread(
        "127.0.0.1", port, authorizer=_build_session_authorizer(app.state)
    )
    try:
        time.sleep(0.05)
        _expect_ack("127.0.0.1", port, alice["session_id"], b"alice payload")
        _expect_ack("127.0.0.1", port, bob["session_id"], b"bob payload")
    finally:
        server.shutdown()
        thread.join(timeout=2.0)


def run_deauthorized_after_terminate() -> None:
    scenario("terminate moves session out of active set -> probes drop again")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    bob = _login(app, "bob", "bob_pw", "dev_bob_win", 2)
    rs_id = _invite(app, alice, 3)
    _approve(app, bob, rs_id, 4)

    port = _find_free_port()
    thread, server = serve_udp_in_thread(
        "127.0.0.1", port, authorizer=_build_session_authorizer(app.state)
    )
    try:
        time.sleep(0.05)
        _expect_ack("127.0.0.1", port, alice["session_id"], b"still approved")
        _terminate(app, bob, rs_id, 5)
        _expect_timeout("127.0.0.1", port, alice["session_id"])
        _expect_timeout("127.0.0.1", port, bob["session_id"])
    finally:
        server.shutdown()
        thread.join(timeout=2.0)


def run_no_authorizer_still_echoes() -> None:
    scenario("no authorizer passed -> server accepts all (backward compat with validate_udp_media.py)")
    port = _find_free_port()
    thread, server = serve_udp_in_thread("127.0.0.1", port)
    try:
        time.sleep(0.05)
        _expect_ack("127.0.0.1", port, "anything", b"still works")
    finally:
        server.shutdown()
        thread.join(timeout=2.0)


def main() -> int:
    scenarios = [
        run_unknown_session_dropped,
        run_logged_in_but_no_remote_dropped,
        run_authorized_after_approve,
        run_deauthorized_after_terminate,
        run_no_authorizer_still_echoes,
    ]
    for fn in scenarios:
        fn()
    print(f"\nAll {len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
