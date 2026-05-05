"""Static checks for the desktop UI parity expansion slice.

Covers the implementation list requested after RC-001/003/004/005/006:
login/onboarding states, richer message surfaces, right-info tabs, and
productized settings entry points for Advanced capabilities.
"""
from __future__ import annotations

import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
MAIN = REPO / "client" / "src" / "app_desktop" / "main.cpp"
BUBBLE_H = REPO / "client" / "src" / "app_desktop" / "bubble_list_view.h"
BUBBLE_CPP = REPO / "client" / "src" / "app_desktop" / "bubble_list_view.cpp"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    main_cpp = MAIN.read_text(encoding="utf-8")
    bubble_h = BUBBLE_H.read_text(encoding="utf-8")
    bubble_cpp = BUBBLE_CPP.read_text(encoding="utf-8")

    print("[scenario] login onboarding exposes password, phone and QR states")
    for token in (
        'setObjectName("loginModeTabs")',
        'setObjectName("loginWelcomePage")',
        'setObjectName("loginPhonePage")',
        'setObjectName("loginQrPage")',
        'setObjectName("loginQrPlaceholder")',
        'setObjectName("loginPhoneInput")',
        'setObjectName("loginPhoneCodeInput")',
        'setObjectName("loginHeroBanner")',
        'setObjectName("loginSettingsButton")',
        'setObjectName("loginAdvancedFields")',
    ):
        require(token in main_cpp, f"missing login state token: {token}")
    print("[ok ] login modal has explicit onboarding modes")

    print("[scenario] right info panel has tabbed media/files/links/voice and member search")
    for token in (
        'detail_media_tabs_ = new QTabWidget()',
        'setObjectName("detailMediaTabs")',
        'setObjectName("detailFilesRows")',
        'setObjectName("detailLinksRows")',
        'setObjectName("detailVoiceRows")',
        'setObjectName("detailMemberSearch")',
    ):
        require(token in main_cpp, f"missing detail panel token: {token}")
    print("[ok ] right info panel has tabbed content sections")

    print("[scenario] Advanced capabilities have productized settings entry points")
    for token in (
        '"Privacy"',
        '"Chat Tools"',
        'setObjectName("accountExportShortcut")',
        'setObjectName("accountTwoFaShortcut")',
        'setObjectName("privacyBlockButton")',
        'setObjectName("privacyMuteButton")',
        'setObjectName("chatToolsSaveDraft")',
        'setObjectName("chatToolsCreatePoll")',
        'advanced_export_action();',
        'advanced_block_action(true);',
        'advanced_poll_create_action();',
    ):
        require(token in main_cpp, f"missing productized advanced token: {token}")
    print("[ok ] account/privacy/chat settings expose Advanced flows")

    print("[scenario] bubble renderer has rich message surfaces")
    for token in ("FilenameRole", "SizeBytesRole", "fileCardHeight", "pollCardHeight", "systemHeight"):
        require(token in bubble_h or token in bubble_cpp, f"missing bubble role/layout token: {token}")
    for token in (
        'text.startsWith(QStringLiteral("[system]"))',
        'text.startsWith(QStringLiteral("[poll]"))',
        'drawRoundedRect(card',
        'drawRoundedRect(poll',
        'QStringLiteral("Attachment")',
    ):
        require(token in bubble_cpp, f"missing rich bubble rendering token: {token}")
    print("[ok ] bubble delegate renders system, file and poll surfaces")

    print("\nAll 4/4 desktop UI expansion scenarios passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"[FAIL] {exc}")
        raise SystemExit(1)
