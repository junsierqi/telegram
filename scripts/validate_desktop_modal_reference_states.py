"""Static checks for reference-21 through reference-24 modal screenshots."""
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

    print("[scenario] profile modal reference state")
    for token in (
        "show_profile_reference_dialog",
        'setObjectName("profileModal")',
        '"profile-modal"',
        '"profile-modal.png"',
        "Your stories will be here.",
    ):
        require(token in main_cpp or token in gui_smoke, f"missing profile modal token: {token}")
    print("[ok ] reference-21 profile modal is captured")

    print("[scenario] new group dialog reference state")
    for token in (
        "show_conversation_create_dialog(false)",
        'setObjectName("newGroupModal")',
        '"new-group-dialog"',
        '"new-group-dialog.png"',
        "Group name",
    ):
        require(token in main_cpp or token in gui_smoke, f"missing new group token: {token}")
    print("[ok ] reference-22 new group dialog is captured")

    print("[scenario] new channel dialog reference state")
    for token in (
        "show_conversation_create_dialog(true)",
        'setObjectName("newChannelModal")',
        '"new-channel-dialog"',
        '"new-channel-dialog.png"',
        "Channel name",
    ):
        require(token in main_cpp or token in gui_smoke, f"missing new channel token: {token}")
    print("[ok ] reference-23 new channel dialog is captured")

    print("[scenario] contacts dialog reference state")
    for token in (
        "show_contacts_dialog",
        'setObjectName("contactsModal")',
        '"contacts-dialog"',
        '"contacts-dialog.png"',
        "Hello Blake",
    ):
        require(token in main_cpp or token in gui_smoke, f"missing contacts token: {token}")
    print("[ok ] reference-24 contacts dialog is captured")

    print("\nAll 4/4 desktop modal reference-state scenarios passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"[FAIL] {exc}")
        raise SystemExit(1)
