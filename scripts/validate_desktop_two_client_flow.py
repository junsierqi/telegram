"""End-to-end desktop flow against the real TCP backend.

This validator deliberately avoids mock transport/state:

- starts `python -m server.main --tcp-server` with an isolated state file
- runs `app_desktop --smoke-two-client-flow`
- the desktop binary logs in Alice and Bob through ControlPlaneClient
- both users add each other as contacts
- Alice sends a message and Bob receives it via conversation_sync
- Bob replies and Alice receives it via conversation_sync
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent


def _binary_candidates(stem: str) -> list[Path]:
    candidates: list[Path] = []
    for build in (
        "build-ui-verify",
        "build-verify",
        "build-codex",
        "build",
        "build-macos",
        "build-linux",
        "build-wsl",
        "build-android",
    ):
        for cfg in ("", "Debug", "Release"):
            for ext in ("", ".exe"):
                candidates.append(REPO / build / "client" / "src" / cfg / f"{stem}{ext}")
    return candidates


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_port(port: int, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def main() -> int:
    app_desktop = next((p for p in _binary_candidates("app_desktop") if p.exists()), None)
    if app_desktop is None:
        print("[FAIL] app_desktop not built")
        return 1

    port = _free_port()
    tmp_state = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    tmp_state.close()
    state_path = tmp_state.name
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "server.main",
            "--tcp-server",
            "--port",
            str(port),
            "--state-file",
            state_path,
        ],
        cwd=str(REPO),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=os.environ.copy(),
    )
    try:
        if not _wait_for_port(port):
            print("[FAIL] server did not open TCP port")
            return 1

        result = subprocess.run(
            [
                str(app_desktop),
                "--smoke-two-client-flow",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--conversation",
                "conv_alice_bob",
            ],
            cwd=str(REPO),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=10,
            env=os.environ.copy(),
        )
        print(result.stdout, end="")
        if result.returncode != 0:
            print(f"[FAIL] app_desktop --smoke-two-client-flow exited {result.returncode}")
            return 1
        marker = "desktop two-client flow smoke ok:"
        if marker not in result.stdout:
            print("[FAIL] success marker missing")
            return 1
        for token in ("alice=u_alice", "bob=u_bob", "contacts=mutual", "conversation=conv_alice_bob"):
            if token not in result.stdout:
                print(f"[FAIL] expected token missing: {token}")
                return 1
        print("passed 1/1")
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
