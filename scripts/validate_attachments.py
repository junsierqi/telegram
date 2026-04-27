"""Validator for REQ-ATTACHMENTS (E3)."""
from __future__ import annotations

import base64
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.connection_registry import ConnectionRegistry  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402
from server.server.services.chat import MAX_ATTACHMENT_SIZE_BYTES  # noqa: E402


class Inbox:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    def writer(self, message: dict) -> None:
        self.messages.append(message)

    def pop_type(self, type_: str) -> dict | None:
        for i, m in enumerate(self.messages):
            if m.get("type") == type_:
                return self.messages.pop(i)
        return None


def _login(app, username, password, device_id, seq):
    resp = app.dispatch(
        {
            **make_envelope(MessageType.LOGIN_REQUEST, correlation_id=f"corr_{username}", sequence=seq),
            "payload": {"username": username, "password": password, "device_id": device_id},
        }
    )
    return resp["payload"]


def _send_attachment(app, session, conv_id, *, caption, filename, mime_type, content: bytes, seq, size_bytes=None, corr=None):
    b64 = base64.b64encode(content).decode("ascii")
    return app.dispatch(
        {
            **make_envelope(
                MessageType.MESSAGE_SEND_ATTACHMENT, correlation_id=corr or f"corr_att_{seq}",
                session_id=session["session_id"], actor_user_id=session["user_id"], sequence=seq,
            ),
            "payload": {
                "conversation_id": conv_id, "caption": caption, "filename": filename,
                "mime_type": mime_type, "content_b64": b64,
                "size_bytes": size_bytes if size_bytes is not None else len(content),
            },
        }
    )


def _fetch(app, session, attachment_id, seq, corr=None):
    return app.dispatch(
        {
            **make_envelope(
                MessageType.ATTACHMENT_FETCH_REQUEST, correlation_id=corr or f"corr_fetch_{seq}",
                session_id=session["session_id"], actor_user_id=session["user_id"], sequence=seq,
            ),
            "payload": {"attachment_id": attachment_id},
        }
    )


def test_send_and_fetch_attachment() -> None:
    registry = ConnectionRegistry()
    bob_inbox = Inbox()
    app = ServerApplication(connection_registry=registry)
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    bob = _login(app, "bob", "bob_pw", "dev_bob_win", 2)
    registry.register(bob["session_id"], bob_inbox.writer)

    payload = b"hello-binary\x00\x01\x02" * 10  # 170 bytes
    send = _send_attachment(app, alice, "conv_alice_bob",
                            caption="look!", filename="note.bin", mime_type="application/octet-stream",
                            content=payload, seq=3)
    assert send["type"] == "message_deliver"
    p = send["payload"]
    assert p["filename"] == "note.bin"
    assert p["size_bytes"] == len(payload)
    assert p["attachment_id"].startswith("att_")
    attachment_id = p["attachment_id"]

    # bob got a push with the reference (no body)
    push = bob_inbox.pop_type("message_deliver")
    assert push is not None
    assert push["payload"]["attachment_id"] == attachment_id
    assert push["payload"]["filename"] == "note.bin"
    # push payload does NOT carry content_b64
    assert "content_b64" not in push["payload"]

    # bob fetches the body
    fetched = _fetch(app, bob, attachment_id, seq=4)
    assert fetched["type"] == "attachment_fetch_response"
    body = base64.b64decode(fetched["payload"]["content_b64"])
    assert body == payload


def test_size_cap_enforced() -> None:
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)

    # exactly over the cap
    too_big = b"x" * (MAX_ATTACHMENT_SIZE_BYTES + 1)
    resp = _send_attachment(app, alice, "conv_alice_bob",
                            caption="", filename="big.bin", mime_type="application/octet-stream",
                            content=too_big, seq=2, corr="corr_big")
    assert resp["type"] == "error"
    assert resp["payload"]["code"] == "attachment_too_large"


def test_size_mismatch_rejected() -> None:
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)

    resp = _send_attachment(app, alice, "conv_alice_bob",
                            caption="", filename="note.bin", mime_type="application/octet-stream",
                            content=b"12345", seq=2, size_bytes=999, corr="corr_sz")
    assert resp["type"] == "error"
    assert resp["payload"]["code"] == "invalid_attachment_payload"


def test_invalid_base64_rejected() -> None:
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    resp = app.dispatch(
        {
            **make_envelope(
                MessageType.MESSAGE_SEND_ATTACHMENT, correlation_id="corr_bad_b64",
                session_id=alice["session_id"], actor_user_id=alice["user_id"], sequence=2,
            ),
            "payload": {
                "conversation_id": "conv_alice_bob", "caption": "", "filename": "x",
                "mime_type": "application/octet-stream",
                "content_b64": "not valid base64!!",
                "size_bytes": 10,
            },
        }
    )
    assert resp["type"] == "error"
    assert resp["payload"]["code"] == "invalid_attachment_payload"


def test_fetch_access_denied_for_non_participant() -> None:
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    _login(app, "bob", "bob_pw", "dev_bob_win", 2)

    # register carol (not in conv_alice_bob)
    reg = app.dispatch(
        {
            **make_envelope(MessageType.REGISTER_REQUEST, correlation_id="corr_reg_carol", sequence=3),
            "payload": {
                "username": "carol", "password": "carol_pw_ok",
                "display_name": "Carol", "device_id": "dev_carol",
            },
        }
    )
    carol = reg["payload"]

    send = _send_attachment(app, alice, "conv_alice_bob",
                            caption="", filename="priv.bin", mime_type="application/octet-stream",
                            content=b"secret", seq=4)
    attachment_id = send["payload"]["attachment_id"]

    # carol tries to fetch — access denied
    fetched = _fetch(app, carol, attachment_id, seq=5, corr="corr_carol_fetch")
    assert fetched["type"] == "error"
    assert fetched["payload"]["code"] == "attachment_access_denied"


def test_unknown_attachment_rejected() -> None:
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    resp = _fetch(app, alice, "att_9999", seq=2, corr="corr_ghost_fetch")
    assert resp["type"] == "error"
    assert resp["payload"]["code"] == "unknown_attachment"


def test_attachment_persists_across_restart() -> None:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        app = ServerApplication(state_file=path)
        alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
        _login(app, "bob", "bob_pw", "dev_bob_win", 2)
        payload = b"persistent-bytes"
        send = _send_attachment(app, alice, "conv_alice_bob",
                                caption="", filename="p.bin", mime_type="application/octet-stream",
                                content=payload, seq=3)
        attachment_id = send["payload"]["attachment_id"]

        app2 = ServerApplication(state_file=path)
        alice2 = _login(app2, "alice", "alice_pw", "dev_alice_win", 1)
        fetched = _fetch(app2, alice2, attachment_id, seq=2)
        assert fetched["type"] == "attachment_fetch_response"
        body = base64.b64decode(fetched["payload"]["content_b64"])
        assert body == payload
    finally:
        Path(path).unlink(missing_ok=True)


def test_attachment_blob_store_keeps_content_out_of_state_json() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        state_path = str(Path(tmp) / "state.json")
        blob_dir = Path(tmp) / "blobs"
        app = ServerApplication(state_file=state_path, attachment_dir=str(blob_dir))
        alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
        payload = b"blob-backed-bytes"
        send = _send_attachment(
            app,
            alice,
            "conv_alice_bob",
            caption="blob",
            filename="blob.bin",
            mime_type="application/octet-stream",
            content=payload,
            seq=2,
        )
        attachment_id = send["payload"]["attachment_id"]
        blob_path = blob_dir / f"{attachment_id}.bin"
        assert blob_path.exists()
        assert blob_path.read_bytes() == payload

        state = json.loads(Path(state_path).read_text(encoding="utf-8"))
        record = state["attachments"][0]
        assert record["attachment_id"] == attachment_id
        assert record["storage_key"] == f"{attachment_id}.bin"
        assert record["content_b64"] == ""


def test_attachment_blob_store_survives_restart() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        state_path = str(Path(tmp) / "state.json")
        blob_dir = str(Path(tmp) / "blobs")
        app = ServerApplication(state_file=state_path, attachment_dir=blob_dir)
        alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
        payload = b"restart-blob"
        send = _send_attachment(
            app,
            alice,
            "conv_alice_bob",
            caption="blob",
            filename="blob.bin",
            mime_type="application/octet-stream",
            content=payload,
            seq=2,
        )
        attachment_id = send["payload"]["attachment_id"]

        app2 = ServerApplication(state_file=state_path, attachment_dir=blob_dir)
        alice2 = _login(app2, "alice", "alice_pw", "dev_alice_win", 1)
        fetched = _fetch(app2, alice2, attachment_id, seq=2)
        assert fetched["type"] == "attachment_fetch_response"
        assert base64.b64decode(fetched["payload"]["content_b64"]) == payload


def test_legacy_inline_attachment_state_still_fetches() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "legacy_state.json"
        content = b"legacy-inline"
        state_path.write_text(
            json.dumps(
                {
                    "conversations": [
                        {
                            "conversation_id": "conv_alice_bob",
                            "participant_user_ids": ["u_alice", "u_bob"],
                            "messages": [
                                {
                                    "message_id": "msg_1",
                                    "sender_user_id": "u_alice",
                                    "text": "legacy",
                                    "attachment_id": "att_legacy",
                                }
                            ],
                        }
                    ],
                    "attachments": [
                        {
                            "attachment_id": "att_legacy",
                            "conversation_id": "conv_alice_bob",
                            "uploader_user_id": "u_alice",
                            "filename": "legacy.bin",
                            "mime_type": "application/octet-stream",
                            "size_bytes": len(content),
                            "content_b64": base64.b64encode(content).decode("ascii"),
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        app = ServerApplication(state_file=str(state_path), attachment_dir=str(Path(tmp) / "blobs"))
        alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
        fetched = _fetch(app, alice, "att_legacy", seq=2)
        assert fetched["type"] == "attachment_fetch_response"
        assert base64.b64decode(fetched["payload"]["content_b64"]) == content


def test_message_descriptor_in_sync_shows_attachment_id() -> None:
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice_win", 1)
    _login(app, "bob", "bob_pw", "dev_bob_win", 2)
    send = _send_attachment(app, alice, "conv_alice_bob",
                            caption="photo", filename="cat.png", mime_type="image/png",
                            content=b"\x89PNGfake", seq=3)
    attachment_id = send["payload"]["attachment_id"]

    sync = app.dispatch(
        {
            **make_envelope(MessageType.CONVERSATION_SYNC, correlation_id="corr_sync",
                             session_id=alice["session_id"], actor_user_id=alice["user_id"], sequence=4),
            "payload": {},
        }
    )
    conv = sync["payload"]["conversations"][0]
    last_msg = conv["messages"][-1]
    assert last_msg["attachment_id"] == attachment_id
    assert last_msg["text"] == "photo"
    assert last_msg["filename"] == "cat.png"
    assert last_msg["mime_type"] == "image/png"
    assert last_msg["size_bytes"] == len(b"\x89PNGfake")


SCENARIOS = [
    ("send_and_fetch_attachment", test_send_and_fetch_attachment),
    ("size_cap_enforced", test_size_cap_enforced),
    ("size_mismatch_rejected", test_size_mismatch_rejected),
    ("invalid_base64_rejected", test_invalid_base64_rejected),
    ("fetch_access_denied_for_non_participant", test_fetch_access_denied_for_non_participant),
    ("unknown_attachment_rejected", test_unknown_attachment_rejected),
    ("attachment_persists_across_restart", test_attachment_persists_across_restart),
    ("attachment_blob_store_keeps_content_out_of_state_json", test_attachment_blob_store_keeps_content_out_of_state_json),
    ("attachment_blob_store_survives_restart", test_attachment_blob_store_survives_restart),
    ("legacy_inline_attachment_state_still_fetches", test_legacy_inline_attachment_state_still_fetches),
    ("message_descriptor_in_sync_shows_attachment_id", test_message_descriptor_in_sync_shows_attachment_id),
]


def main() -> int:
    failures: list[str] = []
    for name, fn in SCENARIOS:
        try:
            fn()
            print(f"[ok ] {name}")
        except Exception as exc:
            failures.append(f"{name}: {exc}")
            print(f"[FAIL] {name}: {exc}")
    print(f"passed {len(SCENARIOS) - len(failures)}/{len(SCENARIOS)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
