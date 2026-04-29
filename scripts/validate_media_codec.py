"""M127 voice/video codec + capture/playback abstraction.

Scenarios:
- PassThroughCodec round-trip: encode then decode == original PCM.
- OpusCodec(dry_run=True): identity behaviour so call flow tests can run.
- OpusCodec(dry_run=False, no libopus) raises PermissionError citing PA-012.
- build_audio_payload + parse_audio_payload round-trip header fields.
- SyntheticAudioSource produces N frames, then None (exhausted).
- End-to-end: SyntheticAudioSource -> encode -> reliable_relay -> decode ->
  MemoryAudioSink yields the same PCM frames in order, and AEAD wire bytes
  reveal no plaintext PCM.
"""
from __future__ import annotations

import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.main import _build_session_authorizer  # noqa: E402
from server.server.app import ServerApplication  # noqa: E402
from server.server.media_codec import (  # noqa: E402
    AUDIO_HEADER_SIZE, CODEC_PASSTHROUGH,
    OpusCodec, PassThroughCodec,
    build_audio_payload, parse_audio_payload,
)
from server.server.media_crypto import generate_key_b64  # noqa: E402
from server.server.media_io import (  # noqa: E402
    MemoryAudioSink, SyntheticAudioSource, drain,
)
from server.server.media_plane import serve_udp_in_thread  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402
from server.server.relay_peer import RelayPeerSession  # noqa: E402


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _login(app, username, password, device_id, seq):
    return app.dispatch({
        **make_envelope(MessageType.LOGIN_REQUEST, correlation_id=f"corr_{username}", sequence=seq),
        "payload": {"username": username, "password": password, "device_id": device_id},
    })["payload"]


def _make_call(app, alice, bob):
    inv = app.dispatch({
        **make_envelope(MessageType.CALL_INVITE_REQUEST, correlation_id="ci",
                        session_id=alice["session_id"], actor_user_id=alice["user_id"], sequence=3),
        "payload": {"callee_user_id": bob["user_id"], "callee_device_id": bob["device_id"], "kind": "audio"},
    })
    call_id = inv["payload"]["call_id"]
    app.dispatch({
        **make_envelope(MessageType.CALL_ACCEPT_REQUEST, correlation_id="ca",
                        session_id=bob["session_id"], actor_user_id=bob["user_id"], sequence=4),
        "payload": {"call_id": call_id},
    })
    rv = app.dispatch({
        **make_envelope(MessageType.CALL_RENDEZVOUS_REQUEST, correlation_id="rv",
                        session_id=alice["session_id"], actor_user_id=alice["user_id"], sequence=5),
        "payload": {"call_id": call_id},
    })
    return call_id, rv["payload"]["relay_key_b64"]


def scenario(label):
    print(f"\n[scenario] {label}")


def run_passthrough_round_trip():
    scenario("PassThroughCodec encode/decode is identity")
    codec = PassThroughCodec()
    pcm = b"\x01\x02\x03\x04" * 240
    assert codec.decode(codec.encode(pcm)) == pcm


def run_opus_dry_run_identity():
    scenario("OpusCodec(dry_run=True) is identity (no PA-012 yet)")
    codec = OpusCodec(dry_run=True)
    pcm = b"hello pcm"
    assert codec.decode(codec.encode(pcm)) == pcm


def run_opus_real_path_raises():
    scenario("OpusCodec(dry_run=False) raises PermissionError citing PA-012")
    codec = OpusCodec(dry_run=False)
    try:
        codec.encode(b"x")
    except PermissionError as exc:
        assert "PA-012" in str(exc), str(exc)
    else:
        raise AssertionError("expected PermissionError")


def run_audio_payload_header_round_trip():
    scenario("build_audio_payload + parse_audio_payload round-trip header fields")
    encoder = PassThroughCodec(sample_rate=48_000, channels=2, samples_per_frame=960)
    payload = build_audio_payload(encoder, b"PCMBYTES", sequence=42)
    assert len(payload) == AUDIO_HEADER_SIZE + 8
    parsed = parse_audio_payload(payload)
    assert parsed is not None
    codec_id, channels, rate, samples, sequence, body = parsed
    assert codec_id == CODEC_PASSTHROUGH
    assert channels == 2
    assert rate == 48_000
    assert samples == 960
    assert sequence == 42
    assert body == b"PCMBYTES"


def run_synthetic_source_finishes():
    scenario("SyntheticAudioSource produces exactly N frames then None")
    src = SyntheticAudioSource(frame_count=5, samples_per_frame=240, channels=1)
    frames = list(drain(src))
    assert len(frames) == 5
    for f in frames:
        assert len(f) == 240 * 2  # 16-bit mono
    assert src.next_frame() is None


def run_end_to_end_codec_relay_aead():
    scenario("E2E: synthetic source -> encode -> AEAD relay -> decode -> sink")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_codec", 1)
    bob = _login(app, "bob", "bob_pw", "dev_bob_codec", 2)
    call_id, relay_key = _make_call(app, alice, bob)
    assert relay_key

    port = _free_port()
    thread, server = serve_udp_in_thread(
        "127.0.0.1", port, authorizer=_build_session_authorizer(app.state)
    )
    try:
        time.sleep(0.05)
        encoder = PassThroughCodec(samples_per_frame=240)
        decoder = PassThroughCodec(samples_per_frame=240)
        captured = []
        def a_observe(packet):
            captured.append(packet)
            return True
        a = RelayPeerSession("127.0.0.1", port, alice["session_id"], bob["session_id"],
                             relay_key_b64=relay_key, tx_loss=a_observe)
        b = RelayPeerSession("127.0.0.1", port, bob["session_id"], alice["session_id"],
                             relay_key_b64=relay_key)
        time.sleep(0.05)
        try:
            sink = MemoryAudioSink(samples_per_frame=240)
            src = SyntheticAudioSource(frame_count=8, samples_per_frame=240, channels=1)

            sent_pcm = []
            for seq, frame in enumerate(drain(src), start=1):
                sent_pcm.append(frame)
                a.send(build_audio_payload(encoder, frame, seq))

            received = b.wait_for(len(sent_pcm), timeout=3.0)
            for raw in received:
                parsed = parse_audio_payload(raw)
                assert parsed is not None
                pcm = decoder.decode(parsed[5])
                sink.feed(pcm)
            assert sink.frames == sent_pcm, "decoded frames must match originals in order"

            # AEAD plaintext-leak guard: scan captured (sealed) bytes; each
            # PCM frame's first 6 bytes must NOT appear verbatim on the wire.
            wire = b"".join(captured)
            for f in sent_pcm:
                if len(f) >= 6:
                    assert f[:6] not in wire, "PCM prefix leaked through AEAD"
        finally:
            a.close()
            b.close()
        # Hang up so call leaves the active state.
        app.dispatch({
            **make_envelope(MessageType.CALL_END_REQUEST, correlation_id="ce",
                            session_id=alice["session_id"], actor_user_id=alice["user_id"], sequence=10),
            "payload": {"call_id": call_id},
        })
    finally:
        server.shutdown()
        thread.join(timeout=2.0)


def main() -> int:
    scenarios = [
        run_passthrough_round_trip,
        run_opus_dry_run_identity,
        run_opus_real_path_raises,
        run_audio_payload_header_round_trip,
        run_synthetic_source_finishes,
        run_end_to_end_codec_relay_aead,
    ]
    for fn in scenarios:
        fn()
    print(f"\nAll {len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
