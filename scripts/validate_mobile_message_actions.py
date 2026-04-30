"""Validator for M141 + M143 — mobile QML message-action parity with desktop.

Static analysis on:
  - mobile_chat_bridge.h: Q_INVOKABLE replyMessage / forwardMessage /
    toggleReaction / pinMessage / editMessage / deleteMessage.
  - mobile_chat_bridge.cpp:
    - selectedMessages publishes replyTo, replyToText, forwardedFrom,
      reactions, pinned, edited, deleted (in addition to the existing
      messageId/sender/text/outgoing/pending/failed/createdAtMs/deliveryTick).
    - Each new method dispatches the corresponding ControlPlaneClient
      RPC on a worker thread and emits storeChanged.
  - ChatPage.qml:
    - Renders reply quote (vertical accent bar + 1-line snippet) when
      replyTo is set, forwarded header (italic) when forwardedFrom is
      set, pinned tag (📌), reactions chips (Flow + Repeater), and the
      edited suffix on the body label.
    - MouseArea pressAndHold opens a Menu with Reply/Forward/React/Pin/
      Unpin/Edit/Delete that calls the new bridge methods.
    - The composer renders a reply-quote strip above the TextField when
      page.replyToId is set; sending while replyToId is set routes
      through ChatBridge.replyMessage(targetId, text).

Pure static analysis — no Qt build needed.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
BRIDGE_H = REPO / "client" / "src" / "app_mobile" / "mobile_chat_bridge.h"
BRIDGE_CPP = REPO / "client" / "src" / "app_mobile" / "mobile_chat_bridge.cpp"
CHAT_QML = REPO / "client" / "src" / "app_mobile" / "qml" / "ChatPage.qml"


def main() -> int:
    for p in (BRIDGE_H, BRIDGE_CPP, CHAT_QML):
        if not p.exists():
            print(f"[FAIL] missing {p}")
            return 1
    h = BRIDGE_H.read_text(encoding="utf-8")
    cpp = BRIDGE_CPP.read_text(encoding="utf-8")
    qml = CHAT_QML.read_text(encoding="utf-8")

    print("[scenario] bridge.h exposes Q_INVOKABLE message-action methods")
    for method in ("replyMessage", "forwardMessage", "toggleReaction",
                   "pinMessage", "editMessage", "deleteMessage"):
        assert re.search(rf"Q_INVOKABLE\s+void\s+{re.escape(method)}\b", h), \
            f"Q_INVOKABLE void {method}(...) missing in mobile_chat_bridge.h"
    print("[ok ] 6 Q_INVOKABLE message-action methods declared")

    print("[scenario] selectedMessages publishes the new fields")
    sel_match = re.search(
        r"QVariantList\s+MobileChatBridge::selectedMessages\s*\(\s*\)\s*const\s*\{(?P<body>.*?)\n\}",
        cpp, re.DOTALL,
    )
    assert sel_match, "selectedMessages body not found"
    sb = sel_match.group("body")
    for field in ("replyTo", "replyToText", "forwardedFrom",
                  "reactions", "pinned", "edited", "deleted"):
        assert f'row["{field}"]' in sb, \
            f"selectedMessages must publish row[{field!r}]"
    print("[ok ] 7 message fields surfaced through the bridge")

    print("[scenario] each new bridge method dispatches the right transport RPC")
    for fn, transport_call in (
        ("replyMessage",   "client->reply_message("),
        ("forwardMessage", "client->forward_message("),
        ("toggleReaction", "client->toggle_reaction("),
        ("pinMessage",     "client->set_message_pin("),
        ("editMessage",    "client->edit_message("),
        ("deleteMessage",  "client->delete_message("),
    ):
        block = re.search(
            rf"void\s+MobileChatBridge::{re.escape(fn)}\s*\([^)]*\)\s*\{{(?P<b>.*?)\n\}}",
            cpp, re.DOTALL,
        )
        assert block, f"{fn} body not found in bridge cpp"
        assert transport_call in block.group("b"), \
            f"{fn} must call {transport_call!r}"
    print("[ok ] 6 bridge methods route through ControlPlaneClient")

    print("[scenario] ChatPage.qml renders reply / forwarded / pinned / reactions")
    # Reply quote with accent bar.
    assert "modelData.replyTo" in qml, "delegate must check modelData.replyTo"
    assert "modelData.replyToText" in qml, "delegate must read modelData.replyToText"
    # Forwarded header.
    assert "modelData.forwardedFrom" in qml or "forwardedFrom" in qml, \
        "delegate must render forwardedFrom"
    assert "Forwarded from" in qml, "forwarded header text missing"
    # Pinned tag.
    assert "modelData.pinned" in qml, "delegate must check modelData.pinned"
    # Reactions chips — Repeater + Flow.
    assert "Repeater" in qml and "Flow" in qml and "modelData.reactions" in qml, \
        "delegate must use Repeater+Flow over modelData.reactions for chips"
    # Edited suffix.
    assert "modelData.edited" in qml, "delegate must render the edited suffix"
    print("[ok ] reply / forwarded / pinned / reactions / edited all rendered")

    print("[scenario] long-press menu wires Reply/Forward/React/Pin/Edit/Delete")
    assert "Menu {" in qml, "ChatPage.qml must declare a Menu"
    # Press-and-hold popup hook.
    assert "onPressAndHold" in qml, "MouseArea must have onPressAndHold to open the menu"
    # Each menu item invokes the matching bridge method.
    for needle in (
        "ChatBridge.forwardMessage",
        "ChatBridge.toggleReaction",
        "ChatBridge.pinMessage",
        "ChatBridge.editMessage",
        "ChatBridge.deleteMessage",
    ):
        assert needle in qml, f"menu must invoke {needle}"
    print("[ok ] long-press menu invokes 5+ bridge methods")

    print("[scenario] composer reply state strip + replyMessage routing")
    # Page exposes replyToId / replyToText state.
    assert re.search(r"property\s+string\s+replyToId\s*:\s*\"\"", qml), \
        "ChatPage must declare replyToId state"
    assert "ChatBridge.replyMessage" in qml, \
        "Send button must route through ChatBridge.replyMessage when replyToId is set"
    # The strip is shown when replyToId is non-empty.
    assert "page.replyToId !==" in qml or 'page.replyToId != ""' in qml, \
        "reply strip visibility must gate on page.replyToId"
    print("[ok ] composer reply state strip + replyMessage routing wired")

    print("\nAll 6/6 scenarios passed.")
    return 0


if __name__ == "__main__":
    import traceback
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(f"[FAIL] {exc}")
        traceback.print_exc()
        sys.exit(1)
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}")
        traceback.print_exc()
        sys.exit(1)
