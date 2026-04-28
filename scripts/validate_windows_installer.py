"""Static checks for the Windows installer pipeline.

Verifies:
  1. Inno Setup template exists and parses-clean variable placeholders.
  2. The installer template references the correct entry executable.
  3. scripts/package_windows_desktop.ps1 actually wires the -Installer switch.
  4. If a built installer is present under artifacts/windows-desktop/installers,
     its SHA256SUMS matches and the .exe is non-trivially sized.

Does NOT execute Inno Setup itself (that requires Windows + ISCC.exe and is
covered by running scripts/package_windows_desktop.ps1 -Installer).
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "deploy" / "windows" / "telegram_like_desktop.iss.template"
SCRIPT = REPO / "scripts" / "package_windows_desktop.ps1"
INSTALLER_DIR = REPO / "artifacts" / "windows-desktop" / "installers"

SCENARIOS: list[tuple[str, callable]] = []


def scenario(name: str):
    def deco(fn):
        SCENARIOS.append((name, fn))
        return fn
    return deco


@scenario("template_exists_and_has_required_placeholders")
def _t1() -> None:
    assert TEMPLATE.exists(), f"missing {TEMPLATE}"
    text = TEMPLATE.read_text(encoding="utf-8")
    for placeholder in ("{APP_VERSION}", "{APP_PUBLISHER}", "{APP_URL}",
                        "{SOURCE_STAGE_DIR}", "{OUTPUT_DIR}", "{OUTPUT_BASE_NAME}"):
        assert placeholder in text, f"template missing {placeholder}"


@scenario("template_targets_app_desktop_exe")
def _t2() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "app_desktop.exe" in text, "template should target app_desktop.exe as the main entry"
    assert "[Files]" in text and "[Icons]" in text, "missing [Files]/[Icons] sections"


@scenario("template_keeps_signtool_directive_documented")
def _t3() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    # The SignTool directive must be present (commented out is fine) so the
    # signing path is rediscoverable when a real cert lands.
    assert "SignTool=" in text, \
        "template should document the SignTool= directive (commented OK) " \
        "so signing is one comment-toggle away"


@scenario("packaging_script_wires_installer_switch")
def _t4() -> None:
    assert SCRIPT.exists(), f"missing {SCRIPT}"
    text = SCRIPT.read_text(encoding="utf-8")
    for needle in ("[switch]$Installer", "ISCC.exe", "telegram_like_desktop.iss.template"):
        assert needle in text, f"package script should reference: {needle}"


@scenario("if_installer_built_then_checksum_matches")
def _t5() -> None:
    if not INSTALLER_DIR.exists():
        # No installer built yet — that's fine for static check.
        return
    exes = list(INSTALLER_DIR.glob("telegram_like_desktop_setup_*.exe"))
    if not exes:
        return
    latest = max(exes, key=lambda p: p.stat().st_mtime)
    assert latest.stat().st_size > 500_000, \
        f"installer suspiciously small: {latest.stat().st_size} bytes"
    sha_file = latest.with_suffix(latest.suffix + ".sha256")
    assert sha_file.exists(), f"missing checksum next to {latest.name}"
    expected = sha_file.read_text(encoding="ascii").split()[0].lower()
    actual = hashlib.sha256(latest.read_bytes()).hexdigest().lower()
    assert expected == actual, f"checksum mismatch for {latest.name}"


def main() -> int:
    failed = 0
    for name, fn in SCENARIOS:
        try:
            fn()
            print(f"[ok ] {name}")
        except AssertionError as e:
            print(f"[FAIL] {name}: {e}")
            failed += 1
    total = len(SCENARIOS)
    print(f"passed {total - failed}/{total}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
