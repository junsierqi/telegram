"""Validator for chunked attachment upload (M88).

Drives an in-process ServerApplication through the init/chunk/complete
RPCs to verify:

  1. Init returns an upload_id + chunk_size.
  2. Streaming a 5 MB payload in 1 MB chunks completes successfully and
     returns a MESSAGE_DELIVER with size_bytes matching the original.
  3. fetch_attachment retrieves the same bytes via the existing path.
  4. Init for a > 64 MB file is rejected with UPLOAD_TOO_LARGE.
  5. An out-of-order chunk is rejected with UPLOAD_CHUNK_OUT_OF_ORDER.
  6. complete with a short stitched buffer is rejected with
     UPLOAD_SIZE_MISMATCH.
  7. Concurrent uploads cap (8) is enforced with UPLOAD_LIMIT_REACHED.
"""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402


def _login(app, user, password, device, seq):
    resp = app.dispatch({
        **make_envelope(MessageType.LOGIN_REQUEST, correlation_id=f"corr_login_{seq}", sequence=seq),
        "payload": {"username": user, "password": password, "device_id": device},
    })
    assert resp["type"] == "login_response", resp
    return resp["payload"]


def _init(app, sess, conv, filename, mime, total, seq):
    return app.dispatch({
        **make_envelope(MessageType.ATTACHMENT_UPLOAD_INIT_REQUEST,
                        correlation_id=f"corr_init_{seq}",
                        session_id=sess["session_id"],
                        actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"conversation_id": conv, "filename": filename,
                    "mime_type": mime, "total_size_bytes": total},
    })


def _chunk(app, sess, upload_id, sequence_index, raw_bytes, seq):
    return app.dispatch({
        **make_envelope(MessageType.ATTACHMENT_UPLOAD_CHUNK_REQUEST,
                        correlation_id=f"corr_chunk_{seq}",
                        session_id=sess["session_id"],
                        actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"upload_id": upload_id, "sequence": sequence_index,
                    "content_b64": base64.b64encode(raw_bytes).decode("ascii")},
    })


def _complete(app, sess, upload_id, caption, seq):
    return app.dispatch({
        **make_envelope(MessageType.ATTACHMENT_UPLOAD_COMPLETE_REQUEST,
                        correlation_id=f"corr_done_{seq}",
                        session_id=sess["session_id"],
                        actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"upload_id": upload_id, "caption": caption},
    })


def _fetch(app, sess, attachment_id, seq):
    return app.dispatch({
        **make_envelope(MessageType.ATTACHMENT_FETCH_REQUEST,
                        correlation_id=f"corr_fetch_{seq}",
                        session_id=sess["session_id"],
                        actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"attachment_id": attachment_id},
    })


def scenario_5mb_round_trip():
    print("[scenario] 5 MB upload round-trips through init/chunk/complete")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice", 1)
    payload = os.urandom(5 * 1_048_576)  # 5 MB random bytes
    init = _init(app, alice, "conv_alice_bob", "big.bin", "application/octet-stream",
                 len(payload), 2)
    assert init["type"] == "attachment_upload_init_response", init
    upload_id = init["payload"]["upload_id"]
    chunk_size = init["payload"]["chunk_size"]
    assert chunk_size > 0
    # Stream chunks of size up to chunk_size.
    seq = 3
    chunk_idx = 0
    offset = 0
    while offset < len(payload):
        chunk = payload[offset:offset + chunk_size]
        ack = _chunk(app, alice, upload_id, chunk_idx, chunk, seq)
        assert ack["type"] == "attachment_upload_chunk_ack", ack
        assert ack["payload"]["sequence"] == chunk_idx
        offset += len(chunk)
        chunk_idx += 1
        seq += 1
    # Complete: should return a MESSAGE_DELIVER with size matching.
    done = _complete(app, alice, upload_id, "5MB blob via chunks", seq)
    assert done["type"] == "message_deliver", done
    msg = done["payload"]
    assert msg["size_bytes"] == len(payload)
    assert msg["filename"] == "big.bin"
    attachment_id = msg["attachment_id"]
    # Fetch and verify the bytes round-trip exactly.
    fetched = _fetch(app, alice, attachment_id, seq + 1)
    assert fetched["type"] == "attachment_fetch_response", fetched
    got = base64.b64decode(fetched["payload"]["content_b64"])
    assert got == payload, "fetched bytes do not match uploaded payload"
    print(f"[ok ] 5 MB round-trip ok ({chunk_idx} chunks, attachment_id={attachment_id})")


def scenario_too_large_rejected():
    print("[scenario] init for >64 MB file -> UPLOAD_TOO_LARGE")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice", 1)
    resp = _init(app, alice, "conv_alice_bob", "huge.bin",
                 "application/octet-stream", 65 * 1_048_576, 2)
    assert resp["type"] == "error", resp
    assert resp["payload"]["code"] == "upload_too_large", resp
    print("[ok ] >64 MB rejected upfront")


def scenario_out_of_order_chunk_rejected():
    print("[scenario] chunk sequence skip -> UPLOAD_CHUNK_OUT_OF_ORDER")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice", 1)
    payload = os.urandom(2 * 1_048_576)
    init = _init(app, alice, "conv_alice_bob", "ooo.bin", "application/octet-stream",
                 len(payload), 2)
    upload_id = init["payload"]["upload_id"]
    # Skip sequence 0, send sequence 1 directly.
    resp = _chunk(app, alice, upload_id, 1, payload[:1_048_576], 3)
    assert resp["type"] == "error", resp
    assert resp["payload"]["code"] == "upload_chunk_out_of_order", resp
    print("[ok ] out-of-order chunk rejected")


def scenario_short_complete_rejected():
    print("[scenario] complete before all bytes arrive -> UPLOAD_SIZE_MISMATCH")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice", 1)
    declared = 3 * 1_048_576
    init = _init(app, alice, "conv_alice_bob", "short.bin",
                 "application/octet-stream", declared, 2)
    upload_id = init["payload"]["upload_id"]
    # Only send one chunk worth of bytes, then complete.
    _chunk(app, alice, upload_id, 0, os.urandom(1_048_576), 3)
    resp = _complete(app, alice, upload_id, "premature", 4)
    assert resp["type"] == "error", resp
    assert resp["payload"]["code"] == "upload_size_mismatch", resp
    print("[ok ] short complete rejected")


def scenario_empty_chunk_rejected():
    print("[scenario] empty content_b64 -> INVALID_ATTACHMENT_PAYLOAD")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice", 1)
    init = _init(app, alice, "conv_alice_bob", "empty.bin",
                 "application/octet-stream", 1024, 2)
    upload_id = init["payload"]["upload_id"]
    resp = app.dispatch({
        **make_envelope(MessageType.ATTACHMENT_UPLOAD_CHUNK_REQUEST,
                        correlation_id="corr_empty_chunk",
                        session_id=alice["session_id"],
                        actor_user_id=alice["user_id"], sequence=3),
        "payload": {"upload_id": upload_id, "sequence": 0, "content_b64": ""},
    })
    assert resp["type"] == "error", resp
    assert resp["payload"]["code"] == "invalid_attachment_payload", resp
    print("[ok ] empty chunk rejected upfront")


def scenario_concurrent_upload_cap():
    print("[scenario] 9th concurrent upload -> UPLOAD_LIMIT_REACHED")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice", 1)
    seq = 2
    for i in range(8):
        resp = _init(app, alice, "conv_alice_bob", f"file_{i}.bin",
                     "application/octet-stream", 1024, seq)
        assert resp["type"] == "attachment_upload_init_response", resp
        seq += 1
    over = _init(app, alice, "conv_alice_bob", "overflow.bin",
                 "application/octet-stream", 1024, seq)
    assert over["type"] == "error", over
    assert over["payload"]["code"] == "upload_limit_reached", over
    print("[ok ] 9th concurrent upload rejected")


def main() -> int:
    scenarios = [
        scenario_5mb_round_trip,
        scenario_too_large_rejected,
        scenario_out_of_order_chunk_rejected,
        scenario_short_complete_rejected,
        scenario_empty_chunk_rejected,
        scenario_concurrent_upload_cap,
    ]
    for s in scenarios:
        s()
    print(f"\nAll {len(scenarios)}/{len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
