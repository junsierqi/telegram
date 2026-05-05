"""Static checks for Settings / Proxy reference screenshot states."""
from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
MAIN = REPO / "client" / "src" / "app_desktop" / "main.cpp"
GUI_SMOKE = REPO / "scripts" / "validate_desktop_gui_smoke.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    main_cpp = MAIN.read_text(encoding="utf-8")
    gui_smoke = GUI_SMOKE.read_text(encoding="utf-8")

    print("[scenario] Settings General reference capture")
    for token in (
        'setObjectName("settingsModal")',
        '"Default interface scale"',
        '"settings-general"',
        '"settings-general.png"',
    ):
        require(token in main_cpp or token in gui_smoke, f"missing settings general token: {token}")
    print("[ok ] Settings General is captured as first-class GUI evidence")

    print("[scenario] Proxy settings empty-list reference surface")
    for token in (
        'void show_proxy_settings_dialog()',
        'setObjectName("proxySettingsModal")',
        '"Proxy settings"',
        '"Use system proxy settings"',
        '"Your saved proxy list will be here."',
        '"proxy-list"',
        '"proxy-list.png"',
    ):
        require(token in main_cpp or token in gui_smoke, f"missing proxy list token: {token}")
    print("[ok ] Proxy settings list-empty surface is wired")

    print("[scenario] Edit proxy SOCKS5 reference surface")
    for token in (
        'void show_proxy_edit_dialog()',
        'setObjectName("proxyEditModal")',
        '"Edit proxy"',
        '"SOCKS5"',
        '"Socket address"',
        '"Credentials (optional)"',
        '"proxy-edit"',
        '"proxy-edit.png"',
    ):
        require(token in main_cpp or token in gui_smoke, f"missing proxy edit token: {token}")
    print("[ok ] Edit proxy SOCKS5 surface is wired")

    print("\nAll 3/3 desktop settings/proxy reference scenarios passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"[FAIL] {exc}")
        raise SystemExit(1)
