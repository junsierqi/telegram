"""Validate production-like no-seed server startup.

The normal validator suite keeps Alice/Bob seed data for historical smoke
coverage. This script covers the production mode added for the desktop
mock-data audit: no built-in users/devices/conversations, while registration
and persistence still work.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication, create_app  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402


REPO = Path(__file__).resolve().parent.parent


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_port(port: int, timeout: float = 4.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _register(app: ServerApplication, username: str, device_id: str, seq: int):
    return app.dispatch(
        {
            **make_envelope(
                MessageType.REGISTER_REQUEST,
                correlation_id=f"corr_reg_{seq}",
                sequence=seq,
            ),
            "payload": {
                "username": username,
                "password": "valid_pw_123",
                "display_name": username.title(),
                "device_id": device_id,
            },
        }
    )


def _login(app: ServerApplication, username: str, device_id: str, seq: int):
    return app.dispatch(
        {
            **make_envelope(
                MessageType.LOGIN_REQUEST,
                correlation_id=f"corr_login_{seq}",
                sequence=seq,
            ),
            "payload": {
                "username": username,
                "password": "valid_pw_123",
                "device_id": device_id,
            },
        }
    )


def test_in_memory_no_seed_starts_empty() -> None:
    app = ServerApplication(seed_defaults=False)
    assert app.state.users == {}
    assert app.state.devices == {}
    assert app.state.conversations == {}


def test_create_app_forwards_seed_flag() -> None:
    app = create_app(seed_defaults=False)
    assert app.state.users == {}
    assert app.state.devices == {}
    assert app.state.conversations == {}


def test_no_seed_registration_login_round_trip() -> None:
    app = ServerApplication(seed_defaults=False)
    reg = _register(app, "firstuser", "dev_first", 1)
    assert reg["type"] == "register_response", reg
    assert len(app.state.users) == 1
    assert "u_alice" not in app.state.users
    login = _login(app, "firstuser", "dev_first", 2)
    assert login["type"] == "login_response", login
    assert login["payload"]["user_id"] == reg["payload"]["user_id"]


def test_no_seed_json_persistence_round_trip() -> None:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        app = ServerApplication(state_file=path, seed_defaults=False)
        _register(app, "persisted", "dev_persisted", 1)

        restored = ServerApplication(state_file=path, seed_defaults=False)
        assert "u_alice" not in restored.state.users
        assert len(restored.state.users) == 1
        login = _login(restored, "persisted", "dev_persisted", 2)
        assert login["type"] == "login_response", login
    finally:
        Path(path).unlink(missing_ok=True)


def test_env_flag_reaches_cli_startup() -> None:
    env = os.environ.copy()
    env["TELEGRAM_NO_SEED_DATA"] = "1"
    env["TELEGRAM_HOST"] = "127.0.0.1"
    port = _free_port()
    env["TELEGRAM_PORT"] = str(port)
    result = subprocess.Popen(
        [sys.executable, "-m", "server.main", "--tcp-server"],
        cwd=str(REPO),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    try:
        assert _wait_for_port(port), "server did not bind TCP port"
        assert result.poll() is None, "server exited early"
    finally:
        result.terminate()
        try:
            result.wait(timeout=2)
        except subprocess.TimeoutExpired:
            result.kill()


SCENARIOS = [
    ("in_memory_no_seed_starts_empty", test_in_memory_no_seed_starts_empty),
    ("create_app_forwards_seed_flag", test_create_app_forwards_seed_flag),
    ("no_seed_registration_login_round_trip", test_no_seed_registration_login_round_trip),
    ("no_seed_json_persistence_round_trip", test_no_seed_json_persistence_round_trip),
    ("env_flag_reaches_cli_startup", test_env_flag_reaches_cli_startup),
]


def main() -> int:
    failures: list[str] = []
    for name, fn in SCENARIOS:
        try:
            fn()
            print(f"[ok ] {name}")
        except Exception as exc:
            failures.append(f"{name}: {exc}")
            print(f"[FAIL] {name}: {exc}")
    print(f"passed {len(SCENARIOS) - len(failures)}/{len(SCENARIOS)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
