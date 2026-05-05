"""Static checks for original Telegram Desktop login reference states.

The login screenshots are three distinct desktop states:

- welcome screen with large blue hero and Start Messaging CTA
- QR login screen with back/settings chrome and phone-number link
- phone-number screen with country/phone fields and QR fallback link

This validator keeps those states explicit while the live provider-backed QR
and SMS behavior remains outside the local-only slice.
"""
from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
MAIN = REPO / "client" / "src" / "app_desktop" / "main.cpp"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    main_cpp = MAIN.read_text(encoding="utf-8")

    print("[scenario] login welcome reference shell")
    for token in (
        'dlg->resize(980, 760)',
        'setObjectName("loginChrome")',
        'setObjectName("loginHeroBanner")',
        'setObjectName("loginHeroPlane")',
        '"Telegram Desktop"',
        '"Welcome to the official Telegram Desktop app.\\nIt\'s fast and secure."',
        '"Start Messaging"',
    ):
        require(token in main_cpp, f"missing welcome reference token: {token}")
    print("[ok ] welcome login state matches the original screenshot structure")

    print("[scenario] QR login reference shell")
    for token in (
        'setObjectName("loginBackButton")',
        'setObjectName("loginSettingsButton")',
        'setObjectName("loginQrPlaceholder")',
        '"Scan From Mobile Telegram"',
        'Go to Settings > Devices > Link Desktop Device',
        '"Log in using phone number"',
        'login_modes->setCurrentIndex(1)',
    ):
        require(token in main_cpp, f"missing QR reference token: {token}")
    print("[ok ] QR login state has back/settings chrome and phone fallback")

    print("[scenario] phone login reference shell")
    for token in (
        '"Your Phone Number"',
        '"Please confirm your country code\\nand enter your phone number."',
        'new QLineEdit("USA")',
        '"+1        --- --- ----"',
        '"Quick log in using QR code"',
        'login_modes->setCurrentIndex(2)',
    ):
        require(token in main_cpp, f"missing phone reference token: {token}")
    print("[ok ] phone login state has country/phone fields and QR fallback")

    print("[scenario] local advanced connection fields are preserved")
    for token in (
        'setObjectName("loginAdvancedFields")',
        'advanced_fields->setVisible(false)',
        'advanced_fields->setVisible(!advanced_fields->isVisible())',
        'user_->setText(user->text().trimmed())',
        'host_->setText(host->text().trimmed())',
    ):
        require(token in main_cpp, f"missing advanced login token: {token}")
    print("[ok ] local username/password/server flow remains available behind Settings")

    print("\nAll 4/4 desktop login reference scenarios passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"[FAIL] {exc}")
        raise SystemExit(1)
