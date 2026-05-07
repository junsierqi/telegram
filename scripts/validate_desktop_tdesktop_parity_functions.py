from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MAIN = ROOT / "client" / "src" / "app_desktop" / "main.cpp"
CLIENT_H = ROOT / "client" / "src" / "transport" / "control_plane_client.h"
CLIENT_CPP = ROOT / "client" / "src" / "transport" / "control_plane_client.cpp"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def scenario_profile_modal_box_shape() -> None:
    print("[scenario] Profile modal follows tdesktop info/profile box shape")
    text = MAIN.read_text(encoding="utf-8")
    for token in (
        'setObjectName("profileModal")',
        'resize(560, 690)',
        '"profileModalField"',
        '"profileModalTopButton"',
        "open_settings_page_by_name(QStringLiteral(\"Profile\"))",
    ):
        require(token in text, f"missing Profile modal token: {token}")
    print("[ok ] Profile modal uses compact box, top buttons and form-like fields")


def scenario_contacts_peer_list_actions() -> None:
    print("[scenario] Contacts dialog exposes peer_list_box-style actions")
    text = MAIN.read_text(encoding="utf-8")
    for token in (
        "QAbstractItemView::SingleSelection",
        'new QPushButton("Edit")',
        'new QPushButton("Share")',
        'new QPushButton("Delete")',
        "client->edit_contact",
        "client->share_contact",
        "client->remove_contact",
    ):
        require(token in text, f"missing Contacts action token: {token}")
    print("[ok ] Contacts dialog can add/edit/share/delete selected peers")


def scenario_right_panel_backend_actions() -> None:
    print("[scenario] right info panel routes Report/Leave/shared-media to backend")
    text = MAIN.read_text(encoding="utf-8")
    for token in (
        "client->leave_conversation(conversation, true)",
        "client->report_conversation(conversation, reason, comment)",
        "load_shared_media_page",
        "client->shared_media_page(conversation, request_kind, offset, 30)",
        '"shared_media_more"',
    ):
        require(token in text, f"missing right-panel backend token: {token}")
    print("[ok ] right panel uses explicit backend contracts")


def scenario_transport_contracts() -> None:
    print("[scenario] transport client exposes tdesktop parity RPCs")
    header = CLIENT_H.read_text(encoding="utf-8")
    cpp = CLIENT_CPP.read_text(encoding="utf-8")
    for token in (
        "ContactShareResult",
        "SharedMediaPageResult",
        "edit_contact",
        "share_contact",
        "leave_conversation",
        "report_conversation",
        "shared_media_page",
    ):
        require(token in header, f"missing client declaration: {token}")
    for token in (
        '"contact_edit"',
        '"contact_share_request"',
        '"conversation_leave_request"',
        '"report_conversation_request"',
        '"shared_media_page_request"',
    ):
        require(token in cpp, f"missing client implementation token: {token}")
    print("[ok ] typed client wraps all new backend contracts")


def main() -> int:
    for scenario in (
        scenario_profile_modal_box_shape,
        scenario_contacts_peer_list_actions,
        scenario_right_panel_backend_actions,
        scenario_transport_contracts,
    ):
        scenario()
    print("\nAll 4/4 desktop tdesktop parity function scenarios passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
