"""Validator for native TLS control-plane configuration."""
from __future__ import annotations

import ssl
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.control_plane import ThreadedControlPlaneServer  # noqa: E402


def test_plain_control_plane_stays_default() -> None:
    server = ThreadedControlPlaneServer(("127.0.0.1", 0), ServerApplication())
    try:
        assert server.tls_enabled is False
    finally:
        server.server_close()


def test_tls_requires_cert_and_key_together() -> None:
    try:
        ThreadedControlPlaneServer(
            ("127.0.0.1", 0),
            ServerApplication(),
            tls_cert_file="server.crt",
        )
    except ValueError as exc:
        assert "configured together" in str(exc)
        return
    raise AssertionError("TLS cert without key should be rejected")


def test_invalid_tls_material_fails_before_listen() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cert_file = Path(tmp) / "server.crt"
        key_file = Path(tmp) / "server.key"
        cert_file.write_text("not a certificate\n", encoding="utf-8")
        key_file.write_text("not a key\n", encoding="utf-8")
        try:
            ThreadedControlPlaneServer(
                ("127.0.0.1", 0),
                ServerApplication(),
                tls_cert_file=str(cert_file),
                tls_key_file=str(key_file),
            )
        except ssl.SSLError:
            return
    raise AssertionError("Invalid TLS certificate material should fail")


SCENARIOS = [
    ("plain_control_plane_stays_default", test_plain_control_plane_stays_default),
    ("tls_requires_cert_and_key_together", test_tls_requires_cert_and_key_together),
    ("invalid_tls_material_fails_before_listen", test_invalid_tls_material_fails_before_listen),
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
