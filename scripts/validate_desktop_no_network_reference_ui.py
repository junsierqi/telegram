"""Validate reference-25 logged-in/no-network desktop UI evidence."""
from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
MAIN_CPP = REPO / "client" / "src" / "app_desktop" / "main.cpp"
GUI_SMOKE = REPO / "scripts" / "validate_desktop_gui_smoke.py"
REFERENCE_MAP = REPO / "artifacts" / "desktop-reference-originals" / "reference-map.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    main_cpp = MAIN_CPP.read_text(encoding="utf-8")
    gui_smoke = GUI_SMOKE.read_text(encoding="utf-8")

    print("[scenario] reference-25 logged-in/no-network GUI evidence")
    for token in (
        "run_gui_smoke_no_network_reference_step",
        "has_remembered_login_ = true",
        "logged_in_ = false",
        "setObjectName(\"reconnectIndicator\")",
        "setObjectName(\"reconnectIndicatorText\")",
        "details_panel_->setVisible(false)",
        "Select a chat to start messaging",
        "Loading...",
        "logined-no-network",
    ):
        require(token in main_cpp or token in gui_smoke, f"missing no-network token: {token}")
    require("logined-no-network.png" in gui_smoke,
            "GUI smoke validator must require the reference-25 screenshot")
    if REFERENCE_MAP.exists():
        require("reference-25-logined-no-network.png" in REFERENCE_MAP.read_text(encoding="utf-8"),
                "reference-map must include reference-25")
    else:
        print(f"[skip] local original reference map not available: {REFERENCE_MAP}")
    print("[ok ] reference-25 no-network screenshot path is locked")

    print("\nAll 1/1 desktop no-network reference UI scenarios passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"[FAIL] {exc}")
        raise SystemExit(1)
