"""HTTP + minimal RFC-6455 WebSocket bridge for browser clients (M110).

Stdlib-only — no external WS lib. Each WebSocket connection is treated as a
single client of `ServerApplication.dispatch`: every text frame the browser
sends is parsed as a JSON envelope, dispatched, and the response is sent back
as a text frame. Push messages (deliveries, presence updates) sent via the
ConnectionRegistry are also forwarded.

GET / and GET /app.js serve the bundled single-page chat client; GET /ws is
the WebSocket upgrade endpoint.

This is the minimal viable bridge, not a hardened gateway:
- No HTTP keep-alive, only upgrades + static files.
- One thread per WS connection, blocking I/O.
- No fragmented frame support (browsers send small messages whole).
- No deflate-frame extension.
- Close frame is sent best-effort.

Browsers can tunnel control-plane requests over this bridge and get the same
typed protocol they would over the TCP server.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import socketserver
import struct
import threading
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Callable, Optional


WS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

# Opcodes
_OP_TEXT = 0x1
_OP_BINARY = 0x2
_OP_CLOSE = 0x8
_OP_PING = 0x9
_OP_PONG = 0xA

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def _ws_accept_key(client_key: str) -> str:
    digest = hashlib.sha1((client_key + WS_MAGIC).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def _send_text_frame(sock: socket.socket, payload: bytes) -> None:
    header = bytearray([0x80 | _OP_TEXT])  # FIN + text
    n = len(payload)
    if n < 126:
        header.append(n)
    elif n < (1 << 16):
        header.append(126)
        header += struct.pack(">H", n)
    else:
        header.append(127)
        header += struct.pack(">Q", n)
    sock.sendall(bytes(header) + payload)


def _send_close_frame(sock: socket.socket, code: int = 1000) -> None:
    body = struct.pack(">H", code)
    header = bytes([0x80 | _OP_CLOSE, len(body)])
    try:
        sock.sendall(header + body)
    except OSError:
        pass


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    chunks: list[bytes] = []
    remaining = n
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("peer closed during recv")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _recv_frame(sock: socket.socket) -> tuple[int, bytes]:
    """Return (opcode, payload). Handles masking; ignores RSV bits.

    Raises ConnectionError on a half-closed socket. Returns (_OP_CLOSE, b"")
    on a clean close frame.
    """
    header = _recv_exact(sock, 2)
    b0, b1 = header[0], header[1]
    opcode = b0 & 0x0F
    masked = (b1 & 0x80) != 0
    length = b1 & 0x7F
    if length == 126:
        length = struct.unpack(">H", _recv_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack(">Q", _recv_exact(sock, 8))[0]
    mask_key = _recv_exact(sock, 4) if masked else b""
    payload = _recv_exact(sock, length) if length > 0 else b""
    if masked and payload:
        payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
    return opcode, payload


class WebBridgeServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        app,
        *,
        web_dir: Optional[Path] = None,
    ) -> None:
        super().__init__(address, _BridgeHandler)
        self.app = app
        self.web_dir = web_dir or WEB_DIR


class _BridgeHandler(BaseHTTPRequestHandler):
    server: WebBridgeServer  # type: ignore[assignment]

    # Suppress noisy default logging during tests; real logs go through the
    # observability layer in the TCP server.
    def log_message(self, *_args, **_kwargs) -> None:  # noqa: D401
        return

    def do_GET(self) -> None:
        if self.path.startswith("/ws"):
            self._handle_websocket()
            return
        if self.path == "/" or self.path == "/index.html":
            self._serve_file("index.html", "text/html; charset=utf-8")
            return
        if self.path == "/app.js":
            self._serve_file("app.js", "application/javascript; charset=utf-8")
            return
        # M124: PWA assets so the browser can install + show push.
        if self.path == "/sw.js":
            self._serve_file("sw.js", "application/javascript; charset=utf-8")
            return
        if self.path == "/manifest.webmanifest":
            self._serve_file("manifest.webmanifest", "application/manifest+json; charset=utf-8")
            return
        self.send_error(404, "not found")

    # ---- static files ----

    def _serve_file(self, name: str, content_type: str) -> None:
        path = self.server.web_dir / name
        try:
            data = path.read_bytes()
        except OSError:
            self.send_error(404, "not found")
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    # ---- websocket upgrade ----

    def _handle_websocket(self) -> None:
        upgrade = self.headers.get("Upgrade", "").lower()
        if upgrade != "websocket":
            self.send_error(400, "expected websocket upgrade")
            return
        client_key = self.headers.get("Sec-WebSocket-Key", "")
        if not client_key:
            self.send_error(400, "missing Sec-WebSocket-Key")
            return
        accept = _ws_accept_key(client_key.strip())
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        # We have raw control of the socket from here on.
        sock: socket.socket = self.connection
        self._ws_loop(sock)

    def _ws_loop(self, sock: socket.socket) -> None:
        sock.settimeout(None)
        send_lock = threading.Lock()

        def send_text(payload: str) -> None:
            with send_lock:
                _send_text_frame(sock, payload.encode("utf-8"))

        try:
            while True:
                try:
                    opcode, payload = _recv_frame(sock)
                except (ConnectionError, OSError):
                    return
                if opcode == _OP_CLOSE:
                    _send_close_frame(sock)
                    return
                if opcode == _OP_PING:
                    with send_lock:
                        sock.sendall(bytes([0x80 | _OP_PONG, len(payload)]) + payload)
                    continue
                if opcode != _OP_TEXT:
                    # Ignore binary / pong / continuation for the MVP.
                    continue
                try:
                    envelope = json.loads(payload.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    send_text(json.dumps({
                        "type": "error",
                        "correlation_id": "",
                        "session_id": "",
                        "actor_user_id": "",
                        "sequence": 0,
                        "payload": {"code": "invalid_envelope", "message": "expected JSON"},
                    }))
                    continue
                response = self.server.app.dispatch(envelope)
                send_text(json.dumps(response))
        finally:
            try:
                sock.close()
            except OSError:
                pass


def serve_web_bridge_in_thread(
    host: str,
    port: int,
    app,
    *,
    web_dir: Optional[Path] = None,
) -> tuple[threading.Thread, WebBridgeServer]:
    server = WebBridgeServer((host, port), app, web_dir=web_dir)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread, server
