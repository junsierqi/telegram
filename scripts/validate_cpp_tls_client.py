"""Runtime validator for C++ direct TLS control-plane client support."""
from __future__ import annotations

import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts.generate_tls_dev_cert import generate_self_signed_cert  # noqa: E402

APP_CHAT_CANDIDATES = [
    REPO / "build-verify" / "client" / "src" / "Debug" / "app_chat.exe",
    REPO / "build-codex" / "client" / "src" / "Debug" / "app_chat.exe",
    REPO / "build" / "client" / "src" / "Debug" / "app_chat.exe",
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
    app_chat = next((p for p in APP_CHAT_CANDIDATES if p.exists()), None)
    if app_chat is None:
        searched = ", ".join(str(p) for p in APP_CHAT_CANDIDATES)
        print(f"[FAIL] app_chat.exe not built; searched: {searched}")
        print("       run: cmake --build build-codex --config Debug")
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        cert_dir = Path(tmp)
        cert_file = cert_dir / "server.crt"
        key_file = cert_dir / "server.key"
        generate_self_signed_cert(
            cert_file=cert_file,
            key_file=key_file,
            common_name="localhost",
            overwrite=True,
        )
        port = _free_port()

        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "server.main",
                "--tcp-server",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--tls-cert-file",
                str(cert_file),
                "--tls-key-file",
                str(key_file),
            ],
            cwd=str(REPO),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            if not _wait_for_port(port, 5.0):
                print("[FAIL] TLS server did not open TCP port")
                return 1

            proc = subprocess.Popen(
                [
                    str(app_chat),
                    "--user",
                    "alice",
                    "--password",
                    "alice_pw",
                    "--device",
                    "dev_cpp_tls_smoke",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--tls",
                    "--tls-insecure",
                    "--tls-server-name",
                    "localhost",
                    "--heartbeat",
                    "0",
                ],
                cwd=str(REPO),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            assert proc.stdin is not None
            proc.stdin.write("/q\n")
            proc.stdin.flush()
            output, _ = proc.communicate(timeout=8)
            if proc.returncode != 0:
                print("[FAIL] app_chat TLS run failed")
                print(output)
                return 1
            if "logged in as u_alice" not in output or "conv_alice_bob" not in output:
                print("[FAIL] app_chat TLS login/sync output missing expected markers")
                print(output)
                return 1
            print("[ok ] app_chat logged in through native TLS")
            print("[ok ] initial sync worked through native TLS")
            print("passed 2/2")
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


if __name__ == "__main__":
    raise SystemExit(main())
