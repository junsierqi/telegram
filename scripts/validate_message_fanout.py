"""Validator for REQ-CHAT-FANOUT.

Verifies that when one participant sends a message, all OTHER participant
sessions receive an unsolicited MESSAGE_DELIVER push on their live control-
plane connection. The sender's own session receives the normal response but
not a duplicate push. Logged-out participants don't cause failures.
"""
from __future__ import annotations

import json
import queue
import socket
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.control_plane import ThreadedControlPlaneServer  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Client:
    def __init__(self, host: str, port: int) -> None:
        self.sock = socket.create_connection((host, port))
        self._file = self.sock.makefile("rb")
        self._inbox: queue.Queue[dict] = queue.Queue()
        self.session_id = ""
        self.user_id = ""
        self._seq = 0
        self._stop = False
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        while not self._stop:
            try:
                line = self._file.readline()
            except Exception:
                return
            if not line:
                return
            try:
                self._inbox.put(json.loads(line.decode("utf-8")))
            except Exception:
                return

    def send(self, obj: dict) -> None:
        self.sock.sendall((json.dumps(obj) + "\n").encode("utf-8"))

    def next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def login(self, username: str, password: str, device_id: str, corr: str) -> dict:
        self.send(
            {
                "type": "login_request",
                "correlation_id": corr,
                "session_id": "",
                "actor_user_id": "",
                "sequence": self.next_seq(),
                "payload": {
                    "username": username,
                    "password": password,
                    "device_id": device_id,
                },
            }
        )
        resp = self.expect(correlation_id=corr)
        payload = resp["payload"]
        self.session_id = payload["session_id"]
        self.user_id = payload["user_id"]
        return resp

    def expect(
        self,
        *,
        correlation_id: str | None = None,
        type_: str | None = None,
        timeout: float = 1.5,
    ) -> dict:
        deadline = time.time() + timeout
        stash: list[dict] = []
        try:
            while True:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                try:
                    msg = self._inbox.get(timeout=remaining)
                except queue.Empty:
                    break
                if correlation_id is not None and msg.get("correlation_id") != correlation_id:
                    stash.append(msg)
                    continue
                if type_ is not None and msg.get("type") != type_:
                    stash.append(msg)
                    continue
                return msg
        finally:
            for item in stash:
                self._inbox.put(item)
        raise AssertionError(
            f"Did not receive expected frame (correlation_id={correlation_id!r}, type={type_!r}) "
            f"within {timeout}s. Stashed: {stash}"
        )

    def assert_silent(self, *, type_: str, timeout: float = 0.3) -> None:
        """Fail if any message of this type arrives within the window."""
        deadline = time.time() + timeout
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                return
            try:
                msg = self._inbox.get(timeout=remaining)
            except queue.Empty:
                return
            if msg.get("type") == type_:
                raise AssertionError(f"Expected no {type_} frame, but got: {msg}")
            # stash non-matching frames back — but since order matters for later
            # expect() calls, put them back at the end of the queue
            self._inbox.put(msg)

    def close(self) -> None:
        self._stop = True
        try:
            self.sock.close()
        except Exception:
            pass


def _start_server() -> tuple[ThreadedControlPlaneServer, int, ServerApplication]:
    app = ServerApplication()
    port = _free_port()
    server = ThreadedControlPlaneServer(("127.0.0.1", port), app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # wait until accepting
    deadline = time.time() + 2.0
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                break
        except OSError:
            time.sleep(0.05)
    return server, port, app


def _shutdown(server: ThreadedControlPlaneServer) -> None:
    server.shutdown()
    server.server_close()


def test_push_to_other_participant(port: int) -> None:
    alice = _Client("127.0.0.1", port)
    bob = _Client("127.0.0.1", port)
    try:
        alice.login("alice", "alice_pw", "dev_alice_win", "corr_a_login")
        bob.login("bob", "bob_pw", "dev_bob_win", "corr_b_login")

        alice.send(
            {
                "type": "message_send",
                "correlation_id": "corr_msg_a",
                "session_id": alice.session_id,
                "actor_user_id": alice.user_id,
                "sequence": alice.next_seq(),
                "payload": {"conversation_id": "conv_alice_bob", "text": "hi bob"},
            }
        )

        # Alice gets the response tied to her correlation_id
        alice_resp = alice.expect(correlation_id="corr_msg_a")
        assert alice_resp["type"] == "message_deliver", f"Unexpected: {alice_resp}"
        assert alice_resp["payload"]["text"] == "hi bob"
        assert alice_resp["payload"]["sender_user_id"] == "u_alice"

        # Bob gets an unsolicited MESSAGE_DELIVER push with push_* correlation_id
        bob_push = bob.expect(type_="message_deliver")
        assert bob_push["correlation_id"].startswith("push_"), bob_push
        assert bob_push["session_id"] == bob.session_id
        assert bob_push["payload"]["text"] == "hi bob"
        assert bob_push["payload"]["sender_user_id"] == "u_alice"
        assert bob_push["payload"]["conversation_id"] == "conv_alice_bob"

        # Alice must NOT receive a duplicate push
        alice.assert_silent(type_="message_deliver", timeout=0.2)
    finally:
        alice.close()
        bob.close()


def test_push_to_other_session_of_same_user(port: int) -> None:
    """Alice logged in twice — sending from session A pushes to session B."""
    alice_a = _Client("127.0.0.1", port)
    alice_b = _Client("127.0.0.1", port)
    try:
        alice_a.login("alice", "alice_pw", "dev_alice_win", "corr_aa_login")
        alice_b.login("alice", "alice_pw", "dev_alice_win", "corr_ab_login")
        assert alice_a.session_id != alice_b.session_id

        alice_a.send(
            {
                "type": "message_send",
                "correlation_id": "corr_msg_aa",
                "session_id": alice_a.session_id,
                "actor_user_id": alice_a.user_id,
                "sequence": alice_a.next_seq(),
                "payload": {"conversation_id": "conv_alice_bob", "text": "multi-device"},
            }
        )
        alice_a.expect(correlation_id="corr_msg_aa")
        push = alice_b.expect(type_="message_deliver")
        assert push["session_id"] == alice_b.session_id
        assert push["payload"]["text"] == "multi-device"
        alice_a.assert_silent(type_="message_deliver", timeout=0.2)
    finally:
        alice_a.close()
        alice_b.close()


def test_no_crash_when_participant_logged_out(port: int) -> None:
    """Only Alice logged in. Her send must succeed; Bob simply won't receive a push."""
    alice = _Client("127.0.0.1", port)
    try:
        alice.login("alice", "alice_pw", "dev_alice_win", "corr_alone_login")
        alice.send(
            {
                "type": "message_send",
                "correlation_id": "corr_alone_msg",
                "session_id": alice.session_id,
                "actor_user_id": alice.user_id,
                "sequence": alice.next_seq(),
                "payload": {"conversation_id": "conv_alice_bob", "text": "anyone there?"},
            }
        )
        resp = alice.expect(correlation_id="corr_alone_msg")
        assert resp["type"] == "message_deliver"
        assert resp["payload"]["text"] == "anyone there?"
    finally:
        alice.close()


def test_multiple_messages_arrive_in_order(port: int) -> None:
    alice = _Client("127.0.0.1", port)
    bob = _Client("127.0.0.1", port)
    try:
        alice.login("alice", "alice_pw", "dev_alice_win", "corr_order_a")
        bob.login("bob", "bob_pw", "dev_bob_win", "corr_order_b")

        for n in range(5):
            alice.send(
                {
                    "type": "message_send",
                    "correlation_id": f"corr_order_{n}",
                    "session_id": alice.session_id,
                    "actor_user_id": alice.user_id,
                    "sequence": alice.next_seq(),
                    "payload": {
                        "conversation_id": "conv_alice_bob",
                        "text": f"ordered_{n}",
                    },
                }
            )
            alice.expect(correlation_id=f"corr_order_{n}")

        received_texts = []
        for _ in range(5):
            push = bob.expect(type_="message_deliver", timeout=2.0)
            received_texts.append(push["payload"]["text"])
        assert received_texts == [f"ordered_{n}" for n in range(5)], received_texts
    finally:
        alice.close()
        bob.close()


def test_non_participant_not_notified(port: int) -> None:
    """A third user not in the conversation must not get a push.

    There are only two users in the fixture (alice, bob), both in conv_alice_bob.
    So simulate by logging in an alice-session-only connection that is NOT a
    participant of a new one-sided conversation. Since conv_alice_bob has both
    as participants we can't test a true third-party here — but we can confirm
    the logged-out participant path (covered above). Skip.
    """
    # Intentionally a no-op — seed data has no third user. See docstring.


SCENARIOS = [
    ("push_to_other_participant", test_push_to_other_participant),
    ("push_to_other_session_of_same_user", test_push_to_other_session_of_same_user),
    ("no_crash_when_participant_logged_out", test_no_crash_when_participant_logged_out),
    ("multiple_messages_arrive_in_order", test_multiple_messages_arrive_in_order),
]


def main() -> int:
    failures: list[str] = []
    for name, fn in SCENARIOS:
        server, port, _app = _start_server()
        try:
            fn(port)
            print(f"[ok ] {name}")
        except Exception as exc:
            failures.append(f"{name}: {exc}")
            print(f"[FAIL] {name}: {exc}")
        finally:
            _shutdown(server)
    print(f"passed {len(SCENARIOS) - len(failures)}/{len(SCENARIOS)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
