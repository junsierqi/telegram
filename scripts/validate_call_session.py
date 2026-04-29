"""M109 voice/video call session FSM + AEAD media-plane skeleton.

Scenarios:
- Full happy path: invite -> ringing -> accept -> accepted -> rendezvous (key
  shared between caller and callee) -> end -> ended.
- Decline by callee: ringing -> declined.
- Caller cancels while ringing: ringing -> canceled (via CALL_END from caller).
- Stranger can't end / accept / rendezvous someone else's call.
- Invalid kind rejected.
- Audio frame transport: after accept, both peers send 6 PCM frames over the
  call's relay (sealed with the call's AES-256-GCM key); both sides receive
  in order via the existing M105/M106 RelayPeerSession.
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


def _call_invite(app, *, caller, callee_device, callee_user_id, kind, seq) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.CALL_INVITE_REQUEST,
                correlation_id=f"corr_inv_{seq}",
                session_id=caller["session_id"],
                actor_user_id=caller["user_id"],
                sequence=seq,
            ),
            "payload": {
                "callee_user_id": callee_user_id,
                "callee_device_id": callee_device,
                "kind": kind,
            },
        }
    )


def _call_action(app, *, msg_type: MessageType, actor, call_id, seq) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                msg_type,
                correlation_id=f"corr_{msg_type.value}_{seq}",
                session_id=actor["session_id"],
                actor_user_id=actor["user_id"],
                sequence=seq,
            ),
            "payload": {"call_id": call_id},
        }
    )


def scenario(label: str) -> None:
    print(f"\n[scenario] {label}")


def run_happy_path() -> None:
    scenario("Invite -> accept -> rendezvous (shared key) -> end")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_call", 1)
    bob = _login(app, "bob", "bob_pw", "dev_bob_call", 2)

    inv = _call_invite(
        app, caller=alice, callee_device=bob["device_id"], callee_user_id=bob["user_id"],
        kind="audio", seq=3,
    )
    assert inv["type"] == "call_state", inv
    assert inv["payload"]["state"] == "ringing", inv["payload"]
    call_id = inv["payload"]["call_id"]

    accept = _call_action(app, msg_type=MessageType.CALL_ACCEPT_REQUEST, actor=bob, call_id=call_id, seq=4)
    assert accept["payload"]["state"] == "accepted", accept

    rv_a = _call_action(app, msg_type=MessageType.CALL_RENDEZVOUS_REQUEST, actor=alice, call_id=call_id, seq=5)
    rv_b = _call_action(app, msg_type=MessageType.CALL_RENDEZVOUS_REQUEST, actor=bob, call_id=call_id, seq=6)
    assert rv_a["type"] == "call_rendezvous_info", rv_a
    assert rv_a["payload"]["relay_key_b64"], "expected non-empty relay_key_b64 after accept"
    assert rv_a["payload"]["relay_key_b64"] == rv_b["payload"]["relay_key_b64"], (
        "both peers must see the same per-call AES key",
        rv_a["payload"]["relay_key_b64"],
        rv_b["payload"]["relay_key_b64"],
    )

    end = _call_action(app, msg_type=MessageType.CALL_END_REQUEST, actor=alice, call_id=call_id, seq=7)
    assert end["payload"]["state"] == "ended"
    assert end["payload"]["detail"].startswith("ended_by_"), end["payload"]


def run_decline() -> None:
    scenario("Callee declines while ringing -> declined (terminal)")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_call", 1)
    bob = _login(app, "bob", "bob_pw", "dev_bob_call", 2)
    inv = _call_invite(app, caller=alice, callee_device=bob["device_id"], callee_user_id=bob["user_id"], kind="audio", seq=3)
    call_id = inv["payload"]["call_id"]
    declined = _call_action(app, msg_type=MessageType.CALL_DECLINE_REQUEST, actor=bob, call_id=call_id, seq=4)
    assert declined["payload"]["state"] == "declined"
    # Second decline must error -> not_ringing.
    again = _call_action(app, msg_type=MessageType.CALL_DECLINE_REQUEST, actor=bob, call_id=call_id, seq=5)
    assert again["type"] == "error", again
    assert again["payload"]["code"] == "call_not_ringing", again["payload"]


def run_caller_cancels_while_ringing() -> None:
    scenario("Caller hangs up before accept -> canceled")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_call", 1)
    bob = _login(app, "bob", "bob_pw", "dev_bob_call", 2)
    inv = _call_invite(app, caller=alice, callee_device=bob["device_id"], callee_user_id=bob["user_id"], kind="audio", seq=3)
    call_id = inv["payload"]["call_id"]
    cancel = _call_action(app, msg_type=MessageType.CALL_END_REQUEST, actor=alice, call_id=call_id, seq=4)
    assert cancel["payload"]["state"] == "canceled", cancel
    assert cancel["payload"]["detail"] == "canceled_by_caller", cancel["payload"]


def _register(app, username: str, password: str, device_id: str, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                MessageType.REGISTER_REQUEST, correlation_id=f"reg_{username}", sequence=seq
            ),
            "payload": {
                "username": username,
                "password": password,
                "display_name": username.capitalize(),
                "device_id": device_id,
            },
        }
    )["payload"]


def run_stranger_denied() -> None:
    scenario("Stranger user can't accept / end / rendezvous someone else's call")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_call", 1)
    bob = _login(app, "bob", "bob_pw", "dev_bob_call", 2)
    _register(app, "carol", "carol_pw_long", "dev_carol_call", 3)
    carol = _login(app, "carol", "carol_pw_long", "dev_carol_call", 4)
    inv = _call_invite(app, caller=alice, callee_device=bob["device_id"], callee_user_id=bob["user_id"], kind="audio", seq=4)
    call_id = inv["payload"]["call_id"]
    for msg in (
        MessageType.CALL_ACCEPT_REQUEST,
        MessageType.CALL_DECLINE_REQUEST,
        MessageType.CALL_END_REQUEST,
        MessageType.CALL_RENDEZVOUS_REQUEST,
    ):
        resp = _call_action(app, msg_type=msg, actor=carol, call_id=call_id, seq=10)
        assert resp["type"] == "error", (msg, resp)
        assert resp["payload"]["code"] in ("call_participant_denied", "call_not_active"), (
            msg, resp["payload"]
        )


def run_invalid_kind_rejected() -> None:
    scenario("Invalid kind on invite -> call_invalid_kind error")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_call", 1)
    bob = _login(app, "bob", "bob_pw", "dev_bob_call", 2)
    resp = _call_invite(
        app, caller=alice, callee_device=bob["device_id"], callee_user_id=bob["user_id"],
        kind="hologram", seq=3,
    )
    assert resp["type"] == "error", resp
    assert resp["payload"]["code"] == "call_invalid_kind", resp["payload"]


def run_audio_frame_transport() -> None:
    scenario("After accept, AEAD-sealed PCM frames round-trip over the relay")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_call", 1)
    bob = _login(app, "bob", "bob_pw", "dev_bob_call", 2)
    # Approve a remote_session too, since the media_plane authorizer is keyed
    # by login session_id (M105 RelayPeerSession only needs valid logins).
    inv = _call_invite(app, caller=alice, callee_device=bob["device_id"], callee_user_id=bob["user_id"], kind="audio", seq=3)
    call_id = inv["payload"]["call_id"]
    _call_action(app, msg_type=MessageType.CALL_ACCEPT_REQUEST, actor=bob, call_id=call_id, seq=4)
    rv = _call_action(app, msg_type=MessageType.CALL_RENDEZVOUS_REQUEST, actor=alice, call_id=call_id, seq=5)
    relay_key = rv["payload"]["relay_key_b64"]
    assert relay_key

    port = _free_port()
    thread, server = serve_udp_in_thread(
        "127.0.0.1", port, authorizer=_build_session_authorizer(app.state)
    )
    try:
        time.sleep(0.05)
        a = RelayPeerSession(
            "127.0.0.1", port, alice["session_id"], bob["session_id"],
            relay_key_b64=relay_key,
        )
        b = RelayPeerSession(
            "127.0.0.1", port, bob["session_id"], alice["session_id"],
            relay_key_b64=relay_key,
        )
        time.sleep(0.05)
        try:
            # Synthetic 16-bit PCM frames at 48 kHz with seq prefix.
            frames_a = [bytes([i & 0xFF]) * 96 for i in range(1, 7)]  # 96 bytes ~= 1ms @ 48k mono
            for f in frames_a:
                a.send(b"PCM:48k:" + f)
            received = b.wait_for(len(frames_a), timeout=2.0)
            assert received == [b"PCM:48k:" + f for f in frames_a], received
            # Send back from B
            for i in range(3):
                b.send(b"PCM:48k:back-" + str(i).encode())
            back = a.wait_for(3, timeout=2.0)
            assert back == [b"PCM:48k:back-" + str(i).encode() for i in range(3)], back
        finally:
            a.close()
            b.close()
    finally:
        server.shutdown()
        thread.join(timeout=2.0)

    # Hang up after the media test so the call ends cleanly.
    _call_action(app, msg_type=MessageType.CALL_END_REQUEST, actor=alice, call_id=call_id, seq=6)


def main() -> int:
    scenarios = [
        run_happy_path,
        run_decline,
        run_caller_cancels_while_ringing,
        run_stranger_denied,
        run_invalid_kind_rejected,
        run_audio_frame_transport,
    ]
    for fn in scenarios:
        fn()
    print(f"\nAll {len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
