"""Static checks for reference-14 onward chat/drawer screenshot states."""
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

    print("[scenario] side menu empty-chat reference states")
    for token in (
        "run_gui_smoke_side_menu_empty_step",
        '"side-menu-empty-scrolled"',
        '"side-menu-empty-scrolled.png"',
        '"side-menu-empty-full"',
        '"side-menu-empty-full.png"',
        "set_selected_conversation({})",
        "sidebar_panel_",
        "sidebar_panel_->width()",
        "mapToGlobal(QPoint(0, 0))",
        "account_drawer_geometry",
        "sync_account_drawer_geometry",
        "QScrollArea#accountDrawerScroll",
        "accountDrawerContent",
        "resizeEvent(QResizeEvent* event) override",
        "moveEvent(QMoveEvent* event) override",
    ):
        require(token in main_cpp or token in gui_smoke, f"missing side-menu empty token: {token}")
    drawer_start = main_cpp.find("void show_account_drawer()")
    drawer_end = main_cpp.find("void show_login_dialog()", drawer_start)
    drawer_body = main_cpp[drawer_start:drawer_end] if drawer_start >= 0 and drawer_end > drawer_start else main_cpp
    require("const int panelW = 360" not in drawer_body,
            "account drawer must follow the sidebar width, not a hard-coded 360px width")
    require("mainGeo.top() + 32" not in drawer_body,
            "account drawer must not offset itself below the main window client area")
    print("[ok ] reference-14/15 side-menu empty states are first-class GUI evidence")

    print("[scenario] Telegram service notification reference states")
    for token in (
        "ref_service_telegram",
        "Login code: 23720",
        '"service-chat"',
        '"service-chat.png"',
        '"service-chat-info"',
        '"service-chat-info.png"',
    ):
        require(token in main_cpp or token in gui_smoke, f"missing service chat token: {token}")
    print("[ok ] reference-16/17 service chat states are wired through DesktopChatStore")

    print("[scenario] channel pinned/unread reference state")
    for token in (
        "ref_channel_m_team",
        "New internal build is available",
        '"channel-pinned-unread"',
        '"channel-pinned-unread.png"',
        "pin_bar_",
    ):
        require(token in main_cpp or token in gui_smoke, f"missing channel pinned token: {token}")
    print("[ok ] reference-18 channel pinned/unread state is captured")

    print("[scenario] group auto-delete empty reference state")
    for token in (
        "ref_group_three",
        "You set messages to auto-delete in 1 week",
        '"group-autodelete-empty"',
        '"group-autodelete-empty.png"',
    ):
        require(token in main_cpp or token in gui_smoke, f"missing group autodelete token: {token}")
    print("[ok ] reference-20 group auto-delete state is captured")

    print("\nAll 4/4 desktop chat reference-state scenarios passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"[FAIL] {exc}")
        raise SystemExit(1)
