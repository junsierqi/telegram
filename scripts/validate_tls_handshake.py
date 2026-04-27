"""End-to-end TLS smoke for the TCP control plane."""
from __future__ import annotations

import json
import socket
import ssl
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.generate_tls_dev_cert import generate_self_signed_cert  # noqa: E402
from server.server.app import ServerApplication  # noqa: E402
from server.server.control_plane import ThreadedControlPlaneServer  # noqa: E402


def test_tls_login_round_trip() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        cert_file, key_file = generate_self_signed_cert(
            cert_file=Path(tmpdir) / "server.crt",
            key_file=Path(tmpdir) / "server.key",
        )
        app = ServerApplication()
        server = ThreadedControlPlaneServer(
            ("127.0.0.1", 0),
            app,
            tls_cert_file=str(cert_file),
            tls_key_file=str(key_file),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        try:
            context = ssl.create_default_context(cafile=str(cert_file))
            with socket.create_connection((host, port), timeout=3) as raw:
                with context.wrap_socket(raw, server_hostname="localhost") as tls_sock:
                    request = {
                        "type": "login_request",
                        "correlation_id": "tls_login",
                        "session_id": "",
                        "actor_user_id": "",
                        "sequence": 1,
                        "payload": {
                            "username": "alice",
                            "password": "alice_pw",
                            "device_id": "dev_tls_smoke",
                        },
                    }
                    tls_sock.sendall((json.dumps(request) + "\n").encode("utf-8"))
                    response = json.loads(tls_sock.recv(65536).decode("utf-8"))
                    assert response["type"] == "login_response", response
                    assert response["payload"]["session_id"].startswith("sess_"), response
                    assert server.tls_enabled is True
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


SCENARIOS = [("tls_login_round_trip", test_tls_login_round_trip)]


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
