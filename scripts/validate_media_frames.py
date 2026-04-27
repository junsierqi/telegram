"""D2: structured frame_chunk stream replacing pure echo.

Scenarios:
- subscribe for N=5 -> receive exactly 5 frame_chunks, seq 1..5, payload matches deterministic builder
- subscribe for N=0 -> no frames (safety — authorized but nothing emitted)
- subscribe with cookie -> cookie echoed inside each frame's payload
- subscribe payload triggers stream mode; legacy echo payload still returns ack (backward compat)
- unauthorized subscribe -> silent drop (integrates with D1's authorizer)
- subscribe count cap MAX_FRAME_COUNT is respected
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
    CODEC_RAW,
    MAX_FRAME_COUNT,
    PAYLOAD_HEADER_SIZE,
    _fake_frame_body,
    _fake_frame_payload,
    build_subscribe_payload,
    parse_frame_payload,
    send_probe,
    serve_udp_in_thread,
    subscribe_and_collect,
)
from server.server.protocol import MessageType, make_envelope  # noqa: E402


def _free_port() -> int:
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
    return response["payload"]


def _approve_flow(app: ServerApplication) -> tuple[dict, dict]:
    """Login alice + bob, invite + approve — gives us two sessions in an active remote session."""
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
                correlation_id="corr_appr",
                session_id=bob["session_id"],
                actor_user_id=bob["user_id"],
                sequence=4,
            ),
            "payload": {"remote_session_id": rs_id},
        }
    )
    return alice, bob


def run_basic_stream() -> None:
    scenario("subscribe for N=5 -> exactly 5 chunks, seq 1..5, payloads match builder")
    app = ServerApplication()
    alice, _ = _approve_flow(app)
    port = _free_port()
    thread, server = serve_udp_in_thread(
        "127.0.0.1", port, authorizer=_build_session_authorizer(app.state)
    )
    try:
        time.sleep(0.05)
        chunks = subscribe_and_collect(
            "127.0.0.1", port, alice["session_id"], 5, cookie=b"demo", timeout=1.5
        )
        assert len(chunks) == 5, chunks
        for i, (seq, payload) in enumerate(chunks, start=1):
            assert seq == i, (i, chunks)
            assert payload == _fake_frame_payload(i, b"demo"), (i, payload)
            header = parse_frame_payload(payload)
            assert header is not None, payload
            width, height, ts_ms, codec, body = header
            assert (width, height, codec) == (640, 360, CODEC_RAW), header
            assert ts_ms == i * 33, header
            assert body == _fake_frame_body(i, b"demo"), body
    finally:
        server.shutdown()
        thread.join(timeout=2.0)


def run_header_sizes_and_parser_roundtrip() -> None:
    scenario("parse_frame_payload round-trips width/height/ts/codec/body")
    app = ServerApplication()
    alice, _ = _approve_flow(app)
    port = _free_port()
    thread, server = serve_udp_in_thread(
        "127.0.0.1", port, authorizer=_build_session_authorizer(app.state)
    )
    try:
        time.sleep(0.05)
        chunks = subscribe_and_collect(
            "127.0.0.1", port, alice["session_id"], 1, cookie=b"C", timeout=1.0
        )
        assert len(chunks) == 1
        _, payload = chunks[0]
        assert len(payload) >= PAYLOAD_HEADER_SIZE
        header = parse_frame_payload(payload)
        assert header is not None, payload
        # malformed (too short) payload returns None
        assert parse_frame_payload(b"\x00" * (PAYLOAD_HEADER_SIZE - 1)) is None
    finally:
        server.shutdown()
        thread.join(timeout=2.0)


def run_zero_frames_is_silent() -> None:
    scenario("subscribe for N=0 -> no frames, timeout on recv (no stray ack)")
    app = ServerApplication()
    alice, _ = _approve_flow(app)
    port = _free_port()
    thread, server = serve_udp_in_thread(
        "127.0.0.1", port, authorizer=_build_session_authorizer(app.state)
    )
    try:
        time.sleep(0.05)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.5)
            from server.server.media_plane import frame as envelope_frame
            sock.sendto(
                envelope_frame(alice["session_id"], build_subscribe_payload(0)),
                ("127.0.0.1", port),
            )
            try:
                data, _ = sock.recvfrom(4096)
                raise AssertionError(f"expected timeout, got data={data!r}")
            except socket.timeout:
                pass
    finally:
        server.shutdown()
        thread.join(timeout=2.0)


def run_cookie_round_trip() -> None:
    scenario("cookie bytes reappear inside every frame payload")
    app = ServerApplication()
    alice, _ = _approve_flow(app)
    port = _free_port()
    thread, server = serve_udp_in_thread(
        "127.0.0.1", port, authorizer=_build_session_authorizer(app.state)
    )
    try:
        time.sleep(0.05)
        cookie = b"stream-42"
        chunks = subscribe_and_collect("127.0.0.1", port, alice["session_id"], 3, cookie=cookie, timeout=1.5)
        for seq, payload in chunks:
            assert payload.endswith(cookie), (seq, payload, cookie)
    finally:
        server.shutdown()
        thread.join(timeout=2.0)


def run_legacy_echo_still_works() -> None:
    scenario("non-subscribe payload still gets the ack: echo (backward compat)")
    app = ServerApplication()
    alice, _ = _approve_flow(app)
    port = _free_port()
    thread, server = serve_udp_in_thread(
        "127.0.0.1", port, authorizer=_build_session_authorizer(app.state)
    )
    try:
        time.sleep(0.05)
        echo = send_probe("127.0.0.1", port, alice["session_id"], b"plain echo", timeout=1.0)
        assert echo == ACK_PREFIX + alice["session_id"].encode() + ACK_SEP + b"plain echo", echo
    finally:
        server.shutdown()
        thread.join(timeout=2.0)


def run_unauthorized_subscribe_silently_drops() -> None:
    scenario("subscribe from a session without an approved remote -> silent drop")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)  # no invite/approve
    port = _free_port()
    thread, server = serve_udp_in_thread(
        "127.0.0.1", port, authorizer=_build_session_authorizer(app.state)
    )
    try:
        time.sleep(0.05)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.6)
            from server.server.media_plane import frame as envelope_frame
            sock.sendto(
                envelope_frame(alice["session_id"], build_subscribe_payload(3)),
                ("127.0.0.1", port),
            )
            try:
                data, _ = sock.recvfrom(4096)
                raise AssertionError(f"expected drop, got data={data!r}")
            except socket.timeout:
                pass
    finally:
        server.shutdown()
        thread.join(timeout=2.0)


def run_count_cap_respected() -> None:
    scenario(f"subscribe count > MAX_FRAME_COUNT -> capped at {MAX_FRAME_COUNT}")
    app = ServerApplication()
    alice, _ = _approve_flow(app)
    port = _free_port()
    thread, server = serve_udp_in_thread(
        "127.0.0.1", port, authorizer=_build_session_authorizer(app.state)
    )
    try:
        time.sleep(0.05)
        # Ask directly via the raw envelope so we bypass client-side bounds check.
        from server.server.media_plane import SUBSCRIBE_PREFIX, frame as envelope_frame
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(2.0)
            sock.sendto(
                envelope_frame(
                    alice["session_id"],
                    SUBSCRIBE_PREFIX + b"9999:demo",
                ),
                ("127.0.0.1", port),
            )
            received = 0
            try:
                while True:
                    sock.settimeout(0.6)
                    sock.recvfrom(4096)
                    received += 1
            except socket.timeout:
                pass
            assert received == MAX_FRAME_COUNT, (received, MAX_FRAME_COUNT)
    finally:
        server.shutdown()
        thread.join(timeout=5.0)


def main() -> int:
    scenarios = [
        run_basic_stream,
        run_header_sizes_and_parser_roundtrip,
        run_zero_frames_is_silent,
        run_cookie_round_trip,
        run_legacy_echo_still_works,
        run_unauthorized_subscribe_silently_drops,
        run_count_cap_respected,
    ]
    for fn in scenarios:
        fn()
    print(f"\nAll {len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
