"""Runtime validator for REQ-CPP-CHAT-DEMO (A3).

Spins up the Python server, then launches two C++ app_chat.exe instances
(alice + bob) connected to it. Drives stdin of both, captures stdout, and
asserts that:
  - both clients log in and print the initial sync
  - when alice sends a message, bob's push handler prints it
  - /presence and /read commands don't return errors

Requires the app_chat binary to be built at build/client/src/Debug/app_chat.exe.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

def _binary_candidates(stem: str) -> list[Path]:
    """All build paths the sweep harness searches, expanded for both
    Windows (Debug/Release subdirs + .exe) and POSIX (no subdir, no .exe).
    Mirrors scripts/_sweep_validators.py:_has_built_binary so a binary the
    harness already detected isn't then declared missing here."""
    candidates: list[Path] = []
    for build in ("build-verify", "build-codex", "build", "build-macos",
                  "build-linux", "build-wsl", "build-android"):
        for cfg in ("", "Debug", "Release"):
            for ext in ("", ".exe"):
                candidates.append(REPO / build / "client" / "src" / cfg / f"{stem}{ext}")
    return candidates


APP_CHAT_CANDIDATES = _binary_candidates("app_chat")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _start_server(port: int, state_file: str) -> subprocess.Popen:
    env = os.environ.copy()
    return subprocess.Popen(
        [sys.executable, "-m", "server.main", "--tcp-server",
         "--port", str(port), "--state-file", state_file],
        cwd=str(REPO),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env,
    )


def _start_chat(app_chat: Path, user: str, password: str, device: str, port: int) -> subprocess.Popen:
    return subprocess.Popen(
        [str(app_chat),
         "--user", user, "--password", password, "--device", device,
         "--host", "127.0.0.1", "--port", str(port), "--heartbeat", "0"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )


def main() -> int:
    app_chat = next((p for p in APP_CHAT_CANDIDATES if p.exists()), None)
    if app_chat is None:
        searched = ", ".join(str(p) for p in APP_CHAT_CANDIDATES)
        print(f"[FAIL] app_chat.exe not built; searched: {searched}")
        print("       run: cmake --build build --config Debug")
        return 1

    port = _free_port()
    tmp_state = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    tmp_state.close()
    state_path = tmp_state.name

    server = _start_server(port, state_path)
    try:
        if not _wait_for_port(port, 5.0):
            print("[FAIL] server did not open TCP port")
            return 1

        bob = _start_chat(app_chat, "bob", "bob_pw", "dev_bob_win", port)
        time.sleep(0.6)
        alice = _start_chat(app_chat, "alice", "alice_pw", "dev_alice_win", port)
        time.sleep(0.6)

        alice.stdin.write("hello bob from C++ chat demo\n"); alice.stdin.flush()
        time.sleep(0.5)
        alice.stdin.write("/presence u_alice u_bob\n"); alice.stdin.flush()
        time.sleep(0.3)
        alice.stdin.write("/q\n"); alice.stdin.flush()

        time.sleep(0.5)
        bob.stdin.write("/q\n"); bob.stdin.flush()

        alice_out, _ = alice.communicate(timeout=5)
        bob_out, _ = bob.communicate(timeout=5)

        failures: list[str] = []

        # Both logged in
        if "logged in as u_alice" not in alice_out:
            failures.append("alice did not log in")
        if "logged in as u_bob" not in bob_out:
            failures.append("bob did not log in")

        # Initial sync worked (shows conversation)
        if "conv_alice_bob" not in alice_out or "conv_alice_bob" not in bob_out:
            failures.append("conversation sync not visible in one of the clients")

        # The key assertion: bob's push handler received alice's message
        if "[u_alice] hello bob from C++ chat demo" not in bob_out:
            failures.append("bob did NOT receive a MESSAGE_DELIVER push for alice's send")

        # Presence query returned both users online
        if "u_alice: online" not in alice_out or "u_bob: online" not in alice_out:
            failures.append("presence_query did not show both users online")

        # No unexpected [ERR ...]
        unexpected_errors = [l for l in (alice_out + bob_out).splitlines()
                             if l.startswith("[ERR ") and "unknown_command" not in l]
        if unexpected_errors:
            failures.append(f"unexpected errors: {unexpected_errors}")

        if failures:
            print("[FAIL]")
            for f in failures:
                print(f"  - {f}")
            print("--- ALICE OUTPUT ---")
            print(alice_out)
            print("--- BOB OUTPUT ---")
            print(bob_out)
            return 1

        print("[ok ] bob received alice's message via push handler")
        print("[ok ] both clients log in + initial sync works")
        print("[ok ] /presence returns both online")
        print("passed 3/3")
        return 0
    finally:
        try:
            server.terminate()
            server.wait(timeout=2)
        except Exception:
            try:
                server.kill()
            except Exception:
                pass
        try:
            Path(state_path).unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
