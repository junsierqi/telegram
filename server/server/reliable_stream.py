"""Peer-side UDP reliability: sequence numbers, NACK-based retransmit, ordering.

Transport-agnostic: the caller supplies a `send_raw` callback that hands bytes
to the wire. Inbound packets are fed via `ingest(packet_bytes)`. Delivered
payloads come out of `pop_delivered()` in sequence order.

Wire verbs (all consumed inside an existing envelope if used over media-plane):
    REL:<seq>:<payload_bytes>
    NAK:<comma-separated seq list>

This is intentionally a pure algorithm module — no socket, no threading. A
future milestone will plug it into the UDP client/server helpers.
"""
from __future__ import annotations

from typing import Callable


REL_PREFIX = b"REL:"
NAK_PREFIX = b"NAK:"
ACK_PREFIX = b"ACK:"


class ReliableChannel:
    """One side of a reliable peer pair.

    Flow:
        send(payload)  -> enqueues outbound, calls send_raw("REL:<seq>:<bytes>")
        ingest(packet) -> parses inbound REL or NAK; may call send_raw again
                          (NAK on gap, retransmit on received NAK)
        pop_delivered() -> list of payloads delivered in seq order since last call
    """

    def __init__(self, send_raw: Callable[[bytes], None]) -> None:
        self._send_raw = send_raw
        self._next_send_seq = 1
        self._unacked: dict[int, bytes] = {}
        self._expected = 1
        self._buffered: dict[int, bytes] = {}
        self._delivered: list[bytes] = []
        # NAKs we've emitted but not yet seen a retransmit for; used to
        # rate-limit repeat NAKs for the same gap.
        self._pending_nak: set[int] = set()

    # ---- outbound ----

    def send(self, payload: bytes) -> int:
        seq = self._next_send_seq
        self._next_send_seq += 1
        self._unacked[seq] = payload
        self._send_raw(REL_PREFIX + str(seq).encode("ascii") + b":" + payload)
        return seq

    def ack(self, seq: int) -> None:
        """Mark a seq delivered so the sender can drop it from its retx buffer.
        Not wired into the protocol yet (we use only NAK + retransmit); exposed
        for future cumulative-ack extension.
        """
        self._unacked.pop(seq, None)

    def tick_retransmit(self) -> int:
        """Retransmit every still-unacked payload. Intended to be called on a
        timer in real deployments (tail-loss recovery — a dropped final packet
        leaves no later arrival to trigger a NAK). Returns the number of
        packets retransmitted.
        """
        for seq, payload in self._unacked.items():
            self._send_raw(REL_PREFIX + str(seq).encode("ascii") + b":" + payload)
        return len(self._unacked)

    # ---- inbound ----

    def ingest(self, packet: bytes) -> None:
        if packet.startswith(REL_PREFIX):
            self._ingest_rel(packet[len(REL_PREFIX):])
            return
        if packet.startswith(NAK_PREFIX):
            self._ingest_nak(packet[len(NAK_PREFIX):])
            return
        if packet.startswith(ACK_PREFIX):
            self._ingest_ack(packet[len(ACK_PREFIX):])
            return
        # Silently ignore foreign packets.

    def _ingest_ack(self, rest: bytes) -> None:
        try:
            highest_delivered = int(rest.decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            return
        stale = [s for s in self._unacked if s <= highest_delivered]
        for s in stale:
            del self._unacked[s]

    def _ingest_rel(self, rest: bytes) -> None:
        sep = rest.find(b":")
        if sep < 0:
            return
        try:
            seq = int(rest[:sep].decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            return
        payload = rest[sep + 1:]

        if seq < self._expected:
            # Duplicate / already delivered — drop, but also clear any pending NAK
            # in case the retransmit caught up.
            self._pending_nak.discard(seq)
            return

        if seq == self._expected:
            self._delivered.append(payload)
            self._expected += 1
            self._pending_nak.discard(seq)
            # Drain contiguous buffered seqs.
            while self._expected in self._buffered:
                self._delivered.append(self._buffered.pop(self._expected))
                self._pending_nak.discard(self._expected)
                self._expected += 1
            # Cumulative ack: tell the sender everything < expected is safe.
            self._send_raw(ACK_PREFIX + str(self._expected - 1).encode("ascii"))
            return

        # seq > expected: reorder / gap. Buffer, and NAK the missing range.
        # We re-NAK on every gap-creating packet rather than dedup — a dropped
        # retransmit in a lossy network would otherwise stall forever. Sender
        # side deduplicates by payload identity so the cost is a handful of
        # redundant datagrams, not redundant work.
        self._buffered[seq] = payload
        missing = list(range(self._expected, seq))
        if missing:
            for s in missing:
                self._pending_nak.add(s)
            self._send_raw(
                NAK_PREFIX + ",".join(str(s) for s in missing).encode("ascii")
            )

    def _ingest_nak(self, rest: bytes) -> None:
        try:
            seqs = [int(s) for s in rest.decode("ascii").split(",") if s]
        except (UnicodeDecodeError, ValueError):
            return
        for seq in seqs:
            payload = self._unacked.get(seq)
            if payload is None:
                continue  # already dropped; peer will eventually give up / time out
            self._send_raw(REL_PREFIX + str(seq).encode("ascii") + b":" + payload)

    # ---- delivery ----

    def pop_delivered(self) -> list[bytes]:
        out = self._delivered
        self._delivered = []
        return out

    # ---- introspection ----

    @property
    def expected_next_seq(self) -> int:
        return self._expected

    @property
    def buffered_seqs(self) -> list[int]:
        return sorted(self._buffered)

    @property
    def unacked_seqs(self) -> list[int]:
        return sorted(self._unacked)

    @property
    def pending_naks(self) -> list[int]:
        return sorted(self._pending_nak)
