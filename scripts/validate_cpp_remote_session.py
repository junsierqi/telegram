"""Drives the new ControlPlaneClient remote-control RPCs end-to-end.

Spawns a Python server, then runs build-verify/.../remote_session_smoke.exe
which logs in as alice and exercises each new RPC against fake session ids
to verify error responses round-trip cleanly through the C++ parsers.
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
SMOKE_CANDIDATES = [
    REPO / "build-verify" / "client" / "src" / "Debug" / "remote_session_smoke.exe",
    REPO / "build-codex" / "client" / "src" / "Debug" / "remote_session_smoke.exe",
    REPO / "build" / "client" / "src" / "Debug" / "remote_session_smoke.exe",
]


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


def main() -> int:
    smoke = next((p for p in SMOKE_CANDIDATES if p.exists()), None)
    if smoke is None:
        print("[FAIL] remote_session_smoke.exe not built; searched:",
              ", ".join(str(p) for p in SMOKE_CANDIDATES))
        return 1

    port = _free_port()
    tmp_state = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    tmp_state.close()
    state_path = tmp_state.name

    server = subprocess.Popen(
        [sys.executable, "-m", "server.main", "--tcp-server",
         "--port", str(port), "--state-file", state_path],
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

        # Pre-register alice via an existing client so the smoke can log in.
        # The smoke uses a fixed --device id so we register that account here.
        # The server creates user + device + session in one register_request.
        import json
        with socket.create_connection(("127.0.0.1", port)) as s:
            req = json.dumps({
                "type": "register_request",
                "correlation_id": "reg_1",
                "session_id": "",
                "actor_user_id": "",
                "payload": {
                    "username": "alice",
                    "password": "alice_pw",
                    "display_name": "Alice",
                    "device_id": "dev_remote_smoke",
                },
            }) + "\n"
            s.sendall(req.encode("utf-8"))
            s.settimeout(2.0)
            data = b""
            while not data.endswith(b"\n"):
                chunk = s.recv(4096)
                if not chunk: break
                data += chunk
            resp = json.loads(data.decode("utf-8").strip())
            if resp.get("type") not in ("register_response", "error"):
                print(f"[FAIL] register prep returned {resp}")
                return 1

        result = subprocess.run(
            [str(smoke),
             "--user", "alice",
             "--password", "alice_pw",
             "--device", "dev_remote_smoke",
             "--host", "127.0.0.1",
             "--port", str(port)],
            cwd=str(REPO),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=15,
            env=os.environ.copy(),
        )
        print(result.stdout, end="")
        if result.returncode != 0:
            print(f"[FAIL] remote_session_smoke exited {result.returncode}")
            return 1
        if "passed " not in result.stdout:
            print("[FAIL] success marker missing")
            return 1
        return 0
    finally:
        try:
            server.terminate()
            server.wait(timeout=2)
        except Exception:
            try: server.kill()
            except Exception: pass
        try: Path(state_path).unlink(missing_ok=True)
        except Exception: pass


if __name__ == "__main__":
    raise SystemExit(main())
