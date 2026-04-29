"""Peer-side reliability over the UDP relay (M105 / ATLAS-M71).

Combines `media_plane.frame` + `RELAY:` prefix with `reliable_stream.ReliableChannel`
so two remote-control peers exchange in-order messages over the relay even
when the underlying UDP path drops or reorders packets.

Server stays a dumb forwarder; reliability lives in the peers. Wire bytes
emitted by a peer to the relay socket:

    frame(my_sid, RELAY:<peer_sid>:REL:<seq>:<payload>)
    frame(my_sid, RELAY:<peer_sid>:NAK:<seq,seq,...>)
    frame(my_sid, RELAY:<peer_sid>:ACK:<highest_delivered>)

A receiving peer sees the relay's envelope (sender_sid|body) and feeds
`body` (the bare REL/NAK/ACK packet) to its local ReliableChannel.
"""
from __future__ import annotations

import socket
import threading
from typing import Callable, Optional

from .media_crypto import decrypt as _aead_decrypt
from .media_crypto import encrypt as _aead_encrypt
from .media_plane import (
    MAX_PACKET_SIZE,
    build_hello_payload,
    build_relay_payload,
    frame,
    _unframe,
)
from .reliable_stream import ReliableChannel


# Return True to forward the packet, False to drop it. Used by tests to
# inject deterministic loss without touching the socket.
LossFilter = Callable[[bytes], bool]


class RelayPeerSession:
    def __init__(
        self,
        relay_host: str,
        relay_port: int,
        my_session_id: str,
        peer_session_id: str,
        *,
        recv_timeout: float = 0.2,
        tx_loss: Optional[LossFilter] = None,
        rx_loss: Optional[LossFilter] = None,
        relay_key_b64: str = "",
    ) -> None:
        self._relay_addr = (relay_host, relay_port)
        self._my_sid = my_session_id
        self._peer_sid = peer_session_id
        self._tx_loss = tx_loss
        self._rx_loss = rx_loss
        # M106 / D9: when set, every reliable packet is sealed with AES-256-GCM
        # before hitting the relay socket and unsealed on the way back. Empty
        # string keeps the legacy plaintext path for backward compat.
        self._relay_key_b64 = relay_key_b64
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.settimeout(recv_timeout)
        self._lock = threading.Lock()
        self._channel = ReliableChannel(self._send_raw)
        self._stop = threading.Event()
        # HELLO so the relay's peer registry knows where to forward to us.
        self._sock.sendto(
            frame(my_session_id, build_hello_payload()), self._relay_addr
        )
        self._reader = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader.start()

    # ---- public API ----

    def send(self, payload: bytes) -> int:
        with self._lock:
            return self._channel.send(payload)

    def tick_retransmit(self) -> int:
        with self._lock:
            return self._channel.tick_retransmit()

    def pop_delivered(self) -> list[bytes]:
        with self._lock:
            return self._channel.pop_delivered()

    def wait_for(self, count: int, *, timeout: float = 2.0) -> list[bytes]:
        """Block until `count` payloads have been delivered, then return them.

        Drains pop_delivered() on each spin so the channel state stays clean.
        Raises TimeoutError if the deadline passes with fewer payloads.
        """
        deadline = _monotonic() + timeout
        collected: list[bytes] = []
        while len(collected) < count:
            collected.extend(self.pop_delivered())
            if len(collected) >= count:
                break
            if _monotonic() >= deadline:
                raise TimeoutError(
                    f"only delivered {len(collected)}/{count} payloads in {timeout}s"
                )
            self._stop.wait(0.02)
        return collected

    def close(self) -> None:
        self._stop.set()
        try:
            self._sock.close()
        except OSError:
            pass
        self._reader.join(timeout=2.0)

    # Introspection for validators.

    @property
    def unacked(self) -> list[int]:
        with self._lock:
            return self._channel.unacked_seqs

    @property
    def buffered(self) -> list[int]:
        with self._lock:
            return self._channel.buffered_seqs

    @property
    def expected_next_seq(self) -> int:
        with self._lock:
            return self._channel.expected_next_seq

    # ---- internals ----

    def _send_raw(self, packet: bytes) -> None:
        # Called from inside self._lock (send / tick_retransmit / ingest).
        outbound = (
            _aead_encrypt(self._relay_key_b64, packet)
            if self._relay_key_b64
            else packet
        )
        if self._tx_loss is not None and not self._tx_loss(outbound):
            return
        wire = frame(self._my_sid, build_relay_payload(self._peer_sid, outbound))
        try:
            self._sock.sendto(wire, self._relay_addr)
        except OSError:
            pass

    def _reader_loop(self) -> None:
        while not self._stop.is_set():
            try:
                data, _ = self._sock.recvfrom(MAX_PACKET_SIZE)
            except socket.timeout:
                continue
            except OSError:
                return
            sender_sid_bytes, body = _unframe(data)
            if sender_sid_bytes.decode("utf-8", errors="replace") != self._peer_sid:
                continue
            if self._rx_loss is not None and not self._rx_loss(body):
                continue
            if self._relay_key_b64:
                opened = _aead_decrypt(self._relay_key_b64, body)
                if opened is None:
                    # Tag failure / wrong key / malformed -> silent drop.
                    continue
                body = opened
            with self._lock:
                self._channel.ingest(body)


def _monotonic() -> float:
    import time

    return time.monotonic()
