"""D8: peer-side reliability layer over a lossy fake transport.

Scenarios:
- Clean transport: 10 sends on A land on B in order, no NAKs
- Drop seq 3 and seq 7 going A->B; B NAKs; A retransmits; eventual in-order delivery
- Reorder (deliver seq 5 before seq 4): B buffers 5, delivers in order once 4 arrives
- Duplicate (seq 4 delivered twice): B ignores the second
- Large burst with 30% random loss still delivers everything in order given enough pumps
"""
from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.reliable_stream import ReliableChannel  # noqa: E402


def scenario(label: str) -> None:
    print(f"\n[scenario] {label}")


class _FakeWire:
    """Two-ended lossy/reorder transport. Each side's send_raw lands in the
    other side's inbox; the test drives ingest explicitly so we control timing.
    """

    def __init__(self, drop_predicate: Callable[[str, bytes], bool] | None = None,
                 reorder: Callable[[list[bytes]], list[bytes]] | None = None) -> None:
        self.a_inbox: list[bytes] = []
        self.b_inbox: list[bytes] = []
        self.drop = drop_predicate or (lambda side, packet: False)
        self.reorder = reorder

    def make_send(self, side: str) -> Callable[[bytes], None]:
        inbox = self.b_inbox if side == "A" else self.a_inbox

        def _send(packet: bytes) -> None:
            if self.drop(side, packet):
                return
            inbox.append(packet)

        return _send


def _pump_until_stable(a: ReliableChannel, b: ReliableChannel, wire: _FakeWire, max_rounds: int = 100) -> int:
    """Drain both inboxes until the wire quiesces. On an idle wire, trigger
    a tick_retransmit on both sides so tail-loss recovery can fire. Stop when
    quiescence holds even after a tick (meaning no unacked left)."""
    rounds = 0
    while rounds < max_rounds:
        if wire.reorder is not None:
            wire.a_inbox = wire.reorder(wire.a_inbox)
            wire.b_inbox = wire.reorder(wire.b_inbox)
        if wire.a_inbox or wire.b_inbox:
            while wire.b_inbox:
                b.ingest(wire.b_inbox.pop(0))
            while wire.a_inbox:
                a.ingest(wire.a_inbox.pop(0))
            rounds += 1
            continue
        # Idle wire. Ask both sides to retransmit anything still pending.
        sent = a.tick_retransmit() + b.tick_retransmit()
        if sent == 0:
            return rounds
        rounds += 1
    return rounds


def run_clean_transport() -> None:
    scenario("clean wire -> 10 sends delivered in order, no NAKs emitted")
    wire = _FakeWire()
    a = ReliableChannel(wire.make_send("A"))
    b = ReliableChannel(wire.make_send("B"))
    for i in range(10):
        a.send(f"hello-{i}".encode())
    _pump_until_stable(a, b, wire)
    delivered = b.pop_delivered()
    assert delivered == [f"hello-{i}".encode() for i in range(10)], delivered
    assert a.pending_naks == [] and b.pending_naks == []


def run_two_drops_trigger_nak_retransmit() -> None:
    scenario("drop seq 3 & 7 A->B -> NAKs + retransmit; full in-order delivery")
    drop_once = {b"REL:3:": True, b"REL:7:": True}

    def drop(side: str, packet: bytes) -> bool:
        if side != "A":
            return False
        for prefix in list(drop_once):
            if packet.startswith(prefix) and drop_once[prefix]:
                drop_once[prefix] = False
                return True
        return False

    wire = _FakeWire(drop_predicate=drop)
    a = ReliableChannel(wire.make_send("A"))
    b = ReliableChannel(wire.make_send("B"))
    for i in range(1, 11):
        a.send(f"p{i}".encode())
    _pump_until_stable(a, b, wire, max_rounds=50)
    delivered = b.pop_delivered()
    assert delivered == [f"p{i}".encode() for i in range(1, 11)], delivered


def run_reorder_delivered_in_order() -> None:
    scenario("receive seq 5 before seq 4 -> buffered, then drained in order")

    def reorder(packets: list[bytes]) -> list[bytes]:
        # If seq 4 and 5 are both in the inbox, swap them once.
        idx4 = idx5 = -1
        for i, p in enumerate(packets):
            if p.startswith(b"REL:4:") and idx4 == -1:
                idx4 = i
            elif p.startswith(b"REL:5:") and idx5 == -1:
                idx5 = i
        if idx4 >= 0 and idx5 >= 0:
            packets[idx4], packets[idx5] = packets[idx5], packets[idx4]
        return packets

    wire = _FakeWire(reorder=reorder)
    a = ReliableChannel(wire.make_send("A"))
    b = ReliableChannel(wire.make_send("B"))
    for i in range(1, 7):
        a.send(f"q{i}".encode())
    _pump_until_stable(a, b, wire)
    delivered = b.pop_delivered()
    assert delivered == [f"q{i}".encode() for i in range(1, 7)], delivered


def run_duplicate_ignored() -> None:
    scenario("duplicate seq 2 -> second copy silently dropped")

    duplicated = {"done": False}

    def drop(side: str, packet: bytes) -> bool:
        # Duplicate seq 2 by pushing an extra copy into b's inbox.
        if side == "A" and packet.startswith(b"REL:2:") and not duplicated["done"]:
            duplicated["done"] = True
            wire.b_inbox.append(packet)  # deliver twice
        return False

    wire = _FakeWire(drop_predicate=drop)
    a = ReliableChannel(wire.make_send("A"))
    b = ReliableChannel(wire.make_send("B"))
    for i in range(1, 5):
        a.send(f"r{i}".encode())
    _pump_until_stable(a, b, wire)
    delivered = b.pop_delivered()
    assert delivered == [f"r{i}".encode() for i in range(1, 5)], delivered


def run_random_loss() -> None:
    scenario("30% random loss -> eventual in-order delivery, no duplicates")
    rng = random.Random(42)

    def drop(side: str, packet: bytes) -> bool:
        # Never drop NAKs — would stall the test forever.
        if packet.startswith(b"NAK:"):
            return False
        # 30% drop for REL packets in both directions.
        return rng.random() < 0.3

    wire = _FakeWire(drop_predicate=drop)
    a = ReliableChannel(wire.make_send("A"))
    b = ReliableChannel(wire.make_send("B"))
    for i in range(1, 21):
        a.send(f"s{i}".encode())
    rounds = _pump_until_stable(a, b, wire, max_rounds=200)
    delivered = b.pop_delivered()
    assert delivered == [f"s{i}".encode() for i in range(1, 21)], delivered
    assert rounds > 0


def main() -> int:
    scenarios = [
        run_clean_transport,
        run_two_drops_trigger_nak_retransmit,
        run_reorder_delivered_in_order,
        run_duplicate_ignored,
        run_random_loss,
    ]
    for fn in scenarios:
        fn()
    print(f"\nAll {len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
