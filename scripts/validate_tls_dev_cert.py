"""Validate the local development TLS certificate generator."""
from __future__ import annotations

import ssl
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_generate_dev_cert_material() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "certs"
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "generate_tls_dev_cert.py"),
                "--out-dir",
                str(out_dir),
                "--days",
                "2",
            ],
            check=True,
            cwd=ROOT,
        )
        cert_file = out_dir / "server.crt"
        key_file = out_dir / "server.key"
        assert cert_file.exists(), cert_file
        assert key_file.exists(), key_file
        ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(
            certfile=str(cert_file),
            keyfile=str(key_file),
        )


def test_generator_refuses_overwrite_by_default() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "certs"
        first = [
            sys.executable,
            str(ROOT / "scripts" / "generate_tls_dev_cert.py"),
            "--out-dir",
            str(out_dir),
        ]
        subprocess.run(first, check=True, cwd=ROOT)
        second = subprocess.run(first, cwd=ROOT, capture_output=True, text=True)
        assert second.returncode != 0
        assert "already exists" in (second.stderr + second.stdout)


SCENARIOS = [
    ("generate_dev_cert_material", test_generate_dev_cert_material),
    ("generator_refuses_overwrite_by_default", test_generator_refuses_overwrite_by_default),
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
