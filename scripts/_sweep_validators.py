"""One-shot helper to run every validate_*.py and summarise results.

Usage: python scripts/_sweep_validators.py
Skips validators that require external services (Docker, PostgreSQL, live
TLS proxy) — those are tracked as Pending Actions in 08-atlas-task-library.
Also skips validators whose backing C++ binary isn't built on this host
(useful for Linux CI where only chat_client_core + non-Qt test exes ship
without Qt).
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

# Validator -> list of binary stems (any one present is enough) that must
# exist somewhere under build-*/client/src/{Debug,Release,}/ for the
# validator to be runnable.
NEEDS_BINARY = {
    "validate_cpp_chat_e2e.py":         ["app_chat"],
    "validate_cpp_tls_client.py":       ["app_chat"],
    "validate_cpp_remote_session.py":   ["remote_session_smoke"],
    "validate_desktop_smoke.py":        ["app_desktop"],
    "validate_windows_installer.py":    [],   # static; built artifact optional
}

# Validator -> sys.platform values it can actually run on. Anything outside
# the listed platforms is skipped with SKIP_PLATFORM. C++ TLS uses Schannel,
# which is Windows-only, so cpp_tls_client only meaningfully runs on win32
# (or via WSL interop when a Windows .exe happens to be present, which the
# harness still treats as Windows runtime).
NEEDS_PLATFORM = {
    "validate_cpp_tls_client.py": {"win32"},
    "validate_windows_installer.py": {"win32"},
}


def _has_built_binary(stem: str) -> bool:
    """True if any build-* directory contains <stem>(.exe)? somewhere under
    client/src/. Walks build-verify, build-codex, build, build-linux, build-android."""
    candidates = [
        f"client/src/{cfg}/{stem}{ext}"
        for cfg in ("", "Debug", "Release")
        for ext in ("", ".exe")
    ]
    for build_root in REPO.glob("build*"):
        if not build_root.is_dir():
            continue
        for rel in candidates:
            if (build_root / rel).exists():
                return True
    return False

env = os.environ.copy()
env["PATH"] = r"C:\Windows\System32;C:\Windows;C:\Windows\System32\Wbem"
# Force UTF-8 in the spawned validators' stdio. Otherwise Windows defaults
# to cp1252 (because subprocess.run(...) sets stdout to a pipe, and Python
# falls back to locale.getpreferredencoding() when stdout is not a tty).
# A single non-ASCII char in a print() then crashes the validator with
# UnicodeEncodeError — exactly how validate_two_fa.py failed in CI.
env["PYTHONIOENCODING"] = "utf-8"

# Same problem on the parent side: when we re-print captured stdout below
# (the on-failure dump), Python encodes via the harness's stdout codec.
# On Windows CI that's cp1252 and any U+2192 etc. would crash THIS script.
# Reconfigure to UTF-8 with errors="replace" so a stray byte never masks
# the actual validator failure with a harness traceback.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

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
    needed = NEEDS_BINARY.get(name)
    if needed:
        if not any(_has_built_binary(stem) for stem in needed):
            print(f"[--] {name:46s} SKIP_NO_BINARY ({', '.join(needed)})")
            skipped += 1
            continue
    needed_platform = NEEDS_PLATFORM.get(name)
    if needed_platform and sys.platform not in needed_platform:
        print(f"[--] {name:46s} SKIP_PLATFORM ({sys.platform} not in {sorted(needed_platform)})")
        skipped += 1
        continue
    try:
        r = subprocess.run(
            [sys.executable, path],
            cwd=str(REPO), env=env,
            capture_output=True, text=True, timeout=200,
            encoding="utf-8", errors="replace",
        )
        out = r.stdout.strip().splitlines()
        last = out[-1] if out else ""
        if r.returncode == 0:
            print(f"[OK] {name:46s} {last[:50]}")
            passed += 1
        else:
            print(f"[!!] {name:46s} rc={r.returncode}  {last[:50]}")
            # Surface the full stdout + stderr on failure so CI logs show
            # the actual exception/traceback. The 50-char last-line summary
            # above hides everything before it (e.g. validate_two_fa.py's
            # per-scenario [FAIL] line + traceback).
            if r.stdout:
                print("    --- stdout ---")
                for line in r.stdout.rstrip().splitlines():
                    print(f"    {line}")
            if r.stderr:
                print("    --- stderr ---")
                for line in r.stderr.rstrip().splitlines():
                    print(f"    {line}")
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
