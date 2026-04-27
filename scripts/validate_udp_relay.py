"""D7: server relays UDP datagrams between peers of an active remote session.

Scenarios:
- A registers (HELLO) and B registers; A sends RELAY:B:<payload> -> B receives envelope(sid_len|A_sid|payload)
- Bidirectional: B also sends RELAY:A and A receives
- Unknown target session_id -> silent drop (no feedback to sender)
- Unauthorized sender (logged-in but no approved remote) -> silent drop, B never sees anything
- Malformed RELAY (no target separator) -> silent drop
- Registry refreshed by each authorized packet (address change is picked up)
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
    MAX_PACKET_SIZE,
    build_hello_payload,
    build_relay_payload,
    frame,
    open_peer_socket,
    send_hello,
    serve_udp_in_thread,
)
from server.server.media_plane import _unframe as unwrap_envelope  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _login(app: ServerApplication, username: str, password: str, device_id: str, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.LOGIN_REQUEST, correlation_id=f"corr_{username}", sequence=seq
            ),
            "payload": {"username": username, "password": password, "device_id": device_id},
        }
    )["payload"]


def _approve_flow(app: ServerApplication) -> tuple[dict, dict]:
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
    return alice, bob


def scenario(label: str) -> None:
    print(f"\n[scenario] {label}")


def run_unidirectional_relay() -> None:
    scenario("A HELLO+RELAY -> B receives envelope(A_sid, body)")
    app = ServerApplication()
    alice, bob = _approve_flow(app)
    port = _free_port()
    thread, server = serve_udp_in_thread(
        "127.0.0.1", port, authorizer=_build_session_authorizer(app.state)
    )
    try:
        time.sleep(0.05)
        a = open_peer_socket("127.0.0.1", port, alice["session_id"], timeout=1.0)
        b = open_peer_socket("127.0.0.1", port, bob["session_id"], timeout=1.0)
        # Let HELLO datagrams land.
        time.sleep(0.05)

        a.sendto(frame(alice["session_id"], build_relay_payload(bob["session_id"], b"hello bob")),
                 ("127.0.0.1", port))
        data, _ = b.recvfrom(MAX_PACKET_SIZE)
        sender_sid, body = unwrap_envelope(data)
        assert sender_sid.decode() == alice["session_id"], sender_sid
        assert body == b"hello bob", body
        a.close()
        b.close()
    finally:
        server.shutdown()
        thread.join(timeout=2.0)


def run_bidirectional_relay() -> None:
    scenario("B relays back to A over the same channel")
    app = ServerApplication()
    alice, bob = _approve_flow(app)
    port = _free_port()
    thread, server = serve_udp_in_thread(
        "127.0.0.1", port, authorizer=_build_session_authorizer(app.state)
    )
    try:
        time.sleep(0.05)
        a = open_peer_socket("127.0.0.1", port, alice["session_id"], timeout=1.0)
        b = open_peer_socket("127.0.0.1", port, bob["session_id"], timeout=1.0)
        time.sleep(0.05)

        a.sendto(frame(alice["session_id"], build_relay_payload(bob["session_id"], b"ping")),
                 ("127.0.0.1", port))
        data, _ = b.recvfrom(MAX_PACKET_SIZE)
        _, body = unwrap_envelope(data)
        assert body == b"ping"

        b.sendto(frame(bob["session_id"], build_relay_payload(alice["session_id"], b"pong")),
                 ("127.0.0.1", port))
        data, _ = a.recvfrom(MAX_PACKET_SIZE)
        sender_sid, body = unwrap_envelope(data)
        assert sender_sid.decode() == bob["session_id"], sender_sid
        assert body == b"pong"
        a.close()
        b.close()
    finally:
        server.shutdown()
        thread.join(timeout=2.0)


def run_unknown_target_dropped() -> None:
    scenario("target not in registry -> silent drop (no reply to A, nothing at sink)")
    app = ServerApplication()
    alice, _ = _approve_flow(app)
    port = _free_port()
    thread, server = serve_udp_in_thread(
        "127.0.0.1", port, authorizer=_build_session_authorizer(app.state)
    )
    try:
        time.sleep(0.05)
        a = open_peer_socket("127.0.0.1", port, alice["session_id"], timeout=0.4)
        time.sleep(0.05)
        a.sendto(frame(alice["session_id"], build_relay_payload("sess_unknown", b"data")),
                 ("127.0.0.1", port))
        try:
            data, _ = a.recvfrom(MAX_PACKET_SIZE)
            raise AssertionError(f"expected no reply, got {data!r}")
        except socket.timeout:
            pass
        a.close()
    finally:
        server.shutdown()
        thread.join(timeout=2.0)


def run_unauthorized_sender_silent() -> None:
    scenario("logged-in but no approved remote -> B never receives anything")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)  # no approve
    bob = _login(app, "bob", "bob_pw", "dev_bob_win", 2)
    # Manually approve only bob side would be weird — here neither has an approved session
    port = _free_port()
    thread, server = serve_udp_in_thread(
        "127.0.0.1", port, authorizer=_build_session_authorizer(app.state)
    )
    try:
        time.sleep(0.05)
        # A and B cannot even register because authorizer rejects them.
        a = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        a.settimeout(0.4)
        a.sendto(frame(alice["session_id"], build_hello_payload()), ("127.0.0.1", port))
        b = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        b.settimeout(0.4)
        b.sendto(frame(bob["session_id"], build_hello_payload()), ("127.0.0.1", port))
        time.sleep(0.05)

        a.sendto(frame(alice["session_id"], build_relay_payload(bob["session_id"], b"x")),
                 ("127.0.0.1", port))
        try:
            data, _ = b.recvfrom(MAX_PACKET_SIZE)
            raise AssertionError(f"expected silent drop, got {data!r}")
        except socket.timeout:
            pass
        a.close()
        b.close()
    finally:
        server.shutdown()
        thread.join(timeout=2.0)


def run_malformed_relay_dropped() -> None:
    scenario("RELAY with no separator -> silent drop")
    app = ServerApplication()
    alice, bob = _approve_flow(app)
    port = _free_port()
    thread, server = serve_udp_in_thread(
        "127.0.0.1", port, authorizer=_build_session_authorizer(app.state)
    )
    try:
        time.sleep(0.05)
        a = open_peer_socket("127.0.0.1", port, alice["session_id"], timeout=0.4)
        b = open_peer_socket("127.0.0.1", port, bob["session_id"], timeout=0.4)
        time.sleep(0.05)

        # "RELAY:" with no target:body separator
        a.sendto(frame(alice["session_id"], b"RELAY:no_separator_here"),
                 ("127.0.0.1", port))
        try:
            data, _ = b.recvfrom(MAX_PACKET_SIZE)
            raise AssertionError(f"expected drop, got {data!r}")
        except socket.timeout:
            pass
        a.close()
        b.close()
    finally:
        server.shutdown()
        thread.join(timeout=2.0)


def run_registry_refreshed() -> None:
    scenario("Peer's address is refreshed on each authorized packet")
    app = ServerApplication()
    alice, bob = _approve_flow(app)
    port = _free_port()
    thread, server = serve_udp_in_thread(
        "127.0.0.1", port, authorizer=_build_session_authorizer(app.state)
    )
    try:
        time.sleep(0.05)
        send_hello("127.0.0.1", port, alice["session_id"])
        send_hello("127.0.0.1", port, bob["session_id"])
        time.sleep(0.05)
        with server._peer_registry_lock:
            alice_addr_first = server.peer_registry.get(alice["session_id"])
        assert alice_addr_first is not None

        # Now "alice" speaks from a different ephemeral port — expect the registry entry to change.
        new_a = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        new_a.sendto(frame(alice["session_id"], build_hello_payload()), ("127.0.0.1", port))
        time.sleep(0.05)
        with server._peer_registry_lock:
            alice_addr_second = server.peer_registry.get(alice["session_id"])
        assert alice_addr_second is not None
        assert alice_addr_second != alice_addr_first, (alice_addr_first, alice_addr_second)
        new_a.close()
    finally:
        server.shutdown()
        thread.join(timeout=2.0)


def main() -> int:
    scenarios = [
        run_unidirectional_relay,
        run_bidirectional_relay,
        run_unknown_target_dropped,
        run_unauthorized_sender_silent,
        run_malformed_relay_dropped,
        run_registry_refreshed,
    ]
    for fn in scenarios:
        fn()
    print(f"\nAll {len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
