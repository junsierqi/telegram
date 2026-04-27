"""Minimal UDP echo server for the first media-plane byte channel.

Packet framing (small on purpose — this is the first byte, not a final design):

    MSG-HEADER: 4-byte big-endian length of session_id
    <session_id bytes>
    <arbitrary payload bytes>

Echo response:

    b"ack:" + session_id + b":" + original payload

No session validation here yet — the control-plane approves the session and
hands out the relay endpoint; the media plane just reflects traffic. Validation
can be layered on top once we have a shared session table.
"""
from __future__ import annotations

import socket
import socketserver
import struct
import threading
from typing import Callable, Optional


SessionAuthorizer = Callable[[str], bool]


MAX_PACKET_SIZE = 1500  # classic MTU ceiling — keep packets tiny for now.
ACK_PREFIX = b"ack:"
ACK_SEP = b":"

# Payload prefix that turns a probe into a subscribe request. When present, the
# server responds with a stream of frame_chunk datagrams instead of a
# single ack. Otherwise we keep the legacy echo for backward compat.
#
# Subscribe request payload shape:
#     b"SUB:" + utf-8(decimal-count) + b":" + <cookie bytes>
# e.g. b"SUB:5:stream-42"
#
# Frame chunk wire format (inside the sid_len|sid|... envelope):
#     kind=b"F" (1 byte) | seq (u32 BE) | payload_len (u32 BE) | payload
SUBSCRIBE_PREFIX = b"SUB:"
RELAY_PREFIX = b"RELAY:"
HELLO_PREFIX = b"HELLO"  # no body after it; register-only probe
FRAME_CHUNK_KIND = b"F"
DEFAULT_FRAME_COUNT = 5
MAX_FRAME_COUNT = 32
_FRAME_HEADER_STRUCT = ">cII"

# Inside a frame_chunk payload the first 12 bytes carry a structured header
# that lets a consumer interpret the rest as a real media frame:
#   u16 width | u16 height | u32 timestamp_ms | u8 codec | 3 reserved bytes
_PAYLOAD_HEADER_STRUCT = ">HHIB3x"
PAYLOAD_HEADER_SIZE = struct.calcsize(_PAYLOAD_HEADER_STRUCT)

CODEC_RAW = 1  # placeholder until we pick a real one


def build_frame_payload(
    width: int,
    height: int,
    timestamp_ms: int,
    codec: int,
    body: bytes,
) -> bytes:
    """Pack the structured frame payload used inside frame_chunk."""
    return struct.pack(_PAYLOAD_HEADER_STRUCT, width, height, timestamp_ms, codec) + body


def parse_frame_payload(payload: bytes) -> tuple[int, int, int, int, bytes] | None:
    """Unpack (width, height, timestamp_ms, codec, body) from a frame payload."""
    if len(payload) < PAYLOAD_HEADER_SIZE:
        return None
    width, height, timestamp_ms, codec = struct.unpack(
        _PAYLOAD_HEADER_STRUCT, payload[:PAYLOAD_HEADER_SIZE]
    )
    return width, height, timestamp_ms, codec, payload[PAYLOAD_HEADER_SIZE:]


class _UdpEchoHandler(socketserver.DatagramRequestHandler):
    def handle(self) -> None:  # pragma: no cover - exercised via sockets
        self._drop = False
        data = self.rfile.read(MAX_PACKET_SIZE)
        session_id, payload = _unframe(data)

        sid_str = session_id.decode("utf-8", errors="replace")
        authorizer: Optional[SessionAuthorizer] = getattr(self.server, "authorizer", None)
        if authorizer is not None:
            try:
                if not authorizer(sid_str):
                    self._drop = True
                    return
            except Exception:  # pragma: no cover - defensive
                self._drop = True
                return

        # Authorized: register the sender's address so peers can reach them
        # by session_id without a separate control-plane roundtrip.
        if hasattr(self.server, "register_peer"):
            self.server.register_peer(sid_str, self.client_address)

        # HELLO: registration-only probe (nothing to reply).
        if payload.startswith(HELLO_PREFIX) and len(payload) == len(HELLO_PREFIX):
            self._drop = True
            return

        # RELAY: forward to target peer from registry; no response to sender.
        if payload.startswith(RELAY_PREFIX):
            self._drop = True
            rest = payload[len(RELAY_PREFIX):]
            sep = rest.find(b":")
            if sep < 0:
                return
            target_sid = rest[:sep].decode("utf-8", errors="replace")
            body = rest[sep + 1:]
            target_addr = (
                self.server.lookup_peer(target_sid)
                if hasattr(self.server, "lookup_peer") else None
            )
            if target_addr is None:
                return
            # Forward as envelope(sender_sid, body) so target sees who sent it.
            datagram = frame(sid_str, body)
            try:
                self.server.socket.sendto(datagram, target_addr)
            except OSError:  # pragma: no cover - best effort
                pass
            return

        subscribe = parse_subscribe_request(payload)
        if subscribe is not None:
            frame_count, cookie = subscribe
            self._drop = True  # no default-finish write; we sendto directly.
            raw_socket = self.server.socket
            source = getattr(self.server, "screen_source", None)
            for seq in range(1, frame_count + 1):
                if source is not None:
                    frame_payload = source.next_frame(seq, cookie)
                else:
                    frame_payload = _fake_frame_payload(seq, cookie)
                body = build_frame_chunk(seq, frame_payload)
                datagram = frame(session_id.decode("utf-8", errors="replace"), body)
                raw_socket.sendto(datagram, self.client_address)
            return

        response = ACK_PREFIX + session_id + ACK_SEP + payload
        self.wfile.write(response)

    def finish(self) -> None:  # pragma: no cover - exercised via sockets
        # DatagramRequestHandler.finish() unconditionally sends wfile.getvalue()
        # back to the client, which turns `return` into a zero-length datagram
        # and defeats "silent drop". Skip the send when we've marked the packet
        # as dropped.
        if getattr(self, "_drop", False):
            return
        super().finish()


class ThreadedUdpMediaServer(socketserver.ThreadingUDPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        authorizer: Optional[SessionAuthorizer] = None,
        screen_source=None,
    ) -> None:
        super().__init__(server_address, _UdpEchoHandler)
        self.authorizer = authorizer
        # Duck-typed: anything with .next_frame(seq, cookie) -> bytes works.
        self.screen_source = screen_source
        # session_id -> last-seen (host, port). Any authorized packet refreshes
        # the entry; relay lookups read from it.
        self.peer_registry: dict[str, tuple[str, int]] = {}
        self._peer_registry_lock = threading.Lock()

    def register_peer(self, session_id: str, address: tuple[str, int]) -> None:
        with self._peer_registry_lock:
            self.peer_registry[session_id] = address

    def lookup_peer(self, session_id: str) -> Optional[tuple[str, int]]:
        with self._peer_registry_lock:
            return self.peer_registry.get(session_id)


def frame(session_id: str, payload: bytes) -> bytes:
    sid = session_id.encode("utf-8")
    if len(sid) > 0xFFFFFFFF:
        raise ValueError("session_id too large")
    return struct.pack(">I", len(sid)) + sid + payload


def build_frame_chunk(seq: int, payload: bytes) -> bytes:
    if seq < 0 or seq > 0xFFFFFFFF:
        raise ValueError("seq out of u32 range")
    if len(payload) > 0xFFFFFFFF:
        raise ValueError("payload too large")
    return struct.pack(_FRAME_HEADER_STRUCT, FRAME_CHUNK_KIND, seq, len(payload)) + payload


def parse_frame_chunk(data: bytes) -> tuple[int, bytes] | None:
    """Return (seq, payload) when `data` is a well-formed frame_chunk body.

    Expects the sid_len|sid envelope to have been peeled already.
    """
    header_size = struct.calcsize(_FRAME_HEADER_STRUCT)
    if len(data) < header_size:
        return None
    kind, seq, payload_len = struct.unpack(_FRAME_HEADER_STRUCT, data[:header_size])
    if kind != FRAME_CHUNK_KIND:
        return None
    if header_size + payload_len > len(data):
        return None
    return seq, data[header_size : header_size + payload_len]


def parse_subscribe_request(body: bytes) -> tuple[int, bytes] | None:
    """Return (frame_count, cookie) if `body` looks like a subscribe request."""
    if not body.startswith(SUBSCRIBE_PREFIX):
        return None
    rest = body[len(SUBSCRIBE_PREFIX):]
    sep = rest.find(b":")
    if sep < 0:
        return None
    count_bytes = rest[:sep]
    cookie = rest[sep + 1:]
    try:
        count = int(count_bytes.decode("ascii"))
    except (UnicodeDecodeError, ValueError):
        return None
    if count < 0:
        return None
    return min(count, MAX_FRAME_COUNT), cookie


_FAKE_WIDTH = 640
_FAKE_HEIGHT = 360
_FAKE_TS_STEP_MS = 33  # ~30 fps


def _fake_frame_payload(seq: int, cookie: bytes) -> bytes:
    """Structured deterministic payload for the first frame stream.

    Wraps the historical body (`frame-<n>|<cookie>`) with the frame header so
    consumers can parse width/height/timestamp/codec. Byte-exactness preserved
    via _fake_frame_body for tests that want to pin the body.
    """
    body = _fake_frame_body(seq, cookie)
    return build_frame_payload(
        width=_FAKE_WIDTH,
        height=_FAKE_HEIGHT,
        timestamp_ms=seq * _FAKE_TS_STEP_MS,
        codec=CODEC_RAW,
        body=body,
    )


def _fake_frame_body(seq: int, cookie: bytes) -> bytes:
    return b"frame-" + str(seq).encode("ascii") + b"|" + cookie


def _unframe(data: bytes) -> tuple[bytes, bytes]:
    if len(data) < 4:
        return b"", data
    (sid_len,) = struct.unpack(">I", data[:4])
    if 4 + sid_len > len(data):
        return b"", data[4:]
    return data[4 : 4 + sid_len], data[4 + sid_len :]


def serve_udp(
    host: str,
    port: int,
    *,
    authorizer: Optional[SessionAuthorizer] = None,
    screen_source=None,
) -> None:
    server = ThreadedUdpMediaServer(
        (host, port), authorizer=authorizer, screen_source=screen_source
    )
    print(f"[server] udp media plane listening on {host}:{port}"
          + (" (auth on)" if authorizer is not None else " (no auth)")
          + (f" (source {type(screen_source).__name__})" if screen_source is not None else ""))
    server.serve_forever()


def serve_udp_in_thread(
    host: str,
    port: int,
    *,
    authorizer: Optional[SessionAuthorizer] = None,
    screen_source=None,
) -> tuple[threading.Thread, ThreadedUdpMediaServer]:
    """Start the UDP echo server on a background daemon thread.

    Returns the thread + server so callers can shut it down cleanly.
    """
    server = ThreadedUdpMediaServer(
        (host, port), authorizer=authorizer, screen_source=screen_source
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread, server


def send_probe(host: str, port: int, session_id: str, payload: bytes, *, timeout: float = 2.0) -> bytes:
    """Client-side helper: send a framed probe, return the echo bytes."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(frame(session_id, payload), (host, port))
        data, _ = sock.recvfrom(MAX_PACKET_SIZE)
        return data


def build_subscribe_payload(frame_count: int, cookie: bytes = b"") -> bytes:
    if frame_count < 0 or frame_count > MAX_FRAME_COUNT:
        raise ValueError(f"frame_count must be in [0, {MAX_FRAME_COUNT}]")
    return SUBSCRIBE_PREFIX + str(frame_count).encode("ascii") + b":" + cookie


def build_relay_payload(target_session_id: str, body: bytes) -> bytes:
    return RELAY_PREFIX + target_session_id.encode("utf-8") + b":" + body


def build_hello_payload() -> bytes:
    return HELLO_PREFIX


def send_hello(host: str, port: int, session_id: str, *, timeout: float = 1.0) -> None:
    """Register the caller's (host, port) with the server's peer registry.

    Sends HELLO (no reply expected). Returns when the datagram has been
    sent — since HELLO is silent, there's no ack to await.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(frame(session_id, build_hello_payload()), (host, port))


def open_peer_socket(host: str, port: int, session_id: str, *, timeout: float = 1.0) -> socket.socket:
    """Open a UDP socket, send HELLO to register, return the socket ready for
    send/recv. Caller is responsible for closing.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    sock.sendto(frame(session_id, build_hello_payload()), (host, port))
    return sock


def subscribe_and_collect(
    host: str,
    port: int,
    session_id: str,
    frame_count: int,
    cookie: bytes = b"",
    *,
    timeout: float = 2.0,
) -> list[tuple[int, bytes]]:
    """Send a subscribe probe and collect the expected number of frame_chunks.

    Returns a list of (seq, payload) pairs in receive order. Raises socket.timeout
    if the stream stalls.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(
            frame(session_id, build_subscribe_payload(frame_count, cookie)),
            (host, port),
        )
        chunks: list[tuple[int, bytes]] = []
        while len(chunks) < frame_count:
            data, _ = sock.recvfrom(MAX_PACKET_SIZE)
            _, body = _unframe(data)
            parsed = parse_frame_chunk(body)
            if parsed is None:
                raise ValueError(f"malformed frame_chunk body: {body!r}")
            chunks.append(parsed)
        return chunks
