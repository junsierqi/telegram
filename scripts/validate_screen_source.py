"""D5: pluggable screen-source drives frame bodies.

Scenarios:
- gradient 24x16 source -> frames carry width=24, height=16, codec=RAW, body
  starts with the deterministic gradient pixel buffer.
- solid 'red' pattern -> every pixel triplet is (255, 0, 0).
- No source attached -> server falls back to _fake_frame_payload (regression).
- Different dimensions propagate end-to-end (8x4 -> frame header reflects that).
- build_test_pattern rejects unknown pattern names.
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
    CODEC_RAW,
    PAYLOAD_HEADER_SIZE,
    _fake_frame_payload,
    parse_frame_payload,
    serve_udp_in_thread,
    subscribe_and_collect,
)
from server.server.protocol import MessageType, make_envelope  # noqa: E402
from server.server.screen_source import (  # noqa: E402
    build_test_pattern,
    make_test_pattern_source,
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _approve_flow(app: ServerApplication) -> dict:
    alice = app.dispatch(
        {
            **make_envelope(
                MessageType.LOGIN_REQUEST, correlation_id="corr_a", sequence=1
            ),
            "payload": {
                "username": "alice",
                "password": "alice_pw",
                "device_id": "dev_alice_win",
            },
        }
    )["payload"]
    bob = app.dispatch(
        {
            **make_envelope(
                MessageType.LOGIN_REQUEST, correlation_id="corr_b", sequence=2
            ),
            "payload": {
                "username": "bob",
                "password": "bob_pw",
                "device_id": "dev_bob_win",
            },
        }
    )["payload"]
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
    app.dispatch(
        {
            **make_envelope(
                MessageType.REMOTE_APPROVE,
                correlation_id="corr_app",
                session_id=bob["session_id"],
                actor_user_id=bob["user_id"],
                sequence=4,
            ),
            "payload": {"remote_session_id": invite["payload"]["remote_session_id"]},
        }
    )
    return alice


def scenario(label: str) -> None:
    print(f"\n[scenario] {label}")


def run_gradient_source() -> None:
    scenario("gradient 24x16 -> frames carry real dims + deterministic pixels")
    app = ServerApplication()
    alice = _approve_flow(app)
    source = make_test_pattern_source(width=24, height=16, pattern="gradient")
    port = _free_port()
    thread, server = serve_udp_in_thread(
        "127.0.0.1",
        port,
        authorizer=_build_session_authorizer(app.state),
        screen_source=source,
    )
    try:
        time.sleep(0.05)
        chunks = subscribe_and_collect(
            "127.0.0.1", port, alice["session_id"], 3, cookie=b"g", timeout=1.5
        )
        expected_pixels = build_test_pattern(24, 16, "gradient")
        for seq, payload in chunks:
            header = parse_frame_payload(payload)
            assert header is not None, payload
            width, height, ts, codec, body = header
            assert (width, height, codec) == (24, 16, CODEC_RAW), header
            assert body.startswith(expected_pixels), body[: len(expected_pixels)]
            assert body.endswith(b"g"), body
            assert ts == seq * 33, (seq, ts)
    finally:
        server.shutdown()
        thread.join(timeout=2.0)


def run_solid_red_source() -> None:
    scenario("solid 'red' pattern -> every RGB triplet is (255, 0, 0)")
    app = ServerApplication()
    alice = _approve_flow(app)
    source = make_test_pattern_source(width=8, height=4, pattern="red")
    port = _free_port()
    thread, server = serve_udp_in_thread(
        "127.0.0.1",
        port,
        authorizer=_build_session_authorizer(app.state),
        screen_source=source,
    )
    try:
        time.sleep(0.05)
        chunks = subscribe_and_collect(
            "127.0.0.1", port, alice["session_id"], 1, cookie=b"", timeout=1.0
        )
        payload = chunks[0][1]
        header = parse_frame_payload(payload)
        assert header is not None
        width, height, _, _, body = header
        assert width == 8 and height == 4
        # first 8x4 RGB triplets = 96 bytes
        pixels = body[: 8 * 4 * 3]
        assert len(pixels) == 96
        for i in range(0, len(pixels), 3):
            assert pixels[i:i + 3] == b"\xff\x00\x00", (i, pixels[i:i + 3])
    finally:
        server.shutdown()
        thread.join(timeout=2.0)


def run_no_source_regression() -> None:
    scenario("no screen_source -> legacy _fake_frame_payload")
    app = ServerApplication()
    alice = _approve_flow(app)
    port = _free_port()
    thread, server = serve_udp_in_thread(
        "127.0.0.1", port, authorizer=_build_session_authorizer(app.state)
    )
    try:
        time.sleep(0.05)
        chunks = subscribe_and_collect(
            "127.0.0.1", port, alice["session_id"], 2, cookie=b"x", timeout=1.0
        )
        for seq, payload in chunks:
            assert payload == _fake_frame_payload(seq, b"x"), (seq, payload)
    finally:
        server.shutdown()
        thread.join(timeout=2.0)


def run_custom_dimensions_propagate() -> None:
    scenario("8x4 source -> frame header reflects 8x4")
    app = ServerApplication()
    alice = _approve_flow(app)
    source = make_test_pattern_source(width=8, height=4, pattern="white")
    port = _free_port()
    thread, server = serve_udp_in_thread(
        "127.0.0.1",
        port,
        authorizer=_build_session_authorizer(app.state),
        screen_source=source,
    )
    try:
        time.sleep(0.05)
        chunks = subscribe_and_collect(
            "127.0.0.1", port, alice["session_id"], 1, cookie=b"", timeout=1.0
        )
        header = parse_frame_payload(chunks[0][1])
        assert header is not None
        width, height, _, codec, _ = header
        assert (width, height, codec) == (8, 4, CODEC_RAW)
    finally:
        server.shutdown()
        thread.join(timeout=2.0)


def run_unknown_pattern_rejected() -> None:
    scenario("build_test_pattern('rainbow') -> ValueError")
    try:
        build_test_pattern(4, 4, "rainbow")
    except ValueError:
        return
    raise AssertionError("expected ValueError for unknown pattern")


def main() -> int:
    scenarios = [
        run_gradient_source,
        run_solid_red_source,
        run_no_source_regression,
        run_custom_dimensions_propagate,
        run_unknown_pattern_rejected,
    ]
    for fn in scenarios:
        fn()
    print(f"\nAll {len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
