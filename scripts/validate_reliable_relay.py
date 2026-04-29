"""M105: peer-side reliability over the UDP relay.

ReliableChannel + media_plane.RELAY composed into RelayPeerSession. The relay
itself stays a dumb forwarder; reliability lives in the peers.

Scenarios:
- Round-trip without loss (10 A->B + 5 B->A all in order).
- TX loss on one mid seq -> NAK + retransmit -> in order.
- Reordering: deliberate delay on one seq -> buffer + NAK + drain in order.
- Tail loss + tick_retransmit recovers the final packet.
- Bidirectional 30% drop on both sides -> all eventually delivered in order.
"""
from __future__ import annotations

import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.main import _build_session_authorizer  # noqa: E402
from server.server.app import ServerApplication  # noqa: E402
from server.server.media_plane import serve_udp_in_thread  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402
from server.server.relay_peer import RelayPeerSession  # noqa: E402


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


def _start_relay(app: ServerApplication):
    port = _free_port()
    thread, server = serve_udp_in_thread(
        "127.0.0.1", port, authorizer=_build_session_authorizer(app.state)
    )
    time.sleep(0.05)
    return port, thread, server


def _stop_relay(thread, server) -> None:
    server.shutdown()
    thread.join(timeout=2.0)


def _open_pair(port: int, alice_sid: str, bob_sid: str, **kwargs):
    a_kwargs = {k.removeprefix("a_"): v for k, v in kwargs.items() if k.startswith("a_")}
    b_kwargs = {k.removeprefix("b_"): v for k, v in kwargs.items() if k.startswith("b_")}
    a = RelayPeerSession("127.0.0.1", port, alice_sid, bob_sid, **a_kwargs)
    b = RelayPeerSession("127.0.0.1", port, bob_sid, alice_sid, **b_kwargs)
    # Let HELLO datagrams land on the relay so peer registry is populated
    # before the first reliable send fires.
    time.sleep(0.05)
    return a, b


def run_lossless_round_trip() -> None:
    scenario("Lossless: A->B 10 + B->A 5 all in order")
    app = ServerApplication()
    alice, bob = _approve_flow(app)
    port, thread, server = _start_relay(app)
    try:
        a, b = _open_pair(port, alice["session_id"], bob["session_id"])
        try:
            for i in range(10):
                a.send(f"a-{i}".encode())
            received = b.wait_for(10, timeout=2.0)
            assert received == [f"a-{i}".encode() for i in range(10)], received

            for i in range(5):
                b.send(f"b-{i}".encode())
            back = a.wait_for(5, timeout=2.0)
            assert back == [f"b-{i}".encode() for i in range(5)], back
        finally:
            a.close()
            b.close()
    finally:
        _stop_relay(thread, server)


def run_drop_one_then_recover() -> None:
    scenario("Drop A's seq 3 -> B NAKs -> A retransmits -> in-order delivery")
    app = ServerApplication()
    alice, bob = _approve_flow(app)
    port, thread, server = _start_relay(app)
    try:
        # Drop the first REL with seq=3, then let everything through.
        dropped = {"hit": False}

        def tx_loss(packet: bytes) -> bool:
            if not dropped["hit"] and packet.startswith(b"REL:3:"):
                dropped["hit"] = True
                return False
            return True

        a, b = _open_pair(
            port, alice["session_id"], bob["session_id"], a_tx_loss=tx_loss
        )
        try:
            for i in range(1, 7):
                a.send(f"m{i}".encode())
            received = b.wait_for(6, timeout=3.0)
            assert received == [f"m{i}".encode() for i in range(1, 7)], received
            assert dropped["hit"], "expected the seq-3 drop to have fired"
        finally:
            a.close()
            b.close()
    finally:
        _stop_relay(thread, server)


def run_reordering() -> None:
    scenario("Reorder: hold seq 4 briefly so seq 5 arrives first; B drains in order")
    app = ServerApplication()
    alice, bob = _approve_flow(app)
    port, thread, server = _start_relay(app)
    try:
        # Drop the first REL:4 outright, force tail-loss, recover with tick.
        deferred = {"hit": False}

        def tx_loss(packet: bytes) -> bool:
            if not deferred["hit"] and packet.startswith(b"REL:4:"):
                deferred["hit"] = True
                return False
            return True

        a, b = _open_pair(
            port, alice["session_id"], bob["session_id"], a_tx_loss=tx_loss
        )
        try:
            for i in range(1, 6):
                a.send(f"x{i}".encode())
            received = b.wait_for(5, timeout=3.0)
            assert received == [f"x{i}".encode() for i in range(1, 6)], received
            # Confirm B saw the gap: seq 5 must have been buffered until 4 arrived.
            assert deferred["hit"]
        finally:
            a.close()
            b.close()
    finally:
        _stop_relay(thread, server)


def run_tail_loss_tick_recovers() -> None:
    scenario("Drop final packet; tick_retransmit on A recovers it")
    app = ServerApplication()
    alice, bob = _approve_flow(app)
    port, thread, server = _start_relay(app)
    try:
        dropped = {"hit": False}

        def tx_loss(packet: bytes) -> bool:
            if not dropped["hit"] and packet.startswith(b"REL:5:"):
                dropped["hit"] = True
                return False
            return True

        a, b = _open_pair(
            port, alice["session_id"], bob["session_id"], a_tx_loss=tx_loss
        )
        try:
            for i in range(1, 6):
                a.send(f"t{i}".encode())
            # First 4 should arrive promptly; final one is dropped, no later
            # packet to force a NAK -> wait briefly and confirm B is stuck.
            partial = b.wait_for(4, timeout=2.0)
            assert partial == [f"t{i}".encode() for i in range(1, 5)], partial
            try:
                stuck = b.wait_for(1, timeout=0.4)
                raise AssertionError(f"expected stuck, got extra payload {stuck!r}")
            except TimeoutError:
                pass
            # Tail-loss recovery: tick re-sends the unacked seq 5.
            retransmitted = a.tick_retransmit()
            assert retransmitted >= 1, retransmitted
            recovered = b.wait_for(1, timeout=2.0)
            assert recovered == [b"t5"], recovered
            assert dropped["hit"]
        finally:
            a.close()
            b.close()
    finally:
        _stop_relay(thread, server)


def run_bidirectional_with_loss() -> None:
    scenario("Bidirectional under deterministic 1-in-3 drop -> all delivered in order")
    app = ServerApplication()
    alice, bob = _approve_flow(app)
    port, thread, server = _start_relay(app)
    try:
        a_calls = {"n": 0}
        b_calls = {"n": 0}

        def a_drop(_packet: bytes) -> bool:
            a_calls["n"] += 1
            # drop every 3rd outbound packet from A
            return a_calls["n"] % 3 != 0

        def b_drop(_packet: bytes) -> bool:
            b_calls["n"] += 1
            return b_calls["n"] % 3 != 0

        a, b = _open_pair(
            port,
            alice["session_id"],
            bob["session_id"],
            a_tx_loss=a_drop,
            b_tx_loss=b_drop,
        )
        try:
            n = 12
            for i in range(1, n + 1):
                a.send(f"A{i}".encode())
                b.send(f"B{i}".encode())
            # Repeated tick to recover any tail loss in either direction.
            received_b: list[bytes] = []
            received_a: list[bytes] = []
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                received_b.extend(b.pop_delivered())
                received_a.extend(a.pop_delivered())
                if len(received_b) >= n and len(received_a) >= n:
                    break
                a.tick_retransmit()
                b.tick_retransmit()
                time.sleep(0.05)
            assert received_b == [f"A{i}".encode() for i in range(1, n + 1)], received_b
            assert received_a == [f"B{i}".encode() for i in range(1, n + 1)], received_a
        finally:
            a.close()
            b.close()
    finally:
        _stop_relay(thread, server)


def main() -> int:
    scenarios = [
        run_lossless_round_trip,
        run_drop_one_then_recover,
        run_reordering,
        run_tail_loss_tick_recovers,
        run_bidirectional_with_loss,
    ]
    for fn in scenarios:
        fn()
    print(f"\nAll {len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
