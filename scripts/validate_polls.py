"""Validator for polls (M102).

Polls live as messages — they share the conversation history list with
text messages, attachments, etc. The poll state is embedded as a
sub-object on the message dict.

Scenarios:
  1. create_poll round-trips through conversation_sync. The resulting
     MessageDescriptor has a non-null `poll` with the right options +
     zero votes.
  2. Single-choice vote: bob votes once, tally goes to {1, 0}.
     total_voters increments to 1.
  3. Changing vote: bob votes again on a different option — overwrites,
     total_voters stays at 1, tally moves.
  4. Multi-choice vote: bob picks two options at once — both tally
     up and total_voters is 1.
  5. Single-choice rejecting >1 indices -> POLL_INVALID_OPTION.
  6. Out-of-range option index -> POLL_INVALID_OPTION.
  7. Author closes the poll; subsequent votes -> POLL_CLOSED.
  8. Non-author calling close -> POLL_CLOSE_DENIED.
  9. <2 options on create -> POLL_TOO_FEW_OPTIONS.
 10. Vote on an unknown message_id -> UNKNOWN_MESSAGE.
 11. Vote on a non-poll message -> NOT_A_POLL.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402


def _login(app, user, pw, dev, seq):
    resp = app.dispatch({
        **make_envelope(MessageType.LOGIN_REQUEST, correlation_id=f"corr_l_{seq}", sequence=seq),
        "payload": {"username": user, "password": pw, "device_id": dev},
    })
    assert resp["type"] == "login_response", resp
    return resp["payload"]


def _create(app, sess, conv, q, options, seq, *, multi=False):
    return app.dispatch({
        **make_envelope(MessageType.POLL_CREATE_REQUEST,
                        correlation_id=f"corr_pc_{seq}",
                        session_id=sess["session_id"],
                        actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"conversation_id": conv, "question": q,
                    "options": options, "multiple_choice": multi},
    })


def _vote(app, sess, conv, msg_id, indices, seq):
    return app.dispatch({
        **make_envelope(MessageType.POLL_VOTE_REQUEST,
                        correlation_id=f"corr_pv_{seq}",
                        session_id=sess["session_id"],
                        actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"conversation_id": conv, "message_id": msg_id,
                    "option_indices": indices},
    })


def _close(app, sess, conv, msg_id, seq):
    return app.dispatch({
        **make_envelope(MessageType.POLL_CLOSE_REQUEST,
                        correlation_id=f"corr_pc_{seq}",
                        session_id=sess["session_id"],
                        actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"conversation_id": conv, "message_id": msg_id},
    })


def _sync(app, sess, seq):
    return app.dispatch({
        **make_envelope(MessageType.CONVERSATION_SYNC,
                        correlation_id=f"corr_sync_{seq}",
                        session_id=sess["session_id"],
                        actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"cursors": {}, "versions": {},
                    "history_limits": {}, "before_message_ids": {}},
    })


def _send(app, sess, conv, text, seq):
    return app.dispatch({
        **make_envelope(MessageType.MESSAGE_SEND, correlation_id=f"corr_m_{seq}",
                        session_id=sess["session_id"],
                        actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"conversation_id": conv, "text": text},
    })


def _find_poll_msg(sync_resp, conv_id, msg_id):
    for c in sync_resp["payload"]["conversations"]:
        if c["conversation_id"] != conv_id:
            continue
        for m in c["messages"]:
            if m["message_id"] == msg_id:
                return m
    return None


def scenario_create_then_sync():
    print("[scenario] create poll surfaces in conversation_sync with zero tallies")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    r = _create(app, alice, "conv_alice_bob", "Pick lunch?", ["pizza", "salad"], 2)
    assert r["type"] == "poll_updated", r
    msg_id = r["payload"]["message_id"]
    assert r["payload"]["poll"]["options"] == [
        {"text": "pizza", "vote_count": 0}, {"text": "salad", "vote_count": 0},
    ], r
    sync = _sync(app, alice, 3)
    msg = _find_poll_msg(sync, "conv_alice_bob", msg_id)
    assert msg is not None and msg["poll"] is not None and msg["text"] == "Pick lunch?"
    assert msg["poll"]["total_voters"] == 0
    print("[ok ] poll round-trips through sync")


def scenario_single_choice_vote_and_change():
    print("[scenario] single-choice vote + change-vote keeps total_voters at 1")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    bob = _login(app, "bob", "bob_pw", "dev_b", 2)
    msg_id = _create(app, alice, "conv_alice_bob", "?", ["a", "b"], 3)["payload"]["message_id"]
    r1 = _vote(app, bob, "conv_alice_bob", msg_id, [0], 4)
    assert r1["payload"]["poll"]["options"][0]["vote_count"] == 1
    assert r1["payload"]["poll"]["total_voters"] == 1
    # Change vote
    r2 = _vote(app, bob, "conv_alice_bob", msg_id, [1], 5)
    assert r2["payload"]["poll"]["options"][0]["vote_count"] == 0
    assert r2["payload"]["poll"]["options"][1]["vote_count"] == 1
    assert r2["payload"]["poll"]["total_voters"] == 1, r2
    print("[ok ] vote-then-change keeps total_voters stable")


def scenario_multi_choice_picks_multiple():
    print("[scenario] multiple-choice poll accepts >1 indices in one request")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    bob = _login(app, "bob", "bob_pw", "dev_b", 2)
    msg_id = _create(app, alice, "conv_alice_bob", "?", ["a", "b", "c"], 3, multi=True)["payload"]["message_id"]
    r = _vote(app, bob, "conv_alice_bob", msg_id, [0, 2], 4)
    poll = r["payload"]["poll"]
    assert poll["options"][0]["vote_count"] == 1
    assert poll["options"][1]["vote_count"] == 0
    assert poll["options"][2]["vote_count"] == 1
    assert poll["total_voters"] == 1
    print("[ok ] multi-choice vote tallies both options")


def scenario_single_choice_rejects_multi():
    print("[scenario] single-choice poll rejects >1 indices -> POLL_INVALID_OPTION")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    bob = _login(app, "bob", "bob_pw", "dev_b", 2)
    msg_id = _create(app, alice, "conv_alice_bob", "?", ["a", "b"], 3)["payload"]["message_id"]
    r = _vote(app, bob, "conv_alice_bob", msg_id, [0, 1], 4)
    assert r["type"] == "error" and r["payload"]["code"] == "poll_invalid_option", r
    print("[ok ] single-choice rejects multi-vote")


def scenario_out_of_range_index():
    print("[scenario] out-of-range index -> POLL_INVALID_OPTION")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    bob = _login(app, "bob", "bob_pw", "dev_b", 2)
    msg_id = _create(app, alice, "conv_alice_bob", "?", ["a", "b"], 3)["payload"]["message_id"]
    r = _vote(app, bob, "conv_alice_bob", msg_id, [99], 4)
    assert r["type"] == "error" and r["payload"]["code"] == "poll_invalid_option", r
    print("[ok ] out-of-range rejected")


def scenario_close_blocks_voting():
    print("[scenario] close + subsequent vote -> POLL_CLOSED")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    bob = _login(app, "bob", "bob_pw", "dev_b", 2)
    msg_id = _create(app, alice, "conv_alice_bob", "?", ["a", "b"], 3)["payload"]["message_id"]
    closed = _close(app, alice, "conv_alice_bob", msg_id, 4)
    assert closed["payload"]["poll"]["closed"] is True
    r = _vote(app, bob, "conv_alice_bob", msg_id, [0], 5)
    assert r["type"] == "error" and r["payload"]["code"] == "poll_closed", r
    print("[ok ] closed poll rejects votes")


def scenario_only_author_can_close():
    print("[scenario] non-author calling close -> POLL_CLOSE_DENIED")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    bob = _login(app, "bob", "bob_pw", "dev_b", 2)
    msg_id = _create(app, alice, "conv_alice_bob", "?", ["a", "b"], 3)["payload"]["message_id"]
    r = _close(app, bob, "conv_alice_bob", msg_id, 4)
    assert r["type"] == "error" and r["payload"]["code"] == "poll_close_denied", r
    print("[ok ] only author may close the poll")


def scenario_too_few_options():
    print("[scenario] poll with <2 options -> POLL_TOO_FEW_OPTIONS")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    r = _create(app, alice, "conv_alice_bob", "?", ["only"], 2)
    assert r["type"] == "error" and r["payload"]["code"] == "poll_too_few_options", r
    print("[ok ] single-option poll rejected")


def scenario_unknown_message():
    print("[scenario] vote on unknown message -> UNKNOWN_MESSAGE")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    r = _vote(app, alice, "conv_alice_bob", "msg_does_not_exist", [0], 2)
    assert r["type"] == "error" and r["payload"]["code"] == "unknown_message", r
    print("[ok ] unknown message rejected")


def scenario_non_poll_message():
    print("[scenario] vote on a non-poll message -> NOT_A_POLL")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_a", 1)
    sent = _send(app, alice, "conv_alice_bob", "just text", 2)
    msg_id = sent["payload"]["message_id"]
    r = _vote(app, alice, "conv_alice_bob", msg_id, [0], 3)
    assert r["type"] == "error" and r["payload"]["code"] == "not_a_poll", r
    print("[ok ] non-poll vote rejected")


def main() -> int:
    scenarios = [
        scenario_create_then_sync,
        scenario_single_choice_vote_and_change,
        scenario_multi_choice_picks_multiple,
        scenario_single_choice_rejects_multi,
        scenario_out_of_range_index,
        scenario_close_blocks_voting,
        scenario_only_author_can_close,
        scenario_too_few_options,
        scenario_unknown_message,
        scenario_non_poll_message,
    ]
    for s in scenarios:
        s()
    print(f"\nAll {len(scenarios)}/{len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
