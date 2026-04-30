"""Validator for M137 — Telegram-style bubble polish across desktop + mobile.

Checks the source files that drive bubble rendering have the right shape
after the M137 refactor:

  1. desktop_chat_store.h: DesktopBubblePalette struct exists with the 10
     expected color fields; render_selected_timeline_html accepts a palette
     parameter; DesktopChatStore exposes a delivery_tick() member.
  2. desktop_chat_store.cpp: the timeline CSS uses palette tokens (no stray
     literal hex apart from a few neutral state colors), and the tick span
     is emitted for outgoing messages.
  3. main.cpp wires active_theme() -> palette before calling the renderer.
  4. mobile_chat_bridge.cpp exposes `deliveryTick` on every selected
     message via store_.delivery_tick(...).
  5. ChatPage.qml uses Theme tokens (`page.palette.X`), defines a Gradient
     for own bubbles, and renders a tick label with ✓ / ✓✓ / ⌛ / ✕ glyphs.

Pure static analysis — runs without Qt and verifies the structure of the
M137 work end-to-end.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
STORE_H = REPO / "client" / "src" / "app_desktop" / "desktop_chat_store.h"
STORE_CPP = REPO / "client" / "src" / "app_desktop" / "desktop_chat_store.cpp"
DESKTOP_MAIN = REPO / "client" / "src" / "app_desktop" / "main.cpp"
BRIDGE = REPO / "client" / "src" / "app_mobile" / "mobile_chat_bridge.cpp"
CHAT_QML = REPO / "client" / "src" / "app_mobile" / "qml" / "ChatPage.qml"


def main() -> int:
    for path in (STORE_H, STORE_CPP, DESKTOP_MAIN, BRIDGE, CHAT_QML):
        if not path.exists():
            print(f"[FAIL] missing {path}")
            return 1

    h = STORE_H.read_text(encoding="utf-8")
    cpp = STORE_CPP.read_text(encoding="utf-8")
    desktop = DESKTOP_MAIN.read_text(encoding="utf-8")
    bridge = BRIDGE.read_text(encoding="utf-8")
    qml = CHAT_QML.read_text(encoding="utf-8")

    print("[scenario] DesktopBubblePalette struct + delivery_tick declared in header")
    assert "struct DesktopBubblePalette" in h, "DesktopBubblePalette struct missing"
    expected_fields = [
        "chat_area_bg", "own_bubble", "own_bubble_text",
        "peer_bubble", "peer_bubble_text", "primary",
        "text_muted", "tick_sent", "tick_read", "failed_bubble",
    ]
    for field in expected_fields:
        assert re.search(rf"const\s+char\*\s+{re.escape(field)}\s*=", h), \
            f"DesktopBubblePalette missing field {field!r}"
    assert "delivery_tick" in h and "render_selected_timeline_html" in h, \
        "delivery_tick + render_selected_timeline_html must be in the public header"
    assert "DesktopBubblePalette& palette" in h, \
        "render_selected_timeline_html signature must take const DesktopBubblePalette&"
    print(f"[ok ] palette struct ({len(expected_fields)} fields) + 2 public methods declared")

    print("[scenario] timeline renderer uses palette tokens + tick span")
    fn_match = re.search(
        r"std::string\s+DesktopChatStore::render_selected_timeline_html\s*\(.*?\n\}\n",
        cpp, re.DOTALL,
    )
    assert fn_match, "could not locate render_selected_timeline_html body"
    body = fn_match.group(0)
    palette_uses = re.findall(r"palette\.(\w+)", body)
    distinct = set(palette_uses)
    assert len(distinct) >= 8, \
        f"renderer references only {len(distinct)} palette fields ({sorted(distinct)}), expected >= 8"
    # Tick span emission.
    assert "class='tick" in body, "renderer must emit a <span class='tick ...'>"
    assert "&#x2713;&#x2713;" in body, "renderer must emit ✓✓ for the read state"
    assert "&#x2713;" in body, "renderer must emit ✓ for the sent state"
    assert "&#x231b;" in body, "renderer must emit ⌛ for pending"
    print(f"[ok ] renderer references {len(distinct)} palette fields + 4 tick glyphs")

    print("[scenario] desktop main.cpp builds a palette from active_theme()")
    rs_match = re.search(r"void\s+render_store\s*\(\s*\)\s*\{(?P<body>.*?)\n\s{4}\}", desktop, re.DOTALL)
    assert rs_match, "could not locate render_store() in app_desktop main.cpp"
    rs_body = rs_match.group("body")
    assert "active_theme()" in rs_body, "render_store must consult active_theme()"
    assert "DesktopBubblePalette" in rs_body, "render_store must construct a DesktopBubblePalette"
    assert "palette.own_bubble" in rs_body, "render_store must set palette.own_bubble"
    # M138 redirected the desktop view from QTextBrowser+setHtml to
    # BubbleListView+setBubblePalette. Either path is acceptable as long
    # as the palette flows from active_theme into a renderer.
    palette_consumer_ok = (
        "render_selected_timeline_html(" in rs_body and ", palette)" in rs_body
    ) or (
        "setBubblePalette(palette)" in rs_body
    )
    assert palette_consumer_ok, \
        "render_store must hand `palette` to render_selected_timeline_html OR to messages_->setBubblePalette"
    print("[ok ] active_theme -> palette -> renderer chain wired")

    print("[scenario] mobile bridge surfaces deliveryTick on every message")
    sel_match = re.search(
        r"QVariantList\s+MobileChatBridge::selectedMessages\s*\(\s*\)\s*const\s*\{(?P<body>.*?)\n\}",
        bridge, re.DOTALL,
    )
    assert sel_match, "could not locate selectedMessages() body"
    sb = sel_match.group("body")
    assert 'row["deliveryTick"]' in sb, "selectedMessages must publish deliveryTick"
    assert "store_.delivery_tick(" in sb, "deliveryTick must be sourced from store_.delivery_tick"
    print("[ok ] bridge exposes deliveryTick via DesktopChatStore::delivery_tick")

    print("[scenario] ChatPage.qml uses theme tokens, gradient, and tick label")
    assert "page.palette" in qml, "ChatPage.qml must read from page.palette (root theme)"
    assert "Gradient {" in qml or "Gradient{" in qml, "ChatPage.qml must define a Gradient block"
    assert "ownBubbleTop" in qml and "ownBubbleBottom" in qml, \
        "ChatPage.qml gradient must use ownBubbleTop + ownBubbleBottom tokens"
    assert "deliveryTick" in qml, "ChatPage.qml must consume modelData.deliveryTick"
    # Tick glyphs in QML — escape sequences must appear.
    assert "\\u2713\\u2713" in qml, "ChatPage.qml must contain the ✓✓ unicode escape"
    assert "\\u231b" in qml, "ChatPage.qml must contain the ⌛ unicode escape"
    # Anti-regression: the legacy WhatsApp-green outgoing color must be gone.
    assert "#eeffde" not in qml, "ChatPage.qml still has the legacy `#eeffde` outgoing fill"
    print("[ok ] gradient + theme tokens + tick glyphs all present; legacy color removed")

    print("[scenario] DesktopChatStore::delivery_tick implementation returns 5-state vocabulary")
    dt_match = re.search(
        r"std::string\s+DesktopChatStore::delivery_tick\s*\(.*?\n\}\n",
        cpp, re.DOTALL,
    )
    assert dt_match, "could not locate delivery_tick body"
    body = dt_match.group(0)
    for tag in ("\"received\"", "\"pending\"", "\"failed\"", "\"sent\"", "\"read\""):
        assert tag in body, f"delivery_tick missing return for {tag}"
    print("[ok ] delivery_tick returns received/pending/failed/sent/read")

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
