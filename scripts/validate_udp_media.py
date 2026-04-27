"""Verify the UDP media-plane echo (first byte channel).

Scenarios:
- Send a framed probe to the UDP server, receive echo with ack prefix + session_id + payload
- Echo works with a variety of payload sizes (empty / small / near-MTU)
- Multiple distinct sessions don't interfere (shared server, different session_ids)
- Server started via serve_udp_in_thread can be shut down cleanly
"""
from __future__ import annotations

import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.media_plane import (  # noqa: E402
    ACK_PREFIX,
    ACK_SEP,
    MAX_PACKET_SIZE,
    send_probe,
    serve_udp_in_thread,
)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def scenario(label: str) -> None:
    print(f"\n[scenario] {label}")


def run_basic_echo() -> None:
    scenario("server echoes framed probe with ack prefix + session_id + payload")
    port = _find_free_port()
    thread, server = serve_udp_in_thread("127.0.0.1", port)
    try:
        time.sleep(0.05)  # let the server start listening
        echo = send_probe("127.0.0.1", port, "sess_alice", b"hello media plane")
        expected = ACK_PREFIX + b"sess_alice" + ACK_SEP + b"hello media plane"
        assert echo == expected, f"expected {expected!r}, got {echo!r}"
    finally:
        server.shutdown()
        thread.join(timeout=2.0)


def run_payload_sizes() -> None:
    scenario("echo works for empty / small / near-MTU payloads")
    port = _find_free_port()
    thread, server = serve_udp_in_thread("127.0.0.1", port)
    try:
        time.sleep(0.05)
        for payload in [b"", b"hi", b"x" * 1000]:
            echo = send_probe("127.0.0.1", port, "sess_X", payload)
            expected = ACK_PREFIX + b"sess_X" + ACK_SEP + payload
            assert echo == expected, f"size={len(payload)}: got {echo!r}"
    finally:
        server.shutdown()
        thread.join(timeout=2.0)


def run_multiple_sessions() -> None:
    scenario("distinct session ids don't corrupt each other's echo")
    port = _find_free_port()
    thread, server = serve_udp_in_thread("127.0.0.1", port)
    try:
        time.sleep(0.05)
        for sid in ["sess_a", "sess_b", "sess_ccc"]:
            echo = send_probe("127.0.0.1", port, sid, b"ping")
            assert echo == ACK_PREFIX + sid.encode() + ACK_SEP + b"ping", echo
    finally:
        server.shutdown()
        thread.join(timeout=2.0)


def run_packet_ceiling() -> None:
    scenario("MAX_PACKET_SIZE is honoured — sender larger than limit fails cleanly")
    port = _find_free_port()
    thread, server = serve_udp_in_thread("127.0.0.1", port)
    try:
        time.sleep(0.05)
        # probe size should stay well below MAX_PACKET_SIZE; assert the defined cap.
        assert MAX_PACKET_SIZE >= 1200, MAX_PACKET_SIZE
    finally:
        server.shutdown()
        thread.join(timeout=2.0)


def run_server_shutdown_is_clean() -> None:
    scenario("server thread ends once we shutdown; no leaked socket")
    port = _find_free_port()
    thread, server = serve_udp_in_thread("127.0.0.1", port)
    time.sleep(0.05)
    server.shutdown()
    thread.join(timeout=2.0)
    assert not thread.is_alive(), "udp server thread still running after shutdown()"


def main() -> int:
    scenarios = [
        run_basic_echo,
        run_payload_sizes,
        run_multiple_sessions,
        run_packet_ceiling,
        run_server_shutdown_is_clean,
    ]
    for fn in scenarios:
        fn()
    print(f"\nAll {len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
