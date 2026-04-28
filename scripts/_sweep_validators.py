"""One-shot helper to run every validate_*.py and summarise results.

Usage: python scripts/_sweep_validators.py
Skips validators that require external services (Docker, PostgreSQL, live
TLS proxy) — those are tracked as Pending Actions in 08-atlas-task-library.
"""
from __future__ import annotations

import glob
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

EXTERNAL_ONLY = {
    "validate_docker_deploy.py",
    "validate_postgres_repository.py",
    "validate_postgres_backup_restore.py",
    "validate_tls_proxy_smoke.py",
}

env = os.environ.copy()
env["PATH"] = r"C:\Windows\System32;C:\Windows;C:\Windows\System32\Wbem"

scripts = sorted(glob.glob(str(REPO / "scripts" / "validate_*.py")))
passed = 0
failed = 0
skipped = 0
fail_names: list[str] = []

print(f"running {len(scripts)} validators (skipping {len(EXTERNAL_ONLY)} external-only)")
print("-" * 78)
for path in scripts:
    name = Path(path).name
    if name in EXTERNAL_ONLY:
        print(f"[--] {name:46s} SKIP_EXTERNAL")
        skipped += 1
        continue
    try:
        r = subprocess.run(
            [sys.executable, path],
            cwd=str(REPO), env=env,
            capture_output=True, text=True, timeout=200,
        )
        out = r.stdout.strip().splitlines()
        last = out[-1] if out else ""
        if r.returncode == 0:
            print(f"[OK] {name:46s} {last[:50]}")
            passed += 1
        else:
            print(f"[!!] {name:46s} rc={r.returncode}  {last[:50]}")
            failed += 1
            fail_names.append(name)
    except Exception as e:
        print(f"[!!] {name:46s} ERROR  {str(e)[:50]}")
        failed += 1
        fail_names.append(name)

print("-" * 78)
print(f"summary: {passed} passed | {failed} failed | {skipped} skipped (external)")
if fail_names:
    print("failures:", ", ".join(fail_names))
sys.exit(0 if failed == 0 else 1)
