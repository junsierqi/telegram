"""Validator for M147 — TYPING_PULSE wired through the desktop client.

Static analysis on the desktop client + transport sources confirming the
end-to-end typing loop is connected (server fanout was M146; this milestone
ships the UI half):

  1. transport/control_plane_client.h declares
     `AckResult send_typing_pulse(const std::string&, bool)`.
  2. transport/control_plane_client.cpp implements it via send_and_wait
     ("typing_pulse", payload) with a JSON body carrying conversation_id +
     is_typing.
  3. app_desktop/main.cpp:
     - includes <QTimer> + <QJsonDocument>;
     - has a `QTimer* typing_decay_timer_` member with a 5s single-shot
       interval;
     - the composer_'s textEdited signal is wired to a debounced send
       that fires send_typing_pulse(true) at most once every 2s;
     - the push handler intercepts type=="typing_pulse" and calls
       handle_typing_pulse_push BEFORE the store_.apply_push path;
     - handle_typing_pulse_push parses the envelope, suppresses
       self-pulses (sender == current_user_id), gates by selected
       conversation, and toggles typing_indicator_->setActive plus
       restarts the decay timer.

Pure static — runs without Qt.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
CP_H = REPO / "client" / "src" / "transport" / "control_plane_client.h"
CP_CPP = REPO / "client" / "src" / "transport" / "control_plane_client.cpp"
MAIN = REPO / "client" / "src" / "app_desktop" / "main.cpp"


def main() -> int:
    for p in (CP_H, CP_CPP, MAIN):
        if not p.exists():
            print(f"[FAIL] missing {p}")
            return 1
    h = CP_H.read_text(encoding="utf-8")
    cpp = CP_CPP.read_text(encoding="utf-8")
    m = MAIN.read_text(encoding="utf-8")

    print("[scenario] ControlPlaneClient declares + implements send_typing_pulse")
    assert re.search(r"AckResult\s+send_typing_pulse\s*\(", h), \
        "header must declare AckResult send_typing_pulse(...)"
    body = re.search(
        r"AckResult\s+ControlPlaneClient::send_typing_pulse\s*\([^)]*\)\s*\{(?P<b>.*?)\n\}",
        cpp, re.DOTALL,
    )
    assert body, "implementation body not found"
    impl = body.group("b")
    assert "send_and_wait" in impl, "implementation must call send_and_wait"
    assert '"typing_pulse"' in impl, "must dispatch typing_pulse type"
    assert "conversation_id" in impl and "is_typing" in impl, \
        "payload must contain conversation_id + is_typing"
    print("[ok ] transport client ships send_typing_pulse")

    print("[scenario] desktop main.cpp has the typing decay timer + debounce state")
    assert "QTimer* typing_decay_timer_" in m, "typing_decay_timer_ member missing"
    assert "qint64 last_typing_sent_ms_" in m, "last_typing_sent_ms_ member missing"
    assert "typing_decay_timer_->setInterval(5000)" in m, "decay timer must be 5s"
    assert "typing_decay_timer_->setSingleShot(true)" in m, \
        "decay timer must be single-shot"
    print("[ok ] timer + debounce state in place")

    print("[scenario] composer_->textEdited fires the debounced TYPING_PULSE(true)")
    block = re.search(
        r"QObject::connect\s*\(\s*composer_\s*,\s*&QLineEdit::textEdited",
        m,
    )
    assert block, "composer textEdited handler missing"
    # The handler must check the 2s window AND call send_typing_pulse.
    # Find the next 600 chars after the connect to scan its lambda body.
    span = m[block.end():block.end() + 600]
    assert "2000" in span, "debounce window (2s) missing in textEdited handler"
    assert "send_typing_pulse(" in span, \
        "textEdited must dispatch send_typing_pulse"
    print("[ok ] composer drives debounced pulses")

    print("[scenario] push handler intercepts typing_pulse before store apply_push")
    push_block = re.search(
        r'set_push_handler\([^}]+typing_pulse[^}]+handle_typing_pulse_push',
        m, re.DOTALL,
    )
    assert push_block, "push handler must intercept type=='typing_pulse' "\
        "before store_.apply_push"
    print("[ok ] push handler routes typing_pulse to handle_typing_pulse_push")

    print("[scenario] handle_typing_pulse_push parses + activates the indicator")
    body_match = re.search(
        r"void\s+handle_typing_pulse_push\s*\([^)]*\)\s*\{(?P<b>.*?)\n\s{4}\}",
        m, re.DOTALL,
    )
    assert body_match, "handle_typing_pulse_push body not found"
    body = body_match.group("b")
    assert "QJsonDocument::fromJson" in body, "envelope must be parsed via QJsonDocument"
    assert "sender_user_id" in body and "is_typing" in body, \
        "must read sender_user_id + is_typing from the envelope"
    assert "current_user_id()" in body, \
        "must suppress self-pulses by comparing to current_user_id()"
    assert "selected_conversation_id()" in body, \
        "must gate by the selected conversation"
    assert "typing_indicator_->setActive" in body, \
        "must call typing_indicator_->setActive(...)"
    assert "typing_decay_timer_->start" in body, \
        "must restart the decay timer on incoming TRUE pulses"
    print("[ok ] envelope parser + indicator activation + decay restart all wired")

    print("\nAll 5/5 scenarios passed.")
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
