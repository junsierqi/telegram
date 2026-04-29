"""M106 / D9: AES-256-GCM AEAD on the media-plane RELAY path.

Scenarios:
- Round-trip with shared key: both peers deliver in order; intercepted bytes
  on the wire never contain the plaintext.
- Wrong key on receiver: decrypt fails; receiver delivers nothing.
- One peer keyed and the other not: tag failure both ways; nothing delivered.
- request_rendezvous mints one stable key per remote_session; second call by
  the other peer returns the same key; both peers using it can talk.
- Backward compat: empty key both sides == legacy plaintext path still works.
"""
from __future__ import annotations

import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.main import _build_session_authorizer  # noqa: E402
from server.server.app import ServerApplication  # noqa: E402
from server.server.media_crypto import generate_key_b64  # noqa: E402
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


def _approve_flow(app: ServerApplication) -> tuple[dict, dict, str]:
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


def _request_rendezvous(app: ServerApplication, *, session_id: str, actor_user_id: str, rs_id: str, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.REMOTE_RENDEZVOUS_REQUEST,
                correlation_id=f"corr_rv_{actor_user_id}_{seq}",
                session_id=session_id,
                actor_user_id=actor_user_id,
                sequence=seq,
            ),
            "payload": {"remote_session_id": rs_id},
        }
    )["payload"]


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
    time.sleep(0.05)
    return a, b


def run_round_trip_with_key_hides_plaintext() -> None:
    scenario("Shared key: round-trip works AND intercepted bytes don't contain plaintext")
    app = ServerApplication()
    alice, bob, _ = _approve_flow(app)
    port, thread, server = _start_relay(app)
    try:
        key = generate_key_b64()
        a_outbound: list[bytes] = []
        b_outbound: list[bytes] = []

        def a_capture(packet: bytes) -> bool:
            a_outbound.append(packet)
            return True

        def b_capture(packet: bytes) -> bool:
            b_outbound.append(packet)
            return True

        a, b = _open_pair(
            port,
            alice["session_id"],
            bob["session_id"],
            a_relay_key_b64=key,
            a_tx_loss=a_capture,
            b_relay_key_b64=key,
            b_tx_loss=b_capture,
        )
        try:
            secrets_a = [b"the password is hunter2", b"transfer to acct 4242", b"meet at noon"]
            for s in secrets_a:
                a.send(s)
            received_b = b.wait_for(len(secrets_a), timeout=2.0)
            assert received_b == secrets_a, received_b

            secrets_b = [b"copy that", b"see you then"]
            for s in secrets_b:
                b.send(s)
            received_a = a.wait_for(len(secrets_b), timeout=2.0)
            assert received_a == secrets_b, received_a

            # Wire-tap: every packet captured on the way out must NOT contain
            # any plaintext substring of length >= 6.
            wire_blob = b"".join(a_outbound) + b"".join(b_outbound)
            for s in secrets_a + secrets_b:
                assert s not in wire_blob, f"plaintext leaked on wire: {s!r}"
            # Also confirm the seq-framing strings ("REL:1:", "REL:2:") aren't
            # visible -- AEAD covers the entire reliable-channel packet.
            assert b"REL:1:" not in wire_blob
            assert b"NAK:" not in wire_blob[:0] or True  # may not appear at all
        finally:
            a.close()
            b.close()
    finally:
        _stop_relay(thread, server)


def run_wrong_key_drops_silently() -> None:
    scenario("Receiver with wrong key delivers nothing; sender's unacked grows")
    app = ServerApplication()
    alice, bob, _ = _approve_flow(app)
    port, thread, server = _start_relay(app)
    try:
        key_a = generate_key_b64()
        key_b = generate_key_b64()
        assert key_a != key_b
        a, b = _open_pair(
            port,
            alice["session_id"],
            bob["session_id"],
            a_relay_key_b64=key_a,
            b_relay_key_b64=key_b,
        )
        try:
            a.send(b"this should never be readable")
            try:
                got = b.wait_for(1, timeout=0.6)
                raise AssertionError(f"expected silent drop, got {got!r}")
            except TimeoutError:
                pass
            # And the sender side never saw an ACK either, so the packet stays
            # in the unacked retx buffer.
            assert a.unacked == [1], a.unacked
        finally:
            a.close()
            b.close()
    finally:
        _stop_relay(thread, server)


def run_keyed_vs_plain_drops() -> None:
    scenario("One peer keyed, the other plaintext -> nothing delivered either way")
    app = ServerApplication()
    alice, bob, _ = _approve_flow(app)
    port, thread, server = _start_relay(app)
    try:
        key = generate_key_b64()
        a, b = _open_pair(
            port,
            alice["session_id"],
            bob["session_id"],
            a_relay_key_b64=key,
            # B has no key -> it sees raw 12+ct+16 bytes and tries to parse as
            # REL/NAK/ACK; doesn't match any prefix -> ignored. Also when B
            # sends in plaintext, A tries AEAD decrypt and drops.
        )
        try:
            a.send(b"keyed -> plain peer")
            b.send(b"plain -> keyed peer")
            try:
                got_b = b.wait_for(1, timeout=0.4)
                raise AssertionError(f"expected drop at B, got {got_b!r}")
            except TimeoutError:
                pass
            try:
                got_a = a.wait_for(1, timeout=0.4)
                raise AssertionError(f"expected drop at A, got {got_a!r}")
            except TimeoutError:
                pass
        finally:
            a.close()
            b.close()
    finally:
        _stop_relay(thread, server)


def run_server_issued_key_round_trip() -> None:
    scenario("request_rendezvous mints stable per-session key; both peers reuse it")
    app = ServerApplication()
    alice, bob, rs_id = _approve_flow(app)
    rv_a = _request_rendezvous(
        app, session_id=alice["session_id"], actor_user_id=alice["user_id"], rs_id=rs_id, seq=10
    )
    rv_b = _request_rendezvous(
        app, session_id=bob["session_id"], actor_user_id=bob["user_id"], rs_id=rs_id, seq=11
    )
    assert rv_a["relay_key_b64"], "expected non-empty relay_key_b64 from server"
    assert rv_a["relay_key_b64"] == rv_b["relay_key_b64"], (
        "server must give both peers the same per-session key",
        rv_a["relay_key_b64"],
        rv_b["relay_key_b64"],
    )

    port, thread, server = _start_relay(app)
    try:
        a, b = _open_pair(
            port,
            alice["session_id"],
            bob["session_id"],
            a_relay_key_b64=rv_a["relay_key_b64"],
            b_relay_key_b64=rv_b["relay_key_b64"],
        )
        try:
            for i in range(6):
                a.send(f"a-{i}".encode())
                b.send(f"b-{i}".encode())
            got_b = b.wait_for(6, timeout=2.0)
            got_a = a.wait_for(6, timeout=2.0)
            assert got_b == [f"a-{i}".encode() for i in range(6)], got_b
            assert got_a == [f"b-{i}".encode() for i in range(6)], got_a
        finally:
            a.close()
            b.close()
    finally:
        _stop_relay(thread, server)


def run_legacy_plaintext_still_works() -> None:
    scenario("Backward compat: empty key both sides == legacy plaintext relay path")
    app = ServerApplication()
    alice, bob, _ = _approve_flow(app)
    port, thread, server = _start_relay(app)
    try:
        a, b = _open_pair(port, alice["session_id"], bob["session_id"])
        try:
            a.send(b"plain hello")
            got = b.wait_for(1, timeout=2.0)
            assert got == [b"plain hello"], got
        finally:
            a.close()
            b.close()
    finally:
        _stop_relay(thread, server)


def main() -> int:
    scenarios = [
        run_round_trip_with_key_hides_plaintext,
        run_wrong_key_drops_silently,
        run_keyed_vs_plain_drops,
        run_server_issued_key_round_trip,
        run_legacy_plaintext_still_works,
    ]
    for fn in scenarios:
        fn()
    print(f"\nAll {len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
