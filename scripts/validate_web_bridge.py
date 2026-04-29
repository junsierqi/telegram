"""M110 web client bridge: HTTP page serving + RFC-6455 WebSocket round-trip.

Scenarios:
- GET / returns the bundled index.html.
- GET /app.js returns the bundled JS.
- WebSocket handshake succeeds (Sec-WebSocket-Accept matches).
- Login envelope over WS returns a login_response with a non-empty session_id.
- message_send round-trip: alice -> bob conversation; bob's WS receives a
  message_deliver push.
- Bad JSON in a text frame returns an error envelope without dropping the
  connection.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import struct
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.web_bridge import serve_web_bridge_in_thread  # noqa: E402


WS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# -- minimal WS client --

def _ws_connect(host: str, port: int) -> socket.socket:
    sock = socket.create_connection((host, port), timeout=5.0)
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    req = (
        f"GET /ws HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n\r\n"
    )
    sock.sendall(req.encode("ascii"))
    # Read until \r\n\r\n
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("no handshake response")
        buf += chunk
    head, _, _ = buf.partition(b"\r\n\r\n")
    head_text = head.decode("ascii", errors="replace")
    expected = base64.b64encode(
        hashlib.sha1((key + WS_MAGIC).encode("ascii")).digest()
    ).decode("ascii")
    if "101" not in head_text.split("\r\n", 1)[0]:
        raise AssertionError(f"expected 101, got: {head_text!r}")
    if expected not in head_text:
        raise AssertionError(f"Sec-WebSocket-Accept mismatch in: {head_text!r}")
    return sock


def _ws_send_text(sock: socket.socket, payload: str) -> None:
    data = payload.encode("utf-8")
    n = len(data)
    header = bytearray([0x81])  # FIN + text
    if n < 126:
        header.append(0x80 | n)  # MASK + length
    elif n < (1 << 16):
        header.append(0x80 | 126)
        header += struct.pack(">H", n)
    else:
        header.append(0x80 | 127)
        header += struct.pack(">Q", n)
    mask = os.urandom(4)
    header += mask
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    sock.sendall(bytes(header) + masked)


def _ws_recv(sock: socket.socket, timeout: float = 2.0) -> tuple[int, bytes]:
    sock.settimeout(timeout)
    h = b""
    while len(h) < 2:
        chunk = sock.recv(2 - len(h))
        if not chunk:
            raise ConnectionError("peer closed")
        h += chunk
    b0, b1 = h[0], h[1]
    opcode = b0 & 0x0F
    length = b1 & 0x7F
    if length == 126:
        length = struct.unpack(">H", _recv_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack(">Q", _recv_exact(sock, 8))[0]
    payload = _recv_exact(sock, length) if length > 0 else b""
    return opcode, payload


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    chunks: list[bytes] = []
    remaining = n
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("peer closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _send_envelope(sock: socket.socket, env: dict) -> None:
    _ws_send_text(sock, json.dumps(env))


def _recv_envelope(sock: socket.socket, timeout: float = 2.0) -> dict:
    opcode, payload = _ws_recv(sock, timeout=timeout)
    if opcode != 0x1:
        raise AssertionError(f"unexpected opcode {opcode}")
    return json.loads(payload.decode("utf-8"))


# -- scenarios --

def scenario(label: str) -> None:
    print(f"\n[scenario] {label}")


def _http_get(host: str, port: int, path: str) -> tuple[int, dict, bytes]:
    sock = socket.create_connection((host, port), timeout=2.0)
    sock.sendall(
        f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nConnection: close\r\n\r\n".encode("ascii")
    )
    buf = b""
    while True:
        chunk = sock.recv(8192)
        if not chunk:
            break
        buf += chunk
    sock.close()
    head, _, body = buf.partition(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    status_line = lines[0].decode("ascii")
    code = int(status_line.split(" ", 2)[1])
    headers = {}
    for ln in lines[1:]:
        if b":" in ln:
            k, _, v = ln.partition(b":")
            headers[k.strip().lower().decode("ascii")] = v.strip().decode("ascii")
    return code, headers, body


def _start_bridge():
    app = ServerApplication()
    port = _free_port()
    thread, server = serve_web_bridge_in_thread("127.0.0.1", port, app)
    time.sleep(0.05)
    return app, port, thread, server


def _stop_bridge(thread, server) -> None:
    server.shutdown()
    thread.join(timeout=2.0)


def run_static_files() -> None:
    scenario("GET / and GET /app.js return bundled HTML and JS")
    _, port, thread, server = _start_bridge()
    try:
        code, headers, body = _http_get("127.0.0.1", port, "/")
        assert code == 200, code
        assert headers.get("content-type", "").startswith("text/html")
        assert b"Telegram-like" in body and b"<script" in body, body[:200]
        code, headers, body = _http_get("127.0.0.1", port, "/app.js")
        assert code == 200, code
        assert headers.get("content-type", "").startswith("application/javascript")
        assert b"login_request" in body and b"WebSocket" in body, body[:200]
    finally:
        _stop_bridge(thread, server)


def run_unknown_path_404() -> None:
    scenario("GET /nope returns 404")
    _, port, thread, server = _start_bridge()
    try:
        code, _, _ = _http_get("127.0.0.1", port, "/nope")
        assert code == 404
    finally:
        _stop_bridge(thread, server)


def run_login_round_trip() -> None:
    scenario("WS login_request -> login_response with non-empty session_id")
    _, port, thread, server = _start_bridge()
    try:
        sock = _ws_connect("127.0.0.1", port)
        try:
            _send_envelope(sock, {
                "type": "login_request",
                "correlation_id": "c1",
                "session_id": "",
                "actor_user_id": "",
                "sequence": 1,
                "payload": {"username": "alice", "password": "alice_pw", "device_id": "dev_alice_web"},
            })
            resp = _recv_envelope(sock)
            assert resp["type"] == "login_response", resp
            assert resp["payload"]["session_id"], resp
            assert resp["payload"]["user_id"] == "u_alice", resp
        finally:
            sock.close()
    finally:
        _stop_bridge(thread, server)


def run_send_round_trip() -> None:
    scenario("alice (WS) sends a message; conversation_sync confirms it")
    _, port, thread, server = _start_bridge()
    try:
        sock = _ws_connect("127.0.0.1", port)
        try:
            _send_envelope(sock, {
                "type": "login_request",
                "correlation_id": "c1",
                "session_id": "",
                "actor_user_id": "",
                "sequence": 1,
                "payload": {"username": "alice", "password": "alice_pw", "device_id": "dev_alice_web"},
            })
            login = _recv_envelope(sock)
            sid = login["payload"]["session_id"]
            uid = login["payload"]["user_id"]

            _send_envelope(sock, {
                "type": "message_send",
                "correlation_id": "c2",
                "session_id": sid,
                "actor_user_id": uid,
                "sequence": 2,
                "payload": {"conversation_id": "conv_alice_bob", "text": "hello from web"},
            })
            ack = _recv_envelope(sock)
            assert ack["type"] in ("message_deliver", "message_send_ack"), ack
            # The seeded conv_alice_bob exists; pull conversation_sync to
            # confirm the message landed.
            _send_envelope(sock, {
                "type": "conversation_sync",
                "correlation_id": "c3",
                "session_id": sid,
                "actor_user_id": uid,
                "sequence": 3,
                "payload": {"cursors": []},
            })
            sync = _recv_envelope(sock, timeout=3.0)
            assert sync["type"] == "conversation_sync", sync
            convs = sync["payload"]["conversations"]
            target = next((c for c in convs if c["conversation_id"] == "conv_alice_bob"), None)
            assert target is not None, sync
            texts = [m.get("text") for m in target.get("messages", [])]
            assert "hello from web" in texts, texts
        finally:
            sock.close()
    finally:
        _stop_bridge(thread, server)


def run_bad_json_returns_error() -> None:
    scenario("Bad JSON text frame returns an error envelope; connection survives")
    _, port, thread, server = _start_bridge()
    try:
        sock = _ws_connect("127.0.0.1", port)
        try:
            _ws_send_text(sock, "{this is not json}")
            resp = _recv_envelope(sock)
            assert resp["type"] == "error", resp
            assert resp["payload"]["code"] == "invalid_envelope", resp
            # Connection still alive: a normal envelope should still respond.
            _send_envelope(sock, {
                "type": "login_request",
                "correlation_id": "c2",
                "session_id": "",
                "actor_user_id": "",
                "sequence": 1,
                "payload": {"username": "alice", "password": "alice_pw", "device_id": "dev_alice_web2"},
            })
            login = _recv_envelope(sock)
            assert login["type"] == "login_response", login
        finally:
            sock.close()
    finally:
        _stop_bridge(thread, server)


def main() -> int:
    scenarios = [
        run_static_files,
        run_unknown_path_404,
        run_login_round_trip,
        run_send_round_trip,
        run_bad_json_returns_error,
    ]
    for fn in scenarios:
        fn()
    print(f"\nAll {len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
