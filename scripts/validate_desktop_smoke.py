"""Runtime validator for the C1 Qt desktop baseline.

Starts the Python TCP server and runs app_desktop.exe in --smoke mode.
The smoke path uses the same ControlPlaneClient as the GUI window and
verifies login, conversation_sync, and message_send without requiring a
display server or manual UI interaction.
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
APP_DESKTOP_CANDIDATES = [
    REPO / "build-verify" / "client" / "src" / "Debug" / "app_desktop.exe",
    REPO / "build-codex" / "client" / "src" / "Debug" / "app_desktop.exe",
    REPO / "build" / "client" / "src" / "Debug" / "app_desktop.exe",
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
    app_desktop = next((p for p in APP_DESKTOP_CANDIDATES if p.exists()), None)
    if app_desktop is None:
        searched = ", ".join(str(p) for p in APP_DESKTOP_CANDIDATES)
        print(f"[FAIL] app_desktop.exe not built; searched: {searched}")
        print("       configure with Qt6 available, then run: cmake --build build --config Debug")
        return 1

    port = _free_port()
    tmp_state = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    tmp_state.close()
    state_path = tmp_state.name
    tmp_cache = tempfile.NamedTemporaryFile(suffix=".desktop-cache.json", delete=False)
    tmp_cache.close()
    cache_path = tmp_cache.name
    save_dir = tempfile.TemporaryDirectory()

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
                "--smoke",
                "--smoke-attachment",
                "--user",
                "alice",
                "--password",
                "alice_pw",
                "--device",
                "dev_alice_qt_smoke",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--cache-file",
                cache_path,
                "--smoke-save-dir",
                save_dir.name,
            ],
            cwd=str(REPO),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=8,
            env=os.environ.copy(),
        )
        print(result.stdout, end="")
        if result.returncode != 0:
            print(f"[FAIL] app_desktop --smoke exited {result.returncode}")
            return 1
        if "desktop smoke ok:" not in result.stdout:
            print("[FAIL] smoke success marker missing")
            return 1
        if "desktop devices smoke ok:" not in result.stdout:
            print("[FAIL] device list smoke success marker missing")
            return 1
        if "desktop navigation search smoke ok:" not in result.stdout:
            print("[FAIL] navigation/search smoke success marker missing")
            return 1
        if "desktop message actions smoke ok:" not in result.stdout:
            print("[FAIL] message actions smoke success marker missing")
            return 1
        if "desktop server message search smoke ok:" not in result.stdout:
            print("[FAIL] server message search smoke success marker missing")
            return 1
        if "desktop history page smoke ok:" not in result.stdout:
            print("[FAIL] history page smoke success marker missing")
            return 1
        if "desktop profile smoke ok:" not in result.stdout:
            print("[FAIL] profile smoke success marker missing")
            return 1
        if "desktop user search smoke ok:" not in result.stdout:
            print("[FAIL] user search smoke success marker missing")
            return 1
        if "desktop contacts smoke ok:" not in result.stdout:
            print("[FAIL] contacts smoke success marker missing")
            return 1
        if "desktop group smoke ok:" not in result.stdout:
            print("[FAIL] group smoke success marker missing")
            return 1
        if "desktop attachment smoke ok:" not in result.stdout:
            print("[FAIL] attachment smoke success marker missing")
            return 1
        if "desktop attachment save smoke ok:" not in result.stdout:
            print("[FAIL] attachment save smoke success marker missing")
            return 1
        if "desktop attachment upload progress smoke ok: stages=queued,uploading,uploaded" not in result.stdout:
            print("[FAIL] attachment upload progress marker missing")
            return 1
        if "desktop attachment download progress smoke ok: stages=downloading,downloaded,saving,saved" not in result.stdout:
            print("[FAIL] attachment download progress marker missing")
            return 1
        saved = Path(save_dir.name) / "desktop-smoke.txt"
        if saved.read_text(encoding="utf-8") != "desktop attachment smoke bytes":
            print("[FAIL] saved attachment content mismatch")
            return 1
        reg_result = subprocess.run(
            [
                str(app_desktop),
                "--smoke-register",
                "--user",
                "qt_reg_smoke",
                "--password",
                "qt_reg_pw_123",
                "--display-name",
                "Qt Register Smoke",
                "--device",
                "dev_qt_reg_smoke",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--cache-file",
                cache_path,
            ],
            cwd=str(REPO),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=8,
            env=os.environ.copy(),
        )
        print(reg_result.stdout, end="")
        if reg_result.returncode != 0:
            print(f"[FAIL] app_desktop --smoke-register exited {reg_result.returncode}")
            return 1
        if "desktop register smoke ok:" not in reg_result.stdout:
            print("[FAIL] registration smoke success marker missing")
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
        try:
            Path(cache_path).unlink(missing_ok=True)
        except Exception:
            pass
        save_dir.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
