"""Launch app_desktop and exercise the new Telegram-reference interactions.

This is intentionally GUI-level, not a store-only smoke:

- clicks the hamburger button
- verifies the account drawer opens
- verifies the drawer can close
- reopens the drawer and clicks Settings
- verifies the centered Settings modal opens and closes
- confirms the right profile panel is present
- captures login welcome / QR / phone reference states before the shell flow
- captures Settings General / Proxy settings / Edit proxy reference states
- captures main-empty-chat-list plus channel/user/group info panel reference states
- captures logged-in/no-network reference state
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
LOCKED_ARTIFACTS = REPO / "artifacts" / "desktop-gui-smoke"


def _binary_candidates(stem: str) -> list[Path]:
    candidates: list[Path] = []
    for build in ("build-ui-verify", "build-verify", "build-codex", "build", "build-local",
                  "build-macos", "build-linux", "build-wsl", "build-android"):
        for cfg in ("", "Debug", "Release"):
            for ext in ("", ".exe"):
                candidates.append(REPO / build / "client" / "src" / cfg / f"{stem}{ext}")
    return candidates


def main() -> int:
    app_desktop = next((p for p in _binary_candidates("app_desktop") if p.exists()), None)
    if app_desktop is None:
        print("[FAIL] app_desktop binary not found; build app_desktop first")
        return 1

    env = os.environ.copy()
    env.setdefault("QT_SCALE_FACTOR", "1")
    env.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "0")
    env.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")
    with tempfile.TemporaryDirectory(prefix="telegram-gui-smoke-") as tmp:
        result = subprocess.run(
            [
                str(app_desktop),
                "--gui-smoke",
                "--cache-file",
                "",
                "--smoke-save-dir",
                tmp,
            ],
            cwd=str(REPO),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            env=env,
        )
        print(result.stdout, end="")
        if result.returncode != 0:
            print(f"[FAIL] app_desktop --gui-smoke exited {result.returncode}")
            return 1
        if "desktop gui smoke ok:" not in result.stdout:
            print("[FAIL] GUI smoke success marker missing")
            return 1
        LOCKED_ARTIFACTS.mkdir(parents=True, exist_ok=True)
        expected = (
            "login-welcome.png",
            "login-qr.png",
            "login-phone.png",
            "main-empty-chat-list.png",
            "info-channel.png",
            "service-chat-info.png",
            "info-user.png",
            "info-group.png",
            "service-chat.png",
            "channel-pinned-unread.png",
            "group-autodelete-empty.png",
            "main-window.png",
            "account-drawer.png",
            "side-menu-overlay.png",
            "side-menu-empty-scrolled.png",
            "side-menu-empty-full.png",
            "settings-modal.png",
            "settings-general.png",
            "proxy-list.png",
            "proxy-edit.png",
            "profile-modal.png",
            "new-group-dialog.png",
            "new-channel-dialog.png",
            "contacts-dialog.png",
            "logined-no-network.png",
        )
        for name in expected:
            shot = Path(tmp) / name
            if not shot.exists() or shot.stat().st_size < 1024:
                print(f"[FAIL] screenshot missing or too small: {shot}")
                return 1
            print(f"[ok ] screenshot {name}: {shot.stat().st_size} bytes")
            shutil.copy2(shot, LOCKED_ARTIFACTS / name)
        diff = subprocess.run(
            [sys.executable, "scripts/validate_desktop_image_diff.py"],
            cwd=str(REPO),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            env=env,
        )
        print(diff.stdout, end="")
        if diff.returncode != 0:
            print(f"[FAIL] desktop image diff exited {diff.returncode}")
            return 1
    print("passed 1/1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
