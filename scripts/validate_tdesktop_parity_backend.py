from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402


def dispatch(app: ServerApplication, session: dict, msg_type: MessageType, payload: dict, seq: int) -> dict:
    return app.dispatch(
        {
            **make_envelope(
                msg_type,
                correlation_id=f"tdp_{msg_type.value}_{seq}",
                session_id=session["session_id"],
                actor_user_id=session["user_id"],
                sequence=seq,
            ),
            "payload": payload,
        }
    )


def login(app: ServerApplication, username: str, password: str, device_id: str, seq: int) -> dict:
    response = app.dispatch(
        {
            **make_envelope(MessageType.LOGIN_REQUEST, correlation_id=f"login_{username}", sequence=seq),
            "payload": {"username": username, "password": password, "device_id": device_id},
        }
    )
    assert response["type"] == "login_response", response
    return response["payload"]


def scenario_contact_edit_share_delete() -> None:
    print("[scenario] contact edit/share/delete flow")
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 1)
    add = dispatch(app, alice, MessageType.CONTACT_ADD, {"target_user_id": "u_bob"}, 2)
    assert add["type"] == "contact_list_response", add
    edit = dispatch(
        app,
        alice,
        MessageType.CONTACT_EDIT,
        {"target_user_id": "u_bob", "display_name": "Bobby Local"},
        3,
    )
    assert edit["type"] == "contact_list_response", edit
    assert edit["payload"]["contacts"][0]["display_name"] == "Bobby Local", edit
    share = dispatch(app, alice, MessageType.CONTACT_SHARE_REQUEST, {"target_user_id": "u_bob"}, 4)
    assert share["type"] == "contact_share_response", share
    assert share["payload"]["share_text"] == "Bobby Local (@bob)", share
    delete = dispatch(app, alice, MessageType.CONTACT_REMOVE, {"target_user_id": "u_bob"}, 5)
    assert delete["type"] == "contact_list_response", delete
    assert delete["payload"]["contacts"] == [], delete
    print("[ok ] contact edit/share/delete backed by real state")


def scenario_report_leave_confirmation() -> None:
    print("[scenario] report reason + leave confirmation")
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 10)
    empty_report = dispatch(
        app,
        alice,
        MessageType.REPORT_CONVERSATION_REQUEST,
        {"conversation_id": "conv_alice_bob", "reason": ""},
        11,
    )
    assert empty_report["type"] == "error", empty_report
    assert empty_report["payload"]["code"] == "report_reason_required", empty_report
    report = dispatch(
        app,
        alice,
        MessageType.REPORT_CONVERSATION_REQUEST,
        {"conversation_id": "conv_alice_bob", "reason": "Spam", "comment": "test"},
        12,
    )
    assert report["type"] == "report_conversation_response", report
    assert app.state.conversation_reports[-1]["reason"] == "Spam"
    leave_denied = dispatch(
        app,
        alice,
        MessageType.CONVERSATION_LEAVE_REQUEST,
        {"conversation_id": "conv_alice_bob", "confirmed": False},
        13,
    )
    assert leave_denied["type"] == "error", leave_denied
    assert leave_denied["payload"]["code"] == "leave_confirmation_required", leave_denied
    leave = dispatch(
        app,
        alice,
        MessageType.CONVERSATION_LEAVE_REQUEST,
        {"conversation_id": "conv_alice_bob", "confirmed": True},
        14,
    )
    assert leave["type"] == "conversation_updated", leave
    assert "u_alice" not in leave["payload"]["participant_user_ids"], leave
    print("[ok ] report and leave use explicit backend contracts")


def scenario_shared_media_pagination() -> None:
    print("[scenario] shared media provider pagination")
    app = ServerApplication()
    alice = login(app, "alice", "alice_pw", "dev_alice_win", 20)
    dispatch(
        app,
        alice,
        MessageType.MESSAGE_SEND_ATTACHMENT,
        {
            "conversation_id": "conv_alice_bob",
            "caption": "photo",
            "filename": "one.png",
            "mime_type": "image/png",
            "content_b64": "aGVsbG8=",
            "size_bytes": 5,
        },
        21,
    )
    dispatch(
        app,
        alice,
        MessageType.MESSAGE_SEND_ATTACHMENT,
        {
            "conversation_id": "conv_alice_bob",
            "caption": "doc",
            "filename": "one.txt",
            "mime_type": "text/plain",
            "content_b64": "aGVsbG8=",
            "size_bytes": 5,
        },
        22,
    )
    dispatch(
        app,
        alice,
        MessageType.MESSAGE_SEND,
        {"conversation_id": "conv_alice_bob", "text": "see https://example.test/a"},
        23,
    )
    media = dispatch(
        app,
        alice,
        MessageType.SHARED_MEDIA_PAGE_REQUEST,
        {"conversation_id": "conv_alice_bob", "kind": "media", "offset": 0, "limit": 1},
        24,
    )
    assert media["type"] == "shared_media_page_response", media
    assert len(media["payload"]["entries"]) == 1, media
    files = dispatch(
        app,
        alice,
        MessageType.SHARED_MEDIA_PAGE_REQUEST,
        {"conversation_id": "conv_alice_bob", "kind": "files", "offset": 0, "limit": 10},
        25,
    )
    assert files["payload"]["entries"][0]["filename"] == "one.txt", files
    links = dispatch(
        app,
        alice,
        MessageType.SHARED_MEDIA_PAGE_REQUEST,
        {"conversation_id": "conv_alice_bob", "kind": "links", "offset": 0, "limit": 10},
        26,
    )
    assert links["payload"]["entries"][0]["link"] == "https://example.test/a", links
    print("[ok ] shared media provider filters media/files/links")


def main() -> int:
    for scenario in (
        scenario_contact_edit_share_delete,
        scenario_report_leave_confirmation,
        scenario_shared_media_pagination,
    ):
        scenario()
    print("\nAll 3/3 tdesktop parity backend scenarios passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
